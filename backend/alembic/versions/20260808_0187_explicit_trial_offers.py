"""Add explicit trial offers and per-course trial booking scope.

Revision ID: 20260808_0187
Revises: 20260806_0186
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0187"
down_revision = "20260806_0186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("is_trial_offer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(
        """
        UPDATE plans
        SET is_trial_offer = true
        WHERE kind::text = 'PACK'
          AND coalesce(credits_count, 0) = 1
          AND (
            lower(coalesce(code, '')) LIKE '%trial%'
            OR lower(coalesce(code, '')) LIKE '%essai%'
            OR lower(coalesce(name, '')) LIKE '%trial%'
            OR lower(coalesce(name, '')) LIKE '%essai%'
            OR lower(coalesce(description, '')) LIKE '%trial%'
            OR lower(coalesce(description, '')) LIKE '%essai%'
          )
        """
    )

    op.add_column(
        "bookings",
        sa.Column("trial_course_type_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bookings_trial_course_type_id",
        "bookings",
        "course_types",
        ["trial_course_type_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        WITH ranked_trials AS (
          SELECT
            booking.id,
            session.course_type_id,
            booking.status::text AS booking_status,
            row_number() OVER (
              PARTITION BY booking.user_id, session.course_type_id
              ORDER BY booking.booked_at ASC, booking.id ASC
            ) AS active_rank
          FROM bookings AS booking
          JOIN course_sessions AS session ON session.id = booking.session_id
          WHERE booking.is_trial_course = true
            AND booking.status::text <> 'CANCELLED'
        )
        UPDATE bookings AS booking
        SET trial_course_type_id = ranked.course_type_id
        FROM ranked_trials AS ranked
        WHERE booking.id = ranked.id
          AND ranked.active_rank = 1
        """
    )
    op.execute(
        """
        UPDATE bookings AS booking
        SET trial_course_type_id = session.course_type_id
        FROM course_sessions AS session
        WHERE booking.session_id = session.id
          AND booking.is_trial_course = true
          AND booking.status::text = 'CANCELLED'
        """
    )
    op.create_index(
        "uq_bookings_active_trial_user_course_type",
        "bookings",
        ["user_id", "trial_course_type_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_trial_course = true AND trial_course_type_id IS NOT NULL AND status <> 'CANCELLED'::booking_status"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_bookings_active_trial_user_course_type", table_name="bookings")
    op.drop_constraint("fk_bookings_trial_course_type_id", "bookings", type_="foreignkey")
    op.drop_column("bookings", "trial_course_type_id")
    op.drop_column("plans", "is_trial_offer")
