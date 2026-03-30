"""add external remaining seats visibility to sessions

Revision ID: 20260330_0089
Revises: 20260329_0088
Create Date: 2026-03-30 12:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_0089"
down_revision: Union[str, None] = "20260329_0088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column("show_external_remaining_seats", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(
        sa.text(
            "UPDATE course_sessions SET show_external_remaining_seats = true "
            "WHERE show_external_remaining_seats IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("course_sessions", "show_external_remaining_seats")
