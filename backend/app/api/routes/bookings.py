from __future__ import annotations
from app.services.annual_contracts import contract_price_for_session

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import unicodedata
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import (
    BOOKING_STATUSES_CONSUMING_CAPACITY,
    Booking,
    BookingStatus,
    CourseSession,
    CourseType,
    DeliveryMode,
    Location,
    PlanningConfig,
    SessionAudienceScope,
    SessionStatus,
)
from app.models.client_record import ClientManualCreditBalance
from app.models.family import ClientFamilyLink
from app.models.ops import AppSetting
from app.models.plan import (
    ClientForfaitActivityPricing,
    ClientPlanSubscription,
    Plan,
    PlanCreditGrant,
    PlanEntitlement,
    PlanKind,
    PlanRestrictionPeriod,
    SubscriptionStatus,
)
from app.models.user import ClientKind, User, UserRole
from app.schemas.booking import BookingCreateRequest, BookingOut, ClientBookingOut, SessionMiniOut
from app.services.makeup_passes import (
    active_restricted_forfait_for_booking,
    claim_pending_makeup_request,
    consume_pass_and_create_makeup,
    is_restricted_annual_forfait,
    pending_makeup_request_for_subscription,
)
from app.services.automation_triggers import schedule_booking_created_triggers
from app.services.family_billing import resolve_billing_profile
from app.services.notifications.application.orchestrator import (
    cancel_pending_booking_reminder_notifications,
    enqueue_notifications,
    schedule_booking_cancelled_notifications,
    schedule_booking_created_notifications,
    schedule_waitlist_joined_notification,
    schedule_waitlist_promoted_notification,
)
from app.services.pricing import resolve_vat_rate
from app.services.pricing_catalog import resolve_catalog_activity_price, resolve_catalog_discount_amounts
from app.services.client_pricing import (
    PriceUnit,
    PricingChannel,
    PricingComputation,
    booking_snapshot_fields,
    build_price_version,
    compute_annual_forfait_price,
    compute_fixed_price,
)
from app.services.reminders import ensure_booking_reminder, skip_pending_reminders_for_booking
from app.services.session_automation import restore_cancelled_booking_credit
from app.services.session_audience import (
    allowed_plan_kinds_for_scopes,
    resolve_session_booking_scopes,
    scopes_allow_planless_booking,
)
from app.services.subscriptions import can_book_with_subscription, reconcile_subscription_status
from app.services.trial_courses import has_prior_course_attendance_for_course_type, has_trial_booking_for_course_type

router = APIRouter()

PLANNING_RULE_DEFAULTS = {
    "min_booking_notice_hours": 1,
    "cancellation_deadline_hours": 1,
    "block_client_cancellation": False,
    "waitlist_capacity": 3,
}
ACCOUNT_DEFAULT_CURRENCY_KEY = "config_account_default_currency"
PAYMENT_HOLD_MINUTES = 15
PAYMENT_TIMEOUT_CANCELLATION_REASON = "PAYMENT_TIMEOUT"


def _normalize_course_access_key(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    decomposed = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = without_accents.casefold()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _account_default_currency(db: Session, *, fallback: str = "EUR") -> str:
    raw = db.scalar(select(AppSetting.value).where(AppSetting.key == ACCOUNT_DEFAULT_CURRENCY_KEY))
    candidate = str(raw or "").strip().upper()
    if len(candidate) == 3:
        return candidate
    normalized_fallback = fallback.strip().upper()
    if len(normalized_fallback) == 3:
        return normalized_fallback
    return "EUR"


def _effective_session_booking_rules(
    db: Session,
    *,
    session_obj: CourseSession,
) -> tuple[int, int, bool]:
    config = db.scalar(select(PlanningConfig).where(PlanningConfig.location_id == session_obj.location_id))
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")

    min_booking_notice_hours = int(
        config.min_booking_notice_hours if config is not None else PLANNING_RULE_DEFAULTS["min_booking_notice_hours"]
    )
    cancellation_deadline_hours = int(
        config.cancellation_deadline_hours if config is not None else PLANNING_RULE_DEFAULTS["cancellation_deadline_hours"]
    )
    block_client_cancellation = bool(
        config.block_client_cancellation if config is not None else PLANNING_RULE_DEFAULTS["block_client_cancellation"]
    )

    if course_type.min_booking_notice_hours_override is not None:
        min_booking_notice_hours = int(course_type.min_booking_notice_hours_override)
    if course_type.cancellation_deadline_hours_override is not None:
        cancellation_deadline_hours = int(course_type.cancellation_deadline_hours_override)

    return (
        max(0, min_booking_notice_hours),
        max(0, cancellation_deadline_hours),
        block_client_cancellation,
    )


def _count_booked(db: Session, session_id: UUID, *, exclude_booking_id: UUID | None = None) -> int:
    stmt = select(func.count(Booking.id)).where(
        Booking.session_id == session_id,
        Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY),
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    value = db.scalar(stmt)
    return int(value or 0)


def _session_client_kind_allowed(session_obj: CourseSession, client_kind: ClientKind) -> bool:
    if client_kind == ClientKind.ADULT:
        return bool(getattr(session_obj, "adult_bookings_enabled", False))
    return bool(getattr(session_obj, "child_bookings_enabled", True))


def _session_trial_allowed(session_obj: CourseSession, client_kind: ClientKind) -> bool:
    if client_kind == ClientKind.ADULT:
        return bool(getattr(session_obj, "adult_trial_bookings_enabled", False))
    return bool(getattr(session_obj, "child_trial_bookings_enabled", True))


def _count_booked_for_client_kind(
    db: Session,
    session_id: UUID,
    *,
    client_kind: ClientKind,
    exclude_booking_id: UUID | None = None,
) -> int:
    stmt = (
        select(func.count(Booking.id))
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.session_id == session_id,
            Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY),
            User.client_kind == client_kind,
        )
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    value = db.scalar(stmt)
    return int(value or 0)


def _participant_capacity_block_reason(
    db: Session,
    *,
    session_obj: CourseSession,
    client_kind: ClientKind,
    exclude_booking_id: UUID | None = None,
) -> str | None:
    if not _session_client_kind_allowed(session_obj, client_kind):
        return "AUDIENCE_DISABLED"
    if _count_booked(db, session_obj.id, exclude_booking_id=exclude_booking_id) >= session_obj.capacity_max:
        return "SESSION_FULL"
    adult_capacity_max = getattr(session_obj, "adult_capacity_max", None)
    if client_kind == ClientKind.ADULT and adult_capacity_max is not None:
        adult_count = _count_booked_for_client_kind(
            db,
            session_obj.id,
            client_kind=ClientKind.ADULT,
            exclude_booking_id=exclude_booking_id,
        )
        if adult_count >= int(adult_capacity_max):
            return "ADULT_QUOTA_FULL"
    return None


def _count_waitlisted(db: Session, session_id: UUID, *, exclude_booking_id: UUID | None = None) -> int:
    stmt = select(func.count(Booking.id)).where(
        Booking.session_id == session_id,
        Booking.status == BookingStatus.WAITLISTED,
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    value = db.scalar(stmt)
    return int(value or 0)


def _effective_waitlist_capacity(db: Session, *, session_obj: CourseSession) -> int:
    config = db.scalar(select(PlanningConfig).where(PlanningConfig.location_id == session_obj.location_id))
    waitlist_capacity = int(
        config.waitlist_capacity if config is not None else PLANNING_RULE_DEFAULTS["waitlist_capacity"]
    )
    return max(0, waitlist_capacity)


def _next_booking_status(
    db: Session,
    *,
    session_obj: CourseSession,
    exclude_booking_id: UUID | None = None,
    create_payment_hold: bool = False,
    client_kind: ClientKind | None = None,
) -> BookingStatus | None:
    block_reason = (
        _participant_capacity_block_reason(
            db,
            session_obj=session_obj,
            client_kind=client_kind,
            exclude_booking_id=exclude_booking_id,
        )
        if client_kind is not None
        else (
            "SESSION_FULL"
            if _count_booked(db, session_obj.id, exclude_booking_id=exclude_booking_id) >= session_obj.capacity_max
            else None
        )
    )
    if block_reason is None:
        return BookingStatus.PENDING_PAYMENT if create_payment_hold else BookingStatus.BOOKED
    if block_reason == "AUDIENCE_DISABLED":
        return None

    waitlisted_count = _count_waitlisted(db, session_obj.id, exclude_booking_id=exclude_booking_id)
    if waitlisted_count < _effective_waitlist_capacity(db, session_obj=session_obj):
        return BookingStatus.WAITLISTED

    return None


def payment_hold_expiration(*, now: datetime | None = None) -> datetime:
    ts = now or _utcnow()
    return ts + timedelta(minutes=PAYMENT_HOLD_MINUTES)


def _activate_confirmed_booking(
    db: Session,
    *,
    booking: Booking,
    booking_owner: User,
    session_obj: CourseSession,
    actor_user_id: UUID | None,
    occurred_at: datetime,
) -> list[object]:
    booking.payment_hold_expires_at = None
    _mark_first_course_if_needed(booking_owner, session_obj)
    ensure_booking_reminder(
        db,
        booking=booking,
        session_obj=session_obj,
        now=occurred_at,
    )
    notifications = []
    if actor_user_id is not None:
        notifications = schedule_booking_created_notifications(
            db,
            booking=booking,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
        )
    notifications.extend(
        schedule_booking_created_triggers(
            db,
            booking=booking,
            session_obj=session_obj,
            occurred_at=occurred_at,
        )
    )
    return notifications


def promote_pending_payment_booking(
    db: Session,
    *,
    booking: Booking,
    booking_owner: User,
    session_obj: CourseSession,
    actor_user_id: UUID | None,
    occurred_at: datetime | None = None,
) -> bool:
    ts = occurred_at or _utcnow()
    if booking.status == BookingStatus.BOOKED:
        booking.payment_hold_expires_at = None
        return False
    if booking.status != BookingStatus.PENDING_PAYMENT:
        return False
    if session_obj.status != SessionStatus.SCHEDULED:
        raise ValueError("Only scheduled sessions can be confirmed")
    if _participant_capacity_block_reason(
        db,
        session_obj=session_obj,
        client_kind=booking_owner.client_kind,
        exclude_booking_id=booking.id,
    ) is not None:
        raise ValueError("Session is no longer available")
    booking.status = BookingStatus.BOOKED
    booking.cancelled_at = None
    booking.cancellation_reason = None
    notifications = _activate_confirmed_booking(
        db,
        booking=booking,
        booking_owner=booking_owner,
        session_obj=session_obj,
        actor_user_id=actor_user_id,
        occurred_at=ts,
    )
    if notifications:
        enqueue_notifications(notifications)
    return True


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
    if not can_book_with_subscription(subscription, allow_booking_during_payment_alert=True):
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


def _load_manual_credit_balance_for_update(
    db: Session,
    *,
    user_id: UUID,
    credit_type_id: UUID | None,
) -> ClientManualCreditBalance | None:
    if credit_type_id is None:
        return None
    return db.scalar(
        select(ClientManualCreditBalance)
        .where(
            ClientManualCreditBalance.user_id == user_id,
            ClientManualCreditBalance.credit_type_id == credit_type_id,
        )
        .with_for_update()
    )


def _consume_manual_credit(balance: ClientManualCreditBalance | None) -> bool:
    if balance is None:
        return False
    if int(balance.credits_count or 0) <= 0:
        return False
    balance.credits_count = int(balance.credits_count or 0) - 1
    return True


def _plan_supports_course_access(
    db: Session,
    *,
    plan_id: UUID,
    plan_kind: PlanKind,
    course_type_id: UUID,
    credit_type_id: UUID | None,
    course_type_name: str | None = None,
    course_type_service_code: str | None = None,
) -> bool:
    has_entitlement = db.scalar(
        select(PlanEntitlement.id).where(
            PlanEntitlement.plan_id == plan_id,
            PlanEntitlement.course_type_id == course_type_id,
        )
    )
    if has_entitlement is not None:
        return True

    if plan_kind == PlanKind.PACK and credit_type_id is not None:
        has_credit_grant = db.scalar(
            select(PlanCreditGrant.id).where(
                PlanCreditGrant.plan_id == plan_id,
                PlanCreditGrant.credit_type_id == credit_type_id,
            )
        )
        if has_credit_grant is not None:
            return True

    target_keys = {
        normalized
        for normalized in (
            _normalize_course_access_key(course_type_name),
            _normalize_course_access_key(course_type_service_code),
        )
        if normalized
    }
    if target_keys:
        entitlement_rows = db.execute(
            select(CourseType.name, CourseType.service_code)
            .join(PlanEntitlement, PlanEntitlement.course_type_id == CourseType.id)
            .where(PlanEntitlement.plan_id == plan_id)
        ).all()
        for entitlement_name, entitlement_service_code in entitlement_rows:
            entitlement_keys = {
                normalized
                for normalized in (
                    _normalize_course_access_key(entitlement_name),
                    _normalize_course_access_key(entitlement_service_code),
                )
                if normalized
            }
            if entitlement_keys & target_keys:
                return True

    return False


def _restore_manual_credit(balance: ClientManualCreditBalance | None) -> None:
    if balance is None:
        return
    balance.credits_count = int(balance.credits_count or 0) + 1


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


def _forfait_adjustment_values(
    *,
    subscription: ClientPlanSubscription | None,
    session_start_at: datetime,
    course_type_id: UUID,
    session_timezone: str,
    booking_id: UUID | None,
    db: Session,
    location_id: UUID | None = None,
    student_category: str | None = None,
) -> tuple[Decimal, Decimal, Decimal, Decimal, bool]:
    if not _forfait_subscription_pricing_applies(subscription, session_start_at=session_start_at):
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False

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
    catalog_amounts = resolve_catalog_discount_amounts(
        db,
        activity_id=course_type_id,
        location_id=location_id,
        student_category=student_category,
        channel=PricingChannel.ANNUAL_FORFAIT.value,
        at=session_start_at,
    )
    # Existing per-client values remain the eligibility signal. Once a
    # catalog is explicitly published, its central amount replaces the old
    # duplicated amount for eligible clients only.
    if loyalty_discount > Decimal("0.00") and "LOYALTY" in catalog_amounts:
        loyalty_discount = catalog_amounts["LOYALTY"]
    if family_discount > Decimal("0.00") and "FAMILY" in catalog_amounts:
        family_discount = catalog_amounts["FAMILY"]
    if short_commitment_supplement > Decimal("0.00") and "SHORT_COMMITMENT" in catalog_amounts:
        short_commitment_supplement = catalog_amounts["SHORT_COMMITMENT"]
    if second_course_weekly_discount > Decimal("0.00") and "SECOND_COURSE" in catalog_amounts:
        second_course_weekly_discount = catalog_amounts["SECOND_COURSE"]
    second_course_weekly_applies = (
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
    )
    return (
        loyalty_discount,
        family_discount,
        short_commitment_supplement,
        second_course_weekly_discount,
        second_course_weekly_applies,
    )


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
    loyalty, family, supplement, second_course, second_course_applies = _forfait_adjustment_values(
        subscription=subscription,
        session_start_at=session_start_at,
        course_type_id=course_type_id,
        session_timezone=session_timezone,
        booking_id=booking_id,
        db=db,
    )
    result = compute_annual_forfait_price(
        base_hourly_ttc=base_hourly_ttc,
        duration_hours=Decimal("1.00"),
        loyalty_discount_per_hour_ttc=loyalty,
        family_discount_per_hour_ttc=family,
        second_course_discount_per_hour_ttc=second_course,
        second_course_applies=second_course_applies,
        short_commitment_supplement_per_hour_ttc=supplement,
        vat_rate=Decimal("0.00"),
        currency="EUR",
        source=f"course-type:{course_type_id}",
        version=f"course-type:{course_type_id}:v1",
    )
    return result.total_incl_vat


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
        return Decimal(course_type.default_course_rate_ttc) / reference_hours

    if course_type.default_hourly_rate is not None:
        return Decimal(course_type.default_hourly_rate).quantize(Decimal("0.01"))

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tarif TTC non defini sur cette activite",
    )


def _booking_vat_country(
    *,
    session_obj: CourseSession,
    course_type: CourseType,
    billing_profile: User,
    db: Session,
) -> str:
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))

    is_online = course_type.mode == DeliveryMode.ONLINE or bool(
        location.is_online if location is not None else False
    )

    if is_online:
        return (billing_profile.residence_country or "FR").upper()
    if location is not None:
        return (location.country_code or "FR").upper()
    return "FR"


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
    now: datetime | None = None,
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

        if period == PlanRestrictionPeriod.ACTIVE_BOOKINGS:
            active_stmt = (
                select(func.count(Booking.id))
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == subscription.user_id,
                    Booking.client_plan_subscription_id == subscription.id,
                    Booking.status == BookingStatus.BOOKED,
                    CourseSession.start_at_utc > (now or _utcnow()),
                )
            )
            if scope_course_type_ids:
                active_stmt = active_stmt.where(CourseSession.course_type_id.in_(scope_course_type_ids))

            active_booking_count = int(db.scalar(active_stmt) or 0)
            if active_booking_count >= max_bookings:
                return f"Restriction formule depassee: {max_bookings} reservations actives maximum"
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
    now: datetime | None = None,
) -> None:
    violation = _restriction_violation_message(
        db,
        subscription=subscription,
        plan=plan,
        session_obj=session_obj,
        now=now,
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
    allowed_plan_kinds: set[PlanKind] | None = None,
    coverage_at: datetime | None = None,
    include_pending_preview: bool = False,
    allow_trial: bool = True,
) -> tuple[ClientPlanSubscription, Plan] | None:
    eligibility_at = coverage_at or now
    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    credit_type_id = course_type.credit_type_id if course_type is not None else None
    course_type_name = course_type.name if course_type is not None else None
    course_type_service_code = course_type.service_code if course_type is not None else None

    eligible_statuses = [
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAYMENT_ALERT,
        SubscriptionStatus.PAUSED,
    ]
    if include_pending_preview:
        eligible_statuses.append(SubscriptionStatus.PENDING)

    stmt = (
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id == user_id,
            ClientPlanSubscription.status.in_(eligible_statuses),
            ClientPlanSubscription.started_at <= eligibility_at,
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at > eligibility_at),
            Plan.active.is_(True),
        )
        .order_by(
            case((Plan.is_trial_offer.is_(True), 0), else_=1),
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
    if allowed_plan_kinds:
        stmt = stmt.where(Plan.kind.in_(tuple(allowed_plan_kinds)))

    candidates = db.execute(stmt).all()
    for subscription, plan in candidates:
        if not _plan_supports_course_access(
            db,
            plan_id=plan.id,
            plan_kind=plan.kind,
            course_type_id=course_type_id,
            credit_type_id=credit_type_id,
            course_type_name=course_type_name,
            course_type_service_code=course_type_service_code,
        ):
            continue
        if is_restricted_annual_forfait(plan) and pending_makeup_request_for_subscription(
            db,
            user_id=user_id,
            subscription_id=subscription.id,
        ) is None:
            continue
        is_pending_preview = include_pending_preview and subscription.status == SubscriptionStatus.PENDING
        if not is_pending_preview and reconcile_subscription_status(subscription, now=now, plan_kind=plan.kind):
            db.add(subscription)
        if plan.kind == PlanKind.PACK and (subscription.credits_remaining is None or subscription.credits_remaining <= 0):
            continue
        if bool(getattr(plan, "is_trial_offer", False)):
            if not allow_trial:
                continue
            if (
                course_type is None
                or not bool(getattr(course_type, "trial_course_enabled", False))
                or getattr(course_type, "trial_course_price_ttc", None) is None
            ):
                continue
            if has_trial_booking_for_course_type(
                db,
                user_id=user_id,
                course_type_id=course_type_id,
            ) or has_prior_course_attendance_for_course_type(
                db,
                user_id=user_id,
                course_type_id=course_type_id,
                reference_at=eligibility_at,
            ):
                continue
        if not is_pending_preview and not _is_subscription_active(subscription, plan, eligibility_at):
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


def _resolve_booking_pricing(
    db: Session,
    *,
    session_obj: CourseSession,
    user: User,
    now: datetime,
    subscription: ClientPlanSubscription | None,
    plan: Plan | None,
    covered_by_manual_credit: bool = False,
    use_makeup: bool = False,
) -> PricingComputation:
    if subscription is not None and plan is not None and plan.kind == PlanKind.FORFAIT:
        if use_makeup and is_restricted_annual_forfait(plan):
            request = pending_makeup_request_for_subscription(db, user_id=user.id, subscription_id=subscription.id)
            if request is not None:
                from app.services.makeup_booking import validate_target, makeup_price
                original, _, _ = validate_target(db, request, session_obj, now=now)
                return makeup_price(original, request, now=now)
        contractual = contract_price_for_session(subscription, session_obj, now=now)
        if contractual is not None:
            return contractual
    billing_profile = resolve_billing_profile(db, user)
    currency = (billing_profile.preferred_currency or "EUR").upper()

    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")

    duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
    if duration_seconds <= 0:
        duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
    duration_hours = Decimal(duration_seconds) / Decimal("3600")
    source = f"course-type:{course_type.id}"
    version = build_price_version(
        "course-type",
        course_type_id=course_type.id,
        default_hourly_rate=course_type.default_hourly_rate,
        default_course_rate_ttc=course_type.default_course_rate_ttc,
        duration_minutes=course_type.duration_minutes,
        service_code=course_type.service_code,
    )

    # For SUBSCRIPTION/PACK plan-backed bookings, there is no per-session pricing.
    if covered_by_manual_credit or (plan is not None and plan.kind in (PlanKind.SUBSCRIPTION, PlanKind.PACK)):
        if covered_by_manual_credit:
            channel = PricingChannel.MANUAL_CREDIT
            source = f"manual-credit:course-type:{course_type.id}"
        elif bool(getattr(plan, "is_trial_offer", False)):
            channel = PricingChannel.TRIAL
            source = f"trial-plan:{plan.id}"
        elif plan is not None and plan.kind == PlanKind.PACK:
            channel = PricingChannel.PACK
            source = f"pack-plan:{plan.id}"
        else:
            channel = PricingChannel.SUBSCRIPTION
            source = f"subscription-plan:{plan.id}" if plan is not None else source
        version = build_price_version(
            "plan-booking",
            plan_id=getattr(plan, "id", None),
            plan_kind=getattr(plan, "kind", None),
            is_trial_offer=bool(getattr(plan, "is_trial_offer", False)),
            course_type_version=version,
        )
        return compute_fixed_price(
            channel=channel,
            amount_ttc=Decimal("0.00"),
            unit=PriceUnit.PER_SESSION,
            duration_hours=duration_hours,
            vat_rate=Decimal("0.00"),
            currency=currency,
            source=source,
            version=version,
            calculated_at=now,
        )

    vat_country = _booking_vat_country(
        session_obj=session_obj,
        course_type=course_type,
        billing_profile=billing_profile,
        db=db,
    )
    vat_rate = resolve_vat_rate(
        db,
        country=vat_country,
        service_code=course_type.service_code,
        on_date=now.date(),
    )
    duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
    if duration_seconds <= 0:
        duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
    duration_hours = Decimal(duration_seconds) / Decimal("3600")

    catalog_external_price = None
    if subscription is None and plan is None:
        catalog_external_price = resolve_catalog_activity_price(
            db,
            activity_id=course_type.id,
            location_id=session_obj.location_id,
            student_category=getattr(getattr(user, "client_kind", None), "value", None),
            channel=PricingChannel.EXTERNAL_UNIT.value,
            at=session_obj.start_at_utc,
        )
    if catalog_external_price is not None:
        return compute_fixed_price(
            channel=PricingChannel.EXTERNAL_UNIT,
            amount_ttc=catalog_external_price.amount_for_duration(duration_hours),
            unit=PriceUnit.PER_SESSION,
            duration_hours=duration_hours,
            vat_rate=vat_rate,
            currency=catalog_external_price.currency,
            source=catalog_external_price.source,
            version=catalog_external_price.version,
            calculated_at=now,
        )

    if subscription is None and plan is None and session_obj.external_booking_price_ttc is not None:
        currency = _account_default_currency(db, fallback=currency)
        raw_unit = str(getattr(session_obj, "external_booking_price_unit", None) or PriceUnit.PER_HOUR.value)
        unit = PriceUnit.PER_SESSION if raw_unit == PriceUnit.PER_SESSION.value else PriceUnit.PER_HOUR
        version = build_price_version(
            "external-session",
            session_id=session_obj.id,
            raw_amount_ttc=session_obj.external_booking_price_ttc,
            unit=unit,
            vat_rate=vat_rate,
            course_type_version=version,
        )
        return compute_fixed_price(
            channel=PricingChannel.EXTERNAL_UNIT,
            amount_ttc=Decimal(session_obj.external_booking_price_ttc),
            unit=unit,
            duration_hours=duration_hours,
            vat_rate=vat_rate,
            currency=currency,
            source=f"course-session:{session_obj.id}:external",
            version=version,
            calculated_at=now,
        )

    hourly_ttc_decimal = _resolve_activity_base_hourly_ttc(course_type)
    if plan is not None and plan.kind == PlanKind.FORFAIT:
        catalog_price = resolve_catalog_activity_price(
            db,
            activity_id=course_type.id,
            location_id=session_obj.location_id,
            student_category=getattr(getattr(user, "client_kind", None), "value", None),
            channel=PricingChannel.ANNUAL_FORFAIT.value,
            at=session_obj.start_at_utc,
        )
        if catalog_price is not None:
            hourly_ttc_decimal = catalog_price.hourly_amount(duration_hours)
            source = catalog_price.source
            version = catalog_price.version
        loyalty, family, supplement, second_course, second_course_applies = _forfait_adjustment_values(
            subscription=subscription,
            session_start_at=session_obj.start_at_utc,
            course_type_id=course_type.id,
            session_timezone=session_obj.timezone,
            booking_id=None,
            db=db,
            location_id=session_obj.location_id,
            student_category=getattr(getattr(user, "client_kind", None), "value", None),
        )
        version = build_price_version(
            "annual-forfait",
            course_type_version=version,
            subscription_id=getattr(subscription, "id", None),
            loyalty_discount=loyalty,
            family_discount=family,
            short_commitment_supplement=supplement,
            second_course_discount=second_course,
            second_course_applies=second_course_applies,
            vat_rate=vat_rate,
        )
        return compute_annual_forfait_price(
            base_hourly_ttc=hourly_ttc_decimal,
            duration_hours=duration_hours,
            loyalty_discount_per_hour_ttc=loyalty,
            family_discount_per_hour_ttc=family,
            second_course_discount_per_hour_ttc=second_course,
            second_course_applies=second_course_applies,
            short_commitment_supplement_per_hour_ttc=supplement,
            vat_rate=vat_rate,
            currency=currency,
            source=(
                f"{source}:subscription:{subscription.id}"
                if subscription is not None and catalog_price is not None
                else f"subscription:{subscription.id}:course-type:{course_type.id}"
                if subscription is not None
                else source
            ),
            version=version,
            calculated_at=now,
        )

    catalog_standard_price = resolve_catalog_activity_price(
        db,
        activity_id=course_type.id,
        location_id=session_obj.location_id,
        student_category=getattr(getattr(user, "client_kind", None), "value", None),
        channel=PricingChannel.STANDARD.value,
        at=session_obj.start_at_utc,
    )
    if catalog_standard_price is not None:
        return compute_fixed_price(
            channel=PricingChannel.STANDARD,
            amount_ttc=catalog_standard_price.amount_for_duration(duration_hours),
            unit=PriceUnit.PER_SESSION,
            duration_hours=duration_hours,
            vat_rate=vat_rate,
            currency=catalog_standard_price.currency,
            source=catalog_standard_price.source,
            version=catalog_standard_price.version,
            calculated_at=now,
        )

    return compute_fixed_price(
        channel=PricingChannel.STANDARD,
        amount_ttc=hourly_ttc_decimal,
        unit=PriceUnit.PER_HOUR,
        duration_hours=duration_hours,
        vat_rate=vat_rate,
        currency=currency,
        source=source,
        version=version,
        calculated_at=now,
    )


def _resolve_booking_snapshot(
    db: Session,
    *,
    session_obj: CourseSession,
    user: User,
    now: datetime,
    subscription: ClientPlanSubscription | None,
    plan: Plan | None,
    covered_by_manual_credit: bool = False,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    return _resolve_booking_pricing(
        db,
        session_obj=session_obj,
        user=user,
        now=now,
        subscription=subscription,
        plan=plan,
        covered_by_manual_credit=covered_by_manual_credit,
    ).legacy_tuple()


def _promote_waitlist_if_possible(
    db: Session,
    session_obj: CourseSession,
    now: datetime,
    *,
    allow_planless_promotion: bool = False,
) -> list[object]:
    notifications: list[object] = []
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    credit_type_id = course_type.credit_type_id if course_type is not None else None
    course_type_name = course_type.name if course_type is not None else None
    course_type_service_code = course_type.service_code if course_type is not None else None

    while True:
        booked_count = _count_booked(db, session_obj.id)
        if booked_count >= session_obj.capacity_max:
            return notifications

        waitlisted_candidates = db.scalars(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status == BookingStatus.WAITLISTED,
            )
            .order_by(Booking.booked_at.asc(), Booking.id.asc())
            .with_for_update()
        ).all()

        next_waitlisted: Booking | None = None
        promoted_user: User | None = None
        for candidate in waitlisted_candidates:
            candidate_user = db.scalar(
                select(User)
                .where(User.id == candidate.user_id)
                .with_for_update()
            )
            if candidate_user is None:
                candidate.status = BookingStatus.CANCELLED
                candidate.cancelled_at = now
                candidate.cancellation_reason = "WAITLIST_PROMOTION_USER_MISSING"
                db.flush()
                continue
            if _participant_capacity_block_reason(
                db,
                session_obj=session_obj,
                client_kind=candidate_user.client_kind,
            ) is None:
                next_waitlisted = candidate
                promoted_user = candidate_user
                break

        if next_waitlisted is None or promoted_user is None:
            return notifications

        if bool(next_waitlisted.is_trial_course) and not _session_trial_allowed(
            session_obj,
            promoted_user.client_kind,
        ):
            next_waitlisted.status = BookingStatus.CANCELLED
            next_waitlisted.cancelled_at = now
            next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_TRIAL_DISABLED"
            db.flush()
            continue

        def confirm_promotion(
            eligible_subscription: ClientPlanSubscription | None = None,
            eligible_plan: Plan | None = None,
        ) -> None:
            if eligible_subscription is not None and eligible_plan is not None and is_restricted_annual_forfait(eligible_plan):
                try:
                    claim_pending_makeup_request(
                        db,
                        booking=next_waitlisted,
                        subscription=eligible_subscription,
                        now=now,
                    )
                except (ValueError, HTTPException):
                    next_waitlisted.status = BookingStatus.CANCELLED
                    next_waitlisted.cancelled_at = now
                    next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_NO_MAKEUP_REQUEST"
                    return
            next_waitlisted.status = BookingStatus.BOOKED
            next_waitlisted.booked_at = now
            next_waitlisted.cancelled_at = None
            next_waitlisted.cancellation_reason = None
            notifications.extend(
                _activate_confirmed_booking(
                    db,
                    booking=next_waitlisted,
                    booking_owner=promoted_user,
                    session_obj=session_obj,
                    actor_user_id=None,
                    occurred_at=now,
                )
            )
            db.flush()
            notifications.extend(
                schedule_waitlist_promoted_notification(
                    db,
                    booking=next_waitlisted,
                    occurred_at=now,
                )
            )
        if next_waitlisted.client_plan_subscription_id is None:
            if next_waitlisted.manual_credit_type_id is not None:
                manual_credit_balance = _load_manual_credit_balance_for_update(
                    db,
                    user_id=next_waitlisted.user_id,
                    credit_type_id=next_waitlisted.manual_credit_type_id,
                )
                if not _consume_manual_credit(manual_credit_balance):
                    next_waitlisted.status = BookingStatus.CANCELLED
                    next_waitlisted.cancelled_at = now
                    next_waitlisted.cancellation_reason = "WAITLIST_PROMOTION_NO_MANUAL_CREDIT"
                    db.flush()
                    continue
                confirm_promotion()
                continue
            if allow_planless_promotion:
                confirm_promotion()
                continue
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

        if (
            not _plan_supports_course_access(
                db,
                plan_id=subscription.plan_id,
                plan_kind=plan.kind,
                course_type_id=session_obj.course_type_id,
                credit_type_id=credit_type_id,
                course_type_name=course_type_name,
                course_type_service_code=course_type_service_code,
            )
            or not _is_subscription_active(subscription, plan, now)
        ):
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

        confirm_promotion(subscription, plan)


def _book_session_internal(
    *,
    session_id: UUID,
    payload: BookingCreateRequest | None,
    db: Session,
    current_user: User,
    allow_pending_payment_hold: bool = False,
) -> BookingOut:
    now = _utcnow()
    orchestrated_notifications = []
    payload = payload or BookingCreateRequest()
    booking_owner = _resolve_family_booking_owner(
        db,
        current_user=current_user,
        requested_user_id=payload.user_id,
    )
    locked_booking_owner = db.scalar(
        select(User)
        .where(User.id == booking_owner.id)
        .with_for_update()
    )
    if locked_booking_owner is not None:
        booking_owner = locked_booking_owner

    session_obj = db.scalar(
        select(CourseSession)
        .where(CourseSession.id == session_id)
        .with_for_update()
    )
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course type not found")
    if not bool(course_type.allows_student_bookings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This slot does not accept student bookings",
        )
    if not _session_client_kind_allowed(session_obj, booking_owner.client_kind):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This slot is not open to this participant type",
        )

    if session_obj.status != SessionStatus.SCHEDULED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not bookable")

    session_booking_scopes = resolve_session_booking_scopes(
        session_obj,
        allows_student_bookings=bool(course_type.allows_student_bookings),
    )
    if session_booking_scopes == [SessionAudienceScope.PRIVATE]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Private session cannot be booked directly")
    allows_planless_booking = scopes_allow_planless_booking(session_booking_scopes)
    allowed_plan_kinds = allowed_plan_kinds_for_scopes(session_booking_scopes)
    if not allowed_plan_kinds and not allows_planless_booking:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Online booking is disabled for this session")

    if session_obj.start_at_utc <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already started")
    min_booking_notice_hours, _, _ = _effective_session_booking_rules(db, session_obj=session_obj)
    if session_obj.start_at_utc < now + timedelta(hours=min_booking_notice_hours):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Booking deadline reached for this activity",
        )

    orchestrated_notifications.extend(
        _promote_waitlist_if_possible(
            db,
            session_obj,
            now,
            allow_planless_promotion=allows_planless_booking,
        )
    )

    existing = db.scalar(
        select(Booking)
        .where(
            Booking.session_id == session_id,
            Booking.user_id == booking_owner.id,
        )
        .with_for_update()
    )

    reusable_existing = existing
    if existing is not None:
        if existing.status == BookingStatus.BOOKED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already booked")
        if existing.status == BookingStatus.WAITLISTED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already in waitlist")
        if existing.status == BookingStatus.PENDING_PAYMENT:
            if not allow_pending_payment_hold:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment pending")
            if existing.payment_hold_expires_at is not None and existing.payment_hold_expires_at <= now:
                existing.status = BookingStatus.CANCELLED
                existing.cancelled_at = now
                existing.cancellation_reason = PAYMENT_TIMEOUT_CANCELLATION_REASON
                existing.payment_hold_expires_at = None
            else:
                reusable_existing = existing
        if existing.status in (BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking already closed")

    selected = _select_eligible_subscription(
        db,
        user_id=booking_owner.id,
        course_type_id=session_obj.course_type_id,
        now=now,
        requested_subscription_id=payload.client_plan_subscription_id,
        allowed_plan_kinds=allowed_plan_kinds,
        coverage_at=session_obj.start_at_utc,
    )
    if (
        selected is not None
        and bool(selected[1].is_trial_offer)
        and not _session_trial_allowed(session_obj, booking_owner.client_kind)
    ):
        if payload.client_plan_subscription_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trial bookings are not open to this participant type for this slot",
            )
        selected = _select_eligible_subscription(
            db,
            user_id=booking_owner.id,
            course_type_id=session_obj.course_type_id,
            now=now,
            requested_subscription_id=None,
            allowed_plan_kinds=allowed_plan_kinds,
            coverage_at=session_obj.start_at_utc,
            allow_trial=False,
        )
    subscription: ClientPlanSubscription | None = None
    plan: Plan | None = None
    manual_credit_balance: ClientManualCreditBalance | None = None
    manual_credit_type_id: UUID | None = None
    if selected is not None:
        subscription, plan = selected
    elif course_type.credit_type_id is not None:
        manual_credit_balance = _load_manual_credit_balance_for_update(
            db,
            user_id=booking_owner.id,
            credit_type_id=course_type.credit_type_id,
        )
        if manual_credit_balance is not None and int(manual_credit_balance.credits_count or 0) > 0:
            manual_credit_type_id = course_type.credit_type_id
    elif payload.client_plan_subscription_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selected plan is not eligible for this session",
        )
    elif not allows_planless_booking:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eligible active plan for this session",
        )
    pricing = _resolve_booking_pricing(
        db,
        session_obj=session_obj,
        user=booking_owner,
        now=now,
        subscription=subscription,
        plan=plan,
        covered_by_manual_credit=manual_credit_type_id is not None,
        use_makeup=True,
    )
    price, vat_rate, vat_amount, total, currency = pricing.legacy_tuple()
    pricing_fields = booking_snapshot_fields(pricing)
    is_trial_booking = bool(plan is not None and plan.is_trial_offer)
    if is_trial_booking and not _session_trial_allowed(session_obj, booking_owner.client_kind):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial bookings are not open to this participant type for this slot",
        )

    should_create_payment_hold = allow_pending_payment_hold and subscription is None and total > Decimal("0.00")
    booking_status = _next_booking_status(
        db,
        session_obj=session_obj,
        exclude_booking_id=(
            reusable_existing.id
            if reusable_existing is not None and reusable_existing.status in BOOKING_STATUSES_CONSUMING_CAPACITY
            else None
        ),
        create_payment_hold=should_create_payment_hold,
        client_kind=booking_owner.client_kind,
    )
    if booking_status is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is full")

    if booking_status == BookingStatus.BOOKED and subscription is not None and plan is not None and not _consume_pack_credit(subscription, plan):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No remaining credits on selected pack",
        )
    if booking_status == BookingStatus.BOOKED and manual_credit_type_id is not None and not _consume_manual_credit(manual_credit_balance):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No remaining manual credits for this activity",
        )

    if booking_status == BookingStatus.BOOKED and subscription is not None and plan is not None:
        _enforce_plan_restrictions(
            db,
            subscription=subscription,
            plan=plan,
            session_obj=session_obj,
            now=now,
        )

    if reusable_existing is not None:
        booking = reusable_existing
        booking.session_id = session_id
        booking.user_id = booking_owner.id
        booking.client_plan_subscription_id = subscription.id if subscription is not None else None
        booking.manual_credit_type_id = manual_credit_type_id
        booking.status = booking_status
        booking.booked_at = now
        booking.cancelled_at = None
        booking.cancellation_reason = None
        booking.price_excl_vat_snapshot = price
        booking.vat_rate_snapshot = vat_rate
        booking.vat_amount_snapshot = vat_amount
        booking.total_incl_vat_snapshot = total
        booking.currency_snapshot = currency
        for field_name, field_value in pricing_fields.items():
            setattr(booking, field_name, field_value)
        booking.payment_hold_expires_at = payment_hold_expiration(now=now) if booking_status == BookingStatus.PENDING_PAYMENT else None
        booking.is_trial_course = is_trial_booking
        booking.trial_course_type_id = session_obj.course_type_id if is_trial_booking else None
    else:
        booking = Booking(
            session_id=session_id,
            user_id=booking_owner.id,
            client_plan_subscription_id=subscription.id if subscription is not None else None,
            manual_credit_type_id=manual_credit_type_id,
            status=booking_status,
            booked_at=now,
            payment_hold_expires_at=payment_hold_expiration(now=now) if booking_status == BookingStatus.PENDING_PAYMENT else None,
            **pricing_fields,
            is_trial_course=is_trial_booking,
            trial_course_type_id=session_obj.course_type_id if is_trial_booking else None,
        )
        db.add(booking)

    if booking_status == BookingStatus.BOOKED:
        db.flush()
        if subscription is not None and plan is not None and is_restricted_annual_forfait(plan):
            try:
                claim_pending_makeup_request(
                    db,
                    booking=booking,
                    subscription=subscription,
                    now=now,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Aucune recuperation de cours n est disponible pour ce forfait.",
                ) from exc
        orchestrated_notifications.extend(
            _activate_confirmed_booking(
                db,
                booking=booking,
                booking_owner=booking_owner,
                session_obj=session_obj,
                actor_user_id=current_user.id,
                occurred_at=now,
            )
        )
    else:
        if reusable_existing is None:
            db.flush()
        if booking_status == BookingStatus.WAITLISTED:
            waitlist_position = _waitlist_position(db, booking)
            if waitlist_position is not None:
                orchestrated_notifications.extend(
                    schedule_waitlist_joined_notification(
                        db,
                        booking=booking,
                        actor_user_id=current_user.id,
                        occurred_at=now,
                        waitlist_position=waitlist_position,
                    )
                )
        skip_pending_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Booking pending payment" if booking_status == BookingStatus.PENDING_PAYMENT else "Booking moved to waitlist",
            now=now,
        )

    db.commit()
    if orchestrated_notifications:
        enqueue_notifications(orchestrated_notifications)
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
        pricing_snapshot_locked=booking.pricing_snapshot_locked,
        pricing_channel_snapshot=booking.pricing_channel_snapshot,
        pricing_source_snapshot=booking.pricing_source_snapshot,
        pricing_unit_snapshot=booking.pricing_unit_snapshot,
        price_book_version_snapshot=booking.price_book_version_snapshot,
        pricing_breakdown_snapshot=booking.pricing_breakdown_snapshot or {},
        pricing_calculated_at=booking.pricing_calculated_at,
        student_start_at_utc=booking.student_start_at_utc,
        student_end_at_utc=booking.student_end_at_utc,
        waitlist_position=_waitlist_position(db, booking),
    )


@router.post("/sessions/{session_id}/book", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def book_session(
    session_id: UUID,
    payload: BookingCreateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> BookingOut:
    return _book_session_internal(
        session_id=session_id,
        payload=payload,
        db=db,
        current_user=current_user,
        allow_pending_payment_hold=False,
    )


def create_or_refresh_pending_payment_booking(
    *,
    session_id: UUID,
    payload: BookingCreateRequest | None,
    db: Session,
    current_user: User,
) -> BookingOut:
    return _book_session_internal(
        session_id=session_id,
        payload=payload,
        db=db,
        current_user=current_user,
        allow_pending_payment_hold=True,
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
    _, cancellation_deadline_hours, block_client_cancellation = _effective_session_booking_rules(db, session_obj=session_obj)
    if previous_status == BookingStatus.BOOKED:
        if block_client_cancellation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client cancellation is disabled for this planning/activity",
            )
        if session_obj.start_at_utc < now + timedelta(hours=cancellation_deadline_hours):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cancellation deadline reached for this activity",
            )

    restricted_forfait = None
    if previous_status == BookingStatus.BOOKED:
        restricted_forfait = active_restricted_forfait_for_booking(
            db,
            booking=booking,
            now=now,
            lock=True,
        )
        if restricted_forfait is not None:
            try:
                consume_pass_and_create_makeup(
                    db,
                    booking=booking,
                    subscription=restricted_forfait,
                    actor_user_id=current_user.id,
                    now=now,
                )
            except ValueError as exc:
                if str(exc) == "MAKEUP_PASS_REQUIRED":
                    preferred_language = str(current_user.preferred_language or "fr").strip().lower()
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Cancellation is not available: the 2026-2027 annual plan requires a Makeup Pass "
                            "with at least one remaining credit."
                            if preferred_language.startswith("en")
                            else "Annulation impossible : le forfait Année 2026-2027 exige un Pass Récup "
                            "avec au moins un crédit disponible."
                        ),
                    ) from exc
                raise

    if previous_status == BookingStatus.BOOKED and session_obj.start_at_utc > now:
        restore_cancelled_booking_credit(db, booking=booking)

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    booking.cancellation_reason = "CLIENT_CANCELLED"

    skip_pending_reminders_for_booking(
        db,
        booking_id=booking.id,
        reason="Booking cancelled by client",
        now=now,
    )
    cancel_pending_booking_reminder_notifications(
        db,
        booking_id=booking.id,
        reason="Booking cancelled by client",
        now=now,
    )
    orchestrated_notifications = schedule_booking_cancelled_notifications(
        db,
        booking=booking,
        actor_user_id=current_user.id,
        occurred_at=now,
    )
    if previous_status in BOOKING_STATUSES_CONSUMING_CAPACITY and session_obj.start_at_utc > now:
        orchestrated_notifications.extend(
            _promote_waitlist_if_possible(
                db,
                session_obj,
                now,
                allow_planless_promotion=scopes_allow_planless_booking(
                    resolve_session_booking_scopes(session_obj)
                ),
            )
        )
    db.commit()
    if orchestrated_notifications:
        enqueue_notifications(orchestrated_notifications)
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
            pricing_snapshot_locked=booking.pricing_snapshot_locked,
            pricing_channel_snapshot=booking.pricing_channel_snapshot,
            pricing_source_snapshot=booking.pricing_source_snapshot,
            pricing_unit_snapshot=booking.pricing_unit_snapshot,
            price_book_version_snapshot=booking.price_book_version_snapshot,
            pricing_breakdown_snapshot=booking.pricing_breakdown_snapshot or {},
            pricing_calculated_at=booking.pricing_calculated_at,
            student_start_at_utc=booking.student_start_at_utc,
            student_end_at_utc=booking.student_end_at_utc,
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
