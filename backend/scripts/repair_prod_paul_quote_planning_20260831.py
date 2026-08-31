"""Rebind one approved quote to its replacement series, without enrolling anyone.

Dry-run by default. Only internal series/session references are changed; the
approved dates, commercial lines and frozen document are left untouched. The
previous calendar and integration state are retained in a QuoteEvent for undo.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.api.routes.quotes import (
    _expected_activity_dates_from_snapshot,
    _quote_transformation_execution,
    _quote_transformation_payload,
    _set_quote_integration_meta,
    _set_quote_transformation_execution,
    _validated_quote_transform_expected_dates,
)
from app.db.session import SessionLocal
from app.models.catalog import CourseSession, SessionStatus
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteEvent, QuoteLine

QUOTE_ID = UUID("8e58dfdc-f0b1-43c7-92e2-7e867a6e35ad")
QUOTE_NUMBER = "DV-20260829162719-AD9B"
OLD_SERIES = UUID("ea0dd206-c42d-4014-b32c-0d7384c8a99e")
NEW_SERIES = UUID("6db69545-1a1d-4e01-acf9-c25ebcffa54c")
SELECTED_SESSION = UUID("fdfd947e-7608-422f-8b6d-3bd907767d3a")
ACTIVITY = UUID("43c77f63-0ac4-40ca-8e49-fafa4fba3c6e")
LOCATION = UUID("b66fe0d7-2990-4a58-b2f0-360911c611ee")
EVENT_TYPE = "approved_planning_references_repaired"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def repair_calendar(snapshot: dict, live_sessions: list) -> dict:
    """Strict one-to-one matching; never add dates from the 42-date live series."""
    before = deepcopy(snapshot)
    rows = before.get("sessions", [])
    blocks = before.get("blocks", [])
    require(len(rows) == 32 and len(blocks) == 1, "Expected 32 dates and one block")
    dates = [row["date"] for row in rows]
    require(len(set(dates)) == 32, "Duplicate approved dates")
    require(min(dates) == "2026-09-09" and max(dates) == "2027-06-16", "Unexpected approved period")
    for row in rows + blocks:
        require(row.get("series_key") == str(OLD_SERIES), "Unexpected source series")
        require(row.get("activity_id") == str(ACTIVITY), "Unexpected activity")
        require(row.get("location_id") == str(LOCATION), "Unexpected location")
        require((row.get("start_time"), row.get("end_time")) == ("19:00", "20:00"), "Unexpected time")
        require(row.get("weekday") == 2, "Unexpected weekday")

    by_date: dict[str, list] = {}
    for session in live_sessions:
        if session.status != SessionStatus.SCHEDULED or session.recurrence_group_id != NEW_SERIES:
            continue
        if session.course_type_id != ACTIVITY or session.location_id != LOCATION:
            continue
        zone = ZoneInfo(session.timezone)
        start, end = session.start_at_utc.astimezone(zone), session.end_at_utc.astimezone(zone)
        if start.weekday() != 2 or (start.strftime("%H:%M"), end.strftime("%H:%M")) != ("19:00", "20:00"):
            continue
        if start.date() != end.date():
            continue
        by_date.setdefault(start.date().isoformat(), []).append(session)

    after = deepcopy(before)
    for row in after["sessions"]:
        matches = by_date.get(row["date"], [])
        require(len(matches) == 1, f"Missing or ambiguous replacement: {row['date']}")
        row["series_key"] = str(NEW_SERIES)
        row["session_id"] = str(matches[0].id)
    after["blocks"][0]["series_key"] = str(NEW_SERIES)
    # Prove that nothing but linkage changed (including exclusions and dates).
    restored = deepcopy(after)
    for old_row, restored_row in zip(before["sessions"], restored["sessions"]):
        restored_row["series_key"] = old_row["series_key"]
        restored_row["session_id"] = old_row["session_id"]
    restored["blocks"][0]["series_key"] = str(OLD_SERIES)
    require(restored == before, "Approved calendar content changed")
    return after


def run(*, apply: bool) -> dict:
    with SessionLocal() as db:
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        statement = select(Quote).where(Quote.id == QUOTE_ID)
        quote = db.scalar(statement.with_for_update() if apply else statement)
        require(quote is not None and quote.quote_number == QUOTE_NUMBER, "Quote not found")
        require(quote.status == "approved" and quote.document_status == "frozen", "Quote is no longer approved/frozen")
        require(quote.total_ttc == Decimal("869.00"), "Quote amount changed")
        statement = select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == QUOTE_ID)
        followup = db.scalar(statement.with_for_update() if apply else statement)
        require(followup is not None and followup.status == "partially_configured", "Followup changed")
        execution = _quote_transformation_execution(followup)
        require(execution.get("status") != "executed", "Enrollment already finalized")
        transformation = _quote_transformation_payload(followup)
        assignments = transformation.get("scheduleResolution", {}).get("assignedSessionByActivityId", {})
        require(assignments == {str(ACTIVITY): str(SELECTED_SESSION)}, "Selected planning changed")
        if all(row.get("series_key") == str(NEW_SERIES) for row in quote.calendar_snapshot.get("sessions", [])):
            require(db.scalar(select(QuoteEvent.id).where(QuoteEvent.quote_id == QUOTE_ID, QuoteEvent.event_type == EVENT_TYPE)) is not None, "Untracked calendar change")
            return {"mode": "already_repaired", "quote_number": QUOTE_NUMBER}
        require(execution.get("status") == "failed" and "prevoit 32" in str(execution.get("error_message")), "Unexpected previous failure")
        lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == QUOTE_ID)).all()
        service_lines = [line for line in lines if line.activity_id is not None]
        require(len(service_lines) == 1 and service_lines[0].activity_id == ACTIVITY and service_lines[0].quantity == Decimal("32"), "Billed sessions changed")
        old_ids = [UUID(row["session_id"]) for row in quote.calendar_snapshot["sessions"]]
        require(db.scalar(select(CourseSession.id).where(CourseSession.id.in_(old_ids)).limit(1)) is None, "Old sessions still exist")
        require(db.scalar(select(CourseSession.id).where(CourseSession.recurrence_group_id == OLD_SERIES).limit(1)) is None, "Old series still exists")
        statement = select(CourseSession).where(CourseSession.recurrence_group_id == NEW_SERIES)
        live = list(db.scalars(statement.with_for_update() if apply else statement).all())
        after = repair_calendar(quote.calendar_snapshot, live)
        dates = _expected_activity_dates_from_snapshot(quote, activity_id=ACTIVITY, schedule_key=str(ACTIVITY), calendar_snapshot=after, expected_series_key=str(NEW_SERIES), expected_weekday=2)
        _validated_quote_transform_expected_dates(dates, session_limit=32)
        require(dates == sorted(date.fromisoformat(row["date"]) for row in quote.calendar_snapshot["sessions"]), "Validated dates changed")
        result = {"quote_number": QUOTE_NUMBER, "mode": "apply" if apply else "dry_run", "sessions": len(dates), "total_ttc": str(quote.total_ttc), "first_date": str(dates[0]), "last_date": str(dates[-1]), "enrollment_finalized": False}
        if apply:
            document_before = (quote.document_status, quote.document_snapshot_id, quote.document_hash)
            event = QuoteEvent(quote_id=QUOTE_ID, event_type=EVENT_TYPE, actor_type="system", payload={"script": Path(__file__).name, "reason": "User-authorized repair of obsolete planning references; no enrollment or email", "before_calendar": deepcopy(quote.calendar_snapshot), "before_followup_payload": deepcopy(followup.payload), "before_meta": deepcopy(quote.meta), "old_series_id": str(OLD_SERIES), "new_series_id": str(NEW_SERIES), "sessions": 32})
            quote.calendar_snapshot = after
            _set_quote_integration_meta(quote, integration_status="a_verifier", central_integration_status="a_verifier", integration_error_message=None, integration_error=None)
            _set_quote_transformation_execution(followup, {"status": "pending", "planning_repaired_at": datetime.now(timezone.utc).isoformat()})
            require(document_before == (quote.document_status, quote.document_snapshot_id, quote.document_hash), "Frozen document changed")
            db.add_all([quote, followup, event])
            db.flush()
            result["audit_event_id"] = str(event.id)
            db.commit()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(run(apply=parser.parse_args().apply), indent=2))
