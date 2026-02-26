from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes.bookings import (
    _consume_pack_credit,
    _count_booked,
    _enforce_plan_restrictions,
    _load_subscription_with_plan_for_update,
    _promote_waitlist_if_possible,
    _resolve_booking_snapshot,
    _restore_pack_credit,
    _select_eligible_subscription,
    _waitlist_position,
)
from app.api.deps import get_db, require_roles
from app.models.catalog import (
    Booking,
    BookingStatus,
    CourseSession,
    CourseType,
    Location,
    PlanningConfig,
    PlanningCourseType,
    Professor,
    SessionStatus,
)
from app.models.ops import AppSetting
from app.models.user import ClientStatus, User, UserRole
from app.services.reminders import ensure_booking_reminder, skip_pending_reminders_for_booking
from app.services.session_notifications import send_session_operation_email
from app.schemas.admin import (
    AdminSessionCancelOperationRequest,
    AdminSessionDeleteOperationRequest,
    AdminSessionMessageFormat,
    AdminSessionOperationNotificationRequest,
    AdminSessionOperationOut,
    AdminPlanningSettingsOut,
    AdminPlanningActivitiesOut,
    AdminPlanningActivitiesUpdateRequest,
    AdminPlanningActivityOut,
    AdminPlanningSettingsUpdateRequest,
    AdminProfessorOut,
    AdminSessionBookingCreateRequest,
    AdminSessionBookingOperationOut,
    AdminSessionBookingOut,
    AdminSessionCreateRequest,
    AdminSessionOut,
    AdminSessionUpdateRequest,
    AppSettingOut,
    AppSettingUpdateRequest,
)

router = APIRouter()

ALLOWED_SETTING_KEYS = {
    "auto_cancel_hours_before_start": 6,
    "reminder_hours_before_start": 24,
}

PLANNING_DEFAULTS = {
    "min_booking_notice_hours": 1,
    "max_booking_horizon_months": 6,
    "cancellation_deadline_hours": 1,
    "max_bookings_per_client": None,
    "allow_negative_credits": False,
    "waitlist_capacity": 3,
    "auto_cancel_if_booked_less_than": 1,
    "auto_cancel_hours_before_start": 1,
    "is_private": False,
    "allow_force_booking": True,
    "allow_multi_booking": False,
    "notify_coach": True,
    "notify_admins": True,
    "hide_booking_count": False,
    "block_client_cancellation": False,
}

BOOKING_STATUSES_COUNTED_AS_RESERVED = (
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)
BOOKING_STATUSES_ACTIVE = (
    BookingStatus.BOOKED,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)
VACATION_COURSE_TYPE_CODE = "VACATION_DAY"

ApplyScope = Literal["ONE", "SERIES_FUTURE", "SERIES_ALL"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_admin_session_out(session_obj: CourseSession, *, booked_count: int) -> AdminSessionOut:
    return AdminSessionOut(
        id=session_obj.id,
        course_type_id=session_obj.course_type_id,
        location_id=session_obj.location_id,
        professor_id=session_obj.professor_id,
        title=session_obj.title,
        description=session_obj.description,
        public_description=session_obj.description,
        private_description=session_obj.private_description,
        start_at_utc=session_obj.start_at_utc,
        end_at_utc=session_obj.end_at_utc,
        is_all_day=session_obj.is_all_day,
        capacity_max=session_obj.capacity_max,
        booked_count=booked_count,
        status=session_obj.status,
        auto_cancel_deadline_utc=session_obj.auto_cancel_deadline_utc,
        cancel_reason=session_obj.cancel_reason,
        zoom_link=session_obj.zoom_link,
        is_private=session_obj.is_private,
        allow_online_booking=session_obj.allow_online_booking,
        timezone=session_obj.timezone,
        recurrence_group_id=session_obj.recurrence_group_id,
        recurrence_rule=session_obj.recurrence_rule,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at,
    )


def _client_display_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _to_admin_session_booking_out(db: Session, booking: Booking, client: User) -> AdminSessionBookingOut:
    return AdminSessionBookingOut(
        id=booking.id,
        session_id=booking.session_id,
        client_id=booking.user_id,
        client_email=client.email,
        client_first_name=client.first_name,
        client_last_name=client.last_name,
        client_display_name=_client_display_name(client),
        client_plan_subscription_id=booking.client_plan_subscription_id,
        status=booking.status.value,
        booked_at=booking.booked_at,
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        waitlist_position=_waitlist_position(db, booking),
    )


def _to_planning_settings_out(config: PlanningConfig, *, location_name: str) -> AdminPlanningSettingsOut:
    return AdminPlanningSettingsOut(
        location_id=config.location_id,
        location_name=location_name,
        description=config.description,
        min_booking_notice_hours=config.min_booking_notice_hours,
        max_booking_horizon_months=config.max_booking_horizon_months,
        cancellation_deadline_hours=config.cancellation_deadline_hours,
        max_bookings_per_client=config.max_bookings_per_client,
        allow_negative_credits=config.allow_negative_credits,
        waitlist_capacity=config.waitlist_capacity,
        auto_cancel_if_booked_less_than=config.auto_cancel_if_booked_less_than,
        auto_cancel_hours_before_start=config.auto_cancel_hours_before_start,
        is_private=config.is_private,
        allow_force_booking=config.allow_force_booking,
        allow_multi_booking=config.allow_multi_booking,
        notify_coach=config.notify_coach,
        notify_admins=config.notify_admins,
        hide_booking_count=config.hide_booking_count,
        block_client_cancellation=config.block_client_cancellation,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _booked_count_by_session(db: Session, session_id: UUID) -> int:
    value = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
        )
    )
    return int(value or 0)


def _any_booking_count_by_session(db: Session, session_id: UUID) -> int:
    value = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.session_id == session_id,
        )
    )
    return int(value or 0)


def _active_booking_count_by_session(db: Session, session_id: UUID) -> int:
    value = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
    )
    return int(value or 0)


def _normalize_message_field(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _booked_counts_map(db: Session, session_ids: list[UUID]) -> dict[UUID, int]:
    if not session_ids:
        return {}

    rows = db.execute(
        select(Booking.session_id, func.count(Booking.id))
        .where(
            Booking.session_id.in_(session_ids),
            Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
        )
        .group_by(Booking.session_id)
    ).all()

    return {session_id: int(count or 0) for session_id, count in rows}


def _require_client(db: Session, client_id: UUID) -> User:
    client = db.scalar(select(User).where(User.id == client_id, User.role == UserRole.CLIENT))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _mark_first_course_if_needed(client: User, session_obj: CourseSession) -> None:
    if client.first_course_at is None or session_obj.start_at_utc < client.first_course_at:
        client.first_course_at = session_obj.start_at_utc


def _get_or_create_setting(db: Session, key: str) -> AppSetting:
    if key not in ALLOWED_SETTING_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")

    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if setting is not None:
        return setting

    setting = AppSetting(key=key, value=str(ALLOWED_SETTING_KEYS[key]))
    db.add(setting)
    db.flush()
    return setting


def _setting_int(db: Session, key: str) -> int:
    setting = _get_or_create_setting(db, key)
    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        value = ALLOWED_SETTING_KEYS[key]

    if value <= 0:
        value = ALLOWED_SETTING_KEYS[key]
    return value


def _validate_and_load_refs(
    db: Session,
    *,
    course_type_id: UUID,
    location_id: UUID,
    professor_id: UUID,
    enforce_planning_allowed: bool = True,
) -> tuple[CourseType, Location, Professor]:
    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")
    if not course_type.active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Activity is inactive")

    location = db.scalar(select(Location).where(Location.id == location_id))
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    professor = db.scalar(select(Professor).where(Professor.id == professor_id))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor not found")

    if enforce_planning_allowed:
        _assert_course_type_allowed_for_location(
            db,
            location_id=location.id,
            course_type_id=course_type.id,
        )

    return course_type, location, professor


def _resolve_end_at(start_at_utc: datetime, end_at_utc: datetime | None, course_type: CourseType) -> datetime:
    if end_at_utc is not None:
        return end_at_utc
    return start_at_utc + timedelta(minutes=course_type.duration_minutes)


def _is_vacation_course_type(course_type: CourseType) -> bool:
    return course_type.code.upper() == VACATION_COURSE_TYPE_CODE


def _normalize_session_timezone(value: str) -> str:
    timezone_name = (value or "").strip()
    if not timezone_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        )
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc
    return timezone_name


def _start_of_utc_day(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _add_months_utc(base: datetime, months: int) -> datetime:
    year = base.year + ((base.month - 1 + months) // 12)
    month = ((base.month - 1 + months) % 12) + 1
    day = min(base.day, monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


def _advance_recurrence_datetime(base: datetime, *, frequency: str, offset: int) -> datetime:
    if offset <= 0:
        return base
    if frequency == "DAILY":
        return base + timedelta(days=offset)
    if frequency == "MONTHLY":
        return _add_months_utc(base, offset)
    return base + timedelta(weeks=offset)


def _resolve_recurrence_occurrences(
    *,
    recurrence_frequency: str,
    recurrence_until_date: date | None,
    anchor_start_at_utc: datetime,
) -> int:
    if recurrence_until_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recurrence requires an end date",
        )

    anchor_day = anchor_start_at_utc.date()
    if recurrence_until_date < anchor_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recurrence end date must be after start date",
        )

    limit = 366
    count = 1
    probe = anchor_start_at_utc
    while count < limit:
        probe = _advance_recurrence_datetime(probe, frequency=recurrence_frequency, offset=1)
        if probe.date() > recurrence_until_date:
            break
        count += 1

    return count


def _has_vacation_on_day(
    db: Session,
    *,
    location_id: UUID,
    day_start_utc: datetime,
) -> bool:
    day_end_utc = day_start_utc + timedelta(days=1)
    exists = db.scalar(
        select(CourseSession.id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.location_id == location_id,
            CourseSession.status != SessionStatus.CANCELLED,
            CourseType.code == VACATION_COURSE_TYPE_CODE,
            CourseSession.start_at_utc < day_end_utc,
            CourseSession.end_at_utc > day_start_utc,
        )
        .limit(1)
    )
    return exists is not None


def _cancel_recurring_occurrences_for_vacation(
    db: Session,
    *,
    location_id: UUID,
    day_start_utc: datetime,
    vacation_session_id: UUID,
    now: datetime,
) -> None:
    day_end_utc = day_start_utc + timedelta(days=1)
    candidates = db.scalars(
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.location_id == location_id,
            CourseSession.id != vacation_session_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.recurrence_group_id.is_not(None),
            CourseType.code != VACATION_COURSE_TYPE_CODE,
            CourseSession.start_at_utc < day_end_utc,
            CourseSession.end_at_utc > day_start_utc,
        )
        .with_for_update()
    ).all()

    for candidate in candidates:
        if _active_booking_count_by_session(db, candidate.id) > 0:
            continue
        candidate.status = SessionStatus.CANCELLED
        candidate.cancel_reason = "VACATION_BLOCKED"
        candidate.updated_at = now

        bookings = db.scalars(
            select(Booking)
            .where(
                Booking.session_id == candidate.id,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            )
            .with_for_update()
        ).all()
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.cancellation_reason = "VACATION_BLOCKED"
            skip_pending_reminders_for_booking(
                db,
                booking_id=booking.id,
                reason="Session blocked by vacation",
                now=now,
            )


def _resolve_auto_cancel_deadline(
    db: Session,
    *,
    start_at_utc: datetime,
    auto_cancel_deadline_utc: datetime | None,
) -> datetime:
    if auto_cancel_deadline_utc is not None:
        return auto_cancel_deadline_utc

    hours = _setting_int(db, "auto_cancel_hours_before_start")
    return start_at_utc - timedelta(hours=hours)


def _validate_session_times(*, start_at_utc: datetime, end_at_utc: datetime, auto_cancel_deadline_utc: datetime) -> None:
    if end_at_utc <= start_at_utc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_at_utc must be after start_at_utc")

    if auto_cancel_deadline_utc >= start_at_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="auto_cancel_deadline_utc must be before start_at_utc",
        )


def _validate_same_day_slot(*, start_at_utc: datetime, end_at_utc: datetime, is_all_day: bool, session_timezone: str) -> None:
    if is_all_day:
        return
    tz = ZoneInfo(session_timezone)
    if start_at_utc.astimezone(tz).date() != end_at_utc.astimezone(tz).date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session end must be on the same day as start",
        )


def _get_location_or_404(db: Session, location_id: UUID) -> Location:
    location = db.scalar(select(Location).where(Location.id == location_id))
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


def _get_or_create_planning_config(db: Session, location: Location) -> PlanningConfig:
    config = db.scalar(
        select(PlanningConfig)
        .where(PlanningConfig.location_id == location.id)
        .with_for_update()
    )
    if config is not None:
        return config

    config = PlanningConfig(
        location_id=location.id,
        description=location.name,
        **PLANNING_DEFAULTS,
        updated_at=_utcnow(),
    )
    db.add(config)
    db.flush()
    return config


def _planning_course_type_rows(db: Session, *, location_id: UUID) -> list[tuple[UUID, int]]:
    rows = db.execute(
        select(PlanningCourseType.course_type_id, PlanningCourseType.display_order)
        .where(PlanningCourseType.location_id == location_id)
        .order_by(PlanningCourseType.display_order.asc(), PlanningCourseType.created_at.asc())
    ).all()
    return [(course_type_id, int(display_order or 0)) for course_type_id, display_order in rows]


def _ensure_planning_course_type_defaults(db: Session, *, location_id: UUID) -> list[tuple[UUID, int]]:
    rows = _planning_course_type_rows(db, location_id=location_id)
    if rows:
        return rows

    active_course_type_ids = db.scalars(
        select(CourseType.id)
        .where(CourseType.active.is_(True))
        .order_by(CourseType.name.asc(), CourseType.code.asc())
    ).all()

    if not active_course_type_ids:
        return []

    for index, course_type_id in enumerate(active_course_type_ids):
        db.add(
            PlanningCourseType(
                location_id=location_id,
                course_type_id=course_type_id,
                display_order=index,
            )
        )
    db.flush()
    return _planning_course_type_rows(db, location_id=location_id)


def _allowed_course_type_ids_for_location(db: Session, *, location_id: UUID) -> set[UUID]:
    rows = _ensure_planning_course_type_defaults(db, location_id=location_id)
    return {course_type_id for course_type_id, _ in rows}


def _assert_course_type_allowed_for_location(db: Session, *, location_id: UUID, course_type_id: UUID) -> None:
    allowed_ids = _allowed_course_type_ids_for_location(db, location_id=location_id)
    if allowed_ids and course_type_id not in allowed_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Activity is not enabled for this planning",
        )


def _target_sessions_for_scope(
    db: Session,
    *,
    session_obj: CourseSession,
    apply_scope: ApplyScope,
) -> list[CourseSession]:
    if apply_scope == "ONE" or session_obj.recurrence_group_id is None:
        return [session_obj]

    stmt = (
        select(CourseSession)
        .where(CourseSession.recurrence_group_id == session_obj.recurrence_group_id)
        .order_by(CourseSession.start_at_utc.asc())
        .with_for_update()
    )
    if apply_scope == "SERIES_FUTURE":
        stmt = stmt.where(CourseSession.start_at_utc >= session_obj.start_at_utc)

    rows = db.scalars(stmt).all()
    if not rows:
        return [session_obj]
    return rows


def _target_sessions_for_admin_booking(
    db: Session,
    *,
    session_obj: CourseSession,
    apply_scope: ApplyScope,
) -> list[CourseSession]:
    if apply_scope == "ONE":
        return [session_obj]

    if session_obj.recurrence_group_id is not None:
        return _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)

    anchor_weekday = session_obj.start_at_utc.weekday()
    anchor_start_sig = (
        session_obj.start_at_utc.hour,
        session_obj.start_at_utc.minute,
        session_obj.start_at_utc.second,
    )
    anchor_duration = session_obj.end_at_utc - session_obj.start_at_utc

    candidates = db.scalars(
        select(CourseSession)
        .where(
            CourseSession.course_type_id == session_obj.course_type_id,
            CourseSession.location_id == session_obj.location_id,
            CourseSession.professor_id == session_obj.professor_id,
            CourseSession.start_at_utc >= session_obj.start_at_utc,
        )
        .order_by(CourseSession.start_at_utc.asc())
        .with_for_update()
    ).all()

    filtered: list[CourseSession] = []
    for candidate in candidates:
        candidate_start_sig = (
            candidate.start_at_utc.hour,
            candidate.start_at_utc.minute,
            candidate.start_at_utc.second,
        )
        if candidate.start_at_utc.weekday() != anchor_weekday:
            continue
        if candidate_start_sig != anchor_start_sig:
            continue
        if (candidate.end_at_utc - candidate.start_at_utc) != anchor_duration:
            continue
        filtered.append(candidate)

    if not filtered:
        return [session_obj]
    return filtered


def _is_retryable_lock_error(exc: OperationalError) -> bool:
    original = getattr(exc, "orig", None)
    code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    return code in {"55P03", "57014"}


def _session_student_emails(db: Session, *, session_ids: list[UUID]) -> set[str]:
    if not session_ids:
        return set()

    rows = db.scalars(
        select(User.email)
        .join(Booking, Booking.user_id == User.id)
        .where(
            Booking.session_id.in_(session_ids),
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
        .distinct()
    ).all()
    return {email.strip().lower() for email in rows if email and email.strip()}


def _session_professor_emails(db: Session, *, session_ids: list[UUID]) -> set[str]:
    if not session_ids:
        return set()

    rows = db.scalars(
        select(Professor.email)
        .join(CourseSession, CourseSession.professor_id == Professor.id)
        .where(CourseSession.id.in_(session_ids))
        .distinct()
    ).all()
    return {email.strip().lower() for email in rows if email and email.strip()}


def _resolve_notification_message(
    *,
    notify_enabled: bool,
    subject: str | None,
    message: str | None,
    message_format: AdminSessionMessageFormat,
    recipient_label: str,
) -> tuple[str, str, str] | None:
    if not notify_enabled:
        return None

    normalized_subject = _normalize_message_field(subject)
    normalized_message = _normalize_message_field(message)
    if not normalized_subject or not normalized_message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Message {recipient_label}: sujet et contenu obligatoires",
        )
    return normalized_subject, normalized_message, message_format.value


def _validate_operation_notifications(notifications: AdminSessionOperationNotificationRequest | None) -> None:
    if notifications is None:
        return

    student_message = _resolve_notification_message(
        notify_enabled=bool(notifications.notify_students),
        subject=notifications.students_subject,
        message=notifications.students_message,
        message_format=notifications.students_format,
        recipient_label="eleves",
    )

    if not notifications.notify_professor:
        return

    if notifications.professor_same_as_students:
        if student_message is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Message professeur: activez un message eleves ou desactivez 'meme message'",
            )
        return

    _resolve_notification_message(
        notify_enabled=True,
        subject=notifications.professor_subject,
        message=notifications.professor_message,
        message_format=notifications.professor_format,
        recipient_label="professeur",
    )


def _send_operation_notifications(
    db: Session,
    *,
    session_ids: list[UUID] | None,
    fallback_session_title: str,
    notifications: AdminSessionOperationNotificationRequest | None,
    operation: str,
    student_emails: set[str] | None = None,
    professor_emails: set[str] | None = None,
) -> tuple[int, int]:
    if notifications is None:
        return 0, 0

    student_message = _resolve_notification_message(
        notify_enabled=bool(notifications.notify_students),
        subject=notifications.students_subject,
        message=notifications.students_message,
        message_format=notifications.students_format,
        recipient_label="eleves",
    )

    professor_message: tuple[str, str, str] | None = None
    if notifications.notify_professor:
        if notifications.professor_same_as_students:
            if student_message is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Message professeur: activez un message eleves ou desactivez 'meme message'",
                )
            professor_message = student_message
        else:
            professor_message = _resolve_notification_message(
                notify_enabled=True,
                subject=notifications.professor_subject,
                message=notifications.professor_message,
                message_format=notifications.professor_format,
                recipient_label="professeur",
            )

    notified_students = 0
    if student_message is not None:
        student_subject, student_body, student_format = student_message
        recipients = student_emails if student_emails is not None else _session_student_emails(db, session_ids=session_ids or [])
        for email in sorted(recipients):
            send_session_operation_email(
                to_email=email,
                subject=student_subject,
                body=student_body,
                body_format=student_format,
                operation=operation,
                session_title=fallback_session_title,
            )
            notified_students += 1

    notified_professors = 0
    if professor_message is not None:
        professor_subject, professor_body, professor_format = professor_message
        recipients = professor_emails if professor_emails is not None else _session_professor_emails(db, session_ids=session_ids or [])
        for email in sorted(recipients):
            send_session_operation_email(
                to_email=email,
                subject=professor_subject,
                body=professor_body,
                body_format=professor_format,
                operation=operation,
                session_title=fallback_session_title,
            )
            notified_professors += 1

    return notified_students, notified_professors


@router.get("/ping")
def admin_ping(current_user: User = Depends(require_roles(UserRole.ADMIN))) -> dict[str, bool]:
    return {"ok": True}


@router.get("/professors", response_model=list[AdminProfessorOut])
def list_admin_professors(
    active: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminProfessorOut]:
    stmt = select(Professor).order_by(Professor.last_name.asc(), Professor.first_name.asc())
    if active:
        stmt = stmt.where(Professor.active.is_(True))

    professors = db.scalars(stmt).all()
    return [
        AdminProfessorOut(
            id=prof.id,
            first_name=prof.first_name,
            last_name=prof.last_name,
            email=prof.email,
            active=prof.active,
        )
        for prof in professors
    ]


@router.get("/settings", response_model=list[AppSettingOut])
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AppSettingOut]:
    items: list[AppSettingOut] = []
    for key in ALLOWED_SETTING_KEYS:
        setting = _get_or_create_setting(db, key)
        items.append(AppSettingOut(key=setting.key, value=setting.value, updated_at=setting.updated_at))

    db.commit()
    return items


@router.put("/settings/{key}", response_model=AppSettingOut)
def update_setting(
    key: str,
    payload: AppSettingUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AppSettingOut:
    setting = _get_or_create_setting(db, key)

    if key in ALLOWED_SETTING_KEYS:
        try:
            int_value = int(payload.value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Setting value must be an integer") from exc
        if int_value <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Setting value must be > 0")

    setting.value = payload.value
    setting.updated_at = _utcnow()
    db.commit()
    db.refresh(setting)
    return AppSettingOut(key=setting.key, value=setting.value, updated_at=setting.updated_at)


@router.get("/plannings/{location_id}/activities", response_model=AdminPlanningActivitiesOut)
def get_planning_activities(
    location_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPlanningActivitiesOut:
    location = _get_location_or_404(db, location_id)
    selected_rows = _ensure_planning_course_type_defaults(db, location_id=location.id)
    selected_ids = [course_type_id for course_type_id, _ in selected_rows]
    selected_set = set(selected_ids)
    display_order_by_id = {course_type_id: display_order for course_type_id, display_order in selected_rows}

    all_activities = db.scalars(
        select(CourseType)
        .order_by(CourseType.name.asc(), CourseType.code.asc())
    ).all()

    def sort_key(activity: CourseType) -> tuple[int, int, str]:
        selected_rank = 0 if activity.id in selected_set else 1
        order_rank = display_order_by_id.get(activity.id, 9999)
        return (selected_rank, order_rank, activity.name.casefold())

    sorted_activities = sorted(all_activities, key=sort_key)
    payload = [
        AdminPlanningActivityOut(
            id=activity.id,
            code=activity.code,
            name=activity.name,
            description=activity.description,
            duration_minutes=activity.duration_minutes,
            color_hex=activity.color_hex,
            mode=activity.mode,
            default_capacity=activity.default_capacity,
            active=activity.active,
            selected=activity.id in selected_set,
            display_order=display_order_by_id.get(activity.id, 9999),
        )
        for activity in sorted_activities
    ]

    db.commit()
    return AdminPlanningActivitiesOut(
        location_id=location.id,
        location_name=location.name,
        selected_activity_ids=selected_ids,
        activities=payload,
    )


@router.put("/plannings/{location_id}/activities", response_model=AdminPlanningActivitiesOut)
def update_planning_activities(
    location_id: UUID,
    payload: AdminPlanningActivitiesUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPlanningActivitiesOut:
    location = _get_location_or_404(db, location_id)

    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for activity_id in payload.activity_ids:
        if activity_id in seen:
            continue
        seen.add(activity_id)
        unique_ids.append(activity_id)

    if not unique_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one activity must be selected for this planning",
        )

    if unique_ids:
        rows = db.scalars(
            select(CourseType.id)
            .where(
                CourseType.id.in_(unique_ids),
                CourseType.active.is_(True),
            )
        ).all()
        found_ids = set(rows)
        missing = [str(activity_id) for activity_id in unique_ids if activity_id not in found_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown or inactive activity ids: {', '.join(missing)}",
            )

    db.execute(delete(PlanningCourseType).where(PlanningCourseType.location_id == location.id))
    for index, activity_id in enumerate(unique_ids):
        db.add(
            PlanningCourseType(
                location_id=location.id,
                course_type_id=activity_id,
                display_order=index,
            )
        )
    db.commit()
    return get_planning_activities(location_id=location.id, db=db, _=_)


@router.get("/plannings/{location_id}/settings", response_model=AdminPlanningSettingsOut)
def get_planning_settings(
    location_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPlanningSettingsOut:
    location = _get_location_or_404(db, location_id)
    config = _get_or_create_planning_config(db, location)
    db.commit()
    db.refresh(config)
    return _to_planning_settings_out(config, location_name=location.name)


@router.put("/plannings/{location_id}/settings", response_model=AdminPlanningSettingsOut)
def update_planning_settings(
    location_id: UUID,
    payload: AdminPlanningSettingsUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminPlanningSettingsOut:
    location = _get_location_or_404(db, location_id)
    config = _get_or_create_planning_config(db, location)

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(config, key, value)

    config.updated_at = _utcnow()
    db.commit()
    db.refresh(config)
    return _to_planning_settings_out(config, location_name=location.name)


@router.post("/sessions", response_model=AdminSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: AdminSessionCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionOut:
    course_type, location, _ = _validate_and_load_refs(
        db,
        course_type_id=payload.course_type_id,
        location_id=payload.location_id,
        professor_id=payload.professor_id,
    )
    session_timezone = _normalize_session_timezone(payload.timezone or location.timezone)

    is_vacation = _is_vacation_course_type(course_type)
    is_all_day = bool(payload.is_all_day or is_vacation)

    if is_all_day:
        start_at_utc = _start_of_utc_day(payload.start_at_utc)
        end_at_utc = start_at_utc + timedelta(days=1)
    else:
        start_at_utc = payload.start_at_utc
        end_at_utc = _resolve_end_at(start_at_utc, payload.end_at_utc, course_type)

    auto_cancel_deadline_utc = _resolve_auto_cancel_deadline(
        db,
        start_at_utc=start_at_utc,
        auto_cancel_deadline_utc=payload.auto_cancel_deadline_utc,
    )
    if is_vacation:
        capacity_max = 0
    else:
        capacity_max = int(payload.capacity_max)
        if capacity_max <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Capacite max obligatoire (>= 1, sauf type vacances)",
            )

    _validate_session_times(
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        auto_cancel_deadline_utc=auto_cancel_deadline_utc,
    )
    _validate_same_day_slot(
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        is_all_day=is_all_day,
        session_timezone=session_timezone,
    )

    recurrence_occurrences = 1
    recurrence_rule = None
    if payload.recurrence is not None:
        recurrence_rule = payload.recurrence.frequency
        recurrence_occurrences = _resolve_recurrence_occurrences(
            recurrence_frequency=recurrence_rule,
            recurrence_until_date=payload.recurrence.until_date,
            anchor_start_at_utc=start_at_utc,
        )

    recurrence_group_id = uuid4() if recurrence_occurrences > 1 else None

    duration = end_at_utc - start_at_utc
    deadline_delta = start_at_utc - auto_cancel_deadline_utc
    now = _utcnow()

    sessions_to_create: list[CourseSession] = []
    for index in range(recurrence_occurrences):
        if recurrence_rule is None:
            starts_at = start_at_utc
        else:
            starts_at = _advance_recurrence_datetime(start_at_utc, frequency=recurrence_rule, offset=index)

        if is_all_day:
            starts_at = _start_of_utc_day(starts_at)
            ends_at = starts_at + timedelta(days=1)
        else:
            ends_at = starts_at + duration

        deadline_at = starts_at - deadline_delta

        _validate_session_times(
            start_at_utc=starts_at,
            end_at_utc=ends_at,
            auto_cancel_deadline_utc=deadline_at,
        )
        _validate_same_day_slot(
            start_at_utc=starts_at,
            end_at_utc=ends_at,
            is_all_day=is_all_day,
            session_timezone=session_timezone,
        )

        if recurrence_occurrences > 1 and not is_vacation:
            if _has_vacation_on_day(db, location_id=payload.location_id, day_start_utc=_start_of_utc_day(starts_at)):
                continue

        sessions_to_create.append(
            CourseSession(
                course_type_id=payload.course_type_id,
                location_id=payload.location_id,
                professor_id=payload.professor_id,
                title=payload.title,
                description=payload.public_description or payload.description,
                private_description=payload.private_description,
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                is_all_day=is_all_day,
                capacity_max=capacity_max,
                status=SessionStatus.SCHEDULED,
                auto_cancel_deadline_utc=deadline_at,
                cancel_reason=None,
                zoom_link=payload.zoom_link,
                is_private=payload.is_private,
                allow_online_booking=(not payload.is_private) and bool(payload.allow_online_booking),
                timezone=session_timezone,
                recurrence_group_id=recurrence_group_id,
                recurrence_rule=recurrence_rule,
                updated_at=now,
            )
        )

    if not sessions_to_create:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All recurring occurrences were blocked by vacation day sessions",
        )

    db.add_all(sessions_to_create)
    db.flush()

    if is_vacation:
        for vacation_session in sessions_to_create:
            _cancel_recurring_occurrences_for_vacation(
                db,
                location_id=vacation_session.location_id,
                day_start_utc=_start_of_utc_day(vacation_session.start_at_utc),
                vacation_session_id=vacation_session.id,
                now=now,
            )

    db.commit()
    db.refresh(sessions_to_create[0])

    return _to_admin_session_out(sessions_to_create[0], booked_count=0)


@router.get("/sessions", response_model=list[AdminSessionOut])
def list_admin_sessions(
    location_id: UUID | None = None,
    location_ids: list[UUID] | None = Query(default=None),
    course_type_id: UUID | None = None,
    professor_id: UUID | None = None,
    professor_ids: list[UUID] | None = Query(default=None),
    client_ids: list[UUID] | None = Query(default=None),
    status: SessionStatus | None = None,
    client_status: ClientStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminSessionOut]:
    stmt = select(CourseSession)

    location_filter_ids = list(dict.fromkeys(location_ids or []))
    if not location_filter_ids and location_id is not None:
        location_filter_ids = [location_id]
    if location_filter_ids:
        stmt = stmt.where(CourseSession.location_id.in_(location_filter_ids))

    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)

    professor_filter_ids = list(dict.fromkeys(professor_ids or []))
    if not professor_filter_ids and professor_id is not None:
        professor_filter_ids = [professor_id]
    if professor_filter_ids:
        stmt = stmt.where(CourseSession.professor_id.in_(professor_filter_ids))

    if status is not None:
        stmt = stmt.where(CourseSession.status == status)

    client_filter_ids = list(dict.fromkeys(client_ids or []))
    if client_status is not None or client_filter_ids:
        stmt = (
            stmt.join(Booking, Booking.session_id == CourseSession.id)
            .join(User, User.id == Booking.user_id)
            .where(Booking.status != BookingStatus.CANCELLED)
        )
        if client_status is not None:
            stmt = stmt.where(User.client_status == client_status)
        if client_filter_ids:
            stmt = stmt.where(User.id.in_(client_filter_ids))
        stmt = stmt.distinct()

    sessions = db.scalars(stmt.order_by(CourseSession.start_at_utc.desc())).all()
    counts = _booked_counts_map(db, [session_obj.id for session_obj in sessions])

    return [
        _to_admin_session_out(
            session_obj,
            booked_count=counts.get(session_obj.id, 0),
        )
        for session_obj in sessions
    ]


@router.get("/sessions/{session_id}", response_model=AdminSessionOut)
def get_admin_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id))
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    booked_count = _booked_count_by_session(db, session_id)
    return _to_admin_session_out(session_obj, booked_count=booked_count)


@router.get("/sessions/{session_id}/bookings", response_model=list[AdminSessionBookingOut])
def list_admin_session_bookings(
    session_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminSessionBookingOut]:
    session_exists = db.scalar(select(CourseSession.id).where(CourseSession.id == session_id))
    if session_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    rows = db.execute(
        select(Booking, User)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.session_id == session_id,
            Booking.status != BookingStatus.CANCELLED,
        )
    ).all()

    order_map = {
        BookingStatus.BOOKED: 0,
        BookingStatus.WAITLISTED: 1,
        BookingStatus.ATTENDED: 2,
        BookingStatus.NO_SHOW: 3,
        BookingStatus.EXCUSED_ABSENCE: 4,
    }

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            order_map.get(row[0].status, 99),
            ((row[1].last_name or "") + (row[1].first_name or "") + row[1].email).lower(),
            row[0].booked_at,
        ),
    )

    return [_to_admin_session_booking_out(db, booking, client) for booking, client in sorted_rows]


@router.post("/sessions/{session_id}/bookings", response_model=AdminSessionBookingOperationOut)
def add_admin_session_booking(
    session_id: UUID,
    payload: AdminSessionBookingCreateRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionBookingOperationOut:
    try:
        anchor_session = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
        if anchor_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        client = _require_client(db, payload.client_id)
        targets = _target_sessions_for_admin_booking(db, session_obj=anchor_session, apply_scope=apply_scope)
        if apply_scope != "ONE" and payload.recurrence_end_date is not None:
            targets = [target for target in targets if target.start_at_utc.date() <= payload.recurrence_end_date]

        now = _utcnow()

        processed_count = 0
        booked_count = 0
        waitlisted_count = 0
        skipped_count = 0
        details: list[str] = []
        planning_force_cache: dict[UUID, bool] = {}

        def add_detail(message: str) -> None:
            if message not in details:
                details.append(message)

        blocked_statuses = {
            BookingStatus.BOOKED,
            BookingStatus.WAITLISTED,
            BookingStatus.ATTENDED,
            BookingStatus.NO_SHOW,
            BookingStatus.EXCUSED_ABSENCE,
        }

        for target in targets:
            if target.status == SessionStatus.CANCELLED:
                skipped_count += 1
                add_detail("Creneau non reservable (annule)")
                continue

            existing = db.scalar(
                select(Booking)
                .where(
                    Booking.session_id == target.id,
                    Booking.user_id == client.id,
                )
                .with_for_update()
            )

            if existing is not None and existing.status in blocked_statuses:
                skipped_count += 1
                add_detail("Client deja inscrit sur ce creneau")
                continue

            selected = _select_eligible_subscription(
                db,
                user_id=client.id,
                course_type_id=target.course_type_id,
                now=now,
                requested_subscription_id=payload.client_plan_subscription_id,
            )
            force_allowed = planning_force_cache.get(target.location_id)
            if force_allowed is None:
                location = _get_location_or_404(db, target.location_id)
                config = _get_or_create_planning_config(db, location)
                force_allowed = bool(config.allow_force_booking)
                planning_force_cache[target.location_id] = force_allowed

            subscription = None
            plan = None
            if selected is not None:
                subscription, plan = selected
            elif not force_allowed:
                skipped_count += 1
                add_detail("Aucun abonnement actif/credit disponible pour ce client")
                continue

            price, vat_rate, vat_amount, total, currency = _resolve_booking_snapshot(
                db,
                session_obj=target,
                user=client,
                now=now,
                plan=plan,
            )
            next_status = BookingStatus.BOOKED if _count_booked(db, target.id) < target.capacity_max else BookingStatus.WAITLISTED

            if subscription is not None and plan is not None and next_status == BookingStatus.BOOKED and not _consume_pack_credit(subscription, plan):
                skipped_count += 1
                add_detail("Credits insuffisants pour inscrire ce client")
                continue

            if subscription is not None and plan is not None and next_status == BookingStatus.BOOKED:
                try:
                    _enforce_plan_restrictions(
                        db,
                        subscription=subscription,
                        plan=plan,
                        session_obj=target,
                    )
                except HTTPException as exc:
                    skipped_count += 1
                    add_detail(str(exc.detail))
                    continue

            if existing is None:
                booking = Booking(
                    session_id=target.id,
                    user_id=client.id,
                    client_plan_subscription_id=subscription.id if subscription is not None else None,
                    status=next_status,
                    booked_at=now,
                    cancelled_at=None,
                    cancellation_reason=None,
                    price_excl_vat_snapshot=price,
                    vat_rate_snapshot=vat_rate,
                    vat_amount_snapshot=vat_amount,
                    total_incl_vat_snapshot=total,
                    currency_snapshot=currency,
                )
                db.add(booking)
                db.flush()
            else:
                existing.client_plan_subscription_id = subscription.id if subscription is not None else None
                existing.status = next_status
                existing.booked_at = now
                existing.cancelled_at = None
                existing.cancellation_reason = None
                existing.price_excl_vat_snapshot = price
                existing.vat_rate_snapshot = vat_rate
                existing.vat_amount_snapshot = vat_amount
                existing.total_incl_vat_snapshot = total
                existing.currency_snapshot = currency
                booking = existing

            if next_status == BookingStatus.BOOKED:
                booked_count += 1
                _mark_first_course_if_needed(client, target)
                db.add(client)
                ensure_booking_reminder(
                    db,
                    booking=booking,
                    session_obj=target,
                    now=now,
                )
            else:
                waitlisted_count += 1
                skip_pending_reminders_for_booking(
                    db,
                    booking_id=booking.id,
                    reason="Booking moved to waitlist",
                    now=now,
                )

            processed_count += 1

        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_lock_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Planning en cours de modification. Reessayez dans quelques secondes.",
            ) from exc
        raise

    return AdminSessionBookingOperationOut(
        processed_count=processed_count,
        booked_count=booked_count,
        waitlisted_count=waitlisted_count,
        skipped_count=skipped_count,
        details=details,
    )


@router.delete("/sessions/{session_id}/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_admin_session_booking(
    session_id: UUID,
    booking_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    session_obj = db.scalar(
        select(CourseSession)
        .where(CourseSession.id == session_id)
        .with_for_update()
    )
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_id,
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.status == BookingStatus.CANCELLED:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    now = _utcnow()
    previous_status = booking.status
    locked_statuses = (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)
    is_future_scheduled_session = session_obj.status == SessionStatus.SCHEDULED and session_obj.start_at_utc > now
    if previous_status in locked_statuses and not is_future_scheduled_session:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed booking cannot be removed")

    refundable_statuses = (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)
    if previous_status in refundable_statuses and booking.client_plan_subscription_id is not None and session_obj.start_at_utc > now:
        sub_and_plan = _load_subscription_with_plan_for_update(
            db,
            subscription_id=booking.client_plan_subscription_id,
        )
        if sub_and_plan is not None:
            subscription, plan = sub_and_plan
            if subscription.user_id == booking.user_id:
                _restore_pack_credit(subscription, plan)

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    booking.cancellation_reason = "ADMIN_REMOVED"

    skip_pending_reminders_for_booking(
        db,
        booking_id=booking.id,
        reason="Booking cancelled by admin",
        now=now,
    )
    _promote_waitlist_if_possible(db, session_obj, now)

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/sessions/{session_id}", response_model=AdminSessionOut)
def update_session(
    session_id: UUID,
    payload: AdminSessionUpdateRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    updates = payload.model_dump(exclude_unset=True)
    if "public_description" not in updates and "description" in updates:
        updates["public_description"] = updates["description"]

    course_type_id = updates.get("course_type_id", session_obj.course_type_id)
    location_id = updates.get("location_id", session_obj.location_id)
    professor_id = updates.get("professor_id", session_obj.professor_id)
    enforce_planning_allowed = "course_type_id" in updates or "location_id" in updates

    course_type, location, _ = _validate_and_load_refs(
        db,
        course_type_id=course_type_id,
        location_id=location_id,
        professor_id=professor_id,
        enforce_planning_allowed=enforce_planning_allowed,
    )
    is_vacation = _is_vacation_course_type(course_type)
    anchor_timezone = _normalize_session_timezone(updates.get("timezone", session_obj.timezone or location.timezone))

    original_anchor_start = session_obj.start_at_utc
    original_anchor_end = session_obj.end_at_utc
    original_anchor_deadline = session_obj.auto_cancel_deadline_utc
    anchor_is_all_day = bool(updates.get("is_all_day", session_obj.is_all_day))

    anchor_start = updates.get("start_at_utc", original_anchor_start)
    if anchor_is_all_day:
        anchor_start = _start_of_utc_day(anchor_start)
        anchor_end = anchor_start + timedelta(days=1)
        if "auto_cancel_deadline_utc" in updates:
            anchor_deadline = updates["auto_cancel_deadline_utc"]
        else:
            anchor_deadline = _resolve_auto_cancel_deadline(
                db,
                start_at_utc=anchor_start,
                auto_cancel_deadline_utc=None,
            )
    else:
        if "end_at_utc" in updates:
            anchor_end = updates["end_at_utc"]
        elif "start_at_utc" in updates:
            anchor_end = anchor_start + (original_anchor_end - original_anchor_start)
        else:
            anchor_end = original_anchor_end

        if anchor_end is None:
            anchor_end = _resolve_end_at(anchor_start, None, course_type)

        if "auto_cancel_deadline_utc" in updates:
            anchor_deadline = updates["auto_cancel_deadline_utc"]
        elif "start_at_utc" in updates:
            anchor_deadline = _resolve_auto_cancel_deadline(
                db,
                start_at_utc=anchor_start,
                auto_cancel_deadline_utc=None,
            )
        else:
            anchor_deadline = original_anchor_deadline

    _validate_session_times(
        start_at_utc=anchor_start,
        end_at_utc=anchor_end,
        auto_cancel_deadline_utc=anchor_deadline,
    )
    _validate_same_day_slot(
        start_at_utc=anchor_start,
        end_at_utc=anchor_end,
        is_all_day=anchor_is_all_day,
        session_timezone=anchor_timezone,
    )

    has_start_update = "start_at_utc" in updates
    has_end_update = "end_at_utc" in updates
    has_deadline_update = "auto_cancel_deadline_utc" in updates

    anchor_start_shift = anchor_start - original_anchor_start
    anchor_end_shift = anchor_end - original_anchor_end
    anchor_deadline_shift = anchor_deadline - original_anchor_deadline
    anchor_new_duration = anchor_end - anchor_start
    anchor_deadline_delta = anchor_start - anchor_deadline

    now = _utcnow()
    target_sessions = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)

    for target in target_sessions:
        target.course_type_id = course_type_id
        target.location_id = location_id
        target.professor_id = professor_id

        if "title" in updates:
            target.title = updates["title"]
        if "public_description" in updates:
            target.description = updates["public_description"]
        if "private_description" in updates:
            target.private_description = updates["private_description"]
        if "zoom_link" in updates:
            target.zoom_link = updates["zoom_link"]
        if is_vacation:
            target.capacity_max = 0
        elif "capacity_max" in updates:
            next_capacity = int(updates["capacity_max"])
            if next_capacity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Capacite max obligatoire (>= 1, sauf type vacances)",
                )
            target.capacity_max = next_capacity
        elif target.capacity_max <= 0:
            target.capacity_max = 1
        if "status" in updates:
            target.status = updates["status"]
        if "cancel_reason" in updates:
            target.cancel_reason = updates["cancel_reason"]
        if "is_private" in updates:
            target.is_private = updates["is_private"]
        if "allow_online_booking" in updates or "is_private" in updates:
            next_online_booking = bool(updates.get("allow_online_booking", target.allow_online_booking))
            next_is_private = bool(updates.get("is_private", target.is_private))
            target.allow_online_booking = False if next_is_private else next_online_booking

        original_target_start = target.start_at_utc
        original_target_end = target.end_at_utc
        original_target_deadline = target.auto_cancel_deadline_utc
        resolved_is_all_day = bool(updates.get("is_all_day", target.is_all_day))
        if apply_scope == "ONE":
            resolved_timezone = anchor_timezone
        elif "timezone" in updates:
            resolved_timezone = anchor_timezone
        else:
            resolved_timezone = _normalize_session_timezone(target.timezone or location.timezone)

        if apply_scope == "ONE":
            resolved_start = anchor_start
            resolved_end = anchor_end
            resolved_deadline = anchor_deadline
        else:
            if has_start_update:
                resolved_start = original_target_start + anchor_start_shift
            else:
                resolved_start = original_target_start

            if has_end_update and has_start_update:
                resolved_end = resolved_start + anchor_new_duration
            elif has_end_update:
                resolved_end = original_target_end + anchor_end_shift
            elif has_start_update:
                resolved_end = resolved_start + (original_target_end - original_target_start)
            else:
                resolved_end = original_target_end

            if has_deadline_update and has_start_update:
                resolved_deadline = resolved_start - anchor_deadline_delta
            elif has_deadline_update:
                resolved_deadline = original_target_deadline + anchor_deadline_shift
            elif has_start_update:
                resolved_deadline = resolved_start - (original_target_start - original_target_deadline)
            else:
                resolved_deadline = original_target_deadline

        if resolved_is_all_day:
            resolved_start = _start_of_utc_day(resolved_start)
            resolved_end = resolved_start + timedelta(days=1)
            if "auto_cancel_deadline_utc" not in updates:
                resolved_deadline = _resolve_auto_cancel_deadline(
                    db,
                    start_at_utc=resolved_start,
                    auto_cancel_deadline_utc=None,
                )

        _validate_session_times(
            start_at_utc=resolved_start,
            end_at_utc=resolved_end,
            auto_cancel_deadline_utc=resolved_deadline,
        )
        _validate_same_day_slot(
            start_at_utc=resolved_start,
            end_at_utc=resolved_end,
            is_all_day=resolved_is_all_day,
            session_timezone=resolved_timezone,
        )

        target.start_at_utc = resolved_start
        target.end_at_utc = resolved_end
        target.auto_cancel_deadline_utc = resolved_deadline
        target.is_all_day = resolved_is_all_day
        target.timezone = resolved_timezone
        target.updated_at = now

    db.commit()
    db.refresh(session_obj)

    booked_count = _booked_count_by_session(db, session_id)
    return _to_admin_session_out(session_obj, booked_count=booked_count)


@router.post("/sessions/{session_id}/cancel", response_model=AdminSessionOperationOut)
def cancel_session_operation(
    session_id: UUID,
    payload: AdminSessionCancelOperationRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionOperationOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _validate_operation_notifications(payload.notifications)

    targets = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)
    now = _utcnow()
    cancel_reason = _normalize_message_field(payload.cancel_reason) or "ADMIN_CANCELLED"
    target_ids = [target.id for target in targets]

    for target in targets:
        target.status = SessionStatus.CANCELLED
        target.cancel_reason = cancel_reason
        target.updated_at = now

    db.commit()

    notified_students, notified_professors = _send_operation_notifications(
        db,
        session_ids=target_ids,
        fallback_session_title=session_obj.title,
        notifications=payload.notifications,
        operation="CANCEL",
    )
    return AdminSessionOperationOut(
        processed_sessions=len(target_ids),
        notified_students=notified_students,
        notified_professors=notified_professors,
        notifications_enabled=payload.notifications is not None,
    )


@router.post("/sessions/{session_id}/delete", response_model=AdminSessionOperationOut)
def delete_session_operation(
    session_id: UUID,
    payload: AdminSessionDeleteOperationRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionOperationOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _validate_operation_notifications(payload.notifications)

    targets = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)
    now = _utcnow()
    target_ids = [target.id for target in targets]
    student_emails = _session_student_emails(db, session_ids=target_ids)
    professor_emails = _session_professor_emails(db, session_ids=target_ids)

    refundable_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )

    for target in targets:
        bookings = db.scalars(
            select(Booking)
            .where(Booking.session_id == target.id)
            .with_for_update()
        ).all()

        for booking in bookings:
            if (
                booking.status in refundable_statuses
                and booking.client_plan_subscription_id is not None
                and target.start_at_utc > now
            ):
                sub_and_plan = _load_subscription_with_plan_for_update(
                    db,
                    subscription_id=booking.client_plan_subscription_id,
                )
                if sub_and_plan is not None:
                    subscription, plan = sub_and_plan
                    if subscription.user_id == booking.user_id:
                        _restore_pack_credit(subscription, plan)

        db.delete(target)

    db.commit()

    notified_students, notified_professors = _send_operation_notifications(
        db,
        session_ids=None,
        fallback_session_title=session_obj.title,
        notifications=payload.notifications,
        operation="DELETE",
        student_emails=student_emails,
        professor_emails=professor_emails,
    )
    return AdminSessionOperationOut(
        processed_sessions=len(target_ids),
        notified_students=notified_students,
        notified_professors=notified_professors,
        notifications_enabled=payload.notifications is not None,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    targets = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)

    for target in targets:
        if _any_booking_count_by_session(db, target.id) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete session(s) with existing bookings",
            )

    for target in targets:
        db.delete(target)

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
