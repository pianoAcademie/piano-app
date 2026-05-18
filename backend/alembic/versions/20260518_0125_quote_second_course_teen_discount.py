"""add teen second course discount rule

Revision ID: 20260518_0125
Revises: 20260518_0124
Create Date: 2026-05-18 15:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260518_0125"
down_revision: Union[str, None] = "20260518_0124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values ('REMISE_DEUXIEME_COURS_ADOS', 'Remise 2e cours - ados', 2.00, 20.00, 'EUR', true, 31)
        on conflict (code) do update
        set label = excluded.label,
            unit_price_ttc = excluded.unit_price_ttc,
            vat_rate = excluded.vat_rate,
            currency = excluded.currency,
            is_active = excluded.is_active,
            sort_order = excluded.sort_order,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute("delete from quote_discount_rules where code = 'REMISE_DEUXIEME_COURS_ADOS'")
