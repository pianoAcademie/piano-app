"""Add location access instructions and complete the Pompe location.

Revision ID: 20260905_0245
Revises: 20260905_0244
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_0245"
down_revision: Union[str, None] = "20260905_0244"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("access_instructions", sa.Text(), nullable=True))
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE locations
            SET address_line = '19 rue de la Pompe',
                access_instructions = '1961A'
            WHERE code = 'POMPE'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("locations", "access_instructions")
