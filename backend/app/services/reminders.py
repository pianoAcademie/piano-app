from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationSenderCategory,
    EmailReminder,
    MessageFormat,
    ReminderStatus,
)
from app.models.user import User
from app.services.communication_journal import COMMUNICATION_TYPE_COURSE_REMINDER, log_communication

logger = logging.getLogger(__name__)


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
        default_hours = 1
        attribute_name = "sms_reminder_hours_before_start"
    else:
        setting_key = "reminder_hours_before_start"
        default_hours = 24
        attribute_name = "email_reminder_hours_before_start"

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
    scheduled_for = session_obj.start_at_utc - timedelta(hours=reminder_hours)

    reminder = db.scalar(
        select(EmailReminder).where(
            EmailReminder.booking_id == booking.id,
            EmailReminder.scheduled_for_utc == scheduled_for,
        )
    )

    if reminder is None:
        reminder = EmailReminder(
            booking_id=booking.id,
            scheduled_for_utc=scheduled_for,
            status=ReminderStatus.PENDING,
        )
        db.add(reminder)
        return reminder

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


def _format_session_datetime(session_obj: CourseSession, timezone_preference: str | None, location: Location) -> str:
    tz_name = timezone_preference or location.timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz_name = location.timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz_name = "UTC"
            tz = ZoneInfo("UTC")

    local_dt = session_obj.start_at_utc.astimezone(tz)
    return f"{local_dt.strftime('%Y-%m-%d %H:%M')} ({tz_name})"


def _build_email_payload(
    db: Session,
    user: User,
    session_obj: CourseSession,
    course_type: CourseType,
    location: Location,
) -> tuple[str, str]:
    start_human = _format_session_datetime(session_obj, user.timezone, location)
    location_label = "Online" if location.is_online else location.name

    subject = f"Rappel cours: {course_type.name} - {start_human}"
    lines = [
        f"Bonjour {user.email},",
        "",
        f"Rappel de votre cours: {course_type.name}",
        f"Date: {start_human}",
        f"Lieu: {location_label}",
        f"Description: {session_obj.description or session_obj.title}",
    ]

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
            or session_obj.start_at_utc <= now
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
                subject, body = _build_email_payload(db, user, session_obj, course_type, location)
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

    return ReminderJobResult(created=created, sent=sent, skipped=skipped, failed=failed)
