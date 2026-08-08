from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.email_delivery import EmailDeliveryError, send_email
from app.services.messaging_templates import MessagingDeliveryConfig


class _FailingSmtp:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FailingSmtp":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def login(self, username: str, password: str) -> None:
        return None

    def send_message(self, message) -> None:
        raise RuntimeError("smtp down")


class _SuccessfulSmtp:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_SuccessfulSmtp":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def login(self, username: str, password: str) -> None:
        return None

    def send_message(self, message) -> None:
        return None


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MessagingDeliveryConfig(
            provider="SMTP",
            from_email="no-reply@piano-academie.com",
            reply_to=None,
            subject_prefix="",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="user",
            smtp_password="pass",
            smtp_use_tls=False,
            smtp_use_ssl=False,
            smtp_timeout_seconds=10,
            frontend_base_url="https://app.piano-academie.com",
        )

    def test_send_email_returns_none_on_smtp_exception(self) -> None:
        with patch(
            "app.services.email_delivery.resolve_messaging_delivery_config",
            return_value=self.config,
        ), patch(
            "app.services.email_delivery.smtplib.SMTP",
            _FailingSmtp,
        ), patch(
            "app.services.email_delivery.log_communication",
            return_value=None,
        ):
            result = send_email(
                to_email="sandra.baes@gmail.com",
                subject="Test",
                body="Hello",
                body_format="TEXT",
                context="QUOTE_APPROVED",
            )

        self.assertIsNone(result)

    def test_send_email_returns_message_id_on_success(self) -> None:
        with patch(
            "app.services.email_delivery.resolve_messaging_delivery_config",
            return_value=self.config,
        ), patch(
            "app.services.email_delivery.smtplib.SMTP",
            _SuccessfulSmtp,
        ), patch(
            "app.services.email_delivery.log_communication",
            return_value=None,
        ) as log_communication_mock:
            db = object()
            result = send_email(
                to_email="sandra.baes@gmail.com",
                subject="Test",
                body="Hello",
                body_format="TEXT",
                context="QUOTE_APPROVED",
                db=db,
            )

        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("mail-"))
        self.assertIs(log_communication_mock.call_args.kwargs["db"], db)

    def test_send_email_can_raise_on_failure_when_requested(self) -> None:
        with patch(
            "app.services.email_delivery.resolve_messaging_delivery_config",
            return_value=self.config,
        ), patch(
            "app.services.email_delivery.smtplib.SMTP",
            _FailingSmtp,
        ), patch(
            "app.services.email_delivery.log_communication",
            return_value=None,
        ):
            with self.assertRaises(EmailDeliveryError) as context:
                send_email(
                    to_email="sandra.baes@gmail.com",
                    subject="Test",
                    body="Hello",
                    body_format="TEXT",
                    context="QUOTE_APPROVED",
                    raise_on_failure=True,
                )

        self.assertEqual(str(context.exception), "SMTP send exception")


if __name__ == "__main__":
    unittest.main()
