from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
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
from app.schemas.plan import ClientSubscriptionOut, PlanMiniOut, PlanOut, PlanPricePreviewOut, PlanPurchaseRequest
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, with_webhook_secret
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.subscriptions import add_months_utc, reconcile_subscription_status

router = APIRouter()


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
            ClientPlanSubscription.status.in_([SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]),
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
    candidate = (settings.frontend_base_url or "").strip() or "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _checkout_urls(*, owner_id: UUID, subscription_id: UUID) -> tuple[str, str, str]:
    query = f"tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}"
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
    current_user: User = Depends(require_roles(UserRole.CLIENT, UserRole.ADMIN)),
) -> list[PlanOut]:
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


@router.post("/plans/{plan_id}/purchase", response_model=ClientSubscriptionOut, status_code=status.HTTP_201_CREATED)
def purchase_plan(
    plan_id: UUID,
    payload: PlanPurchaseRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientSubscriptionOut:
    plan = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.active.is_(True), Plan.is_private.is_(False)))
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

    if plan.kind == PlanKind.PACK and _has_active_pack_with_remaining_credits(
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
        forfait_loyalty_discount_per_hour_ttc=Decimal("0.00"),
        forfait_family_discount_per_hour_ttc=Decimal("0.00"),
        forfait_short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
    )
    db.add(subscription)
    db.flush()

    checkout_url: str | None = None
    if should_start_pending and method_code is not None:
        success_url, cancel_url, webhook_url = _checkout_urls(owner_id=owner.id, subscription_id=subscription.id)
        checkout = create_checkout_session(
            db,
            CheckoutCreateRequest(
                amount=amount_due,
                currency=currency_code,
                description=f"{plan.name} ({owner.email})",
                customer_email=owner.email,
                success_return_url=success_url,
                cancel_return_url=cancel_url,
                webhook_url=with_webhook_secret(webhook_url, settings.payment_webhook_secret),
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
        credits_initial=subscription.credits_initial,
        credits_remaining=subscription.credits_remaining,
        auto_renew=subscription.auto_renew,
        billing_method_code=subscription.billing_method_code,
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
                credits_initial=sub.credits_initial,
                credits_remaining=sub.credits_remaining,
                auto_renew=sub.auto_renew,
                billing_method_code=sub.billing_method_code,
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
