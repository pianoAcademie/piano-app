from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db
from app.models.catalog import (
    BOOKING_STATUSES_CONSUMING_CAPACITY,
    Booking,
    CourseSession,
    CourseType,
    CreditType,
    Location,
    PlanningCourseType,
    Professor,
    SessionAudienceScope,
    SessionStatus,
)
from app.models.ops import AppSetting
from app.models.user import ClientKind, User
from app.schemas.catalog import (
    CourseTypeOut,
    LocationOut,
    SessionCourseTypeOut,
    SessionLocationOut,
    SessionOut,
    SessionProfessorOut,
)
from app.services.session_audience import (
    primary_session_audience_scope,
    resolve_session_booking_scopes,
    resolve_session_visibility_scopes,
    scopes_allow_external_visibility,
)
from app.services.client_pricing import PriceUnit, amount_for_unit

router = APIRouter()
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"


def _account_default_currency(db: Session) -> str:
    raw = db.scalar(select(AppSetting.value).where(AppSetting.key == ACCOUNT_DEFAULT_CURRENCY_KEY))
    candidate = str(raw or "").strip().upper()
    return candidate if len(candidate) == 3 else "EUR"


def _session_accepts_participant_kind(session: CourseSession, participant_kind: ClientKind | None) -> bool:
    if participant_kind == ClientKind.ADULT:
        return bool(getattr(session, "adult_bookings_enabled", False))
    if participant_kind == ClientKind.CHILD:
        return bool(getattr(session, "child_bookings_enabled", True))
    return True


def _participant_seats_remaining(
    session: CourseSession,
    *,
    booked_count: int,
    adult_booked_count: int,
    participant_kind: ClientKind | None,
) -> int:
    total_remaining = max(int(session.capacity_max) - int(booked_count or 0), 0)
    if participant_kind != ClientKind.ADULT:
        return total_remaining

    adult_capacity_max = getattr(session, "adult_capacity_max", None)
    if adult_capacity_max is None:
        return total_remaining
    adult_remaining = max(int(adult_capacity_max) - int(adult_booked_count or 0), 0)
    return min(total_remaining, adult_remaining)


def _serialize_public_session(
    *,
    session: CourseSession,
    course_type: CourseType,
    location: Location,
    professor: Professor | None,
    substitute: Professor | None,
    booked_count: int,
    adult_booked_count: int,
    timezone: str,
    external_booking_currency: str,
    participant_kind: ClientKind | None = None,
) -> SessionOut | None:
    if not _session_accepts_participant_kind(session, participant_kind):
        return None
    visibility_scopes = resolve_session_visibility_scopes(session)
    if not scopes_allow_external_visibility(visibility_scopes):
        return None
    booking_scopes = resolve_session_booking_scopes(
        session,
        allows_student_bookings=bool(course_type.allows_student_bookings),
    )
    visibility_scope = primary_session_audience_scope(visibility_scopes)
    booking_scope = primary_session_audience_scope(booking_scopes, fallback=SessionAudienceScope.PRIVATE)
    effective_professor = substitute or professor
    substitute_display_name = (
        f"{(substitute.first_name or '').strip()} {(substitute.last_name or '').strip()}".strip()
        if substitute is not None
        else None
    )
    effective_display_name = (
        f"{(effective_professor.first_name or '').strip()} {(effective_professor.last_name or '').strip()}".strip()
        if effective_professor is not None
        else None
    )
    booked = int(booked_count or 0)
    seats_remaining = _participant_seats_remaining(
        session,
        booked_count=booked,
        adult_booked_count=adult_booked_count,
        participant_kind=participant_kind,
    )
    external_booking_price_ttc = None
    external_booking_price_unit = str(
        getattr(session, "external_booking_price_unit", None) or PriceUnit.PER_HOUR.value
    )
    if session.external_booking_price_ttc is not None:
        duration_seconds = int(max((session.end_at_utc - session.start_at_utc).total_seconds(), 0))
        if duration_seconds <= 0:
            duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
        duration_hours = Decimal(duration_seconds) / Decimal("3600")
        external_booking_price_ttc = amount_for_unit(
            Decimal(session.external_booking_price_ttc),
            unit=(
                PriceUnit.PER_SESSION
                if external_booking_price_unit == PriceUnit.PER_SESSION.value
                else PriceUnit.PER_HOUR
            ),
            duration_hours=duration_hours,
        )

    return SessionOut(
        id=session.id,
        title=session.title,
        description=session.description,
        start_at_utc=session.start_at_utc,
        end_at_utc=session.end_at_utc,
        start_at_local=session.start_at_utc.astimezone(ZoneInfo(timezone)),
        end_at_local=session.end_at_utc.astimezone(ZoneInfo(timezone)),
        timezone=timezone,
        session_timezone=session.timezone,
        status=session.status,
        capacity_max=session.capacity_max,
        booked_count=booked,
        seats_remaining=seats_remaining,
        child_bookings_enabled=bool(getattr(session, "child_bookings_enabled", True)),
        adult_bookings_enabled=bool(getattr(session, "adult_bookings_enabled", False)),
        adult_capacity_max=getattr(session, "adult_capacity_max", None),
        adult_booked_count=int(adult_booked_count or 0),
        child_trial_bookings_enabled=bool(getattr(session, "child_trial_bookings_enabled", True)),
        adult_trial_bookings_enabled=bool(getattr(session, "adult_trial_bookings_enabled", False)),
        visibility_scopes=visibility_scopes,
        booking_scopes=booking_scopes,
        visibility_scope=visibility_scope,
        booking_scope=booking_scope,
        online_booking_enabled=SessionAudienceScope.EXTERNAL in booking_scopes,
        external_booking_price_ttc=external_booking_price_ttc,
        external_booking_price_unit=external_booking_price_unit,
        external_booking_currency=external_booking_currency if session.external_booking_price_ttc is not None else None,
        show_external_remaining_seats=bool(session.show_external_remaining_seats),
        zoom_link=session.zoom_link,
        substitute_teacher_id=session.substitute_teacher_id,
        substitute_teacher_display_name=substitute_display_name,
        effective_teacher_id=effective_professor.id if effective_professor is not None else None,
        effective_teacher_display_name=effective_display_name,
        course_type=SessionCourseTypeOut(
            id=course_type.id,
            code=course_type.code,
            name=course_type.name,
            supports_student_time_overrides=bool(course_type.supports_student_time_overrides),
        ),
        location=SessionLocationOut(
            id=location.id,
            code=location.code,
            name=location.name,
            is_online=location.is_online,
        ),
        professor=(
            SessionProfessorOut(
                id=effective_professor.id,
                first_name=effective_professor.first_name,
                last_name=effective_professor.last_name,
            )
            if effective_professor is not None
            else None
        ),
    )


@router.get("/course-types", response_model=list[CourseTypeOut])
def list_course_types(
    active: bool = True,
    location_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[CourseTypeOut]:
    stmt = select(CourseType)
    if active:
        stmt = stmt.where(CourseType.active.is_(True))

    selected_ids: list[UUID] = []
    order_index: dict[UUID, int] = {}
    if location_id is not None:
        selected_rows = db.execute(
            select(PlanningCourseType.course_type_id, PlanningCourseType.display_order)
            .where(PlanningCourseType.location_id == location_id)
            .order_by(PlanningCourseType.display_order.asc(), PlanningCourseType.created_at.asc())
        ).all()
        selected_ids = [course_type_id for course_type_id, _ in selected_rows]
        order_index = {course_type_id: int(display_order or 0) for course_type_id, display_order in selected_rows}
        if selected_ids:
            stmt = stmt.where(CourseType.id.in_(selected_ids))

    stmt = stmt.order_by(CourseType.name.asc())

    rows = db.scalars(stmt).all()
    credit_type_rows = db.execute(select(CreditType.id, CreditType.code, CreditType.name)).all()
    credit_type_by_id = {
        credit_type_id: {"code": credit_type_code, "name": credit_type_name}
        for credit_type_id, credit_type_code, credit_type_name in credit_type_rows
    }
    if selected_ids:
        rows.sort(key=lambda row: (order_index.get(row.id, 9999), row.name.casefold()))

    return [
        CourseTypeOut(
            id=row.id,
            code=row.code,
            name=row.name,
            description=row.description,
            service_code=row.service_code,
            credit_type_id=row.credit_type_id,
            credit_type_code=credit_type_by_id.get(row.credit_type_id, {}).get("code") if row.credit_type_id else None,
            credit_type_name=credit_type_by_id.get(row.credit_type_id, {}).get("name") if row.credit_type_id else None,
            duration_minutes=row.duration_minutes,
            color_hex=row.color_hex,
            mode=row.mode,
            lesson_format=row.lesson_format,
            requires_professor=bool(row.requires_professor),
            allows_student_bookings=bool(row.allows_student_bookings),
            supports_student_time_overrides=bool(row.supports_student_time_overrides),
            default_capacity=row.default_capacity,
            default_hourly_rate=row.default_hourly_rate,
            default_course_rate_ttc=row.default_course_rate_ttc,
            auto_cancel_if_booked_less_than_override=row.auto_cancel_if_booked_less_than_override,
            auto_cancel_hours_before_start_override=row.auto_cancel_hours_before_start_override,
            auto_cancel_rule_enabled=bool(row.auto_cancel_rule_enabled),
            active=row.active,
        )
        for row in rows
    ]


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    active: bool = True,
    course_type_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[LocationOut]:
    stmt = select(Location)
    if course_type_id is not None:
        stmt = stmt.join(PlanningCourseType, PlanningCourseType.location_id == Location.id).where(
            PlanningCourseType.course_type_id == course_type_id
        )
    if active:
        stmt = stmt.where(Location.active.is_(True))
    stmt = stmt.order_by(Location.name.asc())

    rows = db.scalars(stmt).all()
    return [
        LocationOut(
            id=row.id,
            code=row.code,
            name=row.name,
            address_line=row.address_line,
            city=row.city,
            country_code=row.country_code,
            is_online=row.is_online,
            timezone=row.timezone,
            active=row.active,
        )
        for row in rows
    ]


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    participant_kind: ClientKind | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    timezone: str = "UTC",
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )

    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc

    booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("booked_count"),
        )
        .where(Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY))
        .group_by(Booking.session_id)
        .subquery()
    )
    adult_booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("adult_booked_count"),
        )
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY),
            User.client_kind == ClientKind.ADULT,
        )
        .group_by(Booking.session_id)
        .subquery()
    )
    substitute_professor = aliased(Professor, name="substitute_professor")

    stmt = (
        select(
            CourseSession,
            CourseType,
            Location,
            Professor,
            substitute_professor,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
            func.coalesce(adult_booked_counts.c.adult_booked_count, 0).label("adult_booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .outerjoin(adult_booked_counts, adult_booked_counts.c.session_id == CourseSession.id)
        .where(CourseSession.status == SessionStatus.SCHEDULED, CourseSession.is_private.is_(False))
    )

    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if participant_kind == ClientKind.ADULT:
        stmt = stmt.where(CourseSession.adult_bookings_enabled.is_(True))
    elif participant_kind == ClientKind.CHILD:
        stmt = stmt.where(CourseSession.child_bookings_enabled.is_(True))
    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)

    stmt = stmt.order_by(CourseSession.start_at_utc.asc())

    rows = db.execute(stmt).all()
    external_booking_currency = _account_default_currency(db)

    result: list[SessionOut] = []
    for session, course_type, location, professor, substitute, booked_count, adult_booked_count in rows:
        serialized = _serialize_public_session(
            session=session,
            course_type=course_type,
            location=location,
            professor=professor,
            substitute=substitute,
            booked_count=int(booked_count or 0),
            adult_booked_count=int(adult_booked_count or 0),
            timezone=timezone,
            external_booking_currency=external_booking_currency,
            participant_kind=participant_kind,
        )
        if serialized is None:
            continue
        result.append(serialized)

    return result


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: UUID,
    timezone: str = "UTC",
    participant_kind: ClientKind | None = None,
    db: Session = Depends(get_db),
) -> SessionOut:
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc

    booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("booked_count"),
        )
        .where(Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY))
        .group_by(Booking.session_id)
        .subquery()
    )
    adult_booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("adult_booked_count"),
        )
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY),
            User.client_kind == ClientKind.ADULT,
        )
        .group_by(Booking.session_id)
        .subquery()
    )
    substitute_professor = aliased(Professor, name="substitute_professor_detail")
    row = db.execute(
        select(
            CourseSession,
            CourseType,
            Location,
            Professor,
            substitute_professor,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
            func.coalesce(adult_booked_counts.c.adult_booked_count, 0).label("adult_booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(substitute_professor, substitute_professor.id == CourseSession.substitute_teacher_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .outerjoin(adult_booked_counts, adult_booked_counts.c.session_id == CourseSession.id)
        .where(
            CourseSession.id == session_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.is_private.is_(False),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session, course_type, location, professor, substitute, booked_count, adult_booked_count = row
    serialized = _serialize_public_session(
        session=session,
        course_type=course_type,
        location=location,
        professor=professor,
        substitute=substitute,
        booked_count=int(booked_count or 0),
        adult_booked_count=int(adult_booked_count or 0),
        timezone=tz.key,
        external_booking_currency=_account_default_currency(db),
        participant_kind=participant_kind,
    )
    if serialized is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return serialized
