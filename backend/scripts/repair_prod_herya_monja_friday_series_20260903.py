"""Repair Herya Monja's Friday quote snapshot from the authoritative live series.

Dry-run by default. The script is deliberately single-purpose and guarded; it
does not price, send, approve or transform the quote.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, SessionStatus
from app.models.quote import Quote, QuoteEvent, QuoteLine

QUOTE_ID = UUID("70aa261d-81e2-4fe4-85b7-56b0a9253bc9")
QUOTE_NUMBER = "DV-20260903034708-2705"
ACTIVITY_ID = UUID("43c77f63-0ac4-40ca-8e49-fafa4fba3c6e")
SERIES_ID = UUID("7510fcca-b3a9-4245-a77a-f76536a64aab")
EVENT_TYPE = "draft_quote_planning_series_repaired"
EXPECTED_OLD_DATES = {
    "2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25", "2026-10-02",
    "2026-10-09", "2026-10-16", "2026-11-06", "2026-11-13", "2026-11-20",
    "2026-11-27", "2026-12-04", "2026-12-11", "2026-12-18", "2027-01-08",
    "2027-01-15", "2027-01-22", "2027-01-29", "2027-02-05", "2027-02-26",
    "2027-03-05", "2027-03-12", "2027-03-19", "2027-03-26", "2027-04-02",
    "2027-04-23", "2027-05-28", "2027-06-04", "2027-06-11", "2027-06-18",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_parts(session: CourseSession) -> tuple[str, str, str, int]:
    zone = ZoneInfo(session.timezone or "Europe/Paris")
    start = session.start_at_utc.astimezone(zone)
    end = session.end_at_utc.astimezone(zone)
    return start.date().isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), start.weekday()


def run(*, apply: bool) -> dict:
    with SessionLocal() as db:
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        statement = select(Quote).where(Quote.id == QUOTE_ID)
        quote = db.scalar(statement.with_for_update() if apply else statement)
        require(quote is not None and quote.quote_number == QUOTE_NUMBER, "Quote not found")
        require(str(quote.status) == "created", "Quote is no longer an editable draft")

        lines = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id == QUOTE_ID)).all())
        activity_lines = [line for line in lines if line.activity_id == ACTIVITY_ID]
        require(len(activity_lines) == 1, "Expected exactly one Friday activity line")
        require(activity_lines[0].quantity == Decimal("32"), "The commercial quantity is no longer 32")

        snapshot = deepcopy(quote.calendar_snapshot or {})
        rows = list(snapshot.get("sessions") or [])
        blocks = list(snapshot.get("blocks") or [])
        piano_rows = [row for row in rows if row.get("activity_id") == str(ACTIVITY_ID)]
        piano_blocks = [row for row in blocks if row.get("activity_id") == str(ACTIVITY_ID)]
        if len(piano_rows) == 32 and len(piano_blocks) == 1 and piano_blocks[0].get("series_key") == str(SERIES_ID):
            require(db.scalar(select(QuoteEvent.id).where(QuoteEvent.quote_id == QUOTE_ID, QuoteEvent.event_type == EVENT_TYPE)) is not None, "Repair is not audited")
            return {"mode": "already_repaired", "quote_number": QUOTE_NUMBER, "sessions": 32}
        require(len(piano_rows) == 30 and len(piano_blocks) == 1, "Unexpected existing planning shape")
        require({str(row.get("date")) for row in piano_rows} == EXPECTED_OLD_DATES, "Existing planning dates changed")

        sessions = list(db.scalars(select(CourseSession).where(CourseSession.recurrence_group_id == SERIES_ID)).all())
        scheduled = []
        for session in sessions:
            if session.status != SessionStatus.SCHEDULED or session.course_type_id != ACTIVITY_ID:
                continue
            date_value, start_time, end_time, weekday = local_parts(session)
            if weekday == 4 and start_time == "19:00" and end_time == "20:00" and date_value <= "2027-06-18":
                scheduled.append((date_value, session))
        scheduled.sort(key=lambda item: item[0])
        dates = [item[0] for item in scheduled]
        require(len(dates) == 32 and len(set(dates)) == 32, "Authoritative series does not contain 32 unique scheduled lessons")
        require(dates[0] == "2026-09-11" and dates[-1] == "2027-06-18", "Unexpected authoritative period")
        require("2026-09-04" not in dates, "Cancelled first lesson leaked into the authoritative series")

        template = deepcopy(piano_rows[0])
        replacement_rows = []
        for date_value, session in scheduled:
            row = deepcopy(template)
            row.update({
                "session_id": str(session.id),
                "date": date_value,
                "start_time": "19:00",
                "end_time": "20:00",
                "duration_minutes": 60,
                "activity_id": str(ACTIVITY_ID),
                "activity_label": "Cours collectifs ado/adultes",
                "location_id": str(session.location_id) if session.location_id else None,
                "location_label": template.get("location_label") or "Rue de Richelieu",
                "modality": "ONSITE",
                "weekday": 4,
                "weekday_label": "Vendredi",
                "series_key": str(SERIES_ID),
            })
            replacement_rows.append(row)

        other_rows = [deepcopy(row) for row in rows if row.get("activity_id") != str(ACTIVITY_ID)]
        after = deepcopy(snapshot)
        after["sessions"] = sorted(other_rows + replacement_rows, key=lambda row: (str(row.get("date")), str(row.get("start_time"))))
        after["sessions_count"] = len(after["sessions"])
        after["generated_at"] = datetime.now(timezone.utc).isoformat()
        repaired_block = deepcopy(piano_blocks[0])
        repaired_block.update({
            "series_key": str(SERIES_ID),
            "start_date": dates[0],
            "end_date": dates[-1],
            "sessions_count": 32,
            "planning_session_limit": None,
            "custom_period": False,
            "weekday": 4,
            "start_time": "19:00",
            "end_time": "20:00",
        })
        after["blocks"] = [repaired_block if row.get("activity_id") == str(ACTIVITY_ID) else deepcopy(row) for row in blocks]
        require(len(after["sessions"]) == len(other_rows) + 32, "Unrelated snapshot rows changed")

        result = {
            "mode": "apply" if apply else "dry_run",
            "quote_number": QUOTE_NUMBER,
            "old_sessions": 30,
            "new_sessions": 32,
            "first_date": dates[0],
            "last_date": dates[-1],
            "removed_cancelled_date": "2026-09-04",
            "restored_dates": sorted(set(dates) - EXPECTED_OLD_DATES),
            "emails_sent": 0,
        }
        if apply:
            event = QuoteEvent(
                quote_id=QUOTE_ID,
                event_type=EVENT_TYPE,
                actor_type="system",
                payload={
                    "script": Path(__file__).name,
                    "reason": "User-authorized repair: competing recurrence groups were stitched together",
                    "before_calendar": snapshot,
                    "authoritative_series_id": str(SERIES_ID),
                    "old_sessions": 30,
                    "new_sessions": 32,
                    "emails_sent": 0,
                },
            )
            quote.calendar_snapshot = after
            quote.updated_at = datetime.now(timezone.utc)
            db.add_all([quote, event])
            db.flush()
            result["audit_event_id"] = str(event.id)
            db.commit()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(run(apply=parser.parse_args().apply), indent=2, ensure_ascii=False))
