from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.notifications.application.orchestrator import schedule_booking_created_notifications
from app.services.notifications.domain.constants import (
    NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
)


class _FakeSession:
    def __init__(self, scalar_values: list[object | None]) -> None:
        self._scalar_values = list(scalar_values)

    def scalar(self, _query: object) -> object | None:
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)


class BookingNotificationTests(unittest.TestCase):
    def test_confirmed_booking_notifies_session_teacher(self) -> None:
        now = datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc)
        session_id = uuid4()
        course_type_id = uuid4()
        location_id = uuid4()
        teacher_id = uuid4()
        booking = SimpleNamespace(id=uuid4(), session_id=session_id, user_id=uuid4())
        session_obj = SimpleNamespace(
            id=session_id,
            course_type_id=course_type_id,
            location_id=location_id,
            professor_id=teacher_id,
            substitute_teacher_id=None,
            start_at_utc=now + timedelta(days=14),
            timezone="Europe/Paris",
        )
        course_type = SimpleNamespace(id=course_type_id, name="Cours collectif")
        student = SimpleNamespace(first_name="Jayden", last_name="Lubin", email="parent@example.test")
        location = SimpleNamespace(name="Bar-le-Duc")
        teacher = SimpleNamespace(
            id=teacher_id,
            first_name="Prof",
            last_name="Test",
            email="prof@example.test",
            active=True,
        )
        planning_config = SimpleNamespace(notify_coach=True)
        fake_db = _FakeSession([session_obj, course_type, student, location, teacher, planning_config])

        created_notification_id = uuid4()
        with patch(
            "app.services.notifications.application.orchestrator.create_domain_event",
            return_value=SimpleNamespace(id=uuid4()),
        ), patch(
            "app.services.notifications.application.orchestrator.resolve_client_booking_notification_recipient",
            return_value=None,
        ), patch(
            "app.services.notifications.application.orchestrator.resolve_admin_booking_notification_recipients",
            return_value=[],
        ), patch(
            "app.services.notifications.application.orchestrator.render_booking_confirmation_email",
            return_value=SimpleNamespace(subject="Reservation", body="<p>OK</p>", body_format="HTML"),
        ), patch(
            "app.services.notifications.application.orchestrator.create_notification_if_new",
            return_value=SimpleNamespace(id=created_notification_id),
        ) as create_notification:
            queued = schedule_booking_created_notifications(
                fake_db,
                booking=booking,
                actor_user_id=booking.user_id,
                occurred_at=now,
            )

        create_notification.assert_called_once()
        kwargs = create_notification.call_args.kwargs
        self.assertEqual(kwargs["notification_type"], NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION)
        self.assertEqual(kwargs["recipient_type"], "PROFESSOR")
        self.assertEqual(kwargs["recipient_contact_id"], teacher_id)
        self.assertEqual(kwargs["recipient_email"], "prof@example.test")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].notification_id, created_notification_id)
        self.assertEqual(queued[0].queue_name, QUEUE_NOTIFICATIONS_IMMEDIATE)


if __name__ == "__main__":
    unittest.main()
