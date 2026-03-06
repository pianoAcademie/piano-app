from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notification_engine import ContactDeliveryStatus
from app.services.notifications.infrastructure.repository import append_contact_delivery_incident, ensure_contact_delivery_status


def get_contact_delivery_status_for_user(db: Session, *, user_id: UUID) -> ContactDeliveryStatus | None:
    return db.query(ContactDeliveryStatus).filter(
        ContactDeliveryStatus.contact_type == "USER",
        ContactDeliveryStatus.contact_id == user_id,
    ).one_or_none()


def is_email_suspended(row: ContactDeliveryStatus | None) -> bool:
    if row is None:
        return False
    return (row.email_status or "").strip().lower() == "suspended"


def is_phone_suspended(row: ContactDeliveryStatus | None) -> bool:
    if row is None:
        return False
    return (row.phone_status or "").strip().lower() == "suspended"


def suspend_email_for_contact(
    db: Session,
    *,
    contact_type: str,
    contact_id: UUID,
    email: str | None,
    reason: str,
    detected_at: datetime,
    notification_id: UUID | None,
    provider_name: str | None,
    provider_message_id: str | None,
) -> ContactDeliveryStatus:
    row = ensure_contact_delivery_status(
        db,
        contact_type=contact_type,
        contact_id=contact_id,
        email=email,
        phone=None,
    )
    row.email_status = "suspended"
    row.email_suspended_at = detected_at
    row.email_suspension_reason = reason
    row.email_last_bounce_at = detected_at
    row.email_last_provider_feedback_at = detected_at
    db.add(row)
    append_contact_delivery_incident(
        db,
        contact_type=contact_type,
        contact_id=contact_id,
        channel="email",
        incident_type="email_bounced",
        severity="high",
        detail_text=reason,
        detected_at=detected_at,
        notification_id=notification_id,
        provider_name=provider_name,
        provider_message_id=provider_message_id,
    )
    return row


def suspend_phone_for_contact(
    db: Session,
    *,
    contact_type: str,
    contact_id: UUID,
    phone: str | None,
    reason: str,
    detected_at: datetime,
    notification_id: UUID | None,
    provider_name: str | None,
    provider_message_id: str | None,
) -> ContactDeliveryStatus:
    row = ensure_contact_delivery_status(
        db,
        contact_type=contact_type,
        contact_id=contact_id,
        email=None,
        phone=phone,
    )
    row.phone_status = "suspended"
    row.phone_suspended_at = detected_at
    row.phone_suspension_reason = reason
    row.phone_last_failure_at = detected_at
    row.phone_last_provider_feedback_at = detected_at
    db.add(row)
    append_contact_delivery_incident(
        db,
        contact_type=contact_type,
        contact_id=contact_id,
        channel="sms",
        incident_type="sms_delivery_failed_permanent",
        severity="high",
        detail_text=reason,
        detected_at=detected_at,
        notification_id=notification_id,
        provider_name=provider_name,
        provider_message_id=provider_message_id,
    )
    return row


def reactivate_contact_channels(
    db: Session,
    *,
    contact_type: str,
    contact_id: UUID,
    reactivate_email: bool,
    reactivate_phone: bool,
    now: datetime,
) -> ContactDeliveryStatus | None:
    row = db.query(ContactDeliveryStatus).filter(
        ContactDeliveryStatus.contact_type == contact_type,
        ContactDeliveryStatus.contact_id == contact_id,
    ).one_or_none()
    if row is None:
        return None
    if reactivate_email:
        row.email_status = "active"
        row.email_suspended_at = None
        row.email_suspension_reason = None
        row.email_last_provider_feedback_at = now
    if reactivate_phone:
        row.phone_status = "active"
        row.phone_suspended_at = None
        row.phone_suspension_reason = None
        row.phone_last_provider_feedback_at = now
    row.updated_at = now
    db.add(row)
    return row
