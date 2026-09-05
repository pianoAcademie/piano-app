from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.catalog import Booking, CourseSession, Professor
from app.models.product_catalog import CatalogProduct, ProductCategory
from app.models.repertoire import SheetMusicPiece, StudentSheetMusic, StudentSheetMusicEvent
from app.models.user import User, UserRole
from app.services.repertoire_progression import start_next_partition_after_completion

router = APIRouter()
STATUSES = {"STANDBY", "TO_DELIVER", "DELIVERED", "IN_PROGRESS", "COMPLETED"}


class PieceIn(BaseModel):
    id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    video_url: str | None = Field(default=None, max_length=2000)


class PieceOut(BaseModel):
    id: UUID
    title: str
    position: int
    video_url: str | None


class PartitionOut(BaseModel):
    product_id: UUID
    title: str
    pieces: list[PieceOut]


class AssignmentOut(BaseModel):
    id: UUID
    student_id: UUID
    product_id: UUID | None
    title: str
    status: str
    current_piece_id: UUID | None
    current_piece_title: str | None
    current_piece_video_url: str | None
    internal_note: str | None
    source: str
    pieces: list[PieceOut]
    updated_at: datetime


class AssignmentCreate(BaseModel):
    product_id: UUID
    status: str = "STANDBY"
    current_piece_id: UUID | None = None


class AssignmentUpdate(BaseModel):
    product_id: UUID | None = None
    status: str | None = None
    current_piece_id: UUID | None = None
    internal_note: str | None = Field(default=None, max_length=4000)


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


def _partition_product(db: Session, product_id: UUID) -> CatalogProduct | None:
    return next((product for product in _partition_products(db) if product.id == product_id), None)


def _pieces(db: Session, product_ids: list[UUID]) -> dict[UUID, list[SheetMusicPiece]]:
    rows = (
        db.scalars(
            select(SheetMusicPiece)
            .where(SheetMusicPiece.product_id.in_(product_ids), SheetMusicPiece.active.is_(True))
            .order_by(SheetMusicPiece.product_id, SheetMusicPiece.position)
        ).all()
        if product_ids
        else []
    )
    result: dict[UUID, list[SheetMusicPiece]] = {}
    for row in rows:
        result.setdefault(row.product_id, []).append(row)
    return result


def _piece_out(row: SheetMusicPiece) -> PieceOut:
    return PieceOut(id=row.id, title=row.title, position=row.position, video_url=row.video_url)


def _partition_out(db: Session, product: CatalogProduct) -> PartitionOut:
    pieces = _pieces(db, [product.id]).get(product.id, [])
    return PartitionOut(product_id=product.id, title=product.title, pieces=[_piece_out(piece) for piece in pieces])


def _assignment_out(db: Session, row: StudentSheetMusic) -> AssignmentOut:
    piece_rows = _pieces(db, [row.product_id]).get(row.product_id, []) if row.product_id else []
    current = next((piece for piece in piece_rows if piece.id == row.current_piece_id), None)
    return AssignmentOut(
        id=row.id,
        student_id=row.student_id,
        product_id=row.product_id,
        title=row.title_snapshot,
        status=row.status,
        current_piece_id=row.current_piece_id,
        current_piece_title=current.title if current else None,
        current_piece_video_url=current.video_url if current else None,
        internal_note=row.internal_note,
        source="DEVIS" if row.source_quote_line_id else "MANUEL",
        pieces=[_piece_out(piece) for piece in piece_rows],
        updated_at=row.updated_at,
    )


def _validated_piece_for_product(
    db: Session,
    *,
    product_id: UUID,
    piece_id: UUID | None,
) -> SheetMusicPiece | None:
    if piece_id is None:
        return None
    piece = db.get(SheetMusicPiece, piece_id)
    if piece is None or not piece.active or piece.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Morceau invalide pour cette partition",
        )
    return piece


@router.get("/repertoire/partitions", response_model=list[PartitionOut])
def list_partitions(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.PROF)),
) -> list[PartitionOut]:
    products = _partition_products(db)
    by_product = _pieces(db, [product.id for product in products])
    return [
        PartitionOut(
            product_id=product.id,
            title=product.title,
            pieces=[_piece_out(piece) for piece in by_product.get(product.id, [])],
        )
        for product in products
    ]


@router.put("/admin/repertoire/partitions/{product_id}/pieces", response_model=PartitionOut)
def replace_partition_pieces(
    product_id: UUID,
    payload: list[PieceIn],
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PartitionOut:
    product = _partition_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partition introuvable")

    rows = list(db.scalars(select(SheetMusicPiece).where(SheetMusicPiece.product_id == product_id)).all())
    existing = {row.id: row for row in rows}
    requested_ids = [item.id for item in payload if item.id is not None]
    if len(requested_ids) != len(set(requested_ids)) or any(piece_id not in existing for piece_id in requested_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Liste de morceaux invalide")

    for temporary_position, row in enumerate(rows, 1):
        row.position = -temporary_position
    db.flush()

    kept_ids: set[UUID] = set()
    for position, item in enumerate(payload, 1):
        row = existing.get(item.id) if item.id else None
        if row is None:
            row = SheetMusicPiece(product_id=product_id, title=item.title.strip(), position=position)
            db.add(row)
            db.flush()
        row.title = item.title.strip()
        row.position = position
        row.video_url = (item.video_url or "").strip() or None
        row.active = True
        row.updated_at = datetime.now(timezone.utc)
        kept_ids.add(row.id)

    inactive_position = len(payload)
    for row in rows:
        if row.id in kept_ids:
            continue
        inactive_position += 1
        row.position = inactive_position
        row.active = False
        row.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(product)
    return _partition_out(db, product)


@router.get("/admin/clients/{student_id}/repertoire", response_model=list[AssignmentOut])
def admin_student_repertoire(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients")),
) -> list[AssignmentOut]:
    rows = db.scalars(
        select(StudentSheetMusic)
        .where(StudentSheetMusic.student_id == student_id)
        .order_by(
            case(
                (StudentSheetMusic.status == "IN_PROGRESS", 0),
                (StudentSheetMusic.status == "TO_DELIVER", 1),
                (StudentSheetMusic.status == "DELIVERED", 2),
                (StudentSheetMusic.status == "STANDBY", 3),
                else_=4,
            ),
            StudentSheetMusic.created_at.desc(),
        )
    ).all()
    return [_assignment_out(db, row) for row in rows]


@router.post("/admin/clients/{student_id}/repertoire", response_model=AssignmentOut)
def admin_add_assignment(
    student_id: UUID,
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AssignmentOut:
    student = db.get(User, student_id)
    product = _partition_product(db, payload.product_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Élève introuvable")
    if product is None or payload.status not in STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Partition ou statut invalide")
    piece = _validated_piece_for_product(
        db,
        product_id=product.id,
        piece_id=payload.current_piece_id,
    )
    row = StudentSheetMusic(
        student_id=student_id,
        product_id=product.id,
        title_snapshot=product.title,
        status=payload.status,
        current_piece_id=piece.id if piece else None,
    )
    db.add(row)
    db.flush()
    db.add(
        StudentSheetMusicEvent(
            assignment_id=row.id,
            actor_user_id=actor.id,
            event_type="CREATED",
            new_status=row.status,
            piece_id=piece.id if piece else None,
        )
    )
    db.commit()
    db.refresh(row)
    return _assignment_out(db, row)


def _professor_can_edit(db: Session, professor: Professor, student_id: UUID) -> bool:
    return (
        db.scalar(
            select(Booking.id)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == student_id,
                or_(
                    CourseSession.professor_id == professor.id,
                    CourseSession.substitute_teacher_id == professor.id,
                ),
            )
            .limit(1)
        )
        is not None
    )


def _update_assignment(
    db: Session,
    row: StudentSheetMusic,
    payload: AssignmentUpdate,
    actor: User,
    *,
    allow_product_change: bool = False,
    distribution_professor_id: UUID | None = None,
) -> AssignmentOut:
    old_status = row.status
    correction_note: str | None = None
    product_changed = False
    if "product_id" in payload.model_fields_set:
        if not allow_product_change:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Correction réservée à l'administration")
        if payload.product_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Partition requise")
        product = _partition_product(db, payload.product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Partition invalide")
        if row.product_id != product.id:
            if row.delivered_at is not None:
                raise HTTPException(409, "Cette partition a déjà été remise. Ajoutez une nouvelle partition pour conserver l'historique.")
            previous_title = row.title_snapshot
            row.product_id = product.id
            row.title_snapshot = product.title
            row.current_piece_id = None
            product_changed = True
            correction_note = f"Correction de partition : {previous_title} → {product.title}"
    if payload.status is not None:
        if payload.status not in STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Statut invalide")
        row.status = payload.status

    if "current_piece_id" in payload.model_fields_set:
        if payload.current_piece_id is None:
            row.current_piece_id = None
        else:
            piece = db.get(SheetMusicPiece, payload.current_piece_id)
            if piece is None or piece.product_id != row.product_id or not piece.active:
                if product_changed:
                    row.current_piece_id = None
                    piece = None
                else:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Morceau incompatible avec la partition",
                    )
            if piece is not None:
                row.current_piece_id = piece.id

    if "internal_note" in payload.model_fields_set:
        row.internal_note = (payload.internal_note or "").strip() or None

    now = datetime.now(timezone.utc)
    if row.status in {"DELIVERED", "IN_PROGRESS"} and row.delivered_at is None:
        if old_status in {"STANDBY", "TO_DELIVER"}:
            from app.services.partition_distribution import consume_partition, delivery_professor
            professor_id = delivery_professor(db, row.student_id, distribution_professor_id)
            if professor_id is not None:
                consume_partition(db, row, professor_id, actor.id)
        row.delivered_at = now
    if row.status == "IN_PROGRESS" and row.started_at is None:
        row.started_at = now
    if row.status == "COMPLETED" and row.completed_at is None:
        row.completed_at = now
    row.updated_at = now
    if correction_note:
        db.add(
            StudentSheetMusicEvent(
                assignment_id=row.id,
                actor_user_id=actor.id,
                event_type="PARTITION_CORRECTED",
                old_status=old_status,
                new_status=row.status,
                note=correction_note,
            )
        )
    db.add(
        StudentSheetMusicEvent(
            assignment_id=row.id,
            actor_user_id=actor.id,
            event_type="UPDATED",
            old_status=old_status,
            new_status=row.status,
            piece_id=row.current_piece_id,
            note=row.internal_note,
        )
    )
    if old_status != "COMPLETED" and row.status == "COMPLETED":
        start_next_partition_after_completion(
            db,
            completed_assignment=row,
            actor_user_id=actor.id,
            now=now,
        )
    db.commit()
    db.refresh(row)
    return _assignment_out(db, row)


@router.patch("/admin/clients/{student_id}/repertoire/{assignment_id}", response_model=AssignmentOut)
def admin_update_assignment(
    student_id: UUID,
    assignment_id: UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AssignmentOut:
    row = db.scalar(select(StudentSheetMusic).where(StudentSheetMusic.id == assignment_id).with_for_update())
    if row is None or row.student_id != student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suivi introuvable")
    return _update_assignment(db, row, payload, actor, allow_product_change=True)


@router.patch("/professors/me/students/{student_id}/repertoire/{assignment_id}", response_model=AssignmentOut)
def professor_update_assignment(
    student_id: UUID,
    assignment_id: UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.PROF)),
) -> AssignmentOut:
    professor = db.scalar(select(Professor).where(func.lower(Professor.email) == actor.email.lower()))
    row = db.scalar(select(StudentSheetMusic).where(StudentSheetMusic.id == assignment_id).with_for_update())
    if (
        professor is None
        or row is None
        or row.student_id != student_id
        or not _professor_can_edit(db, professor, student_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé")
    return _update_assignment(db, row, payload, actor, allow_product_change=True, distribution_professor_id=professor.id)


@router.post("/professors/me/students/{student_id}/repertoire", response_model=AssignmentOut)
def professor_add_assignment(
    student_id: UUID,
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.PROF)),
) -> AssignmentOut:
    professor = db.scalar(select(Professor).where(func.lower(Professor.email) == actor.email.lower()))
    student = db.get(User, student_id)
    product = _partition_product(db, payload.product_id)
    if professor is None or student is None or not _professor_can_edit(db, professor, student_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé")
    if product is None or payload.status not in STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Partition ou statut invalide")
    piece = _validated_piece_for_product(
        db,
        product_id=product.id,
        piece_id=payload.current_piece_id,
    )
    row = StudentSheetMusic(
        student_id=student_id,
        product_id=product.id,
        title_snapshot=product.title,
        status=payload.status,
        current_piece_id=piece.id if piece else None,
    )
    db.add(row)
    db.flush()
    db.add(
        StudentSheetMusicEvent(
            assignment_id=row.id,
            actor_user_id=actor.id,
            event_type="CREATED",
            new_status=row.status,
            piece_id=piece.id if piece else None,
            note="Partition ajoutée depuis le suivi professeur",
        )
    )
    db.commit()
    db.refresh(row)
    return _assignment_out(db, row)
