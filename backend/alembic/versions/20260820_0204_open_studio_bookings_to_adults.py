"""Always allow adult bookings for rehearsal studio sessions.

Revision ID: 20260820_0204
Revises: 20260818_0203
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0204"
down_revision = "20260818_0203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE course_sessions AS session
            SET adult_bookings_enabled = true,
                adult_capacity_max = NULL
            FROM course_types AS course_type
            WHERE course_type.id = session.course_type_id
              AND course_type.code = 'STUDIO_REHEARSAL'
            """
        )
    )


def downgrade() -> None:
    # The previous value cannot be reconstructed safely. Keeping adult access
    # is preferable to closing valid studio bookings during a rollback.
    pass
