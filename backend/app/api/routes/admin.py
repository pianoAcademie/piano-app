from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import logging
import re
import unicodedata
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased

from app.api.routes.bookings import (
    _consume_pack_credit,
    _enforce_plan_restrictions,
    _load_subscription_with_plan_for_update,
    _next_booking_status,
    _promote_waitlist_if_possible,
    _resolve_booking_snapshot,
    _restore_pack_credit,
    _select_eligible_subscription,
    _waitlist_position,
)
from app.api.deps import get_admin_permission_map, get_db, require_admin_or_permissions, require_roles
from app.models.catalog import (
    Booking,
    BookingStatus,
    CourseSession,
    CourseType,
    DeliveryMode,
    Location,
    PlanningConfig,
    PlanningCourseType,
    Professor,
    SessionAudienceScope,
    SessionStatus,
)
from app.models.family import ClientFamilyLink
from app.models.client_record import ClientBillingAdjustment, StudentQuoteChange
from app.models.ops import (
    AppSetting,
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationSenderCategory,
    MessageFormat,
)
from app.models.notification_engine import Notification
from app.models.quote import Prospect, Quote, QuoteAcceptanceFollowup
from app.models.user import ClientStatus, User, UserPresence, UserRole
from app.services.communication_journal import COMMUNICATION_TYPE_OPERATIONAL, log_communication
from app.services.automation_triggers import schedule_trial_attended_triggers
from app.services.invoice_documents import normalize_billing_entity
from app.services.notifications.application.orchestrator import enqueue_notifications, schedule_slot_cancelled_notifications
from app.services.notifications.domain.constants import (
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_QUEUED,
    NOTIFICATION_TYPE_REMINDER_EMAIL,
    NOTIFICATION_TYPE_REMINDER_SMS,
)
from app.services.payment_receipts import (
    FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES,
    generate_final_invoice_for_booking,
    send_final_invoice_email,
)
from app.services.reminders import ensure_booking_reminder, skip_pending_reminders_for_booking
from app.services.makeup_passes import grant_makeup_for_excused_absence, revoke_pending_makeup_for_corrected_absence
from app.services.session_audience import (
    coerce_session_scope_sets,
    legacy_flags_from_scopes,
    normalize_session_audience_scopes,
    primary_session_audience_scope,
    resolve_session_booking_scopes,
    resolve_session_visibility_scopes,
    serialize_session_audience_scopes,
)
from app.services.session_teachers import (
    normalized_substitute_teacher_id,
    professor_display_name,
)
from app.services.session_notifications import send_session_operation_email
from app.schemas.admin import (
    AdminInternalNoteUpdateRequest,
    AdminSessionBroadcastAudience,
    AdminSessionBroadcastOut,
    AdminSessionBroadcastRequest,
    AdminSessionCancelOperationRequest,
    AdminSessionDeleteOperationRequest,
    AdminSessionDuplicateOperationOut,
    AdminSessionDuplicateRequest,
    AdminSessionMessageFormat,
    AdminSessionOperationNotificationRequest,
    AdminSessionOperationOut,
    AdminPlanningSettingsOut,
    AdminPlanningActivitiesOut,
    AdminPlanningActivitiesUpdateRequest,
    AdminPlanningActivityOut,
    AdminPlanningSimulationOut,
    AdminPlanningSimulationSlotOut,
    AdminPlanningSimulationSummaryOut,
    AdminPlanningReorganizationBookingOut,
    AdminPlanningReorganizationLocationOut,
    AdminPlanningReorganizationMoveOut,
    AdminPlanningReorganizationMoveRequest,
    AdminPlanningReorganizationOut,
    AdminPlanningReorganizationSessionOut,
    AdminPlanningSettingsUpdateRequest,
    AdminOnlinePresenceOut,
    AdminClientBillingAdjustmentQueueOut,
    AdminProfessorOut,
    AdminSessionBookingCreateRequest,
    AdminSessionBookingAttendanceUpdateRequest,
    AdminSessionBookingNoteUpdateRequest,
    AdminSessionBookingOperationOut,
    AdminSessionBookingOut,
    AdminSessionBookingStudentTimeUpdateRequest,
    AdminSessionCreateRequest,
    AdminSessionGroupNoteUpdateRequest,
    AdminSessionOut,
    AdminSessionUpdateRequest,
    AppSettingOut,
    AppSettingUpdateRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_SETTING_KEYS = {
    "auto_cancel_hours_before_start": 6,
    "reminder_hours_before_start": 24,
    "sms_reminder_hours_before_start": 1,
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
    BookingStatus.PENDING_PAYMENT,
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
PLANNING_SIMULATION_QUOTE_APPROVED_STATUSES = {"approved"}
PLANNING_SIMULATION_QUOTE_PENDING_STATUSES = {"sent", "change_requested"}
PLANNING_SIMULATION_QUOTE_DRAFT_STATUSES = {"created"}
PLANNING_SIMULATION_QUOTE_RELEVANT_STATUSES = (
    PLANNING_SIMULATION_QUOTE_APPROVED_STATUSES
    | PLANNING_SIMULATION_QUOTE_PENDING_STATUSES
    | PLANNING_SIMULATION_QUOTE_DRAFT_STATUSES
)
PLANNING_SIMULATION_ACTIVITY_GROUP_COLLECTIVE_PIANO = "collective_piano"
VACATION_COURSE_TYPE_CODE = "VACATION_DAY"
QUOTE_SCHOOL_CALENDARS_SETTING_KEY = "quote_school_calendars_v1"

ApplyScope = Literal["ONE", "SERIES_FUTURE", "SERIES_ALL"]
BookingScope = Literal["OCCURRENCE", "SERIES_FUTURE"]
EMAIL_RECIPIENT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_CLEAN_RE = re.compile(r"[^\d+]+")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _billing_adjustment_display_name(first_name: str | None, last_name: str | None, email: str | None) -> str:
    full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return full_name or (email or "")


def _billing_adjustment_money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _billing_adjustment_currency(value: str | None, fallback: str = "EUR") -> str:
    normalized = (value or fallback or "EUR").strip().upper()
    return normalized[:3] if len(normalized) >= 3 else fallback


@router.get("/billing-adjustments", response_model=list[AdminClientBillingAdjustmentQueueOut])
def list_admin_billing_adjustments(
    status_filter: str | None = Query(default="READY", alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_clients")),
) -> list[AdminClientBillingAdjustmentQueueOut]:
    normalized_status = (status_filter or "").strip().upper()
    stmt = select(ClientBillingAdjustment)
    if normalized_status:
        stmt = stmt.where(ClientBillingAdjustment.status == normalized_status)
    rows = db.scalars(stmt.order_by(ClientBillingAdjustment.created_at.desc()).limit(500)).all()
    if not rows:
        return []

    user_ids = {row.user_id for row in rows}
    user_ids.update(row.student_user_id for row in rows if row.student_user_id is not None)
    users_by_id = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()}

    quote_ids = {row.quote_id for row in rows if row.quote_id is not None}
    quotes_by_id = {quote.id: quote for quote in db.scalars(select(Quote).where(Quote.id.in_(quote_ids))).all()} if quote_ids else {}

    change_ids = {row.change_id for row in rows if row.change_id is not None}
    changes_by_id = {
        change.id: change
        for change in db.scalars(select(StudentQuoteChange).where(StudentQuoteChange.id.in_(change_ids))).all()
    } if change_ids else {}

    out: list[AdminClientBillingAdjustmentQueueOut] = []
    for row in rows:
        client = users_by_id.get(row.user_id)
        student = users_by_id.get(row.student_user_id) if row.student_user_id is not None else None
        quote = quotes_by_id.get(row.quote_id) if row.quote_id is not None else None
        change = changes_by_id.get(row.change_id) if row.change_id is not None else None
        out.append(
            AdminClientBillingAdjustmentQueueOut(
                id=row.id,
                client_id=row.user_id,
                client_display_name=_billing_adjustment_display_name(client.first_name, client.last_name, client.email) if client is not None else str(row.user_id),
                student_id=row.student_user_id,
                student_display_name=_billing_adjustment_display_name(student.first_name, student.last_name, student.email) if student is not None else None,
                change_id=row.change_id,
                change_title=change.title if change is not None else None,
                change_type=change.change_type if change is not None else None,
                quote_id=row.quote_id,
                quote_number=quote.quote_number if quote is not None else None,
                status=(row.status or "READY").strip().upper(),
                adjustment_type=(row.adjustment_type or "INVOICE").strip().upper(),
                label=row.label,
                description=row.description,
                amount_excl_vat=_billing_adjustment_money(row.amount_excl_vat),
                vat_rate=Decimal(row.vat_rate),
                vat_amount=_billing_adjustment_money(row.vat_amount),
                total_incl_vat=_billing_adjustment_money(row.total_incl_vat),
                currency=_billing_adjustment_currency(row.currency),
                legal_entity_id=row.legal_entity_id,
                converted_manual_transaction_id=row.converted_manual_transaction_id,
                dismissed_reason=row.dismissed_reason,
                decided_at=row.decided_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return out


def _session_status_label(status: SessionStatus) -> str:
    if status == SessionStatus.CANCELLED:
        return "Annule"
    if status == SessionStatus.COMPLETED:
        return "Termine"
    return "Planifie"


def _session_teacher_display_name(professor: Professor | None) -> str:
    return professor_display_name(professor)


def _session_location_label(location: Location | None) -> str:
    if location is None:
        return "Lieu"
    name = (location.name or "").strip()
    if not name:
        return "Lieu"
    for separator in (" - ", ",", "|"):
        if separator in name:
            name = name.split(separator, 1)[0].strip()
            break
    return name or "Lieu"


def _session_type_label(session_obj: CourseSession, *, course_type: CourseType | None, location: Location | None) -> str:
    if resolve_session_visibility_scopes(session_obj) == [SessionAudienceScope.PRIVATE]:
        return "Prive"
    location_code = (location.code if location is not None else "").upper()
    location_name = (location.name if location is not None else "").lower()
    if location is not None and (location.is_online or location_code == "ONLINE"):
        return "Online"
    if "DOMICILE" in location_code or "domicile" in location_name:
        return "Domicile"
    if course_type is not None and course_type.mode == DeliveryMode.ONLINE:
        return "Online"
    return "Collectif"


def _is_online_session_context(*, course_type: CourseType | None, location: Location | None) -> bool:
    location_code = (location.code if location is not None else "").upper()
    if location is not None and (location.is_online or location_code == "ONLINE"):
        return True
    if course_type is not None and course_type.mode == DeliveryMode.ONLINE:
        return True
    return False


def _resolve_payload_session_scopes(
    *,
    visibility_scopes: list[SessionAudienceScope] | list[str] | None = None,
    booking_scopes: list[SessionAudienceScope] | list[str] | None = None,
    visibility_scope: SessionAudienceScope | str | None,
    booking_scope: SessionAudienceScope | str | None,
    is_private: bool | None,
    allow_online_booking: bool | None,
    allows_student_bookings: bool,
    current_visibility_scopes: list[SessionAudienceScope] | None = None,
    current_booking_scopes: list[SessionAudienceScope] | None = None,
    current_is_private: bool = False,
    current_allow_online_booking: bool = True,
) -> tuple[list[SessionAudienceScope], list[SessionAudienceScope]]:
    fallback_visibility_scopes = current_visibility_scopes or (
        [SessionAudienceScope.PRIVATE]
        if bool(is_private if is_private is not None else current_is_private)
        else [SessionAudienceScope.EXTERNAL]
    )
    raw_visibility_scopes: object | None = (
        visibility_scopes if visibility_scopes is not None else ([visibility_scope] if visibility_scope is not None else None)
    )
    next_visibility_scopes = normalize_session_audience_scopes(
        raw_visibility_scopes,
        fallback=fallback_visibility_scopes,
    )

    fallback_booking_scopes = current_booking_scopes or (
        [SessionAudienceScope.PRIVATE]
        if bool(is_private if is_private is not None else current_is_private)
        or not bool(allow_online_booking if allow_online_booking is not None else current_allow_online_booking)
        else [SessionAudienceScope.EXTERNAL]
    )
    raw_booking_scopes: object | None = booking_scopes if booking_scopes is not None else ([booking_scope] if booking_scope is not None else None)
    next_booking_scopes = normalize_session_audience_scopes(
        raw_booking_scopes,
        fallback=fallback_booking_scopes,
    )
    if visibility_scopes is None and visibility_scope is None and current_visibility_scopes is None and is_private is not None:
        next_visibility_scopes = [SessionAudienceScope.PRIVATE] if is_private else [SessionAudienceScope.EXTERNAL]
    if booking_scopes is None and booking_scope is None and current_booking_scopes is None and allow_online_booking is not None:
        next_booking_scopes = [SessionAudienceScope.PRIVATE] if not allow_online_booking else [SessionAudienceScope.EXTERNAL]
    return coerce_session_scope_sets(
        visibility_scopes=next_visibility_scopes,
        booking_scopes=next_booking_scopes,
        allows_student_bookings=allows_student_bookings,
        fallback_is_private=current_is_private,
        fallback_allow_online_booking=current_allow_online_booking,
    )


def _resolve_session_zoom_link(
    *,
    requested_zoom_link: str | None,
    course_type: CourseType | None,
    location: Location | None,
    professor: Professor | None,
) -> str | None:
    if requested_zoom_link is not None:
        normalized = requested_zoom_link.strip()
        if normalized:
            return normalized

    if _is_online_session_context(course_type=course_type, location=location):
        teacher_zoom = (professor.zoom_link if professor is not None else None) or ""
        teacher_zoom = teacher_zoom.strip()
        if teacher_zoom:
            return teacher_zoom

    return None


def _to_admin_session_out(
    session_obj: CourseSession,
    *,
    booked_count: int,
    course_type: CourseType | None = None,
    location: Location | None = None,
    professor: Professor | None = None,
    substitute_professor: Professor | None = None,
    recurrence_end_date: date | None = None,
) -> AdminSessionOut:
    habitual_teacher_display_name = _session_teacher_display_name(professor)
    substitute_teacher_display_name = _session_teacher_display_name(substitute_professor) if substitute_professor is not None else None
    effective_teacher_id = session_obj.substitute_teacher_id or session_obj.professor_id
    effective_teacher_display_name = substitute_teacher_display_name or habitual_teacher_display_name
    allows_student_bookings = bool(course_type.allows_student_bookings) if course_type is not None else True
    visibility_scopes = resolve_session_visibility_scopes(session_obj)
    booking_scopes = resolve_session_booking_scopes(session_obj, allows_student_bookings=allows_student_bookings)
    visibility_scope = primary_session_audience_scope(visibility_scopes)
    booking_scope = primary_session_audience_scope(booking_scopes, fallback=SessionAudienceScope.PRIVATE)
    is_private, allow_online_booking = legacy_flags_from_scopes(
        visibility_scopes=visibility_scopes,
        booking_scopes=booking_scopes,
        allows_student_bookings=allows_student_bookings,
    )
    location_label = _session_location_label(location)
    type_label = _session_type_label(session_obj, course_type=course_type, location=location)
    status_label = _session_status_label(session_obj.status)
    resolved_recurrence_end_date = recurrence_end_date or session_obj.recurrence_until_date

    return AdminSessionOut(
        id=session_obj.id,
        course_type_id=session_obj.course_type_id,
        location_id=session_obj.location_id,
        professor_id=session_obj.professor_id,
        substitute_teacher_id=session_obj.substitute_teacher_id,
        substitute_set_at=session_obj.substitute_set_at,
        substitute_set_by=session_obj.substitute_set_by,
        substitute_note=session_obj.substitute_note,
        teacher_id=effective_teacher_id,
        teacher_display_name=effective_teacher_display_name,
        habitual_teacher_id=session_obj.professor_id,
        habitual_teacher_display_name=habitual_teacher_display_name,
        substitute_teacher_display_name=substitute_teacher_display_name,
        effective_teacher_id=effective_teacher_id,
        effective_teacher_display_name=effective_teacher_display_name,
        requires_professor=bool(course_type.requires_professor) if course_type is not None else True,
        allows_student_bookings=bool(course_type.allows_student_bookings) if course_type is not None else True,
        supports_student_time_overrides=bool(course_type.supports_student_time_overrides) if course_type is not None else False,
        location_label=location_label,
        type_label=type_label,
        status_label=status_label,
        title=session_obj.title,
        description=session_obj.description,
        public_description=session_obj.description,
        private_description=session_obj.private_description,
        professor_reminder_note=session_obj.professor_reminder_note,
        group_note=session_obj.group_note,
        internal_note=session_obj.internal_note,
        start_at_utc=session_obj.start_at_utc,
        end_at_utc=session_obj.end_at_utc,
        is_all_day=session_obj.is_all_day,
        capacity_max=session_obj.capacity_max,
        booked_count=booked_count,
        status=session_obj.status,
        auto_cancel_deadline_utc=session_obj.auto_cancel_deadline_utc,
        auto_cancel_rule_enabled_override=session_obj.auto_cancel_rule_enabled_override,
        auto_cancel_if_booked_less_than_override=session_obj.auto_cancel_if_booked_less_than_override,
        auto_cancel_hours_before_start_override=session_obj.auto_cancel_hours_before_start_override,
        cancel_reason=session_obj.cancel_reason,
        zoom_link=session_obj.zoom_link,
        visibility_scopes=visibility_scopes,
        booking_scopes=booking_scopes,
        visibility_scope=visibility_scope,
        booking_scope=booking_scope,
        is_private=is_private,
        allow_online_booking=allow_online_booking,
        external_booking_price_ttc=session_obj.external_booking_price_ttc,
        show_external_remaining_seats=bool(session_obj.show_external_remaining_seats),
        timezone=session_obj.timezone,
        recurrence_group_id=session_obj.recurrence_group_id,
        recurrence_rule=session_obj.recurrence_rule,
        recurrence_end_date=(
            resolved_recurrence_end_date
            if resolved_recurrence_end_date is not None and session_obj.recurrence_group_id is not None
            else None
        ),
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at,
    )


def _recurrence_end_date_map(
    db: Session,
    *,
    recurrence_group_ids: list[UUID | None],
) -> dict[UUID, date]:
    filtered_ids = [group_id for group_id in recurrence_group_ids if group_id is not None]
    if not filtered_ids:
        return {}

    rows = db.execute(
        select(
            CourseSession.recurrence_group_id,
            func.max(CourseSession.recurrence_until_date),
            func.max(CourseSession.start_at_utc),
            func.max(CourseSession.timezone),
        )
        .where(CourseSession.recurrence_group_id.in_(filtered_ids))
        .group_by(CourseSession.recurrence_group_id)
    ).all()

    result: dict[UUID, date] = {}
    for group_id, explicit_until_date, end_at, timezone_name in rows:
        if group_id is None:
            continue
        if explicit_until_date is not None:
            result[group_id] = explicit_until_date
            continue
        if end_at is None:
            continue
        result[group_id] = _local_date_in_timezone(end_at, _normalize_session_timezone(timezone_name or "UTC"))
    return result


def _client_display_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _parse_student_time_local(value: str | None) -> time | None:
    raw = (value or "").strip()
    if not raw:
        return None
    match = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", raw)
    if match is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Horaire eleve invalide")
    return time(hour=int(match.group(1)), minute=int(match.group(2)))


def _student_time_override_for_session(
    *,
    session_obj: CourseSession,
    course_type: CourseType,
    start_time_local: str | None,
    end_time_local: str | None,
) -> tuple[datetime | None, datetime | None]:
    start_time = _parse_student_time_local(start_time_local)
    end_time = _parse_student_time_local(end_time_local)
    if start_time is None and end_time is None:
        return None, None
    if start_time is None or end_time is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Renseigner le debut et la fin de l horaire eleve",
        )
    if not bool(course_type.supports_student_time_overrides):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cette activite ne permet pas les horaires eleves decales",
        )

    tz = ZoneInfo(_normalize_session_timezone(session_obj.timezone))
    session_start_local = session_obj.start_at_utc.astimezone(tz)
    session_end_local = session_obj.end_at_utc.astimezone(tz)
    student_start_local = datetime.combine(session_start_local.date(), start_time, tzinfo=tz)
    student_end_local = datetime.combine(session_start_local.date(), end_time, tzinfo=tz)
    if student_end_local <= student_start_local:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fin doit etre apres le debut")
    if student_start_local < session_start_local or student_end_local > session_end_local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="L horaire eleve doit rester dans le creneau professeur",
        )
    return student_start_local.astimezone(timezone.utc), student_end_local.astimezone(timezone.utc)


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
        student_start_at_utc=booking.student_start_at_utc,
        student_end_at_utc=booking.student_end_at_utc,
        waitlist_position=_waitlist_position(db, booking),
        student_note=booking.student_note,
        internal_note=booking.internal_note,
    )


def _school_year_label_for_day(value: date) -> str:
    if value.month >= 8:
        return f"{value.year}-{value.year + 1}"
    return f"{value.year - 1}-{value.year}"


def _school_year_bounds_utc(label: str) -> tuple[datetime, datetime]:
    match = re.match(r"^\s*(20\d{2})\s*[-/]\s*(20\d{2})\s*$", label or "")
    if match is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid school year")
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year != start_year + 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid school year")
    return (
        datetime(start_year, 8, 1, tzinfo=timezone.utc),
        datetime(end_year, 8, 1, tzinfo=timezone.utc),
    )


def _available_school_years(db: Session) -> list[str]:
    starts = db.scalars(select(CourseSession.start_at_utc).order_by(CourseSession.start_at_utc.desc()).limit(3000)).all()
    labels = sorted({_school_year_label_for_day(start.astimezone(timezone.utc).date()) for start in starts}, reverse=True)
    if "2026-2027" not in labels:
        labels.insert(0, "2026-2027")
    return labels or ["2026-2027"]


def _planning_reorganization_locations(
    db: Session,
    *,
    season_start_utc: datetime,
    season_end_utc: datetime,
) -> list[Location]:
    rows = db.scalars(
        select(Location)
        .join(CourseSession, CourseSession.location_id == Location.id)
        .where(
            CourseSession.start_at_utc >= season_start_utc,
            CourseSession.start_at_utc < season_end_utc,
        )
        .distinct()
        .order_by(Location.name.asc())
    ).all()
    if rows:
        return rows
    return db.scalars(select(Location).where(Location.active.is_(True)).order_by(Location.name.asc())).all()


def _planning_reorganization_available_days(
    db: Session,
    *,
    location_id: UUID,
    season_start_utc: datetime,
    season_end_utc: datetime,
) -> list[date]:
    rows = db.execute(
        select(CourseSession.start_at_utc, CourseSession.timezone)
        .where(
            CourseSession.location_id == location_id,
            CourseSession.start_at_utc >= season_start_utc,
            CourseSession.start_at_utc < season_end_utc,
        )
        .order_by(CourseSession.start_at_utc.asc())
    ).all()
    return sorted(
        {
            _local_date_in_timezone(start_at, _normalize_session_timezone(timezone_name or "Europe/Paris"))
            for start_at, timezone_name in rows
        }
    )


def _planning_reorganization_session_out(
    session_obj: CourseSession,
    *,
    course_type: CourseType,
    location: Location,
    professor: Professor | None,
    substitute_professor: Professor | None,
    booked_count: int,
    bookings: list[AdminPlanningReorganizationBookingOut],
) -> AdminPlanningReorganizationSessionOut:
    return AdminPlanningReorganizationSessionOut(
        id=session_obj.id,
        title=session_obj.title,
        type_label=_session_type_label(session_obj, course_type=course_type, location=location),
        location_id=session_obj.location_id,
        location_label=_session_location_label(location),
        teacher_display_name=_session_teacher_display_name(substitute_professor or professor),
        start_at_utc=session_obj.start_at_utc,
        end_at_utc=session_obj.end_at_utc,
        timezone=session_obj.timezone,
        capacity_max=session_obj.capacity_max,
        booked_count=booked_count,
        recurrence_group_id=session_obj.recurrence_group_id,
        recurrence_rule=session_obj.recurrence_rule,
        status=session_obj.status,
        bookings=bookings,
    )


def _copy_booking_payload(source: Booking, target: Booking) -> None:
    target.client_plan_subscription_id = source.client_plan_subscription_id
    target.status = source.status
    target.booked_at = source.booked_at
    target.cancelled_at = None
    target.cancellation_reason = None
    target.price_excl_vat_snapshot = source.price_excl_vat_snapshot
    target.vat_rate_snapshot = source.vat_rate_snapshot
    target.vat_amount_snapshot = source.vat_amount_snapshot
    target.total_incl_vat_snapshot = source.total_incl_vat_snapshot
    target.currency_snapshot = source.currency_snapshot
    target.student_note = source.student_note
    target.internal_note = source.internal_note


def _cancel_pending_notification_reminders_for_booking(
    db: Session,
    *,
    booking_id: UUID,
    reason: str,
    now: datetime,
) -> int:
    notifications = db.scalars(
        select(Notification).where(
            Notification.booking_id == booking_id,
            Notification.notification_type.in_(
                [
                    NOTIFICATION_TYPE_REMINDER_EMAIL,
                    NOTIFICATION_TYPE_REMINDER_SMS,
                ]
            ),
            Notification.status.in_([NOTIFICATION_STATUS_PENDING, NOTIFICATION_STATUS_QUEUED]),
        )
    ).all()

    for notification in notifications:
        notification.status = NOTIFICATION_STATUS_CANCELLED
        notification.skipped_at = now
        notification.failure_reason = reason
        notification.updated_at = now

    return len(notifications)


def _move_planning_reorganization_booking_occurrence(
    db: Session,
    *,
    booking: Booking,
    source_session: CourseSession,
    target_session: CourseSession,
    now: datetime,
) -> tuple[bool, str | None]:
    if source_session.id == target_session.id:
        return False, "Eleve deja sur ce creneau"
    if booking.status not in BOOKING_STATUSES_ACTIVE:
        return False, "Reservation inactive ignoree"
    if target_session.status != SessionStatus.SCHEDULED:
        return False, "Creneau cible non planifie"

    target_course_type = db.scalar(select(CourseType).where(CourseType.id == target_session.course_type_id))
    if target_course_type is None:
        return False, "Activite du creneau cible introuvable"
    if not bool(target_course_type.allows_student_bookings):
        return False, "Creneau cible sans inscription eleve"

    existing_target_booking = db.scalar(
        select(Booking)
        .where(
            Booking.session_id == target_session.id,
            Booking.user_id == booking.user_id,
        )
        .with_for_update()
    )
    if existing_target_booking is not None and existing_target_booking.id != booking.id:
        if existing_target_booking.status != BookingStatus.CANCELLED:
            return False, "Eleve deja inscrit sur le creneau cible"
        target_booking = existing_target_booking
    else:
        target_booking = booking

    same_time_booking = db.scalar(
        select(Booking)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == booking.user_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            Booking.id != booking.id,
            Booking.id != target_booking.id,
            CourseSession.location_id == target_session.location_id,
            CourseSession.start_at_utc == target_session.start_at_utc,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .limit(1)
        .with_for_update()
    )
    if same_time_booking is not None:
        return False, "Eleve deja inscrit sur un creneau au meme horaire"

    if booking.status in BOOKING_STATUSES_COUNTED_AS_RESERVED:
        reserved_count = _booked_count_by_session(db, target_session.id)
        if reserved_count >= target_session.capacity_max and target_booking.id == booking.id:
            return False, "Creneau cible complet"
        if reserved_count >= target_session.capacity_max and target_booking.id != booking.id:
            return False, "Creneau cible complet"

    if target_booking.id == booking.id:
        booking.session_id = target_session.id
        booking.student_start_at_utc = None
        booking.student_end_at_utc = None
        moved_booking = booking
    else:
        _copy_booking_payload(booking, target_booking)
        target_booking.student_start_at_utc = None
        target_booking.student_end_at_utc = None
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = "ADMIN_MOVED_TO_ANOTHER_SLOT"
        skip_pending_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Booking moved by admin",
            now=now,
        )
        _cancel_pending_notification_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Booking moved by admin",
            now=now,
        )
        moved_booking = target_booking

    if moved_booking.status == BookingStatus.BOOKED:
        _cancel_pending_notification_reminders_for_booking(
            db,
            booking_id=moved_booking.id,
            reason="Booking moved by admin",
            now=now,
        )
        ensure_booking_reminder(
            db,
            booking=moved_booking,
            session_obj=target_session,
            now=now,
        )
    return True, None


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


def _display_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _normalize_email_recipient(value: str) -> str | None:
    candidate = value.strip().lower()
    if not candidate:
        return None
    if EMAIL_RECIPIENT_RE.match(candidate) is None:
        return None
    return candidate


def _normalize_phone_recipient(value: str) -> str | None:
    candidate = PHONE_CLEAN_RE.sub("", value.strip())
    if candidate.startswith("00"):
        candidate = f"+{candidate[2:]}"
    if not candidate:
        return None
    if candidate.startswith("+"):
        digits = candidate[1:]
        if not digits.isdigit() or len(digits) < 8:
            return None
        return f"+{digits}"
    if not candidate.isdigit() or len(candidate) < 8:
        return None
    return candidate


def _preferred_sms_recipient(user: User) -> str | None:
    for raw in (user.mobile_phone_1, user.mobile_phone_2, user.phone, user.home_phone):
        if not raw:
            continue
        normalized = _normalize_phone_recipient(raw)
        if normalized:
            return normalized
    return None


def _session_active_student_ids(db: Session, *, session_id: UUID) -> set[UUID]:
    rows = db.scalars(
        select(Booking.user_id).where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
    ).all()
    return {user_id for user_id in rows if user_id is not None}


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


def _load_admin_session_with_refs(
    db: Session,
    *,
    session_id: UUID,
    for_update: bool = False,
) -> tuple[CourseSession, CourseType, Location, Professor | None, Professor | None] | None:
    substitute_professor = aliased(Professor, name="substitute_professor")
    stmt = (
        select(CourseSession, CourseType, Location, Professor, substitute_professor)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
        .where(CourseSession.id == session_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = db.execute(stmt).first()
    if row is None:
        return None
    return row[0], row[1], row[2], row[3], row[4]


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
    professor_id: UUID | None,
    enforce_planning_allowed: bool = True,
) -> tuple[CourseType, Location, Professor | None]:
    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")
    if not course_type.active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Activity is inactive")

    location = db.scalar(select(Location).where(Location.id == location_id))
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    professor: Professor | None = None
    if professor_id is not None:
        professor = db.scalar(select(Professor).where(Professor.id == professor_id))
        if professor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor not found")
    elif bool(course_type.requires_professor):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Professor is required for this activity",
        )

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


def _safe_zoneinfo(value: str | None) -> ZoneInfo:
    timezone_name = (value or "").strip() or "Europe/Paris"
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def _start_of_utc_day(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _add_months_utc(base: datetime, months: int) -> datetime:
    year = base.year + ((base.month - 1 + months) // 12)
    month = ((base.month - 1 + months) % 12) + 1
    day = min(base.day, monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


def _add_months_local(base: datetime, months: int) -> datetime:
    year = base.year + ((base.month - 1 + months) // 12)
    month = ((base.month - 1 + months) % 12) + 1
    day = min(base.day, monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


def _normalize_recurrence_frequency(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in {"DAILY", "WEEKLY", "MONTHLY"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid recurrence frequency",
        )
    return normalized


def _normalize_recurrence_interval(value: int | None) -> int:
    interval = int(value or 1)
    if interval < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid recurrence interval",
        )
    return interval


def _normalize_recurrence_time_basis(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return "LOCAL"
    if normalized not in {"LOCAL", "UTC"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid recurrence time basis",
        )
    return normalized


def _serialize_recurrence_rule(*, frequency: str, interval: int, time_basis: str) -> str:
    normalized_frequency = _normalize_recurrence_frequency(frequency)
    normalized_interval = _normalize_recurrence_interval(interval)
    normalized_time_basis = _normalize_recurrence_time_basis(time_basis)
    if normalized_interval == 1:
        return f"{normalized_frequency}@{normalized_time_basis}"
    return f"{normalized_frequency}:{normalized_interval}@{normalized_time_basis}"


def _parse_recurrence_rule(value: str | None) -> tuple[str, int, str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return ("WEEKLY", 1, "LOCAL")

    time_basis = "LOCAL"
    if "@" in raw:
        raw, time_basis_raw = raw.split("@", 1)
        time_basis = _normalize_recurrence_time_basis(time_basis_raw or "LOCAL")

    if ":" not in raw:
        return (_normalize_recurrence_frequency(raw), 1, time_basis)

    frequency_raw, interval_raw = raw.split(":", 1)
    frequency = _normalize_recurrence_frequency(frequency_raw)
    try:
        interval_value = int(interval_raw)
    except ValueError:
        interval_value = 1
    interval = _normalize_recurrence_interval(interval_value)
    return (frequency, interval, time_basis)


def _local_date_in_timezone(moment: datetime, timezone_name: str) -> date:
    return moment.astimezone(ZoneInfo(timezone_name)).date()


def _utc_from_local_wall_clock(local_moment: datetime, *, timezone_name: str) -> datetime:
    zone = ZoneInfo(timezone_name)
    requested_marker = datetime(
        local_moment.year,
        local_moment.month,
        local_moment.day,
        local_moment.hour,
        local_moment.minute,
        local_moment.second,
        local_moment.microsecond,
        tzinfo=timezone.utc,
    )

    candidate = requested_marker
    for _ in range(4):
        observed = candidate.astimezone(zone)
        observed_marker = datetime(
            observed.year,
            observed.month,
            observed.day,
            observed.hour,
            observed.minute,
            observed.second,
            observed.microsecond,
            tzinfo=timezone.utc,
        )
        delta = requested_marker - observed_marker
        candidate = candidate + delta
        if delta == timedelta(0):
            break
    return candidate.astimezone(timezone.utc)


def _advance_recurrence_datetime(
    base: datetime,
    *,
    frequency: str,
    interval: int,
    offset: int,
    timezone_name: str,
    time_basis: str,
) -> datetime:
    if offset <= 0:
        return base
    normalized_frequency = _normalize_recurrence_frequency(frequency)
    normalized_interval = _normalize_recurrence_interval(interval)
    normalized_time_basis = _normalize_recurrence_time_basis(time_basis)
    steps = offset * normalized_interval
    if normalized_time_basis == "LOCAL":
        local_base = base.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
        if normalized_frequency == "DAILY":
            local_target = local_base + timedelta(days=steps)
        elif normalized_frequency == "MONTHLY":
            local_target = _add_months_local(local_base, steps)
        else:
            local_target = local_base + timedelta(weeks=steps)
        return _utc_from_local_wall_clock(local_target, timezone_name=timezone_name)
    if normalized_frequency == "DAILY":
        return base + timedelta(days=steps)
    if normalized_frequency == "MONTHLY":
        return _add_months_utc(base, steps)
    return base + timedelta(weeks=steps)


def _resolve_recurrence_occurrences(
    *,
    recurrence_frequency: str,
    recurrence_interval: int,
    recurrence_until_date: date | None,
    anchor_start_at_utc: datetime,
    session_timezone: str,
    recurrence_time_basis: str,
) -> int:
    if recurrence_until_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recurrence requires an end date",
        )

    anchor_day = _local_date_in_timezone(anchor_start_at_utc, session_timezone)
    if recurrence_until_date < anchor_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Recurrence end date must be after start date",
        )

    limit = 366
    count = 1
    probe = anchor_start_at_utc
    while count < limit:
        probe = _advance_recurrence_datetime(
            probe,
            frequency=recurrence_frequency,
            interval=recurrence_interval,
            offset=1,
            timezone_name=session_timezone,
            time_basis=recurrence_time_basis,
        )
        if _local_date_in_timezone(probe, session_timezone) > recurrence_until_date:
            break
        count += 1

    return count


def _recurrence_datetimes_until(
    *,
    anchor_start_at_utc: datetime,
    recurrence_frequency: str,
    recurrence_interval: int,
    recurrence_until_date: date,
    session_timezone: str,
    recurrence_time_basis: str,
    limit: int = 366,
) -> list[datetime]:
    out: list[datetime] = []
    offset = 0
    while offset < limit:
        candidate = _advance_recurrence_datetime(
            anchor_start_at_utc,
            frequency=recurrence_frequency,
            interval=recurrence_interval,
            offset=offset,
            timezone_name=session_timezone,
            time_basis=recurrence_time_basis,
        )
        if _local_date_in_timezone(candidate, session_timezone) > recurrence_until_date:
            break
        out.append(candidate)
        offset += 1
    return out


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


def _parse_school_calendar_rows(db: Session) -> list[dict[str, object]]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_SCHOOL_CALENDARS_SETTING_KEY))
    if setting is None:
        return []
    try:
        parsed = json.loads(setting.value or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _safe_parse_iso_date(value: object | None) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _parse_school_year_bounds(label: str) -> tuple[date, date] | None:
    normalized = (label or "").strip()
    match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{4})", normalized)
    if match is None:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year < start_year:
        return None
    # School year in France: Sep 1 -> Aug 31.
    return (date(start_year, 9, 1), date(end_year, 8, 31))


def _school_year_label_for_day(day: date) -> str:
    start_year = day.year if day.month >= 9 else day.year - 1
    return f"{start_year}-{start_year + 1}"


def _default_school_year_label() -> str:
    try:
        today = datetime.now(ZoneInfo("Europe/Paris")).date()
    except Exception:
        today = datetime.now(timezone.utc).date()
    return _school_year_label_for_day(today)


def _available_school_year_labels(db: Session) -> list[str]:
    labels: set[str] = {_default_school_year_label()}

    quote_labels = db.scalars(select(Quote.school_year_label).where(Quote.school_year_label.is_not(None))).all()
    for value in quote_labels:
        raw = str(value or "").strip()
        if _parse_school_year_bounds(raw) is not None:
            labels.add(raw)

    session_month_rows = db.execute(
        select(
            func.extract("year", CourseSession.start_at_utc),
            func.extract("month", CourseSession.start_at_utc),
        )
        .where(CourseSession.status != SessionStatus.CANCELLED)
        .distinct()
    ).all()
    for year_raw, month_raw in session_month_rows:
        try:
            year_value = int(year_raw)
            month_value = int(month_raw)
            labels.add(_school_year_label_for_day(date(year_value, month_value, 1)))
        except Exception:
            continue

    return sorted(labels, key=lambda item: int(item.split("-", 1)[0]), reverse=True)


def _weekday_label(value: int) -> str:
    labels = [
        "Lundi",
        "Mardi",
        "Mercredi",
        "Jeudi",
        "Vendredi",
        "Samedi",
        "Dimanche",
    ]
    if 0 <= value < len(labels):
        return labels[value]
    return f"Jour {value}"


def _json_object_local(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list_local(value: object | None) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _parse_uuid_local(value: object | None) -> UUID | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except Exception:
        return None


def _planning_simulation_signature(
    *,
    location_id: UUID | None,
    course_type_id: UUID | None,
    weekday: int,
    start_time: str,
    end_time: str,
) -> str:
    return "|".join(
        [
            str(location_id or ""),
            str(course_type_id or ""),
            str(weekday),
            start_time.strip(),
            end_time.strip(),
        ]
    )


def _planning_simulation_live_slot_key(
    *,
    session_id: UUID,
    recurrence_group_id: UUID | None,
    signature: str,
) -> str:
    if recurrence_group_id is not None:
        return f"series::{recurrence_group_id}"
    return f"series-signature::{signature}"


def _planning_simulation_quote_person_key(quote: Quote, prospect: Prospect | None) -> str | None:
    if quote.client_id is not None:
        return f"client:{quote.client_id}"
    if prospect is not None and prospect.linked_client_id is not None:
        return f"client:{prospect.linked_client_id}"
    if quote.prospect_id is not None:
        return f"prospect:{quote.prospect_id}"
    return None


def _planning_simulation_search_text(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold()) if unicodedata.category(char) != "Mn"
    )


def _planning_simulation_entry_projected_count(entry: dict[str, object]) -> int:
    return (
        len(entry.get("_booked_user_ids", set()))
        + len(entry.get("_approved_quote_ids", set()))
        + len(entry.get("_pending_quote_ids", set()))
        + len(entry.get("_draft_quote_ids", set()))
    )


def _planning_simulation_select_live_slot_for_quote(
    slot_entries: dict[str, dict[str, object]],
    matching_live_keys: list[str],
) -> str | None:
    candidates: list[tuple[bool, int, int, str]] = []
    for slot_key in matching_live_keys:
        entry = slot_entries.get(slot_key)
        if entry is None:
            continue
        projected_count = _planning_simulation_entry_projected_count(entry)
        raw_capacity = entry.get("capacity_max")
        capacity = int(raw_capacity) if raw_capacity is not None else None
        remaining_capacity = 999_999 if capacity is None else capacity - projected_count
        candidates.append((remaining_capacity <= 0, projected_count, -remaining_capacity, slot_key))
    if not candidates:
        return None
    return sorted(candidates)[0][3]


def _planning_simulation_resolve_live_slot_for_quote(
    *,
    slot_entries: dict[str, dict[str, object]],
    live_slot_keys_by_signature: dict[str, set[str]],
    signature: str,
    block_series_key: str,
) -> str | None:
    matching_live_keys = sorted(live_slot_keys_by_signature.get(signature, set()))
    if len(matching_live_keys) > 1:
        return _planning_simulation_select_live_slot_for_quote(slot_entries, matching_live_keys)
    if len(matching_live_keys) == 1:
        return matching_live_keys[0]

    if block_series_key:
        candidate_key = f"series::{block_series_key}"
        if candidate_key in slot_entries:
            return candidate_key
    return None


def _planning_simulation_collective_piano_course_type_ids(db: Session) -> set[UUID]:
    rows = db.scalars(
        select(CourseType).where(
            CourseType.active.is_(True),
            func.upper(CourseType.code) != VACATION_COURSE_TYPE_CODE,
        )
    ).all()
    out: set[UUID] = set()
    excluded_terms = ("solfege", "eveil", "initiation", "studio", "repetition", "booster", "rattrap")
    for course_type in rows:
        searchable = _planning_simulation_search_text(f"{course_type.code or ''} {course_type.name or ''}")
        if "collectif" not in searchable and "collective" not in searchable:
            continue
        if any(term in searchable for term in excluded_terms):
            continue
        if "piano" in searchable or "ado" in searchable or "adulte" in searchable:
            out.add(course_type.id)
    return out


def _planning_simulation_person_name(
    *,
    first_name: str | None,
    last_name: str | None,
    fallback: str | None = None,
) -> str:
    full_name = " ".join(part for part in [(last_name or "").strip(), (first_name or "").strip()] if part).strip()
    return full_name or (fallback or "").strip() or "Sans nom"


def _planning_simulation_user_name(user: User | None) -> str | None:
    if user is None:
        return None
    return _planning_simulation_person_name(
        first_name=user.first_name,
        last_name=user.last_name,
        fallback=user.email,
    )


def _planning_simulation_quote_student_name(
    *,
    quote: Quote,
    prospect: Prospect | None,
    client: User | None,
) -> str:
    client_name = _planning_simulation_user_name(client)
    if client_name:
        return client_name
    if prospect is not None:
        return _planning_simulation_person_name(
            first_name=prospect.first_name,
            last_name=prospect.last_name,
            fallback=prospect.email,
        )
    return f"Devis {quote.quote_number}"


def _planning_simulation_clean_location_label(value: object | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _parse_uuid_local(raw) is not None:
        return ""
    return raw


def _planning_simulation_quote_location_name(
    block: dict[str, object],
    *,
    resolved_location_name: str = "",
    course_type: CourseType | None = None,
) -> str:
    explicit_label = _planning_simulation_clean_location_label(
        block.get("location_label") or block.get("location_name")
    )
    if explicit_label:
        return explicit_label

    resolved_label = _planning_simulation_clean_location_label(resolved_location_name)
    if resolved_label:
        return resolved_label

    modality = str(block.get("modality") or "").strip().upper()
    activity_label = str(block.get("activity_label") or block.get("activity_name") or "").strip().casefold()
    if modality == "ONLINE" or (course_type is not None and course_type.mode == DeliveryMode.ONLINE):
        return "En ligne"
    if "en ligne" in activity_label or "online" in activity_label:
        return "En ligne"
    if modality == "ONSITE":
        return "Sur site"
    return "Lieu non defini"


def _school_calendar_updated_at(raw: dict[str, object]) -> datetime:
    value = str(raw.get("updated_at") or "").strip()
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _calendar_location_matches(raw: dict[str, object], *, location_id: UUID) -> bool:
    return str(raw.get("location_id") or "").strip() == str(location_id)


def _select_school_calendar_for_day(
    rows: list[dict[str, object]],
    *,
    location_id: UUID,
    day: date,
) -> dict[str, object] | None:
    location_rows = [
        item for item in rows if bool(item.get("is_active", True)) and _calendar_location_matches(item, location_id=location_id)
    ]
    if not location_rows:
        return None

    scoped: list[dict[str, object]] = []
    for item in location_rows:
        bounds = _parse_school_year_bounds(str(item.get("school_year_label") or ""))
        if bounds is None:
            continue
        start_day, end_day = bounds
        if start_day <= day <= end_day:
            scoped.append(item)
    if scoped:
        scoped.sort(key=_school_calendar_updated_at, reverse=True)
        return scoped[0]

    location_rows.sort(key=_school_calendar_updated_at, reverse=True)
    return location_rows[0]


def _calendar_holiday_dates(raw: dict[str, object]) -> set[date]:
    values = raw.get("holiday_dates")
    if not isinstance(values, list):
        return set()
    out: set[date] = set()
    for entry in values:
        parsed = _safe_parse_iso_date(entry)
        if parsed is not None:
            out.add(parsed)
    return out


def _calendar_closure_dates(raw: dict[str, object]) -> set[date]:
    values = raw.get("closure_dates")
    if not isinstance(values, list):
        return set()
    out: set[date] = set()
    for entry in values:
        parsed = _safe_parse_iso_date(entry)
        if parsed is not None:
            out.add(parsed)
    return out


def _calendar_vacation_dates(raw: dict[str, object]) -> set[date]:
    values = raw.get("vacation_periods")
    if not isinstance(values, list):
        return set()
    out: set[date] = set()
    for entry in values:
        if not isinstance(entry, dict):
            continue
        start = _safe_parse_iso_date(entry.get("start_date"))
        end = _safe_parse_iso_date(entry.get("end_date"))
        if start is None or end is None or end < start:
            continue
        current = start
        while current <= end:
            out.add(current)
            current += timedelta(days=1)
    return out


def _is_blocked_by_school_calendar(
    db: Session,
    *,
    location_id: UUID,
    location_timezone: str,
    starts_at_utc: datetime,
    include_holidays: bool,
    include_school_vacations: bool,
    cache: dict[str, object],
) -> bool:
    if not include_holidays and not include_school_vacations:
        return False

    rows = cache.get("rows")
    if not isinstance(rows, list):
        rows = _parse_school_calendar_rows(db)
        cache["rows"] = rows

    try:
        local_day = starts_at_utc.astimezone(ZoneInfo(location_timezone)).date()
    except Exception:
        local_day = starts_at_utc.date()

    calendar_row = _select_school_calendar_for_day(rows, location_id=location_id, day=local_day)
    if calendar_row is None:
        return False

    day_cache = cache.setdefault("day_cache", {})
    day_key = f"{calendar_row.get('id')}::{local_day.isoformat()}"
    cached = day_cache.get(day_key)
    if isinstance(cached, tuple) and len(cached) == 2:
        is_holiday, is_vacation = bool(cached[0]), bool(cached[1])
    else:
        holiday_dates = _calendar_holiday_dates(calendar_row)
        vacation_dates = _calendar_vacation_dates(calendar_row)
        closure_dates = _calendar_closure_dates(calendar_row)
        is_holiday = local_day in holiday_dates
        is_vacation = local_day in vacation_dates or local_day in closure_dates
        day_cache[day_key] = (is_holiday, is_vacation)

    return (include_holidays and is_holiday) or (include_school_vacations and is_vacation)


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
    location_id: UUID,
    course_type_id: UUID,
    auto_cancel_rule_enabled_override: bool | None = None,
    auto_cancel_hours_before_start_override: int | None = None,
) -> datetime:
    if auto_cancel_deadline_utc is not None:
        return auto_cancel_deadline_utc

    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if auto_cancel_rule_enabled_override is True:
        hours = int(auto_cancel_hours_before_start_override or 0)
    elif auto_cancel_rule_enabled_override is False:
        hours = 0
    elif course_type is not None and bool(course_type.auto_cancel_rule_enabled):
        hours = int(course_type.auto_cancel_hours_before_start_override or 0)
    else:
        hours = 0
    hours = max(0, hours)
    # The legacy deadline column is non-null and must precede the start even
    # when the opt-in rule is disabled. Disabled rules are excluded by the job.
    return start_at_utc - timedelta(hours=hours) if hours > 0 else start_at_utc - timedelta(minutes=1)


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


def _duplicate_auto_cancel_deadline(
    *,
    source_start_at_utc: datetime,
    source_deadline_utc: datetime,
    duplicate_start_at_utc: datetime,
) -> datetime:
    deadline_delta = source_start_at_utc - source_deadline_utc
    duplicate_deadline = duplicate_start_at_utc - deadline_delta
    if duplicate_deadline >= duplicate_start_at_utc:
        # Legacy all-day blockers were created with a deadline equal to the slot start.
        # Keep duplication working by nudging the copied deadline just before the new slot.
        return duplicate_start_at_utc - timedelta(seconds=1)
    return duplicate_deadline


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


def _resolve_booking_scope(
    *,
    scope: BookingScope | None,
    apply_scope: ApplyScope | None,
) -> ApplyScope:
    if scope is not None:
        return "SERIES_FUTURE" if scope == "SERIES_FUTURE" else "ONE"
    if apply_scope is not None:
        if apply_scope == "SERIES_ALL":
            return "SERIES_FUTURE"
        return apply_scope
    return "ONE"


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


def _session_student_recipient_map(
    db: Session,
    *,
    student_ids: set[UUID],
    channel: CommunicationChannel,
) -> dict[str, UUID]:
    if not student_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(student_ids))).all()
    recipients: dict[str, UUID | None] = {}
    for user in users:
        if channel == CommunicationChannel.EMAIL:
            if not user.email_opt_in:
                continue
            email = _normalize_email_recipient(user.email)
            if email:
                recipients.setdefault(email, user.id)
            continue
        if not user.sms_opt_in:
            continue
        phone = _preferred_sms_recipient(user)
        if phone:
            recipients.setdefault(phone, user.id)
    return recipients


def _session_parent_recipient_map(
    db: Session,
    *,
    student_ids: set[UUID],
    channel: CommunicationChannel,
) -> dict[str, UUID]:
    if not student_ids:
        return {}
    parent_rows = db.scalars(
        select(User)
        .join(ClientFamilyLink, ClientFamilyLink.adult_user_id == User.id)
        .where(ClientFamilyLink.child_user_id.in_(student_ids))
    ).all()
    recipients: dict[str, UUID] = {}
    for parent in parent_rows:
        if channel == CommunicationChannel.EMAIL:
            if not parent.email_opt_in:
                continue
            email = _normalize_email_recipient(parent.email)
            if email:
                recipients.setdefault(email, parent.id)
            continue
        if not parent.sms_opt_in:
            continue
        phone = _preferred_sms_recipient(parent)
        if phone:
            recipients.setdefault(phone, parent.id)
    return recipients


def _single_user_recipient_map(
    *,
    user: User,
    channel: CommunicationChannel,
    enforce_opt_in: bool = True,
) -> dict[str, UUID]:
    if channel == CommunicationChannel.EMAIL:
        if enforce_opt_in and not user.email_opt_in:
            return {}
        email = _normalize_email_recipient(user.email)
        if not email:
            return {}
        return {email: user.id}

    if enforce_opt_in and not user.sms_opt_in:
        return {}
    phone = _preferred_sms_recipient(user)
    if not phone:
        return {}
    return {phone: user.id}


def _session_professor_recipient_map(
    db: Session,
    *,
    session_obj: CourseSession,
    channel: CommunicationChannel,
) -> dict[str, UUID | None]:
    professor = db.scalar(select(Professor).where(Professor.id == session_obj.professor_id))
    if professor is None:
        return {}
    if channel == CommunicationChannel.EMAIL:
        email = _normalize_email_recipient(professor.email)
        if not email:
            return {}
        return {email: None}
    phone = _normalize_phone_recipient(professor.phone or "")
    if not phone:
        return {}
    return {phone: None}


def _admin_recipient_map(
    db: Session,
    *,
    channel: CommunicationChannel,
    exclude_user_id: UUID | None = None,
) -> dict[str, UUID]:
    admin_users = db.scalars(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))).all()
    recipients: dict[str, UUID | None] = {}
    for admin_user in admin_users:
        if exclude_user_id is not None and admin_user.id == exclude_user_id:
            continue
        recipients.update(
            _single_user_recipient_map(
                user=admin_user,
                channel=channel,
                enforce_opt_in=True,
            )
        )
    return recipients


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


@router.get("/presence", response_model=AdminOnlinePresenceOut)
def admin_online_presence(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_planning", "can_view_clients")),
) -> AdminOnlinePresenceOut:
    now = datetime.now(timezone.utc)
    active_window_seconds = 90
    cutoff = now - timedelta(seconds=active_window_seconds)
    rows = db.execute(
        select(UserPresence.user_id, UserPresence.channel, UserPresence.last_seen_at, User.role)
        .join(User, User.id == UserPresence.user_id)
        .where(UserPresence.last_seen_at >= cutoff, User.is_active.is_(True))
    ).all()

    latest_by_user: dict[UUID, tuple[datetime, str, UserRole]] = {}
    for row in rows:
        previous = latest_by_user.get(row.user_id)
        if previous is None or row.last_seen_at > previous[0]:
            latest_by_user[row.user_id] = (row.last_seen_at, row.channel, row.role)

    web_users = {user_id for user_id, (_, channel, _) in latest_by_user.items() if channel == "WEB"}
    mobile_users = {user_id for user_id, (_, channel, _) in latest_by_user.items() if channel == "MOBILE_APP"}
    client_users = {user_id for user_id, (_, _, role) in latest_by_user.items() if role == UserRole.CLIENT}
    professor_users = {user_id for user_id, (_, _, role) in latest_by_user.items() if role == UserRole.PROF}
    admin_users = {user_id for user_id, (_, _, role) in latest_by_user.items() if role == UserRole.ADMIN}

    return AdminOnlinePresenceOut(
        generated_at=now,
        active_window_seconds=active_window_seconds,
        total=len(latest_by_user),
        web=len(web_users),
        mobile_app=len(mobile_users),
        clients=len(client_users),
        professors=len(professor_users),
        admins=len(admin_users),
    )


@router.get("/professors", response_model=list[AdminProfessorOut])
def list_admin_professors(
    active: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_planning", "can_access_collaborators")),
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
            zoom_link=prof.zoom_link,
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
    _: User = Depends(require_admin_or_permissions("can_view_planning")),
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
    _: User = Depends(require_admin_or_permissions("can_view_planning")),
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


@router.get("/plannings/simulation", response_model=AdminPlanningSimulationOut)
def get_planning_simulation(
    school_year_label: str | None = Query(default=None),
    location_id: UUID | None = Query(default=None),
    activity_id: UUID | None = Query(default=None),
    activity_group: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_permissions("can_view_planning_simulation")),
) -> AdminPlanningSimulationOut:
    permission_map = get_admin_permission_map(db, current_user)
    scoped_location_id = permission_map.get("planning_simulation_location_id")
    if scoped_location_id is not None:
        try:
            scoped_location_uuid = scoped_location_id if isinstance(scoped_location_id, UUID) else UUID(str(scoped_location_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid planning simulation location scope") from exc
        if location_id is not None and location_id != scoped_location_uuid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning simulation location not allowed")
        location_id = scoped_location_uuid

    available_school_years = _available_school_year_labels(db)
    requested_school_year = (school_year_label or "").strip() or _default_school_year_label()
    bounds = _parse_school_year_bounds(requested_school_year)
    if bounds is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid school year label")
    season_start, season_end = bounds
    if requested_school_year not in available_school_years:
        available_school_years = sorted(
            {requested_school_year, *available_school_years},
            key=lambda item: int(item.split("-", 1)[0]),
            reverse=True,
        )

    if location_id is not None:
        _get_location_or_404(db, location_id)
    if activity_id is not None:
        requested_activity_code = db.scalar(select(CourseType.code).where(CourseType.id == activity_id).limit(1))
        if requested_activity_code is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")
        if requested_activity_code.upper() == VACATION_COURSE_TYPE_CODE:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Vacation course types are excluded")
    normalized_activity_group = str(activity_group or "").strip().lower() or None
    if activity_id is not None:
        normalized_activity_group = None
    elif normalized_activity_group in {None, "all"}:
        normalized_activity_group = None
    elif normalized_activity_group != PLANNING_SIMULATION_ACTIVITY_GROUP_COLLECTIVE_PIANO:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid activity group")

    activity_filter_ids: set[UUID] = set()
    if activity_id is not None:
        activity_filter_ids.add(activity_id)
    elif normalized_activity_group == PLANNING_SIMULATION_ACTIVITY_GROUP_COLLECTIVE_PIANO:
        activity_filter_ids = _planning_simulation_collective_piano_course_type_ids(db)

    vacation_course_type_ids = set(
        db.scalars(select(CourseType.id).where(func.upper(CourseType.code) == VACATION_COURSE_TYPE_CODE)).all()
    )

    slot_entries: dict[str, dict[str, object]] = {}
    session_slot_by_id: dict[UUID, str] = {}
    session_signature_by_id: dict[UUID, str] = {}
    reference_session_id_by_slot_key: dict[str, UUID] = {}
    live_slot_keys_by_signature: dict[str, set[str]] = {}
    live_signatures_by_person_key: dict[str, set[str]] = {}
    quote_location_name_by_id: dict[UUID, str] = {}
    quote_course_type_by_id: dict[UUID, CourseType | None] = {}

    def ensure_slot(
        *,
        slot_key: str,
        slot_label_location_id: UUID | None,
        slot_label_location_name: str,
        slot_label_timezone: str | None,
        slot_label_activity_id: UUID | None,
        slot_label_activity_name: str,
        slot_label_activity_color: str | None,
        slot_label_activity_mode: DeliveryMode | None,
        weekday: int,
        start_time: str,
        end_time: str,
        quote_only: bool,
        note: str | None = None,
    ) -> dict[str, object]:
        existing = slot_entries.get(slot_key)
        if existing is not None:
            if note and note not in existing["notes"]:
                existing["notes"].append(note)
            if quote_only:
                existing["quote_only"] = bool(existing["quote_only"]) and True
            return existing
        payload = {
            "slot_key": slot_key,
            "location_id": slot_label_location_id,
            "location_name": slot_label_location_name,
            "location_timezone": slot_label_timezone,
            "course_type_id": slot_label_activity_id,
            "course_type_name": slot_label_activity_name,
            "course_type_color_hex": slot_label_activity_color,
            "course_type_mode": slot_label_activity_mode,
            "weekday": weekday,
            "weekday_label": _weekday_label(weekday),
            "start_time": start_time,
            "end_time": end_time,
            "first_date": None,
            "last_date": None,
            "occurrence_count": 0,
            "live_session_count": 0,
            "capacity_min": None,
            "capacity_max": None,
            "_booked_user_ids": set(),
            "_booked_students": {},
            "_approved_quote_ids": set(),
            "_approved_quote_students": {},
            "_pending_quote_ids": set(),
            "_pending_quote_students": {},
            "_draft_quote_ids": set(),
            "_draft_quote_students": {},
            "quote_only": quote_only,
            "notes": [note] if note else [],
        }
        slot_entries[slot_key] = payload
        return payload

    session_query_start = datetime(season_start.year, 1, 1, tzinfo=timezone.utc)
    session_query_end = datetime(season_end.year + 1, 1, 1, tzinfo=timezone.utc)
    session_stmt = (
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            CourseSession.start_at_utc >= session_query_start,
            CourseSession.start_at_utc < session_query_end,
            CourseSession.status != SessionStatus.CANCELLED,
            func.upper(CourseType.code) != VACATION_COURSE_TYPE_CODE,
        )
        .order_by(Location.name.asc(), CourseType.name.asc(), CourseSession.start_at_utc.asc())
    )
    if location_id is not None:
        session_stmt = session_stmt.where(CourseSession.location_id == location_id)
    if activity_filter_ids:
        session_stmt = session_stmt.where(CourseSession.course_type_id.in_(list(activity_filter_ids)))

    session_rows = db.execute(session_stmt).all()
    for session_obj, course_type, location in session_rows:
        zone = _safe_zoneinfo(session_obj.timezone or location.timezone)
        local_start = session_obj.start_at_utc.astimezone(zone)
        local_end = session_obj.end_at_utc.astimezone(zone)
        local_day = local_start.date()
        if local_day < season_start or local_day > season_end:
            continue

        weekday = local_start.weekday()
        start_time = local_start.strftime("%H:%M")
        end_time = local_end.strftime("%H:%M")
        signature = _planning_simulation_signature(
            location_id=location.id,
            course_type_id=course_type.id,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
        )
        slot_key = _planning_simulation_live_slot_key(
            session_id=session_obj.id,
            recurrence_group_id=session_obj.recurrence_group_id,
            signature=signature,
        )
        live_slot_keys_by_signature.setdefault(signature, set()).add(slot_key)
        session_slot_by_id[session_obj.id] = slot_key
        session_signature_by_id[session_obj.id] = signature
        reference_session_id_by_slot_key.setdefault(slot_key, session_obj.id)

        entry = ensure_slot(
            slot_key=slot_key,
            slot_label_location_id=location.id,
            slot_label_location_name=location.name,
            slot_label_timezone=session_obj.timezone or location.timezone,
            slot_label_activity_id=course_type.id,
            slot_label_activity_name=course_type.name,
            slot_label_activity_color=course_type.color_hex,
            slot_label_activity_mode=course_type.mode,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            quote_only=False,
            note=None if session_obj.recurrence_group_id is not None else "Creation ponctuelle",
        )

        entry["occurrence_count"] = int(entry["occurrence_count"]) + 1
        entry["live_session_count"] = int(entry["live_session_count"]) + 1
        if entry["first_date"] is None or local_day < entry["first_date"]:
            entry["first_date"] = local_day
        if entry["last_date"] is None or local_day > entry["last_date"]:
            entry["last_date"] = local_day
        capacity_value = int(session_obj.capacity_max)
        current_min = entry["capacity_min"]
        current_max = entry["capacity_max"]
        entry["capacity_min"] = capacity_value if current_min is None else min(int(current_min), capacity_value)
        entry["capacity_max"] = capacity_value if current_max is None else max(int(current_max), capacity_value)

    if session_slot_by_id:
        reference_session_slot_by_id = {
            session_id: slot_key for slot_key, session_id in reference_session_id_by_slot_key.items()
        }
        booking_rows = db.execute(
            select(Booking.session_id, User.id, User.first_name, User.last_name, User.email)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.session_id.in_(list(session_slot_by_id.keys())),
                Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
            )
        ).all()
        for session_id, user_id, first_name, last_name, email in booking_rows:
            slot_key = session_slot_by_id.get(session_id)
            if slot_key is None:
                continue
            signature = session_signature_by_id.get(session_id)
            if signature:
                live_signatures_by_person_key.setdefault(f"client:{user_id}", set()).add(signature)
            counted_slot_key = reference_session_slot_by_id.get(session_id)
            if counted_slot_key is None:
                continue
            slot_entries[counted_slot_key]["_booked_user_ids"].add(str(user_id))
            slot_entries[counted_slot_key]["_booked_students"][str(user_id)] = _planning_simulation_person_name(
                first_name=first_name,
                last_name=last_name,
                fallback=email,
            )

    quote_client_alias = aliased(User)
    quote_rows = db.execute(
        select(Quote, QuoteAcceptanceFollowup, Prospect, quote_client_alias)
        .outerjoin(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
        .outerjoin(Prospect, Prospect.id == Quote.prospect_id)
        .outerjoin(quote_client_alias, quote_client_alias.id == Quote.client_id)
        .where(
            Quote.school_year_label == requested_school_year,
            Quote.status.in_(tuple(sorted(PLANNING_SIMULATION_QUOTE_RELEVANT_STATUSES))),
        )
    ).all()

    for quote, followup, prospect, quote_client in quote_rows:
        normalized_status = str(quote.status or "").strip().lower()
        if normalized_status in PLANNING_SIMULATION_QUOTE_APPROVED_STATUSES and followup is not None and followup.status == "completed":
            continue
        quote_person_key = _planning_simulation_quote_person_key(quote, prospect)

        if normalized_status in PLANNING_SIMULATION_QUOTE_APPROVED_STATUSES:
            bucket_name = "_approved_quote_ids"
            bucket_people_name = "_approved_quote_students"
        elif normalized_status in PLANNING_SIMULATION_QUOTE_PENDING_STATUSES:
            bucket_name = "_pending_quote_ids"
            bucket_people_name = "_pending_quote_students"
        else:
            bucket_name = "_draft_quote_ids"
            bucket_people_name = "_draft_quote_students"

        snapshot = _json_object_local(quote.calendar_snapshot)
        for raw_block in _json_list_local(snapshot.get("blocks")):
            block = _json_object_local(raw_block)
            if not block:
                continue
            if bool(block.get("selection_pending")):
                continue

            block_weekday_raw = block.get("weekday")
            try:
                block_weekday = int(block_weekday_raw)
            except Exception:
                continue
            if block_weekday < 0 or block_weekday > 6:
                continue

            block_start_time = str(block.get("start_time") or "").strip()
            block_end_time = str(block.get("end_time") or "").strip()
            if not block_start_time or not block_end_time:
                continue

            block_location_id = _parse_uuid_local(block.get("location_id"))
            block_activity_id = _parse_uuid_local(block.get("activity_id"))
            if location_id is not None and block_location_id != location_id:
                continue
            if activity_filter_ids and block_activity_id not in activity_filter_ids:
                continue
            if block_activity_id in vacation_course_type_ids:
                continue
            block_course_type: CourseType | None = None
            if block_activity_id is not None:
                if block_activity_id not in quote_course_type_by_id:
                    quote_course_type_by_id[block_activity_id] = db.scalar(
                        select(CourseType).where(CourseType.id == block_activity_id).limit(1)
                    )
                block_course_type = quote_course_type_by_id.get(block_activity_id)
            resolved_location_name = ""
            if block_location_id is not None:
                if block_location_id not in quote_location_name_by_id:
                    quote_location_name_by_id[block_location_id] = str(
                        db.scalar(select(Location.name).where(Location.id == block_location_id).limit(1)) or ""
                    ).strip()
                resolved_location_name = quote_location_name_by_id.get(block_location_id, "")
            block_location_name = _planning_simulation_quote_location_name(
                block,
                resolved_location_name=resolved_location_name,
                course_type=block_course_type,
            )

            block_start_date = _safe_parse_iso_date(block.get("start_date"))
            block_end_date = _safe_parse_iso_date(block.get("end_date"))
            if block_start_date is not None and block_start_date > season_end:
                continue
            if block_end_date is not None and block_end_date < season_start:
                continue

            signature = _planning_simulation_signature(
                location_id=block_location_id,
                course_type_id=block_activity_id,
                weekday=block_weekday,
                start_time=block_start_time,
                end_time=block_end_time,
            )
            if quote_person_key and signature in live_signatures_by_person_key.get(quote_person_key, set()):
                continue
            block_series_key = str(block.get("series_key") or "").strip()
            resolved_slot_key = _planning_simulation_resolve_live_slot_for_quote(
                slot_entries=slot_entries,
                live_slot_keys_by_signature=live_slot_keys_by_signature,
                signature=signature,
                block_series_key=block_series_key,
            )
            slot_note: str | None = None
            if resolved_slot_key is None:
                resolved_slot_key = f"quote::{signature}"
                slot_note = "Aucun creneau live correspondant"

            entry = ensure_slot(
                slot_key=resolved_slot_key,
                slot_label_location_id=block_location_id,
                slot_label_location_name=block_location_name,
                slot_label_timezone=None,
                slot_label_activity_id=block_activity_id,
                slot_label_activity_name=str(
                    block.get("activity_label") or (block_course_type.name if block_course_type is not None else "") or "Activite"
                ),
                slot_label_activity_color=block_course_type.color_hex if block_course_type is not None else None,
                slot_label_activity_mode=block_course_type.mode if block_course_type is not None else None,
                weekday=block_weekday,
                start_time=block_start_time,
                end_time=block_end_time,
                quote_only=resolved_slot_key.startswith("quote::"),
                note=slot_note,
            )
            if entry["first_date"] is None and block_start_date is not None:
                entry["first_date"] = block_start_date
            if entry["last_date"] is None and block_end_date is not None:
                entry["last_date"] = block_end_date
            entry[bucket_name].add(str(quote.id))
            entry[bucket_people_name][str(quote.id)] = _planning_simulation_quote_student_name(
                quote=quote,
                prospect=prospect,
                client=quote_client,
            )

    slot_payloads: list[AdminPlanningSimulationSlotOut] = []
    location_ids_seen: set[UUID] = set()
    course_type_ids_seen: set[UUID] = set()
    total_booked = 0
    total_approved = 0
    total_pending = 0
    total_draft = 0
    quote_only_slot_count = 0

    sorted_entries = sorted(
        slot_entries.values(),
        key=lambda item: (
            str(item["location_name"]).casefold(),
            int(item["weekday"]),
            str(item["start_time"]),
            str(item["course_type_name"]).casefold(),
            str(item["end_time"]),
        ),
    )

    for entry in sorted_entries:
        booked_count = len(entry["_booked_user_ids"])
        approved_quotes_count = len(entry["_approved_quote_ids"])
        pending_quotes_count = len(entry["_pending_quote_ids"])
        draft_quotes_count = len(entry["_draft_quote_ids"])
        projected_count = booked_count + approved_quotes_count + pending_quotes_count + draft_quotes_count
        capacity_min = entry["capacity_min"]
        capacity_max = entry["capacity_max"]
        capacity_value = int(capacity_max) if capacity_max is not None else None
        remaining_capacity = (capacity_value - projected_count) if capacity_value is not None else None
        fill_rate = None if capacity_value in {None, 0} else round(booked_count / capacity_value, 4)
        projected_fill_rate = None if capacity_value in {None, 0} else round(projected_count / capacity_value, 4)

        location_uuid = entry["location_id"]
        activity_uuid = entry["course_type_id"]
        if isinstance(location_uuid, UUID):
            location_ids_seen.add(location_uuid)
        if isinstance(activity_uuid, UUID):
            course_type_ids_seen.add(activity_uuid)
        total_booked += booked_count
        total_approved += approved_quotes_count
        total_pending += pending_quotes_count
        total_draft += draft_quotes_count
        if bool(entry["quote_only"]):
            quote_only_slot_count += 1

        slot_payloads.append(
            AdminPlanningSimulationSlotOut(
                slot_key=str(entry["slot_key"]),
                location_id=location_uuid if isinstance(location_uuid, UUID) else None,
                location_name=str(entry["location_name"]),
                location_timezone=str(entry["location_timezone"]) if entry["location_timezone"] else None,
                course_type_id=activity_uuid if isinstance(activity_uuid, UUID) else None,
                course_type_name=str(entry["course_type_name"]),
                course_type_color_hex=str(entry["course_type_color_hex"]) if entry["course_type_color_hex"] else None,
                course_type_mode=entry["course_type_mode"] if isinstance(entry["course_type_mode"], DeliveryMode) else None,
                weekday=int(entry["weekday"]),
                weekday_label=str(entry["weekday_label"]),
                start_time=str(entry["start_time"]),
                end_time=str(entry["end_time"]),
                first_date=entry["first_date"] if isinstance(entry["first_date"], date) else None,
                last_date=entry["last_date"] if isinstance(entry["last_date"], date) else None,
                occurrence_count=int(entry["occurrence_count"]),
                live_session_count=int(entry["live_session_count"]),
                capacity=capacity_value,
                capacity_min=int(capacity_min) if capacity_min is not None else None,
                capacity_max=int(capacity_max) if capacity_max is not None else None,
                booked_count=booked_count,
                approved_quotes_count=approved_quotes_count,
                pending_quotes_count=pending_quotes_count,
                draft_quotes_count=draft_quotes_count,
                projected_count=projected_count,
                remaining_capacity=remaining_capacity,
                fill_rate=fill_rate,
                projected_fill_rate=projected_fill_rate,
                quote_only=bool(entry["quote_only"]),
                booked_students=sorted(str(item) for item in entry["_booked_students"].values()),
                approved_quote_students=sorted(str(item) for item in entry["_approved_quote_students"].values()),
                pending_quote_students=sorted(str(item) for item in entry["_pending_quote_students"].values()),
                draft_quote_students=sorted(str(item) for item in entry["_draft_quote_students"].values()),
                notes=[str(item) for item in entry["notes"]],
            )
        )

    return AdminPlanningSimulationOut(
        school_year_label=requested_school_year,
        available_school_years=available_school_years,
        location_filter_id=location_id,
        activity_filter_id=activity_id,
        activity_group_filter=normalized_activity_group,
        generated_at=_utcnow(),
        summary=AdminPlanningSimulationSummaryOut(
            location_count=len(location_ids_seen),
            slot_count=len(slot_payloads),
            course_type_count=len(course_type_ids_seen),
            booked_count=total_booked,
            approved_quotes_count=total_approved,
            pending_quotes_count=total_pending,
            draft_quotes_count=total_draft,
            quote_only_slot_count=quote_only_slot_count,
        ),
        slots=slot_payloads,
    )


@router.get("/planning-reorganization", response_model=AdminPlanningReorganizationOut)
def get_planning_reorganization_day(
    school_year: str | None = None,
    location_id: UUID | None = None,
    day: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminPlanningReorganizationOut:
    school_years = _available_school_years(db)
    selected_school_year = (school_year or "").strip() or (
        "2026-2027" if "2026-2027" in school_years else school_years[0]
    )
    season_start_utc, season_end_utc = _school_year_bounds_utc(selected_school_year)

    location_rows = _planning_reorganization_locations(
        db,
        season_start_utc=season_start_utc,
        season_end_utc=season_end_utc,
    )
    selected_location: Location | None = None
    if location_id is not None:
        selected_location = next((location for location in location_rows if location.id == location_id), None)
        if selected_location is None:
            selected_location = db.scalar(select(Location).where(Location.id == location_id).limit(1))
    if selected_location is None and location_rows:
        selected_location = location_rows[0]

    available_days: list[date] = []
    selected_day = day
    sessions_out: list[AdminPlanningReorganizationSessionOut] = []
    if selected_location is not None:
        available_days = _planning_reorganization_available_days(
            db,
            location_id=selected_location.id,
            season_start_utc=season_start_utc,
            season_end_utc=season_end_utc,
        )
        if selected_day is None and available_days:
            selected_day = available_days[0]

    if selected_location is not None and selected_day is not None:
        zone = _safe_zoneinfo(_normalize_session_timezone(selected_location.timezone))
        local_start = datetime.combine(selected_day, time.min).replace(tzinfo=zone)
        local_end = local_start + timedelta(days=1)
        day_start_utc = local_start.astimezone(timezone.utc)
        day_end_utc = local_end.astimezone(timezone.utc)

        substitute_professor = aliased(Professor, name="planning_reorg_substitute_professor")
        session_rows = db.execute(
            select(CourseSession, CourseType, Location, Professor, substitute_professor)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .outerjoin(Professor, Professor.id == CourseSession.professor_id)
            .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
            .where(
                CourseSession.location_id == selected_location.id,
                CourseSession.start_at_utc >= day_start_utc,
                CourseSession.start_at_utc < day_end_utc,
            )
            .order_by(CourseSession.start_at_utc.asc(), CourseSession.title.asc())
        ).all()
        session_ids = [session_obj.id for session_obj, *_ in session_rows]
        booked_counts = _booked_counts_map(db, session_ids)
        bookings_by_session: dict[UUID, list[AdminPlanningReorganizationBookingOut]] = {
            session_id: [] for session_id in session_ids
        }
        if session_ids:
            booking_rows = db.execute(
                select(Booking, User)
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.session_id.in_(session_ids),
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                )
                .order_by(
                    func.lower(func.coalesce(User.last_name, "")),
                    func.lower(func.coalesce(User.first_name, "")),
                    User.email.asc(),
                )
            ).all()
            for booking, client in booking_rows:
                bookings_by_session.setdefault(booking.session_id, []).append(
                    AdminPlanningReorganizationBookingOut(
                        id=booking.id,
                        client_id=client.id,
                        client_display_name=_client_display_name(client),
                        status=booking.status.value,
                        student_note=booking.student_note,
                    )
                )

        sessions_out = [
            _planning_reorganization_session_out(
                session_obj,
                course_type=course_type,
                location=location,
                professor=professor,
                substitute_professor=substitute,
                booked_count=booked_counts.get(session_obj.id, 0),
                bookings=bookings_by_session.get(session_obj.id, []),
            )
            for session_obj, course_type, location, professor, substitute in session_rows
        ]

    return AdminPlanningReorganizationOut(
        school_years=school_years,
        locations=[
            AdminPlanningReorganizationLocationOut(
                id=location.id,
                name=_session_location_label(location),
                timezone=_normalize_session_timezone(location.timezone),
            )
            for location in location_rows
        ],
        available_days=available_days,
        selected_school_year=selected_school_year,
        selected_location_id=selected_location.id if selected_location is not None else None,
        selected_day=selected_day,
        sessions=sessions_out,
    )


@router.post("/planning-reorganization/move-booking", response_model=AdminPlanningReorganizationMoveOut)
def move_planning_reorganization_booking(
    payload: AdminPlanningReorganizationMoveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminPlanningReorganizationMoveOut:
    now = _utcnow()
    source_booking = db.scalar(select(Booking).where(Booking.id == payload.booking_id).with_for_update())
    if source_booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    source_session = db.scalar(
        select(CourseSession).where(CourseSession.id == source_booking.session_id).with_for_update()
    )
    target_session = db.scalar(
        select(CourseSession).where(CourseSession.id == payload.target_session_id).with_for_update()
    )
    if source_session is None or target_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    moved_count = 0
    skipped_count = 0
    details: list[str] = []

    if (
        payload.scope == "single"
        or source_session.recurrence_group_id is None
        or target_session.recurrence_group_id is None
    ):
        moved, detail = _move_planning_reorganization_booking_occurrence(
            db,
            booking=source_booking,
            source_session=source_session,
            target_session=target_session,
            now=now,
        )
        moved_count += 1 if moved else 0
        skipped_count += 0 if moved else 1
        if detail:
            details.append(detail)
        db.commit()
        return AdminPlanningReorganizationMoveOut(
            moved_count=moved_count,
            skipped_count=skipped_count,
            details=details[:8],
        )

    source_sessions = _target_sessions_for_scope(db, source_session, ApplyScope.SERIES_FUTURE)
    target_sessions = _target_sessions_for_scope(db, target_session, ApplyScope.SERIES_FUTURE)
    source_session_by_id = {session_obj.id: session_obj for session_obj in source_sessions}
    target_by_day = {
        _local_date_in_timezone(
            session_obj.start_at_utc,
            _normalize_session_timezone(session_obj.timezone),
        ): session_obj
        for session_obj in target_sessions
    }

    recurring_bookings = db.scalars(
        select(Booking)
        .where(
            Booking.session_id.in_(list(source_session_by_id.keys())),
            Booking.user_id == source_booking.user_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
        .order_by(Booking.booked_at.asc())
        .with_for_update()
    ).all()
    for booking in recurring_bookings:
        current_source_session = source_session_by_id.get(booking.session_id)
        if current_source_session is None:
            skipped_count += 1
            continue
        source_day = _local_date_in_timezone(
            current_source_session.start_at_utc,
            _normalize_session_timezone(current_source_session.timezone),
        )
        current_target_session = target_by_day.get(source_day)
        if current_target_session is None:
            skipped_count += 1
            if len(details) < 8:
                details.append(f"Aucun creneau cible le {source_day.isoformat()}")
            continue
        moved, detail = _move_planning_reorganization_booking_occurrence(
            db,
            booking=booking,
            source_session=current_source_session,
            target_session=current_target_session,
            now=now,
        )
        moved_count += 1 if moved else 0
        skipped_count += 0 if moved else 1
        if detail and len(details) < 8:
            details.append(detail)

    db.commit()
    return AdminPlanningReorganizationMoveOut(
        moved_count=moved_count,
        skipped_count=skipped_count,
        details=details[:8],
    )


@router.post("/sessions", response_model=AdminSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: AdminSessionCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionOut:
    if payload.auto_cancel_rule_enabled_override is True and (
        payload.auto_cancel_if_booked_less_than_override is None
        or payload.auto_cancel_hours_before_start_override is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A custom auto-cancellation rule requires a minimum attendee count and a check delay",
        )
    course_type, location, professor = _validate_and_load_refs(
        db,
        course_type_id=payload.course_type_id,
        location_id=payload.location_id,
        professor_id=payload.professor_id,
    )
    session_timezone = _normalize_session_timezone(payload.timezone or location.timezone)

    is_vacation = _is_vacation_course_type(course_type)
    allows_student_bookings = bool(course_type.allows_student_bookings)
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
        location_id=payload.location_id,
        course_type_id=payload.course_type_id,
        auto_cancel_rule_enabled_override=payload.auto_cancel_rule_enabled_override,
        auto_cancel_hours_before_start_override=payload.auto_cancel_hours_before_start_override,
    )
    if is_vacation or not allows_student_bookings:
        capacity_max = 0
    else:
        capacity_max = int(payload.capacity_max)
        if capacity_max <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Capacite max obligatoire (>= 1, sauf creneau sans eleve)",
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
    recurrence_frequency = "WEEKLY"
    recurrence_interval = 1
    recurrence_time_basis = "LOCAL"
    recurrence_until_date: date | None = None
    if payload.recurrence is not None:
        recurrence_frequency = _normalize_recurrence_frequency(payload.recurrence.frequency)
        recurrence_interval = _normalize_recurrence_interval(payload.recurrence.interval)
        recurrence_time_basis = _normalize_recurrence_time_basis(payload.recurrence.time_basis)
        recurrence_until_date = payload.recurrence.until_date
        recurrence_rule = _serialize_recurrence_rule(
            frequency=recurrence_frequency,
            interval=recurrence_interval,
            time_basis=recurrence_time_basis,
        )
        recurrence_occurrences = _resolve_recurrence_occurrences(
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_until_date=payload.recurrence.until_date,
            anchor_start_at_utc=start_at_utc,
            session_timezone=session_timezone,
            recurrence_time_basis=recurrence_time_basis,
        )

    recurrence_group_id = uuid4() if recurrence_occurrences > 1 else None

    duration = end_at_utc - start_at_utc
    deadline_delta = start_at_utc - auto_cancel_deadline_utc
    now = _utcnow()
    calendar_skip_cache: dict[str, object] = {}
    visibility_scopes, booking_scopes = _resolve_payload_session_scopes(
        visibility_scopes=payload.visibility_scopes,
        booking_scopes=payload.booking_scopes,
        visibility_scope=payload.visibility_scope,
        booking_scope=payload.booking_scope,
        is_private=payload.is_private,
        allow_online_booking=payload.allow_online_booking,
        allows_student_bookings=allows_student_bookings,
    )
    is_private, allow_online_booking = legacy_flags_from_scopes(
        visibility_scopes=visibility_scopes,
        booking_scopes=booking_scopes,
        allows_student_bookings=allows_student_bookings,
    )

    sessions_to_create: list[CourseSession] = []
    for index in range(recurrence_occurrences):
        if recurrence_rule is None:
            starts_at = start_at_utc
        else:
            starts_at = _advance_recurrence_datetime(
                start_at_utc,
                frequency=recurrence_frequency,
                interval=recurrence_interval,
                offset=index,
                timezone_name=session_timezone,
                time_basis=recurrence_time_basis,
            )

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
            if _is_blocked_by_school_calendar(
                db,
                location_id=payload.location_id,
                location_timezone=location.timezone,
                starts_at_utc=starts_at,
                include_holidays=bool(course_type.exclude_holidays_in_recurrence),
                include_school_vacations=bool(course_type.exclude_school_vacations_in_recurrence),
                cache=calendar_skip_cache,
            ):
                continue

        sessions_to_create.append(
            CourseSession(
                course_type_id=payload.course_type_id,
                billing_entity_snapshot=normalize_billing_entity(course_type.billing_entity_code),
                snapshot_seller_legal_entity_id=course_type.seller_legal_entity_id,
                snapshot_payor_legal_entity_id=course_type.payor_legal_entity_id,
                location_id=payload.location_id,
                professor_id=payload.professor_id,
                title=payload.title,
                description=payload.public_description or payload.description,
                private_description=payload.private_description,
                professor_reminder_note=_normalize_message_field(payload.professor_reminder_note),
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                is_all_day=is_all_day,
                capacity_max=capacity_max,
                status=SessionStatus.SCHEDULED,
                auto_cancel_deadline_utc=deadline_at,
                auto_cancel_rule_enabled_override=payload.auto_cancel_rule_enabled_override,
                auto_cancel_if_booked_less_than_override=payload.auto_cancel_if_booked_less_than_override,
                auto_cancel_hours_before_start_override=payload.auto_cancel_hours_before_start_override,
                cancel_reason=None,
                zoom_link=_resolve_session_zoom_link(
                    requested_zoom_link=payload.zoom_link,
                    course_type=course_type,
                    location=location,
                    professor=professor,
                ),
                visibility_scope=serialize_session_audience_scopes(visibility_scopes),
                booking_scope=serialize_session_audience_scopes(booking_scopes),
                is_private=is_private,
                allow_online_booking=allow_online_booking,
                external_booking_price_ttc=payload.external_booking_price_ttc,
                show_external_remaining_seats=payload.show_external_remaining_seats,
                timezone=session_timezone,
                recurrence_group_id=recurrence_group_id,
                recurrence_rule=recurrence_rule,
                recurrence_until_date=recurrence_until_date if recurrence_group_id is not None else None,
                updated_at=now,
            )
        )

    if not sessions_to_create:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All recurring occurrences were blocked by configured holidays, vacations or closure slots",
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
    created_with_refs = _load_admin_session_with_refs(db, session_id=sessions_to_create[0].id)
    if created_with_refs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    created_session, created_course_type, created_location, created_professor, created_substitute_professor = created_with_refs

    return _to_admin_session_out(
        created_session,
        booked_count=0,
        course_type=created_course_type,
        location=created_location,
        professor=created_professor,
        substitute_professor=created_substitute_professor,
    )


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
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_planning")),
) -> list[AdminSessionOut]:
    substitute_professor = aliased(Professor, name="substitute_professor")
    stmt = (
        select(CourseSession, CourseType, Location, Professor, substitute_professor)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
    )

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
        stmt = stmt.where(
            or_(
                CourseSession.substitute_teacher_id.in_(professor_filter_ids),
                and_(
                    CourseSession.substitute_teacher_id.is_(None),
                    CourseSession.professor_id.in_(professor_filter_ids),
                ),
            )
        )

    if status is not None:
        stmt = stmt.where(CourseSession.status == status)
    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)

    client_filter_ids = list(dict.fromkeys(client_ids or []))
    if client_status is not None or client_filter_ids:
        stmt = (
            stmt.join(Booking, Booking.session_id == CourseSession.id)
            .join(User, User.id == Booking.user_id)
            .where(Booking.status.in_(BOOKING_STATUSES_ACTIVE))
        )
        if client_status is not None:
            stmt = stmt.where(User.client_status == client_status)
        if client_filter_ids:
            stmt = stmt.where(User.id.in_(client_filter_ids))
        stmt = stmt.distinct()

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc())).all()
    session_ids = [session_obj.id for session_obj, _, _, _, _ in rows]
    counts = _booked_counts_map(db, session_ids)
    recurrence_end_map = _recurrence_end_date_map(
        db,
        recurrence_group_ids=[session_obj.recurrence_group_id for session_obj, _, _, _, _ in rows],
    )

    return [
        _to_admin_session_out(
            session_obj,
            booked_count=counts.get(session_obj.id, 0),
            course_type=course_type,
            location=location,
            professor=professor,
            substitute_professor=substitute_professor_row,
            recurrence_end_date=recurrence_end_map.get(session_obj.recurrence_group_id) if session_obj.recurrence_group_id else None,
        )
        for session_obj, course_type, location, professor, substitute_professor_row in rows
    ]


@router.get("/sessions/{session_id}", response_model=AdminSessionOut)
def get_admin_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_planning")),
) -> AdminSessionOut:
    session_with_refs = _load_admin_session_with_refs(db, session_id=session_id)
    if session_with_refs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_obj, course_type, location, professor, substitute_professor = session_with_refs

    booked_count = _booked_count_by_session(db, session_id)
    return _to_admin_session_out(
        session_obj,
        booked_count=booked_count,
        course_type=course_type,
        location=location,
        professor=professor,
        substitute_professor=substitute_professor,
        recurrence_end_date=(
            _recurrence_end_date_map(db, recurrence_group_ids=[session_obj.recurrence_group_id]).get(session_obj.recurrence_group_id)
            if session_obj.recurrence_group_id is not None
            else None
        ),
    )


@router.get("/sessions/{session_id}/bookings", response_model=list[AdminSessionBookingOut])
def list_admin_session_bookings(
    session_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_view_planning")),
) -> list[AdminSessionBookingOut]:
    session_exists = db.scalar(select(CourseSession.id).where(CourseSession.id == session_id))
    if session_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    rows = db.execute(
        select(Booking, User)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
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


@router.post("/sessions/{session_id}/bookings/{booking_id}/attendance", response_model=AdminSessionBookingOut)
def update_admin_session_booking_attendance(
    session_id: UUID,
    booking_id: UUID,
    payload: AdminSessionBookingAttendanceUpdateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionBookingOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_obj.id,
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.status in (BookingStatus.CANCELLED, BookingStatus.WAITLISTED):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking attendance cannot be updated")

    if booking.status not in (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking attendance cannot be updated")

    previous_status = booking.status
    next_status = BookingStatus(payload.attendance_status)
    if previous_status != next_status and booking.client_plan_subscription_id is not None:
        sub_and_plan = _load_subscription_with_plan_for_update(db, subscription_id=booking.client_plan_subscription_id)
        if sub_and_plan is not None:
            subscription, plan = sub_and_plan
            if (
                next_status == BookingStatus.EXCUSED_ABSENCE
                and previous_status in (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW)
                and subscription.user_id == booking.user_id
            ):
                _restore_pack_credit(subscription, plan)
            elif (
                previous_status == BookingStatus.EXCUSED_ABSENCE
                and next_status in (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW)
                and subscription.user_id == booking.user_id
            ):
                if not _consume_pack_credit(subscription, plan):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Credits insuffisants pour remettre le statut present/absent",
                    )

    attendance_updated_at = _utcnow()
    if previous_status != next_status and next_status == BookingStatus.EXCUSED_ABSENCE:
        grant_makeup_for_excused_absence(
            db,
            booking=booking,
            actor_user_id=actor.id,
            now=attendance_updated_at,
        )
    elif previous_status == BookingStatus.EXCUSED_ABSENCE and next_status != BookingStatus.EXCUSED_ABSENCE:
        revoke_pending_makeup_for_corrected_absence(db, booking=booking, now=attendance_updated_at)

    booking.status = next_status
    booking.cancelled_at = None
    booking.cancellation_reason = None
    if "internal_note" in payload.model_fields_set:
        booking.internal_note = _normalize_message_field(payload.internal_note)

    automation_notifications = []
    if previous_status != next_status and next_status == BookingStatus.ATTENDED:
        automation_notifications = schedule_trial_attended_triggers(
            db,
            booking=booking,
            session_obj=session_obj,
            occurred_at=attendance_updated_at,
        )

    db.commit()
    enqueue_notifications(automation_notifications)
    db.refresh(booking)

    client = db.scalar(select(User).where(User.id == booking.user_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    return _to_admin_session_booking_out(db, booking, client)


@router.patch("/sessions/{session_id}/group-note", response_model=AdminSessionOut)
def update_admin_session_group_note(
    session_id: UUID,
    payload: AdminSessionGroupNoteUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session_obj.group_note = _normalize_message_field(payload.group_note)
    session_obj.updated_at = _utcnow()

    db.commit()
    db.refresh(session_obj)

    booked_count = _booked_count_by_session(db, session_obj.id)
    session_with_refs = _load_admin_session_with_refs(db, session_id=session_obj.id)
    if session_with_refs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_ref, course_type, location, professor, substitute_professor = session_with_refs
    return _to_admin_session_out(
        session_ref,
        booked_count=booked_count,
        course_type=course_type,
        location=location,
        professor=professor,
        substitute_professor=substitute_professor,
    )


@router.patch("/sessions/{session_id}/internal-note", response_model=AdminSessionOut)
def update_admin_session_internal_note(
    session_id: UUID,
    payload: AdminInternalNoteUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_obj.internal_note = _normalize_message_field(payload.internal_note)
    session_obj.updated_at = _utcnow()
    db.commit()
    db.refresh(session_obj)

    session_with_refs = _load_admin_session_with_refs(db, session_id=session_obj.id)
    if session_with_refs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_ref, course_type, location, professor, substitute_professor = session_with_refs
    return _to_admin_session_out(
        session_ref,
        booked_count=_booked_count_by_session(db, session_ref.id),
        course_type=course_type,
        location=location,
        professor=professor,
        substitute_professor=substitute_professor,
    )


@router.post("/sessions/{session_id}/broadcast", response_model=AdminSessionBroadcastOut)
def broadcast_admin_session_message(
    session_id: UUID,
    payload: AdminSessionBroadcastRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminSessionBroadcastOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id))
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    subject = _normalize_message_field(payload.subject)
    body = _normalize_message_field(payload.body)
    if body is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message obligatoire")

    channel = CommunicationChannel(payload.channel.value)
    if channel == CommunicationChannel.EMAIL and subject is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Sujet obligatoire pour un email")

    recipients: dict[str, UUID] = {}
    include_students = payload.audience.value in {"STUDENTS", "STUDENTS_AND_PARENTS"}
    include_parents = payload.audience.value in {"PARENTS", "STUDENTS_AND_PARENTS"}
    include_professor = payload.audience == AdminSessionBroadcastAudience.PROFESSOR
    include_admins = payload.audience == AdminSessionBroadcastAudience.ADMINS
    include_self = payload.audience == AdminSessionBroadcastAudience.SELF

    student_ids: set[UUID] = set()
    if include_students or include_parents:
        available_student_ids = _session_active_student_ids(db, session_id=session_obj.id)
        selected_student_ids = set(payload.included_student_ids) if payload.included_student_ids else available_student_ids
        student_ids = available_student_ids.intersection(selected_student_ids)
        if not student_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun eleve selectionne")
    if include_students:
        recipients.update(_session_student_recipient_map(db, student_ids=student_ids, channel=channel))
    if include_parents:
        parent_recipients = _session_parent_recipient_map(db, student_ids=student_ids, channel=channel)
        for destination, user_id in parent_recipients.items():
            recipients.setdefault(destination, user_id)
    if include_professor:
        recipients.update(_session_professor_recipient_map(db, session_obj=session_obj, channel=channel))
    if include_admins:
        admin_recipients = _admin_recipient_map(
            db,
            channel=channel,
            exclude_user_id=current_user.id if not payload.send_to_self else None,
        )
        for destination, user_id in admin_recipients.items():
            recipients.setdefault(destination, user_id)
    if include_self or payload.send_to_self:
        for destination, user_id in _single_user_recipient_map(
            user=current_user,
            channel=channel,
            enforce_opt_in=True,
        ).items():
            recipients.setdefault(destination, user_id)

    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Aucun destinataire valide (opt-in/email/telephone)",
        )

    sender_label = _display_name(current_user)
    skipped_count = 0
    details: list[str] = []
    cc_count = 0

    if channel == CommunicationChannel.EMAIL:
        for to_email, recipient_user_id in sorted(recipients.items()):
            send_session_operation_email(
                to_email=to_email,
                subject=subject or f"Message creneau: {session_obj.title}",
                body=body,
                body_format=payload.body_format.value,
                operation="ADMIN_SESSION_BROADCAST_EMAIL",
                session_title=session_obj.title,
                sender_user_id=current_user.id,
                sender_label=sender_label,
                sender_category=CommunicationSenderCategory.OTHER_USER,
                professor_id=session_obj.professor_id,
                recipient_user_id=recipient_user_id,
            )

        cc_emails: set[str] = set()
        for raw in payload.cc_emails:
            normalized = _normalize_email_recipient(raw)
            if normalized is None:
                skipped_count += 1
                details.append(f"Copie email invalide ignoree: {raw.strip() or '-'}")
                continue
            if normalized in recipients or normalized in cc_emails:
                continue
            cc_emails.add(normalized)

        for cc_email in sorted(cc_emails):
            send_session_operation_email(
                to_email=cc_email,
                subject=subject or f"Message creneau: {session_obj.title}",
                body=body,
                body_format=payload.body_format.value,
                operation="ADMIN_SESSION_BROADCAST_EMAIL",
                session_title=session_obj.title,
                sender_user_id=current_user.id,
                sender_label=sender_label,
                sender_category=CommunicationSenderCategory.OTHER_USER,
                professor_id=session_obj.professor_id,
                recipient_user_id=None,
            )
        cc_count = len(cc_emails)
        return AdminSessionBroadcastOut(
            channel=payload.channel,
            recipient_count=len(recipients),
            cc_count=cc_count,
            skipped_count=skipped_count,
            details=details,
        )

    sms_subject = subject or f"SMS creneau: {session_obj.title}"
    sms_body = body
    if payload.body_format == AdminSessionMessageFormat.HTML:
        sms_body = re.sub(r"<[^>]+>", " ", sms_body)
    sms_body = re.sub(r"\s{2,}", " ", sms_body).strip()
    if not sms_body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SMS vide apres normalisation")

    for phone_number, recipient_user_id in sorted(recipients.items()):
        log_communication(
            db=db,
            channel=CommunicationChannel.SMS,
            source="ADMIN_SESSION_BROADCAST_SMS",
            communication_type=COMMUNICATION_TYPE_OPERATIONAL,
            sender_category=CommunicationSenderCategory.OTHER_USER,
            sender_user_id=current_user.id,
            sender_label=sender_label,
            recipient_user_id=recipient_user_id,
            recipient=phone_number,
            subject=sms_subject,
            content=sms_body,
            content_format=MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.UNKNOWN,
            professor_id=session_obj.professor_id,
        )

    cc_phones: set[str] = set()
    for raw in payload.cc_phone_numbers:
        normalized = _normalize_phone_recipient(raw)
        if normalized is None:
            skipped_count += 1
            details.append(f"Copie SMS invalide ignoree: {raw.strip() or '-'}")
            continue
        if normalized in recipients or normalized in cc_phones:
            continue
        cc_phones.add(normalized)

    for cc_phone in sorted(cc_phones):
        log_communication(
            db=db,
            channel=CommunicationChannel.SMS,
            source="ADMIN_SESSION_BROADCAST_SMS",
            communication_type=COMMUNICATION_TYPE_OPERATIONAL,
            sender_category=CommunicationSenderCategory.OTHER_USER,
            sender_user_id=current_user.id,
            sender_label=sender_label,
            recipient_user_id=None,
            recipient=cc_phone,
            subject=sms_subject,
            content=sms_body,
            content_format=MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.UNKNOWN,
            professor_id=session_obj.professor_id,
        )
    db.commit()
    cc_count = len(cc_phones)

    return AdminSessionBroadcastOut(
        channel=payload.channel,
        recipient_count=len(recipients),
        cc_count=cc_count,
        skipped_count=skipped_count,
        details=details,
    )


@router.patch("/sessions/{session_id}/bookings/{booking_id}/note", response_model=AdminSessionBookingOut)
def update_admin_session_booking_note(
    session_id: UUID,
    booking_id: UUID,
    payload: AdminSessionBookingNoteUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionBookingOut:
    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    booking.student_note = _normalize_message_field(payload.student_note)

    db.commit()
    db.refresh(booking)

    client = db.scalar(select(User).where(User.id == booking.user_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    return _to_admin_session_booking_out(db, booking, client)


@router.patch("/sessions/{session_id}/bookings/{booking_id}/internal-note", response_model=AdminSessionBookingOut)
def update_admin_session_booking_internal_note(
    session_id: UUID,
    booking_id: UUID,
    payload: AdminInternalNoteUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionBookingOut:
    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    booking.internal_note = _normalize_message_field(payload.internal_note)
    db.commit()
    db.refresh(booking)
    client = db.scalar(select(User).where(User.id == booking.user_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return _to_admin_session_booking_out(db, booking, client)


@router.patch("/sessions/{session_id}/bookings/{booking_id}/student-time", response_model=AdminSessionBookingOut)
def update_admin_session_booking_student_time(
    session_id: UUID,
    booking_id: UUID,
    payload: AdminSessionBookingStudentTimeUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionBookingOut:
    row = db.execute(
        select(Booking, CourseSession, CourseType)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    booking, session_obj, course_type = row
    student_start_at_utc, student_end_at_utc = _student_time_override_for_session(
        session_obj=session_obj,
        course_type=course_type,
        start_time_local=payload.student_start_time_local,
        end_time_local=payload.student_end_time_local,
    )
    booking.student_start_at_utc = student_start_at_utc
    booking.student_end_at_utc = student_end_at_utc

    now = _utcnow()
    if booking.status == BookingStatus.BOOKED:
        skip_pending_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Student reminder time changed by admin",
            now=now,
        )
        _cancel_pending_notification_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Student reminder time changed by admin",
            now=now,
        )
        ensure_booking_reminder(db, booking=booking, session_obj=session_obj, now=now)

    db.commit()
    db.refresh(booking)

    client = db.scalar(select(User).where(User.id == booking.user_id))
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    return _to_admin_session_booking_out(db, booking, client)


@router.post("/sessions/{session_id}/bookings", response_model=AdminSessionBookingOperationOut)
def add_admin_session_booking(
    session_id: UUID,
    payload: AdminSessionBookingCreateRequest,
    scope: BookingScope | None = Query(default=None),
    apply_scope: ApplyScope | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionBookingOperationOut:
    try:
        resolved_scope = _resolve_booking_scope(scope=scope, apply_scope=apply_scope)
        anchor_session = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
        if anchor_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        client = _require_client(db, payload.client_id)
        targets = _target_sessions_for_admin_booking(db, session_obj=anchor_session, apply_scope=resolved_scope)
        if resolved_scope != "ONE" and payload.recurrence_end_date is not None:
            targets = [target for target in targets if target.start_at_utc.date() <= payload.recurrence_end_date]

        now = _utcnow()

        processed_count = 0
        booked_count = 0
        waitlisted_count = 0
        skipped_count = 0
        details: list[str] = []
        planning_force_cache: dict[UUID, bool] = {}
        course_type_cache: dict[UUID, CourseType | None] = {}

        def add_detail(message: str) -> None:
            if message not in details:
                details.append(message)

        blocked_statuses = {
            BookingStatus.BOOKED,
            BookingStatus.PENDING_PAYMENT,
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

            target_course_type = course_type_cache.get(target.course_type_id)
            if target_course_type is None:
                target_course_type = db.scalar(select(CourseType).where(CourseType.id == target.course_type_id))
                course_type_cache[target.course_type_id] = target_course_type
            if target_course_type is None:
                skipped_count += 1
                add_detail("Activite introuvable pour ce creneau")
                continue
            if not bool(target_course_type.allows_student_bookings):
                skipped_count += 1
                add_detail("Creneau sans eleve: inscription impossible")
                continue
            student_start_at_utc, student_end_at_utc = _student_time_override_for_session(
                session_obj=target,
                course_type=target_course_type,
                start_time_local=payload.student_start_time_local,
                end_time_local=payload.student_end_time_local,
            )

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
                coverage_at=target.start_at_utc,
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

            is_trial_booking = bool(plan is not None and plan.is_trial_offer)

            price, vat_rate, vat_amount, total, currency = _resolve_booking_snapshot(
                db,
                session_obj=target,
                user=client,
                now=now,
                subscription=subscription,
                plan=plan,
            )
            next_status = _next_booking_status(db, session_obj=target)
            if next_status is None:
                skipped_count += 1
                add_detail("Creneau complet et liste d attente pleine")
                continue

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
                    student_start_at_utc=student_start_at_utc,
                    student_end_at_utc=student_end_at_utc,
                    is_trial_course=is_trial_booking,
                    trial_course_type_id=target.course_type_id if is_trial_booking else None,
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
                existing.student_start_at_utc = student_start_at_utc
                existing.student_end_at_utc = student_end_at_utc
                existing.is_trial_course = is_trial_booking
                existing.trial_course_type_id = target.course_type_id if is_trial_booking else None
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
    scope: BookingScope | None = Query(default=None),
    apply_scope: ApplyScope | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
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

    resolved_scope = _resolve_booking_scope(scope=scope, apply_scope=apply_scope)
    now = _utcnow()
    locked_statuses = (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)
    refundable_statuses = (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)

    target_bookings: list[tuple[CourseSession, Booking]] = []
    if resolved_scope == "ONE" or session_obj.recurrence_group_id is None:
        target_bookings = [(session_obj, booking)]
    else:
        target_sessions = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope="SERIES_FUTURE")
        target_session_ids = [target.id for target in target_sessions]
        if target_session_ids:
            rows = db.execute(
                select(CourseSession, Booking)
                .join(Booking, Booking.session_id == CourseSession.id)
                .where(
                    CourseSession.id.in_(target_session_ids),
                    Booking.user_id == booking.user_id,
                )
                .with_for_update()
            ).all()
            target_bookings = [(row[0], row[1]) for row in rows]

    if not target_bookings:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    for target_session, target_booking in target_bookings:
        if target_booking.status == BookingStatus.CANCELLED:
            continue

        previous_status = target_booking.status
        is_future_scheduled_session = target_session.status == SessionStatus.SCHEDULED and target_session.start_at_utc > now
        if previous_status in locked_statuses and not is_future_scheduled_session:
            if resolved_scope == "ONE":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed booking cannot be removed")
            continue

        if previous_status in refundable_statuses and target_booking.client_plan_subscription_id is not None and target_session.start_at_utc > now:
            sub_and_plan = _load_subscription_with_plan_for_update(
                db,
                subscription_id=target_booking.client_plan_subscription_id,
            )
            if sub_and_plan is not None:
                subscription, plan = sub_and_plan
                if subscription.user_id == target_booking.user_id:
                    _restore_pack_credit(subscription, plan)

        target_booking.status = BookingStatus.CANCELLED
        target_booking.cancelled_at = now
        target_booking.cancellation_reason = "ADMIN_REMOVED"

        skip_pending_reminders_for_booking(
            db,
            booking_id=target_booking.id,
            reason="Booking cancelled by admin",
            now=now,
        )
        _promote_waitlist_if_possible(db, target_session, now)

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/sessions/{session_id}", response_model=AdminSessionOut)
def update_session(
    session_id: UUID,
    payload: AdminSessionUpdateRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    updates = payload.model_dump(exclude_unset=True)
    next_auto_cancel_enabled_override = updates.get(
        "auto_cancel_rule_enabled_override",
        session_obj.auto_cancel_rule_enabled_override,
    )
    next_auto_cancel_threshold_override = updates.get(
        "auto_cancel_if_booked_less_than_override",
        session_obj.auto_cancel_if_booked_less_than_override,
    )
    next_auto_cancel_hours_override = updates.get(
        "auto_cancel_hours_before_start_override",
        session_obj.auto_cancel_hours_before_start_override,
    )
    if next_auto_cancel_enabled_override is True and (
        next_auto_cancel_threshold_override is None or next_auto_cancel_hours_override is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A custom auto-cancellation rule requires a minimum attendee count and a check delay",
        )
    has_auto_cancel_rule_update = any(
        field in updates
        for field in (
            "auto_cancel_rule_enabled_override",
            "auto_cancel_if_booked_less_than_override",
            "auto_cancel_hours_before_start_override",
        )
    )
    recurrence_payload = updates.pop("recurrence", None)
    has_substitute_teacher_update = "substitute_teacher_id" in updates
    requested_substitute_teacher_id = updates.pop("substitute_teacher_id", None) if has_substitute_teacher_update else session_obj.substitute_teacher_id
    has_substitute_note_update = "substitute_note" in updates
    requested_substitute_note = updates.pop("substitute_note", None) if has_substitute_note_update else session_obj.substitute_note
    if (has_substitute_teacher_update or has_substitute_note_update) and apply_scope != "ONE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Substitute teacher can only be changed for this occurrence",
        )
    if recurrence_payload is not None:
        if session_obj.recurrence_group_id is None and apply_scope != "ONE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Recurrence conversion is only supported with apply_scope=ONE",
            )
        if session_obj.recurrence_group_id is not None and apply_scope == "ONE":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Recurrence update for recurring session requires apply_scope=SERIES_FUTURE or apply_scope=SERIES_ALL",
            )
    if "public_description" not in updates and "description" in updates:
        updates["public_description"] = updates["description"]

    course_type_id = updates.get("course_type_id", session_obj.course_type_id)
    location_id = updates.get("location_id", session_obj.location_id)
    professor_id = updates.get("professor_id", session_obj.professor_id)
    substitute_teacher_id = normalized_substitute_teacher_id(
        professor_id=professor_id,
        substitute_teacher_id=requested_substitute_teacher_id,
    )
    substitute_professor: Professor | None = None
    if substitute_teacher_id is not None:
        substitute_professor = db.scalar(
            select(Professor).where(
                Professor.id == substitute_teacher_id,
                Professor.active.is_(True),
            )
        )
        if substitute_professor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Substitute professor not found or inactive",
            )
    enforce_planning_allowed = "course_type_id" in updates or "location_id" in updates

    course_type, location, professor = _validate_and_load_refs(
        db,
        course_type_id=course_type_id,
        location_id=location_id,
        professor_id=professor_id,
        enforce_planning_allowed=enforce_planning_allowed,
    )
    session_zoom_professor = professor
    is_vacation = _is_vacation_course_type(course_type)
    allows_student_bookings = bool(course_type.allows_student_bookings)
    anchor_timezone = _normalize_session_timezone(updates.get("timezone", session_obj.timezone or location.timezone))
    current_visibility_scopes = resolve_session_visibility_scopes(session_obj)
    current_booking_scopes = resolve_session_booking_scopes(
        session_obj,
        allows_student_bookings=allows_student_bookings,
    )
    next_visibility_scopes, next_booking_scopes = _resolve_payload_session_scopes(
        visibility_scopes=updates.get("visibility_scopes"),
        booking_scopes=updates.get("booking_scopes"),
        visibility_scope=updates.get("visibility_scope"),
        booking_scope=updates.get("booking_scope"),
        is_private=updates.get("is_private"),
        allow_online_booking=updates.get("allow_online_booking"),
        allows_student_bookings=allows_student_bookings,
        current_visibility_scopes=current_visibility_scopes,
        current_booking_scopes=current_booking_scopes,
        current_is_private=bool(session_obj.is_private),
        current_allow_online_booking=bool(session_obj.allow_online_booking),
    )
    next_is_private, next_allow_online_booking = legacy_flags_from_scopes(
        visibility_scopes=next_visibility_scopes,
        booking_scopes=next_booking_scopes,
        allows_student_bookings=allows_student_bookings,
    )

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
                location_id=location_id,
                course_type_id=course_type_id,
                auto_cancel_rule_enabled_override=next_auto_cancel_enabled_override,
                auto_cancel_hours_before_start_override=next_auto_cancel_hours_override,
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
        elif "start_at_utc" in updates or has_auto_cancel_rule_update or "course_type_id" in updates:
            anchor_deadline = _resolve_auto_cancel_deadline(
                db,
                start_at_utc=anchor_start,
                auto_cancel_deadline_utc=None,
                location_id=location_id,
                course_type_id=course_type_id,
                auto_cancel_rule_enabled_override=next_auto_cancel_enabled_override,
                auto_cancel_hours_before_start_override=next_auto_cancel_hours_override,
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

    recurrence_rule: str | None = None
    recurrence_group_id: UUID | None = None
    recurrence_occurrences = 1
    recurrence_frequency = "WEEKLY"
    recurrence_interval = 1
    recurrence_time_basis = "LOCAL"
    recurrence_until_date: date | None = None
    create_future_recurrences = False
    realign_existing_recurrence = False
    existing_recurrence_frequency, existing_recurrence_interval, existing_recurrence_time_basis = _parse_recurrence_rule(
        session_obj.recurrence_rule
    )
    has_schedule_affecting_update = any(
        field in updates for field in ("start_at_utc", "end_at_utc", "timezone", "is_all_day")
    )
    if recurrence_payload is not None:
        recurrence_frequency = _normalize_recurrence_frequency(str(recurrence_payload.get("frequency") or ""))
        recurrence_interval = _normalize_recurrence_interval(recurrence_payload.get("interval"))
        recurrence_time_basis = _normalize_recurrence_time_basis(str(recurrence_payload.get("time_basis") or "LOCAL"))
        recurrence_until_date = recurrence_payload.get("until_date")
        recurrence_rule = _serialize_recurrence_rule(
            frequency=recurrence_frequency,
            interval=recurrence_interval,
            time_basis=recurrence_time_basis,
        )
        if session_obj.recurrence_group_id is not None:
            recurrence_occurrences = 1
            recurrence_group_id = session_obj.recurrence_group_id if apply_scope == "SERIES_ALL" else uuid4()
            realign_existing_recurrence = True
        else:
            recurrence_occurrences = _resolve_recurrence_occurrences(
                recurrence_frequency=recurrence_frequency,
                recurrence_interval=recurrence_interval,
                recurrence_until_date=recurrence_until_date,
                anchor_start_at_utc=anchor_start,
                session_timezone=anchor_timezone,
                recurrence_time_basis=recurrence_time_basis,
            )
            if recurrence_occurrences <= 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Recurrence end date must generate at least one future occurrence",
                )
            recurrence_group_id = uuid4()
            create_future_recurrences = True
    elif (
        session_obj.recurrence_group_id is not None
        and apply_scope != "ONE"
        and has_schedule_affecting_update
        and existing_recurrence_time_basis == "LOCAL"
    ):
        recurrence_frequency = existing_recurrence_frequency
        recurrence_interval = existing_recurrence_interval
        recurrence_time_basis = existing_recurrence_time_basis
        recurrence_rule = _serialize_recurrence_rule(
            frequency=recurrence_frequency,
            interval=recurrence_interval,
            time_basis=recurrence_time_basis,
        )
        recurrence_group_id = session_obj.recurrence_group_id if apply_scope == "SERIES_ALL" else uuid4()
        realign_existing_recurrence = True

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
    recurrence_base_start: datetime | None = None
    if realign_existing_recurrence and target_sessions:
        if apply_scope == "SERIES_ALL":
            recurrence_base_start = target_sessions[0].start_at_utc
            if has_start_update:
                recurrence_base_start = recurrence_base_start + anchor_start_shift
        else:
            recurrence_base_start = anchor_start

    desired_recurrence_starts: list[datetime] | None = None
    missing_recurrence_starts: list[datetime] = []
    calendar_skip_cache: dict[str, object] = {}
    if (
        realign_existing_recurrence
        and recurrence_rule is not None
        and recurrence_until_date is not None
        and recurrence_base_start is not None
    ):
        theoretical_recurrence_starts = _recurrence_datetimes_until(
            anchor_start_at_utc=recurrence_base_start,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
            recurrence_until_date=recurrence_until_date,
            session_timezone=anchor_timezone,
            recurrence_time_basis=recurrence_time_basis,
        )
        desired_recurrence_starts = []
        for starts_at in theoretical_recurrence_starts:
            if not is_vacation and _has_vacation_on_day(
                db,
                location_id=location_id,
                day_start_utc=_start_of_utc_day(starts_at),
            ):
                continue
            if not is_vacation and _is_blocked_by_school_calendar(
                db,
                location_id=location_id,
                location_timezone=location.timezone,
                starts_at_utc=starts_at,
                include_holidays=bool(course_type.exclude_holidays_in_recurrence),
                include_school_vacations=bool(course_type.exclude_school_vacations_in_recurrence),
                cache=calendar_skip_cache,
            ):
                continue
            desired_recurrence_starts.append(starts_at)

        if not desired_recurrence_starts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All recurring future occurrences were blocked by configured holidays, vacations or closure slots",
            )

        target_sessions = target_sessions[: len(desired_recurrence_starts)]
        missing_recurrence_starts = desired_recurrence_starts[len(target_sessions):]

    sessions_completed_for_invoicing: set[UUID] = set()
    for target_index, target in enumerate(target_sessions):
        previous_status = target.status
        target.course_type_id = course_type_id
        target.billing_entity_snapshot = normalize_billing_entity(course_type.billing_entity_code)
        target.snapshot_seller_legal_entity_id = course_type.seller_legal_entity_id
        target.snapshot_payor_legal_entity_id = course_type.payor_legal_entity_id
        target.location_id = location_id
        target.professor_id = professor_id
        target.auto_cancel_rule_enabled_override = next_auto_cancel_enabled_override
        target.auto_cancel_if_booked_less_than_override = next_auto_cancel_threshold_override
        target.auto_cancel_hours_before_start_override = next_auto_cancel_hours_override
        if has_auto_cancel_rule_update or "start_at_utc" in updates or "course_type_id" in updates:
            target.auto_cancel_checked_at = None

        if "title" in updates:
            target.title = updates["title"]
        if "public_description" in updates:
            target.description = updates["public_description"]
        if "private_description" in updates:
            target.private_description = updates["private_description"]
        if "professor_reminder_note" in updates:
            target.professor_reminder_note = _normalize_message_field(updates["professor_reminder_note"])
        if "zoom_link" in updates:
            target.zoom_link = _resolve_session_zoom_link(
                requested_zoom_link=updates["zoom_link"],
                course_type=course_type,
                location=location,
                professor=session_zoom_professor,
            )
        elif (
            ("course_type_id" in updates or "location_id" in updates or "professor_id" in updates)
            and not (target.zoom_link or "").strip()
        ):
            target.zoom_link = _resolve_session_zoom_link(
                requested_zoom_link=None,
                course_type=course_type,
                location=location,
                professor=session_zoom_professor,
            )
        if is_vacation or not allows_student_bookings:
            target.capacity_max = 0
        elif "capacity_max" in updates:
            next_capacity = int(updates["capacity_max"])
            if next_capacity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Capacite max obligatoire (>= 1, sauf creneau sans eleve)",
                )
            target.capacity_max = next_capacity
        elif target.capacity_max <= 0:
            target.capacity_max = 1
        if "status" in updates:
            target.status = updates["status"]
        if "cancel_reason" in updates:
            target.cancel_reason = updates["cancel_reason"]
        target.visibility_scope = serialize_session_audience_scopes(next_visibility_scopes)
        target.booking_scope = serialize_session_audience_scopes(next_booking_scopes)
        target.is_private = next_is_private
        target.allow_online_booking = next_allow_online_booking
        if "external_booking_price_ttc" in updates:
            target.external_booking_price_ttc = updates["external_booking_price_ttc"]
        if "show_external_remaining_seats" in updates:
            target.show_external_remaining_seats = bool(updates["show_external_remaining_seats"])

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
        elif recurrence_base_start is not None and recurrence_rule is not None:
            if desired_recurrence_starts is not None:
                resolved_start = desired_recurrence_starts[target_index]
            else:
                resolved_start = _advance_recurrence_datetime(
                    recurrence_base_start,
                    frequency=recurrence_frequency,
                    interval=recurrence_interval,
                    offset=target_index,
                    timezone_name=resolved_timezone,
                    time_basis=recurrence_time_basis,
                )
            if resolved_is_all_day:
                resolved_start = _start_of_utc_day(resolved_start)
                resolved_end = resolved_start + timedelta(days=1)
                if "auto_cancel_deadline_utc" in updates:
                    resolved_deadline = resolved_start - anchor_deadline_delta
                else:
                    resolved_deadline = _resolve_auto_cancel_deadline(
                        db,
                        start_at_utc=resolved_start,
                        auto_cancel_deadline_utc=None,
                        location_id=target.location_id,
                        course_type_id=target.course_type_id,
                        auto_cancel_rule_enabled_override=target.auto_cancel_rule_enabled_override,
                        auto_cancel_hours_before_start_override=target.auto_cancel_hours_before_start_override,
                    )
            else:
                resolved_end = resolved_start + anchor_new_duration
                resolved_deadline = resolved_start - anchor_deadline_delta
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
            elif has_auto_cancel_rule_update or "course_type_id" in updates:
                resolved_deadline = _resolve_auto_cancel_deadline(
                    db,
                    start_at_utc=resolved_start,
                    auto_cancel_deadline_utc=None,
                    location_id=target.location_id,
                    course_type_id=target.course_type_id,
                    auto_cancel_rule_enabled_override=target.auto_cancel_rule_enabled_override,
                    auto_cancel_hours_before_start_override=target.auto_cancel_hours_before_start_override,
                )
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
                    location_id=target.location_id,
                    course_type_id=target.course_type_id,
                    auto_cancel_rule_enabled_override=target.auto_cancel_rule_enabled_override,
                    auto_cancel_hours_before_start_override=target.auto_cancel_hours_before_start_override,
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
        if recurrence_group_id is not None and recurrence_rule is not None:
            target.recurrence_group_id = recurrence_group_id
            target.recurrence_rule = recurrence_rule
            if recurrence_until_date is not None:
                target.recurrence_until_date = recurrence_until_date
        target.updated_at = now
        if previous_status != SessionStatus.COMPLETED and target.status == SessionStatus.COMPLETED:
            sessions_completed_for_invoicing.add(target.id)
        if (
            "capacity_max" in updates
            and target.status == SessionStatus.SCHEDULED
            and target.capacity_max > 0
        ):
            _promote_waitlist_if_possible(db, target, now)

    if has_substitute_teacher_update:
        session_obj.substitute_teacher_id = substitute_teacher_id
        if substitute_teacher_id is None:
            session_obj.substitute_set_at = None
            session_obj.substitute_set_by = None
            if not has_substitute_note_update:
                session_obj.substitute_note = None
        else:
            session_obj.substitute_set_at = now
            session_obj.substitute_set_by = current_user.id
            if "zoom_link" not in updates and not (session_obj.zoom_link or "").strip():
                session_obj.zoom_link = _resolve_session_zoom_link(
                    requested_zoom_link=None,
                    course_type=course_type,
                    location=location,
                    professor=substitute_professor,
                )
    elif "professor_id" in updates and session_obj.substitute_teacher_id is not None:
        normalized_existing_substitute = normalized_substitute_teacher_id(
            professor_id=professor_id,
            substitute_teacher_id=session_obj.substitute_teacher_id,
        )
        if normalized_existing_substitute is None:
            session_obj.substitute_teacher_id = None
            session_obj.substitute_set_at = None
            session_obj.substitute_set_by = None
            session_obj.substitute_note = None
    if has_substitute_note_update:
        session_obj.substitute_note = _normalize_message_field(requested_substitute_note)

    if create_future_recurrences and recurrence_group_id is not None and recurrence_rule is not None:
        anchor_duration = session_obj.end_at_utc - session_obj.start_at_utc
        anchor_deadline_delta = session_obj.start_at_utc - session_obj.auto_cancel_deadline_utc
        created_future_count = 0

        for index in range(1, recurrence_occurrences):
            starts_at = _advance_recurrence_datetime(
                session_obj.start_at_utc,
                frequency=recurrence_frequency,
                interval=recurrence_interval,
                offset=index,
                timezone_name=session_obj.timezone,
                time_basis=recurrence_time_basis,
            )
            if session_obj.is_all_day:
                starts_at = _start_of_utc_day(starts_at)
                ends_at = starts_at + timedelta(days=1)
            else:
                ends_at = starts_at + anchor_duration
            deadline_at = starts_at - anchor_deadline_delta

            _validate_session_times(
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                auto_cancel_deadline_utc=deadline_at,
            )
            _validate_same_day_slot(
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                is_all_day=session_obj.is_all_day,
                session_timezone=session_obj.timezone,
            )

            if not is_vacation and _has_vacation_on_day(
                db,
                location_id=session_obj.location_id,
                day_start_utc=_start_of_utc_day(starts_at),
            ):
                continue
            if not is_vacation and _is_blocked_by_school_calendar(
                db,
                location_id=session_obj.location_id,
                location_timezone=location.timezone,
                starts_at_utc=starts_at,
                include_holidays=bool(course_type.exclude_holidays_in_recurrence),
                include_school_vacations=bool(course_type.exclude_school_vacations_in_recurrence),
                cache=calendar_skip_cache,
            ):
                continue

            db.add(
                CourseSession(
                    course_type_id=session_obj.course_type_id,
                    billing_entity_snapshot=session_obj.billing_entity_snapshot,
                    snapshot_seller_legal_entity_id=session_obj.snapshot_seller_legal_entity_id,
                    snapshot_payor_legal_entity_id=session_obj.snapshot_payor_legal_entity_id,
                    location_id=session_obj.location_id,
                    professor_id=session_obj.professor_id,
                    title=session_obj.title,
                    description=session_obj.description,
                    private_description=session_obj.private_description,
                    professor_reminder_note=session_obj.professor_reminder_note,
                    group_note=session_obj.group_note,
                    start_at_utc=starts_at,
                    end_at_utc=ends_at,
                    is_all_day=session_obj.is_all_day,
                    capacity_max=session_obj.capacity_max,
                    status=session_obj.status,
                    auto_cancel_deadline_utc=deadline_at,
                    auto_cancel_rule_enabled_override=session_obj.auto_cancel_rule_enabled_override,
                    auto_cancel_if_booked_less_than_override=session_obj.auto_cancel_if_booked_less_than_override,
                    auto_cancel_hours_before_start_override=session_obj.auto_cancel_hours_before_start_override,
                    cancel_reason=session_obj.cancel_reason,
                    zoom_link=session_obj.zoom_link,
                    visibility_scope=session_obj.visibility_scope,
                    booking_scope=session_obj.booking_scope,
                    is_private=session_obj.is_private,
                    allow_online_booking=session_obj.allow_online_booking,
                    external_booking_price_ttc=session_obj.external_booking_price_ttc,
                    show_external_remaining_seats=session_obj.show_external_remaining_seats,
                    timezone=session_obj.timezone,
                    recurrence_group_id=recurrence_group_id,
                    recurrence_rule=recurrence_rule,
                    recurrence_until_date=recurrence_until_date,
                    updated_at=now,
                )
            )
            created_future_count += 1

        if created_future_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="All recurring future occurrences were blocked by configured holidays, vacations or closure slots",
            )
    elif missing_recurrence_starts and recurrence_group_id is not None and recurrence_rule is not None:
        anchor_duration = session_obj.end_at_utc - session_obj.start_at_utc
        anchor_deadline_delta = session_obj.start_at_utc - session_obj.auto_cancel_deadline_utc

        for starts_at in missing_recurrence_starts:
            if session_obj.is_all_day:
                starts_at = _start_of_utc_day(starts_at)
                ends_at = starts_at + timedelta(days=1)
            else:
                ends_at = starts_at + anchor_duration
            deadline_at = starts_at - anchor_deadline_delta

            _validate_session_times(
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                auto_cancel_deadline_utc=deadline_at,
            )
            _validate_same_day_slot(
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                is_all_day=session_obj.is_all_day,
                session_timezone=session_obj.timezone,
            )

            db.add(
                CourseSession(
                    course_type_id=session_obj.course_type_id,
                    billing_entity_snapshot=session_obj.billing_entity_snapshot,
                    snapshot_seller_legal_entity_id=session_obj.snapshot_seller_legal_entity_id,
                    snapshot_payor_legal_entity_id=session_obj.snapshot_payor_legal_entity_id,
                    location_id=session_obj.location_id,
                    professor_id=session_obj.professor_id,
                    title=session_obj.title,
                    description=session_obj.description,
                    private_description=session_obj.private_description,
                    professor_reminder_note=session_obj.professor_reminder_note,
                    group_note=session_obj.group_note,
                    start_at_utc=starts_at,
                    end_at_utc=ends_at,
                    is_all_day=session_obj.is_all_day,
                    capacity_max=session_obj.capacity_max,
                    status=session_obj.status,
                    auto_cancel_deadline_utc=deadline_at,
                    auto_cancel_rule_enabled_override=session_obj.auto_cancel_rule_enabled_override,
                    auto_cancel_if_booked_less_than_override=session_obj.auto_cancel_if_booked_less_than_override,
                    auto_cancel_hours_before_start_override=session_obj.auto_cancel_hours_before_start_override,
                    cancel_reason=session_obj.cancel_reason,
                    zoom_link=session_obj.zoom_link,
                    visibility_scope=session_obj.visibility_scope,
                    booking_scope=session_obj.booking_scope,
                    is_private=session_obj.is_private,
                    allow_online_booking=session_obj.allow_online_booking,
                    external_booking_price_ttc=session_obj.external_booking_price_ttc,
                    show_external_remaining_seats=session_obj.show_external_remaining_seats,
                    timezone=session_obj.timezone,
                    recurrence_group_id=recurrence_group_id,
                    recurrence_rule=recurrence_rule,
                    recurrence_until_date=recurrence_until_date,
                    updated_at=now,
                )
            )

    if sessions_completed_for_invoicing:
        completed_booking_rows = db.execute(
            select(Booking, CourseSession, CourseType, Location, User)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(User, User.id == Booking.user_id)
            .where(
                Booking.session_id.in_(sessions_completed_for_invoicing),
                Booking.status.in_(FINAL_INVOICE_ELIGIBLE_BOOKING_STATUSES),
            )
        ).all()
        for booking, completed_session, completed_course_type, completed_location, booking_owner in completed_booking_rows:
            try:
                note, metadata, _ = generate_final_invoice_for_booking(
                    db,
                    booking=booking,
                    session_obj=completed_session,
                    course_type=completed_course_type,
                    location=completed_location,
                    owner=booking_owner,
                    author_user_id=current_user.id,
                )
            except ValueError:
                continue
            invoice_customer = db.scalar(select(User).where(User.id == note.user_id, User.role == UserRole.CLIENT))
            if invoice_customer is None:
                continue
            try:
                send_final_invoice_email(
                    db,
                    customer=invoice_customer,
                    note_id=note.id,
                    metadata=metadata,
                )
            except Exception:
                logger.exception(
                    "Unable to send final invoice email for session=%s booking=%s note=%s",
                    completed_session.id,
                    booking.id,
                    note.id,
                )

    db.commit()
    db.refresh(session_obj)

    booked_count = _booked_count_by_session(db, session_id)
    session_with_refs = _load_admin_session_with_refs(db, session_id=session_id)
    if session_with_refs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session_ref, course_type, location, professor, substitute_professor = session_with_refs
    return _to_admin_session_out(
        session_ref,
        booked_count=booked_count,
        course_type=course_type,
        location=location,
        professor=professor,
        substitute_professor=substitute_professor,
    )


@router.post("/sessions/{session_id}/duplicate", response_model=AdminSessionDuplicateOperationOut)
def duplicate_session_operation(
    session_id: UUID,
    payload: AdminSessionDuplicateRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionDuplicateOperationOut:
    if apply_scope == "SERIES_ALL":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplication supports ONE or SERIES_FUTURE scope only",
        )

    try:
        session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
        if session_obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        targets = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)
        targets.sort(key=lambda row: row.start_at_utc)
        if not targets:
            targets = [session_obj]

        now = _utcnow()
        target_anchor_start = payload.target_start_at_utc
        if target_anchor_start.tzinfo is None:
            target_anchor_start = target_anchor_start.replace(tzinfo=timezone.utc)
        else:
            target_anchor_start = target_anchor_start.astimezone(timezone.utc)
        anchor_shift = target_anchor_start - session_obj.start_at_utc
        duplicate_recurrence_group_id: UUID | None = None
        if apply_scope == "SERIES_FUTURE" and session_obj.recurrence_group_id is not None:
            duplicate_recurrence_group_id = uuid4()

        duplicated_bookings = 0

        for target in targets:
            target_timezone = _normalize_session_timezone(target.timezone or "UTC")
            target_duration = target.end_at_utc - target.start_at_utc

            duplicate_start = target.start_at_utc + anchor_shift
            if target.is_all_day:
                duplicate_start = _start_of_utc_day(duplicate_start)
                duplicate_end = duplicate_start + timedelta(days=1)
            else:
                duplicate_end = duplicate_start + target_duration
            duplicate_deadline = _duplicate_auto_cancel_deadline(
                source_start_at_utc=target.start_at_utc,
                source_deadline_utc=target.auto_cancel_deadline_utc,
                duplicate_start_at_utc=duplicate_start,
            )

            _validate_session_times(
                start_at_utc=duplicate_start,
                end_at_utc=duplicate_end,
                auto_cancel_deadline_utc=duplicate_deadline,
            )
            _validate_same_day_slot(
                start_at_utc=duplicate_start,
                end_at_utc=duplicate_end,
                is_all_day=target.is_all_day,
                session_timezone=target_timezone,
            )

            recurrence_group_id = (
                duplicate_recurrence_group_id
                if duplicate_recurrence_group_id is not None and target.recurrence_group_id is not None
                else None
            )
            recurrence_rule = target.recurrence_rule if recurrence_group_id is not None else None
            recurrence_until_date = target.recurrence_until_date if recurrence_group_id is not None else None

            duplicate_session = CourseSession(
                course_type_id=target.course_type_id,
                billing_entity_snapshot=target.billing_entity_snapshot,
                snapshot_seller_legal_entity_id=target.snapshot_seller_legal_entity_id,
                snapshot_payor_legal_entity_id=target.snapshot_payor_legal_entity_id,
                location_id=target.location_id,
                professor_id=target.professor_id,
                title=target.title,
                description=target.description,
                private_description=target.private_description,
                professor_reminder_note=target.professor_reminder_note,
                group_note=target.group_note,
                start_at_utc=duplicate_start,
                end_at_utc=duplicate_end,
                is_all_day=target.is_all_day,
                capacity_max=target.capacity_max,
                status=SessionStatus.SCHEDULED,
                auto_cancel_deadline_utc=duplicate_deadline,
                auto_cancel_rule_enabled_override=target.auto_cancel_rule_enabled_override,
                auto_cancel_if_booked_less_than_override=target.auto_cancel_if_booked_less_than_override,
                auto_cancel_hours_before_start_override=target.auto_cancel_hours_before_start_override,
                cancel_reason=None,
                zoom_link=target.zoom_link,
                visibility_scope=target.visibility_scope,
                booking_scope=target.booking_scope,
                is_private=target.is_private,
                allow_online_booking=target.allow_online_booking,
                external_booking_price_ttc=target.external_booking_price_ttc,
                show_external_remaining_seats=target.show_external_remaining_seats,
                timezone=target_timezone,
                recurrence_group_id=recurrence_group_id,
                recurrence_rule=recurrence_rule,
                recurrence_until_date=recurrence_until_date,
                updated_at=now,
            )
            db.add(duplicate_session)
            db.flush()

            source_bookings = db.scalars(
                select(Booking)
                .where(
                    Booking.session_id == target.id,
                    Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                )
                .with_for_update()
            ).all()

            for source_booking in source_bookings:
                # A trial is a one-off booking and must never be propagated to a
                # duplicated/recurring session.
                if source_booking.is_trial_course:
                    continue
                duplicate_status = source_booking.status
                if duplicate_status in (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE):
                    duplicate_status = BookingStatus.BOOKED
                duplicate_student_start_at_utc = None
                duplicate_student_end_at_utc = None
                if source_booking.student_start_at_utc is not None and source_booking.student_end_at_utc is not None:
                    duplicate_student_start_at_utc = duplicate_session.start_at_utc + (
                        source_booking.student_start_at_utc - target.start_at_utc
                    )
                    duplicate_student_end_at_utc = duplicate_session.start_at_utc + (
                        source_booking.student_end_at_utc - target.start_at_utc
                    )

                duplicate_booking = Booking(
                    session_id=duplicate_session.id,
                    user_id=source_booking.user_id,
                    client_plan_subscription_id=source_booking.client_plan_subscription_id,
                    status=duplicate_status,
                    booked_at=now,
                    cancelled_at=None,
                    cancellation_reason=None,
                    price_excl_vat_snapshot=source_booking.price_excl_vat_snapshot,
                    vat_rate_snapshot=source_booking.vat_rate_snapshot,
                    vat_amount_snapshot=source_booking.vat_amount_snapshot,
                    total_incl_vat_snapshot=source_booking.total_incl_vat_snapshot,
                    currency_snapshot=source_booking.currency_snapshot,
                    student_note=source_booking.student_note,
                    student_start_at_utc=duplicate_student_start_at_utc,
                    student_end_at_utc=duplicate_student_end_at_utc,
                    is_trial_course=False,
                    trial_course_type_id=None,
                )
                db.add(duplicate_booking)
                db.flush()

                if duplicate_status == BookingStatus.BOOKED:
                    ensure_booking_reminder(
                        db,
                        booking=duplicate_booking,
                        session_obj=duplicate_session,
                        now=now,
                    )
                else:
                    skip_pending_reminders_for_booking(
                        db,
                        booking_id=duplicate_booking.id,
                        reason="Booking duplicated as waitlist",
                        now=now,
                    )
                duplicated_bookings += 1

        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_lock_error(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Planning en cours de modification. Reessayez dans quelques secondes.",
            ) from exc
        raise

    return AdminSessionDuplicateOperationOut(
        processed_sessions=len(targets),
        duplicated_bookings=duplicated_bookings,
    )


@router.post("/sessions/{session_id}/cancel", response_model=AdminSessionOperationOut)
def cancel_session_operation(
    session_id: UUID,
    payload: AdminSessionCancelOperationRequest,
    apply_scope: ApplyScope = Query(default="ONE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_permissions("can_edit_planning")),
) -> AdminSessionOperationOut:
    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _validate_operation_notifications(payload.notifications)

    targets = _target_sessions_for_scope(db, session_obj=session_obj, apply_scope=apply_scope)
    now = _utcnow()
    cancel_reason = _normalize_message_field(payload.cancel_reason) or "ADMIN_CANCELLED"
    target_ids = [target.id for target in targets]
    orchestrated_notifications = []

    for target in targets:
        target.status = SessionStatus.CANCELLED
        target.cancel_reason = cancel_reason
        target.updated_at = now
        orchestrated_notifications.extend(
            schedule_slot_cancelled_notifications(
                db,
                slot=target,
                actor_user_id=current_user.id,
                occurred_at=now,
                source="admin_bo",
            )
        )

    db.commit()
    if orchestrated_notifications:
        enqueue_notifications(orchestrated_notifications)

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
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
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
    _: User = Depends(require_admin_or_permissions("can_edit_planning")),
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
