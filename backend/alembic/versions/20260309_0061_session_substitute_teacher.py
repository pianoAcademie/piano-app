"""Add substitute teacher fields on course sessions

Revision ID: 20260309_0061
Revises: 20260308_0060
Create Date: 2026-03-09 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260309_0061"
down_revision: Union[str, None] = "20260308_0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column("substitute_teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "course_sessions",
        sa.Column("substitute_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "course_sessions",
        sa.Column("substitute_set_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "course_sessions",
        sa.Column("substitute_note", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_course_sessions_substitute_teacher_id",
        "course_sessions",
        "professors",
        ["substitute_teacher_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_course_sessions_substitute_set_by",
        "course_sessions",
        "users",
        ["substitute_set_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_course_sessions_substitute_teacher_id",
        "course_sessions",
        ["substitute_teacher_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_sessions_substitute_teacher_id", table_name="course_sessions")
    op.drop_constraint("fk_course_sessions_substitute_set_by", "course_sessions", type_="foreignkey")
    op.drop_constraint("fk_course_sessions_substitute_teacher_id", "course_sessions", type_="foreignkey")
    op.drop_column("course_sessions", "substitute_note")
    op.drop_column("course_sessions", "substitute_set_by")
    op.drop_column("course_sessions", "substitute_set_at")
    op.drop_column("course_sessions", "substitute_teacher_id")
