"""Add product catalog, kits, stock and request workflow

Revision ID: 20260302_0044
Revises: 20260301_0043
Create Date: 2026-03-02 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260302_0044"
down_revision: Union[str, None] = "20260301_0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    product_request_source = postgresql.ENUM("ADMIN", "PROFESSOR", name="product_request_source")
    product_request_source.create(op.get_bind(), checkfirst=True)

    product_request_status = postgresql.ENUM(
        "PROCESSING",
        "REJECTED",
        "INVOICE_TO_SEND",
        "TO_DELIVER",
        "DELIVERED",
        name="product_request_status",
    )
    product_request_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "product_categories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_product_categories_name"),
    )

    op.create_table(
        "catalog_products",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("barcode", sa.String(length=120), nullable=True),
        sa.Column("price_excl_vat", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("price_incl_vat", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("vat_rate", sa.Numeric(6, 3), nullable=False, server_default=sa.text("20")),
        sa.Column("stock_global_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("web_link", sa.Text(), nullable=True),
        sa.Column("purchasable_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("price_excl_vat >= 0", name="ck_catalog_products_price_excl_non_negative"),
        sa.CheckConstraint("price_incl_vat >= 0", name="ck_catalog_products_price_incl_non_negative"),
        sa.CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="ck_catalog_products_vat_rate_range"),
        sa.CheckConstraint("stock_global_quantity >= 0", name="ck_catalog_products_global_stock_non_negative"),
        sa.UniqueConstraint("barcode", name="uq_catalog_products_barcode"),
    )

    op.create_table(
        "catalog_kits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("price_incl_vat", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("vat_rate", sa.Numeric(6, 3), nullable=False, server_default=sa.text("20")),
        sa.Column("purchasable_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="ck_catalog_kits_vat_rate_range"),
        sa.CheckConstraint("price_incl_vat >= 0", name="ck_catalog_kits_price_incl_non_negative"),
    )

    op.create_table(
        "catalog_kit_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "kit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_kits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_catalog_kit_items_quantity_positive"),
        sa.UniqueConstraint("kit_id", "product_id", name="uq_catalog_kit_items_kit_product"),
    )

    op.create_table(
        "product_location_stocks",
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
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("inventory_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("inventory_date", sa.Date(), nullable=True),
        sa.Column("real_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("inventory_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("real_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("estimated_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("product_id", "location_id", name="uq_product_location_stocks_product_location"),
    )

    op.create_table(
        "product_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "student_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "request_source",
            postgresql.ENUM("ADMIN", "PROFESSOR", name="product_request_source", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PROCESSING",
                "REJECTED",
                "INVOICE_TO_SEND",
                "TO_DELIVER",
                "DELIVERED",
                name="product_request_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'PROCESSING'::product_request_status"),
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "admin_reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("admin_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("should_bill", sa.Boolean(), nullable=True),
        sa.Column(
            "manual_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client_manual_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "delivered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "delivery_marked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivery_marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_product_requests_quantity_positive"),
    )

    op.create_index("ix_catalog_products_title", "catalog_products", ["title"], unique=False)
    op.create_index("ix_catalog_kits_title", "catalog_kits", ["title"], unique=False)
    op.create_index("ix_product_requests_status", "product_requests", ["status", "requested_at"], unique=False)
    op.create_index("ix_product_requests_student", "product_requests", ["student_user_id", "requested_at"], unique=False)

    op.execute(
        """
        INSERT INTO product_categories (name)
        VALUES
            ('Partitions'),
            ('Solfege'),
            ('Gestion'),
            ('Cours'),
            ('Concert'),
            ('Marketing')
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO locations (code, name, address_line, city, country_code, is_online, timezone)
        VALUES ('BAR_LE_DUC', 'Bar-le-Duc', 'Bar-le-Duc', 'Bar-le-Duc', 'FR', false, 'Europe/Paris')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_product_requests_student", table_name="product_requests")
    op.drop_index("ix_product_requests_status", table_name="product_requests")
    op.drop_index("ix_catalog_kits_title", table_name="catalog_kits")
    op.drop_index("ix_catalog_products_title", table_name="catalog_products")

    op.drop_table("product_requests")
    op.drop_table("product_location_stocks")
    op.drop_table("catalog_kit_items")
    op.drop_table("catalog_kits")
    op.drop_table("catalog_products")
    op.drop_table("product_categories")

    product_request_status = postgresql.ENUM(
        "PROCESSING",
        "REJECTED",
        "INVOICE_TO_SEND",
        "TO_DELIVER",
        "DELIVERED",
        name="product_request_status",
    )
    product_request_status.drop(op.get_bind(), checkfirst=True)

    product_request_source = postgresql.ENUM("ADMIN", "PROFESSOR", name="product_request_source")
    product_request_source.drop(op.get_bind(), checkfirst=True)
