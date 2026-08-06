from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.plan import PlanKind, SubscriptionStatus


class PlanFirstPurchaseLineOut(BaseModel):
    code: str
    label: str
    amount_ttc: Decimal


class PlanOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    kind: PlanKind
    credits_count: int | None
    forfait_start_date: date | None = None
    forfait_end_date: date | None = None
    monthly_price_excl_vat: Decimal | None
    price_ttc: Decimal | None = None
    base_price_ttc: Decimal | None = None
    currency_code: str | None
    active: bool
    first_purchase_required: bool = False
    first_purchase_fee_ttc: Decimal | None = None
    first_purchase_partitions_price_ttc: Decimal | None = None
    first_purchase_breakdown: list[PlanFirstPurchaseLineOut] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    entitlement_course_type_names: list[str] = Field(default_factory=list)


class PublicFormulaPurchaseSummaryOut(BaseModel):
    formula_id: UUID
    formula_code: str
    formula_type: PlanKind
    name: str
    description: str | None = None
    active: bool
    is_private: bool
    purchase_link_allowed: bool
    purchase_url: str
    price_ttc: Decimal | None = None
    currency: str
    frequency_label: str | None = None
    includes: list[str] = Field(default_factory=list)
    restriction_labels: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    base_price_ttc: Decimal | None = None
    first_purchase_fee_ttc: Decimal | None = None
    first_purchase_partitions_price_ttc: Decimal | None = None


class PublicFormulaPurchaseStartRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    session_id: UUID | None = None
    booking_user_id: UUID | None = None
    planning_return_to: str | None = None


class PublicFormulaPurchaseStartOut(BaseModel):
    existing_user: bool
    redirect_mode: Literal["login", "signup"]
    purchase_context: str


class PublicFormulaPurchaseContextOut(BaseModel):
    purchase_context: str
    email: str
    formula_id: UUID
    formula_code: str
    formula_type: PlanKind
    price_snapshot: Decimal | None = None
    currency: str
    session_id: UUID | None = None
    booking_user_id: UUID | None = None
    planning_return_to: str | None = None
    summary: PublicFormulaPurchaseSummaryOut


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
    price_ttc: Decimal | None = None
    currency_code: str | None = None


class ClientSubscriptionOut(BaseModel):
    id: UUID
    status: SubscriptionStatus
    started_at: datetime
    ends_at: datetime | None
    next_payment_at: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    credits_initial: int | None
    credits_remaining: int | None
    auto_renew: bool
    bookings_blocked: bool = False
    billing_method_code: str | None = None
    payment_method_type: str | None = None
    payment_method_brand: str | None = None
    payment_method_last4: str | None = None
    payment_method_exp_month: int | None = None
    payment_method_exp_year: int | None = None
    payment_method_setup_required: bool = False
    payment_method_setup_completed_at: datetime | None = None
    last_successful_charge_at: datetime | None = None
    payment_alert_started_at: datetime | None = None
    pre_termination_at: datetime | None = None
    direct_payment_recovery_url: str | None = None
    suspension_starts_at: datetime | None = None
    suspension_ends_at: datetime | None = None
    suspension_start_date: date | None = None
    suspension_end_date: date | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    cancellation_request_status: str | None = None
    cancellation_request_note: str | None = None
    cancellation_request_reviewed_at: datetime | None = None
    plan: PlanMiniOut
    entitlement_course_type_ids: list[UUID] = Field(default_factory=list)
    entitlement_course_type_names: list[str] = Field(default_factory=list)
    checkout_url: str | None = None
    payment_reference: str | None = None


class PlanPurchaseRequest(BaseModel):
    user_id: UUID | None = None
    start_date: date | None = None
    purchase_context: str | None = None
    confirm_existing_pack_purchase: bool = False
    billing_method_code: str | None = Field(default=None, max_length=40)


class ClientSubscriptionCancellationRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class PlanPricePreviewQuery(BaseModel):
    country: str = Field(default="FR", min_length=2, max_length=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
