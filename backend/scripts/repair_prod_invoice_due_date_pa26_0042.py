from __future__ import annotations

import argparse
import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client_record import ClientNoteEntry
from app.services.payment_receipts import _build_invoice_range_note_message, _parse_invoice_range_note_entry

SCRIPT_PREFIX = "PROD_INVOICE_DUE_DATE_REPAIR"
DEFAULT_INVOICE_NUMBER = "PA26-0042"
DEFAULT_DUE_DATE = "2026-09-01"


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair one stored invoice range due date.")
    parser.add_argument("--invoice-number", default=DEFAULT_INVOICE_NUMBER)
    parser.add_argument("--due-date", default=DEFAULT_DUE_DATE)
    parser.add_argument("--apply", action="store_true", help="Write the repair. Without this flag, dry-run only.")
    args = parser.parse_args()

    invoice_number = args.invoice_number.strip()
    if not invoice_number:
        raise SystemExit("invoice-number is required")
    try:
        due_date = date.fromisoformat(args.due_date.strip()).isoformat()
    except ValueError as exc:
        raise SystemExit(f"Invalid due-date: {args.due_date}") from exc

    with SessionLocal() as db:
        notes = db.scalars(
            select(ClientNoteEntry)
            .where(ClientNoteEntry.message.contains(invoice_number))
            .order_by(ClientNoteEntry.created_at.asc(), ClientNoteEntry.id.asc())
        ).all()
        matches: list[tuple[ClientNoteEntry, dict[str, object]]] = []
        for note in notes:
            metadata = _parse_invoice_range_note_entry(note)
            if metadata is None:
                continue
            if str(metadata.get("invoice_number") or "").strip() == invoice_number:
                matches.append((note, metadata))

        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(f"[{SCRIPT_PREFIX}] invoice_number={invoice_number}")
        print(f"[{SCRIPT_PREFIX}] target_due_date={due_date}")
        print(f"[{SCRIPT_PREFIX}] matches={len(matches)}")

        if len(matches) != 1:
            db.rollback()
            raise SystemExit(f"Expected exactly one invoice match, found {len(matches)}")

        note, metadata = matches[0]
        old_due_date = str(metadata.get("due_date") or "").strip()
        print(f"[{SCRIPT_PREFIX}] note_id={note.id}")
        print(f"[{SCRIPT_PREFIX}] old_due_date={old_due_date}")

        if old_due_date == due_date:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] already_correct=true")
            return

        if args.apply:
            metadata["due_date"] = due_date
            metadata["no_due_date"] = False
            note.message = _build_invoice_range_note_message(metadata)
            db.add(note)
            db.commit()
            print(f"[{SCRIPT_PREFIX}] updated=true")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] would_update=true")


if __name__ == "__main__":
    main()
