from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

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

PREFIX = "PROD_ASSAS_ADULT_COLLECTIVE_SERIES_INSPECT"
QUOTE_NUMBER = "DV-20260528100238-F277"
TARGET_DATES = (date(2027, 3, 31), date(2027, 5, 19))


def p(line: str) -> None:
    print(f"[{PREFIX}] {line}")


def local_parts(session_obj: CourseSession) -> tuple[date, str, str]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return start.date(), start.strftime("%H:%M"), end.strftime("%H:%M")


def main() -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is None:
            p(f"quote_not_found={QUOTE_NUMBER}")
            return
        snapshot = quote.calendar_snapshot or {}
        p(
            f"quote={quote.quote_number}|status={quote.status}|document_status={quote.document_status}|"
            f"total={quote.total_ttc}|snapshot_sessions={len(snapshot.get('sessions') or [])}|blocks={len(snapshot.get('blocks') or [])}"
        )
        for idx, block in enumerate(snapshot.get("blocks") or [], start=1):
            if not isinstance(block, dict):
                continue
            p(
                f"block#{idx}|activity={block.get('activity_label')}|location={block.get('location_label')}|"
                f"series_key={block.get('series_key')}|start={block.get('start_date')}|end={block.get('end_date')}|"
                f"time={block.get('start_time')}-{block.get('end_time')}|weekday={block.get('weekday')}|"
                f"count={block.get('sessions_count')}|limit={block.get('planning_session_limit')}"
            )

        for line in db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order.asc())):
            p(
                f"line={line.id}|title={line.title}|activity={line.activity_id}|category={line.line_category}|"
                f"type={line.line_type}|quantity={line.quantity}|unit_price_ttc={line.unit_price_ttc}|amount_ttc={line.amount_ttc}|meta={line.meta}"
            )

        target_block = next(
            (
                block
                for block in snapshot.get("blocks") or []
                if isinstance(block, dict)
                and str(block.get("location_label") or "").lower().find("assas") >= 0
                and str(block.get("start_time") or "") == "19:00"
            ),
            None,
        )
        if not isinstance(target_block, dict):
            p("target_block_not_found")
            return

        course_id = str(target_block.get("activity_id") or "").strip()
        location_id = str(target_block.get("location_id") or "").strip()
        series_key = str(target_block.get("series_key") or "").strip()
        course = db.scalar(select(CourseType).where(CourseType.id == course_id).limit(1))
        location = db.scalar(select(Location).where(Location.id == location_id).limit(1))
        p(
            f"target course={course.id if course else '-'}|course_name={course.name if course else '-'}|"
            f"location={location.id if location else '-'}|location_name={location.name if location else '-'}|series={series_key}"
        )

        setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
        rows = _json_list(json.loads(setting.value or "[]")) if setting else []
        for target in TARGET_DATES:
            p(f"date={target.isoformat()}")
            blockers = 0
            for idx, raw in enumerate(rows, start=1):
                row = _json_object(raw)
                if not _is_true(row.get("is_active", True)):
                    continue
                applies = _calendar_row_applies_to_session(row, location_id=location_id, session_date=target)
                holidays = target in _parse_iso_date_set(row.get("holiday_dates"))
                closures = target in _parse_iso_date_set(row.get("closure_dates"))
                vacations = target in _expand_calendar_vacation_dates(row)
                if applies and (holidays or closures or vacations):
                    blockers += 1
                    p(
                        f"blocker idx={idx}|name={row.get('name')}|holiday={holidays}|closure={closures}|vacation={vacations}|"
                        f"holiday_dates={row.get('holiday_dates')}|closure_dates={row.get('closure_dates')}|vacation_periods={row.get('vacation_periods')}"
                    )
            if blockers == 0:
                p(f"no_calendar_blocker date={target.isoformat()}")

        tz = ZoneInfo((location.timezone if location else None) or "Europe/Paris")
        start_utc = datetime.combine(date(2026, 9, 1), time.min, tzinfo=tz).astimezone(timezone.utc)
        end_utc = datetime.combine(date(2027, 6, 30), time.max, tzinfo=tz).astimezone(timezone.utc)
        sessions = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.course_type_id == course.id,
                CourseSession.location_id == location.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc <= end_utc,
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all() if course is not None and location is not None else []

        by_group: dict[str, list[CourseSession]] = defaultdict(list)
        for session_obj in sessions:
            by_group[str(session_obj.recurrence_group_id or session_obj.id)].append(session_obj)
        p(f"sessions_total={len(sessions)}|groups={len(by_group)}")
        for group_id, group_sessions in sorted(by_group.items(), key=lambda item: min(local_parts(row)[0] for row in item[1])):
            target_rows = [
                row for row in group_sessions
                if local_parts(row)[0].weekday() == 2 and local_parts(row)[1:] == ("19:00", "20:00")
            ]
            if not target_rows:
                continue
            dates = [local_parts(row)[0] for row in target_rows]
            p(
                f"group={group_id}|count={len(target_rows)}|first={min(dates)}|last={max(dates)}|"
                f"untils={','.join(sorted({str(row.recurrence_until_date or '-') for row in target_rows}))}|"
                f"dates={','.join(day.isoformat() for day in dates)}"
            )


if __name__ == "__main__":
    main()
