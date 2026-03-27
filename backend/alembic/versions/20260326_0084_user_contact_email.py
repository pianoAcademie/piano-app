"""add user contact email

Revision ID: 20260326_0084
Revises: 20260326_0083
Create Date: 2026-03-26 19:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260326_0084"
down_revision = "20260326_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.create_index("ix_users_contact_email", "users", ["contact_email"], unique=False)
    op.execute(
        """
        UPDATE users
        SET contact_email = lower(email)
        WHERE contact_email IS NULL
          AND email IS NOT NULL
          AND lower(email) NOT LIKE '%@no-email.local'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_contact_email", table_name="users")
    op.drop_column("users", "contact_email")
