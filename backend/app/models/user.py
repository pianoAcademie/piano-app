from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROF = "prof"
    CLIENT = "client"


class ClientKind(str, enum.Enum):
    ADULT = "ADULT"
    CHILD = "CHILD"


class ClientStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RESPONSABLE = "RESPONSABLE"
    INACTIVE = "INACTIVE"
    TRIAL = "TRIAL"
    PENDING = "PENDING"
    ARCHIVED = "ARCHIVED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'client'::user_role"),
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_country: Mapped[str] = mapped_column(String(2), nullable=False, server_default=text("'FR'"))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mobile_phone_1: Mapped[str | None] = mapped_column(String(30), nullable=True)
    mobile_phone_2: Mapped[str | None] = mapped_column(String(30), nullable=True)
    home_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    important_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    residence_country: Mapped[str] = mapped_column(String(2), nullable=False, server_default=text("'FR'"))
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'fr'"))
    preferred_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'Europe/Paris'"))
    first_course_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    portal_contact_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    email_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    lesson_reminder_email_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    lesson_reminder_sms_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    communication_optout_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        server_default=text("gen_random_uuid()::text"),
    )
    client_kind: Mapped[ClientKind] = mapped_column(
        Enum(
            ClientKind,
            name="client_kind",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ADULT'::client_kind"),
    )
    client_status: Mapped[ClientStatus] = mapped_column(
        Enum(
            ClientStatus,
            name="client_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ACTIVE'::client_status"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
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
