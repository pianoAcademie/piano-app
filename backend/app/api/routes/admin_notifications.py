from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.notification_engine import ContactDeliveryIncident, ContactDeliveryStatus, JobRun, JobRunLog, Notification
from app.models.user import User, UserRole
from app.schemas.notifications import (
    ContactDeliveryReactivateRequest,
    ContactDeliveryStatusOut,
    NotificationIncidentOut,
    NotificationJobRelatedEntityOut,
    NotificationJobRunDetailOut,
    NotificationJobRunLogOut,
    NotificationJobRunOut,
    NotificationJobRunPageOut,
)
from app.services.contacts.delivery_status.service import reactivate_contact_channels

router = APIRouter(prefix="/admin/notifications")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _duration_seconds(started_at: datetime, finished_at: datetime | None) -> int | None:
    if finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds()))


def _to_job_run_out(row: JobRun) -> NotificationJobRunOut:
    return NotificationJobRunOut(
        id=row.id,
        job_name=row.job_name,
        triggered_by=row.triggered_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        duration_seconds=_duration_seconds(row.started_at, row.finished_at),
        items_scanned=int(row.items_scanned or 0),
        items_processed=int(row.items_processed or 0),
        items_sent=int(row.items_sent or 0),
        items_skipped=int(row.items_skipped or 0),
        items_failed=int(row.items_failed or 0),
        summary_text=row.summary_text,
        error_text=row.error_text,
    )


@router.get("/job-runs", response_model=NotificationJobRunPageOut)
def list_notification_job_runs(
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    job_name: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationJobRunPageOut:
    stmt = select(JobRun)
    if started_from is not None:
        stmt = stmt.where(JobRun.started_at >= started_from)
    if started_to is not None:
        stmt = stmt.where(JobRun.started_at <= started_to)
    if job_name:
        stmt = stmt.where(JobRun.job_name == job_name.strip())
    if status_filter:
        stmt = stmt.where(JobRun.status == status_filter.strip().lower())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                JobRun.summary_text.ilike(pattern),
                JobRun.error_text.ilike(pattern),
                JobRun.job_name.ilike(pattern),
            )
        )

    rows = db.scalars(stmt.order_by(JobRun.started_at.desc()).limit(limit)).all()
    return NotificationJobRunPageOut(
        items=[_to_job_run_out(row) for row in rows],
        total=len(rows),
    )


@router.get("/job-runs/{job_run_id}", response_model=NotificationJobRunDetailOut)
def get_notification_job_run_detail(
    job_run_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> NotificationJobRunDetailOut:
    run = db.scalar(select(JobRun).where(JobRun.id == job_run_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job run not found")

    logs = db.scalars(
        select(JobRunLog)
        .where(JobRunLog.job_run_id == job_run_id)
        .order_by(JobRunLog.created_at.asc())
        .limit(5000)
    ).all()
    notifications = db.scalars(
        select(Notification)
        .where(Notification.job_run_id == job_run_id)
        .order_by(Notification.updated_at.desc(), Notification.created_at.desc())
        .limit(5000)
    ).all()
    incidents = db.scalars(
        select(ContactDeliveryIncident)
        .where(ContactDeliveryIncident.notification_id.in_([row.id for row in notifications]))
        .order_by(ContactDeliveryIncident.detected_at.desc())
        .limit(5000)
    ).all() if notifications else []

    return NotificationJobRunDetailOut(
        run=_to_job_run_out(run),
        metadata_json=run.metadata_json or {},
        logs=[
            NotificationJobRunLogOut(
                id=row.id,
                level=row.level,
                message=row.message,
                context_json=row.context_json or {},
                created_at=row.created_at,
            )
            for row in logs
        ],
        notifications=[
            NotificationJobRelatedEntityOut(
                id=row.id,
                notification_type=row.notification_type,
                channel=row.channel,
                status=row.status,
                related_entity_type=row.related_entity_type,
                related_entity_id=row.related_entity_id,
                recipient_email=row.recipient_email,
                recipient_phone=row.recipient_phone,
                scheduled_for=row.scheduled_for,
                sent_at=row.sent_at,
                failed_at=row.failed_at,
                skipped_at=row.skipped_at,
                failure_reason=row.failure_reason,
            )
            for row in notifications
        ],
        incidents=[
            NotificationIncidentOut(
                id=row.id,
                contact_type=row.contact_type,
                contact_id=row.contact_id,
                channel=row.channel,
                incident_type=row.incident_type,
                severity=row.severity,
                provider_name=row.provider_name,
                provider_message_id=row.provider_message_id,
                detail_text=row.detail_text,
                notification_id=row.notification_id,
                detected_at=row.detected_at,
            )
            for row in incidents
        ],
    )


@router.get("/incidents", response_model=list[NotificationIncidentOut])
def list_delivery_incidents(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    channel: str | None = None,
    incident_type: str | None = None,
    contact_id: UUID | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[NotificationIncidentOut]:
    stmt = select(ContactDeliveryIncident)
    if from_ is not None:
        stmt = stmt.where(ContactDeliveryIncident.detected_at >= from_)
    if to is not None:
        stmt = stmt.where(ContactDeliveryIncident.detected_at <= to)
    if channel:
        stmt = stmt.where(ContactDeliveryIncident.channel == channel.strip().lower())
    if incident_type:
        stmt = stmt.where(ContactDeliveryIncident.incident_type == incident_type.strip().lower())
    if contact_id is not None:
        stmt = stmt.where(ContactDeliveryIncident.contact_id == contact_id)

    rows = db.scalars(stmt.order_by(ContactDeliveryIncident.detected_at.desc()).limit(limit)).all()
    return [
        NotificationIncidentOut(
            id=row.id,
            contact_type=row.contact_type,
            contact_id=row.contact_id,
            channel=row.channel,
            incident_type=row.incident_type,
            severity=row.severity,
            provider_name=row.provider_name,
            provider_message_id=row.provider_message_id,
            detail_text=row.detail_text,
            notification_id=row.notification_id,
            detected_at=row.detected_at,
        )
        for row in rows
    ]


@router.get("/contacts/{contact_type}/{contact_id}/status", response_model=ContactDeliveryStatusOut)
def get_contact_status(
    contact_type: str,
    contact_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ContactDeliveryStatusOut:
    row = db.scalar(
        select(ContactDeliveryStatus).where(
            ContactDeliveryStatus.contact_type == contact_type,
            ContactDeliveryStatus.contact_id == contact_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact delivery status not found")
    return ContactDeliveryStatusOut(
        contact_type=row.contact_type,
        contact_id=row.contact_id,
        email=row.email,
        email_status=row.email_status,
        email_suspended_at=row.email_suspended_at,
        email_suspension_reason=row.email_suspension_reason,
        phone=row.phone,
        phone_status=row.phone_status,
        phone_suspended_at=row.phone_suspended_at,
        phone_suspension_reason=row.phone_suspension_reason,
    )


@router.post("/contacts/{contact_type}/{contact_id}/reactivate", response_model=ContactDeliveryStatusOut)
def reactivate_contact_status(
    contact_type: str,
    contact_id: UUID,
    payload: ContactDeliveryReactivateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ContactDeliveryStatusOut:
    row = reactivate_contact_channels(
        db,
        contact_type=contact_type,
        contact_id=contact_id,
        reactivate_email=bool(payload.reactivate_email),
        reactivate_phone=bool(payload.reactivate_phone),
        now=_utcnow(),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact delivery status not found")
    db.commit()
    db.refresh(row)
    return ContactDeliveryStatusOut(
        contact_type=row.contact_type,
        contact_id=row.contact_id,
        email=row.email,
        email_status=row.email_status,
        email_suspended_at=row.email_suspended_at,
        email_suspension_reason=row.email_suspension_reason,
        phone=row.phone,
        phone_status=row.phone_status,
        phone_suspended_at=row.phone_suspended_at,
        phone_suspension_reason=row.phone_suspension_reason,
    )
