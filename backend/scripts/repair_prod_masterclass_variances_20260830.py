from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.admin_clients import _build_invoice_range_note_message, _parse_invoice_range_note_entry
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry, PaymentReceipt
from app.models.notification_engine import DomainEvent
from app.models.quote import Quote, QuoteEvent, QuoteLine
from app.services.notifications.application.orchestrator import cancel_pending_booking_reminder_notifications
from app.services.reminders import skip_pending_reminders_for_booking


SCRIPT_PREFIX = "PROD_REPAIR_MASTERCLASS_VARIANCES_20260830"
SCHOOL_YEAR = "2026-2027"
MASTERCLASS_ID = UUID("8195eb4a-8dd4-4dc8-bde6-304a773abd77")
RICHELIEU_ID = UUID("b66fe0d7-2990-4a58-b2f0-360911c611ee")
ONLINE_ID = UUID("90e90b51-e74a-4d94-86e7-7e2f132aa537")
SOLFEGE_LEVEL_2_ID = UUID("b3bdde45-0ba2-4aa1-b1e1-0d6d23842a96")
SOLFEGE_LEVEL_3_ID = UUID("b1c8e29e-5d48-4398-8cc7-5cdf1da88b4e")

YAZ_QUOTE_ID = UUID("320fb300-9f0f-4fa1-80b2-f0aca09c3fa4")
YAZ_QUOTE_NUMBER = "DV-20260810114842-5AB2"
YAZ_STUDENT_ID = UUID("46e704e4-47a6-4c6c-91e5-b23a14a54ab5")
YAZ_INVOICE_NUMBER = "PA26-0720"
YAZ_EXTRA_DATE = date(2027, 6, 12)
YAZ_EXPECTED_COUNT = 14
YAZ_MASTERCLASS_TOTAL = Decimal("2800.00")
YAZ_DOCUMENT_TOTAL = Decimal("5216.00")

DANIEL_QUOTE_ID = UUID("d83d4730-f5e2-434e-9795-88d5a711e193")
DANIEL_STUDENT_ID = UUID("31574128-1dfd-4b3b-b712-dd1b7bc29ab8")
VICTORIA_QUOTE_ID = UUID("9764739d-619b-4a70-af7e-779507b06991")
VICTORIA_STUDENT_ID = UUID("57d2146a-646c-4b3d-bdce-ac872135e3ad")

ACTIVE_BOOKING_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}


def _abort(reason: str) -> None:
    raise RuntimeError(f"{SCRIPT_PREFIX}|abort|reason={reason}")


def _money(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _local_start(session_obj: CourseSession) -> datetime:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))


def _target_rows(
    db,
    *,
    student_id: UUID,
    course_type_id: UUID,
    location_id: UUID,
    weekday: int,
    start_time: time,
) -> list[tuple[Booking, CourseSession]]:
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == student_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            CourseSession.course_type_id == course_type_id,
            CourseSession.location_id == location_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= datetime(2026, 8, 1, tzinfo=timezone.utc),
            CourseSession.start_at_utc < datetime(2027, 7, 15, tzinfo=timezone.utc),
        )
        .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
        .with_for_update()
    ).all()
    return [
        (booking, session_obj)
        for booking, session_obj in rows
        if _local_start(session_obj).weekday() == weekday
        and _local_start(session_obj).timetz().replace(tzinfo=None, second=0, microsecond=0) == start_time
    ]


def _quote(db, *, quote_id: UUID, quote_number: str) -> Quote:
    quote = db.scalar(select(Quote).where(Quote.id == quote_id).with_for_update())
    if quote is None or quote.quote_number != quote_number:
        _abort(f"quote_guard_failed_{quote_id}")
    if (quote.school_year_label or "").strip() != SCHOOL_YEAR or (quote.status or "").lower() != "approved":
        _abort(f"quote_state_guard_failed_{quote_number}_{quote.status}_{quote.school_year_label}")
    return quote


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
            .order_by(ClientInvoiceLine.occurred_at.asc(), ClientInvoiceLine.id.asc())
            .with_for_update()
        ).all()
    )
    note_ids = {line.note_id for line in course_lines}
    if len(note_ids) != 1:
        _abort(f"yaz_invoice_note_count_{len(note_ids)}")
    note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == next(iter(note_ids))).with_for_update())
    if note is None:
        _abort("yaz_invoice_note_missing")
    metadata = _parse_invoice_range_note_entry(note)
    if str(metadata.get("invoice_number") or "") != YAZ_INVOICE_NUMBER:
        _abort(f"yaz_invoice_number_{metadata.get('invoice_number')}")
    if str(metadata.get("invoice_status") or "").strip().upper() != "ISSUED":
        _abort(f"yaz_invoice_status_{metadata.get('invoice_status')}")
    all_lines = list(
        db.scalars(
            select(ClientInvoiceLine)
            .where(ClientInvoiceLine.note_id == note.id)
            .order_by(ClientInvoiceLine.occurred_at.asc(), ClientInvoiceLine.id.asc())
            .with_for_update()
        ).all()
    )
    return note, metadata, course_lines, all_lines


def _allocated_cents(total: Decimal, count: int) -> list[Decimal]:
    cents = int((_money(total) * 100).to_integral_exact())
    base, remainder = divmod(cents, count)
    return [Decimal(base + (1 if index < remainder else 0)) / 100 for index in range(count)]


def _ensure_confirmation(
    db,
    *,
    quote_id: UUID,
    student_id: UUID,
    series_id: UUID,
    expected_sessions: int,
    booked_sessions: int,
    confirmation_key: str,
    reason: str,
    details: dict[str, object],
) -> bool:
    existing = db.scalar(
        select(QuoteEvent.id).where(
            QuoteEvent.quote_id == quote_id,
            QuoteEvent.event_type == "quote_planning_variance_confirmed",
            QuoteEvent.payload["confirmation_key"].astext == confirmation_key,
        )
    )
    if existing is not None:
        return False
    db.add(
        QuoteEvent(
            quote_id=quote_id,
            event_type="quote_planning_variance_confirmed",
            actor_type="admin",
            actor_id=None,
            payload={
                "confirmation_key": confirmation_key,
                "student_id": str(student_id),
                "series_id": str(series_id),
                "expected_sessions": expected_sessions,
                "booked_sessions": booked_sessions,
                "reason": reason,
                "details": details,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    return True


def _repair_yaz(db, *, now: datetime, apply: bool) -> dict[str, object]:
    quote = _quote(db, quote_id=YAZ_QUOTE_ID, quote_number=YAZ_QUOTE_NUMBER)
    quote_lines = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id).with_for_update()).all())
    masterclass_lines = [line for line in quote_lines if line.activity_id == MASTERCLASS_ID]
    if len(masterclass_lines) != 1:
        _abort(f"yaz_quote_masterclass_line_count_{len(masterclass_lines)}")
    quote_line = masterclass_lines[0]
    if _money(quote.total_ttc) != YAZ_DOCUMENT_TOTAL:
        _abort(f"yaz_quote_total_{quote.total_ttc}")
    if _money(quote_line.quantity) != Decimal("14.00") or _money(quote_line.amount_ttc) != YAZ_MASTERCLASS_TOTAL:
        _abort(f"yaz_quote_masterclass_amount_{quote_line.quantity}_{quote_line.amount_ttc}")

    active_rows = _target_rows(
        db,
        student_id=YAZ_STUDENT_ID,
        course_type_id=MASTERCLASS_ID,
        location_id=RICHELIEU_ID,
        weekday=5,
        start_time=time(9, 0),
    )
    cancelled_extra = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == YAZ_STUDENT_ID,
            Booking.status == BookingStatus.CANCELLED,
            Booking.cancellation_reason == "ADMIN_REMOVED_QUOTE_CORRECTION",
            CourseSession.course_type_id == MASTERCLASS_ID,
        )
    ).first()

    if len(active_rows) == YAZ_EXPECTED_COUNT and cancelled_extra is not None:
        active_ids = {booking.id for booking, _ in active_rows}
        note, _, course_invoice_lines, all_invoice_lines = _invoice_context(db, booking_ids=active_ids)
        if len(course_invoice_lines) != YAZ_EXPECTED_COUNT:
            _abort(f"yaz_repaired_invoice_line_count_{len(course_invoice_lines)}")
        if sum((_money(line.total_incl_vat) for line in course_invoice_lines), Decimal("0.00")) != YAZ_MASTERCLASS_TOTAL:
            _abort("yaz_repaired_masterclass_total")
        if sum((_money(line.total_incl_vat) for line in all_invoice_lines), Decimal("0.00")) != YAZ_DOCUMENT_TOTAL:
            _abort("yaz_repaired_invoice_total")
        return {"status": "already_repaired", "active_bookings": len(active_rows), "invoice_note_id": str(note.id)}

    if len(active_rows) != YAZ_EXPECTED_COUNT + 1:
        _abort(f"yaz_active_masterclass_count_{len(active_rows)}")
    recurrence_ids = {session_obj.recurrence_group_id for _, session_obj in active_rows}
    if None in recurrence_ids or len(recurrence_ids) != 1:
        _abort(f"yaz_recurrence_group_count_{len(recurrence_ids)}")
    by_date = {_local_start(session_obj).date(): (booking, session_obj) for booking, session_obj in active_rows}
    if YAZ_EXTRA_DATE not in by_date:
        _abort("yaz_extra_date_missing")
    expected_dates = sorted(value for value in by_date if value != YAZ_EXTRA_DATE)
    if len(expected_dates) != YAZ_EXPECTED_COUNT or expected_dates[-1] != date(2027, 5, 29):
        _abort(f"yaz_expected_dates_guard_{expected_dates}")

    booking_ids = {booking.id for booking, _ in active_rows}
    note, metadata, course_invoice_lines, all_invoice_lines = _invoice_context(db, booking_ids=booking_ids)
    if len(course_invoice_lines) != YAZ_EXPECTED_COUNT + 1:
        _abort(f"yaz_invoice_masterclass_line_count_{len(course_invoice_lines)}")
    if sum((_money(line.total_incl_vat) for line in course_invoice_lines), Decimal("0.00")) != YAZ_MASTERCLASS_TOTAL:
        _abort("yaz_masterclass_total_before")
    if sum((_money(line.total_incl_vat) for line in all_invoice_lines), Decimal("0.00")) != YAZ_DOCUMENT_TOTAL:
        _abort("yaz_invoice_total_before")

    extra_booking, _ = by_date[YAZ_EXTRA_DATE]
    extra_invoice_lines = [line for line in course_invoice_lines if line.source_payment_id == extra_booking.id]
    if len(extra_invoice_lines) != 1:
        _abort(f"yaz_extra_invoice_line_count_{len(extra_invoice_lines)}")
    receipt_count = len(list(db.scalars(select(PaymentReceipt.id).where(PaymentReceipt.booking_id == extra_booking.id)).all()))
    if receipt_count:
        _abort(f"yaz_extra_booking_has_payment_receipts_{receipt_count}")

    summary = {
        "status": "ready",
        "active_bookings_before": len(active_rows),
        "active_bookings_after": YAZ_EXPECTED_COUNT,
        "removed_date": YAZ_EXTRA_DATE.isoformat(),
        "masterclass_total": str(YAZ_MASTERCLASS_TOTAL),
        "document_total": str(YAZ_DOCUMENT_TOTAL),
    }
    if not apply:
        return summary

    remaining_rows = [(booking, session_obj) for booking, session_obj in active_rows if booking.id != extra_booking.id]
    ht_allocations = _allocated_cents(_money(quote_line.amount_ht), YAZ_EXPECTED_COUNT)
    vat_allocations = list(reversed(_allocated_cents(_money(quote_line.amount_vat), YAZ_EXPECTED_COUNT)))
    line_by_booking = {line.source_payment_id: line for line in course_invoice_lines}
    for index, (booking, session_obj) in enumerate(remaining_rows):
        ht = ht_allocations[index]
        vat = vat_allocations[index]
        if ht + vat != Decimal("200.00"):
            _abort(f"yaz_unit_allocation_{index}_{ht}_{vat}")
        booking.price_excl_vat_snapshot = ht
        booking.vat_rate_snapshot = quote_line.vat_rate
        booking.vat_amount_snapshot = vat
        booking.total_incl_vat_snapshot = Decimal("200.00")
        booking.currency_snapshot = quote.currency
        booking.pricing_snapshot_locked = True
        db.add(booking)
        invoice_line = line_by_booking[booking.id]
        invoice_line.occurred_at = session_obj.start_at_utc
        invoice_line.amount_excl_vat = ht
        invoice_line.vat_rate = quote_line.vat_rate
        invoice_line.vat_amount = vat
        invoice_line.total_incl_vat = Decimal("200.00")
        invoice_line.currency = quote.currency
        db.add(invoice_line)

    extra_booking.status = BookingStatus.CANCELLED
    extra_booking.cancelled_at = now
    extra_booking.cancellation_reason = "ADMIN_REMOVED_QUOTE_CORRECTION"
    db.add(extra_booking)
    skip_pending_reminders_for_booking(
        db,
        booking_id=extra_booking.id,
        reason="Extra Masterclass removed to match accepted quote",
        now=now,
    )
    cancel_pending_booking_reminder_notifications(
        db,
        booking_id=extra_booking.id,
        reason="Extra Masterclass removed to match accepted quote",
        now=now,
    )
    db.delete(extra_invoice_lines[0])

    included_keys = [str(value) for value in metadata.get("included_payment_keys") or []]
    excluded_key = f"BOOKING:{extra_booking.id}"
    metadata["included_payment_keys"] = [value for value in included_keys if value != excluded_key]
    metadata["private_note"] = (
        f"{str(metadata.get('private_note') or '').strip()} "
        "Répartition corrigée le 30/08/2026 : 14 Masterclass à 200 EUR, total inchangé."
    ).strip()
    note.message = _build_invoice_range_note_message(metadata)
    db.add(note)

    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="planning_invoice_allocation_repaired",
            actor_type="system",
            actor_id=None,
            payload={
                "student_id": str(YAZ_STUDENT_ID),
                "invoice_number": YAZ_INVOICE_NUMBER,
                "before": {"masterclass_bookings": 15, "masterclass_total": "2800.00"},
                "after": {"masterclass_bookings": 14, "unit_ttc": "200.00", "masterclass_total": "2800.00"},
                "removed_date": YAZ_EXTRA_DATE.isoformat(),
                "document_total": "5216.00",
                "email_sent": False,
            },
        )
    )
    db.add(
        DomainEvent(
            event_type="masterclass_quote_invoice_allocation_repaired",
            source="admin_repair",
            actor_type="system",
            actor_id=None,
            related_entity_type="student",
            related_entity_id=YAZ_STUDENT_ID,
            occurred_at=now,
            payload_json={
                "quote_number": YAZ_QUOTE_NUMBER,
                "invoice_number": YAZ_INVOICE_NUMBER,
                "cancelled_booking_id": str(extra_booking.id),
                "removed_date": YAZ_EXTRA_DATE.isoformat(),
                "masterclass_total": "2800.00",
                "document_total": "5216.00",
            },
        )
    )
    db.flush()

    final_rows = _target_rows(
        db,
        student_id=YAZ_STUDENT_ID,
        course_type_id=MASTERCLASS_ID,
        location_id=RICHELIEU_ID,
        weekday=5,
        start_time=time(9, 0),
    )
    final_ids = {booking.id for booking, _ in final_rows}
    final_lines = list(
        db.scalars(
            select(ClientInvoiceLine).where(
                ClientInvoiceLine.note_id == note.id,
                ClientInvoiceLine.source == "BOOKING",
                ClientInvoiceLine.source_payment_id.in_(final_ids),
            )
        ).all()
    )
    final_all_lines = list(db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id == note.id)).all())
    if len(final_rows) != YAZ_EXPECTED_COUNT or len(final_lines) != YAZ_EXPECTED_COUNT:
        _abort("yaz_postcheck_count")
    if any(_money(booking.total_incl_vat_snapshot) != Decimal("200.00") for booking, _ in final_rows):
        _abort("yaz_postcheck_booking_unit")
    if sum((_money(line.total_incl_vat) for line in final_lines), Decimal("0.00")) != YAZ_MASTERCLASS_TOTAL:
        _abort("yaz_postcheck_masterclass_total")
    if sum((_money(line.total_incl_vat) for line in final_all_lines), Decimal("0.00")) != YAZ_DOCUMENT_TOTAL:
        _abort("yaz_postcheck_document_total")
    return {**summary, "status": "repaired"}


def _document_confirmed_variances(db, *, apply: bool) -> dict[str, object]:
    daniel_quote = _quote(db, quote_id=DANIEL_QUOTE_ID, quote_number="DV-20260602064635-72E0")
    daniel_rows = _target_rows(
        db,
        student_id=DANIEL_STUDENT_ID,
        course_type_id=MASTERCLASS_ID,
        location_id=RICHELIEU_ID,
        weekday=5,
        start_time=time(14, 0),
    )
    if len(daniel_rows) != 14:
        _abort(f"daniel_masterclass_count_{len(daniel_rows)}")
    daniel_series = {session_obj.recurrence_group_id for _, session_obj in daniel_rows}
    if None in daniel_series or len(daniel_series) != 1:
        _abort("daniel_series_guard")

    victoria_quote = _quote(db, quote_id=VICTORIA_QUOTE_ID, quote_number="DV-20260512094758-E181")
    victoria_rows = _target_rows(
        db,
        student_id=VICTORIA_STUDENT_ID,
        course_type_id=SOLFEGE_LEVEL_3_ID,
        location_id=ONLINE_ID,
        weekday=0,
        start_time=time(18, 5),
    )
    if len(victoria_rows) != 26:
        _abort(f"victoria_solfege3_count_{len(victoria_rows)}")
    victoria_series = {session_obj.recurrence_group_id for _, session_obj in victoria_rows}
    if None in victoria_series or len(victoria_series) != 1:
        _abort("victoria_series_guard")

    summary = {
        "daniel_masterclass": len(daniel_rows),
        "victoria_solfege_level": 3,
        "events_created": 0,
    }
    if not apply:
        return summary

    created = 0
    created += int(
        _ensure_confirmation(
            db,
            quote_id=daniel_quote.id,
            student_id=DANIEL_STUDENT_ID,
            series_id=next(iter(daniel_series)),
            expected_sessions=15,
            booked_sessions=14,
            confirmation_key="daniel-masterclass-14-confirmed-20260830",
            reason="Volume Masterclass confirmé à 14 séances",
            details={"activity_id": str(MASTERCLASS_ID), "location_id": str(RICHELIEU_ID)},
        )
    )
    created += int(
        _ensure_confirmation(
            db,
            quote_id=victoria_quote.id,
            student_id=VICTORIA_STUDENT_ID,
            series_id=next(iter(victoria_series)),
            expected_sessions=26,
            booked_sessions=26,
            confirmation_key="victoria-solfege-level-3-confirmed-20260830",
            reason="Solfège niveau 3 confirmé",
            details={
                "accepted_snapshot_activity_id": str(SOLFEGE_LEVEL_2_ID),
                "confirmed_activity_id": str(SOLFEGE_LEVEL_3_ID),
                "location_id": str(ONLINE_ID),
            },
        )
    )
    summary["events_created"] = created
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair confirmed Masterclass planning and invoice variances.")
    parser.add_argument("--apply", action="store_true", help="Commit the guarded repair. Default is dry-run.")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        yaz = _repair_yaz(db, now=now, apply=args.apply)
        documented = _document_confirmed_variances(db, apply=args.apply)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(
            f"{SCRIPT_PREFIX}|summary|result={'applied' if args.apply else 'dry_run'}|"
            f"yaz_status={yaz['status']}|yaz_bookings={yaz.get('active_bookings_after', yaz.get('active_bookings'))}|"
            f"masterclass_total={yaz.get('masterclass_total', '2800.00')}|document_total={yaz.get('document_total', '5216.00')}|"
            f"daniel_masterclass={documented['daniel_masterclass']}|victoria_solfege_level={documented['victoria_solfege_level']}|"
            f"events_created={documented['events_created']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
