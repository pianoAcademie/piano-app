from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

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


if __name__ == "__main__":
    unittest.main()
