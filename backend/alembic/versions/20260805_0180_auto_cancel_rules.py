"""Add opt-in automatic session cancellation rules.

Revision ID: 20260805_0180
Revises: 20260805_0179
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0180"
down_revision = "20260805_0179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column("auto_cancel_rule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("course_sessions", sa.Column("auto_cancel_rule_enabled_override", sa.Boolean(), nullable=True))
    op.add_column(
        "course_sessions",
        sa.Column("auto_cancel_if_booked_less_than_override", sa.Integer(), nullable=True),
    )
    op.add_column(
        "course_sessions",
        sa.Column("auto_cancel_hours_before_start_override", sa.Integer(), nullable=True),
    )
    op.add_column("course_sessions", sa.Column("auto_cancel_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_course_sessions_auto_cancel_count_override_positive",
        "course_sessions",
        "auto_cancel_if_booked_less_than_override IS NULL OR auto_cancel_if_booked_less_than_override >= 1",
    )
    op.create_check_constraint(
        "ck_course_sessions_auto_cancel_hours_override_non_negative",
        "course_sessions",
        "auto_cancel_hours_before_start_override IS NULL OR auto_cancel_hours_before_start_override >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_course_sessions_auto_cancel_hours_override_non_negative",
        "course_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_course_sessions_auto_cancel_count_override_positive",
        "course_sessions",
        type_="check",
    )
    op.drop_column("course_sessions", "auto_cancel_checked_at")
    op.drop_column("course_sessions", "auto_cancel_hours_before_start_override")
    op.drop_column("course_sessions", "auto_cancel_if_booked_less_than_override")
    op.drop_column("course_sessions", "auto_cancel_rule_enabled_override")
    op.drop_column("course_types", "auto_cancel_rule_enabled")
