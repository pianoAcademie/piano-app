from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.models.plan import SubscriptionStatus
from app.services.subscription_payment_reminders import (
    _has_valid_stripe_card,
    _has_valid_stripe_recurring_method,
    _payment_issue_and_due_at,
    _reminder_phase,
    build_subscription_payment_reminder_email,
)


def _subscription(**overrides):
    values = {
        "id": uuid4(),
        "status": SubscriptionStatus.PENDING,
        "started_at": datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc),
        "next_payment_at": datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc),
        "current_period_end": datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc),
        "last_successful_charge_at": None,
        "last_payment_at": None,
        "last_payment_status": "CARD_ACTIVE",
        "payment_provider_code": "STRIPE",
        "payment_provider_payment_method_ref": "pm_saved",
        "payment_method_type": "card",
        "payment_method_setup_required": False,
        "billing_method_code": "CARD_ONLINE",
        "initial_total_incl_vat": "125.00",
        "initial_currency_code": "EUR",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SubscriptionPaymentReminderTests(unittest.TestCase):
    def test_reminder_phases_use_paris_calendar_days(self) -> None:
        due_at = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            _reminder_phase(due_at=due_at, now=datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc)),
            "before_due",
        )
        self.assertEqual(
            _reminder_phase(due_at=due_at, now=datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)),
            "due_today",
        )
        self.assertEqual(
            _reminder_phase(due_at=due_at, now=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)),
            "overdue",
        )
        self.assertIsNone(
            _reminder_phase(due_at=due_at, now=datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc))
        )

    def test_pending_subscription_requires_initial_payment_even_when_card_is_saved(self) -> None:
        subscription = _subscription(last_payment_status="CARD_ACTIVE")
        self.assertTrue(_has_valid_stripe_card(subscription))
        self.assertEqual(
            _payment_issue_and_due_at(subscription),
            ("initial_payment", subscription.started_at),
        )

    def test_active_subscription_with_valid_stripe_card_needs_no_reminder(self) -> None:
        subscription = _subscription(status=SubscriptionStatus.ACTIVE)
        self.assertIsNone(_payment_issue_and_due_at(subscription))

    def test_active_subscription_with_valid_stripe_sepa_mandate_needs_no_reminder(self) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            billing_method_code="SEPA_DEBIT",
            payment_method_type="sepa_debit",
        )
        self.assertTrue(_has_valid_stripe_recurring_method(subscription))
        self.assertIsNone(_payment_issue_and_due_at(subscription))

    def test_active_subscription_without_sepa_mandate_requires_payment_method(self) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            billing_method_code="SEPA_DEBIT",
            payment_provider_payment_method_ref=None,
            payment_method_type=None,
            payment_method_setup_required=True,
        )
        self.assertEqual(
            _payment_issue_and_due_at(subscription),
            ("payment_method", subscription.next_payment_at),
        )

    def test_active_subscription_without_card_requires_payment_method(self) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            payment_provider_payment_method_ref=None,
            payment_method_setup_required=True,
        )
        self.assertEqual(
            _payment_issue_and_due_at(subscription),
            ("payment_method", subscription.next_payment_at),
        )

    @patch("app.services.subscription_payment_reminders.resolve_frontend_base_url", return_value="https://piano-academie.example")
    def test_french_initial_payment_email_links_directly_to_checkout_flow(self, _base_url) -> None:
        subscription = _subscription()
        plan = SimpleNamespace(name="Abonnement mensuel présentiel", monthly_price_value="125.00", currency_code="EUR")
        recipient = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Véronique",
            last_name="Attal",
            preferred_language="fr",
        )

        rendered = build_subscription_payment_reminder_email(
            subscription=subscription,
            plan=plan,
            recipient=recipient,
            issue="initial_payment",
            phase="due_today",
            due_at=subscription.started_at,
        )

        self.assertIn("finalisez le paiement", rendered.subject)
        self.assertIn("FINALISER MON PAIEMENT", rendered.body)
        self.assertIn("Stripe", rendered.body)
        self.assertIn("source=PLAN_PURCHASE", rendered.body)
        self.assertIn(f"payment_id={subscription.id}", rendered.body)
        self.assertNotIn("PayPlug", rendered.body)

    @patch("app.services.subscription_payment_reminders.resolve_frontend_base_url", return_value="https://piano-academie.example")
    def test_english_missing_card_email_opens_subscription(self, _base_url) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            payment_provider_payment_method_ref=None,
            payment_method_setup_required=True,
        )
        plan = SimpleNamespace(name="Monthly subscription", monthly_price_value="125.00", currency_code="EUR")
        recipient = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Jane",
            last_name="Doe",
            preferred_language="en",
        )

        rendered = build_subscription_payment_reminder_email(
            subscription=subscription,
            plan=plan,
            recipient=recipient,
            issue="payment_method",
            phase="before_due",
            due_at=subscription.next_payment_at,
        )

        self.assertIn("add a card", rendered.subject)
        self.assertIn("ADD MY CARD", rendered.body)
        self.assertIn("tab=offers", rendered.body)
        self.assertIn(f"offer_detail_id={subscription.id}", rendered.body)

    @patch("app.services.subscription_payment_reminders.resolve_frontend_base_url", return_value="https://piano-academie.example")
    def test_french_overdue_sepa_email_requests_card_then_future_mandate(self, _base_url) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            billing_method_code="SEPA_DEBIT",
            payment_provider_payment_method_ref=None,
            payment_method_type=None,
            payment_method_setup_required=True,
        )
        plan = SimpleNamespace(name="Abonnement mensuel présentiel", monthly_price_value="125.00", currency_code="EUR")
        recipient = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Gwendoline",
            last_name="Gautier",
            preferred_language="fr",
        )

        rendered = build_subscription_payment_reminder_email(
            subscription=subscription,
            plan=plan,
            recipient=recipient,
            issue="payment_method",
            phase="overdue",
            due_at=subscription.next_payment_at,
        )

        self.assertIn("par carte", rendered.subject)
        self.assertIn("RÉGLER MAINTENANT PAR CARTE", rendered.body)
        self.assertIn("Carte bancaire sécurisée par Stripe", rendered.body)
        self.assertIn("Étape 1", rendered.body)
        self.assertIn("Étape 2", rendered.body)
        self.assertIn("prélèvements mensuels suivants", rendered.body)
        self.assertIn("tab=finance", rendered.body)
        self.assertIn(f"payment_id={subscription.id}", rendered.body)

    @patch("app.services.subscription_payment_reminders.resolve_frontend_base_url", return_value="https://piano-academie.example")
    def test_french_upcoming_sepa_email_requests_mandate_without_payment(self, _base_url) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.ACTIVE,
            billing_method_code="SEPA_DEBIT",
            payment_provider_payment_method_ref=None,
            payment_method_type=None,
            payment_method_setup_required=True,
        )
        plan = SimpleNamespace(name="Abonnement mensuel présentiel", monthly_price_value="125.00", currency_code="EUR")
        recipient = SimpleNamespace(
            id=uuid4(),
            email="client@example.test",
            first_name="Gwendoline",
            last_name="Gautier",
            preferred_language="fr",
        )

        rendered = build_subscription_payment_reminder_email(
            subscription=subscription,
            plan=plan,
            recipient=recipient,
            issue="payment_method",
            phase="before_due",
            due_at=subscription.next_payment_at,
        )

        self.assertIn("mandat SEPA", rendered.subject)
        self.assertIn("ENREGISTRER MON MANDAT SEPA", rendered.body)
        self.assertIn("Aucun paiement n’est effectué maintenant", rendered.body)
        self.assertIn("tab=offers", rendered.body)
        self.assertIn(f"offer_detail_id={subscription.id}", rendered.body)


if __name__ == "__main__":
    unittest.main()
