from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.booking_transfers import (
    bookings_have_equivalent_financial_coverage,
    inherited_coverage_booking_id,
    neutral_transfer_source_ids,
)


def _booking(*, booking_id=None, total="36.00", subscription_id=None):
    total_value = Decimal(total)
    subscription_id = subscription_id or uuid4()
    return SimpleNamespace(
        id=booking_id or uuid4(),
        user_id=uuid4(),
        client_plan_subscription_id=subscription_id,
        price_excl_vat_snapshot=(total_value / Decimal("1.20")).quantize(Decimal("0.01")),
        vat_rate_snapshot=Decimal("20.00"),
        vat_amount_snapshot=(total_value - total_value / Decimal("1.20")).quantize(Decimal("0.01")),
        total_incl_vat_snapshot=total_value,
        currency_snapshot="EUR",
    )


def _copy_financial_identity(source, *, booking_id=None):
    return SimpleNamespace(
        id=booking_id or uuid4(),
        user_id=source.user_id,
        client_plan_subscription_id=source.client_plan_subscription_id,
        price_excl_vat_snapshot=source.price_excl_vat_snapshot,
        vat_rate_snapshot=source.vat_rate_snapshot,
        vat_amount_snapshot=source.vat_amount_snapshot,
        total_incl_vat_snapshot=source.total_incl_vat_snapshot,
        currency_snapshot=source.currency_snapshot,
    )


def test_equivalent_transfer_keeps_invoice_coverage() -> None:
    source = _booking()
    target = _copy_financial_identity(source)
    link = SimpleNamespace(
        source_booking_id=source.id,
        target_booking_id=target.id,
        financially_neutral=True,
    )

    assert bookings_have_equivalent_financial_coverage(source, target)
    assert neutral_transfer_source_ids([link]) == {source.id}
    assert inherited_coverage_booking_id(
        target,
        neutral_links=[link],
        directly_covered_booking_ids={source.id},
    ) == source.id


def test_price_change_does_not_inherit_invoice_coverage() -> None:
    source = _booking(total="36.00")
    target = _copy_financial_identity(source)
    target.total_incl_vat_snapshot = Decimal("38.00")
    link = SimpleNamespace(
        source_booking_id=source.id,
        target_booking_id=target.id,
        financially_neutral=False,
    )

    assert not bookings_have_equivalent_financial_coverage(source, target)
    assert neutral_transfer_source_ids([link]) == set()
    assert inherited_coverage_booking_id(
        target,
        neutral_links=[link],
        directly_covered_booking_ids={source.id},
    ) is None


def test_invoice_coverage_follows_multiple_equivalent_moves() -> None:
    source = _booking()
    middle = _copy_financial_identity(source)
    target = _copy_financial_identity(middle)
    links = [
        SimpleNamespace(
            source_booking_id=source.id,
            target_booking_id=middle.id,
            financially_neutral=True,
        ),
        SimpleNamespace(
            source_booking_id=middle.id,
            target_booking_id=target.id,
            financially_neutral=True,
        ),
    ]

    assert inherited_coverage_booking_id(
        target,
        neutral_links=links,
        directly_covered_booking_ids={source.id},
    ) == source.id


def test_multiple_paid_sources_can_cover_one_real_lesson() -> None:
    first_source = _booking()
    second_source = _copy_financial_identity(first_source)
    target = _copy_financial_identity(first_source)
    links = [
        SimpleNamespace(
            source_booking_id=first_source.id,
            target_booking_id=target.id,
            financially_neutral=True,
        ),
        SimpleNamespace(
            source_booking_id=second_source.id,
            target_booking_id=target.id,
            financially_neutral=True,
        ),
    ]

    assert neutral_transfer_source_ids(links) == {first_source.id, second_source.id}
    assert inherited_coverage_booking_id(
        target,
        neutral_links=links,
        directly_covered_booking_ids={first_source.id, second_source.id},
    ) in {first_source.id, second_source.id}
