from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.plan_entitlements import effective_entitlements_by_plan


class _ExecuteResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeSession:
    def __init__(self, row_sets: list[list[tuple[object, ...]]]) -> None:
        self._row_sets = list(row_sets)

    def execute(self, _query: object) -> _ExecuteResult:
        return _ExecuteResult(self._row_sets.pop(0))


class EffectivePlanEntitlementsTests(unittest.TestCase):
    def test_pack_credit_grants_add_compatible_course_types_without_duplicates(self) -> None:
        plan_id = uuid4()
        explicit_course_type_id = uuid4()
        grant_course_type_id = uuid4()
        db = _FakeSession(
            [
                [(plan_id, explicit_course_type_id, "Cours collectif")],
                [
                    (plan_id, explicit_course_type_id, "Cours collectif"),
                    (plan_id, grant_course_type_id, "Studio de repetition"),
                ],
            ]
        )

        ids_map, names_map = effective_entitlements_by_plan(db, plan_ids=[plan_id])  # type: ignore[arg-type]

        self.assertEqual(set(ids_map[plan_id]), {explicit_course_type_id, grant_course_type_id})
        self.assertEqual(names_map[plan_id], ["Cours collectif", "Studio de repetition"])


if __name__ == "__main__":
    unittest.main()
