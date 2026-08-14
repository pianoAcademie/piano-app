"""Add per-session participant audiences, adult quotas, and trial permissions.

Revision ID: 20260814_0198
Revises: 20260813_0197
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0198"
down_revision = "20260813_0197"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column("child_bookings_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "course_sessions",
        sa.Column("adult_bookings_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "course_sessions",
        sa.Column("adult_capacity_max", sa.Integer(), nullable=True),
    )
    op.add_column(
        "course_sessions",
        sa.Column("child_trial_bookings_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "course_sessions",
        sa.Column("adult_trial_bookings_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        "ck_course_sessions_adult_capacity_positive",
        "course_sessions",
        "adult_capacity_max IS NULL OR adult_capacity_max >= 1",
    )
    op.create_check_constraint(
        "ck_course_sessions_adult_capacity_within_total",
        "course_sessions",
        "adult_capacity_max IS NULL OR adult_capacity_max <= capacity_max",
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_sessions_adult_capacity_within_total", "course_sessions", type_="check")
    op.drop_constraint("ck_course_sessions_adult_capacity_positive", "course_sessions", type_="check")
    op.drop_column("course_sessions", "adult_trial_bookings_enabled")
    op.drop_column("course_sessions", "child_trial_bookings_enabled")
    op.drop_column("course_sessions", "adult_capacity_max")
    op.drop_column("course_sessions", "adult_bookings_enabled")
    op.drop_column("course_sessions", "child_bookings_enabled")
