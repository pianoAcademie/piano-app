from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminTask(Base):
    __tablename__ = "admin_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('CLIENT_CALL','PROVIDER_CALL','SLOT_CHOICE','PROFESSOR_CONTACT','SHEET_MUSIC_DELIVERY')",
            name="ck_admin_tasks_type",
        ),
        CheckConstraint(
            "status IN ('CREATED','ASSIGNED','IN_PROGRESS','WAITING_CLIENT','COMPLETED','ARCHIVED')",
            name="ck_admin_tasks_status",
        ),
        Index("ix_admin_tasks_assignee_status", "assignee_user_id", "status"),
        Index("ix_admin_tasks_due_at", "due_at"),
        Index("ix_admin_tasks_client_id", "client_id"),
        Index("ix_admin_tasks_prospect_id", "prospect_id"),
        Index("ix_admin_tasks_intake_id", "intake_id"),
        Index("ix_admin_tasks_quote_id", "quote_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    task_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'CREATED'"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    prospect_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("prospects.id", ondelete="SET NULL"),
        nullable=True,
    )
    intake_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("typeform_intakes.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class AdminTaskComment(Base):
    __tablename__ = "admin_task_comments"
    __table_args__ = (
        Index("ix_admin_task_comments_task_created", "task_id", "created_at"),
        Index("ix_admin_task_comments_author_user_id", "author_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    task_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("admin_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
