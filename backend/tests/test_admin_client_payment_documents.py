from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _apply_invoice_presentation_to_payment_item,
    _should_count_in_client_balance,
    download_admin_client_payment_invoice,
)
from app.schemas.admin import AdminClientPaymentOut


class _FakeScalarDb:
    def __init__(self, scalar_value: object | None) -> None:
        self._scalar_value = scalar_value

    def scalar(self, _query: object) -> object | None:
        return self._scalar_value


class AdminClientPaymentDocumentTests(unittest.TestCase):
    def test_booking_payment_receipt_manual_row_is_not_counted_in_opening_balance(self) -> None:
        row = AdminClientPaymentOut(
            id=uuid4(),
            source="MANUAL",
            occurred_at=datetime(2026, 4, 3, 18, 16, tzinfo=timezone.utc),
            label="Paiement recu - Reservation studio",
            status="PAID",
            amount_excl_vat="-15.00",
            vat_rate="0.00",
            vat_amount="0.00",
            total_incl_vat="-15.00",
            currency="EUR",
            reference=None,
            category="BOOKING_PAYMENT_RECEIPT",
        )

        self.assertFalse(_should_count_in_client_balance(row))

    def test_booking_payment_receipt_manual_row_gets_no_invoice_presentation(self) -> None:
        row = AdminClientPaymentOut(
            id=uuid4(),
            source="MANUAL",
            occurred_at=datetime(2026, 4, 3, 18, 16, tzinfo=timezone.utc),
            label="Paiement recu - Reservation studio",
            status="PAID",
            amount_excl_vat="-15.00",
            vat_rate="0.00",
            vat_amount="0.00",
            total_incl_vat="-15.00",
            currency="EUR",
            reference=None,
            category="BOOKING_PAYMENT_RECEIPT",
        )

        _apply_invoice_presentation_to_payment_item(row)

        self.assertIsNone(row.invoice_status)
        self.assertIsNone(row.invoice_number)

    def test_download_booking_payment_receipt_manual_row_uses_receipt_pdf(self) -> None:
        client_id = uuid4()
        payment_id = uuid4()
        receipt_id = uuid4()
        payment = AdminClientPaymentOut(
            id=payment_id,
            source="MANUAL",
            occurred_at=datetime(2026, 4, 3, 18, 16, tzinfo=timezone.utc),
            label="Paiement recu - Reservation studio",
            status="PAID",
            amount_excl_vat="-15.00",
            vat_rate="0.00",
            vat_amount="0.00",
            total_incl_vat="-15.00",
            currency="EUR",
            reference=None,
            category="BOOKING_PAYMENT_RECEIPT",
        )
        db = _FakeScalarDb(SimpleNamespace(id=receipt_id))

        with patch("app.api.routes.admin_clients._require_client", return_value=SimpleNamespace(id=client_id)), patch(
            "app.api.routes.admin_clients._build_admin_client_payments",
            return_value=[payment],
        ), patch(
            "app.api.routes.admin_clients.download_admin_client_payment_receipt",
            return_value=SimpleNamespace(status_code=200, body=b"pdf"),
        ) as download_receipt:
            response = download_admin_client_payment_invoice(
                client_id=client_id,
                source="MANUAL",
                payment_id=payment_id,
                inline=False,
                db=db,
                actor=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 200)
        download_receipt.assert_called_once()
        self.assertEqual(download_receipt.call_args.kwargs["receipt_id"], receipt_id)


if __name__ == "__main__":
    unittest.main()
