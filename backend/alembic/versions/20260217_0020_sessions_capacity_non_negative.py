"""allow zero capacity on course sessions (vacation day)

Revision ID: 20260217_0020
Revises: 20260216_0019
Create Date: 2026-02-17 10:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260217_0020"
down_revision: Union[str, None] = "20260216_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_course_sessions_capacity_positive", "course_sessions", type_="check")
    op.create_check_constraint(
        "ck_course_sessions_capacity_positive",
        "course_sessions",
        "capacity_max >= 0",
    )
    op.execute(
        """
        UPDATE course_sessions cs
        SET capacity_max = 0
        FROM course_types ct
        WHERE cs.course_type_id = ct.id
          AND ct.code = 'VACATION_DAY'
        """
    )


def downgrade() -> None:
    op.execute("UPDATE course_sessions SET capacity_max = 1 WHERE capacity_max = 0")
    op.drop_constraint("ck_course_sessions_capacity_positive", "course_sessions", type_="check")
    op.create_check_constraint(
        "ck_course_sessions_capacity_positive",
        "course_sessions",
        "capacity_max > 0",
    )
