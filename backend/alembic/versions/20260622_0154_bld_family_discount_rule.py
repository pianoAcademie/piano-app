"""add Bar-le-Duc family discount rule

Revision ID: 20260622_0154
Revises: 20260615_0153
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260622_0154"
down_revision: Union[str, None] = "20260615_0153"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values ('REMISE_FAMILLE_BAR_LE_DUC', 'Remise famille - Bar-le-Duc', 2.00, 20.00, 'EUR', true, 23)
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
    op.execute("delete from quote_discount_rules where code = 'REMISE_FAMILLE_BAR_LE_DUC'")
