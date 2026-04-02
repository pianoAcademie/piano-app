from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.bookings import _plan_supports_course_access, _select_eligible_subscription
from app.api.routes.clients import _active_formula_options_for_course_type
from app.models.plan import PlanKind, SubscriptionStatus


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = list(rows)

    def all(self) -> list[object]:
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self._rows = list(rows)

    def all(self) -> list[tuple[object, object]]:
        return list(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_values: list[object] | None = None,
        scalar_rows: list[object] | None = None,
        execute_rows: list[tuple[object, object]] | None = None,
    ) -> None:
        self._scalar_values = list(scalar_values or [])
        self._scalar_rows = list(scalar_rows or [])
        self._execute_rows = list(execute_rows or [])
        self.added: list[object] = []

    def scalar(self, _query: object) -> object | None:
        if self._scalar_values:
            return self._scalar_values.pop(0)
        return None

    def scalars(self, _query: object) -> _ScalarResult:
        return _ScalarResult(self._scalar_rows)

    def execute(self, _query: object) -> _ExecuteResult:
        return _ExecuteResult(self._execute_rows)

    def add(self, obj: object) -> None:
        self.added.append(obj)


class FormulaCompatibilityTests(unittest.TestCase):
    def test_pack_matches_course_access_via_credit_type(self) -> None:
        plan_id = uuid4()
        course_type_id = uuid4()
        credit_type_id = uuid4()
        fake_db = _FakeSession(scalar_values=[None, uuid4()])

        supported = _plan_supports_course_access(
            fake_db,
            plan_id=plan_id,
            plan_kind=PlanKind.PACK,
            course_type_id=course_type_id,
            credit_type_id=credit_type_id,
        )

        self.assertTrue(supported)

    def test_formula_options_include_pack_matched_by_credit_type(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM-STUDIO-1",
            kind=PlanKind.PACK,
            name="1 reservation de studio",
            description="Pack studio",
            options_json=[],
            payment_methods_json=["CARD_ONLINE"],
            monthly_price_value=15,
            monthly_price_excl_vat=None,
            currency_code="EUR",
        )
        fake_db = _FakeSession(
            scalar_rows=[plan],
            scalar_values=[None, uuid4()],
        )

        options = _active_formula_options_for_course_type(
            fake_db,
            course_type_id=uuid4(),
            course_type_name="Reservation studio de repetition",
            credit_type_id=uuid4(),
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].formula_code, "FORM-STUDIO-1")
        self.assertEqual(options[0].restriction_labels, ["Reservation studio de repetition"])

    def test_select_eligible_subscription_accepts_pack_matched_by_credit_type(self) -> None:
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ends_at=None,
            credits_remaining=3,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            bookings_blocked=False,
            cancellation_effective_at=None,
            suspension_starts_at=None,
            suspension_ends_at=None,
        )
        plan = SimpleNamespace(
            id=subscription.plan_id,
            kind=PlanKind.PACK,
            active=True,
        )
        course_type = SimpleNamespace(id=uuid4(), credit_type_id=uuid4())
        fake_db = _FakeSession(
            scalar_values=[course_type, None, uuid4()],
            execute_rows=[(subscription, plan)],
        )

        selected = _select_eligible_subscription(
            fake_db,
            user_id=subscription.user_id,
            course_type_id=course_type.id,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            requested_subscription_id=None,
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertIsNotNone(selected)
        selected_subscription, selected_plan = selected
        self.assertIs(selected_subscription, subscription)
        self.assertIs(selected_plan, plan)


if __name__ == "__main__":
    unittest.main()
