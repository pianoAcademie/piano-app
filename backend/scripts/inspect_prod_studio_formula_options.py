from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location
from app.models.user import User

SCRIPT_PREFIX = "PROD_INITIATION_RICHELIEU_15H_INSPECT"

COUNTED_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}
ACTIVE_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _status_value(value: object) -> str:
    return getattr(value, "value", str(value))


def _display_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _local_dt(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))


def _local_time_in_window(local_moment: datetime) -> bool:
    return time(14, 30) <= local_moment.time().replace(second=0, microsecond=0) <= time(15, 30)


def main() -> None:
    period_start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 12, 1, tzinfo=timezone.utc)

    with SessionLocal() as db:
        rows = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                CourseSession.start_at_utc >= period_start,
                CourseSession.start_at_utc < period_end,
                func.lower(CourseType.name).like("%initiation%"),
                func.lower(Location.name).like("%richelieu%"),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        _print(f"candidate_initiation_richelieu_sessions_sep_to_nov={len(rows)}")
        target_rows = [
            (session_obj, course_type, location, _local_dt(session_obj))
            for session_obj, course_type, location in rows
            if _local_time_in_window(_local_dt(session_obj))
        ]
        _print(f"target_sessions_around_15h={len(target_rows)}")

        if not target_rows:
            for session_obj, course_type, location in rows:
                local_moment = _local_dt(session_obj)
                _print(
                    "available_initiation_session="
                    f"{local_moment:%Y-%m-%d %H:%M}|session={session_obj.id}|"
                    f"group={session_obj.recurrence_group_id or '-'}|type={course_type.name}|"
                    f"location={location.name}|status={_status_value(session_obj.status)}"
                )
            return

        session_ids = [session_obj.id for session_obj, _, _, _ in target_rows]
        booking_rows = db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.session_id.in_(session_ids))
            .order_by(User.last_name.asc(), User.first_name.asc(), Booking.booked_at.asc())
        ).all()
        bookings_by_session = defaultdict(list)
        for booking, user in booking_rows:
            bookings_by_session[booking.session_id].append((booking, user))

        target_group_ids = sorted({str(session_obj.recurrence_group_id) for session_obj, _, _, _ in target_rows if session_obj.recurrence_group_id})

        for session_obj, course_type, location, local_moment in target_rows:
            session_bookings = bookings_by_session.get(session_obj.id, [])
            counted = [(booking, user) for booking, user in session_bookings if booking.status in COUNTED_STATUSES]
            waitlisted = [(booking, user) for booking, user in session_bookings if booking.status == BookingStatus.WAITLISTED]
            cancelled = [(booking, user) for booking, user in session_bookings if booking.status == BookingStatus.CANCELLED]
            _print(
                "slot="
                f"{local_moment:%Y-%m-%d %H:%M}|session={session_obj.id}|"
                f"group={session_obj.recurrence_group_id or '-'}|rule={session_obj.recurrence_rule or '-'}|"
                f"until={session_obj.recurrence_until_date or '-'}|type={course_type.name}|location={location.name}|"
                f"status={_status_value(session_obj.status)}|capacity={session_obj.capacity_max}|"
                f"counted={len(counted)}|waitlisted={len(waitlisted)}|cancelled={len(cancelled)}"
            )
            for label, items in (("counted", counted), ("waitlisted", waitlisted), ("cancelled", cancelled)):
                names = ", ".join(f"{_display_name(user)} [{_status_value(booking.status)}]" for booking, user in items)
                _print(f"slot_{label}={local_moment:%Y-%m-%d}|{names or '-'}")

        for group_id in target_group_ids:
            group_sessions = db.execute(
                select(CourseSession, CourseType, Location)
                .join(CourseType, CourseType.id == CourseSession.course_type_id)
                .join(Location, Location.id == CourseSession.location_id)
                .where(
                    CourseSession.recurrence_group_id == group_id,
                    CourseSession.start_at_utc >= period_start,
                    CourseSession.start_at_utc < period_end,
                )
                .order_by(CourseSession.start_at_utc.asc())
            ).all()
            group_session_ids = [session_obj.id for session_obj, _, _ in group_sessions]
            group_bookings = db.execute(
                select(Booking, User)
                .join(User, User.id == Booking.user_id)
                .where(Booking.session_id.in_(group_session_ids))
                .order_by(User.last_name.asc(), User.first_name.asc(), Booking.booked_at.asc())
            ).all()
            by_user: dict[str, list[str]] = defaultdict(list)
            by_user_statuses: dict[str, set[str]] = defaultdict(set)
            by_session = defaultdict(list)
            for booking, user in group_bookings:
                session_local = next(
                    _local_dt(session_obj)
                    for session_obj, _, _ in group_sessions
                    if session_obj.id == booking.session_id
                )
                key = f"{_display_name(user)} <{user.email}>"
                by_user[key].append(f"{session_local:%Y-%m-%d}:{_status_value(booking.status)}")
                by_user_statuses[key].add(_status_value(booking.status))
                by_session[booking.session_id].append((booking, user))

            _print(f"group_summary={group_id}|sessions={len(group_sessions)}|distinct_students={len(by_user)}")
            for session_obj, _, _ in group_sessions:
                local_moment = _local_dt(session_obj)
                counted = [
                    (booking, user)
                    for booking, user in by_session.get(session_obj.id, [])
                    if booking.status in COUNTED_STATUSES
                ]
                _print(
                    "group_slot_count="
                    f"{local_moment:%Y-%m-%d %H:%M}|session={session_obj.id}|"
                    f"counted={len(counted)}|students={', '.join(_display_name(user) for _, user in counted) or '-'}"
                )
            for user_key, dates in sorted(by_user.items()):
                _print(f"group_student={group_id}|{user_key}|{';'.join(dates)}")


if __name__ == "__main__":
    main()
