from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import _invoice_range_pending_check_coverage
from app.services.invoice_reminders import invoice_is_due_for_j_minus_one_reminder


class InvoiceReminderSelectionTests(unittest.TestCase):
    def test_invoice_due_tomorrow_with_amount_due_is_selected(self) -> None:
        self.assertTrue(
            invoice_is_due_for_j_minus_one_reminder(
                {
                    "invoice_status": "ISSUED",
                    "due_date": "2026-05-24",
                    "no_due_date": False,
                    "total_to_pay_by_currency": {"EUR": "120.00"},
                },
                target_due_date=date(2026, 5, 24),
            )
        )

    def test_paid_cancelled_already_reminded_or_empty_amount_are_skipped(self) -> None:
        target_due_date = date(2026, 5, 24)
        base = {
            "invoice_status": "ISSUED",
            "due_date": "2026-05-24",
            "no_due_date": False,
            "total_to_pay_by_currency": {"EUR": "120.00"},
        }

        for override in (
            {"invoice_status": "PAID"},
            {"invoice_status": "CANCELLED"},
            {"reminded_at": "2026-05-23T08:00:00+00:00"},
            {"total_to_pay_by_currency": {"EUR": "0.00"}},
            {"total_to_pay_by_currency": {"EUR": "-20.00"}},
            {"due_date": "2026-05-25"},
            {"no_due_date": True},
        ):
            metadata = dict(base)
            metadata.update(override)
            self.assertFalse(
                invoice_is_due_for_j_minus_one_reminder(
                    metadata,
                    target_due_date=target_due_date,
                )
            )


class InvoicePendingCheckCoverageTests(unittest.TestCase):
    @staticmethod
    def _db_with_rows(rows: list[SimpleNamespace]) -> SimpleNamespace:
        return SimpleNamespace(scalars=lambda _query: SimpleNamespace(all=lambda: rows))

    @staticmethod
    def _check_row(*, status: str, amount: str = "-281.75") -> SimpleNamespace:
        return SimpleNamespace(
            reference="MODE:CHECK",
            status=status,
            currency="EUR",
            total_incl_vat=amount,
        )

    def test_received_checks_cover_balance_without_marking_invoice_paid(self) -> None:
        payment_id = uuid4()
        coverage, amounts, count = _invoice_range_pending_check_coverage(
            self._db_with_rows([self._check_row(status="CHECK_RECEIVED")]),
            metadata={
                "invoice_status": "ISSUED",
                "reconciled_manual_payment_ids": [str(payment_id)],
                "totals_by_currency": {"EUR": "281.75"},
                "total_to_pay_by_currency": {"EUR": "0.00"},
            },
        )

        self.assertEqual(coverage, "COVERED")
        self.assertEqual(amounts, {"EUR": "281.75"})
        self.assertEqual(count, 1)

    def test_partial_or_cashed_checks_do_not_suspend_reminders(self) -> None:
        payment_id = uuid4()
        metadata = {
            "invoice_status": "ISSUED",
            "reconciled_manual_payment_ids": [str(payment_id)],
            "totals_by_currency": {"EUR": "281.75"},
            "total_to_pay_by_currency": {"EUR": "181.75"},
        }

        partial, _, _ = _invoice_range_pending_check_coverage(
            self._db_with_rows([self._check_row(status="CHECK_DEPOSITED", amount="-100.00")]),
            metadata=metadata,
        )
        cashed, _, _ = _invoice_range_pending_check_coverage(
            self._db_with_rows([self._check_row(status="PAID")]),
            metadata=metadata,
        )

        self.assertEqual(partial, "PARTIAL")
        self.assertEqual(cashed, "NONE")


if __name__ == "__main__":
    unittest.main()
