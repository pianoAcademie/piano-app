from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry, PaymentReceipt
from app.models.user import User
from app.services.payment_receipts import (
    _parse_invoice_range_note_entry,
    build_booking_receipt_snapshot,
    get_or_create_pending_booking_payment_receipt,
    is_final_booking_invoice_metadata,
    is_single_booking_invoice_scope,
)

SCRIPT_PREFIX = "PROD_FUTURE_BOOKING_INVOICE_CLEANUP"


def _reconciled_manual_payment_ids(metadata: dict[str, object]) -> list[UUID]:
    values = metadata.get("reconciled_manual_payment_ids")
    if not isinstance(values, list):
        return []
    out: list[UUID] = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            out.append(UUID(raw))
        except ValueError:
            continue
    return out


def _invoice_label(note: ClientNoteEntry, metadata: dict[str, object]) -> str:
    invoice_number = str(metadata.get("invoice_number") or "").strip()
    if invoice_number:
        return invoice_number
    return str(note.id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove buggy booking invoices that were emitted before the booked service was completed, "
            "then recreate a clean pending payment receipt for the affected booking."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the cleanup in the database. Without this flag, run in dry-run mode only.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.execute(
            select(ClientInvoiceLine, ClientNoteEntry, Booking, CourseSession, CourseType, Location, User)
            .join(ClientNoteEntry, ClientNoteEntry.id == ClientInvoiceLine.note_id)
            .join(Booking, Booking.id == ClientInvoiceLine.source_payment_id)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(User, User.id == Booking.user_id)
            .where(ClientInvoiceLine.source == "BOOKING")
            .order_by(CourseSession.start_at_utc.asc(), ClientNoteEntry.created_at.asc(), ClientNoteEntry.id.asc())
        ).all()

        seen_note_ids: set[UUID] = set()
        summary = Counter()
        samples: list[str] = []

        for invoice_line, note, booking, session_obj, course_type, location, owner in rows:
            if note.id in seen_note_ids:
                continue
            seen_note_ids.add(note.id)

            metadata = _parse_invoice_range_note_entry(note)
            if metadata is None:
                continue
            if is_final_booking_invoice_metadata(metadata):
                continue
            if not is_single_booking_invoice_scope(metadata):
                continue
            if session_obj.status == SessionStatus.COMPLETED:
                continue

            invoice_number = _invoice_label(note, metadata)
            tx_ids = _reconciled_manual_payment_ids(metadata)
            pending_receipt_ids = db.scalars(
                select(PaymentReceipt.id).where(
                    PaymentReceipt.booking_id == booking.id,
                    PaymentReceipt.status == "PENDING",
                    PaymentReceipt.final_invoice_note_id.is_(None),
                )
            ).all()

            summary["problematic_notes"] += 1
            summary["problematic_bookings"] += 1
            summary["linked_manual_transactions"] += len(tx_ids)
            summary["stale_pending_receipts"] += len(pending_receipt_ids)
            sample = (
                f"{invoice_number}|booking={booking.id}|session={session_obj.id}|"
                f"session_status={session_obj.status.value if hasattr(session_obj.status, 'value') else session_obj.status}|"
                f"start={session_obj.start_at_utc.isoformat()}|activity={course_type.name}|location={location.name}"
            )
            samples.append(sample)

            if not args.apply:
                continue

            if pending_receipt_ids:
                db.execute(delete(PaymentReceipt).where(PaymentReceipt.id.in_(pending_receipt_ids)))

            if tx_ids:
                db.execute(
                    delete(ClientManualTransaction).where(
                        ClientManualTransaction.id.in_(tx_ids),
                        ClientManualTransaction.category == "INVOICE_RANGE_PUBLIC_PAYMENT",
                    )
                )

            db.execute(delete(ClientInvoiceLine).where(ClientInvoiceLine.note_id == note.id))
            db.execute(delete(ClientNoteEntry).where(ClientNoteEntry.id == note.id))

            snapshot = build_booking_receipt_snapshot(
                db,
                booking=booking,
                session_obj=session_obj,
                course_type=course_type,
                location=location,
                owner=owner,
            )
            get_or_create_pending_booking_payment_receipt(
                db,
                booking=booking,
                snapshot=snapshot,
            )
            summary["pending_receipts_recreated"] += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] problematic_notes={summary['problematic_notes']}")
    print(f"[{SCRIPT_PREFIX}] problematic_bookings={summary['problematic_bookings']}")
    print(f"[{SCRIPT_PREFIX}] linked_manual_transactions={summary['linked_manual_transactions']}")
    print(f"[{SCRIPT_PREFIX}] stale_pending_receipts={summary['stale_pending_receipts']}")
    print(f"[{SCRIPT_PREFIX}] pending_receipts_recreated={summary['pending_receipts_recreated']}")
    for sample in samples[:20]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")


if __name__ == "__main__":
    main()
