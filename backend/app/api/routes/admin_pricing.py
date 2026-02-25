from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import CourseType
from app.models.plan import Plan
from app.models.pricing import CourseTypePrice, PlanPrice, VatRule
from app.models.user import User, UserRole
from app.schemas.pricing import (
    CourseTypePriceCreateRequest,
    CourseTypePriceOut,
    PlanPriceCreateRequest,
    PlanPriceOut,
    VatRuleCreateRequest,
    VatRuleOut,
)

router = APIRouter()


def _normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_required_code(value: str, field_name: str, *, uppercase: bool = True) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be empty",
        )
    return normalized.upper() if uppercase else normalized


def _validate_date_window(valid_from: date, valid_to: date | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="valid_to must be after or equal to valid_from",
        )


@router.post("/admin/pricing/plan-prices", response_model=PlanPriceOut, status_code=status.HTTP_201_CREATED)
def create_plan_price(
    payload: PlanPriceCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PlanPriceOut:
    _validate_date_window(payload.valid_from, payload.valid_to)

    plan = db.scalar(select(Plan).where(Plan.id == payload.plan_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    price = PlanPrice(
        plan_id=payload.plan_id,
        residence_country=_normalize_country(payload.residence_country),
        currency_code=_normalize_required_code(payload.currency_code, "currency_code"),
        price_excl_vat=payload.price_excl_vat,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(price)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan price rule already exists for this plan/country/currency/valid_from",
        ) from exc

    db.refresh(price)
    return price


@router.get("/admin/pricing/plan-prices", response_model=list[PlanPriceOut])
def list_plan_prices(
    plan_id: UUID | None = None,
    country: str | None = Query(default=None, min_length=2, max_length=2),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PlanPriceOut]:
    stmt = select(PlanPrice)

    if plan_id is not None:
        stmt = stmt.where(PlanPrice.plan_id == plan_id)
    if country is not None:
        stmt = stmt.where(PlanPrice.residence_country == country.upper())
    if currency is not None:
        stmt = stmt.where(PlanPrice.currency_code == currency.upper())

    stmt = stmt.order_by(PlanPrice.valid_from.desc(), PlanPrice.created_at.desc())
    return db.scalars(stmt).all()


@router.post("/admin/pricing/course-type-prices", response_model=CourseTypePriceOut, status_code=status.HTTP_201_CREATED)
def create_course_type_price(
    payload: CourseTypePriceCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CourseTypePriceOut:
    _validate_date_window(payload.valid_from, payload.valid_to)

    course_type = db.scalar(select(CourseType).where(CourseType.id == payload.course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")

    price = CourseTypePrice(
        course_type_id=payload.course_type_id,
        residence_country=_normalize_country(payload.residence_country),
        currency_code=_normalize_required_code(payload.currency_code, "currency_code"),
        price_excl_vat=payload.price_excl_vat,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(price)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Course type price rule already exists for this course/country/currency/valid_from",
        ) from exc

    db.refresh(price)
    return price


@router.get("/admin/pricing/course-type-prices", response_model=list[CourseTypePriceOut])
def list_course_type_prices(
    course_type_id: UUID | None = None,
    country: str | None = Query(default=None, min_length=2, max_length=2),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[CourseTypePriceOut]:
    stmt = select(CourseTypePrice)

    if course_type_id is not None:
        stmt = stmt.where(CourseTypePrice.course_type_id == course_type_id)
    if country is not None:
        stmt = stmt.where(CourseTypePrice.residence_country == country.upper())
    if currency is not None:
        stmt = stmt.where(CourseTypePrice.currency_code == currency.upper())

    stmt = stmt.order_by(CourseTypePrice.valid_from.desc(), CourseTypePrice.created_at.desc())
    return db.scalars(stmt).all()


@router.post("/admin/vat-rules", response_model=VatRuleOut, status_code=status.HTTP_201_CREATED)
def create_vat_rule(
    payload: VatRuleCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> VatRuleOut:
    _validate_date_window(payload.valid_from, payload.valid_to)

    vat_rule = VatRule(
        country_code=_normalize_required_code(payload.country_code, "country_code"),
        service_code=_normalize_required_code(payload.service_code, "service_code"),
        vat_rate=payload.vat_rate,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(vat_rule)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="VAT rule already exists for this country/service/valid_from",
        ) from exc

    db.refresh(vat_rule)
    return vat_rule


@router.get("/admin/vat-rules", response_model=list[VatRuleOut])
def list_vat_rules(
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    service_code: str | None = Query(default=None, min_length=2, max_length=80),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[VatRuleOut]:
    stmt = select(VatRule)

    if country_code is not None:
        stmt = stmt.where(VatRule.country_code == country_code.upper())
    if service_code is not None:
        stmt = stmt.where(VatRule.service_code == service_code.upper())

    stmt = stmt.order_by(VatRule.valid_from.desc(), VatRule.created_at.desc())
    return db.scalars(stmt).all()
