from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.bookings import cancel_booking
from app.models.catalog import BookingStatus, DeliveryMode
from app.services.notifications.application.orchestrator import (
    _body_for_booking_notification,
    _build_lesson_reminder_email,
    _refresh_pending_email_reminder,
    cancel_pending_booking_reminder_notifications,
    schedule_booking_created_notifications,
    schedule_reminder_notifications_for_booking,
    schedule_waitlist_joined_notification,
    schedule_waitlist_promoted_notification,
)
from app.services.notifications.application.recipients import ResolvedRecipient
from app.services.notifications.domain.constants import (
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_CLIENT_WAITLIST_JOINED,
    NOTIFICATION_TYPE_CLIENT_WAITLIST_PROMOTED,
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
    def test_client_cancellation_stops_legacy_and_engine_reminders(self) -> None:
        booking_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()
        booking = SimpleNamespace(
            id=booking_id,
            user_id=user_id,
            session_id=session_id,
            status=BookingStatus.BOOKED,
            cancelled_at=None,
            cancellation_reason=None,
        )
        session_obj = SimpleNamespace(
            id=session_id,
            start_at_utc=datetime.now(timezone.utc) + timedelta(days=2),
        )
        current_user = SimpleNamespace(id=user_id, preferred_language="fr")
        db = MagicMock()
        db.scalar.side_effect = [booking, session_obj]

        with patch(
            "app.api.routes.bookings._can_manage_booking_owner",
            return_value=True,
        ), patch(
            "app.api.routes.bookings._effective_session_booking_rules",
            return_value=(1, 1, False),
        ), patch(
            "app.api.routes.bookings.active_restricted_forfait_for_booking",
            return_value=None,
        ), patch(
            "app.api.routes.bookings.restore_cancelled_booking_credit",
        ), patch(
            "app.api.routes.bookings.skip_pending_reminders_for_booking",
        ) as skip_legacy, patch(
            "app.api.routes.bookings.cancel_pending_booking_reminder_notifications",
        ) as cancel_engine, patch(
            "app.api.routes.bookings.schedule_booking_cancelled_notifications",
            return_value=[],
        ), patch(
            "app.api.routes.bookings._promote_waitlist_if_possible",
            return_value=[],
        ):
            response = cancel_booking(booking_id, db=db, current_user=current_user)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        skip_legacy.assert_called_once()
        cancel_engine.assert_called_once_with(
            db,
            booking_id=booking_id,
            reason="Booking cancelled by client",
            now=booking.cancelled_at,
        )

    def test_cancelling_a_booking_cancels_pending_engine_reminders(self) -> None:
        now = datetime(2026, 8, 25, 19, 49, tzinfo=timezone.utc)
        pending_email = SimpleNamespace(
            status=NOTIFICATION_STATUS_PENDING,
            skipped_at=None,
            failure_reason=None,
            updated_at=None,
        )
        queued_sms = SimpleNamespace(
            status=NOTIFICATION_STATUS_QUEUED,
            skipped_at=None,
            failure_reason=None,
            updated_at=None,
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [pending_email, queued_sms]

        cancelled = cancel_pending_booking_reminder_notifications(
            db,
            booking_id=uuid4(),
            reason="Booking cancelled by client",
            now=now,
        )

        self.assertEqual(cancelled, 2)
        for notification in (pending_email, queued_sms):
            self.assertEqual(notification.status, NOTIFICATION_STATUS_CANCELLED)
            self.assertEqual(notification.skipped_at, now)
            self.assertEqual(notification.failure_reason, "Booking cancelled by client")
            self.assertEqual(notification.updated_at, now)

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
            teacher_names=["Prof Test", "Guest Teacher"],
            language="en",
            account_url="https://app.example.test/client?tab=planning",
        )

        self.assertEqual(subject, "Lesson reminder - Private piano lesson")
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("Sunday, August 2, 2026", body)
        self.assertIn("18:00 – 19:00", body)
        self.assertIn("Asia/Riyadh", body)
        self.assertIn("Join the Zoom lesson", body)
        self.assertIn('href="https://example.test/online-lesson"', body)
        self.assertIn("If the button does not work, copy this link", body)
        self.assertIn("View or manage my booking", body)
        self.assertIn("Teachers", body)
        self.assertIn("Prof Test, Guest Teacher", body)
        self.assertIn('href="https://app.example.test/client?tab=planning"', body)

    def test_physical_reminder_includes_address_and_main_door_code_in_french(self) -> None:
        _, body = _build_lesson_reminder_email(
            recipient_name="Camille",
            student_name="Alma",
            course_type_name="Cours collectif",
            start_at=datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc),
            timezone_name="Europe/Paris",
            location_name="Rue de la Pompe",
            location_address="19 rue de la Pompe",
            location_access_instructions="1961A",
            meeting_link=None,
            teacher_names=["Prof Test"],
            language="fr",
        )

        self.assertIn("Rue de la Pompe", body)
        self.assertIn("Adresse :</strong> 19 rue de la Pompe", body)
        self.assertIn("Code de la porte principale :</strong> 1961A", body)

    def test_physical_reminder_localizes_access_details_in_english(self) -> None:
        _, body = _build_lesson_reminder_email(
            recipient_name="Camille",
            student_name="Alma",
            course_type_name="Cours collectif",
            start_at=datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc),
            timezone_name="Europe/Paris",
            location_name="Rue de la Pompe",
            location_address="19 rue de la Pompe",
            location_access_instructions="1961A",
            meeting_link=None,
            teacher_names=["Prof Test"],
            language="en",
        )

        self.assertIn("Address :</strong> 19 rue de la Pompe", body)
        self.assertIn("Main door code :</strong> 1961A", body)

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
        fake_db = _FakeSession([location, student, guardian])
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
            "app.services.notifications.application.orchestrator._effective_session_professors",
            return_value=[teacher],
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
        self.assertIn("Prof Test", guardian_kwargs["body_snapshot"])
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

    def test_waitlist_emails_explain_join_and_automatic_promotion(self) -> None:
        now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
        session_id = uuid4()
        student_id = uuid4()
        recipient_id = uuid4()
        booking = SimpleNamespace(id=uuid4(), session_id=session_id, user_id=student_id)
        session_obj = SimpleNamespace(
            id=session_id,
            location_id=uuid4(),
            start_at_utc=datetime(2026, 8, 14, 17, 0, tzinfo=timezone.utc),
            timezone="Europe/Paris",
        )
        course_type = SimpleNamespace(id=uuid4(), name="Cours collectif")
        student = SimpleNamespace(first_name="Gabrielle", last_name="Partula", email="student@example.test")
        location = SimpleNamespace(name="Rue de Richelieu", timezone="Europe/Paris")
        recipient_contact = SimpleNamespace(preferred_language="fr", timezone="Europe/Paris")
        recipient = ResolvedRecipient(
            contact_type="USER",
            contact_id=recipient_id,
            email="parent@example.test",
            phone=None,
        )

        for promoted in (False, True):
            with self.subTest(promoted=promoted):
                fake_db = _FakeSession([student, location, recipient_contact])
                created_notification_id = uuid4()
                with patch(
                    "app.services.notifications.application.orchestrator._booking_context",
                    return_value=(session_obj, course_type),
                ), patch(
                    "app.services.notifications.application.orchestrator.resolve_client_booking_notification_recipient",
                    return_value=recipient,
                ), patch(
                    "app.services.notifications.application.orchestrator.create_domain_event",
                    return_value=SimpleNamespace(id=uuid4()),
                ), patch(
                    "app.services.notifications.application.orchestrator.create_notification_if_new",
                    return_value=SimpleNamespace(id=created_notification_id),
                ) as create_notification:
                    if promoted:
                        queued = schedule_waitlist_promoted_notification(
                            fake_db,
                            booking=booking,
                            occurred_at=now,
                        )
                    else:
                        queued = schedule_waitlist_joined_notification(
                            fake_db,
                            booking=booking,
                            actor_user_id=student_id,
                            occurred_at=now,
                            waitlist_position=2,
                        )

                kwargs = create_notification.call_args.kwargs
                expected_type = (
                    NOTIFICATION_TYPE_CLIENT_WAITLIST_PROMOTED
                    if promoted
                    else NOTIFICATION_TYPE_CLIENT_WAITLIST_JOINED
                )
                self.assertEqual(kwargs["notification_type"], expected_type)
                self.assertEqual(kwargs["recipient_email"], "parent@example.test")
                self.assertIn("Gabrielle Partula", kwargs["body_snapshot"])
                self.assertIn("Rue de Richelieu", kwargs["body_snapshot"])
                if promoted:
                    self.assertIn("Votre place est confirmée", kwargs["subject"])
                    self.assertIn("Une place s’est libérée", kwargs["body_snapshot"])
                else:
                    self.assertIn("Inscription sur liste d’attente", kwargs["subject"])
                    self.assertIn("Position sur la liste", kwargs["body_snapshot"])
                    self.assertIn(">2<", kwargs["body_snapshot"])
                self.assertEqual(len(queued), 1)
                self.assertEqual(queued[0].notification_id, created_notification_id)

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
        fake_db = _FakeSession([session_obj, course_type, student, location, planning_config])

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
            "app.services.notifications.application.orchestrator._effective_session_professors",
            return_value=[teacher],
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
