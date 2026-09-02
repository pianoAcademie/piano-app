from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product_catalog import CatalogProduct, ProductCategory
from app.models.repertoire import SheetMusicPiece, StudentSheetMusic, StudentSheetMusicEvent


def _fold(value: str | None) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", (value or "").casefold())
        if not unicodedata.combining(char)
    )


def partition_degree(title: str | None) -> int | None:
    """Return the degree encoded in a partition product title, if any."""
    match = re.search(r"\bdegre\s*(\d{1,2})\b", _fold(title))
    return int(match.group(1)) if match else None


def _partition_products(db: Session) -> list[CatalogProduct]:
    return list(
        db.scalars(
            select(CatalogProduct)
            .outerjoin(ProductCategory, ProductCategory.id == CatalogProduct.category_id)
            .where(
                CatalogProduct.active.is_(True),
                or_(
                    func.lower(CatalogProduct.title).contains("partition"),
                    func.lower(func.coalesce(ProductCategory.name, "")).contains("partition"),
                ),
            )
            .order_by(CatalogProduct.title)
        ).all()
    )


def previous_partition_product(db: Session, next_product: CatalogProduct) -> CatalogProduct | None:
    next_degree = partition_degree(next_product.title)
    if next_degree is None or next_degree <= 2:
        return None
    previous_degree = next_degree - 1
    matches = [product for product in _partition_products(db) if partition_degree(product.title) == previous_degree]
    return matches[0] if len(matches) == 1 else None


def first_active_piece(db: Session, product_id: UUID | None) -> SheetMusicPiece | None:
    if product_id is None:
        return None
    return db.scalar(
        select(SheetMusicPiece)
        .where(SheetMusicPiece.product_id == product_id, SheetMusicPiece.active.is_(True))
        .order_by(SheetMusicPiece.position, SheetMusicPiece.id)
        .limit(1)
    )


def ensure_previous_partition_for_reenrollment(
    db: Session,
    *,
    student_id: UUID,
    next_product: CatalogProduct,
    actor_user_id: UUID | None,
) -> StudentSheetMusic | None:
    """Create the previous degree as the current book for a returning student."""
    previous_product = previous_partition_product(db, next_product)
    if previous_product is None:
        return None

    existing = db.scalar(
        select(StudentSheetMusic)
        .where(
            StudentSheetMusic.student_id == student_id,
            StudentSheetMusic.product_id == previous_product.id,
        )
        .order_by(StudentSheetMusic.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc)
    assignment = StudentSheetMusic(
        student_id=student_id,
        product_id=previous_product.id,
        title_snapshot=previous_product.title,
        status="IN_PROGRESS",
        started_at=now,
    )
    db.add(assignment)
    db.flush()
    db.add(
        StudentSheetMusicEvent(
            assignment_id=assignment.id,
            actor_user_id=actor_user_id,
            event_type="CREATED_AS_PREVIOUS_PARTITION",
            new_status=assignment.status,
            note=f"Partition précédente de {next_product.title}",
        )
    )
    return assignment


def start_next_partition_after_completion(
    db: Session,
    *,
    completed_assignment: StudentSheetMusic,
    actor_user_id: UUID | None,
    now: datetime | None = None,
) -> StudentSheetMusic | None:
    """Start the pending quote partition at its first piece after the current book ends."""
    next_assignment = db.scalar(
        select(StudentSheetMusic)
        .where(
            StudentSheetMusic.student_id == completed_assignment.student_id,
            StudentSheetMusic.id != completed_assignment.id,
            StudentSheetMusic.source_quote_line_id.is_not(None),
            StudentSheetMusic.status.in_(("STANDBY", "TO_DELIVER", "DELIVERED")),
        )
        .order_by(StudentSheetMusic.created_at.desc(), StudentSheetMusic.id.desc())
        .limit(1)
    )
    if next_assignment is None:
        return None

    transition_at = now or datetime.now(timezone.utc)
    old_status = next_assignment.status
    first_piece = first_active_piece(db, next_assignment.product_id)
    next_assignment.status = "IN_PROGRESS"
    next_assignment.current_piece_id = first_piece.id if first_piece is not None else None
    if next_assignment.delivered_at is None:
        next_assignment.delivered_at = transition_at
    if next_assignment.started_at is None:
        next_assignment.started_at = transition_at
    next_assignment.updated_at = transition_at
    db.add(
        StudentSheetMusicEvent(
            assignment_id=next_assignment.id,
            actor_user_id=actor_user_id,
            event_type="AUTO_STARTED_AFTER_PREVIOUS_COMPLETED",
            old_status=old_status,
            new_status=next_assignment.status,
            piece_id=next_assignment.current_piece_id,
            note=f"Démarrage après validation de {completed_assignment.title_snapshot}",
        )
    )
    return next_assignment
