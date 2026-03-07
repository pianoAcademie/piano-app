from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Professor
from app.models.teacher_invoicing import TeacherStatementMessage
from app.models.user import User, UserRole
from app.schemas.admin_to_process import (
    AdminToProcessMessageOut,
    AdminToProcessStatus,
    AdminToProcessStatusUpdateOut,
    AdminToProcessStatusUpdateRequest,
)

router = APIRouter(prefix="/admin/to-process")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _teacher_name(professor: Professor | None) -> str | None:
    if professor is None:
        return None
    full_name = f"{(professor.first_name or '').strip()} {(professor.last_name or '').strip()}".strip()
    return full_name or (professor.email or None)


def _row_to_out(row: TeacherStatementMessage, professor: Professor | None) -> AdminToProcessMessageOut:
    normalized_status = str(row.status or "a_traiter").strip().lower()
    if normalized_status not in {"a_traiter", "en_cours", "termine"}:
        normalized_status = "a_traiter"
    return AdminToProcessMessageOut(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source=(row.source or "releves_professeur").strip() or "releves_professeur",
        message_type=(row.message_type or "erreur_releve").strip() or "erreur_releve",
        status=normalized_status,
        message_body=row.message,
        teacher_id=row.teacher_id,
        teacher_name=_teacher_name(professor),
        handled_by_user_id=row.handled_by_user_id,
        related_entity_type=row.related_entity_type,
        related_entity_id=row.related_entity_id,
        metadata=row.metadata or {},
    )


@router.get("/messages", response_model=list[AdminToProcessMessageOut])
def list_admin_to_process_messages(
    status_filter: AdminToProcessStatus | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None, max_length=120),
    message_type: str | None = Query(default=None, max_length=120),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminToProcessMessageOut]:
    stmt = select(TeacherStatementMessage, Professor).outerjoin(Professor, Professor.id == TeacherStatementMessage.teacher_id)

    if status_filter is not None:
        stmt = stmt.where(TeacherStatementMessage.status == status_filter)
    if source:
        stmt = stmt.where(TeacherStatementMessage.source == source.strip())
    if message_type:
        stmt = stmt.where(TeacherStatementMessage.message_type == message_type.strip())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                TeacherStatementMessage.message.ilike(pattern),
                TeacherStatementMessage.source.ilike(pattern),
                TeacherStatementMessage.message_type.ilike(pattern),
                Professor.first_name.ilike(pattern),
                Professor.last_name.ilike(pattern),
                Professor.email.ilike(pattern),
            )
        )

    rows = db.execute(stmt.order_by(TeacherStatementMessage.created_at.desc()).limit(limit)).all()
    return [_row_to_out(row, professor) for row, professor in rows]


@router.get("/messages/{message_id}", response_model=AdminToProcessMessageOut)
def get_admin_to_process_message(
    message_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminToProcessMessageOut:
    row = db.execute(
        select(TeacherStatementMessage, Professor)
        .outerjoin(Professor, Professor.id == TeacherStatementMessage.teacher_id)
        .where(TeacherStatementMessage.id == message_id)
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")
    message, professor = row
    return _row_to_out(message, professor)


@router.patch("/messages/{message_id}/status", response_model=AdminToProcessStatusUpdateOut)
def update_admin_to_process_message_status(
    message_id: UUID,
    payload: AdminToProcessStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminToProcessStatusUpdateOut:
    row = db.scalar(select(TeacherStatementMessage).where(TeacherStatementMessage.id == message_id).limit(1))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")

    row.status = payload.status
    row.handled_by_user_id = current_user.id
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()

    return AdminToProcessStatusUpdateOut(id=row.id, status=payload.status, updated_at=row.updated_at)
