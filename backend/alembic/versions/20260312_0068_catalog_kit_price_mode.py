"""Add catalog kit pricing mode fields

Revision ID: 20260312_0068
Revises: 20260312_0067
Create Date: 2026-03-12 22:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260312_0068"
down_revision: Union[str, None] = "20260312_0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("catalog_kits", sa.Column("price_mode", sa.String(length=16), nullable=True))
    op.add_column("catalog_kits", sa.Column("forced_price", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "catalog_kits",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
    )

    op.execute(
        """
        UPDATE catalog_kits
        SET price_mode = 'forced',
            forced_price = price_incl_vat
        WHERE price_mode IS NULL
        """
    )

    op.alter_column(
        "catalog_kits",
        "price_mode",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default=sa.text("'calculated'"),
    )

    op.create_check_constraint(
        "ck_catalog_kits_price_mode",
        "catalog_kits",
        "price_mode IN ('calculated', 'forced')",
    )
    op.create_check_constraint(
        "ck_catalog_kits_forced_price_non_negative",
        "catalog_kits",
        "forced_price IS NULL OR forced_price >= 0",
    )
    op.create_check_constraint(
        "ck_catalog_kits_currency_len",
        "catalog_kits",
        "char_length(currency) = 3",
    )


def downgrade() -> None:
    op.drop_constraint("ck_catalog_kits_currency_len", "catalog_kits", type_="check")
    op.drop_constraint("ck_catalog_kits_forced_price_non_negative", "catalog_kits", type_="check")
    op.drop_constraint("ck_catalog_kits_price_mode", "catalog_kits", type_="check")
    op.drop_column("catalog_kits", "currency")
    op.drop_column("catalog_kits", "forced_price")
    op.drop_column("catalog_kits", "price_mode")
