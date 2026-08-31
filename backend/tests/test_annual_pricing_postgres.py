"""Opt-in PostgreSQL round trips; isolated database only, fixtures always rolled back."""
import os
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.user import User, ClientKind, UserRole
from app.models.catalog import CourseType, Location, DeliveryMode
from app.models.family import ClientFamilyLink
from app.models.quote import Quote, QuoteLine, PricingCatalog, PricingActivityPrice
from app.models.annual_pricing import AnnualFamilyReference
from app.services.annual_pricing_review import AnnualReviewRequest, prepare_review, apply_review, check_review_current, quote_fingerprint

URL = os.environ.get("ANNUAL_PRICING_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


@pytest.fixture
def case():
    assert URL.rsplit("/", 1)[-1] == "piano_annual_pricing_metadata", "Never run against live data"
    engine = create_engine(URL)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(connection, join_transaction_mode="create_savepoint")
    try:
        def child(name):
            u = User(email=f"{uuid4()}@example.invalid", hashed_password="disabled", role=UserRole.CLIENT,
                     first_name=name, last_name="Test", client_kind=ClientKind.CHILD, birth_date=date(2018, 1, 1))
            db.add(u); db.flush(); return u
        a, b, parent = child("Premier"), child("Second"), child("Parent")
        parent.client_kind = ClientKind.ADULT
        db.add_all([ClientFamilyLink(adult_user_id=parent.id, child_user_id=a.id), ClientFamilyLink(adult_user_id=parent.id, child_user_id=b.id)])
        location = Location(code=str(uuid4()), name="Salle Paris test", city="Paris", timezone="Europe/Paris")
        activity = CourseType(code=str(uuid4()), name="Cours collectif enfants présentiel", service_code="PIANO", mode=DeliveryMode.ONSITE,
                              duration_minutes=60, default_capacity=6, color_hex="#FFFFFF")
        catalog = PricingCatalog(name="Test annual", school_year_label="2026-2027", lifecycle_status="PUBLISHED", is_active=True,
            effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc), published_at=datetime.now(timezone.utc))
        db.add_all([location, activity, catalog]); db.flush()
        db.add(PricingActivityPrice(catalog_id=catalog.id, activity_id=activity.id, location_id=location.id,
            student_category="CHILD", pricing_unit="per_session", price_channel="ANNUAL_FORFAIT", unit_price_ttc=38, currency="EUR", is_active=True))
        def quote(student):
            q = Quote(quote_number=str(uuid4()), context_type="active_client", client_id=student.id, quote_type="forfait",
                school_year_label="2026-2027", location_id=location.id, pricing_catalog_id=catalog.id, currency="EUR", total_ttc=2432)
            db.add(q); db.flush(); return q
        ref_quote, q = quote(a), quote(b)
        lines = []
        for order in (0, 10):
            line = QuoteLine(quote_id=q.id, activity_id=activity.id, line_category="service", line_type="item", title=f"Cours {order}",
                pricing_unit="session", quantity=32, vat_rate=20, unit_price_ttc=38, unit_price_ht=Decimal("31.67"), unit_vat_amount=Decimal("6.33"),
                amount_ht=Decimal("1013.33"), amount_vat=Decimal("202.67"), amount_ttc=1216, duration_minutes=60, sort_order=order,
                meta={"recommendation_key": f"{activity.id}:{order}"})
            db.add(line); lines.append(line)
        db.flush()
        request = AnnualReviewRequest(student_id=b.id, audience="CHILD", primary_line_id=lines[0].id,
            family_reference_child_id=a.id, review_note="Vérification inscription annuelle et catégorie enfant effectuée.")
        db.commit()
        yield db, q, lines, request, parent, ref_quote
    finally:
        db.close(); transaction.rollback(); connection.close(); engine.dispose()


def test_preview_apply_roundtrip_preserves_visible_components(case):
    db, q, lines, request, actor, _ = case
    first = prepare_review(db, q, lines, request)
    assert [d["net"] for d in first["decisions"]] == ["34.00", "29.00"]
    assert first["total"] == "2016.00"
    assert first["version"] == prepare_review(db, q, lines, request)["version"]
    request.expected_version = first["version"]
    review = apply_review(db, q, lines, request, actor)
    db.flush(); db.expire_all()
    fresh_lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    assert sum(l.amount_ttc for l in fresh_lines) == q.total_ttc == 2016
    assert len([l for l in fresh_lines if l.line_type == "discount"]) == 3
    check_review_current(db, q, fresh_lines)
    assert db.get(AnnualFamilyReference, (actor.id, "2026-2027")).child_id == request.family_reference_child_id
    assert quote_fingerprint(q, fresh_lines) == quote_fingerprint(q, list(reversed(fresh_lines)))
    from app.services.quotes.quote_documents import render_quote_document_bundle, AUDIENCE_PUBLIC_PAGE, AUDIENCE_CLIENT_PDF
    for audience in (AUDIENCE_PUBLIC_PAGE, AUDIENCE_CLIENT_PDF):
        document = render_quote_document_bundle(db=db, quote=q, lines=fresh_lines, audience=audience)
        assert "Remise famille" in document["body_html"]
        assert "deuxième cours" in document["body_html"]
    fresh_lines[0].quantity += 1
    with pytest.raises(HTTPException, match="changé"):
        check_review_current(db, q, fresh_lines)


def test_family_reference_does_not_depend_on_quote_acceptance(case):
    db, q, lines, request, _, reference_quote = case
    assert reference_quote.status == "created"
    assert prepare_review(db, q, lines, request)["family"] is True
    reference_quote.status = "cancelled"; db.flush()
    with pytest.raises(HTTPException, match="Aucun engagement"):
        prepare_review(db, q, lines, request)


def test_sent_quote_never_changes_and_stale_preview_rejected(case):
    db, q, lines, request, actor, _ = case
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    lines[0].quantity = 31
    with pytest.raises(HTTPException, match="changé"):
        apply_review(db, q, lines, request, actor)
    q.sent_at = datetime.now(timezone.utc)
    with pytest.raises(HTTPException, match="déjà envoyés"):
        prepare_review(db, q, lines, request)


def test_cannot_stack_legacy_discounts(case):
    db, q, lines, request, _, _ = case
    lines.append(QuoteLine(line_type="discount", meta={}))
    with pytest.raises(HTTPException, match="manuelles"):
        prepare_review(db, q, lines, request)


def test_legacy_software_renewal_persists_for_student_and_season(case):
    from app.models.annual_pricing import AnnualStudentEnrollment
    from app.services.annual_enrollment import enrollment_context
    from app.api.routes.annual_pricing import context
    db, q, lines, request, actor, _ = case
    request.family_reference_child_id = request.student_id
    request.enrollment_status = "RETURNING_MANUAL"
    request.enrollment_note = "Ancien logiciel : inscription 2025-2026 vérifiée par administration."
    db.delete(lines.pop()); lines[0].quantity = 31; lines[0].amount_ttc = 1178; q.total_ttc = 1178
    db.flush()
    preview = prepare_review(db, q, lines, request)
    assert preview["total"] == "1116.00"
    assert preview["returning_verified"] is True
    assert preview["enrollment"]["source"] == "ADMIN"
    assert preview["display_lines"][-1]["total"] == "-62.00"
    assert db.get(AnnualStudentEnrollment, (request.student_id, q.school_year_label)) is None  # preview never saves
    request.expected_version = preview["version"]
    apply_review(db, q, lines, request, actor); db.commit(); db.expire_all()
    saved = db.get(AnnualStudentEnrollment, (request.student_id, q.school_year_label))
    assert saved.status == "RETURNING_MANUAL" and saved.evidence["actor_id"] == str(actor.id)
    loaded = context(q.id, db, actor)
    assert loaded["review_error"] is None
    assert loaded["enrollments"][str(request.student_id)]["status"] == "RETURNING_MANUAL"
    assert loaded["review"]["actor_name"]
    assert enrollment_context(db, request.student_id, "2027-2028")["status"] == "AUTO"
    assert enrollment_context(db, request.family_reference_child_id, "2026-2027")["evidence"]["note"] == request.enrollment_note
    other = Quote(quote_number=str(uuid4()), context_type="active_client", client_id=request.student_id,
                  quote_type="forfait", school_year_label="2026-2027", total_ttc=0)
    db.add(other); db.flush()
    assert context(other.id, db, actor)["enrollments"][str(request.student_id)]["status"] == "RETURNING_MANUAL"


def add_manual_discount(db, q, lines):
    line = QuoteLine(quote_id=q.id, line_category="service", line_type="discount", title="Remise fidélité importée",
        pricing_unit="session", quantity=32, vat_rate=20, unit_price_ttc=-2, unit_price_ht=Decimal("-1.67"), unit_vat_amount=Decimal("-0.33"),
        amount_ht=Decimal("-53.33"), amount_vat=Decimal("-10.67"), amount_ttc=-64, sort_order=20, meta={})
    db.add(line); db.flush(); lines.append(line); q.total_ttc -= 64
    return line


@pytest.mark.parametrize("policy", ["KEEP", "REPLACE"])
def test_manual_discount_resolution_is_explicit_atomic_and_totals_match(case, policy):
    db, q, lines, request, actor, _ = case
    manual = add_manual_discount(db, q, lines)
    request.manual_discount_policy = policy
    preview = prepare_review(db, q, lines, request)
    assert sum(Decimal(l["total"]) for l in preview["display_lines"]) == Decimal(preview["total"])
    assert db.get(QuoteLine, manual.id) is not None
    assert preview["total"] == ("2368.00" if policy == "KEEP" else "2016.00")
    assert bool(preview["replaced_discounts"]) == (policy == "REPLACE")
    request.expected_version = preview["version"]
    apply_review(db, q, lines, request, actor); db.flush()
    fresh = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    assert sum(l.amount_ttc for l in fresh) == q.total_ttc
    assert (manual in fresh) == (policy == "KEEP")
    check_review_current(db, q, fresh)


def test_renewal_requires_evidence_and_cannot_reuse_changed_preview(case):
    db, q, lines, request, actor, _ = case
    request.enrollment_status = "RETURNING_MANUAL"
    with pytest.raises(HTTPException, match="Justifiez"):
        prepare_review(db, q, lines, request)
    request.enrollment_note = "Ancien logiciel vérifié"
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    request.enrollment_status = "NEW"
    with pytest.raises(HTTPException, match="changé"):
        apply_review(db, q, lines, request, actor)


def test_migrated_renewal_replaces_loyalty_once_and_preserves_products(case):
    from app.services.annual_enrollment import enrollment_context
    db, q, lines, request, actor, reference_quote = case
    db.delete(lines.pop())
    lines[0].quantity = 31
    lines[0].amount_ttc = 1178
    q.total_ttc = 1178
    for title, amount in [("Kit école", 245), ("Partition", 25)]:
        line = QuoteLine(quote_id=q.id, line_category="product", line_type="item", title=title,
            pricing_unit="unit", quantity=1, vat_rate=20, unit_price_ttc=amount,
            unit_price_ht=Decimal(amount) / Decimal("1.2"), unit_vat_amount=Decimal(amount) / 6,
            amount_ht=Decimal(amount) / Decimal("1.2"), amount_vat=Decimal(amount) / 6,
            amount_ttc=amount, sort_order=30, meta={})
        db.add(line); lines.append(line); q.total_ttc += amount
    manual = add_manual_discount(db, q, lines)
    manual.quantity = 31; manual.amount_ttc = -62; q.total_ttc += 2
    request.family_reference_child_id = request.student_id
    request.enrollment_status = "RETURNING_MANUAL"
    request.enrollment_note = "Réinscription confirmée dans l'ancien logiciel."
    request.manual_discount_policy = "REPLACE"
    db.flush()
    preview = prepare_review(db, q, lines, request)
    assert Decimal(preview["total"]) == Decimal(preview["previous_total"]) == Decimal("1386.00")
    assert sum(Decimal(l["total"]) for l in preview["display_lines"]) == Decimal("1386")
    request.expected_version = preview["version"]
    apply_review(db, q, lines, request, actor); db.flush()
    fresh = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    assert len([l for l in fresh if l.line_type == "discount"]) == 1
    assert sum(l.amount_ttc for l in fresh) == q.total_ttc == 1386
    assert enrollment_context(db, reference_quote.client_id, "2026-2027")["status"] == "AUTO"


def test_changed_enrollment_blocks_unsent_review_but_preserves_sent_quote(case):
    from app.models.annual_pricing import AnnualStudentEnrollment
    db, q, lines, request, actor, _ = case
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    apply_review(db, q, lines, request, actor)
    db.add(AnnualStudentEnrollment(student_id=request.student_id, season=q.school_year_label,
        status="RETURNING_MANUAL", evidence={"note": "Correction validée"})); db.flush()
    fresh = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    with pytest.raises(HTTPException, match="réinscription"):
        check_review_current(db, q, fresh)
    q.sent_at = datetime.now(timezone.utc)
    check_review_current(db, q, fresh)


def test_document_generation_blocks_total_mismatch_before_rendering(case):
    from app.api.routes.quotes import _freeze_quote_document_snapshot
    from unittest.mock import patch
    db, q, lines, _, _, _ = case
    q.total_ttc += 1
    with patch("app.api.routes.quotes.render_quote_parts_html") as render:
        with pytest.raises(HTTPException, match="total enregistré"):
            _freeze_quote_document_snapshot(db, quote=q, lines=lines, state="frozen")
        render.assert_not_called()


@pytest.mark.parametrize("named_type", ["Forfait 2026-2027", "FORFAIT_2026_2027", "Custom annual tuition"])
def test_named_annual_quote_types_use_linked_formula(case, named_type):
    from app.models.quote import QuoteType
    from app.models.plan import Plan, PlanKind
    db, q, lines, request, _, reference = case
    plan = Plan(code=str(uuid4()), name="Année 2026-2027", kind=PlanKind.FORFAIT)
    db.add(plan); db.flush()
    kind = QuoteType(code=str(uuid4()), name=named_type, formula_id=plan.id)
    db.add(kind); db.flush()
    q.quote_type = named_type
    q.quote_type_id = kind.id
    reference.quote_type = named_type
    reference.quote_type_id = kind.id
    db.flush()
    assert prepare_review(db, q, lines, request)["total"] == "2016.00"


def test_named_pack_is_not_an_annual_quote(case):
    from app.models.quote import QuoteType
    from app.models.plan import Plan, PlanKind
    db, q, lines, request, _, _ = case
    plan = Plan(code=str(uuid4()), name="Carnet", kind=PlanKind.PACK)
    db.add(plan); db.flush()
    kind = QuoteType(code="FORFAIT_2026_2027", name="Forfait 2026-2027", formula_id=plan.id)
    db.add(kind); db.flush()
    q.quote_type_id = kind.id
    with pytest.raises(HTTPException, match="uniquement le forfait"):
        prepare_review(db, q, lines, request)


def test_reviewed_discounts_never_collapse_into_legacy_activity_wide_rates(case):
    from types import SimpleNamespace
    from app.api.routes.quotes import _apply_followup_forfait_discount_rows
    from app.models.plan import PlanKind
    db, q, lines, request, actor, _ = case
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    apply_review(db, q, lines, request, actor)
    db.flush()
    discounts = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id, QuoteLine.line_type == "discount")).all()
    rows = [{"rowId": f"extra-{d.id}", "sourceLineId": str(d.id), "type": "discount", "amountTtc": str(d.amount_ttc)} for d in discounts]
    consumed = _apply_followup_forfait_discount_rows(db, quote=q, subscription=SimpleNamespace(id=uuid4()),
        plan=SimpleNamespace(kind=PlanKind.FORFAIT), transformation_payload={"billingResolution": {"rows": rows}})
    assert consumed == {r["rowId"] for r in rows}
    # The fake subscription ID has no row in the DB: attempting any legacy write would fail.
    db.flush()


def test_review_invalidates_after_exceptional_financial_adjustment(case):
    db, q, lines, request, actor, _ = case
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    apply_review(db, q, lines, request, actor)
    db.flush()
    fresh = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    q.meta = {**q.meta, "financial_adjustment": {"amount_ttc": "5.00"}}
    with pytest.raises(HTTPException, match="changé"):
        check_review_current(db, q, fresh)


def test_family_evidence_checked_again_before_sending(case):
    db, q, lines, request, actor, reference = case
    request.expected_version = prepare_review(db, q, lines, request)["version"]
    apply_review(db, q, lines, request, actor)
    reference.status = "cancelled"
    db.flush()
    fresh = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == q.id)).all()
    with pytest.raises(HTTPException, match="engagement annuel"):
        check_review_current(db, q, fresh)


@pytest.mark.parametrize("filename, table", [
    ("20260830_0230_annual_pricing_decisions.py", "annual_family_references"),
    ("20260831_0231_student_enrollment_evidence.py", "annual_student_enrollments"),
])
def test_migration_up_down_is_additive(case, filename, table):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    db, q, _, _, _, _ = case
    path = Path(__file__).parents[1] / "alembic/versions" / filename
    spec = importlib.util.spec_from_file_location("annual_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    connection = db.connection()
    original_total = q.total_ttc
    with Operations.context(MigrationContext.configure(connection)):
        module.downgrade()
        assert table not in inspect(connection).get_table_names()
        module.upgrade()
    assert "annual_pricing_terms" in {c["name"] for c in inspect(connection).get_columns("client_plan_subscriptions")}
    assert table in inspect(connection).get_table_names()
    db.expire(q)
    assert q.total_ttc == original_total


def setup_move(case):
    from app.models.catalog import CourseSession, Booking, BookingStatus
    from app.models.plan import Plan, PlanKind, ClientPlanSubscription
    from app.services.client_pricing import compute_contract_price, PricingChannel, booking_snapshot_fields
    db, quote, lines, req, actor, _ = case
    plan = Plan(code=str(uuid4()), name="Annual test", kind=PlanKind.FORFAIT)
    db.add(plan); db.flush()
    start = datetime.now(timezone.utc) + timedelta(days=30)
    subscription = ClientPlanSubscription(user_id=req.student_id, plan_id=plan.id, started_at=start-timedelta(days=10), ends_at=start+timedelta(days=60))
    db.add(subscription); db.flush()
    sources, targets, bookings = [], [], []
    source_group, target_group = uuid4(), uuid4()
    for week in (0, 1):
        def slot(offset, group):
            at = start+timedelta(days=week*7, hours=offset)
            s = CourseSession(course_type_id=lines[0].activity_id, location_id=quote.location_id, title="Test move",
                start_at_utc=at, end_at_utc=at+timedelta(hours=1), capacity_max=6,
                recurrence_group_id=group, timezone="Europe/Paris", auto_cancel_deadline_utc=at-timedelta(hours=1))
            db.add(s); db.flush(); return s
        source, target = slot(0, source_group), slot(2, target_group)
        price = compute_contract_price(channel=PricingChannel.QUOTE, amount_excl_vat="28.33", vat_rate=20, vat_amount="5.67",
            total_incl_vat=34, currency="EUR", source="accepted-quote:test", version="test-price")
        booking = Booking(session_id=source.id, user_id=req.student_id, client_plan_subscription_id=subscription.id,
            status=BookingStatus.BOOKED, **booking_snapshot_fields(price))
        db.add(booking); sources.append(source); targets.append(target); bookings.append(booking)
    db.commit()
    return db, actor, sources, targets, bookings


def test_series_move_is_atomic_when_later_slot_is_full(case):
    from app.api.routes.admin import preview_planning_reorganization_booking_move, move_planning_reorganization_booking
    from app.schemas.admin import AdminPlanningReorganizationMovePreviewRequest, AdminPlanningReorganizationMoveRequest
    db, actor, sources, targets, bookings = setup_move(case)
    targets[1].capacity_max = 0; db.commit()
    preview = preview_planning_reorganization_booking_move(AdminPlanningReorganizationMovePreviewRequest(
        booking_id=bookings[0].id, target_session_id=targets[0].id, scope="series_future"), db=db, _=actor)
    with pytest.raises(HTTPException, match="Aucun déplacement"):
        move_planning_reorganization_booking(AdminPlanningReorganizationMoveRequest(booking_id=bookings[0].id,
            target_session_id=targets[0].id, scope="series_future", price_policy="keep_source", expected_version=preview.version), db=db, actor=actor)
    db.expire_all()
    assert [b.session_id for b in bookings] == [s.id for s in sources]


def test_neutral_move_preserves_ids_money_and_writes_change_history(case):
    from app.api.routes.admin import preview_planning_reorganization_booking_move, move_planning_reorganization_booking
    from app.models.client_record import StudentQuoteChange
    from app.schemas.admin import AdminPlanningReorganizationMovePreviewRequest, AdminPlanningReorganizationMoveRequest, AdminStudentQuoteChangeOut
    db, actor, sources, targets, bookings = setup_move(case)
    from app.models.plan import ClientPlanSubscription
    from app.services.annual_contracts import bind_contract_course, contract_price_for_session
    from app.services.annual_discounts import AnnualEligibility, annual_discount_price
    subscription = db.get(ClientPlanSubscription, bookings[0].client_plan_subscription_id)
    price = annual_discount_price(base=Decimal(38), vat_rate=Decimal(20), eligibility=AnnualEligibility("PARIS", "CHILD", "COLLECTIVE_ONSITE", True))
    decision = {"course_key": "move-term", "activity_id": str(sources[0].course_type_id), "location_id": str(sources[0].location_id),
        "duration_minutes": 60, "quantity": "2", "version": "test-price", "pricing": price.snapshot_breakdown(), "base": "38"}
    bind_contract_course(subscription, decision, sources)
    db.commit()
    ids = [b.id for b in bookings]
    preview = preview_planning_reorganization_booking_move(AdminPlanningReorganizationMovePreviewRequest(
        booking_id=bookings[0].id, target_session_id=targets[0].id, scope="series_future"), db=db, _=actor)
    result = move_planning_reorganization_booking(AdminPlanningReorganizationMoveRequest(booking_id=bookings[0].id,
        target_session_id=targets[0].id, scope="series_future", price_policy="keep_source", expected_version=preview.version), db=db, actor=actor)
    assert result.moved_count == 2 and result.skipped_count == 0
    db.expire_all()
    assert [b.id for b in bookings] == ids
    assert [b.session_id for b in bookings] == [s.id for s in targets]
    assert all(b.total_incl_vat_snapshot == 34 and b.price_book_version_snapshot == "test-price" for b in bookings)
    for target in targets:
        assert contract_price_for_session(subscription, target, now=datetime.now(timezone.utc)).total_incl_vat == 34
    with pytest.raises(HTTPException):
        contract_price_for_session(subscription, sources[0], now=datetime.now(timezone.utc))
    change = db.scalar(select(StudentQuoteChange).where(StudentQuoteChange.student_user_id == bookings[0].user_id))
    assert change.change_type == "SLOT_CHANGE" and change.financial_impact_ttc == 0 and change.billing_action == "NONE"
