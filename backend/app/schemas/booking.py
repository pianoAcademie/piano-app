from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.catalog import BookingStatus, SessionStatus


class AttendanceStatus(str, enum.Enum):
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"
    EXCUSED_ABSENCE = "EXCUSED_ABSENCE"


class BookingCreateRequest(BaseModel):
    client_plan_subscription_id: UUID | None = None
    user_id: UUID | None = None


class AttendanceUpdateRequest(BaseModel):
    attendance_status: AttendanceStatus


class SessionMiniOut(BaseModel):
    id: UUID
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    status: SessionStatus


class BookingOut(BaseModel):
    id: UUID
    session_id: UUID
    client_plan_subscription_id: UUID | None
    status: BookingStatus
    booked_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    price_excl_vat_snapshot: Decimal
    vat_rate_snapshot: Decimal
    vat_amount_snapshot: Decimal
    total_incl_vat_snapshot: Decimal
    currency_snapshot: str
    pricing_snapshot_locked: bool = False
    pricing_channel_snapshot: str | None = None
    pricing_source_snapshot: str | None = None
    pricing_unit_snapshot: str | None = None
    price_book_version_snapshot: str | None = None
    pricing_breakdown_snapshot: dict[str, object] = Field(default_factory=dict)
    pricing_calculated_at: datetime | None = None
    student_start_at_utc: datetime | None = None
    student_end_at_utc: datetime | None = None
    waitlist_position: int | None = None


class ClientBookingOut(BaseModel):
    id: UUID
    client_plan_subscription_id: UUID | None
    status: BookingStatus
    booked_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    price_excl_vat_snapshot: Decimal
    vat_rate_snapshot: Decimal
    vat_amount_snapshot: Decimal
    total_incl_vat_snapshot: Decimal
    currency_snapshot: str
    pricing_snapshot_locked: bool = False
    pricing_channel_snapshot: str | None = None
    pricing_source_snapshot: str | None = None
    pricing_unit_snapshot: str | None = None
    price_book_version_snapshot: str | None = None
    pricing_breakdown_snapshot: dict[str, object] = Field(default_factory=dict)
    pricing_calculated_at: datetime | None = None
    student_start_at_utc: datetime | None = None
    student_end_at_utc: datetime | None = None
    session: SessionMiniOut


class MakeupCreditOut(BaseModel):
    id: UUID
    status: str
    original_booking_id: UUID
    original_session_title: str
    original_session_start_at_utc: datetime
    created_at: datetime


class MakeupStudentSummaryOut(BaseModel):
    user_id: UUID
    display_name: str
    has_active_restricted_forfait: bool
    credits_initial: int
    credits_remaining: int
    pending_makeups: list[MakeupCreditOut]
    history: list[MakeupCreditOut]
