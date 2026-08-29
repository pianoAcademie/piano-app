from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.plan import SubscriptionStatus
from app.services.payment_checkout import PaymentLookupResult
from app.services.payment_provider import PaymentProvider
from app.services.pending_plan_purchases import has_unresolved_pending_plan_purchase


class _ScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.added: list[object] = []

    def scalars(self, _query: object) -> _ScalarsResult:
        return _ScalarsResult(self.rows)

    def add(self, row: object) -> None:
        self.added.append(row)


def _pending_subscription(*, reference: str = "pay_test") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        payment_provider_code="PAYPLUG",
        payment_provider_subscription_ref=reference,
        status=SubscriptionStatus.PENDING,
        credits_remaining=1,
        auto_renew=False,
        bookings_blocked=False,
        next_payment_at=None,
        last_payment_status="OPEN",
    )


def _lookup(*, status: str, paid: bool = False, cancelled: bool = False, failed: bool = False) -> PaymentLookupResult:
    return PaymentLookupResult(
        success=True,
        provider=PaymentProvider.PAYPLUG,
        provider_reference="pay_test",
        status=status,
        paid=paid,
        cancelled=cancelled,
        failed=failed,
        metadata={},
        message="ok",
    )


class PendingPlanPurchaseTests(unittest.TestCase):
    @patch("app.services.pending_plan_purchases.lookup_payment", return_value=_lookup(status="OPEN"))
    def test_open_checkout_blocks_a_duplicate(self, _lookup_payment: object) -> None:
        subscription = _pending_subscription()
        db = _FakeSession([subscription])

        blocked = has_unresolved_pending_plan_purchase(db, user_id=uuid4(), plan_id=uuid4())  # type: ignore[arg-type]

        self.assertTrue(blocked)
        self.assertEqual(subscription.status, SubscriptionStatus.PENDING)
        self.assertEqual(subscription.credits_remaining, 1)

    @patch("app.services.pending_plan_purchases.lookup_payment", return_value=_lookup(status="FAILED", failed=True))
    def test_failed_checkout_is_archived_and_does_not_block_retry(self, _lookup_payment: object) -> None:
        subscription = _pending_subscription()
        db = _FakeSession([subscription])

        blocked = has_unresolved_pending_plan_purchase(db, user_id=uuid4(), plan_id=uuid4())  # type: ignore[arg-type]

        self.assertFalse(blocked)
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(subscription.credits_remaining, 0)
        self.assertTrue(subscription.bookings_blocked)
        self.assertEqual(subscription.last_payment_status, "FAILED")

    def test_checkout_without_provider_reference_blocks_a_duplicate(self) -> None:
        subscription = _pending_subscription(reference="")
        db = _FakeSession([subscription])

        blocked = has_unresolved_pending_plan_purchase(db, user_id=uuid4(), plan_id=uuid4())  # type: ignore[arg-type]

        self.assertTrue(blocked)
        self.assertEqual(subscription.status, SubscriptionStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
