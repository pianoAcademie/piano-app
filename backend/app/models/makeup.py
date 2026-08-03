from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class MakeupRequestStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    BOOKED = "BOOKED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class MakeupPassPurchase(Base):
    __tablename__ = "makeup_pass_purchases"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog_products.id", ondelete="RESTRICT"), nullable=False
    )
    forfait_subscription_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    manual_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("client_manual_transactions.id", ondelete="SET NULL"), nullable=True
    )
    purchased_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    source_quote_line_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quote_lines.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    credits_initial: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    price_incl_vat_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    currency_snapshot: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'EUR'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class MakeupRequest(Base):
    __tablename__ = "makeup_requests"
    __table_args__ = (
        UniqueConstraint("original_booking_id", name="uq_makeup_requests_original_booking"),
        UniqueConstraint("reserved_booking_id", name="uq_makeup_requests_reserved_booking"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, nullable=False, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_booking_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    forfait_subscription_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    reserved_booking_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    used_pass_purchase_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("makeup_pass_purchases.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[MakeupRequestStatus] = mapped_column(
        Enum(
            MakeupRequestStatus,
            name="makeup_request_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'PROPOSED'::makeup_request_status"),
    )
    force_without_pass: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    force_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
