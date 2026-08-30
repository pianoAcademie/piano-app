from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.client_pricing import (
    PriceUnit,
    PricingChannel,
    booking_snapshot_fields,
    build_price_version,
    compute_annual_forfait_price,
    compute_contract_price,
    compute_fixed_price,
    copy_booking_pricing_snapshot,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def test_price_version_is_stable_and_changes_with_pricing_inputs() -> None:
    first = build_price_version("course-type", course_type_id="abc", hourly_rate=Decimal("38.00"))
    same = build_price_version("course-type", hourly_rate=Decimal("38.00"), course_type_id="abc")
    changed = build_price_version("course-type", course_type_id="abc", hourly_rate=Decimal("39.00"))

    assert first == same
    assert first.startswith("course-type:v1:")
    assert first != changed


def test_fixed_price_distinguishes_session_and_hour_units() -> None:
    per_session = compute_fixed_price(
        channel=PricingChannel.EXTERNAL_UNIT,
        amount_ttc=Decimal("45.00"),
        unit=PriceUnit.PER_SESSION,
        duration_hours=Decimal("0.50"),
        vat_rate=Decimal("20.00"),
        currency="EUR",
        source="session:one",
        version="v1",
        calculated_at=NOW,
    )
    per_hour = compute_fixed_price(
        channel=PricingChannel.EXTERNAL_UNIT,
        amount_ttc=Decimal("45.00"),
        unit=PriceUnit.PER_HOUR,
        duration_hours=Decimal("0.50"),
        vat_rate=Decimal("20.00"),
        currency="EUR",
        source="session:two",
        version="v1",
        calculated_at=NOW,
    )

    assert per_session.total_incl_vat == Decimal("45.00")
    assert per_session.amount_excl_vat == Decimal("37.50")
    assert per_session.vat_amount == Decimal("7.50")
    assert per_hour.total_incl_vat == Decimal("22.50")
    assert per_hour.amount_excl_vat == Decimal("18.75")
    assert per_hour.vat_amount == Decimal("3.75")


def test_forfait_uses_more_favorable_primary_discount_then_stacks_family() -> None:
    result = compute_annual_forfait_price(
        base_hourly_ttc=Decimal("38.00"),
        duration_hours=Decimal("1.00"),
        loyalty_discount_per_hour_ttc=Decimal("2.00"),
        family_discount_per_hour_ttc=Decimal("3.00"),
        second_course_discount_per_hour_ttc=Decimal("5.00"),
        second_course_applies=True,
        short_commitment_supplement_per_hour_ttc=Decimal("1.00"),
        vat_rate=Decimal("20.00"),
        currency="eur",
        source="course-type:paris",
        version="paris:v1",
        calculated_at=NOW,
    )

    assert result.base_amount_ttc == Decimal("38.00")
    assert result.total_incl_vat == Decimal("31.00")
    assert [(item.code, item.amount_ttc) for item in result.components] == [
        ("SECOND_COURSE_DISCOUNT", Decimal("-5.00")),
        ("FAMILY_DISCOUNT", Decimal("-3.00")),
        ("SHORT_COMMITMENT_SUPPLEMENT", Decimal("1.00")),
    ]
    assert result.amount_excl_vat == Decimal("25.83")
    assert result.vat_amount == Decimal("5.17")


def test_forfait_keeps_loyalty_when_second_course_is_less_favorable() -> None:
    result = compute_annual_forfait_price(
        base_hourly_ttc=Decimal("38.00"),
        duration_hours=Decimal("1.50"),
        loyalty_discount_per_hour_ttc=Decimal("4.00"),
        family_discount_per_hour_ttc=Decimal("0.00"),
        second_course_discount_per_hour_ttc=Decimal("3.00"),
        second_course_applies=True,
        vat_rate=Decimal("0.00"),
        currency="EUR",
        source="course-type:paris",
        version="paris:v1",
        calculated_at=NOW,
    )

    assert result.total_incl_vat == Decimal("51.00")
    assert result.components[0].code == "LOYALTY_DISCOUNT"
    assert result.components[0].amount_ttc == Decimal("-6.00")


def test_quote_contract_price_is_preserved_exactly() -> None:
    result = compute_contract_price(
        channel=PricingChannel.QUOTE,
        amount_excl_vat=Decimal("18.33"),
        vat_rate=Decimal("20.00"),
        vat_amount=Decimal("3.67"),
        total_incl_vat=Decimal("22.00"),
        currency="EUR",
        source="quote:abc:line:1",
        version="quote:abc:v1",
        calculated_at=NOW,
    )

    assert result.legacy_tuple() == (
        Decimal("18.33"),
        Decimal("20.000"),
        Decimal("3.67"),
        Decimal("22.00"),
        "EUR",
    )


def test_snapshot_contains_auditable_rule_and_can_be_copied() -> None:
    result = compute_fixed_price(
        channel=PricingChannel.TRIAL,
        amount_ttc=Decimal("0.00"),
        unit=PriceUnit.PER_SESSION,
        duration_hours=Decimal("1.00"),
        vat_rate=Decimal("0.00"),
        currency="EUR",
        source="trial-plan:123",
        version="course-type:456:v1",
        calculated_at=NOW,
    )
    fields = booking_snapshot_fields(result)

    assert fields["pricing_snapshot_locked"] is True
    assert fields["pricing_channel_snapshot"] == "TRIAL"
    assert fields["pricing_source_snapshot"] == "trial-plan:123"
    assert fields["price_book_version_snapshot"] == "course-type:456:v1"
    assert fields["pricing_breakdown_snapshot"]["schema_version"] == 1
    assert fields["pricing_breakdown_snapshot"]["total_incl_vat"] == "0.00"

    copied = copy_booking_pricing_snapshot(SimpleNamespace(**fields))
    assert copied == fields
    assert copied["pricing_breakdown_snapshot"] is not fields["pricing_breakdown_snapshot"]
