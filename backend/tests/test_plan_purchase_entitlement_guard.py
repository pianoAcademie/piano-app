from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.plans import _covering_current_plan_name


class _ExecuteResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def execute(self, _query: object) -> _ExecuteResult:
        return _ExecuteResult(self._rows)


class PlanPurchaseEntitlementGuardTests(unittest.TestCase):
    def test_blocks_pack_fully_covered_by_current_subscription(self) -> None:
        requested_plan_id = uuid4()
        subscription_plan_id = uuid4()
        studio_course_type_id = uuid4()
        db = _FakeSession([(subscription_plan_id, "Abonnement mensuel presentiel + studio + solfege")])

        with patch(
            "app.api.routes.plans.effective_entitlements_by_plan",
            return_value=(
                {
                    requested_plan_id: [studio_course_type_id],
                    subscription_plan_id: [studio_course_type_id, uuid4()],
                },
                {},
            ),
        ):
            covering_name = _covering_current_plan_name(
                db,  # type: ignore[arg-type]
                user_id=uuid4(),
                requested_plan_id=requested_plan_id,
                reference_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(covering_name, "Abonnement mensuel presentiel + studio + solfege")

    def test_allows_plan_with_additional_entitlements(self) -> None:
        requested_plan_id = uuid4()
        subscription_plan_id = uuid4()
        studio_course_type_id = uuid4()
        additional_course_type_id = uuid4()
        db = _FakeSession([(subscription_plan_id, "Abonnement studio")])

        with patch(
            "app.api.routes.plans.effective_entitlements_by_plan",
            return_value=(
                {
                    requested_plan_id: [studio_course_type_id, additional_course_type_id],
                    subscription_plan_id: [studio_course_type_id],
                },
                {},
            ),
        ):
            covering_name = _covering_current_plan_name(
                db,  # type: ignore[arg-type]
                user_id=uuid4(),
                requested_plan_id=requested_plan_id,
                reference_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )

        self.assertIsNone(covering_name)


if __name__ == "__main__":
    unittest.main()
