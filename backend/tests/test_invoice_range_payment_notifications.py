from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes import admin_clients
from app.models.client_record import ClientManualTransaction, ClientNoteEntry


class _FakeScalarResult:
    def all(self) -> list[object]:
        return []


class _FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_calls = 0
        self.commit_calls = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_calls += 1
        for item in self.added:
            if isinstance(item, ClientManualTransaction) and item.id is None:
                item.id = uuid4()

    def commit(self) -> None:
        self.commit_calls += 1

    def scalars(self, *_args: object, **_kwargs: object) -> _FakeScalarResult:
        return _FakeScalarResult()


class InvoiceRangePaymentNotificationTests(unittest.TestCase):
    def test_already_paid_reconciliation_is_idempotent(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0296",
            "invoice_status": "PAID",
            "paid_at": "2026-08-08T08:57:00+00:00",
            "payment_transaction_id": str(uuid4()),
        }

        with (
            patch.object(admin_clients, "_require_client"),
            patch.object(admin_clients, "_load_range_invoice_note", return_value=(note, metadata)),
            patch.object(admin_clients, "_invoice_range_metadata_with_display_totals", return_value=metadata),
            patch.object(admin_clients, "lookup_payment") as lookup_payment,
        ):
            result = admin_clients.reconcile_admin_client_range_invoice_public_payment_by_provider_reference(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note_id=note.id,
                provider_reference="pay_paid_123",
                defer_postprocessing=True,
            )

        lookup_payment.assert_not_called()
        self.assertTrue(result["paid"])
        self.assertFalse(result["processed"])
        self.assertEqual(result["reason"], "already_reconciled")
        self.assertEqual(db.commit_calls, 1)

    def test_deferred_payment_commits_before_notifications(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0296",
            "total_to_pay_by_currency": {"EUR": "200.00"},
            "included_payment_keys": [f"BOOKING:{uuid4()}"],
        }

        with (
            patch.object(admin_clients, "_run_invoice_range_payment_notifications") as notifications,
            patch.object(admin_clients, "evaluate_referrals_for_invoice") as referrals,
        ):
            transaction_id, _paid_at = admin_clients._record_invoice_range_public_payment(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note=note,
                metadata=metadata,
                provider_reference="pay_paid_123",
                seller_legal_entity_id=None,
                defer_postprocessing=True,
            )

        notifications.assert_not_called()
        referrals.assert_not_called()
        self.assertIsNotNone(transaction_id)
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["payment_postprocessing_status"], "PENDING")
        self.assertEqual(db.commit_calls, 1)

    def test_multi_booking_invoice_payment_suppresses_individual_booking_confirmations(self) -> None:
        db = _FakeDb()
        client_id = uuid4()
        note = ClientNoteEntry(
            id=uuid4(),
            user_id=client_id,
            entry_type="AUTO",
            message="",
            created_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        metadata: dict[str, object] = {
            "invoice_number": "PA26-0206",
            "total_to_pay_by_currency": {"EUR": "1472.00"},
            "included_payment_keys": [f"BOOKING:{uuid4()}", f"BOOKING:{uuid4()}"],
            "payment_confirmation_emails_sent_at": "2026-06-18T16:00:00+00:00",
            "admin_payment_confirmation_emails_sent_at": "2026-06-18T16:00:00+00:00",
        }

        with (
            patch.object(admin_clients, "_send_invoice_range_booking_confirmation_emails") as send_booking_confirmations,
            patch.object(admin_clients, "evaluate_referrals_for_invoice"),
        ):
            transaction_id, _paid_at = admin_clients._record_invoice_range_public_payment(
                db,  # type: ignore[arg-type]
                client_id=client_id,
                note=note,
                metadata=metadata,
                provider_reference="VIR-20260618-03ECEB6D",
                seller_legal_entity_id=None,
                payment_method_code="BANK_TRANSFER",
                payment_label="Virement bancaire",
                transaction_category="INVOICE_RANGE_BANK_TRANSFER",
                public_note_reference_label="Virement bancaire",
            )

        send_booking_confirmations.assert_not_called()
        self.assertIsNotNone(transaction_id)
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["booking_confirmation_emails_suppressed_reason"], "MULTI_BOOKING_INVOICE_RANGE_PAYMENT")
        self.assertIn("booking_confirmation_emails_sent_at", metadata)
        self.assertEqual(db.commit_calls, 1)
        created_transaction = next(item for item in db.added if isinstance(item, ClientManualTransaction))
        self.assertEqual(created_transaction.total_incl_vat, Decimal("-1472.00"))


if __name__ == "__main__":
    unittest.main()
