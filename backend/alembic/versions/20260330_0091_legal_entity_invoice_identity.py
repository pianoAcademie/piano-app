"""add legal entity invoice identity fields

Revision ID: 20260330_0091
Revises: 20260330_0090
Create Date: 2026-03-30 18:42:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_0091"
down_revision: Union[str, None] = "20260330_0090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("legal_entities", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("legal_entities", sa.Column("legal_form", sa.String(length=20), nullable=True))
    op.add_column("legal_entities", sa.Column("share_capital", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("legal_entities", "share_capital")
    op.drop_column("legal_entities", "legal_form")
    op.drop_column("legal_entities", "phone")
