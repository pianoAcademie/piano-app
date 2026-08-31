from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.routes.quotes import (
    _create_followup_annual_invoices,
    _create_followup_deposit_invoice,
    _quote_transformation_invoice_due_date,
)
from app.services.invoice_reminders import invoice_is_due_for_j_minus_one_reminder


class QuoteTransformationInvoiceDueDatesTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.scalars.return_value.all.return_value = []
        self.db.scalar.return_value = SimpleNamespace(name="PIANO ACADEMIE")
        self.db.add.side_effect = lambda row: setattr(row, "id", row.id or uuid4())
        self.quote = SimpleNamespace(
            id=uuid4(), quote_number="DV-TEST-DUE-DATE", legal_entity_id=uuid4(),
            currency="EUR", school_year_label="2026-2027",
            # An old quote transformed today must receive the new terms too.
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        self.student = SimpleNamespace(id=uuid4(), first_name="Test", last_name="Eleve", email="test@example.test")
        self.billing = SimpleNamespace(id=uuid4())
        self.actor = SimpleNamespace(id=uuid4())
        self.metadata = []

    def capture_note(self, *_args, **kwargs):
        self.metadata.append(json.loads(kwargs["message"].split("INVOICE_RANGE::", 1)[1]))
        return SimpleNamespace(id=uuid4())

    def common_patches(self, stack, now):
        for name, options in (
            ("_utcnow", {"return_value": now}),
            ("_create_client_note", {"side_effect": self.capture_note}),
            ("_allocate_invoice_number_for_seller_entity", {"return_value": "PA26-TEST"}),
        ):
            stack.enter_context(patch(f"app.api.routes.quotes.{name}", **options))

    def annual_invoices(self, now):
        payments = [
            SimpleNamespace(
                id=uuid4(), source="BOOKING", occurred_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
                seller_legal_entity_id=seller_id, billing_entity="PIANO_ACADEMIE",
                total_incl_vat=Decimal("38.00"), currency="EUR",
            )
            for seller_id in (self.quote.legal_entity_id, uuid4())
        ]
        with ExitStack() as stack:
            self.common_patches(stack, now)
            for name, result in (
                ("_build_admin_client_payments", payments),
                ("_quote_annual_invoice_applied_deposit_payments", []),
                ("_quote_annual_invoice_available_referral_credits", []),
                ("_invoice_recipient_snapshot_for_client", {"client_name": "Test", "client_billing_address": ""}),
                ("build_company_identity_snapshot", {}),
                ("_persist_invoice_lines_for_note", None),
            ):
                stack.enter_context(patch(f"app.api.routes.quotes.{name}", return_value=result))
            return _create_followup_annual_invoices(
                self.db, quote=self.quote, student=self.student, billing=self.billing,
                current_user=self.actor, booking_ids=[payment.id for payment in payments],
                transaction_ids=[], deposit_invoice_note_id=None, created_invoice_note_ids=[],
            )

    def deposit_invoice(self, now, *, paid=False):
        payment = SimpleNamespace(
            id=uuid4(), total_incl_vat=Decimal("-200.00"), occurred_at=now,
        ) if paid else None
        with ExitStack() as stack:
            self.common_patches(stack, now)
            for name, result in (
                ("_quote_deposit_invoice_breakdown", (Decimal("200.00"), Decimal("166.67"), Decimal("20.000"), Decimal("33.33"))),
                ("_resolve_configured_product_category", "PRE_REGISTRATION_DEPOSIT"),
                ("_find_reusable_followup_deposit_payment", payment),
            ):
                stack.enter_context(patch(f"app.api.routes.quotes.{name}", return_value=result))
            return _create_followup_deposit_invoice(
                self.db, quote=self.quote, followup=SimpleNamespace(), student=self.student,
                billing=self.billing, current_user=self.actor,
                created_transaction_ids=[], created_invoice_note_ids=[],
            )

    def test_three_calendar_days_from_effective_date_and_across_boundaries(self):
        for issued, expected in (
            (date(2026, 8, 31), date(2026, 9, 3)),
            (date(2026, 9, 1), date(2026, 9, 4)),
            (date(2026, 9, 4), date(2026, 9, 7)),  # Friday -> Monday, not three working days.
            (date(2026, 12, 30), date(2027, 1, 2)),
            (date(2028, 2, 27), date(2028, 3, 1)),
        ):
            with self.subTest(issued=issued):
                self.assertEqual(_quote_transformation_invoice_due_date(
                    issued_date=issued, legacy_due_date=issued + timedelta(days=7),
                ), expected)

    def test_legacy_dates_keep_the_previous_terms(self):
        for legacy in (date(2026, 9, 1), date(2026, 9, 6)):
            with self.subTest(legacy=legacy):
                self.assertEqual(_quote_transformation_invoice_due_date(
                    issued_date=date(2026, 8, 30), legacy_due_date=legacy,
                ), legacy)

    def test_all_seller_invoices_use_generation_date_not_quote_creation_date(self):
        now = datetime(2026, 8, 31, 10, tzinfo=timezone.utc)
        self.assertEqual(len(self.annual_invoices(now)), 2)
        for metadata in self.metadata:
            self.assertEqual(metadata["issued_date"], "2026-08-31")
            self.assertEqual(metadata["due_date"], "2026-09-03")
            self.assertEqual(metadata["issued_at"], now.isoformat())
            self.assertFalse(metadata["no_due_date"])
            self.assertEqual(metadata["totals_by_currency"], {"EUR": "38.00"})

    def test_deposit_uses_three_days_without_changing_paid_status(self):
        for paid in (False, True):
            with self.subTest(paid=paid):
                self.deposit_invoice(datetime(2026, 8, 31, 10, tzinfo=timezone.utc), paid=paid)
                metadata = self.metadata[-1]
                self.assertEqual(metadata["issued_date"], "2026-08-31")
                self.assertEqual(metadata["due_date"], "2026-09-03")
                self.assertEqual(metadata["invoice_status"], "PAID" if paid else "ISSUED")
                self.assertEqual(metadata["totals_by_currency"], {"EUR": "200.00"})

    def test_generation_before_effective_date_retains_each_legacy_rule(self):
        now = datetime(2026, 8, 30, 21, 59, tzinfo=timezone.utc)
        self.annual_invoices(now)
        self.assertEqual(self.metadata[-1]["issued_date"], "2026-08-30")
        self.assertEqual(self.metadata[-1]["due_date"], "2026-09-01")
        self.deposit_invoice(now)
        self.assertEqual(self.metadata[-1]["issued_date"], "2026-08-30")
        self.assertEqual(self.metadata[-1]["due_date"], "2026-09-06")

    def test_reminder_selection_uses_new_invoice_due_date(self):
        self.annual_invoices(datetime(2026, 8, 31, 10, tzinfo=timezone.utc))
        metadata = self.metadata[-1]
        self.assertFalse(invoice_is_due_for_j_minus_one_reminder(
            metadata, target_due_date=date(2026, 9, 1),
        ))
        self.assertTrue(invoice_is_due_for_j_minus_one_reminder(
            metadata, target_due_date=date(2026, 9, 3),
        ))

    def test_effective_date_starts_at_paris_midnight_for_both_invoice_types(self):
        for generation in (self.annual_invoices, self.deposit_invoice):
            for now, issued, due in (
                (datetime(2026, 8, 30, 22, tzinfo=timezone.utc), "2026-08-31", "2026-09-03"),
                (datetime(2026, 8, 31, 23, tzinfo=timezone.utc), "2026-09-01", "2026-09-04"),
                (datetime(2026, 12, 31, 23, tzinfo=timezone.utc), "2027-01-01", "2027-01-04"),
            ):
                with self.subTest(generation=generation.__name__, now=now):
                    generation(now)
                    self.assertEqual(self.metadata[-1]["issued_date"], issued)
                    self.assertEqual(self.metadata[-1]["due_date"], due)
                    self.assertEqual(self.metadata[-1]["issued_at"], now.isoformat())

    def test_new_rule_does_not_replace_or_modify_an_existing_invoice(self):
        existing_metadata = {
            "invoice_status": "ISSUED", "start_date": "2026-08-01", "end_date": "2027-06-30",
            "issued_date": "2026-08-30", "due_date": "2026-09-01",
        }
        original_message = "INVOICE_RANGE::" + json.dumps(existing_metadata)
        existing_note = SimpleNamespace(message=original_message)
        self.db.scalars.return_value.all.return_value = [existing_note]
        with patch("app.api.routes.quotes._parse_quote_invoice_range_note_entry", return_value=existing_metadata):
            with self.assertRaises(HTTPException) as caught:
                self.annual_invoices(datetime(2026, 8, 31, 10, tzinfo=timezone.utc))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(existing_note.message, original_message)
        self.assertEqual(existing_metadata["due_date"], "2026-09-01")
        self.assertEqual(self.metadata, [])
        self.db.add.assert_not_called()
        self.db.add_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
