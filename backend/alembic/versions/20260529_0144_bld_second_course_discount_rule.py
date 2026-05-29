"""add Bar-le-Duc second course discount rule

Revision ID: 20260529_0144
Revises: 20260529_0143
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0144"
down_revision = "20260529_0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values ('REMISE_DEUXIEME_COURS_BAR_LE_DUC', 'Remise 2e cours - Bar-le-Duc', 2.00, 20.00, 'EUR', true, 33)
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
    op.execute("delete from quote_discount_rules where code = 'REMISE_DEUXIEME_COURS_BAR_LE_DUC'")
