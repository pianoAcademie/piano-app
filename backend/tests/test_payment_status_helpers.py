from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin_clients import (
    _is_failed_payment_status as _admin_is_failed_payment_status,
    _subscription_payment_status as _admin_subscription_payment_status,
)
from app.api.routes.clients import (
    _invoice_status_from_payment_status,
    _is_failed_payment_status as _client_is_failed_payment_status,
    _subscription_payment_status as _client_subscription_payment_status,
    _sportigo_opening_balance_has_new_app_payment,
    _subscription_payment_occurred_at,
)
from app.services.payment_checkout import _looks_like_local_callback_url, _payplug_lookup_status_label


class PaymentStatusHelpersTests(unittest.TestCase):
    def test_http_200_is_not_treated_as_failed(self) -> None:
        self.assertFalse(_client_is_failed_payment_status("HTTP_200"))
        self.assertFalse(_admin_is_failed_payment_status("HTTP_200"))

    def test_http_500_is_treated_as_failed(self) -> None:
        self.assertTrue(_client_is_failed_payment_status("HTTP_500"))
        self.assertTrue(_admin_is_failed_payment_status("HTTP_500"))

    def test_payplug_lookup_without_state_uses_paid_status_when_paid(self) -> None:
        status = _payplug_lookup_status_label(
            status_code=200,
            payment_status="",
            is_paid=True,
            is_refunded=False,
            is_canceled=False,
            is_failed=False,
        )
        self.assertEqual(status, "PAID")

    def test_local_callback_url_detection_matches_localhost(self) -> None:
        self.assertTrue(_looks_like_local_callback_url("http://localhost:3000/api/v1/public/payments/webhook"))
        self.assertTrue(_looks_like_local_callback_url("http://127.0.0.1:3000/api/v1/public/payments/webhook"))
        self.assertFalse(_looks_like_local_callback_url("https://app.piano-academie.com/api/v1/public/payments/webhook"))

    def test_subscription_status_treats_http_200_as_paid(self) -> None:
        subscription = type(
            "Subscription",
            (),
            {
                "status": type("Status", (), {"value": "ACTIVE"})(),
                "last_payment_status": "HTTP_200",
                "billing_method_code": "CARD_ONLINE",
            },
        )()
        self.assertEqual(_client_subscription_payment_status(subscription), "PAID")
        self.assertEqual(_admin_subscription_payment_status(subscription), "PAID")

    def test_invoice_status_treats_http_200_as_paid(self) -> None:
        self.assertEqual(_invoice_status_from_payment_status("HTTP_200"), "PAID")

    def test_sportigo_opening_balance_is_not_a_new_app_payment(self) -> None:
        from datetime import datetime, timezone

        subscription = type(
            "Subscription",
            (),
            {
                "migration_source_code": "SPORTIGO_2026_OPENING_BALANCE",
                "started_at": datetime(2025, 5, 7, tzinfo=timezone.utc),
                "created_at": datetime(2026, 8, 5, tzinfo=timezone.utc),
                "last_payment_at": datetime(2026, 7, 11, tzinfo=timezone.utc),
            },
        )()

        self.assertFalse(_sportigo_opening_balance_has_new_app_payment(subscription))
        self.assertEqual(_subscription_payment_occurred_at(subscription), subscription.started_at)

    def test_first_post_migration_payment_uses_its_real_date(self) -> None:
        from datetime import datetime, timezone

        subscription = type(
            "Subscription",
            (),
            {
                "migration_source_code": "SPORTIGO_2026_OPENING_BALANCE",
                "started_at": datetime(2025, 5, 7, tzinfo=timezone.utc),
                "created_at": datetime(2026, 8, 5, tzinfo=timezone.utc),
                "last_payment_at": datetime(2026, 8, 10, tzinfo=timezone.utc),
            },
        )()

        self.assertTrue(_sportigo_opening_balance_has_new_app_payment(subscription))
        self.assertEqual(_subscription_payment_occurred_at(subscription), subscription.last_payment_at)


if __name__ == "__main__":
    unittest.main()
