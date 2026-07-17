from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.bookings import _restriction_violation_message


class _FakeSession:
    def __init__(self, active_booking_count: int) -> None:
        self.active_booking_count = active_booking_count

    def scalar(self, _query: object) -> int:
        return self.active_booking_count


class ActiveBookingRestrictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc)
        self.subscription = SimpleNamespace(id=uuid4(), user_id=uuid4())
        self.course_type_id = uuid4()
        self.session_obj = SimpleNamespace(
            course_type_id=self.course_type_id,
            start_at_utc=self.now + timedelta(days=1),
        )
        self.plan = SimpleNamespace(
            restrictions_json=[
                {
                    "period": "ACTIVE_BOOKINGS",
                    "max_bookings": 2,
                    "course_type_ids": [],
                }
            ]
        )

    def test_allows_booking_below_active_limit(self) -> None:
        violation = _restriction_violation_message(
            _FakeSession(active_booking_count=1),
            subscription=self.subscription,
            plan=self.plan,
            session_obj=self.session_obj,
            now=self.now,
        )

        self.assertIsNone(violation)

    def test_blocks_booking_at_active_limit(self) -> None:
        violation = _restriction_violation_message(
            _FakeSession(active_booking_count=2),
            subscription=self.subscription,
            plan=self.plan,
            session_obj=self.session_obj,
            now=self.now,
        )

        self.assertEqual(
            violation,
            "Restriction formule depassee: 2 reservations actives maximum",
        )

    def test_ignores_scoped_restriction_for_another_activity(self) -> None:
        self.plan.restrictions_json[0]["course_type_ids"] = [str(uuid4())]

        violation = _restriction_violation_message(
            _FakeSession(active_booking_count=2),
            subscription=self.subscription,
            plan=self.plan,
            session_obj=self.session_obj,
            now=self.now,
        )

        self.assertIsNone(violation)


if __name__ == "__main__":
    unittest.main()
