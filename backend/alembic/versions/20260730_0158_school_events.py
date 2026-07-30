"""add school events and registrations

Revision ID: 20260730_0158
Revises: 20260716_0157
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260730_0158"
down_revision = "20260716_0157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    event_status = postgresql.ENUM(
        "DRAFT", "PUBLISHED", "CLOSED", "CANCELLED", "COMPLETED",
        name="school_event_status",
        create_type=False,
    )
    event_audience = postgresql.ENUM(
        "PUBLIC", "CLIENTS",
        name="school_event_audience",
        create_type=False,
    )
    registration_mode = postgresql.ENUM(
        "INDIVIDUAL_SLOT", "GROUP_SESSION",
        name="school_event_registration_mode",
        create_type=False,
    )
    payment_mode = postgresql.ENUM(
        "FREE", "ON_SITE", "ONLINE",
        name="school_event_payment_mode",
        create_type=False,
    )
    slot_status = postgresql.ENUM(
        "SCHEDULED", "CANCELLED", "COMPLETED",
        name="school_event_slot_status",
        create_type=False,
    )
    registration_status = postgresql.ENUM(
        "PENDING_PAYMENT", "CONFIRMED", "WAITLISTED", "CANCELLED", "ATTENDED", "NO_SHOW",
        name="school_event_registration_status",
        create_type=False,
    )
    bind = op.get_bind()
    for enum_type in (event_status, event_audience, registration_mode, payment_mode, slot_status, registration_status):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "school_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title_fr", sa.String(length=255), nullable=False),
        sa.Column("title_en", sa.String(length=255), nullable=True),
        sa.Column("description_fr", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), server_default=sa.text("'AUTRE'"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("status", event_status, server_default=sa.text("'DRAFT'::school_event_status"), nullable=False),
        sa.Column("audience", event_audience, server_default=sa.text("'CLIENTS'::school_event_audience"), nullable=False),
        sa.Column("registration_mode", registration_mode, server_default=sa.text("'GROUP_SESSION'::school_event_registration_mode"), nullable=False),
        sa.Column("payment_mode", payment_mode, server_default=sa.text("'FREE'::school_event_payment_mode"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booking_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_ttc", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("max_per_family", sa.Integer(), server_default=sa.text("6"), nullable=False),
        sa.Column("waitlist_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("cancellation_deadline_hours", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("collect_piece_info", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("collect_photo_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("confirmation_message_fr", sa.Text(), nullable=True),
        sa.Column("confirmation_message_en", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price_ttc >= 0", name="ck_school_events_price_non_negative"),
        sa.CheckConstraint("max_per_family >= 1", name="ck_school_events_max_per_family_positive"),
        sa.CheckConstraint("cancellation_deadline_hours >= 0", name="ck_school_events_cancel_deadline_non_negative"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_school_events_status_category", "school_events", ["status", "category"])

    op.create_table(
        "school_event_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(length=180), nullable=True),
        sa.Column("start_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), server_default=sa.text("'Europe/Paris'"), nullable=False),
        sa.Column("capacity_max", sa.Integer(), nullable=False),
        sa.Column("status", slot_status, server_default=sa.text("'SCHEDULED'::school_event_slot_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("capacity_max >= 1", name="ck_school_event_slots_capacity_positive"),
        sa.CheckConstraint("end_at_utc > start_at_utc", name="ck_school_event_slots_dates_order"),
        sa.ForeignKeyConstraint(["event_id"], ["school_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_school_event_slots_event_start", "school_event_slots", ["event_id", "start_at_utc"])

    op.create_table(
        "school_event_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booker_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("participant_display_name", sa.String(length=255), nullable=False),
        sa.Column("party_size", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("guest_names_json", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("answers_json", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("status", registration_status, nullable=False),
        sa.Column("unit_price_ttc_snapshot", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_ttc_snapshot", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("currency_snapshot", sa.String(length=3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("payment_provider", sa.String(length=30), nullable=True),
        sa.Column("payment_reference", sa.String(length=180), nullable=True),
        sa.Column("payment_hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("party_size >= 1", name="ck_school_event_registrations_party_size_positive"),
        sa.CheckConstraint("total_ttc_snapshot >= 0", name="ck_school_event_registrations_total_non_negative"),
        sa.ForeignKeyConstraint(["booker_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["slot_id"], ["school_event_slots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_school_event_registrations_slot_status", "school_event_registrations", ["slot_id", "status"])
    op.create_index("ix_school_event_registrations_booker", "school_event_registrations", ["booker_user_id", "booked_at"])


def downgrade() -> None:
    op.drop_index("ix_school_event_registrations_booker", table_name="school_event_registrations")
    op.drop_index("ix_school_event_registrations_slot_status", table_name="school_event_registrations")
    op.drop_table("school_event_registrations")
    op.drop_index("ix_school_event_slots_event_start", table_name="school_event_slots")
    op.drop_table("school_event_slots")
    op.drop_index("ix_school_events_status_category", table_name="school_events")
    op.drop_table("school_events")
    bind = op.get_bind()
    for name in (
        "school_event_registration_status",
        "school_event_slot_status",
        "school_event_payment_mode",
        "school_event_registration_mode",
        "school_event_audience",
        "school_event_status",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
