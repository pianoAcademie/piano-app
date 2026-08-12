from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.subscription_lifecycle_notifications import (
    send_cancellation_decision_email,
    send_suspension_confirmation_email,
)
from app.services.subscriptions import apply_suspension_dates, replace_suspension_dates


def _subscription() -> SimpleNamespace:
    return SimpleNamespace(
        started_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
        next_payment_at=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc),
        current_period_end=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc),
        suspension_start_date=None,
        suspension_end_date=None,
        suspension_starts_at=None,
        suspension_ends_at=None,
        suspension_duration_unit=None,
        suspension_duration_value=None,
    )


class SubscriptionLifecycleTests(unittest.TestCase):
    def test_pause_end_date_is_inclusive_and_resume_is_next_day(self) -> None:
        subscription = _subscription()

        start_at, end_at = apply_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 8, 6),
            end_date=date(2026, 8, 8),
        )

        self.assertEqual(start_at, datetime(2026, 8, 5, 22, 0, tzinfo=timezone.utc))
        self.assertEqual(end_at, datetime(2026, 8, 8, 22, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.suspension_duration_value, 3)
        self.assertEqual(subscription.next_payment_at, datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.ends_at, datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.current_period_end, datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc))

    def test_pause_rejects_end_before_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "on or after"):
            apply_suspension_dates(
                _subscription(),  # type: ignore[arg-type]
                start_date=date(2026, 8, 8),
                end_date=date(2026, 8, 7),
            )

    def test_pause_keeps_local_payment_time_across_dst_change(self) -> None:
        subscription = _subscription()
        subscription.next_payment_at = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)
        subscription.current_period_end = subscription.next_payment_at
        subscription.ends_at = subscription.next_payment_at

        apply_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 10, 24),
            end_date=date(2026, 10, 26),
        )

        self.assertEqual(subscription.next_payment_at, datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc))

    def test_replacing_pause_dates_recalculates_from_original_billing_schedule(self) -> None:
        subscription = _subscription()
        apply_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 8, 6),
            end_date=date(2026, 8, 8),
        )

        replace_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 8, 7),
            end_date=date(2026, 8, 10),
        )

        self.assertEqual(subscription.suspension_duration_value, 4)
        self.assertEqual(subscription.next_payment_at, datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.ends_at, datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.current_period_end, datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc))

    def test_replacing_pause_after_next_payment_restores_unaffected_due_date(self) -> None:
        subscription = _subscription()
        apply_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 8, 6),
            end_date=date(2026, 8, 8),
        )

        replace_suspension_dates(
            subscription,  # type: ignore[arg-type]
            start_date=date(2026, 8, 20),
            end_date=date(2026, 8, 22),
        )

        self.assertEqual(subscription.next_payment_at, datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.current_period_end, datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(subscription.ends_at, datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc))

    @patch("app.services.subscription_lifecycle_notifications.resolve_sender_profile")
    @patch("app.services.subscription_lifecycle_notifications.send_email")
    def test_english_cancellation_confirmation_mentions_no_next_charge(self, send_email, sender_profile) -> None:
        sender_profile.return_value = SimpleNamespace(from_email="school@example.test", from_name="School", reply_to=None, subject_prefix=None)
        send_email.return_value = "message-1"
        client = SimpleNamespace(
            id="client-1",
            email="client@example.test",
            first_name="Jane",
            last_name="Doe",
            preferred_language="en",
        )
        plan = SimpleNamespace(name="Monthly subscription")

        message_id = send_cancellation_decision_email(
            object(),  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            plan=plan,  # type: ignore[arg-type]
            approved=True,
            effective_at=datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(message_id, "message-1")
        self.assertIn("No new payment will be collected", send_email.call_args.kwargs["body"])
        self.assertIn("Cancellation confirmed", send_email.call_args.kwargs["subject"])
        self.assertEqual(send_email.call_args.kwargs["body_format"], "HTML")

    @patch("app.services.subscription_lifecycle_notifications.resolve_sender_profile")
    @patch("app.services.subscription_lifecycle_notifications.send_email")
    def test_french_cancellation_confirmation_states_last_access_day(self, send_email, sender_profile) -> None:
        sender_profile.return_value = SimpleNamespace(from_email="school@example.test", from_name="School", reply_to=None, subject_prefix=None)
        send_email.return_value = "message-2"
        client = SimpleNamespace(
            id="client-2",
            email="client@example.test",
            first_name="Esther",
            last_name="Honegger",
            preferred_language="fr",
        )
        plan = SimpleNamespace(name="Abonnement mensuel")

        send_cancellation_decision_email(
            object(),  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            plan=plan,  # type: ignore[arg-type]
            approved=True,
            effective_at=datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc),
        )

        body = send_email.call_args.kwargs["body"]
        self.assertIn("Confirmation de résiliation", body)
        self.assertIn("7 septembre 2026 inclus", body)
        self.assertIn("Aucun nouveau prélèvement", body)
        self.assertIn("PIANO ACADÉMIE", body)
        self.assertEqual(send_email.call_args.kwargs["subject"], "Confirmation de résiliation - Abonnement mensuel")
        self.assertEqual(send_email.call_args.kwargs["body_format"], "HTML")

    @patch("app.services.subscription_lifecycle_notifications.resolve_sender_profile")
    @patch("app.services.subscription_lifecycle_notifications.send_email")
    def test_french_pause_confirmation_states_inclusive_end_and_resume_date(self, send_email, sender_profile) -> None:
        sender_profile.return_value = SimpleNamespace(from_email="school@example.test", from_name="School", reply_to=None, subject_prefix=None)
        send_email.return_value = "message-3"
        client = SimpleNamespace(
            id="client-2",
            email="client@example.test",
            first_name="Jean",
            last_name="Dupont",
            preferred_language="fr",
        )
        plan = SimpleNamespace(name="Abonnement mensuel")

        send_suspension_confirmation_email(
            object(),  # type: ignore[arg-type]
            client=client,  # type: ignore[arg-type]
            plan=plan,  # type: ignore[arg-type]
            start_date=date(2026, 8, 6),
            end_date=date(2026, 8, 8),
        )

        body = send_email.call_args.kwargs["body"]
        self.assertIn("08/08/2026 inclus", body)
        self.assertIn("09/08/2026", body)
        self.assertIn("PIANO ACADÉMIE", body)
        self.assertEqual(send_email.call_args.kwargs["body_format"], "HTML")


if __name__ == "__main__":
    unittest.main()
