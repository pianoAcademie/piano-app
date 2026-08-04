"""persist trial course marker on bookings

Revision ID: 20260804_0172
Revises: 20260803_0171
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260804_0172"
down_revision = "20260803_0171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("is_trial_course", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        """
        UPDATE bookings AS booking
        SET is_trial_course = true
        FROM users AS student, course_sessions AS session, course_types AS course_type
        WHERE booking.user_id = student.id
          AND booking.session_id = session.id
          AND session.course_type_id = course_type.id
          AND (
            student.client_status::text = 'TRIAL'
            OR lower(coalesce(session.title, '') || ' ' || coalesce(course_type.name, '') || ' ' || coalesce(course_type.code, '')) LIKE '%essai%'
            OR lower(coalesce(session.title, '') || ' ' || coalesce(course_type.name, '') || ' ' || coalesce(course_type.code, '')) LIKE '%trial%'
            OR (
              booking.client_plan_subscription_id IS NULL
              AND student.first_course_at IS NOT NULL
              AND abs(extract(epoch FROM (
                student.first_course_at - coalesce(booking.student_start_at_utc, session.start_at_utc)
              ))) < 60
            )
          )
        """
    )


def downgrade() -> None:
    op.drop_column("bookings", "is_trial_course")
