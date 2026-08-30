from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import BOOKING_STATUSES_ACTIVE
from app.api.routes.admin_clients import _build_invoice_range_note_message, _parse_invoice_range_note_entry
from app.api.routes.quotes import _quote_transformation_execution, _set_quote_transformation_execution
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.notification_engine import DomainEvent
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteEvent, QuoteLine
from app.services.reminders import ensure_booking_reminder


SCRIPT_PREFIX = "PROD_REPAIR_LINA_GHEMARI_FRIDAY_20260830"
STUDENT_ID = UUID("6af3cc4a-a64f-4360-a3f7-b275393e317f")
QUOTE_ID = UUID("229310dd-508c-4f42-a3d9-36c1ac134389")
QUOTE_NUMBER = "DV-20260519045329-CA5B"
INVOICE_NOTE_ID = UUID("11ef9108-fe15-4d6d-aa94-807ea031d5bf")
INVOICE_NUMBER = "PA26-0597"
SCHOOL_YEAR = "2026-2027"
COURSE_NAME = "Cours collectifs ado/adultes"
LOCATION_NAME = "Rue Scheffer"
TARGET_WEEKDAY = 4
TARGET_TIME = time(19, 0)
TARGET_DATE = date(2027, 5, 14)
SCHOOL_CLOSURE_DATE = date(2027, 5, 7)
EXPECTED_COUNT = 32
CURRENT_BAD_COUNT = 31
EXPECTED_UNIT_TTC = Decimal("22.00")
EXPECTED_COURSE_TOTAL = Decimal("704.00")
EXPECTED_DOCUMENT_TOTAL = Decimal("879.00")
SEASON_START = datetime(2026, 9, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 7, 1, tzinfo=timezone.utc)


def _abort(reason: str) -> None:
    raise RuntimeError(f"{SCRIPT_PREFIX}|abort|reason={reason}")


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
    return datetime.combine(
        local_target.date(),
        local_value.timetz().replace(tzinfo=None),
        tzinfo=zone,
    ).astimezone(timezone.utc)


def _uuid_list(values: object) -> list[UUID]:
    if not isinstance(values, list):
        return []
    out: list[UUID] = []
    for value in values:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def _quote_context(db) -> tuple[Quote, QuoteAcceptanceFollowup, QuoteLine, CourseType, Location]:
    quote = db.scalar(select(Quote).where(Quote.id == QUOTE_ID).with_for_update())
    if quote is None or quote.quote_number != QUOTE_NUMBER:
        _abort("quote_missing_or_number_changed")
    if str(quote.status or "").strip().lower() != "approved":
        _abort(f"unexpected_quote_status_{quote.status}")
    if (quote.school_year_label or "").strip() != SCHOOL_YEAR:
        _abort(f"unexpected_school_year_{quote.school_year_label}")
    if _money(quote.total_ttc) != EXPECTED_DOCUMENT_TOTAL:
        _abort(f"unexpected_quote_total_{quote.total_ttc}")

    line_rows = db.execute(
        select(QuoteLine, CourseType)
        .join(CourseType, CourseType.id == QuoteLine.activity_id)
        .where(QuoteLine.quote_id == quote.id, CourseType.name == COURSE_NAME)
        .with_for_update()
    ).all()
    if len(line_rows) != 1:
        _abort(f"expected_one_course_line_found_{len(line_rows)}")
    course_line, course_type = line_rows[0]
    if _money(course_line.quantity) != Decimal(EXPECTED_COUNT):
        _abort(f"unexpected_quote_quantity_{course_line.quantity}")
    if _money(course_line.unit_price_ttc) != EXPECTED_UNIT_TTC:
        _abort(f"unexpected_quote_unit_ttc_{course_line.unit_price_ttc}")
    if _money(course_line.amount_ttc) != EXPECTED_COURSE_TOTAL:
        _abort(f"unexpected_quote_course_total_{course_line.amount_ttc}")

    followup = db.scalar(
        select(QuoteAcceptanceFollowup)
        .where(QuoteAcceptanceFollowup.quote_id == quote.id)
        .with_for_update()
    )
    if followup is None:
        _abort("followup_missing")
    location = db.scalar(select(Location).where(Location.name == LOCATION_NAME))
    if location is None:
        _abort("location_missing")
    return quote, followup, course_line, course_type, location


def _target_rows(
    db,
    *,
    booking_ids: list[UUID],
    course_type_id: UUID,
    location_id: UUID,
) -> list[tuple[Booking, CourseSession]]:
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.id.in_(booking_ids),
            Booking.user_id == STUDENT_ID,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            CourseSession.course_type_id == course_type_id,
            CourseSession.location_id == location_id,
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


def _series_sessions(
    db,
    *,
    recurrence_group_id: UUID,
    course_type_id: UUID,
    location_id: UUID,
) -> tuple[list[CourseSession], CourseSession | None]:
    candidates = list(
        db.scalars(
            select(CourseSession)
            .where(
                CourseSession.recurrence_group_id == recurrence_group_id,
                CourseSession.course_type_id == course_type_id,
                CourseSession.location_id == location_id,
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
    by_date = {_local_start(row).date(): row for row in rows}
    if len(by_date) != len(rows):
        _abort("duplicate_dates_in_target_series")
    closure_session = by_date.pop(SCHOOL_CLOSURE_DATE, None)
    if len(by_date) != EXPECTED_COUNT:
        _abort(f"target_series_expected_32_teaching_dates_found_{len(by_date)}")
    if TARGET_DATE not in by_date:
        _abort("target_date_missing_from_live_series")
    return [by_date[value] for value in sorted(by_date)], closure_session


def _invoice_context(
    db,
    *,
    booking_ids: set[UUID],
) -> tuple[ClientNoteEntry, dict[str, object], list[ClientInvoiceLine], list[ClientInvoiceLine]]:
    course_lines = list(
        db.scalars(
            select(ClientInvoiceLine)
            .where(
                ClientInvoiceLine.source == "BOOKING",
                ClientInvoiceLine.source_payment_id.in_(booking_ids),
            )
            .with_for_update()
        ).all()
    )
    if len(course_lines) != len(booking_ids):
        _abort(f"course_invoice_line_count_{len(course_lines)}_{len(booking_ids)}")
    if {line.note_id for line in course_lines} != {INVOICE_NOTE_ID}:
        _abort("course_lines_not_on_expected_invoice")
    note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == INVOICE_NOTE_ID).with_for_update())
    if note is None:
        _abort("invoice_note_missing")
    metadata = _parse_invoice_range_note_entry(note)
    if not metadata or str(metadata.get("invoice_number") or "") != INVOICE_NUMBER:
        _abort("invoice_metadata_missing_or_number_changed")
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
    if sum((_money(line.total_incl_vat) for line in all_lines), Decimal("0.00")) != EXPECTED_DOCUMENT_TOTAL:
        _abort("issued_invoice_total_mismatch")
    if _money(dict(metadata.get("totals_by_currency") or {}).get("EUR")) != EXPECTED_DOCUMENT_TOTAL:
        _abort("invoice_metadata_total_mismatch")
    if sum((_money(line.total_incl_vat) for line in course_lines), Decimal("0.00")) != EXPECTED_COURSE_TOTAL:
        _abort("course_invoice_total_mismatch")
    return note, metadata, course_lines, all_lines


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
        _abort(f"target_session_full_{active_count}_of_{session_obj.capacity_max}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair Lina Ghemari's missing 14 May Friday booking.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded repair. Without it, audit only.")
    parser.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="Exit successfully when the production-only quote is absent.",
    )
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        if db.get(Quote, QUOTE_ID) is None:
            if args.skip_if_missing:
                print(f"{SCRIPT_PREFIX}|summary|result=skipped_missing_quote|applied={args.apply}")
                return 0
            _abort("quote_missing")

        quote, followup, course_line, course_type, location = _quote_context(db)
        execution = _quote_transformation_execution(followup)
        execution_booking_ids = _uuid_list(execution.get("created_booking_ids"))
        rows = _target_rows(
            db,
            booking_ids=execution_booking_ids,
            course_type_id=course_type.id,
            location_id=location.id,
        )
        if len(rows) not in {CURRENT_BAD_COUNT, EXPECTED_COUNT}:
            _abort(f"unexpected_booking_count_{len(rows)}")
        recurrence_groups = {session_obj.recurrence_group_id for _, session_obj in rows}
        if None in recurrence_groups or len(recurrence_groups) != 1:
            _abort(f"expected_one_recurrence_group_found_{len(recurrence_groups)}")
        recurrence_group_id = next(iter(recurrence_groups))
        if recurrence_group_id is None:
            _abort("recurrence_group_missing")
        series_sessions, closure_session = _series_sessions(
            db,
            recurrence_group_id=recurrence_group_id,
            course_type_id=course_type.id,
            location_id=location.id,
        )
        series_by_date = {_local_start(row).date(): row for row in series_sessions}
        current_by_date = {_local_start(session_obj).date(): booking for booking, session_obj in rows}
        missing_dates = sorted(set(series_by_date) - set(current_by_date))
        if len(rows) == CURRENT_BAD_COUNT and missing_dates != [TARGET_DATE]:
            _abort(f"expected_only_2027_05_14_missing_found_{','.join(map(str, missing_dates))}")
        if len(rows) == EXPECTED_COUNT and missing_dates:
            _abort(f"complete_series_has_missing_dates_{len(missing_dates)}")

        if closure_session is not None:
            closure_booking_count = int(
                db.scalar(
                    select(func.count(Booking.id)).where(
                        Booking.session_id == closure_session.id,
                        Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                    )
                )
                or 0
            )
            if closure_booking_count:
                _abort(f"school_closure_has_{closure_booking_count}_active_bookings")

        booking_ids = {booking.id for booking, _ in rows}
        note, invoice_metadata, course_invoice_lines, _ = _invoice_context(db, booking_ids=booking_ids)
        unit = (
            _money(course_line.unit_price_ht),
            _rate(course_line.vat_rate),
            _money(course_line.unit_vat_amount),
            _money(course_line.unit_price_ttc),
            (quote.currency or "EUR").strip().upper(),
        )
        already_repaired = len(rows) == EXPECTED_COUNT
        if already_repaired:
            if any(_money(booking.total_incl_vat_snapshot) != EXPECTED_UNIT_TTC for booking, _ in rows):
                _abort("complete_series_booking_unit_mismatch")
            if len(course_invoice_lines) != EXPECTED_COUNT or any(
                _money(line.total_incl_vat) != EXPECTED_UNIT_TTC for line in course_invoice_lines
            ):
                _abort("complete_series_invoice_allocation_mismatch")
            db.rollback()
            print(
                f"{SCRIPT_PREFIX}|summary|result=already_repaired|bookings=32|unit_ttc=22.00|"
                "course_total=704.00|invoice_total=879.00|applied=" + str(args.apply)
            )
            return 0

        print(
            f"{SCRIPT_PREFIX}|audit|quote={QUOTE_NUMBER}|invoice={INVOICE_NUMBER}|"
            f"series={recurrence_group_id}|bookings=31|missing={TARGET_DATE}|"
            f"course_total=704.00|invoice_total=879.00|applied={args.apply}"
        )
        if not args.apply:
            db.rollback()
            print(f"{SCRIPT_PREFIX}|summary|result=audit_only|applied=False")
            return 0

        if closure_session is not None:
            closure_session.status = SessionStatus.CANCELLED
            closure_session.cancel_reason = "Fermeture exceptionnelle des établissements scolaires le 07/05/2027"
            db.add(closure_session)

        for booking, _ in rows:
            booking.price_excl_vat_snapshot = unit[0]
            booking.vat_rate_snapshot = unit[1]
            booking.vat_amount_snapshot = unit[2]
            booking.total_incl_vat_snapshot = unit[3]
            booking.currency_snapshot = unit[4]
            booking.pricing_snapshot_locked = True
            db.add(booking)
        for line in course_invoice_lines:
            line.amount_excl_vat = unit[0]
            line.vat_rate = unit[1]
            line.vat_amount = unit[2]
            line.total_incl_vat = unit[3]
            line.currency = unit[4]
            db.add(line)

        template_booking = rows[0][0]
        template_invoice_line = course_invoice_lines[0]
        target_session = series_by_date[TARGET_DATE]
        existing = db.scalar(
            select(Booking).where(
                Booking.session_id == target_session.id,
                Booking.user_id == STUDENT_ID,
            )
        )
        if existing is not None:
            _abort(f"target_booking_already_exists_{existing.status}")
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
            price_excl_vat_snapshot=unit[0],
            vat_rate_snapshot=unit[1],
            vat_amount_snapshot=unit[2],
            total_incl_vat_snapshot=unit[3],
            currency_snapshot=unit[4],
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
            amount_excl_vat=unit[0],
            vat_rate=unit[1],
            vat_amount=unit[2],
            total_incl_vat=unit[3],
            currency=unit[4],
            billing_entity=template_invoice_line.billing_entity,
            seller_legal_entity_id=template_invoice_line.seller_legal_entity_id,
        )
        db.add(invoice_line)
        db.flush()

        execution["created_booking_ids"] = [
            str(value) for value in dict.fromkeys([*execution_booking_ids, booking.id])
        ]
        execution["series_repaired_at"] = now.isoformat()
        execution["series_repair_reason"] = "Ajout du vendredi 14/05/2027; 32 cours à 22 EUR; facture inchangée"
        _set_quote_transformation_execution(followup, execution)

        included_keys = [str(value) for value in invoice_metadata.get("included_payment_keys") or []]
        included_keys.append(f"BOOKING:{booking.id}")
        invoice_metadata["included_payment_keys"] = list(dict.fromkeys(included_keys))
        invoice_metadata["private_note"] = (
            f"{str(invoice_metadata.get('private_note') or '').strip()} "
            "Répartition corrigée le 30/08/2026 : 32 cours à 22 EUR, total inchangé."
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
                    "added_date": TARGET_DATE.isoformat(),
                    "cancelled_empty_closure_date": SCHOOL_CLOSURE_DATE.isoformat() if closure_session else None,
                    "before": {"booking_count": 31, "course_total": "704.00"},
                    "after": {"booking_count": 32, "unit_ttc": "22.00", "course_total": "704.00"},
                    "document_total": "879.00",
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
                    "created_booking_id": str(booking.id),
                    "created_invoice_line_id": str(invoice_line.id),
                    "added_date": TARGET_DATE.isoformat(),
                    "cancelled_empty_closure_date": SCHOOL_CLOSURE_DATE.isoformat() if closure_session else None,
                    "unit_ttc": "22.00",
                    "course_total": "704.00",
                    "document_total": "879.00",
                },
            )
        )
        db.flush()

        repaired_rows = _target_rows(
            db,
            booking_ids=_uuid_list(execution.get("created_booking_ids")),
            course_type_id=course_type.id,
            location_id=location.id,
        )
        repaired_ids = {row.id for row, _ in repaired_rows}
        repaired_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.note_id == note.id,
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(repaired_ids),
                )
            ).all()
        )
        final_all_lines = list(
            db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id == note.id)).all()
        )
        if len(repaired_rows) != EXPECTED_COUNT or {
            _local_start(session_obj).date() for _, session_obj in repaired_rows
        } != set(series_by_date):
            _abort("postcheck_booking_dates_mismatch")
        if len(repaired_lines) != EXPECTED_COUNT:
            _abort(f"postcheck_invoice_line_count_{len(repaired_lines)}")
        if any(_money(row.total_incl_vat_snapshot) != EXPECTED_UNIT_TTC for row, _ in repaired_rows):
            _abort("postcheck_booking_unit_mismatch")
        if sum((_money(line.total_incl_vat) for line in repaired_lines), Decimal("0.00")) != EXPECTED_COURSE_TOTAL:
            _abort("postcheck_course_total_mismatch")
        if sum((_money(line.total_incl_vat) for line in final_all_lines), Decimal("0.00")) != EXPECTED_DOCUMENT_TOTAL:
            _abort("postcheck_document_total_mismatch")

        db.commit()
        print(
            f"{SCRIPT_PREFIX}|summary|result=applied|created_booking={booking.id}|"
            f"created_invoice_line={invoice_line.id}|bookings=32|unit_ttc=22.00|"
            "course_total=704.00|invoice_total=879.00|email_sent=False|applied=True"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
