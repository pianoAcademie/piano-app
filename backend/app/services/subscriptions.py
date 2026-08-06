from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from app.models.plan import ClientPlanSubscription, PlanKind, SubscriptionStatus

SuspensionUnit = Literal["DAY", "MONTH"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def add_months_utc(value: datetime, months: int) -> datetime:
    if months == 0:
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    total = value.month - 1 + months
    year = value.year + total // 12
    month = total % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_duration(value: datetime, *, unit: SuspensionUnit, amount: int) -> datetime:
    if unit == "MONTH":
        return add_months_utc(value, amount)
    return value + timedelta(days=amount)


def default_next_payment_at(started_at: datetime) -> datetime:
    return add_months_utc(started_at, 1)


def shift_calendar_days_utc(value: datetime, *, days: int, timezone_name: str = "Europe/Paris") -> datetime:
    local_timezone = ZoneInfo(timezone_name)
    localized = value.astimezone(local_timezone)
    return (localized + timedelta(days=days)).astimezone(timezone.utc)


def can_book_with_subscription(
    subscription: ClientPlanSubscription,
    *,
    allow_booking_during_payment_alert: bool = True,
) -> bool:
    if bool(subscription.bookings_blocked):
        return False

    status = subscription.status
    if status == SubscriptionStatus.ACTIVE:
        return True
    if status == SubscriptionStatus.PAYMENT_ALERT:
        return bool(allow_booking_during_payment_alert)
    if status in {
        SubscriptionStatus.PRE_TERMINATION,
        SubscriptionStatus.TERMINATED,
        SubscriptionStatus.PAUSED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.PENDING,
    }:
        return False
    return False


def compute_suspension_end(start_at: datetime, *, unit: SuspensionUnit, amount: int) -> datetime:
    return add_duration(start_at, unit=unit, amount=amount)


def validate_suspension_duration(*, unit: SuspensionUnit, amount: int) -> None:
    if amount < 1:
        raise ValueError("suspension amount must be >= 1")
    if unit == "DAY" and amount > 30:
        raise ValueError("day suspension cannot exceed 30")
    if unit == "MONTH" and amount > 12:
        raise ValueError("month suspension cannot exceed 12")


def apply_suspension(
    subscription: ClientPlanSubscription,
    *,
    start_at: datetime,
    unit: SuspensionUnit,
    amount: int,
) -> datetime:
    validate_suspension_duration(unit=unit, amount=amount)
    end_at = compute_suspension_end(start_at, unit=unit, amount=amount)

    subscription.suspension_starts_at = start_at
    subscription.suspension_ends_at = end_at
    subscription.suspension_duration_unit = unit
    subscription.suspension_duration_value = amount

    # Suspension freezes the billing cycle by pushing the next charge (and period end) forward.
    if subscription.next_payment_at is not None:
        if subscription.next_payment_at >= start_at:
            subscription.next_payment_at = add_duration(subscription.next_payment_at, unit=unit, amount=amount)
    else:
        subscription.next_payment_at = add_duration(default_next_payment_at(subscription.started_at), unit=unit, amount=amount)

    if subscription.ends_at is not None and subscription.ends_at >= start_at:
        subscription.ends_at = add_duration(subscription.ends_at, unit=unit, amount=amount)

    return end_at


def apply_suspension_dates(
    subscription: ClientPlanSubscription,
    *,
    start_date: date,
    end_date: date,
    timezone_name: str = "Europe/Paris",
) -> tuple[datetime, datetime]:
    """Apply an inclusive, calendar-date suspension.

    The persisted UTC end boundary is the start of the day following ``end_date``.
    Consequently the existing ``start <= now < end`` checks keep the advertised
    end date fully paused and restore access on the following day.
    """
    if end_date < start_date:
        raise ValueError("suspension end date must be on or after start date")
    paused_days = (end_date - start_date).days + 1
    if paused_days > 730:
        raise ValueError("suspension cannot exceed 730 days")

    local_timezone = ZoneInfo(timezone_name)
    start_at = datetime.combine(start_date, time.min, tzinfo=local_timezone).astimezone(timezone.utc)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=local_timezone).astimezone(timezone.utc)

    subscription.suspension_start_date = start_date
    subscription.suspension_end_date = end_date
    subscription.suspension_starts_at = start_at
    subscription.suspension_ends_at = end_at
    subscription.suspension_duration_unit = "DAY"
    subscription.suspension_duration_value = paused_days

    if subscription.next_payment_at is not None:
        if subscription.next_payment_at >= start_at:
            subscription.next_payment_at = shift_calendar_days_utc(subscription.next_payment_at, days=paused_days, timezone_name=timezone_name)
    else:
        subscription.next_payment_at = shift_calendar_days_utc(default_next_payment_at(subscription.started_at), days=paused_days, timezone_name=timezone_name)

    if subscription.ends_at is not None and subscription.ends_at >= start_at:
        subscription.ends_at = shift_calendar_days_utc(subscription.ends_at, days=paused_days, timezone_name=timezone_name)
    if subscription.current_period_end is not None and subscription.current_period_end >= start_at:
        subscription.current_period_end = shift_calendar_days_utc(subscription.current_period_end, days=paused_days, timezone_name=timezone_name)

    return start_at, end_at


def reconcile_subscription_status(subscription: ClientPlanSubscription, *, now: datetime, plan_kind: PlanKind) -> bool:
    changed = False

    if subscription.cancellation_effective_at is not None and now >= subscription.cancellation_effective_at:
        if subscription.status != SubscriptionStatus.CANCELLED:
            subscription.status = SubscriptionStatus.CANCELLED
            changed = True
        if subscription.auto_renew:
            subscription.auto_renew = False
            changed = True
        if subscription.next_payment_at is not None:
            subscription.next_payment_at = None
            changed = True
        return changed

    suspension_start = subscription.suspension_starts_at
    suspension_end = subscription.suspension_ends_at
    if suspension_start is not None and suspension_end is not None and suspension_start <= now < suspension_end:
        if subscription.status != SubscriptionStatus.PAUSED:
            subscription.status = SubscriptionStatus.PAUSED
            changed = True
        return changed

    if (
        plan_kind in {PlanKind.PACK, PlanKind.FORFAIT}
        and subscription.ends_at is not None
        and now >= subscription.ends_at
        and subscription.status in {SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED}
    ):
        subscription.status = SubscriptionStatus.EXPIRED
        changed = True
        if subscription.auto_renew:
            subscription.auto_renew = False
            changed = True
        if subscription.next_payment_at is not None:
            subscription.next_payment_at = None
            changed = True
        if plan_kind == PlanKind.PACK and (subscription.credits_remaining or 0) != 0:
            subscription.credits_remaining = 0
            changed = True
        return changed

    if subscription.status == SubscriptionStatus.PAUSED and (suspension_end is None or now >= suspension_end):
        if plan_kind == PlanKind.SUBSCRIPTION:
            subscription.status = SubscriptionStatus.ACTIVE
            changed = True

    if subscription.status == SubscriptionStatus.PRE_TERMINATION and not subscription.bookings_blocked:
        subscription.bookings_blocked = True
        changed = True

    if (
        plan_kind == PlanKind.SUBSCRIPTION
        and not subscription.auto_renew
        and subscription.ends_at is not None
        and now >= subscription.ends_at
        and subscription.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED}
    ):
        subscription.status = SubscriptionStatus.CANCELLED
        changed = True

    return changed
