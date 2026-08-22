from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.family_billing_allocations import (
    BillingAllocationInput,
    allocate_signed_amount_by_targets,
    allocate_billing_total,
    validate_billing_allocations,
)


class FamilyBillingAllocationTests(unittest.TestCase):
    def test_equal_percent_split_absorbs_rounding_on_last_payer(self) -> None:
        first = uuid4()
        second = uuid4()
        result = allocate_billing_total(
            Decimal("1063.00"),
            [
                BillingAllocationInput(first, "PERCENT", Decimal("50")),
                BillingAllocationInput(second, "PERCENT", Decimal("50")),
            ],
        )
        self.assertEqual(result[first], Decimal("531.50"))
        self.assertEqual(result[second], Decimal("531.50"))

    def test_fixed_amount_requires_and_uses_remainder_payer(self) -> None:
        first = uuid4()
        second = uuid4()
        result = allocate_billing_total(
            Decimal("1232.00"),
            [
                BillingAllocationInput(first, "FIXED", Decimal("500")),
                BillingAllocationInput(second, "REMAINDER", None),
            ],
        )
        self.assertEqual(result[first], Decimal("500.00"))
        self.assertEqual(result[second], Decimal("732.00"))

    def test_mixed_percent_fixed_and_remainder(self) -> None:
        percent_payer = uuid4()
        fixed_payer = uuid4()
        remainder_payer = uuid4()
        result = allocate_billing_total(
            Decimal("1000"),
            [
                BillingAllocationInput(percent_payer, "PERCENT", Decimal("40")),
                BillingAllocationInput(fixed_payer, "FIXED", Decimal("150")),
                BillingAllocationInput(remainder_payer, "REMAINDER", None),
            ],
        )
        self.assertEqual(result[percent_payer], Decimal("400.00"))
        self.assertEqual(result[fixed_payer], Decimal("150.00"))
        self.assertEqual(result[remainder_payer], Decimal("450.00"))

    def test_rejects_percent_total_without_remainder(self) -> None:
        with self.assertRaisesRegex(ValueError, "100 %"):
            validate_billing_allocations(
                [
                    BillingAllocationInput(uuid4(), "PERCENT", Decimal("40")),
                    BillingAllocationInput(uuid4(), "PERCENT", Decimal("40")),
                ]
            )

    def test_rejects_fixed_total_above_invoice(self) -> None:
        with self.assertRaisesRegex(ValueError, "dépasse"):
            allocate_billing_total(
                Decimal("100"),
                [
                    BillingAllocationInput(uuid4(), "FIXED", Decimal("120")),
                    BillingAllocationInput(uuid4(), "REMAINDER", None),
                ],
            )

    def test_signed_line_allocation_preserves_positive_cents(self) -> None:
        payer_a = uuid4()
        payer_b = uuid4()
        result = allocate_signed_amount_by_targets(
            Decimal("33.05"),
            {payer_a: Decimal("50.00"), payer_b: Decimal("50.00")},
        )
        self.assertEqual(sum(result.values()), Decimal("33.05"))
        self.assertEqual(sorted(result.values()), [Decimal("16.52"), Decimal("16.53")])

    def test_signed_line_allocation_preserves_credit_cents(self) -> None:
        payer_a = uuid4()
        payer_b = uuid4()
        result = allocate_signed_amount_by_targets(
            Decimal("-100.00"),
            {payer_a: Decimal("30.00"), payer_b: Decimal("70.00")},
        )
        self.assertEqual(result[payer_a], Decimal("-30.00"))
        self.assertEqual(result[payer_b], Decimal("-70.00"))
        self.assertEqual(sum(result.values()), Decimal("-100.00"))


if __name__ == "__main__":
    unittest.main()
