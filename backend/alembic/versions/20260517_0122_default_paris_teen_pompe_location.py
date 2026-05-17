"""default Paris teen Typeform to Pompe location

Revision ID: 20260517_0122
Revises: 20260517_0121
Create Date: 2026-05-17 17:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_0122"
down_revision: Union[str, None] = "20260517_0121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_SOURCE_CODE = "typeform_paris_teen_2026_2027_multisite"
TARGET_FORM_ID = "hnX4kqpY"


def _location_id(connection: sa.Connection, code: str) -> object | None:
    return connection.execute(
        sa.text(
            """
            SELECT id
            FROM locations
            WHERE active IS TRUE
              AND code = :code
            LIMIT 1
            """
        ),
        {"code": code},
    ).scalar()


def upgrade() -> None:
    connection = op.get_bind()
    pompe_id = _location_id(connection, "POMPE")
    if pompe_id is None:
        return
    connection.execute(
        sa.text(
            """
            UPDATE typeform_form_configs
            SET default_location_id = :pompe_id,
                updated_at = now()
            WHERE source_code = :source_code
               OR typeform_form_id = :form_id
            """
        ),
        {
            "pompe_id": pompe_id,
            "source_code": TARGET_SOURCE_CODE,
            "form_id": TARGET_FORM_ID,
        },
    )


def downgrade() -> None:
    connection = op.get_bind()
    scheffer_id = _location_id(connection, "SCHEFFER")
    if scheffer_id is None:
        return
    connection.execute(
        sa.text(
            """
            UPDATE typeform_form_configs
            SET default_location_id = :scheffer_id,
                updated_at = now()
            WHERE source_code = :source_code
               OR typeform_form_id = :form_id
            """
        ),
        {
            "scheffer_id": scheffer_id,
            "source_code": TARGET_SOURCE_CODE,
            "form_id": TARGET_FORM_ID,
        },
    )
