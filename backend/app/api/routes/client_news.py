from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.client_news import ClientNewsArticle
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, DeliveryMode, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, SubscriptionStatus
from app.models.user import ClientKind, User, UserRole
from app.schemas.client_news import (
    AdminClientNewsCreate,
    AdminClientNewsOut,
    AdminClientNewsUpdate,
    ClientNewsOut,
)


router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _admin_out(row: ClientNewsArticle) -> AdminClientNewsOut:
    return AdminClientNewsOut.model_validate(row, from_attributes=True)


def _client_out(row: ClientNewsArticle, language: str) -> ClientNewsOut:
    english = language.strip().lower().startswith("en")
    return ClientNewsOut(
        id=row.id,
        title=(row.title_en if english and row.title_en else row.title_fr),
        summary=(row.summary_en if english and row.summary_en else row.summary_fr),
        body=(row.body_en if english and row.body_en else row.body_fr),
        link_url=row.link_url,
        link_label=(row.link_label_en if english and row.link_label_en else row.link_label_fr),
        is_pinned=row.is_pinned,
        published_at=row.published_at or row.created_at,
    )


def _normalized_values(payload: AdminClientNewsCreate | AdminClientNewsUpdate) -> dict[str, object]:
    values = payload.model_dump()
    if values["status"] == "PUBLISHED" and values["published_at"] is None:
        values["published_at"] = _utcnow()
    published_at = values.get("published_at")
    expires_at = values.get("expires_at")
    if isinstance(published_at, datetime) and isinstance(expires_at, datetime) and expires_at <= published_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La date d'expiration doit être postérieure à la publication",
        )
    return values


_ACTIVE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)
_CURRENT_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAYMENT_ALERT,
    SubscriptionStatus.PRE_TERMINATION,
)


def _age_on_today(user: User, now: datetime) -> int | None:
    if user.birth_date is None:
        return None
    today = now.date()
    return today.year - user.birth_date.year - ((today.month, today.day) < (user.birth_date.month, user.birth_date.day))


def _course_family(course_type: CourseType) -> str:
    value = " ".join((course_type.code, course_type.service_code, course_type.name)).lower()
    normalized = value.replace("é", "e").replace("è", "e").replace("ê", "e")
    if "eveil" in normalized:
        return "EARLY_MUSIC"
    if "initiation" in normalized:
        return "INITIATION"
    return "OTHER"


def _client_audience_codes(db: Session, current_user: User, now: datetime) -> set[str]:
    """Return cumulative audiences for this account and all linked children.

    Membership is derived from non-cancelled enrolments in the current/future
    programme.  The set naturally de-duplicates an article matching several
    members of the same family.
    """
    child_ids = list(
        db.scalars(
            select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == current_user.id)
        ).all()
    )
    subject_ids = list(dict.fromkeys([current_user.id, *child_ids]))
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(subject_ids))).all()
    }
    rows = db.execute(
        select(Booking.user_id, CourseType, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .outerjoin(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id)
        .where(
            Booking.user_id.in_(subject_ids),
            Booking.status.in_(_ACTIVE_BOOKING_STATUSES),
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc >= now,
            or_(
                Booking.client_plan_subscription_id.is_(None),
                (
                    ClientPlanSubscription.status.in_(_CURRENT_SUBSCRIPTION_STATUSES)
                    & (ClientPlanSubscription.started_at <= now)
                    & or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at >= now)
                ),
            ),
        )
    ).all()
    by_user: dict[UUID, list[tuple[CourseType, CourseSession]]] = {}
    for user_id, course_type, session in rows:
        by_user.setdefault(user_id, []).append((course_type, session))

    audiences: set[str] = set()
    own_courses = by_user.get(current_user.id, [])
    if current_user.client_kind == ClientKind.ADULT and own_courses:
        audiences.add("ADULT_STUDENTS")
        if all(course_type.mode == DeliveryMode.ONLINE for course_type, _ in own_courses):
            audiences.add("ADULT_ONLINE_ONLY")

    for child_id in child_ids:
        child = users.get(child_id)
        child_courses = by_user.get(child_id, [])
        if child is None or not child_courses:
            continue
        age = _age_on_today(child, now)
        if age is not None and 5 <= age <= 12:
            audiences.add("PARENTS_CHILD_5_12")
        if age is not None and 13 <= age <= 17:
            audiences.add("PARENTS_TEEN")
        families = {_course_family(course_type) for course_type, _ in child_courses}
        if "EARLY_MUSIC" in families:
            audiences.add("PARENTS_EARLY_MUSIC")
        if "INITIATION" in families:
            audiences.add("PARENTS_INITIATION")
        if all(course_type.mode == DeliveryMode.ONLINE for course_type, _ in child_courses):
            audiences.add("CHILD_ONLINE_ONLY")
    return audiences


def _article_matches_client(row: ClientNewsArticle, audiences: set[str]) -> bool:
    codes = set(row.audience_codes or ["ALL_CLIENTS"])
    return "ALL_CLIENTS" in codes or bool(codes & audiences)


def _published_news_query(now: datetime):
    return (
        select(ClientNewsArticle)
        .where(
            ClientNewsArticle.status == "PUBLISHED",
            ClientNewsArticle.published_at.is_not(None),
            ClientNewsArticle.published_at <= now,
            or_(ClientNewsArticle.expires_at.is_(None), ClientNewsArticle.expires_at > now),
        )
        .order_by(ClientNewsArticle.is_pinned.desc(), ClientNewsArticle.published_at.desc())
        .limit(100)
    )


@router.get("/admin/client-news", response_model=list[AdminClientNewsOut])
def list_admin_client_news(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> list[AdminClientNewsOut]:
    rows = db.scalars(
        select(ClientNewsArticle).order_by(
            ClientNewsArticle.is_pinned.desc(),
            ClientNewsArticle.published_at.desc().nulls_last(),
            ClientNewsArticle.created_at.desc(),
        )
    ).all()
    return [_admin_out(row) for row in rows]


@router.post("/admin/client-news", response_model=AdminClientNewsOut, status_code=status.HTTP_201_CREATED)
def create_admin_client_news(
    payload: AdminClientNewsCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> AdminClientNewsOut:
    values = _normalized_values(payload)
    row = ClientNewsArticle(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _admin_out(row)


@router.put("/admin/client-news/{article_id}", response_model=AdminClientNewsOut)
def update_admin_client_news(
    article_id: UUID,
    payload: AdminClientNewsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> AdminClientNewsOut:
    row = db.get(ClientNewsArticle, article_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable")
    values = _normalized_values(payload)
    if values["status"] == "DRAFT":
        values["published_at"] = None
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _admin_out(row)


@router.delete("/admin/client-news/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_client_news(
    article_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_mobile_news", "can_manage_website_and_news")),
) -> Response:
    row = db.get(ClientNewsArticle, article_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/clients/me/news", response_model=list[ClientNewsOut])
def list_client_news(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientNewsOut]:
    now = _utcnow()
    audiences = _client_audience_codes(db, current_user, now)
    rows = db.scalars(_published_news_query(now)).all()
    return [
        _client_out(row, current_user.preferred_language or "fr")
        for row in rows
        if _article_matches_client(row, audiences)
    ][:50]


@router.get("/professors/me/news", response_model=list[ClientNewsOut])
def list_professor_news(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ClientNewsOut]:
    rows = db.scalars(_published_news_query(_utcnow())).all()
    return [
        _client_out(row, current_user.preferred_language or "fr")
        for row in rows
        if "PROFESSORS" in set(row.audience_codes or [])
    ][:50]
