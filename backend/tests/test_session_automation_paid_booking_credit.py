from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.session_automation import (
    DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY,
    restore_cancelled_booking_credit,
)


def _direct_paid_booking():
    return SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        client_plan_subscription_id=None,
        manual_credit_type_id=None,
        total_incl_vat_snapshot=Decimal("15.00"),
    )


def test_cancelled_paid_direct_booking_adds_one_mapped_manual_credit() -> None:
    booking = _direct_paid_booking()
    credit_type_id = uuid4()
    balance = SimpleNamespace(credits_count=1, updated_at=None)
    receipt = SimpleNamespace(
        amount_paid=Decimal("15.00"),
        receipt_metadata={},
        updated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [receipt]
    db.scalar.side_effect = [credit_type_id, balance]

    assert restore_cancelled_booking_credit(db, booking=booking) is True
    assert balance.credits_count == 2
    assert receipt.receipt_metadata["cancelled_booking_credit_type_id"] == str(credit_type_id)
    assert DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY in receipt.receipt_metadata


def test_cancelled_paid_direct_booking_credit_is_idempotent() -> None:
    booking = _direct_paid_booking()
    receipt = SimpleNamespace(
        amount_paid=Decimal("15.00"),
        receipt_metadata={DIRECT_BOOKING_CREDIT_RESTORED_AT_KEY: "2026-08-11T17:40:00+00:00"},
        updated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [receipt]

    assert restore_cancelled_booking_credit(db, booking=booking) is False
    db.scalar.assert_not_called()


def test_cancelled_partially_paid_direct_booking_does_not_add_credit() -> None:
    booking = _direct_paid_booking()
    receipt = SimpleNamespace(
        amount_paid=Decimal("10.00"),
        receipt_metadata={},
        updated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [receipt]

    assert restore_cancelled_booking_credit(db, booking=booking) is False
    db.scalar.assert_not_called()
