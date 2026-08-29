from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import unicodedata
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location
from app.models.notification_engine import Notification
from app.models.ops import AppSetting
from app.models.plan import ClientPlanSubscription, Plan
from app.models.user import ClientKind, User, UserRole
from app.schemas.automation import AdminAutomationRuleCreate, AdminAutomationRuleUpdate
from app.services.messaging_templates import (
    PREDEFINED_EMAIL_TEMPLATE_TRIAL_ADULT_GUIDE,
    render_template_content,
    resolve_frontend_base_url,
    resolve_messaging_template_ref,
)
from app.services.notifications.application.orchestrator import OrchestratedNotification
from app.services.notifications.application.recipients import resolve_client_user_notification_recipient
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    DISPATCH_MODE_IMMEDIATE,
    DISPATCH_MODE_SCHEDULED,
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    QUEUE_NOTIFICATIONS_SCHEDULED,
)
from app.services.notifications.infrastructure.repository import create_notification_if_new


AUTOMATION_RULES_SETTING_KEY = "automation_trigger_rules_v1"
EVENT_PLAN_PURCHASE_CONFIRMED = "PLAN_PURCHASE_CONFIRMED"
EVENT_TRIAL_COURSE_ATTENDED = "TRIAL_COURSE_ATTENDED"
EVENT_FIRST_STUDIO_BOOKING_CREATED = "FIRST_STUDIO_BOOKING_CREATED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_text(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in raw if not unicodedata.combining(char)).lower().split())


def _serialize_rule(rule: AdminAutomationRuleCreate | AdminAutomationRuleUpdate, *, rule_id: UUID, created_at: datetime) -> dict[str, object]:
    now = _utcnow()
    return {
        "id": str(rule_id),
        "name": rule.name.strip(),
        "event_type": rule.event_type,
        "template_ref": rule.template_ref.strip(),
        "plan_id": str(rule.plan_id) if rule.plan_id else None,
        "course_type_id": str(rule.course_type_id) if rule.course_type_id else None,
        "location_id": str(rule.location_id) if rule.location_id else None,
        "client_kind": rule.client_kind,
        "delay_minutes": int(rule.delay_minutes),
        "active": bool(rule.active),
        "created_at": created_at.isoformat(),
        "updated_at": now.isoformat(),
    }


def _load_raw_rules(db: Session) -> list[dict[str, object]]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == AUTOMATION_RULES_SETTING_KEY))
    if setting is None or not (setting.value or "").strip():
        return []
    try:
        payload = json.loads(setting.value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _save_raw_rules(db: Session, rules: list[dict[str, object]]) -> None:
    now = _utcnow()
    setting = db.scalar(select(AppSetting).where(AppSetting.key == AUTOMATION_RULES_SETTING_KEY).with_for_update())
    value = json.dumps(rules, ensure_ascii=False, separators=(",", ":"))
    if setting is None:
        db.add(AppSetting(key=AUTOMATION_RULES_SETTING_KEY, value=value, updated_at=now))
    else:
        setting.value = value
        setting.updated_at = now
        db.add(setting)


def list_automation_rules(db: Session) -> list[dict[str, object]]:
    return sorted(_load_raw_rules(db), key=lambda item: (not bool(item.get("active", True)), str(item.get("name") or "").lower()))


def create_automation_rule(db: Session, payload: AdminAutomationRuleCreate) -> dict[str, object]:
    rules = _load_raw_rules(db)
    row = _serialize_rule(payload, rule_id=uuid4(), created_at=_utcnow())
    rules.append(row)
    _save_raw_rules(db, rules)
    return row


def update_automation_rule(db: Session, rule_id: UUID, payload: AdminAutomationRuleUpdate) -> dict[str, object] | None:
    rules = _load_raw_rules(db)
    for index, row in enumerate(rules):
        if str(row.get("id")) != str(rule_id):
            continue
        try:
            created_at = datetime.fromisoformat(str(row.get("created_at")))
        except ValueError:
            created_at = _utcnow()
        updated = _serialize_rule(payload, rule_id=rule_id, created_at=created_at)
        rules[index] = updated
        _save_raw_rules(db, rules)
        return updated
    return None


def delete_automation_rule(db: Session, rule_id: UUID) -> bool:
    rules = _load_raw_rules(db)
    kept = [row for row in rules if str(row.get("id")) != str(rule_id)]
    if len(kept) == len(rules):
        return False
    _save_raw_rules(db, kept)
    return True


def _uuid_matches(raw: object, expected: UUID | None) -> bool:
    return raw in (None, "") or (expected is not None and str(raw) == str(expected))


def _rule_matches(
    rule: dict[str, object], *, event_type: str, client: User, plan_id: UUID | None = None,
    course_type_id: UUID | None = None, location_id: UUID | None = None,
) -> bool:
    if not bool(rule.get("active", True)) or rule.get("event_type") != event_type:
        return False
    kind = client.client_kind.value if hasattr(client.client_kind, "value") else str(client.client_kind)
    if rule.get("client_kind") not in (None, "", kind):
        return False
    return (
        _uuid_matches(rule.get("plan_id"), plan_id)
        and _uuid_matches(rule.get("course_type_id"), course_type_id)
        and _uuid_matches(rule.get("location_id"), location_id)
    )


def _is_trial(booking: Booking, session_obj: CourseSession, course_type: CourseType) -> bool:
    haystack = _normalized_text(f"{session_obj.title} {course_type.name} {course_type.code}")
    return bool(booking.is_trial_course) or "essai" in haystack or "trial" in haystack


def _is_studio(course_type: CourseType) -> bool:
    haystack = _normalized_text(f"{course_type.name} {course_type.code} {course_type.service_code}")
    return "studio" in haystack or "repetition" in haystack


def _has_previous_studio_booking(db: Session, *, booking: Booking, course_type: CourseType, location_id: UUID) -> bool:
    if not _is_studio(course_type):
        return True
    previous = db.scalar(
        select(Booking.id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            Booking.id != booking.id,
            Booking.user_id == booking.user_id,
            Booking.status.in_((BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)),
            CourseSession.location_id == location_id,
            (
                CourseType.name.ilike("%studio%")
                | CourseType.code.ilike("%studio%")
                | CourseType.service_code.ilike("%studio%")
                | CourseType.name.ilike("%répétition%")
            ),
        )
        .limit(1)
    )
    return previous is not None


def _unsubscribe_url(db: Session, recipient: User) -> str:
    if not recipient.communication_optout_token:
        return ""
    return (
        f"{resolve_frontend_base_url(db).rstrip('/')}/api/v1/clients/communication/optout"
        f"?token={recipient.communication_optout_token}&channel=EMAIL"
    )


def _local_session_labels(session_obj: CourseSession, location: Location) -> tuple[str, str, str]:
    timezone_name = session_obj.timezone or location.timezone or "Europe/Paris"
    try:
        local_start = session_obj.start_at_utc.astimezone(ZoneInfo(timezone_name))
    except (ValueError, KeyError):
        local_start = session_obj.start_at_utc.astimezone(ZoneInfo("Europe/Paris"))
        timezone_name = "Europe/Paris"
    return local_start.strftime("%d/%m/%Y"), local_start.strftime("%H:%M"), timezone_name


def _context(
    db: Session, *, client: User, recipient: User, plan: Plan | None = None,
    session_obj: CourseSession | None = None, course_type: CourseType | None = None, location: Location | None = None,
) -> dict[str, object]:
    first_name = (recipient.first_name or client.first_name or "").strip()
    last_name = (recipient.last_name or client.last_name or "").strip()
    student_name = f"{client.first_name or ''} {client.last_name or ''}".strip() or client.email
    location_address = ""
    if location is not None:
        location_address = ", ".join(part for part in (location.address_line, location.city) if part)
    session_date = session_time = session_timezone = ""
    if session_obj is not None and location is not None:
        session_date, session_time, session_timezone = _local_session_labels(session_obj, location)
    account_url = f"{resolve_frontend_base_url(db).rstrip('/')}/dashboard"
    return {
        "firstname": first_name,
        "first_name": first_name,
        "lastname": last_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}".strip(),
        "recipient_name": f"{first_name} {last_name}".strip() or recipient.email,
        "client_name": student_name,
        "student_name": student_name,
        "email": recipient.email,
        "plan_name": plan.name if plan else "",
        "activity_name": course_type.name if course_type else (plan.name if plan else ""),
        "location_name": location.name if location else "",
        "location_address": location_address,
        "session_date": session_date,
        "session_time": session_time,
        "session_timezone": session_timezone,
        "account_url": account_url,
        "booking_url": f"{account_url}?section=planning",
        "unsubscribe_url": _unsubscribe_url(db, recipient),
    }


def _automation_scheduled_for(
    *,
    event_type: str,
    occurred_at: datetime,
    delay: timedelta,
    session_obj: CourseSession | None,
) -> datetime:
    if event_type == EVENT_TRIAL_COURSE_ATTENDED and session_obj is not None:
        return max(occurred_at, session_obj.end_at_utc + delay)
    return occurred_at + delay


def cancel_pending_trial_attended_triggers(
    db: Session,
    *,
    booking_id: UUID,
    now: datetime,
) -> int:
    notifications = db.scalars(
        select(Notification).where(
            Notification.booking_id == booking_id,
            Notification.notification_type == "automation_trigger_email",
            Notification.source == "automation_trigger",
            Notification.status.in_([NOTIFICATION_STATUS_PENDING, NOTIFICATION_STATUS_QUEUED]),
        )
    ).all()
    cancelled = 0
    for notification in notifications:
        payload = notification.payload_snapshot or {}
        if payload.get("automation_event_type") != EVENT_TRIAL_COURSE_ATTENDED:
            continue
        notification.status = NOTIFICATION_STATUS_CANCELLED
        notification.skipped_at = now
        notification.failure_reason = "Trial attendance corrected before follow-up delivery"
        notification.updated_at = now
        db.add(notification)
        cancelled += 1
    return cancelled


def _schedule_matching(
    db: Session, *, event_type: str, related_entity_type: str, related_entity_id: UUID,
    client: User, plan: Plan | None = None, booking: Booking | None = None,
    session_obj: CourseSession | None = None, course_type: CourseType | None = None,
    location: Location | None = None, occurred_at: datetime,
) -> list[OrchestratedNotification]:
    recipient_ref = resolve_client_user_notification_recipient(db, user=client)
    if recipient_ref is None or not recipient_ref.email or recipient_ref.contact_id is None:
        return []
    recipient = db.scalar(select(User).where(User.id == recipient_ref.contact_id))
    if recipient is None:
        return []
    result: list[OrchestratedNotification] = []
    for rule in _load_raw_rules(db):
        if not _rule_matches(
            rule, event_type=event_type, client=client, plan_id=plan.id if plan else None,
            course_type_id=course_type.id if course_type else None, location_id=location.id if location else None,
        ):
            continue
        template_ref = str(rule.get("template_ref") or "").strip()
        try:
            template = resolve_messaging_template_ref(
                db, template_ref=template_ref,
                default_ref=f"predefined:{PREDEFINED_EMAIL_TEMPLATE_TRIAL_ADULT_GUIDE}",
                channel="EMAIL", language=recipient.preferred_language,
            )
        except (KeyError, ValueError):
            continue
        context = _context(
            db, client=client, recipient=recipient, plan=plan, session_obj=session_obj,
            course_type=course_type, location=location,
        )
        delay = max(0, min(10080, int(rule.get("delay_minutes") or 0)))
        delay_delta = timedelta(minutes=delay)
        scheduled_for = _automation_scheduled_for(
            event_type=event_type,
            occurred_at=occurred_at,
            delay=delay_delta,
            session_obj=session_obj,
        )
        due_now = scheduled_for <= occurred_at
        dispatch_mode = DISPATCH_MODE_IMMEDIATE if due_now else DISPATCH_MODE_SCHEDULED
        queue_name = QUEUE_NOTIFICATIONS_IMMEDIATE if due_now else QUEUE_NOTIFICATIONS_SCHEDULED
        rule_id = str(rule.get("id"))
        idempotency_key = f"automation:{rule_id}:{event_type}:{related_entity_id}:{recipient_ref.contact_id}"
        payload_snapshot = {
            "body_format": str(template.get("body_format") or "TEXT"),
            "automation_rule_id": rule_id,
            "automation_rule_name": str(rule.get("name") or ""),
            "automation_event_type": event_type,
            "template_ref": template_ref,
        }
        created = create_notification_if_new(
            db,
            notification_type="automation_trigger_email",
            channel=CHANNEL_EMAIL,
            dispatch_mode=dispatch_mode,
            source_event_id=None,
            source="automation_trigger",
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            booking_id=booking.id if booking else None,
            slot_id=session_obj.id if session_obj else None,
            recipient_type=recipient_ref.contact_type,
            recipient_contact_id=recipient_ref.contact_id,
            recipient_email=recipient_ref.email,
            recipient_phone=None,
            subject=render_template_content(str(template.get("subject") or "Piano Academie"), context),
            body_snapshot=render_template_content(str(template.get("body") or ""), context),
            payload_snapshot=payload_snapshot,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
            status=NOTIFICATION_STATUS_PENDING,
        )
        if created is None:
            existing = db.scalar(select(Notification).where(Notification.idempotency_key == idempotency_key).limit(1))
            if existing is not None and existing.status == NOTIFICATION_STATUS_CANCELLED:
                existing.dispatch_mode = dispatch_mode
                existing.recipient_email = recipient_ref.email
                existing.subject = render_template_content(str(template.get("subject") or "Piano Academie"), context)
                existing.body_snapshot = render_template_content(str(template.get("body") or ""), context)
                existing.payload_snapshot = payload_snapshot
                existing.scheduled_for = scheduled_for
                existing.status = NOTIFICATION_STATUS_PENDING
                existing.provider_name = None
                existing.provider_message_id = None
                existing.provider_status = None
                existing.sent_at = None
                existing.failed_at = None
                existing.skipped_at = None
                existing.failure_reason = None
                existing.updated_at = occurred_at
                db.add(existing)
                db.flush()
                created = existing
        if created is not None:
            result.append(OrchestratedNotification(notification_id=created.id, queue_name=queue_name))
    return result


def schedule_plan_purchase_triggers(
    db: Session, *, subscription: ClientPlanSubscription, plan: Plan, occurred_at: datetime,
) -> list[OrchestratedNotification]:
    client = db.scalar(select(User).where(User.id == subscription.user_id, User.role == UserRole.CLIENT))
    if client is None:
        return []
    return _schedule_matching(
        db, event_type=EVENT_PLAN_PURCHASE_CONFIRMED, related_entity_type="client_plan_subscription",
        related_entity_id=subscription.id, client=client, plan=plan, occurred_at=occurred_at,
    )


def schedule_booking_created_triggers(
    db: Session, *, booking: Booking, session_obj: CourseSession, occurred_at: datetime,
) -> list[OrchestratedNotification]:
    client = db.scalar(select(User).where(User.id == booking.user_id, User.role == UserRole.CLIENT))
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))
    if client is None or course_type is None or location is None or not _is_studio(course_type):
        return []
    if _has_previous_studio_booking(db, booking=booking, course_type=course_type, location_id=location.id):
        return []
    return _schedule_matching(
        db, event_type=EVENT_FIRST_STUDIO_BOOKING_CREATED, related_entity_type="booking",
        related_entity_id=booking.id, client=client, booking=booking, session_obj=session_obj,
        course_type=course_type, location=location, occurred_at=occurred_at,
    )

def schedule_trial_attended_triggers(
    db: Session, *, booking: Booking, session_obj: CourseSession, occurred_at: datetime,
) -> list[OrchestratedNotification]:
    client = db.scalar(select(User).where(User.id == booking.user_id, User.role == UserRole.CLIENT))
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))
    if client is None or course_type is None or location is None or not _is_trial(booking, session_obj, course_type):
        return []
    return _schedule_matching(
        db, event_type=EVENT_TRIAL_COURSE_ATTENDED, related_entity_type="booking",
        related_entity_id=booking.id, client=client, booking=booking, session_obj=session_obj,
        course_type=course_type, location=location, occurred_at=occurred_at,
    )
