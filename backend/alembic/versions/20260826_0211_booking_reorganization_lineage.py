"""Track the financial lineage of reorganized bookings.

Revision ID: 20260826_0211
Revises: 20260825_0210
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0211"
down_revision: str | None = "20260825_0210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_reorganization_links",
        sa.Column("source_booking_id", sa.UUID(), nullable=False),
        sa.Column("target_booking_id", sa.UUID(), nullable=False),
        sa.Column("financially_neutral", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_booking_id"),
    )
    op.create_index(
        "ix_booking_reorganization_links_target_booking_id",
        "booking_reorganization_links",
        ["target_booking_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_booking_reorganization_links_target_booking_id", table_name="booking_reorganization_links")
    op.drop_table("booking_reorganization_links")
