from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ProfessorContractLineMode(str, enum.Enum):
    PRESENTIEL = "PRESENTIEL"
    EN_LIGNE = "EN_LIGNE"
    AUTRE = "AUTRE"


class ProfessorContractGrid(Base):
    __tablename__ = "professor_contract_grids"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_professor_contract_grids_valid_range"),
    )

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
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    location_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class ProfessorContractGridLine(Base):
    __tablename__ = "professor_contract_grid_lines"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="ck_professor_contract_grid_lines_display_order_non_negative"),
        CheckConstraint(
            "reference_duration_minutes IS NULL OR reference_duration_minutes > 0",
            name="ck_professor_contract_grid_lines_duration_positive",
        ),
        CheckConstraint(
            "default_hourly_rate IS NULL OR default_hourly_rate >= 0",
            name="ck_professor_contract_grid_lines_default_rate_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    grid_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professor_contract_grids.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id"),
        nullable=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    service_type: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[ProfessorContractLineMode] = mapped_column(
        Enum(
            ProfessorContractLineMode,
            name="professor_contract_line_mode",
            native_enum=True,
            values_callable=_enum_values,
            validate_strings=True,
            create_type=False,
        ),
        nullable=False,
    )
    reference_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ProfessorContractGridLineRule(Base):
    __tablename__ = "professor_contract_grid_line_rules"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="ck_prof_contract_line_rules_disp_nonneg"),
        CheckConstraint("min_students >= 0", name="ck_professor_contract_grid_line_rules_min_non_negative"),
        CheckConstraint(
            "max_students IS NULL OR max_students >= min_students",
            name="ck_professor_contract_grid_line_rules_max_ge_min",
        ),
        CheckConstraint("hourly_rate >= 0", name="ck_professor_contract_grid_line_rules_rate_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professor_contract_grid_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    min_students: Mapped[int] = mapped_column(Integer, nullable=False)
    max_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
