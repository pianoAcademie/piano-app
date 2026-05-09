from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("typeform_intake_id", name="uq_referral_rewards_typeform_intake"),
        UniqueConstraint("quote_id", name="uq_referral_rewards_quote"),
        UniqueConstraint("credit_transaction_id", name="uq_referral_rewards_credit_transaction"),
        Index("ix_referral_rewards_status", "status"),
        Index("ix_referral_rewards_referrer_user_id", "referrer_user_id"),
        Index("ix_referral_rewards_referred_client_id", "referred_client_id"),
        Index("ix_referral_rewards_invoice_note_id", "trigger_invoice_note_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    typeform_intake_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("typeform_intakes.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    referred_client_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    referred_student_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    referrer_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    declared_referrer_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'DECLARED'"))
    match_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'UNMATCHED'"))
    match_confidence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    match_candidates_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    trigger_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, server_default=text("0.5000"))
    trigger_invoice_note_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_note_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    credit_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_manual_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    announcement_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credit_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credit_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
