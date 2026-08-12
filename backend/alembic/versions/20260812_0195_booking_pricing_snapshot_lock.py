"""Lock an explicitly confirmed booking price snapshot.

Revision ID: 20260812_0195
Revises: 20260812_0194
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0195"
down_revision = "20260812_0194"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("pricing_snapshot_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("bookings", "pricing_snapshot_locked")
