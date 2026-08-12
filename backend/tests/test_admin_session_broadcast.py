from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.routes.admin import broadcast_admin_session_message
from app.models.ops import CommunicationSenderCategory
from app.schemas.admin import AdminSessionBroadcastRequest
from app.services.providers.sms import SmsProviderSendResult


class _FakeDb:
    def __init__(self, session: SimpleNamespace) -> None:
        self.session = session
        self.commits = 0

    def scalar(self, _statement: object) -> SimpleNamespace:
        return self.session

    def commit(self) -> None:
        self.commits += 1


class AdminSessionBroadcastTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = SimpleNamespace(
            id=uuid4(),
            title="Cours collectif",
            professor_id=uuid4(),
        )
        self.actor = SimpleNamespace(
            id=uuid4(),
            first_name="Admin",
            last_name="Test",
            email="admin@example.com",
        )

    def test_email_broadcast_still_sends_formatted_group_note(self) -> None:
        db = _FakeDb(self.session)
        recipient_id = uuid4()
        payload = AdminSessionBroadcastRequest(
            channel="EMAIL",
            audience="SELF",
            subject="Note de groupe",
            body="<p>Bonjour au groupe</p>",
            body_format="HTML",
        )

        with (
            patch(
                "app.api.routes.admin._single_user_recipient_map",
                return_value={"admin@example.com": recipient_id},
            ),
            patch("app.api.routes.admin.send_session_operation_email") as send_email,
        ):
            result = broadcast_admin_session_message(
                session_id=self.session.id,
                payload=payload,
                db=db,
                current_user=self.actor,
            )

        self.assertEqual(result.channel.value, "EMAIL")
        self.assertEqual(result.recipient_count, 1)
        send_email.assert_called_once()
        sent = send_email.call_args.kwargs
        self.assertEqual(sent["to_email"], "admin@example.com")
        self.assertEqual(sent["body"], "<p>Bonjour au groupe</p>")
        self.assertEqual(sent["body_format"], "HTML")

    def test_sms_broadcast_uses_provider_and_reports_partial_failure(self) -> None:
        db = _FakeDb(self.session)
        first_recipient_id = uuid4()
        second_recipient_id = uuid4()
        payload = AdminSessionBroadcastRequest(
            channel="SMS",
            audience="SELF",
            subject="Note de groupe",
            body="<p>Bonjour <strong>au groupe</strong> &amp; aux parents</p>",
            body_format="HTML",
        )
        provider_results = [
            SmsProviderSendResult(
                ok=True,
                provider_name="BREVO",
                provider_message_id="sms-ok",
                provider_status="SENT",
            ),
            SmsProviderSendResult(
                ok=False,
                provider_name="BREVO",
                provider_message_id="sms-failed",
                provider_status="FAILED",
                error_message="Quota depasse",
            ),
        ]

        with (
            patch(
                "app.api.routes.admin._single_user_recipient_map",
                return_value={
                    "+33600000001": first_recipient_id,
                    "+33600000002": second_recipient_id,
                },
            ),
            patch(
                "app.api.routes.admin.send_provider_sms",
                side_effect=provider_results,
            ) as send_sms,
        ):
            result = broadcast_admin_session_message(
                session_id=self.session.id,
                payload=payload,
                db=db,
                current_user=self.actor,
            )

        self.assertEqual(result.channel.value, "SMS")
        self.assertEqual(result.recipient_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(db.commits, 1)
        self.assertIn("Quota depasse", result.details[0])
        self.assertEqual(send_sms.call_count, 2)
        first_send = send_sms.call_args_list[0].kwargs
        self.assertEqual(first_send["message"], "Bonjour au groupe & aux parents")
        self.assertEqual(first_send["sender_category"], CommunicationSenderCategory.OTHER_USER)
        self.assertEqual(first_send["sender_user_id"], self.actor.id)
        self.assertEqual(first_send["sender_label"], "Admin Test")
        self.assertEqual(first_send["professor_id"], self.session.professor_id)

    def test_sms_broadcast_returns_gateway_error_when_provider_rejects_every_message(self) -> None:
        db = _FakeDb(self.session)
        payload = AdminSessionBroadcastRequest(
            channel="SMS",
            audience="SELF",
            subject="Note de groupe",
            body="Bonjour au groupe",
            body_format="TEXT",
        )

        with (
            patch(
                "app.api.routes.admin._single_user_recipient_map",
                return_value={"+33600000001": uuid4()},
            ),
            patch(
                "app.api.routes.admin.send_provider_sms",
                return_value=SmsProviderSendResult(
                    ok=False,
                    provider_name="BREVO",
                    provider_message_id="sms-failed",
                    provider_status="FAILED",
                    error_message="Cle API invalide",
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                broadcast_admin_session_message(
                    session_id=self.session.id,
                    payload=payload,
                    db=db,
                    current_user=self.actor,
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("Cle API invalide", str(raised.exception.detail))
        self.assertEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
