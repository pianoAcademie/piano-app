from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.catalog import (
    Booking,
    BookingStatus,
    CourseSession,
    CourseType,
    CreditType,
    Location,
    PlanningCourseType,
    Professor,
    SessionStatus,
)
from app.schemas.catalog import (
    CourseTypeOut,
    LocationOut,
    SessionCourseTypeOut,
    SessionLocationOut,
    SessionOut,
    SessionProfessorOut,
)

router = APIRouter()


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
            default_capacity=row.default_capacity,
            default_hourly_rate=row.default_hourly_rate,
            active=row.active,
        )
        for row in rows
    ]


@router.get("/locations", response_model=list[LocationOut])
def list_locations(active: bool = True, db: Session = Depends(get_db)) -> list[LocationOut]:
    stmt = select(Location)
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
        .where(Booking.status == BookingStatus.BOOKED)
        .group_by(Booking.session_id)
        .subquery()
    )

    stmt = (
        select(
            CourseSession,
            CourseType,
            Location,
            Professor,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .where(CourseSession.status == SessionStatus.SCHEDULED, CourseSession.is_private.is_(False))
    )

    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)

    stmt = stmt.order_by(CourseSession.start_at_utc.asc())

    rows = db.execute(stmt).all()

    result: list[SessionOut] = []
    for session, course_type, location, professor, booked_count in rows:
        booked = int(booked_count or 0)
        seats_remaining = max(session.capacity_max - booked, 0)

        result.append(
            SessionOut(
                id=session.id,
                title=session.title,
                description=session.description,
                start_at_utc=session.start_at_utc,
                end_at_utc=session.end_at_utc,
                start_at_local=session.start_at_utc.astimezone(tz),
                end_at_local=session.end_at_utc.astimezone(tz),
                timezone=timezone,
                status=session.status,
                capacity_max=session.capacity_max,
                booked_count=booked,
                seats_remaining=seats_remaining,
                zoom_link=session.zoom_link,
                course_type=SessionCourseTypeOut(
                    id=course_type.id,
                    code=course_type.code,
                    name=course_type.name,
                ),
                location=SessionLocationOut(
                    id=location.id,
                    code=location.code,
                    name=location.name,
                    is_online=location.is_online,
                ),
                professor=SessionProfessorOut(
                    id=professor.id,
                    first_name=professor.first_name,
                    last_name=professor.last_name,
                ),
            )
        )

    return result
