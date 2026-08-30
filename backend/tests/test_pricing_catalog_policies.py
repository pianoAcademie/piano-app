from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.pricing_catalog import ResolvedCatalogActivityPrice, resolve_discount_rule_values


def test_catalog_price_converts_per_session_amount_to_hourly_without_rounding_history() -> None:
    price = ResolvedCatalogActivityPrice(
        catalog_id=uuid4(),
        catalog_name="Tarifs 2026-2027",
        price_id=uuid4(),
        channel="ANNUAL_FORFAIT",
        pricing_unit="per_session",
        unit_price_ttc=Decimal("38.00"),
        currency="EUR",
        source="pricing-catalog:test",
        version="catalog:test:v1",
    )

    assert price.amount_for_duration(Decimal("0.50")) == Decimal("38.00")
    assert price.hourly_amount(Decimal("0.50")) == Decimal("76.00")


def test_exclusive_discount_group_uses_highest_priority_then_family_stacks() -> None:
    rows = [
        SimpleNamespace(
            applies_to_channels=["ANNUAL_FORFAIT"],
            priority=20,
            sort_order=20,
            id=uuid4(),
            stacking_group="PRIMARY",
            is_stackable=False,
            rule_kind="SECOND_COURSE",
            unit_price_ttc=Decimal("5.00"),
        ),
        SimpleNamespace(
            applies_to_channels=["ANNUAL_FORFAIT"],
            priority=10,
            sort_order=10,
            id=uuid4(),
            stacking_group="PRIMARY",
            is_stackable=False,
            rule_kind="LOYALTY",
            unit_price_ttc=Decimal("2.00"),
        ),
        SimpleNamespace(
            applies_to_channels=["ANNUAL_FORFAIT"],
            priority=30,
            sort_order=30,
            id=uuid4(),
            stacking_group="FAMILY",
            is_stackable=True,
            rule_kind="FAMILY",
            unit_price_ttc=Decimal("3.00"),
        ),
    ]

    resolved = resolve_discount_rule_values(rows, channel="ANNUAL_FORFAIT")

    assert resolved == {"LOYALTY": Decimal("2.00"), "FAMILY": Decimal("3.00")}


def test_discount_rules_are_isolated_by_pricing_channel() -> None:
    row = SimpleNamespace(
        applies_to_channels=["TRIAL"],
        priority=10,
        sort_order=10,
        id=uuid4(),
        stacking_group=None,
        is_stackable=True,
        rule_kind="CUSTOM",
        unit_price_ttc=Decimal("10.00"),
    )

    assert resolve_discount_rule_values([row], channel="ANNUAL_FORFAIT") == {}
    assert resolve_discount_rule_values([row], channel="TRIAL") == {"CUSTOM": Decimal("10.00")}
