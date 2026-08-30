from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unicodedata
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.annual_pricing import AnnualFamilyReference
from app.models.catalog import CourseType, Location
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.quote import Quote, QuoteLine
from app.models.user import User, ClientKind
from app.services.annual_discounts import AnnualEligibility, annual_discount_price, POLICY_VERSION
from app.services.client_pricing import build_price_version, split_tax
from app.services.pricing_catalog import resolve_catalog_activity_price

KEY = "annual_pricing_review"


class AnnualReviewRequest(BaseModel):
    student_id: UUID
    audience: Literal["CHILD", "TEEN"]
    primary_line_id: UUID | None = None
    primary_contract_course_key: str | None = None
    family_reference_child_id: UUID | None = None
    replace_family_reference: bool = False
    review_note: str = Field(min_length=10, max_length=2000)
    expected_version: str | None = None


def fail(message: str):
    raise HTTPException(409, message)


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value or "").lower()) if not unicodedata.combining(c))


def quote_fingerprint(quote, lines):
    def numeric(value):
        return str(Decimal(str(value or 0)).quantize(Decimal("0.001")))
    return build_price_version("quote-review", season=quote.school_year_label, client=quote.client_id,
        location=quote.location_id, catalog=quote.pricing_catalog_id, currency=quote.currency,
        prospect=quote.prospect_id, total=numeric(quote.total_ttc),
        adjustment=(quote.meta or {}).get("financial_adjustment"),
        calendar=quote.calendar_snapshot, lines=[{
            "id": str(l.id), "activity": l.activity_id, "quantity": numeric(l.quantity),
            "price": numeric(l.unit_price_ttc), "total": numeric(l.amount_ttc), "vat": numeric(l.vat_rate),
            "meta": l.meta, "title": l.title, "kind": l.line_type,
            "unit": l.pricing_unit, "duration": l.duration_minutes, "category": l.line_category,
        } for l in sorted(lines, key=lambda row: str(row.id))])


def family_members(db, student_id):
    """Connected family graph: both guardians share one reference, never separate discounts."""
    children, adults = {student_id}, set()
    while True:
        old = (len(children), len(adults))
        adults.update(db.scalars(select(ClientFamilyLink.adult_user_id).where(ClientFamilyLink.child_user_id.in_(children))).all())
        if adults:
            children.update(db.scalars(select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id.in_(adults))).all())
        if old == (len(children), len(adults)):
            break
    return children, adults


def quote_students(db, quote):
    from app.models.quote import Prospect
    client_id = quote.client_id
    if not client_id and quote.prospect_id:
        prospect = db.get(Prospect, quote.prospect_id)
        client_id = prospect.linked_client_id if prospect else None
    if not client_id:
        return []
    ids = {client_id}
    ids.update(db.scalars(select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == client_id)).all())
    return db.scalars(select(User).where(User.id.in_(ids), User.client_kind == ClientKind.CHILD).order_by(User.last_name, User.first_name)).all()


def activity_family(activity):
    label = normalized(activity.name)
    if any(word in label for word in ("essai", "trial", "solfege", "masterclass")):
        return None
    if "eveil" in label:
        return "MUSICAL_AWAKENING"
    if "collectif" in label and "ligne" not in label:
        return "COLLECTIVE_ONSITE"
    return None


def reviewed_lines(db, quote, lines):
    result = []
    for line in lines:
        if line.line_type != "item" or line.line_category != "service" or not line.activity_id or Decimal(line.amount_ttc) <= 0:
            continue
        activity = db.get(CourseType, line.activity_id)
        family = activity_family(activity) if activity else None
        if family:
            result.append((line, activity, family))
    return result


def check_review_current(db, quote, lines):
    review = (quote.meta or {}).get(KEY)
    if not review:
        return
    if review.get("fingerprint") != quote_fingerprint(quote, lines):
        fail("Le devis a changé depuis la vérification tarifaire. Recalculez les remises dans Lignes facturées avant envoi ou intégration.")
    # Sent documents keep their decision even if the family graph later changes.
    if quote.sent_at:
        return
    for guardian_id in review.get("guardian_ids", []):
        reference = db.get(AnnualFamilyReference, (UUID(guardian_id), quote.school_year_label))
        if not reference or str(reference.child_id) != review.get("family_reference_child_id"):
            fail("L'enfant de référence de la famille a changé : vérifiez de nouveau les remises.")
    reference_id = review.get("family_reference_child_id")
    if reference_id and reference_id != review.get("student_id"):
        if not reference_has_engagement(db, quote, UUID(reference_id)):
            fail("L'engagement annuel de l'enfant de référence n'est plus disponible : revérifiez la remise famille avant envoi.")


def reference_has_engagement(db, quote, reference_id):
    subscription = db.scalar(select(ClientPlanSubscription.id).join(Plan).where(
        ClientPlanSubscription.user_id == reference_id, Plan.kind == PlanKind.FORFAIT,
        ClientPlanSubscription.started_at < datetime(2027, 8, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.ends_at >= datetime(2026, 9, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
    ).limit(1))
    quotes = db.scalars(select(Quote).where(Quote.school_year_label == quote.school_year_label,
        Quote.quote_type == "forfait", Quote.total_ttc > 0,
        Quote.status.in_(["created", "sent", "approved", "accepted"]), Quote.id != quote.id)).all()
    return bool(subscription or any(q.client_id == reference_id or (q.meta or {}).get(KEY, {}).get("student_id") == str(reference_id) for q in quotes))


def prepare_review(db: Session, quote: Quote, lines: list[QuoteLine], request: AnnualReviewRequest):
    if quote.sent_at or quote.approved_at or quote.status != "created":
        fail("Les devis déjà envoyés ou acceptés sont conservés. Créez une révision pour changer le prix.")
    if quote.quote_type != "forfait" or quote.school_year_label != "2026-2027" or quote.currency != "EUR":
        fail("Ces règles concernent uniquement le forfait annuel 2026-2027 en EUR.")
    adjustment = (quote.meta or {}).get("financial_adjustment") or {}
    if Decimal(str(adjustment.get("amount_ttc") or 0)) != 0:
        fail("Ce devis comporte un ajustement financier exceptionnel : faites-le vérifier séparément avant de calculer les remises.")
    candidates = quote_students(db, quote)
    student = next((u for u in candidates if u.id == request.student_id), None)
    if student is None:
        fail("Rattachez d'abord l'élève au client du devis. Aucun rapprochement par nom n'est effectué.")
    # Serialize household choices across distinct quotes and both guardians.
    children, guardians = family_members(db, student.id)
    db.scalars(select(User).where(User.id.in_({student.id, *guardians})).order_by(User.id).with_for_update()).all()
    birth = student.birth_date
    if birth and date(2026, 9, 1).year - birth.year - ((9, 1) < (birth.month, birth.day)) >= 18:
        fail("La fiche élève indique un adulte : les remises enfant/adolescent ne peuvent pas être attribuées.")
    reference_id = request.family_reference_child_id
    if reference_id and (reference_id not in children or not guardians):
        fail("L'enfant de référence doit appartenir à la même famille vérifiée.")
    references = db.scalars(select(AnnualFamilyReference).where(
        AnnualFamilyReference.guardian_id.in_(guardians), AnnualFamilyReference.season == quote.school_year_label,
    ).with_for_update()).all() if guardians else []
    if references and any(row.child_id != reference_id for row in references):
        if not reference_id or not request.replace_family_reference:
            fail("Cette famille possède déjà un enfant de référence. Confirmez explicitement le changement pour les brouillons ou conservez ce choix.")
        sent = db.scalars(select(Quote).where(Quote.school_year_label == quote.school_year_label, Quote.sent_at.is_not(None))).all()
        if any(set((q.meta or {}).get(KEY, {}).get("guardian_ids", [])) & {str(i) for i in guardians} for q in sent):
            fail("Une décision de cette famille a déjà été envoyée : l'enfant de référence est figé pour cette saison. Une révision coordonnée est nécessaire.")
    if reference_id:
        reference_user = db.get(User, reference_id)
        if not reference_user or reference_user.client_kind != ClientKind.CHILD:
            fail("L'enfant de référence doit être une fiche enfant.")
    family = bool(reference_id and reference_id != student.id)
    if family:
        if not reference_has_engagement(db, quote, reference_id):
            fail("Préparez d'abord le devis annuel de l'enfant de référence (son acceptation n'est pas nécessaire), ou rattachez son contrat annuel. Aucun engagement de cet enfant n'a été retrouvé.")
    previous_subscription = db.scalar(select(ClientPlanSubscription.id).join(Plan).where(
        ClientPlanSubscription.user_id == student.id, Plan.kind == PlanKind.FORFAIT,
        ClientPlanSubscription.started_at < datetime(2026, 8, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.ends_at >= datetime(2025, 9, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
    ).limit(1))
    entries = reviewed_lines(db, quote, lines)
    external_primary = None
    if request.primary_contract_course_key:
        subs = db.scalars(select(ClientPlanSubscription).join(Plan).where(ClientPlanSubscription.user_id == student.id,
            Plan.kind == PlanKind.FORFAIT, ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPlanSubscription.started_at < datetime(2027, 8, 1, tzinfo=timezone.utc),
            ClientPlanSubscription.ends_at >= datetime(2026, 9, 1, tzinfo=timezone.utc))).all()
        external_primary = next((t for sub in subs for t in (sub.annual_pricing_terms or []) if t.get("primary") and t.get("course_key") == request.primary_contract_course_key), None)
        if not external_primary or request.primary_line_id:
            fail("Le cours principal doit être un cours annuel vérifié du même élève, sans double sélection.")
    if not entries or (not external_primary and request.primary_line_id not in {line.id for line, _, _ in entries}):
        fail("Choisissez le premier cours annuel parmi les activités éligibles du devis.")
    primary_family = activity_family(db.get(CourseType, UUID(external_primary["activity_id"]))) if external_primary else next(item[2] for item in entries if item[0].id == request.primary_line_id)
    if (len(entries) > 1 or external_primary) and primary_family != "COLLECTIVE_ONSITE":
        fail("Le premier cours doit être un cours collectif en présentiel pour attribuer une remise deuxième cours.")
    # Existing explicit discounts are never guessed/stacked with this engine.
    legacy = [line for line in lines if line.line_type == "discount" and not (line.meta or {}).get("annual_auto_discount")]
    if legacy:
        fail("Ce devis contient déjà des remises manuelles. Retirez-les après vérification pour éviter un double avantage, puis relancez le calcul.")
    version = quote_fingerprint(quote, lines)
    decisions = []
    for line, activity, family_code in entries:
        if line.pricing_unit != "session" or Decimal(line.quantity) != int(line.quantity):
            fail("Les remises par séance exigent une quantité entière avec l'unité séance.")
        key = str((line.meta or {}).get("recommendation_key") or (line.meta or {}).get("line_recommendation_key") or "")
        sessions = (quote.calendar_snapshot or {}).get("sessions", [])
        matches = [s for s in sessions if (s.get("recommendation_key") == key if key else s.get("activity_id") == str(line.activity_id))]
        locations = {str(s.get("location_id")) for s in matches if s.get("location_id")}
        if not locations and quote.location_id:
            locations = {str(quote.location_id)}
        if len(locations) != 1:
            fail("Le lieu de chaque cours doit être défini sans ambiguïté dans le planning du devis.")
        location = db.get(Location, UUID(next(iter(locations))))
        if not location or location.is_online:
            fail("Les remises collectives concernent les cours en présentiel.")
        site = "BAR_LE_DUC" if location.code == "BAR_LE_DUC" else "PARIS" if normalized(location.city) == "paris" and location.code != "DOMICILE" else "OTHER"
        if "ado" in normalized(activity.name) and request.audience != "TEEN":
            fail("Cette activité est destinée aux adolescents : sélectionnez le profil adolescent.")
        duration = Decimal(line.duration_minutes or activity.duration_minutes) / 60
        catalog = resolve_catalog_activity_price(db, activity_id=activity.id, location_id=location.id,
            student_category="CHILD", channel="ANNUAL_FORFAIT", catalog_id=quote.pricing_catalog_id,
            at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        if not catalog:
            fail(f"Tarif annuel publié manquant pour {activity.name} à {location.name}. Complétez la grille avant calcul.")
        if external_primary and external_primary["location_id"] != str(location.id):
            fail("Le cours principal souscrit est dans un autre lieu : faites vérifier le rattachement avant d'attribuer une remise deuxième cours.")
        try:
            price = annual_discount_price(base=catalog.amount_for_duration(duration),
                eligibility=AnnualEligibility(site, request.audience, family_code, family=family,
                    returning=bool(previous_subscription), second_course=line.id != request.primary_line_id),
                vat_rate=Decimal(line.vat_rate), source=f"quote:{quote.id}:course:{line.id}",
                evidence_version=build_price_version("eligibility", student=student.id, reference=reference_id,
                    primary=request.primary_line_id or request.primary_contract_course_key, prior=previous_subscription, note=request.review_note, catalog=catalog.version))
        except ValueError as exc:
            fail(str(exc))
        decisions.append({"line_id": str(line.id), "course_key": str((line.meta or {}).get("annual_course_key") or uuid4()),
            "title": line.title, "activity_id": str(activity.id), "location_id": str(location.id),
            "duration_minutes": int(duration * 60), "quantity": str(line.quantity),
            "primary": line.id == request.primary_line_id, "pricing": price.snapshot_breakdown(),
            "base": str(price.base_amount_ttc), "net": str(price.total_incl_vat),
            "vat_rate": str(line.vat_rate), "version": price.version})
    # Stable preview token includes external evidence (family reference, catalog, history).
    for decision in decisions:
        decision["course_key"] = str((next(l for l in lines if str(l.id) == decision["line_id"]).meta or {}).get("annual_course_key") or decision["line_id"])
    stable_decisions = [{**d, "pricing": {k: v for k, v in d["pricing"].items() if k != "calculated_at"}} for d in decisions]
    preview_version = build_price_version("annual-review-preview", quote=version, request=request.model_dump(exclude={"expected_version"}), decisions=stable_decisions,
        references=[str(r.child_id) for r in references])
    total = sum((Decimal(l.amount_ttc) for l in lines if not (l.meta or {}).get("annual_auto_discount")), Decimal("0"))
    for decision in decisions:
        line = next(l for l in lines if str(l.id) == decision["line_id"])
        total += Decimal(decision["net"]) * Decimal(decision["quantity"]) - Decimal(line.amount_ttc)
    return {"version": preview_version, "previous_total": str(quote.total_ttc), "total": str(total.quantize(Decimal("0.01"))),
        "decisions": decisions, "returning_verified": bool(previous_subscription), "family": family,
        "guardian_ids": sorted(str(i) for i in guardians) if reference_id else [], "policy": POLICY_VERSION}


def apply_review(db, quote, lines, request, actor):
    preview = prepare_review(db, quote, lines, request)
    if request.expected_version != preview["version"]:
        fail("Le devis ou ses critères ont changé. Relancez l'aperçu avant confirmation.")
    for line in lines:
        if (line.meta or {}).get("annual_auto_discount"):
            db.delete(line)
    for entry in preview["decisions"]:
        line = next(l for l in lines if str(l.id) == entry["line_id"])
        base, qty, rate = Decimal(entry["base"]), Decimal(entry["quantity"]), Decimal(entry["vat_rate"])
        line.unit_price_ttc = base
        line.unit_price_ht, line.unit_vat_amount, _ = split_tax(base, vat_rate=rate)
        line.amount_ht, line.amount_vat, line.amount_ttc = split_tax(base * qty, vat_rate=rate)
        line.meta = {**(line.meta or {}), "annual_course_key": entry["course_key"], "annual_decision": entry}
        for component in entry["pricing"]["components"]:
            amount = Decimal(component["amount_ttc"])
            unit_ht, unit_tax, _ = split_tax(amount, vat_rate=rate)
            ht, tax, total = split_tax(amount * qty, vat_rate=rate)
            db.add(QuoteLine(quote_id=quote.id, line_category="service", line_type="discount", title=f"{component['label']} — {line.title}"[:255],
                pricing_unit="session", quantity=qty, vat_rate=rate, unit_price_ttc=amount, unit_price_ht=unit_ht, unit_vat_amount=unit_tax,
                amount_ht=ht, amount_vat=tax, amount_ttc=total, sort_order=line.sort_order + 1,
                meta={"annual_auto_discount": True, "target_course_key": entry["course_key"], "discount_kind": component["code"].lower()}))
    for guardian in preview["guardian_ids"]:
        ref = db.get(AnnualFamilyReference, (UUID(guardian), quote.school_year_label))
        if not ref:
            db.add(AnnualFamilyReference(guardian_id=UUID(guardian), season=quote.school_year_label,
                child_id=request.family_reference_child_id, evidence={"quote_id": str(quote.id), "actor_id": str(actor.id), "note": request.review_note}))
        elif ref.child_id != request.family_reference_child_id:
            ref.child_id = request.family_reference_child_id
            ref.evidence = {"quote_id": str(quote.id), "actor_id": str(actor.id), "note": request.review_note}
    quote.total_ttc = Decimal(preview["total"])
    db.flush()
    updated_lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order, QuoteLine.created_at)).all()
    review = {**request.model_dump(mode="json", exclude={"expected_version"}), **preview,
              "actor_id": str(actor.id), "verified_at": datetime.now(timezone.utc).isoformat(),
              "fingerprint": quote_fingerprint(quote, updated_lines)}
    quote.meta = {**(quote.meta or {}), KEY: review}
    return review
