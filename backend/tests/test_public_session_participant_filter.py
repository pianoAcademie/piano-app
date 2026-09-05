from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.catalogue import (
    _participant_seats_remaining,
    _session_accepts_participant_kind,
    _session_is_public_child_trial,
)
from app.models.user import ClientKind


class PublicSessionParticipantFilterTests(unittest.TestCase):
    def test_public_child_trial_requires_explicit_publication(self) -> None:
        session_obj = SimpleNamespace(
            public_child_trial_listing_enabled=False,
            child_bookings_enabled=True,
            child_trial_bookings_enabled=True,
            allow_online_booking=True,
        )

        self.assertFalse(_session_is_public_child_trial(session_obj))
        session_obj.public_child_trial_listing_enabled = True
        self.assertTrue(_session_is_public_child_trial(session_obj))

    def test_public_child_trial_fails_closed_when_flag_is_missing(self) -> None:
        session_obj = SimpleNamespace(
            child_bookings_enabled=True,
            child_trial_bookings_enabled=True,
            allow_online_booking=True,
        )

        self.assertFalse(_session_is_public_child_trial(session_obj))

    def test_public_child_trial_requires_booking_and_trial_access(self) -> None:
        session_obj = SimpleNamespace(
            public_child_trial_listing_enabled=True,
            child_bookings_enabled=True,
            child_trial_bookings_enabled=False,
            allow_online_booking=True,
        )

        self.assertFalse(_session_is_public_child_trial(session_obj))
        session_obj.child_trial_bookings_enabled = True
        session_obj.allow_online_booking = False
        self.assertFalse(_session_is_public_child_trial(session_obj))


    def test_adult_planning_excludes_slot_closed_to_adults(self) -> None:
        session_obj = SimpleNamespace(
            child_bookings_enabled=True,
            adult_bookings_enabled=False,
        )

        self.assertFalse(_session_accepts_participant_kind(session_obj, ClientKind.ADULT))
        self.assertTrue(_session_accepts_participant_kind(session_obj, ClientKind.CHILD))

    def test_adult_planning_fails_closed_when_legacy_flag_is_missing(self) -> None:
        session_obj = SimpleNamespace(child_bookings_enabled=True)

        self.assertFalse(_session_accepts_participant_kind(session_obj, ClientKind.ADULT))

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
