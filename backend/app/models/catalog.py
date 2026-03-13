from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class DeliveryMode(str, enum.Enum):
    ONLINE = "ONLINE"
    ONSITE = "ONSITE"
    ANY = "ANY"


class SessionStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class BookingStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"
    EXCUSED_ABSENCE = "EXCUSED_ABSENCE"


class Professor(Base):
    __tablename__ = "professors"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    siret: Mapped[str | None] = mapped_column(String(30), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_invoice_counter: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    teacher_is_vat_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    teacher_vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    teacher_siret: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_iban: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_company_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contract_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contract_file_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    contract_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    zoom_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    spoken_languages: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    is_coach: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    daily_schedule_email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    daily_schedule_email_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default=text("'07:00'"))
    daily_schedule_skip_if_no_course: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_daily_schedule_sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_activation_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CreditType(Base):
    __tablename__ = "credit_types"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class CourseType(Base):
    __tablename__ = "course_types"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_course_types_duration_positive"),
        CheckConstraint("default_capacity >= 0", name="ck_course_types_capacity_positive"),
        CheckConstraint(
            "allows_student_bookings OR default_capacity = 0",
            name="ck_course_types_no_student_requires_zero_capacity",
        ),
        CheckConstraint("char_length(color_hex) = 7", name="ck_course_types_color_hex_length"),
        CheckConstraint(
            "default_hourly_rate IS NULL OR default_hourly_rate >= 0",
            name="ck_course_types_default_hourly_rate_non_negative",
        ),
        CheckConstraint(
            "default_course_rate_ttc IS NULL OR default_course_rate_ttc >= 0",
            name="ck_course_types_default_course_rate_non_negative",
        ),
        CheckConstraint(
            "email_reminder_hours_before_start IS NULL OR email_reminder_hours_before_start >= 0",
            name="ck_course_types_email_reminder_hours_non_negative",
        ),
        CheckConstraint(
            "sms_reminder_hours_before_start IS NULL OR sms_reminder_hours_before_start >= 0",
            name="ck_course_types_sms_reminder_hours_non_negative",
        ),
        CheckConstraint(
            "min_booking_notice_hours_override IS NULL OR min_booking_notice_hours_override >= 0",
            name="ck_course_types_min_notice_override_non_negative",
        ),
        CheckConstraint(
            "cancellation_deadline_hours_override IS NULL OR cancellation_deadline_hours_override >= 0",
            name="ck_course_types_cancel_deadline_override_non_negative",
        ),
        CheckConstraint(
            "auto_cancel_if_booked_less_than_override IS NULL OR auto_cancel_if_booked_less_than_override >= 0",
            name="ck_course_types_auto_cancel_count_override_non_negative",
        ),
        CheckConstraint(
            "auto_cancel_hours_before_start_override IS NULL OR auto_cancel_hours_before_start_override >= 0",
            name="ck_course_types_auto_cancel_hours_override_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    billing_entity_code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default=text("'PIANO_ACADEMIE'"),
    )
    seller_legal_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    payor_legal_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    credit_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False, server_default=text("'#94C973'"))
    mode: Mapped[DeliveryMode] = mapped_column(
        Enum(
            DeliveryMode,
            name="delivery_mode",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
    )
    requires_professor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    allows_student_bookings: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    default_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    default_course_rate_ttc: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    email_reminder_hours_before_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_reminder_hours_before_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_booking_notice_hours_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancellation_deadline_hours_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_cancel_if_booked_less_than_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_cancel_hours_before_start_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exclude_holidays_in_recurrence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    exclude_school_vacations_in_recurrence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CourseSession(Base):
    __tablename__ = "course_sessions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="restrict"),
        nullable=False,
    )
    billing_entity_snapshot: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default=text("'PIANO_ACADEMIE'"),
    )
    snapshot_seller_legal_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    snapshot_payor_legal_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=True,
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="restrict"),
        nullable=False,
    )
    professor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="restrict"),
        nullable=True,
    )
    substitute_teacher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="restrict"),
        nullable=True,
    )
    substitute_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    substitute_set_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    substitute_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    professor_reminder_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    capacity_max: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'SCHEDULED'::session_status"),
    )
    auto_cancel_deadline_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    zoom_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    allow_online_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'UTC'"))
    recurrence_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String(30), nullable=True)
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


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_bookings_session_user"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_sessions.id", ondelete="cascade"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="cascade"),
        nullable=False,
    )
    client_plan_subscription_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_plan_subscriptions.id"),
        nullable=True,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'BOOKED'::booking_status"),
    )
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_excl_vat_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    vat_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    vat_amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    total_incl_vat_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    student_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlanningConfig(Base):
    __tablename__ = "planning_configs"
    __table_args__ = (
        CheckConstraint("min_booking_notice_hours >= 0", name="ck_planning_configs_min_notice_non_negative"),
        CheckConstraint("max_booking_horizon_months >= 1", name="ck_planning_configs_max_horizon_positive"),
        CheckConstraint("cancellation_deadline_hours >= 0", name="ck_planning_configs_cancel_deadline_non_negative"),
        CheckConstraint(
            "max_bookings_per_client IS NULL OR max_bookings_per_client >= 1",
            name="ck_planning_configs_max_bookings_positive",
        ),
        CheckConstraint("waitlist_capacity >= 0", name="ck_planning_configs_waitlist_non_negative"),
        CheckConstraint("auto_cancel_if_booked_less_than >= 0", name="ck_planning_configs_auto_cancel_count_non_negative"),
        CheckConstraint("auto_cancel_hours_before_start >= 0", name="ck_planning_configs_auto_cancel_hours_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_booking_notice_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_booking_horizon_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    cancellation_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_bookings_per_client: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_negative_credits: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    waitlist_capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    auto_cancel_if_booked_less_than: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    auto_cancel_hours_before_start: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    allow_force_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    allow_multi_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notify_coach: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_admins: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    hide_booking_count: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    block_client_cancellation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class PlanningCourseType(Base):
    __tablename__ = "planning_course_types"
    __table_args__ = (
        UniqueConstraint("location_id", "course_type_id", name="uq_planning_course_types_location_course_type"),
        CheckConstraint("display_order >= 0", name="ck_planning_course_types_display_order_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
