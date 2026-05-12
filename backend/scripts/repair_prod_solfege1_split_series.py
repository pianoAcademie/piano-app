from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, SessionStatus


START_DATE = date(2026, 9, 1)


def _token(value: object) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.replace("-", " ").split())


def _is_solfege_level_1(name: str) -> bool:
    token = _token(name)
    return "solfege" in token and "niveau 1" in token


def _local_start_key(session_obj: CourseSession) -> tuple[object, ...]:
    local_start = session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone)).replace(tzinfo=None)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        session_obj.timezone,
        local_start,
    )


def _series_key(session_obj: CourseSession) -> tuple[object, ...]:
    local_start = session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone)).replace(tzinfo=None)
    duration_minutes = int((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds() // 60)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        session_obj.timezone,
        local_start.weekday(),
        local_start.time().replace(second=0, microsecond=0),
        duration_minutes,
    )


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(CourseSession, CourseType.name, func.count(Booking.id).label("bookings_count"))
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .outerjoin(Booking, Booking.session_id == CourseSession.id)
            .where(
                CourseSession.recurrence_group_id.is_not(None),
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= START_DATE,
            )
            .group_by(CourseSession.id, CourseType.name)
            .order_by(CourseSession.start_at_utc.asc(), CourseSession.created_at.asc())
        ).all()

        sessions: list[tuple[CourseSession, int]] = [
            (session_obj, int(bookings_count or 0))
            for session_obj, course_name, bookings_count in rows
            if _is_solfege_level_1(course_name)
        ]

        by_local_start: dict[tuple[object, ...], list[tuple[CourseSession, int]]] = defaultdict(list)
        for session_obj, bookings_count in sessions:
            by_local_start[_local_start_key(session_obj)].append((session_obj, bookings_count))

        deleted_duplicates = 0
        deleted_ids: set[UUID] = set()
        for duplicates in by_local_start.values():
            if len(duplicates) <= 1:
                continue
            duplicates.sort(key=lambda item: (-item[1], item[0].created_at, str(item[0].id)))
            keep = duplicates[0][0]
            for duplicate, bookings_count in duplicates[1:]:
                if bookings_count > 0:
                    continue
                deleted_ids.add(duplicate.id)
                db.delete(duplicate)
                deleted_duplicates += 1

        remaining_sessions = [(session_obj, bookings_count) for session_obj, bookings_count in sessions if session_obj.id not in deleted_ids]
        by_series: dict[tuple[object, ...], list[CourseSession]] = defaultdict(list)
        for session_obj, _bookings_count in remaining_sessions:
            by_series[_series_key(session_obj)].append(session_obj)

        merged_groups = 0
        updated_sessions = 0
        for series_sessions in by_series.values():
            group_ids = {session_obj.recurrence_group_id for session_obj in series_sessions}
            if len(group_ids) <= 1:
                continue
            series_sessions.sort(key=lambda session_obj: (session_obj.start_at_utc, session_obj.created_at, str(session_obj.id)))
            canonical_group_id = series_sessions[0].recurrence_group_id
            canonical_until = max(
                (session_obj.recurrence_until_date for session_obj in series_sessions if session_obj.recurrence_until_date is not None),
                default=None,
            )
            merged_groups += len(group_ids) - 1
            for session_obj in series_sessions:
                if session_obj.recurrence_group_id != canonical_group_id:
                    updated_sessions += 1
                session_obj.recurrence_group_id = canonical_group_id
                session_obj.recurrence_rule = "WEEKLY@LOCAL"
                if canonical_until is not None:
                    session_obj.recurrence_until_date = canonical_until

        db.commit()

        print(f"solfege1_sessions={len(remaining_sessions)}")
        print(f"merged_groups={merged_groups}")
        print(f"updated_sessions={updated_sessions}")
        print(f"deleted_duplicates={deleted_duplicates}")


if __name__ == "__main__":
    main()
