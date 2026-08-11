from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PlanKind(str, enum.Enum):
    PACK = "PACK"
    SUBSCRIPTION = "SUBSCRIPTION"
    FORFAIT = "FORFAIT"


class PlanRestrictionPeriod(str, enum.Enum):
    ACTIVE_BOOKINGS = "ACTIVE_BOOKINGS"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    ROLLING_MONTH = "ROLLING_MONTH"
    SEMESTER = "SEMESTER"


class PlanPriceTaxMode(str, enum.Enum):
    HT = "HT"
    TTC = "TTC"


class PlanCreditGrantsRelation(str, enum.Enum):
    AND = "AND"
    OR = "OR"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[PlanKind] = mapped_column(
        Enum(
            PlanKind,
            name="plan_kind",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
    )
    credits_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pack_validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forfait_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    forfait_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_price_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_tax_mode: Mapped[PlanPriceTaxMode] = mapped_column(
        Enum(
            PlanPriceTaxMode,
            name="plan_price_tax_mode",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'HT'::plan_price_tax_mode"),
    )
    monthly_price_excl_vat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_frequency: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'monthly'"))
    booking_rights_policy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retry_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_retry_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_policy_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_notification_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    signup_fee_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    signup_fee_excl_vat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    first_purchase_signup_fee_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    first_purchase_partitions_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    first_purchase_partitions_price_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    credit_grants_relation: Mapped[PlanCreditGrantsRelation] = mapped_column(
        Enum(
            PlanCreditGrantsRelation,
            name="plan_credit_grants_relation",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'OR'::plan_credit_grants_relation"),
    )
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_trial_offer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    options_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    payment_methods_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    restrictions_json: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class PlanEntitlement(Base):
    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "course_type_id", name="uq_plan_entitlements"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class PlanCreditGrant(Base):
    __tablename__ = "plan_credit_grants"
    __table_args__ = (UniqueConstraint("plan_id", "credit_type_id", name="uq_plan_credit_grants"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    credit_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credits_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class SubscriptionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PAYMENT_ALERT = "PAYMENT_ALERT"
    PRE_TERMINATION = "PRE_TERMINATION"
    TERMINATED = "TERMINATED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ClientPlanSubscription(Base):
    __tablename__ = "client_plan_subscriptions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    migration_source_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    payer_contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(
            SubscriptionStatus,
            name="subscription_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ACTIVE'::subscription_status"),
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credits_initial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    bookings_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    billing_method_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_charge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    initial_amount_excl_vat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    initial_vat_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    initial_total_incl_vat: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    initial_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    initial_price_breakdown_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    first_purchase_charges_applied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    payment_provider_subscription_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_provider_customer_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_provider_mandate_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_provider_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_provider_payment_method_ref: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payment_method_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_method_brand: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payment_method_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    payment_method_exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method_exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method_setup_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    payment_method_setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_alert_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pre_termination_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    direct_payment_recovery_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    forfait_loyalty_discount_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    forfait_family_discount_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    forfait_short_commitment_supplement_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    suspension_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suspension_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suspension_duration_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suspension_duration_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_request_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancellation_request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_request_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_terms_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    legal_terms_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    legal_terms_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legal_terms_content_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_terms_acceptance_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ClientForfaitActivityPricing(Base):
    __tablename__ = "client_forfait_activity_pricing"
    __table_args__ = (UniqueConstraint("subscription_id", "course_type_id", name="uq_client_forfait_activity_pricing"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    loyalty_discount_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    family_discount_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    short_commitment_supplement_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    second_course_weekly_discount_per_hour_ttc: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
