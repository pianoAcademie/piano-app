from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.services.reminders import skip_pending_reminders_for_booking


@dataclass(frozen=True)
class AutoCancelResult:
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int


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
        booked_count = db.scalar(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status == BookingStatus.BOOKED,
            )
        )
        if booked_count is not None:
            continue

        session_obj.status = SessionStatus.CANCELLED
        session_obj.cancel_reason = "AUTO_NO_BOOKINGS"
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
