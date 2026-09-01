"""Allocate paid deposit PA26-0413 to final invoice PA26-0649. Dry-run by default."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.api.routes.admin_clients import (
    _parse_invoice_range_note_entry,
    _propagate_paid_deposit_to_issued_long_period_invoice,
)
from app.db.session import SessionLocal
from app.models.client_record import ClientManualTransaction, ClientNoteEntry

OWNER_ID = UUID("42b6ef84-248a-43f7-a005-1541d7a1da51")
SOURCE_NOTE_ID = UUID("2b3f2d54-90a7-4e33-bb5a-9cc9c04b7c09")
TARGET_NOTE_ID = UUID("f42fbd4d-d49c-48b1-9300-0ae66a084f0a")
PAYMENT_ID = UUID("0db71725-e976-42e1-8c73-038574065919")


def q2(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        source = db.get(ClientNoteEntry, SOURCE_NOTE_ID)
        target = db.get(ClientNoteEntry, TARGET_NOTE_ID)
        payment = db.get(ClientManualTransaction, PAYMENT_ID)
        source_meta = _parse_invoice_range_note_entry(source) if source else None
        target_before = _parse_invoice_range_note_entry(target) if target else None
        if source_meta is None or target_before is None or payment is None:
            raise SystemExit("Expected source invoice, final invoice or payment is missing")
        if source.user_id != OWNER_ID or target.user_id != OWNER_ID or payment.user_id != OWNER_ID:
            raise SystemExit("Owner guard failed")
        if source_meta.get("invoice_number") != "PA26-0413" or source_meta.get("invoice_status") != "PAID":
            raise SystemExit("Paid deposit invoice guard failed")
        if target_before.get("invoice_number") != "PA26-0649" or target_before.get("invoice_status") != "ISSUED":
            raise SystemExit("Final invoice guard failed")
        if q2((target_before.get("totals_by_currency") or {}).get("EUR")) != Decimal("4465.00"):
            raise SystemExit("Final invoice total guard failed")
        if q2((target_before.get("total_to_pay_by_currency") or {}).get("EUR")) != Decimal("200.00"):
            raise SystemExit("Final invoice outstanding balance guard failed")
        if payment.transaction_type != "PAYMENT" or payment.status != "COMPLETED" or q2(payment.total_incl_vat) != Decimal("-200.00"):
            raise SystemExit("Deposit payment guard failed")

        reconciled_note_id = _propagate_paid_deposit_to_issued_long_period_invoice(
            db,
            owner_client_id=OWNER_ID,
            source_note=source,
            source_metadata=source_meta,
            payment_transaction_id=PAYMENT_ID,
        )
        if reconciled_note_id != TARGET_NOTE_ID:
            raise SystemExit(f"Unique final invoice was not matched: {reconciled_note_id}")
        target_after = _parse_invoice_range_note_entry(target)
        assert target_after is not None
        if q2((target_after.get("total_to_pay_by_currency") or {}).get("EUR")) != Decimal("0.00"):
            raise SystemExit("Final balance did not reach zero")
        if target_after.get("invoice_status") != "PAID":
            raise SystemExit("Final invoice was not marked paid")
        if str(PAYMENT_ID) not in (target_after.get("reconciled_manual_payment_ids") or []):
            raise SystemExit("Deposit payment was not recorded on final invoice")
        result = {
            "apply": args.apply,
            "deposit_invoice": "PA26-0413",
            "final_invoice": "PA26-0649",
            "before_due_eur": "200.00",
            "after_due_eur": "0.00",
            "final_status": "PAID",
            "email_sent": False,
        }
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
