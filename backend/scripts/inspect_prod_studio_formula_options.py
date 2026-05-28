from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
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

PREFIX = "PROD_BAR_LE_DUC_PLANNING_INSPECT"
QUOTE_NUMBER = "DV-20260523090618-2B4D"


def p(line: str) -> None:
    print(f"[{PREFIX}] {line}")


def local_parts(session_obj: CourseSession) -> tuple[date, int, str, str]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return start.date(), start.date().weekday(), start.strftime("%H:%M"), end.strftime("%H:%M")


def main() -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is not None:
            snapshot = quote.calendar_snapshot or {}
            p(
                f"quote={quote.quote_number}|status={quote.status}|document_status={quote.document_status}|"
                f"total={quote.total_ttc}|snapshot_sessions={len(snapshot.get('sessions') or [])}|blocks={len(snapshot.get('blocks') or [])}"
            )
            for idx, block in enumerate(snapshot.get("blocks") or [], start=1):
                if not isinstance(block, dict):
                    continue
                p(
                    f"quote_block#{idx}|activity={block.get('activity_label')}|location={block.get('location_label')}|"
                    f"activity_id={block.get('activity_id')}|location_id={block.get('location_id')}|series={block.get('series_key')}|"
                    f"start={block.get('start_date')}|end={block.get('end_date')}|time={block.get('start_time')}-{block.get('end_time')}|"
                    f"weekday={block.get('weekday')}|count={block.get('sessions_count')}|limit={block.get('planning_session_limit')}"
                )
            for line in db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.sort_order.asc())):
                p(
                    f"quote_line={line.id}|title={line.title}|activity={line.activity_id}|category={line.line_category}|"
                    f"type={line.line_type}|quantity={line.quantity}|unit_price_ttc={line.unit_price_ttc}|amount_ttc={line.amount_ttc}|meta={line.meta}"
                )

        locations = db.scalars(
            select(Location)
            .where(func.lower(Location.name).like("%bar%le%duc%"))
            .order_by(Location.name.asc())
        ).all()
        if not locations:
            p("location_not_found")
            return
        location = locations[0]
        p(f"location={location.id}|name={location.name}|code={location.code}|timezone={location.timezone}")

        setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
        rows = _json_list(json.loads(setting.value or "[]")) if setting else []
        for raw in rows:
            row = _json_object(raw)
            if not _is_true(row.get("is_active", True)):
                continue
            if not _calendar_row_applies_to_session(row, location_id=str(location.id), session_date=date(2027, 4, 10)):
                continue
            vacation_dates = sorted(_expand_calendar_vacation_dates(row))
            closures = sorted(_parse_iso_date_set(row.get("closure_dates")))
            holidays = sorted(_parse_iso_date_set(row.get("holiday_dates")))
            p(
                f"calendar name={row.get('name')}|school_year={row.get('school_year_label')}|"
                f"holiday_count={len(holidays)}|closure_count={len(closures)}|vacation_count={len(vacation_dates)}|"
                f"last_holiday={holidays[-1] if holidays else '-'}|last_closure={closures[-1] if closures else '-'}|"
                f"last_vacation={vacation_dates[-1] if vacation_dates else '-'}|vacation_periods={row.get('vacation_periods')}"
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
        p(f"sessions_total={len(sessions)}")
        by_signature: dict[tuple[str, str, int, str, str], list[CourseSession]] = defaultdict(list)
        for session_obj, course in sessions:
            local_date, weekday, start_time, end_time = local_parts(session_obj)
            by_signature[(str(course.id), course.name, weekday, start_time, end_time)].append(session_obj)

        for (course_id, course_name, weekday, start_time, end_time), group in sorted(
            by_signature.items(),
            key=lambda item: (item[0][1], item[0][2], item[0][3], min(local_parts(row)[0] for row in item[1])),
        ):
            dates = [local_parts(row)[0] for row in group]
            groups = sorted({str(row.recurrence_group_id or row.id) for row in group})
            after_april_10 = [day for day in dates if day > date(2027, 4, 10)]
            p(
                f"series course={course_name}|course_id={course_id}|weekday={weekday}|time={start_time}-{end_time}|"
                f"count={len(group)}|first={min(dates)}|last={max(dates)}|after_2027_04_10={len(after_april_10)}|"
                f"groups={','.join(groups)}|dates={','.join(day.isoformat() for day in dates)}"
            )


if __name__ == "__main__":
    main()
