from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

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
    session: SessionMiniOut
