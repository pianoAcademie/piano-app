from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.quote import PricingActivityPrice, PricingCatalog, QuoteDiscountRule


SUPPORTED_CHANNELS = {"STANDARD", "ANNUAL_FORFAIT", "TRIAL", "EXTERNAL_UNIT"}


def _money(value: Decimal | float | int | str | None) -> Decimal:
    try:
        result = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")
    return max(result, Decimal("0.00"))


@dataclass(frozen=True)
class ResolvedCatalogActivityPrice:
    catalog_id: UUID
    catalog_name: str
    price_id: UUID
    channel: str
    pricing_unit: str
    unit_price_ttc: Decimal
    currency: str
    source: str
    version: str

    def amount_for_duration(self, duration_hours: Decimal) -> Decimal:
        if self.pricing_unit == "hourly":
            return _money(self.unit_price_ttc * max(duration_hours, Decimal("0")))
        return self.unit_price_ttc

    def hourly_amount(self, duration_hours: Decimal) -> Decimal:
        if self.pricing_unit == "hourly":
            return self.unit_price_ttc
        if duration_hours <= Decimal("0"):
            return self.unit_price_ttc
        return _money(self.unit_price_ttc / duration_hours)


def resolve_published_catalog(
    db: Session,
    *,
    at: datetime | None = None,
    catalog_id: UUID | None = None,
) -> PricingCatalog | None:
    instant = at or datetime.now(timezone.utc)
    stmt = select(PricingCatalog).where(
        PricingCatalog.is_active.is_(True),
        PricingCatalog.lifecycle_status == "PUBLISHED",
        # Legacy catalogs migrated as PUBLISHED keep published_at NULL. They
        # remain available to quotes but do not silently change live pricing.
        PricingCatalog.published_at.is_not(None),
        PricingCatalog.effective_from <= instant,
        or_(PricingCatalog.effective_to.is_(None), PricingCatalog.effective_to >= instant),
    )
    if catalog_id is not None:
        stmt = stmt.where(PricingCatalog.id == catalog_id)
    return db.scalar(
        stmt.order_by(PricingCatalog.is_default.desc(), PricingCatalog.effective_from.desc()).limit(1)
    )


def resolve_catalog_activity_price(
    db: Session,
    *,
    activity_id: UUID,
    location_id: UUID | None,
    student_category: str | None,
    channel: str,
    at: datetime | None = None,
    catalog_id: UUID | None = None,
) -> ResolvedCatalogActivityPrice | None:
    normalized_channel = str(channel or "").strip().upper()
    if normalized_channel not in SUPPORTED_CHANNELS:
        return None
    catalog = resolve_published_catalog(db, at=at, catalog_id=catalog_id)
    if catalog is None:
        return None
    rows = db.scalars(
        select(PricingActivityPrice).where(
            PricingActivityPrice.catalog_id == catalog.id,
            PricingActivityPrice.activity_id == activity_id,
            PricingActivityPrice.price_channel == normalized_channel,
            PricingActivityPrice.is_active.is_(True),
            or_(PricingActivityPrice.location_id.is_(None), PricingActivityPrice.location_id == location_id),
            or_(
                PricingActivityPrice.student_category.is_(None),
                PricingActivityPrice.student_category == student_category,
            ),
        )
    ).all()
    if not rows:
        return None
    row = max(
        rows,
        key=lambda item: (
            1 if item.location_id is not None and item.location_id == location_id else 0,
            1 if item.student_category is not None and item.student_category == student_category else 0,
            item.updated_at,
        ),
    )
    updated = row.updated_at.isoformat() if row.updated_at is not None else "unknown"
    return ResolvedCatalogActivityPrice(
        catalog_id=catalog.id,
        catalog_name=catalog.name,
        price_id=row.id,
        channel=normalized_channel,
        pricing_unit=row.pricing_unit,
        unit_price_ttc=_money(row.unit_price_ttc),
        currency=str(row.currency or "EUR").upper(),
        source=f"pricing-catalog:{catalog.id}:activity-price:{row.id}",
        version=f"catalog:{catalog.id}:price:{row.id}:{updated}",
    )


def resolve_catalog_discount_amounts(
    db: Session,
    *,
    activity_id: UUID,
    location_id: UUID | None,
    student_category: str | None,
    channel: str,
    at: datetime | None = None,
) -> dict[str, Decimal]:
    catalog = resolve_published_catalog(db, at=at)
    if catalog is None:
        return {}
    rows = db.scalars(
        select(QuoteDiscountRule).where(
            QuoteDiscountRule.catalog_id == catalog.id,
            QuoteDiscountRule.is_active.is_(True),
            QuoteDiscountRule.calculation_mode == "PER_HOUR_TTC",
            or_(QuoteDiscountRule.activity_id.is_(None), QuoteDiscountRule.activity_id == activity_id),
            or_(QuoteDiscountRule.location_id.is_(None), QuoteDiscountRule.location_id == location_id),
            or_(QuoteDiscountRule.student_category.is_(None), QuoteDiscountRule.student_category == student_category),
        )
    ).all()
    return resolve_discount_rule_values(rows, channel=channel)


def resolve_discount_rule_values(rows: list[QuoteDiscountRule] | tuple[QuoteDiscountRule, ...], *, channel: str) -> dict[str, Decimal]:
    eligible = [row for row in rows if channel in list(row.applies_to_channels or [])]
    eligible.sort(key=lambda row: (int(row.priority or 100), int(row.sort_order or 0), str(row.id)))
    resolved: dict[str, Decimal] = {}
    occupied_groups: set[str] = set()
    for row in eligible:
        group = str(row.stacking_group or "").strip().upper()
        if group and not bool(row.is_stackable) and group in occupied_groups:
            continue
        kind = str(row.rule_kind or "CUSTOM").strip().upper()
        resolved.setdefault(kind, _money(row.unit_price_ttc))
        if group and not bool(row.is_stackable):
            occupied_groups.add(group)
    return resolved
