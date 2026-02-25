"""add all-day/private descriptions on sessions and seed vacation activity

Revision ID: 20260216_0019
Revises: 20260215_0018
Create Date: 2026-02-16 16:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260216_0019"
down_revision: Union[str, None] = "20260215_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("private_description", sa.Text(), nullable=True))
    op.add_column(
        "course_sessions",
        sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.execute(
        """
        INSERT INTO course_types (
            code,
            name,
            description,
            service_code,
            duration_minutes,
            color_hex,
            mode,
            default_capacity,
            active
        )
        VALUES (
            'VACATION_DAY',
            'Vacances',
            'Journee vacances (blocage des occurrences recurrentes)',
            'VACATION',
            1440,
            '#B3BAC5',
            'ANY',
            1,
            true
        )
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO planning_course_types (location_id, course_type_id, display_order)
        SELECT
            l.id,
            ct.id,
            COALESCE(
                (
                    SELECT MAX(pct.display_order) + 1
                    FROM planning_course_types pct
                    WHERE pct.location_id = l.id
                ),
                0
            ) AS display_order
        FROM locations l
        JOIN course_types ct ON ct.code = 'VACATION_DAY'
        ON CONFLICT (location_id, course_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM planning_course_types
        WHERE course_type_id IN (
            SELECT id
            FROM course_types
            WHERE code = 'VACATION_DAY'
        )
        """
    )

    op.execute("DELETE FROM course_types WHERE code = 'VACATION_DAY'")
    op.drop_column("course_sessions", "is_all_day")
    op.drop_column("course_sessions", "private_description")

