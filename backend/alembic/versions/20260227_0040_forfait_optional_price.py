"""allow forfait formulas without monthly price

Revision ID: 20260227_0040
Revises: 20260227_0039
Create Date: 2026-02-27 15:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260227_0040"
down_revision: Union[str, None] = "20260227_0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS ck_plans_kind_fields")
    op.execute(
        """
        ALTER TABLE plans
        ADD CONSTRAINT ck_plans_kind_fields
        CHECK (
            (kind = 'PACK' AND credits_count IS NOT NULL AND credits_count > 0 AND pack_validity_months IS NOT NULL AND pack_validity_months BETWEEN 1 AND 12)
            OR (kind = 'SUBSCRIPTION' AND monthly_price_excl_vat IS NOT NULL AND currency_code IS NOT NULL)
            OR (kind <> 'PACK' AND kind <> 'SUBSCRIPTION')
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS ck_plans_kind_fields")
    op.execute(
        """
        ALTER TABLE plans
        ADD CONSTRAINT ck_plans_kind_fields
        CHECK (
            (kind = 'PACK' AND credits_count IS NOT NULL AND credits_count > 0 AND pack_validity_months IS NOT NULL AND pack_validity_months BETWEEN 1 AND 12)
            OR (kind <> 'PACK' AND monthly_price_excl_vat IS NOT NULL AND currency_code IS NOT NULL)
        )
        """
    )
