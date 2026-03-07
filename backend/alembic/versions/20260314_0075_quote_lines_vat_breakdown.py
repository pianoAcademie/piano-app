"""add per-line VAT breakdown fields on quote_lines

Revision ID: 20260314_0075
Revises: 20260314_0074
Create Date: 2026-03-14 22:50:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260314_0075"
down_revision: Union[str, None] = "20260314_0074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_lines",
        sa.Column("vat_rate", sa.Numeric(6, 3), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "quote_lines",
        sa.Column("unit_price_ht", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "quote_lines",
        sa.Column("unit_vat_amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "quote_lines",
        sa.Column("amount_ht", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "quote_lines",
        sa.Column("amount_vat", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )

    op.execute(
        """
        UPDATE quote_lines
        SET
          amount_ht = amount_ttc,
          amount_vat = 0,
          unit_price_ht = unit_price_ttc,
          unit_vat_amount = 0,
          vat_rate = 0
        """
    )

    op.alter_column("quote_lines", "vat_rate", server_default=None)
    op.alter_column("quote_lines", "unit_price_ht", server_default=None)
    op.alter_column("quote_lines", "unit_vat_amount", server_default=None)
    op.alter_column("quote_lines", "amount_ht", server_default=None)
    op.alter_column("quote_lines", "amount_vat", server_default=None)


def downgrade() -> None:
    op.drop_column("quote_lines", "amount_vat")
    op.drop_column("quote_lines", "amount_ht")
    op.drop_column("quote_lines", "unit_vat_amount")
    op.drop_column("quote_lines", "unit_price_ht")
    op.drop_column("quote_lines", "vat_rate")
