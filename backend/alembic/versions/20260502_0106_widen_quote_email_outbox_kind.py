"""widen quote email outbox kind column

Revision ID: 20260502_0106
Revises: 20260430_0105
Create Date: 2026-05-02 15:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260502_0106"
down_revision: Union[str, None] = "20260430_0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "quote_email_outbox",
        "kind",
        existing_type=sa.String(length=30),
        type_=sa.String(length=80),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "quote_email_outbox",
        "kind",
        existing_type=sa.String(length=80),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
