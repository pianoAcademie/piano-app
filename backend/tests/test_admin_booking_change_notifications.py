from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.admin import (
    _normalize_email_recipient,
    _send_admin_booking_change_email,
)
from app.schemas.admin import AdminSessionBookingCreateRequest


class _FakeDb:
    def __init__(self, scalar_values: list[object]) -> None:
        self.scalar_values = list(scalar_values)

    def scalar(self, _statement: object) -> object:
        return self.scalar_values.pop(0)


class AdminBookingChangeNotificationTests(unittest.TestCase):
    def test_notification_is_opt_in_by_default(self) -> None:
        payload = AdminSessionBookingCreateRequest(client_id=uuid4())
        self.assertFalse(payload.notify_client)

    def test_synthetic_client_addresses_are_never_notified(self) -> None:
        self.assertIsNone(_normalize_email_recipient("child-123@no-email.local"))
        self.assertIsNone(_normalize_email_recipient("child@piano-academie.invalid"))
        self.assertEqual(_normalize_email_recipient("CLIENT@example.com"), "client@example.com")

    def test_series_change_sends_one_consolidated_email(self) -> None:
        now = datetime(2026, 9, 7, 16, 5, tzinfo=timezone.utc)
        course_type_id = uuid4()
        location_id = uuid4()
        teacher_id = uuid4()
        client = SimpleNamespace(
            id=uuid4(),
            first_name="Victoria Lily",
            last_name="Loubière",
            email="victoria@example.test",
        )
        recipient = SimpleNamespace(
            id=uuid4(),
            first_name="Olivia",
            last_name="Loubière",
            email="parent@example.test",
            preferred_language="fr",
        )
        actor = SimpleNamespace(
            id=uuid4(),
            first_name="Admin",
            last_name="Piano Académie",
            email="admin@example.test",
        )
        sessions = [
            SimpleNamespace(
                id=uuid4(),
                title="Solfège niveau 3",
                course_type_id=course_type_id,
                location_id=location_id,
                professor_id=teacher_id,
                start_at_utc=now,
                timezone="Europe/Paris",
            ),
            SimpleNamespace(
                id=uuid4(),
                title="Solfège niveau 3",
                course_type_id=course_type_id,
                location_id=location_id,
                professor_id=teacher_id,
                start_at_utc=now + timedelta(days=7),
                timezone="Europe/Paris",
            ),
        ]
        db = _FakeDb(
            [
                SimpleNamespace(name="Solfège niveau 3"),
                SimpleNamespace(name="Online", timezone="Europe/Paris"),
                recipient,
            ]
        )

        with (
            patch(
                "app.api.routes.admin._admin_booking_change_email_recipients",
                return_value={"parent@example.test": recipient.id},
            ),
            patch("app.api.routes.admin.send_session_operation_email") as send_email,
        ):
            sent_count = _send_admin_booking_change_email(
                db,
                client=client,
                sessions=sessions,
                operation="ADDED",
                actor=actor,
            )

        self.assertEqual(sent_count, 1)
        send_email.assert_called_once()
        sent = send_email.call_args.kwargs
        self.assertEqual(sent["to_email"], "parent@example.test")
        self.assertIn("Nombre de séances concernées : 2", sent["body"])
        self.assertIn("Victoria Lily Loubière", sent["body"])


if __name__ == "__main__":
    unittest.main()
