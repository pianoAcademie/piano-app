from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PartitionMovement(Base):
    __tablename__ = "partition_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_partition_movement_quantity"),
        CheckConstraint("kind IN ('PICKUP','RETURN','DELIVERY')", name="ck_partition_movement_kind"),
        CheckConstraint("state IN ('PENDING','CONFIRMED','CANCELLED')", name="ck_partition_movement_state"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    professor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("professors.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("catalog_products.id"), index=True)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("locations.id"))
    assignment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("student_sheet_music.id"), unique=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
