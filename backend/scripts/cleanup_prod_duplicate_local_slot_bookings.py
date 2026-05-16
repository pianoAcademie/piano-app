from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, PaymentReceipt
from app.models.user import User
from app.services.reminders import skip_pending_reminders_for_booking

SCRIPT_PREFIX = "PROD_DUPLICATE_LOCAL_SLOT_BOOKING_CLEANUP"
DEFAULT_START_DATE = date(2026, 9, 1)
BOOKING_CLEANUP_REASON = "DUPLICATE_LOCAL_SLOT_QUOTE_TRANSFORMATION_CLEANUP"


@dataclass(frozen=True)
class BookingRow:
    booking: Booking
    session: CourseSession
    course_type: CourseType
    location: Location
    user: User
    invoice_lines_count: int
    unsafe_receipts_count: int
    pending_receipts_count: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_slot_key(row: BookingRow) -> tuple[object, ...]:
    zone = _safe_zoneinfo(row.session.timezone or row.location.timezone)
    local_start = row.session.start_at_utc.astimezone(zone).replace(tzinfo=None, second=0, microsecond=0)
    local_end = row.session.end_at_utc.astimezone(zone).replace(tzinfo=None, second=0, microsecond=0)
    return (
        row.booking.user_id,
        row.session.course_type_id,
        row.session.location_id,
        row.session.timezone or row.location.timezone or "UTC",
        local_start,
        local_end,
    )


def _display_name(user: User) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part) or user.email


def _is_unsafe_to_cancel(row: BookingRow) -> bool:
    return row.invoice_lines_count > 0 or row.unsafe_receipts_count > 0


def _keeper_sort_key(row: BookingRow) -> tuple[int, int, datetime, str]:
    # Keep rows already linked to accounting artifacts first, then confirmed rows,
    # then the oldest booking. Duplicates after that can be cancelled safely.
    unsafe_rank = 0 if _is_unsafe_to_cancel(row) else 1
    status_rank = 0 if row.booking.status == BookingStatus.BOOKED else 1
    return (unsafe_rank, status_rank, row.booking.booked_at, str(row.booking.id))


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _expire_pending_receipts(db, *, booking_id: UUID, now: datetime) -> int:
    receipts = db.scalars(
        select(PaymentReceipt)
        .where(
            PaymentReceipt.booking_id == booking_id,
            PaymentReceipt.status == "PENDING",
            PaymentReceipt.final_invoice_note_id.is_(None),
        )
        .with_for_update()
    ).all()
    for receipt in receipts:
        metadata = dict(receipt.receipt_metadata or {})
        metadata["cleanup_reason"] = BOOKING_CLEANUP_REASON
        metadata["expired_at"] = now.isoformat()
        receipt.status = "EXPIRED"
        receipt.receipt_metadata = metadata
        receipt.updated_at = now
        db.add(receipt)
    return len(receipts)


def run_cleanup(*, apply: bool = False, start_date: date = DEFAULT_START_DATE) -> Counter:
    start_utc = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    now = _utcnow()

    invoice_count_subquery = (
        select(func.count(ClientInvoiceLine.id))
        .where(
            ClientInvoiceLine.source == "BOOKING",
            ClientInvoiceLine.source_payment_id == Booking.id,
        )
        .correlate(Booking)
        .scalar_subquery()
    )
    unsafe_receipt_count_subquery = (
        select(func.count(PaymentReceipt.id))
        .where(
            PaymentReceipt.booking_id == Booking.id,
            (
                (PaymentReceipt.status != "PENDING")
                | PaymentReceipt.final_invoice_note_id.is_not(None)
                | PaymentReceipt.paid_at.is_not(None)
                | (PaymentReceipt.amount_paid > 0)
            ),
        )
        .correlate(Booking)
        .scalar_subquery()
    )
    pending_receipt_count_subquery = (
        select(func.count(PaymentReceipt.id))
        .where(
            PaymentReceipt.booking_id == Booking.id,
            PaymentReceipt.status == "PENDING",
            PaymentReceipt.final_invoice_note_id.is_(None),
        )
        .correlate(Booking)
        .scalar_subquery()
    )

    with SessionLocal() as db:
        rows = db.execute(
            select(
                Booking,
                CourseSession,
                CourseType,
                Location,
                User,
                invoice_count_subquery.label("invoice_lines_count"),
                unsafe_receipt_count_subquery.label("unsafe_receipts_count"),
                pending_receipt_count_subquery.label("pending_receipts_count"),
            )
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.status.in_([BookingStatus.BOOKED, BookingStatus.PENDING_PAYMENT]),
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= start_utc,
            )
            .order_by(User.last_name.asc(), User.first_name.asc(), CourseSession.start_at_utc.asc(), Booking.booked_at.asc())
            .with_for_update()
        ).all()

        grouped: dict[tuple[object, ...], list[BookingRow]] = defaultdict(list)
        for booking, session_obj, course_type, location, user, invoice_count, unsafe_receipt_count, pending_receipt_count in rows:
            row = BookingRow(
                booking=booking,
                session=session_obj,
                course_type=course_type,
                location=location,
                user=user,
                invoice_lines_count=int(invoice_count or 0),
                unsafe_receipts_count=int(unsafe_receipt_count or 0),
                pending_receipts_count=int(pending_receipt_count or 0),
            )
            grouped[_local_slot_key(row)].append(row)

        summary = Counter()
        samples: list[str] = []
        blocked_samples: list[str] = []
        amount_cancelled = Decimal("0.00")

        duplicate_groups = [items for items in grouped.values() if len(items) > 1]
        for items in duplicate_groups:
            items.sort(key=_keeper_sort_key)
            keeper = items[0]
            duplicate_rows = items[1:]
            summary["duplicate_groups"] += 1
            summary["duplicate_bookings_detected"] += len(duplicate_rows)

            zone = _safe_zoneinfo(keeper.session.timezone or keeper.location.timezone)
            local_start = keeper.session.start_at_utc.astimezone(zone)
            sample_prefix = (
                f"client={_display_name(keeper.user)}|email={keeper.user.email}|"
                f"activity={keeper.course_type.name}|location={keeper.location.name}|"
                f"slot={local_start.strftime('%Y-%m-%d %H:%M')}|"
                f"keep_booking={keeper.booking.id}"
            )
            samples.append(
                f"{sample_prefix}|duplicates={len(duplicate_rows)}|"
                f"duplicate_total={sum(_money(row.booking.total_incl_vat_snapshot) for row in duplicate_rows)}"
            )

            for row in duplicate_rows:
                if _is_unsafe_to_cancel(row):
                    summary["blocked_duplicate_bookings"] += 1
                    blocked_samples.append(
                        f"{sample_prefix}|blocked_booking={row.booking.id}|"
                        f"invoice_lines={row.invoice_lines_count}|unsafe_receipts={row.unsafe_receipts_count}"
                    )
                    continue

                summary["safe_duplicate_bookings"] += 1
                amount_cancelled += _money(row.booking.total_incl_vat_snapshot)
                if not apply:
                    continue

                row.booking.status = BookingStatus.CANCELLED
                row.booking.cancelled_at = now
                row.booking.cancellation_reason = BOOKING_CLEANUP_REASON
                row.booking.payment_hold_expires_at = None
                db.add(row.booking)
                summary["cancelled_duplicate_bookings"] += 1
                summary["skipped_reminders"] += skip_pending_reminders_for_booking(
                    db,
                    booking_id=row.booking.id,
                    reason=BOOKING_CLEANUP_REASON,
                    now=now,
                )
                summary["expired_pending_receipts"] += _expire_pending_receipts(db, booking_id=row.booking.id, now=now)

        if apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] start_date={start_date.isoformat()}")
    print(f"[{SCRIPT_PREFIX}] duplicate_groups={summary['duplicate_groups']}")
    print(f"[{SCRIPT_PREFIX}] duplicate_bookings_detected={summary['duplicate_bookings_detected']}")
    print(f"[{SCRIPT_PREFIX}] safe_duplicate_bookings={summary['safe_duplicate_bookings']}")
    print(f"[{SCRIPT_PREFIX}] blocked_duplicate_bookings={summary['blocked_duplicate_bookings']}")
    print(f"[{SCRIPT_PREFIX}] cancelled_duplicate_bookings={summary['cancelled_duplicate_bookings']}")
    print(f"[{SCRIPT_PREFIX}] expired_pending_receipts={summary['expired_pending_receipts']}")
    print(f"[{SCRIPT_PREFIX}] skipped_reminders={summary['skipped_reminders']}")
    print(f"[{SCRIPT_PREFIX}] amount_removed_from_pending_balance={amount_cancelled}")
    for sample in samples[:50]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")
    for sample in blocked_samples[:50]:
        print(f"[{SCRIPT_PREFIX}] blocked={sample}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Find active bookings duplicated on the exact same local student/course/location slot "
            "and cancel the safe duplicate rows created by quote transformation overmatching."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Apply the cleanup. Without this flag, dry-run only.")
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE.isoformat(),
        help=f"Only inspect sessions starting on or after this date (default: {DEFAULT_START_DATE.isoformat()}).",
    )
    args = parser.parse_args()

    try:
        start_date = date.fromisoformat(str(args.start_date))
    except ValueError as exc:
        raise SystemExit(f"--start-date must be YYYY-MM-DD, got {args.start_date!r}") from exc

    run_cleanup(apply=args.apply, start_date=start_date)


if __name__ == "__main__":
    main()
