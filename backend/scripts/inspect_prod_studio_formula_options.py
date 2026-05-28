from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.ops import AppSetting
from app.models.quote import Quote, QuoteLine
from app.services.quotes.quote_documents import (
    QUOTE_SCHOOL_CALENDARS_SETTING_KEY,
    _calendar_row_applies_to_session,
    _expand_calendar_vacation_dates,
    _is_true,
    _json_list,
    _json_object,
    _parse_iso_date_set,
)

PREFIX = "PROD_BAR_LE_DUC_PLANNING_SUMMARY"
QUOTE_NUMBER = "DV-20260523090618-2B4D"
EXPECTED_END = date(2027, 6, 19)


def p(line: str) -> None:
    print(f"[{PREFIX}] {line}")


def local_parts(session_obj: CourseSession) -> tuple[date, int, str, str]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return start.date(), start.date().weekday(), start.strftime("%H:%M"), end.strftime("%H:%M")


def expected_dates_after(last_date: date, *, weekday: int, excluded: set[date]) -> list[date]:
    cursor = last_date + timedelta(days=1)
    cursor += timedelta(days=(weekday - cursor.weekday()) % 7)
    rows: list[date] = []
    while cursor <= EXPECTED_END:
        if cursor not in excluded:
            rows.append(cursor)
        cursor += timedelta(days=7)
    return rows


def main() -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is not None:
            p(f"quote={quote.quote_number}|status={quote.status}|total={quote.total_ttc}|blocks={len((quote.calendar_snapshot or {}).get('blocks') or [])}")
            for line in db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order.asc())):
                p(f"quote_line title={line.title}|activity={line.activity_id}|quantity={line.quantity}|amount_ttc={line.amount_ttc}|meta={line.meta}")

        location = db.scalar(select(Location).where(Location.code == "BAR_LE_DUC").limit(1))
        if location is None:
            p("location_not_found")
            return

        excluded: set[date] = set()
        setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
        rows = _json_list(json.loads(setting.value or "[]")) if setting else []
        for raw in rows:
            row = _json_object(raw)
            if not _is_true(row.get("is_active", True)):
                continue
            if not _calendar_row_applies_to_session(row, location_id=str(location.id), session_date=date(2027, 4, 12)):
                continue
            excluded |= _parse_iso_date_set(row.get("holiday_dates"))
            excluded |= _parse_iso_date_set(row.get("closure_dates"))
            excluded |= _expand_calendar_vacation_dates(row)
            p(
                f"calendar={row.get('name')}|holiday_count={len(_parse_iso_date_set(row.get('holiday_dates')))}|"
                f"closure_count={len(_parse_iso_date_set(row.get('closure_dates')))}|vacation_count={len(_expand_calendar_vacation_dates(row))}"
            )

        start_utc = datetime.combine(date(2026, 9, 1), time.min, tzinfo=ZoneInfo(location.timezone)).astimezone(timezone.utc)
        end_utc = datetime.combine(date(2027, 7, 1), time.min, tzinfo=ZoneInfo(location.timezone)).astimezone(timezone.utc)
        sessions = db.execute(
            select(CourseSession, CourseType)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(
                CourseSession.location_id == location.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc < end_utc,
            )
            .order_by(CourseType.name.asc(), CourseSession.start_at_utc.asc())
        ).all()

        by_group: dict[str, list[tuple[CourseSession, CourseType]]] = defaultdict(list)
        for session_obj, course in sessions:
            by_group[str(session_obj.recurrence_group_id or session_obj.id)].append((session_obj, course))

        p(f"location={location.id}|sessions_total={len(sessions)}|groups={len(by_group)}|expected_end={EXPECTED_END}")
        total_missing = 0
        for group_id, group_rows in sorted(by_group.items(), key=lambda item: min(local_parts(row[0])[0] for row in item[1])):
            first_session, course = group_rows[0]
            dates = [local_parts(row[0])[0] for row in group_rows]
            weekdays = sorted({local_parts(row[0])[1] for row in group_rows})
            times = sorted({f"{local_parts(row[0])[2]}-{local_parts(row[0])[3]}" for row in group_rows})
            if len(weekdays) != 1 or len(times) != 1:
                p(f"mixed_group={group_id}|course={course.name}|weekdays={weekdays}|times={times}|count={len(group_rows)}")
                continue
            missing = expected_dates_after(max(dates), weekday=weekdays[0], excluded=excluded)
            total_missing += len(missing)
            p(
                f"group={group_id}|course={course.name}|course_id={course.id}|weekday={weekdays[0]}|time={times[0]}|"
                f"count={len(group_rows)}|first={min(dates)}|last={max(dates)}|until={first_session.recurrence_until_date}|"
                f"missing_count={len(missing)}|missing={','.join(day.isoformat() for day in missing) or '-'}"
            )
        p(f"total_missing={total_missing}")


if __name__ == "__main__":
    main()
