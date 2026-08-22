import unittest

from app.api.routes.admin import _normalize_session_participant_settings


class StudioAdultBookingInvariantTests(unittest.TestCase):
    def test_studio_sessions_always_allow_adults_without_a_separate_quota(self) -> None:
        child_enabled, adult_enabled, adult_capacity = _normalize_session_participant_settings(
            course_type_code="STUDIO_REHEARSAL",
            allows_student_bookings=True,
            child_bookings_enabled=True,
            adult_bookings_enabled=False,
            adult_capacity_max=1,
        )

        self.assertTrue(child_enabled)
        self.assertTrue(adult_enabled)
        self.assertIsNone(adult_capacity)

    def test_other_course_types_keep_their_explicit_adult_settings(self) -> None:
        child_enabled, adult_enabled, adult_capacity = _normalize_session_participant_settings(
            course_type_code="PIANO_GROUP_ONSITE_1H",
            allows_student_bookings=True,
            child_bookings_enabled=True,
            adult_bookings_enabled=True,
            adult_capacity_max=2,
        )

        self.assertTrue(child_enabled)
        self.assertTrue(adult_enabled)
        self.assertEqual(adult_capacity, 2)


if __name__ == "__main__":
    unittest.main()
