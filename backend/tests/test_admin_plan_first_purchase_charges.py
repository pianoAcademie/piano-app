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

from app.api.routes.admin_clients import _admin_plan_purchase_pricing
from app.models.plan import PlanKind, PlanPriceTaxMode


class AdminPlanFirstPurchaseChargesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = SimpleNamespace(
            id=uuid4(),
            is_active=False,
            residence_country="FR",
            preferred_currency="EUR",
        )
        self.plan = SimpleNamespace(
            id=uuid4(),
            name="Abonnement solfege enfant",
            kind=PlanKind.PACK,
            signup_fee_value=Decimal("0.00"),
            signup_fee_excl_vat=Decimal("0.00"),
            first_purchase_signup_fee_enabled=False,
            first_purchase_partitions_enabled=True,
            first_purchase_partitions_price_value=Decimal("10.00"),
            price_tax_mode=PlanPriceTaxMode.TTC,
        )
        self.started_at = datetime(2026, 8, 19, tzinfo=timezone.utc)

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("130.00"), "EUR"))
    @patch("app.api.routes.admin_clients._has_prior_purchase_for_plan", return_value=False)
    @patch("app.api.routes.admin_clients.resolve_billing_profile")
    def test_admin_first_purchase_for_inactive_client_adds_partitions_to_total(
        self,
        billing_profile: object,
        _prior_purchase: object,
        _amount: object,
        _vat: object,
    ) -> None:
        billing_profile.return_value = self.client

        pricing = _admin_plan_purchase_pricing(
            SimpleNamespace(),
            client=self.client,
            plan=self.plan,
            started_at=self.started_at,
        )

        self.assertTrue(pricing.first_purchase_required)
        self.assertEqual(pricing.base_price_ttc, Decimal("130.00"))
        self.assertEqual(pricing.first_purchase_partitions_price_ttc, Decimal("10.00"))
        self.assertEqual(pricing.total_incl_vat, Decimal("140.00"))
        self.assertEqual(
            [line["code"] for line in pricing.breakdown],
            ["FORMULA", "FIRST_PURCHASE_PARTITIONS"],
        )

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("130.00"), "EUR"))
    @patch("app.api.routes.admin_clients._has_prior_purchase_for_plan", return_value=True)
    @patch("app.api.routes.admin_clients.resolve_billing_profile")
    def test_admin_later_purchase_keeps_base_total(
        self,
        billing_profile: object,
        _prior_purchase: object,
        _amount: object,
        _vat: object,
    ) -> None:
        billing_profile.return_value = self.client

        pricing = _admin_plan_purchase_pricing(
            SimpleNamespace(),
            client=self.client,
            plan=self.plan,
            started_at=self.started_at,
        )

        self.assertFalse(pricing.first_purchase_required)
        self.assertEqual(pricing.total_incl_vat, Decimal("130.00"))
        self.assertEqual([line["code"] for line in pricing.breakdown], ["FORMULA"])


if __name__ == "__main__":
    unittest.main()
