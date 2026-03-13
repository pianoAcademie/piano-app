"""activity studentless slots

Revision ID: 20260314_0080
Revises: 20260314_0079
Create Date: 2026-03-14 19:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260314_0080"
down_revision: Union[str, None] = "20260314_0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column("allows_student_bookings", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.drop_constraint("ck_course_types_capacity_positive", "course_types", type_="check")
    op.create_check_constraint(
        "ck_course_types_capacity_positive",
        "course_types",
        "default_capacity >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_no_student_requires_zero_capacity",
        "course_types",
        "allows_student_bookings OR default_capacity = 0",
    )
    op.execute(
        """
        UPDATE course_types
        SET allows_student_bookings = false,
            default_capacity = 0,
            requires_professor = false
        WHERE code = 'VACATION_DAY'
           OR UPPER(service_code) LIKE 'VACATION%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE course_types
        SET default_capacity = CASE WHEN default_capacity <= 0 THEN 1 ELSE default_capacity END,
            requires_professor = CASE
              WHEN code = 'VACATION_DAY' OR UPPER(service_code) LIKE 'VACATION%' THEN true
              ELSE requires_professor
            END
        """
    )
    op.drop_constraint("ck_course_types_no_student_requires_zero_capacity", "course_types", type_="check")
    op.drop_constraint("ck_course_types_capacity_positive", "course_types", type_="check")
    op.create_check_constraint(
        "ck_course_types_capacity_positive",
        "course_types",
        "default_capacity > 0",
    )
    op.drop_column("course_types", "allows_student_bookings")
