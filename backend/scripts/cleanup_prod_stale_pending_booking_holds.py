from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location
from app.models.client_record import PaymentReceipt
from app.models.user import User
from app.services.reminders import skip_pending_reminders_for_booking
from app.services.session_automation import PAYMENT_TIMEOUT_CANCELLATION_REASON

SCRIPT_PREFIX = "PROD_STALE_PENDING_BOOKING_CLEANUP"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean_receipt(receipt: PaymentReceipt, *, now: datetime, reason: str) -> None:
    metadata = dict(receipt.receipt_metadata or {})
    metadata["booking_hold_expired_at"] = now.isoformat()
    metadata["cleanup_reason"] = reason
    receipt.status = "EXPIRED"
    receipt.receipt_metadata = metadata
    receipt.updated_at = now


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Expire stale production pending-payment bookings and pending payment receipts. "
            "This is intended as a manual catch-up when test data or an interrupted worker left "
            "obsolete booking holds in place."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup. Without this flag, run in dry-run mode only.",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=30,
        help="Only clean pending-payment rows older than this many minutes (default: 30).",
    )
    args = parser.parse_args()

    now = utcnow()
    stale_before = now - timedelta(minutes=max(1, int(args.grace_minutes)))

    with SessionLocal() as db:
        rows = db.execute(
            select(Booking, CourseSession, CourseType, Location, User)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.status == BookingStatus.PENDING_PAYMENT,
                Booking.booked_at <= stale_before,
            )
            .order_by(Booking.booked_at.asc(), Booking.id.asc())
            .with_for_update()
        ).all()

        summary = Counter()
        samples: list[str] = []
        cleaned_receipt_ids: set[UUID] = set()

        for booking, session_obj, course_type, location, owner in rows:
            receipts = db.scalars(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.booking_id == booking.id,
                    PaymentReceipt.status == "PENDING",
                    PaymentReceipt.final_invoice_note_id.is_(None),
                )
                .with_for_update()
            ).all()

            summary["stale_bookings"] += 1
            summary["linked_pending_receipts"] += len(receipts)
            samples.append(
                f"booking={booking.id}|member={owner.first_name} {owner.last_name}|email={owner.email}|"
                f"activity={course_type.name}|location={location.name}|"
                f"booked_at={booking.booked_at.isoformat()}|"
                f"hold_expires_at={(booking.payment_hold_expires_at.isoformat() if booking.payment_hold_expires_at else '-')}"
            )

            if not args.apply:
                continue

            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.cancellation_reason = PAYMENT_TIMEOUT_CANCELLATION_REASON
            booking.payment_hold_expires_at = None
            skip_pending_reminders_for_booking(
                db,
                booking_id=str(booking.id),
                reason="Manual stale pending-payment cleanup",
                now=now,
            )
            for receipt in receipts:
                _clean_receipt(receipt, now=now, reason="STALE_PENDING_BOOKING_CLEANUP")
                cleaned_receipt_ids.add(receipt.id)
                summary["expired_receipts_from_bookings"] += 1
                db.add(receipt)

        orphan_receipts = db.scalars(
            select(PaymentReceipt)
            .join(Booking, Booking.id == PaymentReceipt.booking_id)
            .where(
                PaymentReceipt.status == "PENDING",
                PaymentReceipt.final_invoice_note_id.is_(None),
                PaymentReceipt.created_at <= stale_before,
                Booking.status != BookingStatus.PENDING_PAYMENT,
            )
            .with_for_update()
        ).all()

        for receipt in orphan_receipts:
            if receipt.id in cleaned_receipt_ids:
                continue
            summary["orphan_pending_receipts"] += 1
            if not args.apply:
                continue
            _clean_receipt(receipt, now=now, reason="ORPHAN_PENDING_RECEIPT_CLEANUP")
            db.add(receipt)
            summary["expired_orphan_receipts"] += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] now={now.isoformat()}")
    print(f"[{SCRIPT_PREFIX}] stale_before={stale_before.isoformat()}")
    print(f"[{SCRIPT_PREFIX}] stale_bookings={summary['stale_bookings']}")
    print(f"[{SCRIPT_PREFIX}] linked_pending_receipts={summary['linked_pending_receipts']}")
    print(f"[{SCRIPT_PREFIX}] expired_receipts_from_bookings={summary['expired_receipts_from_bookings']}")
    print(f"[{SCRIPT_PREFIX}] orphan_pending_receipts={summary['orphan_pending_receipts']}")
    print(f"[{SCRIPT_PREFIX}] expired_orphan_receipts={summary['expired_orphan_receipts']}")
    for sample in samples[:25]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")


if __name__ == "__main__":
    main()
