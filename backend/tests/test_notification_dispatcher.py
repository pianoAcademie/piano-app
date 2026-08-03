from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.notifications.application.dispatcher import dispatch_notification
from app.services.notifications.domain.constants import NOTIFICATION_STATUS_PENDING
from app.services.providers.email import EmailProviderSendResult


class _FakeSession:
    def __init__(self, user: object) -> None:
        self._user = user
        self.added: list[object] = []

    def scalar(self, _query: object) -> object:
        return self._user

    def add(self, value: object) -> None:
        self.added.append(value)


class NotificationDispatcherTests(unittest.TestCase):
    def test_email_journal_keeps_recipient_user_link(self) -> None:
        user_id = uuid4()
        user = SimpleNamespace(
            id=user_id,
            email="client@example.test",
            email_opt_in=True,
            lesson_reminder_email_opt_in=True,
        )
        notification = SimpleNamespace(
            status=NOTIFICATION_STATUS_PENDING,
            recipient_contact_id=user_id,
            recipient_phone=None,
            recipient_email="client@example.test",
            notification_type="client_booking_cancellation",
            channel="email",
            subject="Annulation",
            body_snapshot="Votre réservation est annulée.",
            payload_snapshot={},
            job_run_id=None,
            updated_at=None,
            provider_name=None,
            provider_message_id=None,
            provider_status=None,
            sent_at=None,
            failure_reason=None,
        )
        fake_db = _FakeSession(user)

        with patch(
            "app.services.notifications.application.dispatcher.ensure_contact_delivery_status",
        ), patch(
            "app.services.notifications.application.dispatcher.get_contact_delivery_status_for_user",
            return_value=None,
        ), patch(
            "app.services.notifications.application.dispatcher.send_provider_email",
            return_value=EmailProviderSendResult(
                ok=True,
                provider_name="BREVO",
                provider_message_id="mail-test",
                provider_status="SENT",
            ),
        ) as send_provider_email:
            result = dispatch_notification(
                fake_db,
                notification=notification,
                now=datetime(2026, 8, 3, 8, 39, tzinfo=timezone.utc),
            )

        self.assertEqual(result.sent, 1)
        self.assertEqual(send_provider_email.call_args.kwargs["recipient_user_id"], user_id)


if __name__ == "__main__":
    unittest.main()
