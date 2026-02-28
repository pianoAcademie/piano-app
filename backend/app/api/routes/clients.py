from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.config import settings
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, Plan, PlanEntitlement, PlanKind, PlanPriceTaxMode, SubscriptionStatus
from app.models.ops import EmailReminder
from app.models.user import ClientKind, User, UserRole
from app.schemas.catalog import SessionCourseTypeOut, SessionLocationOut, SessionOut, SessionProfessorOut
from app.schemas.user import (
    ClientFamilyOverviewOut,
    ClientInvoiceOut,
    ClientPaymentConfirmOut,
    ClientMessageOut,
    ClientMessageScope,
    ClientPaymentCheckoutOut,
    ClientMeUpdateRequest,
    ClientPaymentOut,
    FamilyBookingOut,
    FamilyLinkOut,
    FamilyMemberOut,
    FamilyPlanMiniOut,
    FamilySessionMiniOut,
    FamilySubscriptionOut,
    UserOut,
)
from app.services.family_billing import resolve_billing_profile
from app.services.client_purchase_notifications import send_client_payment_success_notifications
from app.services.invoice_documents import InvoicePeriodLine, render_invoice_period_pdf
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, lookup_payment, with_webhook_secret
from app.services.payment_provider import resolve_provider
from app.services.pricing import compute_tax_totals, plan_service_code, resolve_plan_price, resolve_vat_rate

router = APIRouter()
logger = logging.getLogger(__name__)

PAID_PAYMENT_STATUSES = {"PAID", "SUCCEEDED", "COMPLETED"}
CANCELLED_PAYMENT_STATUSES = {"CANCELLED", "EXPIRED", "INACTIVE", "ARCHIVED"}
PENDING_PAYMENT_STATUSES = {
    "PENDING",
    "WAITLISTED",
    "TRIAL",
    "OPEN",
    "CREATED",
    "PROCESSING",
    "WAITING_PAYMENT",
    "FAILED",
    "BOOKED",
    "ATTENDED",
    "NO_SHOW",
}
FAILED_PAYMENT_STATUSES = {"NOT_SUPPORTED", "MISSING_KEY", "MISSING_CUSTOMER_REF", "MISSING_MANDATE_REF", "NETWORK_ERROR", "UNEXPECTED_ERROR"}
ONLINE_COLLECTION_METHOD_CODES = {"CARD_ONLINE", "SEPA_DEBIT", "PAYPAL"}
COUNTRY_NAME_BY_CODE = {
    "FR": "France",
    "BE": "Belgique",
    "CH": "Suisse",
    "LU": "Luxembourg",
    "ES": "Espagne",
    "IT": "Italie",
    "GB": "Royaume-Uni",
    "UK": "Royaume-Uni",
    "US": "Etats-Unis",
    "CA": "Canada",
    "DE": "Allemagne",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _frontend_url(*, path: str) -> str:
    candidate = (settings.frontend_base_url or "").strip() or "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _checkout_urls(*, owner_id: UUID, subscription_id: UUID) -> tuple[str, str, str]:
    query = f"tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}"
    success_url = _frontend_url(path=f"/dashboard?{query}&payment_return=success")
    cancel_url = _frontend_url(path=f"/dashboard?{query}&payment_return=cancel")
    webhook_url = _frontend_url(path=f"/api/v1/public/payments/webhook?client_id={owner_id}&subscription_id={subscription_id}")
    return success_url, cancel_url, webhook_url


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_required(value: str | None, field_name: str) -> str:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be null",
        )
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} cannot be empty",
        )
    return normalized


def _validate_timezone(value: str) -> str:
    timezone_name = _normalize_required(value, "timezone")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone",
        ) from exc
    return timezone_name


def _normalize_optout_channel(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"EMAIL", "SMS", "ALL"}:
        return normalized
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid optout channel",
    )


def _member_out(user: User) -> FamilyMemberOut:
    return FamilyMemberOut(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.mobile_phone_1 or user.phone,
        mobile_phone_1=user.mobile_phone_1,
        mobile_phone_2=user.mobile_phone_2,
        home_phone=user.home_phone,
        address_line=user.address_line,
        postal_code=user.postal_code,
        city=user.city,
        address_country=user.address_country,
        client_kind=user.client_kind,
        is_active=user.is_active,
    )


def _display_name(user: User) -> str:
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return full_name or user.email


def _country_display_name(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    code = value.upper()
    if len(code) == 2:
        return COUNTRY_NAME_BY_CODE.get(code, code)
    return value[:1].upper() + value[1:].lower()


def _billing_address_label(user: User) -> str:
    line_1 = (user.address_line or "").strip()
    city_line = " ".join(part for part in [(user.postal_code or "").strip(), (user.city or "").strip()] if part).strip()
    country = _country_display_name(user.address_country or user.residence_country)
    parts = [line_1, city_line, country]
    return ", ".join(part for part in parts if part) or "-"


def _is_failed_payment_status(status_value: str) -> bool:
    normalized = (status_value or "").strip().upper()
    if not normalized:
        return False
    if normalized in FAILED_PAYMENT_STATUSES:
        return True
    if normalized.startswith("HTTP_"):
        return True
    if normalized.startswith("FAILED"):
        return True
    if normalized.endswith("_ERROR"):
        return True
    return False


def _subscription_payment_status(subscription: ClientPlanSubscription) -> str:
    subscription_status = (subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)).strip().upper()
    if subscription_status in CANCELLED_PAYMENT_STATUSES:
        return "CANCELLED"
    if subscription_status == "PENDING":
        return "PENDING"

    last_payment_status = (subscription.last_payment_status or "").strip().upper()
    if last_payment_status:
        if last_payment_status in PAID_PAYMENT_STATUSES:
            return "PAID"
        if last_payment_status in CANCELLED_PAYMENT_STATUSES:
            return "CANCELLED"
        if _is_failed_payment_status(last_payment_status):
            return "FAILED"
        if last_payment_status in PENDING_PAYMENT_STATUSES:
            return "PENDING"
        return "PENDING"

    billing_method = (subscription.billing_method_code or "").strip().upper()
    if billing_method in ONLINE_COLLECTION_METHOD_CODES:
        return "PENDING"
    if billing_method:
        return "PAID"
    return "PENDING"


def _payment_source_label(source: str) -> str:
    normalized = (source or "").strip().upper()
    if normalized == "PLAN_PURCHASE":
        return "Achat formule"
    if normalized == "BOOKING":
        return "Reservation"
    return normalized or "Paiement"


def _booking_uuid_from_payment_id(payment_id: str) -> UUID | None:
    raw_id = str(payment_id or "").split(":", maxsplit=1)[-1].strip()
    if not raw_id:
        return None
    try:
        return UUID(raw_id)
    except ValueError:
        return None


def _forfait_booking_ids(db: Session, booking_ids: list[UUID]) -> set[UUID]:
    unique_ids = list({booking_id for booking_id in booking_ids if booking_id is not None})
    if not unique_ids:
        return set()

    rows = db.execute(
        select(Booking.id)
        .select_from(Booking)
        .join(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id, isouter=True)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id, isouter=True)
        .where(
            Booking.id.in_(unique_ids),
            Plan.kind == PlanKind.FORFAIT,
        )
    ).all()
    return {row[0] for row in rows}


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
) -> Decimal:
    if not _forfait_subscription_pricing_applies(subscription, session_start_at=session_start_at):
        return base_hourly_ttc.quantize(Decimal("0.01"))

    loyalty_discount = _non_negative_money(subscription.forfait_loyalty_discount_per_hour_ttc)
    family_discount = _non_negative_money(subscription.forfait_family_discount_per_hour_ttc)
    short_commitment_supplement = _non_negative_money(subscription.forfait_short_commitment_supplement_per_hour_ttc)
    adjusted = (base_hourly_ttc - loyalty_discount - family_discount + short_commitment_supplement).quantize(Decimal("0.01"))
    if adjusted < Decimal("0.00"):
        return Decimal("0.00")
    return adjusted


def _booking_amounts_from_activity(
    *,
    booking: Booking,
    session_obj: CourseSession,
    course_type: CourseType,
    billing_profile: User,
    forfait_subscription: ClientPlanSubscription | None,
    db: Session,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str] | None:
    if course_type.default_hourly_rate is None:
        return None

    duration_seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
    if duration_seconds <= 0:
        duration_seconds = int(max(course_type.duration_minutes, 0) * 60)
    duration_hours = Decimal(duration_seconds) / Decimal("3600")
    hourly_ttc = _forfait_hourly_ttc_with_overrides(
        base_hourly_ttc=Decimal(course_type.default_hourly_rate).quantize(Decimal("0.01")),
        subscription=forfait_subscription,
        session_start_at=session_obj.start_at_utc,
    )
    total_incl_vat = (hourly_ttc * duration_hours).quantize(Decimal("0.01"))

    country_code = (billing_profile.residence_country or "FR").upper()
    vat_rate = resolve_vat_rate(
        db,
        country=country_code,
        service_code=course_type.service_code,
        on_date=session_obj.start_at_utc.date(),
    ).quantize(Decimal("0.01"))

    if vat_rate <= Decimal("0.00"):
        amount_excl_vat = total_incl_vat
        vat_amount = Decimal("0.00")
    else:
        divisor = Decimal("1.00") + (vat_rate / Decimal("100.00"))
        amount_excl_vat = (total_incl_vat / divisor).quantize(Decimal("0.01")) if divisor > Decimal("0.00") else total_incl_vat
        vat_amount = (total_incl_vat - amount_excl_vat).quantize(Decimal("0.01"))

    currency = (booking.currency_snapshot or billing_profile.preferred_currency or "EUR").upper()
    return amount_excl_vat, vat_rate, vat_amount, total_incl_vat, currency


def _managed_client_ids_for_sessions(db: Session, current_user: User) -> set[UUID]:
    managed_ids: set[UUID] = {current_user.id}
    if current_user.client_kind != ClientKind.ADULT:
        return managed_ids

    child_ids = db.scalars(
        select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == current_user.id)
    ).all()
    managed_ids.update(child_ids)
    return managed_ids


def _message_scope_since(scope: ClientMessageScope) -> datetime | None:
    now = _utcnow()
    if scope == ClientMessageScope.LAST_3_MONTHS:
        return now.replace(microsecond=0) - timedelta(days=90)
    if scope == ClientMessageScope.CURRENT_YEAR:
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)
    return None


def _format_session_datetime(session_obj: CourseSession, timezone_name: str) -> str:
    tz_name = timezone_name or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    return session_obj.start_at_utc.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def _link_out(link: ClientFamilyLink, users_by_id: dict[UUID, User]) -> FamilyLinkOut:
    adult = users_by_id.get(link.adult_user_id)
    child = users_by_id.get(link.child_user_id)
    if adult is None or child is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Family link integrity error")
    return FamilyLinkOut(
        id=link.id,
        adult=_member_out(adult),
        child=_member_out(child),
        relationship_label=link.relationship_label,
        is_billing_recipient=link.is_billing_recipient,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _plan_amount_due_and_currency(
    db: Session,
    *,
    plan: Plan,
    country: str,
    currency: str,
    on_date: datetime,
) -> tuple[Decimal, str]:
    currency_code = (plan.currency_code or currency or "EUR").upper()
    if plan.kind == PlanKind.FORFAIT:
        return Decimal("0.00"), currency_code

    vat_rate = resolve_vat_rate(
        db,
        country=country,
        service_code=plan_service_code(plan.kind.value),
        on_date=on_date.date(),
    )

    price_excl_vat: Decimal | None = None
    if plan.monthly_price_value is not None:
        raw_price = Decimal(plan.monthly_price_value)
        if plan.price_tax_mode == PlanPriceTaxMode.TTC:
            return raw_price.quantize(Decimal("0.01")), currency_code
        price_excl_vat = raw_price
    elif plan.monthly_price_excl_vat is not None:
        price_excl_vat = Decimal(plan.monthly_price_excl_vat)
    else:
        resolved_price = resolve_plan_price(
            db,
            plan_id=plan.id,
            country=country,
            currency=currency,
            on_date=on_date.date(),
        )
        if resolved_price is not None:
            price_excl_vat = Decimal(resolved_price.price_excl_vat)
            currency_code = resolved_price.currency_code

    if price_excl_vat is None:
        return Decimal("0.00"), currency_code

    _, _, total_incl_vat = compute_tax_totals(price_excl_vat=price_excl_vat, vat_rate=vat_rate)
    return total_incl_vat.quantize(Decimal("0.01")), currency_code


@router.get("/clients/me", response_model=UserOut)
def get_client_me(current_user: User = Depends(require_roles(UserRole.CLIENT))) -> UserOut:
    return current_user


@router.get("/clients/me/sessions", response_model=list[SessionOut])
def list_client_visible_sessions(
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    timezone: str = "UTC",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
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

    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    private_visible_session_ids_stmt = (
        select(Booking.session_id)
        .where(
            Booking.user_id.in_(managed_client_ids),
            Booking.status != BookingStatus.CANCELLED,
        )
        .distinct()
    )

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
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            (
                CourseSession.is_private.is_(False)
                | CourseSession.id.in_(private_visible_session_ids_stmt)
            ),
        )
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

    payload: list[SessionOut] = []
    for session, course_type, location, professor, booked_count in rows:
        booked = int(booked_count or 0)
        seats_remaining = max(session.capacity_max - booked, 0)
        payload.append(
            SessionOut(
                id=session.id,
                title=session.title,
                description=session.description,
                start_at_utc=session.start_at_utc,
                end_at_utc=session.end_at_utc,
                start_at_local=session.start_at_utc.astimezone(tz),
                end_at_local=session.end_at_utc.astimezone(tz),
                timezone=timezone,
                session_timezone=session.timezone,
                status=session.status,
                capacity_max=session.capacity_max,
                booked_count=booked,
                seats_remaining=seats_remaining,
                online_booking_enabled=(not session.is_private) and bool(session.allow_online_booking),
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

    return payload


@router.patch("/clients/me", response_model=UserOut)
def patch_client_me(
    payload: ClientMeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> UserOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return current_user

    if "first_name" in changes:
        current_user.first_name = _normalize_optional(changes["first_name"])

    if "last_name" in changes:
        current_user.last_name = _normalize_optional(changes["last_name"])

    if "address_line" in changes:
        current_user.address_line = _normalize_optional(changes["address_line"])

    if "postal_code" in changes:
        current_user.postal_code = _normalize_optional(changes["postal_code"])

    if "city" in changes:
        current_user.city = _normalize_optional(changes["city"])

    if "address_country" in changes:
        current_user.address_country = _normalize_required(changes["address_country"], "address_country").upper()

    if "phone" in changes:
        normalized_phone = _normalize_optional(changes["phone"])
        current_user.phone = normalized_phone
        if "mobile_phone_1" not in changes:
            current_user.mobile_phone_1 = normalized_phone

    if "mobile_phone_1" in changes:
        current_user.mobile_phone_1 = _normalize_optional(changes["mobile_phone_1"])
        current_user.phone = current_user.mobile_phone_1

    if "mobile_phone_2" in changes:
        current_user.mobile_phone_2 = _normalize_optional(changes["mobile_phone_2"])

    if "home_phone" in changes:
        current_user.home_phone = _normalize_optional(changes["home_phone"])

    if "important_info" in changes:
        current_user.important_info = _normalize_optional(changes["important_info"])

    if "portal_contact_visible" in changes and changes["portal_contact_visible"] is not None:
        current_user.portal_contact_visible = bool(changes["portal_contact_visible"])

    if "email_opt_in" in changes and changes["email_opt_in"] is not None:
        current_user.email_opt_in = bool(changes["email_opt_in"])

    if "sms_opt_in" in changes and changes["sms_opt_in"] is not None:
        current_user.sms_opt_in = bool(changes["sms_opt_in"])

    if "lesson_reminder_email_opt_in" in changes and changes["lesson_reminder_email_opt_in"] is not None:
        current_user.lesson_reminder_email_opt_in = bool(changes["lesson_reminder_email_opt_in"])

    if "lesson_reminder_sms_opt_in" in changes and changes["lesson_reminder_sms_opt_in"] is not None:
        current_user.lesson_reminder_sms_opt_in = bool(changes["lesson_reminder_sms_opt_in"])

    if "residence_country" in changes:
        current_user.residence_country = _normalize_required(changes["residence_country"], "residence_country").upper()

    if "preferred_currency" in changes:
        current_user.preferred_currency = _normalize_required(changes["preferred_currency"], "preferred_currency").upper()

    if "timezone" in changes:
        current_user.timezone = _validate_timezone(changes["timezone"])

    current_user.updated_at = _utcnow()

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/clients/communication/optout")
def client_communication_optout(
    token: str = Query(min_length=8, max_length=64),
    channel: str = Query(default="EMAIL"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    normalized_channel = _normalize_optout_channel(channel)
    user = db.scalar(
        select(User).where(
            User.communication_optout_token == token,
            User.role == UserRole.CLIENT,
        )
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optout token not found")

    if normalized_channel in {"EMAIL", "ALL"}:
        user.email_opt_in = False
        user.lesson_reminder_email_opt_in = False

    if normalized_channel in {"SMS", "ALL"}:
        user.sms_opt_in = False
        user.lesson_reminder_sms_opt_in = False

    user.updated_at = _utcnow()
    db.add(user)
    db.commit()

    return {
        "ok": "true",
        "message": "Preferences de communication mises a jour",
    }


@router.get("/clients/me/family", response_model=ClientFamilyOverviewOut)
def get_client_family_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientFamilyOverviewOut:
    links_as_adult = db.scalars(
        select(ClientFamilyLink)
        .where(ClientFamilyLink.adult_user_id == current_user.id)
        .order_by(ClientFamilyLink.created_at.desc())
    ).all()
    links_as_child = db.scalars(
        select(ClientFamilyLink)
        .where(ClientFamilyLink.child_user_id == current_user.id)
        .order_by(ClientFamilyLink.created_at.desc())
    ).all()

    user_ids: set[UUID] = {current_user.id}
    for link in links_as_adult:
        user_ids.add(link.adult_user_id)
        user_ids.add(link.child_user_id)
    for link in links_as_child:
        user_ids.add(link.adult_user_id)
        user_ids.add(link.child_user_id)

    users = db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    users_by_id = {user.id: user for user in users}

    managed_client_ids: set[UUID] = {current_user.id}
    if current_user.client_kind == ClientKind.ADULT:
        managed_client_ids.update(link.child_user_id for link in links_as_adult)

    rows_subscriptions = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(ClientPlanSubscription.user_id.in_(managed_client_ids))
        .order_by(ClientPlanSubscription.created_at.desc())
    ).all()
    plan_ids = list({plan.id for _, plan, _ in rows_subscriptions})
    entitlement_rows = db.execute(
        select(PlanEntitlement.plan_id, PlanEntitlement.course_type_id, CourseType.name)
        .join(CourseType, CourseType.id == PlanEntitlement.course_type_id)
        .where(PlanEntitlement.plan_id.in_(plan_ids))
        .order_by(PlanEntitlement.plan_id.asc(), CourseType.name.asc())
    ).all() if plan_ids else []
    entitlement_course_type_ids_by_plan: dict[UUID, list[UUID]] = defaultdict(list)
    entitlement_course_type_names_by_plan: dict[UUID, list[str]] = defaultdict(list)
    for plan_id, course_type_id, course_type_name in entitlement_rows:
        entitlement_course_type_ids_by_plan[plan_id].append(course_type_id)
        entitlement_course_type_names_by_plan[plan_id].append(course_type_name)

    rows_bookings = db.execute(
        select(Booking, CourseSession, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.user_id.in_(managed_client_ids))
        .order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())
    ).all()

    billing_recipient_adult_id: UUID | None = None
    for link in links_as_child:
        if link.is_billing_recipient:
            billing_recipient_adult_id = link.adult_user_id
            break

    return ClientFamilyOverviewOut(
        me=_member_out(current_user),
        links_as_adult=[_link_out(link, users_by_id) for link in links_as_adult],
        links_as_child=[_link_out(link, users_by_id) for link in links_as_child],
        billing_recipient_adult_id=billing_recipient_adult_id,
        managed_client_ids=sorted(managed_client_ids, key=lambda value: str(value)),
        subscriptions=[
            FamilySubscriptionOut(
                id=sub.id,
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                owner_email=owner.email,
                status=sub.status,
                started_at=sub.started_at,
                ends_at=sub.ends_at,
                next_payment_at=sub.next_payment_at,
                credits_initial=sub.credits_initial,
                credits_remaining=sub.credits_remaining,
                auto_renew=sub.auto_renew,
                billing_method_code=sub.billing_method_code,
                suspension_starts_at=sub.suspension_starts_at,
                suspension_ends_at=sub.suspension_ends_at,
                cancellation_requested_at=sub.cancellation_requested_at,
                cancellation_effective_at=sub.cancellation_effective_at,
                plan=FamilyPlanMiniOut(
                    id=plan.id,
                    code=plan.code,
                    name=plan.name,
                    kind=plan.kind,
                ),
                entitlement_course_type_ids=entitlement_course_type_ids_by_plan.get(plan.id, []),
                entitlement_course_type_names=entitlement_course_type_names_by_plan.get(plan.id, []),
            )
            for sub, plan, owner in rows_subscriptions
        ],
        bookings=[
            FamilyBookingOut(
                id=booking.id,
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                owner_email=owner.email,
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
                session=FamilySessionMiniOut(
                    id=session.id,
                    title=session.title,
                    start_at_utc=session.start_at_utc,
                    end_at_utc=session.end_at_utc,
                    status=session.status,
                ),
            )
            for booking, session, owner in rows_bookings
        ],
    )


@router.get("/clients/me/messages", response_model=list[ClientMessageOut])
def list_client_messages(
    scope: ClientMessageScope = Query(default=ClientMessageScope.LAST_3_MONTHS),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientMessageOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    owners = db.scalars(select(User).where(User.id.in_(managed_client_ids))).all()
    owners_by_id = {owner.id: owner for owner in owners}
    since = _message_scope_since(scope)

    stmt = (
        select(EmailReminder, Booking, CourseSession, CourseType, User)
        .join(Booking, Booking.id == EmailReminder.booking_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.user_id.in_(managed_client_ids))
        .order_by(EmailReminder.created_at.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(EmailReminder.created_at >= since)

    rows = db.execute(stmt).all()
    payload: list[ClientMessageOut] = []

    for reminder, booking, session_obj, course_type, owner in rows:
        owner_display = _display_name(owners_by_id.get(owner.id, owner))
        start_human = _format_session_datetime(session_obj, owner.timezone)
        subject_preview = f"Rappel cours: {course_type.name} - {start_human}"
        payload.append(
            ClientMessageOut(
                id=reminder.id,
                owner_client_id=owner.id,
                owner_display_name=owner_display,
                channel="EMAIL",
                booking_id=booking.id,
                session_id=session_obj.id,
                session_title=session_obj.title,
                scheduled_for_utc=reminder.scheduled_for_utc,
                sent_at=reminder.sent_at,
                status=reminder.status,
                provider_message_id=reminder.provider_message_id,
                error_message=reminder.error_message,
                subject_preview=subject_preview,
            )
        )

    return payload


def _build_client_payments(db: Session, current_user: User) -> list[ClientPaymentOut]:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)

    rows_subs = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(ClientPlanSubscription.user_id.in_(managed_client_ids))
    ).all()

    rows_bookings = db.execute(
        select(Booking, CourseSession, CourseType, Location, User, ClientPlanSubscription, Plan)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(ClientPlanSubscription, ClientPlanSubscription.id == Booking.client_plan_subscription_id)
        .outerjoin(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == Booking.user_id)
        .where(Booking.user_id.in_(managed_client_ids))
    ).all()

    items: list[ClientPaymentOut] = []

    for sub, plan, owner in rows_subs:
        if plan.kind == PlanKind.FORFAIT:
            continue

        billing_profile = resolve_billing_profile(db, owner)
        country_code = (billing_profile.residence_country or "FR").upper()
        preferred_currency = (billing_profile.preferred_currency or "EUR").upper()

        vat_rate = resolve_vat_rate(
            db,
            country=country_code,
            service_code=plan_service_code(plan.kind.value),
            on_date=sub.started_at.date(),
        )

        price_excl_vat: Decimal | None = None
        currency_code = (plan.currency_code or preferred_currency).upper()
        if plan.monthly_price_value is not None:
            raw_price = Decimal(plan.monthly_price_value)
            if plan.price_tax_mode == PlanPriceTaxMode.TTC:
                divisor = Decimal("1") + (vat_rate / Decimal("100"))
                price_excl_vat = raw_price if divisor <= 0 else (raw_price / divisor)
            else:
                price_excl_vat = raw_price
        elif plan.monthly_price_excl_vat is not None:
            price_excl_vat = Decimal(plan.monthly_price_excl_vat)
        else:
            resolved_price = resolve_plan_price(
                db,
                plan_id=plan.id,
                country=country_code,
                currency=preferred_currency,
                on_date=sub.started_at.date(),
            )
            if resolved_price is not None:
                price_excl_vat = Decimal(resolved_price.price_excl_vat)
                currency_code = resolved_price.currency_code

        if price_excl_vat is not None:
            price_excl_vat, vat_amount, total_incl_vat = compute_tax_totals(
                price_excl_vat=price_excl_vat,
                vat_rate=vat_rate,
            )
        else:
            price_excl_vat = Decimal("0.00")
            vat_amount = Decimal("0.00")
            total_incl_vat = Decimal("0.00")

        items.append(
            ClientPaymentOut(
                id=f"plan:{sub.id}",
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                source="PLAN_PURCHASE",
                occurred_at=sub.started_at,
                label=plan.name,
                status=_subscription_payment_status(sub),
                amount_excl_vat=price_excl_vat,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
                total_incl_vat=total_incl_vat,
                currency=currency_code or "EUR",
                reference=plan.code,
                payment_url=_frontend_url(path=f"/dashboard?tab=transactions&source=PLAN_PURCHASE&payment_id={sub.id}"),
            )
        )

    for booking, session_obj, course_type, location, owner, forfait_subscription, plan in rows_bookings:
        status_value = booking.status.value if hasattr(booking.status, "value") else str(booking.status)
        is_billable = True
        amount_excl_vat = booking.price_excl_vat_snapshot
        vat_rate = booking.vat_rate_snapshot
        vat_amount = booking.vat_amount_snapshot
        total_incl_vat = booking.total_incl_vat_snapshot
        currency = booking.currency_snapshot

        if plan is None or (plan is not None and plan.kind == PlanKind.FORFAIT):
            is_billable = (
                session_obj.status != SessionStatus.CANCELLED
                and booking.status not in {BookingStatus.WAITLISTED, BookingStatus.CANCELLED, BookingStatus.EXCUSED_ABSENCE}
            )
            if not is_billable:
                status_value = "NOT_BILLABLE"
            else:
                billing_profile = resolve_billing_profile(db, owner)
                computed = _booking_amounts_from_activity(
                    booking=booking,
                    session_obj=session_obj,
                    course_type=course_type,
                    billing_profile=billing_profile,
                    forfait_subscription=forfait_subscription,
                    db=db,
                )
                if computed is not None:
                    amount_excl_vat, vat_rate, vat_amount, total_incl_vat, currency = computed
        elif booking.status == BookingStatus.EXCUSED_ABSENCE:
            is_billable = False
        items.append(
            ClientPaymentOut(
                id=f"booking:{booking.id}",
                owner_client_id=owner.id,
                owner_display_name=_display_name(owner),
                source="BOOKING",
                occurred_at=booking.booked_at,
                label=f"{course_type.name} - {location.name}",
                status=status_value,
                amount_excl_vat=Decimal("0.00") if not is_billable else amount_excl_vat,
                vat_rate=Decimal("0.00") if not is_billable else vat_rate,
                vat_amount=Decimal("0.00") if not is_billable else vat_amount,
                total_incl_vat=Decimal("0.00") if not is_billable else total_incl_vat,
                currency=currency,
                reference=str(session_obj.id),
                payment_url=None,
            )
        )

    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return items


@router.post("/clients/me/payments/{payment_id}/checkout", response_model=ClientPaymentCheckoutOut)
def create_client_payment_checkout(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientPaymentCheckoutOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    row = db.execute(
        select(ClientPlanSubscription, Plan, User)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .join(User, User.id == ClientPlanSubscription.user_id)
        .where(
            ClientPlanSubscription.id == payment_id,
            ClientPlanSubscription.user_id.in_(managed_ids),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")

    subscription, plan, owner = row
    normalized_status = (subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)).strip().upper()
    if normalized_status in {"CANCELLED", "EXPIRED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce paiement est clos")

    method_code = (subscription.billing_method_code or "").strip().upper()
    if method_code not in ONLINE_COLLECTION_METHOD_CODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ce paiement n'utilise pas un moyen en ligne")

    amount_due, currency_code = _plan_amount_due_and_currency(
        db,
        plan=plan,
        country=(owner.residence_country or "FR").upper(),
        currency=(owner.preferred_currency or "EUR").upper(),
        on_date=subscription.started_at,
    )
    if amount_due <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun montant a regler pour ce paiement")

    success_url, cancel_url, webhook_url = _checkout_urls(owner_id=owner.id, subscription_id=subscription.id)
    checkout = create_checkout_session(
        db,
        CheckoutCreateRequest(
            amount=amount_due,
            currency=currency_code,
            description=f"{plan.name} ({owner.email})",
            customer_email=owner.email,
            success_return_url=success_url,
            cancel_return_url=cancel_url,
            webhook_url=with_webhook_secret(webhook_url, settings.payment_webhook_secret),
            metadata={
                "client_id": str(owner.id),
                "subscription_id": str(subscription.id),
                "plan_id": str(plan.id),
                "plan_code": plan.code,
            },
        ),
    )
    if not checkout.success or not checkout.checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Impossible de creer la session de paiement ({checkout.message})",
        )

    subscription.payment_provider_subscription_ref = checkout.provider_reference or subscription.payment_provider_subscription_ref
    subscription.last_payment_status = (checkout.status or "WAITING_PAYMENT").strip().upper() or "WAITING_PAYMENT"
    if subscription.status != SubscriptionStatus.ACTIVE:
        subscription.status = SubscriptionStatus.PENDING
        subscription.auto_renew = False
    db.add(subscription)
    db.commit()

    return ClientPaymentCheckoutOut(
        payment_id=f"plan:{subscription.id}",
        checkout_url=checkout.checkout_url,
        provider_reference=subscription.payment_provider_subscription_ref,
    )


@router.post("/clients/me/payments/{payment_id}/confirm", response_model=ClientPaymentConfirmOut)
def confirm_client_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> ClientPaymentConfirmOut:
    managed_ids = _managed_client_ids_for_sessions(db, current_user)
    row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.id == payment_id,
            ClientPlanSubscription.user_id.in_(managed_ids),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement introuvable")

    subscription, plan = row
    was_paid_before = subscription.last_payment_at is not None
    payment_reference = (subscription.payment_provider_subscription_ref or "").strip()
    if not payment_reference:
        return ClientPaymentConfirmOut(
            payment_id=f"plan:{subscription.id}",
            subscription_status=(subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)),
            last_payment_status=subscription.last_payment_status,
            paid=False,
            cancelled=False,
            failed=False,
            processed=False,
            message="Reference PSP absente",
        )

    provider = resolve_provider(db)
    lookup = lookup_payment(db, provider=provider, payment_reference=payment_reference)
    status_text = (lookup.status or "").strip().upper() or "UNKNOWN"

    changed = False
    if (subscription.last_payment_status or "") != status_text:
        subscription.last_payment_status = status_text
        changed = True

    mandate_missing_for_recurring = False
    if lookup.paid:
        customer_reference = (lookup.metadata.get("customer_reference") or "").strip()
        mandate_reference = (lookup.metadata.get("mandate_reference") or "").strip()
        if customer_reference and subscription.payment_provider_customer_ref != customer_reference:
            subscription.payment_provider_customer_ref = customer_reference
            changed = True
        if mandate_reference and subscription.payment_provider_mandate_ref != mandate_reference:
            subscription.payment_provider_mandate_ref = mandate_reference
            changed = True
        if subscription.last_payment_at is None:
            subscription.last_payment_at = _utcnow()
            changed = True
        if subscription.status in {SubscriptionStatus.PENDING, SubscriptionStatus.PAUSED, SubscriptionStatus.ACTIVE}:
            if subscription.status != SubscriptionStatus.ACTIVE:
                subscription.status = SubscriptionStatus.ACTIVE
                changed = True
        if plan.kind == PlanKind.SUBSCRIPTION:
            billing_method_code = (subscription.billing_method_code or "").strip().upper()
            has_customer_ref = bool((subscription.payment_provider_customer_ref or "").strip())
            has_mandate_ref = bool((subscription.payment_provider_mandate_ref or "").strip())
            requires_stored_card = billing_method_code == "CARD_ONLINE"
            mandate_missing_for_recurring = requires_stored_card and (not has_customer_ref or not has_mandate_ref)
            if mandate_missing_for_recurring:
                if subscription.auto_renew:
                    subscription.auto_renew = False
                    changed = True
                if (subscription.last_payment_status or "") != "PAID_MANDATE_MISSING":
                    subscription.last_payment_status = "PAID_MANDATE_MISSING"
                    changed = True
            elif not subscription.auto_renew:
                subscription.auto_renew = True
                changed = True
    elif lookup.cancelled:
        if subscription.status == SubscriptionStatus.PENDING:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.auto_renew = False
            subscription.next_payment_at = None
            changed = True

    if changed:
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
    else:
        db.rollback()

    if lookup.paid and not was_paid_before:
        owner = db.scalar(select(User).where(User.id == subscription.user_id))
        if owner is not None and owner.email:
            try:
                amount_due, currency_code = _plan_amount_due_and_currency(
                    db,
                    plan=plan,
                    country=(owner.residence_country or "FR").upper(),
                    currency=(owner.preferred_currency or "EUR").upper(),
                    on_date=subscription.started_at,
                )
                send_client_payment_success_notifications(
                    db,
                    to_email=owner.email,
                    first_name=owner.first_name,
                    last_name=owner.last_name,
                    plan_name=plan.name,
                    subscription_id=subscription.id,
                    paid_at=subscription.last_payment_at or _utcnow(),
                    amount_paid=amount_due,
                    currency=currency_code,
                )
            except Exception:
                logger.exception("Unable to send paid confirmation emails for subscription=%s", subscription.id)

    return ClientPaymentConfirmOut(
        payment_id=f"plan:{subscription.id}",
        subscription_status=(subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status)),
        last_payment_status=subscription.last_payment_status,
        paid=lookup.paid,
        cancelled=lookup.cancelled,
        failed=lookup.failed,
        processed=lookup.success,
        message=(
            "Paiement confirme mais mandat de prelevement recurrent introuvable. L auto-renouvellement est desactive."
            if mandate_missing_for_recurring
            else lookup.message
        ),
    )


@router.get("/clients/me/payments", response_model=list[ClientPaymentOut])
def list_client_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientPaymentOut]:
    return _build_client_payments(db, current_user)


@router.get("/clients/me/invoices", response_model=list[ClientInvoiceOut])
def list_client_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[ClientInvoiceOut]:
    payments = _build_client_payments(db, current_user)
    booking_payment_ids = [
        booking_id
        for payment in payments
        for booking_id in (_booking_uuid_from_payment_id(payment.id),)
        if (payment.source or "").strip().upper() == "BOOKING" and booking_id is not None
    ]
    forfait_bookings = _forfait_booking_ids(db, booking_payment_ids)
    invoices: list[ClientInvoiceOut] = []

    for payment in payments:
        if (payment.source or "").strip().upper() == "BOOKING":
            booking_id = _booking_uuid_from_payment_id(payment.id)
            if booking_id is not None and booking_id in forfait_bookings:
                continue

        normalized_status = (payment.status or "").upper()
        if normalized_status in PAID_PAYMENT_STATUSES:
            invoice_status = "PAID"
        elif normalized_status in CANCELLED_PAYMENT_STATUSES:
            invoice_status = "CANCELLED"
        else:
            invoice_status = "PENDING"

        raw_id = payment.id.split(":", maxsplit=1)[-1]
        compact = raw_id.replace("-", "").upper()
        short = compact[:8] if compact else "XXXX0000"
        number = f"FAC-{payment.occurred_at.strftime('%Y%m%d')}-{short}"

        invoices.append(
            ClientInvoiceOut(
                id=f"invoice:{payment.id}",
                owner_client_id=payment.owner_client_id,
                owner_display_name=payment.owner_display_name,
                invoice_number=number,
                issued_at=payment.occurred_at,
                source=payment.source,
                status=invoice_status,
                label=payment.label,
                total_incl_vat=payment.total_incl_vat,
                currency=payment.currency,
                reference=payment.reference,
                download_url=f"/dashboard/invoices/{payment.id}/download",
            )
        )

    return invoices


@router.get("/clients/me/invoices/{invoice_id}/download")
def download_client_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    managed_client_ids = _managed_client_ids_for_sessions(db, current_user)
    invoice_ref = invoice_id.strip()
    if invoice_ref.startswith("invoice:"):
        invoice_ref = invoice_ref[len("invoice:") :]
    invoice_ref = invoice_ref.strip()
    if not invoice_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    payments = _build_client_payments(db, current_user)
    payment = next((row for row in payments if row.id == invoice_ref), None)
    if payment is None and ":" not in invoice_ref:
        payment = next((row for row in payments if row.id in {f"plan:{invoice_ref}", f"booking:{invoice_ref}"}), None)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if (payment.source or "").strip().upper() == "BOOKING":
        booking_id = _booking_uuid_from_payment_id(payment.id)
        if booking_id is not None and booking_id in _forfait_booking_ids(db, [booking_id]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Forfait booking invoices are generated manually from back office.",
            )
    if payment.owner_client_id not in managed_client_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    payment_user = db.scalar(select(User).where(User.id == payment.owner_client_id))
    if payment_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    raw_id = payment.id.split(":", maxsplit=1)[-1]
    compact = raw_id.replace("-", "").upper()
    short = compact[:8] if compact else "XXXX0000"
    invoice_number = f"FAC-{payment.occurred_at.strftime('%Y%m%d')}-{short}"
    billing_profile = resolve_billing_profile(db, payment_user)
    line = InvoicePeriodLine(
        date_label=payment.occurred_at.strftime("%d/%m/%Y"),
        type_label=_payment_source_label(payment.source),
        label=payment.label,
        quantity=1,
        amount_excl_vat=payment.amount_excl_vat,
        vat_rate=payment.vat_rate,
        vat_amount=payment.vat_amount,
        total_incl_vat=payment.total_incl_vat,
        currency=payment.currency,
    )
    currency_code = (payment.currency or "EUR").upper()
    totals = {
        currency_code: {
            "amount_excl_vat": payment.amount_excl_vat,
            "vat_amount": payment.vat_amount,
            "total_incl_vat": payment.total_incl_vat,
        }
    }
    content = render_invoice_period_pdf(
        db,
        invoice_number=invoice_number,
        issued_at=payment.occurred_at,
        client_id=str(payment.owner_client_id),
        client_name=_display_name(billing_profile),
        period_label=payment.occurred_at.strftime("%d/%m/%Y"),
        lines=[line],
        totals_by_currency=totals,
        note=f"Reference: {payment.reference or '-'}",
        client_billing_address=_billing_address_label(billing_profile),
        due_date=payment.occurred_at.date(),
    )

    file_name = f"{invoice_number}.pdf".replace('"', "")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Cache-Control": "no-store",
        },
    )
