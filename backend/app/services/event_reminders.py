from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.event import (
    SchoolEvent,
    SchoolEventRegistration,
    SchoolEventRegistrationStatus,
    SchoolEventSlot,
    SchoolEventSlotStatus,
    SchoolEventStatus,
)
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationLog,
    CommunicationSenderCategory,
    MessageFormat,
)
from app.models.user import User
from app.services.client_email import deliverable_client_email
from app.services.communication_journal import COMMUNICATION_TYPE_EVENT_REMINDER, log_communication
from app.services.email_delivery import send_email
from app.services.local_time import resolve_timezone_name
from app.services.messaging_templates import resolve_frontend_base_url


DEFAULT_EVENT_REMINDER_HOURS_BEFORE_START = 24
EVENT_REMINDER_SETTING_KEY = "school_event_reminder_hours_before_start"


@dataclass(frozen=True)
class EventReminderJobResult:
    checked: int
    sent: int
    skipped: int
    failed: int


def school_event_reminder_hours(db: Session) -> int:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == EVENT_REMINDER_SETTING_KEY))
    if setting is None:
        return DEFAULT_EVENT_REMINDER_HOURS_BEFORE_START
    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return DEFAULT_EVENT_REMINDER_HOURS_BEFORE_START
    return value if 1 <= value <= 720 else DEFAULT_EVENT_REMINDER_HOURS_BEFORE_START


def event_reminder_source(*, event_id: UUID, group_id: UUID, start_at_utc: datetime) -> str:
    start_key = start_at_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"SCHOOL_EVENT_REMINDER:{event_id}:{group_id}:{start_key}"


def _event_datetime(slot: SchoolEventSlot, language: str, recipient_timezone: str | None) -> str:
    timezone_name = resolve_timezone_name(recipient_timezone, slot.timezone)
    timezone = ZoneInfo(timezone_name)
    local_start = slot.start_at_utc.astimezone(timezone)
    local_end = slot.end_at_utc.astimezone(timezone)
    if language == "en":
        return f"{local_start.strftime('%A %d %B %Y, %H:%M')}–{local_end.strftime('%H:%M')} ({timezone_name})"
    return f"{local_start.strftime('%d/%m/%Y à %H:%M')}–{local_end.strftime('%H:%M')} ({timezone_name})"


def _location_label(location: Location | None, language: str) -> str:
    if location is None:
        return "Location to be confirmed" if language == "en" else "Lieu à préciser"
    if location.is_online:
        return "Online" if language == "en" else "En ligne"
    address = ", ".join(part for part in [location.address_line, location.city] if part)
    return f"{location.name} — {address}" if address else location.name


def _message(
    *,
    db: Session,
    booker: User,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    location: Location | None,
    participant_names: list[str],
    group_id: UUID,
) -> tuple[str, str]:
    language = "en" if (booker.preferred_language or "fr").strip().lower().startswith("en") else "fr"
    title = event.title_en if language == "en" and event.title_en else event.title_fr
    when = _event_datetime(slot, language, booker.timezone)
    where = _location_label(location, language)
    base_url = resolve_frontend_base_url(db).rstrip("/")
    event_url = f"{base_url}/events/{event.slug}{'?lang=en' if language == 'en' else ''}"
    calendar_url = f"{base_url}/events/calendar/{group_id}"
    if language == "en":
        return (
            f"Reminder — {title}",
            "\n".join(
                [
                    f"Hello {(booker.first_name or '').strip() or booker.email},",
                    "",
                    f"This is a reminder for {title}.",
                    f"Date: {when}",
                    f"Location: {where}",
                    f"Participants: {', '.join(participant_names)}",
                    "",
                    f"View the event: {event_url}",
                    f"Add to calendar: {calendar_url}",
                    "",
                    "Piano Académie",
                ]
            ),
        )
    return (
        f"Rappel — {title}",
        "\n".join(
            [
                f"Bonjour {(booker.first_name or '').strip() or booker.email},",
                "",
                f"Nous vous rappelons votre inscription à {title}.",
                f"Date : {when}",
                f"Lieu : {where}",
                f"Participants : {', '.join(participant_names)}",
                "",
                f"Voir l’événement : {event_url}",
                f"Ajouter au calendrier : {calendar_url}",
                "",
                "Piano Académie",
            ]
        ),
    )


def run_school_event_reminders_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 200,
) -> EventReminderJobResult:
    cutoff = now + timedelta(hours=school_event_reminder_hours(db))
    joined_rows = db.execute(
        select(SchoolEventRegistration, SchoolEventSlot, SchoolEvent, Location, User)
        .join(SchoolEventSlot, SchoolEventSlot.id == SchoolEventRegistration.slot_id)
        .join(SchoolEvent, SchoolEvent.id == SchoolEventSlot.event_id)
        .outerjoin(Location, Location.id == func.coalesce(SchoolEventSlot.location_id, SchoolEvent.location_id))
        .join(User, User.id == SchoolEventRegistration.booker_user_id)
        .where(
            SchoolEvent.status.in_([SchoolEventStatus.PUBLISHED, SchoolEventStatus.CLOSED]),
            SchoolEventSlot.status == SchoolEventSlotStatus.SCHEDULED,
            SchoolEventSlot.start_at_utc > now,
            SchoolEventSlot.start_at_utc <= cutoff,
            SchoolEventRegistration.status == SchoolEventRegistrationStatus.CONFIRMED,
        )
        .order_by(SchoolEventSlot.start_at_utc.asc(), SchoolEventRegistration.booked_at.asc())
        .limit(max(limit * 20, limit))
    ).all()
    rows_by_group: dict[
        UUID,
        list[tuple[SchoolEventRegistration, SchoolEventSlot, SchoolEvent, Location | None, User]],
    ] = defaultdict(list)
    for registration, slot, event, location, booker in joined_rows:
        if registration.group_id not in rows_by_group and len(rows_by_group) >= limit:
            continue
        rows_by_group[registration.group_id].append((registration, slot, event, location, booker))

    sent = 0
    skipped = 0
    failed = 0
    successful_statuses = {
        CommunicationDeliveryStatus.SENT,
        CommunicationDeliveryStatus.DELIVERED,
        CommunicationDeliveryStatus.SKIPPED,
    }
    for group_id, group_rows in rows_by_group.items():
        first_registration, slot, event, location, booker = group_rows[0]
        source = event_reminder_source(event_id=event.id, group_id=group_id, start_at_utc=slot.start_at_utc)
        already_processed = db.scalar(
            select(CommunicationLog.id)
            .where(
                CommunicationLog.source == source,
                CommunicationLog.delivery_status.in_(successful_statuses),
            )
            .limit(1)
        )
        if already_processed is not None:
            skipped += 1
            continue
        email = deliverable_client_email(booker)
        participant_names = [registration.participant_display_name for registration, _, _, _, _ in group_rows]
        subject, body = _message(
            db=db,
            booker=booker,
            event=event,
            slot=slot,
            location=location,
            participant_names=participant_names,
            group_id=group_id,
        )
        if not email:
            log_communication(
                db=db,
                channel=CommunicationChannel.EMAIL,
                source=source,
                communication_type=COMMUNICATION_TYPE_EVENT_REMINDER,
                sender_category=CommunicationSenderCategory.SYSTEM,
                sender_label="Système",
                recipient="-",
                recipient_user_id=booker.id,
                subject=subject,
                content=body,
                content_format=MessageFormat.TEXT,
                delivery_status=CommunicationDeliveryStatus.SKIPPED,
                error_message="Adresse email indisponible",
                occurred_at=now,
            )
            skipped += 1
            continue
        try:
            send_email(
                to_email=email,
                subject=subject,
                body=body,
                context=source,
                recipient_user_id=booker.id,
                communication_type=COMMUNICATION_TYPE_EVENT_REMINDER,
            )
            latest_delivery = db.scalar(
                select(CommunicationLog.delivery_status)
                .where(CommunicationLog.source == source)
                .order_by(CommunicationLog.created_at.desc())
                .limit(1)
            )
            if latest_delivery in {CommunicationDeliveryStatus.SENT, CommunicationDeliveryStatus.DELIVERED}:
                sent += 1
            elif latest_delivery == CommunicationDeliveryStatus.SKIPPED:
                skipped += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return EventReminderJobResult(
        checked=len(rows_by_group),
        sent=sent,
        skipped=skipped,
        failed=failed,
    )
