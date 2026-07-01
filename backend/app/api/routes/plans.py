from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_admin_permission_map, get_current_user, get_db, require_roles
from app.core.config import settings
from app.models.catalog import CourseType
from app.models.family import ClientFamilyLink
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
    PlanMiniOut,
    PlanOut,
    PlanPricePreviewOut,
    PlanPurchaseRequest,
    PublicFormulaPurchaseContextOut,
    PublicFormulaPurchaseStartOut,
    PublicFormulaPurchaseStartRequest,
    PublicFormulaPurchaseSummaryOut,
)
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, with_webhook_secret
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.payment_provider import resolve_webhook_secret
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.client_status import promote_client_to_active_student
from app.services.subscriptions import add_months_utc, reconcile_subscription_status

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


def _formula_price_snapshot(plan: Plan) -> tuple[Decimal | None, str]:
    if plan.monthly_price_value is not None:
        return Decimal(plan.monthly_price_value).quantize(Decimal("0.01")), (plan.currency_code or "EUR").upper()
    if plan.monthly_price_excl_vat is not None:
        return Decimal(plan.monthly_price_excl_vat).quantize(Decimal("0.01")), (plan.currency_code or "EUR").upper()
    return None, (plan.currency_code or "EUR").upper()


def _restriction_period_label(raw: str) -> str:
    value = raw.strip().upper()
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
    price_snapshot, currency = _formula_price_snapshot(plan)
    payment_methods = _plan_payment_methods(plan)
    return PublicFormulaPurchaseSummaryOut(
        formula_id=plan.id,
        formula_code=plan.code,
        formula_type=plan.kind,
        name=plan.name,
        description=plan.description,
        active=bool(plan.active),
        is_private=bool(plan.is_private),
        purchase_link_allowed=_formula_purchase_link_allowed(plan),
        purchase_url=_purchase_url_for_plan(plan.id),
        price_ttc=price_snapshot,
        currency=currency,
        frequency_label=_formula_frequency_label(plan.kind),
        includes=includes,
        restriction_labels=restriction_labels,
        payment_methods=payment_methods,
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
    if not plan_ids:
        return {}, {}

    rows = db.execute(
        select(PlanEntitlement.plan_id, PlanEntitlement.course_type_id, CourseType.name)
        .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
        .where(PlanEntitlement.plan_id.in_(plan_ids))
        .order_by(PlanEntitlement.plan_id.asc(), CourseType.name.asc())
    ).all()

    ids_map: dict[UUID, list[UUID]] = defaultdict(list)
    names_map: dict[UUID, list[str]] = defaultdict(list)
    for plan_id, course_type_id, course_type_name in rows:
        ids_map[plan_id].append(course_type_id)
        names_map[plan_id].append(course_type_name)

    return dict(ids_map), dict(names_map)


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
    return [
        PlanOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
            credits_count=_effective_pack_credits_for_plan(db, plan=plan),
            forfait_start_date=plan.forfait_start_date,
            forfait_end_date=plan.forfait_end_date,
            monthly_price_excl_vat=plan.monthly_price_excl_vat,
            currency_code=plan.currency_code,
            active=plan.active,
        )
        for plan in plans
    ]


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

    price_snapshot, currency = _formula_price_snapshot(plan)
    purchase_context = _encode_purchase_context(
        plan=plan,
        email=normalized_email,
        price_snapshot=price_snapshot,
        currency=currency,
        session_id=payload.session_id,
        booking_user_id=payload.booking_user_id,
        planning_return_to=payload.planning_return_to,
    )
    existing_user = db.scalar(select(User.id).where(User.email == normalized_email, User.role == UserRole.CLIENT)) is not None

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
    price_snapshot, currency = _formula_price_snapshot(plan)
    return PublicFormulaPurchaseContextOut(
        purchase_context=context_token,
        email=email,
        formula_id=plan.id,
        formula_code=plan.code,
        formula_type=plan.kind,
        price_snapshot=price_snapshot,
        currency=currency,
        session_id=str(payload.get("session_id") or "").strip() or None,
        booking_user_id=str(payload.get("booking_user_id") or "").strip() or None,
        planning_return_to=str(payload.get("planning_return_to") or "").strip() or None,
        summary=summary,
    )


@router.post("/plans/{plan_id}/purchase", response_model=ClientSubscriptionOut, status_code=status.HTTP_201_CREATED)
def purchase_plan(
    plan_id: UUID,
    payload: PlanPurchaseRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSubscriptionOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    payload = payload or PlanPurchaseRequest()
    owner = _resolve_plan_owner(
        db,
        current_user=current_user,
        requested_user_id=payload.user_id,
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

    if plan.kind == PlanKind.PACK and not bool(payload.confirm_existing_pack_purchase) and _has_active_pack_with_remaining_credits(
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
    method_code = (_default_subscription_billing_method(plan) or "").strip().upper() or None
    amount_due, currency_code = _plan_amount_due_and_currency(
        db,
        plan=plan,
        country=(owner.residence_country or "FR").upper(),
        currency=(owner.preferred_currency or "EUR").upper(),
        on_date=subscription_started_at.date(),
    )
    requires_online_checkout = amount_due > Decimal("0.00")
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
        forfait_loyalty_discount_per_hour_ttc=Decimal("0.00"),
        forfait_family_discount_per_hour_ttc=Decimal("0.00"),
        forfait_short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
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
                description=f"{plan.name} ({owner.email})",
                customer_email=owner.email,
                success_return_url=success_url,
                cancel_return_url=cancel_url,
                webhook_url=with_webhook_secret(webhook_url, resolve_webhook_secret(db)),
                metadata={
                    "client_id": str(owner.id),
                    "subscription_id": str(subscription.id),
                    "plan_id": str(plan.id),
                    "plan_code": plan.code,
                },
            ),
        )
        if not checkout.success or not checkout.checkout_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Impossible de creer la session de paiement ({checkout.message})",
            )
        subscription.payment_provider_subscription_ref = checkout.provider_reference
        subscription.last_payment_status = (checkout.status or "WAITING_PAYMENT").strip().upper() or "WAITING_PAYMENT"
        checkout_url = checkout.checkout_url

    db.commit()
    db.refresh(subscription)

    entitlement_ids_map, entitlement_names_map = _entitlements_by_plan(db, plan_ids=[plan.id])

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
        auto_renew=subscription.auto_renew,
        bookings_blocked=bool(subscription.bookings_blocked),
        billing_method_code=subscription.billing_method_code,
        last_successful_charge_at=subscription.last_successful_charge_at,
        payment_alert_started_at=subscription.payment_alert_started_at,
        pre_termination_at=subscription.pre_termination_at,
        direct_payment_recovery_url=subscription.direct_payment_recovery_url,
        suspension_starts_at=subscription.suspension_starts_at,
        suspension_ends_at=subscription.suspension_ends_at,
        cancellation_requested_at=subscription.cancellation_requested_at,
        cancellation_effective_at=subscription.cancellation_effective_at,
        plan=PlanMiniOut(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            kind=plan.kind,
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
    now = datetime.now(timezone.utc)
    changed = False
    payload: list[ClientSubscriptionOut] = []
    for sub, plan in rows:
        if reconcile_subscription_status(sub, now=now, plan_kind=plan.kind):
            changed = True
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
                auto_renew=sub.auto_renew,
                bookings_blocked=bool(sub.bookings_blocked),
                billing_method_code=sub.billing_method_code,
                last_successful_charge_at=sub.last_successful_charge_at,
                payment_alert_started_at=sub.payment_alert_started_at,
                pre_termination_at=sub.pre_termination_at,
                direct_payment_recovery_url=sub.direct_payment_recovery_url,
                suspension_starts_at=sub.suspension_starts_at,
                suspension_ends_at=sub.suspension_ends_at,
                cancellation_requested_at=sub.cancellation_requested_at,
                cancellation_effective_at=sub.cancellation_effective_at,
                plan=PlanMiniOut(
                    id=plan.id,
                    code=plan.code,
                    name=plan.name,
                    kind=plan.kind,
                ),
                entitlement_course_type_ids=entitlement_ids_map.get(plan.id, []),
                entitlement_course_type_names=entitlement_names_map.get(plan.id, []),
            )
        )
    if changed:
        db.commit()
    return payload
