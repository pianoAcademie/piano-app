from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.admin import BOOKING_STATUSES_ACTIVE
from app.api.routes.admin_clients import _parse_invoice_range_note_entry
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.notification_engine import DomainEvent
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import User, UserRole


SCHOOL_YEAR = "2026-2027"
SEASON_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 7, 1, tzinfo=timezone.utc)
TARGET_WEEKDAY = 4
TARGET_TIME = time(17, 0)
EXPECTED_TAIL = {date(2027, 6, 11), date(2027, 6, 18)}


def _zone(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "Europe/Paris")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _json_object(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _execution(followup: QuoteAcceptanceFollowup) -> dict[str, Any]:
    return _json_object(_json_object(followup.payload).get("quote_to_enrollment_execution"))


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(_zone(session_obj.timezone))


def _candidate_series(db) -> list[dict[str, Any]]:
    repair_events = list(
        db.scalars(
            select(DomainEvent)
            .where(
                DomainEvent.event_type == "booking_series_moved_by_admin_repair",
                DomainEvent.source == "admin_repair",
            )
            .order_by(DomainEvent.occurred_at.desc(), DomainEvent.created_at.desc())
        ).all()
    )
    rows: list[dict[str, Any]] = []
    seen: set[tuple[UUID, UUID]] = set()
    for event in repair_events:
        payload = _json_object(event.payload_json)
        moved_booking_ids = {
            parsed
            for raw in _json_list(payload.get("moved_booking_ids"))
            if (parsed := _parse_uuid(raw)) is not None
        }
        if not moved_booking_ids or payload.get("price_policy") != "keep_source":
            continue
        student_id = _parse_uuid(payload.get("student_id")) or event.related_entity_id
        student = db.get(User, student_id)
        if student is None or student.role != UserRole.CLIENT:
            continue
        booking_rows = db.execute(
            select(Booking, CourseSession, CourseType, Location)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                Booking.user_id == student.id,
                Booking.id.in_(moved_booking_ids),
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= SEASON_START,
                CourseSession.start_at_utc < SEASON_END,
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        grouped: dict[UUID, list[tuple[Booking, CourseSession, CourseType, Location]]] = defaultdict(list)
        for booking, session_obj, course_type, location in booking_rows:
            local_start = _local_start(session_obj)
            if (
                session_obj.recurrence_group_id is not None
                and local_start.weekday() == TARGET_WEEKDAY
                and local_start.timetz().replace(tzinfo=None, second=0, microsecond=0) == TARGET_TIME
            ):
                grouped[session_obj.recurrence_group_id].append((booking, session_obj, course_type, location))
        for group_id, group_rows in grouped.items():
            if len(group_rows) < 20:
                continue
            key = (student.id, group_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "student": student,
                    "group_id": group_id,
                    "rows": group_rows,
                    "repair_event_id": event.id,
                }
            )
    return rows


def _matching_quotes(db, *, booking_ids: set[UUID]) -> list[tuple[Quote, QuoteAcceptanceFollowup]]:
    rows = db.execute(
        select(Quote, QuoteAcceptanceFollowup)
        .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
        .where(Quote.school_year_label == SCHOOL_YEAR)
        .order_by(Quote.created_at.asc())
    ).all()
    matches: list[tuple[Quote, QuoteAcceptanceFollowup]] = []
    for quote, followup in rows:
        execution_ids = {
            parsed
            for raw in _json_list(_execution(followup).get("created_booking_ids"))
            if (parsed := _parse_uuid(raw)) is not None
        }
        if execution_ids & booking_ids:
            matches.append((quote, followup))
    return matches


def main() -> int:
    with SessionLocal() as db:
        candidates = _candidate_series(db)
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one Diane Friday 17 annual series, found {len(candidates)}")
        candidate = candidates[0]
        student: User = candidate["student"]
        group_id: UUID = candidate["group_id"]
        rows = candidate["rows"]
        bookings = [row[0] for row in rows]
        sessions = [row[1] for row in rows]
        course_type: CourseType = rows[0][2]
        location: Location = rows[0][3]
        booking_ids = {booking.id for booking in bookings}
        current_dates = {_local_start(session_obj).date() for session_obj in sessions}

        quote_matches = _matching_quotes(db, booking_ids=booking_ids)
        quote_rows: list[dict[str, Any]] = []
        related_note_ids: set[UUID] = set()
        for quote, followup in quote_matches:
            execution = _execution(followup)
            related_note_ids.update(
                parsed
                for raw in _json_list(execution.get("created_annual_invoice_note_ids"))
                if (parsed := _parse_uuid(raw)) is not None
            )
            lines = list(
                db.scalars(
                    select(QuoteLine)
                    .where(QuoteLine.quote_id == quote.id)
                    .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
                ).all()
            )
            quote_rows.append(
                {
                    "quote_number": quote.quote_number,
                    "status": quote.status,
                    "total_ttc": str(_money(quote.total_ttc)),
                    "line_total_ttc": str(sum((_money(line.amount_ttc) for line in lines), Decimal("0.00"))),
                    "matching_activity_lines": [
                        {
                            "quantity": str(_money(line.quantity)),
                            "unit_ttc": str(_money(line.unit_price_ttc)),
                            "amount_ttc": str(_money(line.amount_ttc)),
                        }
                        for line in lines
                        if line.activity_id == course_type.id
                    ],
                }
            )

        invoice_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(booking_ids),
                )
            ).all()
        )
        related_note_ids.update(line.note_id for line in invoice_lines)
        notes = {
            note.id: note
            for note in db.scalars(select(ClientNoteEntry).where(ClientNoteEntry.id.in_(related_note_ids))).all()
        } if related_note_ids else {}
        all_note_lines = list(
            db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id.in_(related_note_ids))).all()
        ) if related_note_ids else []
        lines_by_note: dict[UUID, list[ClientInvoiceLine]] = defaultdict(list)
        for line in all_note_lines:
            lines_by_note[line.note_id].append(line)

        invoice_rows: list[dict[str, Any]] = []
        for note_id in sorted(related_note_ids, key=str):
            note = notes.get(note_id)
            metadata = _parse_invoice_range_note_entry(note) if note is not None else None
            note_lines = lines_by_note.get(note_id, [])
            student_lines = [line for line in note_lines if line.source_payment_id in booking_ids]
            invoice_rows.append(
                {
                    "invoice_number": str((metadata or {}).get("invoice_number") or ""),
                    "invoice_status": str((metadata or {}).get("invoice_status") or ""),
                    "invoice_total_ttc": str(sum((_money(line.total_incl_vat) for line in note_lines), Decimal("0.00"))),
                    "student_booking_line_count": len(student_lines),
                    "student_booking_total_ttc": str(
                        sum((_money(line.total_incl_vat) for line in student_lines), Decimal("0.00"))
                    ),
                }
            )

        booking_invoice_amount_mismatches = 0
        invoice_by_booking: dict[UUID, list[ClientInvoiceLine]] = defaultdict(list)
        for line in invoice_lines:
            invoice_by_booking[line.source_payment_id].append(line)
        for booking in bookings:
            if any(_money(line.total_incl_vat) != _money(booking.total_incl_vat_snapshot) for line in invoice_by_booking[booking.id]):
                booking_invoice_amount_mismatches += 1

        result = {
            "student_id": str(student.id),
            "series_id": str(group_id),
            "activity_id": str(course_type.id),
            "location_id": str(location.id),
            "booked_session_count": len(bookings),
            "first_session": min(current_dates).isoformat(),
            "last_session": max(current_dates).isoformat(),
            "expected_tail_missing": sorted(value.isoformat() for value in EXPECTED_TAIL - current_dates),
            "booking_snapshot_total_ttc": str(
                sum((_money(booking.total_incl_vat_snapshot) for booking in bookings), Decimal("0.00"))
            ),
            "invoiced_booking_count": len({line.source_payment_id for line in invoice_lines}),
            "invoiced_booking_total_ttc": str(
                sum((_money(line.total_incl_vat) for line in invoice_lines), Decimal("0.00"))
            ),
            "booking_invoice_amount_mismatches": booking_invoice_amount_mismatches,
            "quotes": quote_rows,
            "invoices": invoice_rows,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
