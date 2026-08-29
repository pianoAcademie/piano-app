from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_admin_permission_map, get_current_user, get_db, require_roles
from app.core.config import settings
from app.models.catalog import CourseSession, CourseType
from app.models.family import ClientFamilyLink
from app.models.ops import AppSetting
from app.models.plan import (
    ClientPlanSubscription,
    Plan,
    PlanCreditGrant,
    PlanCreditGrantsRelation,
    PlanEntitlement,
    PlanKind,
    PlanPriceTaxMode,
    SubscriptionStatus,
)
from app.models.user import ClientKind, User, UserRole
from app.schemas.plan import (
    ClientSubscriptionOut,
    ClientSubscriptionCancellationRequest,
    PlanMiniOut,
    PlanOut,
    PlanFirstPurchaseLineOut,
    PlanPricePreviewOut,
    PlanPurchaseRequest,
    PublicFormulaPurchaseContextOut,
    PublicFormulaPurchaseStartOut,
    PublicFormulaPurchaseStartRequest,
    PublicFormulaPurchaseSummaryOut,
    PublicLegalTermsOut,
)
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, with_webhook_secret
from app.services.automation_triggers import schedule_plan_purchase_triggers
from app.services.notifications.application.orchestrator import enqueue_notifications
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.payment_provider import PaymentProvider, resolve_webhook_secret
from app.services.plan_entitlements import effective_entitlements_by_plan
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.client_status import promote_client_to_active_student
from app.services.subscriptions import add_months_utc, reconcile_subscription_status
from app.services.subscription_lifecycle_notifications import send_cancellation_request_admin_notifications
from app.services.subscription_credit_allocations import subscription_credit_allocations
from app.services.trial_courses import (
    has_available_trial_credit,
    has_available_trial_credit_for_course_type,
    has_prior_course_attendance_for_course_type,
    has_trial_booking_for_course_type,
    plan_supports_trial_course_type,
    trial_plan_course_type_ids,
)
from app.services.legal_terms import resolve_legal_terms

router = APIRouter()

PURCHASE_CONTEXT_SCOPE = "PUBLIC_FORMULA_PURCHASE_CONTEXT"
PURCHASE_LINK_OPTION_ENABLED = {
    "achat_par_lien",
    "purchase_link_enabled",
    "buy_link_enabled",
}
PURCHASE_LINK_OPTION_DISABLED = {
    "achat_par_lien_desactive",
    "purchase_link_disabled",
    "buy_link_disabled",
}
PRIOR_PURCHASE_STATUSES = {
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAYMENT_ALERT,
    SubscriptionStatus.PRE_TERMINATION,
    SubscriptionStatus.PAUSED,
    SubscriptionStatus.TERMINATED,
    SubscriptionStatus.EXPIRED,
}
SUCCESSFUL_PURCHASE_PAYMENT_STATUSES = {
    "PAID",
    "SUCCEEDED",
    "COMPLETED",
    "SEPA_MANDATE_ACTIVE",
    "PAID_PAYMENT_METHOD_MISSING",
}


def _request_ip(request: Request) -> str | None:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    value = forwarded or (request.client.host if request.client is not None else "")
    return value[:64] or None


@router.get("/public/legal-terms", response_model=PublicLegalTermsOut)
def get_public_legal_terms(
    language: str = Query(default="fr", max_length=8),
    db: Session = Depends(get_db),
) -> PublicLegalTermsOut:
    terms = resolve_legal_terms(db, language)
    if terms is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Les conditions générales de vente ne sont pas encore publiées.",
        )
    return PublicLegalTermsOut(
        language=terms.language,
        content=terms.content,
        content_hash=terms.content_hash,
        version=terms.version,
        updated_at=terms.updated_at,
        used_fallback=terms.used_fallback,
    )


@dataclass(frozen=True)
class _PurchasePricing:
    amount_excl_vat: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
    currency: str
    base_price_ttc: Decimal
    first_purchase_required: bool
    first_purchase_fee_ttc: Decimal | None
    first_purchase_partitions_price_ttc: Decimal | None
    breakdown: list[dict[str, object]]


def _formula_frequency_label(kind: PlanKind) -> str | None:
    if kind == PlanKind.SUBSCRIPTION:
        return "Mensuel"
    return None


def _normalize_formula_options(plan: Plan) -> set[str]:
    raw = plan.options_json if isinstance(plan.options_json, list) else []
    return {str(value or "").strip().lower() for value in raw if str(value or "").strip()}


def _formula_purchase_link_allowed(plan: Plan) -> bool:
    option_keys = _normalize_formula_options(plan)
    if option_keys & PURCHASE_LINK_OPTION_DISABLED:
        return False
    if option_keys & PURCHASE_LINK_OPTION_ENABLED:
        return True
    return True


def _has_prior_purchase_for_plan(db: Session, *, user_id: UUID, plan_id: UUID) -> bool:
    prior = db.scalar(
        select(ClientPlanSubscription.id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.plan_id == plan_id,
            or_(
                ClientPlanSubscription.status.in_(list(PRIOR_PURCHASE_STATUSES)),
                ClientPlanSubscription.migration_source_code.is_not(None),
                ClientPlanSubscription.last_successful_charge_at.is_not(None),
                func.upper(ClientPlanSubscription.last_payment_status).in_(list(SUCCESSFUL_PURCHASE_PAYMENT_STATUSES)),
            ),
        )
        .limit(1)
    )
    return prior is not None


def _ttc_to_tax_totals(*, total_incl_vat: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    total = total_incl_vat.quantize(Decimal("0.01"))
    divisor = Decimal("1") + (vat_rate / Decimal("100"))
    price_excl_vat = total if divisor <= 0 else (total / divisor)
    price_excl_vat = price_excl_vat.quantize(Decimal("0.01"))
    vat_amount = (total - price_excl_vat).quantize(Decimal("0.01"))
    return price_excl_vat, vat_amount, total


def _purchase_pricing(
    db: Session,
    *,
    plan: Plan,
    country: str,
    currency: str,
    on_date: date,
    has_prior_purchase: bool,
    trial_course_type: CourseType | None = None,
) -> _PurchasePricing:
    if trial_course_type is not None:
        trial_price = getattr(trial_course_type, "trial_course_price_ttc", None)
        if not bool(getattr(trial_course_type, "trial_course_enabled", False)) or trial_price is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Les cours d'essai ne sont pas autorises pour cette activite",
            )
        currency_code = (plan.currency_code or currency or "EUR").upper()
        vat_rate = resolve_vat_rate(
            db,
            country=country,
            service_code=trial_course_type.service_code,
            on_date=on_date,
        )
        amount_excl, vat_amount, total = _ttc_to_tax_totals(
            total_incl_vat=Decimal(trial_price),
            vat_rate=vat_rate,
        )
        return _PurchasePricing(
            amount_excl_vat=amount_excl,
            vat_amount=vat_amount,
            total_incl_vat=total,
            currency=currency_code,
            base_price_ttc=total,
            first_purchase_required=False,
            first_purchase_fee_ttc=None,
            first_purchase_partitions_price_ttc=None,
            breakdown=[
                {
                    "code": "TRIAL_COURSE",
                    "label": f"Cours d'essai - {trial_course_type.name}",
                    "amount_excl_vat": str(amount_excl),
                    "vat_rate": str(vat_rate),
                    "vat_amount": str(vat_amount),
                    "amount_ttc": str(total),
                }
            ],
        )

    base_ttc, currency_code = _plan_amount_due_and_currency(
        db,
        plan=plan,
        country=country,
        currency=currency,
        on_date=on_date,
    )
    plan_vat_rate = resolve_vat_rate(
        db,
        country=country,
        service_code=plan_service_code(plan.kind.value),
        on_date=on_date,
    )
    base_excl, base_vat, base_total = _ttc_to_tax_totals(total_incl_vat=base_ttc, vat_rate=plan_vat_rate)
    breakdown: list[dict[str, object]] = [
        {
            "code": "FORMULA",
            "label": plan.name,
            "amount_excl_vat": str(base_excl),
            "vat_rate": str(plan_vat_rate),
            "vat_amount": str(base_vat),
            "amount_ttc": str(base_total),
        }
    ]
    amount_excl = base_excl
    vat_amount = base_vat
    total = base_total
    fee_ttc: Decimal | None = None
    partitions_ttc: Decimal | None = None

    first_purchase_configured = bool(
        (
            plan.first_purchase_signup_fee_enabled
            and Decimal(plan.signup_fee_value or plan.signup_fee_excl_vat or 0) > 0
        )
        or (
            plan.first_purchase_partitions_enabled
            and Decimal(plan.first_purchase_partitions_price_value or 0) > 0
        )
    )
    first_purchase_required = first_purchase_configured and not has_prior_purchase
    if first_purchase_required:
        raw_fee = plan.signup_fee_value if plan.signup_fee_value is not None else plan.signup_fee_excl_vat
        if plan.first_purchase_signup_fee_enabled and raw_fee is not None and Decimal(raw_fee) > 0:
            if plan.price_tax_mode == PlanPriceTaxMode.TTC:
                fee_excl, fee_vat, fee_total = _ttc_to_tax_totals(
                    total_incl_vat=Decimal(raw_fee),
                    vat_rate=plan_vat_rate,
                )
            else:
                fee_excl, fee_vat, fee_total = compute_tax_totals(
                    price_excl_vat=Decimal(raw_fee),
                    vat_rate=plan_vat_rate,
                )
            fee_ttc = fee_total.quantize(Decimal("0.01"))
            amount_excl += fee_excl
            vat_amount += fee_vat
            total += fee_total
            breakdown.append(
                {
                    "code": "SIGNUP_FEE",
                    "label": "Frais de dossier",
                    "amount_excl_vat": str(fee_excl.quantize(Decimal("0.01"))),
                    "vat_rate": str(plan_vat_rate),
                    "vat_amount": str(fee_vat.quantize(Decimal("0.01"))),
                    "amount_ttc": str(fee_ttc),
                }
            )

        raw_partitions_price = Decimal(plan.first_purchase_partitions_price_value or 0)
        if plan.first_purchase_partitions_enabled and raw_partitions_price > 0:
            if plan.price_tax_mode == PlanPriceTaxMode.TTC:
                partitions_excl, partitions_vat, partitions_total = _ttc_to_tax_totals(
                    total_incl_vat=raw_partitions_price,
                    vat_rate=plan_vat_rate,
                )
            else:
                partitions_excl, partitions_vat, partitions_total = compute_tax_totals(
                    price_excl_vat=raw_partitions_price,
                    vat_rate=plan_vat_rate,
                )
            partitions_ttc = partitions_total
            amount_excl += partitions_excl
            vat_amount += partitions_vat
            total += partitions_total
            breakdown.append(
                {
                    "code": "FIRST_PURCHASE_PARTITIONS",
                    "label": "Cahier de partitions",
                    "amount_excl_vat": str(partitions_excl),
                    "vat_rate": str(plan_vat_rate),
                    "vat_amount": str(partitions_vat),
                    "amount_ttc": str(partitions_total),
                }
            )

    return _PurchasePricing(
        amount_excl_vat=amount_excl.quantize(Decimal("0.01")),
        vat_amount=vat_amount.quantize(Decimal("0.01")),
        total_incl_vat=total.quantize(Decimal("0.01")),
        currency=currency_code,
        base_price_ttc=base_total,
        first_purchase_required=first_purchase_required,
        first_purchase_fee_ttc=fee_ttc,
        first_purchase_partitions_price_ttc=partitions_ttc,
        breakdown=breakdown,
    )


def _trial_session_and_course_type(
    db: Session,
    *,
    plan: Plan,
    session_id: UUID,
) -> tuple[CourseSession, CourseType]:
    row = db.execute(
        select(CourseSession, CourseType)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(CourseSession.id == session_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creneau introuvable")
    session_obj, course_type = row
    if not plan_supports_trial_course_type(
        db,
        plan_id=plan.id,
        course_type_id=course_type.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette offre d'essai n'est pas compatible avec ce creneau",
        )
    if not bool(course_type.trial_course_enabled) or course_type.trial_course_price_ttc is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les cours d'essai ne sont pas autorises pour cette activite",
        )
    return session_obj, course_type


def _restriction_period_label(raw: str) -> str:
    value = raw.strip().upper()
    if value == "ACTIVE_BOOKINGS":
        return "reservations actives"
    if value == "DAY":
        return "jour"
    if value == "WEEK":
        return "semaine"
    if value == "MONTH":
        return "mois"
    if value == "ROLLING_MONTH":
        return "mois glissant"
    if value == "SEMESTER":
        return "semestre"
    return value or "-"


def _formula_restriction_labels(plan: Plan, *, course_name_by_id: dict[UUID, str]) -> list[str]:
    raw_restrictions = plan.restrictions_json if isinstance(plan.restrictions_json, list) else []
    labels: list[str] = []
    for raw in raw_restrictions:
        if not isinstance(raw, dict):
            continue
        max_bookings = int(raw.get("max_bookings") or 1)
        period = _restriction_period_label(str(raw.get("period") or ""))
        raw_course_ids = raw.get("course_type_ids")
        course_names: list[str] = []
        if isinstance(raw_course_ids, list):
            for raw_course_id in raw_course_ids:
                try:
                    parsed_course_id = UUID(str(raw_course_id))
                except (TypeError, ValueError):
                    continue
                course_names.append(course_name_by_id.get(parsed_course_id, str(parsed_course_id)))
        scope = ", ".join(course_names) if course_names else "toutes activites"
        if str(raw.get("period") or "").strip().upper() == "ACTIVE_BOOKINGS":
            labels.append(f"{max_bookings} reservations actives maximum ({scope})")
        else:
            labels.append(f"{max_bookings} / {period} ({scope})")
    return labels


def _purchase_url_for_plan(plan_id: UUID) -> str:
    return _frontend_url(path=f"/buy/formula/{plan_id}")


def _serialize_public_formula_summary(db: Session, *, plan: Plan) -> PublicFormulaPurchaseSummaryOut:
    entitlement_ids = db.scalars(select(PlanEntitlement.course_type_id).where(PlanEntitlement.plan_id == plan.id)).all()
    unique_entitlement_ids = list(dict.fromkeys(entitlement_ids))
    if unique_entitlement_ids:
        rows = db.execute(select(CourseType.id, CourseType.name).where(CourseType.id.in_(unique_entitlement_ids))).all()
        course_name_by_id = {course_id: name for course_id, name in rows}
    else:
        course_name_by_id = {}
    includes = [course_name_by_id.get(course_id, str(course_id)) for course_id in unique_entitlement_ids]
    restriction_labels = _formula_restriction_labels(plan, course_name_by_id=course_name_by_id)
    pricing = _purchase_pricing(
        db,
        plan=plan,
        country="FR",
        currency=(plan.currency_code or "EUR").upper(),
        on_date=date.today(),
        has_prior_purchase=False,
    )
    price_snapshot = pricing.total_incl_vat
    currency = pricing.currency
    payment_methods = _plan_payment_methods(plan)
    return PublicFormulaPurchaseSummaryOut(
        formula_id=plan.id,
        formula_code=plan.code,
        formula_type=plan.kind,
        name=plan.name,
        description=plan.description,
        active=bool(plan.active),
        is_private=bool(plan.is_private),
        is_trial_offer=bool(plan.is_trial_offer),
        purchase_link_allowed=_formula_purchase_link_allowed(plan),
        purchase_url=_purchase_url_for_plan(plan.id),
        price_ttc=price_snapshot,
        currency=currency,
        frequency_label=_formula_frequency_label(plan.kind),
        includes=includes,
        restriction_labels=restriction_labels,
        payment_methods=payment_methods,
        base_price_ttc=pricing.base_price_ttc,
        first_purchase_fee_ttc=pricing.first_purchase_fee_ttc,
        first_purchase_partitions_price_ttc=pricing.first_purchase_partitions_price_ttc,
    )


def _encode_purchase_context(
    *,
    plan: Plan,
    email: str,
    price_snapshot: Decimal | None,
    currency: str,
    session_id: UUID | None = None,
    booking_user_id: UUID | None = None,
    planning_return_to: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "scope": PURCHASE_CONTEXT_SCOPE,
        "formula_id": str(plan.id),
        "formula_code": plan.code,
        "formula_type": plan.kind.value,
        "email": email,
        "price_snapshot": str(price_snapshot) if price_snapshot is not None else None,
        "currency": currency,
        "session_id": str(session_id) if session_id is not None else None,
        "booking_user_id": str(booking_user_id) if booking_user_id is not None else None,
        "planning_return_to": str(planning_return_to or "").strip() or None,
        "iat": now,
        "exp": now + timedelta(hours=3),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_purchase_context(context_token: str) -> dict[str, object]:
    try:
        payload = jwt.decode(context_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide ou expire") from exc
    if payload.get("scope") != PURCHASE_CONTEXT_SCOPE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide")
    return payload


def _entitlements_by_plan(
    db: Session,
    *,
    plan_ids: list[UUID],
) -> tuple[dict[UUID, list[UUID]], dict[UUID, list[str]]]:
    return effective_entitlements_by_plan(db, plan_ids=plan_ids)


def _lock_user_purchase_scope(db: Session, user_id: UUID) -> None:
    db.scalar(
        select(User.id)
        .where(User.id == user_id)
        .with_for_update()
    )


def _has_same_subscription_in_current_month(
    db: Session,
    *,
    user_id: UUID,
    plan_id: UUID,
    reference_at: datetime,
) -> bool:
    cycle_end = add_months_utc(reference_at, 1)
    existing = db.scalar(
        select(ClientPlanSubscription.id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.plan_id == plan_id,
            ClientPlanSubscription.status.in_(
                [
                    SubscriptionStatus.PENDING,
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.PAYMENT_ALERT,
                    SubscriptionStatus.PRE_TERMINATION,
                    SubscriptionStatus.PAUSED,
                ]
            ),
            ClientPlanSubscription.started_at < cycle_end,
            or_(
                ClientPlanSubscription.cancellation_effective_at.is_(None),
                ClientPlanSubscription.cancellation_effective_at > reference_at,
            ),
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > reference_at),
        )
        .limit(1)
        .with_for_update()
    )
    return existing is not None


def _has_active_pack_with_remaining_credits(db: Session, *, user_id: UUID, now: datetime) -> bool:
    existing = db.scalar(
        select(ClientPlanSubscription.id)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            or_(ClientPlanSubscription.cancellation_effective_at.is_(None), ClientPlanSubscription.cancellation_effective_at > now),
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
            Plan.active.is_(True),
            Plan.kind == PlanKind.PACK,
            ClientPlanSubscription.credits_remaining.is_not(None),
            ClientPlanSubscription.credits_remaining > 0,
        )
        .limit(1)
        .with_for_update()
    )
    return existing is not None


def _covering_current_plan_name(
    db: Session,
    *,
    user_id: UUID,
    requested_plan_id: UUID,
    reference_at: datetime,
) -> str | None:
    """Return a current formula that already grants every requested entitlement."""
    rows = db.execute(
        select(Plan.id, Plan.name)
        .join(ClientPlanSubscription, ClientPlanSubscription.plan_id == Plan.id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.status.in_(
                [
                    SubscriptionStatus.PENDING,
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.PAYMENT_ALERT,
                    SubscriptionStatus.PRE_TERMINATION,
                ]
            ),
            ClientPlanSubscription.started_at <= reference_at,
            or_(
                ClientPlanSubscription.cancellation_effective_at.is_(None),
                ClientPlanSubscription.cancellation_effective_at > reference_at,
            ),
            or_(
                ClientPlanSubscription.ends_at.is_(None),
                ClientPlanSubscription.ends_at > reference_at,
            ),
            ClientPlanSubscription.bookings_blocked.is_(False),
            Plan.active.is_(True),
            Plan.kind.in_([PlanKind.SUBSCRIPTION, PlanKind.FORFAIT]),
            Plan.id != requested_plan_id,
        )
        .with_for_update()
    ).all()
    if not rows:
        return None

    covering_names = {plan_id: plan_name for plan_id, plan_name in rows}
    entitlement_ids, _ = effective_entitlements_by_plan(
        db,
        plan_ids=[requested_plan_id, *covering_names],
    )
    requested_entitlements = set(entitlement_ids.get(requested_plan_id, []))
    if not requested_entitlements:
        return None

    for plan_id, plan_name in rows:
        if requested_entitlements.issubset(set(entitlement_ids.get(plan_id, []))):
            return str(plan_name)
    return None


def _resolve_plan_owner(
    db: Session,
    *,
    current_user: User,
    requested_user_id: UUID | None,
) -> User:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user

    if current_user.client_kind != ClientKind.ADULT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only adult accounts can purchase for another family member",
        )

    link_exists = db.scalar(
        select(ClientFamilyLink.id).where(
            ClientFamilyLink.adult_user_id == current_user.id,
            ClientFamilyLink.child_user_id == requested_user_id,
        )
    )
    if link_exists is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Target member is not attached to this adult account",
        )

    member = db.scalar(
        select(User).where(
            User.id == requested_user_id,
            User.role == UserRole.CLIENT,
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target client not found")
    if not member.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Target client is inactive")
    return member


def _plan_purchase_parties(*, purchaser: User, owner: User) -> tuple[UUID | None, User]:
    """Keep the beneficiary and the person paying for the purchase distinct.

    ``owner`` receives the entitlement.  When an adult purchases for a linked
    child, ``purchaser`` remains the billing contact and the PSP customer.
    Self-purchases keep the historical ``NULL`` payer contact convention.
    """
    payer_contact_id = purchaser.id if purchaser.id != owner.id else None
    return payer_contact_id, purchaser


def _plan_payment_methods(plan: Plan) -> list[str]:
    raw = plan.payment_methods_json
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        code = str(value).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _default_subscription_billing_method(plan: Plan) -> str | None:
    methods = _plan_payment_methods(plan)
    if "CARD_ONLINE" in methods:
        return "CARD_ONLINE"
    return methods[0] if methods else None


def _is_online_collection_method(method_code: str | None) -> bool:
    return (method_code or "").strip().upper() in {"CARD_ONLINE", "SEPA_DEBIT", "PAYPAL"}


def _frontend_url(*, path: str) -> str:
    candidate = resolve_frontend_base_url()
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _checkout_urls(
    *,
    owner_id: UUID,
    subscription_id: UUID,
    purchase_context: str | None = None,
) -> tuple[str, str, str]:
    query = f"tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}"
    if purchase_context:
        query += f"&purchase_context={purchase_context}"
    success_url = _frontend_url(path=f"/dashboard?{query}&payment_return=success")
    cancel_url = _frontend_url(path=f"/dashboard?{query}&payment_return=cancel")
    webhook_url = _frontend_url(path=f"/api/v1/public/payments/webhook?client_id={owner_id}&subscription_id={subscription_id}")
    return success_url, cancel_url, webhook_url


def _plan_amount_due_and_currency(
    db: Session,
    *,
    plan: Plan,
    country: str,
    currency: str,
    on_date: date,
) -> tuple[Decimal, str]:
    currency_code = (plan.currency_code or currency or "EUR").upper()
    if plan.kind == PlanKind.FORFAIT:
        return Decimal("0.00"), currency_code

    vat_rate = resolve_vat_rate(
        db,
        country=country,
        service_code=plan_service_code(plan.kind.value),
        on_date=on_date,
    )

    price_excl_vat: Decimal | None = None
    if plan.monthly_price_value is not None:
        raw_price = Decimal(plan.monthly_price_value)
        if plan.price_tax_mode == PlanPriceTaxMode.TTC:
            return raw_price.quantize(Decimal("0.01")), currency_code
        price_excl_vat = raw_price
    elif plan.monthly_price_excl_vat is not None:
        price_excl_vat = Decimal(plan.monthly_price_excl_vat)
    else:
        resolved = resolve_plan_price(
            db,
            plan_id=plan.id,
            country=country,
            currency=currency,
            on_date=on_date,
        )
        if resolved is not None:
            price_excl_vat = Decimal(resolved.price_excl_vat)
            currency_code = resolved.currency_code

    if price_excl_vat is None:
        return Decimal("0.00"), currency_code

    _, _, total = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)
    return total.quantize(Decimal("0.01")), currency_code


def _effective_pack_credits_for_plan(db: Session, *, plan: Plan) -> int | None:
    if plan.kind != PlanKind.PACK:
        return None
    grant_counts = db.scalars(
        select(PlanCreditGrant.credits_count).where(PlanCreditGrant.plan_id == plan.id)
    ).all()
    normalized = [int(count) for count in grant_counts if int(count) > 0]
    if normalized:
        if plan.credit_grants_relation == PlanCreditGrantsRelation.OR:
            return max(normalized)
        return sum(normalized)
    return int(plan.credits_count or 0)


def _forfait_period_bounds(plan: Plan) -> tuple[datetime, datetime]:
    if plan.forfait_start_date is None or plan.forfait_end_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La formule forfait doit avoir une date de debut et une date de fin configurees",
        )
    if plan.forfait_end_date <= plan.forfait_start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La date de fin de la formule forfait doit etre apres la date de debut",
        )
    started_at = datetime.combine(plan.forfait_start_date, datetime.min.time(), tzinfo=timezone.utc)
    ends_at = datetime.combine(plan.forfait_end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return started_at, ends_at


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    active: bool = True,
    purchase_user_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PlanOut]:
    if current_user.role not in {UserRole.CLIENT, UserRole.ADMIN}:
        permission_map = get_admin_permission_map(db, current_user)
        if not (permission_map.get("can_view_clients") or permission_map.get("can_view_quotes")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    stmt = select(Plan)
    if active:
        stmt = stmt.where(Plan.active.is_(True))
    if current_user.role == UserRole.CLIENT:
        stmt = stmt.where(Plan.is_private.is_(False))
    stmt = stmt.order_by(Plan.name.asc())

    plans = db.scalars(stmt).all()
    pricing_owner = current_user
    if current_user.role == UserRole.CLIENT:
        pricing_owner = _resolve_plan_owner(
            db,
            current_user=current_user,
            requested_user_id=purchase_user_id,
        )
    elif purchase_user_id is not None:
        pricing_owner = db.scalar(
            select(User).where(
                User.id == purchase_user_id,
                User.role == UserRole.CLIENT,
            )
        )
        if pricing_owner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target client not found")
    _, entitlement_names_by_plan = _entitlements_by_plan(db, plan_ids=[plan.id for plan in plans])
    output: list[PlanOut] = []
    for plan in plans:
        has_prior_purchase = (
            _has_prior_purchase_for_plan(
                db,
                user_id=pricing_owner.id,
                plan_id=plan.id,
            )
            if current_user.role == UserRole.CLIENT or purchase_user_id is not None
            else True
        )
        pricing = _purchase_pricing(
            db,
            plan=plan,
            country=(pricing_owner.residence_country or "FR").upper(),
            currency=(pricing_owner.preferred_currency or "EUR").upper(),
            on_date=date.today(),
            has_prior_purchase=has_prior_purchase,
        )
        output.append(PlanOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            kind=plan.kind,
            credits_count=_effective_pack_credits_for_plan(db, plan=plan),
            forfait_start_date=plan.forfait_start_date,
            forfait_end_date=plan.forfait_end_date,
            monthly_price_excl_vat=plan.monthly_price_excl_vat,
            price_ttc=pricing.total_incl_vat,
            base_price_ttc=pricing.base_price_ttc,
            currency_code=plan.currency_code,
            active=plan.active,
            is_trial_offer=bool(plan.is_trial_offer),
            first_purchase_required=pricing.first_purchase_required,
            first_purchase_fee_ttc=pricing.first_purchase_fee_ttc,
            first_purchase_partitions_price_ttc=pricing.first_purchase_partitions_price_ttc,
            first_purchase_breakdown=[
                PlanFirstPurchaseLineOut(
                    code=str(line.get("code") or ""),
                    label=str(line.get("label") or ""),
                    amount_ttc=Decimal(str(line.get("amount_ttc") or "0")),
                )
                for line in pricing.breakdown
            ],
            payment_methods=_plan_payment_methods(plan),
            entitlement_course_type_names=entitlement_names_by_plan.get(plan.id, []),
        ))
    return output


@router.get("/plans/{plan_id}/price-preview", response_model=PlanPricePreviewOut)
def plan_price_preview(
    plan_id: UUID,
    country: str = Query(default="FR", min_length=2, max_length=2),
    currency: str = Query(default="EUR", min_length=3, max_length=3),
    db: Session = Depends(get_db),
) -> PlanPricePreviewOut:
    normalized_country = country.upper()
    normalized_currency = currency.upper()
    today = date.today()

    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.active.is_(True), Plan.is_private.is_(False)))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    service_code = plan_service_code(plan.kind.value)
    vat_rate = resolve_vat_rate(
        db,
        country=normalized_country,
        service_code=service_code,
        on_date=today,
    )

    price_excl_vat: Decimal | None = None
    currency_code = (plan.currency_code or normalized_currency).upper()
    if plan.monthly_price_value is not None:
        raw_price = Decimal(plan.monthly_price_value)
        if plan.price_tax_mode == PlanPriceTaxMode.TTC:
            divisor = Decimal("1") + (vat_rate / Decimal("100"))
            price_excl_vat = raw_price if divisor <= 0 else (raw_price / divisor)
        else:
            price_excl_vat = raw_price
    elif plan.monthly_price_excl_vat is not None:
        price_excl_vat = Decimal(plan.monthly_price_excl_vat)
    else:
        resolved_price = resolve_plan_price(
            db,
            plan_id=plan.id,
            country=normalized_country,
            currency=normalized_currency,
            on_date=today,
        )
        if resolved_price is not None:
            price_excl_vat = Decimal(resolved_price.price_excl_vat)
            currency_code = resolved_price.currency_code

    if price_excl_vat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No price rule found for this plan")

    price, vat_amount, total = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)

    return PlanPricePreviewOut(
        plan_id=plan.id,
        country=normalized_country,
        currency=currency_code,
        price_excl_vat=price,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_incl_vat=total,
    )


@router.get("/public/formulas/{plan_id}/purchase-summary", response_model=PublicFormulaPurchaseSummaryOut)
def public_formula_purchase_summary(
    plan_id: UUID,
    db: Session = Depends(get_db),
) -> PublicFormulaPurchaseSummaryOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None or not plan.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formule introuvable")
    if not _formula_purchase_link_allowed(plan):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Achat par lien desactive pour cette formule")
    return _serialize_public_formula_summary(db, plan=plan)


@router.post("/public/formulas/{plan_id}/purchase-start", response_model=PublicFormulaPurchaseStartOut)
def public_formula_purchase_start(
    plan_id: UUID,
    payload: PublicFormulaPurchaseStartRequest,
    db: Session = Depends(get_db),
) -> PublicFormulaPurchaseStartOut:
    normalized_email = payload.email.strip().lower()
    if "@" not in normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email invalide")

    plan = db.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None or not plan.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formule introuvable")
    if not _formula_purchase_link_allowed(plan):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Achat par lien desactive pour cette formule")

    existing_client = db.scalar(
        select(User).where(User.email == normalized_email, User.role == UserRole.CLIENT)
    )
    trial_course_type: CourseType | None = None
    if plan.is_trial_offer and payload.session_id is not None:
        _, trial_course_type = _trial_session_and_course_type(
            db,
            plan=plan,
            session_id=payload.session_id,
        )
    pricing = _purchase_pricing(
        db,
        plan=plan,
        country=((existing_client.residence_country if existing_client is not None else None) or "FR").upper(),
        currency=((existing_client.preferred_currency if existing_client is not None else None) or plan.currency_code or "EUR").upper(),
        on_date=date.today(),
        has_prior_purchase=(
            _has_prior_purchase_for_plan(db, user_id=existing_client.id, plan_id=plan.id)
            if existing_client is not None
            else False
        ),
        trial_course_type=trial_course_type,
    )
    price_snapshot, currency = pricing.total_incl_vat, pricing.currency
    purchase_context = _encode_purchase_context(
        plan=plan,
        email=normalized_email,
        price_snapshot=price_snapshot,
        currency=currency,
        session_id=payload.session_id,
        booking_user_id=payload.booking_user_id,
        planning_return_to=payload.planning_return_to,
    )
    existing_user = existing_client is not None

    return PublicFormulaPurchaseStartOut(
        existing_user=existing_user,
        redirect_mode="login" if existing_user else "signup",
        purchase_context=purchase_context,
    )


@router.get("/public/formulas/purchase-context/{context_token}", response_model=PublicFormulaPurchaseContextOut)
def public_formula_purchase_context(
    context_token: str,
    db: Session = Depends(get_db),
) -> PublicFormulaPurchaseContextOut:
    payload = _decode_purchase_context(context_token)
    formula_id_raw = str(payload.get("formula_id") or "").strip()
    try:
        formula_id = UUID(formula_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide") from exc
    email = str(payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide")

    plan = db.scalar(select(Plan).where(Plan.id == formula_id))
    if plan is None or not plan.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formule introuvable")
    if not _formula_purchase_link_allowed(plan):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Achat par lien desactive pour cette formule")

    summary = _serialize_public_formula_summary(db, plan=plan)
    existing_client = db.scalar(select(User).where(User.email == email, User.role == UserRole.CLIENT))
    context_session_id_raw = str(payload.get("session_id") or "").strip()
    try:
        context_session_id = UUID(context_session_id_raw) if context_session_id_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide") from exc
    trial_course_type: CourseType | None = None
    if plan.is_trial_offer and context_session_id is not None:
        _, trial_course_type = _trial_session_and_course_type(
            db,
            plan=plan,
            session_id=context_session_id,
        )
    pricing = _purchase_pricing(
        db,
        plan=plan,
        country=((existing_client.residence_country if existing_client is not None else None) or "FR").upper(),
        currency=((existing_client.preferred_currency if existing_client is not None else None) or plan.currency_code or "EUR").upper(),
        on_date=date.today(),
        has_prior_purchase=(
            _has_prior_purchase_for_plan(db, user_id=existing_client.id, plan_id=plan.id)
            if existing_client is not None
            else False
        ),
        trial_course_type=trial_course_type,
    )
    price_snapshot, currency = pricing.total_incl_vat, pricing.currency
    if trial_course_type is not None:
        summary = summary.model_copy(
            update={
                "price_ttc": pricing.total_incl_vat,
                "base_price_ttc": pricing.base_price_ttc,
                "currency": pricing.currency,
                "first_purchase_fee_ttc": None,
                "first_purchase_partitions_price_ttc": None,
            }
        )
    return PublicFormulaPurchaseContextOut(
        purchase_context=context_token,
        email=email,
        formula_id=plan.id,
        formula_code=plan.code,
        formula_type=plan.kind,
        price_snapshot=price_snapshot,
        currency=currency,
        session_id=context_session_id,
        booking_user_id=str(payload.get("booking_user_id") or "").strip() or None,
        planning_return_to=str(payload.get("planning_return_to") or "").strip() or None,
        summary=summary,
    )


@router.post("/plans/{plan_id}/purchase", response_model=ClientSubscriptionOut, status_code=status.HTTP_201_CREATED)
def purchase_plan(
    plan_id: UUID,
    request: Request,
    payload: PlanPurchaseRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSubscriptionOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    payload = payload or PlanPurchaseRequest()
    accepted_terms = None
    if plan.kind in {PlanKind.PACK, PlanKind.SUBSCRIPTION}:
        if not payload.legal_terms_accepted:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Vous devez accepter les conditions générales de vente avant de poursuivre.",
            )
        accepted_terms = resolve_legal_terms(db, payload.legal_terms_language)
        if accepted_terms is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Les conditions générales de vente ne sont pas configurées.",
            )
    context_payload: dict[str, object] = {}
    context_booking_user_id: UUID | None = None
    context_session_id: UUID | None = None
    trial_course_type: CourseType | None = None
    if payload.purchase_context:
        context_payload = _decode_purchase_context(payload.purchase_context)
        if str(context_payload.get("formula_id") or "") != str(plan.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase context does not match this formula")
        if str(context_payload.get("email") or "").strip().lower() != current_user.email.strip().lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Purchase context does not belong to this account")
        context_booking_user_id_raw = str(context_payload.get("booking_user_id") or "").strip()
        context_session_id_raw = str(context_payload.get("session_id") or "").strip()
        try:
            context_booking_user_id = UUID(context_booking_user_id_raw) if context_booking_user_id_raw else None
            context_session_id = UUID(context_session_id_raw) if context_session_id_raw else None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Purchase context invalide") from exc
        if payload.user_id is not None and context_booking_user_id is not None and payload.user_id != context_booking_user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase member does not match the selected participant")
    owner = _resolve_plan_owner(
        db,
        current_user=current_user,
        requested_user_id=payload.user_id or context_booking_user_id,
    )
    payer_contact_id, checkout_payer = _plan_purchase_parties(
        purchaser=current_user,
        owner=owner,
    )

    now = datetime.now(timezone.utc)
    subscription_started_at = now
    if plan.kind == PlanKind.SUBSCRIPTION and payload.start_date is not None:
        if payload.start_date < now.date():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La date de demarrage d'un abonnement mensuel doit etre aujourd'hui ou dans le futur",
            )
        subscription_started_at = datetime.combine(payload.start_date, datetime.min.time(), tzinfo=timezone.utc)
    _lock_user_purchase_scope(db, owner.id)

    if plan.is_trial_offer:
        trial_course_type_ids = trial_plan_course_type_ids(db, plan_id=plan.id)
        if not trial_course_type_ids:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette offre d'essai n'est rattachee a aucun type de cours")
        if context_session_id is not None:
            trial_session, trial_course_type = _trial_session_and_course_type(
                db,
                plan=plan,
                session_id=context_session_id,
            )
            if has_trial_booking_for_course_type(
                db,
                user_id=owner.id,
                course_type_id=trial_session.course_type_id,
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un cours d'essai a deja ete utilise pour ce type de cours")
            if has_prior_course_attendance_for_course_type(
                db,
                user_id=owner.id,
                course_type_id=trial_session.course_type_id,
                reference_at=trial_session.start_at_utc,
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce participant a deja suivi ce type de cours")
            if has_available_trial_credit_for_course_type(
                db,
                user_id=owner.id,
                course_type_id=trial_session.course_type_id,
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un cours d'essai achete est deja disponible pour ce type de cours")
        elif all(
            has_trial_booking_for_course_type(db, user_id=owner.id, course_type_id=course_type_id)
            or has_prior_course_attendance_for_course_type(
                db,
                user_id=owner.id,
                course_type_id=course_type_id,
                reference_at=now,
            )
            or has_available_trial_credit_for_course_type(
                db,
                user_id=owner.id,
                course_type_id=course_type_id,
            )
            for course_type_id in trial_course_type_ids
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tous les cours d'essai de cette offre ont deja ete utilises ou achetes")
        if has_available_trial_credit(db, user_id=owner.id, plan_id=plan.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un cours d'essai achete est deja disponible pour ce participant")

    if plan.kind == PlanKind.SUBSCRIPTION and _has_same_subscription_in_current_month(
        db,
        user_id=owner.id,
        plan_id=plan.id,
        reference_at=subscription_started_at,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This subscription is already purchased for the current month",
        )

    if not plan.is_trial_offer:
        covering_plan_name = _covering_current_plan_name(
            db,
            user_id=owner.id,
            requested_plan_id=plan.id,
            reference_at=subscription_started_at,
        )
        if covering_plan_name is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cet achat est déjà inclus dans votre formule actuelle "
                    f'« {covering_plan_name} ». Aucun paiement supplémentaire n\'est nécessaire.'
                ),
            )

    if plan.kind == PlanKind.PACK and not plan.is_trial_offer and not bool(payload.confirm_existing_pack_purchase) and _has_active_pack_with_remaining_credits(
        db,
        user_id=owner.id,
        now=now,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active pack with remaining credits already exists",
        )

    credits_initial: int | None = None
    credits_remaining: int | None = None
    ends_at = None
    configured_methods = _plan_payment_methods(plan)
    requested_method = (payload.billing_method_code or "").strip().upper()
    if requested_method and requested_method not in configured_methods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Moyen de paiement non autorise pour cette formule",
        )
    method_code = (requested_method or _default_subscription_billing_method(plan) or "").strip().upper() or None
    has_prior_purchase = _has_prior_purchase_for_plan(db, user_id=owner.id, plan_id=plan.id)
    pricing = _purchase_pricing(
        db,
        plan=plan,
        country=(checkout_payer.residence_country or "FR").upper(),
        currency=(checkout_payer.preferred_currency or "EUR").upper(),
        on_date=subscription_started_at.date(),
        has_prior_purchase=has_prior_purchase,
        trial_course_type=trial_course_type,
    )
    amount_due = pricing.total_incl_vat
    currency_code = pricing.currency
    requires_online_checkout = amount_due > Decimal("0.00")
    if plan.kind == PlanKind.SUBSCRIPTION and requires_online_checkout and method_code not in {"CARD_ONLINE", "SEPA_DEBIT"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Un abonnement payant doit utiliser la carte ou le prelevement SEPA",
        )
    if plan.is_trial_offer and requires_online_checkout and not _is_online_collection_method(method_code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Une offre d'essai payante doit utiliser un moyen de paiement en ligne",
        )
    should_start_pending = requires_online_checkout and _is_online_collection_method(method_code)

    if plan.kind == PlanKind.PACK:
        credits_initial = _effective_pack_credits_for_plan(db, plan=plan) or 0
        credits_remaining = credits_initial
        ends_at = add_months_utc(now, int(plan.pack_validity_months or 12))
    elif plan.kind == PlanKind.SUBSCRIPTION:
        ends_at = add_months_utc(subscription_started_at, 1)
    elif plan.kind == PlanKind.FORFAIT:
        subscription_started_at, ends_at = _forfait_period_bounds(plan)

    initial_status = SubscriptionStatus.PENDING if should_start_pending else SubscriptionStatus.ACTIVE
    if plan.kind == PlanKind.FORFAIT and ends_at is not None and ends_at <= now:
        initial_status = SubscriptionStatus.EXPIRED
    subscription = ClientPlanSubscription(
        user_id=owner.id,
        payer_contact_id=payer_contact_id,
        plan_id=plan.id,
        status=initial_status,
        started_at=subscription_started_at,
        ends_at=ends_at,
        credits_initial=credits_initial,
        credits_remaining=credits_remaining,
        auto_renew=(plan.kind == PlanKind.SUBSCRIPTION and not should_start_pending),
        billing_method_code=method_code,
        next_payment_at=ends_at if plan.kind == PlanKind.SUBSCRIPTION else None,
        current_period_start=subscription_started_at if plan.kind == PlanKind.SUBSCRIPTION else None,
        current_period_end=ends_at if plan.kind == PlanKind.SUBSCRIPTION else None,
        initial_amount_excl_vat=pricing.amount_excl_vat,
        initial_vat_amount=pricing.vat_amount,
        initial_total_incl_vat=pricing.total_incl_vat,
        initial_currency_code=pricing.currency,
        initial_price_breakdown_json=pricing.breakdown,
        first_purchase_charges_applied=pricing.first_purchase_required,
        forfait_loyalty_discount_per_hour_ttc=Decimal("0.00"),
        forfait_family_discount_per_hour_ttc=Decimal("0.00"),
        forfait_short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
        legal_terms_accepted_at=now if accepted_terms is not None else None,
        legal_terms_language=accepted_terms.language if accepted_terms is not None else None,
        legal_terms_version=accepted_terms.version if accepted_terms is not None else None,
        legal_terms_content_hash=accepted_terms.content_hash if accepted_terms is not None else None,
        legal_terms_content_snapshot=accepted_terms.content if accepted_terms is not None else None,
        legal_terms_acceptance_ip=_request_ip(request) if accepted_terms is not None else None,
    )
    db.add(subscription)
    db.flush()
    promote_client_to_active_student(owner)
    db.add(owner)

    checkout_url: str | None = None
    if should_start_pending and method_code is not None:
        success_url, cancel_url, webhook_url = _checkout_urls(
            owner_id=owner.id,
            subscription_id=subscription.id,
            purchase_context=payload.purchase_context,
        )
        checkout = create_checkout_session(
            db,
            CheckoutCreateRequest(
                amount=amount_due,
                currency=currency_code,
                description=" + ".join(str(line.get("label") or "") for line in pricing.breakdown),
                customer_email=checkout_payer.email,
                customer_first_name=checkout_payer.first_name,
                customer_last_name=checkout_payer.last_name,
                customer_country=(checkout_payer.residence_country or "FR"),
                success_return_url=success_url,
                cancel_return_url=cancel_url,
                webhook_url=with_webhook_secret(webhook_url, resolve_webhook_secret(db)),
                save_payment_method=(plan.kind == PlanKind.SUBSCRIPTION),
                metadata={
                    "client_id": str(owner.id),
                    "payer_contact_id": str(checkout_payer.id),
                    "subscription_id": str(subscription.id),
                    "plan_id": str(plan.id),
                    "plan_code": plan.code,
                    "is_trial_offer": "1" if plan.is_trial_offer else "0",
                    "requested_billing_method": method_code,
                    "first_purchase_charges_applied": "1" if pricing.first_purchase_required else "0",
                },
            ),
            provider_override=(PaymentProvider.STRIPE if plan.kind == PlanKind.SUBSCRIPTION else None),
        )
        if not checkout.success or not checkout.checkout_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Impossible de creer la session de paiement ({checkout.message})",
            )
        subscription.payment_provider_subscription_ref = checkout.provider_reference
        subscription.payment_provider_code = checkout.provider.value
        if plan.kind == PlanKind.SUBSCRIPTION:
            subscription.payment_method_setup_required = True
        subscription.last_payment_status = (checkout.status or "WAITING_PAYMENT").strip().upper() or "WAITING_PAYMENT"
        checkout_url = checkout.checkout_url

    automation_notifications = []
    if initial_status == SubscriptionStatus.ACTIVE:
        automation_notifications = schedule_plan_purchase_triggers(
            db,
            subscription=subscription,
            plan=plan,
            occurred_at=now,
        )

    db.commit()
    enqueue_notifications(automation_notifications)
    db.refresh(subscription)

    entitlement_ids_map, entitlement_names_map = _entitlements_by_plan(db, plan_ids=[plan.id])
    credit_allocations_map = subscription_credit_allocations(db, subscriptions=[(subscription, plan)])

    return ClientSubscriptionOut(
        id=subscription.id,
        status=subscription.status,
        started_at=subscription.started_at,
        ends_at=subscription.ends_at,
        next_payment_at=subscription.next_payment_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        credits_initial=subscription.credits_initial,
        credits_remaining=subscription.credits_remaining,
        credit_allocations=credit_allocations_map.get(subscription.id, []),
        auto_renew=subscription.auto_renew,
        bookings_blocked=bool(subscription.bookings_blocked),
        billing_method_code=subscription.billing_method_code,
        payment_method_type=subscription.payment_method_type,
        payment_method_brand=subscription.payment_method_brand,
        payment_method_last4=subscription.payment_method_last4,
        payment_method_exp_month=subscription.payment_method_exp_month,
        payment_method_exp_year=subscription.payment_method_exp_year,
        payment_method_setup_required=bool(subscription.payment_method_setup_required),
        payment_method_setup_completed_at=subscription.payment_method_setup_completed_at,
        last_successful_charge_at=subscription.last_successful_charge_at,
        payment_alert_started_at=subscription.payment_alert_started_at,
        pre_termination_at=subscription.pre_termination_at,
        direct_payment_recovery_url=subscription.direct_payment_recovery_url,
        suspension_starts_at=subscription.suspension_starts_at,
        suspension_ends_at=subscription.suspension_ends_at,
        suspension_start_date=subscription.suspension_start_date,
        suspension_end_date=subscription.suspension_end_date,
        cancellation_requested_at=subscription.cancellation_requested_at,
        cancellation_effective_at=subscription.cancellation_effective_at,
        cancellation_request_status=subscription.cancellation_request_status,
        cancellation_request_note=subscription.cancellation_request_note,
        cancellation_request_reviewed_at=subscription.cancellation_request_reviewed_at,
        plan=PlanMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
            is_trial_offer=bool(plan.is_trial_offer),
            price_ttc=amount_due,
            currency_code=currency_code,
        ),
        entitlement_course_type_ids=entitlement_ids_map.get(plan.id, []),
        entitlement_course_type_names=entitlement_names_map.get(plan.id, []),
        checkout_url=checkout_url,
        payment_reference=subscription.payment_provider_subscription_ref,
    )


@router.get("/clients/me/subscriptions", response_model=list[ClientSubscriptionOut])
def list_my_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientSubscriptionOut]:
    rows = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.user_id == current_user.id)
        .order_by(ClientPlanSubscription.created_at.desc())
    ).all()
    plan_ids = list({plan.id for _, plan in rows})
    entitlement_ids_map, entitlement_names_map = _entitlements_by_plan(db, plan_ids=plan_ids)
    credit_allocations_map = subscription_credit_allocations(db, subscriptions=rows)
    now = datetime.now(timezone.utc)
    changed = False
    payload: list[ClientSubscriptionOut] = []
    for sub, plan in rows:
        if reconcile_subscription_status(sub, now=now, plan_kind=plan.kind):
            changed = True
        price_ttc, currency_code = _plan_amount_due_and_currency(
            db,
            plan=plan,
            country=(current_user.residence_country or "FR").upper(),
            currency=(current_user.preferred_currency or "EUR").upper(),
            on_date=now.date(),
        )
        payload.append(
            ClientSubscriptionOut(
                id=sub.id,
                status=sub.status,
                started_at=sub.started_at,
                ends_at=sub.ends_at,
                next_payment_at=sub.next_payment_at,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                credits_initial=sub.credits_initial,
                credits_remaining=sub.credits_remaining,
                credit_allocations=credit_allocations_map.get(sub.id, []),
                auto_renew=sub.auto_renew,
                bookings_blocked=bool(sub.bookings_blocked),
                billing_method_code=sub.billing_method_code,
                payment_method_type=sub.payment_method_type,
                payment_method_brand=sub.payment_method_brand,
                payment_method_last4=sub.payment_method_last4,
                payment_method_exp_month=sub.payment_method_exp_month,
                payment_method_exp_year=sub.payment_method_exp_year,
                payment_method_setup_required=bool(sub.payment_method_setup_required),
                payment_method_setup_completed_at=sub.payment_method_setup_completed_at,
                last_successful_charge_at=sub.last_successful_charge_at,
                payment_alert_started_at=sub.payment_alert_started_at,
                pre_termination_at=sub.pre_termination_at,
                direct_payment_recovery_url=sub.direct_payment_recovery_url,
                suspension_starts_at=sub.suspension_starts_at,
                suspension_ends_at=sub.suspension_ends_at,
                suspension_start_date=sub.suspension_start_date,
                suspension_end_date=sub.suspension_end_date,
                cancellation_requested_at=sub.cancellation_requested_at,
                cancellation_effective_at=sub.cancellation_effective_at,
                cancellation_request_status=sub.cancellation_request_status,
                cancellation_request_note=sub.cancellation_request_note,
                cancellation_request_reviewed_at=sub.cancellation_request_reviewed_at,
                plan=PlanMiniOut(
                    id=plan.id,
                    code=plan.code,
                    name=plan.name,
                    kind=plan.kind,
                    is_trial_offer=bool(plan.is_trial_offer),
                    price_ttc=price_ttc,
                    currency_code=currency_code,
                ),
                entitlement_course_type_ids=entitlement_ids_map.get(plan.id, []),
                entitlement_course_type_names=entitlement_names_map.get(plan.id, []),
            )
        )
    if changed:
        db.commit()
    return payload


@router.post(
    "/clients/me/subscriptions/{subscription_id}/cancellation-request",
    response_model=ClientSubscriptionOut,
)
def request_my_subscription_cancellation(
    subscription_id: UUID,
    payload: ClientSubscriptionCancellationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSubscriptionOut:
    enabled_value = db.scalar(
        select(AppSetting.value).where(AppSetting.key == "config_subscription_online_resiliation_enabled")
    )
    if enabled_value is not None and enabled_value.strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La demande de resiliation en ligne est desactivee")

    row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.id == subscription_id,
            ClientPlanSubscription.user_id == current_user.id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Abonnement introuvable")
    subscription, plan = row
    if plan.kind != PlanKind.SUBSCRIPTION:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Seul un abonnement mensuel peut etre resilie")
    if subscription.status not in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAYMENT_ALERT,
        SubscriptionStatus.PAUSED,
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cet abonnement ne peut pas faire l'objet d'une demande")
    if subscription.cancellation_request_status == "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une demande de resiliation est deja en attente")
    if subscription.cancellation_effective_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La resiliation de cet abonnement est deja programmee")

    now = datetime.now(timezone.utc)
    note = (payload.note or "").strip() or None
    subscription.cancellation_requested_at = now
    subscription.cancellation_request_status = "PENDING"
    subscription.cancellation_request_note = note
    subscription.cancellation_request_reviewed_at = None
    db.add(subscription)
    db.flush()
    send_cancellation_request_admin_notifications(
        db,
        client=current_user,
        plan=plan,
        subscription=subscription,
        requested_at=now,
        note=note,
    )
    db.commit()

    refreshed = list_my_subscriptions(db=db, current_user=current_user)
    return next(item for item in refreshed if item.id == subscription.id)
