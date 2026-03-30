"""add external booking price on course sessions

Revision ID: 20260327_0085
Revises: 20260326_0084
Create Date: 2026-03-27 13:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260327_0085"
down_revision = "20260326_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("external_booking_price_ttc", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("course_sessions", "external_booking_price_ttc")
