"""add product nature for quote rendering

Revision ID: 20260430_0104
Revises: 20260430_0103
Create Date: 2026-04-30 18:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260430_0104"
down_revision: Union[str, None] = "20260430_0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catalog_products",
        sa.Column("nature", sa.String(length=20), nullable=False, server_default=sa.text("'material'")),
    )
    op.create_check_constraint(
        "ck_catalog_products_nature",
        "catalog_products",
        "nature IN ('material', 'service')",
    )
    op.execute(
        sa.text(
            """
            UPDATE catalog_products
            SET nature = 'service'
            WHERE regexp_replace(
                lower(
                    concat_ws(
                        ' ',
                        coalesce(title, ''),
                        coalesce(barcode, ''),
                        coalesce(short_description, ''),
                        coalesce(long_description, '')
                    )
                ),
                '[^a-z0-9]+',
                '',
                'g'
            ) LIKE '%passrecup%'
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("ck_catalog_products_nature", "catalog_products", type_="check")
    op.drop_column("catalog_products", "nature")
