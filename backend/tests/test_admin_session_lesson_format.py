from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.api.routes.admin import _session_type_label
from app.models.catalog import LessonFormat


class AdminSessionLessonFormatTests(unittest.TestCase):
    def test_individual_activity_is_not_inferred_from_public_visibility(self) -> None:
        session = SimpleNamespace(capacity_max=1, is_private=False, visibility_scope="EXTERNAL")
        activity = SimpleNamespace(lesson_format=LessonFormat.INDIVIDUAL, default_capacity=1)

        label = _session_type_label(session, course_type=activity, location=None)  # type: ignore[arg-type]

        self.assertEqual(label, "Individuel")

    def test_group_activity_classification_wins_over_capacity(self) -> None:
        session = SimpleNamespace(capacity_max=1)
        activity = SimpleNamespace(lesson_format=LessonFormat.GROUP, default_capacity=8)

        label = _session_type_label(session, course_type=activity, location=None)  # type: ignore[arg-type]

        self.assertEqual(label, "Collectif")

    def test_legacy_session_without_activity_uses_capacity_fallback(self) -> None:
        individual_label = _session_type_label(
            SimpleNamespace(capacity_max=1),  # type: ignore[arg-type]
            course_type=None,
            location=None,
        )
        group_label = _session_type_label(
            SimpleNamespace(capacity_max=4),  # type: ignore[arg-type]
            course_type=None,
            location=None,
        )

        self.assertEqual(individual_label, "Individuel")
        self.assertEqual(group_label, "Collectif")


if __name__ == "__main__":
    unittest.main()
