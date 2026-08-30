from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Professor
from app.models.ops import CommunicationSenderCategory
from app.models.teacher_invoicing import (
    TeacherInvoiceAuditEvent,
    TeacherMonthlyStatement,
    TeacherStatementMessage,
)
from app.models.user import User, UserRole
from app.schemas.admin_to_process import (
    AdminToProcessMessageOut,
    AdminToProcessMissingServiceResolveOut,
    AdminToProcessStatus,
    AdminToProcessStatusUpdateOut,
    AdminToProcessStatusUpdateRequest,
)
from app.services.email_delivery import EmailDeliveryError, send_email
from app.services.messaging_templates import resolve_sender_profile
from app.services.teacher_invoicing import (
    ComputedStatement,
    compute_teacher_monthly_statements,
    statement_to_snapshot_payload,
)
from app.services.teacher_statement_notifications import (
    build_missing_service_resolved_email,
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
        metadata=row.meta or {},
    )


def _missing_service_period(row: TeacherStatementMessage) -> tuple[int, int, date]:
    metadata = row.meta or {}
    try:
        year = int(metadata.get("year") or 0)
        month = int(metadata.get("month") or 0)
        service_date = date.fromisoformat(str(metadata.get("service_date") or ""))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Le signalement ne contient pas une période exploitable.",
        ) from exc
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La période du signalement est invalide.")
    return year, month, service_date


def _statement_session_candidates(
    statements: list[ComputedStatement],
    *,
    service_date: date,
    location_name: str | None,
    course_type_id: str | None,
) -> list[tuple[ComputedStatement, dict[str, Any]]]:
    same_date: list[tuple[ComputedStatement, dict[str, Any], str | None]] = []
    normalized_location = (location_name or "").strip().casefold()
    normalized_course_type_id = (course_type_id or "").strip()
    for statement in statements:
        for line in statement.lines:
            session_items = line.meta.get("session_items") if isinstance(line.meta, dict) else None
            if not isinstance(session_items, list):
                continue
            for raw_item in session_items:
                if not isinstance(raw_item, dict) or str(raw_item.get("date") or "") != service_date.isoformat():
                    continue
                item = dict(raw_item)
                item_location = str(item.get("location_name") or "").strip().casefold()
                if normalized_location and item_location != normalized_location:
                    continue
                same_date.append(
                    (statement, item, str(line.course_type_id) if line.course_type_id is not None else None)
                )
    exact_course_type = [
        (statement, item)
        for statement, item, item_course_type_id in same_date
        if normalized_course_type_id and item_course_type_id == normalized_course_type_id
    ]
    if exact_course_type:
        return exact_course_type
    return [(statement, item) for statement, item, _ in same_date]


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
    for search_token in [token for token in (q or "").strip().split() if token]:
        pattern = f"%{search_token}%"
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


@router.post(
    "/messages/{message_id}/resolve-missing-service",
    response_model=AdminToProcessMissingServiceResolveOut,
)
def resolve_admin_missing_service_message(
    message_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminToProcessMissingServiceResolveOut:
    row = db.scalar(
        select(TeacherStatementMessage)
        .where(TeacherStatementMessage.id == message_id)
        .with_for_update()
        .limit(1)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")
    if row.message_type != "prestation_manquante":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette action est réservée aux signalements de prestation manquante.",
        )
    if row.status == "termine":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce signalement a déjà été résolu.")

    year, month, service_date = _missing_service_period(row)
    professor = db.scalar(select(Professor).where(Professor.id == row.teacher_id).limit(1))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professeur introuvable")

    computed_rows = compute_teacher_monthly_statements(db, professor=professor, year=year, month=month)
    if not computed_rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune prestation ne figure encore dans le relevé de cette période.",
        )
    metadata = row.meta or {}
    candidates = _statement_session_candidates(
        computed_rows,
        service_date=service_date,
        location_name=str(metadata.get("location_name") or "") or None,
        course_type_id=str(metadata.get("course_type_id") or "") or None,
    )
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La correction ne peut pas être validée : aucune prestation correspondant à la date "
                "et au lieu signalés n'apparaît dans le relevé recalculé."
            ),
        )
    if len(candidates) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Plusieurs prestations correspondent au signalement. Vérifiez le type de cours avant de valider."
            ),
        )

    now = _utcnow()
    existing_statements = db.scalars(
        select(TeacherMonthlyStatement).where(
            TeacherMonthlyStatement.teacher_id == professor.id,
            TeacherMonthlyStatement.year == year,
            TeacherMonthlyStatement.month == month,
        )
    ).all()
    existing_by_payor = {statement.payor_legal_entity_id: statement for statement in existing_statements}
    statement_ids: list[UUID] = []
    for computed in computed_rows:
        statement = existing_by_payor.get(computed.payor_legal_entity_id)
        if statement is None:
            statement = TeacherMonthlyStatement(
                teacher_id=professor.id,
                payor_legal_entity_id=computed.payor_legal_entity_id,
                year=year,
                month=month,
            )
        statement.status = "to_verify" if computed.attendance_complete else "awaiting_attendance"
        statement.attendance_complete = computed.attendance_complete
        statement.totals_snapshot = statement_to_snapshot_payload(computed)
        statement.dispute_message_last = None
        statement.updated_at = now
        db.add(statement)
        db.flush()
        existing_by_payor[computed.payor_legal_entity_id] = statement
        statement_ids.append(statement.id)

    sibling_rows = db.scalars(
        select(TeacherStatementMessage).where(
            TeacherStatementMessage.teacher_id == professor.id,
            TeacherStatementMessage.message_type == "prestation_manquante",
            TeacherStatementMessage.status != "termine",
        )
    ).all()
    resolved_messages = []
    for sibling in sibling_rows:
        sibling_meta = sibling.meta or {}
        if (
            str(sibling_meta.get("year") or "") == str(year)
            and str(sibling_meta.get("month") or "") == str(month)
            and str(sibling_meta.get("service_date") or "") == service_date.isoformat()
        ):
            resolved_messages.append(sibling)
    if row not in resolved_messages:
        resolved_messages.append(row)

    matched_statement, matched_session = candidates[0]
    subject, body = build_missing_service_resolved_email(
        db,
        professor=professor,
        statements=computed_rows,
        matched_session=matched_session,
        year=year,
        month=month,
        attendee_count=int(metadata.get("attendee_count") or 0),
        language="fr",
    )
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    try:
        provider_message_id = send_email(
            to_email=professor.email,
            subject=subject,
            body=body,
            body_format="HTML",
            context="TEACHER_MISSING_SERVICE_RESOLVED",
            from_email=sender.from_email,
            from_name=sender.from_name,
            reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix,
            sender_user_id=current_user.id,
            sender_label=(current_user.email or "Administration"),
            sender_category=CommunicationSenderCategory.OTHER_USER,
            professor_id=professor.id,
            raise_on_failure=True,
            db=db,
        )
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La correction n'a pas été clôturée car l'e-mail au professeur n'a pas pu être envoyé.",
        ) from exc

    matched_session_ids = [UUID(str(matched_session["session_id"]))]
    resolution_meta = {
        "resolved_at": now.isoformat(),
        "resolved_by_user_id": str(current_user.id),
        "matched_session_ids": [str(value) for value in matched_session_ids],
        "statement_ids": [str(value) for value in statement_ids],
        "provider_message_id": provider_message_id,
    }
    for resolved_message in resolved_messages:
        resolved_message.status = "termine"
        resolved_message.handled_by_user_id = current_user.id
        resolved_message.updated_at = now
        resolved_message.meta = {**(resolved_message.meta or {}), **resolution_meta}
        db.add(resolved_message)

    db.add(
        TeacherInvoiceAuditEvent(
            event_type="teacher_statement_missing_service_resolved",
            teacher_id=professor.id,
            statement_id=existing_by_payor[matched_statement.payor_legal_entity_id].id,
            actor_user_id=current_user.id,
            payload={
                "period": f"{year:04d}-{month:02d}",
                "message_id": str(row.id),
                **resolution_meta,
            },
        )
    )
    db.commit()

    total_ht = sum((statement.totals_ht for statement in computed_rows), Decimal("0.00"))
    return AdminToProcessMissingServiceResolveOut(
        id=row.id,
        status="termine",
        updated_at=row.updated_at,
        statement_ids=statement_ids,
        matched_session_ids=matched_session_ids,
        statement_total_ht=f"{total_ht.quantize(Decimal('0.01'))}",
        currency=computed_rows[0].currency,
        teacher_notified=True,
    )
