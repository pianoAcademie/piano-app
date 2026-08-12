from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin import move_planning_reorganization_booking
from app.models.catalog import BookingStatus, SessionStatus
from app.schemas.admin import AdminPlanningReorganizationMoveRequest


class _FakeSession:
    def __init__(self, scalar_values: list[object], scalars_values: list[list[object]] | None = None) -> None:
        self._scalar_values = list(scalar_values)
        self._scalars_values = list(scalars_values or [])
        self.commit_count = 0

    def scalar(self, _query: object) -> object | None:
        return self._scalar_values.pop(0) if self._scalar_values else None

    def scalars(self, _query: object) -> SimpleNamespace:
        values = self._scalars_values.pop(0) if self._scalars_values else []
        return SimpleNamespace(all=lambda: values)

    def commit(self) -> None:
        self.commit_count += 1


class AdminPlanningReorganizationTests(unittest.TestCase):
    def test_single_move_does_not_promote_waitlist_or_enqueue_notifications(self) -> None:
        now = datetime.now(timezone.utc)
        source_session_id = uuid4()
        source_booking = SimpleNamespace(
            id=uuid4(),
            session_id=source_session_id,
            status=BookingStatus.BOOKED,
        )
        source_session = SimpleNamespace(
            id=source_session_id,
            recurrence_group_id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=now + timedelta(days=30),
        )
        target_session = SimpleNamespace(
            id=uuid4(),
            recurrence_group_id=uuid4(),
        )
        db = _FakeSession([source_booking, source_session, target_session])
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="single",
        )

        with patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence, patch(
            "app.api.routes.admin._promote_waitlist_if_possible",
        ) as promote_waitlist, patch(
            "app.api.routes.admin.enqueue_notifications",
        ) as enqueue_notifications:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once()
        promote_waitlist.assert_not_called()
        enqueue_notifications.assert_not_called()

    def test_future_series_move_does_not_promote_waitlist_or_enqueue_notifications(self) -> None:
        start_at = datetime.now(timezone.utc) + timedelta(days=30)
        source_session_id = uuid4()
        source_booking = SimpleNamespace(
            id=uuid4(),
            session_id=source_session_id,
            status=BookingStatus.BOOKED,
            user_id=uuid4(),
        )
        source_session = SimpleNamespace(
            id=source_session_id,
            recurrence_group_id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=start_at,
            timezone="Europe/Paris",
        )
        target_session = SimpleNamespace(
            id=uuid4(),
            recurrence_group_id=uuid4(),
            start_at_utc=start_at,
            timezone="Europe/Paris",
        )
        db = _FakeSession(
            [source_booking, source_session, target_session],
            scalars_values=[[source_booking]],
        )
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="series_future",
        )

        with patch(
            "app.api.routes.admin._target_sessions_for_scope",
            side_effect=[[source_session], [target_session]],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence, patch(
            "app.api.routes.admin._promote_waitlist_if_possible",
        ) as promote_waitlist, patch(
            "app.api.routes.admin.enqueue_notifications",
        ) as enqueue_notifications:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once()
        promote_waitlist.assert_not_called()
        enqueue_notifications.assert_not_called()


if __name__ == "__main__":
    unittest.main()
