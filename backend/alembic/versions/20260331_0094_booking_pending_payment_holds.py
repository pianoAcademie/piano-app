"""add pending-payment booking holds

Revision ID: 20260331_0094
Revises: 20260331_0093
Create Date: 2026-03-31 10:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260331_0094"
down_revision: Union[str, None] = "20260331_0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT'"))

    op.add_column(
        "bookings",
        sa.Column("payment_hold_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bookings_status_payment_hold_expires_at",
        "bookings",
        ["status", "payment_hold_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_status_payment_hold_expires_at", table_name="bookings")
    op.drop_column("bookings", "payment_hold_expires_at")
