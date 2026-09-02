from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import combinations
import unicodedata
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.services.annual_enrollment import resolve_enrollment
from app.models.catalog import CourseType, Location
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.quote import Quote, QuoteLine, QuoteType, Prospect
from app.services.annual_discounts import AnnualEligibility, annual_discount_price, POLICY_VERSION
from app.services.client_pricing import build_price_version, split_tax
from app.services.pricing_catalog import resolve_catalog_activity_price
from app.services.annual_pricing_students import (
    quote_students, family_members, identity, canonical_id, is_child, birth_date,
    student_enrollment, save_enrollment, family_reference, save_family_reference,
    lock_family, identity_evidence,
)

KEY = "annual_pricing_review"


class AnnualReviewRequest(BaseModel):
    student_id: UUID
    audience: Literal["CHILD", "TEEN", "ADULT"]
    primary_line_id: UUID | None = None
    primary_contract_course_key: str | None = None
    family_reference_child_id: UUID | None = None
    replace_family_reference: bool = False
    enrollment_status: Literal["AUTO", "NEW", "RETURNING_MANUAL"] = "AUTO"
    enrollment_note: str = Field(default="", max_length=2000)
    manual_discount_policy: Literal["BLOCK", "KEEP", "REPLACE"] = "BLOCK"
    review_note: str = Field(min_length=10, max_length=2000)
    expected_version: str | None = None


def fail(message: str):
    raise HTTPException(409, message)


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value or "").lower()) if not unicodedata.combining(c))


def quote_fingerprint(quote, lines, *, calendar_snapshot=None):
    def numeric(value):
        return str(Decimal(str(value or 0)).quantize(Decimal("0.001")))
    return build_price_version("quote-review", season=quote.school_year_label, client=quote.client_id,
        location=quote.location_id, catalog=quote.pricing_catalog_id, currency=quote.currency,
        prospect=quote.prospect_id, total=numeric(quote.total_ttc), quote_type=quote.quote_type, quote_type_id=quote.quote_type_id,
        adjustment=(quote.meta or {}).get("financial_adjustment"),
        calendar=quote.calendar_snapshot if calendar_snapshot is None else calendar_snapshot, lines=[{
            "id": str(l.id), "activity": l.activity_id, "quantity": numeric(l.quantity),
            "price": numeric(l.unit_price_ttc), "total": numeric(l.amount_ttc), "vat": numeric(l.vat_rate),
            "meta": l.meta, "title": l.title, "kind": l.line_type,
            "unit": l.pricing_unit, "duration": l.duration_minutes, "category": l.line_category,
        } for l in sorted(lines, key=lambda row: str(row.id))])


SOLFEGE_SELECTION_FIELDS = {
    "weekday",
    "weekday_label",
    "start_time",
    "end_time",
    "duration_minutes",
    "location_id",
    "location_label",
    "modality",
    "selection_pending",
    "pending_slot_options",
}


def pricing_review_calendar(quote, lines):
    """Ignore only the later scheduling choice for a free solfege line."""
    calendar = deepcopy(quote.calendar_snapshot or {})
    free_solfege_activity_ids = {
        str(line.activity_id)
        for line in lines
        if line.activity_id
        and line.line_type == "item"
        and line.line_category == "service"
        and Decimal(str(line.amount_ttc or 0)) == 0
        and "solfege" in normalized(line.title)
    }
    if not free_solfege_activity_ids:
        return calendar

    normalized_blocks: list[object] = []
    for raw_block in calendar.get("blocks", []):
        if not isinstance(raw_block, dict):
            normalized_blocks.append(raw_block)
            continue
        block = dict(raw_block)
        if str(block.get("activity_id") or "") in free_solfege_activity_ids:
            for field in SOLFEGE_SELECTION_FIELDS:
                block.pop(field, None)
        normalized_blocks.append(block)
    calendar["blocks"] = normalized_blocks

    solfege = calendar.get("solfege")
    if isinstance(solfege, dict):
        normalized_solfege = dict(solfege)
        normalized_solfege.pop("selected_slot", None)
        calendar["solfege"] = normalized_solfege
    return calendar


def pricing_review_fingerprint(quote, lines):
    return quote_fingerprint(quote, lines, calendar_snapshot=pricing_review_calendar(quote, lines))


def ensure_pricing_review_fingerprint(quote, lines) -> bool:
    """Backfill the selection-insensitive fingerprint before slot selection."""
    meta = dict(quote.meta or {})
    review = dict(meta.get(KEY) or {})
    if not review or review.get("pricing_fingerprint"):
        return False
    review["pricing_fingerprint"] = pricing_review_fingerprint(quote, lines)
    meta[KEY] = review
    quote.meta = meta
    return True


def is_annual_quote(db, quote):
    quote_type = db.get(QuoteType, quote.quote_type_id) if quote.quote_type_id else None
    if quote_type and quote_type.formula_id:
        plan = db.get(Plan, quote_type.formula_id)
        return bool(plan and plan.kind == PlanKind.FORFAIT)
    code = normalized(quote_type.code if quote_type else quote.quote_type).replace("-", "_").replace(" ", "_")
    return code in {"forfait", "forfait_2026_2027"}


def activity_family(activity):
    if not activity:
        return None
    label = normalized(activity.name)
    if any(word in label for word in ("essai", "trial", "solfege", "masterclass")):
        return None
    if "eveil" in label:
        return "MUSICAL_AWAKENING"
    if ("collectif" in label or "initiation au piano" in label) and "ligne" not in label:
        return "COLLECTIVE_ONSITE"
    return None


def activity_audiences(activity):
    label = normalized(activity.name)
    if any(word in label for word in ("eveil", "initiation", "enfant")):
        return {"CHILD"}
    if "ado" in label and "adult" in label:
        return {"TEEN", "ADULT"}
    if "ado" in label:
        return {"TEEN"}
    if "adult" in label:
        return {"ADULT"}
    return {"CHILD", "TEEN", "ADULT"}


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


def review_fingerprint_matches(quote, lines, expected_fingerprint, expected_pricing_fingerprint=None):
    """Accept only harmless metadata materialized after an annual quote approval.

    The approval fingerprint remains authoritative.  The compatibility path only
    removes redundant fields from already selected, zero-priced solfege blocks
    and then requires the complete historical fingerprint to match.  Prices,
    identities, quantities, activities, times and every other calendar field
    therefore remain protected.
    """
    if expected_fingerprint == quote_fingerprint(quote, lines):
        return True
    if expected_pricing_fingerprint and expected_pricing_fingerprint == pricing_review_fingerprint(quote, lines):
        return True
    if quote.status != "approved" or not expected_fingerprint:
        return False

    free_solfege_activity_ids = {
        str(line.activity_id)
        for line in lines
        if line.activity_id
        and line.line_type == "item"
        and line.line_category == "service"
        and Decimal(line.amount_ttc) == 0
        and "solfege" in normalized(line.title)
    }
    removable_fields: list[tuple[int, str]] = []
    blocks = (quote.calendar_snapshot or {}).get("blocks", [])
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or str(block.get("activity_id")) not in free_solfege_activity_ids:
            continue
        if block.get("selection_pending") is not False:
            continue
        try:
            start = datetime.strptime(block["start_time"], "%H:%M")
            end = datetime.strptime(block["end_time"], "%H:%M")
            duration_minutes = int((end - start).total_seconds() / 60)
        except (KeyError, TypeError, ValueError):
            continue
        if duration_minutes <= 0:
            continue
        if block.get("duration_minutes") == duration_minutes:
            removable_fields.append((index, "duration_minutes"))
        if block.get("pending_slot_options") == []:
            removable_fields.append((index, "pending_slot_options"))

    # Keep the compatibility search deliberately small and fail closed for an
    # unexpected or malformed calendar instead of weakening the review.
    if len(removable_fields) > 8:
        return False
    for field_count in range(1, len(removable_fields) + 1):
        for fields in combinations(removable_fields, field_count):
            candidate_calendar = deepcopy(quote.calendar_snapshot)
            for index, key in fields:
                candidate_calendar["blocks"][index].pop(key)
            if expected_fingerprint == quote_fingerprint(
                quote,
                lines,
                calendar_snapshot=candidate_calendar,
            ):
                return True
    return False


def check_review_current(db, quote, lines):
    review = (quote.meta or {}).get(KEY)
    if not review:
        return
    if not review_fingerprint_matches(
        quote,
        lines,
        review.get("fingerprint"),
        review.get("pricing_fingerprint"),
    ):
        fail("Le devis a changé depuis la vérification tarifaire. Recalculez les remises dans Lignes facturées avant envoi ou intégration.")
    # Sent documents keep their decision even if the family graph later changes.
    if quote.sent_at:
        return
    student = next((s for s in quote_students(db, quote) if str(s.id) == review["student_id"]), None)
    if student is None:
        fail("Le rattachement de l'élève a changé : revérifiez la décision tarifaire.")
    if review.get("identity_evidence"):
        _, guardians = family_members(db, student.id)
        if identity_evidence(db, student, guardians) != review["identity_evidence"]:
            fail("La fiche élève ou ses liens familiaux ont changé : revérifiez les remises.")
    if "enrollment" in review:
        status = student_enrollment(db, student.id, quote.school_year_label)["status"]
        if status != review["enrollment"]["status"]:
            fail("La réinscription de cet élève a changé. Revérifiez les remises dans Lignes facturées avant envoi.")
    for guardian_id in review.get("guardian_ids", []):
        reference = family_reference(db, UUID(guardian_id), quote.school_year_label)
        if not reference or canonical_id(db, reference.child_id) != canonical_id(db, review.get("family_reference_child_id")):
            fail("L'enfant de référence de la famille a changé : vérifiez de nouveau les remises.")
    reference_id = review.get("family_reference_child_id")
    if reference_id and reference_id != review.get("student_id"):
        if not reference_has_engagement(db, quote, UUID(reference_id)):
            fail("L'engagement annuel de l'enfant de référence n'est plus disponible : revérifiez la remise famille avant envoi.")


def reference_has_engagement(db, quote, reference_id):
    reference_id = canonical_id(db, reference_id)
    if not reference_id:
        return False
    aliases = {reference_id, *db.scalars(select(Prospect.id).where(Prospect.linked_client_id == reference_id)).all()}
    subscription = db.scalar(select(ClientPlanSubscription.id).join(Plan).where(
        ClientPlanSubscription.user_id == reference_id, Plan.kind == PlanKind.FORFAIT,
        ClientPlanSubscription.started_at < datetime(2027, 8, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.ends_at >= datetime(2026, 9, 1, tzinfo=timezone.utc),
        ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
    ).limit(1))
    quotes = db.scalars(select(Quote).where(Quote.school_year_label == quote.school_year_label,
        Quote.total_ttc > 0,
        or_(Quote.client_id.in_(aliases), Quote.prospect_id.in_(aliases),
            Quote.meta[KEY]["student_id"].astext.in_([str(i) for i in aliases])),
        Quote.status.in_(["created", "sent", "approved", "accepted"]), Quote.id != quote.id)).all()
    return bool(subscription or any((canonical_id(db, q.client_id or q.prospect_id) == reference_id or
        canonical_id(db, (q.meta or {}).get(KEY, {}).get("student_id")) == reference_id) and is_annual_quote(db, q) for q in quotes))


def prepare_review(db: Session, quote: Quote, lines: list[QuoteLine], request: AnnualReviewRequest):
    if quote.sent_at or quote.approved_at or quote.status != "created":
        fail("Les devis déjà envoyés ou acceptés sont conservés. Créez une révision pour changer le prix.")
    if not is_annual_quote(db, quote) or quote.school_year_label != "2026-2027" or quote.currency != "EUR":
        fail("Ces règles concernent uniquement le forfait annuel 2026-2027 en EUR.")
    adjustment = (quote.meta or {}).get("financial_adjustment") or {}
    if Decimal(str(adjustment.get("amount_ttc") or 0)) != 0:
        fail("Ce devis comporte un ajustement financier exceptionnel : faites-le vérifier séparément avant de calculer les remises.")
    candidates = quote_students(db, quote)
    student = next((u for u in candidates if u.id == request.student_id), None)
    if student is None:
        fail("Sélectionnez l'élève client ou prospect rattaché à ce devis. Aucun rapprochement par nom n'est effectué.")
    # Serialize household choices across distinct quotes and both guardians.
    children, guardians = family_members(db, student.id)
    lock_family(db, {student.id, *guardians})
    children, current_guardians = family_members(db, student.id)
    if guardians != current_guardians or not any(s.id == student.id for s in quote_students(db, quote)):
        fail("Le rattachement familial a changé pendant le calcul. Rechargez le formulaire.")
    birth = birth_date(student)
    adult_age = birth and date(2026, 9, 1).year - birth.year - ((9, 1) < (birth.month, birth.day)) >= 18
    if request.audience != "ADULT" and (not is_child(student) or adult_age):
        fail("La fiche élève indique un adulte : les remises enfant/adolescent ne peuvent pas être attribuées.")
    if request.audience == "ADULT" and (is_child(student) and not adult_age or birth and not adult_age):
        fail("La fiche élève indique un mineur : sélectionnez enfant ou adolescent.")
    reference_id = request.family_reference_child_id
    if request.audience == "ADULT" and reference_id:
        fail("Les remises famille enfant/adolescent ne s'appliquent pas aux adultes.")
    if reference_id and (reference_id not in children or not guardians):
        fail("L'enfant de référence doit appartenir à la même famille vérifiée.")
    references = [r for g in sorted(guardians, key=str) if (r := family_reference(db, g, quote.school_year_label))]
    if references and any(canonical_id(db, row.child_id) != reference_id for row in references):
        if not reference_id or not request.replace_family_reference:
            fail("Cette famille possède déjà un enfant de référence. Confirmez explicitement le changement pour les brouillons ou conservez ce choix.")
        sent = db.scalars(select(Quote).where(Quote.school_year_label == quote.school_year_label, Quote.sent_at.is_not(None))).all()
        if any(set((q.meta or {}).get(KEY, {}).get("guardian_ids", [])) & {str(i) for i in guardians} for q in sent):
            fail("Une décision de cette famille a déjà été envoyée : l'enfant de référence est figé pour cette saison. Une révision coordonnée est nécessaire.")
    if reference_id:
        reference_user = identity(db, reference_id)
        if not reference_user or not is_child(reference_user):
            fail("L'enfant de référence doit être une fiche enfant.")
    family = bool(reference_id and reference_id != student.id)
    if family:
        if not reference_has_engagement(db, quote, reference_id):
            fail("Préparez d'abord le devis annuel de l'enfant de référence (son acceptation n'est pas nécessaire), ou rattachez son contrat annuel. Aucun engagement de cet enfant n'a été retrouvé.")
    enrollment_before = student_enrollment(db, student.id, quote.school_year_label)
    try:
        enrollment = resolve_enrollment(enrollment_before, request.enrollment_status, request.enrollment_note)
    except ValueError as exc:
        fail(str(exc))
    previous_subscription = enrollment["subscription_id"]
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
    for _, activity, _ in entries:
        if request.audience not in activity_audiences(activity):
            fail(f"La catégorie sélectionnée ne correspond pas à {activity.name}. Vérifiez enfant, adolescent ou adulte.")
    primary_family = activity_family(db.get(CourseType, UUID(external_primary["activity_id"]))) if external_primary else next(item[2] for item in entries if item[0].id == request.primary_line_id)
    if (len(entries) > 1 or external_primary) and primary_family != "COLLECTIVE_ONSITE":
        fail("Le premier cours doit être un cours collectif en présentiel pour attribuer une remise deuxième cours.")
    # Existing explicit discounts are never guessed/stacked with this engine.
    legacy = [line for line in lines if line.line_type == "discount" and not (line.meta or {}).get("annual_auto_discount")]
    if legacy and request.manual_discount_policy == "BLOCK":
        fail("Ce devis contient des remises manuelles. Dans Lignes facturées, choisissez explicitement de les conserver sans cumul ou de les remplacer, puis relancez l'aperçu.")
    keep_manual = bool(legacy and request.manual_discount_policy == "KEEP")
    version = quote_fingerprint(quote, lines)
    decisions = []
    for line, activity, family_code in ([] if keep_manual else entries):
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
        duration = Decimal(line.duration_minutes or activity.duration_minutes) / 60
        catalog = resolve_catalog_activity_price(db, activity_id=activity.id, location_id=location.id,
            student_category="ADULT" if request.audience == "ADULT" else "CHILD", channel="ANNUAL_FORFAIT", catalog_id=quote.pricing_catalog_id,
            at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        if not catalog:
            fail(f"Tarif annuel publié manquant pour {activity.name} à {location.name}. Complétez la grille avant calcul.")
        if external_primary and external_primary["location_id"] != str(location.id):
            fail("Le cours principal souscrit est dans un autre lieu : faites vérifier le rattachement avant d'attribuer une remise deuxième cours.")
        try:
            price = annual_discount_price(base=catalog.amount_for_duration(duration),
                eligibility=AnnualEligibility(site, request.audience, family_code, family=family,
                    returning=enrollment["returning"], second_course=line.id != request.primary_line_id),
                vat_rate=Decimal(line.vat_rate), source=f"quote:{quote.id}:course:{line.id}",
                evidence_version=build_price_version("eligibility", student=student.id, reference=reference_id,
                    primary=request.primary_line_id or request.primary_contract_course_key, prior=previous_subscription,
                    enrollment=enrollment, note=request.review_note, catalog=catalog.version))
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
    evidence = identity_evidence(db, student, guardians)
    preview_version = build_price_version("annual-review-preview", quote=version, request=request.model_dump(exclude={"expected_version"}), decisions=stable_decisions,
        references=[str(r.child_id) for r in references], enrollment=enrollment, enrollment_before=enrollment_before, identity=evidence)
    retained = [l for l in lines if keep_manual or (not (l.meta or {}).get("annual_auto_discount") and l not in legacy)]
    total = sum((Decimal(l.amount_ttc) for l in retained), Decimal("0"))
    for decision in decisions:
        line = next(l for l in lines if str(l.id) == decision["line_id"])
        total += Decimal(decision["net"]) * Decimal(decision["quantity"]) - Decimal(line.amount_ttc)
    display_lines = [display_line(l) for l in retained]
    for decision in decisions:
        display_lines = [l for l in display_lines if l["id"] != decision["line_id"]]
        display_lines.append({"id": decision["line_id"], "title": decision["title"], "kind": "item", "origin": "Grille annuelle",
            "quantity": decision["quantity"], "unit": decision["base"], "total": str(Decimal(decision["base"]) * Decimal(decision["quantity"]))})
        for component in decision["pricing"]["components"]:
            display_lines.append({"id": f'{decision["line_id"]}:{component["code"]}', "title": f'{component["label"]} — {decision["title"]}',
                "kind": "discount", "origin": "Calcul automatique", "quantity": decision["quantity"], "unit": str(component["amount_ttc"]),
                "total": str(Decimal(str(component["amount_ttc"])) * Decimal(decision["quantity"]))})
    return {"version": preview_version, "previous_total": str(quote.total_ttc), "total": str(total.quantize(Decimal("0.01"))),
        "decisions": decisions, "returning_verified": enrollment["returning"], "family": family,
        "student_kind": "PROSPECT" if isinstance(student, Prospect) else "CLIENT", "identity_evidence": evidence,
        "enrollment": enrollment, "display_lines": display_lines, "keep_manual": keep_manual,
        "replaced_discounts": [display_line(l) for l in legacy] if not keep_manual else [],
        "guardian_ids": sorted(str(i) for i in guardians) if reference_id else [], "policy": POLICY_VERSION}


def display_line(line):
    return {"id": str(line.id), "title": line.title, "kind": line.line_type,
            "quantity": str(line.quantity), "unit": str(line.unit_price_ttc), "total": str(line.amount_ttc),
            "origin": "Calcul automatique" if (line.meta or {}).get("annual_auto_discount") else "Remise manuelle / importée" if line.line_type == "discount" else "Ligne enregistrée"}


def apply_review(db, quote, lines, request, actor):
    preview = prepare_review(db, quote, lines, request)
    if request.expected_version != preview["version"]:
        fail("Le devis ou ses critères ont changé. Relancez l'aperçu avant confirmation.")
    for line in lines:
        if not preview["keep_manual"] and ((line.meta or {}).get("annual_auto_discount") or
                (line.line_type == "discount" and request.manual_discount_policy == "REPLACE")):
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
        save_family_reference(db, UUID(guardian), request.family_reference_child_id, quote.school_year_label,
            {"quote_id": str(quote.id), "actor_id": str(actor.id), "note": request.review_note})
    evidence = {"actor_id": str(actor.id), "actor_name": f"{actor.first_name or ''} {actor.last_name or ''}".strip() or actor.email,
                "verified_at": datetime.now(timezone.utc).isoformat(), "quote_id": str(quote.id), "note": preview["enrollment"]["note"]}
    if preview["enrollment"]["status"] != "AUTO":
        save_enrollment(db, request.student_id, quote.school_year_label, preview["enrollment"]["status"], evidence)
    quote.total_ttc = Decimal(preview["total"])
    db.flush()
    updated_lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order, QuoteLine.created_at)).all()
    review = {**request.model_dump(mode="json", exclude={"expected_version"}), **preview,
              "actor_id": str(actor.id), "actor_name": evidence["actor_name"], "verified_at": evidence["verified_at"],
              "fingerprint": quote_fingerprint(quote, updated_lines),
              "pricing_fingerprint": pricing_review_fingerprint(quote, updated_lines)}
    quote.meta = {**(quote.meta or {}), KEY: review}
    return review
