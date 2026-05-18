"""clear draft quote expiration before first send

Revision ID: 20260518_0124
Revises: 20260518_0123
Create Date: 2026-05-18 14:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260518_0124"
down_revision: Union[str, None] = "20260518_0123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE quotes
            SET expires_at = NULL,
                updated_at = now()
            WHERE status = 'created'
              AND sent_at IS NULL
              AND expires_at IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    # The previous values depended on each quote creation date and cannot be
    # reconstructed reliably once corrected.
    pass
