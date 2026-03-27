"""session audience scope sets

Revision ID: 20260325_0082
Revises: 20260325_0081
Create Date: 2026-03-25 18:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260325_0082"
down_revision: Union[str, None] = "20260325_0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("course_sessions", "visibility_scope", existing_type=sa.String(length=20), type_=sa.Text(), nullable=False)
    op.alter_column("course_sessions", "booking_scope", existing_type=sa.String(length=20), type_=sa.Text(), nullable=False)


def downgrade() -> None:
    op.alter_column("course_sessions", "booking_scope", existing_type=sa.Text(), type_=sa.String(length=20), nullable=False)
    op.alter_column("course_sessions", "visibility_scope", existing_type=sa.Text(), type_=sa.String(length=20), nullable=False)
