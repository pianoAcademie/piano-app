from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.notification_engine import Notification
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.user import User
from app.services.email_branding import render_branded_email
from app.services.family_billing import resolve_billing_profile
from app.services.i18n import normalize_language
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    DISPATCH_MODE_SCHEDULED,
    EVENT_SUBSCRIPTION_INITIAL_PAYMENT_REQUIRED,
    EVENT_SUBSCRIPTION_PAYMENT_METHOD_REQUIRED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_TYPE_SUBSCRIPTION_INITIAL_PAYMENT_REQUIRED_CUSTOMER,
    NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_METHOD_REQUIRED_CUSTOMER,
    SOURCE_SCHEDULER,
)
from app.services.notifications.infrastructure.repository import (
    append_job_run_log,
    create_domain_event,
    create_notification_if_new,
    finish_job_run,
    start_job_run,
)
from app.services.shared.locks.redis_lock import redis_lock

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")
JOB_SUBSCRIPTION_PAYMENT_ACTION_REMINDERS = "subscription_payment_action_reminders_job"
PAYMENT_ACTION_REMINDER_PHASE_BY_DAYS_UNTIL_DUE = {
    7: "before_due",
    0: "due_today",
    -2: "overdue",
}
SUCCESSFUL_INITIAL_PAYMENT_STATUSES = {
    "PAID",
    "SUCCESS",
    "SUCCEEDED",
    "COMPLETED",
    "AUTHORIZED",
    "CAPTURED",
}


@dataclass(frozen=True)
class SubscriptionPaymentReminderJobResult:
    checked: int
    created: int
    skipped: int
    failed: int
    job_run_id: UUID


@dataclass(frozen=True)
class SubscriptionPaymentReminderEmail:
    notification_type: str
    event_type: str
    subject: str
    body: str
    action_url: str
    issue: str


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _local_date(value: datetime) -> date:
    return _aware(value).astimezone(PARIS_TZ).date()


def _reminder_phase(*, due_at: datetime, now: datetime) -> str | None:
    days_until_due = (_local_date(due_at) - _local_date(now)).days
    return PAYMENT_ACTION_REMINDER_PHASE_BY_DAYS_UNTIL_DUE.get(days_until_due)


def _due_date_window_condition(column: object, *, now: datetime) -> object:
    local_today = _local_date(now)
    windows = []
    for days_until_due in PAYMENT_ACTION_REMINDER_PHASE_BY_DAYS_UNTIL_DUE:
        target_date = local_today + timedelta(days=days_until_due)
        local_start = datetime.combine(target_date, time.min, tzinfo=PARIS_TZ)
        utc_start = local_start.astimezone(timezone.utc)
        utc_end = (local_start + timedelta(days=1)).astimezone(timezone.utc)
        windows.append(and_(column >= utc_start, column < utc_end))
    return or_(*windows)


def _has_valid_stripe_card(subscription: ClientPlanSubscription) -> bool:
    provider = str(subscription.payment_provider_code or "").strip().upper()
    payment_method_ref = str(subscription.payment_provider_payment_method_ref or "").strip()
    payment_method_type = str(subscription.payment_method_type or "").strip().lower()
    return bool(
        provider == "STRIPE"
        and payment_method_ref.startswith("pm_")
        and payment_method_type == "card"
        and not subscription.payment_method_setup_required
    )


def _initial_payment_is_complete(subscription: ClientPlanSubscription) -> bool:
    status = str(subscription.last_payment_status or "").strip().upper()
    return bool(
        subscription.last_successful_charge_at is not None
        or subscription.last_payment_at is not None
        or status in SUCCESSFUL_INITIAL_PAYMENT_STATUSES
    )


def _payment_issue_and_due_at(
    subscription: ClientPlanSubscription,
) -> tuple[str, datetime] | None:
    status = subscription.status
    if status == SubscriptionStatus.PENDING:
        if _initial_payment_is_complete(subscription):
            return None
        return "initial_payment", subscription.started_at

    if status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT}:
        return None
    if _has_valid_stripe_card(subscription):
        return None
    due_at = subscription.next_payment_at or subscription.current_period_end
    if due_at is None:
        return None
    return "payment_method", due_at


def _client_url(*, path: str, query: dict[str, str]) -> str:
    base = resolve_frontend_base_url().strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return f"{base}{path}?{urlencode(query)}"


def _display_name(user: User) -> str:
    name = " ".join(
        part
        for part in ((user.first_name or "").strip(), (user.last_name or "").strip())
        if part
    )
    return name or (user.email or "").strip() or "Client"


def _format_amount(subscription: ClientPlanSubscription, plan: Plan, *, english: bool) -> str | None:
    raw_amount = (
        subscription.initial_total_incl_vat
        if subscription.status == SubscriptionStatus.PENDING
        else plan.monthly_price_value
    )
    if raw_amount is None:
        return None
    try:
        amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    currency = (subscription.initial_currency_code or plan.currency_code or "EUR").upper()
    if currency == "EUR":
        return f"€{amount:.2f}" if english else f"{amount:.2f} €".replace(".", ",")
    return f"{amount:.2f} {currency}"


def _phase_copy(phase: str, *, english: bool) -> tuple[str, str]:
    if english:
        return {
            "before_due": ("before the due date", "Upcoming due date"),
            "due_today": ("today", "Due today"),
            "overdue": ("as soon as possible", "Action still required"),
        }[phase]
    return {
        "before_due": ("avant l’échéance", "Échéance à venir"),
        "due_today": ("aujourd’hui", "Échéance aujourd’hui"),
        "overdue": ("dès que possible", "Action toujours requise"),
    }[phase]


def build_subscription_payment_reminder_email(
    *,
    subscription: ClientPlanSubscription,
    plan: Plan,
    recipient: User,
    issue: str,
    phase: str,
    due_at: datetime,
) -> SubscriptionPaymentReminderEmail:
    english = normalize_language(recipient.preferred_language) == "en"
    name = _display_name(recipient)
    due_date = _local_date(due_at)
    due_label = due_date.strftime("%B %-d, %Y") if english else due_date.strftime("%d/%m/%Y")
    action_timing, status_label = _phase_copy(phase, english=english)
    amount_label = _format_amount(subscription, plan, english=english)

    if issue == "initial_payment":
        action_url = _client_url(
            path="/client",
            query={
                "tab": "finance",
                "finance_view": "transactions",
                "source": "PLAN_PURCHASE",
                "payment_id": str(subscription.id),
            },
        )
        if english:
            subject = "Action required – complete your Piano Academie subscription payment"
            body = render_branded_email(
                preview="Your subscription is awaiting its initial payment.",
                eyebrow="SUBSCRIPTION",
                title="Complete your payment",
                greeting=f"Hello {name},",
                intro=f"Your “{plan.name}” subscription is still awaiting its initial payment. Please complete it {action_timing} to activate your subscription and access lesson bookings.",
                rows=[
                    ("Subscription", plan.name),
                    ("Due date", due_label),
                    ("Status", status_label),
                    *([("Amount", amount_label)] if amount_label else []),
                    ("Secure payment", "Stripe"),
                ],
                message="Click the button below, sign in to your client area, check your card details and confirm the payment. Your bank may request an additional security check.",
                button_url=action_url,
                button_label="COMPLETE MY PAYMENT",
                footer="This service email was sent automatically by Piano Academie. Never send your card details by email.",
            )
        else:
            subject = "Action requise – finalisez le paiement de votre abonnement Piano Académie"
            body = render_branded_email(
                preview="Votre abonnement attend toujours son premier règlement.",
                eyebrow="ABONNEMENT",
                title="Finalisez votre paiement",
                greeting=f"Bonjour {name},",
                intro=f"Votre abonnement « {plan.name} » attend toujours son premier règlement. Merci de le finaliser {action_timing} afin d’activer votre abonnement et d’accéder aux réservations de cours.",
                rows=[
                    ("Abonnement", plan.name),
                    ("Échéance", due_label),
                    ("Statut", status_label),
                    *([("Montant", amount_label)] if amount_label else []),
                    ("Paiement sécurisé", "Stripe"),
                ],
                message="Cliquez sur le bouton ci-dessous, connectez-vous à votre espace client, vérifiez les informations de votre carte puis confirmez le paiement. Votre banque pourra demander une validation supplémentaire.",
                button_url=action_url,
                button_label="FINALISER MON PAIEMENT",
                footer="Cet e-mail de service a été envoyé automatiquement par Piano Académie. Ne transmettez jamais vos coordonnées bancaires par e-mail.",
            )
        return SubscriptionPaymentReminderEmail(
            notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_INITIAL_PAYMENT_REQUIRED_CUSTOMER,
            event_type=EVENT_SUBSCRIPTION_INITIAL_PAYMENT_REQUIRED,
            subject=subject,
            body=body,
            action_url=action_url,
            issue=issue,
        )

    action_url = _client_url(
        path="/client",
        query={"tab": "offers", "offer_detail_id": str(subscription.id)},
    )
    if english:
        subject = "Action required – add a card for your Piano Academie subscription"
        body = render_branded_email(
            preview="A payment card is required for your next subscription renewal.",
            eyebrow="SUBSCRIPTION",
            title="Add your payment card",
            greeting=f"Hello {name},",
            intro=f"No valid Stripe payment card is currently linked to your “{plan.name}” subscription. Please add one {action_timing} to avoid interrupting your subscription and lesson bookings.",
            rows=[
                ("Subscription", plan.name),
                ("Next due date", due_label),
                ("Status", status_label),
                ("Secure card storage", "Stripe"),
            ],
            message="Click the button below, sign in, open the subscription and select Add or replace payment method. Enter your card details and wait for the confirmation message.",
            button_url=action_url,
            button_label="ADD MY CARD",
            footer="This service email was sent automatically by Piano Academie. Piano Academie never has access to your full card details.",
        )
    else:
        subject = "Action requise – enregistrez votre carte pour votre abonnement Piano Académie"
        body = render_branded_email(
            preview="Une carte bancaire est nécessaire pour votre prochaine échéance.",
            eyebrow="ABONNEMENT",
            title="Enregistrez votre carte bancaire",
            greeting=f"Bonjour {name},",
            intro=f"Aucune carte Stripe valide n’est actuellement associée à votre abonnement « {plan.name} ». Merci d’en enregistrer une {action_timing} afin d’éviter l’interruption de votre abonnement et de vos réservations.",
            rows=[
                ("Abonnement", plan.name),
                ("Prochaine échéance", due_label),
                ("Statut", status_label),
                ("Carte sécurisée par", "Stripe"),
            ],
            message="Cliquez sur le bouton ci-dessous, connectez-vous, ouvrez l’abonnement puis choisissez Enregistrer ou remplacer le moyen de paiement. Saisissez votre carte et attendez le message de confirmation.",
            button_url=action_url,
            button_label="ENREGISTRER MA CARTE",
            footer="Cet e-mail de service a été envoyé automatiquement par Piano Académie. Piano Académie n’a jamais accès aux données complètes de votre carte.",
        )
    return SubscriptionPaymentReminderEmail(
        notification_type=NOTIFICATION_TYPE_SUBSCRIPTION_PAYMENT_METHOD_REQUIRED_CUSTOMER,
        event_type=EVENT_SUBSCRIPTION_PAYMENT_METHOD_REQUIRED,
        subject=subject,
        body=body,
        action_url=action_url,
        issue=issue,
    )


def _notification_key(
    *,
    subscription_id: UUID,
    recipient_id: UUID,
    issue: str,
    phase: str,
    due_at: datetime,
) -> str:
    return (
        f"subscription-payment-action:{issue}:{phase}:"
        f"{subscription_id}:{recipient_id}:{_local_date(due_at).isoformat()}"
    )


def _recipient_for_subscription(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    owner: User,
) -> User:
    if subscription.payer_contact_id is not None and subscription.payer_contact_id != owner.id:
        payer = db.scalar(select(User).where(User.id == subscription.payer_contact_id))
        if payer is not None:
            return payer
    return resolve_billing_profile(db, owner)


def run_subscription_payment_action_reminder_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> SubscriptionPaymentReminderJobResult:
    with redis_lock("lock:job:subscription_payment_action_reminders", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("subscription_payment_action_reminders_job lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_SUBSCRIPTION_PAYMENT_ACTION_REMINDERS,
            job_key=JOB_SUBSCRIPTION_PAYMENT_ACTION_REMINDERS,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit, "local_date": _local_date(now).isoformat()},
        )
        checked = created = skipped = failed = 0
        try:
            rows = db.execute(
                # Restrict the scan to J-7, D-day and J+2 in Europe/Paris so
                # old pending records cannot crowd current reminders out of
                # the bounded batch.
                select(ClientPlanSubscription, Plan, User)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .join(User, User.id == ClientPlanSubscription.user_id)
                .where(
                    Plan.kind == PlanKind.SUBSCRIPTION,
                    ClientPlanSubscription.billing_method_code == "CARD_ONLINE",
                    ClientPlanSubscription.status.in_(
                        [SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT]
                    ),
                    or_(
                        and_(
                            ClientPlanSubscription.status == SubscriptionStatus.PENDING,
                            _due_date_window_condition(ClientPlanSubscription.started_at, now=now),
                        ),
                        and_(
                            ClientPlanSubscription.status.in_(
                                [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAYMENT_ALERT]
                            ),
                            or_(
                                ClientPlanSubscription.payment_method_setup_required.is_(True),
                                ClientPlanSubscription.payment_provider_code.is_(None),
                                ClientPlanSubscription.payment_provider_code != "STRIPE",
                                ClientPlanSubscription.payment_provider_payment_method_ref.is_(None),
                                ~ClientPlanSubscription.payment_provider_payment_method_ref.like("pm_%"),
                                ClientPlanSubscription.payment_method_type.is_(None),
                                ClientPlanSubscription.payment_method_type != "card",
                            ),
                            _due_date_window_condition(
                                func.coalesce(
                                    ClientPlanSubscription.next_payment_at,
                                    ClientPlanSubscription.current_period_end,
                                ),
                                now=now,
                            ),
                        ),
                    ),
                )
                .order_by(ClientPlanSubscription.started_at.asc(), ClientPlanSubscription.created_at.asc())
                .limit(limit)
            ).all()
            checked = len(rows)

            for subscription, plan, owner in rows:
                try:
                    issue_and_due_at = _payment_issue_and_due_at(subscription)
                    if issue_and_due_at is None:
                        skipped += 1
                        continue
                    issue, due_at = issue_and_due_at
                    phase = _reminder_phase(due_at=due_at, now=now)
                    if phase is None:
                        skipped += 1
                        continue
                    recipient = _recipient_for_subscription(db, subscription=subscription, owner=owner)
                    recipient_email = str(recipient.email or "").strip().lower()
                    if not recipient_email:
                        skipped += 1
                        continue
                    idempotency_key = _notification_key(
                        subscription_id=subscription.id,
                        recipient_id=recipient.id,
                        issue=issue,
                        phase=phase,
                        due_at=due_at,
                    )
                    if db.scalar(select(Notification.id).where(Notification.idempotency_key == idempotency_key)) is not None:
                        skipped += 1
                        continue

                    email = build_subscription_payment_reminder_email(
                        subscription=subscription,
                        plan=plan,
                        recipient=recipient,
                        issue=issue,
                        phase=phase,
                        due_at=due_at,
                    )
                    event = create_domain_event(
                        db,
                        event_type=email.event_type,
                        source=SOURCE_SCHEDULER,
                        actor_type="system",
                        actor_id=None,
                        related_entity_type="client_plan_subscription",
                        related_entity_id=subscription.id,
                        occurred_at=now,
                        payload_json={
                            "subscription_id": str(subscription.id),
                            "plan_id": str(plan.id),
                            "recipient_id": str(recipient.id),
                            "issue": issue,
                            "phase": phase,
                            "due_at": _aware(due_at).isoformat(),
                            "action_url": email.action_url,
                        },
                    )
                    notification = create_notification_if_new(
                        db,
                        notification_type=email.notification_type,
                        channel=CHANNEL_EMAIL,
                        dispatch_mode=DISPATCH_MODE_SCHEDULED,
                        source_event_id=event.id,
                        source=SOURCE_SCHEDULER,
                        related_entity_type="client_plan_subscription",
                        related_entity_id=subscription.id,
                        booking_id=None,
                        slot_id=None,
                        recipient_type="CLIENT",
                        recipient_contact_id=recipient.id,
                        recipient_email=recipient_email,
                        recipient_phone=None,
                        subject=email.subject,
                        body_snapshot=email.body,
                        payload_snapshot={
                            "body_format": "HTML",
                            "issue": issue,
                            "phase": phase,
                            "due_at": _aware(due_at).isoformat(),
                            "action_url": email.action_url,
                        },
                        idempotency_key=idempotency_key,
                        scheduled_for=now,
                        status=NOTIFICATION_STATUS_PENDING,
                    )
                    if notification is None:
                        skipped += 1
                        continue
                    created += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="INFO",
                        message=f"Subscription payment action email scheduled for {subscription.id}",
                        context_json={
                            "subscription_id": str(subscription.id),
                            "recipient_id": str(recipient.id),
                            "issue": issue,
                            "phase": phase,
                        },
                    )
                except Exception as exc:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="ERROR",
                        message=f"Subscription payment reminder failed for {subscription.id}",
                        context_json={"subscription_id": str(subscription.id), "error": str(exc)},
                    )
                    logger.exception("Subscription payment reminder failed subscription=%s", subscription.id)

            finish_job_run(
                db,
                job_run=job_run,
                status="warning" if failed else "success",
                finished_at=now,
                items_scanned=checked,
                items_processed=created + skipped + failed,
                items_sent=created,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{created} subscription payment action emails scheduled",
            )
            return SubscriptionPaymentReminderJobResult(
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


__all__ = [
    "SubscriptionPaymentReminderEmail",
    "SubscriptionPaymentReminderJobResult",
    "build_subscription_payment_reminder_email",
    "run_subscription_payment_action_reminder_job",
]
