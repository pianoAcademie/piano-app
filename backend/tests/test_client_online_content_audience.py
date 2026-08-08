from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.clients import (  # noqa: E402
    _is_child_solfege_content_course_type,
    _member_can_access_content_course_type,
)
from app.models.user import ClientKind  # noqa: E402


class ClientOnlineContentAudienceTests(unittest.TestCase):
    def test_adult_cannot_access_child_solfege_levels_one_to_five(self) -> None:
        adult = SimpleNamespace(client_kind=ClientKind.ADULT)

        for level in range(1, 6):
            course_type = SimpleNamespace(
                code=f"SOLFEGE_LEVEL_{level}",
                name=f"Solfège niveau {level}",
                service_code="SOLFEGE",
            )
            self.assertTrue(_is_child_solfege_content_course_type(course_type))
            self.assertFalse(_member_can_access_content_course_type(adult, course_type))

    def test_child_keeps_access_to_child_solfege_content(self) -> None:
        child = SimpleNamespace(client_kind=ClientKind.CHILD)
        course_type = SimpleNamespace(
            code="SOLFEGE_ONLINE_30M",
            name="Solfege - Niveau 1",
            service_code="SOLFEGE",
        )

        self.assertTrue(_member_can_access_content_course_type(child, course_type))

    def test_adult_solfege_activity_is_not_treated_as_child_content(self) -> None:
        adult = SimpleNamespace(client_kind=ClientKind.ADULT)
        course_type = SimpleNamespace(
            code="ACT_SOLFEGE_EN_PRESENTIEL",
            name="Solfège en présentiel",
            service_code="ACTIVITY",
        )

        self.assertFalse(_is_child_solfege_content_course_type(course_type))
        self.assertTrue(_member_can_access_content_course_type(adult, course_type))


if __name__ == "__main__":
    unittest.main()
