from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SheetMusicPiece(Base):
    __tablename__ = "sheet_music_pieces"
    __table_args__ = (UniqueConstraint("product_id", "position", name="uq_sheet_music_piece_position"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog_products.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    video_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StudentSheetMusic(Base):
    __tablename__ = "student_sheet_music"
    __table_args__ = (
        CheckConstraint(
            "status IN ('STANDBY','TO_DELIVER','DELIVERED','IN_PROGRESS','COMPLETED')",
            name="ck_student_sheet_music_status",
        ),
        UniqueConstraint("source_quote_line_id", name="uq_student_sheet_music_source_quote_line"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    student_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("catalog_products.id", ondelete="SET NULL"), index=True
    )
    title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'STANDBY'"), index=True)
    current_piece_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sheet_music_pieces.id", ondelete="SET NULL")
    )
    source_quote_line_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quote_lines.id", ondelete="SET NULL")
    )
    internal_note: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class StudentSheetMusicEvent(Base):
    __tablename__ = "student_sheet_music_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    assignment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("student_sheet_music.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    piece_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sheet_music_pieces.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
