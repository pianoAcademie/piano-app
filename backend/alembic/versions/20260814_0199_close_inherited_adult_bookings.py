"""Close inherited adult booking access unless the slot is explicitly adult-facing.

Revision ID: 20260814_0199
Revises: 20260814_0198
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0199"
down_revision = "20260814_0198"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "course_sessions",
        "adult_bookings_enabled",
        server_default=sa.text("false"),
    )
    op.alter_column(
        "course_sessions",
        "adult_trial_bookings_enabled",
        server_default=sa.text("false"),
    )

    # Revision 0198 initially opened every existing slot to adults. Keep that
    # access only where an adult intent can be recovered safely from the data:
    # an explicit quota, an adult/teen course label, or an existing adult booking.
    op.execute(
        sa.text(
            """
            UPDATE course_sessions AS session
            SET adult_bookings_enabled = false,
                adult_trial_bookings_enabled = false
            WHERE session.adult_capacity_max IS NULL
              AND NOT (
                  lower(coalesce(session.title, ''))
                      ~ '(^|[^[:alnum:]])(ado|ados|adolescent|adolescents|adult|adulte|adultes)([^[:alnum:]]|$)'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM course_types AS course_type
                  WHERE course_type.id = session.course_type_id
                    AND (
                        lower(coalesce(course_type.name, ''))
                            ~ '(^|[^[:alnum:]])(ado|ados|adolescent|adolescents|adult|adulte|adultes)([^[:alnum:]]|$)'
                        OR lower(coalesce(course_type.code, ''))
                            ~ '(^|[^[:alnum:]])(ado|ados|adolescent|adolescents|adult|adulte|adultes)([^[:alnum:]]|$)'
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings AS booking
                  JOIN users AS participant ON participant.id = booking.user_id
                  WHERE booking.session_id = session.id
                    AND participant.client_kind = 'ADULT'::client_kind
                    AND booking.status::text <> 'CANCELLED'
              )
            """
        )
    )


def downgrade() -> None:
    # Cleaned rows cannot be distinguished reliably from rows that were already
    # closed before this revision, so only restore the former creation defaults.
    op.alter_column(
        "course_sessions",
        "adult_trial_bookings_enabled",
        server_default=sa.text("true"),
    )
    op.alter_column(
        "course_sessions",
        "adult_bookings_enabled",
        server_default=sa.text("true"),
    )
