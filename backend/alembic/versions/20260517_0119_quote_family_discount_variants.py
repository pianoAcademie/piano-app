"""add family discount variants for quote management

Revision ID: 20260517_0119
Revises: 20260516_0118
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260517_0119"
down_revision: Union[str, None] = "20260516_0118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values
          ('REMISE_FAMILLE_EVEIL_MUSICAL', 'Remise famille - éveil musical', 2.00, 20.00, 'EUR', true, 21),
          ('REMISE_FAMILLE_ADOS', 'Remise famille - ados', 2.00, 20.00, 'EUR', true, 22)
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
    op.execute(
        """
        delete from quote_discount_rules
        where code in ('REMISE_FAMILLE_EVEIL_MUSICAL', 'REMISE_FAMILLE_ADOS')
        """
    )
