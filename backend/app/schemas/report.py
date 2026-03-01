from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.catalog import BookingStatus, SessionStatus


class ReservationReportRow(BaseModel):
    session_id: UUID
    start_at_utc: datetime
    end_at_utc: datetime
    session_status: SessionStatus
    course_type_id: UUID
    course_type_code: str
    course_type_name: str
    location_id: UUID
    location_name: str
    professor_id: UUID
    professor_name: str
    booking_id: UUID
    client_email: str
    booking_status: BookingStatus
    total_incl_vat_snapshot: Decimal
    currency_snapshot: str


class AttendanceReportRow(BaseModel):
    session_id: UUID
    start_at_utc: datetime
    course_type_name: str
    location_name: str
    professor_name: str
    booking_id: UUID
    client_email: str
    attendance_status: str


class ProfessorStatementRow(BaseModel):
    session_id: UUID
    professor_id: UUID
    professor_name: str
    start_at_utc: datetime
    end_at_utc: datetime
    session_status: SessionStatus
    course_type_name: str
    location_name: str
    duration_hours: float
    booked_students: int
    attended_students: int
    no_show_students: int
    excused_absence_students: int
    hourly_rate_snapshot: Decimal | None
    amount_snapshot: Decimal | None
    currency_snapshot: str | None
    payout_status: Literal['PENDING', 'APPROVED', 'PAID'] | None


class CommunicationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class CommunicationSenderCategory(str, enum.Enum):
    PROFESSOR = "PROFESSOR"
    SYSTEM = "SYSTEM"
    OTHER_USER = "OTHER_USER"


class CommunicationDeliveryStatus(str, enum.Enum):
    DELIVERED = "DELIVERED"
    SENT = "SENT"
    FAILED = "FAILED"
    PENDING = "PENDING"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class CommunicationReportRow(BaseModel):
    id: str
    channel: CommunicationChannel
    source: str
    sender_category: CommunicationSenderCategory
    sender_label: str
    occurred_at: datetime
    subject: str
    recipient: str
    delivery_status: CommunicationDeliveryStatus
    provider_message_id: str | None
    content: str
    content_format: Literal["TEXT", "HTML"]
