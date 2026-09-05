from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientManualCreditBalance, PaymentReceipt
from app.models.plan import ClientPlanSubscription, Plan, PlanKind
from app.services.notifications.application.orchestrator import (
    OrchestratedNotification,
    schedule_auto_low_attendance_cancellation_notifications,
)
from app.services.reminders import skip_pending_reminders_for_booking
from app.services.session_protection import is_core_lesson_course_type


@dataclass(frozen=True)
class AutoCancelResult:
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int
    notifications: tuple[OrchestratedNotification, ...] = ()


@dataclass(frozen=True)
class PaymentHoldExpirationResult:
    checked: int
    expired_bookings: int
    expired_receipts: int


PAYMENT_TIMEOUT_CANCELLATION_REASON = "PAYMENT_TIMEOUT"
DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY = "cancelled_booking_credit_restored_at"
RICHELIEU_LOCATION_CODE = "RICHELIEU"
REHEARSAL_STUDIO_COURSE_CODE = "STUDIO_REHEARSAL"
RICHELIEU_COLLECTIVE_PROTECTED_HOUR = 19


def _restore_fully_paid_direct_booking_credit(db: Session, *, booking: Booking) -> bool:
    """Turn a retained payment for a cancelled direct booking into one reusable credit."""
    if booking.client_plan_subscription_id is not None or booking.manual_credit_type_id is not None:
        return False

    booking_total = Decimal(booking.total_incl_vat_snapshot or 0).quantize(Decimal("0.01"))
    if booking_total <= Decimal("0.00"):
        return False

    receipts = db.scalars(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.booking_id == booking.id,
            PaymentReceipt.status.in_(["COMPLETED", "PAID"]),
        )
        .order_by(PaymentReceipt.created_at.asc())
        .with_for_update()
    ).all()
    if not receipts:
        return False
    if any(DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY in dict(receipt.receipt_metadata or {}) for receipt in receipts):
        return False

    paid_total = sum((Decimal(receipt.amount_paid or 0) for receipt in receipts), Decimal("0.00")).quantize(Decimal("0.01"))
    if paid_total < booking_total:
        return False

    credit_type_id = db.scalar(
        select(CourseType.credit_type_id)
        .join(CourseSession, CourseSession.course_type_id == CourseType.id)
        .where(CourseSession.id == booking.session_id)
    )
    if credit_type_id is None:
        return False

    balance = db.scalar(
        select(ClientManualCreditBalance)
        .where(
            ClientManualCreditBalance.user_id == booking.user_id,
            ClientManualCreditBalance.credit_type_id == credit_type_id,
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if balance is None:
        balance = ClientManualCreditBalance(
            user_id=booking.user_id,
            credit_type_id=credit_type_id,
            credits_count=1,
            updated_at=now,
        )
        db.add(balance)
    else:
        balance.credits_count = int(balance.credits_count or 0) + 1
        balance.updated_at = now

    marker_receipt = receipts[-1]
    metadata = dict(marker_receipt.receipt_metadata or {})
    metadata[DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY] = now.isoformat()
    metadata["cancelled_booking_credit_type_id"] = str(credit_type_id)
    marker_receipt.receipt_metadata = metadata
    marker_receipt.updated_at = now
    return True


def restore_cancelled_booking_credit(db: Session, *, booking: Booking) -> bool:
    """Restore a credit consumed by a booking and report whether it changed.

    Subscription and forfait bookings do not consume a unit credit. Pack and
    manual-credit bookings do, so only those balances are incremented.
    """
    from app.services.makeup_accounting import makeup_role
    if makeup_role(booking) == "replacement":
        from app.services.makeup_booking import release_replacement
        return release_replacement(db, booking, now=datetime.now(timezone.utc)) is not None
    restored = False
    if booking.client_plan_subscription_id is not None:
        row = db.execute(
            select(ClientPlanSubscription, Plan)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(ClientPlanSubscription.id == booking.client_plan_subscription_id)
            .with_for_update()
        ).first()
        if row is not None:
            subscription, plan = row
            if subscription.user_id == booking.user_id and plan.kind == PlanKind.PACK:
                current = int(subscription.credits_remaining or 0)
                cap = int(subscription.credits_initial) if subscription.credits_initial is not None else current + 1
                subscription.credits_remaining = min(current + 1, cap)
                restored = int(subscription.credits_remaining or 0) > current
    if booking.manual_credit_type_id is not None:
        balance = db.scalar(
            select(ClientManualCreditBalance)
            .where(
                ClientManualCreditBalance.user_id == booking.user_id,
                ClientManualCreditBalance.credit_type_id == booking.manual_credit_type_id,
            )
            .with_for_update()
        )
        if balance is not None:
            balance.credits_count = int(balance.credits_count or 0) + 1
            restored = True
    if not restored:
        restored = _restore_fully_paid_direct_booking_credit(db, booking=booking)
    return restored


# Kept for compatibility with existing imports/tests while callers migrate to
# the public helper above.
_restore_cancelled_booking_credit = restore_cancelled_booking_credit


def _effective_auto_cancel_threshold(db: Session, *, session_obj: CourseSession) -> int | None:
    if session_obj.auto_cancel_rule_enabled_override is False:
        return None
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None or is_core_lesson_course_type(course_type):
        return None
    if session_obj.auto_cancel_rule_enabled_override is True:
        threshold = session_obj.auto_cancel_if_booked_less_than_override
        return int(threshold) if threshold is not None and int(threshold) >= 1 else None
    if not bool(course_type.auto_cancel_rule_enabled):
        return None
    threshold = course_type.auto_cancel_if_booked_less_than_override
    return int(threshold) if threshold is not None and int(threshold) >= 1 else None


def _is_protected_richelieu_collective(
    *,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
) -> bool:
    if (location.code or "").strip().upper() != RICHELIEU_LOCATION_CODE:
        return False
    course_type_label = (course_type.name or "").casefold()
    if "collectif" not in course_type_label or "ado/adultes" not in course_type_label:
        return False
    try:
        local_start = session_obj.start_at_utc.astimezone(ZoneInfo(location.timezone or "Europe/Paris"))
    except ZoneInfoNotFoundError:
        return False
    return local_start.hour == RICHELIEU_COLLECTIVE_PROTECTED_HOUR and local_start.minute == 0


def _has_booked_overlapping_rehearsal_studio(db: Session, *, session_obj: CourseSession) -> bool:
    context = db.execute(
        select(CourseType, Location)
        .join(CourseSession, CourseSession.course_type_id == CourseType.id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            CourseSession.id == session_obj.id,
        )
    ).one_or_none()
    if context is None:
        return False
    course_type, location = context
    if not _is_protected_richelieu_collective(
        session_obj=session_obj,
        course_type=course_type,
        location=location,
    ):
        return False

    booked_studio_count = db.scalar(
        select(func.count(Booking.id))
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.id != session_obj.id,
            CourseSession.location_id == session_obj.location_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc < session_obj.end_at_utc,
            CourseSession.end_at_utc > session_obj.start_at_utc,
            CourseType.code == REHEARSAL_STUDIO_COURSE_CODE,
            Booking.status == BookingStatus.BOOKED,
        )
    )
    return int(booked_studio_count or 0) >= 1


def run_auto_cancel_empty_sessions_job(db: Session, *, now: datetime, limit: int = 200) -> AutoCancelResult:
    sessions = db.scalars(
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.auto_cancel_deadline_utc <= now,
            CourseSession.auto_cancel_checked_at.is_(None),
            CourseSession.start_at_utc > now,
            (
                (CourseSession.auto_cancel_rule_enabled_override.is_(True))
                | (
                    CourseSession.auto_cancel_rule_enabled_override.is_(None)
                    & CourseType.auto_cancel_rule_enabled.is_(True)
                )
            ),
        )
        .order_by(CourseSession.auto_cancel_deadline_utc.asc())
        .limit(limit)
        .with_for_update(of=CourseSession, skip_locked=True)
    ).all()

    cancelled_sessions = 0
    cancelled_bookings = 0
    notifications: list[OrchestratedNotification] = []

    for session_obj in sessions:
        threshold = _effective_auto_cancel_threshold(db, session_obj=session_obj)
        if threshold is None:
            continue
        session_obj.auto_cancel_checked_at = now
        if _has_booked_overlapping_rehearsal_studio(db, session_obj=session_obj):
            continue
        booked_count = int(
            db.scalar(
                select(func.count(Booking.id))
                .where(
                    Booking.session_id == session_obj.id,
                    Booking.status == BookingStatus.BOOKED,
                )
            )
            or 0
        )
        if booked_count >= threshold:
            continue

        bookings = db.scalars(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status.in_([BookingStatus.BOOKED, BookingStatus.WAITLISTED]),
            )
            .with_for_update()
        ).all()

        participant_bookings = [booking for booking in bookings if booking.status == BookingStatus.BOOKED]
        notifications.extend(
            schedule_auto_low_attendance_cancellation_notifications(
                db,
                slot=session_obj,
                bookings=participant_bookings,
                booked_count=booked_count,
                minimum_attendees=threshold,
                occurred_at=now,
            )
        )
        session_obj.status = SessionStatus.CANCELLED
        session_obj.cancel_reason = "AUTO_LOW_BOOKINGS"
        cancelled_sessions += 1

        for booking in bookings:
            if booking.status == BookingStatus.BOOKED:
                restore_cancelled_booking_credit(db, booking=booking)
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.cancellation_reason = "AUTO_SESSION_CANCELLED"
            cancelled_bookings += 1
            skip_pending_reminders_for_booking(
                db,
                booking_id=str(booking.id),
                reason="Session auto-cancelled",
                now=now,
            )

    return AutoCancelResult(
        checked=len(sessions),
        cancelled_sessions=cancelled_sessions,
        cancelled_bookings=cancelled_bookings,
        notifications=tuple(notifications),
    )


def run_expire_pending_payment_bookings_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 200,
) -> PaymentHoldExpirationResult:
    bookings = db.scalars(
        select(Booking)
        .where(
            Booking.status == BookingStatus.PENDING_PAYMENT,
            Booking.payment_hold_expires_at.is_not(None),
            Booking.payment_hold_expires_at <= now,
        )
        .order_by(Booking.payment_hold_expires_at.asc(), Booking.booked_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    expired_receipts = 0
    for booking in bookings:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = PAYMENT_TIMEOUT_CANCELLATION_REASON
        booking.payment_hold_expires_at = None
        skip_pending_reminders_for_booking(
            db,
            booking_id=str(booking.id),
            reason="Pending payment expired",
            now=now,
        )
        receipts = db.scalars(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.booking_id == booking.id,
                PaymentReceipt.status == "PENDING",
                PaymentReceipt.final_invoice_note_id.is_(None),
            )
            .with_for_update()
        ).all()
        for receipt in receipts:
            metadata = dict(receipt.receipt_metadata or {})
            metadata["booking_hold_expired_at"] = now.isoformat()
            receipt.status = "EXPIRED"
            receipt.receipt_metadata = metadata
            receipt.updated_at = now
            db.add(receipt)
            expired_receipts += 1

    return PaymentHoldExpirationResult(
        checked=len(bookings),
        expired_bookings=len(bookings),
        expired_receipts=expired_receipts,
    )
