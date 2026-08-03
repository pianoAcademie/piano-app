"""control remaining seats visibility for events

Revision ID: 20260803_0171
Revises: 20260803_0170
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260803_0171"
down_revision = "20260803_0170"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school_events",
        sa.Column("show_remaining_seats", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("school_events", "show_remaining_seats")
