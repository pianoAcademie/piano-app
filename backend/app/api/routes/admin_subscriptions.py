from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.client_record import ClientPaymentRefund
from app.models.notification_engine import Notification
from app.models.plan import ClientPlanSubscription, Plan, PlanKind
from app.models.subscription_engine import SubscriptionBillingCycle, SubscriptionPaymentAttempt
from app.models.user import User, UserRole
from app.schemas.subscription_engine import (
    AdminSubscriptionChargeNowRequest,
    AdminSubscriptionAttemptOut,
    AdminSubscriptionCycleOut,
    AdminSubscriptionEngineDetailOut,
    AdminSubscriptionEngineListOut,
    AdminSubscriptionEngineRowOut,
    AdminSubscriptionNotificationOut,
    AdminSubscriptionRefundRequest,
)
from app.services.payment_provider import PaymentProvider
from app.services.psp_gateway import PayplugGateway
from app.services.subscription_billing import (
    resolve_provider_secret,
    run_subscription_charge_now,
    run_subscription_retry_job,
)

router = APIRouter(prefix="/admin/subscriptions")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _display_name(user: User) -> str:
    full_name = (f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}").strip()
    return full_name or user.email


def _sub_status(sub: ClientPlanSubscription) -> str:
    return sub.status.value if hasattr(sub.status, "value") else str(sub.status)


def _row_out(
    db: Session,
    *,
    sub: ClientPlanSubscription,
    plan: Plan,
    owner: User,
) -> AdminSubscriptionEngineRowOut:
    latest_cycle = db.scalar(
        select(SubscriptionBillingCycle)
        .where(SubscriptionBillingCycle.subscription_id == sub.id)
        .order_by(SubscriptionBillingCycle.billing_date.desc(), SubscriptionBillingCycle.created_at.desc())
        .limit(1)
    )
    amount: Decimal | None = None
    currency: str | None = None
    if latest_cycle is not None:
        amount = Decimal(latest_cycle.amount)
        currency = latest_cycle.currency

    return AdminSubscriptionEngineRowOut(
        id=sub.id,
        customer_id=owner.id,
        customer_name=_display_name(owner),
        customer_email=owner.email,
        plan_id=plan.id,
        plan_name=plan.name,
        status=_sub_status(sub),
        bookings_blocked=bool(sub.bookings_blocked),
        next_billing_date=sub.next_payment_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        last_attempt_at=(latest_cycle.last_attempt_at if latest_cycle else None),
        last_successful_charge_at=sub.last_successful_charge_at,
        last_cycle_status=(latest_cycle.status if latest_cycle else None),
        recovery_url=sub.direct_payment_recovery_url or (latest_cycle.payment_recovery_url if latest_cycle else None),
        amount=amount,
        currency=currency,
    )


def _load_subscription(db: Session, subscription_id: UUID) -> tuple[ClientPlanSubscription, Plan, User]:
    row = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(
            ClientPlanSubscription.id == subscription_id,
            Plan.kind == PlanKind.SUBSCRIPTION,
        )
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return row


def _detail_out(db: Session, *, sub: ClientPlanSubscription, plan: Plan, owner: User) -> AdminSubscriptionEngineDetailOut:
    subscription_out = _row_out(db, sub=sub, plan=plan, owner=owner)

    cycles = db.scalars(
        select(SubscriptionBillingCycle)
        .where(SubscriptionBillingCycle.subscription_id == sub.id)
        .order_by(SubscriptionBillingCycle.billing_date.desc(), SubscriptionBillingCycle.created_at.desc())
        .limit(100)
    ).all()
    cycle_ids = [row.id for row in cycles]

    attempts = db.scalars(
        select(SubscriptionPaymentAttempt)
        .where(SubscriptionPaymentAttempt.subscription_id == sub.id)
        .order_by(SubscriptionPaymentAttempt.attempted_at.desc(), SubscriptionPaymentAttempt.created_at.desc())
        .limit(500)
    ).all()

    notifications = db.scalars(
        select(Notification)
        .where(
            Notification.related_entity_type == "subscription_billing_cycle",
            Notification.related_entity_id.in_(cycle_ids) if cycle_ids else False,
        )
        .order_by(Notification.created_at.desc())
        .limit(500)
    ).all() if cycle_ids else []

    initial_refund = db.scalar(
        select(ClientPaymentRefund.id).where(
            ClientPaymentRefund.user_id == owner.id,
            ClientPaymentRefund.source == "PLAN_PURCHASE",
            ClientPaymentRefund.source_payment_id == sub.id,
        )
    )
    initial_reference = (sub.payment_provider_subscription_ref or "").strip()

    return AdminSubscriptionEngineDetailOut(
        subscription=subscription_out,
        cycles=[
            AdminSubscriptionCycleOut(
                id=row.id,
                period_start=row.period_start,
                period_end=row.period_end,
                billing_date=row.billing_date,
                status=row.status,
                attempt_count=int(row.attempt_count or 0),
                first_attempt_at=row.first_attempt_at,
                last_attempt_at=row.last_attempt_at,
                next_retry_at=row.next_retry_at,
                paid_at=row.paid_at,
                amount=Decimal(row.amount),
                currency=row.currency,
                payment_recovery_url=row.payment_recovery_url,
            )
            for row in cycles
        ],
        attempts=[
            AdminSubscriptionAttemptOut(
                id=row.id,
                billing_cycle_id=row.billing_cycle_id,
                attempt_number=int(row.attempt_number),
                attempted_at=row.attempted_at,
                amount=Decimal(row.amount),
                currency=row.currency,
                status=row.status,
                provider_name=row.provider_name,
                provider_payment_id=row.provider_payment_id,
                provider_status=row.provider_status,
                failure_code=row.failure_code,
                failure_reason=row.failure_reason,
            )
            for row in attempts
        ],
        notifications=[
            AdminSubscriptionNotificationOut(
                id=row.id,
                notification_type=row.notification_type,
                status=row.status,
                recipient_email=row.recipient_email,
                scheduled_for=row.scheduled_for,
                sent_at=row.sent_at,
                failed_at=row.failed_at,
                failure_reason=row.failure_reason,
            )
            for row in notifications
        ],
        initial_payment_refundable=initial_reference.startswith("pay_") and initial_refund is None,
        initial_payment_refunded=initial_refund is not None,
    )


@router.get("", response_model=AdminSubscriptionEngineListOut)
def list_admin_subscriptions(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    only_retry_due: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineListOut:
    stmt = (
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(Plan.kind == PlanKind.SUBSCRIPTION)
    )
    if status_filter:
        stmt = stmt.where(ClientPlanSubscription.status == status_filter.strip().upper())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                Plan.name.ilike(pattern),
                Plan.code.ilike(pattern),
            )
        )

    rows = db.execute(
        stmt.order_by(ClientPlanSubscription.next_payment_at.asc().nullsfirst(), ClientPlanSubscription.created_at.desc()).limit(limit)
    ).all()

    now = _utcnow()
    items: list[AdminSubscriptionEngineRowOut] = []
    for sub, plan, owner in rows:
        out = _row_out(db, sub=sub, plan=plan, owner=owner)
        if only_retry_due:
            if out.last_cycle_status != "failed_first_attempt":
                continue
            latest_cycle = db.scalar(
                select(SubscriptionBillingCycle)
                .where(SubscriptionBillingCycle.subscription_id == sub.id)
                .order_by(SubscriptionBillingCycle.billing_date.desc(), SubscriptionBillingCycle.created_at.desc())
                .limit(1)
            )
            if latest_cycle is None or latest_cycle.next_retry_at is None or latest_cycle.next_retry_at > now:
                continue
        items.append(out)

    return AdminSubscriptionEngineListOut(items=items, total=len(items))


@router.get("/{subscription_id}", response_model=AdminSubscriptionEngineDetailOut)
def get_admin_subscription_detail(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineDetailOut:
    sub, plan, owner = _load_subscription(db, subscription_id)
    return _detail_out(db, sub=sub, plan=plan, owner=owner)


@router.post("/{subscription_id}/retry-now", response_model=AdminSubscriptionEngineDetailOut)
def retry_admin_subscription_now(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineDetailOut:
    sub, plan, owner = _load_subscription(db, subscription_id)
    now = _utcnow()

    rows = db.scalars(
        select(SubscriptionBillingCycle)
        .where(
            SubscriptionBillingCycle.subscription_id == sub.id,
            SubscriptionBillingCycle.status == "failed_first_attempt",
        )
        .order_by(SubscriptionBillingCycle.next_retry_at.asc().nullsfirst(), SubscriptionBillingCycle.created_at.asc())
        .limit(20)
        .with_for_update()
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No retryable billing cycle found")

    for row in rows:
        row.next_retry_at = now
        db.add(row)
    try:
        run_subscription_retry_job(db, now=now, limit=500)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _detail_out(db, sub=sub, plan=plan, owner=owner)


@router.post("/{subscription_id}/charge-now", response_model=AdminSubscriptionEngineDetailOut)
def charge_admin_subscription_now(
    subscription_id: UUID,
    payload: AdminSubscriptionChargeNowRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineDetailOut:
    if not payload.confirm_charge:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Explicit charge confirmation is required")
    sub, plan, owner = _load_subscription(db, subscription_id)
    now = _utcnow()
    try:
        run_subscription_charge_now(
            db,
            subscription=sub,
            plan=plan,
            owner=owner,
            now=now,
            expected_amount=payload.expected_amount,
            expected_currency=payload.expected_currency,
        )
    except (RuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _detail_out(db, sub=sub, plan=plan, owner=owner)


def _refund_payplug_payment(db: Session, *, payment_reference: str) -> None:
    gateway = PayplugGateway(api_key=resolve_provider_secret(db, provider=PaymentProvider.PAYPLUG))
    result = gateway.refund_payment(payment_reference)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Payplug refund failed: {result.status}")


@router.post("/{subscription_id}/refund-initial", response_model=AdminSubscriptionEngineDetailOut)
def refund_admin_subscription_initial_payment(
    subscription_id: UUID,
    payload: AdminSubscriptionRefundRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineDetailOut:
    if not payload.confirm_refund:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Explicit refund confirmation is required")
    sub, plan, owner = _load_subscription(db, subscription_id)
    payment_reference = (sub.payment_provider_subscription_ref or "").strip()
    if not payment_reference.startswith("pay_"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No refundable initial Payplug payment found")
    _refund_payplug_payment(db, payment_reference=payment_reference)

    refund = db.scalar(
        select(ClientPaymentRefund).where(
            ClientPaymentRefund.user_id == owner.id,
            ClientPaymentRefund.source == "PLAN_PURCHASE",
            ClientPaymentRefund.source_payment_id == sub.id,
        )
    )
    now = _utcnow()
    if refund is None:
        refund = ClientPaymentRefund(
            user_id=owner.id,
            source="PLAN_PURCHASE",
            source_payment_id=sub.id,
            actor_user_id=actor.id,
            refunded_at=now,
            updated_at=now,
            reason="Remboursement Payplug administrateur",
        )
    else:
        refund.actor_user_id = actor.id
        refund.refunded_at = now
        refund.updated_at = now
    db.add(refund)
    db.commit()
    return _detail_out(db, sub=sub, plan=plan, owner=owner)


@router.post("/{subscription_id}/attempts/{attempt_id}/refund", response_model=AdminSubscriptionEngineDetailOut)
def refund_admin_subscription_attempt(
    subscription_id: UUID,
    attempt_id: UUID,
    payload: AdminSubscriptionRefundRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSubscriptionEngineDetailOut:
    if not payload.confirm_refund:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Explicit refund confirmation is required")
    sub, plan, owner = _load_subscription(db, subscription_id)
    attempt = db.scalar(
        select(SubscriptionPaymentAttempt).where(
            SubscriptionPaymentAttempt.id == attempt_id,
            SubscriptionPaymentAttempt.subscription_id == sub.id,
        )
    )
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment attempt not found")
    payment_reference = (attempt.provider_payment_id or "").strip()
    if not payment_reference.startswith("pay_"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No refundable Payplug payment found")
    if attempt.status.strip().lower() not in {"success", "refunded"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a successful payment can be refunded")
    _refund_payplug_payment(db, payment_reference=payment_reference)

    now = _utcnow()
    attempt.status = "refunded"
    attempt.provider_status = "REFUNDED"
    db.add(attempt)
    cycle = db.get(SubscriptionBillingCycle, attempt.billing_cycle_id)
    if cycle is not None:
        cycle.status = "refunded"
        db.add(cycle)
    refund = db.scalar(
        select(ClientPaymentRefund).where(
            ClientPaymentRefund.user_id == owner.id,
            ClientPaymentRefund.source == "SUBSCRIPTION_RENEWAL",
            ClientPaymentRefund.source_payment_id == attempt.id,
        )
    )
    if refund is None:
        refund = ClientPaymentRefund(
            user_id=owner.id,
            source="SUBSCRIPTION_RENEWAL",
            source_payment_id=attempt.id,
            actor_user_id=actor.id,
            refunded_at=now,
            updated_at=now,
            reason="Remboursement Payplug administrateur",
        )
    else:
        refund.actor_user_id = actor.id
        refund.refunded_at = now
        refund.updated_at = now
    db.add(refund)
    db.commit()
    return _detail_out(db, sub=sub, plan=plan, owner=owner)
