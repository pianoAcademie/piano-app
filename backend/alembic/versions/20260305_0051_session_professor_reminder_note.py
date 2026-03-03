"""add professor reminder note on sessions

Revision ID: 20260305_0051
Revises: 20260305_0050
Create Date: 2026-03-05 11:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260305_0051"
down_revision: Union[str, None] = "20260305_0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("professor_reminder_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("course_sessions", "professor_reminder_note")

