from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.pricing import CourseTypePrice, PlanPrice, VatRule

Money = Decimal


@dataclass(frozen=True)
class ResolvedPrice:
    price_excl_vat: Money
    currency_code: str
    residence_country: str | None


def quantize_money(value: Decimal) -> Money:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_price(
    db: Session,
    *,
    table: type[CourseTypePrice] | type[PlanPrice],
    id_field: str,
    entity_id: UUID,
    country: str,
    currency: str,
    on_date: date,
) -> ResolvedPrice | None:
    entity_col = getattr(table, id_field)

    stmt = (
        select(table)
        .where(
            entity_col == entity_id,
            table.currency_code == currency,
            table.valid_from <= on_date,
            (table.valid_to.is_(None) | (table.valid_to >= on_date)),
            ((table.residence_country == country) | (table.residence_country.is_(None))),
        )
        .order_by(
            case((table.residence_country == country, 0), else_=1),
            table.valid_from.desc(),
        )
    )

    row = db.scalars(stmt).first()
    if row is not None:
        return ResolvedPrice(
            price_excl_vat=quantize_money(Decimal(row.price_excl_vat)),
            currency_code=row.currency_code,
            residence_country=row.residence_country,
        )

    fallback = db.scalars(
        select(table)
        .where(
            entity_col == entity_id,
            table.valid_from <= on_date,
            (table.valid_to.is_(None) | (table.valid_to >= on_date)),
            table.residence_country.is_(None),
        )
        .order_by(
            case((table.currency_code == currency, 0), else_=1),
            table.valid_from.desc(),
        )
    ).first()

    if fallback is None:
        return None

    return ResolvedPrice(
        price_excl_vat=quantize_money(Decimal(fallback.price_excl_vat)),
        currency_code=fallback.currency_code,
        residence_country=fallback.residence_country,
    )


def resolve_plan_price(
    db: Session,
    *,
    plan_id: UUID,
    country: str,
    currency: str,
    on_date: date,
) -> ResolvedPrice | None:
    return _resolve_price(
        db,
        table=PlanPrice,
        id_field="plan_id",
        entity_id=plan_id,
        country=country,
        currency=currency,
        on_date=on_date,
    )


def resolve_course_type_price(
    db: Session,
    *,
    course_type_id: UUID,
    country: str,
    currency: str,
    on_date: date,
) -> ResolvedPrice | None:
    return _resolve_price(
        db,
        table=CourseTypePrice,
        id_field="course_type_id",
        entity_id=course_type_id,
        country=country,
        currency=currency,
        on_date=on_date,
    )


def resolve_vat_rate(
    db: Session,
    *,
    country: str,
    service_code: str,
    on_date: date,
) -> Decimal:
    stmt = (
        select(VatRule)
        .where(
            VatRule.country_code == country,
            VatRule.service_code == service_code,
            VatRule.valid_from <= on_date,
            (VatRule.valid_to.is_(None) | (VatRule.valid_to >= on_date)),
        )
        .order_by(VatRule.valid_from.desc())
    )

    rule = db.scalars(stmt).first()
    if rule is not None:
        return quantize_money(Decimal(rule.vat_rate))

    fallback = db.scalars(
        select(VatRule)
        .where(
            VatRule.country_code == "FR",
            VatRule.service_code == service_code,
            VatRule.valid_from <= on_date,
            (VatRule.valid_to.is_(None) | (VatRule.valid_to >= on_date)),
        )
        .order_by(VatRule.valid_from.desc())
    ).first()

    if fallback is None:
        return quantize_money(Decimal("0"))

    return quantize_money(Decimal(fallback.vat_rate))


def compute_tax_totals(*, price_excl_vat: Decimal, vat_rate: Decimal) -> tuple[Money, Money, Money]:
    price = quantize_money(price_excl_vat)
    vat = quantize_money(price * vat_rate / Decimal("100"))
    total = quantize_money(price + vat)
    return price, vat, total


def plan_service_code(plan_kind: Literal["PACK", "SUBSCRIPTION", "FORFAIT"]) -> str:
    return "SUBSCRIPTION" if plan_kind == "SUBSCRIPTION" else "COURSE_PACKAGE"
