"""add event venues and price tiers

Revision ID: 20260803_0167
Revises: 20260803_0166
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260803_0167"
down_revision = "20260803_0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "school_event_venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("address_line", sa.String(length=255), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), server_default="FR", nullable=False),
        sa.Column("timezone", sa.String(length=100), server_default="Europe/Paris", nullable=False),
        sa.Column("is_online", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("school_events", sa.Column("event_venue_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_school_events_event_venue", "school_events", "school_event_venues", ["event_venue_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("school_event_slots", sa.Column("event_venue_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_school_event_slots_event_venue", "school_event_slots", "school_event_venues", ["event_venue_id"], ["id"], ondelete="SET NULL"
    )
    op.create_table(
        "school_event_price_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_fr", sa.String(length=120), nullable=False),
        sa.Column("label_en", sa.String(length=120), nullable=True),
        sa.Column("price_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price_ttc >= 0", name="ck_school_event_price_tiers_price_non_negative"),
        sa.ForeignKeyConstraint(["event_id"], ["school_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_school_event_price_tiers_event_sort", "school_event_price_tiers", ["event_id", "sort_order"])
    op.add_column("school_event_registrations", sa.Column("price_tier_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("school_event_registrations", sa.Column("price_tier_label_snapshot", sa.String(length=120), nullable=True))
    op.create_foreign_key(
        "fk_school_event_registrations_price_tier",
        "school_event_registrations",
        "school_event_price_tiers",
        ["price_tier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_school_event_registrations_price_tier", "school_event_registrations", type_="foreignkey")
    op.drop_column("school_event_registrations", "price_tier_label_snapshot")
    op.drop_column("school_event_registrations", "price_tier_id")
    op.drop_index("ix_school_event_price_tiers_event_sort", table_name="school_event_price_tiers")
    op.drop_table("school_event_price_tiers")
    op.drop_constraint("fk_school_event_slots_event_venue", "school_event_slots", type_="foreignkey")
    op.drop_column("school_event_slots", "event_venue_id")
    op.drop_constraint("fk_school_events_event_venue", "school_events", type_="foreignkey")
    op.drop_column("school_events", "event_venue_id")
    op.drop_table("school_event_venues")
