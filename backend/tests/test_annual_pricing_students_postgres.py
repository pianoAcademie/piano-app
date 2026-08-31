"""Real DB round trips, isolated and rolled back; no production access."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from tests.test_annual_pricing_postgres import case, URL
from app.models.quote import Prospect, Quote, QuoteLine, PricingActivityPrice
from app.models.user import User, ClientKind
from app.models.catalog import CourseType
from app.models.annual_pricing import AnnualStudentEnrollment
from app.api.routes.annual_pricing import context
from app.services.annual_pricing_review import prepare_review, apply_review, check_review_current
from app.services.annual_pricing_students import (
    quote_students, family_members, family_reference, review_client_id,
    student_enrollment, save_enrollment,
)

pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


def one_course(case, name, base=38, audience="CHILD"):
    db, q, lines, request, actor, ref = case
    db.delete(lines.pop())
    activity = db.get(CourseType, lines[0].activity_id)
    activity.name = name
    lines[0].title = name
    lines[0].unit_price_ttc = base
    lines[0].amount_ttc = Decimal(base) * lines[0].quantity
    q.total_ttc = lines[0].amount_ttc
    price = db.scalar(select(PricingActivityPrice).where(PricingActivityPrice.catalog_id == q.pricing_catalog_id))
    price.unit_price_ttc, price.student_category = base, audience
    request.audience = audience
    db.flush()
    return activity


def prospect_case(case, *, adult=False):
    db, q, _, request, _, _ = case
    parent = Prospect(first_name="Responsable", last_name="Test", email=f"{uuid4()}@example.invalid", meta={"prospect_type":"adult"})
    db.add(parent); db.flush()
    person = parent if adult else Prospect(first_name="Paul", last_name="Test", email=parent.email,
        parent_prospect_id=parent.id, meta={"prospect_type":"child", "child":{"birth_date":"2019-01-01"}})
    db.add(person); db.flush()
    q.client_id, q.prospect_id, q.context_type = None, person.id, "acquisition"
    request.student_id, request.family_reference_child_id = person.id, None
    db.flush()
    return person, parent


def apply_and_reload(case):
    db, q, lines, request, actor, _ = case
    preview = prepare_review(db, q, lines, request)
    request.expected_version = preview["version"]
    review = apply_review(db, q, lines, request, actor)
    db.flush(); db.expire_all()
    fresh = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)))
    check_review_current(db, q, fresh)
    assert sum(l.amount_ttc for l in fresh) == q.total_ttc == Decimal(preview["total"])
    return preview, review, fresh


def test_paul_prospect_initiation_preserves_manual_discount_and_products(case):
    db, q, lines, request, actor, _ = case
    one_course(case, "Initiation au piano")
    person, parent = prospect_case(case)
    lines[0].quantity, lines[0].amount_ttc = 31, 1178
    q.total_ttc = 1291
    for title, kind, qty, unit, total in [("Remise fidélité", "discount", 31, -2, -62), ("Kit Initiation", "item", 1, 150, 150), ("Partition degré 1", "item", 1, 25, 25)]:
        l = QuoteLine(quote_id=q.id, line_type=kind, line_category="product", title=title,
            pricing_unit="unit", quantity=qty, vat_rate=20, unit_price_ttc=unit, unit_price_ht=Decimal(unit)/Decimal("1.2"),
            unit_vat_amount=Decimal(unit)/6, amount_ht=Decimal(total)/Decimal("1.2"), amount_vat=Decimal(total)/6, amount_ttc=total)
        db.add(l); lines.append(l)
    db.flush()
    before = {l.id:(l.quantity,l.unit_price_ttc,l.amount_ttc) for l in lines}
    users_before = db.scalar(select(func.count()).select_from(User))
    loaded = context(q.id, db, actor)
    assert loaded["students"] == [{"id":str(person.id),"label":"Paul Test","kind":"PROSPECT","audiences":["CHILD","TEEN"]}]
    assert loaded["lines"][0]["title"] == "Initiation au piano"
    assert q.total_ttc == 1291 and person.linked_client_id is None
    with pytest.raises(HTTPException, match="manuelles"):
        prepare_review(db,q,lines,request)
    request.manual_discount_policy = "KEEP"
    request.enrollment_status, request.enrollment_note = "RETURNING_MANUAL", "Ancienne inscription vérifiée dans le dossier."
    preview = prepare_review(db,q,lines,request)
    assert student_enrollment(db,person.id,q.school_year_label)["status"] == "AUTO"
    assert preview["total"] == "1291.00"
    _, review, fresh = apply_and_reload(case)
    assert before == {l.id:(l.quantity,l.unit_price_ttc,l.amount_ttc) for l in fresh}
    assert db.scalar(select(func.count()).select_from(User)) == users_before
    assert db.get(AnnualStudentEnrollment,(person.id,q.school_year_label)) is None
    assert student_enrollment(db,person.id,q.school_year_label)["status"] == "RETURNING_MANUAL"
    assert review["student_kind"] == "PROSPECT"
    assert person.linked_client_id is None
    assert context(q.id, db, actor)["review_error"] is None


@pytest.mark.parametrize("name,base,family,loyalty,expected", [
    ("Initiation au piano",38,False,True,"36.00"),
    ("Initiation au piano",38,True,False,"34.00"),
    ("Éveil musical",22,True,True,"20.00"),
    ("Éveil musical",22,False,True,"22.00"),
])
def test_child_activities_apply_existing_policies(case,name,base,family,loyalty,expected):
    db,q,lines,req,_,_ = case
    one_course(case,name,base)
    if not family:
        req.family_reference_child_id=None
    if loyalty:
        req.enrollment_status,req.enrollment_note="RETURNING_MANUAL","Ancienne inscription annuelle vérifiée."
    preview,_,_=apply_and_reload(case)
    assert preview["decisions"][0]["net"] == expected


@pytest.mark.parametrize("prospect",[False,True])
def test_adult_mixed_course_uses_adult_catalog_without_child_discounts(case,prospect):
    db,q,lines,req,actor,_=case
    one_course(case,"Cours collectifs ado/adultes",45,"ADULT")
    if prospect:
        person,_=prospect_case(case,adult=True)
    else:
        person=db.get(User,req.student_id)
        person.client_kind,person.birth_date=ClientKind.ADULT,date(1990,1,1)
        req.family_reference_child_id=None
    db.flush()
    loaded=context(q.id,db,actor)
    assert loaded["students"][0]["audiences"]==["ADULT"]
    req.enrollment_status,req.enrollment_note="RETURNING_MANUAL","Ancienne inscription annuelle confirmée."
    preview,_,_=apply_and_reload(case)
    assert preview["decisions"][0]["base"]=="45.00"
    assert preview["decisions"][0]["net"]=="45.00"
    assert preview["decisions"][0]["pricing"]["components"]==[]


def test_teen_on_mixed_course_uses_minor_tariff_and_teen_discount(case):
    db,_,_,req,_,_=case
    one_course(case,"Cours collectifs ado/adultes")
    db.get(User,req.student_id).birth_date=date(2011,1,1)
    req.audience="TEEN"
    preview,_,_=apply_and_reload(case)
    assert preview["decisions"][0]["net"]=="36.00"


def test_cannot_apply_child_rates_to_adult_or_adult_to_minor(case):
    db,q,lines,req,_,_=case
    one_course(case,"Cours collectifs ado/adultes")
    req.audience="ADULT";req.family_reference_child_id=None
    with pytest.raises(HTTPException,match="mineur"):
        prepare_review(db,q,lines,req)
    person=db.get(User,req.student_id)
    person.client_kind,person.birth_date=ClientKind.ADULT,None
    req.audience="TEEN"
    with pytest.raises(HTTPException,match="adulte"):
        prepare_review(db,q,lines,req)


def test_foreign_prospect_or_sibling_is_not_selectable_on_child_quote(case):
    db,q,lines,req,_,_=case
    one_course(case,"Initiation au piano")
    person,parent=prospect_case(case)
    other=Prospect(first_name="Paul",last_name="Test",email=parent.email,
        parent_prospect_id=parent.id,meta={"prospect_type":"child"})
    db.add(other);db.flush()
    assert [s.id for s in quote_students(db,q)]==[person.id]
    req.student_id=other.id
    with pytest.raises(HTTPException,match="rattaché"):
        prepare_review(db,q,lines,req)


def test_prospect_family_reference_persists_without_fk_or_client_creation(case):
    db,q,lines,req,actor,_=case
    one_course(case,"Éveil musical",22)
    person,parent=prospect_case(case)
    sibling=Prospect(first_name="Aîné",last_name="Test",email=parent.email,parent_prospect_id=parent.id,meta={"prospect_type":"child"})
    db.add(sibling);db.flush()
    sibling_quote=Quote(quote_number=str(uuid4()),context_type="acquisition",prospect_id=sibling.id,
        quote_type="forfait",school_year_label=q.school_year_label,total_ttc=100)
    db.add(sibling_quote);db.flush()
    req.family_reference_child_id=sibling.id
    preview,_,fresh=apply_and_reload(case)
    assert preview["decisions"][0]["net"]=="20.00"
    assert family_reference(db,parent.id,q.school_year_label).child_id==sibling.id
    assert context(q.id,db,actor)["references"][str(person.id)]==str(sibling.id)
    sibling_quote.status="cancelled";db.flush()
    with pytest.raises(HTTPException,match="engagement"):
        check_review_current(db,q,fresh)


def test_conversion_keeps_review_identity_and_enrollment_without_duplicate(case):
    db,q,lines,req,actor,_=case
    one_course(case,"Initiation au piano")
    person,parent=prospect_case(case)
    req.enrollment_status,req.enrollment_note="RETURNING_MANUAL","Ancienne inscription vérifiée dans le dossier."
    _,review,fresh=apply_and_reload(case)
    assert review_client_id(db,review) is None
    client=db.get(User,case[-1].client_id)
    person.linked_client_id=client.id;db.flush()
    assert review_client_id(db,review)==client.id
    assert student_enrollment(db,client.id,q.school_year_label)["status"]=="RETURNING_MANUAL"
    assert quote_students(db,q)[0].id==client.id
    with pytest.raises(HTTPException,match="rattachement"):
        check_review_current(db,q,fresh)
    q.sent_at=datetime.now(timezone.utc)
    check_review_current(db,q,fresh)  # Accepted decision is frozen across conversion.


def test_changed_prospect_birth_or_parent_rejects_stale_preview(case):
    db,q,lines,req,_,_=case
    one_course(case,"Initiation au piano")
    person,parent=prospect_case(case)
    req.expected_version=prepare_review(db,q,lines,req)["version"]
    person.meta={**person.meta,"child":{"birth_date":"2018-01-01"}};db.flush()
    with pytest.raises(HTTPException,match="changé"):
        apply_review(db,q,lines,req,case[4])


def test_parent_quote_lists_self_and_explicit_children_without_duplicates(case):
    db,q,_,_,_,_=case
    child,parent=prospect_case(case)
    q.prospect_id=parent.id
    assert {p.id for p in quote_students(db,q)}=={parent.id,child.id}
    client=db.get(User,case[-1].client_id)
    child.linked_client_id=client.id;db.flush()
    assert {p.id for p in quote_students(db,q)}=={parent.id,client.id}


def test_mixed_client_prospect_family_keeps_reference_after_conversion(case):
    db,q,lines,req,actor,_=case
    one_course(case,"Initiation au piano")
    child,parent=prospect_case(case)
    parent.linked_client_id=actor.id
    sibling=Prospect(first_name="Référence",last_name="Test",email=parent.email,parent_prospect_id=parent.id,meta={"prospect_type":"child"})
    db.add(sibling);db.flush()
    db.add(Quote(quote_number=str(uuid4()),context_type="acquisition",prospect_id=sibling.id,
        quote_type="forfait",school_year_label=q.school_year_label,total_ttc=100));db.flush()
    req.family_reference_child_id=sibling.id
    _,_,fresh=apply_and_reload(case)
    assert family_reference(db,actor.id,q.school_year_label).child_id==sibling.id
    sibling.linked_client_id=case[-1].client_id;db.flush()
    # Conversion of the reference doesn't invalidate the explicit sibling link.
    assert context(q.id,db,actor)["references"][str(child.id)]==str(sibling.linked_client_id)
    check_review_current(db,q,fresh)


def test_missing_adult_catalog_never_falls_back_to_child_price(case):
    db,q,lines,req,_,_=case
    one_course(case,"Cours collectifs ado/adultes")
    person=db.get(User,req.student_id)
    person.client_kind,person.birth_date=ClientKind.ADULT,date(1990,1,1)
    req.audience,req.family_reference_child_id="ADULT",None
    with pytest.raises(HTTPException,match="Tarif annuel publié manquant"):
        prepare_review(db,q,lines,req)


def test_family_reference_from_another_household_is_rejected(case):
    db,q,lines,req,_,_=case
    one_course(case,"Initiation au piano")
    prospect_case(case)
    unrelated=Prospect(first_name="Autre",last_name="Test",email=f"{uuid4()}@example.invalid",meta={"prospect_type":"child"})
    db.add(unrelated);db.flush()
    req.family_reference_child_id=unrelated.id
    with pytest.raises(HTTPException,match="même famille"):
        prepare_review(db,q,lines,req)


@pytest.mark.parametrize("addressed_to_parent",[False,True])
def test_real_client_transformation_resolves_reviewed_prospect_and_reuses_it(case,addressed_to_parent):
    from app.models.quote import QuoteAcceptanceFollowup
    from app.api.routes.quotes import _resolve_followup_clients
    db,q,lines,req,actor,_=case
    one_course(case,"Initiation au piano")
    child,parent=prospect_case(case)
    parent.linked_client_id=actor.id
    if addressed_to_parent:
        q.prospect_id=parent.id
    db.flush()
    _,review,_=apply_and_reload(case)
    followup=QuoteAcceptanceFollowup(quote_id=q.id)
    db.add(followup);db.flush()
    created_users,created_links=[],[]
    kwargs=dict(db=db,quote=q,followup=followup,
        transformation_payload={"clientResolution":{"mode":"new_child_existing_parent","selectedParentClientId":str(actor.id)}},
        user_snapshots={},prospect_snapshots={},created_user_ids=created_users,created_family_link_ids=created_links)
    student,billing=_resolve_followup_clients(**kwargs)
    db.flush()
    assert student.first_name==child.first_name and student.birth_date==date(2019,1,1)
    assert student.id==review_client_id(db,review)==child.linked_client_id
    assert billing.id==actor.id and student.id!=billing.id
    assert created_users==[student.id]
    again,_=_resolve_followup_clients(**kwargs)
    assert again.id==student.id and created_users==[student.id]
