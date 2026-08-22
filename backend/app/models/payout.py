from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PayoutStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"


class SalaryPaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    CASH = "CASH"


class ProfessorHourlyRate(Base):
    __tablename__ = "professor_hourly_rates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    professor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    headcount_rules_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProfessorSessionPayout(Base):
    __tablename__ = "professor_session_payouts"
    __table_args__ = (
        UniqueConstraint("session_id", "professor_id", name="uq_professor_session_payout_session_professor"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    professor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    hourly_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payout_status: Mapped[PayoutStatus] = mapped_column(
        Enum(
            PayoutStatus,
            name="payout_status",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'PENDING'::payout_status"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProfessorSalaryPayment(Base):
    __tablename__ = "professor_salary_payments"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    professor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(120), nullable=False)
    payment_method: Mapped[SalaryPaymentMethod] = mapped_column(
        Enum(
            SalaryPaymentMethod,
            name="salary_payment_method",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
        server_default=text("'BANK_TRANSFER'::salary_payment_method"),
    )
    amount_excl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_incl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    settled_payout_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProfessorPayGridPeriod(Base):
    __tablename__ = "professor_pay_grid_periods"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
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


class ProfessorPayGridRule(Base):
    __tablename__ = "professor_pay_grid_rules"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professor_pay_grid_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'AUTRE'"))
    reference_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'EUR'"))
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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


class ProfessorPayGridBracket(Base):
    __tablename__ = "professor_pay_grid_brackets"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professor_pay_grid_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    min_students: Mapped[int] = mapped_column(Integer, nullable=False)
    max_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
