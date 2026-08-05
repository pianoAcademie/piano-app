from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.plans import _purchase_pricing
from app.models.plan import PlanKind, PlanPriceTaxMode


class PlanFirstPurchaseChargesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = SimpleNamespace(
            name="Abonnement mensuel presentiel + studio + solfege",
            kind=PlanKind.SUBSCRIPTION,
            signup_fee_value=Decimal("70.00"),
            signup_fee_excl_vat=Decimal("70.00"),
            first_purchase_signup_fee_enabled=True,
            first_purchase_partitions_enabled=True,
            first_purchase_partitions_price_value=Decimal("25.00"),
            price_tax_mode=PlanPriceTaxMode.TTC,
        )

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("125.00"), "EUR"))
    def test_first_subscription_purchase_charges_fee_and_booklet(self, _amount: object, _vat: object) -> None:
        pricing = _purchase_pricing(
            SimpleNamespace(),
            plan=self.plan,
            country="FR",
            currency="EUR",
            on_date=SimpleNamespace(),
            has_prior_purchase=False,
        )

        self.assertTrue(pricing.first_purchase_required)
        self.assertEqual(pricing.base_price_ttc, Decimal("125.00"))
        self.assertEqual(pricing.first_purchase_fee_ttc, Decimal("70.00"))
        self.assertEqual(pricing.first_purchase_partitions_price_ttc, Decimal("25.00"))
        self.assertEqual(pricing.total_incl_vat, Decimal("220.00"))
        self.assertEqual(
            [line["code"] for line in pricing.breakdown],
            ["FORMULA", "SIGNUP_FEE", "FIRST_PURCHASE_PARTITIONS"],
        )

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("125.00"), "EUR"))
    def test_later_subscription_purchase_only_charges_monthly_price(self, _amount: object, _vat: object) -> None:
        pricing = _purchase_pricing(
            SimpleNamespace(),
            plan=self.plan,
            country="FR",
            currency="EUR",
            on_date=SimpleNamespace(),
            has_prior_purchase=True,
        )

        self.assertFalse(pricing.first_purchase_required)
        self.assertEqual(pricing.total_incl_vat, Decimal("125.00"))
        self.assertEqual([line["code"] for line in pricing.breakdown], ["FORMULA"])

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("125.00"), "EUR"))
    def test_existing_fee_values_are_safe_until_feature_is_enabled(self, _amount: object, _vat: object) -> None:
        self.plan.first_purchase_signup_fee_enabled = False
        self.plan.first_purchase_partitions_enabled = False

        pricing = _purchase_pricing(
            SimpleNamespace(),
            plan=self.plan,
            country="FR",
            currency="EUR",
            on_date=SimpleNamespace(),
            has_prior_purchase=False,
        )

        self.assertFalse(pricing.first_purchase_required)
        self.assertEqual(pricing.total_incl_vat, Decimal("125.00"))

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("280.00"), "EUR"))
    def test_first_pack_purchase_adds_only_booklet_when_no_signup_fee(self, _amount: object, _vat: object) -> None:
        self.plan.kind = PlanKind.PACK
        self.plan.signup_fee_value = Decimal("0")
        self.plan.signup_fee_excl_vat = Decimal("0")
        self.plan.first_purchase_signup_fee_enabled = False

        pricing = _purchase_pricing(
            SimpleNamespace(),
            plan=self.plan,
            country="FR",
            currency="EUR",
            on_date=SimpleNamespace(),
            has_prior_purchase=False,
        )

        self.assertEqual(pricing.total_incl_vat, Decimal("305.00"))
        self.assertEqual([line["code"] for line in pricing.breakdown], ["FORMULA", "FIRST_PURCHASE_PARTITIONS"])

    @patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("0"))
    @patch("app.api.routes.plans._plan_amount_due_and_currency", return_value=(Decimal("125.00"), "EUR"))
    def test_country_vat_is_used_for_first_purchase_items(self, _amount: object, _vat: object) -> None:
        self.plan.price_tax_mode = PlanPriceTaxMode.HT

        pricing = _purchase_pricing(
            SimpleNamespace(),
            plan=self.plan,
            country="US",
            currency="EUR",
            on_date=SimpleNamespace(),
            has_prior_purchase=False,
        )

        self.assertEqual(pricing.total_incl_vat, Decimal("220.00"))
        self.assertEqual({line["vat_rate"] for line in pricing.breakdown}, {"0"})


if __name__ == "__main__":
    unittest.main()
