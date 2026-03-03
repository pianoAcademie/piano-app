"""Add DOMICILE location for planning

Revision ID: 20260306_0054
Revises: 20260306_0053
Create Date: 2026-03-06 21:40:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260306_0054"
down_revision: Union[str, None] = "20260306_0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO locations (code, name, address_line, city, country_code, is_online, timezone, active)
        SELECT
            'DOMICILE',
            'Domicile',
            'A domicile',
            'Paris',
            'FR',
            false,
            'Europe/Paris',
            true
        WHERE NOT EXISTS (
            SELECT 1
            FROM locations
            WHERE upper(code) = 'DOMICILE'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM locations WHERE code = 'DOMICILE'")
