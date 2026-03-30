from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.catalog import BookingStatus, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.services.invoice_documents import CompanyIdentity, preview_invoice_number, render_payment_receipt_pdf
from app.services.payment_receipts import (
    BookingReceiptSnapshot,
    _format_receipt_number,
    build_final_invoice_metadata,
    generate_final_invoice_for_booking,
    should_defer_booking_invoice,
)


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []
        self.added: list[object] = []
        self.flush_calls = 0

    def scalars(self, _query: object) -> _ScalarResult:
        return _ScalarResult(self._rows)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_calls += 1


class PaymentReceiptsFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.booking_id = uuid4()
        self.customer_id = uuid4()
        self.student_id = uuid4()
        self.session_id = uuid4()
        self.issued_at = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
        self.snapshot = BookingReceiptSnapshot(
            customer_id=self.customer_id,
            customer_first_name="Hector",
            customer_last_name="Souza",
            customer_email="hector@example.com",
            customer_name="Hector Souza",
            customer_billing_address="1 rue de Richelieu 75001 Paris (France)",
            student_id=self.student_id,
            student_name="Gabriel TEST01",
            booking_id=self.booking_id,
            session_id=self.session_id,
            session_status="COMPLETED",
            service_date=date(2026, 9, 23),
            reservation_label="Eveil musical - Rue de la Pompe - Gabriel TEST01",
            activity_name="Eveil musical",
            location_label="Rue de la Pompe",
            session_time_label="10:00 - 11:00",
            amount_total=Decimal("30.00"),
            currency="EUR",
            legal_entity_id=None,
        )
        self.booking = SimpleNamespace(
            id=self.booking_id,
            status=BookingStatus.ATTENDED,
            total_incl_vat_snapshot=Decimal("30.00"),
            price_excl_vat_snapshot=Decimal("25.00"),
            vat_rate_snapshot=Decimal("0.20"),
            vat_amount_snapshot=Decimal("5.00"),
        )
        self.session_obj = SimpleNamespace(
            id=self.session_id,
            status=SessionStatus.COMPLETED,
            start_at_utc=self.issued_at,
            end_at_utc=datetime(2026, 9, 23, 11, 0, tzinfo=timezone.utc),
            timezone="Europe/Paris",
        )

    def test_future_service_is_deferred_but_same_day_is_not(self) -> None:
        future_session = SimpleNamespace(
            status=SessionStatus.SCHEDULED,
            start_at_utc=datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc),
            timezone="Europe/Paris",
        )
        same_day_session = SimpleNamespace(
            status=SessionStatus.SCHEDULED,
            start_at_utc=datetime(2026, 3, 30, 18, 0, tzinfo=timezone.utc),
            timezone="Europe/Paris",
        )

        self.assertTrue(
            should_defer_booking_invoice(
                future_session,
                now=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
            )
        )
        self.assertFalse(
            should_defer_booking_invoice(
                same_day_session,
                now=datetime(2026, 3, 30, 8, 0, tzinfo=timezone.utc),
            )
        )

    def test_final_invoice_metadata_can_reconcile_multiple_payments(self) -> None:
        payment_ids = [uuid4(), uuid4()]
        metadata = build_final_invoice_metadata(
            booking=self.booking,
            snapshot=self.snapshot,
            issued_at=self.issued_at,
            invoice_number="PA26-0187",
            reconciled_manual_payment_ids=payment_ids,
            total_paid=Decimal("30.00"),
        )

        self.assertEqual(metadata["invoice_number"], "PA26-0187")
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["totals_by_currency"], {"EUR": "30.00"})
        self.assertEqual(metadata["applied_payment_totals_by_currency"], {"EUR": "30.00"})
        self.assertEqual(metadata["total_to_pay_by_currency"], {"EUR": "0.00"})
        self.assertEqual(metadata["reconciled_manual_payment_ids"], [str(value) for value in payment_ids])
        self.assertEqual(metadata["service_realized_date"], "2026-09-23")

    def test_cancelled_booking_never_generates_final_invoice(self) -> None:
        cancelled_booking = SimpleNamespace(id=self.booking_id, status=BookingStatus.CANCELLED)
        with patch("app.services.payment_receipts._invoice_note_for_booking", return_value=None):
            with self.assertRaisesRegex(ValueError, "Cancelled bookings cannot generate a final invoice"):
                generate_final_invoice_for_booking(
                    _FakeSession(),
                    booking=cancelled_booking,
                    session_obj=self.session_obj,
                    course_type=SimpleNamespace(),
                    location=SimpleNamespace(),
                    owner=SimpleNamespace(),
                    author_user_id=None,
                )

    def test_duplicate_generation_returns_existing_invoice(self) -> None:
        existing_note = SimpleNamespace(id=uuid4(), message="existing")
        existing_metadata = {"invoice_number": "PA26-0009", "invoice_status": "ISSUED"}
        with patch("app.services.payment_receipts._invoice_note_for_booking", return_value=(existing_note, existing_metadata)):
            note, metadata, created = generate_final_invoice_for_booking(
                _FakeSession(),
                booking=SimpleNamespace(id=self.booking_id),
                session_obj=self.session_obj,
                course_type=SimpleNamespace(),
                location=SimpleNamespace(),
                owner=SimpleNamespace(),
                author_user_id=None,
            )

        self.assertIs(note, existing_note)
        self.assertEqual(metadata["invoice_number"], "PA26-0009")
        self.assertFalse(created)

    def test_completed_service_generates_final_invoice_with_zero_balance_when_fully_paid(self) -> None:
        reconciled_ids = [uuid4(), uuid4()]
        completed_receipts = [SimpleNamespace(final_invoice_note_id=None, final_invoice_generated_at=None, updated_at=None)]
        fake_db = _FakeSession(rows=completed_receipts)

        with patch("app.services.payment_receipts._invoice_note_for_booking", return_value=None), patch(
            "app.services.payment_receipts.build_booking_receipt_snapshot",
            return_value=self.snapshot,
        ), patch(
            "app.services.payment_receipts.reserve_next_invoice_number",
            return_value="PA26-0187",
        ), patch(
            "app.services.payment_receipts.completed_payment_receipt_totals",
            return_value=(Decimal("30.00"), "EUR", reconciled_ids),
        ):
            note, metadata, created = generate_final_invoice_for_booking(
                fake_db,
                booking=self.booking,
                session_obj=self.session_obj,
                course_type=SimpleNamespace(),
                location=SimpleNamespace(),
                owner=SimpleNamespace(),
                author_user_id=uuid4(),
                issued_at=self.issued_at,
            )

        self.assertTrue(created)
        self.assertIsInstance(note, ClientNoteEntry)
        self.assertEqual(metadata["invoice_number"], "PA26-0187")
        self.assertEqual(metadata["invoice_status"], "PAID")
        self.assertEqual(metadata["total_to_pay_by_currency"], {"EUR": "0.00"})
        invoice_lines = [row for row in fake_db.added if isinstance(row, ClientInvoiceLine)]
        self.assertEqual(len(invoice_lines), 1)
        self.assertEqual(invoice_lines[0].label, self.snapshot.reservation_label)
        self.assertEqual(invoice_lines[0].occurred_at, self.session_obj.start_at_utc)
        self.assertEqual(completed_receipts[0].final_invoice_note_id, note.id)

    def test_receipt_numbering_is_independent_from_invoice_numbering(self) -> None:
        receipt_number = _format_receipt_number(
            "PAY-%YYYY%-%NNNN%",
            paid_at=datetime(2026, 3, 30, 16, 0, tzinfo=timezone.utc),
            next_number=41,
        )
        invoice_number = preview_invoice_number(
            pattern="PA%YY%-%NNNN%",
            next_number=187,
            issued_at=datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(receipt_number, "PAY-2026-0041")
        self.assertEqual(invoice_number, "PA26-0187")
        self.assertNotEqual(receipt_number, invoice_number)

    def test_payment_receipt_pdf_is_distinct_from_invoice_pdf(self) -> None:
        fake_identity = CompanyIdentity(
            company_name="Piano Academie",
            company_email="compta@example.com",
            company_phone="0102030405",
            company_siren="828051417",
            company_siret="82805141700032",
            company_vat_number="FR74828051417",
            company_address="1, rue de Richelieu, 75001 Paris (France)",
            company_legal_form="SAS",
            company_share_capital="10 000 EUR",
            company_logo_jpeg=None,
            company_logo_width_px=None,
            company_logo_height_px=None,
        )

        with patch("app.services.invoice_documents._company_identity", return_value=fake_identity):
            content = render_payment_receipt_pdf(
                SimpleNamespace(),
                receipt_number="PAY-2026-0041",
                paid_at=datetime(2026, 3, 30, 16, 19, tzinfo=timezone.utc),
                client_name="Hector Souza",
                client_billing_address="1 rue de Richelieu 75001 Paris (France)",
                amount_paid=Decimal("30.00"),
                currency="EUR",
                payment_method="CB en ligne",
                payment_provider="Payplug",
                payment_transaction_reference="pay_123",
                reservation_label="Eveil musical - Rue de la Pompe - Gabriel TEST01",
                scheduled_service_date=date(2026, 9, 23),
                location_label="Rue de la Pompe",
                student_name="Gabriel TEST01",
                note="Document de paiement uniquement.",
                legal_entity_id=None,
            )

        self.assertIn(b"JUSTIFICATIF DE PAIEMENT", content)
        self.assertNotIn(b"FACTURE", content)


if __name__ == "__main__":
    unittest.main()
