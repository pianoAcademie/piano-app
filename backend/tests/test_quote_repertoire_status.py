from __future__ import annotations

import unittest

from app.api.routes.quotes import _initial_partition_status


class QuoteRepertoireStatusTests(unittest.TestCase):
    def test_explicit_new_enrollment_is_to_deliver(self):
        self.assertEqual(
            _initial_partition_status(intake_reenrollment=False, student_created=False),
            "TO_DELIVER",
        )

    def test_explicit_reenrollment_stays_waiting(self):
        self.assertEqual(
            _initial_partition_status(intake_reenrollment=True, student_created=True),
            "STANDBY",
        )

    def test_legacy_quote_uses_student_creation_as_fallback(self):
        self.assertEqual(
            _initial_partition_status(intake_reenrollment=None, student_created=True),
            "TO_DELIVER",
        )
        self.assertEqual(
            _initial_partition_status(intake_reenrollment=None, student_created=False),
            "STANDBY",
        )


if __name__ == "__main__":
    unittest.main()
