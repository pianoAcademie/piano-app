from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientNewsArticle(Base):
    __tablename__ = "client_news_articles"
    __table_args__ = (
        CheckConstraint("status in ('DRAFT', 'PUBLISHED')", name="ck_client_news_articles_status"),
        Index("ix_client_news_articles_publication", "status", "published_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    title_fr: Mapped[str] = mapped_column(String(220), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(220), nullable=True)
    summary_fr: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_fr: Mapped[str] = mapped_column(Text, nullable=False)
    body_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_label_fr: Mapped[str | None] = mapped_column(String(120), nullable=True)
    link_label_en: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    audience_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[\"ALL_CLIENTS\"]'::jsonb"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
