"""Track origin and activity context for online users.

Revision ID: 20260808_0191
Revises: 20260808_0190
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0191"
down_revision = "20260808_0190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_presences", sa.Column("origin", sa.String(length=200), nullable=True))
    op.add_column("user_presences", sa.Column("last_action", sa.String(length=200), nullable=True))
    op.add_column("user_presences", sa.Column("device_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("user_presences", "device_type")
    op.drop_column("user_presences", "last_action")
    op.drop_column("user_presences", "origin")
