from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import (
    _execute_quote_followup_transformation,
    _quote_transformation_execution,
)
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import User


SCRIPT = "PROD_TRANSFORM_ADELINE_KRAWIEC_20260903"
QUOTE_NUMBER = "DV-20260817062547-307B"
QUOTE_ID = UUID("affba511-4f7c-421c-a74e-2e3dce12474a")
STUDENT_ID = UUID("5c7182af-574b-4b15-853c-f423dc016501")
RECURRENCE_GROUP_ID = UUID("a0001c2c-a42c-4fd7-ac79-d41641c6eb9c")
ADMIN_EMAIL = "admin@piano-academie.com"
EXPECTED_TOTAL = Decimal("803.00")
EXPECTED_BOOKINGS = 34


def _series_sessions(db) -> list[CourseSession]:
    return list(
        db.scalars(
            select(CourseSession)
            .where(CourseSession.recurrence_group_id == RECURRENCE_GROUP_ID)
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
    )


def _validate_before(db) -> tuple[Quote, QuoteAcceptanceFollowup, User]:
    quote = db.scalar(select(Quote).where(Quote.id == QUOTE_ID).with_for_update())
    if quote is None or quote.quote_number != QUOTE_NUMBER or quote.status != "approved":
        raise SystemExit(f"[{SCRIPT}] quote_guard_failed")
    if Decimal(quote.total_ttc or 0) != EXPECTED_TOTAL:
        raise SystemExit(f"[{SCRIPT}] quote_total_guard_failed:{quote.total_ttc}")
    followup = db.scalar(
        select(QuoteAcceptanceFollowup)
        .where(QuoteAcceptanceFollowup.quote_id == quote.id)
        .with_for_update()
    )
    if followup is None or followup.status != "partially_configured":
        raise SystemExit(f"[{SCRIPT}] followup_guard_failed:{getattr(followup, 'status', None)}")
    if followup.target_client_id != STUDENT_ID:
        raise SystemExit(f"[{SCRIPT}] target_guard_failed:{followup.target_client_id}")
    if str(_quote_transformation_execution(followup).get("status") or "").lower() == "executed":
        raise SystemExit(f"[{SCRIPT}] already_executed")
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL, User.is_active.is_(True)))
    if admin is None:
        raise SystemExit(f"[{SCRIPT}] admin_guard_failed")

    sessions = _series_sessions(db)
    completed = [row for row in sessions if row.status == SessionStatus.COMPLETED]
    scheduled = [row for row in sessions if row.status == SessionStatus.SCHEDULED]
    if len(completed) != 1 or len(scheduled) != 33 or len(sessions) != EXPECTED_BOOKINGS:
        raise SystemExit(
            f"[{SCRIPT}] series_guard_failed:completed={len(completed)}:scheduled={len(scheduled)}:total={len(sessions)}"
        )
    if completed[0].start_at_utc.date() != date(2026, 9, 2):
        raise SystemExit(f"[{SCRIPT}] completed_date_guard_failed:{completed[0].start_at_utc}")
    existing = list(
        db.scalars(
            select(Booking)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == STUDENT_ID,
                CourseSession.recurrence_group_id == RECURRENCE_GROUP_ID,
            )
        ).all()
    )
    if existing:
        raise SystemExit(f"[{SCRIPT}] existing_bookings_guard_failed:{len(existing)}")
    return quote, followup, admin


def _validate_after(db, execution: dict[str, object]) -> dict[str, object]:
    raw_ids = execution.get("created_booking_ids") or []
    booking_ids = [UUID(str(value)) for value in raw_ids]
    if len(booking_ids) != EXPECTED_BOOKINGS:
        raise SystemExit(f"[{SCRIPT}] booking_count_guard_failed:{len(booking_ids)}")
    bookings = list(
        db.scalars(select(Booking).where(Booking.id.in_(booking_ids))).all()
    )
    attended = [row for row in bookings if row.status == BookingStatus.ATTENDED]
    booked = [row for row in bookings if row.status == BookingStatus.BOOKED]
    if len(attended) != 1 or len(booked) != 33:
        raise SystemExit(f"[{SCRIPT}] booking_status_guard_failed:attended={len(attended)}:booked={len(booked)}")
    attended_session = db.get(CourseSession, attended[0].session_id)
    if attended_session is None or attended_session.start_at_utc.date() != date(2026, 9, 2):
        raise SystemExit(f"[{SCRIPT}] attended_session_guard_failed")
    sessions = _series_sessions(db)
    if len(sessions) != EXPECTED_BOOKINGS:
        raise SystemExit(f"[{SCRIPT}] duplicate_session_guard_failed:{len(sessions)}")
    return {
        "status": execution.get("status"),
        "student_client_id": execution.get("student_client_id"),
        "subscription_id": execution.get("subscription_id"),
        "booking_count": len(bookings),
        "attended_booking_count": len(attended),
        "future_booking_count": len(booked),
        "transaction_count": len(execution.get("created_transaction_ids") or []),
        "invoice_count": len(execution.get("created_invoice_note_ids") or []),
        "annual_invoice_skipped_reason": execution.get("annual_invoice_skipped_reason"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely transform Adeline Krawiec's approved quote.")
    parser.add_argument("--apply", action="store_true", help="Commit the validated transformation.")
    args = parser.parse_args()
    with SessionLocal() as db:
        quote, followup, admin = _validate_before(db)
        execution = _execute_quote_followup_transformation(
            db,
            quote=quote,
            followup=followup,
            current_user=admin,
        )
        result = _validate_after(db, execution)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"script": SCRIPT, "mode": "apply" if args.apply else "dry-run", **result}, indent=2))


if __name__ == "__main__":
    main()
