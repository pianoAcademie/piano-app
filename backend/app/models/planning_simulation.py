from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanningSimulationTeacherAssignment(Base):
    __tablename__ = "planning_simulation_teacher_assignments"
    __table_args__ = (
        UniqueConstraint(
            "school_year_label",
            "slot_key",
            "position",
            name="uq_planning_simulation_teacher_assignment_slot_position",
        ),
        CheckConstraint(
            "status IN ('PREVISIONAL', 'CONFIRMED')",
            name="ck_planning_simulation_teacher_assignment_status",
        ),
        CheckConstraint("position >= 1 AND position <= 4", name="ck_planning_simulation_teacher_assignment_position"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    school_year_label: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    slot_key: Mapped[str] = mapped_column(String(600), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    professor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    teacher_label: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PREVISIONAL'"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
