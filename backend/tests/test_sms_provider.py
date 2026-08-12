from __future__ import annotations

import unittest

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.ops import CommunicationSenderCategory
from app.services.providers.sms import normalize_sms_recipient_number, send_provider_sms


class SmsProviderTests(unittest.TestCase):
    def test_normalize_sms_recipient_number_accepts_french_display_formats(self) -> None:
        self.assertEqual(normalize_sms_recipient_number("+33 6 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("06 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("0033 6 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("33 6 32 79 81 95"), "+33632798195")

    def test_log_provider_keeps_explicit_sender_attribution(self) -> None:
        sender_user_id = uuid4()
        professor_id = uuid4()
        recipient_user_id = uuid4()

        with (
            patch(
                "app.services.providers.sms.resolve_messaging_sms_delivery_config",
                return_value=SimpleNamespace(provider="LOG"),
            ),
            patch("app.services.providers.sms.log_communication") as log_communication,
        ):
            result = send_provider_sms(
                to_phone="06 32 79 81 95",
                message="Information groupe",
                context="ADMIN_SESSION_BROADCAST_SMS",
                subject="Note de groupe",
                recipient_user_id=recipient_user_id,
                sender_category=CommunicationSenderCategory.OTHER_USER,
                sender_user_id=sender_user_id,
                sender_label="Admin Test",
                professor_id=professor_id,
            )

        self.assertTrue(result.ok)
        log_communication.assert_called_once()
        logged = log_communication.call_args.kwargs
        self.assertEqual(logged["recipient"], "+33632798195")
        self.assertEqual(logged["recipient_user_id"], recipient_user_id)
        self.assertEqual(logged["sender_category"], CommunicationSenderCategory.OTHER_USER)
        self.assertEqual(logged["sender_user_id"], sender_user_id)
        self.assertEqual(logged["sender_label"], "Admin Test")
        self.assertEqual(logged["professor_id"], professor_id)


if __name__ == "__main__":
    unittest.main()
