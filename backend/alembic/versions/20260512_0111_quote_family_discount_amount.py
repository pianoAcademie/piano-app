"""Set family discount rule amount to 4 euros TTC.

Revision ID: 20260512_0111
Revises: 20260512_0110
Create Date: 2026-05-12 13:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260512_0111"
down_revision = "20260512_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        update quote_discount_rules
        set unit_price_ttc = 4.00,
            updated_at = now()
        where code = 'REMISE_FAMILLE'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        update quote_discount_rules
        set unit_price_ttc = 2.00,
            updated_at = now()
        where code = 'REMISE_FAMILLE'
        """
    )
