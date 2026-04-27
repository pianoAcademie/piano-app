from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _try_send_public_quote_confirmation_email
from app.models.quote import QuoteEvent


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


class QuotePublicConfirmationEmailTests(unittest.TestCase):
    def test_records_failed_event_when_confirmation_email_send_fails(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(id=uuid4(), meta={})

        with patch(
            "app.api.routes.quotes._resolve_recipient_email",
            return_value="sandra.baes@gmail.com",
        ), patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes._send_quote_email",
            side_effect=RuntimeError("SMTP send exception"),
        ):
            _try_send_public_quote_confirmation_email(
                db,
                quote=quote,
                lines=[],
                usage_context="QUOTE_APPROVED",
                kind="quote_public_approved_confirmation",
            )

        failure_events = [
            row for row in db.added
            if isinstance(row, QuoteEvent) and row.event_type == "quote_public_confirmation_email_failed"
        ]
        self.assertEqual(len(failure_events), 1)
        self.assertEqual(db.rollback_count, 1)
        self.assertGreaterEqual(db.commit_count, 1)
        self.assertEqual(failure_events[0].payload.get("recipient_email"), "sandra.baes@gmail.com")
        self.assertEqual(failure_events[0].payload.get("kind"), "quote_public_approved_confirmation")

    def test_records_skipped_event_when_recipient_email_is_missing(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(id=uuid4(), meta={})

        with patch(
            "app.api.routes.quotes._resolve_recipient_email",
            return_value=None,
        ):
            _try_send_public_quote_confirmation_email(
                db,
                quote=quote,
                lines=[],
                usage_context="QUOTE_APPROVED",
                kind="quote_public_approved_confirmation",
            )

        skipped_events = [
            row for row in db.added
            if isinstance(row, QuoteEvent) and row.event_type == "quote_public_confirmation_email_skipped"
        ]
        self.assertEqual(len(skipped_events), 1)
        self.assertEqual(skipped_events[0].payload.get("reason"), "missing_recipient_email")


if __name__ == "__main__":
    unittest.main()
