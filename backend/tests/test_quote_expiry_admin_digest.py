from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.quotes.lifecycle_jobs import (
    _build_bar_le_duc_daily_alert_body,
    _build_quote_expiry_digest_body,
    _send_quote_expiry_admin_digest,
    _quote_is_expired_notification_candidate,
    _quote_uuid_from_reference,
    _quote_expiry_digest_date,
    _quote_student_name,
    _trigger_due,
)
from app.services.quotes.email_templates import _quote_language


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
            status="sent",
            meta={},
        )
        prospect = SimpleNamespace(first_name="Ada", last_name="Lovelace")

        body = _build_quote_expiry_digest_body([(quote, prospect, None)], digest_date=datetime(2026, 5, 21).date())

        self.assertIn("Ada Lovelace", body)
        self.assertIn("DV-123", body)
        self.assertIn("12:30 UTC", body)

    def test_yesterday_digest_only_requests_really_expired_quotes(self) -> None:
        calls: list[set[str] | None] = []

        def fake_rows(_db: object, *, digest_date: date, limit: int, statuses: set[str] | None = None) -> list[object]:
            calls.append(statuses)
            return []

        from unittest.mock import patch

        with (
            patch("app.services.quotes.lifecycle_jobs._quote_expiry_digest_already_processed", return_value=False),
            patch("app.services.quotes.lifecycle_jobs._quote_expiry_digest_rows", side_effect=fake_rows),
            patch("app.services.quotes.lifecycle_jobs._mark_quote_expiry_digest_processed"),
            patch("app.services.quotes.lifecycle_jobs.append_job_run_log"),
        ):
            _send_quote_expiry_admin_digest(
                SimpleNamespace(),
                digest_date=date(2026, 5, 26),
                now=datetime(2026, 5, 26, 5, 0, tzinfo=timezone.utc),
                limit=2000,
                delivery_enabled=False,
                job_run_id=uuid4(),
            )

        self.assertEqual(calls[0], {"sent", "change_requested"})
        self.assertEqual(calls[1], {"expired"})

    def test_bar_le_duc_alert_body_contains_expired_quotes_and_overdue_invoices(self) -> None:
        quote = SimpleNamespace(
            quote_number="DV-BLD",
            expires_at=datetime(2026, 5, 23, 12, 30, tzinfo=timezone.utc),
            status="expired",
            meta={
                "typeform_intake": {
                    "normalized_payload": {
                        "child_first_name": "Olympia",
                        "child_last_name": "Delcour",
                    }
                }
            },
        )
        client = SimpleNamespace(first_name="Hang", last_name="Nguyen", email="hang@example.com")
        metadata = {
            "invoice_number": "PA26-0117",
            "total_to_pay_by_currency": {"EUR": "200.00"},
        }

        body = _build_bar_le_duc_daily_alert_body(
            digest_date=date(2026, 5, 24),
            expired_quote_rows=[(quote, None, None)],
            overdue_invoice_rows=[(SimpleNamespace(), client, metadata, date(2026, 5, 22))],
        )

        self.assertIn("Olympia Delcour", body)
        self.assertIn("DV-BLD", body)
        self.assertIn("PA26-0117", body)
        self.assertIn("200.00 EUR", body)
        self.assertIn("Hang Nguyen", body)

    def test_quote_uuid_from_invoice_reference(self) -> None:
        quote_id = uuid4()

        self.assertEqual(_quote_uuid_from_reference(f"QUOTE:{quote_id}:DEPOSIT"), quote_id)

    def test_expired_notification_is_due_at_7am_local_time_next_day(self) -> None:
        zone = ZoneInfo("Europe/Paris")
        reference_at = datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)
        notification_reference = datetime(2026, 5, 25, 18, 0, tzinfo=timezone.utc)

        self.assertFalse(
            _trigger_due(
                now=datetime(2026, 5, 25, 4, 59, tzinfo=timezone.utc),
                zone=zone,
                reference_at=notification_reference,
                local_time=datetime.strptime("07:00", "%H:%M").time(),
            )
        )
        self.assertTrue(
            _trigger_due(
                now=datetime(2026, 5, 25, 5, 0, tzinfo=timezone.utc),
                zone=zone,
                reference_at=notification_reference,
                local_time=datetime.strptime("07:00", "%H:%M").time(),
            )
        )
        self.assertEqual(reference_at.date().isoformat(), "2026-05-24")

    def test_expired_notification_candidate_excludes_rejected_and_cancelled_quotes(self) -> None:
        expires_at = datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)

        self.assertTrue(
            _quote_is_expired_notification_candidate(
                SimpleNamespace(status="expired", cancelled_at=None, expires_at=expires_at, meta={})
            )
        )
        self.assertFalse(
            _quote_is_expired_notification_candidate(
                SimpleNamespace(status="rejected", cancelled_at=None, expires_at=expires_at, meta={})
            )
        )
        self.assertFalse(
            _quote_is_expired_notification_candidate(
                SimpleNamespace(status="cancelled", cancelled_at=expires_at, expires_at=expires_at, meta={})
            )
        )
        self.assertFalse(
            _quote_is_expired_notification_candidate(
                SimpleNamespace(
                    status="expired",
                    cancelled_at=None,
                    expires_at=expires_at,
                    meta={"expired_notification_sent_at": "2026-05-25T05:00:00+00:00"},
                )
            )
        )

    def test_quote_notification_language_prefers_client_language(self) -> None:
        class FakeDb:
            def scalar(self, _stmt: object) -> object:
                return SimpleNamespace(preferred_language="en")

        quote = SimpleNamespace(client_id=uuid4(), language="fr")

        self.assertEqual(_quote_language(FakeDb(), quote), "en")

    def test_quote_notification_language_falls_back_to_quote_language(self) -> None:
        quote = SimpleNamespace(client_id=None, language="en")

        self.assertEqual(_quote_language(SimpleNamespace(), quote), "en")


if __name__ == "__main__":
    unittest.main()
