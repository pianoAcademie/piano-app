from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ReminderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class MessageFormat(str, enum.Enum):
    TEXT = "TEXT"
    HTML = "HTML"


class EmailReminder(Base):
    __tablename__ = "email_reminders"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(
            ReminderStatus,
            name="reminder_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'PENDING'::reminder_status"),
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProfessorSessionMessage(Base):
    __tablename__ = "professor_session_messages"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    professor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_format: Mapped[MessageFormat] = mapped_column(
        Enum(
            MessageFormat,
            name="message_format",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'TEXT'::message_format"),
    )
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
