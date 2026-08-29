from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.plans import _plan_purchase_parties


class PlanPurchasePartiesTests(unittest.TestCase):
    def test_family_purchase_keeps_adult_as_payer_and_child_as_owner(self) -> None:
        adult = type("UserStub", (), {"id": uuid4(), "email": "parent@example.com"})()
        child = type("UserStub", (), {"id": uuid4(), "email": "child@example.invalid"})()

        payer_contact_id, checkout_payer = _plan_purchase_parties(
            purchaser=adult,  # type: ignore[arg-type]
            owner=child,  # type: ignore[arg-type]
        )

        self.assertEqual(payer_contact_id, adult.id)
        self.assertIs(checkout_payer, adult)

    def test_self_purchase_keeps_nullable_payer_contact(self) -> None:
        adult = type("UserStub", (), {"id": uuid4(), "email": "client@example.com"})()

        payer_contact_id, checkout_payer = _plan_purchase_parties(
            purchaser=adult,  # type: ignore[arg-type]
            owner=adult,  # type: ignore[arg-type]
        )

        self.assertIsNone(payer_contact_id)
        self.assertIs(checkout_payer, adult)


if __name__ == "__main__":
    unittest.main()
