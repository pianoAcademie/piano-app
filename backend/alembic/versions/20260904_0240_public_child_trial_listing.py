"""Add explicit publication flag for the public child trial calendar.

Revision ID: 20260904_0240
Revises: 20260903_0239
"""

import sqlalchemy as sa
from alembic import op


revision = "20260904_0240"
down_revision = "20260903_0239"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_sessions",
        sa.Column(
            "public_child_trial_listing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_course_sessions_public_child_trial_listing",
        "course_sessions",
        ["start_at_utc"],
        unique=False,
        postgresql_where=sa.text("public_child_trial_listing_enabled = true"),
    )
    op.execute(
        """
        update course_sessions as session
        set public_child_trial_listing_enabled = true
        from course_types as activity
        where activity.id = session.course_type_id
          and lower(activity.name) in (
              'cours d''essai collectif enfants',
              'cours d''essai individuel'
          )
          and session.child_bookings_enabled = true
        """
    )


def downgrade() -> None:
    op.drop_index("ix_course_sessions_public_child_trial_listing", table_name="course_sessions")
    op.drop_column("course_sessions", "public_child_trial_listing_enabled")
