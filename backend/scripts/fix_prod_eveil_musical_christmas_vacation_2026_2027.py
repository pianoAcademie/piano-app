from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.ops import AppSetting
from app.services.quotes.quote_documents import (
    QUOTE_SCHOOL_CALENDARS_SETTING_KEY,
    _calendar_row_applies_to_session,
    _expand_calendar_vacation_dates,
    _is_true,
    _json_list,
    _json_object,
    _parse_iso_date_set,
)

SCRIPT_PREFIX = "PROD_REPAIR_BAR_LE_DUC_MISSING_SESSIONS"
LOCATION_CODE = "BAR_LE_DUC"
EXPECTED_END = date(2027, 6, 19)


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _local_parts(session_obj: CourseSession) -> tuple[date, int, time, time]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return start.date(), start.date().weekday(), start.time().replace(tzinfo=None), end.time().replace(tzinfo=None)


def _excluded_dates_for_location(db, *, location_id: str) -> set[date]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
    rows = _json_list(json.loads(setting.value or "[]")) if setting else []
    excluded: set[date] = set()
    for raw in rows:
        row = _json_object(raw)
        if not _is_true(row.get("is_active", True)):
            continue
        if not _calendar_row_applies_to_session(row, location_id=location_id, session_date=date(2027, 4, 12)):
            continue
        excluded |= _parse_iso_date_set(row.get("holiday_dates"))
        excluded |= _parse_iso_date_set(row.get("closure_dates"))
        excluded |= _expand_calendar_vacation_dates(row)
    return excluded


def _expected_missing_dates(last_date: date, *, weekday: int, excluded: set[date]) -> list[date]:
    cursor = last_date + timedelta(days=1)
    cursor += timedelta(days=(weekday - cursor.weekday()) % 7)
    rows: list[date] = []
    while cursor <= EXPECTED_END:
        if cursor not in excluded:
            rows.append(cursor)
        cursor += timedelta(days=7)
    return rows


def _copy_session(template: CourseSession, *, target_date: date) -> CourseSession:
    local_date, _weekday, start_time, end_time = _local_parts(template)
    del local_date
    tz = ZoneInfo(template.timezone or "Europe/Paris")
    start_utc = datetime.combine(target_date, start_time, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(target_date, end_time, tzinfo=tz).astimezone(timezone.utc)
    deadline_delta = template.start_at_utc - template.auto_cancel_deadline_utc
    if deadline_delta.total_seconds() <= 0:
        deadline_delta = template.end_at_utc - template.start_at_utc
    return CourseSession(
        course_type_id=template.course_type_id,
        billing_entity_snapshot=template.billing_entity_snapshot,
        snapshot_seller_legal_entity_id=template.snapshot_seller_legal_entity_id,
        snapshot_payor_legal_entity_id=template.snapshot_payor_legal_entity_id,
        location_id=template.location_id,
        professor_id=template.professor_id,
        substitute_teacher_id=template.substitute_teacher_id,
        substitute_set_at=template.substitute_set_at,
        substitute_set_by=template.substitute_set_by,
        substitute_note=template.substitute_note,
        title=template.title,
        description=template.description,
        private_description=template.private_description,
        group_note=template.group_note,
        professor_reminder_note=template.professor_reminder_note,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        is_all_day=template.is_all_day,
        capacity_max=template.capacity_max,
        status=SessionStatus.SCHEDULED,
        auto_cancel_deadline_utc=start_utc - deadline_delta,
        cancel_reason=None,
        zoom_link=template.zoom_link,
        is_private=template.is_private,
        allow_online_booking=template.allow_online_booking,
        visibility_scope=template.visibility_scope,
        booking_scope=template.booking_scope,
        external_booking_price_ttc=template.external_booking_price_ttc,
        show_external_remaining_seats=template.show_external_remaining_seats,
        timezone=template.timezone,
        recurrence_group_id=template.recurrence_group_id,
        recurrence_rule=template.recurrence_rule,
        recurrence_until_date=template.recurrence_until_date,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create missing Bar-le-Duc sessions.")
    args = parser.parse_args()

    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.code == LOCATION_CODE).limit(1))
        if location is None:
            raise RuntimeError(f"Location not found: {LOCATION_CODE}")
        excluded = _excluded_dates_for_location(db, location_id=str(location.id))

        rows = db.execute(
            select(CourseSession, CourseType)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(
                CourseSession.location_id == location.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.recurrence_group_id.is_not(None),
                CourseSession.start_at_utc >= datetime(2026, 9, 1, tzinfo=timezone.utc),
                CourseSession.start_at_utc < datetime(2027, 7, 1, tzinfo=timezone.utc),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        by_group: dict[str, list[tuple[CourseSession, CourseType]]] = defaultdict(list)
        for session_obj, course in rows:
            name = str(course.name or "").casefold()
            if "bar-le-duc" not in name or "vacances" in name:
                continue
            by_group[str(session_obj.recurrence_group_id)].append((session_obj, course))

        created_dates: list[str] = []
        already_present = 0
        planned_creates = 0

        for group_id, group_rows in sorted(by_group.items()):
            group_sessions = [item[0] for item in group_rows]
            course = group_rows[0][1]
            local_rows = [(_local_parts(session_obj), session_obj) for session_obj in group_sessions]
            weekdays = sorted({parts[1] for parts, _session_obj in local_rows})
            starts = sorted({parts[2] for parts, _session_obj in local_rows})
            ends = sorted({parts[3] for parts, _session_obj in local_rows})
            if len(weekdays) != 1 or len(starts) != 1 or len(ends) != 1:
                _print(f"skip_mixed_group={group_id}|course={course.name}")
                continue
            last_date = max(parts[0] for parts, _session_obj in local_rows)
            missing_dates = _expected_missing_dates(last_date, weekday=weekdays[0], excluded=excluded)
            template = max(group_sessions, key=lambda session_obj: _local_parts(session_obj)[0])
            _print(
                f"group={group_id}|course={course.name}|weekday={weekdays[0]}|"
                f"time={starts[0].strftime('%H:%M')}-{ends[0].strftime('%H:%M')}|"
                f"last={last_date.isoformat()}|missing={','.join(day.isoformat() for day in missing_dates) or '-'}"
            )
            for target_date in missing_dates:
                tz = ZoneInfo(template.timezone or "Europe/Paris")
                start_utc = datetime.combine(target_date, starts[0], tzinfo=tz).astimezone(timezone.utc)
                end_utc = datetime.combine(target_date, ends[0], tzinfo=tz).astimezone(timezone.utc)
                existing = db.scalar(
                    select(CourseSession.id)
                    .where(
                        CourseSession.course_type_id == template.course_type_id,
                        CourseSession.location_id == template.location_id,
                        CourseSession.status == SessionStatus.SCHEDULED,
                        CourseSession.start_at_utc == start_utc,
                        CourseSession.end_at_utc == end_utc,
                    )
                    .limit(1)
                )
                if existing is not None:
                    already_present += 1
                    continue
                planned_creates += 1
                if args.apply:
                    session_obj = _copy_session(template, target_date=target_date)
                    db.add(session_obj)
                    db.flush()
                    created_dates.append(target_date.isoformat())

        if args.apply:
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|groups={len(by_group)}|planned_creates={planned_creates}|"
            f"created={len(created_dates)}|already_present={already_present}|"
            f"created_dates={','.join(created_dates) or '-'}"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Bar-le-Duc missing sessions repair::{summary}")


if __name__ == "__main__":
    main()
