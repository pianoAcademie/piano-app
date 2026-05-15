from __future__ import annotations

import unittest

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.providers.sms import normalize_sms_recipient_number


class SmsProviderTests(unittest.TestCase):
    def test_normalize_sms_recipient_number_accepts_french_display_formats(self) -> None:
        self.assertEqual(normalize_sms_recipient_number("+33 6 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("06 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("0033 6 32 79 81 95"), "+33632798195")
        self.assertEqual(normalize_sms_recipient_number("33 6 32 79 81 95"), "+33632798195")


if __name__ == "__main__":
    unittest.main()
