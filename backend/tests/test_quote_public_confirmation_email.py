from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _try_send_public_quote_admin_notification_email,
    _try_send_public_quote_confirmation_email,
)
from app.models.quote import QuoteEmailOutbox, QuoteEvent


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
    def test_confirmation_kinds_fit_quote_email_outbox_column(self) -> None:
        max_len = int(QuoteEmailOutbox.__table__.c.kind.type.length or 0)
        kinds = [
            "quote_public_approved_confirmation",
            "quote_public_rejected_confirmation",
            "quote_public_change_requested_confirmation",
        ]

        self.assertGreaterEqual(max_len, max(len(kind) for kind in kinds))

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
            result = _try_send_public_quote_confirmation_email(
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
        self.assertEqual(result.get("status"), "failed")
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
            result = _try_send_public_quote_confirmation_email(
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
        self.assertEqual(result.get("status"), "skipped")
        self.assertEqual(len(skipped_events), 1)
        self.assertEqual(skipped_events[0].payload.get("reason"), "missing_recipient_email")

    def test_sends_admin_notification_when_public_quote_is_approved(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(
            id=uuid4(),
            quote_number="DV-TEST",
            total_ttc=Decimal("1534.00"),
            currency="EUR",
            approved_at=datetime(2026, 5, 12, 12, 18, tzinfo=timezone.utc),
            rejected_at=None,
            meta={},
        )

        with patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@piano-academie.com")],
        ), patch(
            "app.api.routes.quotes.build_quote_email_context",
            return_value={"recipient_name": "Olivia Loubiere"},
        ), patch(
            "app.api.routes.quotes.resolve_frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.quotes.send_email",
            return_value="mail-admin",
        ) as send_email_mock:
            result = _try_send_public_quote_admin_notification_email(
                db,
                quote=quote,
                lines=[],
                action="approved",
                client_recipient_email="olivia@example.com",
                client_message_status="sent",
            )

        sent_events = [
            row for row in db.added
            if isinstance(row, QuoteEvent) and row.event_type == "quote_public_admin_notification_email_sent"
        ]
        self.assertEqual(result.get("status"), "sent")
        self.assertEqual(len(sent_events), 1)
        self.assertEqual(sent_events[0].payload.get("sent_recipients"), ["admin@piano-academie.com"])
        send_email_mock.assert_called_once()

    def test_admin_approval_notification_ignores_previous_change_request_message(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(
            id=uuid4(),
            quote_number="DV-TEST",
            total_ttc=Decimal("650.00"),
            currency="EUR",
            approved_at=datetime(2026, 5, 18, 12, 51, tzinfo=timezone.utc),
            rejected_at=None,
            meta={
                "public_response_last_action": "approved",
                "public_response_last_message": "Pourriez-vous modifier pour le vendredi a 19h ?",
            },
        )

        with patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@piano-academie.com")],
        ), patch(
            "app.api.routes.quotes.build_quote_email_context",
            return_value={"recipient_name": "Sophie Barberis"},
        ), patch(
            "app.api.routes.quotes.resolve_frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.quotes.send_email",
            return_value="mail-admin",
        ) as send_email_mock:
            _try_send_public_quote_admin_notification_email(
                db,
                quote=quote,
                lines=[],
                action="approved",
                client_recipient_email="sophie@example.com",
                client_message_status="sent",
            )

        body = str(send_email_mock.call_args.kwargs.get("body") or "")
        self.assertNotIn("Message client:", body)
        self.assertNotIn("vendredi a 19h", body)

    def test_admin_approval_notification_includes_bar_le_duc_manager(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(
            id=uuid4(),
            quote_number="DV-BLD",
            total_ttc=Decimal("879.00"),
            currency="EUR",
            approved_at=datetime(2026, 5, 24, 12, 51, tzinfo=timezone.utc),
            rejected_at=None,
            location_id=None,
            meta={"location_code": "BAR_LE_DUC"},
        )

        with patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@piano-academie.com")],
        ), patch(
            "app.api.routes.quotes.build_quote_email_context",
            return_value={"recipient_name": "Olympia Delcour"},
        ), patch(
            "app.api.routes.quotes.resolve_frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.quotes.send_email",
            return_value="mail-admin",
        ) as send_email_mock:
            result = _try_send_public_quote_admin_notification_email(
                db,
                quote=quote,
                lines=[],
                action="approved",
                client_recipient_email="olympia@example.com",
                client_message_status="sent",
            )

        recipients = [call.kwargs.get("to_email") for call in send_email_mock.call_args_list]
        self.assertEqual(result.get("status"), "sent")
        self.assertIn("admin@piano-academie.com", recipients)
        self.assertIn("estela.oliviero@piano-academie.com", recipients)

    def test_admin_change_request_notification_includes_current_message(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(
            id=uuid4(),
            quote_number="DV-TEST",
            total_ttc=Decimal("650.00"),
            currency="EUR",
            approved_at=None,
            rejected_at=None,
            meta={
                "public_response_last_action": "change_requested",
                "public_response_last_message": "Pourriez-vous modifier pour le vendredi a 19h ?",
            },
        )

        with patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_admin_booking_notification_recipients",
            return_value=[SimpleNamespace(email="admin@piano-academie.com")],
        ), patch(
            "app.api.routes.quotes.build_quote_email_context",
            return_value={"recipient_name": "Sophie Barberis"},
        ), patch(
            "app.api.routes.quotes.resolve_frontend_base_url",
            return_value="https://app.piano-academie.com",
        ), patch(
            "app.api.routes.quotes.send_email",
            return_value="mail-admin",
        ) as send_email_mock:
            _try_send_public_quote_admin_notification_email(
                db,
                quote=quote,
                lines=[],
                action="change_requested",
                client_recipient_email="sophie@example.com",
                client_message_status="sent",
            )

        body = str(send_email_mock.call_args.kwargs.get("body") or "")
        self.assertIn("Message client:", body)
        self.assertIn("vendredi a 19h", body)

    def test_records_skipped_admin_notification_when_admin_recipient_is_missing(self) -> None:
        db = _FakeSession()
        quote = SimpleNamespace(id=uuid4(), meta={})

        with patch(
            "app.api.routes.quotes.email_delivery_disabled_reason",
            return_value=None,
        ), patch(
            "app.api.routes.quotes.resolve_admin_booking_notification_recipients",
            return_value=[],
        ):
            result = _try_send_public_quote_admin_notification_email(
                db,
                quote=quote,
                lines=[],
                action="approved",
                client_recipient_email="olivia@example.com",
                client_message_status="sent",
            )

        skipped_events = [
            row for row in db.added
            if isinstance(row, QuoteEvent) and row.event_type == "quote_public_admin_notification_email_skipped"
        ]
        self.assertEqual(result.get("status"), "skipped")
        self.assertEqual(len(skipped_events), 1)
        self.assertEqual(skipped_events[0].payload.get("reason"), "missing_admin_recipient")


if __name__ == "__main__":
    unittest.main()
