from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from app.models.catalog import Booking, BookingReorganizationLink


def bookings_have_equivalent_financial_coverage(source: Booking, target: Booking) -> bool:
    """Return whether a move can retain the source booking's invoice coverage."""

    return (
        source.user_id == target.user_id
        and source.client_plan_subscription_id == target.client_plan_subscription_id
        and Decimal(source.price_excl_vat_snapshot or 0) == Decimal(target.price_excl_vat_snapshot or 0)
        and Decimal(source.vat_rate_snapshot or 0) == Decimal(target.vat_rate_snapshot or 0)
        and Decimal(source.vat_amount_snapshot or 0) == Decimal(target.vat_amount_snapshot or 0)
        and Decimal(source.total_incl_vat_snapshot or 0) == Decimal(target.total_incl_vat_snapshot or 0)
        and str(source.currency_snapshot or "EUR").strip().upper()
        == str(target.currency_snapshot or "EUR").strip().upper()
    )


def neutral_transfer_source_ids(links: Iterable[BookingReorganizationLink]) -> set[UUID]:
    return {link.source_booking_id for link in links if bool(link.financially_neutral)}


def inherited_coverage_booking_id(
    booking: Booking,
    *,
    neutral_links: Iterable[BookingReorganizationLink],
    directly_covered_booking_ids: set[UUID],
) -> UUID | None:
    """Find an invoiced ancestor whose coverage follows this real lesson."""

    sources_by_target: dict[UUID, list[UUID]] = defaultdict(list)
    for link in neutral_links:
        if bool(link.financially_neutral):
            sources_by_target[link.target_booking_id].append(link.source_booking_id)

    queue: deque[UUID] = deque([booking.id])
    visited: set[UUID] = set()
    while queue:
        booking_id = queue.popleft()
        if booking_id in visited:
            continue
        visited.add(booking_id)
        if booking_id in directly_covered_booking_ids:
            return booking_id
        queue.extend(sources_by_target.get(booking_id, []))
    return None
