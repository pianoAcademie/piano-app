from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _quote_per_course_discounts_by_schedule_key


def _service(*, activity_id, quantity: str, amount: str, second: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        activity_id=activity_id,
        line_category="service",
        line_type="item",
        quantity=quantity,
        amount_ttc=amount,
        meta={
            "typeform_second_course": second,
            "typeform_automatic_line": "second_piano_course" if second else None,
        },
    )


def _discount(*, title: str, quantity: str, amount: str, code: str):
    return SimpleNamespace(
        id=uuid4(),
        activity_id=None,
        line_category="product",
        line_type="discount",
        title=title,
        quantity=quantity,
        amount_ttc=amount,
        meta={"discount_rule_code": code},
    )


class QuoteIntegrationPricingTests(unittest.TestCase):
    def test_discounts_are_assigned_to_one_schedule_only(self) -> None:
        activity_id = uuid4()
        primary = _service(activity_id=activity_id, quantity="33", amount="1254")
        second = _service(activity_id=activity_id, quantity="32", amount="1024", second=True)
        family = _discount(
            title="Remise famille",
            quantity="33",
            amount="-132",
            code="REMISE_FAMILLE",
        )
        second_family = _discount(
            title="Remise famille - 2e cours",
            quantity="32",
            amount="-96",
            code="REMISE_FAMILLE_DEUXIEME_COURS",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [primary, second, family, second_family],
            {str(activity_id)},
        )

        self.assertEqual(result[f"{activity_id}:line:{primary.id}"], [family])
        self.assertEqual(result[f"{activity_id}:second_piano_course"], [second_family])

    def test_second_course_label_wins_when_quantities_differ(self) -> None:
        activity_id = uuid4()
        primary = _service(activity_id=activity_id, quantity="32", amount="704")
        second = _service(activity_id=activity_id, quantity="31", amount="558", second=True)
        discount = _discount(
            title="Remise 2e cours - Bar-le-Duc",
            quantity="32",
            amount="-64",
            code="REMISE_DEUXIEME_COURS_BAR_LE_DUC",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [primary, second, discount],
            {str(activity_id)},
        )

        self.assertEqual(result[f"{activity_id}:second_piano_course"], [discount])

    def test_flat_loyalty_discount_targets_only_positive_primary_service(self) -> None:
        piano_id = uuid4()
        solfege_id = uuid4()
        piano = _service(activity_id=piano_id, quantity="32", amount="1216")
        solfege = _service(activity_id=solfege_id, quantity="26", amount="0")
        discount = _discount(
            title="Remise fidélité",
            quantity="1",
            amount="-2",
            code="REMISE_FIDELITE",
        )

        result = _quote_per_course_discounts_by_schedule_key(
            [piano, solfege, discount],
            set(),
        )

        self.assertEqual(result[str(piano_id)], [discount])
        self.assertNotIn(str(solfege_id), result)


if __name__ == "__main__":
    unittest.main()
