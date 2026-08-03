"""support repeat public bookings and performer-specific forms

Revision ID: 20260803_0169
Revises: 20260803_0168
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260803_0169"
down_revision = "20260803_0168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school_events",
        sa.Column("collect_performer_booking", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "school_event_registrations",
        sa.Column("public_booking_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_school_event_registrations_public_booking_request_id",
        "school_event_registrations",
        ["public_booking_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_school_event_registrations_public_booking_request_id",
        table_name="school_event_registrations",
    )
    op.drop_column("school_event_registrations", "public_booking_request_id")
    op.drop_column("school_events", "collect_performer_booking")
