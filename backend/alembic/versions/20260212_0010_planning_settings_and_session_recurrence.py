"""Add planning settings and session recurrence/private flags

Revision ID: 20260212_0010
Revises: 20260211_0009
Create Date: 2026-02-12 15:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260212_0010"
down_revision: Union[str, None] = "20260211_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column(
            "is_private",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "course_sessions",
        sa.Column(
            "recurrence_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "course_sessions",
        sa.Column(
            "recurrence_rule",
            sa.String(length=30),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_course_sessions_recurrence_group",
        "course_sessions",
        ["recurrence_group_id"],
        unique=False,
    )

    op.create_table(
        "planning_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("min_booking_notice_hours", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_booking_horizon_months", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("cancellation_deadline_hours", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_bookings_per_client", sa.Integer(), nullable=True),
        sa.Column("allow_negative_credits", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("waitlist_capacity", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("auto_cancel_if_booked_less_than", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("auto_cancel_hours_before_start", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_force_booking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_multi_booking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notify_coach", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notify_admins", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("hide_booking_count", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("block_client_cancellation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("min_booking_notice_hours >= 0", name="ck_planning_configs_min_notice_non_negative"),
        sa.CheckConstraint("max_booking_horizon_months >= 1", name="ck_planning_configs_max_horizon_positive"),
        sa.CheckConstraint("cancellation_deadline_hours >= 0", name="ck_planning_configs_cancel_deadline_non_negative"),
        sa.CheckConstraint("max_bookings_per_client IS NULL OR max_bookings_per_client >= 1", name="ck_planning_configs_max_bookings_positive"),
        sa.CheckConstraint("waitlist_capacity >= 0", name="ck_planning_configs_waitlist_non_negative"),
        sa.CheckConstraint("auto_cancel_if_booked_less_than >= 0", name="ck_planning_configs_auto_cancel_count_non_negative"),
        sa.CheckConstraint("auto_cancel_hours_before_start >= 0", name="ck_planning_configs_auto_cancel_hours_non_negative"),
    )

    op.create_index(
        "idx_planning_configs_location",
        "planning_configs",
        ["location_id"],
        unique=True,
    )

    op.execute(
        """
        INSERT INTO planning_configs (location_id, description)
        SELECT l.id, l.name
        FROM locations l
        WHERE NOT EXISTS (
            SELECT 1
            FROM planning_configs pc
            WHERE pc.location_id = l.id
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_planning_configs_location", table_name="planning_configs")
    op.drop_table("planning_configs")

    op.drop_index("idx_course_sessions_recurrence_group", table_name="course_sessions")
    op.drop_column("course_sessions", "recurrence_rule")
    op.drop_column("course_sessions", "recurrence_group_id")
    op.drop_column("course_sessions", "is_private")
