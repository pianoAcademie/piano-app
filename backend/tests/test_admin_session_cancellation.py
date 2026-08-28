from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin import (
    _cancel_booking_for_cancelled_session,
    _require_series_cancellation_confirmation,
)
from app.models.catalog import BookingStatus


def _booking(status: BookingStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=status,
        cancelled_at=None,
        cancellation_reason=None,
        payment_hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )


def test_admin_session_cancellation_closes_booking_restores_credit_and_stops_reminders() -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    booking = _booking(BookingStatus.BOOKED)
    session_obj = SimpleNamespace(start_at_utc=now + timedelta(days=2))
    db = MagicMock()

    with patch(
        "app.api.routes.admin.restore_cancelled_booking_credit",
        return_value=True,
    ) as restore_credit, patch(
        "app.api.routes.admin.skip_pending_reminders_for_booking",
    ) as skip_legacy_reminders, patch(
        "app.api.routes.admin.cancel_pending_booking_reminder_notifications",
    ) as cancel_engine_reminders:
        restored = _cancel_booking_for_cancelled_session(
            db,
            booking=booking,
            session_obj=session_obj,
            now=now,
            cancellation_reason="ADMIN_SESSION_CANCELLED",
        )

    assert restored is True
    assert booking.status == BookingStatus.CANCELLED
    assert booking.cancelled_at == now
    assert booking.cancellation_reason == "ADMIN_SESSION_CANCELLED"
    assert booking.payment_hold_expires_at is None
    restore_credit.assert_called_once_with(db, booking=booking)
    skip_legacy_reminders.assert_called_once()
    cancel_engine_reminders.assert_called_once()


def test_admin_session_cancellation_does_not_credit_waitlist_booking() -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    booking = _booking(BookingStatus.WAITLISTED)
    session_obj = SimpleNamespace(start_at_utc=now + timedelta(days=2))
    db = MagicMock()

    with patch(
        "app.api.routes.admin.restore_cancelled_booking_credit",
    ) as restore_credit, patch(
        "app.api.routes.admin.skip_pending_reminders_for_booking",
    ), patch(
        "app.api.routes.admin.cancel_pending_booking_reminder_notifications",
    ):
        restored = _cancel_booking_for_cancelled_session(
            db,
            booking=booking,
            session_obj=session_obj,
            now=now,
            cancellation_reason="ADMIN_SESSION_CANCELLED",
        )

    assert restored is False
    assert booking.status == BookingStatus.CANCELLED
    restore_credit.assert_not_called()


def test_admin_session_cancellation_expires_pending_payment_receipt() -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    booking = _booking(BookingStatus.PENDING_PAYMENT)
    session_obj = SimpleNamespace(start_at_utc=now + timedelta(days=2))
    receipt = SimpleNamespace(status="PENDING", updated_at=None)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [receipt]

    with patch(
        "app.api.routes.admin.restore_cancelled_booking_credit",
    ) as restore_credit, patch(
        "app.api.routes.admin.skip_pending_reminders_for_booking",
    ), patch(
        "app.api.routes.admin.cancel_pending_booking_reminder_notifications",
    ):
        restored = _cancel_booking_for_cancelled_session(
            db,
            booking=booking,
            session_obj=session_obj,
            now=now,
            cancellation_reason="ADMIN_SESSION_CANCELLED",
        )

    assert restored is False
    assert receipt.status == "EXPIRED"
    assert receipt.updated_at == now
    restore_credit.assert_not_called()


def test_recurring_series_cancellation_requires_second_confirmation() -> None:
    session_obj = SimpleNamespace(recurrence_group_id=uuid4())

    with pytest.raises(HTTPException) as exc_info:
        _require_series_cancellation_confirmation(
            session_obj=session_obj,
            apply_scope="SERIES_FUTURE",
            confirmed=False,
        )

    assert exc_info.value.status_code == 422


def test_single_occurrence_cancellation_does_not_require_second_confirmation() -> None:
    session_obj = SimpleNamespace(recurrence_group_id=uuid4())

    _require_series_cancellation_confirmation(
        session_obj=session_obj,
        apply_scope="ONE",
        confirmed=False,
    )


def test_recurring_series_cancellation_accepts_explicit_confirmation() -> None:
    session_obj = SimpleNamespace(recurrence_group_id=uuid4())

    _require_series_cancellation_confirmation(
        session_obj=session_obj,
        apply_scope="SERIES_ALL",
        confirmed=True,
    )
