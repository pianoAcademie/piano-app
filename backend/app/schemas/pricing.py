from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanPriceCreateRequest(BaseModel):
    plan_id: UUID
    residence_country: str | None = Field(default=None, min_length=2, max_length=2)
    currency_code: str = Field(min_length=3, max_length=3)
    price_excl_vat: Decimal = Field(ge=Decimal("0"))
    valid_from: date
    valid_to: date | None = None


class PlanPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    residence_country: str | None
    currency_code: str
    price_excl_vat: Decimal
    valid_from: date
    valid_to: date | None
    created_at: datetime


class CourseTypePriceCreateRequest(BaseModel):
    course_type_id: UUID
    residence_country: str | None = Field(default=None, min_length=2, max_length=2)
    currency_code: str = Field(min_length=3, max_length=3)
    price_excl_vat: Decimal = Field(ge=Decimal("0"))
    valid_from: date
    valid_to: date | None = None


class CourseTypePriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_type_id: UUID
    residence_country: str | None
    currency_code: str
    price_excl_vat: Decimal
    valid_from: date
    valid_to: date | None
    created_at: datetime


class VatRuleCreateRequest(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    service_code: str = Field(min_length=2, max_length=80)
    vat_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    valid_from: date
    valid_to: date | None = None


class VatRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    service_code: str
    vat_rate: Decimal
    valid_from: date
    valid_to: date | None
    created_at: datetime
