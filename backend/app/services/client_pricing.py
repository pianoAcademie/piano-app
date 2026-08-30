from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.001")


class PricingChannel(str, Enum):
    STANDARD = "STANDARD"
    ANNUAL_FORFAIT = "ANNUAL_FORFAIT"
    TRIAL = "TRIAL"
    EXTERNAL_UNIT = "EXTERNAL_UNIT"
    QUOTE = "QUOTE"
    SUBSCRIPTION = "SUBSCRIPTION"
    PACK = "PACK"
    MANUAL_CREDIT = "MANUAL_CREDIT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class PriceUnit(str, Enum):
    PER_SESSION = "PER_SESSION"
    PER_HOUR = "PER_HOUR"


@dataclass(frozen=True)
class PricingComponent:
    code: str
    label: str
    amount_ttc: Decimal

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "label": self.label,
            "amount_ttc": _money_text(self.amount_ttc),
        }


@dataclass(frozen=True)
class PricingComputation:
    channel: PricingChannel
    source: str
    version: str
    unit: PriceUnit
    base_amount_ttc: Decimal
    components: tuple[PricingComponent, ...]
    amount_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
    currency: str
    calculated_at: datetime
    locked: bool = True

    def snapshot_breakdown(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "channel": self.channel.value,
            "source": self.source,
            "price_version": self.version,
            "unit": self.unit.value,
            "base_amount_ttc": _money_text(self.base_amount_ttc),
            "components": [component.as_dict() for component in self.components],
            "amount_excl_vat": _money_text(self.amount_excl_vat),
            "vat_rate": _rate_text(self.vat_rate),
            "vat_amount": _money_text(self.vat_amount),
            "total_incl_vat": _money_text(self.total_incl_vat),
            "currency": self.currency,
            "calculated_at": self.calculated_at.isoformat(),
            "locked": self.locked,
        }

    def legacy_tuple(self) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
        return (
            self.amount_excl_vat,
            self.vat_rate,
            self.vat_amount,
            self.total_incl_vat,
            self.currency,
        )


def _money(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _rate(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def _non_negative_money(value: Decimal | float | int | str | None) -> Decimal:
    return max(_money(value), Decimal("0.00"))


def _money_text(value: Decimal) -> str:
    return f"{_money(value):.2f}"


def _rate_text(value: Decimal) -> str:
    return f"{_rate(value):.3f}"


def _currency(value: str | None) -> str:
    normalized = str(value or "EUR").strip().upper()
    return normalized[:3] or "EUR"


def build_price_version(namespace: str, **values: Any) -> str:
    """Return a stable version identifier for the inputs that produced a price."""

    def normalize(value: Any) -> Any:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
        if isinstance(value, set):
            return sorted((normalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    normalized_namespace = str(namespace or "pricing").strip().lower().replace(" ", "-") or "pricing"
    serialized = json.dumps(normalize(values), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{normalized_namespace}:v1:{digest}"


def amount_for_unit(
    amount_ttc: Decimal | float | int | str,
    *,
    unit: PriceUnit,
    duration_hours: Decimal | float | int | str,
) -> Decimal:
    amount = _non_negative_money(amount_ttc)
    if unit == PriceUnit.PER_SESSION:
        return amount
    duration = max(Decimal(str(duration_hours or 0)), Decimal("0"))
    return _money(amount * duration)


def split_tax(
    total_incl_vat: Decimal | float | int | str,
    *,
    vat_rate: Decimal | float | int | str,
) -> tuple[Decimal, Decimal, Decimal]:
    total = _money(total_incl_vat)
    normalized_rate = _rate(vat_rate)
    if normalized_rate <= Decimal("0.000"):
        return total, Decimal("0.00"), total
    divisor = Decimal("1.00") + (normalized_rate / Decimal("100"))
    amount_excl_vat = _money(total / divisor)
    vat_amount = _money(total - amount_excl_vat)
    return amount_excl_vat, vat_amount, total


def compute_fixed_price(
    *,
    channel: PricingChannel,
    amount_ttc: Decimal | float | int | str,
    unit: PriceUnit,
    duration_hours: Decimal | float | int | str,
    vat_rate: Decimal | float | int | str,
    currency: str,
    source: str,
    version: str,
    calculated_at: datetime | None = None,
    locked: bool = True,
) -> PricingComputation:
    final_ttc = amount_for_unit(amount_ttc, unit=unit, duration_hours=duration_hours)
    amount_excl_vat, vat_amount, final_ttc = split_tax(final_ttc, vat_rate=vat_rate)
    return PricingComputation(
        channel=channel,
        source=source,
        version=version,
        unit=unit,
        base_amount_ttc=final_ttc,
        components=(),
        amount_excl_vat=amount_excl_vat,
        vat_rate=_rate(vat_rate),
        vat_amount=vat_amount,
        total_incl_vat=final_ttc,
        currency=_currency(currency),
        calculated_at=calculated_at or datetime.now(timezone.utc),
        locked=locked,
    )


def compute_annual_forfait_price(
    *,
    base_hourly_ttc: Decimal | float | int | str,
    duration_hours: Decimal | float | int | str,
    loyalty_discount_per_hour_ttc: Decimal | float | int | str = Decimal("0.00"),
    family_discount_per_hour_ttc: Decimal | float | int | str = Decimal("0.00"),
    second_course_discount_per_hour_ttc: Decimal | float | int | str = Decimal("0.00"),
    second_course_applies: bool = False,
    short_commitment_supplement_per_hour_ttc: Decimal | float | int | str = Decimal("0.00"),
    vat_rate: Decimal | float | int | str,
    currency: str,
    source: str,
    version: str,
    calculated_at: datetime | None = None,
    locked: bool = True,
) -> PricingComputation:
    duration = max(Decimal(str(duration_hours or 0)), Decimal("0"))
    base_total = _money(_non_negative_money(base_hourly_ttc) * duration)
    loyalty = _non_negative_money(loyalty_discount_per_hour_ttc)
    family = _non_negative_money(family_discount_per_hour_ttc)
    second_course = _non_negative_money(second_course_discount_per_hour_ttc) if second_course_applies else Decimal("0.00")
    supplement = _non_negative_money(short_commitment_supplement_per_hour_ttc)

    primary_discount = loyalty
    primary_code = "LOYALTY_DISCOUNT"
    primary_label = "Remise fidelite"
    if second_course > loyalty:
        primary_discount = second_course
        primary_code = "SECOND_COURSE_DISCOUNT"
        primary_label = "Remise deuxieme cours"

    components: list[PricingComponent] = []
    if primary_discount > Decimal("0.00"):
        components.append(
            PricingComponent(
                code=primary_code,
                label=primary_label,
                amount_ttc=-_money(primary_discount * duration),
            )
        )
    if family > Decimal("0.00"):
        components.append(
            PricingComponent(
                code="FAMILY_DISCOUNT",
                label="Remise famille",
                amount_ttc=-_money(family * duration),
            )
        )
    if supplement > Decimal("0.00"):
        components.append(
            PricingComponent(
                code="SHORT_COMMITMENT_SUPPLEMENT",
                label="Supplement engagement court",
                amount_ttc=_money(supplement * duration),
            )
        )

    final_ttc = max(
        _money(base_total + sum((component.amount_ttc for component in components), Decimal("0.00"))),
        Decimal("0.00"),
    )
    amount_excl_vat, vat_amount, final_ttc = split_tax(final_ttc, vat_rate=vat_rate)
    return PricingComputation(
        channel=PricingChannel.ANNUAL_FORFAIT,
        source=source,
        version=version,
        unit=PriceUnit.PER_HOUR,
        base_amount_ttc=base_total,
        components=tuple(components),
        amount_excl_vat=amount_excl_vat,
        vat_rate=_rate(vat_rate),
        vat_amount=vat_amount,
        total_incl_vat=final_ttc,
        currency=_currency(currency),
        calculated_at=calculated_at or datetime.now(timezone.utc),
        locked=locked,
    )


def compute_contract_price(
    *,
    channel: PricingChannel,
    amount_excl_vat: Decimal | float | int | str,
    vat_rate: Decimal | float | int | str,
    vat_amount: Decimal | float | int | str,
    total_incl_vat: Decimal | float | int | str,
    currency: str,
    source: str,
    version: str,
    calculated_at: datetime | None = None,
) -> PricingComputation:
    normalized_total = _money(total_incl_vat)
    return PricingComputation(
        channel=channel,
        source=source,
        version=version,
        unit=PriceUnit.PER_SESSION,
        base_amount_ttc=normalized_total,
        components=(),
        amount_excl_vat=_money(amount_excl_vat),
        vat_rate=_rate(vat_rate),
        vat_amount=_money(vat_amount),
        total_incl_vat=normalized_total,
        currency=_currency(currency),
        calculated_at=calculated_at or datetime.now(timezone.utc),
        locked=True,
    )


def booking_snapshot_fields(computation: PricingComputation) -> dict[str, Any]:
    return {
        "price_excl_vat_snapshot": computation.amount_excl_vat,
        "vat_rate_snapshot": computation.vat_rate,
        "vat_amount_snapshot": computation.vat_amount,
        "total_incl_vat_snapshot": computation.total_incl_vat,
        "currency_snapshot": computation.currency,
        "pricing_snapshot_locked": computation.locked,
        "pricing_channel_snapshot": computation.channel.value,
        "pricing_source_snapshot": computation.source,
        "pricing_unit_snapshot": computation.unit.value,
        "price_book_version_snapshot": computation.version,
        "pricing_breakdown_snapshot": computation.snapshot_breakdown(),
        "pricing_calculated_at": computation.calculated_at,
    }


def copy_booking_pricing_snapshot(source: Any) -> dict[str, Any]:
    return {
        "price_excl_vat_snapshot": source.price_excl_vat_snapshot,
        "vat_rate_snapshot": source.vat_rate_snapshot,
        "vat_amount_snapshot": source.vat_amount_snapshot,
        "total_incl_vat_snapshot": source.total_incl_vat_snapshot,
        "currency_snapshot": source.currency_snapshot,
        "pricing_snapshot_locked": bool(source.pricing_snapshot_locked),
        "pricing_channel_snapshot": getattr(source, "pricing_channel_snapshot", None),
        "pricing_source_snapshot": getattr(source, "pricing_source_snapshot", None),
        "pricing_unit_snapshot": getattr(source, "pricing_unit_snapshot", None),
        "price_book_version_snapshot": getattr(source, "price_book_version_snapshot", None),
        "pricing_breakdown_snapshot": dict(getattr(source, "pricing_breakdown_snapshot", None) or {}),
        "pricing_calculated_at": getattr(source, "pricing_calculated_at", None),
    }
