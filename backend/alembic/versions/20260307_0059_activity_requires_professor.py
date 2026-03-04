"""activity requires_professor and nullable session professor

Revision ID: 20260307_0059
Revises: 20260307_0058
Create Date: 2026-03-07 16:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260307_0059"
down_revision: Union[str, None] = "20260307_0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column("requires_professor", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("course_sessions", "professor_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.execute(
        """
        UPDATE course_sessions
        SET professor_id = (
            SELECT id
            FROM professors
            ORDER BY created_at ASC
            LIMIT 1
        )
        WHERE professor_id IS NULL
        """
    )
    op.alter_column("course_sessions", "professor_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("course_types", "requires_professor")
