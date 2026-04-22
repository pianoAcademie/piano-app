"""add preferred language on users

Revision ID: 20260422_0101
Revises: 20260410_0100
Create Date: 2026-04-22 11:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260422_0101"
down_revision: Union[str, None] = "20260410_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_language", sa.String(length=8), nullable=False, server_default=sa.text("'fr'")),
    )
    op.execute(sa.text("UPDATE users SET preferred_language = 'fr' WHERE preferred_language IS NULL OR preferred_language = ''"))


def downgrade() -> None:
    op.drop_column("users", "preferred_language")
