import unittest

from pydantic import ValidationError

from app.schemas.auth import PresenceHeartbeatRequest


class PresenceChannelSchemaTests(unittest.TestCase):
    def test_accepts_detailed_and_legacy_presence_channels(self) -> None:
        channels = (
            "WEB",
            "MOBILE_APP",
            "WEB_DESKTOP",
            "WEB_MOBILE",
            "INSTALLED_WEB",
            "NATIVE_APP",
        )

        for channel in channels:
            with self.subTest(channel=channel):
                payload = PresenceHeartbeatRequest(channel=channel)
                self.assertEqual(payload.channel, channel)

    def test_rejects_unknown_presence_channel(self) -> None:
        with self.assertRaises(ValidationError):
            PresenceHeartbeatRequest(channel="APPLICATION")


if __name__ == "__main__":
    unittest.main()
