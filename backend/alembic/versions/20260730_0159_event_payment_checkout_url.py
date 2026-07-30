"""store active school event checkout url

Revision ID: 20260730_0159
Revises: 20260730_0158
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260730_0159"
down_revision = "20260730_0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school_event_registrations",
        sa.Column("payment_checkout_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("school_event_registrations", "payment_checkout_url")
