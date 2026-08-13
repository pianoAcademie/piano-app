from __future__ import annotations

import base64
import hashlib
import hmac
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services.webhook_security import assert_bearer_webhook_token, assert_typeform_signature


class _Request:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class WebhookSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.typeform_secret = "typeform-test-secret-with-at-least-32-characters"
        self.brevo_secret = "brevo-test-secret-with-at-least-32-characters"
        self.settings_patch = patch(
            "app.services.webhook_security.settings",
            SimpleNamespace(
                typeform_webhook_secret=self.typeform_secret,
                brevo_webhook_secret=self.brevo_secret,
            ),
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def test_accepts_valid_typeform_signature(self) -> None:
        raw_body = b'{"event_id":"evt_1"}'
        signature = "sha256=" + base64.b64encode(
            hmac.new(self.typeform_secret.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        assert_typeform_signature(raw_body=raw_body, signature=signature)

    def test_rejects_missing_or_tampered_typeform_signature(self) -> None:
        for signature in (None, "sha256=tampered"):
            with self.subTest(signature=signature), self.assertRaises(HTTPException) as context:
                assert_typeform_signature(raw_body=b"{}", signature=signature)
            self.assertEqual(context.exception.status_code, 403)

    def test_accepts_valid_brevo_bearer_token(self) -> None:
        assert_bearer_webhook_token(_Request({"authorization": f"Bearer {self.brevo_secret}"}))

    def test_rejects_invalid_brevo_bearer_token(self) -> None:
        for authorization in ("", "Basic abc", "Bearer invalid"):
            with self.subTest(authorization=authorization), self.assertRaises(HTTPException) as context:
                assert_bearer_webhook_token(_Request({"authorization": authorization}))
            self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
