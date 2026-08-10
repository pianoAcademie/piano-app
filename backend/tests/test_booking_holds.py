from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.bookings import (
    PAYMENT_TIMEOUT_CANCELLATION_REASON,
    _next_booking_status,
    _promote_waitlist_if_possible,
    promote_pending_payment_booking,
)
from app.models.catalog import BookingStatus, SessionStatus
from app.services.session_automation import run_expire_pending_payment_bookings_job


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_values: list[object] | None = None,
        scalars_results: list[list[object]] | None = None,
    ) -> None:
        self._scalar_values = list(scalar_values or [])
        self._scalars_results = list(scalars_results or [])
        self.added: list[object] = []

    def scalar(self, _query: object) -> object | None:
        if not self._scalar_values:
            return None
        return self._scalar_values.pop(0)

    def scalars(self, _query: object) -> _ScalarResult:
        if not self._scalars_results:
            return _ScalarResult([])
        return _ScalarResult(self._scalars_results.pop(0))

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None


class BookingHoldTests(unittest.TestCase):
    def test_next_booking_status_waitlists_when_waitlist_has_space(self) -> None:
        session_id = uuid4()
        session_obj = SimpleNamespace(id=session_id, capacity_max=1, location_id=uuid4())
        fake_db = _FakeSession(
            scalar_values=[
                1,
                0,
                SimpleNamespace(waitlist_capacity=1),
            ]
        )

        next_status = _next_booking_status(fake_db, session_obj=session_obj)

        self.assertEqual(next_status, BookingStatus.WAITLISTED)

    def test_next_booking_status_rejects_when_waitlist_is_full(self) -> None:
        session_id = uuid4()
        session_obj = SimpleNamespace(id=session_id, capacity_max=1, location_id=uuid4())
        fake_db = _FakeSession(
            scalar_values=[
                1,
                1,
                SimpleNamespace(waitlist_capacity=1),
            ]
        )

        next_status = _next_booking_status(fake_db, session_obj=session_obj)

        self.assertIsNone(next_status)

    def test_promote_pending_payment_booking_confirms_booking(self) -> None:
        now = datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            id=uuid4(),
            status=BookingStatus.PENDING_PAYMENT,
            payment_hold_expires_at=now + timedelta(minutes=10),
            cancelled_at=None,
            cancellation_reason=None,
        )
        owner = SimpleNamespace(first_course_at=None)
        session_obj = SimpleNamespace(
            id=uuid4(),
            status=SessionStatus.SCHEDULED,
            capacity_max=6,
            start_at_utc=now + timedelta(days=1),
        )
        fake_db = _FakeSession(scalar_values=[0])

        with patch("app.api.routes.bookings.ensure_booking_reminder") as ensure_booking_reminder, patch(
            "app.api.routes.bookings.schedule_booking_created_notifications",
            return_value=[],
        ) as schedule_notifications, patch(
            "app.api.routes.bookings.schedule_booking_created_triggers",
            return_value=[],
        ), patch(
            "app.api.routes.bookings.enqueue_notifications",
        ) as enqueue_notifications:
            promoted = promote_pending_payment_booking(
                fake_db,
                booking=booking,
                booking_owner=owner,
                session_obj=session_obj,
                actor_user_id=uuid4(),
                occurred_at=now,
            )

        self.assertTrue(promoted)
        self.assertEqual(booking.status, BookingStatus.BOOKED)
        self.assertIsNone(booking.payment_hold_expires_at)
        self.assertEqual(owner.first_course_at, session_obj.start_at_utc)
        ensure_booking_reminder.assert_called_once()
        schedule_notifications.assert_called_once()
        enqueue_notifications.assert_not_called()

    def test_waitlist_promotion_confirms_first_person_and_schedules_notification(self) -> None:
        now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
        user_id = uuid4()
        session_obj = SimpleNamespace(
            id=uuid4(),
            course_type_id=uuid4(),
            capacity_max=1,
            start_at_utc=now + timedelta(days=1),
        )
        course_type = SimpleNamespace(
            id=session_obj.course_type_id,
            name="Cours collectif",
            credit_type_id=uuid4(),
            service_code="COLLECTIF",
        )
        waitlisted = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            status=BookingStatus.WAITLISTED,
            booked_at=now - timedelta(hours=1),
            client_plan_subscription_id=None,
            manual_credit_type_id=course_type.credit_type_id,
            cancelled_at=None,
            cancellation_reason=None,
        )
        user = SimpleNamespace(id=user_id)
        balance = SimpleNamespace(credits_count=1)
        queued_notification = SimpleNamespace(notification_id=uuid4())
        fake_db = _FakeSession(scalar_values=[course_type, waitlisted, user, None])

        with patch("app.api.routes.bookings._count_booked", side_effect=[0, 1]), patch(
            "app.api.routes.bookings._load_manual_credit_balance_for_update",
            return_value=balance,
        ), patch(
            "app.api.routes.bookings._activate_confirmed_booking",
            return_value=[],
        ), patch(
            "app.api.routes.bookings.schedule_waitlist_promoted_notification",
            return_value=[queued_notification],
        ) as schedule_promoted:
            notifications = _promote_waitlist_if_possible(fake_db, session_obj, now)

        self.assertEqual(waitlisted.status, BookingStatus.BOOKED)
        self.assertEqual(waitlisted.booked_at, now)
        self.assertEqual(balance.credits_count, 0)
        self.assertEqual(notifications, [queued_notification])
        schedule_promoted.assert_called_once_with(fake_db, booking=waitlisted, occurred_at=now)

    def test_expire_pending_payment_bookings_cancels_booking_and_receipt(self) -> None:
        now = datetime(2026, 3, 31, 10, 30, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            id=uuid4(),
            status=BookingStatus.PENDING_PAYMENT,
            payment_hold_expires_at=now - timedelta(minutes=1),
            cancelled_at=None,
            cancellation_reason=None,
        )
        receipt = SimpleNamespace(
            status="PENDING",
            receipt_metadata=None,
            updated_at=None,
            final_invoice_note_id=None,
        )
        fake_db = _FakeSession(
            scalars_results=[
                [booking],
                [receipt],
            ]
        )

        with patch("app.services.session_automation.skip_pending_reminders_for_booking") as skip_pending_reminders:
            result = run_expire_pending_payment_bookings_job(fake_db, now=now, limit=20)

        self.assertEqual(result.checked, 1)
        self.assertEqual(result.expired_bookings, 1)
        self.assertEqual(result.expired_receipts, 1)
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancellation_reason, PAYMENT_TIMEOUT_CANCELLATION_REASON)
        self.assertIsNone(booking.payment_hold_expires_at)
        self.assertEqual(receipt.status, "EXPIRED")
        self.assertEqual(receipt.receipt_metadata["booking_hold_expired_at"], now.isoformat())
        skip_pending_reminders.assert_called_once()


if __name__ == "__main__":
    unittest.main()
