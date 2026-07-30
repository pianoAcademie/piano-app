from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class SchoolEventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class SchoolEventAudience(str, enum.Enum):
    PUBLIC = "PUBLIC"
    CLIENTS = "CLIENTS"


class SchoolEventRegistrationMode(str, enum.Enum):
    INDIVIDUAL_SLOT = "INDIVIDUAL_SLOT"
    GROUP_SESSION = "GROUP_SESSION"


class SchoolEventPaymentMode(str, enum.Enum):
    FREE = "FREE"
    ON_SITE = "ON_SITE"
    ONLINE = "ONLINE"


class SchoolEventSlotStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class SchoolEventRegistrationStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"


EVENT_REGISTRATION_CAPACITY_STATUSES = (
    SchoolEventRegistrationStatus.PENDING_PAYMENT,
    SchoolEventRegistrationStatus.CONFIRMED,
    SchoolEventRegistrationStatus.ATTENDED,
    SchoolEventRegistrationStatus.NO_SHOW,
)


class SchoolEvent(Base):
    __tablename__ = "school_events"
    __table_args__ = (
        CheckConstraint("price_ttc >= 0", name="ck_school_events_price_non_negative"),
        CheckConstraint("max_per_family >= 1", name="ck_school_events_max_per_family_positive"),
        CheckConstraint("cancellation_deadline_hours >= 0", name="ck_school_events_cancel_deadline_non_negative"),
        Index("ix_school_events_status_category", "status", "category"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    title_fr: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'AUTRE'"))
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SchoolEventStatus] = mapped_column(
        Enum(
            SchoolEventStatus,
            name="school_event_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'DRAFT'::school_event_status"),
    )
    audience: Mapped[SchoolEventAudience] = mapped_column(
        Enum(
            SchoolEventAudience,
            name="school_event_audience",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'CLIENTS'::school_event_audience"),
    )
    registration_mode: Mapped[SchoolEventRegistrationMode] = mapped_column(
        Enum(
            SchoolEventRegistrationMode,
            name="school_event_registration_mode",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'GROUP_SESSION'::school_event_registration_mode"),
    )
    payment_mode: Mapped[SchoolEventPaymentMode] = mapped_column(
        Enum(
            SchoolEventPaymentMode,
            name="school_event_payment_mode",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'FREE'::school_event_payment_mode"),
    )
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    booking_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booking_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    price_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    max_per_family: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    waitlist_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    cancellation_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("24"))
    collect_piece_info: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    collect_photo_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    confirmation_message_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_message_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SchoolEventSlot(Base):
    __tablename__ = "school_event_slots"
    __table_args__ = (
        CheckConstraint("capacity_max >= 1", name="ck_school_event_slots_capacity_positive"),
        CheckConstraint("end_at_utc > start_at_utc", name="ck_school_event_slots_dates_order"),
        Index("ix_school_event_slots_event_start", "event_id", "start_at_utc"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("school_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    label: Mapped[str | None] = mapped_column(String(180), nullable=True)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'Europe/Paris'"))
    capacity_max: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SchoolEventSlotStatus] = mapped_column(
        Enum(
            SchoolEventSlotStatus,
            name="school_event_slot_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'SCHEDULED'::school_event_slot_status"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SchoolEventRegistration(Base):
    __tablename__ = "school_event_registrations"
    __table_args__ = (
        CheckConstraint("party_size >= 1", name="ck_school_event_registrations_party_size_positive"),
        CheckConstraint("total_ttc_snapshot >= 0", name="ck_school_event_registrations_total_non_negative"),
        Index("ix_school_event_registrations_slot_status", "slot_id", "status"),
        Index("ix_school_event_registrations_booker", "booker_user_id", "booked_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    slot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("school_event_slots.id", ondelete="CASCADE"),
        nullable=False,
    )
    booker_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    participant_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    guest_names_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, server_default=text("'[]'::json"))
    answers_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, server_default=text("'{}'::json"))
    status: Mapped[SchoolEventRegistrationStatus] = mapped_column(
        Enum(
            SchoolEventRegistrationStatus,
            name="school_event_registration_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
    )
    unit_price_ttc_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    total_ttc_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    payment_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payment_hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
