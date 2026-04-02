"""track manual credit coverage on bookings

Revision ID: 20260402_0099
Revises: 20260401_0098
Create Date: 2026-04-02 10:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260402_0099"
down_revision: Union[str, None] = "20260401_0098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("manual_credit_type_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bookings_manual_credit_type_id",
        "bookings",
        "credit_types",
        ["manual_credit_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_bookings_manual_credit_type_id",
        "bookings",
        ["manual_credit_type_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_manual_credit_type_id", table_name="bookings")
    op.drop_constraint("fk_bookings_manual_credit_type_id", "bookings", type_="foreignkey")
    op.drop_column("bookings", "manual_credit_type_id")
