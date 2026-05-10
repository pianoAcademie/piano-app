from __future__ import annotations

import unittest

from app.services.quotes.recipient_resolution import _is_synthetic_email


class QuoteRecipientResolutionTests(unittest.TestCase):
    def test_synthetic_client_emails_are_not_direct_recipients(self) -> None:
        self.assertTrue(_is_synthetic_email("mms-child-sdt-ygrzjw@no-email.local"))
        self.assertTrue(_is_synthetic_email("child-123@piano-academie.invalid"))
        self.assertFalse(_is_synthetic_email("karen@example.com"))


if __name__ == "__main__":
    unittest.main()
