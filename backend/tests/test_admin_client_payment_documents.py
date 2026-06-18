from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _apply_invoice_presentation_to_payment_item,
    _build_range_invoice_email_defaults,
    _normalize_invoice_range_metadata,
    _send_invoice_range_payment_admin_emails,
    _send_invoice_range_payment_success_emails,
    _select_reusable_pre_registration_deposit_reconciliation,
    _select_reusable_pre_registration_deposit_payment_ids,
    _resolve_public_payment_webhook_query_credentials,
    _should_count_in_client_balance,
    send_admin_client_range_invoice_email,
    download_admin_client_payment_invoice,
)
from app.schemas.admin import AdminClientPaymentOut
from app.services.payment_checkout import with_webhook_secret


class _FakeScalarDb:
    def __init__(self, scalar_value: object | None) -> None:
        self._scalar_value = scalar_value

    def scalar(self, _query: object) -> object | None:
        return self._scalar_value


class _FakeMutationDb:
    def add(self, _value: object) -> None:
        return None

    def commit(self) -> None:
        return None


class _FakeEmailDefaultDb:
    def __init__(self, note: object | None) -> None:
        self._note = note

    def get(self, _model: object, _key: object) -> object | None:
        return self._note


class _FakeQueryParams:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def getlist(self, key: str) -> list[str]:
        if key != "token":
            return []
        return list(self._values)


class AdminClientPaymentDocumentTests(unittest.TestCase):
    def test_select_reusable_pre_registration_deposit_reconciliation_returns_charge_and_payment_ids(self) -> None:
        deposit_charge_id = uuid4()
        deposit_payment_id = uuid4()

        selected_payments, selected_charges = _select_reusable_pre_registration_deposit_reconciliation(
            invoice_metadatas=[
                {
                    "invoice_status": "PAID",
                    "included_payment_keys": [f"MANUAL:{deposit_charge_id}"],
                    "reconciled_manual_payment_ids": [str(deposit_payment_id)],
                },
            ],
            manual_charge_rows_by_id={
                deposit_charge_id: SimpleNamespace(category="PRE_REGISTRATION_DEPOSIT"),
            },
            manual_payment_rows_by_id={
                deposit_payment_id: SimpleNamespace(transaction_type="PAYMENT", status="COMPLETED"),
            },
        )

        self.assertEqual(selected_payments, [deposit_payment_id])
        self.assertEqual(selected_charges, {deposit_charge_id})

    def test_select_reusable_pre_registration_deposit_reconciliation_accepts_business_category(self) -> None:
        deposit_charge_id = uuid4()
        deposit_payment_id = uuid4()

        selected_payments, selected_charges = _select_reusable_pre_registration_deposit_reconciliation(
            invoice_metadatas=[
                {
                    "invoice_status": "PAID",
                    "included_payment_keys": [f"MANUAL:{deposit_charge_id}"],
                    "reconciled_manual_payment_ids": [str(deposit_payment_id)],
                },
            ],
            manual_charge_rows_by_id={
                deposit_charge_id: SimpleNamespace(category="Acompte preinscription"),
            },
            manual_payment_rows_by_id={
                deposit_payment_id: SimpleNamespace(transaction_type="PAYMENT", status="COMPLETED"),
            },
        )

        self.assertEqual(selected_payments, [deposit_payment_id])
        self.assertEqual(selected_charges, {deposit_charge_id})

    def test_select_reusable_pre_registration_deposit_payment_ids_returns_paid_deposit_payment(self) -> None:
        deposit_charge_id = uuid4()
        deposit_payment_id = uuid4()

        selected = _select_reusable_pre_registration_deposit_payment_ids(
            invoice_metadatas=[
                {
                    "invoice_status": "PAID",
                    "included_payment_keys": [f"MANUAL:{deposit_charge_id}"],
                    "reconciled_manual_payment_ids": [str(deposit_payment_id)],
                },
                {
                    "invoice_status": "ISSUED",
                    "included_payment_keys": [f"BOOKING:{uuid4()}"],
                },
            ],
            manual_charge_rows_by_id={
                deposit_charge_id: SimpleNamespace(category="PRE_REGISTRATION_DEPOSIT"),
            },
            manual_payment_rows_by_id={
                deposit_payment_id: SimpleNamespace(transaction_type="PAYMENT", status="COMPLETED"),
            },
        )

        self.assertEqual(selected, [deposit_payment_id])

    def test_select_reusable_pre_registration_deposit_payment_ids_ignores_payment_already_consumed_elsewhere(self) -> None:
        deposit_charge_id = uuid4()
        deposit_payment_id = uuid4()

        selected = _select_reusable_pre_registration_deposit_payment_ids(
            invoice_metadatas=[
                {
                    "invoice_status": "PAID",
                    "included_payment_keys": [f"MANUAL:{deposit_charge_id}"],
                    "reconciled_manual_payment_ids": [str(deposit_payment_id)],
                },
                {
                    "invoice_status": "ISSUED",
                    "included_payment_keys": [f"BOOKING:{uuid4()}"],
                    "reconciled_manual_payment_ids": [str(deposit_payment_id)],
                },
            ],
            manual_charge_rows_by_id={
                deposit_charge_id: SimpleNamespace(category="PRE_REGISTRATION_DEPOSIT"),
            },
            manual_payment_rows_by_id={
                deposit_payment_id: SimpleNamespace(transaction_type="PAYMENT", status="COMPLETED"),
            },
        )

        self.assertEqual(selected, [])

    def test_with_webhook_secret_supports_explicit_param_name(self) -> None:
        url = "https://app.piano-academie.com/api/v1/public/payments/invoices/range/client/note/webhook?token=public-jwt"

        signed = with_webhook_secret(url, "webhook-secret", param_name="secret")

        self.assertIn("token=public-jwt", signed)
        self.assertIn("secret=webhook-secret", signed)

    def test_legacy_public_payment_webhook_uses_second_token_as_secret(self) -> None:
        public_token = "public-jwt"
        webhook_secret = "webhook-secret"
        request = SimpleNamespace(query_params=_FakeQueryParams([public_token, webhook_secret]))

        normalized_token, normalized_secret = _resolve_public_payment_webhook_query_credentials(
            request,
            token=public_token,
            secret=None,
            expected_secret=webhook_secret,
        )

        self.assertEqual(normalized_token, public_token)
        self.assertEqual(normalized_secret, webhook_secret)

    def test_send_range_invoice_email_passes_note_id_to_pdf_generation(self) -> None:
        client_id = uuid4()
        note_id = uuid4()
        note = SimpleNamespace(id=note_id, message="")
        metadata = {
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "issued_date": "2026-04-30",
            "due_date": "2026-04-30",
            "invoice_number": "PA26-0037",
            "issuer_snapshot": {},
        }
        payload = SimpleNamespace(
            kind="INVOICE",
            to_emails=None,
            subject=None,
            body=None,
            body_format="TEXT",
        )
        db = _FakeMutationDb()

        with patch("app.api.routes.admin_clients._require_client", return_value=SimpleNamespace(id=client_id)), patch(
            "app.api.routes.admin_clients._load_range_invoice_note",
            return_value=(note, metadata),
        ), patch(
            "app.api.routes.admin_clients._frozen_invoice_selection_for_note",
            return_value=([], None, None),
        ), patch(
            "app.api.routes.admin_clients._build_range_invoice_email_defaults",
            return_value=(["parent@example.com"], "Sujet", "Corps", "TEXT"),
        ), patch(
            "app.api.routes.admin_clients.download_admin_client_range_invoice",
            return_value=SimpleNamespace(body=b"%PDF-1.4"),
        ) as download_pdf, patch(
            "app.api.routes.admin_clients.resolve_sender_profile",
            return_value=SimpleNamespace(
                from_email="studio@example.com",
                from_name="Piano Academie",
                reply_to=None,
                subject_prefix=None,
            ),
        ), patch(
            "app.api.routes.admin_clients.send_email",
            return_value="message-id",
        ), patch(
            "app.api.routes.admin_clients._build_invoice_range_note_message",
            return_value="note message",
        ):
            response = send_admin_client_range_invoice_email(
                client_id=client_id,
                note_id=note_id,
                payload=payload,
                db=db,
                actor=SimpleNamespace(),
            )

        self.assertEqual(response.note_id, note_id)
        self.assertEqual(download_pdf.call_args.kwargs["note_id"], note_id)

    def test_range_invoice_email_defaults_use_amount_to_pay_for_invoice_and_reminder(self) -> None:
        client_id = uuid4()
        note_id = uuid4()
        note = SimpleNamespace(id=note_id, created_at=datetime(2026, 5, 7, tzinfo=timezone.utc))
        metadata = {
            "invoice_number": "PA26-0042",
            "issued_date": "2026-05-07",
            "due_date": "2026-09-01",
            "totals_by_currency": {"EUR": "2700.00"},
            "total_to_pay_by_currency": {"EUR": "2370.00"},
        }
        db = _FakeEmailDefaultDb(note)
        client = SimpleNamespace(
            id=client_id,
            email="client@example.com",
            first_name="Coraline",
            last_name="Schnee",
            preferred_language="fr",
        )

        def fake_template(_db: object, *, code: str, language: str) -> dict[str, object]:
            self.assertEqual(language, "fr")
            return {
                "active": True,
                "subject": f"{code} {{invoice_number}} {{amount_due}} {{currency}}",
                "body": "Montant {total_incl_vat} {currency} - {payment_url}",
                "body_format": "TEXT",
            }

        captured_payment_metadata: list[dict[str, object]] = []

        def fake_payment_url(*, client_id: object, note_id: object, metadata: dict[str, object]) -> str:
            captured_payment_metadata.append(dict(metadata))
            return "https://pay.example.test"

        with patch(
            "app.api.routes.admin_clients.resolve_billing_profile",
            return_value=SimpleNamespace(
                email="parent@example.com",
                first_name="Coraline",
                last_name="Schnee",
            ),
        ), patch(
            "app.api.routes.admin_clients.resolve_predefined_template",
            side_effect=fake_template,
        ), patch(
            "app.api.routes.admin_clients._invoice_range_download_url",
            return_value="https://invoice.example.test",
        ), patch(
            "app.api.routes.admin_clients._invoice_range_payment_url",
            side_effect=fake_payment_url,
        ):
            invoice_defaults = _build_range_invoice_email_defaults(
                db,
                client=client,
                note_id=note_id,
                metadata=metadata,
                kind="INVOICE",
            )
            reminder_defaults = _build_range_invoice_email_defaults(
                db,
                client=client,
                note_id=note_id,
                metadata=metadata,
                kind="REMINDER",
            )

        self.assertIn("2370.00 EUR", invoice_defaults[1])
        self.assertIn("Montant 2370.00 EUR", invoice_defaults[2])
        self.assertIn("2370.00 EUR", reminder_defaults[1])
        self.assertIn("Montant 2370.00 EUR", reminder_defaults[2])
        self.assertEqual(
            [entry.get("total_to_pay_by_currency") for entry in captured_payment_metadata],
            [{"EUR": "2370.00"}, {"EUR": "2370.00"}],
        )

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

    def test_manual_discount_gets_no_invoice_presentation(self) -> None:
        row = AdminClientPaymentOut(
            id=uuid4(),
            source="MANUAL",
            occurred_at=datetime(2026, 6, 18, 9, 24, tzinfo=timezone.utc),
            label="Remise famille",
            status="COMPLETED",
            amount_excl_vat="-128.00",
            vat_rate="0.00",
            vat_amount="0.00",
            total_incl_vat="-128.00",
            currency="EUR",
            reference=None,
            category=None,
            manual_transaction_type="DISCOUNT",
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

    def test_invoice_range_payment_success_email_uses_paid_amount_for_customer(self) -> None:
        client = SimpleNamespace(
            id=uuid4(),
            email="parent@example.com",
            first_name="Coraline",
            last_name="Schnee",
            preferred_language="fr",
        )
        note_id = uuid4()
        metadata = {
            "invoice_number": "PA26-0042",
            "payment_amount_paid": "2370.00",
            "payment_currency": "EUR",
            "totals_by_currency": {"EUR": "2770.00"},
            "total_to_pay_by_currency": {"EUR": "2770.00"},
            "issued_date": "2026-05-07",
            "due_date": "2026-09-01",
        }
        billing_profile = SimpleNamespace(
            id=uuid4(),
            email="billing@example.com",
            first_name="Coraline",
            last_name="Schnee",
        )
        paid_at = datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc)

        with patch("app.api.routes.admin_clients.resolve_billing_profile", return_value=billing_profile), patch(
            "app.api.routes.admin_clients._invoice_range_download_url",
            return_value="https://app.piano-academie.com/invoice.pdf",
        ), patch(
            "app.api.routes.admin_clients._frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.admin_clients.send_payment_success_notifications",
            return_value={"payment_confirmation_message_id": "client-msg", "invoice_message_id": "invoice-msg"},
        ) as send_success:
            result = _send_invoice_range_payment_success_emails(
                _FakeMutationDb(),
                client=client,
                note_id=note_id,
                metadata=metadata,
                paid_at=paid_at,
            )

        self.assertTrue(result)
        self.assertEqual(send_success.call_args.kwargs["to_email"], "billing@example.com")
        self.assertEqual(send_success.call_args.kwargs["recipient_user_id"], billing_profile.id)
        self.assertEqual(send_success.call_args.kwargs["amount_paid"], Decimal("2370.00"))
        self.assertEqual(send_success.call_args.kwargs["currency"], "EUR")

    def test_invoice_range_metadata_preserves_payment_email_markers(self) -> None:
        metadata = {
            "kind": "INVOICE_RANGE",
            "invoice_number": "PA26-0042",
            "issued_date": "2026-05-07",
            "due_date": "2026-09-01",
            "start_date": "2026-05-01",
            "end_date": "2027-06-30",
            "layout": "NORMAL",
            "totals_by_currency": {"EUR": "2770.00"},
            "applied_payment_totals_by_currency": {"EUR": "-400.00"},
            "applied_payment_lines": [
                {
                    "date": "09/05/2026",
                    "method": "CB en ligne",
                    "reference": "REF:pay_test",
                    "amount": "400.00",
                    "currency": "EUR",
                }
            ],
            "total_to_pay_by_currency": {"EUR": "2370.00"},
            "payment_amount_paid": "2370.00",
            "payment_currency": "EUR",
            "payment_confirmation_emails_sent_at": "2026-05-09T05:09:00+00:00",
            "admin_payment_confirmation_emails_sent_at": "2026-05-09T05:10:00+00:00",
        }

        normalized = _normalize_invoice_range_metadata(metadata)

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["applied_payment_totals_by_currency"], {"EUR": "-400.00"})
        self.assertEqual(
            normalized["applied_payment_lines"],
            [
                {
                    "date": "09/05/2026",
                    "method": "CB en ligne",
                    "reference": "REF:pay_test",
                    "amount": "400.00",
                    "currency": "EUR",
                }
            ],
        )
        self.assertEqual(normalized["total_to_pay_by_currency"], {"EUR": "2370.00"})
        self.assertEqual(normalized["payment_amount_paid"], "2370.00")
        self.assertEqual(normalized["payment_currency"], "EUR")
        self.assertEqual(normalized["payment_confirmation_emails_sent_at"], "2026-05-09T05:09:00+00:00")
        self.assertEqual(normalized["admin_payment_confirmation_emails_sent_at"], "2026-05-09T05:10:00+00:00")

    def test_invoice_range_payment_sends_admin_notification(self) -> None:
        client = SimpleNamespace(
            id=uuid4(),
            email="parent@example.com",
            first_name="Coraline",
            last_name="Schnee",
        )
        note_id = uuid4()
        metadata = {
            "invoice_number": "PA26-0042",
            "payment_amount_paid": "2370.00",
            "payment_currency": "EUR",
            "payment_provider_reference": "pay_test_123",
            "totals_by_currency": {"EUR": "2770.00"},
            "total_to_pay_by_currency": {"EUR": "2770.00"},
        }
        billing_profile = SimpleNamespace(
            email="billing@example.com",
            first_name="Coraline",
            last_name="Schnee",
        )
        template = {
            "subject": "Paiement facture recu - {invoice_number}",
            "body": "{client_name} {client_email} {amount_paid} {currency} {payment_reference} {invoice_url}",
            "body_format": "TEXT",
            "active": True,
        }
        sender = SimpleNamespace(
            from_email="contact@piano-academie.com",
            from_name="Piano Academie",
            reply_to=None,
            subject_prefix=None,
        )
        paid_at = datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc)

        with patch("app.api.routes.admin_clients.resolve_billing_profile", return_value=billing_profile), patch(
            "app.api.routes.admin_clients._invoice_range_download_url",
            return_value="https://app.piano-academie.com/invoice.pdf",
        ), patch(
            "app.api.routes.admin_clients._frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.admin_clients.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@example.com")],
        ), patch(
            "app.api.routes.admin_clients.resolve_predefined_template",
            return_value=template,
        ), patch(
            "app.api.routes.admin_clients.resolve_sender_profile",
            return_value=sender,
        ), patch(
            "app.api.routes.admin_clients.send_email",
            return_value="admin-msg",
        ) as send_email_mock:
            result = _send_invoice_range_payment_admin_emails(
                _FakeMutationDb(),
                client=client,
                note_id=note_id,
                metadata=metadata,
                paid_at=paid_at,
            )

        self.assertTrue(result)
        kwargs = send_email_mock.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "admin@example.com")
        self.assertEqual(kwargs["context"], "ADMIN_INVOICE_PAYMENT_CONFIRMED")
        self.assertIn("PA26-0042", kwargs["subject"])
        self.assertIn("2370.00 EUR", kwargs["body"])
        self.assertIn("pay_test_123", kwargs["body"])
        self.assertIn("invoice.pdf", kwargs["body"])
        self.assertNotIn("2770.00", kwargs["body"])


if __name__ == "__main__":
    unittest.main()
