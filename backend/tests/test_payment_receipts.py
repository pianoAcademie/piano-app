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
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry, ClientPaymentRefund
from app.services.invoice_documents import CompanyIdentity, preview_invoice_number, render_payment_receipt_pdf
from app.services.payment_receipts import (
    BookingReceiptSnapshot,
    _format_receipt_number,
    build_final_invoice_metadata,
    generate_final_invoice_for_booking,
    mark_payment_receipt_completed,
    refund_payment_receipt,
    send_final_invoice_email,
    send_payment_refund_notifications,
    should_defer_booking_invoice,
)


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows: list[object] | None = None, scalar_values: list[object] | None = None) -> None:
        self._rows = rows or []
        self._scalar_values = list(scalar_values or [])
        self.added: list[object] = []
        self.flush_calls = 0

    def scalars(self, _query: object) -> _ScalarResult:
        return _ScalarResult(self._rows)

    def scalar(self, _query: object) -> object | None:
        if self._scalar_values:
            return self._scalar_values.pop(0)
        return None

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

    def test_future_service_is_deferred_until_completion_even_same_day(self) -> None:
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
        self.assertTrue(
            should_defer_booking_invoice(
                same_day_session,
                now=datetime(2026, 3, 30, 8, 0, tzinfo=timezone.utc),
            )
        )
        self.assertFalse(should_defer_booking_invoice(self.session_obj))

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

    def test_excused_absence_never_generates_final_invoice(self) -> None:
        excused_booking = SimpleNamespace(id=self.booking_id, status=BookingStatus.EXCUSED_ABSENCE)
        with patch("app.services.payment_receipts._invoice_note_for_booking", return_value=None):
            with self.assertRaisesRegex(ValueError, "Excused absences cannot generate a final invoice"):
                generate_final_invoice_for_booking(
                    _FakeSession(),
                    booking=excused_booking,
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

    def test_refund_payment_receipt_records_refund_and_manual_transaction(self) -> None:
        receipt = SimpleNamespace(
            id=uuid4(),
            customer_id=self.customer_id,
            student_id=self.student_id,
            amount_paid=Decimal("30.00"),
            currency="EUR",
            reservation_label=self.snapshot.reservation_label,
            receipt_number="PAY-2026-0041",
            legal_entity_id=None,
            receipt_metadata={},
            status="COMPLETED",
            updated_at=None,
        )
        fake_db = _FakeSession(scalar_values=[None])

        updated_receipt, refund_row, refund_transaction, created = refund_payment_receipt(
            fake_db,
            receipt=receipt,
            actor_user_id=uuid4(),
            reason="Annulation du cours d essai",
            refunded_at=datetime(2026, 3, 30, 17, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(created)
        self.assertEqual(updated_receipt.status, "REFUNDED")
        self.assertIsInstance(refund_row, ClientPaymentRefund)
        self.assertEqual(refund_row.source, "PAYMENT_RECEIPT")
        self.assertEqual(refund_row.amount_incl_vat, Decimal("30.00"))
        self.assertIsInstance(refund_transaction, ClientManualTransaction)
        self.assertEqual(refund_transaction.transaction_type, "REFUND")
        self.assertEqual(refund_transaction.total_incl_vat, Decimal("30.00"))
        self.assertEqual(updated_receipt.receipt_metadata["refund_reason"], "Annulation du cours d essai")

    def test_refunded_payment_receipt_cannot_be_completed_again(self) -> None:
        receipt = SimpleNamespace(status="REFUNDED")
        with self.assertRaisesRegex(ValueError, "Refunded payment receipts cannot be marked as completed"):
            mark_payment_receipt_completed(
                _FakeSession(),
                receipt=receipt,
                provider_reference="pay_123",
                payment_provider="PAYPLUG",
            )

    def test_payment_refund_notifications_use_refund_templates(self) -> None:
        receipt = SimpleNamespace(
            receipt_number="PAY-2026-0041",
            amount_paid=Decimal("30.00"),
            currency="EUR",
            payment_method="CARD_ONLINE",
            payment_provider="PAYPLUG",
            payment_transaction_reference="pay_123",
            reservation_label=self.snapshot.reservation_label,
            scheduled_service_date=date(2026, 9, 23),
            location_label="Rue de la Pompe",
        )
        template = {
            "subject": "Remboursement {receipt_number}",
            "body": "<div>{first_name} {refund_amount} {currency}</div>",
            "body_format": "HTML",
            "active": True,
        }

        with patch("app.services.payment_receipts.resolve_predefined_template", return_value=template), patch(
            "app.services.payment_receipts.resolve_sender_profile",
            return_value=SimpleNamespace(
                from_email="contact@piano-academie.com",
                from_name="Piano Academie",
                reply_to=None,
                subject_prefix=None,
            ),
        ), patch(
            "app.services.payment_receipts._frontend_url",
            return_value="https://app.piano-academie.com/client?tab=finance&finance_view=transactions",
        ), patch(
            "app.services.payment_receipts.send_email",
            side_effect=["client-msg", "admin-msg"],
        ) as send_email_mock, patch(
            "app.services.notifications.application.recipients.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@piano-academie.com")],
        ):
            sent = send_payment_refund_notifications(
                _FakeSession(),
                receipt=receipt,
                snapshot=self.snapshot,
                refunded_at=datetime(2026, 3, 30, 17, 0, tzinfo=timezone.utc),
                refund_reason="Cours annule",
                send_admin_copy=True,
            )

        self.assertTrue(sent)
        self.assertEqual(send_email_mock.call_count, 2)
        self.assertEqual(send_email_mock.call_args_list[0].kwargs["context"], "CLIENT_PAYMENT_REFUND")
        self.assertEqual(send_email_mock.call_args_list[1].kwargs["context"], "ADMIN_PAYMENT_REFUND")
        self.assertIn("PAY-2026-0041", send_email_mock.call_args_list[0].kwargs["subject"])

    def test_paid_final_invoice_email_uses_paid_template_and_renders_placeholders(self) -> None:
        customer = SimpleNamespace(
            id=uuid4(),
            email="hector@example.com",
            first_name="Hector",
            last_name="Souza",
        )
        metadata = {
            "invoice_number": "PA26-0006",
            "invoice_status": "PAID",
            "totals_by_currency": {"EUR": "30.00"},
            "applied_payment_totals_by_currency": {"EUR": "30.00"},
            "total_to_pay_by_currency": {"EUR": "0.00"},
            "due_date": "2026-09-23",
            "issued_date": "2026-09-23",
        }
        template = {
            "subject": "Facture {invoice_number} deja reglee",
            "body": "<div>Bonjour {first_name} - reglee {amount_paid} {currency} - {invoice_url}</div>",
            "body_format": "HTML",
        }
        sender = SimpleNamespace(
            from_email="contact@piano-academie.com",
            from_name="Piano Academie",
            reply_to=None,
            subject_prefix=None,
        )

        with patch("app.services.payment_receipts.resolve_billing_profile", return_value=customer), patch(
            "app.services.payment_receipts.resolve_predefined_template",
            return_value=template,
        ) as resolve_template, patch(
            "app.services.payment_receipts._public_invoice_range_download_url",
            return_value="https://app.piano-academie.com/api/v1/admin/clients/client-1/invoices/range/note-1/public-pdf?token=test",
        ), patch(
            "app.services.payment_receipts._frontend_url",
            return_value="https://app.piano-academie.com/client?tab=finance",
        ), patch(
            "app.services.payment_receipts.resolve_sender_profile",
            return_value=sender,
        ), patch(
            "app.services.payment_receipts.send_email",
            return_value="msg-123",
        ) as send_email_mock:
            result = send_final_invoice_email(
                _FakeSession(),
                customer=customer,
                note_id=uuid4(),
                metadata=metadata,
            )

        self.assertEqual(result, "msg-123")
        self.assertEqual(resolve_template.call_args.kwargs["code"], "INVOICE_PAID")
        kwargs = send_email_mock.call_args.kwargs
        self.assertEqual(kwargs["context"], "CLIENT_FINAL_INVOICE_PAID")
        self.assertIn("PA26-0006", kwargs["subject"])
        self.assertIn("Bonjour Hector", kwargs["body"])
        self.assertIn("30.00", kwargs["body"])
        self.assertIn("public-pdf?token=test", kwargs["body"])
        self.assertNotIn("{invoice_number}", kwargs["body"])


if __name__ == "__main__":
    unittest.main()
