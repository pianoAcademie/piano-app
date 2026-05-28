from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.quote import Quote, QuoteLine

PREFIX = "PROD_ONLINE_CHILD_PIANO_SERIES_INSPECT"
COURSE_NAME = "Cours de piano collectif en ligne - enfants (1h)"
QUOTE_NUMBER = "DV-20260521044742-9E89"
START = date(2026, 9, 1)
END = date(2027, 6, 30)


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
        if quote is not None:
            p(
                f"quote={quote.quote_number}|status={quote.status}|document_status={quote.document_status}|"
                f"calendar_snapshot_sessions={len((quote.calendar_snapshot or {}).get('sessions') or [])}|"
                f"blocks={len((quote.calendar_snapshot or {}).get('blocks') or [])}"
            )
            for idx, block in enumerate((quote.calendar_snapshot or {}).get("blocks") or [], start=1):
                if not isinstance(block, dict):
                    continue
                p(
                    f"quote_block#{idx}|activity={block.get('activity_label')}|series_key={block.get('series_key')}|"
                    f"start={block.get('start_date')}|end={block.get('end_date')}|"
                    f"time={block.get('start_time')}-{block.get('end_time')}|count={block.get('sessions_count')}|"
                    f"limit={block.get('planning_session_limit')}"
                )
            lines = db.scalars(
                select(QuoteLine)
                .where(QuoteLine.quote_id == quote.id)
                .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
            ).all()
            for line in lines:
                p(
                    f"quote_line id={line.id}|title={line.title}|activity={line.activity_id}|"
                    f"category={line.line_category}|type={line.line_type}|quantity={line.quantity}|unit={line.pricing_unit}|"
                    f"unit_ht={line.unit_price_ht}|amount_ht={line.amount_ht}|amount_ttc={line.amount_ttc}|meta={line.meta}"
                )

        course = db.scalar(select(CourseType).where(CourseType.name == COURSE_NAME).limit(1))
        location = db.scalar(select(Location).where(Location.code == "ONLINE").limit(1))
        p(f"course={course.id if course else '-'}|location={location.id if location else '-'}")
        if course is None or location is None:
            return

        start_utc = datetime.combine(START, datetime.min.time(), tzinfo=ZoneInfo("Europe/Paris")).astimezone(timezone.utc)
        end_utc = datetime.combine(END, datetime.max.time(), tzinfo=ZoneInfo("Europe/Paris")).astimezone(timezone.utc)
        rows = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.course_type_id == course.id,
                CourseSession.location_id == location.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
                CourseSession.start_at_utc <= end_utc,
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        by_signature: dict[tuple[int, str, str], list[CourseSession]] = defaultdict(list)
        by_group: dict[str, list[CourseSession]] = defaultdict(list)
        for session_obj in rows:
            local_date, start_time, end_time = local_parts(session_obj)
            by_signature[(local_date.weekday(), start_time, end_time)].append(session_obj)
            by_group[str(session_obj.recurrence_group_id or session_obj.id)].append(session_obj)

        p(f"sessions_total={len(rows)}|signature_groups={len(by_signature)}|recurrence_groups={len(by_group)}")
        for (weekday, start_time, end_time), sessions in sorted(by_signature.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])):
            dates = [local_parts(session_obj)[0] for session_obj in sessions]
            if weekday == 1 and start_time == "18:00" and end_time == "19:00":
                p(
                    f"target_signature weekday={weekday}|time={start_time}-{end_time}|count={len(sessions)}|"
                    f"first={min(dates)}|last={max(dates)}|"
                    f"dates={','.join(day.isoformat() for day in dates)}"
                )
                groups = sorted({str(session_obj.recurrence_group_id or session_obj.id) for session_obj in sessions})
                p(f"target_signature_groups={','.join(groups)}")
        for group_id, sessions in sorted(by_group.items(), key=lambda item: min(local_parts(s)[0] for s in item[1])):
            target_sessions = [s for s in sessions if local_parts(s)[1:] == ("18:00", "19:00") and local_parts(s)[0].weekday() == 1]
            if not target_sessions:
                continue
            dates = [local_parts(session_obj)[0] for session_obj in target_sessions]
            untils = sorted({str(session_obj.recurrence_until_date or "-") for session_obj in target_sessions})
            ids = [str(session_obj.id) for session_obj in target_sessions]
            p(
                f"target_group={group_id}|count={len(target_sessions)}|first={min(dates)}|last={max(dates)}|"
                f"untils={','.join(untils)}|ids={','.join(ids)}|dates={','.join(day.isoformat() for day in dates)}"
            )


if __name__ == "__main__":
    main()
