"""add professor permission to view all school sessions

Revision ID: 20260223_0026
Revises: 20260222_0025
Create Date: 2026-02-23 10:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260223_0026"
down_revision: Union[str, None] = "20260222_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column(
            "can_view_all_school_sessions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("professor_permissions", "can_view_all_school_sessions")
