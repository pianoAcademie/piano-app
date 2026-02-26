"""add session timezone and online booking toggle

Revision ID: 20260226_0037
Revises: 20260226_0036
Create Date: 2026-02-26 20:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0037"
down_revision: Union[str, None] = "20260226_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column("allow_online_booking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "course_sessions",
        sa.Column("timezone", sa.String(length=100), nullable=False, server_default=sa.text("'UTC'")),
    )
    op.execute(
        """
        UPDATE course_sessions AS cs
        SET timezone = COALESCE(NULLIF(loc.timezone, ''), 'UTC')
        FROM locations AS loc
        WHERE loc.id = cs.location_id
        """
    )


def downgrade() -> None:
    op.drop_column("course_sessions", "timezone")
    op.drop_column("course_sessions", "allow_online_booking")
