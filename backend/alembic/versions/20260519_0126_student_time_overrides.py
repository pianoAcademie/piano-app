"""add student time overrides for bookings

Revision ID: 20260519_0126
Revises: 20260518_0125
Create Date: 2026-05-19 12:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0126"
down_revision: Union[str, None] = "20260518_0125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column(
            "supports_student_time_overrides",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("bookings", sa.Column("student_start_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("student_end_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_bookings_student_time_override_pair",
        "bookings",
        """
        (
            student_start_at_utc is null
            and student_end_at_utc is null
        )
        or (
            student_start_at_utc is not null
            and student_end_at_utc is not null
            and student_end_at_utc > student_start_at_utc
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint("ck_bookings_student_time_override_pair", "bookings", type_="check")
    op.drop_column("bookings", "student_end_at_utc")
    op.drop_column("bookings", "student_start_at_utc")
    op.drop_column("course_types", "supports_student_time_overrides")
