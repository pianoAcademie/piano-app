from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.plan import PlanKind
from app.services.makeup_passes import (
    consume_pass_and_create_makeup,
    grant_makeup_for_excused_absence,
    is_restricted_annual_forfait,
    revoke_pending_makeup_for_corrected_absence,
)
from app.models.makeup import MakeupRequestStatus


class _FakeSession:
    def __init__(self, *scalar_values: object | None) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[object] = []
        self.flush_count = 0

    def scalar(self, _query: object) -> object | None:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add_all(self, values: list[object]) -> None:
        self.added.extend(values)

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_count += 1
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


class MakeupPassCancellationTests(unittest.TestCase):
    def test_restricted_forfait_matches_exact_2026_2027_name(self) -> None:
        self.assertTrue(
            is_restricted_annual_forfait(SimpleNamespace(kind=PlanKind.FORFAIT, name="Année 2026-2027"))
        )
        self.assertFalse(
            is_restricted_annual_forfait(SimpleNamespace(kind=PlanKind.FORFAIT, name="Année 2025-2026"))
        )
        self.assertFalse(
            is_restricted_annual_forfait(SimpleNamespace(kind=PlanKind.PACK, name="Année 2026-2027"))
        )

    def test_cancellation_consumes_one_pass_credit_and_creates_pending_makeup(self) -> None:
        now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
        purchase = SimpleNamespace(id=uuid4(), credits_remaining=4, updated_at=None)
        db = _FakeSession(purchase)
        booking = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            makeup_request_id=None,
            makeup_credit_consumed=False,
        )
        subscription = SimpleNamespace(id=uuid4())

        request = consume_pass_and_create_makeup(
            db,
            booking=booking,
            subscription=subscription,
            actor_user_id=uuid4(),
            now=now,
        )

        self.assertEqual(purchase.credits_remaining, 3)
        self.assertEqual(purchase.updated_at, now)
        self.assertEqual(request.original_booking_id, booking.id)
        self.assertEqual(request.proposed_at, now)
        self.assertEqual(booking.makeup_request_id, request.id)
        self.assertTrue(booking.makeup_credit_consumed)
        self.assertEqual(db.flush_count, 1)

    def test_cancellation_is_rejected_without_remaining_pass_credit(self) -> None:
        db = _FakeSession(None)
        booking = SimpleNamespace(id=uuid4(), user_id=uuid4())

        with self.assertRaisesRegex(ValueError, "MAKEUP_PASS_REQUIRED"):
            consume_pass_and_create_makeup(
                db,
                booking=booking,
                subscription=SimpleNamespace(id=uuid4()),
                actor_user_id=uuid4(),
                now=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
            )

    def test_excused_absence_creates_makeup_when_pass_has_credit(self) -> None:
        now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
        purchase = SimpleNamespace(id=uuid4(), credits_remaining=2, credits_initial=4, updated_at=None)
        db = _FakeSession(None, purchase)
        booking = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            makeup_request_id=None,
            makeup_credit_consumed=False,
        )
        subscription = SimpleNamespace(id=uuid4())

        with patch(
            "app.services.makeup_passes.active_restricted_forfait_for_booking",
            return_value=subscription,
        ):
            granted = grant_makeup_for_excused_absence(
                db,
                booking=booking,
                actor_user_id=uuid4(),
                now=now,
            )

        self.assertTrue(granted)
        self.assertEqual(purchase.credits_remaining, 1)
        self.assertTrue(booking.makeup_credit_consumed)

    def test_excused_absence_remains_valid_without_pass_credit(self) -> None:
        db = _FakeSession(None, None)
        booking = SimpleNamespace(id=uuid4(), user_id=uuid4())

        with patch(
            "app.services.makeup_passes.active_restricted_forfait_for_booking",
            return_value=SimpleNamespace(id=uuid4()),
        ):
            granted = grant_makeup_for_excused_absence(
                db,
                booking=booking,
                actor_user_id=uuid4(),
                now=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
            )

        self.assertFalse(granted)

    def test_excused_absence_does_not_consume_twice_for_the_same_booking(self) -> None:
        db = _FakeSession(uuid4())
        booking = SimpleNamespace(id=uuid4(), user_id=uuid4())

        granted = grant_makeup_for_excused_absence(
            db,
            booking=booking,
            actor_user_id=uuid4(),
            now=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(granted)
        self.assertEqual(db.added, [])

    def test_corrected_excused_absence_restores_unused_pass_credit(self) -> None:
        now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
        purchase = SimpleNamespace(id=uuid4(), credits_remaining=1, credits_initial=4, updated_at=None)
        request = SimpleNamespace(
            used_pass_purchase_id=purchase.id,
            status=MakeupRequestStatus.PROPOSED,
            updated_at=None,
        )
        booking = SimpleNamespace(
            id=uuid4(),
            makeup_request_id=uuid4(),
            makeup_credit_consumed=True,
        )
        db = _FakeSession(request, purchase)

        revoked = revoke_pending_makeup_for_corrected_absence(
            db,
            booking=booking,
            now=now,
        )

        self.assertTrue(revoked)
        self.assertEqual(purchase.credits_remaining, 2)
        self.assertEqual(purchase.updated_at, now)
        self.assertEqual(request.status, MakeupRequestStatus.CANCELLED)
        self.assertEqual(request.updated_at, now)
        self.assertIsNone(booking.makeup_request_id)
        self.assertFalse(booking.makeup_credit_consumed)


if __name__ == "__main__":
    unittest.main()
