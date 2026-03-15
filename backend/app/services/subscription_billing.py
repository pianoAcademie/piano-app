from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ops import AppSetting
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, PlanPriceTaxMode, SubscriptionStatus
from app.models.subscription_engine import (
    SubscriptionBillingCycle,
    SubscriptionNotificationPolicy,
    SubscriptionPaymentAttempt,
    SubscriptionRetryPolicy,
)
from app.models.user import User
from app.services.family_billing import resolve_billing_profile
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    DISPATCH_MODE_IMMEDIATE,
    EVENT_SUBSCRIPTION_BILLING_CYCLE_CREATED,
    EVENT_SUBSCRIPTION_PAYMENT_FAILED_FINAL,
    EVENT_SUBSCRIPTION_PAYMENT_FAILED_FIRST,
    EVENT_SUBSCRIPTION_PAYMENT_RECOVERED,
    EVENT_SUBSCRIPTION_PAYMENT_SUCCESS,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_ADMIN,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_CUSTOMER,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_ADMIN,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_CUSTOMER,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_RECOVERED_ADMIN,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_RECOVERED_CUSTOMER,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_ADMIN,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_CUSTOMER,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    SOURCE_SCHEDULER,
)
from app.services.notifications.infrastructure.repository import (
    append_job_run_log,
    create_domain_event,
    create_notification_if_new,
    finish_job_run,
    list_admin_recipients_for_type,
    start_job_run,
)
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, lookup_payment
from app.services.payment_provider import PaymentProvider, detect_provider_from_reference, resolve_mode, resolve_provider
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate
from app.services.psp_gateway import MollieGateway, PayplugGateway, RecurringChargeRequest
from app.services.shared.locks.redis_lock import redis_lock
from app.services.shared.queue.redis_queue import queue_push
from app.services.subscriptions import add_months_utc

logger = logging.getLogger(__name__)

JOB_SUBSCRIPTION_CYCLE_GENERATION = "subscription_cycle_generation_job"
JOB_SUBSCRIPTION_BILLING = "subscription_billing_job"
JOB_SUBSCRIPTION_RETRY = "subscription_retry_job"
JOB_SUBSCRIPTION_RECOVERY_RECON = "subscription_recovery_reconciliation_job"

CYCLE_STATUS_PENDING = "pending"
CYCLE_STATUS_PROCESSING = "processing"
CYCLE_STATUS_PAID = "paid"
CYCLE_STATUS_FAILED_FIRST = "failed_first_attempt"
CYCLE_STATUS_FAILED_FINAL = "failed_final"
CYCLE_STATUS_CANCELLED = "cancelled"

ATTEMPT_STATUS_PENDING = "pending"
ATTEMPT_STATUS_SUCCESS = "success"
ATTEMPT_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class SubscriptionCycleGenerationJobResult:
    checked: int
    created: int
    skipped: int
    failed: int
    job_run_id: UUID


@dataclass(frozen=True)
class SubscriptionBillingJobResult:
    checked: int
    charged: int
    skipped: int
    failed: int
    processed: int
    first_failures: int
    final_failures: int
    job_run_id: UUID


@dataclass(frozen=True)
class SubscriptionRetryJobResult:
    checked: int
    recovered: int
    skipped: int
    failed: int
    final_failures: int
    processed: int
    job_run_id: UUID


@dataclass(frozen=True)
class SubscriptionRecoveryReconciliationJobResult:
    checked: int
    reconciled: int
    skipped: int
    failed: int
    job_run_id: UUID


@dataclass(frozen=True)
class _RetryPolicyConfig:
    first_retry_delay_days: int
    max_auto_attempts: int
    move_to_pre_termination_after_failed_attempts: int


@dataclass(frozen=True)
class _NotificationPolicyConfig:
    on_success_customer_enabled: bool
    on_success_admin_enabled: bool
    on_first_failure_customer_enabled: bool
    on_first_failure_admin_enabled: bool
    on_final_failure_customer_enabled: bool
    on_final_failure_admin_enabled: bool


@dataclass(frozen=True)
class _AmountResolution:
    total_incl_vat: Decimal
    currency: str


def _get_setting_text(db: Session, key: str, default: str = "") -> str:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == key))
    if value is None:
        return default
    return str(value).strip() or default


def _get_setting_bool(db: Session, key: str, default: bool) -> bool:
    raw = _get_setting_text(db, key, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _format_money(amount: Decimal, currency: str) -> str:
    return f"{amount.quantize(Decimal('0.01')):.2f} {currency.upper()}"


def _format_dt(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M")


def _format_period(start: datetime, end: datetime) -> str:
    return f"du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"


def _resolve_retry_policy(db: Session, *, plan: Plan) -> _RetryPolicyConfig:
    policy: SubscriptionRetryPolicy | None = None
    if plan.retry_policy_id is not None:
        policy = db.scalar(
            select(SubscriptionRetryPolicy).where(
                SubscriptionRetryPolicy.id == plan.retry_policy_id,
                SubscriptionRetryPolicy.active.is_(True),
            )
        )
    if policy is None:
        policy = db.scalar(
            select(SubscriptionRetryPolicy).where(
                SubscriptionRetryPolicy.code == "DEFAULT_MONTHLY"
            )
        )
    if policy is None:
        policy = db.scalar(
            select(SubscriptionRetryPolicy)
            .where(SubscriptionRetryPolicy.active.is_(True))
            .order_by(SubscriptionRetryPolicy.created_at.asc())
        )
    if policy is None:
        return _RetryPolicyConfig(
            first_retry_delay_days=1,
            max_auto_attempts=2,
            move_to_pre_termination_after_failed_attempts=2,
        )
    return _RetryPolicyConfig(
        first_retry_delay_days=max(1, int(policy.first_retry_delay_days or 1)),
        max_auto_attempts=max(1, int(policy.max_auto_attempts or 2)),
        move_to_pre_termination_after_failed_attempts=max(
            1,
            int(policy.move_to_pre_termination_after_failed_attempts or policy.max_auto_attempts or 2),
        ),
    )


def _resolve_notification_policy(db: Session, *, plan: Plan) -> _NotificationPolicyConfig:
    policy: SubscriptionNotificationPolicy | None = None
    if plan.notification_policy_id is not None:
        policy = db.scalar(
            select(SubscriptionNotificationPolicy).where(
                SubscriptionNotificationPolicy.id == plan.notification_policy_id,
                SubscriptionNotificationPolicy.active.is_(True),
            )
        )
    if policy is None:
        policy = db.scalar(
            select(SubscriptionNotificationPolicy).where(
                SubscriptionNotificationPolicy.code == "DEFAULT_SUBSCRIPTION_NOTIFICATIONS"
            )
        )
    if policy is None:
        policy = db.scalar(
            select(SubscriptionNotificationPolicy)
            .where(SubscriptionNotificationPolicy.active.is_(True))
            .order_by(SubscriptionNotificationPolicy.created_at.asc())
        )
    if policy is None:
        return _NotificationPolicyConfig(
            on_success_customer_enabled=True,
            on_success_admin_enabled=True,
            on_first_failure_customer_enabled=True,
            on_first_failure_admin_enabled=True,
            on_final_failure_customer_enabled=True,
            on_final_failure_admin_enabled=True,
        )
    return _NotificationPolicyConfig(
        on_success_customer_enabled=bool(policy.on_success_customer_enabled),
        on_success_admin_enabled=bool(policy.on_success_admin_enabled),
        on_first_failure_customer_enabled=bool(policy.on_first_failure_customer_enabled),
        on_first_failure_admin_enabled=bool(policy.on_first_failure_admin_enabled),
        on_final_failure_customer_enabled=bool(policy.on_final_failure_customer_enabled),
        on_final_failure_admin_enabled=bool(policy.on_final_failure_admin_enabled),
    )


def _subscription_amount(db: Session, *, subscription: ClientPlanSubscription, plan: Plan, owner: User, now: datetime) -> _AmountResolution:
    billing_profile = resolve_billing_profile(db, owner)
    country_code = (billing_profile.residence_country or "FR").upper()
    preferred_currency = (billing_profile.preferred_currency or plan.currency_code or "EUR").upper()
    vat_rate = resolve_vat_rate(
        db,
        country=country_code,
        service_code=plan_service_code(plan.kind.value),
        on_date=now.date(),
    )

    price_excl_vat: Decimal | None = None
    currency_code = (plan.currency_code or preferred_currency).upper()
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
            country=country_code,
            currency=preferred_currency,
            on_date=now.date(),
        )
        if resolved_price is not None:
            price_excl_vat = Decimal(resolved_price.price_excl_vat)
            currency_code = resolved_price.currency_code

    if price_excl_vat is None:
        raise ValueError("subscription monthly price is missing")

    _, _, total_incl_vat = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)
    return _AmountResolution(total_incl_vat=total_incl_vat, currency=currency_code)


def _admin_recipients_for_notification(db: Session, *, notification_type: str) -> list[str]:
    recipients = list_admin_recipients_for_type(db, notification_type=notification_type)
    fallback = _get_setting_text(db, "config_account_contact_email", "")
    if fallback:
        recipients.append(fallback.strip().lower())

    uniq: list[str] = []
    seen: set[str] = set()
    for raw in recipients:
        value = (raw or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        uniq.append(value)
    return uniq


def _notification_subject_and_body(
    *,
    notification_type: str,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
    failure_reason: str | None = None,
) -> tuple[str, str]:
    owner_name = ((owner.first_name or "").strip() + " " + (owner.last_name or "").strip()).strip() or owner.email
    amount_label = _format_money(amount, currency)
    period_label = _format_period(cycle.period_start, cycle.period_end)

    if notification_type in {
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_CUSTOMER,
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_ADMIN,
    }:
        subject = "Confirmation de paiement de votre abonnement"
        body = (
            f"Abonnement: {plan.name}\n"
            f"Client: {owner_name}\n"
            f"Montant: {amount_label}\n"
            f"Date de paiement: {_format_dt(now)}\n"
            f"Periode couverte: {period_label}\n"
            f"Prochaine echeance: {_format_dt(cycle.period_end)}\n"
        )
        return subject, body

    if notification_type in {
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_CUSTOMER,
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_ADMIN,
    }:
        subject = "Echec du renouvellement de votre abonnement"
        body = (
            f"Abonnement: {plan.name}\n"
            f"Client: {owner_name}\n"
            f"Montant non preleve: {amount_label}\n"
            f"Date echec: {_format_dt(now)}\n"
            f"Periode: {period_label}\n"
            f"Nouvelle tentative automatique prevue: {(_format_dt(cycle.next_retry_at) if cycle.next_retry_at else '-')}\n"
            f"Lien de regularisation: {cycle.payment_recovery_url or '-'}\n"
            f"Raison: {failure_reason or 'Refus de paiement'}\n"
        )
        return subject, body

    if notification_type in {
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_CUSTOMER,
        NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_ADMIN,
    }:
        subject = "Votre abonnement necessite une regularisation urgente"
        body = (
            f"Abonnement: {plan.name}\n"
            f"Client: {owner_name}\n"
            f"Montant impaye: {amount_label}\n"
            f"Date echec final: {_format_dt(now)}\n"
            f"Periode: {period_label}\n"
            f"Statut abonnement: PRE_TERMINATION\n"
            f"Reservations bloquees: OUI\n"
            f"Lien de regularisation: {cycle.payment_recovery_url or '-'}\n"
            f"Raison: {failure_reason or 'Refus persistant'}\n"
        )
        return subject, body

    subject = "Votre abonnement a bien ete regularise"
    body = (
        f"Abonnement: {plan.name}\n"
        f"Client: {owner_name}\n"
        f"Montant regle: {amount_label}\n"
        f"Date regularisation: {_format_dt(now)}\n"
        f"Periode: {period_label}\n"
    )
    return subject, body


def _create_immediate_email_notification(
    db: Session,
    *,
    event_id: UUID,
    notification_type: str,
    related_entity_type: str,
    related_entity_id: UUID,
    recipient_type: str,
    recipient_contact_id: UUID | None,
    recipient_email: str,
    subject: str,
    body: str,
    payload_snapshot: dict[str, object],
    scheduled_for: datetime,
) -> None:
    created = create_notification_if_new(
        db,
        notification_type=notification_type,
        channel=CHANNEL_EMAIL,
        dispatch_mode=DISPATCH_MODE_IMMEDIATE,
        source_event_id=event_id,
        source=SOURCE_SCHEDULER,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        booking_id=None,
        slot_id=None,
        recipient_type=recipient_type,
        recipient_contact_id=recipient_contact_id,
        recipient_email=recipient_email,
        recipient_phone=None,
        subject=subject,
        body_snapshot=body,
        payload_snapshot=payload_snapshot,
        idempotency_key=f"{notification_type}:{related_entity_id}:{recipient_email}:{event_id}",
        scheduled_for=scheduled_for,
        status=NOTIFICATION_STATUS_PENDING,
    )
    if created is not None:
        queue_push(QUEUE_NOTIFICATIONS_IMMEDIATE, {"notification_id": str(created.id)})


def _emit_billing_notifications(
    db: Session,
    *,
    event_type: str,
    customer_notification_type: str,
    admin_notification_type: str,
    policy_customer_enabled: bool,
    policy_admin_enabled: bool,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
    failure_reason: str | None = None,
) -> None:
    event = create_domain_event(
        db,
        event_type=event_type,
        source=SOURCE_SCHEDULER,
        actor_type="system",
        actor_id=None,
        related_entity_type="subscription_billing_cycle",
        related_entity_id=cycle.id,
        occurred_at=now,
        payload_json={
            "subscription_id": str(subscription.id),
            "cycle_id": str(cycle.id),
            "status": cycle.status,
            "amount": f"{amount.quantize(Decimal('0.01')):.2f}",
            "currency": currency,
        },
    )

    subject_customer, body_customer = _notification_subject_and_body(
        notification_type=customer_notification_type,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
        failure_reason=failure_reason,
    )
    subject_admin, body_admin = _notification_subject_and_body(
        notification_type=admin_notification_type,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
        failure_reason=failure_reason,
    )

    if policy_customer_enabled and owner.email:
        _create_immediate_email_notification(
            db,
            event_id=event.id,
            notification_type=customer_notification_type,
            related_entity_type="subscription_billing_cycle",
            related_entity_id=cycle.id,
            recipient_type="USER",
            recipient_contact_id=owner.id,
            recipient_email=owner.email.strip().lower(),
            subject=subject_customer,
            body=body_customer,
            payload_snapshot={
                "subscription_id": str(subscription.id),
                "cycle_id": str(cycle.id),
                "recipient_scope": "customer",
            },
            scheduled_for=now,
        )

    if policy_admin_enabled:
        for admin_email in _admin_recipients_for_notification(db, notification_type=admin_notification_type):
            _create_immediate_email_notification(
                db,
                event_id=event.id,
                notification_type=admin_notification_type,
                related_entity_type="subscription_billing_cycle",
                related_entity_id=cycle.id,
                recipient_type="ADMIN",
                recipient_contact_id=None,
                recipient_email=admin_email,
                subject=subject_admin,
                body=body_admin,
                payload_snapshot={
                    "subscription_id": str(subscription.id),
                    "cycle_id": str(cycle.id),
                    "recipient_scope": "admin",
                },
                scheduled_for=now,
            )


def _resolve_recovery_urls(subscription_id: UUID, cycle_id: UUID) -> tuple[str, str, str]:
    base = resolve_frontend_base_url().rstrip("/")
    success_url = f"{base}/dashboard?tab=finance&subscription_recovery=success&subscription_id={subscription_id}"
    cancel_url = f"{base}/dashboard?tab=finance&subscription_recovery=cancelled&subscription_id={subscription_id}"
    webhook_url = f"{base}/api/v1/public/payments/webhook?subscription_id={subscription_id}&cycle_id={cycle_id}"
    return success_url, cancel_url, webhook_url


def _ensure_recovery_checkout(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
) -> None:
    if cycle.payment_recovery_url:
        subscription.direct_payment_recovery_url = cycle.payment_recovery_url
        return

    success_url, cancel_url, webhook_url = _resolve_recovery_urls(subscription.id, cycle.id)
    checkout = create_checkout_session(
        db,
        CheckoutCreateRequest(
            amount=Decimal(cycle.amount),
            currency=(cycle.currency or "EUR").upper(),
            description=f"Regularisation abonnement {plan.name}",
            customer_email=owner.email,
            success_return_url=success_url,
            cancel_return_url=cancel_url,
            webhook_url=webhook_url,
            metadata={
                "source": "SUBSCRIPTION_RECOVERY",
                "subscription_id": str(subscription.id),
                "billing_cycle_id": str(cycle.id),
            },
        ),
    )
    if checkout.success and checkout.checkout_url:
        cycle.payment_recovery_url = checkout.checkout_url
        cycle.payment_recovery_provider_ref = checkout.provider_reference
        subscription.direct_payment_recovery_url = checkout.checkout_url


def _mark_subscription_paid(subscription: ClientPlanSubscription, cycle: SubscriptionBillingCycle, *, now: datetime, provider_status: str) -> None:
    next_period_start = cycle.period_end
    next_period_end = add_months_utc(cycle.period_end, 1)

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.bookings_blocked = False
    subscription.payment_alert_started_at = None
    subscription.pre_termination_at = None
    subscription.direct_payment_recovery_url = None
    subscription.last_payment_at = now
    subscription.last_successful_charge_at = now
    subscription.last_payment_status = provider_status
    subscription.current_period_start = next_period_start
    subscription.current_period_end = next_period_end
    subscription.next_payment_at = next_period_end
    subscription.ends_at = next_period_end
    subscription.auto_renew = True


def _mark_subscription_first_failure(
    subscription: ClientPlanSubscription,
    cycle: SubscriptionBillingCycle,
    *,
    now: datetime,
    provider_status: str,
    allow_booking_during_payment_alert: bool,
) -> None:
    subscription.status = SubscriptionStatus.PAYMENT_ALERT
    subscription.last_payment_at = now
    subscription.last_payment_status = provider_status
    if subscription.payment_alert_started_at is None:
        subscription.payment_alert_started_at = now
    subscription.bookings_blocked = not allow_booking_during_payment_alert
    subscription.direct_payment_recovery_url = cycle.payment_recovery_url


def _mark_subscription_final_failure(subscription: ClientPlanSubscription, cycle: SubscriptionBillingCycle, *, now: datetime, provider_status: str) -> None:
    subscription.status = SubscriptionStatus.PRE_TERMINATION
    subscription.pre_termination_at = now
    subscription.bookings_blocked = True
    subscription.last_payment_at = now
    subscription.last_payment_status = provider_status
    subscription.direct_payment_recovery_url = cycle.payment_recovery_url


def _gateway_for_provider(db: Session) -> tuple[PaymentProvider, object]:
    provider = resolve_provider(db)
    if provider == PaymentProvider.MOLLIE:
        return provider, MollieGateway(api_key=resolve_provider_secret(db, provider=provider), mode=resolve_mode(db))
    return provider, PayplugGateway()


def resolve_provider_secret(db: Session, *, provider: PaymentProvider) -> str:
    from app.services.payment_provider import resolve_active_secret

    return resolve_active_secret(db, provider=provider)


def _create_cycle_if_missing(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    plan: Plan,
    owner: User,
    due_at: datetime,
    now: datetime,
) -> bool:
    period_end = due_at
    period_start = subscription.current_period_start
    if period_start is None:
        period_start = add_months_utc(period_end, -1)

    existing = db.scalar(
        select(SubscriptionBillingCycle).where(
            SubscriptionBillingCycle.subscription_id == subscription.id,
            SubscriptionBillingCycle.period_start == period_start,
            SubscriptionBillingCycle.period_end == period_end,
        )
    )
    if existing is not None:
        return False

    amount = _subscription_amount(db, subscription=subscription, plan=plan, owner=owner, now=now)
    cycle = SubscriptionBillingCycle(
        subscription_id=subscription.id,
        period_start=period_start,
        period_end=period_end,
        billing_date=due_at,
        status=CYCLE_STATUS_PENDING,
        attempt_count=0,
        amount=amount.total_incl_vat,
        currency=amount.currency,
    )
    with db.begin_nested():
        db.add(cycle)
        try:
            db.flush()
        except IntegrityError:
            return False

    create_domain_event(
        db,
        event_type=EVENT_SUBSCRIPTION_BILLING_CYCLE_CREATED,
        source=SOURCE_SCHEDULER,
        actor_type="system",
        actor_id=None,
        related_entity_type="subscription_billing_cycle",
        related_entity_id=cycle.id,
        occurred_at=now,
        payload_json={
            "subscription_id": str(subscription.id),
            "cycle_id": str(cycle.id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "billing_date": due_at.isoformat(),
        },
    )
    return True


def run_subscription_cycle_generation_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> SubscriptionCycleGenerationJobResult:
    with redis_lock("lock:job:subscription_cycle_generation", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("subscription_cycle_generation_job lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_SUBSCRIPTION_CYCLE_GENERATION,
            job_key=JOB_SUBSCRIPTION_CYCLE_GENERATION,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )
        checked = 0
        created = 0
        skipped = 0
        failed = 0

        try:
            rows = db.execute(
                select(ClientPlanSubscription, Plan, User)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .join(User, User.id == ClientPlanSubscription.user_id)
                .where(
                    Plan.kind == PlanKind.SUBSCRIPTION,
                    ClientPlanSubscription.auto_renew.is_(True),
                    ClientPlanSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT]),
                )
                .order_by(ClientPlanSubscription.next_payment_at.asc().nullsfirst(), ClientPlanSubscription.created_at.asc())
                .limit(limit)
            ).all()

            checked = len(rows)
            for subscription, plan, owner in rows:
                due_at = subscription.next_payment_at or subscription.current_period_end or add_months_utc(subscription.started_at, 1)
                if due_at > now:
                    skipped += 1
                    continue
                try:
                    if _create_cycle_if_missing(
                        db,
                        subscription=subscription,
                        plan=plan,
                        owner=owner,
                        due_at=due_at,
                        now=now,
                    ):
                        created += 1
                        append_job_run_log(
                            db,
                            job_run_id=job_run.id,
                            level="INFO",
                            message=f"Subscription {subscription.id} cycle created",
                            context_json={
                                "subscription_id": str(subscription.id),
                                "due_at": due_at.isoformat(),
                            },
                        )
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="ERROR",
                        message=f"Cycle generation failed for subscription {subscription.id}",
                        context_json={"error": str(exc)},
                    )

            finish_job_run(
                db,
                job_run=job_run,
                status="warning" if failed > 0 else "success",
                finished_at=now,
                items_scanned=checked,
                items_processed=created + skipped + failed,
                items_sent=created,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{created} cycles created",
            )
            return SubscriptionCycleGenerationJobResult(
                checked=checked,
                created=created,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=created + skipped,
                items_sent=created,
                items_skipped=skipped,
                items_failed=failed + 1,
                error_text=str(exc),
            )
            raise


def _record_attempt(
    db: Session,
    *,
    cycle: SubscriptionBillingCycle,
    attempt_number: int,
    attempted_at: datetime,
    idempotency_key: str,
) -> SubscriptionPaymentAttempt | None:
    existing = db.scalar(
        select(SubscriptionPaymentAttempt).where(SubscriptionPaymentAttempt.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return None

    attempt = SubscriptionPaymentAttempt(
        billing_cycle_id=cycle.id,
        subscription_id=cycle.subscription_id,
        attempt_number=attempt_number,
        attempted_at=attempted_at,
        amount=Decimal(cycle.amount),
        currency=(cycle.currency or "EUR").upper(),
        status=ATTEMPT_STATUS_PENDING,
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    db.flush()
    return attempt


def _send_success_notifications(
    db: Session,
    *,
    policy: _NotificationPolicyConfig,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
) -> None:
    _emit_billing_notifications(
        db,
        event_type=EVENT_SUBSCRIPTION_PAYMENT_SUCCESS,
        customer_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_CUSTOMER,
        admin_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_SUCCESS_ADMIN,
        policy_customer_enabled=policy.on_success_customer_enabled,
        policy_admin_enabled=policy.on_success_admin_enabled,
        subscription=subscription,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
    )


def _send_first_failure_notifications(
    db: Session,
    *,
    policy: _NotificationPolicyConfig,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
    failure_reason: str,
) -> None:
    _emit_billing_notifications(
        db,
        event_type=EVENT_SUBSCRIPTION_PAYMENT_FAILED_FIRST,
        customer_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_CUSTOMER,
        admin_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FIRST_ADMIN,
        policy_customer_enabled=policy.on_first_failure_customer_enabled,
        policy_admin_enabled=policy.on_first_failure_admin_enabled,
        subscription=subscription,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
        failure_reason=failure_reason,
    )


def _send_final_failure_notifications(
    db: Session,
    *,
    policy: _NotificationPolicyConfig,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
    failure_reason: str,
) -> None:
    _emit_billing_notifications(
        db,
        event_type=EVENT_SUBSCRIPTION_PAYMENT_FAILED_FINAL,
        customer_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_CUSTOMER,
        admin_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_FAILED_FINAL_ADMIN,
        policy_customer_enabled=policy.on_final_failure_customer_enabled,
        policy_admin_enabled=policy.on_final_failure_admin_enabled,
        subscription=subscription,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
        failure_reason=failure_reason,
    )


def _send_recovered_notifications(
    db: Session,
    *,
    policy: _NotificationPolicyConfig,
    subscription: ClientPlanSubscription,
    owner: User,
    plan: Plan,
    cycle: SubscriptionBillingCycle,
    amount: Decimal,
    currency: str,
    now: datetime,
) -> None:
    _emit_billing_notifications(
        db,
        event_type=EVENT_SUBSCRIPTION_PAYMENT_RECOVERED,
        customer_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_RECOVERED_CUSTOMER,
        admin_notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_RECOVERED_ADMIN,
        policy_customer_enabled=policy.on_success_customer_enabled,
        policy_admin_enabled=policy.on_success_admin_enabled,
        subscription=subscription,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
    )


def _charge_cycle(
    db: Session,
    *,
    cycle: SubscriptionBillingCycle,
    subscription: ClientPlanSubscription,
    plan: Plan,
    owner: User,
    now: datetime,
    retry_policy: _RetryPolicyConfig,
    notification_policy: _NotificationPolicyConfig,
    provider: PaymentProvider,
    gateway: object,
    is_retry: bool,
) -> tuple[str, str]:
    if subscription.status in {SubscriptionStatus.CANCELLED, SubscriptionStatus.TERMINATED, SubscriptionStatus.EXPIRED}:
        cycle.status = CYCLE_STATUS_CANCELLED
        return "skipped", "subscription_not_active"

    attempt_number = int(cycle.attempt_count or 0) + 1
    idempotency_key = f"subscription_charge:{cycle.id}:{attempt_number}"
    attempt = _record_attempt(
        db,
        cycle=cycle,
        attempt_number=attempt_number,
        attempted_at=now,
        idempotency_key=idempotency_key,
    )
    if attempt is None:
        return "skipped", "duplicate_attempt"

    cycle.status = CYCLE_STATUS_PROCESSING
    cycle.last_attempt_at = now
    if cycle.first_attempt_at is None:
        cycle.first_attempt_at = now

    failure_reason = ""
    provider_status = "FAILED_UNKNOWN"

    if subscription.billing_method_code != "CARD_ONLINE":
        failure_reason = "Moyen de paiement non compatible avec le renouvellement automatique"
        provider_status = "FAILED_INVALID_BILLING_METHOD"
        result_success = False
        provider_reference = None
    elif provider != PaymentProvider.MOLLIE:
        failure_reason = "Le PSP actif ne supporte pas le prelevement recurrent automatique"
        provider_status = "FAILED_PROVIDER_NOT_SUPPORTED"
        result_success = False
        provider_reference = None
    else:
        result = gateway.create_recurring_charge(
            RecurringChargeRequest(
                amount=Decimal(cycle.amount),
                currency=(cycle.currency or "EUR").upper(),
                description=f"{plan.name} - renouvellement mensuel",
                customer_reference=subscription.payment_provider_customer_ref,
                mandate_reference=subscription.payment_provider_mandate_ref,
                idempotency_key=idempotency_key,
            )
        )
        provider_status = result.status
        failure_reason = result.message or "Echec du prelevement"
        result_success = bool(result.success)
        provider_reference = result.provider_reference

    amount = Decimal(cycle.amount)
    currency = (cycle.currency or "EUR").upper()

    attempt.provider_name = provider.value
    attempt.provider_payment_id = provider_reference
    attempt.provider_status = provider_status

    if result_success:
        attempt.status = ATTEMPT_STATUS_SUCCESS
        cycle.attempt_count = attempt_number
        cycle.status = CYCLE_STATUS_PAID
        cycle.paid_at = now
        cycle.next_retry_at = None
        cycle.payment_recovery_url = None
        cycle.payment_recovery_provider_ref = None
        _mark_subscription_paid(subscription, cycle, now=now, provider_status=provider_status)
        _send_success_notifications(
            db,
            policy=notification_policy,
            subscription=subscription,
            owner=owner,
            plan=plan,
            cycle=cycle,
            amount=amount,
            currency=currency,
            now=now,
        )
        return "charged", provider_status

    attempt.status = ATTEMPT_STATUS_FAILED
    attempt.failure_code = provider_status
    attempt.failure_reason = failure_reason
    cycle.attempt_count = attempt_number

    allow_booking_during_alert = _get_setting_bool(db, "config_subscription_allow_booking_during_payment_alert", True)
    _ensure_recovery_checkout(db, subscription=subscription, owner=owner, plan=plan, cycle=cycle)

    failure_threshold = max(
        retry_policy.max_auto_attempts,
        retry_policy.move_to_pre_termination_after_failed_attempts,
    )

    if attempt_number >= failure_threshold:
        cycle.status = CYCLE_STATUS_FAILED_FINAL
        cycle.next_retry_at = None
        _mark_subscription_final_failure(subscription, cycle, now=now, provider_status=provider_status)
        _send_final_failure_notifications(
            db,
            policy=notification_policy,
            subscription=subscription,
            owner=owner,
            plan=plan,
            cycle=cycle,
            amount=amount,
            currency=currency,
            now=now,
            failure_reason=failure_reason,
        )
        return "final_failure", provider_status

    cycle.status = CYCLE_STATUS_FAILED_FIRST
    cycle.next_retry_at = now + timedelta(days=retry_policy.first_retry_delay_days)
    _mark_subscription_first_failure(
        subscription,
        cycle,
        now=now,
        provider_status=provider_status,
        allow_booking_during_payment_alert=allow_booking_during_alert,
    )
    _send_first_failure_notifications(
        db,
        policy=notification_policy,
        subscription=subscription,
        owner=owner,
        plan=plan,
        cycle=cycle,
        amount=amount,
        currency=currency,
        now=now,
        failure_reason=failure_reason,
    )
    return "first_failure", provider_status


def run_subscription_billing_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> SubscriptionBillingJobResult:
    with redis_lock("lock:job:subscription_billing", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("subscription_billing_job lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_SUBSCRIPTION_BILLING,
            job_key=JOB_SUBSCRIPTION_BILLING,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )

        checked = 0
        processed = 0
        charged = 0
        skipped = 0
        failed = 0
        first_failures = 0
        final_failures = 0

        try:
            # Generate due cycles first, then process pending ones.
            try:
                run_subscription_cycle_generation_job(db, now=now, limit=limit)
            except RuntimeError:
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO",
                    message="Cycle generation lock already held, continuing with existing pending cycles",
                    context_json={},
                )

            provider, gateway = _gateway_for_provider(db)

            rows = db.execute(
                select(SubscriptionBillingCycle, ClientPlanSubscription, Plan, User)
                .join(ClientPlanSubscription, ClientPlanSubscription.id == SubscriptionBillingCycle.subscription_id)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .join(User, User.id == ClientPlanSubscription.user_id)
                .where(
                    SubscriptionBillingCycle.status == CYCLE_STATUS_PENDING,
                    SubscriptionBillingCycle.billing_date <= now,
                    Plan.kind == PlanKind.SUBSCRIPTION,
                )
                .order_by(SubscriptionBillingCycle.billing_date.asc(), SubscriptionBillingCycle.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()

            checked = len(rows)
            for cycle, subscription, plan, owner in rows:
                processed += 1
                retry_policy = _resolve_retry_policy(db, plan=plan)
                notification_policy = _resolve_notification_policy(db, plan=plan)

                outcome, provider_status = _charge_cycle(
                    db,
                    cycle=cycle,
                    subscription=subscription,
                    plan=plan,
                    owner=owner,
                    now=now,
                    retry_policy=retry_policy,
                    notification_policy=notification_policy,
                    provider=provider,
                    gateway=gateway,
                    is_retry=False,
                )
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO" if outcome in {"charged", "skipped"} else "WARNING",
                    message=f"Billing cycle {cycle.id} outcome={outcome}",
                    context_json={
                        "cycle_id": str(cycle.id),
                        "subscription_id": str(subscription.id),
                        "provider_status": provider_status,
                    },
                )

                if outcome == "charged":
                    charged += 1
                elif outcome == "first_failure":
                    first_failures += 1
                    failed += 1
                elif outcome == "final_failure":
                    final_failures += 1
                    failed += 1
                else:
                    skipped += 1

            status = "success"
            if failed > 0:
                status = "warning" if charged > 0 or skipped > 0 else "failed"
            finish_job_run(
                db,
                job_run=job_run,
                status=status,
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=charged,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"charged={charged}, first_failed={first_failures}, final_failed={final_failures}",
            )
            return SubscriptionBillingJobResult(
                checked=checked,
                charged=charged,
                skipped=skipped,
                failed=failed,
                processed=processed,
                first_failures=first_failures,
                final_failures=final_failures,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=charged,
                items_skipped=skipped,
                items_failed=failed + 1,
                error_text=str(exc),
            )
            raise


def run_subscription_retry_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> SubscriptionRetryJobResult:
    with redis_lock("lock:job:subscription_retry", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("subscription_retry_job lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_SUBSCRIPTION_RETRY,
            job_key=JOB_SUBSCRIPTION_RETRY,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )

        checked = 0
        processed = 0
        recovered = 0
        skipped = 0
        failed = 0
        final_failures = 0

        try:
            provider, gateway = _gateway_for_provider(db)

            rows = db.execute(
                select(SubscriptionBillingCycle, ClientPlanSubscription, Plan, User)
                .join(ClientPlanSubscription, ClientPlanSubscription.id == SubscriptionBillingCycle.subscription_id)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .join(User, User.id == ClientPlanSubscription.user_id)
                .where(
                    SubscriptionBillingCycle.status == CYCLE_STATUS_FAILED_FIRST,
                    SubscriptionBillingCycle.next_retry_at.is_not(None),
                    SubscriptionBillingCycle.next_retry_at <= now,
                    Plan.kind == PlanKind.SUBSCRIPTION,
                )
                .order_by(SubscriptionBillingCycle.next_retry_at.asc(), SubscriptionBillingCycle.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()

            checked = len(rows)
            for cycle, subscription, plan, owner in rows:
                processed += 1
                retry_policy = _resolve_retry_policy(db, plan=plan)
                notification_policy = _resolve_notification_policy(db, plan=plan)
                outcome, provider_status = _charge_cycle(
                    db,
                    cycle=cycle,
                    subscription=subscription,
                    plan=plan,
                    owner=owner,
                    now=now,
                    retry_policy=retry_policy,
                    notification_policy=notification_policy,
                    provider=provider,
                    gateway=gateway,
                    is_retry=True,
                )
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO" if outcome in {"charged", "skipped"} else "WARNING",
                    message=f"Retry cycle {cycle.id} outcome={outcome}",
                    context_json={
                        "cycle_id": str(cycle.id),
                        "subscription_id": str(subscription.id),
                        "provider_status": provider_status,
                    },
                )

                if outcome == "charged":
                    recovered += 1
                elif outcome == "first_failure":
                    failed += 1
                elif outcome == "final_failure":
                    failed += 1
                    final_failures += 1
                else:
                    skipped += 1

            status = "success"
            if failed > 0:
                status = "warning" if recovered > 0 or skipped > 0 else "failed"
            finish_job_run(
                db,
                job_run=job_run,
                status=status,
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=recovered,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"recovered={recovered}, final_failed={final_failures}",
            )
            return SubscriptionRetryJobResult(
                checked=checked,
                recovered=recovered,
                skipped=skipped,
                failed=failed,
                final_failures=final_failures,
                processed=processed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=recovered,
                items_skipped=skipped,
                items_failed=failed + 1,
                error_text=str(exc),
            )
            raise


def run_subscription_recovery_reconciliation_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> SubscriptionRecoveryReconciliationJobResult:
    with redis_lock("lock:job:subscription_recovery_reconciliation", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("subscription_recovery_reconciliation_job lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_SUBSCRIPTION_RECOVERY_RECON,
            job_key=JOB_SUBSCRIPTION_RECOVERY_RECON,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )

        checked = 0
        reconciled = 0
        skipped = 0
        failed = 0

        try:
            rows = db.execute(
                select(SubscriptionBillingCycle, ClientPlanSubscription, Plan, User)
                .join(ClientPlanSubscription, ClientPlanSubscription.id == SubscriptionBillingCycle.subscription_id)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .join(User, User.id == ClientPlanSubscription.user_id)
                .where(
                    SubscriptionBillingCycle.status.in_([CYCLE_STATUS_FAILED_FIRST, CYCLE_STATUS_FAILED_FINAL]),
                    SubscriptionBillingCycle.payment_recovery_provider_ref.is_not(None),
                    Plan.kind == PlanKind.SUBSCRIPTION,
                )
                .order_by(SubscriptionBillingCycle.updated_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()

            checked = len(rows)
            for cycle, subscription, plan, owner in rows:
                provider_ref = (cycle.payment_recovery_provider_ref or "").strip()
                if not provider_ref:
                    skipped += 1
                    continue

                provider = detect_provider_from_reference(provider_ref) or resolve_provider(db)
                lookup = lookup_payment(db, provider=provider, payment_reference=provider_ref)
                if not lookup.paid:
                    skipped += 1
                    continue

                amount = Decimal(cycle.amount)
                currency = (cycle.currency or "EUR").upper()
                cycle.status = CYCLE_STATUS_PAID
                cycle.paid_at = now
                cycle.next_retry_at = None
                cycle.attempt_count = int(cycle.attempt_count or 0) + 1
                cycle.payment_recovery_url = None
                cycle.payment_recovery_provider_ref = None

                _mark_subscription_paid(subscription, cycle, now=now, provider_status=(lookup.status or "PAID"))

                attempt_number = int(cycle.attempt_count or 1)
                attempt_key = f"subscription_recovery:{cycle.id}:{attempt_number}:{provider_ref}"
                attempt_existing = db.scalar(
                    select(SubscriptionPaymentAttempt).where(SubscriptionPaymentAttempt.idempotency_key == attempt_key)
                )
                if attempt_existing is None:
                    db.add(
                        SubscriptionPaymentAttempt(
                            billing_cycle_id=cycle.id,
                            subscription_id=subscription.id,
                            attempt_number=attempt_number,
                            attempted_at=now,
                            amount=amount,
                            currency=currency,
                            status=ATTEMPT_STATUS_SUCCESS,
                            provider_name=provider.value,
                            provider_payment_id=provider_ref,
                            provider_status=(lookup.status or "paid"),
                            idempotency_key=attempt_key,
                        )
                    )

                notification_policy = _resolve_notification_policy(db, plan=plan)
                _send_recovered_notifications(
                    db,
                    policy=notification_policy,
                    subscription=subscription,
                    owner=owner,
                    plan=plan,
                    cycle=cycle,
                    amount=amount,
                    currency=currency,
                    now=now,
                )

                reconciled += 1
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO",
                    message=f"Recovery payment detected for subscription {subscription.id}",
                    context_json={
                        "subscription_id": str(subscription.id),
                        "cycle_id": str(cycle.id),
                        "provider_reference": provider_ref,
                    },
                )

            status = "success"
            if failed > 0:
                status = "warning" if reconciled > 0 or skipped > 0 else "failed"
            finish_job_run(
                db,
                job_run=job_run,
                status=status,
                finished_at=now,
                items_scanned=checked,
                items_processed=reconciled + skipped,
                items_sent=reconciled,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"reconciled={reconciled}",
            )
            return SubscriptionRecoveryReconciliationJobResult(
                checked=checked,
                reconciled=reconciled,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=reconciled + skipped,
                items_sent=reconciled,
                items_skipped=skipped,
                items_failed=failed + 1,
                error_text=str(exc),
            )
            raise
