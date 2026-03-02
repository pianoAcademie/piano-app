from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.plan import (
    ClientForfaitActivityPricing,
    ClientPlanSubscription,
    Plan,
    PlanEntitlement,
    PlanKind,
    PlanRestrictionPeriod,
    SubscriptionStatus,
)
from app.models.user import ClientKind, User, UserRole
from app.schemas.booking import BookingCreateRequest, BookingOut, ClientBookingOut, SessionMiniOut
from app.services.family_billing import resolve_billing_profile
from app.services.pricing import resolve_vat_rate
from app.services.reminders import ensure_booking_reminder, skip_pending_reminders_for_booking
from app.services.subscriptions import reconcile_subscription_status

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _count_booked(db: Session, session_id: UUID) -> int:
    value = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.session_id == session_id,
            Booking.status == BookingStatus.BOOKED,
        )
    )
    return int(value or 0)


def _mark_first_course_if_needed(user: User, session_obj: CourseSession) -> None:
    if user.first_course_at is None or session_obj.start_at_utc < user.first_course_at:
        user.first_course_at = session_obj.start_at_utc


def _resolve_family_booking_owner(
    db: Session,
    *,
    current_user: User,
    requested_user_id: UUID | None,
) -> User:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user

    if current_user.client_kind != ClientKind.ADULT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only adult accounts can book for attached family members",
        )

    link_exists = db.scalar(
        select(ClientFamilyLink.id).where(
            ClientFamilyLink.adult_user_id == current_user.id,
            ClientFamilyLink.child_user_id == requested_user_id,
        )
    )
    if link_exists is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Target member is not attached to this adult account",
        )

    member = db.scalar(
        select(User).where(
            User.id == requested_user_id,
            User.role == UserRole.CLIENT,
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target client not found")
    if not member.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Target client is inactive")
    return member


def _can_manage_booking_owner(db: Session, *, current_user: User, owner_user_id: UUID) -> bool:
    if owner_user_id == current_user.id:
        return True
    if current_user.client_kind != ClientKind.ADULT:
        return False
    return db.scalar(
        select(ClientFamilyLink.id).where(
            ClientFamilyLink.adult_user_id == current_user.id,
            ClientFamilyLink.child_user_id == owner_user_id,
        )
    ) is not None


def _waitlist_position(db: Session, booking: Booking) -> int | None:
    if booking.status != BookingStatus.WAITLISTED:
        return None

    queue_ids = db.scalars(
        select(Booking.id)
        .where(
            Booking.session_id == booking.session_id,
            Booking.status == BookingStatus.WAITLISTED,
        )
        .order_by(Booking.booked_at.asc(), Booking.id.asc())
    ).all()

    for index, booking_id in enumerate(queue_ids, start=1):
        if booking_id == booking.id:
            return index
    return None


def _is_subscription_active(subscription: ClientPlanSubscription, plan: Plan, now: datetime) -> bool:
    if not plan.active:
        return False
    if subscription.status != SubscriptionStatus.ACTIVE:
        return False
    if subscription.cancellation_effective_at is not None and now >= subscription.cancellation_effective_at:
        return False
    if (
        subscription.suspension_starts_at is not None
        and subscription.suspension_ends_at is not None
        and subscription.suspension_starts_at <= now < subscription.suspension_ends_at
    ):
        return False
    if subscription.started_at > now:
        return False
    if subscription.ends_at is not None and subscription.ends_at <= now:
        return False
    return True


def _consume_pack_credit(subscription: ClientPlanSubscription, plan: Plan) -> bool:
    if plan.kind != PlanKind.PACK:
        return True

    if subscription.credits_remaining is None or subscription.credits_remaining <= 0:
        return False

    subscription.credits_remaining -= 1
    return True


def _restore_pack_credit(subscription: ClientPlanSubscription, plan: Plan) -> None:
    if plan.kind != PlanKind.PACK:
        return

    current = int(subscription.credits_remaining or 0)
    cap = subscription.credits_initial if subscription.credits_initial is not None else current + 1
    subscription.credits_remaining = min(current + 1, cap)


def _non_negative_money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    quantized = Decimal(value).quantize(Decimal("0.01"))
    if quantized < Decimal("0.00"):
        return Decimal("0.00")
    return quantized


def _forfait_subscription_pricing_applies(
    subscription: ClientPlanSubscription | None,
    *,
    session_start_at: datetime,
) -> bool:
    if subscription is None:
        return False
    if session_start_at < subscription.started_at:
        return False
    if subscription.ends_at is not None and session_start_at >= subscription.ends_at:
        return False
    return True


def _forfait_hourly_ttc_with_overrides(
    *,
    base_hourly_ttc: Decimal,
    subscription: ClientPlanSubscription | None,
    session_start_at: datetime,
    course_type_id: UUID,
    session_timezone: str,
    booking_id: UUID | None,
    db: Session,
) -> Decimal:
    if not _forfait_subscription_pricing_applies(subscription, session_start_at=session_start_at):
        return base_hourly_ttc.quantize(Decimal("0.01"))

    loyalty_discount = Decimal("0.00")
    family_discount = Decimal("0.00")
    short_commitment_supplement = Decimal("0.00")
    second_course_weekly_discount = Decimal("0.00")
    if subscription is not None:
        row = db.execute(
            select(
                ClientForfaitActivityPricing.loyalty_discount_per_hour_ttc,
                ClientForfaitActivityPricing.family_discount_per_hour_ttc,
                ClientForfaitActivityPricing.short_commitment_supplement_per_hour_ttc,
                ClientForfaitActivityPricing.second_course_weekly_discount_per_hour_ttc,
            ).where(
                ClientForfaitActivityPricing.subscription_id == subscription.id,
                ClientForfaitActivityPricing.course_type_id == course_type_id,
            )
        ).first()
        if row is not None:
            loyalty_discount = _non_negative_money(row[0])
            family_discount = _non_negative_money(row[1])
            short_commitment_supplement = _non_negative_money(row[2])
            second_course_weekly_discount = _non_negative_money(row[3])
    if (
        second_course_weekly_discount > Decimal("0.00")
        and subscription is not None
        and _forfait_second_course_weekly_applies(
            db,
            subscription=subscription,
            course_type_id=course_type_id,
            session_start_at=session_start_at,
            session_timezone=session_timezone,
            booking_id=booking_id,
        )
    ):
        loyalty_discount += second_course_weekly_discount
    adjusted = (base_hourly_ttc - loyalty_discount - family_discount + short_commitment_supplement).quantize(Decimal("0.01"))
    if adjusted < Decimal("0.00"):
        return Decimal("0.00")
    return adjusted


def _forfait_week_utc_bounds(*, session_start_at: datetime, session_timezone: str) -> tuple[datetime, datetime]:
    tz_name = (session_timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    local_start = session_start_at.astimezone(tz)
    week_start_local = (local_start - timedelta(days=local_start.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_end_local = week_start_local + timedelta(days=7)
    return week_start_local.astimezone(timezone.utc), week_end_local.astimezone(timezone.utc)


def _forfait_second_course_weekly_applies(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    course_type_id: UUID,
    session_start_at: datetime,
    session_timezone: str,
    booking_id: UUID | None,
) -> bool:
    week_start_utc, week_end_utc = _forfait_week_utc_bounds(
        session_start_at=session_start_at,
        session_timezone=session_timezone,
    )
    counted_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )
    earlier_filters = [CourseSession.start_at_utc < session_start_at]
    if booking_id is not None:
        earlier_filters.append((CourseSession.start_at_utc == session_start_at) & (Booking.id < booking_id))
    earlier_count = int(
        db.scalar(
            select(func.count(Booking.id))
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == subscription.user_id,
                Booking.client_plan_subscription_id == subscription.id,
                Booking.status.in_(counted_statuses),
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.course_type_id == course_type_id,
                CourseSession.start_at_utc >= week_start_utc,
                CourseSession.start_at_utc < week_end_utc,
                or_(*earlier_filters),
            )
        )
        or 0
    )
    return earlier_count >= 1


def _resolve_activity_base_hourly_ttc(course_type: CourseType) -> Decimal:
    if course_type.default_course_rate_ttc is not None:
        reference_minutes = int(course_type.duration_minutes or 0)
        if reference_minutes <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duree de reference invalide pour le tarif par cours",
            )
        reference_hours = Decimal(reference_minutes) / Decimal("60")
        if reference_hours <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duree de reference invalide pour le tarif par cours",
            )
        return (Decimal(course_type.default_course_rate_ttc) / reference_hours).quantize(Decimal("0.01"))

    if course_type.default_hourly_rate is not None:
        return Decimal(course_type.default_hourly_rate).quantize(Decimal("0.01"))

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tarif TTC non defini sur cette activite",
    )


def _restriction_window_start(reference: datetime, period: PlanRestrictionPeriod) -> datetime:
    if period == PlanRestrictionPeriod.DAY:
        return reference.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == PlanRestrictionPeriod.MONTH:
        return reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == PlanRestrictionPeriod.ROLLING_MONTH:
        return reference - timedelta(days=30)
    if period == PlanRestrictionPeriod.SEMESTER:
        semester_start_month = 1 if reference.month <= 6 else 7
        return reference.replace(month=semester_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)

    start_of_day = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = start_of_day.weekday()
    return start_of_day - timedelta(days=weekday)


def _add_months(reference: datetime, months: int) -> datetime:
    total_month = reference.month - 1 + months
    year = reference.year + total_month // 12
    month = total_month % 12 + 1
    return reference.replace(year=year, month=month, day=1)


def _restriction_window_end(start: datetime, period: PlanRestrictionPeriod) -> datetime:
    if period == PlanRestrictionPeriod.DAY:
        return start + timedelta(days=1)
    if period == PlanRestrictionPeriod.WEEK:
        return start + timedelta(days=7)
    if period == PlanRestrictionPeriod.MONTH:
        return _add_months(start, 1)
    if period == PlanRestrictionPeriod.ROLLING_MONTH:
        return start + timedelta(days=30)
    if period == PlanRestrictionPeriod.SEMESTER:
        return _add_months(start, 6)
    return start + timedelta(days=7)


def _normalize_plan_restrictions(plan: Plan) -> list[dict[str, object]]:
    raw = plan.restrictions_json
    if not isinstance(raw, list):
        return []
    restrictions: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            restrictions.append(item)
    return restrictions


def _restriction_course_type_ids(raw: object) -> set[UUID]:
    if not isinstance(raw, list):
        return set()
    out: set[UUID] = set()
    for value in raw:
        try:
            out.add(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def _parse_restriction_period(value: object) -> PlanRestrictionPeriod:
    if isinstance(value, str):
        normalized = value.upper()
        for candidate in PlanRestrictionPeriod:
            if normalized == candidate.value:
                return candidate
    return PlanRestrictionPeriod.WEEK


def _parse_restriction_max(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _restriction_violation_message(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    plan: Plan,
    session_obj: CourseSession,
) -> str | None:
    restrictions = _normalize_plan_restrictions(plan)
    if not restrictions:
        return None

    counted_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )

    for restriction in restrictions:
        period = _parse_restriction_period(restriction.get("period"))
        max_bookings = _parse_restriction_max(restriction.get("max_bookings"))
        if max_bookings <= 0:
            continue

        scope_course_type_ids = _restriction_course_type_ids(restriction.get("course_type_ids"))
        if scope_course_type_ids and session_obj.course_type_id not in scope_course_type_ids:
            continue

        window_start = _restriction_window_start(session_obj.start_at_utc, period)
        window_end = _restriction_window_end(window_start, period)

        stmt = (
            select(func.count(Booking.id))
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == subscription.user_id,
                Booking.client_plan_subscription_id == subscription.id,
                Booking.status.in_(counted_statuses),
                CourseSession.start_at_utc >= window_start,
                CourseSession.start_at_utc < window_end,
            )
        )
        if scope_course_type_ids:
            stmt = stmt.where(CourseSession.course_type_id.in_(scope_course_type_ids))

        count_in_period = int(db.scalar(stmt) or 0)
        if count_in_period >= max_bookings:
            period_label = {
                PlanRestrictionPeriod.DAY: "jour",
                PlanRestrictionPeriod.WEEK: "semaine",
                PlanRestrictionPeriod.MONTH: "mois",
                PlanRestrictionPeriod.ROLLING_MONTH: "mois glissant",
                PlanRestrictionPeriod.SEMESTER: "semestre",
            }.get(period, "periode")
            return f"Restriction formule depassee: {max_bookings} cours max par {period_label}"

    return None


def _enforce_plan_restrictions(
    db: Session,
    *,
    subscription: ClientPlanSubscription,
    plan: Plan,
    session_obj: CourseSession,
) -> None:
    violation = _restriction_violation_message(
        db,
        subscription=subscription,
        plan=plan,
        session_obj=session_obj,
    )
    if violation is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=violation)


def _select_eligible_subscription(
    db: Session,
    *,
    user_id: UUID,
    course_type_id: UUID,
    now: datetime,
    requested_subscription_id: UUID | None,
) -> tuple[ClientPlanSubscription, Plan] | None:
    stmt = (
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(
            PlanEntitlement,
            (PlanEntitlement.plan_id == ClientPlanSubscription.plan_id)
            & (PlanEntitlement.course_type_id == course_type_id),
        )
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]),
            ClientPlanSubscription.started_at <= now,
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > now),
            Plan.active.is_(True),
        )
        .order_by(
            case(
                (Plan.kind == PlanKind.PACK, 0),
                (Plan.kind == PlanKind.FORFAIT, 1),
                else_=2,
            ),
            ClientPlanSubscription.created_at.asc(),
        )
        .with_for_update()
    )

    if requested_subscription_id is not None:
        stmt = stmt.where(ClientPlanSubscription.id == requested_subscription_id)

    candidates = db.execute(stmt).all()
    for subscription, plan in candidates:
        if reconcile_subscription_status(subscription, now=now, plan_kind=plan.kind):
            db.add(subscription)
        if plan.kind == PlanKind.PACK and (subscription.credits_remaining is None or subscription.credits_remaining <= 0):
            continue
        if not _is_subscription_active(subscription, plan, now):
            continue
        return subscription, plan

    return None


def _load_subscription_with_plan_for_update(
    db: Session,
    *,
    subscription_id: UUID,
) -> tuple[ClientPlanSubscription, Plan] | None:
    subscription = db.scalar(
        select(ClientPlanSubscription)
        .where(ClientPlanSubscription.id == subscription_id)
        .with_for_update()
    )
    if subscription is None:
        return None

    plan = db.scalar(select(Plan).where(Plan.id == subscription.plan_id))
    if plan is None:
        return None

    return subscription, plan


def _resolve_booking_snapshot(
    db: Session,
    *,
    session_obj: CourseSession,
    user: User,
    now: datetime,
    subscription: ClientPlanSubscription | None,
    plan: Plan | None,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    billing_profile = resolve_billing_profile(db, user)
    country = (billing_profile.residence_country or "FR").upper()
    currency = (billing_profile.preferred_currency or "EUR").upper()

    # For SUBSCRIPTION/PACK plan-backed bookings, there is no per-session pricing.
    if plan is not None and plan.kind in (PlanKind.SUBSCRIPTION, PlanKind.PACK):
        zero = Decimal("0.00")
        return zero, zero, zero, zero, currency

    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")

    vat_rate = resolve_vat_rate(
        db,
        country=country,
        service_code=course_type.service_code,
        on_date=now.date(),
    )
    duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
    if duration_seconds <= 0:
        duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
    duration_hours = Decimal(duration_seconds) / Decimal("3600")
    hourly_ttc_decimal = _resolve_activity_base_hourly_ttc(course_type)
    if plan is not None and plan.kind == PlanKind.FORFAIT:
        hourly_ttc_decimal = _forfait_hourly_ttc_with_overrides(
            base_hourly_ttc=hourly_ttc_decimal,
            subscription=subscription,
            session_start_at=session_obj.start_at_utc,
            course_type_id=course_type.id,
            session_timezone=session_obj.timezone,
            booking_id=None,
            db=db,
        )
    total_incl_vat = (hourly_ttc_decimal * duration_hours).quantize(Decimal("0.01"))

    if vat_rate <= Decimal("0.00"):
        amount_excl_vat = total_incl_vat
        vat_amount = Decimal("0.00")
    else:
        divisor = Decimal("1.00") + (vat_rate / Decimal("100.00"))
        amount_excl_vat = (total_incl_vat / divisor).quantize(Decimal("0.01")) if divisor > Decimal("0.00") else total_incl_vat
        vat_amount = (total_incl_vat - amount_excl_vat).quantize(Decimal("0.01"))

    return amount_excl_vat, vat_rate.quantize(Decimal("0.01")), vat_amount, total_incl_vat, currency


def _promote_waitlist_if_possible(db: Session, session_obj: CourseSession, now: datetime) -> None:
    while True:
        booked_count = _count_booked(db, session_obj.id)
        if booked_count >= session_obj.capacity_max:
            return

        next_waitlisted = db.scalar(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status == BookingStatus.WAITLISTED,
            )
            .order_by(Booking.booked_at.asc(), Booking.id.asc())
            .with_for_update()
            .limit(1)
        )

        if next_waitlisted is None:
            return

        if next_waitlisted.client_plan_subscription_id is None:
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_NO_PLAN"
            db.flush()
            continue

        sub_and_plan = _load_subscription_with_plan_for_update(
            db,
            subscription_id=next_waitlisted.client_plan_subscription_id,
        )
        if sub_and_plan is None:
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_INVALID_PLAN"
            db.flush()
            continue

        subscription, plan = sub_and_plan

        has_entitlement = db.scalar(
            select(PlanEntitlement.id).where(
                PlanEntitlement.plan_id == subscription.plan_id,
                PlanEntitlement.course_type_id == session_obj.course_type_id,
            )
        )
        if has_entitlement is None or not _is_subscription_active(subscription, plan, now):
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_INELIGIBLE"
            db.flush()
            continue

        violation = _restriction_violation_message(
            db,
            subscription=subscription,
            plan=plan,
            session_obj=session_obj,
        )
        if violation is not None:
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_RESTRICTION"
            db.flush()
            continue

        if not _consume_pack_credit(subscription, plan):
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_NO_CREDIT"
            db.flush()
            continue

        next_waitlisted.status = BookingStatus.BOOKED
        next_waitlisted.booked_at = now
        next_waitlisted.cancelled_at = None
        next_waitlisted.cancellation_reason = None
        promoted_user = db.scalar(
            select(User)
            .where(User.id == next_waitlisted.user_id)
            .with_for_update()
        )
        if promoted_user is not None:
            _mark_first_course_if_needed(promoted_user, session_obj)
        ensure_booking_reminder(
            db,
            booking=next_waitlisted,
            session_obj=session_obj,
            now=now,
        )
        db.flush()


@router.post("/sessions/{session_id}/book", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def book_session(
    session_id: UUID,
    payload: BookingCreateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> BookingOut:
    now = _utcnow()
    payload = payload or BookingCreateRequest()
    booking_owner = _resolve_family_booking_owner(
        db,
        current_user=current_user,
        requested_user_id=payload.user_id,
    )

    session_obj = db.scalar(
        select(CourseSession)
        .where(CourseSession.id == session_id)
        .with_for_update()
    )
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_obj.status != SessionStatus.SCHEDULED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not bookable")

    if session_obj.is_private:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Private session cannot be booked directly")
    if not session_obj.allow_online_booking:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Online booking is disabled for this session")

    if session_obj.start_at_utc <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already started")

    _promote_waitlist_if_possible(db, session_obj, now)

    existing = db.scalar(
        select(Booking)
        .where(
            Booking.session_id == session_id,
            Booking.user_id == booking_owner.id,
        )
        .with_for_update()
    )

    if existing is not None:
        if existing.status == BookingStatus.BOOKED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already booked")
        if existing.status == BookingStatus.WAITLISTED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already in waitlist")
        if existing.status in (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking already closed")

    selected = _select_eligible_subscription(
        db,
        user_id=booking_owner.id,
        course_type_id=session_obj.course_type_id,
        now=now,
        requested_subscription_id=payload.client_plan_subscription_id,
    )
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eligible active plan for this session",
        )

    subscription, plan = selected
    price, vat_rate, vat_amount, total, currency = _resolve_booking_snapshot(
        db,
        session_obj=session_obj,
        user=booking_owner,
        now=now,
        subscription=subscription,
        plan=plan,
    )

    booked_count = _count_booked(db, session_id)
    booking_status = BookingStatus.BOOKED if booked_count < session_obj.capacity_max else BookingStatus.WAITLISTED

    if existing is not None:
        existing.status = booking_status
        existing.client_plan_subscription_id = subscription.id
        existing.booked_at = now
        existing.cancelled_at = None
        existing.cancellation_reason = None
        existing.price_excl_vat_snapshot = price
        existing.vat_rate_snapshot = vat_rate
        existing.vat_amount_snapshot = vat_amount
        existing.total_incl_vat_snapshot = total
        existing.currency_snapshot = currency

        if booking_status == BookingStatus.BOOKED and not _consume_pack_credit(subscription, plan):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No remaining credits on selected pack",
            )

        if booking_status == BookingStatus.BOOKED:
            _enforce_plan_restrictions(
                db,
                subscription=subscription,
                plan=plan,
                session_obj=session_obj,
            )

        if booking_status == BookingStatus.BOOKED:
            _mark_first_course_if_needed(booking_owner, session_obj)
            ensure_booking_reminder(
                db,
                booking=existing,
                session_obj=session_obj,
                now=now,
            )
        else:
            skip_pending_reminders_for_booking(
                db,
                booking_id=existing.id,
                reason="Booking moved to waitlist",
                now=now,
            )

        db.commit()
        db.refresh(existing)

        return BookingOut(
            id=existing.id,
            session_id=existing.session_id,
            client_plan_subscription_id=existing.client_plan_subscription_id,
            status=existing.status,
            booked_at=existing.booked_at,
            cancelled_at=existing.cancelled_at,
            cancellation_reason=existing.cancellation_reason,
            price_excl_vat_snapshot=existing.price_excl_vat_snapshot,
            vat_rate_snapshot=existing.vat_rate_snapshot,
            vat_amount_snapshot=existing.vat_amount_snapshot,
            total_incl_vat_snapshot=existing.total_incl_vat_snapshot,
            currency_snapshot=existing.currency_snapshot,
            waitlist_position=_waitlist_position(db, existing),
        )

    booking = Booking(
        session_id=session_id,
        user_id=booking_owner.id,
        client_plan_subscription_id=subscription.id,
        status=booking_status,
        booked_at=now,
        price_excl_vat_snapshot=price,
        vat_rate_snapshot=vat_rate,
        vat_amount_snapshot=vat_amount,
        total_incl_vat_snapshot=total,
        currency_snapshot=currency,
    )

    if booking_status == BookingStatus.BOOKED and not _consume_pack_credit(subscription, plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No remaining credits on selected pack",
        )

    if booking_status == BookingStatus.BOOKED:
        _enforce_plan_restrictions(
            db,
            subscription=subscription,
            plan=plan,
            session_obj=session_obj,
        )

    db.add(booking)

    if booking_status == BookingStatus.BOOKED:
        db.flush()
        _mark_first_course_if_needed(booking_owner, session_obj)
        ensure_booking_reminder(
            db,
            booking=booking,
            session_obj=session_obj,
            now=now,
        )

    db.commit()
    db.refresh(booking)

    return BookingOut(
        id=booking.id,
        session_id=booking.session_id,
        client_plan_subscription_id=booking.client_plan_subscription_id,
        status=booking.status,
        booked_at=booking.booked_at,
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        price_excl_vat_snapshot=booking.price_excl_vat_snapshot,
        vat_rate_snapshot=booking.vat_rate_snapshot,
        vat_amount_snapshot=booking.vat_amount_snapshot,
        total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
        currency_snapshot=booking.currency_snapshot,
        waitlist_position=_waitlist_position(db, booking),
    )


@router.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_booking(
    booking_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if not _can_manage_booking_owner(db, current_user=current_user, owner_user_id=booking.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to cancel this booking")

    session_obj = db.scalar(
        select(CourseSession)
        .where(CourseSession.id == booking.session_id)
        .with_for_update()
    )
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking already cancelled")

    if booking.status in (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking cannot be cancelled")

    now = _utcnow()
    previous_status = booking.status

    if previous_status == BookingStatus.BOOKED and booking.client_plan_subscription_id is not None and session_obj.start_at_utc > now:
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
    booking.cancellation_reason = "CLIENT_CANCELLED"

    skip_pending_reminders_for_booking(
        db,
        booking_id=booking.id,
        reason="Booking cancelled by client",
        now=now,
    )

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/clients/me/bookings", response_model=list[ClientBookingOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientBookingOut]:
    rows = db.execute(
        select(Booking, CourseSession)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(Booking.user_id == current_user.id)
        .order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())
    ).all()

    return [
        ClientBookingOut(
            id=booking.id,
            client_plan_subscription_id=booking.client_plan_subscription_id,
            status=booking.status,
            booked_at=booking.booked_at,
            cancelled_at=booking.cancelled_at,
            cancellation_reason=booking.cancellation_reason,
            price_excl_vat_snapshot=booking.price_excl_vat_snapshot,
            vat_rate_snapshot=booking.vat_rate_snapshot,
            vat_amount_snapshot=booking.vat_amount_snapshot,
            total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
            currency_snapshot=booking.currency_snapshot,
            session=SessionMiniOut(
                id=session.id,
                title=session.title,
                start_at_utc=session.start_at_utc,
                end_at_utc=session.end_at_utc,
                status=session.status,
            ),
        )
        for booking, session in rows
    ]
