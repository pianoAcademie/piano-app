from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import _cancel_booking_for_cancelled_session
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.notification_engine import Notification
from app.models.ops import EmailReminder, ReminderStatus
from app.models.user import User
from app.services.notifications.domain.constants import (
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_REMINDER_SMS,
)


SCRIPT_PREFIX = "REPAIR_CANCELLED_SESSION_BOOKINGS"


def _full_name(user: User | None) -> str:
    if user is None:
        return "-"
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or user.email


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Close bookings that remained active after an administrator cancelled their session."
    )
    parser.add_argument("--local-date", type=date.fromisoformat, required=True)
    parser.add_argument("--local-time", type=time.fromisoformat, required=True)
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    local_start = datetime.combine(args.local_date, args.local_time, tzinfo=ZoneInfo(args.timezone))
    target_start_utc = local_start.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        sessions = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.status == SessionStatus.CANCELLED,
                CourseSession.start_at_utc == target_start_utc,
            )
            .order_by(CourseSession.title.asc(), CourseSession.id.asc())
            .with_for_update()
        ).all()
        if not sessions:
            raise SystemExit(
                f"{SCRIPT_PREFIX}|abort|reason=no_cancelled_session|start_utc={target_start_utc.isoformat()}"
            )

        cancelled_bookings = 0
        restored_credits = 0
        for session_obj in sessions:
            bookings = db.scalars(
                select(Booking)
                .where(
                    Booking.session_id == session_obj.id,
                    Booking.status != BookingStatus.CANCELLED,
                )
                .order_by(Booking.booked_at.asc(), Booking.id.asc())
                .with_for_update()
            ).all()
            print(
                f"{SCRIPT_PREFIX}|session|id={session_obj.id}|title={session_obj.title}|"
                f"start_utc={session_obj.start_at_utc.isoformat()}|active_bookings={len(bookings)}"
            )
            for booking in bookings:
                user = db.get(User, booking.user_id)
                previous_status = booking.status.value
                restored = _cancel_booking_for_cancelled_session(
                    db,
                    booking=booking,
                    session_obj=session_obj,
                    now=now,
                    cancellation_reason="ADMIN_SESSION_CANCELLED_REPAIR",
                )
                cancelled_bookings += 1
                restored_credits += int(restored)
                print(
                    f"{SCRIPT_PREFIX}|booking|id={booking.id}|student={_full_name(user)}|"
                    f"email={user.email if user else '-'}|previous_status={previous_status}|"
                    f"credit_restored={restored}"
                )

        db.flush()
        target_ids = [session_obj.id for session_obj in sessions]
        active_bookings_after = int(
            db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.session_id.in_(target_ids),
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
            or 0
        )
        legacy_reminders_after = int(
            db.scalar(
                select(func.count(EmailReminder.id))
                .join(Booking, Booking.id == EmailReminder.booking_id)
                .where(
                    Booking.session_id.in_(target_ids),
                    EmailReminder.status == ReminderStatus.PENDING,
                )
            )
            or 0
        )
        engine_reminders_after = int(
            db.scalar(
                select(func.count(Notification.id))
                .join(Booking, Booking.id == Notification.booking_id)
                .where(
                    Booking.session_id.in_(target_ids),
                    Notification.notification_type.in_(
                        [NOTIFICATION_TYPE_REMINDER_EMAIL, NOTIFICATION_TYPE_REMINDER_SMS]
                    ),
                    Notification.status.in_([NOTIFICATION_STATUS_PENDING, NOTIFICATION_STATUS_QUEUED]),
                )
            )
            or 0
        )

        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(
            f"{SCRIPT_PREFIX}|summary|sessions={len(sessions)}|cancelled_bookings={cancelled_bookings}|"
            f"restored_credits={restored_credits}|active_bookings_after={active_bookings_after}|"
            f"legacy_reminders_after={legacy_reminders_after}|engine_reminders_after={engine_reminders_after}|"
            f"applied={args.apply}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
