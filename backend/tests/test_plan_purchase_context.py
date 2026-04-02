from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.plans import _decode_purchase_context, _encode_purchase_context


class PurchaseContextTests(unittest.TestCase):
    def test_roundtrip_preserves_booking_context(self) -> None:
        session_id = uuid4()
        booking_user_id = uuid4()
        plan = type(
            "Plan",
            (),
            {
                "id": uuid4(),
                "code": "SOLFEGE-N1",
                "kind": type("PlanKind", (), {"value": "PACK"})(),
            },
        )()

        token = _encode_purchase_context(
            plan=plan,
            email="parent@example.com",
            price_snapshot=Decimal("149.00"),
            currency="EUR",
            session_id=session_id,
            booking_user_id=booking_user_id,
            planning_return_to="/dashboard?tab=planning&session_id=abc",
        )

        payload = _decode_purchase_context(token)

        self.assertEqual(payload["formula_id"], str(plan.id))
        self.assertEqual(payload["formula_code"], "SOLFEGE-N1")
        self.assertEqual(payload["email"], "parent@example.com")
        self.assertEqual(payload["price_snapshot"], "149.00")
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(payload["session_id"], str(session_id))
        self.assertEqual(payload["booking_user_id"], str(booking_user_id))
        self.assertEqual(payload["planning_return_to"], "/dashboard?tab=planning&session_id=abc")

    def test_roundtrip_allows_standalone_formula_purchase(self) -> None:
        plan = type(
            "Plan",
            (),
            {
                "id": uuid4(),
                "code": "SOLFEGE-N2",
                "kind": type("PlanKind", (), {"value": "SUBSCRIPTION"})(),
            },
        )()

        token = _encode_purchase_context(
            plan=plan,
            email="parent@example.com",
            price_snapshot=None,
            currency="EUR",
        )

        payload = _decode_purchase_context(token)

        self.assertIsNone(payload["session_id"])
        self.assertIsNone(payload["booking_user_id"])
        self.assertIsNone(payload["planning_return_to"])


if __name__ == "__main__":
    unittest.main()
