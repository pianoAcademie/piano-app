"""rename Dulong location

Revision ID: 20260602_0147
Revises: 20260529_0146
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260602_0147"
down_revision: Union[str, None] = "20260529_0146"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DULONG_CODE = "DULONG"
OLD_DULONG_NAME = "Dulong"
NEW_DULONG_NAME = "Rue Dulong"


def upgrade() -> None:
    connection = op.get_bind()
    dulong_id = connection.execute(
        sa.text(
            """
            UPDATE locations
            SET name = :new_name
            WHERE code = :code
            RETURNING id
            """
        ),
        {"code": DULONG_CODE, "new_name": NEW_DULONG_NAME},
    ).scalar()

    if dulong_id is None:
        return

    connection.execute(
        sa.text(
            """
            UPDATE planning_configs
            SET description = :new_name,
                updated_at = now()
            WHERE location_id = :location_id
              AND (description IS NULL OR description = :old_name)
            """
        ),
        {
            "location_id": dulong_id,
            "old_name": OLD_DULONG_NAME,
            "new_name": NEW_DULONG_NAME,
        },
    )


def downgrade() -> None:
    connection = op.get_bind()
    dulong_id = connection.execute(
        sa.text(
            """
            UPDATE locations
            SET name = :old_name
            WHERE code = :code
            RETURNING id
            """
        ),
        {"code": DULONG_CODE, "old_name": OLD_DULONG_NAME},
    ).scalar()

    if dulong_id is None:
        return

    connection.execute(
        sa.text(
            """
            UPDATE planning_configs
            SET description = :old_name,
                updated_at = now()
            WHERE location_id = :location_id
              AND (description IS NULL OR description = :new_name)
            """
        ),
        {
            "location_id": dulong_id,
            "old_name": OLD_DULONG_NAME,
            "new_name": NEW_DULONG_NAME,
        },
    )
