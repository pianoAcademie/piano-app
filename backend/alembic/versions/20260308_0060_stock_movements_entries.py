"""Add stock movements journal for stock entries and adjustments

Revision ID: 20260308_0060
Revises: 20260307_0059
Create Date: 2026-03-08 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260308_0060"
down_revision: Union[str, None] = "20260307_0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    stock_movement_type = postgresql.ENUM(
        "STOCK_IN",
        "ADJUSTMENT",
        name="stock_movement_type",
    )
    stock_movement_type.create(op.get_bind(), checkfirst=True)

    stock_movement_source_type = postgresql.ENUM(
        "purchase",
        "delivery",
        "correction",
        "return",
        "other",
        name="stock_movement_source_type",
    )
    stock_movement_source_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "stock_movements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "movement_type",
            postgresql.ENUM(
                "STOCK_IN",
                "ADJUSTMENT",
                name="stock_movement_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "source_type",
            postgresql.ENUM(
                "purchase",
                "delivery",
                "correction",
                "return",
                "other",
                name="stock_movement_source_type",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'other'::stock_movement_source_type"),
        ),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("attachment_key", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_non_zero"),
        sa.CheckConstraint(
            "(movement_type = 'STOCK_IN'::stock_movement_type AND quantity > 0) "
            "OR (movement_type = 'ADJUSTMENT'::stock_movement_type AND quantity <> 0)",
            name="ck_stock_movements_quantity_by_type",
        ),
    )
    op.create_index(
        "ix_stock_movements_product_location_occurred_at",
        "stock_movements",
        ["product_id", "location_id", "occurred_at"],
    )
    op.create_index(
        "ix_stock_movements_type_occurred_at",
        "stock_movements",
        ["movement_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_movements_type_occurred_at", table_name="stock_movements")
    op.drop_index("ix_stock_movements_product_location_occurred_at", table_name="stock_movements")
    op.drop_table("stock_movements")

    stock_movement_source_type = postgresql.ENUM(
        "purchase",
        "delivery",
        "correction",
        "return",
        "other",
        name="stock_movement_source_type",
    )
    stock_movement_source_type.drop(op.get_bind(), checkfirst=True)

    stock_movement_type = postgresql.ENUM(
        "STOCK_IN",
        "ADJUSTMENT",
        name="stock_movement_type",
    )
    stock_movement_type.drop(op.get_bind(), checkfirst=True)
