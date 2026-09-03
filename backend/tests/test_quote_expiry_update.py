from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _apply_quote_expiry_days_update,
    _apply_sent_quote_expiration_update,
    _mark_quote_sent_for_first_delivery,
    _quote_expiry_days_for_context,
    _sync_draft_quote_expiry_days_from_type,
)
from app.services.quotes.quote_documents import display_quote_expires_at


class QuoteExpiryUpdateTests(unittest.TestCase):
    def test_sent_quote_expiration_can_be_changed_to_a_future_instant(self) -> None:
        now = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
        sent_at = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        original_expiration = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
        next_expiration = datetime(2026, 8, 12, 18, 30, tzinfo=timezone.utc)
        quote = SimpleNamespace(
            status="sent",
            sent_at=sent_at,
            expires_at=original_expiration,
            expiry_days=5,
            meta={"reminder_offsets_sent": [48, 24], "other": "kept"},
            reminder_sent_at=datetime(2026, 8, 4, 8, 0, tzinfo=timezone.utc),
            updated_at=None,
        )

        previous, updated, changed = _apply_sent_quote_expiration_update(
            quote,
            next_expiration,
            now=now,
        )

        self.assertTrue(changed)
        self.assertEqual(previous, original_expiration)
        self.assertEqual(updated, next_expiration)
        self.assertEqual(quote.expires_at, next_expiration)
        self.assertEqual(quote.expiry_days, 12)
        self.assertIsNone(quote.reminder_sent_at)
        self.assertEqual(quote.meta, {"other": "kept"})
        self.assertEqual(quote.updated_at, now)

    def test_sent_quote_expiration_rejects_a_past_instant(self) -> None:
        now = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
        quote = SimpleNamespace(status="sent")

        with self.assertRaises(HTTPException) as raised:
            _apply_sent_quote_expiration_update(
                quote,
                datetime(2026, 8, 4, 9, 59, tzinfo=timezone.utc),
                now=now,
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_sent_quote_expiration_requires_an_explicit_timezone(self) -> None:
        quote = SimpleNamespace(status="sent")

        with self.assertRaises(HTTPException) as raised:
            _apply_sent_quote_expiration_update(
                quote,
                datetime(2026, 8, 12, 18, 30),
                now=datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_only_a_quote_still_awaiting_response_can_change_expiration(self) -> None:
        quote = SimpleNamespace(status="approved")

        with self.assertRaises(HTTPException) as raised:
            _apply_sent_quote_expiration_update(
                quote,
                datetime(2026, 8, 12, 18, 30, tzinfo=timezone.utc),
                now=datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(raised.exception.status_code, 409)

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

    def test_draft_syncs_expiry_days_from_quote_type_before_send(self) -> None:
        quote = SimpleNamespace(
            sent_at=None,
            quote_type_id="quote-type-id",
            expiry_days=10,
            expires_at=datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc),
            document_status="generated",
            document_hash="hash",
            document_snapshot_id="snapshot-id",
            document_generated_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
            updated_at=None,
        )
        db = SimpleNamespace(
            scalar=lambda _query: SimpleNamespace(default_expiry_days=7),
            add=lambda _row: None,
        )

        changed = _sync_draft_quote_expiry_days_from_type(db, quote)

        self.assertTrue(changed)
        self.assertEqual(quote.expiry_days, 7)
        self.assertIsNone(quote.expires_at)
        self.assertEqual(quote.document_status, "stale")
        self.assertIsNone(quote.document_hash)

    def test_default_expiry_days_uses_quote_type_default_for_paris_location(self) -> None:
        db = SimpleNamespace(scalar=lambda _query: "Paris")

        expiry_days = _quote_expiry_days_for_context(
            db,
            quote_type=SimpleNamespace(default_expiry_days=7),
            location_id="paris-location-id",
        )

        self.assertEqual(expiry_days, 7)

    def test_default_expiry_days_preserves_quote_type_for_non_paris_location(self) -> None:
        db = SimpleNamespace(scalar=lambda _query: "Bar-le-Duc")

        expiry_days = _quote_expiry_days_for_context(
            db,
            quote_type=SimpleNamespace(default_expiry_days=7),
            location_id="bar-le-duc-location-id",
        )

        self.assertEqual(expiry_days, 7)

    def test_draft_syncs_paris_quote_to_quote_type_default(self) -> None:
        quote = SimpleNamespace(
            sent_at=None,
            quote_type_id="quote-type-id",
            location_id="paris-location-id",
            expiry_days=7,
            expires_at=datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc),
            document_status="generated",
            document_hash="hash",
            document_snapshot_id="snapshot-id",
            document_generated_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
            updated_at=None,
        )
        scalar_results = iter([SimpleNamespace(default_expiry_days=3)])
        db = SimpleNamespace(
            scalar=lambda _query: next(scalar_results),
            add=lambda _row: None,
        )

        changed = _sync_draft_quote_expiry_days_from_type(db, quote)

        self.assertTrue(changed)
        self.assertEqual(quote.expiry_days, 3)
        self.assertIsNone(quote.expires_at)
        self.assertEqual(quote.document_status, "stale")

    def test_sent_quote_does_not_sync_expiry_days_from_quote_type(self) -> None:
        quote = SimpleNamespace(
            sent_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
            quote_type_id="quote-type-id",
            expiry_days=10,
            expires_at=datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc),
        )
        db = SimpleNamespace(scalar=lambda _query: SimpleNamespace(default_expiry_days=7), add=lambda _row: None)

        changed = _sync_draft_quote_expiry_days_from_type(db, quote)

        self.assertFalse(changed)
        self.assertEqual(quote.expiry_days, 10)
        self.assertEqual(quote.expires_at, datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc))

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
