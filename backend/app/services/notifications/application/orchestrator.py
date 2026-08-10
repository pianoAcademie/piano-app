from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, CourseSession, CourseType, DeliveryMode, Location, PlanningConfig, Professor
from app.models.notification_engine import Notification
from app.models.ops import AppSetting
from app.models.user import User, UserRole
from app.services.booking_confirmation_templates import render_booking_confirmation_email
from app.services.email_branding import render_branded_email
from app.services.i18n import normalize_language
from app.services.local_time import localize_datetime, resolve_timezone_name
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_ADMIN,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_PARTICIPANT,
    PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_TEACHER,
    render_template_content,
    resolve_frontend_base_url,
    resolve_predefined_template,
)
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
    EVENT_BOOKING_WAITLISTED,
    EVENT_BOOKING_WAITLIST_PROMOTED,
    EVENT_BOOKING_REMINDER_DUE,
    EVENT_SLOT_CANCELLED,
    EVENT_SLOT_AUTO_CANCELLED_LOW_ATTENDANCE,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    NOTIFICATION_STATUS_SKIPPED,
    NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_ADMIN_SLOT_CANCELLATION,
    NOTIFICATION_TYPE_AUTO_CANCEL_ADMIN,
    NOTIFICATION_TYPE_AUTO_CANCEL_PARTICIPANT,
    NOTIFICATION_TYPE_AUTO_CANCEL_TEACHER,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_CLIENT_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_CLIENT_WAITLIST_JOINED,
    NOTIFICATION_TYPE_CLIENT_WAITLIST_PROMOTED,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_REMINDER_SMS,
    NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    QUEUE_NOTIFICATIONS_SCHEDULED,
    SOURCE_CLIENT_PORTAL,
    SOURCE_SCHEDULER,
    SOURCE_SYSTEM,
)
from app.services.notifications.infrastructure.repository import (
    create_domain_event,
    create_notification_if_new,
    resolve_notification_rule,
)
from app.services.session_teachers import effective_teacher_id_for_session, professor_display_name
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
    timezone_name: str | None,
) -> tuple[str, str]:
    local_start, resolved_timezone = localize_datetime(start_at, timezone_name)
    date_label = f"{local_start.strftime('%d/%m/%Y %H:%M')} ({resolved_timezone})"
    if is_cancellation:
        subject = f"Annulation de réservation - {course_type_name}"
        body = render_branded_email(
            preview=f"La réservation de {student_label} a été annulée.",
            eyebrow="RÉSERVATION",
            title="Réservation annulée",
            greeting="Bonjour,",
            intro="Nous vous confirmons l’annulation de la réservation ci-dessous.",
            rows=[
                ("Élève", student_label),
                ("Activité", course_type_name),
                ("Date et horaire", date_label),
            ],
        )
        return subject, body
    subject = f"Confirmation de réservation - {course_type_name}"
    body = render_branded_email(
        preview=f"La réservation de {student_label} est confirmée.",
        eyebrow="RÉSERVATION",
        title="Réservation confirmée",
        greeting="Bonjour,",
        intro="Nous vous confirmons la réservation ci-dessous.",
        rows=[
            ("Élève", student_label),
            ("Activité", course_type_name),
            ("Date et horaire", date_label),
        ],
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


def _should_notify_session_teacher(db: Session, *, session_obj: CourseSession) -> bool:
    config = db.scalar(select(PlanningConfig).where(PlanningConfig.location_id == session_obj.location_id))
    if config is None:
        return True
    return bool(config.notify_coach)


def _teacher_booking_notification_recipient(
    db: Session,
    *,
    session_obj: CourseSession,
    teacher: Professor | None,
) -> tuple[str, UUID] | None:
    if teacher is None or not _should_notify_session_teacher(db, session_obj=session_obj):
        return None
    email = (teacher.email or "").strip().lower()
    if not email or not bool(teacher.active):
        return None
    return email, teacher.id


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


def _reminder_display_name(user: User | None, *, fallback: str) -> str:
    if user is None:
        return fallback
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or (user.email or fallback)


def _course_timezone_name(session_obj: CourseSession, location: Location | None) -> str:
    return resolve_timezone_name(
        getattr(session_obj, "timezone", None),
        getattr(location, "timezone", None) if location is not None else None,
    )


def _recipient_course_timezone_name(
    recipient_user: User | None,
    session_obj: CourseSession,
    location: Location | None,
) -> str:
    return resolve_timezone_name(
        getattr(recipient_user, "timezone", None) if recipient_user is not None else None,
        getattr(session_obj, "timezone", None),
        getattr(location, "timezone", None) if location is not None else None,
    )


def _reminder_activity_name(name: str, *, language: str | None) -> str:
    value = (name or "").strip()
    if normalize_language(language) != "en":
        return value
    replacements = (
        ("Cours particulier", "Private piano lesson"),
        ("Cours de piano collectif", "Group piano lesson"),
        ("Cours collectif", "Group lesson"),
        ("Solfège", "Music theory"),
    )
    folded = value.casefold()
    for french, english in replacements:
        if folded.startswith(french.casefold()):
            return f"{english}{value[len(french):]}"
    return value


def _reminder_period_label(
    *,
    start_at: datetime,
    end_at: datetime,
    timezone_name: str | None,
) -> str:
    normalized_timezone = resolve_timezone_name(timezone_name)
    recipient_timezone = ZoneInfo(normalized_timezone)
    local_start = start_at.astimezone(recipient_timezone)
    local_end = end_at.astimezone(recipient_timezone)
    if local_start.date() == local_end.date():
        return (
            f"{local_start.strftime('%d/%m/%Y %H:%M')} - "
            f"{local_end.strftime('%H:%M')} ({normalized_timezone})"
        )
    return (
        f"{local_start.strftime('%d/%m/%Y %H:%M')} - "
        f"{local_end.strftime('%d/%m/%Y %H:%M')} ({normalized_timezone})"
    )


def _build_lesson_reminder_email(
    *,
    recipient_name: str,
    student_name: str,
    course_type_name: str,
    start_at: datetime,
    end_at: datetime,
    timezone_name: str | None,
    location_name: str,
    meeting_link: str | None,
    language: str | None,
    account_url: str | None = None,
) -> tuple[str, str]:
    normalized_language = normalize_language(language)
    activity_name = _reminder_activity_name(course_type_name, language=normalized_language)
    normalized_timezone = resolve_timezone_name(timezone_name)
    recipient_timezone = ZoneInfo(normalized_timezone)
    local_start = start_at.astimezone(recipient_timezone)
    local_end = end_at.astimezone(recipient_timezone)

    english_months = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    french_months = (
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )
    english_weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    french_weekdays = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

    if normalized_language == "en":
        subject = f"Lesson reminder - {activity_name}"
        eyebrow = "LESSON REMINDER"
        title = "Your lesson is coming up"
        greeting = f"Hello {recipient_name},"
        intro = "Here are the details of the upcoming lesson."
        student_label = "Student"
        date_label = "Date"
        time_label = "Time"
        location_label = "Location"
        timezone_label = "Time zone"
        online_label = "ONLINE LESSON"
        online_title = "Join your lesson on Zoom"
        online_help = "Use the button below at the scheduled lesson time."
        button_label = "Join the Zoom lesson"
        fallback_label = "If the button does not work, copy this link:"
        account_button_label = "View or manage my booking"
        footer = "This is an automatic reminder from Piano Academie."
        date_value = (
            f"{english_weekdays[local_start.weekday()]}, {english_months[local_start.month - 1]} "
            f"{local_start.day}, {local_start.year}"
        )
        displayed_location = "Online" if location_name.strip().lower() in {"online", "en ligne"} else location_name
    else:
        subject = f"Rappel de cours - {activity_name}"
        eyebrow = "RAPPEL DE COURS"
        title = "Votre cours approche"
        greeting = f"Bonjour {recipient_name},"
        intro = "Voici les informations de votre prochain cours."
        student_label = "Élève"
        date_label = "Date"
        time_label = "Horaire"
        location_label = "Lieu"
        timezone_label = "Fuseau horaire"
        online_label = "COURS EN LIGNE"
        online_title = "Rejoignez votre cours sur Zoom"
        online_help = "Utilisez le bouton ci-dessous à l'heure prévue du cours."
        button_label = "Rejoindre le cours Zoom"
        fallback_label = "Si le bouton ne fonctionne pas, copiez ce lien :"
        account_button_label = "Voir ou gérer ma réservation"
        footer = "Ceci est un rappel automatique envoyé par Piano Academie."
        date_value = (
            f"{french_weekdays[local_start.weekday()]} {local_start.day} "
            f"{french_months[local_start.month - 1]} {local_start.year}"
        )
        displayed_location = "En ligne" if location_name.strip().lower() in {"online", "en ligne"} else location_name

    if local_start.date() == local_end.date():
        time_value = f"{local_start.strftime('%H:%M')} – {local_end.strftime('%H:%M')}"
    else:
        time_value = (
            f"{local_start.strftime('%H:%M')} – "
            f"{local_end.strftime('%d/%m/%Y %H:%M')}"
        )

    safe_meeting_link: str | None = None
    if meeting_link:
        raw_meeting_link = meeting_link.strip()
        parsed_link = urlparse(raw_meeting_link)
        if parsed_link.scheme.lower() in {"http", "https"} and parsed_link.netloc:
            safe_meeting_link = raw_meeting_link

    zoom_block = ""
    if safe_meeting_link:
        escaped_link = escape(safe_meeting_link, quote=True)
        zoom_block = (
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
            'style="margin:0 0 24px 0;background:#fff7e6;border:2px solid #d9a441;border-radius:14px;">'
            '<tr><td style="padding:22px;text-align:center;">'
            f'<div style="font-size:12px;line-height:18px;font-weight:800;letter-spacing:1.2px;color:#8a5a12;">{escape(online_label)}</div>'
            f'<div style="margin-top:4px;font-size:21px;line-height:28px;font-weight:800;color:#172033;">{escape(online_title)}</div>'
            f'<div style="margin:8px 0 18px 0;font-size:15px;line-height:22px;color:#5f6673;">{escape(online_help)}</div>'
            '<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center"><tr><td '
            'style="border-radius:9px;background:#c98224;">'
            f'<a href="{escaped_link}" style="display:inline-block;padding:13px 22px;color:#ffffff;text-decoration:none;font-size:16px;line-height:20px;font-weight:800;">{escape(button_label)}</a>'
            '</td></tr></table>'
            f'<div style="margin-top:15px;font-size:12px;line-height:18px;color:#6f6557;">{escape(fallback_label)}<br>'
            f'<a href="{escaped_link}" style="color:#8a5a12;text-decoration:underline;word-break:break-all;">{escaped_link}</a></div>'
            '</td></tr></table>'
        )

    account_block = ""
    if account_url:
        raw_account_url = account_url.strip()
        parsed_account_url = urlparse(raw_account_url)
        if parsed_account_url.scheme.lower() in {"http", "https"} and parsed_account_url.netloc:
            escaped_account_url = escape(raw_account_url, quote=True)
            account_block = (
                '<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" '
                'style="margin:22px auto 0 auto;"><tr><td style="border-radius:9px;background:#c98224;">'
                f'<a href="{escaped_account_url}" style="display:inline-block;padding:13px 22px;color:#ffffff;'
                f'text-decoration:none;font-size:15px;line-height:20px;font-weight:800;">{escape(account_button_label)}</a>'
                '</td></tr></table>'
            )

    body = (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f2f4f7;">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        f'{escape(activity_name)} · {escape(date_value)} · {escape(time_value)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f4f7;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="max-width:620px;background:#ffffff;border:1px solid #e3e7ee;border-radius:16px;overflow:hidden;">'
        '<tr><td style="padding:28px 30px;background:#172033;">'
        '<div style="font-size:13px;line-height:18px;font-weight:800;letter-spacing:1.5px;color:#e4b85d;">PIANO ACADEMIE</div>'
        f'<div style="margin-top:8px;font-size:12px;line-height:18px;font-weight:700;letter-spacing:1px;color:#e4b85d;">{escape(eyebrow)}</div>'
        f'<div style="margin-top:5px;font-size:28px;line-height:35px;font-weight:800;color:#ffffff;">{escape(title)}</div>'
        '</td></tr>'
        '<tr><td style="padding:28px 30px 30px 30px;">'
        f'<p style="margin:0 0 10px 0;font-size:17px;line-height:25px;color:#172033;">{escape(greeting)}</p>'
        f'<p style="margin:0 0 22px 0;font-size:15px;line-height:23px;color:#5f6673;">{escape(intro)}</p>'
        f'{zoom_block}'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:0;background:#f8fafc;border:1px solid #e3e7ee;border-radius:12px;">'
        '<tr><td colspan="2" style="padding:18px 20px 12px 20px;font-size:20px;line-height:27px;font-weight:800;color:#172033;">'
        f'{escape(activity_name)}</td></tr>'
        f'<tr><td style="padding:8px 12px 8px 20px;width:34%;font-size:13px;font-weight:700;color:#667085;">{escape(student_label)}</td>'
        f'<td style="padding:8px 20px 8px 12px;font-size:15px;font-weight:700;color:#172033;">{escape(student_name)}</td></tr>'
        f'<tr><td style="padding:8px 12px 8px 20px;font-size:13px;font-weight:700;color:#667085;">{escape(date_label)}</td>'
        f'<td style="padding:8px 20px 8px 12px;font-size:15px;color:#172033;">{escape(date_value)}</td></tr>'
        f'<tr><td style="padding:8px 12px 8px 20px;font-size:13px;font-weight:700;color:#667085;">{escape(time_label)}</td>'
        f'<td style="padding:8px 20px 8px 12px;font-size:15px;font-weight:700;color:#172033;">{escape(time_value)}</td></tr>'
        f'<tr><td style="padding:8px 12px 8px 20px;font-size:13px;font-weight:700;color:#667085;">{escape(timezone_label)}</td>'
        f'<td style="padding:8px 20px 8px 12px;font-size:15px;color:#172033;">{escape(normalized_timezone)}</td></tr>'
        f'<tr><td style="padding:8px 12px 18px 20px;font-size:13px;font-weight:700;color:#667085;">{escape(location_label)}</td>'
        f'<td style="padding:8px 20px 18px 12px;font-size:15px;color:#172033;">{escape(displayed_location)}</td></tr>'
        '</table>'
        f'{account_block}'
        f'<p style="margin:22px 0 0 0;font-size:12px;line-height:19px;color:#7b8494;text-align:center;">{escape(footer)}</p>'
        '</td></tr></table>'
        '</td></tr></table></body></html>'
    )
    return subject, body


def _refresh_pending_email_reminder(
    db: Session,
    *,
    idempotency_key: str,
    recipient_email: str | None,
    subject: str,
    body: str,
    meeting_link_included: bool,
    now: datetime,
) -> Notification | None:
    notification = db.scalar(
        select(Notification).where(Notification.idempotency_key == idempotency_key).limit(1)
    )
    if notification is None:
        return None
    if notification.status in {NOTIFICATION_STATUS_PENDING, NOTIFICATION_STATUS_QUEUED}:
        notification.recipient_email = recipient_email
        notification.subject = subject
        notification.body_snapshot = body
        notification.payload_snapshot = {
            **(notification.payload_snapshot or {}),
            "body_format": "HTML",
            "meeting_link_included": meeting_link_included,
        }
        notification.updated_at = now
        db.add(notification)
    return notification


def _notification_already_exists(db: Session, *, idempotency_key: str) -> bool:
    return db.scalar(
        select(Notification.id).where(Notification.idempotency_key == idempotency_key).limit(1)
    ) is not None


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
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))
    teacher_id = effective_teacher_id_for_session(session_obj)
    teacher = db.scalar(select(Professor).where(Professor.id == teacher_id)) if teacher_id is not None else None
    location_label = (location.name or "").strip() if location is not None else ""
    teacher_label = professor_display_name(teacher)

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
        client_contact = (
            db.scalar(select(User).where(User.id == client_recipient.contact_id))
            if client_recipient.contact_id is not None
            else None
        )
        client_recipient_name = (
            f"{(client_contact.first_name or '').strip()} {(client_contact.last_name or '').strip()}".strip()
            if client_contact is not None
            else client_recipient.email
        )
        rendered = render_booking_confirmation_email(
            db,
            audience="CLIENT",
            recipient_name=client_recipient_name,
            student_name=student_label,
            activity_name=course_type.name,
            start_at=session_obj.start_at_utc,
            timezone_name=_recipient_course_timezone_name(client_contact, session_obj, location),
            location_name=location_label,
            teacher_name=teacher_label,
            language=client_contact.preferred_language if client_contact is not None else None,
            is_trial_course=bool(getattr(booking, "is_trial_course", False)),
        )
    else:
        rendered = None

    if client_recipient is not None and client_recipient.email is not None and rendered is not None:
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
            subject=rendered.subject,
            body_snapshot=rendered.body,
            payload_snapshot={"booking_id": str(booking.id), "body_format": rendered.body_format},
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

    teacher_recipient = _teacher_booking_notification_recipient(db, session_obj=session_obj, teacher=teacher)
    if teacher_recipient is not None:
        teacher_email, teacher_contact_id = teacher_recipient
        rendered = render_booking_confirmation_email(
            db,
            audience="ADMIN",
            recipient_name=teacher_label,
            student_name=student_label,
            activity_name=course_type.name,
            start_at=session_obj.start_at_utc,
            timezone_name=_course_timezone_name(session_obj, location),
            location_name=location_label,
            teacher_name=teacher_label,
            language="fr",
            is_trial_course=bool(getattr(booking, "is_trial_course", False)),
        )
        if rendered is not None:
            created = create_notification_if_new(
                db,
                notification_type=NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
                channel=CHANNEL_EMAIL,
                dispatch_mode=DISPATCH_MODE_IMMEDIATE,
                source_event_id=event.id,
                source=SOURCE_CLIENT_PORTAL,
                related_entity_type="booking",
                related_entity_id=booking.id,
                booking_id=booking.id,
                slot_id=session_obj.id,
                recipient_type="PROFESSOR",
                recipient_contact_id=teacher_contact_id,
                recipient_email=teacher_email,
                recipient_phone=None,
                subject=rendered.subject,
                body_snapshot=rendered.body,
                payload_snapshot={"booking_id": str(booking.id), "body_format": rendered.body_format},
                idempotency_key=_idempotency_key_for_booking_notification(
                    notification_type=NOTIFICATION_TYPE_TEACHER_BOOKING_CONFIRMATION,
                    booking_id=booking.id,
                    recipient_value=teacher_email,
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
        rendered = render_booking_confirmation_email(
            db,
            audience="ADMIN",
            recipient_name="Administration",
            student_name=student_label,
            activity_name=course_type.name,
            start_at=session_obj.start_at_utc,
            timezone_name=_course_timezone_name(session_obj, location),
            location_name=location_label,
            teacher_name=teacher_label,
            language="fr",
            is_trial_course=bool(getattr(booking, "is_trial_course", False)),
        )
        if rendered is None:
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
            subject=rendered.subject,
            body_snapshot=rendered.body,
            payload_snapshot={"booking_id": str(booking.id), "body_format": rendered.body_format},
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


def _schedule_client_waitlist_notification(
    db: Session,
    *,
    booking: Booking,
    occurred_at: datetime,
    promoted: bool,
    actor_user_id: UUID | None = None,
    source: str = SOURCE_CLIENT_PORTAL,
    actor_type: str = "client",
    waitlist_position: int | None = None,
) -> list[OrchestratedNotification]:
    session_obj, course_type = _booking_context(db, booking=booking)
    student = db.scalar(select(User).where(User.id == booking.user_id))
    student_label = (
        f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip()
        if student is not None
        else ""
    ) or (student.email if student is not None else str(booking.user_id))
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))
    location_label = (location.name or "").strip() if location is not None else ""
    recipient = resolve_client_booking_notification_recipient(db, booking=booking)
    if recipient is None or recipient.email is None:
        return []

    recipient_contact = (
        db.scalar(select(User).where(User.id == recipient.contact_id))
        if recipient.contact_id is not None
        else None
    )
    language = normalize_language(
        recipient_contact.preferred_language if recipient_contact is not None else None
    )
    timezone_name = _recipient_course_timezone_name(recipient_contact, session_obj, location)
    local_start, resolved_timezone = localize_datetime(session_obj.start_at_utc, timezone_name)
    date_label = f"{local_start.strftime('%d/%m/%Y %H:%M')} ({resolved_timezone})"

    notification_type = (
        NOTIFICATION_TYPE_CLIENT_WAITLIST_PROMOTED
        if promoted
        else NOTIFICATION_TYPE_CLIENT_WAITLIST_JOINED
    )
    event_type = EVENT_BOOKING_WAITLIST_PROMOTED if promoted else EVENT_BOOKING_WAITLISTED
    source = SOURCE_SYSTEM if promoted else source
    event = create_domain_event(
        db,
        event_type=event_type,
        source=source,
        actor_type="system" if promoted else actor_type,
        actor_id=None if promoted else actor_user_id,
        related_entity_type="booking",
        related_entity_id=booking.id,
        occurred_at=occurred_at,
        payload_json={
            "booking_id": str(booking.id),
            "session_id": str(session_obj.id),
            "course_type_id": str(course_type.id),
            "waitlist_position": waitlist_position,
        },
    )

    if language == "en":
        if promoted:
            subject = f"Your place is confirmed - {course_type.name}"
            preview = f"A place is now confirmed for {student_label}."
            title = "Your place is confirmed"
            intro = "A place has become available. Your booking is now confirmed."
            message = "You no longer need to take any action for this booking."
        else:
            subject = f"Waitlist registration - {course_type.name}"
            preview = f"{student_label} has been added to the waitlist."
            title = "Waitlist registration"
            intro = "The class is currently full. We have added you to the waitlist."
            message = "We will email you automatically if a place becomes available."
        rows = [
            ("Student", student_label),
            ("Activity", course_type.name),
            ("Date and time", date_label),
        ]
        if location_label:
            rows.append(("Location", location_label))
        if not promoted and waitlist_position is not None:
            rows.append(("Waitlist position", str(waitlist_position)))
        greeting = "Hello,"
        footer = "This email was sent automatically by Piano Académie."
    else:
        if promoted:
            subject = f"Votre place est confirmée - {course_type.name}"
            preview = f"Une place est maintenant confirmée pour {student_label}."
            title = "Votre place est confirmée"
            intro = "Une place s’est libérée. Votre réservation est désormais confirmée."
            message = "Vous n’avez aucune action supplémentaire à effectuer pour cette réservation."
        else:
            subject = f"Inscription sur liste d’attente - {course_type.name}"
            preview = f"{student_label} a été ajouté(e) à la liste d’attente."
            title = "Inscription sur liste d’attente"
            intro = "Le cours est actuellement complet. Nous vous avons inscrit(e) sur la liste d’attente."
            message = "Nous vous préviendrons automatiquement par e-mail si une place se libère."
        rows = [
            ("Élève", student_label),
            ("Activité", course_type.name),
            ("Date et horaire", date_label),
        ]
        if location_label:
            rows.append(("Lieu", location_label))
        if not promoted and waitlist_position is not None:
            rows.append(("Position sur la liste", str(waitlist_position)))
        greeting = "Bonjour,"
        footer = "Cet e-mail a été envoyé automatiquement par Piano Académie."

    body = render_branded_email(
        preview=preview,
        eyebrow="LISTE D’ATTENTE" if language != "en" else "WAITLIST",
        title=title,
        greeting=greeting,
        intro=intro,
        rows=rows,
        message=message,
        footer=footer,
    )
    created = create_notification_if_new(
        db,
        notification_type=notification_type,
        channel=CHANNEL_EMAIL,
        dispatch_mode=DISPATCH_MODE_IMMEDIATE,
        source_event_id=event.id,
        source=source,
        related_entity_type="booking",
        related_entity_id=booking.id,
        booking_id=booking.id,
        slot_id=session_obj.id,
        recipient_type=recipient.contact_type,
        recipient_contact_id=recipient.contact_id,
        recipient_email=recipient.email,
        recipient_phone=None,
        subject=subject,
        body_snapshot=body,
        payload_snapshot={
            "booking_id": str(booking.id),
            "body_format": "HTML",
            "waitlist_position": waitlist_position,
        },
        idempotency_key=_idempotency_key_for_booking_notification(
            notification_type=notification_type,
            booking_id=booking.id,
            recipient_value=recipient.email,
            source_event_id=event.id,
        ),
        scheduled_for=occurred_at,
        status=NOTIFICATION_STATUS_PENDING,
    )
    if created is None:
        return []
    return [OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE)]


def schedule_waitlist_joined_notification(
    db: Session,
    *,
    booking: Booking,
    actor_user_id: UUID,
    occurred_at: datetime,
    waitlist_position: int,
    source: str = SOURCE_CLIENT_PORTAL,
    actor_type: str = "client",
) -> list[OrchestratedNotification]:
    return _schedule_client_waitlist_notification(
        db,
        booking=booking,
        actor_user_id=actor_user_id,
        source=source,
        actor_type=actor_type,
        occurred_at=occurred_at,
        promoted=False,
        waitlist_position=waitlist_position,
    )


def schedule_waitlist_promoted_notification(
    db: Session,
    *,
    booking: Booking,
    occurred_at: datetime,
) -> list[OrchestratedNotification]:
    return _schedule_client_waitlist_notification(
        db,
        booking=booking,
        occurred_at=occurred_at,
        promoted=True,
    )


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
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))

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
        client_contact = (
            db.scalar(select(User).where(User.id == client_recipient.contact_id))
            if client_recipient.contact_id is not None
            else None
        )
        client_subject, client_body = _body_for_booking_notification(
            is_cancellation=True,
            course_type_name=course_type.name,
            start_at=session_obj.start_at_utc,
            student_label=student_label,
            timezone_name=_recipient_course_timezone_name(client_contact, session_obj, location),
        )
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
            subject=client_subject,
            body_snapshot=client_body,
            payload_snapshot={"booking_id": str(booking.id), "body_format": "HTML"},
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

    admin_subject, admin_body = _body_for_booking_notification(
        is_cancellation=True,
        course_type_name=course_type.name,
        start_at=session_obj.start_at_utc,
        student_label=student_label,
        timezone_name=_course_timezone_name(session_obj, location),
    )
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
            subject=admin_subject,
            body_snapshot=admin_body,
            payload_snapshot={"booking_id": str(booking.id), "body_format": "HTML"},
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
    local_start, resolved_timezone = localize_datetime(slot.start_at_utc, slot.timezone)
    body = (
        f"Creneau annule.\nTitre: {slot.title}\n"
        f"Debut: {local_start.strftime('%d/%m/%Y %H:%M')} ({resolved_timezone})\n"
    )
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


def schedule_auto_low_attendance_cancellation_notifications(
    db: Session,
    *,
    slot: CourseSession,
    bookings: list[Booking],
    booked_count: int,
    minimum_attendees: int,
    occurred_at: datetime,
) -> list[OrchestratedNotification]:
    course_type = db.scalar(select(CourseType).where(CourseType.id == slot.course_type_id))
    location = db.scalar(select(Location).where(Location.id == slot.location_id))
    teacher_id = effective_teacher_id_for_session(slot)
    teacher = db.scalar(select(Professor).where(Professor.id == teacher_id)) if teacher_id is not None else None
    local_start, timezone_name = localize_datetime(slot.start_at_utc, slot.timezone or (location.timezone if location else None))
    location_name = (location.name or "").strip() if location is not None else ""
    location_address = " ".join(
        part for part in (
            (location.address_line or "").strip() if location is not None else "",
            (location.city or "").strip() if location is not None else "",
        ) if part
    )
    teacher_name = professor_display_name(teacher)
    common_context: dict[str, object] = {
        "activity_name": course_type.name if course_type is not None else slot.title,
        "session_date": local_start.strftime("%d/%m/%Y"),
        "session_time": local_start.strftime("%H:%M"),
        "timezone": timezone_name,
        "location_name": location_name,
        "location_address": location_address,
        "teacher_name": teacher_name,
        "booked_count": booked_count,
        "minimum_attendees": minimum_attendees,
    }
    event = create_domain_event(
        db,
        event_type=EVENT_SLOT_AUTO_CANCELLED_LOW_ATTENDANCE,
        source=SOURCE_SCHEDULER,
        actor_type="system",
        actor_id=None,
        related_entity_type="slot",
        related_entity_id=slot.id,
        occurred_at=occurred_at,
        payload_json={"slot_id": str(slot.id), **common_context},
    )
    out: list[OrchestratedNotification] = []

    for booking in bookings:
        recipient = resolve_client_booking_notification_recipient(db, booking=booking)
        if recipient is None or recipient.email is None:
            continue
        contact = (
            db.scalar(select(User).where(User.id == recipient.contact_id))
            if recipient.contact_id is not None
            else None
        )
        student = db.scalar(select(User).where(User.id == booking.user_id))
        recipient_name = (
            f"{(contact.first_name or '').strip()} {(contact.last_name or '').strip()}".strip()
            if contact is not None
            else recipient.email
        )
        student_name = (
            f"{(student.first_name or '').strip()} {(student.last_name or '').strip()}".strip()
            if student is not None
            else ""
        )
        template = resolve_predefined_template(
            db,
            code=PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_PARTICIPANT,
            language=contact.preferred_language if contact is not None else None,
        )
        context = {**common_context, "recipient_name": recipient_name, "student_name": student_name}
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_AUTO_CANCEL_PARTICIPANT,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_SCHEDULER,
            related_entity_type="booking",
            related_entity_id=booking.id,
            booking_id=booking.id,
            slot_id=slot.id,
            recipient_type=recipient.contact_type,
            recipient_contact_id=recipient.contact_id,
            recipient_email=recipient.email,
            recipient_phone=None,
            subject=render_template_content(str(template.get("subject") or ""), context),
            body_snapshot=render_template_content(str(template.get("body") or ""), context),
            payload_snapshot={"booking_id": str(booking.id), "body_format": template.get("body_format", "HTML")},
            idempotency_key=f"{NOTIFICATION_TYPE_AUTO_CANCEL_PARTICIPANT}:{booking.id}:{recipient.email}",
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))

    if teacher is not None and (teacher.email or "").strip() and bool(teacher.active):
        template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_TEACHER, language="fr")
        context = {**common_context, "recipient_name": teacher_name}
        teacher_email = teacher.email.strip().lower()
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_AUTO_CANCEL_TEACHER,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_SCHEDULER,
            related_entity_type="slot",
            related_entity_id=slot.id,
            booking_id=None,
            slot_id=slot.id,
            recipient_type="PROFESSOR",
            recipient_contact_id=teacher.id,
            recipient_email=teacher_email,
            recipient_phone=None,
            subject=render_template_content(str(template.get("subject") or ""), context),
            body_snapshot=render_template_content(str(template.get("body") or ""), context),
            payload_snapshot={"slot_id": str(slot.id), "body_format": template.get("body_format", "HTML")},
            idempotency_key=f"{NOTIFICATION_TYPE_AUTO_CANCEL_TEACHER}:{slot.id}:{teacher_email}",
            scheduled_for=occurred_at,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is not None:
            out.append(OrchestratedNotification(notification_id=created.id, queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE))

    template = resolve_predefined_template(db, code=PREDEFINED_EMAIL_TEMPLATE_AUTO_CANCEL_ADMIN, language="fr")
    for recipient in resolve_admin_cancellation_recipients(db):
        if recipient.email is None:
            continue
        created = create_notification_if_new(
            db,
            notification_type=NOTIFICATION_TYPE_AUTO_CANCEL_ADMIN,
            channel=CHANNEL_EMAIL,
            dispatch_mode=DISPATCH_MODE_IMMEDIATE,
            source_event_id=event.id,
            source=SOURCE_SCHEDULER,
            related_entity_type="slot",
            related_entity_id=slot.id,
            booking_id=None,
            slot_id=slot.id,
            recipient_type=recipient.contact_type,
            recipient_contact_id=recipient.contact_id,
            recipient_email=recipient.email,
            recipient_phone=None,
            subject=render_template_content(str(template.get("subject") or ""), common_context),
            body_snapshot=render_template_content(str(template.get("body") or ""), common_context),
            payload_snapshot={"slot_id": str(slot.id), "body_format": template.get("body_format", "HTML")},
            idempotency_key=f"{NOTIFICATION_TYPE_AUTO_CANCEL_ADMIN}:{slot.id}:{recipient.email}",
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
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))
    student = db.scalar(select(User).where(User.id == booking.user_id))
    teacher_id = effective_teacher_id_for_session(session_obj)
    teacher = db.scalar(select(Professor).where(Professor.id == teacher_id)) if teacher_id is not None else None

    if not recipients:
        return []

    event = None

    def _event_id() -> UUID:
        nonlocal event
        if event is None:
            event = create_domain_event(
                db,
                event_type=EVENT_BOOKING_REMINDER_DUE,
                source=SOURCE_SCHEDULER,
                actor_type="system",
                actor_id=None,
                related_entity_type="booking",
                related_entity_id=booking.id,
                occurred_at=now,
                payload_json={
                    "booking_id": str(booking.id),
                    "session_id": str(session_obj.id),
                    "course_type_id": str(course_type.id),
                },
            )
        return event.id

    out: list[OrchestratedNotification] = []
    booking_start_at = booking.student_start_at_utc or session_obj.start_at_utc
    booking_end_at = booking.student_end_at_utc or session_obj.end_at_utc
    student_name = _reminder_display_name(student, fallback=str(booking.user_id))
    is_online = bool(location.is_online) if location is not None else course_type.mode == DeliveryMode.ONLINE
    location_name = "Online" if is_online else ((location.name or "").strip() if location is not None else "-")
    meeting_link = None
    if is_online:
        meeting_link = (session_obj.zoom_link or (teacher.zoom_link if teacher is not None else None) or "").strip() or None

    for recipient in recipients:
        recipient_user = (
            db.scalar(select(User).where(User.id == recipient.contact_id))
            if recipient.contact_id is not None
            else None
        )
        recipient_timezone = _recipient_course_timezone_name(recipient_user, session_obj, location)
        if email_enabled:
            scheduled_for = booking_start_at - timedelta(minutes=email_offset_minutes)
            status = NOTIFICATION_STATUS_PENDING
            failure_reason = None
            if recipient.email is None:
                status = NOTIFICATION_STATUS_SKIPPED
                failure_reason = "skipped because no email"
            recipient_name = _reminder_display_name(recipient_user, fallback=recipient.email or "client")
            language = recipient_user.preferred_language if recipient_user is not None else None
            subject, body = _build_lesson_reminder_email(
                recipient_name=recipient_name,
                student_name=student_name,
                course_type_name=course_type.name,
                start_at=booking_start_at,
                end_at=booking_end_at,
                timezone_name=recipient_timezone,
                location_name=location_name,
                meeting_link=meeting_link,
                language=language,
                account_url=f"{resolve_frontend_base_url(db).rstrip('/')}/client?tab=planning",
            )
            idempotency_key = _idempotency_key_for_reminder(
                notification_type=NOTIFICATION_TYPE_REMINDER_EMAIL,
                booking_id=booking.id,
                recipient_contact_id=recipient.contact_id,
                offset_minutes=email_offset_minutes,
                scheduled_for=scheduled_for,
            )
            existing_email_reminder = _refresh_pending_email_reminder(
                db,
                idempotency_key=idempotency_key,
                recipient_email=recipient.email,
                subject=subject,
                body=body,
                meeting_link_included=bool(meeting_link),
                now=now,
            )
            if existing_email_reminder is None:
                created = create_notification_if_new(
                    db,
                    notification_type=NOTIFICATION_TYPE_REMINDER_EMAIL,
                    channel=CHANNEL_EMAIL,
                    dispatch_mode=DISPATCH_MODE_SCHEDULED,
                    source_event_id=_event_id(),
                    source=SOURCE_SCHEDULER,
                    related_entity_type="booking",
                    related_entity_id=booking.id,
                    booking_id=booking.id,
                    slot_id=session_obj.id,
                    recipient_type=recipient.contact_type,
                    recipient_contact_id=recipient.contact_id,
                    recipient_email=recipient.email,
                    recipient_phone=None,
                    subject=subject,
                    body_snapshot=body,
                    payload_snapshot={
                        "offset_minutes": email_offset_minutes,
                        "body_format": "HTML",
                        "meeting_link_included": bool(meeting_link),
                    },
                    idempotency_key=idempotency_key,
                    scheduled_for=scheduled_for,
                    status=status,
                    failure_reason=failure_reason,
                )
                if created is not None and status == NOTIFICATION_STATUS_PENDING:
                    out.append(
                        OrchestratedNotification(
                            notification_id=created.id,
                            queue_name=QUEUE_NOTIFICATIONS_SCHEDULED,
                        )
                    )

        if sms_enabled:
            scheduled_for = booking_start_at - timedelta(minutes=sms_offset_minutes)
            status = NOTIFICATION_STATUS_PENDING
            failure_reason = None
            if recipient.phone is None:
                status = NOTIFICATION_STATUS_SKIPPED
                failure_reason = "skipped because no phone"
            sms_period = _reminder_period_label(
                start_at=booking_start_at,
                end_at=booking_end_at,
                timezone_name=recipient_timezone,
            )
            sms_body = f"Rappel: {course_type.name} le {sms_period}."
            if meeting_link:
                sms_body = f"{sms_body} Lien: {meeting_link}"
            idempotency_key = _idempotency_key_for_reminder(
                notification_type=NOTIFICATION_TYPE_REMINDER_SMS,
                booking_id=booking.id,
                recipient_contact_id=recipient.contact_id,
                offset_minutes=sms_offset_minutes,
                scheduled_for=scheduled_for,
            )
            if not _notification_already_exists(db, idempotency_key=idempotency_key):
                created = create_notification_if_new(
                    db,
                    notification_type=NOTIFICATION_TYPE_REMINDER_SMS,
                    channel=CHANNEL_SMS,
                    dispatch_mode=DISPATCH_MODE_SCHEDULED,
                    source_event_id=_event_id(),
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
                    body_snapshot=sms_body,
                    payload_snapshot={
                        "offset_minutes": sms_offset_minutes,
                        "meeting_link_included": bool(meeting_link),
                    },
                    idempotency_key=idempotency_key,
                    scheduled_for=scheduled_for,
                    status=status,
                    failure_reason=failure_reason,
                )
                if created is not None and status == NOTIFICATION_STATUS_PENDING:
                    out.append(
                        OrchestratedNotification(
                            notification_id=created.id,
                            queue_name=QUEUE_NOTIFICATIONS_SCHEDULED,
                        )
                    )

    return out
