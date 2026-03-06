from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.notification_engine import (
    AdminNotificationSetting,
    ContactDeliveryIncident,
    ContactDeliveryStatus,
    DomainEvent,
    JobCursor,
    JobRun,
    JobRunLog,
    Notification,
    NotificationRule,
)
from app.services.notifications.domain.constants import NOTIFICATION_STATUS_PENDING


def create_domain_event(
    db: Session,
    *,
    event_type: str,
    source: str,
    actor_type: str | None,
    actor_id: UUID | None,
    related_entity_type: str,
    related_entity_id: UUID,
    occurred_at: datetime,
    payload_json: dict[str, Any],
) -> DomainEvent:
    event = DomainEvent(
        event_type=event_type,
        source=source,
        actor_type=actor_type,
        actor_id=actor_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        occurred_at=occurred_at,
        payload_json=payload_json,
    )
    db.add(event)
    db.flush()
    return event


def create_notification_if_new(
    db: Session,
    *,
    notification_type: str,
    channel: str,
    dispatch_mode: str,
    source_event_id: UUID | None,
    source: str,
    related_entity_type: str,
    related_entity_id: UUID,
    booking_id: UUID | None,
    slot_id: UUID | None,
    recipient_type: str,
    recipient_contact_id: UUID | None,
    recipient_email: str | None,
    recipient_phone: str | None,
    subject: str | None,
    body_snapshot: str | None,
    payload_snapshot: dict[str, Any],
    idempotency_key: str,
    scheduled_for: datetime,
    status: str = NOTIFICATION_STATUS_PENDING,
    failure_reason: str | None = None,
) -> Notification | None:
    with db.begin_nested():
        notification = Notification(
            notification_type=notification_type,
            channel=channel,
            dispatch_mode=dispatch_mode,
            source_event_id=source_event_id,
            source=source,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            booking_id=booking_id,
            slot_id=slot_id,
            recipient_type=recipient_type,
            recipient_contact_id=recipient_contact_id,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone,
            subject=subject,
            body_snapshot=body_snapshot,
            payload_snapshot=payload_snapshot,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
            status=status,
            failure_reason=failure_reason,
        )
        db.add(notification)
        try:
            db.flush()
        except IntegrityError:
            return None
    return notification


def list_due_notifications(
    db: Session,
    *,
    dispatch_mode: str,
    now: datetime,
    limit: int,
) -> list[Notification]:
    return db.scalars(
        select(Notification)
        .where(
            Notification.dispatch_mode == dispatch_mode,
            Notification.status == NOTIFICATION_STATUS_PENDING,
            Notification.scheduled_for <= now,
        )
        .order_by(Notification.scheduled_for.asc(), Notification.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()


def get_notification_for_dispatch(db: Session, *, notification_id: UUID) -> Notification | None:
    return db.scalar(
        select(Notification)
        .where(Notification.id == notification_id)
        .with_for_update()
    )


def ensure_contact_delivery_status(
    db: Session,
    *,
    contact_type: str,
    contact_id: UUID,
    email: str | None,
    phone: str | None,
) -> ContactDeliveryStatus:
    row = db.scalar(
        select(ContactDeliveryStatus).where(
            ContactDeliveryStatus.contact_type == contact_type,
            ContactDeliveryStatus.contact_id == contact_id,
        )
    )
    if row is not None:
        row.email = email or row.email
        row.phone = phone or row.phone
        db.add(row)
        return row

    row = ContactDeliveryStatus(
        contact_type=contact_type,
        contact_id=contact_id,
        email=email,
        phone=phone,
    )
    db.add(row)
    db.flush()
    return row


def append_contact_delivery_incident(
    db: Session,
    *,
    contact_type: str,
    contact_id: UUID,
    channel: str,
    incident_type: str,
    severity: str,
    detail_text: str | None,
    detected_at: datetime,
    notification_id: UUID | None,
    provider_name: str | None = None,
    provider_message_id: str | None = None,
) -> ContactDeliveryIncident:
    incident = ContactDeliveryIncident(
        contact_type=contact_type,
        contact_id=contact_id,
        channel=channel,
        incident_type=incident_type,
        severity=severity,
        detail_text=detail_text,
        detected_at=detected_at,
        notification_id=notification_id,
        provider_name=provider_name,
        provider_message_id=provider_message_id,
    )
    db.add(incident)
    db.flush()
    return incident


def resolve_notification_rule(
    db: Session,
    *,
    slot_id: UUID,
    course_type_id: UUID,
) -> NotificationRule | None:
    return db.scalar(
        select(NotificationRule)
        .where(
            NotificationRule.active.is_(True),
            or_(
                and_(NotificationRule.scope_type == "SLOT", NotificationRule.scope_id == slot_id),
                and_(NotificationRule.scope_type == "COURSE_TYPE", NotificationRule.scope_id == course_type_id),
                and_(NotificationRule.scope_type == "GLOBAL", NotificationRule.scope_id.is_(None)),
            ),
        )
        .order_by(
            NotificationRule.scope_type.desc(),
            NotificationRule.updated_at.desc(),
            NotificationRule.created_at.desc(),
        )
        .limit(1)
    )


def list_admin_recipients_for_type(db: Session, *, notification_type: str) -> list[str]:
    rows = db.scalars(
        select(AdminNotificationSetting.recipient_email)
        .where(
            AdminNotificationSetting.notification_type == notification_type,
            AdminNotificationSetting.active.is_(True),
        )
        .order_by(AdminNotificationSetting.created_at.asc())
    ).all()
    return [row.strip().lower() for row in rows if isinstance(row, str) and row.strip()]


def start_job_run(
    db: Session,
    *,
    job_name: str,
    job_key: str | None,
    triggered_by: str,
    started_at: datetime,
    metadata_json: dict[str, Any],
) -> JobRun:
    row = JobRun(
        job_name=job_name,
        job_key=job_key,
        triggered_by=triggered_by,
        started_at=started_at,
        status="running",
        metadata_json=metadata_json,
    )
    db.add(row)
    db.flush()
    return row


def finish_job_run(
    db: Session,
    *,
    job_run: JobRun,
    status: str,
    finished_at: datetime,
    items_scanned: int,
    items_processed: int,
    items_sent: int,
    items_skipped: int,
    items_failed: int,
    summary_text: str | None = None,
    error_text: str | None = None,
) -> None:
    job_run.status = status
    job_run.finished_at = finished_at
    job_run.items_scanned = int(items_scanned)
    job_run.items_processed = int(items_processed)
    job_run.items_sent = int(items_sent)
    job_run.items_skipped = int(items_skipped)
    job_run.items_failed = int(items_failed)
    job_run.summary_text = summary_text
    job_run.error_text = error_text
    db.add(job_run)


def append_job_run_log(
    db: Session,
    *,
    job_run_id: UUID,
    level: str,
    message: str,
    context_json: dict[str, Any] | None = None,
) -> JobRunLog:
    row = JobRunLog(
        job_run_id=job_run_id,
        level=level,
        message=message,
        context_json=context_json or {},
    )
    db.add(row)
    db.flush()
    return row


def get_job_cursor(db: Session, *, job_name: str) -> JobCursor | None:
    return db.scalar(select(JobCursor).where(JobCursor.job_name == job_name))


def upsert_job_cursor(db: Session, *, job_name: str, last_processed_at: datetime, updated_at: datetime) -> JobCursor:
    row = get_job_cursor(db, job_name=job_name)
    if row is None:
        row = JobCursor(job_name=job_name, last_processed_at=last_processed_at, updated_at=updated_at)
    else:
        row.last_processed_at = last_processed_at
        row.updated_at = updated_at
    db.add(row)
    db.flush()
    return row
