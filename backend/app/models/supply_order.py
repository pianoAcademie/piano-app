from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductSupplyOrder(Base):
    __tablename__ = "product_supply_orders"
    __table_args__ = (
        CheckConstraint("status IN ('ORDERED', 'RECEIVED', 'CANCELLED')", name="ck_supply_order_status"),
        CheckConstraint("expected_delivery_date >= ordered_date", name="ck_supply_order_dates"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255))
    supplier: Mapped[str | None] = mapped_column(String(255))
    ordered_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ORDERED", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    received_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductSupplyOrderLine(Base):
    __tablename__ = "product_supply_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_supply_order_product"),
        CheckConstraint("quantity > 0 AND quantity <= 1000000", name="ck_supply_order_quantity"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("product_supply_orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("catalog_products.id", ondelete="RESTRICT"), nullable=True, index=True)
    product_title: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_movement_id: Mapped[UUID | None] = mapped_column(ForeignKey("stock_movements.id", ondelete="RESTRICT"), unique=True)
