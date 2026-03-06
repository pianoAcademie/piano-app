from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionRetryPolicy(Base):
    __tablename__ = "subscription_retry_policies"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    first_retry_delay_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_auto_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    move_to_pre_termination_after_failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("2"),
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SubscriptionNotificationPolicy(Base):
    __tablename__ = "subscription_notification_policies"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    on_success_customer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    on_success_admin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    on_first_failure_customer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    on_first_failure_admin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    on_final_failure_customer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    on_final_failure_admin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    customer_success_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    admin_success_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_first_failure_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    admin_first_failure_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_final_failure_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    admin_final_failure_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SubscriptionBillingCycle(Base):
    __tablename__ = "subscription_billing_cycles"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "period_start",
            "period_end",
            name="uq_subscription_billing_cycles_subscription_period",
        ),
    )

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
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    billing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_recovery_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_recovery_provider_ref: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SubscriptionPaymentAttempt(Base):
    __tablename__ = "subscription_payment_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_subscription_payment_attempts_idempotency_key"),
        UniqueConstraint(
            "billing_cycle_id",
            "attempt_number",
            name="uq_subscription_payment_attempts_cycle_attempt_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    billing_cycle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_billing_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    provider_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
