from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4

from app.services.bank_transfer_orders import (
    BANK_TRANSFER_ORDER_STATUS_EXPIRED,
    BANK_TRANSFER_ORDER_STATUS_PENDING,
    _build_review_digest_body,
    _latest_review_digest_rows,
    _reviewable_bank_transfer_rows,
)


def _order(
    *,
    reference: str,
    status: str,
    created_at: datetime,
    customer_id: object | None = None,
    invoice_note_id: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        order_reference=reference,
        status=status,
        customer_id=customer_id or uuid4(),
        invoice_note_id=invoice_note_id,
        amount_incl_vat="200.00",
        currency="EUR",
        expires_at=created_at,
        created_at=created_at,
    )


class BankTransferReviewDigestTests(unittest.TestCase):
    def _range_invoice_note(self, *, invoice_number: str, invoice_status: str) -> SimpleNamespace:
        return SimpleNamespace(
            message=(
                f"Facture {invoice_number} generee.\n"
                f'INVOICE_RANGE::{{"invoice_number":"{invoice_number}","invoice_status":"{invoice_status}"}}'
            )
        )

    def test_digest_body_identifies_expired_orders_to_relaunch(self) -> None:
        customer = SimpleNamespace(first_name="Elvira", last_name="Giner", email="elvira@example.com")
        note = SimpleNamespace(message="Facture PA26-0079 generee.")
        expired_order = _order(
            reference="VIR-20260527-524E444B",
            status=BANK_TRANSFER_ORDER_STATUS_EXPIRED,
            created_at=datetime(2026, 5, 27, 16, 7, tzinfo=timezone.utc),
        )

        body = _build_review_digest_body(
            [(expired_order, customer, note)],
            now=datetime(2026, 6, 12, 6, 0, tzinfo=timezone.utc),
        )

        self.assertIn("Expires a relancer", body)
        self.assertIn("VIR-20260527-524E444B", body)
        self.assertIn("Expire - relancer", body)
        self.assertIn("PA26-0079", body)

    def test_digest_keeps_only_latest_order_for_same_invoice(self) -> None:
        customer_id = uuid4()
        invoice_note_id = uuid4()
        customer = SimpleNamespace(first_name="Philippe", last_name="Roch", email="philippe@example.com")
        note = SimpleNamespace(message="Facture PA26-0098 generee.")
        expired_order = _order(
            reference="VIR-OLD",
            status=BANK_TRANSFER_ORDER_STATUS_EXPIRED,
            created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            customer_id=customer_id,
            invoice_note_id=invoice_note_id,
        )
        pending_order = _order(
            reference="VIR-NEW",
            status=BANK_TRANSFER_ORDER_STATUS_PENDING,
            created_at=datetime(2026, 6, 9, 9, 0, tzinfo=timezone.utc),
            customer_id=customer_id,
            invoice_note_id=invoice_note_id,
        )

        rows = _latest_review_digest_rows(
            [(expired_order, customer, note), (pending_order, customer, note)],
            limit=10,
        )

        self.assertEqual([row[0].order_reference for row in rows], ["VIR-NEW"])

    def test_digest_excludes_bank_transfer_when_invoice_is_already_paid(self) -> None:
        customer = SimpleNamespace(first_name="Herve", last_name="Louis", email="herve@example.com")
        paid_note = self._range_invoice_note(invoice_number="PA26-0260", invoice_status="PAID")
        pending_order = _order(
            reference="VIR-20260619-FEC8E25A",
            status=BANK_TRANSFER_ORDER_STATUS_PENDING,
            created_at=datetime(2026, 6, 19, 7, 13, tzinfo=timezone.utc),
        )

        rows = _reviewable_bank_transfer_rows([(pending_order, customer, paid_note)])

        self.assertEqual(rows, [])

    def test_digest_excludes_expired_bank_transfer_when_invoice_is_paid_by_newer_order(self) -> None:
        customer = SimpleNamespace(first_name="Sonia", last_name="Thornton", email="sonia@example.com")
        paid_note = self._range_invoice_note(invoice_number="PA26-0206", invoice_status="PAID")
        expired_order = _order(
            reference="VIR-20260604-8FAF7D53",
            status=BANK_TRANSFER_ORDER_STATUS_EXPIRED,
            created_at=datetime(2026, 6, 4, 10, 14, tzinfo=timezone.utc),
        )

        rows = _reviewable_bank_transfer_rows([(expired_order, customer, paid_note)])

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
