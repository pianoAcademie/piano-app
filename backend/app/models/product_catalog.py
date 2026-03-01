from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ProductRequestSource(str, enum.Enum):
    ADMIN = "ADMIN"
    PROFESSOR = "PROFESSOR"


class ProductRequestStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    REJECTED = "REJECTED"
    INVOICE_TO_SEND = "INVOICE_TO_SEND"
    TO_DELIVER = "TO_DELIVER"
    DELIVERED = "DELIVERED"


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CatalogProduct(Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint("price_excl_vat >= 0", name="ck_catalog_products_price_excl_non_negative"),
        CheckConstraint("price_incl_vat >= 0", name="ck_catalog_products_price_incl_non_negative"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="ck_catalog_products_vat_rate_range"),
        CheckConstraint("stock_global_quantity >= 0", name="ck_catalog_products_global_stock_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    price_excl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    price_incl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, server_default=text("20"))
    stock_global_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    web_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchasable_online: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CatalogKit(Base):
    __tablename__ = "catalog_kits"
    __table_args__ = (
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100", name="ck_catalog_kits_vat_rate_range"),
        CheckConstraint("price_incl_vat >= 0", name="ck_catalog_kits_price_incl_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_incl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, server_default=text("20"))
    purchasable_online: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CatalogKitItem(Base):
    __tablename__ = "catalog_kit_items"
    __table_args__ = (
        UniqueConstraint("kit_id", "product_id", name="uq_catalog_kit_items_kit_product"),
        CheckConstraint("quantity > 0", name="ck_catalog_kit_items_quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    kit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_kits.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProductLocationStock(Base):
    __tablename__ = "product_location_stocks"
    __table_args__ = (
        UniqueConstraint("product_id", "location_id", name="uq_product_location_stocks_product_location"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    inventory_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    inventory_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    real_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    inventory_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    real_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    estimated_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProductRequest(Base):
    __tablename__ = "product_requests"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_product_requests_quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    student_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    location_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_source: Mapped[ProductRequestSource] = mapped_column(
        Enum(
            ProductRequestSource,
            name="product_request_source",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
    )
    status: Mapped[ProductRequestStatus] = mapped_column(
        Enum(
            ProductRequestStatus,
            name="product_request_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'PROCESSING'::product_request_status"),
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    admin_reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    admin_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    should_bill: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_manual_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivered_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivery_marked_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivery_marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
