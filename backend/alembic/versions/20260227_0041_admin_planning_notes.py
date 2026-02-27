"""add admin planning notes for sessions and bookings

Revision ID: 20260227_0041
Revises: 20260227_0040
Create Date: 2026-02-27 17:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260227_0041"
down_revision: Union[str, None] = "20260227_0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("group_note", sa.Text(), nullable=True))
    op.add_column("bookings", sa.Column("student_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "student_note")
    op.drop_column("course_sessions", "group_note")
