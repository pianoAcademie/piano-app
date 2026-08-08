from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_config import _validate_formula_payload
from app.models.plan import PlanKind


class TrialOfferValidationTests(unittest.TestCase):
    def validate(self, *, kind: PlanKind, credits_count: int) -> None:
        _validate_formula_payload(
            kind=kind,
            credits_count=credits_count,
            pack_validity_months=12 if kind == PlanKind.PACK else None,
            forfait_start_date=date(2026, 9, 1) if kind == PlanKind.FORFAIT else None,
            forfait_end_date=date(2027, 6, 30) if kind == PlanKind.FORFAIT else None,
            monthly_price_value=Decimal("20.00"),
            currency_code="EUR",
            credit_grants=[(uuid4(), credits_count)] if kind == PlanKind.PACK else [],
            is_trial_offer=True,
        )

    def test_trial_offer_accepts_one_credit_pack(self) -> None:
        self.validate(kind=PlanKind.PACK, credits_count=1)

    def test_trial_offer_rejects_multiple_credits(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.validate(kind=PlanKind.PACK, credits_count=2)

        self.assertEqual(raised.exception.status_code, 422)

    def test_trial_offer_rejects_subscription(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            self.validate(kind=PlanKind.SUBSCRIPTION, credits_count=1)

        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
