from __future__ import annotations

import argparse
from uuid import UUID

from sqlalchemy import select

from app.api.routes.admin_clients import (
    _parse_invoice_range_note_entry,
    reconcile_admin_client_range_invoice_public_payment_by_provider_reference,
)
from app.db.session import SessionLocal
from app.models.client_record import ClientNoteEntry
from app.services.payment_checkout import lookup_payment
from app.services.payment_provider import detect_provider_from_reference, resolve_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair an invoice payment from a PSP payment reference.")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--note-id", required=True)
    parser.add_argument("--payment-reference", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client_id = UUID(args.client_id)
    note_id = UUID(args.note_id)
    payment_reference = args.payment_reference.strip()
    if not payment_reference:
        raise SystemExit("--payment-reference is required")

    db = SessionLocal()
    try:
        note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == note_id, ClientNoteEntry.user_id == client_id))
        if note is None:
            raise SystemExit("Invoice note not found for this client")
        metadata = _parse_invoice_range_note_entry(note)
        if metadata is None:
            raise SystemExit("Invoice note does not contain invoice range metadata")

        provider = detect_provider_from_reference(payment_reference) or resolve_provider(db)
        lookup = lookup_payment(db, provider=provider, payment_reference=payment_reference)
        print(f"provider={provider.value}")
        print(f"payment_reference={lookup.provider_reference}")
        print(f"payment_status={lookup.status}")
        print(f"payment_paid={lookup.paid}")
        print(f"metadata_client_id={lookup.metadata.get('client_id', '-')}")
        print(f"metadata_note_id={lookup.metadata.get('note_id', '-')}")
        print(f"invoice_number={metadata.get('invoice_number', '-')}")
        print(f"invoice_status_before={metadata.get('invoice_status', 'ISSUED')}")

        if not args.apply:
            print("dry_run=true")
            return

        result = reconcile_admin_client_range_invoice_public_payment_by_provider_reference(
            db,
            client_id=client_id,
            note_id=note_id,
            provider_reference=payment_reference,
            defer_postprocessing=True,
        )
        print(f"result={result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
