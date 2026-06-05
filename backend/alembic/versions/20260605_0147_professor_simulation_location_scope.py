"""professor simulation location scope

Revision ID: 20260605_0147
Revises: 20260529_0146
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260605_0147"
down_revision = "20260529_0146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column("planning_simulation_location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_professor_permissions_planning_simulation_location_id",
        "professor_permissions",
        "locations",
        ["planning_simulation_location_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_professor_permissions_planning_simulation_location_id",
        "professor_permissions",
        type_="foreignkey",
    )
    op.drop_column("professor_permissions", "planning_simulation_location_id")
