from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession
from app.models.ops import AppSetting
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, PlanPriceTaxMode, SubscriptionStatus
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.family_billing import resolve_billing_profile
from app.services.messaging_templates import resolve_predefined_template, resolve_sender_profile
from app.services.payment_provider import PaymentProvider, resolve_active_secret, resolve_mode, resolve_provider
from app.services.pricing import compute_tax_totals, resolve_plan_price, resolve_vat_rate, plan_service_code
from app.services.psp_gateway import MollieGateway, PayplugGateway, RecurringChargeRequest
from app.services.reminders import skip_pending_reminders_for_booking
from app.services.subscriptions import add_months_utc, default_next_payment_at, reconcile_subscription_status

logger = logging.getLogger(__name__)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class SubscriptionBillingJobResult:
    checked: int
    charged: int
    skipped: int
    failed: int


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render subscription template; returning normalized content")
        return normalized.strip()


def _admin_notification_email(db: Session, *, fallback: str | None = None) -> str | None:
    row = db.scalar(select(AppSetting).where(AppSetting.key == "config_account_contact_email"))
    configured = (row.value if row is not None else "").strip()
    if configured:
        return configured
    if fallback:
        normalized = fallback.strip()
        if normalized:
            return normalized
    return None


def _send_template_email(
    db: Session,
    *,
    template_code: str,
    context: dict[str, str],
    to_email: str,
    delivery_context: str,
) -> str | None:
    recipient = (to_email or "").strip()
    if not recipient:
        return None
    try:
        template = resolve_predefined_template(db, code=template_code)
    except KeyError:
        logger.warning("Missing predefined email template: %s", template_code)
        return None

    if not bool(template.get("active", True)):
        return None

    subject_template = str(template.get("subject") or "").strip()
    body_template = str(template.get("body") or "").strip()
    if not subject_template or not body_template:
        logger.warning("Template %s is incomplete", template_code)
        return None

    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)
    body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    return send_email(
        to_email=recipient,
        subject=subject,
        body=body,
        body_format=body_format,
        context=delivery_context,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )


def _notification_context(
    *,
    owner: User,
    plan: Plan,
    subscription: ClientPlanSubscription,
    amount: Decimal,
    currency: str,
    occurred_at: datetime,
    reason: str | None = None,
) -> dict[str, str]:
    first_name = (owner.first_name or "").strip() or owner.email
    last_name = (owner.last_name or "").strip()
    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}".strip(),
        "email": owner.email,
        "plan_name": plan.name,
        "subscription_reference": str(subscription.id),
        "amount_paid": f"{amount.quantize(Decimal('0.01')):.2f}",
        "amount_due": f"{amount.quantize(Decimal('0.01')):.2f}",
        "currency": (currency or "EUR").upper(),
        "paid_at": occurred_at.strftime("%d/%m/%Y %H:%M"),
        "payment_date": occurred_at.strftime("%d/%m/%Y %H:%M"),
        "failure_reason": reason or "",
    }


def _send_subscription_renewal_success_notifications(
    db: Session,
    *,
    owner: User,
    plan: Plan,
    subscription: ClientPlanSubscription,
    amount: Decimal,
    currency: str,
    charged_at: datetime,
) -> None:
    context = _notification_context(
        owner=owner,
        plan=plan,
        subscription=subscription,
        amount=amount,
        currency=currency,
        occurred_at=charged_at,
    )
    _send_template_email(
        db,
        template_code="PAYMENT_CONFIRMED",
        context=context,
        to_email=owner.email,
        delivery_context="SUBSCRIPTION_RENEWAL_SUCCESS_CLIENT",
    )
    admin_email = _admin_notification_email(db)
    if admin_email:
        admin_context = dict(context)
        admin_context["first_name"] = "Administration"
        admin_context["last_name"] = ""
        admin_context["full_name"] = "Administration"
        _send_template_email(
            db,
            template_code="PAYMENT_CONFIRMED",
            context=admin_context,
            to_email=admin_email,
            delivery_context="SUBSCRIPTION_RENEWAL_SUCCESS_ADMIN",
        )


def _send_subscription_renewal_failed_notifications(
    db: Session,
    *,
    owner: User,
    plan: Plan,
    subscription: ClientPlanSubscription,
    amount: Decimal,
    currency: str,
    failed_at: datetime,
    reason: str,
) -> None:
    context = _notification_context(
        owner=owner,
        plan=plan,
        subscription=subscription,
        amount=amount,
        currency=currency,
        occurred_at=failed_at,
        reason=reason,
    )
    _send_template_email(
        db,
        template_code="AUTOMATIC_PAYMENT_FAILED",
        context=context,
        to_email=owner.email,
        delivery_context="SUBSCRIPTION_RENEWAL_FAILED_CLIENT",
    )
    admin_email = _admin_notification_email(db)
    if admin_email:
        admin_context = dict(context)
        admin_context["first_name"] = "Administration"
        admin_context["last_name"] = ""
        admin_context["full_name"] = "Administration"
        _send_template_email(
            db,
            template_code="AUTOMATIC_PAYMENT_FAILED",
            context=admin_context,
            to_email=admin_email,
            delivery_context="SUBSCRIPTION_RENEWAL_FAILED_ADMIN",
        )


def _cancel_future_bookings_after_failed_renewal(
    db: Session,
    *,
    subscription_id: UUID,
    from_datetime: datetime,
    cancelled_at: datetime,
) -> int:
    rows = db.execute(
        select(Booking.id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.client_plan_subscription_id == subscription_id,
            Booking.status.in_([BookingStatus.BOOKED, BookingStatus.WAITLISTED]),
            CourseSession.start_at_utc >= from_datetime,
        )
    ).all()

    cancelled = 0
    for booking_id, in rows:
        booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
        if booking is None:
            continue
        if booking.status not in {BookingStatus.BOOKED, BookingStatus.WAITLISTED}:
            continue
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = cancelled_at
        booking.cancellation_reason = "SUBSCRIPTION_RENEWAL_FAILED"
        db.add(booking)
        skip_pending_reminders_for_booking(db, booking_id=booking.id)
        cancelled += 1
    return cancelled


def _apply_renewal_failure_state(subscription: ClientPlanSubscription, *, now: datetime) -> None:
    subscription.status = SubscriptionStatus.PAUSED
    subscription.auto_renew = False
    subscription.suspension_starts_at = now
    subscription.suspension_ends_at = None
    subscription.suspension_duration_unit = None
    subscription.suspension_duration_value = None


def run_subscription_billing_job(db: Session, *, now: datetime, limit: int = 500) -> SubscriptionBillingJobResult:
    provider = resolve_provider(db)
    active_secret = resolve_active_secret(db)
    gateway = MollieGateway(api_key=active_secret, mode=resolve_mode(db)) if provider == PaymentProvider.MOLLIE else PayplugGateway()

    rows = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(Plan.kind == PlanKind.SUBSCRIPTION)
        .order_by(ClientPlanSubscription.next_payment_at.asc().nullsfirst(), ClientPlanSubscription.created_at.asc())
        .limit(limit)
    ).all()

    checked = 0
    charged = 0
    skipped = 0
    failed = 0

    for subscription, plan, owner in rows:
        checked += 1

        if reconcile_subscription_status(subscription, now=now, plan_kind=plan.kind):
            db.add(subscription)

        if not subscription.auto_renew:
            skipped += 1
            continue
        if subscription.status != SubscriptionStatus.ACTIVE:
            skipped += 1
            continue

        due_at = subscription.next_payment_at or subscription.ends_at or default_next_payment_at(subscription.started_at)
        subscription.next_payment_at = due_at
        if due_at > now:
            db.add(subscription)
            skipped += 1
            continue

        billing_profile = resolve_billing_profile(db, owner)
        country_code = (billing_profile.residence_country or "FR").upper()
        preferred_currency = (billing_profile.preferred_currency or "EUR").upper()
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

        if subscription.billing_method_code != "CARD_ONLINE":
            subscription.last_payment_at = now
            subscription.last_payment_status = "FAILED_INVALID_BILLING_METHOD"
            _apply_renewal_failure_state(subscription, now=now)
            _cancel_future_bookings_after_failed_renewal(
                db,
                subscription_id=subscription.id,
                from_datetime=due_at,
                cancelled_at=now,
            )
            try:
                _send_subscription_renewal_failed_notifications(
                    db,
                    owner=owner,
                    plan=plan,
                    subscription=subscription,
                    amount=Decimal("0.00"),
                    currency=currency_code,
                    failed_at=now,
                    reason="Moyen de paiement non compatible avec le renouvellement automatique",
                )
            except Exception:
                logger.exception("Unable to send renewal-failed emails (invalid billing method) for subscription=%s", subscription.id)
            db.add(subscription)
            failed += 1
            continue

        if provider != PaymentProvider.MOLLIE:
            subscription.last_payment_at = now
            subscription.last_payment_status = "FAILED_PROVIDER_NOT_SUPPORTED"
            _apply_renewal_failure_state(subscription, now=now)
            _cancel_future_bookings_after_failed_renewal(
                db,
                subscription_id=subscription.id,
                from_datetime=due_at,
                cancelled_at=now,
            )
            try:
                _send_subscription_renewal_failed_notifications(
                    db,
                    owner=owner,
                    plan=plan,
                    subscription=subscription,
                    amount=Decimal("0.00"),
                    currency=currency_code,
                    failed_at=now,
                    reason="PSP non compatible avec le prelevement recurrent",
                )
            except Exception:
                logger.exception("Unable to send renewal-failed emails (provider unsupported) for subscription=%s", subscription.id)
            db.add(subscription)
            failed += 1
            continue

        if price_excl_vat is None:
            subscription.last_payment_at = now
            subscription.last_payment_status = "FAILED_NO_PRICE"
            _apply_renewal_failure_state(subscription, now=now)
            _cancel_future_bookings_after_failed_renewal(
                db,
                subscription_id=subscription.id,
                from_datetime=due_at,
                cancelled_at=now,
            )
            try:
                _send_subscription_renewal_failed_notifications(
                    db,
                    owner=owner,
                    plan=plan,
                    subscription=subscription,
                    amount=Decimal("0.00"),
                    currency=currency_code,
                    failed_at=now,
                    reason="Tarif d'abonnement introuvable",
                )
            except Exception:
                logger.exception("Unable to send renewal-failed emails (missing price) for subscription=%s", subscription.id)
            db.add(subscription)
            failed += 1
            continue

        _, _, total_incl_vat = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)

        result = gateway.create_recurring_charge(
            RecurringChargeRequest(
                amount=total_incl_vat,
                currency=currency_code,
                description=f"{plan.name} - renouvellement mensuel",
                customer_reference=subscription.payment_provider_customer_ref,
                mandate_reference=subscription.payment_provider_mandate_ref,
            )
        )

        subscription.last_payment_at = now
        subscription.last_payment_status = result.status
        if result.success:
            next_due = add_months_utc(due_at, 1)
            subscription.next_payment_at = next_due
            subscription.ends_at = next_due
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.auto_renew = True
            charged += 1
            try:
                _send_subscription_renewal_success_notifications(
                    db,
                    owner=owner,
                    plan=plan,
                    subscription=subscription,
                    amount=total_incl_vat,
                    currency=currency_code,
                    charged_at=now,
                )
            except Exception:
                logger.exception("Unable to send renewal-success emails for subscription=%s", subscription.id)
        else:
            _apply_renewal_failure_state(subscription, now=now)
            _cancel_future_bookings_after_failed_renewal(
                db,
                subscription_id=subscription.id,
                from_datetime=due_at,
                cancelled_at=now,
            )
            try:
                _send_subscription_renewal_failed_notifications(
                    db,
                    owner=owner,
                    plan=plan,
                    subscription=subscription,
                    amount=total_incl_vat,
                    currency=currency_code,
                    failed_at=now,
                    reason=(result.message or result.status or "Echec de renouvellement"),
                )
            except Exception:
                logger.exception("Unable to send renewal-failed emails for subscription=%s", subscription.id)
            failed += 1
        db.add(subscription)

    return SubscriptionBillingJobResult(
        checked=checked,
        charged=charged,
        skipped=skipped,
        failed=failed,
    )
