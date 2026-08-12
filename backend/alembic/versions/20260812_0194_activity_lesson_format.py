"""Add the pedagogical format to activities.

Revision ID: 20260812_0194
Revises: 20260811_0193
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0194"
down_revision = "20260811_0193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column("lesson_format", sa.String(length=20), server_default=sa.text("'GROUP'"), nullable=False),
    )
    op.create_check_constraint(
        "ck_course_types_lesson_format",
        "course_types",
        "lesson_format IN ('INDIVIDUAL', 'GROUP')",
    )
    op.execute(
        """
        UPDATE course_types
        SET lesson_format = 'INDIVIDUAL'
        WHERE allows_student_bookings = true
          AND (
            default_capacity = 1
            OR upper(code) LIKE '%INDIVID%'
            OR upper(code) LIKE '%PARTICUL%'
            OR lower(name) LIKE '%individuel%'
            OR lower(name) LIKE '%particulier%'
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_types_lesson_format", "course_types", type_="check")
    op.drop_column("course_types", "lesson_format")
