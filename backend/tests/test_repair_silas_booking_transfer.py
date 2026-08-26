from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from scripts.repair_prod_silas_piyatissa_booking_transfer import (
    BookingSession,
    _copy_price,
    _nearest_target,
)


def _row(*, start_at: datetime, subscription_id, total: str) -> BookingSession:
    booking = SimpleNamespace(
        id=uuid4(),
        client_plan_subscription_id=subscription_id,
        price_excl_vat_snapshot=Decimal(total) / Decimal("1.20"),
        vat_rate_snapshot=Decimal("20.00"),
        vat_amount_snapshot=Decimal(total) - Decimal(total) / Decimal("1.20"),
        total_incl_vat_snapshot=Decimal(total),
        currency_snapshot="EUR",
        pricing_snapshot_locked=False,
    )
    session = SimpleNamespace(start_at_utc=start_at, timezone="Europe/Paris")
    return BookingSession(booking=booking, session=session)


def test_repair_accepts_an_unlinked_target_and_copies_fixed_forfait_coverage() -> None:
    subscription_id = uuid4()
    source = _row(
        start_at=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
        subscription_id=subscription_id,
        total="36.00",
    )
    target = _row(
        start_at=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
        subscription_id=None,
        total="38.00",
    )

    assert _nearest_target(source, [target]) is target

    target.booking.client_plan_subscription_id = source.booking.client_plan_subscription_id
    _copy_price(source.booking, target.booking)

    assert target.booking.client_plan_subscription_id == subscription_id
    assert target.booking.total_incl_vat_snapshot == Decimal("36.00")
    assert target.booking.pricing_snapshot_locked is True


def test_repair_rejects_a_target_linked_to_another_subscription() -> None:
    source = _row(
        start_at=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
        subscription_id=uuid4(),
        total="36.00",
    )
    target = _row(
        start_at=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
        subscription_id=uuid4(),
        total="38.00",
    )

    assert _nearest_target(source, [target]) is None
