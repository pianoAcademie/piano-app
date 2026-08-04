"""add scoped check-deposit permission for Bar-le-Duc manager

Revision ID: 20260804_0175
Revises: 20260804_0174
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260804_0175"
down_revision = "20260804_0174"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_check_deposits", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("check_deposits_location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_professor_permissions_check_deposits_location_id",
        "professor_permissions",
        "locations",
        ["check_deposits_location_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO professor_permissions (
                professor_id,
                can_manage_check_deposits,
                check_deposits_location_id,
                updated_at
            )
            SELECT professor.id, true, location.id, now()
            FROM professors AS professor
            CROSS JOIN locations AS location
            WHERE lower(professor.email) = 'estela.oliviero@piano-academie.com'
              AND upper(location.code) = 'BAR_LE_DUC'
            ON CONFLICT (professor_id) DO UPDATE
            SET can_manage_check_deposits = EXCLUDED.can_manage_check_deposits,
                check_deposits_location_id = EXCLUDED.check_deposits_location_id,
                updated_at = EXCLUDED.updated_at
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_professor_permissions_check_deposits_location_id",
        "professor_permissions",
        type_="foreignkey",
    )
    op.drop_column("professor_permissions", "check_deposits_location_id")
    op.drop_column("professor_permissions", "can_manage_check_deposits")
