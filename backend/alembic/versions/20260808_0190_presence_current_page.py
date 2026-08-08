"""Track the current page for active users.

Revision ID: 20260808_0190
Revises: 20260808_0189
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0190"
down_revision = "20260808_0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_presences", sa.Column("current_path", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("user_presences", "current_path")
