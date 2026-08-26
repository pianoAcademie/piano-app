from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


GIFT_CARD_STATUSES = (
    "CREATED",
    "ACTIVE",
    "REDEEMED",
    "EXPIRED",
    "CANCELLED",
    "REFUNDED",
    "BLOCKED",
)

GIFT_CARD_SOURCES = (
    "ADMIN",
    "APP",
    "PHYSICAL",
    "WORDPRESS",
    "MIGRATION",
)


class GiftCard(Base):
    __tablename__ = "gift_cards"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED','ACTIVE','REDEEMED','EXPIRED','CANCELLED','REFUNDED','BLOCKED')",
            name="ck_gift_cards_status",
        ),
        CheckConstraint(
            "source IN ('ADMIN','APP','PHYSICAL','WORDPRESS','MIGRATION')",
            name="ck_gift_cards_source",
        ),
        CheckConstraint("face_value_ttc >= 0", name="ck_gift_cards_face_value_non_negative"),
        CheckConstraint("purchase_price_ttc >= 0", name="ck_gift_cards_purchase_price_non_negative"),
        CheckConstraint("discount_ttc >= 0", name="ck_gift_cards_discount_non_negative"),
        CheckConstraint("vat_rate >= 0", name="ck_gift_cards_vat_rate_non_negative"),
        UniqueConstraint("code_hash", name="uq_gift_cards_code_hash"),
        UniqueConstraint("external_reference_key", name="uq_gift_cards_external_reference_key"),
        UniqueConstraint("subscription_id", name="uq_gift_cards_subscription_id"),
        Index("ix_gift_cards_status", "status"),
        Index("ix_gift_cards_code_suffix", "code_suffix"),
        Index("ix_gift_cards_plan_id", "plan_id"),
        Index("ix_gift_cards_redeemed_for_user_id", "redeemed_for_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_suffix: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'CREATED'"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ADMIN'"))
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_order_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_line_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_reference_key: Mapped[str | None] = mapped_column(String(280), nullable=True)
    purchaser_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchaser_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personal_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    face_value_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    purchase_price_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    discount_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    redeemed_for_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_plan_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    terms_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class GiftCardEvent(Base):
    __tablename__ = "gift_card_events"
    __table_args__ = (
        Index("ix_gift_card_events_gift_card_id", "gift_card_id"),
        Index("ix_gift_card_events_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    gift_card_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("gift_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status_before: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_after: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
