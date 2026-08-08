from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_config import _ensure_activity_trial_entitlement, _validate_activity_trial_configuration
from app.api.routes.plans import _purchase_pricing
from app.models.plan import PlanEntitlement


class _FakeDb:
    def __init__(self, scalar_values: list[object | None]) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[object] = []

    def scalar(self, _query: object) -> object | None:
        return self.scalar_values.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)


class ActivityTrialPricingTests(unittest.TestCase):
    def test_enabling_activity_adds_entitlement_to_trial_plan(self) -> None:
        plan = SimpleNamespace(id=uuid4())
        activity = SimpleNamespace(
            id=uuid4(),
            trial_course_enabled=True,
        )
        db = _FakeDb([plan, None])

        _ensure_activity_trial_entitlement(db, activity=activity)

        entitlement = next(value for value in db.added if isinstance(value, PlanEntitlement))
        self.assertEqual(entitlement.plan_id, plan.id)
        self.assertEqual(entitlement.course_type_id, activity.id)

    def test_activity_trial_price_overrides_formula_price(self) -> None:
        plan = SimpleNamespace(currency_code="EUR")
        course_type = SimpleNamespace(
            name="Cours collectif",
            service_code="COURSE",
            trial_course_enabled=True,
            trial_course_price_ttc=Decimal("27.50"),
        )

        with patch("app.api.routes.plans.resolve_vat_rate", return_value=Decimal("20.00")):
            pricing = _purchase_pricing(
                SimpleNamespace(),
                plan=plan,
                country="FR",
                currency="EUR",
                on_date=date(2026, 9, 14),
                has_prior_purchase=False,
                trial_course_type=course_type,
            )

        self.assertEqual(pricing.total_incl_vat, Decimal("27.50"))
        self.assertEqual(pricing.amount_excl_vat, Decimal("22.92"))
        self.assertEqual(pricing.vat_amount, Decimal("4.58"))
        self.assertEqual(pricing.breakdown[0]["code"], "TRIAL_COURSE")
        self.assertFalse(pricing.first_purchase_required)

    def test_disabled_activity_rejects_trial_pricing(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _purchase_pricing(
                SimpleNamespace(),
                plan=SimpleNamespace(currency_code="EUR"),
                country="FR",
                currency="EUR",
                on_date=date(2026, 9, 14),
                has_prior_purchase=False,
                trial_course_type=SimpleNamespace(
                    name="Cours collectif",
                    service_code="COURSE",
                    trial_course_enabled=False,
                    trial_course_price_ttc=Decimal("20.00"),
                ),
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_enabled_activity_requires_trial_price(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _validate_activity_trial_configuration(
                allows_student_bookings=True,
                trial_course_enabled=True,
                trial_course_price_ttc=None,
            )

        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
