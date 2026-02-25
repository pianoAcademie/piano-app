"""Add default hourly rate on activity referential

Revision ID: 20260214_0014
Revises: 20260213_0013
Create Date: 2026-02-14 11:25:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260214_0014"
down_revision: Union[str, None] = "20260213_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_types", sa.Column("default_hourly_rate", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(
        "ck_course_types_default_hourly_rate_non_negative",
        "course_types",
        "default_hourly_rate IS NULL OR default_hourly_rate >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_types_default_hourly_rate_non_negative", "course_types", type_="check")
    op.drop_column("course_types", "default_hourly_rate")
