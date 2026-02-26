from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.plan import PlanKind, SubscriptionStatus


class PlanOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: PlanKind
    credits_count: int | None
    monthly_price_excl_vat: Decimal | None
    currency_code: str | None
    active: bool


class PlanPricePreviewOut(BaseModel):
    plan_id: UUID
    country: str
    currency: str
    price_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal


class PlanMiniOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: PlanKind


class ClientSubscriptionOut(BaseModel):
    id: UUID
    status: SubscriptionStatus
    started_at: datetime
    ends_at: datetime | None
    next_payment_at: datetime | None = None
    credits_initial: int | None
    credits_remaining: int | None
    auto_renew: bool
    billing_method_code: str | None = None
    suspension_starts_at: datetime | None = None
    suspension_ends_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    plan: PlanMiniOut
    entitlement_course_type_ids: list[UUID] = Field(default_factory=list)
    entitlement_course_type_names: list[str] = Field(default_factory=list)
    checkout_url: str | None = None
    payment_reference: str | None = None


class PlanPurchaseRequest(BaseModel):
    user_id: UUID | None = None


class PlanPricePreviewQuery(BaseModel):
    country: str = Field(default="FR", min_length=2, max_length=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
