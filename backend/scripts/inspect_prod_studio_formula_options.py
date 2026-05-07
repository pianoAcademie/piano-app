from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.user import ClientKind, User, UserRole

SCRIPT_PREFIX = "PROD_SERIES_BOOKING_AUDIT"
SCHOOL_YEAR_START_LOCAL = datetime(2026, 9, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))
SCHOOL_YEAR_END_LOCAL = datetime(2027, 7, 1, 0, 0, tzinfo=ZoneInfo("Europe/Paris"))

BOOKING_STATUSES_PRESENT = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))


def _local_label(session_obj: CourseSession) -> str:
    return _local_start(session_obj).strftime("%Y-%m-%d %H:%M")


def _slot_label(session_obj: CourseSession) -> str:
    start = _local_start(session_obj)
    end = session_obj.end_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))
    weekdays = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    return f"{weekdays[start.weekday()]} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _user_label(user: User) -> str:
    return f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email or str(user.id)


def _course_is_vacation(course_type: CourseType) -> bool:
    haystack = f"{course_type.name or ''} {course_type.code or ''} {course_type.service_code or ''}".casefold()
    return "vacance" in haystack or "vacation" in haystack


def main() -> None:
    start_utc = SCHOOL_YEAR_START_LOCAL.astimezone(timezone.utc)
    end_utc = SCHOOL_YEAR_END_LOCAL.astimezone(timezone.utc)

    with SessionLocal() as db:
        rows = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                CourseSession.recurrence_group_id.is_not(None),
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc < end_utc,
            )
            .order_by(CourseSession.recurrence_group_id.asc(), CourseSession.start_at_utc.asc())
        ).all()

        series: dict[object, list[tuple[CourseSession, CourseType, Location]]] = defaultdict(list)
        for session_obj, course_type, location in rows:
            if _course_is_vacation(course_type):
                continue
            series[session_obj.recurrence_group_id].append((session_obj, course_type, location))

        series = {group_id: group_rows for group_id, group_rows in series.items() if len(group_rows) > 1}
        session_ids = [session_obj.id for group_rows in series.values() for session_obj, _, _ in group_rows]

        _print(f"school_year=2026-2027|series_checked={len(series)}|sessions_checked={len(session_ids)}")

        booking_rows = []
        if session_ids:
            booking_rows = db.execute(
                select(Booking, User)
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.session_id.in_(session_ids),
                    User.role == UserRole.CLIENT,
                    User.client_kind == ClientKind.CHILD,
                )
            ).all()

        bookings_by_session_user: dict[tuple[object, object], list[Booking]] = defaultdict(list)
        present_user_ids_by_session: dict[object, set[object]] = defaultdict(set)
        users_by_id: dict[object, User] = {}
        for booking, user in booking_rows:
            bookings_by_session_user[(booking.session_id, booking.user_id)].append(booking)
            users_by_id[user.id] = user
            if booking.status in BOOKING_STATUSES_PRESENT:
                present_user_ids_by_session[booking.session_id].add(user.id)

        anomalies: list[dict[str, object]] = []
        complete_students = 0
        audited_student_series = 0

        for group_id, group_rows in series.items():
            sessions = [session_obj for session_obj, _, _ in group_rows]
            course_type = group_rows[0][1]
            location = group_rows[0][2]
            student_ids = set()
            for session_obj in sessions:
                student_ids.update(present_user_ids_by_session.get(session_obj.id, set()))

            for user_id in sorted(student_ids, key=lambda value: _user_label(users_by_id[value]).casefold()):
                present_indexes = []
                cancelled_indexes = []
                for index, session_obj in enumerate(sessions):
                    bookings = bookings_by_session_user.get((session_obj.id, user_id), [])
                    if any(booking.status in BOOKING_STATUSES_PRESENT for booking in bookings):
                        present_indexes.append(index)
                    elif any(booking.status == BookingStatus.CANCELLED for booking in bookings):
                        cancelled_indexes.append(index)

                if not present_indexes:
                    continue

                audited_student_series += 1
                first_index = min(present_indexes)
                expected_indexes = list(range(first_index, len(sessions)))
                missing_indexes = [index for index in expected_indexes if index not in present_indexes]
                if not missing_indexes:
                    complete_students += 1
                    continue

                user = users_by_id[user_id]
                missing_sessions = [sessions[index] for index in missing_indexes]
                cancelled_missing = [sessions[index] for index in missing_indexes if index in cancelled_indexes]
                anomalies.append(
                    {
                        "group_id": group_id,
                        "student": _user_label(user),
                        "student_id": user_id,
                        "activity": course_type.name,
                        "location": location.name,
                        "slot": _slot_label(sessions[first_index]),
                        "series_sessions": len(sessions),
                        "present_count": len(present_indexes),
                        "first_present": _local_label(sessions[first_index]),
                        "last_present": _local_label(sessions[max(present_indexes)]),
                        "missing_count": len(missing_sessions),
                        "cancelled_missing_count": len(cancelled_missing),
                        "missing_sample": ", ".join(_local_label(session_obj) for session_obj in missing_sessions[:12]),
                    }
                )

        _print(
            "summary="
            f"student_series_audited={audited_student_series}|complete={complete_students}|"
            f"anomalies={len(anomalies)}"
        )

        for anomaly in sorted(
            anomalies,
            key=lambda item: (
                str(item["activity"]).casefold(),
                str(item["location"]).casefold(),
                str(item["slot"]),
                str(item["student"]).casefold(),
            ),
        ):
            _print(
                "anomaly="
                f"student={anomaly['student']}|student_id={anomaly['student_id']}|"
                f"activity={anomaly['activity']}|location={anomaly['location']}|slot={anomaly['slot']}|"
                f"group={anomaly['group_id']}|series_sessions={anomaly['series_sessions']}|"
                f"present={anomaly['present_count']}|missing={anomaly['missing_count']}|"
                f"cancelled_missing={anomaly['cancelled_missing_count']}|"
                f"first_present={anomaly['first_present']}|last_present={anomaly['last_present']}|"
                f"missing_sample={anomaly['missing_sample']}"
            )


if __name__ == "__main__":
    main()
