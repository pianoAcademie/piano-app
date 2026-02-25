"""Add client profile fields on users

Revision ID: 20260211_0009
Revises: 20260211_0008
Create Date: 2026-02-11 20:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260211_0009"
down_revision: Union[str, None] = "20260211_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("address_line", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=100),
            nullable=False,
            server_default=sa.text("'Europe/Paris'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at")
    op.drop_column("users", "timezone")
    op.drop_column("users", "phone")
    op.drop_column("users", "address_line")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
