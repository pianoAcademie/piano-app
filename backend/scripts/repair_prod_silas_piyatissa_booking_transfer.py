from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import (
    Booking,
    BookingReorganizationLink,
    BookingStatus,
    CourseSession,
)
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.user import User, UserRole


SCRIPT_PREFIX = "PROD_REPAIR_SILAS_PIYATISSA_BOOKING_TRANSFER"
TARGET_FIRST_NAME = "silas"
TARGET_LAST_NAME = "piyatissa"
SOURCE_WEEKDAY = 2  # Wednesday
SOURCE_HOUR = 17
TARGET_WEEKDAY = 5  # Saturday
TARGET_HOUR = 12
START_UTC = datetime(2026, 8, 26, tzinfo=timezone.utc)
END_UTC = datetime(2027, 8, 31, tzinfo=timezone.utc)
ACTIVE_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}


@dataclass(frozen=True)
class BookingSession:
    booking: Booking
    session: CourseSession


def _local_start(row: BookingSession) -> datetime:
    return row.session.start_at_utc.astimezone(ZoneInfo(row.session.timezone or "Europe/Paris"))


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _copy_price(source: Booking, target: Booking) -> None:
    target.price_excl_vat_snapshot = source.price_excl_vat_snapshot
    target.vat_rate_snapshot = source.vat_rate_snapshot
    target.vat_amount_snapshot = source.vat_amount_snapshot
    target.total_incl_vat_snapshot = source.total_incl_vat_snapshot
    target.currency_snapshot = source.currency_snapshot
    target.pricing_snapshot_locked = True


def _nearest_target(source: BookingSession, targets: list[BookingSession]) -> BookingSession | None:
    source_local = _local_start(source)
    candidates = [
        target
        for target in targets
        if target.booking.client_plan_subscription_id in {
            None,
            source.booking.client_plan_subscription_id,
        }
        and abs((_local_start(target).date() - source_local.date()).days) <= 14
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda target: (
            abs((_local_start(target).date() - source_local.date()).days),
            _local_start(target),
            str(target.booking.id),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transfer Silas Piyatissa's paid Wednesday coverage to his real Saturday lessons."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    parser.add_argument("--student-id", type=UUID, help="Optional explicit student id safety override.")
    args = parser.parse_args()

    with SessionLocal() as db:
        stmt = select(User).where(User.role == UserRole.CLIENT)
        if args.student_id is not None:
            stmt = stmt.where(User.id == args.student_id)
        else:
            stmt = stmt.where(
                func.lower(func.coalesce(User.first_name, "")) == TARGET_FIRST_NAME,
                func.lower(func.coalesce(User.last_name, "")) == TARGET_LAST_NAME,
            )
        students = db.scalars(stmt.with_for_update()).all()
        if len(students) != 1:
            raise SystemExit(f"[{SCRIPT_PREFIX}] expected_one_student found={len(students)}")
        student = students[0]

        rows = [
            BookingSession(booking=booking, session=session_obj)
            for booking, session_obj in db.execute(
                select(Booking, CourseSession)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == student.id,
                    CourseSession.start_at_utc >= START_UTC,
                    CourseSession.start_at_utc < END_UTC,
                )
                .order_by(CourseSession.start_at_utc, Booking.id)
                .with_for_update()
            ).all()
        ]
        paid_invoice_booking_ids: set[UUID] = set()
        invoice_rows = db.execute(
            select(ClientInvoiceLine.source_payment_id, ClientNoteEntry.message)
            .join(ClientNoteEntry, ClientNoteEntry.id == ClientInvoiceLine.note_id)
            .where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_([row.booking.id for row in rows]),
            )
        ).all()
        for booking_id, note_message in invoice_rows:
            marker = "INVOICE_RANGE::"
            marker_index = (note_message or "").find(marker)
            if marker_index < 0:
                continue
            try:
                metadata = json.loads((note_message or "")[marker_index + len(marker) :].strip())
            except (TypeError, ValueError):
                continue
            if not isinstance(metadata, dict):
                continue
            if str(metadata.get("invoice_status") or "ISSUED").strip().upper() == "PAID":
                paid_invoice_booking_ids.add(booking_id)

        sources = [
            row
            for row in rows
            if row.booking.id in paid_invoice_booking_ids
            and (
                row.booking.status in ACTIVE_STATUSES
                or (
                    row.booking.status == BookingStatus.CANCELLED
                    and (row.booking.cancellation_reason or "").strip().upper()
                    == "ADMIN_MOVED_TO_ANOTHER_SLOT"
                )
            )
            and _local_start(row).weekday() == SOURCE_WEEKDAY
            and _local_start(row).hour == SOURCE_HOUR
        ]
        targets = [
            row
            for row in rows
            if row.booking.status in ACTIVE_STATUSES
            and _local_start(row).weekday() == TARGET_WEEKDAY
            and _local_start(row).hour == TARGET_HOUR
        ]
        if not sources or not targets:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] missing_candidates sources={len(sources)} targets={len(targets)}"
            )

        existing_links = {
            link.source_booking_id: link
            for link in db.scalars(
                select(BookingReorganizationLink).where(
                    BookingReorganizationLink.source_booking_id.in_([row.booking.id for row in sources])
                )
            ).all()
        }
        if len(targets) > len(sources):
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] insufficient_paid_sources sources={len(sources)} targets={len(targets)}"
            )

        # First give every real Saturday lesson one paid Wednesday source.
        planned: list[tuple[BookingSession, BookingSession]] = []
        unused_sources = list(sources)
        for target in targets:
            target_local = _local_start(target)
            candidates = [
                source
                for source in unused_sources
                if target.booking.client_plan_subscription_id in {
                    None,
                    source.booking.client_plan_subscription_id,
                }
                and abs((_local_start(source).date() - target_local.date()).days) <= 14
            ]
            if not candidates:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] no_paid_source_for_target={target.booking.id}|date={target_local.date()}"
                )
            source = min(
                candidates,
                key=lambda row: (
                    abs((_local_start(row).date() - target_local.date()).days),
                    _local_start(row),
                    str(row.booking.id),
                ),
            )
            unused_sources.remove(source)
            planned.append((source, target))

        # A fixed-price forfait can contain one more source occurrence than
        # the destination series. Attach those absorbed occurrences to the
        # nearest real lesson so they disappear from the operational account.
        for source in unused_sources:
            target = _nearest_target(source, targets)
            if target is None:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] no_target_for_source={source.booking.id}|date={_local_start(source).date()}"
                )
            planned.append((source, target))

        for source, target in planned:
            existing = existing_links.get(source.booking.id)
            if existing is not None and existing.target_booking_id != target.booking.id:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] conflicting_link source={source.booking.id}|existing={existing.target_booking_id}|expected={target.booking.id}"
                )

        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(
            f"[{SCRIPT_PREFIX}] student={student.id}|name={student.first_name} {student.last_name}|"
            f"sources={len(sources)}|targets={len(targets)}|links={len(planned)}"
        )
        for source, target in planned:
            print(
                f"[{SCRIPT_PREFIX}] move={_local_start(source).isoformat()}->{_local_start(target).isoformat()}|"
                f"source={source.booking.id}|target={target.booking.id}|"
                f"price={_money(source.booking.total_incl_vat_snapshot):.2f}->"
                f"{_money(target.booking.total_incl_vat_snapshot):.2f}"
            )

        if not args.apply:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")
            return

        primary_source_by_target: dict[UUID, BookingSession] = {}
        for source, target in planned:
            primary_source_by_target.setdefault(target.booking.id, source)
            if source.booking.status != BookingStatus.CANCELLED:
                source.booking.status = BookingStatus.CANCELLED
                source.booking.cancelled_at = datetime.now(timezone.utc)
                source.booking.cancellation_reason = "ADMIN_MOVED_TO_ANOTHER_SLOT"
            if source.booking.id not in existing_links:
                db.add(
                    BookingReorganizationLink(
                        source_booking_id=source.booking.id,
                        target_booking_id=target.booking.id,
                        financially_neutral=True,
                    )
                )
        for target in targets:
            primary_source = primary_source_by_target.get(target.booking.id)
            if primary_source is not None:
                target.booking.client_plan_subscription_id = primary_source.booking.client_plan_subscription_id
                _copy_price(primary_source.booking, target.booking)
        db.commit()
        print(
            f"[{SCRIPT_PREFIX}] committed=true|links={len(planned)}|"
            f"updated_targets={len(primary_source_by_target)}"
        )


if __name__ == "__main__":
    main()
