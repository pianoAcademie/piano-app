"""session audience scopes

Revision ID: 20260325_0081
Revises: 20260314_0080
Create Date: 2026-03-25 11:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260325_0081"
down_revision: Union[str, None] = "20260314_0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column("visibility_scope", sa.String(length=20), nullable=False, server_default=sa.text("'EXTERNAL'")),
    )
    op.add_column(
        "course_sessions",
        sa.Column("booking_scope", sa.String(length=20), nullable=False, server_default=sa.text("'EXTERNAL'")),
    )

    op.execute(
        """
        UPDATE course_sessions
        SET visibility_scope = CASE
              WHEN is_private THEN 'PRIVATE'
              ELSE 'EXTERNAL'
            END,
            booking_scope = CASE
              WHEN is_private OR NOT allow_online_booking THEN 'PRIVATE'
              ELSE 'EXTERNAL'
            END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE course_sessions
        SET is_private = CASE WHEN visibility_scope = 'PRIVATE' THEN true ELSE false END,
            allow_online_booking = CASE
              WHEN visibility_scope = 'PRIVATE' OR booking_scope = 'PRIVATE' THEN false
              ELSE true
            END
        """
    )
    op.drop_column("course_sessions", "booking_scope")
    op.drop_column("course_sessions", "visibility_scope")
