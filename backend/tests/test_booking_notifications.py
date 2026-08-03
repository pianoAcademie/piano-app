from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.catalog import DeliveryMode
from app.services.notifications.application.orchestrator import (
    _body_for_booking_notification,
    _build_lesson_reminder_email,
    _refresh_pending_email_reminder,
    schedule_booking_created_notifications,
    schedule_reminder_notifications_for_booking,
)
from app.services.notifications.application.recipients import ResolvedRecipient
from app.services.notifications.domain.constants import (
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    QUEUE_NOTIFICATIONS_SCHEDULED,
)


class _FakeSession:
    def __init__(self, scalar_values: list[object | None]) -> None:
        self._scalar_values = list(scalar_values)
        self.added: list[object] = []

    def scalar(self, _query: object) -> object | None:
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)


class BookingNotificationTests(unittest.TestCase):
    def test_cancellation_uses_local_time_instead_of_utc(self) -> None:
        _, body = _body_for_booking_notification(
            is_cancellation=True,
            course_type_name="Cours collectif",
            start_at=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
            student_label="Sienna Stiebert Ambroise",
            timezone_name="Europe/Paris",
        )

        self.assertIn("12/09/2026 12:00 (Europe/Paris)", body)
        self.assertNotIn("UTC", body)

    def test_online_reminder_is_localized_and_includes_link(self) -> None:
        subject, body = _build_lesson_reminder_email(
            recipient_name="Sarah Alshaikh",
            student_name="Alya Alsowailem",
            course_type_name="Cours particulier",
            start_at=datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc),
            timezone_name="Asia/Riyadh",
            location_name="Online",
            meeting_link="https://example.test/online-lesson",
            language="en",
        )

        self.assertEqual(subject, "Lesson reminder - Private piano lesson")
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("Sunday, August 2, 2026", body)
        self.assertIn("18:00 – 19:00", body)
        self.assertIn("Asia/Riyadh", body)
        self.assertIn("Join the Zoom lesson", body)
        self.assertIn('href="https://example.test/online-lesson"', body)
        self.assertIn("If the button does not work, copy this link", body)

    def test_reminder_schedules_email_for_guardian_only(self) -> None:
        now = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
        session_id = uuid4()
        course_type_id = uuid4()
        location_id = uuid4()
        student_id = uuid4()
        guardian_id = uuid4()
        teacher_id = uuid4()
        booking = SimpleNamespace(
            id=uuid4(),
            session_id=session_id,
            user_id=student_id,
            student_start_at_utc=None,
            student_end_at_utc=None,
        )
        session_obj = SimpleNamespace(
            id=session_id,
            course_type_id=course_type_id,
            location_id=location_id,
            professor_id=teacher_id,
            substitute_teacher_id=None,
            start_at_utc=datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc),
            timezone="Europe/Paris",
            zoom_link="https://example.test/online-lesson",
        )
        course_type = SimpleNamespace(
            id=course_type_id,
            name="Cours particulier",
            mode=DeliveryMode.ONLINE,
        )
        location = SimpleNamespace(name="Online", is_online=True, timezone="Europe/Paris")
        student = SimpleNamespace(first_name="Alya", last_name="Alsowailem", email=None)
        guardian = SimpleNamespace(
            first_name="Sarah",
            last_name="Alshaikh",
            email="parent@example.test",
            preferred_language="en",
            timezone="Asia/Riyadh",
        )
        teacher = SimpleNamespace(
            id=teacher_id,
            first_name="Prof",
            last_name="Test",
            email="teacher@example.test",
            zoom_link="https://example.test/teacher-room",
            active=True,
        )
        fake_db = _FakeSession([location, student, teacher, guardian])
        guardian_recipient = ResolvedRecipient(
            contact_type="USER",
            contact_id=guardian_id,
            email="parent@example.test",
            phone=None,
        )
        notification_ids = [uuid4()]

        with patch(
            "app.services.notifications.application.orchestrator._booking_context",
            return_value=(session_obj, course_type),
        ), patch(
            "app.services.notifications.application.orchestrator._notification_rule_for_session",
            return_value=(True, 1440, False, 60),
        ), patch(
            "app.services.notifications.application.orchestrator.resolve_reminder_recipients",
            return_value=[guardian_recipient],
        ), patch(
            "app.services.notifications.application.orchestrator.effective_teacher_id_for_session",
            return_value=teacher_id,
        ), patch(
            "app.services.notifications.application.orchestrator.create_domain_event",
            return_value=SimpleNamespace(id=uuid4()),
        ), patch(
            "app.services.notifications.application.orchestrator.create_notification_if_new",
            side_effect=[SimpleNamespace(id=value) for value in notification_ids],
        ) as create_notification:
            queued = schedule_reminder_notifications_for_booking(
                fake_db,
                booking=booking,
                now=now,
            )

        self.assertEqual(create_notification.call_count, 1)
        guardian_kwargs = create_notification.call_args_list[0].kwargs
        self.assertEqual(guardian_kwargs["notification_type"], NOTIFICATION_TYPE_REMINDER_EMAIL)
        self.assertEqual(guardian_kwargs["recipient_email"], "parent@example.test")
        self.assertIn("Sunday, August 2, 2026", guardian_kwargs["body_snapshot"])
        self.assertIn("Join the Zoom lesson", guardian_kwargs["body_snapshot"])
        self.assertIn('href="https://example.test/online-lesson"', guardian_kwargs["body_snapshot"])
        self.assertEqual(guardian_kwargs["payload_snapshot"]["body_format"], "HTML")
        self.assertEqual([item.notification_id for item in queued], notification_ids)
        self.assertTrue(all(item.queue_name == QUEUE_NOTIFICATIONS_SCHEDULED for item in queued))

    def test_existing_pending_reminder_is_upgraded_to_html(self) -> None:
        notification = SimpleNamespace(
            status=NOTIFICATION_STATUS_PENDING,
            recipient_email="old@example.test",
            subject="Old reminder",
            body_snapshot="Old plain-text reminder",
            payload_snapshot={"body_format": "TEXT", "offset_minutes": 1440},
            updated_at=None,
        )
        db = _FakeSession([notification])
        now = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)

        result = _refresh_pending_email_reminder(
            db,
            idempotency_key="reminder-key",
            recipient_email="parent@example.test",
            subject="Lesson reminder",
            body="<!doctype html><p>Zoom</p>",
            meeting_link_included=True,
            now=now,
        )

        self.assertIs(result, notification)
        self.assertEqual(notification.recipient_email, "parent@example.test")
        self.assertEqual(notification.subject, "Lesson reminder")
        self.assertTrue(notification.body_snapshot.startswith("<!doctype html>"))
        self.assertEqual(notification.payload_snapshot["body_format"], "HTML")
        self.assertTrue(notification.payload_snapshot["meeting_link_included"])
        self.assertEqual(notification.updated_at, now)
        self.assertEqual(db.added, [notification])

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
