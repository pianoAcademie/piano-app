"""add family second course discount rule

Revision ID: 20260525_0134
Revises: 20260523_0133
Create Date: 2026-05-25 13:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260525_0134"
down_revision: Union[str, None] = "20260523_0133"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values ('REMISE_FAMILLE_DEUXIEME_COURS', 'Remise famille - 2e cours', 3.00, 20.00, 'EUR', true, 32)
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
    op.execute("delete from quote_discount_rules where code = 'REMISE_FAMILLE_DEUXIEME_COURS'")
