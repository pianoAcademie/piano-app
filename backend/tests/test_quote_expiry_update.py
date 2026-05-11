from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _apply_quote_expiry_days_update


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
        now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            expiry_days=10,
            expires_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
        )

        changed = _apply_quote_expiry_days_update(quote, 15, now=now)

        self.assertTrue(changed)
        self.assertEqual(quote.expiry_days, 15)
        self.assertEqual(quote.expires_at, now + timedelta(days=15))


if __name__ == "__main__":
    unittest.main()
