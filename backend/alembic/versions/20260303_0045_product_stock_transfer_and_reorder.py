"""Add product reorder fields and stock transfer workflow

Revision ID: 20260303_0045
Revises: 20260302_0044
Create Date: 2026-03-03 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260303_0045"
down_revision: Union[str, None] = "20260302_0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    product_reorder_status = postgresql.ENUM(
        "NORMAL",
        "TO_ORDER",
        "ORDERED",
        "RECEIVED",
        name="product_reorder_status",
    )
    product_reorder_status.create(op.get_bind(), checkfirst=True)

    product_transfer_status = postgresql.ENUM(
        "PENDING",
        "DONE",
        "CANCELLED",
        name="product_transfer_status",
    )
    product_transfer_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "catalog_products",
        sa.Column("primary_location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "catalog_products",
        sa.Column("reserve_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "catalog_products",
        sa.Column(
            "reorder_status",
            postgresql.ENUM("NORMAL", "TO_ORDER", "ORDERED", "RECEIVED", name="product_reorder_status", create_type=False),
            nullable=False,
            server_default=sa.text("'NORMAL'::product_reorder_status"),
        ),
    )
    op.add_column(
        "catalog_products",
        sa.Column("reorder_status_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_foreign_key(
        "fk_catalog_products_primary_location_id",
        "catalog_products",
        "locations",
        ["primary_location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_catalog_products_reserve_stock_non_negative",
        "catalog_products",
        "reserve_stock >= 0",
    )

    op.create_table(
        "product_stock_transfers",
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
            "source_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("planned_transfer_date", sa.Date(), nullable=True),
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "DONE", "CANCELLED", name="product_transfer_status", create_type=False),
            nullable=False,
            server_default=sa.text("'PENDING'::product_transfer_status"),
        ),
        sa.Column(
            "completed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_transfer_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_product_stock_transfers_quantity_positive"),
        sa.CheckConstraint("source_location_id <> target_location_id", name="ck_product_stock_transfers_distinct_locations"),
    )

    op.execute(
        """
        UPDATE catalog_products p
        SET stock_global_quantity = COALESCE(s.total_real, 0)
        FROM (
            SELECT product_id, SUM(real_quantity)::integer AS total_real
            FROM product_location_stocks
            GROUP BY product_id
        ) s
        WHERE p.id = s.product_id
        """
    )
    op.execute(
        """
        UPDATE catalog_products
        SET stock_global_quantity = 0
        WHERE id NOT IN (SELECT DISTINCT product_id FROM product_location_stocks)
        """
    )
    op.execute(
        """
        UPDATE catalog_products
        SET reorder_status = CASE
            WHEN stock_global_quantity < reserve_stock THEN 'TO_ORDER'::product_reorder_status
            ELSE 'NORMAL'::product_reorder_status
        END,
        reorder_status_updated_at = now()
        """
    )


def downgrade() -> None:
    op.drop_table("product_stock_transfers")

    op.drop_constraint("ck_catalog_products_reserve_stock_non_negative", "catalog_products", type_="check")
    op.drop_constraint("fk_catalog_products_primary_location_id", "catalog_products", type_="foreignkey")
    op.drop_column("catalog_products", "reorder_status_updated_at")
    op.drop_column("catalog_products", "reorder_status")
    op.drop_column("catalog_products", "reserve_stock")
    op.drop_column("catalog_products", "primary_location_id")

    product_transfer_status = postgresql.ENUM("PENDING", "DONE", "CANCELLED", name="product_transfer_status")
    product_transfer_status.drop(op.get_bind(), checkfirst=True)

    product_reorder_status = postgresql.ENUM("NORMAL", "TO_ORDER", "ORDERED", "RECEIVED", name="product_reorder_status")
    product_reorder_status.drop(op.get_bind(), checkfirst=True)
