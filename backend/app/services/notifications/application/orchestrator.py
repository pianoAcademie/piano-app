from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, CourseSession, CourseType
from app.models.ops import AppSetting
from app.models.user import User, UserRole
from app.services.notifications.application.recipients import (
    resolve_admin_booking_notification_recipients,
    resolve_admin_cancellation_recipients,
    resolve_client_booking_notification_recipient,
    resolve_reminder_recipients,
)
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    DISPATCH_MODE_IMMEDIATE,
    DISPATCH_MODE_SCHEDULED,
    EVENT_BOOKING_CANCELLED_FROM_CLIENT_PORTAL,
    EVENT_BOOKING_CREATED_FROM_CLIENT_PORTAL,
    EVENT_BOOKING_REMINDER_DUE,
    EVENT_SLOT_CANCELLED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_SKIPPED,
    NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_ADMIN_SLOT_CANCELLATION,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_REMINDER_SMS,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    QUEUE_NOTIFICATIONS_SCHEDULED,
    SOURCE_CLIENT_PORTAL,
    SOURCE_SCHEDULER,
)
from app.services.notifications.infrastructure.repository import (
    create_domain_event,
    create_notification_if_new,
    resolve_notification_rule,
)
from app.services.shared.queue.redis_queue import queue_push


@dataclass(frozen=True)
class OrchestratedNotification:
    notification_id: UUID
    queue_name: str


def _get_setting_int(db: Session, key: str, default: int) -> int:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        return default
    try:
        parsed = int((setting.value or "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _notification_rule_for_session(
    db: Session,
    *,
    session_obj: CourseSession,
) -> tuple[bool, int, bool, int]:
    rule = resolve_notification_rule(
        db,
        slot_id=session_obj.id,
        course_type_id=session_obj.course_type_id,
    )
    if rule is not None:
        email_enabled = bool(rule.email_enabled)
        email_offset = int(rule.email_offset_minutes or 0)
        sms_enabled = bool(rule.sms_enabled)
        sms_offset = int(rule.sms_offset_minutes or 0)
        return email_enabled, max(0, email_offset), sms_enabled, max(0, sms_offset)

    email_offset = _get_setting_int(db, "reminder_hours_before_start", 24) * 60
    sms_offset = _get_setting_int(db, "sms_reminder_hours_before_start", 1) * 60
    return True, max(0, email_offset), True, max(0, sms_offset)


def _booking_context(db: Session, *, booking: Booking) -> tuple[CourseSession, CourseType]:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == booking.session_id))
    if session_obj is None:
        raise ValueError("Session missing for booking notification orchestration")
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None:
        raise ValueError("Course type missing for booking notification orchestration")
    return session_obj, course_type


def _body_for_booking_notification(
    *,
    is_cancellation: bool,
    course_type_name: str,
    start_at: datetime,
    student_label: str,
) -> tuple[str, str]:
    date_label = start_at.strftime("%d/%m/%Y %H:%M UTC")
    if is_cancellation:
        subject = f"Annulation de reservation - {course_type_name}"
        body = (
            f"Reservation annulee.\n"
            f"Eleve: {student_label}\n"
            f"Activite: {course_type_name}\n"
            f"Debut: {date_label}\n"
        )
        return subject, body
    subject = f"Confirmation de reservation - {course_type_name}"
    body = (
        f"Reservation confirmee.\n"
        f"Eleve: {student_label}\n"
        f"Activite: {course_type_name}\n"
        f"Debut: {date_label}\n"
    )
    return subject, body


def _idempotency_key_for_booking_notification(
    *,
    notification_type: str,
    booking_id: UUID,
    recipient_value: str,
    source_event_id: UUID,
) -> str:
    return f"{notification_type}:{booking_id}:{recipient_value}:{source_event_id}"


def _idempotency_key_for_slot_cancellation(
    *,
    slot_id: UUID,
    recipient_email: str,
    cancelled_at: datetime,
) -> str:
    return f"admin_slot_cancellation:{slot_id}:{recipient_email}:{cancelled_at.isoformat()}"


def _idempotency_key_for_reminder(
    *,
    notification_type: str,
    booking_id: UUID,
    recipient_contact_id: UUID | None,
    offset_minutes: int,
    scheduled_for: datetime,
) -> str:
    recipient_part = str(recipient_contact_id) if recipient_contact_id is not None else "anonymous"
    return f"{notification_type}:{booking_id}:{recipient_part}:{offset_minutes}:{scheduled_for.isoformat()}"


def enqueue_notifications(notifications: list[OrchestratedNotification]) -> None:
    for row in notifications:
        queue_push(row.queue_name, {"notification_id": str(row.notification_id)})


def schedule_booking_created_notifications(
    db: Session,
    *,
    booking: Booking,
    actor_user_id: UUID,
    occurred_at: datetime,
) -> list[OrchestratedNotification]:
    session_obj, course_type = _booking_context(db, booking=booking)
    student = db.scalar(select(User).where(User.id == booking.user_id))
    student_label = (f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip() if student is not None else "") or (
        student.email if student is not None else str(booking.user_id)
    )
    subject, body = _body_for_booking_notification(
        is_cancellation=False,
        course_type_name=course_type.name,
        start_at=session_obj.start_at_utc,
        student_label=student_label,
    )

    event = create_domain_event(
        db,
        event_type=EVENT_BOOKING_CREATED_FROM_CLIENT_PORTAL,
        source=SOURCE_CLIENT_PORTAL,
        actor_type="client",
        actor_id=actor_user_id,
        related_entity_type="booking",
        related_entity_id=booking.id,
        occurred_at=occurred_at,
        payload_json={
            "booking_id": str(booking.id),
            "session_id": str(session_obj.id),
            "course_type_id": str(course_type.id),
        },
    )

    out: list[OrchestratedNotification] = []
    client_recipient = resolve_client_booking_notification_recipient(db, booking=booking)
    if client_recipient is not None and client_recipient.email is not None:
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_CLIENT_BOOKING_CONFIRMATION,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_CLIENT_PORTAL,
            related_entity_type="booking",
            related_entity_id=booking.id,
            booking_id=booking.id,
            slot_id=session_obj.id,
            recipient_type=client_recipient.contact_type,
            recipient_contact_id=client_recipient.contact_id,
            recipient_email=client_recipient.email,
            recipient_phone=None,
            subject=subject,
            body_snapshot=body,
            payload_snapshot={"booking_id": str(booking.id)},
            idempotency_key=_idempotency_key_for_booking_notification(
                notification_type=NOTIFICATION_TYPE_CLIENT_BOOKING_CONFIRMATION,
                booking_id=booking.id,
                recipient_value=client_recipient.email,
                source_event_id=event.id,
            ),
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))

    for admin_recipient in resolve_admin_booking_notification_recipients(db, is_cancellation=False):
        if admin_recipient.email is None:
            continue
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_CLIENT_PORTAL,
            related_entity_type="booking",
            related_entity_id=booking.id,
            booking_id=booking.id,
            slot_id=session_obj.id,
            recipient_type=admin_recipient.contact_type,
            recipient_contact_id=admin_recipient.contact_id,
            recipient_email=admin_recipient.email,
            recipient_phone=None,
            subject=subject,
            body_snapshot=body,
            payload_snapshot={"booking_id": str(booking.id)},
            idempotency_key=_idempotency_key_for_booking_notification(
                notification_type=NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION,
                booking_id=booking.id,
                recipient_value=admin_recipient.email,
                source_event_id=event.id,
            ),
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))
    return out


def schedule_booking_cancelled_notifications(
    db: Session,
    *,
    booking: Booking,
    actor_user_id: UUID,
    occurred_at: datetime,
) -> list[OrchestratedNotification]:
    session_obj, course_type = _booking_context(db, booking=booking)
    student = db.scalar(select(User).where(User.id == booking.user_id))
    student_label = (f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip() if student is not None else "") or (
        student.email if student is not None else str(booking.user_id)
    )
    subject, body = _body_for_booking_notification(
        is_cancellation=True,
        course_type_name=course_type.name,
        start_at=session_obj.start_at_utc,
        student_label=student_label,
    )

    event = create_domain_event(
        db,
        event_type=EVENT_BOOKING_CANCELLED_FROM_CLIENT_PORTAL,
        source=SOURCE_CLIENT_PORTAL,
        actor_type="client",
        actor_id=actor_user_id,
        related_entity_type="booking",
        related_entity_id=booking.id,
        occurred_at=occurred_at,
        payload_json={
            "booking_id": str(booking.id),
            "session_id": str(session_obj.id),
            "course_type_id": str(course_type.id),
        },
    )

    out: list[OrchestratedNotification] = []
    client_recipient = resolve_client_booking_notification_recipient(db, booking=booking)
    if client_recipient is not None and client_recipient.email is not None:
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_CLIENT_PORTAL,
            related_entity_type="booking",
            related_entity_id=booking.id,
            booking_id=booking.id,
            slot_id=session_obj.id,
            recipient_type=client_recipient.contact_type,
            recipient_contact_id=client_recipient.contact_id,
            recipient_email=client_recipient.email,
            recipient_phone=None,
            subject=subject,
            body_snapshot=body,
            payload_snapshot={"booking_id": str(booking.id)},
            idempotency_key=_idempotency_key_for_booking_notification(
                notification_type=NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
                booking_id=booking.id,
                recipient_value=client_recipient.email,
                source_event_id=event.id,
            ),
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))

    for admin_recipient in resolve_admin_booking_notification_recipients(db, is_cancellation=True):
        if admin_recipient.email is None:
            continue
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_CLIENT_PORTAL,
            related_entity_type="booking",
            related_entity_id=booking.id,
            booking_id=booking.id,
            slot_id=session_obj.id,
            recipient_type=admin_recipient.contact_type,
            recipient_contact_id=admin_recipient.contact_id,
            recipient_email=admin_recipient.email,
            recipient_phone=None,
            subject=subject,
            body_snapshot=body,
            payload_snapshot={"booking_id": str(booking.id)},
            idempotency_key=_idempotency_key_for_booking_notification(
                notification_type=NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION,
                booking_id=booking.id,
                recipient_value=admin_recipient.email,
                source_event_id=event.id,
            ),
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))
    return out


def schedule_slot_cancelled_notifications(
    db: Session,
    *,
    slot: CourseSession,
    actor_user_id: UUID | None,
    occurred_at: datetime,
    source: str,
) -> list[OrchestratedNotification]:
    event = create_domain_event(
        db,
        event_type=EVENT_SLOT_CANCELLED,
        source=source,
        actor_type="admin" if actor_user_id is not None else "system",
        actor_id=actor_user_id,
        related_entity_type="slot",
        related_entity_id=slot.id,
        occurred_at=occurred_at,
        payload_json={
            "slot_id": str(slot.id),
            "session_title": slot.title,
            "start_at_utc": slot.start_at_utc.isoformat(),
        },
    )

    subject = f"Creneau annule - {slot.title}"
    body = f"Creneau annule.\nTitre: {slot.title}\nDebut: {slot.start_at_utc.strftime('%d/%m/%Y %H:%M UTC')}\n"
    out: list[OrchestratedNotification] = []
    for recipient in resolve_admin_cancellation_recipients(db):
        if recipient.email is None:
            continue
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_ADMIN_SLOT_CANCELLATION,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=source,
            related_entity_type="slot",
            related_entity_id=slot.id,
            booking_id=None,
            slot_id=slot.id,
            recipient_type=recipient.contact_type,
            recipient_contact_id=recipient.contact_id,
            recipient_email=recipient.email,
            recipient_phone=None,
            subject=subject,
            body_snapshot=body,
            payload_snapshot={"slot_id": str(slot.id)},
            idempotency_key=_idempotency_key_for_slot_cancellation(
                slot_id=slot.id,
                recipient_email=recipient.email,
                cancelled_at=occurred_at,
            ),
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))
    return out


def schedule_reminder_notifications_for_booking(
    db: Session,
    *,
    booking: Booking,
    now: datetime,
) -> list[OrchestratedNotification]:
    session_obj, course_type = _booking_context(db, booking=booking)
    email_enabled, email_offset_minutes, sms_enabled, sms_offset_minutes = _notification_rule_for_session(
        db,
        session_obj=session_obj,
    )
    recipients = resolve_reminder_recipients(db, booking=booking)
    if not recipients:
        return []

    event = create_domain_event(
        db,
        event_type=EVENT_BOOKING_REMINDER_DUE,
        source=SOURCE_SCHEDULER,
        actor_type="system",
        actor_id=None,
        related_entity_type="booking",
        related_entity_id=booking.id,
        occurred_at=now,
        payload_json={"booking_id": str(booking.id), "session_id": str(session_obj.id), "course_type_id": str(course_type.id)},
    )
    out: list[OrchestratedNotification] = []
    start_label = session_obj.start_at_utc.strftime("%d/%m/%Y %H:%M UTC")

    for recipient in recipients:
        if email_enabled:
            scheduled_for = session_obj.start_at_utc - timedelta(minutes=email_offset_minutes)
            status = NOTIFICATION_STATUS_PENDING
            failure_reason = None
            if recipient.email is None:
                status = NOTIFICATION_STATUS_SKIPPED
                failure_reason = "skipped because no email"
            created = create_notification_if_new(
                db,
                notification_type=NOTIFICATION_TYPE_REMINDER_EMAIL,
                channel=CHANNEL_EMAIL,
                dispatch_mode=DISPATCH_MODE_SCHEDULED,
                source_event_id=event.id,
                source=SOURCE_SCHEDULER,
                related_entity_type="booking",
                related_entity_id=booking.id,
                booking_id=booking.id,
                slot_id=session_obj.id,
                recipient_type=recipient.contact_type,
                recipient_contact_id=recipient.contact_id,
                recipient_email=recipient.email,
                recipient_phone=None,
                subject=f"Rappel de cours - {course_type.name}",
                body_snapshot=f"Rappel: {course_type.name} le {start_label}.",
                payload_snapshot={"offset_minutes": email_offset_minutes},
                idempotency_key=_idempotency_key_for_reminder(
                    notification_type=NOTIFICATION_TYPE_REMINDER_EMAIL,
                    booking_id=booking.id,
                    recipient_contact_id=recipient.contact_id,
                    offset_minutes=email_offset_minutes,
                    scheduled_for=scheduled_for,
                ),
                scheduled_for=scheduled_for,
                status=status,
                failure_reason=failure_reason,
            )
            if created is not None and status == NOTIFICATION_STATUS_PENDING:
                out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_SCHEDULED))

        if sms_enabled:
            scheduled_for = session_obj.start_at_utc - timedelta(minutes=sms_offset_minutes)
            status = NOTIFICATION_STATUS_PENDING
            failure_reason = None
            if recipient.phone is None:
                status = NOTIFICATION_STATUS_SKIPPED
                failure_reason = "skipped because no phone"
            created = create_notification_if_new(
                db,
                notification_type=NOTIFICATION_TYPE_REMINDER_SMS,
                channel=CHANNEL_SMS,
                dispatch_mode=DISPATCH_MODE_SCHEDULED,
                source_event_id=event.id,
                source=SOURCE_SCHEDULER,
                related_entity_type="booking",
                related_entity_id=booking.id,
                booking_id=booking.id,
                slot_id=session_obj.id,
                recipient_type=recipient.contact_type,
                recipient_contact_id=recipient.contact_id,
                recipient_email=None,
                recipient_phone=recipient.phone,
                subject=None,
                body_snapshot=f"Rappel: {course_type.name} le {start_label}.",
                payload_snapshot={"offset_minutes": sms_offset_minutes},
                idempotency_key=_idempotency_key_for_reminder(
                    notification_type=NOTIFICATION_TYPE_REMINDER_SMS,
                    booking_id=booking.id,
                    recipient_contact_id=recipient.contact_id,
                    offset_minutes=sms_offset_minutes,
                    scheduled_for=scheduled_for,
                ),
                scheduled_for=scheduled_for,
                status=status,
                failure_reason=failure_reason,
            )
            if created is not None and status == NOTIFICATION_STATUS_PENDING:
                out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_SCHEDULED))
    return out
