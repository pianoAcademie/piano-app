from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DomainEvent(Base):
    __tablename__ = "domain_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    related_entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    related_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    email_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    email_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    sms_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'Europe/Paris'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notifications_idempotency_key"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    source_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("domain_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    related_entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    related_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    booking_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    slot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_type: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_contact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bounce_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ContactDeliveryStatus(Base):
    __tablename__ = "contact_delivery_status"
    __table_args__ = (
        UniqueConstraint("contact_type", "contact_id", name="uq_contact_delivery_status_contact"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    contact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    contact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    email_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_last_bounce_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_last_provider_feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    phone_suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone_last_provider_feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ContactDeliveryIncident(Base):
    __tablename__ = "contact_delivery_incidents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    contact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    contact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    detail_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    job_name: Mapped[str] = mapped_column(String(120), nullable=False)
    job_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    items_scanned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class JobRunLog(Base):
    __tablename__ = "job_run_logs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    job_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class JobCursor(Base):
    __tablename__ = "job_cursors"

    job_name: Mapped[str] = mapped_column(String(120), primary_key=True, nullable=False)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminNotificationSetting(Base):
    __tablename__ = "admin_notification_settings"
    __table_args__ = (
        UniqueConstraint("notification_type", "recipient_email", name="uq_admin_notification_settings_type_email"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
