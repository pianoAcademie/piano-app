from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AdminSubscriptionChargeNowRequest(BaseModel):
    expected_amount: Decimal = Field(gt=0)
    expected_currency: str = Field(min_length=3, max_length=3)
    confirm_charge: bool = False


class AdminSubscriptionRefundRequest(BaseModel):
    confirm_refund: bool = False


class AdminSubscriptionEngineRowOut(BaseModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    customer_email: str
    plan_id: UUID
    plan_name: str
    status: str
    bookings_blocked: bool
    next_billing_date: datetime | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    last_attempt_at: datetime | None
    last_successful_charge_at: datetime | None
    last_cycle_status: str | None
    recovery_url: str | None
    amount: Decimal | None
    currency: str | None


class AdminSubscriptionEngineListOut(BaseModel):
    items: list[AdminSubscriptionEngineRowOut]
    total: int


class AdminSubscriptionCycleOut(BaseModel):
    id: UUID
    period_start: datetime
    period_end: datetime
    billing_date: datetime
    status: str
    attempt_count: int
    first_attempt_at: datetime | None
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    paid_at: datetime | None
    amount: Decimal
    currency: str
    payment_recovery_url: str | None


class AdminSubscriptionAttemptOut(BaseModel):
    id: UUID
    billing_cycle_id: UUID
    attempt_number: int
    attempted_at: datetime
    amount: Decimal
    currency: str
    status: str
    provider_name: str | None
    provider_payment_id: str | None
    provider_status: str | None
    failure_code: str | None
    failure_reason: str | None


class AdminSubscriptionNotificationOut(BaseModel):
    id: UUID
    notification_type: str
    status: str
    recipient_email: str | None
    scheduled_for: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None


class AdminSubscriptionEngineDetailOut(BaseModel):
    subscription: AdminSubscriptionEngineRowOut
    cycles: list[AdminSubscriptionCycleOut]
    attempts: list[AdminSubscriptionAttemptOut]
    notifications: list[AdminSubscriptionNotificationOut]
    initial_payment_refundable: bool = False
    initial_payment_refunded: bool = False
