from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.notification_engine import DomainEvent, Notification
from app.services.contacts.delivery_status.service import suspend_email_for_contact, suspend_phone_for_contact
from app.services.notifications.application.dispatcher import dispatch_notification
from app.services.notifications.application.orchestrator import enqueue_notifications, schedule_reminder_notifications_for_booking
from app.services.notifications.domain.constants import (
    DISPATCH_MODE_IMMEDIATE,
    DISPATCH_MODE_SCHEDULED,
    EVENT_EMAIL_BOUNCED,
    EVENT_SMS_DELIVERY_FAILED_PERMANENT,
    NOTIFICATION_STATUS_BOUNCED,
    NOTIFICATION_STATUS_FAILED,
    NOTIFICATION_STATUS_PENDING,
    SOURCE_SCHEDULER,
)
from app.services.notifications.infrastructure.repository import (
    append_job_run_log,
    finish_job_run,
    get_job_cursor,
    get_notification_for_dispatch,
    list_due_notifications,
    start_job_run,
    upsert_job_cursor,
)
from app.services.shared.locks.redis_lock import redis_lock


@dataclass(frozen=True)
class NotificationJobResult:
    checked: int
    processed: int
    sent: int
    skipped: int
    failed: int
    job_run_id: UUID


def _run_dispatch_job(
    db: Session,
    *,
    now: datetime,
    limit: int,
    dispatch_mode: str,
    job_name: str,
    lock_key: str,
) -> NotificationJobResult:
    with redis_lock(lock_key, ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError(f"{job_name} lock already held")

        job_run = start_job_run(
            db,
            job_name=job_name,
            job_key=job_name,
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"dispatch_mode": dispatch_mode, "limit": limit},
        )
        checked = 0
        processed = 0
        sent = 0
        skipped = 0
        failed = 0
        try:
            due_rows = list_due_notifications(
                db,
                dispatch_mode=dispatch_mode,
                now=now,
                limit=limit,
            )
            checked = len(due_rows)
            for row in due_rows:
                checked += 0
                locked = get_notification_for_dispatch(db, notification_id=row.id)
                if locked is None:
                    continue
                result = dispatch_notification(
                    db,
                    notification=locked,
                    now=now,
                    job_run_id=job_run.id,
                )
                processed += 1
                sent += result.sent
                skipped += result.skipped
                failed += result.failed
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO",
                    message=f"Notification {locked.id} -> {result.status}",
                    context_json={"notification_id": str(locked.id), "status": result.status, "reason": result.reason},
                )

            status = "success"
            if failed > 0:
                status = "warning" if sent > 0 or skipped > 0 else "failed"
            finish_job_run(
                db,
                job_run=job_run,
                status=status,
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{processed} notifications dispatch mode={dispatch_mode}",
            )
            return NotificationJobResult(
                checked=checked,
                processed=processed,
                sent=sent,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed + 1,
                summary_text=None,
                error_text=str(exc),
            )
            raise


def run_immediate_notification_dispatch_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> NotificationJobResult:
    return _run_dispatch_job(
        db,
        now=now,
        limit=limit,
        dispatch_mode=DISPATCH_MODE_IMMEDIATE,
        job_name="immediate_notification_dispatch_job",
        lock_key="lock:job:immediate_notification_dispatch",
    )


def run_scheduled_notification_dispatch_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> NotificationJobResult:
    return _run_dispatch_job(
        db,
        now=now,
        limit=limit,
        dispatch_mode=DISPATCH_MODE_SCHEDULED,
        job_name="scheduled_notification_dispatch_job",
        lock_key="lock:job:scheduled_notification_dispatch",
    )


def run_reminder_generation_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 1000,
) -> NotificationJobResult:
    with redis_lock("lock:job:reminder_generation", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("reminder_generation_job lock already held")

        job_run = start_job_run(
            db,
            job_name="reminder_generation_job",
            job_key="reminder_generation_job",
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )
        checked = 0
        processed = 0
        sent = 0
        skipped = 0
        failed = 0
        try:
            rows = db.execute(
                select(Booking, CourseSession)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.status == BookingStatus.BOOKED,
                    CourseSession.status == SessionStatus.SCHEDULED,
                    CourseSession.start_at_utc > now,
                    CourseSession.start_at_utc <= now + timedelta(days=7),
                )
                .order_by(CourseSession.start_at_utc.asc(), Booking.booked_at.asc())
                .limit(limit)
            ).all()
            checked = len(rows)
            all_enqueued = []
            for booking, _ in rows:
                processed += 1
                try:
                    created = schedule_reminder_notifications_for_booking(
                        db,
                        booking=booking,
                        now=now,
                    )
                    sent += len(created)
                    all_enqueued.extend(created)
                except Exception as exc:
                    failed += 1
                    append_job_run_log(
                        db,
                        job_run_id=job_run.id,
                        level="ERROR",
                        message=f"Reminder generation failed for booking {booking.id}",
                        context_json={"booking_id": str(booking.id), "error": str(exc)},
                    )
            enqueue_notifications(all_enqueued)
            finish_job_run(
                db,
                job_run=job_run,
                status="warning" if failed > 0 else "success",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{sent} notifications scheduled",
            )
            return NotificationJobResult(
                checked=checked,
                processed=processed,
                sent=sent,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed + 1,
                summary_text=None,
                error_text=str(exc),
            )
            raise


def run_delivery_feedback_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 500,
) -> NotificationJobResult:
    with redis_lock("lock:job:delivery_feedback", ttl_seconds=240) as acquired:
        if not acquired:
            raise RuntimeError("delivery_feedback_job lock already held")

        job_run = start_job_run(
            db,
            job_name="delivery_feedback_job",
            job_key="delivery_feedback_job",
            triggered_by=SOURCE_SCHEDULER,
            started_at=now,
            metadata_json={"limit": limit},
        )
        checked = 0
        processed = 0
        sent = 0
        skipped = 0
        failed = 0
        try:
            cursor = get_job_cursor(db, job_name="delivery_feedback_job")
            last_processed_at = cursor.last_processed_at if cursor is not None else None
            stmt = select(DomainEvent).where(
                DomainEvent.event_type.in_((EVENT_EMAIL_BOUNCED, EVENT_SMS_DELIVERY_FAILED_PERMANENT))
            )
            if last_processed_at is not None:
                stmt = stmt.where(DomainEvent.occurred_at > last_processed_at)
            events = db.scalars(stmt.order_by(DomainEvent.occurred_at.asc()).limit(limit)).all()
            checked = len(events)
            latest_processed_at = last_processed_at

            for event in events:
                processed += 1
                latest_processed_at = event.occurred_at
                payload = event.payload_json or {}
                provider_message_id = str(payload.get("provider_message_id") or "").strip() or None
                if provider_message_id is None:
                    skipped += 1
                    continue
                notification = db.scalar(
                    select(Notification)
                    .where(Notification.provider_message_id == provider_message_id)
                    .order_by(Notification.created_at.desc())
                    .limit(1)
                )
                if notification is None:
                    skipped += 1
                    continue
                notification.job_run_id = job_run.id
                notification.provider_status = str(payload.get("provider_status") or "").strip() or notification.provider_status
                detail = str(payload.get("detail") or "").strip() or None
                if event.event_type == EVENT_EMAIL_BOUNCED:
                    notification.status = NOTIFICATION_STATUS_BOUNCED
                    notification.bounce_type = str(payload.get("bounce_type") or "hard").strip().lower()
                    notification.failed_at = event.occurred_at
                    notification.failure_reason = detail or "email bounced"
                    if notification.recipient_contact_id is not None:
                        suspend_email_for_contact(
                            db,
                            contact_type="USER",
                            contact_id=notification.recipient_contact_id,
                            email=notification.recipient_email,
                            reason=notification.failure_reason or "email bounced",
                            detected_at=event.occurred_at,
                            notification_id=notification.id,
                            provider_name=notification.provider_name,
                            provider_message_id=provider_message_id,
                        )
                else:
                    notification.status = NOTIFICATION_STATUS_FAILED
                    notification.failed_at = event.occurred_at
                    notification.failure_reason = detail or "sms permanent failure"
                    if notification.recipient_contact_id is not None:
                        suspend_phone_for_contact(
                            db,
                            contact_type="USER",
                            contact_id=notification.recipient_contact_id,
                            phone=notification.recipient_phone,
                            reason=notification.failure_reason or "sms permanent failure",
                            detected_at=event.occurred_at,
                            notification_id=notification.id,
                            provider_name=notification.provider_name,
                            provider_message_id=provider_message_id,
                        )
                notification.updated_at = now
                db.add(notification)
                sent += 1
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="INFO",
                    message=f"Feedback processed for notification {notification.id}",
                    context_json={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "notification_id": str(notification.id),
                    },
                )

            if latest_processed_at is not None:
                upsert_job_cursor(
                    db,
                    job_name="delivery_feedback_job",
                    last_processed_at=latest_processed_at,
                    updated_at=now,
                )

            finish_job_run(
                db,
                job_run=job_run,
                status="warning" if failed > 0 else "success",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=f"{processed} feedback events processed",
            )
            return NotificationJobResult(
                checked=checked,
                processed=processed,
                sent=sent,
                skipped=skipped,
                failed=failed,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=now,
                items_scanned=checked,
                items_processed=processed,
                items_sent=sent,
                items_skipped=skipped,
                items_failed=failed + 1,
                summary_text=None,
                error_text=str(exc),
            )
            raise
