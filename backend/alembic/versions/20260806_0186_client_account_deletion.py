"""Track client-initiated account deletion.

Revision ID: 20260806_0186
Revises: 20260806_0185
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0186"
down_revision = "20260806_0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("account_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_account_deleted_at", "users", ["account_deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_account_deleted_at", table_name="users")
    op.drop_column("users", "account_deleted_at")
