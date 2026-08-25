from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_admin_permission_map, get_current_user, get_db
from app.models.admin_task import AdminTask
from app.models.quote import Prospect, Quote
from app.models.typeform_intake import TypeformIntake
from app.models.user import User, UserRole
from app.schemas.admin_task import (
    AdminTaskContactOut,
    AdminTaskCreateRequest,
    AdminTaskManagerOut,
    AdminTaskOptionsOut,
    AdminTaskOut,
    AdminTaskSourceOut,
    AdminTaskUpdateRequest,
)
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_frontend_base_url

router = APIRouter(prefix="/admin/tasks")

TASK_MANAGER_PERMISSION_KEYS = {
    "can_edit_planning",
    "can_view_planning_simulation",
    "can_manage_check_deposits",
    "can_view_clients",
    "can_access_collaborators",
    "can_view_intakes",
    "can_view_quotes",
    "can_manage_events",
    "can_manage_mobile_news",
    "can_manage_website_and_news",
    "can_manage_invoices_and_accounts",
}

TASK_TYPE_LABELS = {
    "CLIENT_CALL": "Appel client",
    "PROVIDER_CALL": "Appel prestataire",
    "SLOT_CHOICE": "Choix de créneau",
    "PROFESSOR_CONTACT": "Contact professeur",
    "SHEET_MUSIC_DELIVERY": "Remise de partition",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or (user.contact_email or user.email)


def _user_email(user: User) -> str:
    return (user.contact_email or user.email or "").strip()


def _has_task_manager_access(db: Session, user: User) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role != UserRole.PROF:
        return False
    permission_map = get_admin_permission_map(db, user)
    return any(bool(permission_map.get(key)) for key in TASK_MANAGER_PERMISSION_KEYS)


def require_task_manager(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not _has_task_manager_access(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès gestionnaire requis")
    return current_user


def _manager_users(db: Session) -> list[User]:
    users = list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.account_deleted_at.is_(None),
                User.role.in_([UserRole.ADMIN, UserRole.PROF]),
            )
            .order_by(func.lower(func.coalesce(User.first_name, "")), func.lower(func.coalesce(User.last_name, "")))
        ).all()
    )
    return [user for user in users if _has_task_manager_access(db, user)]


def _manager_out(user: User | None) -> AdminTaskManagerOut | None:
    if user is None:
        return None
    return AdminTaskManagerOut(id=user.id, name=_user_name(user), email=_user_email(user))


def _archive_old_completed_tasks(db: Session) -> None:
    cutoff = _utcnow() - timedelta(days=7)
    db.execute(
        update(AdminTask)
        .where(
            AdminTask.status == "COMPLETED",
            AdminTask.completed_at.is_not(None),
            AdminTask.completed_at <= cutoff,
        )
        .values(status="ARCHIVED", archived_at=_utcnow(), updated_at=_utcnow())
    )
    db.commit()


def _effective_status(task: AdminTask) -> str:
    if task.status in {"COMPLETED", "ARCHIVED"}:
        return task.status
    due_at = task.due_at
    if due_at is not None:
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        if due_at < _utcnow():
            return "OVERDUE"
    return task.status


def _contact_out(client: User | None, prospect: Prospect | None) -> AdminTaskContactOut | None:
    if client is not None:
        return AdminTaskContactOut(
            kind="CLIENT",
            id=client.id,
            name=_user_name(client),
            email=_user_email(client) or None,
            phone=client.mobile_phone_1 or client.phone or client.mobile_phone_2 or client.home_phone,
        )
    if prospect is not None:
        full_name = f"{(prospect.first_name or '').strip()} {(prospect.last_name or '').strip()}".strip()
        return AdminTaskContactOut(
            kind="PROSPECT",
            id=prospect.id,
            name=full_name or prospect.email,
            email=prospect.email,
            phone=prospect.phone,
            linked_client_id=prospect.linked_client_id,
        )
    return None


def _task_out(db: Session, task: AdminTask) -> AdminTaskOut:
    assignee = db.get(User, task.assignee_user_id) if task.assignee_user_id else None
    creator = db.get(User, task.created_by_user_id) if task.created_by_user_id else None
    client = db.get(User, task.client_id) if task.client_id else None
    prospect = db.get(Prospect, task.prospect_id) if task.prospect_id else None
    intake = db.get(TypeformIntake, task.intake_id) if task.intake_id else None
    quote = db.get(Quote, task.quote_id) if task.quote_id else None
    intake_label = None
    if intake is not None:
        intake_label = f"Questionnaire {intake.source_response_id}"
    quote_label = f"Devis {quote.quote_number}" if quote is not None else None
    return AdminTaskOut(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        effective_status=_effective_status(task),
        description=task.description,
        comment=task.comment,
        assignee=_manager_out(assignee),
        created_by=_manager_out(creator),
        contact=_contact_out(client, prospect),
        source=AdminTaskSourceOut(
            intake_id=task.intake_id,
            intake_label=intake_label,
            quote_id=task.quote_id,
            quote_label=quote_label,
        ),
        due_at=task.due_at,
        completed_at=task.completed_at,
        archived_at=task.archived_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _validate_assignee(db: Session, assignee_user_id: UUID | None) -> User | None:
    if assignee_user_id is None:
        return None
    assignee = db.get(User, assignee_user_id)
    if assignee is None or not assignee.is_active or not _has_task_manager_access(db, assignee):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Responsable invalide")
    return assignee


def _resolve_sources_and_contact(
    db: Session,
    *,
    intake_id: UUID | None,
    quote_id: UUID | None,
    client_id: UUID | None,
    prospect_id: UUID | None,
) -> tuple[UUID | None, UUID | None, UUID | None]:
    intake = db.get(TypeformIntake, intake_id) if intake_id else None
    if intake_id and intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire introuvable")
    if quote_id is None and intake is not None and intake.related_quote_id is not None:
        quote_id = intake.related_quote_id
    quote = db.get(Quote, quote_id) if quote_id else None
    if quote_id and quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devis introuvable")
    if client_id is None and prospect_id is None and quote is not None:
        client_id = quote.client_id
        prospect_id = None if client_id is not None else quote.prospect_id
    if client_id is not None:
        client = db.get(User, client_id)
        if client is None or client.role != UserRole.CLIENT:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Client invalide")
    if prospect_id is not None and db.get(Prospect, prospect_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Prospect invalide")
    return quote_id, client_id, prospect_id


def _send_assignment_email(db: Session, task: AdminTask, assignee: User, sender: User) -> None:
    to_email = _user_email(assignee)
    if not to_email:
        return
    task_url = f"{resolve_frontend_base_url(db).rstrip('/')}/admin/tasks/{task.id}"
    type_label = TASK_TYPE_LABELS.get(task.task_type, task.task_type)
    due_label = (
        task.due_at.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %H:%M")
        if task.due_at
        else "Non renseignée"
    )
    body = f"""
    <div style="font-family:Arial,sans-serif;color:#172033;max-width:680px;margin:0 auto">
      <div style="background:#172033;color:#fff;padding:24px 28px;border-radius:14px 14px 0 0">
        <div style="color:#f0bd58;font-weight:700;letter-spacing:.08em">PIANO ACADÉMIE</div>
        <h1 style="margin:10px 0 0;font-size:28px">Nouvelle tâche assignée</h1>
      </div>
      <div style="border:1px solid #ead8b7;border-top:0;padding:28px;border-radius:0 0 14px 14px">
        <p>Bonjour {escape(_user_name(assignee))},</p>
        <p>Une tâche administrative vous a été assignée par {escape(_user_name(sender))}.</p>
        <div style="background:#faf6ee;border:1px solid #ead8b7;border-radius:10px;padding:18px;margin:22px 0">
          <p style="margin:0 0 8px"><strong>Type :</strong> {escape(type_label)}</p>
          <p style="margin:0 0 8px"><strong>Échéance :</strong> {escape(due_label)}</p>
          <p style="margin:0"><strong>Description :</strong><br>{escape(task.description).replace(chr(10), '<br>')}</p>
        </div>
        <p style="margin:26px 0">
          <a href="{escape(task_url)}" style="background:#cf8124;color:#fff;text-decoration:none;padding:13px 20px;border-radius:8px;font-weight:700">Ouvrir la tâche</a>
        </p>
        <p>Bien cordialement,<br>Piano Académie</p>
      </div>
    </div>
    """
    send_email(
        to_email=to_email,
        subject=f"Piano Académie — Tâche assignée : {type_label}",
        body=body,
        body_format="HTML",
        context="ADMIN_TASK_ASSIGNED",
        sender_user_id=sender.id,
        sender_label=_user_name(sender),
        recipient_user_id=assignee.id,
        db=db,
        raise_on_failure=False,
    )


@router.get("/options", response_model=AdminTaskOptionsOut)
def task_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_task_manager),
) -> AdminTaskOptionsOut:
    return AdminTaskOptionsOut(
        managers=[manager for user in _manager_users(db) if (manager := _manager_out(user)) is not None],
        current_user_id=current_user.id,
    )


@router.get("/contacts", response_model=list[AdminTaskContactOut])
def search_task_contacts(
    q: str = Query(min_length=2, max_length=160),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_task_manager),
) -> list[AdminTaskContactOut]:
    pattern = f"%{q.strip()}%"
    clients = list(
        db.scalars(
            select(User)
            .where(
                User.role == UserRole.CLIENT,
                User.account_deleted_at.is_(None),
                or_(
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                    User.email.ilike(pattern),
                    User.contact_email.ilike(pattern),
                    User.phone.ilike(pattern),
                    User.mobile_phone_1.ilike(pattern),
                ),
            )
            .order_by(func.lower(func.coalesce(User.first_name, "")), func.lower(func.coalesce(User.last_name, "")))
            .limit(limit)
        ).all()
    )
    remaining = max(0, limit - len(clients))
    prospects = []
    if remaining:
        prospects = list(
            db.scalars(
                select(Prospect)
                .where(
                    or_(
                        Prospect.first_name.ilike(pattern),
                        Prospect.last_name.ilike(pattern),
                        Prospect.email.ilike(pattern),
                        Prospect.phone.ilike(pattern),
                    )
                )
                .order_by(func.lower(func.coalesce(Prospect.first_name, "")), func.lower(func.coalesce(Prospect.last_name, "")))
                .limit(remaining)
            ).all()
        )
    return [
        *[contact for client in clients if (contact := _contact_out(client, None)) is not None],
        *[contact for prospect in prospects if (contact := _contact_out(None, prospect)) is not None],
    ]


@router.get("", response_model=list[AdminTaskOut])
def list_tasks(
    mine: bool = False,
    assignee_user_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    include_archived: bool = False,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_task_manager),
) -> list[AdminTaskOut]:
    _archive_old_completed_tasks(db)
    stmt = select(AdminTask)
    if mine:
        stmt = stmt.where(AdminTask.assignee_user_id == current_user.id)
    elif assignee_user_id is not None:
        stmt = stmt.where(AdminTask.assignee_user_id == assignee_user_id)
    if status_filter:
        normalized_status = status_filter.strip().upper()
        if normalized_status == "OVERDUE":
            stmt = stmt.where(
                AdminTask.status.notin_(["COMPLETED", "ARCHIVED"]),
                AdminTask.due_at.is_not(None),
                AdminTask.due_at < _utcnow(),
            )
        else:
            stmt = stmt.where(AdminTask.status == normalized_status)
    if not include_archived:
        stmt = stmt.where(AdminTask.status != "ARCHIVED")
    rows = list(
        db.scalars(
            stmt.order_by(
                case((AdminTask.status.in_(["COMPLETED", "ARCHIVED"]), 1), else_=0),
                case((AdminTask.due_at.is_(None), 1), else_=0),
                AdminTask.due_at.asc(),
                AdminTask.created_at.desc(),
            ).limit(limit)
        ).all()
    )
    return [_task_out(db, row) for row in rows]


@router.post("", response_model=AdminTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: AdminTaskCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_task_manager),
) -> AdminTaskOut:
    assignee = _validate_assignee(db, payload.assignee_user_id)
    quote_id, client_id, prospect_id = _resolve_sources_and_contact(
        db,
        intake_id=payload.intake_id,
        quote_id=payload.quote_id,
        client_id=payload.client_id,
        prospect_id=payload.prospect_id,
    )
    task = AdminTask(
        task_type=payload.task_type,
        status="ASSIGNED" if assignee is not None else "CREATED",
        description=payload.description,
        comment=payload.comment,
        assignee_user_id=assignee.id if assignee else None,
        created_by_user_id=current_user.id,
        client_id=client_id,
        prospect_id=prospect_id,
        intake_id=payload.intake_id,
        quote_id=quote_id,
        due_at=payload.due_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if assignee is not None:
        _send_assignment_email(db, task, assignee, current_user)
    return _task_out(db, task)


@router.get("/{task_id}", response_model=AdminTaskOut)
def get_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_task_manager),
) -> AdminTaskOut:
    _archive_old_completed_tasks(db)
    task = db.get(AdminTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable")
    return _task_out(db, task)


@router.patch("/{task_id}", response_model=AdminTaskOut)
def update_task(
    task_id: UUID,
    payload: AdminTaskUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_task_manager),
) -> AdminTaskOut:
    task = db.get(AdminTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable")
    fields = payload.model_fields_set
    previous_assignee_id = task.assignee_user_id
    assignee: User | None = None
    if payload.clear_assignee:
        task.assignee_user_id = None
    elif "assignee_user_id" in fields:
        assignee = _validate_assignee(db, payload.assignee_user_id)
        task.assignee_user_id = assignee.id if assignee else None
    elif task.assignee_user_id:
        assignee = db.get(User, task.assignee_user_id)

    if payload.task_type is not None:
        task.task_type = payload.task_type
    if payload.description is not None:
        task.description = payload.description
    if "comment" in fields:
        task.comment = payload.comment
    if payload.clear_due_at:
        task.due_at = None
    elif "due_at" in fields:
        task.due_at = payload.due_at
    if payload.clear_contact:
        task.client_id = None
        task.prospect_id = None
    elif payload.client_id is not None or payload.prospect_id is not None:
        _, task.client_id, task.prospect_id = _resolve_sources_and_contact(
            db,
            intake_id=None,
            quote_id=None,
            client_id=payload.client_id,
            prospect_id=payload.prospect_id,
        )

    if payload.status is not None:
        task.status = payload.status
    elif task.assignee_user_id is not None and task.status == "CREATED":
        task.status = "ASSIGNED"
    elif task.assignee_user_id is None and task.status == "ASSIGNED":
        task.status = "CREATED"

    if task.status == "COMPLETED":
        task.completed_at = task.completed_at or _utcnow()
        task.archived_at = None
    elif task.status == "ARCHIVED":
        task.completed_at = task.completed_at or _utcnow()
        task.archived_at = task.archived_at or _utcnow()
    else:
        task.completed_at = None
        task.archived_at = None
    task.updated_at = _utcnow()
    db.commit()
    db.refresh(task)
    if task.assignee_user_id is not None and task.assignee_user_id != previous_assignee_id:
        assignee = db.get(User, task.assignee_user_id)
        if assignee is not None:
            _send_assignment_email(db, task, assignee, current_user)
    return _task_out(db, task)
