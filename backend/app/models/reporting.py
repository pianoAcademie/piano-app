from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    report_type: Mapped[str] = mapped_column(String(80), nullable=False)
    report_label: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PDF'"))
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    criteria_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    content_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
