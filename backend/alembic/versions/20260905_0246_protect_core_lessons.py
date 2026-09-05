"""Protect core lessons from low-attendance cancellation.

Revision ID: 20260905_0246
Revises: 20260905_0245
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_0246"
down_revision: Union[str, None] = "20260905_0245"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROTECTED_ACTIVITY_FILTER = """
    lesson_format = 'INDIVIDUAL'
    OR code IN ('PIANO_GROUP_ONSITE_1H', 'PIANO_GROUP_ONLINE_1H')
    OR lower(name) LIKE '%éveil musical%'
    OR lower(name) LIKE '%eveil musical%'
    OR lower(name) LIKE '%initiation%'
    OR (lower(name) LIKE '%collectif%' AND lower(name) LIKE '%enfant%')
"""


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            f"""
            UPDATE course_types
            SET auto_cancel_rule_enabled = false,
                auto_cancel_if_booked_less_than_override = NULL,
                auto_cancel_hours_before_start_override = NULL
            WHERE {PROTECTED_ACTIVITY_FILTER}
            """
        )
    )
    connection.execute(
        sa.text(
            f"""
            UPDATE course_sessions
            SET auto_cancel_rule_enabled_override = false,
                auto_cancel_if_booked_less_than_override = NULL,
                auto_cancel_hours_before_start_override = NULL,
                auto_cancel_checked_at = NULL
            WHERE course_type_id IN (
                SELECT id FROM course_types WHERE {PROTECTED_ACTIVITY_FILTER}
            )
              AND status = 'SCHEDULED'
              AND start_at_utc > now()
            """
        )
    )


def downgrade() -> None:
    # Safety policy/data cleanup is intentionally not re-enabled automatically.
    pass
