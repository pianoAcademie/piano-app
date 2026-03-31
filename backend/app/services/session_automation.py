from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, PlanningConfig, SessionStatus
from app.models.client_record import PaymentReceipt
from app.services.reminders import skip_pending_reminders_for_booking


@dataclass(frozen=True)
class AutoCancelResult:
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int


@dataclass(frozen=True)
class PaymentHoldExpirationResult:
    checked: int
    expired_bookings: int
    expired_receipts: int


PLANNING_AUTO_CANCEL_DEFAULTS = {
    "auto_cancel_if_booked_less_than": 1,
}
PAYMENT_TIMEOUT_CANCELLATION_REASON = "PAYMENT_TIMEOUT"


def _effective_auto_cancel_threshold(db: Session, *, session_obj: CourseSession) -> int:
    config = db.scalar(select(PlanningConfig).where(PlanningConfig.location_id == session_obj.location_id))
    threshold = int(
        config.auto_cancel_if_booked_less_than
        if config is not None
        else PLANNING_AUTO_CANCEL_DEFAULTS["auto_cancel_if_booked_less_than"]
    )
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is not None and course_type.auto_cancel_if_booked_less_than_override is not None:
        threshold = int(course_type.auto_cancel_if_booked_less_than_override)
    return max(0, threshold)


def run_auto_cancel_empty_sessions_job(db: Session, *, now: datetime, limit: int = 200) -> AutoCancelResult:
    sessions = db.scalars(
        select(CourseSession)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.auto_cancel_deadline_utc <= now,
        )
        .order_by(CourseSession.auto_cancel_deadline_utc.asc())
        .limit(limit)
        .with_for_update()
    ).all()

    cancelled_sessions = 0
    cancelled_bookings = 0

    for session_obj in sessions:
        threshold = _effective_auto_cancel_threshold(db, session_obj=session_obj)
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

        session_obj.status = SessionStatus.CANCELLED
        session_obj.cancel_reason = "AUTO_NO_BOOKINGS" if threshold <= 1 and booked_count == 0 else "AUTO_LOW_BOOKINGS"
        cancelled_sessions += 1

        bookings = db.scalars(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status.in_([BookingStatus.BOOKED, BookingStatus.WAITLISTED]),
            )
            .with_for_update()
        ).all()

        for booking in bookings:
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
