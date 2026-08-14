from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.catalogue import (
    _participant_seats_remaining,
    _session_accepts_participant_kind,
)
from app.models.user import ClientKind


class PublicSessionParticipantFilterTests(unittest.TestCase):
    def test_adult_planning_excludes_slot_closed_to_adults(self) -> None:
        session_obj = SimpleNamespace(
            child_bookings_enabled=True,
            adult_bookings_enabled=False,
        )

        self.assertFalse(_session_accepts_participant_kind(session_obj, ClientKind.ADULT))
        self.assertTrue(_session_accepts_participant_kind(session_obj, ClientKind.CHILD))

    def test_adult_remaining_seats_respects_adult_quota(self) -> None:
        session_obj = SimpleNamespace(capacity_max=6, adult_capacity_max=2)

        remaining = _participant_seats_remaining(
            session_obj,
            booked_count=4,
            adult_booked_count=1,
            participant_kind=ClientKind.ADULT,
        )

        self.assertEqual(remaining, 1)

    def test_adult_remaining_seats_cannot_exceed_global_capacity(self) -> None:
        session_obj = SimpleNamespace(capacity_max=6, adult_capacity_max=2)

        remaining = _participant_seats_remaining(
            session_obj,
            booked_count=5,
            adult_booked_count=0,
            participant_kind=ClientKind.ADULT,
        )

        self.assertEqual(remaining, 1)

    def test_unlimited_adult_quota_uses_global_remaining_seats(self) -> None:
        session_obj = SimpleNamespace(capacity_max=6, adult_capacity_max=None)

        remaining = _participant_seats_remaining(
            session_obj,
            booked_count=2,
            adult_booked_count=1,
            participant_kind=ClientKind.ADULT,
        )

        self.assertEqual(remaining, 4)


if __name__ == "__main__":
    unittest.main()
