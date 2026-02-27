"""add forfait plan kind and pack validity months

Revision ID: 20260227_0038
Revises: 20260226_0037
Create Date: 2026-02-27 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260227_0038"
down_revision: Union[str, None] = "20260226_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE plan_kind ADD VALUE IF NOT EXISTS 'FORFAIT'")

    op.add_column("plans", sa.Column("pack_validity_months", sa.Integer(), nullable=True))
    op.execute("UPDATE plans SET pack_validity_months = 12 WHERE kind = 'PACK' AND pack_validity_months IS NULL")

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


def downgrade() -> None:
    op.execute("UPDATE plans SET kind = 'SUBSCRIPTION' WHERE kind = 'FORFAIT'")

    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS ck_plans_kind_fields")
    op.execute(
        """
        ALTER TABLE plans
        ADD CONSTRAINT ck_plans_kind_fields
        CHECK (
            (kind = 'PACK' AND credits_count IS NOT NULL AND credits_count > 0)
            OR (kind = 'SUBSCRIPTION' AND monthly_price_excl_vat IS NOT NULL AND currency_code IS NOT NULL)
        )
        """
    )

    op.drop_column("plans", "pack_validity_months")
    # PostgreSQL enum value removal is not supported safely in-place.
