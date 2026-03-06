"""Add catalog category and kit admin fields

Revision ID: 20260311_0064
Revises: 20260311_0063
Create Date: 2026-03-11 15:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0064"
down_revision: Union[str, None] = "20260311_0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_categories", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column(
        "product_categories",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_unique_constraint("uq_product_categories_code", "product_categories", ["code"])

    op.add_column("catalog_kits", sa.Column("code", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_catalog_kits_code", "catalog_kits", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_catalog_kits_code", "catalog_kits", type_="unique")
    op.drop_column("catalog_kits", "code")

    op.drop_constraint("uq_product_categories_code", "product_categories", type_="unique")
    op.drop_column("product_categories", "display_order")
    op.drop_column("product_categories", "code")
