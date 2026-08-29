from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_engine import Notification
from app.models.user import User
from app.services.contacts.delivery_status.service import (
    get_contact_delivery_status_for_user,
    is_email_suspended,
    is_phone_suspended,
)
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    NOTIFICATION_STATUS_BOUNCED,
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_FAILED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    NOTIFICATION_STATUS_SENT,
    NOTIFICATION_STATUS_SKIPPED,
    NOTIFICATION_TYPE_AUTO_CANCEL_PARTICIPANT,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_COLLABORATOR_PAYMENT_CONFIRMATION,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_REMINDER_SMS,
)
from app.services.notifications.infrastructure.repository import ensure_contact_delivery_status
from app.services.providers.email import send_provider_email
from app.services.providers.sms import send_provider_sms


@dataclass(frozen=True)
class DispatchResult:
    status: str
    sent: int
    skipped: int
    failed: int
    reason: str | None = None


LESSON_EMAIL_NOTIFICATION_TYPES = {
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_AUTO_CANCEL_PARTICIPANT,
}

TRANSACTIONAL_EMAIL_NOTIFICATION_TYPES = {
    NOTIFICATION_TYPE_COLLABORATOR_PAYMENT_CONFIRMATION,
}


def _load_user_for_notification(db: Session, *, notification: Notification) -> User | None:
    if notification.recipient_contact_id is None:
        return None
    return db.scalar(select(User).where(User.id == notification.recipient_contact_id))


def dispatch_notification(
    db: Session,
    *,
    notification: Notification,
    now: datetime,
    job_run_id: UUID | None = None,
) -> DispatchResult:
    if notification.status not in {NOTIFICATION_STATUS_PENDING, NOTIFICATION_STATUS_QUEUED}:
        return DispatchResult(status=notification.status, sent=0, skipped=0, failed=0)
    if notification.status in {NOTIFICATION_STATUS_CANCELLED, NOTIFICATION_STATUS_BOUNCED}:
        return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0)

    user = _load_user_for_notification(db, notification=notification)
    if user is not None:
        ensure_contact_delivery_status(
            db,
            contact_type="USER",
            contact_id=user.id,
            email=(user.email or "").strip().lower() or None,
            phone=(notification.recipient_phone or "").strip() or None,
        )
        delivery_status = get_contact_delivery_status_for_user(db, user_id=user.id)
    else:
        delivery_status = None

    notification.job_run_id = job_run_id
    notification.updated_at = now

    if notification.channel == CHANNEL_EMAIL:
        if notification.recipient_email is None:
            notification.status = NOTIFICATION_STATUS_SKIPPED
            notification.failure_reason = "skipped because no email"
            notification.skipped_at = now
            db.add(notification)
            return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)

        if user is not None:
            if (
                notification.notification_type in LESSON_EMAIL_NOTIFICATION_TYPES
                and not user.lesson_reminder_email_opt_in
            ):
                notification.status = NOTIFICATION_STATUS_SKIPPED
                notification.failure_reason = "skipped because email opt-out"
                notification.skipped_at = now
                db.add(notification)
                return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)
            if (
                notification.notification_type not in LESSON_EMAIL_NOTIFICATION_TYPES
                and notification.notification_type not in TRANSACTIONAL_EMAIL_NOTIFICATION_TYPES
                and not user.email_opt_in
            ):
                notification.status = NOTIFICATION_STATUS_SKIPPED
                notification.failure_reason = "skipped because email opt-out"
                notification.skipped_at = now
                db.add(notification)
                return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)
        if delivery_status is not None and is_email_suspended(delivery_status):
            notification.status = NOTIFICATION_STATUS_SKIPPED
            notification.failure_reason = "skipped because email suspended"
            notification.skipped_at = now
            db.add(notification)
            return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)

        provider_result = send_provider_email(
            to_email=notification.recipient_email,
            subject=notification.subject or "Notification",
            body=notification.body_snapshot or "",
            body_format=(
                "HTML"
                if str((notification.payload_snapshot or {}).get("body_format") or "").strip().upper() == "HTML"
                else "TEXT"
            ),
            context=f"NOTIFICATION:{notification.notification_type}",
            recipient_user_id=user.id if user is not None else None,
        )
        notification.provider_name = provider_result.provider_name
        notification.provider_message_id = provider_result.provider_message_id
        notification.provider_status = provider_result.provider_status
        if provider_result.ok:
            notification.status = NOTIFICATION_STATUS_SENT
            notification.sent_at = now
            notification.failure_reason = None
            db.add(notification)
            return DispatchResult(status=notification.status, sent=1, skipped=0, failed=0)

        notification.status = NOTIFICATION_STATUS_FAILED
        notification.failed_at = now
        notification.failure_reason = provider_result.error_message or "email delivery failed"
        db.add(notification)
        return DispatchResult(status=notification.status, sent=0, skipped=0, failed=1, reason=notification.failure_reason)

    if notification.channel == CHANNEL_SMS:
        if notification.recipient_phone is None:
            notification.status = NOTIFICATION_STATUS_SKIPPED
            notification.failure_reason = "skipped because no phone"
            notification.skipped_at = now
            db.add(notification)
            return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)

        if user is not None:
            if notification.notification_type == NOTIFICATION_TYPE_REMINDER_SMS and not user.lesson_reminder_sms_opt_in:
                notification.status = NOTIFICATION_STATUS_SKIPPED
                notification.failure_reason = "skipped because sms opt-out"
                notification.skipped_at = now
                db.add(notification)
                return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)
            if notification.notification_type != NOTIFICATION_TYPE_REMINDER_SMS and not user.sms_opt_in:
                notification.status = NOTIFICATION_STATUS_SKIPPED
                notification.failure_reason = "skipped because sms opt-out"
                notification.skipped_at = now
                db.add(notification)
                return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)
        if delivery_status is not None and is_phone_suspended(delivery_status):
            notification.status = NOTIFICATION_STATUS_SKIPPED
            notification.failure_reason = "skipped because phone suspended"
            notification.skipped_at = now
            db.add(notification)
            return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)

        provider_result = send_provider_sms(
            to_phone=notification.recipient_phone,
            message=notification.body_snapshot or "Notification",
            context=f"NOTIFICATION:{notification.notification_type}",
            recipient_user_id=user.id if user is not None else None,
        )
        notification.provider_name = provider_result.provider_name
        notification.provider_message_id = provider_result.provider_message_id
        notification.provider_status = provider_result.provider_status
        if provider_result.ok:
            notification.status = NOTIFICATION_STATUS_SENT
            notification.sent_at = now
            notification.failure_reason = None
            db.add(notification)
            return DispatchResult(status=notification.status, sent=1, skipped=0, failed=0)

        notification.status = NOTIFICATION_STATUS_FAILED
        notification.failed_at = now
        notification.failure_reason = provider_result.error_message or "sms delivery failed"
        db.add(notification)
        return DispatchResult(status=notification.status, sent=0, skipped=0, failed=1, reason=notification.failure_reason)

    notification.status = NOTIFICATION_STATUS_SKIPPED
    notification.failure_reason = f"unsupported channel: {notification.channel}"
    notification.skipped_at = now
    db.add(notification)
    return DispatchResult(status=notification.status, sent=0, skipped=1, failed=0, reason=notification.failure_reason)
