from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.catalog import DeliveryMode, LessonFormat, SessionAudienceScope, SessionStatus


class CourseTypeOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    service_code: str
    credit_type_id: UUID | None = None
    credit_type_code: str | None = None
    credit_type_name: str | None = None
    duration_minutes: int
    color_hex: str
    mode: DeliveryMode
    lesson_format: LessonFormat
    requires_professor: bool
    allows_student_bookings: bool
    supports_student_time_overrides: bool
    default_capacity: int
    default_hourly_rate: Decimal | None
    default_course_rate_ttc: Decimal | None
    auto_cancel_if_booked_less_than_override: int | None = None
    auto_cancel_hours_before_start_override: int | None = None
    auto_cancel_rule_enabled: bool = False
    active: bool


class LocationOut(BaseModel):
    id: UUID
    code: str
    name: str
    supports_student_time_overrides: bool = False
    address_line: str | None
    city: str | None
    country_code: str | None
    is_online: bool
    timezone: str
    active: bool


class SessionCourseTypeOut(BaseModel):
    id: UUID
    code: str
    name: str


class SessionLocationOut(BaseModel):
    id: UUID
    code: str
    name: str
    is_online: bool


class SessionProfessorOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str


class SessionOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    start_at_local: datetime
    end_at_local: datetime
    timezone: str
    session_timezone: str
    status: SessionStatus
    capacity_max: int
    booked_count: int
    seats_remaining: int
    visibility_scopes: list[SessionAudienceScope]
    booking_scopes: list[SessionAudienceScope]
    visibility_scope: SessionAudienceScope
    booking_scope: SessionAudienceScope
    online_booking_enabled: bool
    external_booking_price_ttc: Decimal | None = None
    external_booking_currency: str | None = None
    show_external_remaining_seats: bool = True
    zoom_link: str | None
    substitute_teacher_id: UUID | None = None
    substitute_teacher_display_name: str | None = None
    effective_teacher_id: UUID | None = None
    effective_teacher_display_name: str | None = None
    course_type: SessionCourseTypeOut
    location: SessionLocationOut
    professor: SessionProfessorOut | None
