"""activity planning rules overrides

Revision ID: 20260305_0049
Revises: 20260305_0048
Create Date: 2026-03-05 00:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260305_0049"
down_revision: Union[str, None] = "20260305_0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_types", sa.Column("min_booking_notice_hours_override", sa.Integer(), nullable=True))
    op.add_column("course_types", sa.Column("cancellation_deadline_hours_override", sa.Integer(), nullable=True))
    op.add_column("course_types", sa.Column("auto_cancel_if_booked_less_than_override", sa.Integer(), nullable=True))
    op.add_column("course_types", sa.Column("auto_cancel_hours_before_start_override", sa.Integer(), nullable=True))

    op.create_check_constraint(
        "ck_course_types_min_notice_override_non_negative",
        "course_types",
        "min_booking_notice_hours_override IS NULL OR min_booking_notice_hours_override >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_cancel_deadline_override_non_negative",
        "course_types",
        "cancellation_deadline_hours_override IS NULL OR cancellation_deadline_hours_override >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_auto_cancel_count_override_non_negative",
        "course_types",
        "auto_cancel_if_booked_less_than_override IS NULL OR auto_cancel_if_booked_less_than_override >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_auto_cancel_hours_override_non_negative",
        "course_types",
        "auto_cancel_hours_before_start_override IS NULL OR auto_cancel_hours_before_start_override >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_types_auto_cancel_hours_override_non_negative", "course_types", type_="check")
    op.drop_constraint("ck_course_types_auto_cancel_count_override_non_negative", "course_types", type_="check")
    op.drop_constraint("ck_course_types_cancel_deadline_override_non_negative", "course_types", type_="check")
    op.drop_constraint("ck_course_types_min_notice_override_non_negative", "course_types", type_="check")

    op.drop_column("course_types", "auto_cancel_hours_before_start_override")
    op.drop_column("course_types", "auto_cancel_if_booked_less_than_override")
    op.drop_column("course_types", "cancellation_deadline_hours_override")
    op.drop_column("course_types", "min_booking_notice_hours_override")
