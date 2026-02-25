"""add headcount rules on professor rate overrides

Revision ID: 20260225_0034
Revises: 20260225_0033
Create Date: 2026-02-25 11:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260225_0034"
down_revision: Union[str, None] = "20260225_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professor_hourly_rates",
        sa.Column("headcount_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.alter_column("professor_hourly_rates", "hourly_rate", existing_type=sa.Numeric(precision=12, scale=2), nullable=True)


def downgrade() -> None:
    op.alter_column("professor_hourly_rates", "hourly_rate", existing_type=sa.Numeric(precision=12, scale=2), nullable=False)
    op.drop_column("professor_hourly_rates", "headcount_rules_json")
