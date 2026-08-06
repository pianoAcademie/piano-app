from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import BOOKING_STATUSES_CONFIRMED, Booking, CourseSession
from app.models.notification_engine import MobilePushDevice
from app.models.user import User, UserRole
from app.schemas.notifications import (
    AdminMobilePushOut,
    AdminMobilePushRequest,
    AdminSessionMobilePushRequest,
    MobilePushDeviceDisableRequest,
    MobilePushDeviceOut,
    MobilePushDeviceRegisterRequest,
    MobilePushEventRequest,
)
from app.services.mobile_push import (
    disable_mobile_push_device,
    record_mobile_push_event,
    register_mobile_push_device,
    send_mobile_push_to_users,
)
from app.services.notifications.application.recipients import resolve_client_user_notification_recipient


router = APIRouter()


def _device_out(row: MobilePushDevice) -> MobilePushDeviceOut:
    return MobilePushDeviceOut(
        id=row.id,
        installation_id=row.installation_id,
        platform=row.platform,
        app_target=row.app_target,
        permission_status=row.permission_status,
        locale=row.locale,
        app_version=row.app_version,
        device_label=row.device_label,
        is_enabled=row.is_enabled,
        last_seen_at=row.last_seen_at,
    )


def _safe_deep_link(value: str | None, fallback: str) -> str:
    candidate = (value or "").strip()
    if candidate.startswith("/client"):
        return candidate
    return fallback


def _summary_out(summary) -> AdminMobilePushOut:
    return AdminMobilePushOut(
        requested_user_count=summary.requested_user_count,
        device_count=summary.device_count,
        sent_count=summary.sent_count,
        failed_count=summary.failed_count,
        skipped_count=summary.skipped_count,
        details=summary.details,
        job_run_id=summary.job_run_id,
    )


@router.get("/clients/me/push-devices", response_model=list[MobilePushDeviceOut])
def list_my_mobile_push_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[MobilePushDeviceOut]:
    rows = db.scalars(
        select(MobilePushDevice)
        .where(MobilePushDevice.user_id == current_user.id, MobilePushDevice.app_target == "CLIENT")
        .order_by(MobilePushDevice.last_seen_at.desc())
    ).all()
    return [_device_out(row) for row in rows]


@router.post("/clients/me/push-devices", response_model=MobilePushDeviceOut)
def register_my_mobile_push_device(
    payload: MobilePushDeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> MobilePushDeviceOut:
    if payload.app_target != "CLIENT":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Application mobile invalide")
    row = register_mobile_push_device(
        db,
        user=current_user,
        installation_id=payload.installation_id,
        push_token=payload.push_token,
        platform=payload.platform,
        app_target=payload.app_target,
        permission_status=payload.permission_status,
        locale=payload.locale or current_user.preferred_language,
        app_version=payload.app_version,
        device_label=payload.device_label,
    )
    return _device_out(row)


@router.delete("/clients/me/push-devices", status_code=status.HTTP_204_NO_CONTENT)
def disable_my_mobile_push_device(
    payload: MobilePushDeviceDisableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    disable_mobile_push_device(
        db,
        user_id=current_user.id,
        installation_id=payload.installation_id,
        app_target=payload.app_target,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/clients/me/push-notifications/{notification_id}/events", status_code=status.HTTP_204_NO_CONTENT)
def acknowledge_mobile_push_event(
    notification_id: UUID,
    payload: MobilePushEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    row = record_mobile_push_event(
        db,
        notification_id=notification_id,
        user_id=current_user.id,
        event=payload.event,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/clients/{client_id}/messages/push", response_model=AdminMobilePushOut)
def send_admin_client_mobile_push(
    client_id: UUID,
    payload: AdminMobilePushRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMobilePushOut:
    client = db.scalar(select(User).where(User.id == client_id, User.role == UserRole.CLIENT))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable")
    recipient = resolve_client_user_notification_recipient(db, user=client)
    recipient_ids = {recipient.contact_id} if recipient is not None and recipient.contact_id is not None else set()
    if not recipient_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Aucun compte adulte destinataire n'est rattache a ce client",
        )
    summary = send_mobile_push_to_users(
        db,
        user_ids=recipient_ids,
        title_fr=payload.title_fr,
        body_fr=payload.body_fr,
        title_en=payload.title_en,
        body_en=payload.body_en,
        deep_link=_safe_deep_link(payload.deep_link, "/client"),
        source="ADMIN_CLIENT_DIRECT_PUSH",
        related_entity_type="USER",
        related_entity_id=client.id,
        actor_id=actor.id,
    )
    return _summary_out(summary)


@router.post("/admin/sessions/{session_id}/push", response_model=AdminMobilePushOut)
def send_admin_session_mobile_push(
    session_id: UUID,
    payload: AdminSessionMobilePushRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminMobilePushOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id))
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creneau introuvable")

    stmt = (
        select(User)
        .join(Booking, Booking.user_id == User.id)
        .where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_CONFIRMED),
            User.role == UserRole.CLIENT,
        )
    )
    if payload.included_student_ids:
        stmt = stmt.where(User.id.in_(set(payload.included_student_ids)))
    students = db.scalars(stmt).all()
    if not students:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun participant selectionne")

    recipient_ids: set[UUID] = set()
    for student in students:
        recipient = resolve_client_user_notification_recipient(db, user=student)
        if recipient is not None and recipient.contact_id is not None:
            recipient_ids.add(recipient.contact_id)
    if not recipient_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Aucun compte adulte destinataire n'est rattache aux participants selectionnes",
        )

    summary = send_mobile_push_to_users(
        db,
        user_ids=recipient_ids,
        title_fr=payload.title_fr,
        body_fr=payload.body_fr,
        title_en=payload.title_en,
        body_en=payload.body_en,
        deep_link=_safe_deep_link(payload.deep_link, "/client?tab=planning"),
        source="ADMIN_SESSION_PUSH",
        related_entity_type="COURSE_SESSION",
        related_entity_id=session_obj.id,
        actor_id=actor.id,
        slot_id=session_obj.id,
    )
    return _summary_out(summary)
