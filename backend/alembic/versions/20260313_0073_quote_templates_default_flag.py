"""add default flag to quote templates

Revision ID: 20260313_0073
Revises: 20260313_0072
Create Date: 2026-03-13 17:15:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260313_0073"
down_revision: Union[str, None] = "20260313_0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quote_templates", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("quote_templates", "is_default")
