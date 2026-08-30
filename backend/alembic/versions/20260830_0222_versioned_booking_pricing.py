"""Add versioned booking pricing snapshots and explicit external price units.

Revision ID: 20260830_0222
Revises: 20260829_0221
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260830_0222"
down_revision = "20260829_0221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing external prices historically behaved as hourly prices in the
    # public purchase flow. Preserve that meaning; new forms explicitly choose
    # PER_SESSION or PER_HOUR.
    op.add_column(
        "course_sessions",
        sa.Column(
            "external_booking_price_unit",
            sa.String(length=20),
            server_default=sa.text("'PER_HOUR'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_course_sessions_external_price_unit",
        "course_sessions",
        "external_booking_price_unit IN ('PER_SESSION', 'PER_HOUR')",
    )

    op.add_column("bookings", sa.Column("pricing_channel_snapshot", sa.String(length=30), nullable=True))
    op.add_column("bookings", sa.Column("pricing_source_snapshot", sa.String(length=120), nullable=True))
    op.add_column("bookings", sa.Column("pricing_unit_snapshot", sa.String(length=20), nullable=True))
    op.add_column("bookings", sa.Column("price_book_version_snapshot", sa.String(length=120), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "pricing_breakdown_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("bookings", sa.Column("pricing_calculated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "pricing_calculated_at")
    op.drop_column("bookings", "pricing_breakdown_snapshot")
    op.drop_column("bookings", "price_book_version_snapshot")
    op.drop_column("bookings", "pricing_unit_snapshot")
    op.drop_column("bookings", "pricing_source_snapshot")
    op.drop_column("bookings", "pricing_channel_snapshot")
    op.drop_constraint("ck_course_sessions_external_price_unit", "course_sessions", type_="check")
    op.drop_column("course_sessions", "external_booking_price_unit")
