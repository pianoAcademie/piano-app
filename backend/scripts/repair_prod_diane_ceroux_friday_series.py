from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import BOOKING_STATUSES_ACTIVE
from app.api.routes.admin_clients import _build_invoice_range_note_message, _parse_invoice_range_note_entry
from app.api.routes.quotes import (
    _quote_transformation_execution,
    _set_quote_integration_meta,
    _set_quote_transformation_execution,
)
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.notification_engine import DomainEvent
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteEvent, QuoteLine
from app.services.reminders import ensure_booking_reminder


SCRIPT_PREFIX = "PROD_REPAIR_DIANE_CEROUX_FRIDAY_SERIES"
STUDENT_ID = UUID("ed14d382-d354-4d03-a05e-b6c7cc51f446")
COURSE_TYPE_ID = UUID("4bdf5d1e-fe55-4f95-80d4-0cafd3ce7683")
LOCATION_ID = UUID("cb3337a8-6a32-431d-b5c4-2cd8667be97f")
QUOTE_NUMBER = "DV-20260709091102-97C1"
INVOICE_NUMBER = "PA26-0502"
SCHOOL_YEAR = "2026-2027"
TARGET_WEEKDAY = 4
TARGET_TIME = time(17, 0)
EXPECTED_COUNT = 32
EXPECTED_COURSE_TOTAL = Decimal("1216.00")
EXPECTED_DOCUMENT_TOTAL = Decimal("1511.00")
CURRENT_BAD_COUNT = 19
CURRENT_BAD_UNIT = Decimal("64.00")
SEASON_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 7, 1, tzinfo=timezone.utc)


def _money(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))


def _move_optional_time(value: datetime | None, *, target: CourseSession) -> datetime | None:
    if value is None:
        return None
    zone = ZoneInfo(target.timezone or "Europe/Paris")
    local_value = value.astimezone(zone)
    local_target = _local_start(target)
    return datetime.combine(local_target.date(), local_value.timetz().replace(tzinfo=None), tzinfo=zone).astimezone(
        timezone.utc
    )


def _abort(reason: str) -> None:
    raise RuntimeError(f"{SCRIPT_PREFIX}|abort|reason={reason}")


def _json_uuid_list(values: object) -> list[UUID]:
    if not isinstance(values, list):
        return []
    parsed: list[UUID] = []
    for value in values:
        try:
            parsed.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


def _target_booking_rows(db) -> list[tuple[Booking, CourseSession]]:
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == STUDENT_ID,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            CourseSession.course_type_id == COURSE_TYPE_ID,
            CourseSession.location_id == LOCATION_ID,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= SEASON_START,
            CourseSession.start_at_utc < SEASON_END,
        )
        .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
        .with_for_update()
    ).all()
    return [
        (booking, session_obj)
        for booking, session_obj in rows
        if _local_start(session_obj).weekday() == TARGET_WEEKDAY
        and _local_start(session_obj).timetz().replace(tzinfo=None, second=0, microsecond=0) == TARGET_TIME
    ]


def _invoice_context(db, *, booking_ids: set[UUID]) -> tuple[ClientNoteEntry, dict[str, object], list[ClientInvoiceLine]]:
    booking_lines = list(
        db.scalars(
            select(ClientInvoiceLine)
            .where(
                ClientInvoiceLine.source == "BOOKING",
                ClientInvoiceLine.source_payment_id.in_(booking_ids),
            )
            .with_for_update()
        ).all()
    )
    note_ids = {line.note_id for line in booking_lines}
    if len(note_ids) != 1:
        _abort(f"expected_one_invoice_note_found_{len(note_ids)}")
    note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == next(iter(note_ids))).with_for_update())
    if note is None:
        _abort("invoice_note_missing")
    metadata = _parse_invoice_range_note_entry(note)
    if not metadata:
        _abort("invoice_metadata_missing")
    if str(metadata.get("invoice_number") or "") != INVOICE_NUMBER:
        _abort(f"unexpected_invoice_{metadata.get('invoice_number')}")
    if str(metadata.get("invoice_status") or "").strip().upper() != "ISSUED":
        _abort(f"unexpected_invoice_status_{metadata.get('invoice_status')}")
    all_lines = list(
        db.scalars(
            select(ClientInvoiceLine)
            .where(ClientInvoiceLine.note_id == note.id)
            .order_by(ClientInvoiceLine.occurred_at.asc(), ClientInvoiceLine.id.asc())
            .with_for_update()
        ).all()
    )
    return note, metadata, all_lines


def _quote_context(db) -> tuple[Quote, QuoteAcceptanceFollowup, QuoteLine, list[QuoteLine]]:
    quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update())
    if quote is None:
        _abort("quote_missing")
    if str(quote.status or "").strip().lower() != "approved":
        _abort(f"unexpected_quote_status_{quote.status}")
    if (quote.school_year_label or "").strip() != SCHOOL_YEAR:
        _abort(f"unexpected_school_year_{quote.school_year_label}")
    lines = list(
        db.scalars(
            select(QuoteLine)
            .where(QuoteLine.quote_id == quote.id)
            .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
            .with_for_update()
        ).all()
    )
    course_lines = [line for line in lines if line.activity_id == COURSE_TYPE_ID]
    if len(course_lines) != 1:
        _abort(f"expected_one_course_line_found_{len(course_lines)}")
    course_line = course_lines[0]
    if _money(course_line.quantity) != Decimal("32.00"):
        _abort(f"unexpected_quote_quantity_{course_line.quantity}")
    if _money(course_line.unit_price_ttc) != Decimal("38.00"):
        _abort(f"unexpected_quote_unit_price_{course_line.unit_price_ttc}")
    if _money(course_line.amount_ttc) != EXPECTED_COURSE_TOTAL:
        _abort(f"unexpected_quote_course_total_{course_line.amount_ttc}")
    if _money(quote.total_ttc) != EXPECTED_DOCUMENT_TOTAL:
        _abort(f"unexpected_quote_total_{quote.total_ttc}")
    if sum((_money(line.amount_ttc) for line in lines), Decimal("0.00")) != EXPECTED_DOCUMENT_TOTAL:
        _abort("quote_line_total_mismatch")
    followup = db.scalar(
        select(QuoteAcceptanceFollowup)
        .where(QuoteAcceptanceFollowup.quote_id == quote.id)
        .with_for_update()
    )
    if followup is None:
        _abort("quote_followup_missing")
    return quote, followup, course_line, lines


def _series_sessions(db, *, recurrence_group_id: UUID) -> list[CourseSession]:
    candidates = list(
        db.scalars(
            select(CourseSession)
            .where(
                CourseSession.recurrence_group_id == recurrence_group_id,
                CourseSession.course_type_id == COURSE_TYPE_ID,
                CourseSession.location_id == LOCATION_ID,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= SEASON_START,
                CourseSession.start_at_utc < SEASON_END,
            )
            .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
            .with_for_update()
        ).all()
    )
    rows = [
        row
        for row in candidates
        if _local_start(row).weekday() == TARGET_WEEKDAY
        and _local_start(row).timetz().replace(tzinfo=None, second=0, microsecond=0) == TARGET_TIME
    ]
    dates = [_local_start(row).date() for row in rows]
    if len(rows) != EXPECTED_COUNT or len(set(dates)) != EXPECTED_COUNT:
        _abort(f"target_series_expected_32_found_{len(rows)}")
    if dates[0] != date(2026, 9, 11) or dates[-1] != date(2027, 6, 18):
        _abort(f"unexpected_series_bounds_{dates[0]}_{dates[-1]}")
    return rows


def _assert_capacity(db, *, session_obj: CourseSession) -> None:
    active_count = int(
        db.scalar(
            select(func.count(Booking.id)).where(
                Booking.session_id == session_obj.id,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            )
        )
        or 0
    )
    if active_count >= int(session_obj.capacity_max or 0):
        _abort(f"target_session_full_{session_obj.id}_{active_count}_of_{session_obj.capacity_max}")


def _course_invoice_lines(lines: list[ClientInvoiceLine], *, booking_ids: set[UUID]) -> list[ClientInvoiceLine]:
    return [
        line
        for line in lines
        if line.source == "BOOKING" and line.source_payment_id in booking_ids
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair Diane Ceroux's Friday annual series and issued invoice allocation.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded repair. Without it, audit only.")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        rows = _target_booking_rows(db)
        if len(rows) not in {CURRENT_BAD_COUNT, EXPECTED_COUNT}:
            _abort(f"unexpected_active_booking_count_{len(rows)}")
        bookings = [row[0] for row in rows]
        sessions = [row[1] for row in rows]
        recurrence_ids = {row.recurrence_group_id for row in sessions}
        if None in recurrence_ids or len(recurrence_ids) != 1:
            _abort(f"expected_one_recurrence_group_found_{len(recurrence_ids)}")
        recurrence_group_id = next(iter(recurrence_ids))
        if recurrence_group_id is None:
            _abort("recurrence_group_missing")
        series_sessions = _series_sessions(db, recurrence_group_id=recurrence_group_id)
        series_by_date = {_local_start(row).date(): row for row in series_sessions}
        current_by_date = {_local_start(session_obj).date(): booking for booking, session_obj in rows}
        if not set(current_by_date).issubset(series_by_date):
            _abort("bookings_outside_target_series")
        missing_dates = sorted(set(series_by_date) - set(current_by_date))
        if len(rows) == CURRENT_BAD_COUNT and len(missing_dates) != EXPECTED_COUNT - CURRENT_BAD_COUNT:
            _abort(f"expected_13_missing_dates_found_{len(missing_dates)}")
        if len(rows) == EXPECTED_COUNT and missing_dates:
            _abort(f"complete_booking_count_but_missing_dates_{len(missing_dates)}")

        quote, followup, course_line, quote_lines = _quote_context(db)
        booking_ids = {booking.id for booking in bookings}
        note, invoice_metadata, all_invoice_lines = _invoice_context(db, booking_ids=booking_ids)
        existing_course_invoice_lines = _course_invoice_lines(all_invoice_lines, booking_ids=booking_ids)
        if len(existing_course_invoice_lines) != len(bookings):
            _abort(
                f"booking_invoice_line_count_mismatch_{len(bookings)}_{len(existing_course_invoice_lines)}"
            )
        if sum((_money(line.total_incl_vat) for line in all_invoice_lines), Decimal("0.00")) != EXPECTED_DOCUMENT_TOTAL:
            _abort("issued_invoice_total_mismatch_before_repair")
        metadata_total = _money(dict(invoice_metadata.get("totals_by_currency") or {}).get("EUR"))
        if metadata_total != EXPECTED_DOCUMENT_TOTAL:
            _abort(f"invoice_metadata_total_mismatch_{metadata_total}")
        execution = _quote_transformation_execution(followup)
        source_quote_id = str(invoice_metadata.get("source_quote_id") or "").strip()
        if source_quote_id and source_quote_id != str(quote.id):
            _abort("invoice_has_conflicting_quote_link")
        execution_invoice_note_ids = set(_json_uuid_list(execution.get("created_annual_invoice_note_ids")))
        execution_booking_ids = set(_json_uuid_list(execution.get("created_booking_ids")))
        if note.id not in execution_invoice_note_ids and not booking_ids.issubset(execution_booking_ids):
            _abort("invoice_and_bookings_missing_from_quote_execution")

        target_unit = (
            _money(course_line.unit_price_ht),
            _rate(course_line.vat_rate),
            _money(course_line.unit_vat_amount),
            _money(course_line.unit_price_ttc),
            (quote.currency or "EUR").strip().upper(),
        )
        expected_unit = target_unit[3]
        complete_state = len(bookings) == EXPECTED_COUNT
        if complete_state:
            if any(_money(booking.total_incl_vat_snapshot) != expected_unit for booking in bookings):
                _abort("complete_series_has_wrong_booking_price")
            if any(_money(line.total_incl_vat) != expected_unit for line in existing_course_invoice_lines):
                _abort("complete_series_has_wrong_invoice_price")
            if sum(
                (_money(line.total_incl_vat) for line in existing_course_invoice_lines), Decimal("0.00")
            ) != EXPECTED_COURSE_TOTAL:
                _abort("complete_series_course_total_mismatch")
            db.rollback()
            print(
                f"{SCRIPT_PREFIX}|summary|result=already_repaired|bookings=32|unit_ttc=38.00|"
                f"course_total=1216.00|invoice_total=1511.00|quote_total=1511.00|applied={args.apply}"
            )
            return 0

        if any(_money(booking.total_incl_vat_snapshot) != CURRENT_BAD_UNIT for booking in bookings):
            _abort("legacy_booking_prices_not_all_64")
        if any(_money(line.total_incl_vat) != CURRENT_BAD_UNIT for line in existing_course_invoice_lines):
            _abort("legacy_invoice_prices_not_all_64")
        if sum(
            (_money(line.total_incl_vat) for line in existing_course_invoice_lines), Decimal("0.00")
        ) != EXPECTED_COURSE_TOTAL:
            _abort("legacy_course_total_mismatch")

        print(
            f"{SCRIPT_PREFIX}|audit|student_id={STUDENT_ID}|recurrence_group_id={recurrence_group_id}|"
            f"current_bookings={len(bookings)}|missing={len(missing_dates)}|"
            f"first_missing={missing_dates[0]}|last_missing={missing_dates[-1]}|"
            f"quote_unit_ttc={target_unit[3]:.2f}|quote_course_total={course_line.amount_ttc}|"
            f"quote_total={quote.total_ttc}|invoice={INVOICE_NUMBER}|invoice_total=1511.00|applied={args.apply}"
        )
        if not args.apply:
            db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|result=audit_only|missing_dates={','.join(map(str, missing_dates))}")
            return 0

        template_booking = bookings[0]
        template_invoice_line = existing_course_invoice_lines[0]
        for booking in bookings:
            booking.price_excl_vat_snapshot = target_unit[0]
            booking.vat_rate_snapshot = target_unit[1]
            booking.vat_amount_snapshot = target_unit[2]
            booking.total_incl_vat_snapshot = target_unit[3]
            booking.currency_snapshot = target_unit[4]
            booking.pricing_snapshot_locked = True
            db.add(booking)
        for line in existing_course_invoice_lines:
            line.amount_excl_vat = target_unit[0]
            line.vat_rate = target_unit[1]
            line.vat_amount = target_unit[2]
            line.total_incl_vat = target_unit[3]
            line.currency = target_unit[4]
            db.add(line)

        created_bookings: list[Booking] = []
        created_invoice_lines: list[ClientInvoiceLine] = []
        for target_date in missing_dates:
            target_session = series_by_date[target_date]
            existing = db.scalar(
                select(Booking).where(
                    Booking.session_id == target_session.id,
                    Booking.user_id == STUDENT_ID,
                )
            )
            if existing is not None:
                _abort(f"booking_already_exists_for_missing_date_{target_date}_{existing.status}")
            _assert_capacity(db, session_obj=target_session)
            booking = Booking(
                session_id=target_session.id,
                user_id=STUDENT_ID,
                client_plan_subscription_id=template_booking.client_plan_subscription_id,
                manual_credit_type_id=template_booking.manual_credit_type_id,
                status=BookingStatus.BOOKED,
                booked_at=template_booking.booked_at,
                payment_hold_expires_at=None,
                cancelled_at=None,
                cancellation_reason=None,
                price_excl_vat_snapshot=target_unit[0],
                vat_rate_snapshot=target_unit[1],
                vat_amount_snapshot=target_unit[2],
                total_incl_vat_snapshot=target_unit[3],
                currency_snapshot=target_unit[4],
                pricing_snapshot_locked=True,
                student_start_at_utc=_move_optional_time(template_booking.student_start_at_utc, target=target_session),
                student_end_at_utc=_move_optional_time(template_booking.student_end_at_utc, target=target_session),
                student_note=template_booking.student_note,
                internal_note=template_booking.internal_note,
                is_trial_course=False,
                trial_course_type_id=None,
                makeup_request_id=None,
                makeup_credit_consumed=False,
                makeup_override_applied=False,
            )
            db.add(booking)
            db.flush()
            ensure_booking_reminder(db, booking=booking, session_obj=target_session, now=now)
            invoice_line = ClientInvoiceLine(
                note_id=note.id,
                user_id=template_invoice_line.user_id,
                source="BOOKING",
                source_payment_id=booking.id,
                occurred_at=target_session.start_at_utc,
                label=template_invoice_line.label,
                amount_excl_vat=target_unit[0],
                vat_rate=target_unit[1],
                vat_amount=target_unit[2],
                total_incl_vat=target_unit[3],
                currency=target_unit[4],
                billing_entity=template_invoice_line.billing_entity,
                seller_legal_entity_id=template_invoice_line.seller_legal_entity_id,
            )
            db.add(invoice_line)
            created_bookings.append(booking)
            created_invoice_lines.append(invoice_line)

        execution_booking_ids = _json_uuid_list(execution.get("created_booking_ids"))
        merged_booking_ids = list(dict.fromkeys([*execution_booking_ids, *[row.id for row in created_bookings]]))
        execution["created_booking_ids"] = [str(value) for value in merged_booking_ids]
        execution["series_repaired_at"] = now.isoformat()
        execution["series_repair_reason"] = "32 cours annuels à 38 EUR; facture totale inchangée"
        _set_quote_transformation_execution(followup, execution)
        _set_quote_integration_meta(
            quote,
            integration_slots_result=f"{len(merged_booking_ids)} reservation(s) creee(s)",
        )

        included_keys = [str(value) for value in invoice_metadata.get("included_payment_keys") or []]
        included_keys.extend(f"BOOKING:{booking.id}" for booking in created_bookings)
        invoice_metadata["included_payment_keys"] = list(dict.fromkeys(included_keys))
        invoice_metadata["private_note"] = (
            f"{str(invoice_metadata.get('private_note') or '').strip()} "
            "Répartition corrigée le 29/08/2026 : 32 cours à 38 EUR, total inchangé."
        ).strip()
        note.message = _build_invoice_range_note_message(invoice_metadata)
        db.add(note)

        db.add(
            QuoteEvent(
                quote_id=quote.id,
                event_type="planning_invoice_allocation_repaired",
                actor_type="system",
                actor_id=None,
                payload={
                    "student_id": str(STUDENT_ID),
                    "invoice_number": INVOICE_NUMBER,
                    "before": {"booking_count": 19, "unit_ttc": "64.00", "course_total": "1216.00"},
                    "after": {"booking_count": 32, "unit_ttc": "38.00", "course_total": "1216.00"},
                    "document_total": "1511.00",
                    "email_sent": False,
                },
            )
        )
        db.add(
            DomainEvent(
                event_type="booking_series_invoice_allocation_repaired",
                source="admin_repair",
                actor_type="system",
                actor_id=None,
                related_entity_type="student",
                related_entity_id=STUDENT_ID,
                occurred_at=now,
                payload_json={
                    "quote_number": QUOTE_NUMBER,
                    "invoice_number": INVOICE_NUMBER,
                    "created_booking_ids": [str(row.id) for row in created_bookings],
                    "created_invoice_line_ids": [str(row.id) for row in created_invoice_lines],
                    "missing_dates": [value.isoformat() for value in missing_dates],
                    "price_policy": "quote_unit_price",
                    "unit_ttc": "38.00",
                    "course_total": "1216.00",
                    "document_total": "1511.00",
                },
            )
        )
        db.flush()

        repaired_rows = _target_booking_rows(db)
        repaired_booking_ids = {row[0].id for row in repaired_rows}
        repaired_dates = {_local_start(row[1]).date() for row in repaired_rows}
        repaired_invoice_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.note_id == note.id,
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(repaired_booking_ids),
                )
            ).all()
        )
        final_all_invoice_lines = list(
            db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id == note.id)).all()
        )
        if len(repaired_rows) != EXPECTED_COUNT or repaired_dates != set(series_by_date):
            _abort("postcheck_booking_series_mismatch")
        if any(_money(row[0].total_incl_vat_snapshot) != Decimal("38.00") for row in repaired_rows):
            _abort("postcheck_booking_unit_price_mismatch")
        if len(repaired_invoice_lines) != EXPECTED_COUNT:
            _abort(f"postcheck_invoice_course_line_count_{len(repaired_invoice_lines)}")
        if sum(
            (_money(line.total_incl_vat) for line in repaired_invoice_lines), Decimal("0.00")
        ) != EXPECTED_COURSE_TOTAL:
            _abort("postcheck_invoice_course_total_mismatch")
        if sum(
            (_money(line.total_incl_vat) for line in final_all_invoice_lines), Decimal("0.00")
        ) != EXPECTED_DOCUMENT_TOTAL:
            _abort("postcheck_invoice_total_mismatch")
        if sum((_money(line.amount_ttc) for line in quote_lines), Decimal("0.00")) != EXPECTED_DOCUMENT_TOTAL:
            _abort("postcheck_quote_total_mismatch")

        db.commit()
        print(
            f"{SCRIPT_PREFIX}|summary|result=repaired|created_bookings={len(created_bookings)}|"
            f"bookings=32|unit_ttc=38.00|course_total=1216.00|"
            f"invoice={INVOICE_NUMBER}|invoice_total=1511.00|quote={QUOTE_NUMBER}|quote_total=1511.00|applied=True"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
