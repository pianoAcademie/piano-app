"""add parallel slots to simulation templates

Revision ID: 20260329_0088
Revises: 20260328_0087
Create Date: 2026-03-29 10:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260329_0088"
down_revision: Union[str, None] = "20260328_0087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulation_templates",
        sa.Column("parallel_slots", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.execute(sa.text("UPDATE simulation_templates SET parallel_slots = 1 WHERE parallel_slots IS NULL"))
    op.create_check_constraint(
        "ck_simulation_templates_parallel_slots_positive",
        "simulation_templates",
        "parallel_slots >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_simulation_templates_parallel_slots_positive",
        "simulation_templates",
        type_="check",
    )
    op.drop_column("simulation_templates", "parallel_slots")
