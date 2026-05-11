"""manager backoffice permissions

Revision ID: 20260511_0109
Revises: 20260509_0108
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260511_0109"
down_revision = "20260509_0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_planning_simulation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_intakes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_quotes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("professor_permissions", "can_view_quotes")
    op.drop_column("professor_permissions", "can_view_intakes")
    op.drop_column("professor_permissions", "can_view_planning_simulation")
