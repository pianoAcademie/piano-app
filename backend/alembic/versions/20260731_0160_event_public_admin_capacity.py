"""add public and admin capacities to school event slots

Revision ID: 20260731_0160
Revises: 20260730_0159
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260731_0160"
down_revision = "20260730_0159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school_event_slots",
        sa.Column("admin_capacity_max", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE school_event_slots
        SET admin_capacity_max = capacity_max
        WHERE admin_capacity_max IS NULL
        """
    )
    op.alter_column("school_event_slots", "admin_capacity_max", nullable=False)
    op.create_check_constraint(
        "ck_school_event_slots_admin_capacity_not_below_public",
        "school_event_slots",
        "admin_capacity_max >= capacity_max",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_school_event_slots_admin_capacity_not_below_public",
        "school_event_slots",
        type_="check",
    )
    op.drop_column("school_event_slots", "admin_capacity_max")
