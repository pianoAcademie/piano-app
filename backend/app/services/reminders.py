from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationLog,
    CommunicationDeliveryStatus,
    CommunicationSenderCategory,
    EmailReminder,
    MessageFormat,
    ReminderStatus,
)
from app.models.user import User
from app.services.local_time import resolve_timezone_name
from app.services.communication_journal import (
    COMMUNICATION_TYPE_COURSE_REMINDER,
    COMMUNICATION_TYPE_OPERATIONAL,
    log_communication,
)
from app.services.email_delivery import send_email
from app.services.session_teachers import effective_professor_ids_for_session, professor_display_name

logger = logging.getLogger(__name__)
HTML_TAG_RE = re.compile(r"<\s*[a-z!/][^>]*>", re.IGNORECASE)
EMAIL_REMINDER_HOURS_BEFORE_START = 24
SMS_REMINDER_HOURS_BEFORE_START = 1


def _booking_start_at_utc(booking: Booking, session_obj: CourseSession) -> datetime:
    return booking.student_start_at_utc or session_obj.start_at_utc


def _booking_end_at_utc(booking: Booking, session_obj: CourseSession) -> datetime:
    return booking.student_end_at_utc or session_obj.end_at_utc


@dataclass(frozen=True)
class ReminderJobResult:
    created: int
    sent: int
    skipped: int
    failed: int


def get_setting_int(db: Session, key: str, default: int) -> int:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        return default

    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return default


def get_setting_str(db: Session, key: str, default: str) -> str:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is None:
        return default
    value = (setting.value or "").strip()
    return value or default


def _public_base_url(db: Session) -> str:
    website = get_setting_str(db, "config_account_website", "http://localhost:3000")
    if website.startswith("http://") or website.startswith("https://"):
        return website.rstrip("/")
    return f"https://{website.rstrip('/')}"


def _resolve_activity_reminder_hours(db: Session, *, course_type_id: UUID, channel: str) -> int:
    if channel == "SMS":
        setting_key = "sms_reminder_hours_before_start"
        default_hours = SMS_REMINDER_HOURS_BEFORE_START
        attribute_name = "sms_reminder_hours_before_start"
    else:
        setting_key = "reminder_hours_before_start"
        default_hours = EMAIL_REMINDER_HOURS_BEFORE_START
        attribute_name = "email_reminder_hours_before_start"

    if channel != "SMS":
        return EMAIL_REMINDER_HOURS_BEFORE_START

    fallback = get_setting_int(db, setting_key, default_hours)
    if fallback < 0:
        fallback = default_hours

    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if course_type is None:
        return fallback

    raw_override = getattr(course_type, attribute_name, None)
    if raw_override is None:
        return fallback
    try:
        override = int(raw_override)
    except (TypeError, ValueError):
        return fallback
    if override < 0:
        return fallback
    return override


def ensure_booking_reminder(
    db: Session,
    *,
    booking: Booking,
    session_obj: CourseSession,
    now: datetime,
) -> EmailReminder | None:
    if booking.status != BookingStatus.BOOKED:
        return None

    reminder_hours = _resolve_activity_reminder_hours(
        db,
        course_type_id=session_obj.course_type_id,
        channel="EMAIL",
    )
    scheduled_for = _booking_start_at_utc(booking, session_obj) - timedelta(hours=reminder_hours)

    reminder = db.scalar(
        select(EmailReminder)
        .where(EmailReminder.booking_id == booking.id)
        .order_by(EmailReminder.created_at.desc())
    )

    if reminder is None:
        reminder = EmailReminder(
            booking_id=booking.id,
            scheduled_for_utc=scheduled_for,
            status=ReminderStatus.PENDING,
        )
        db.add(reminder)
        return reminder

    if reminder.status == ReminderStatus.SENT:
        return reminder

    if reminder.scheduled_for_utc != scheduled_for:
        reminder.scheduled_for_utc = scheduled_for

    if reminder.status in (ReminderStatus.SKIPPED, ReminderStatus.FAILED):
        reminder.status = ReminderStatus.PENDING
        reminder.sent_at = None
        reminder.provider_message_id = None
        reminder.error_message = None

    return reminder


def skip_pending_reminders_for_booking(db: Session, *, booking_id: UUID | str, reason: str, now: datetime) -> int:
    reminders = db.scalars(
        select(EmailReminder).where(
            EmailReminder.booking_id == booking_id,
            EmailReminder.status == ReminderStatus.PENDING,
        )
    ).all()

    for reminder in reminders:
        reminder.status = ReminderStatus.SKIPPED
        reminder.error_message = reason
        reminder.sent_at = now

    return len(reminders)


def backfill_future_booking_reminders(db: Session, *, now: datetime, limit: int = 500) -> int:
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.status == BookingStatus.BOOKED,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc > now,
        )
        .limit(limit)
    ).all()

    created_or_updated = 0
    for booking, session_obj in rows:
        reminder = ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)
        if reminder is not None:
            created_or_updated += 1

    return created_or_updated


def _format_session_datetime(
    session_obj: CourseSession,
    timezone_preference: str | None,
    location: Location,
    *,
    booking: Booking | None = None,
) -> str:
    tz_name = resolve_timezone_name(timezone_preference, location.timezone, session_obj.timezone)
    tz = ZoneInfo(tz_name)

    start_at = _booking_start_at_utc(booking, session_obj) if booking is not None else session_obj.start_at_utc
    end_at = _booking_end_at_utc(booking, session_obj) if booking is not None else session_obj.end_at_utc
    local_start = start_at.astimezone(tz)
    local_end = end_at.astimezone(tz)
    if local_start.date() == local_end.date():
        return f"{local_start.strftime('%Y-%m-%d %H:%M')} - {local_end.strftime('%H:%M')} ({tz_name})"
    return f"{local_start.strftime('%Y-%m-%d %H:%M')} - {local_end.strftime('%Y-%m-%d %H:%M')} ({tz_name})"


def _build_email_payload(
    db: Session,
    user: User,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
    booking: Booking | None = None,
) -> tuple[str, str]:
    start_human = _format_session_datetime(session_obj, user.timezone, location, booking=booking)
    location_label = "Online" if location.is_online else location.name

    subject = f"Rappel cours: {course_type.name} - {start_human}"
    lines = [
        f"Bonjour {user.email},",
        "",
        f"Rappel de votre cours: {course_type.name}",
        f"Date: {start_human}",
        f"Lieu: {location_label}",
    ]
    if not location.is_online and (location.address_line or "").strip():
        lines.append(f"Adresse: {location.address_line.strip()}")
    if not location.is_online and (location.access_instructions or "").strip():
        lines.append(f"Code de la porte principale: {location.access_instructions.strip()}")

    professor_ids = effective_professor_ids_for_session(db, session_obj=session_obj)
    if professor_ids:
        professors = db.scalars(select(Professor).where(Professor.id.in_(professor_ids))).all()
        professor_by_id = {professor.id: professor for professor in professors}
        professor_names = [
            professor_display_name(professor_by_id[professor_id])
            for professor_id in professor_ids
            if professor_id in professor_by_id and professor_display_name(professor_by_id[professor_id])
        ]
        if professor_names:
            lines.append(f"Professeur{'s' if len(professor_names) > 1 else ''}: {', '.join(professor_names)}")

    lines.append(f"Description: {session_obj.description or session_obj.title}")

    if location.is_online and session_obj.zoom_link:
        lines.append(f"Lien Zoom: {session_obj.zoom_link}")

    lines.append("")
    if user.communication_optout_token:
        lines.append(
            "Se desinscrire des rappels non transactionnels: "
            f"{_public_base_url(db)}/api/v1/clients/communication/optout"
            f"?token={user.communication_optout_token}&channel=EMAIL"
        )
        lines.append("")
    lines.append("Piano Academie")

    return subject, "\n".join(lines)


def _professor_note_source(session_id: UUID) -> str:
    return f"SYSTEM_PROFESSOR_NOTE_REMINDER:{session_id}"


def _looks_like_html(value: str) -> bool:
    return bool(HTML_TAG_RE.search(value or ""))


def _build_professor_note_email_payload(
    *,
    professor_email: str,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
    note: str,
) -> tuple[str, str, str]:
    start_human = _format_session_datetime(session_obj, location.timezone, location)
    location_label = "Online" if location.is_online else location.name
    subject = f"Rappel professeur (24h): {course_type.name} - {start_human}"
    clean_note = (note or "").strip()
    if _looks_like_html(clean_note):
        body = (
            f"<p>Bonjour {professor_email},</p>"
            f"<p>Rappel de votre cours: <strong>{course_type.name}</strong><br>"
            f"Date: {start_human}<br>"
            f"Lieu: {location_label}</p>"
            f"<p><strong>Note administration:</strong></p>{clean_note}"
            "<p>Piano Academie</p>"
        )
        return subject, body, "HTML"

    lines = [
        f"Bonjour {professor_email},",
        "",
        f"Rappel de votre cours: {course_type.name}",
        f"Date: {start_human}",
        f"Lieu: {location_label}",
        "",
        "Note administration:",
        clean_note,
        "",
        "Piano Academie",
    ]
    return subject, "\n".join(lines), "TEXT"


def _send_professor_note_reminders(db: Session, *, now: datetime, limit: int) -> tuple[int, int, int]:
    reminder_time = now + timedelta(hours=24)
    rows = db.execute(
        select(CourseSession, CourseType, Location, Professor)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc > now,
            CourseSession.start_at_utc <= reminder_time,
            CourseSession.professor_reminder_note.is_not(None),
        )
        .order_by(CourseSession.start_at_utc.asc())
        .limit(limit)
    ).all()

    sent = 0
    skipped = 0
    failed = 0

    for session_obj, course_type, location, professor in rows:
        note = (session_obj.professor_reminder_note or "").strip()
        if not note:
            skipped += 1
            continue
        recipient = (professor.email or "").strip().lower()
        if not recipient:
            skipped += 1
            continue

        source = _professor_note_source(session_obj.id)
        already_sent = db.scalar(select(CommunicationLog.id).where(CommunicationLog.source == source).limit(1))
        if already_sent is not None:
            skipped += 1
            continue

        recipient_user_id = db.scalar(select(User.id).where(func.lower(User.email) == recipient).limit(1))
        subject, body, body_format = _build_professor_note_email_payload(
            professor_email=recipient,
            session_obj=session_obj,
            course_type=course_type,
            location=location,
            note=note,
        )
        try:
            send_email(
                to_email=recipient,
                subject=subject,
                body=body,
                body_format=body_format,
                context=source,
                sender_category=CommunicationSenderCategory.SYSTEM,
                sender_label="Systeme",
                professor_id=session_obj.professor_id,
                recipient_user_id=recipient_user_id,
                communication_type=COMMUNICATION_TYPE_OPERATIONAL,
            )
            sent += 1
        except Exception:  # pragma: no cover - defensive runtime guard
            failed += 1

    return sent, skipped, failed


def run_send_reminders_job(db: Session, *, now: datetime, limit: int = 200) -> ReminderJobResult:
    created = backfill_future_booking_reminders(db, now=now, limit=limit)

    rows = db.execute(
        select(EmailReminder, Booking, User, CourseSession, CourseType, Location)
        .join(Booking, Booking.id == EmailReminder.booking_id)
        .join(User, User.id == Booking.user_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            EmailReminder.status == ReminderStatus.PENDING,
            EmailReminder.scheduled_for_utc <= now,
        )
        .order_by(EmailReminder.scheduled_for_utc.asc())
        .limit(limit)
    ).all()

    sent = 0
    skipped = 0
    failed = 0

    for reminder, booking, user, session_obj, course_type, location in rows:
        subject = ""
        body = ""
        delivery_status = CommunicationDeliveryStatus.UNKNOWN
        error_message: str | None = None

        if (
            booking.status != BookingStatus.BOOKED
            or session_obj.status != SessionStatus.SCHEDULED
            or _booking_start_at_utc(booking, session_obj) <= now
        ):
            reminder.status = ReminderStatus.SKIPPED
            reminder.sent_at = now
            reminder.error_message = "Booking/session not active"
            error_message = reminder.error_message
            delivery_status = CommunicationDeliveryStatus.SKIPPED
            skipped += 1
        elif not user.email_opt_in or not user.lesson_reminder_email_opt_in:
            reminder.status = ReminderStatus.SKIPPED
            reminder.sent_at = now
            reminder.error_message = "Client opt-out email reminders"
            error_message = reminder.error_message
            delivery_status = CommunicationDeliveryStatus.SKIPPED
            skipped += 1
        else:
            try:
                subject, body = _build_email_payload(db, user, session_obj, course_type, location, booking=booking)
                message_id = f"dev-{uuid4()}"
                logger.info("Reminder sent | id=%s | to=%s | subject=%s | body=%s", message_id, user.email, subject, body)

                reminder.status = ReminderStatus.SENT
                reminder.sent_at = now
                reminder.provider_message_id = message_id
                reminder.error_message = None
                delivery_status = CommunicationDeliveryStatus.DELIVERED
                sent += 1
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                reminder.status = ReminderStatus.FAILED
                reminder.sent_at = now
                reminder.error_message = str(exc)
                error_message = reminder.error_message
                delivery_status = CommunicationDeliveryStatus.FAILED
                failed += 1

        if not subject:
            subject = f"Rappel cours: {course_type.name}"
        if not body:
            body = reminder.error_message or "Rappel de cours genere automatiquement par le systeme."

        log_communication(
            db=db,
            channel=CommunicationChannel.EMAIL,
            source="SYSTEM_EMAIL_REMINDER",
            communication_type=COMMUNICATION_TYPE_COURSE_REMINDER,
            sender_category=CommunicationSenderCategory.SYSTEM,
            sender_label="Systeme",
            recipient=(user.email or "").strip().lower() or "-",
            recipient_user_id=user.id,
            subject=subject,
            content=body,
            content_format=MessageFormat.TEXT,
            delivery_status=delivery_status,
            provider_message_id=reminder.provider_message_id,
            provider="LOG",
            error_message=error_message,
            occurred_at=reminder.sent_at or reminder.created_at or now,
            delivered_at=(reminder.sent_at if delivery_status == CommunicationDeliveryStatus.DELIVERED else None),
            failed_at=(reminder.sent_at if delivery_status == CommunicationDeliveryStatus.FAILED else None),
        )

    professor_sent, professor_skipped, professor_failed = _send_professor_note_reminders(db, now=now, limit=limit)

    return ReminderJobResult(
        created=created,
        sent=sent + professor_sent,
        skipped=skipped + professor_skipped,
        failed=failed + professor_failed,
    )
