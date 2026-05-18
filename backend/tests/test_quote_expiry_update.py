from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _apply_quote_expiry_days_update, _mark_quote_sent_for_first_delivery
from app.services.quotes.quote_documents import display_quote_expires_at


class QuoteExpiryUpdateTests(unittest.TestCase):
    def test_same_expiry_days_preserves_existing_expiration_date(self) -> None:
        original_expiration = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(expiry_days=10, expires_at=original_expiration)

        changed = _apply_quote_expiry_days_update(
            quote,
            10,
            now=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(changed)
        self.assertEqual(quote.expiry_days, 10)
        self.assertEqual(quote.expires_at, original_expiration)

    def test_changed_expiry_days_recomputes_expiration_date(self) -> None:
        sent_at = datetime(2026, 5, 12, 9, 30, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            expiry_days=10,
            sent_at=sent_at,
            expires_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        )

        changed = _apply_quote_expiry_days_update(quote, 15, now=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc))

        self.assertTrue(changed)
        self.assertEqual(quote.expiry_days, 15)
        self.assertEqual(quote.expires_at, sent_at + timedelta(days=15))

    def test_changed_expiry_days_before_send_keeps_expiration_empty(self) -> None:
        quote = SimpleNamespace(
            expiry_days=10,
            sent_at=None,
            expires_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        )

        changed = _apply_quote_expiry_days_update(quote, 15, now=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc))

        self.assertTrue(changed)
        self.assertEqual(quote.expiry_days, 15)
        self.assertIsNone(quote.expires_at)

    def test_draft_display_expiration_projects_from_reference_date(self) -> None:
        reference_at = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            status="created",
            expiry_days=7,
            sent_at=None,
            expires_at=None,
        )

        self.assertEqual(
            display_quote_expires_at(quote, reference_at=reference_at),
            reference_at + timedelta(days=7),
        )

    def test_sent_display_expiration_uses_frozen_value(self) -> None:
        sent_at = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        frozen_expiration = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            status="sent",
            expiry_days=7,
            sent_at=sent_at,
            expires_at=frozen_expiration,
        )

        self.assertEqual(
            display_quote_expires_at(
                quote,
                reference_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
            ),
            frozen_expiration,
        )

    def test_first_send_sets_expiration_from_send_date_even_if_draft_had_expiration(self) -> None:
        sent_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            status="created",
            expiry_days=10,
            sent_at=None,
            expires_at=datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
        )

        _mark_quote_sent_for_first_delivery(quote, sent_at=sent_at)

        self.assertEqual(quote.status, "sent")
        self.assertEqual(quote.sent_at, sent_at)
        self.assertEqual(quote.expires_at, sent_at + timedelta(days=10))

    def test_resend_preserves_first_send_expiration(self) -> None:
        first_sent_at = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        expiration = first_sent_at + timedelta(days=10)
        quote = SimpleNamespace(
            status="change_requested",
            expiry_days=10,
            sent_at=first_sent_at,
            expires_at=expiration,
        )

        _mark_quote_sent_for_first_delivery(quote, sent_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc))

        self.assertEqual(quote.status, "sent")
        self.assertEqual(quote.sent_at, first_sent_at)
        self.assertEqual(quote.expires_at, expiration)


if __name__ == "__main__":
    unittest.main()
