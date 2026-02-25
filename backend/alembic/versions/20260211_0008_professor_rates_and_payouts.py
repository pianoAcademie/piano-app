"""Add professor hourly rates and payout snapshots

Revision ID: 20260211_0008
Revises: 20260211_0007
Create Date: 2026-02-11 18:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211_0008"
down_revision: Union[str, None] = "20260211_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    payout_status = postgresql.ENUM("PENDING", "APPROVED", "PAID", name="payout_status")
    payout_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "professor_hourly_rates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "professor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("hourly_rate >= 0", name="ck_professor_hourly_rates_non_negative"),
    )
    op.create_index(
        "idx_professor_hourly_rates_lookup",
        "professor_hourly_rates",
        ["professor_id", "course_type_id", "location_id", "valid_from"],
        unique=False,
    )

    op.create_table(
        "professor_session_payouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "professor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("duration_hours", sa.Numeric(6, 2), nullable=False),
        sa.Column("hourly_rate_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_snapshot", sa.String(length=3), nullable=False),
        sa.Column("amount_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "payout_status",
            postgresql.ENUM("PENDING", "APPROVED", "PAID", name="payout_status", create_type=False),
            nullable=False,
            server_default=sa.text("'PENDING'::payout_status"),
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("duration_hours >= 0", name="ck_professor_session_payouts_duration_non_negative"),
        sa.CheckConstraint("hourly_rate_snapshot >= 0", name="ck_professor_session_payouts_rate_non_negative"),
        sa.CheckConstraint("amount_snapshot >= 0", name="ck_professor_session_payouts_amount_non_negative"),
    )
    op.create_index(
        "idx_professor_session_payouts_professor_status",
        "professor_session_payouts",
        ["professor_id", "payout_status"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO professor_hourly_rates (
            professor_id,
            course_type_id,
            location_id,
            currency_code,
            hourly_rate,
            valid_from
        )
        SELECT
            p.id,
            NULL,
            NULL,
            'EUR',
            40.00,
            DATE '2025-01-01'
        FROM professors p
        WHERE p.email = 'prof.demo@piano-academie.local'
          AND NOT EXISTS (
              SELECT 1
              FROM professor_hourly_rates r
              WHERE r.professor_id = p.id
                AND r.course_type_id IS NULL
                AND r.location_id IS NULL
                AND r.valid_from = DATE '2025-01-01'
          )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_professor_session_payouts_professor_status", table_name="professor_session_payouts")
    op.drop_table("professor_session_payouts")

    op.drop_index("idx_professor_hourly_rates_lookup", table_name="professor_hourly_rates")
    op.drop_table("professor_hourly_rates")

    payout_status = postgresql.ENUM("PENDING", "APPROVED", "PAID", name="payout_status")
    payout_status.drop(op.get_bind(), checkfirst=True)
