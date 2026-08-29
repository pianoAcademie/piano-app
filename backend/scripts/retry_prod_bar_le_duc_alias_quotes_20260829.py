from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import (
    _calendar_snapshot_with_line_recommendation_keys,
    _execute_quote_followup_transformation,
    _expected_activity_dates_from_snapshot,
    _json_object,
    _quote_line_schedule_key,
    _quote_transformation_execution,
    _quote_transformation_payload,
)
from app.db.session import SessionLocal
from app.models.catalog import CourseSession
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import User


SCRIPT = "PROD_BAR_LE_DUC_ALIAS_QUOTES_RETRY_20260829"
ADMIN_EMAIL = "admin@piano-academie.com"
QUOTE_NUMBERS = (
    "DV-20260826084730-847A",
    "DV-20260826084204-6BB5",
)
EXPECTED_TOTAL = Decimal("861.00")
EXPECTED_PIANO_QUANTITY = 33
EXPECTED_ERROR_FRAGMENT = "le planning valide du devis contient 0 creneau(x)"


def _validate_quote(db, quote_number: str) -> tuple[Quote, QuoteAcceptanceFollowup, dict[str, object]]:
    quote = db.scalar(select(Quote).where(Quote.quote_number == quote_number).with_for_update())
    if quote is None or quote.status != "approved" or Decimal(quote.total_ttc or 0) != EXPECTED_TOTAL:
        raise SystemExit(f"[{SCRIPT}] quote_guard_failed:{quote_number}")
    followup = db.scalar(
        select(QuoteAcceptanceFollowup)
        .where(QuoteAcceptanceFollowup.quote_id == quote.id)
        .with_for_update()
    )
    if followup is None or followup.status != "partially_configured":
        raise SystemExit(f"[{SCRIPT}] followup_guard_failed:{quote_number}")
    execution = _quote_transformation_execution(followup)
    if (
        str(execution.get("status") or "").lower() != "failed"
        or EXPECTED_ERROR_FRAGMENT not in str(execution.get("error_message") or "")
    ):
        raise SystemExit(f"[{SCRIPT}] execution_guard_failed:{quote_number}:{execution}")

    lines = list(
        db.scalars(
            select(QuoteLine)
            .where(QuoteLine.quote_id == quote.id)
            .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
        ).all()
    )
    piano_lines = [
        line
        for line in lines
        if line.line_category == "service"
        and line.line_type == "item"
        and line.pricing_unit == "session"
        and int(Decimal(line.quantity or 0)) == EXPECTED_PIANO_QUANTITY
    ]
    if len(piano_lines) != 1 or piano_lines[0].activity_id is None:
        raise SystemExit(f"[{SCRIPT}] piano_line_guard_failed:{quote_number}")
    piano_line = piano_lines[0]
    schedule_key = _quote_line_schedule_key(piano_line)
    if not schedule_key:
        raise SystemExit(f"[{SCRIPT}] schedule_key_guard_failed:{quote_number}")
    transformation = _quote_transformation_payload(followup)
    assignments = _json_object(_json_object(transformation.get("scheduleResolution")).get("assignedSessionByActivityId"))
    selected_session_id_raw = str(assignments.get(schedule_key) or "").strip()
    try:
        selected_session_id = UUID(selected_session_id_raw)
    except ValueError as exc:
        raise SystemExit(f"[{SCRIPT}] selected_session_id_guard_failed:{quote_number}:{selected_session_id_raw}") from exc
    selected_session = db.get(CourseSession, selected_session_id)
    if selected_session is None:
        raise SystemExit(f"[{SCRIPT}] selected_session_guard_failed:{quote_number}:{selected_session_id}")

    snapshot = _calendar_snapshot_with_line_recommendation_keys(None, _json_object(quote.calendar_snapshot), lines=lines)
    expected_dates = _expected_activity_dates_from_snapshot(
        quote,
        activity_id=piano_line.activity_id,
        schedule_key=schedule_key,
        calendar_snapshot=snapshot,
        expected_series_key=str(selected_session.recurrence_group_id or selected_session.id),
        expected_weekday=selected_session.start_at_utc.astimezone(ZoneInfo(selected_session.timezone)).weekday(),
    )
    if len(expected_dates) != EXPECTED_PIANO_QUANTITY:
        raise SystemExit(f"[{SCRIPT}] expected_dates_guard_failed:{quote_number}:{len(expected_dates)}")
    return quote, followup, {
        "quote_number": quote_number,
        "piano_sessions": len(expected_dates),
        "first_date": expected_dates[0].isoformat(),
        "last_date": expected_dates[-1].isoformat(),
        "selected_session_id": str(selected_session.id),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry the two Bar-le-Duc quote transformations after alias matching repair.")
    parser.add_argument("--apply", action="store_true", help="Execute and commit both transformations.")
    args = parser.parse_args()
    results: list[dict[str, object]] = []

    for quote_number in QUOTE_NUMBERS:
        with SessionLocal() as db:
            quote, followup, result = _validate_quote(db, quote_number)
            if not args.apply:
                db.rollback()
                results.append(result)
                continue
            admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL, User.is_active.is_(True)))
            if admin is None:
                raise SystemExit(f"[{SCRIPT}] admin_guard_failed")
            execution = _execute_quote_followup_transformation(
                db,
                quote=quote,
                followup=followup,
                current_user=admin,
            )
            db.commit()
            result.update(
                {
                    "status": execution.get("status"),
                    "student_client_id": execution.get("student_client_id"),
                    "booking_count": len(execution.get("created_booking_ids") or []),
                    "transaction_count": len(execution.get("created_transaction_ids") or []),
                }
            )
            results.append(result)

    print(json.dumps({"script": SCRIPT, "mode": "apply" if args.apply else "dry-run", "quotes": results}, indent=2))


if __name__ == "__main__":
    main()
