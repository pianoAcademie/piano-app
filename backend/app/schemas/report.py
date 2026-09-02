from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

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


class TrialCourseEmailEvent(BaseModel):
    communication_id: UUID
    trigger_code: str
    trigger_label: str
    subject: str
    delivery_status: str
    sent_at: datetime
    delivered_at: datetime | None = None


class TrialCourseReportRow(BaseModel):
    booking_id: UUID
    session_id: UUID
    session_start_at: datetime
    session_end_at: datetime
    session_timezone: str
    course_type_name: str
    course_format: Literal["COLLECTIF", "PARTICULIER"]
    location_id: UUID
    location_name: str
    professor_id: UUID | None = None
    professor_name: str
    student_id: UUID
    student_first_name: str | None = None
    student_last_name: str | None = None
    student_email: str
    parent_email: str | None = None
    attendance_status: str
    attendance_label: str
    internal_note: str | None = None
    conversion_status: str
    account_status_label: str
    client_kind: str
    client_status: str
    has_intake: bool
    intake_status_label: str
    intake_status: str | None = None
    intake_received_at: datetime | None = None
    quote_status: str | None = None
    quote_status_label: str
    is_registered: bool
    enrollment_status_label: str
    enrollment_evidence: str | None = None
    email_history: list[TrialCourseEmailEvent] = Field(default_factory=list)
    trial_detection_source: str


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


class IntakeFamilyChildSummary(BaseModel):
    intake_id: UUID
    received_at: datetime
    source_form_id: str
    source_form_label: str | None = None
    child_name: str
    segment: str | None = None
    status: str
    course_1: str | None = None
    course_2: str | None = None
    solfege: str | None = None
    masterclass: str | None = None
    pass_recup: str | None = None


class IntakeFamilySummaryRow(BaseModel):
    family_key: str
    family_label: str
    parent_name: str | None = None
    parent_email: str | None = None
    parent_phone: str | None = None
    intake_count: int
    children: list[IntakeFamilyChildSummary] = Field(default_factory=list)


class GeneratedReportCreate(BaseModel):
    report_type: str = Field(min_length=1, max_length=80)
    period_start: date | None = None
    period_end: date | None = None
    note: str | None = Field(default=None, max_length=500)
    criteria: dict[str, object] = Field(default_factory=dict)


class GeneratedReportOut(BaseModel):
    id: UUID
    report_type: str
    report_label: str
    file_format: str
    period_start: date | None = None
    period_end: date | None = None
    note: str | None = None
    row_count: int
    created_by_user_id: UUID | None = None
    created_at: datetime


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
    communication_type: str
    communication_type_label: str
    sender_category: CommunicationSenderCategory
    sender_label: str
    sender_user_id: UUID | None
    professor_id: UUID | None
    occurred_at: datetime
    subject: str
    recipient: str
    recipient_display_name: str | None
    recipient_user_id: UUID | None
    delivery_status: CommunicationDeliveryStatus
    provider_message_id: str | None
    provider: str | None
    content: str
    content_format: Literal["TEXT", "HTML"]
    error_message: str | None


class CommunicationResendRequest(BaseModel):
    recipient_email: str | None = Field(default=None, min_length=3, max_length=255)


class CommunicationPeriod(str, enum.Enum):
    TODAY = "TODAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    SEMESTER = "SEMESTER"
    YEAR = "YEAR"
    ALL = "ALL"


class CommunicationReportPageOut(BaseModel):
    items: list[CommunicationReportRow]
    page: int
    per_page: int
    total: int
    total_pages: int


class CommunicationTypeFilterOut(BaseModel):
    code: str
    label: str


class CommunicationProfessorFilterOut(BaseModel):
    id: UUID
    label: str


class CommunicationFiltersOut(BaseModel):
    communication_types: list[CommunicationTypeFilterOut]
    professors: list[CommunicationProfessorFilterOut]
