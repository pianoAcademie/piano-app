from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherMonthlyStatement(Base):
    __tablename__ = "teacher_monthly_statements"
    __table_args__ = (
        CheckConstraint("month >= 1 AND month <= 12", name="ck_teacher_monthly_statements_month_range"),
        UniqueConstraint(
            "teacher_id",
            "payor_legal_entity_id",
            "year",
            "month",
            name="uq_teacher_monthly_statements_teacher_payor_year_month",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    teacher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        nullable=False,
    )
    payor_legal_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'draft'"))
    attendance_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    totals_snapshot: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    dispute_message_last: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class TeacherInvoice(Base):
    __tablename__ = "teacher_invoices"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    teacher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    statement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_monthly_statements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payor_legal_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_vat_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    vat_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    totals_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    totals_vat: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    totals_ttc: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    recipient_company_name: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_company_address: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_company_siret: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_company_vat: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_siret_display: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_iban: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'generated'"))
    sent_to_accounting_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class TeacherInvoiceLine(Base):
    __tablename__ = "teacher_invoice_lines"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    course_type_label: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_rate_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    amount_ht: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    amount_ttc: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    meta: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TeacherStatementMessage(Base):
    __tablename__ = "teacher_statement_messages"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    statement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_monthly_statements.id", ondelete="CASCADE"),
        nullable=False,
    )
    teacher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TeacherInvoiceAuditEvent(Base):
    __tablename__ = "teacher_invoice_audit_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    teacher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="SET NULL"),
        nullable=True,
    )
    statement_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_monthly_statements.id", ondelete="SET NULL"),
        nullable=True,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("teacher_invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    html_template: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
