from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.services.quotes.lifecycle_jobs import (
    _build_quote_expiry_digest_body,
    _quote_expiry_digest_date,
    _quote_student_name,
)


class QuoteExpiryAdminDigestTests(unittest.TestCase):
    def test_digest_is_due_from_5am_utc(self) -> None:
        before = datetime(2026, 5, 21, 4, 59, tzinfo=timezone.utc)
        after = datetime(2026, 5, 21, 5, 0, tzinfo=timezone.utc)

        self.assertIsNone(_quote_expiry_digest_date(before))
        self.assertEqual(_quote_expiry_digest_date(after).isoformat(), "2026-05-21")

    def test_student_name_prefers_typeform_child_name(self) -> None:
        quote = SimpleNamespace(
            meta={
                "typeform_intake": {
                    "normalized_payload": {
                        "child_first_name": "Basile",
                        "child_last_name": "Imbert",
                    }
                }
            }
        )
        prospect = SimpleNamespace(first_name="Parent", last_name="Prospect")
        client = SimpleNamespace(first_name="Client", last_name="Actif")

        self.assertEqual(_quote_student_name(quote, prospect, client), "Basile Imbert")

    def test_digest_body_contains_student_and_quote_number(self) -> None:
        quote = SimpleNamespace(
            quote_number="DV-123",
            expires_at=datetime(2026, 5, 21, 12, 30, tzinfo=timezone.utc),
            meta={},
        )
        prospect = SimpleNamespace(first_name="Ada", last_name="Lovelace")

        body = _build_quote_expiry_digest_body([(quote, prospect, None)], digest_date=datetime(2026, 5, 21).date())

        self.assertIn("Ada Lovelace", body)
        self.assertIn("DV-123", body)
        self.assertIn("12:30 UTC", body)


if __name__ == "__main__":
    unittest.main()
