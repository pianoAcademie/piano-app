from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, PlanningConfig, SessionStatus
from app.services.reminders import skip_pending_reminders_for_booking


@dataclass(frozen=True)
class AutoCancelResult:
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int


PLANNING_AUTO_CANCEL_DEFAULTS = {
    "auto_cancel_if_booked_less_than": 1,
}


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
