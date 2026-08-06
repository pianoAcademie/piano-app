from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.mobile_push import _localized_content
from app.services.mobile_push_provider import _secret_value, send_mobile_push


class MobilePushTests(unittest.TestCase):
    def test_localized_content_uses_english_when_available(self) -> None:
        title, body = _localized_content(
            language="en",
            title_fr="Titre",
            body_fr="Message",
            title_en="Title",
            body_en="Body",
        )
        self.assertEqual((title, body), ("Title", "Body"))

    def test_localized_content_falls_back_to_french(self) -> None:
        title, body = _localized_content(
            language="en",
            title_fr="Titre",
            body_fr="Message",
            title_en=None,
            body_en=None,
        )
        self.assertEqual((title, body), ("Titre", "Message"))

    def test_secret_value_accepts_escaped_newlines(self) -> None:
        self.assertEqual(_secret_value("line1\\nline2"), "line1\nline2")

    def test_disabled_provider_never_attempts_delivery(self) -> None:
        fake_settings = SimpleNamespace(push_notifications_enabled=False)
        with patch("app.services.mobile_push_provider.settings", fake_settings):
            result = send_mobile_push(
                platform="IOS",
                token="token",
                title="Titre",
                body="Message",
                data={},
            )
        self.assertFalse(result.accepted)
        self.assertEqual(result.provider_status, "DISABLED")


if __name__ == "__main__":
    unittest.main()
