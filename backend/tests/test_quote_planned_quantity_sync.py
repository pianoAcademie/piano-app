from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _sync_typeform_planned_quote_line_quantities


def _line(*, activity_id, quantity: str, automatic_key: str | None = None, planned: bool = True):
    meta: dict[str, object] = {}
    if automatic_key:
        meta["typeform_automatic_line"] = automatic_key
    if planned:
        meta["typeform_planned_quantity_applied"] = True
        meta["typeform_planned_quantity"] = quantity
    return SimpleNamespace(
        activity_id=activity_id,
        line_category="service",
        line_type="item",
        pricing_unit="session",
        quantity=Decimal(quantity),
        unit_price_ht=Decimal("18.33"),
        unit_vat_amount=Decimal("3.67"),
        amount_ht=Decimal("0.00"),
        amount_vat=Decimal("0.00"),
        amount_ttc=Decimal("0.00"),
        meta=meta,
        updated_at=None,
    )


class QuotePlannedQuantitySyncTests(unittest.TestCase):
    def test_realigns_intake_line_to_final_planning_count(self) -> None:
        activity_id = uuid4()
        line = _line(
            activity_id=activity_id,
            quantity="29.00",
            automatic_key="online_solfege",
        )
        recommendation_key = f"{activity_id}:online_solfege"
        snapshot = {
            "sessions": [
                {
                    "activity_id": str(activity_id),
                    "recommendation_key": recommendation_key,
                    "date": f"2027-01-{day:02d}",
                }
                for day in range(1, 27)
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([line], calendar_snapshot=snapshot)

        self.assertTrue(changed)
        self.assertEqual(line.quantity, Decimal("26.00"))
        self.assertEqual(line.amount_ht, Decimal("476.58"))
        self.assertEqual(line.amount_vat, Decimal("95.42"))
        self.assertEqual(line.amount_ttc, Decimal("572.00"))
        self.assertEqual(line.meta["typeform_planned_quantity"], "26.00")

    def test_keeps_manual_line_quantity_unchanged(self) -> None:
        activity_id = uuid4()
        line = _line(activity_id=activity_id, quantity="29.00", planned=False)
        snapshot = {
            "sessions": [
                {"activity_id": str(activity_id), "date": f"2027-02-{day:02d}"}
                for day in range(1, 27)
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([line], calendar_snapshot=snapshot)

        self.assertFalse(changed)
        self.assertEqual(line.quantity, Decimal("29.00"))

    def test_uses_recommendation_key_for_duplicate_activity_lines(self) -> None:
        activity_id = uuid4()
        first = _line(activity_id=activity_id, quantity="5.00", automatic_key="first")
        second = _line(activity_id=activity_id, quantity="5.00", automatic_key="second")
        snapshot = {
            "sessions": [
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:first"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:first"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
                {"activity_id": str(activity_id), "recommendation_key": f"{activity_id}:second"},
            ]
        }

        changed = _sync_typeform_planned_quote_line_quantities([first, second], calendar_snapshot=snapshot)

        self.assertTrue(changed)
        self.assertEqual(first.quantity, Decimal("2.00"))
        self.assertEqual(second.quantity, Decimal("3.00"))


if __name__ == "__main__":
    unittest.main()
