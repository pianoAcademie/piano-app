from __future__ import annotations

from uuid import UUID
from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AnnualFamilyReference(Base):
    __tablename__ = "annual_family_references"
    guardian_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    child_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class AnnualStudentEnrollment(Base):
    """Administrative enrollment evidence, shared by the student's quotes for one season."""
    __tablename__ = "annual_student_enrollments"
    student_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
