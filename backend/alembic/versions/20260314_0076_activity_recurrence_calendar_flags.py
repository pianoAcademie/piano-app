"""add recurrence calendar exclusion flags on course types

Revision ID: 20260314_0076
Revises: 20260314_0075
Create Date: 2026-03-14 23:35:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260314_0076"
down_revision: Union[str, None] = "20260314_0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column(
            "exclude_holidays_in_recurrence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "course_types",
        sa.Column(
            "exclude_school_vacations_in_recurrence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("course_types", "exclude_school_vacations_in_recurrence")
    op.drop_column("course_types", "exclude_holidays_in_recurrence")
