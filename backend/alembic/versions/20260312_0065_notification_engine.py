"""Add centralized notification engine tables

Revision ID: 20260312_0065
Revises: 20260311_0064
Create Date: 2026-03-12 09:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260312_0065"
down_revision: Union[str, None] = "20260311_0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("actor_type", sa.String(length=40), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_entity_type", sa.String(length=60), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_domain_events_event_type_occurred", "domain_events", ["event_type", "occurred_at"], unique=False)
    op.create_index("ix_domain_events_related_entity", "domain_events", ["related_entity_type", "related_entity_id"], unique=False)
    op.create_index("ix_domain_events_source_occurred", "domain_events", ["source", "occurred_at"], unique=False)

    op.create_table(
        "notification_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("email_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sms_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timezone", sa.String(length=100), nullable=False, server_default=sa.text("'Europe/Paris'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_rules_scope", "notification_rules", ["scope_type", "scope_id", "active"], unique=False)

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_name", sa.String(length=120), nullable=False),
        sa.Column("job_key", sa.String(length=120), nullable=True),
        sa.Column("triggered_by", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("items_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_sent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"], unique=False)
    op.create_index("ix_job_runs_job_name_status", "job_runs", ["job_name", "status"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("dispatch_mode", sa.String(length=20), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("related_entity_type", sa.String(length=60), nullable=False),
        sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_type", sa.String(length=40), nullable=False),
        sa.Column("recipient_contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("recipient_phone", sa.String(length=40), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body_snapshot", sa.Text(), nullable=True),
        sa.Column("payload_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=60), nullable=True),
        sa.Column("provider_message_id", sa.String(length=180), nullable=True),
        sa.Column("provider_status", sa.String(length=80), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("bounce_type", sa.String(length=80), nullable=True),
        sa.Column("job_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["slot_id"], ["course_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_event_id"], ["domain_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_notifications_idempotency_key"),
    )
    op.create_index("ix_notifications_dispatch_status_schedule", "notifications", ["dispatch_mode", "status", "scheduled_for"], unique=False)
    op.create_index("ix_notifications_type_created_at", "notifications", ["notification_type", "created_at"], unique=False)
    op.create_index("ix_notifications_recipient_contact_id", "notifications", ["recipient_contact_id", "created_at"], unique=False)
    op.create_index("ix_notifications_booking_id", "notifications", ["booking_id"], unique=False)
    op.create_index("ix_notifications_slot_id", "notifications", ["slot_id"], unique=False)
    op.create_index("ix_notifications_provider_message_id", "notifications", ["provider_message_id"], unique=False)

    op.create_table(
        "contact_delivery_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contact_type", sa.String(length=40), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("email_suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_suspension_reason", sa.Text(), nullable=True),
        sa.Column("email_last_bounce_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_last_provider_feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("phone_status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("phone_suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_suspension_reason", sa.Text(), nullable=True),
        sa.Column("phone_last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_last_provider_feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_type", "contact_id", name="uq_contact_delivery_status_contact"),
    )
    op.create_index("ix_contact_delivery_status_email_status", "contact_delivery_status", ["email_status"], unique=False)
    op.create_index("ix_contact_delivery_status_phone_status", "contact_delivery_status", ["phone_status"], unique=False)

    op.create_table(
        "contact_delivery_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contact_type", sa.String(length=40), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("incident_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=60), nullable=True),
        sa.Column("provider_message_id", sa.String(length=180), nullable=True),
        sa.Column("detail_text", sa.Text(), nullable=True),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_delivery_incidents_detected", "contact_delivery_incidents", ["detected_at"], unique=False)
    op.create_index("ix_contact_delivery_incidents_contact", "contact_delivery_incidents", ["contact_type", "contact_id"], unique=False)
    op.create_index("ix_contact_delivery_incidents_channel", "contact_delivery_incidents", ["channel", "incident_type"], unique=False)

    op.create_table(
        "job_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_run_logs_job_run_id", "job_run_logs", ["job_run_id", "created_at"], unique=False)

    op.create_table(
        "job_cursors",
        sa.Column("job_name", sa.String(length=120), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("job_name"),
    )

    op.create_table(
        "admin_notification_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_type", "recipient_email", name="uq_admin_notification_settings_type_email"),
    )
    op.create_index("ix_admin_notification_settings_type_active", "admin_notification_settings", ["notification_type", "active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_admin_notification_settings_type_active", table_name="admin_notification_settings")
    op.drop_table("admin_notification_settings")

    op.drop_table("job_cursors")

    op.drop_index("ix_job_run_logs_job_run_id", table_name="job_run_logs")
    op.drop_table("job_run_logs")

    op.drop_index("ix_contact_delivery_incidents_channel", table_name="contact_delivery_incidents")
    op.drop_index("ix_contact_delivery_incidents_contact", table_name="contact_delivery_incidents")
    op.drop_index("ix_contact_delivery_incidents_detected", table_name="contact_delivery_incidents")
    op.drop_table("contact_delivery_incidents")

    op.drop_index("ix_contact_delivery_status_phone_status", table_name="contact_delivery_status")
    op.drop_index("ix_contact_delivery_status_email_status", table_name="contact_delivery_status")
    op.drop_table("contact_delivery_status")

    op.drop_index("ix_notifications_provider_message_id", table_name="notifications")
    op.drop_index("ix_notifications_slot_id", table_name="notifications")
    op.drop_index("ix_notifications_booking_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_contact_id", table_name="notifications")
    op.drop_index("ix_notifications_type_created_at", table_name="notifications")
    op.drop_index("ix_notifications_dispatch_status_schedule", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_job_runs_job_name_status", table_name="job_runs")
    op.drop_index("ix_job_runs_started_at", table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_index("ix_notification_rules_scope", table_name="notification_rules")
    op.drop_table("notification_rules")

    op.drop_index("ix_domain_events_source_occurred", table_name="domain_events")
    op.drop_index("ix_domain_events_related_entity", table_name="domain_events")
    op.drop_index("ix_domain_events_event_type_occurred", table_name="domain_events")
    op.drop_table("domain_events")
