"""Explicit, atomic replacement of a signalled absence. Never a second paid lesson."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select, or_, and_

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, DeliveryMode, LessonFormat, Location, SessionStatus, BOOKING_STATUSES_CONSUMING_CAPACITY
from app.models.makeup import MakeupRequest, MakeupRequestStatus, MakeupPassPurchase
from app.models.plan import ClientPlanSubscription, Plan, SubscriptionStatus
from app.models.product_catalog import CatalogProduct
from app.models.user import User
from app.services.makeup_passes import _normalized, is_restricted_annual_forfait
from app.services.makeup_accounting import KEY, mark_original
from app.services.client_pricing import compute_fixed_price, PricingChannel, PriceUnit, booking_snapshot_fields


def fail(message):
    raise HTTPException(409, message)


def preview_version(request, original, subscription, product, target):
    payload = {"request": request.id, "student": request.user_id, "original": original.id,
        "original_status": original.status, "price": original.total_incl_vat_snapshot,
        "currency": original.currency_snapshot, "pass": product.id, "conditions": product.title,
        "valid_until": subscription.ends_at, "session": target.id, "activity": target.course_type_id,
        "location": target.location_id, "start": target.start_at_utc, "end": target.end_at_utc, "title": target.title}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_request(db, request_id, student_id, *, lock=False):
    query = select(MakeupRequest).where(MakeupRequest.id == request_id, MakeupRequest.user_id == student_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    request = db.scalar(query)
    if request is None:
        raise HTTPException(404, "Rattrapage introuvable pour cet élève.")
    return request


def validate_request(db, request, *, now):
    if request.status != MakeupRequestStatus.PROPOSED or request.reserved_booking_id is not None:
        fail("Ce rattrapage n'est plus disponible. Actualisez la fiche élève.")
    original = db.get(Booking, request.original_booking_id)
    subscription = db.get(ClientPlanSubscription, request.forfait_subscription_id)
    purchase = db.get(MakeupPassPurchase, request.used_pass_purchase_id) if request.used_pass_purchase_id else None
    if not original or original.user_id != request.user_id or original.status not in (BookingStatus.CANCELLED, BookingStatus.EXCUSED_ABSENCE):
        fail("L'absence d'origine doit être signalée avant de programmer son rattrapage.")
    if original.client_plan_subscription_id != request.forfait_subscription_id or not original.makeup_credit_consumed:
        fail("Le lien entre cette absence, son forfait et le crédit consommé doit être vérifié.")
    if not purchase or purchase.user_id != request.user_id or purchase.forfait_subscription_id != request.forfait_subscription_id:
        fail("Aucun Pass Récup valide n'est associé à cette absence.")
    plan = db.get(Plan, subscription.plan_id) if subscription else None
    if not subscription or subscription.user_id != request.user_id or not plan or not is_restricted_annual_forfait(plan):
        fail("Le forfait annuel associé au pass est introuvable.")
    if subscription.status != SubscriptionStatus.ACTIVE or subscription.started_at > now or (subscription.ends_at and subscription.ends_at <= now):
        fail("Le forfait et le Pass Récup doivent être en cours de validité.")
    if subscription.ends_at is None:
        fail("La fin de validité du forfait doit être renseignée avant de programmer ce rattrapage.")
    if original.student_start_at_utc or original.student_end_at_utc:
        fail("Ce cours utilise des horaires individuels : vérifiez sa durée avant de programmer le rattrapage.")
    product = db.get(CatalogProduct, purchase.product_id)
    # Match the existing documented standard/Online products, not an arbitrary product.
    if not product or not product.is_makeup_pass or "pass recup" not in _normalized(product.title):
        fail("Les conditions de ce pass doivent être vérifiées avant programmation.")
    return original, subscription, product


def compatible_activity(source, target, product):
    title = _normalized(product.title)
    online_only = "online" in title or "en ligne" in title
    if online_only and target.mode != DeliveryMode.ONLINE:
        return False
    if source.lesson_format != LessonFormat.GROUP or target.lesson_format != LessonFormat.GROUP:
        return False
    if any(word in _normalized(target.name).split() for word in ("essai", "trial", "vacances")):
        return False
    if target.id == source.id:
        return True
    # Another activity must explicitly share the pedagogical credit, not merely a price.
    return (target.mode == DeliveryMode.ONLINE and source.credit_type_id is not None
            and target.credit_type_id == source.credit_type_id and target.service_code == source.service_code)


def validate_target(db, request, target, *, now, exclude_booking_id=None):
    from app.api.routes.bookings import _participant_capacity_block_reason, _effective_session_booking_rules
    original, subscription, product = validate_request(db, request, now=now)
    source_session = db.get(CourseSession, original.session_id)
    source_type = db.get(CourseType, source_session.course_type_id)
    target_type = db.get(CourseType, target.course_type_id)
    student = db.get(User, request.user_id)
    if not target_type or not target_type.active or not target_type.allows_student_bookings or not compatible_activity(source_type, target_type, product) or original.is_trial_course:
        fail("Cette activité n'est pas compatible avec le cours manqué et les conditions du pass.")
    if target.id == original.session_id or target.status != SessionStatus.SCHEDULED or target.start_at_utc <= now:
        fail("Choisissez un autre créneau futur et planifié.")
    if target.end_at_utc - target.start_at_utc != source_session.end_at_utc - source_session.start_at_utc:
        fail("Le rattrapage doit conserver la durée du cours manqué.")
    if target.start_at_utc < subscription.started_at or not subscription.ends_at or target.end_at_utc > subscription.ends_at:
        fail("Ce créneau est hors de la période de validité du forfait et du pass.")
    notice, _, _ = _effective_session_booking_rules(db, session_obj=target)
    if target.start_at_utc < now + timedelta(hours=notice):
        fail("Le délai de réservation de ce créneau est dépassé.")
    if _participant_capacity_block_reason(db, session_obj=target, client_kind=student.client_kind, exclude_booking_id=exclude_booking_id):
        fail("Ce créneau est complet ou n'est pas ouvert au public de cet élève.")
    existing_query = select(Booking.id).where(Booking.user_id == request.user_id, Booking.session_id == target.id)
    if exclude_booking_id:
        existing_query = existing_query.where(Booking.id != exclude_booking_id)
    existing = db.scalar(existing_query)
    if existing:
        fail("Une inscription existe déjà pour cet élève sur ce créneau.")
    conflicts = select(Booking.id).join(CourseSession, Booking.session_id == CourseSession.id).where(
        Booking.user_id == request.user_id, Booking.status.in_(BOOKING_STATUSES_CONSUMING_CAPACITY),
        CourseSession.status != SessionStatus.CANCELLED,
        CourseSession.start_at_utc < target.end_at_utc, CourseSession.end_at_utc > target.start_at_utc,
    )
    if exclude_booking_id:
        conflicts = conflicts.where(Booking.id != exclude_booking_id)
    if db.scalar(conflicts.limit(1)):
        fail("L'élève a déjà un cours sur cet horaire.")
    return original, subscription, product


def check_accounting(db, original):
    from app.api.routes.admin_clients import _active_invoice_lock_by_payment_key
    from app.services.family_billing import resolve_billing_profile
    student = db.get(User, original.user_id)
    payer = resolve_billing_profile(db, student)
    payer_id = getattr(payer, "id", student.id)
    locks = _active_invoice_lock_by_payment_key(db, client_id=payer_id)
    if payer_id != student.id:
        locks.update(_active_invoice_lock_by_payment_key(db, client_id=student.id))
    if f"BOOKING_CREDIT:{original.id}" in locks:
        fail("Un avoir a déjà été émis pour cette absence. Une vérification comptable est nécessaire ; aucune facture n'a été modifiée.")


def makeup_price(original, request, *, now):
    return compute_fixed_price(channel=PricingChannel.MANUAL_CREDIT, amount_ttc=Decimal("0.00"),
        unit=PriceUnit.PER_SESSION, duration_hours=Decimal("1"), vat_rate=Decimal("0.00"),
        currency=original.currency_snapshot, source=f"makeup:{request.id}:original:{original.id}",
        version="makeup-v1", calculated_at=now)


def makeup_snapshot(original, request, *, now):
    fields = booking_snapshot_fields(makeup_price(original, request, now=now))
    fields["pricing_breakdown_snapshot"] = {**fields["pricing_breakdown_snapshot"], KEY: {
        "role": "replacement", "request_id": str(request.id), "original_booking_id": str(original.id),
    }}
    fields["pricing_snapshot_locked"] = True
    return fields


def attach_replacement(db, request, booking, *, now):
    target = db.get(CourseSession, booking.session_id)
    original, _, _ = validate_target(db, request, target, now=now, exclude_booking_id=booking.id)
    check_accounting(db, original)
    for key, value in makeup_snapshot(original, request, now=now).items():
        setattr(booking, key, value)
    mark_original(original, request)


def release_replacement(db, booking, *, now):
    from app.services.makeup_accounting import makeup_role
    if makeup_role(booking) != "replacement":
        return None
    request = db.scalar(select(MakeupRequest).where(MakeupRequest.reserved_booking_id == booking.id).with_for_update())
    if request and request.status == MakeupRequestStatus.BOOKED:
        request.status = MakeupRequestStatus.PROPOSED
        request.reserved_booking_id = None
        request.booked_at = None
        request.updated_at = now
    return request


def options(db, request, *, now, start, end):
    original, subscription, product = validate_request(db, request, now=now)
    check_accounting(db, original)
    source_session = db.get(CourseSession, original.session_id)
    source_type = db.get(CourseType, source_session.course_type_id)
    activity_filter = CourseType.id == source_type.id
    if source_type.credit_type_id:
        activity_filter = or_(activity_filter, and_(CourseType.mode == DeliveryMode.ONLINE,
            CourseType.credit_type_id == source_type.credit_type_id, CourseType.service_code == source_type.service_code))
    candidates = db.scalars(select(CourseSession).join(CourseType, CourseSession.course_type_id == CourseType.id).where(
        activity_filter, CourseType.active.is_(True), CourseSession.status == SessionStatus.SCHEDULED,
        CourseSession.start_at_utc >= max(now, start), CourseSession.start_at_utc < end,
        CourseSession.end_at_utc <= subscription.ends_at).order_by(CourseSession.start_at_utc, CourseSession.id)).all()
    result = []
    for target in candidates:
        try:
            validate_target(db, request, target, now=now)
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            continue
        location = db.get(Location, target.location_id)
        result.append({"id": target.id, "title": target.title, "start": target.start_at_utc,
            "end": target.end_at_utc, "location": location.name, "timezone": target.timezone,
            "version": preview_version(request, original, subscription, product, target)})
    return {"options": result, "pass": product.title, "ends_at": subscription.ends_at,
            "additional_amount": "0.00", "currency": original.currency_snapshot}


def program(db, *, request_id, student_id, target_id, actor_id, expected_version=None, now=None):
    from app.services.reminders import ensure_booking_reminder
    now = now or datetime.now(timezone.utc)
    # Lock capacity and entitlement before rechecking: a stale preview grants nothing.
    db.scalar(select(User).where(User.id == student_id).with_for_update())
    target = db.scalar(select(CourseSession).where(CourseSession.id == target_id).with_for_update().execution_options(populate_existing=True))
    if not target:
        raise HTTPException(404, "Créneau introuvable.")
    request = load_request(db, request_id, student_id)
    db.scalar(select(Booking).where(Booking.id == request.original_booking_id).with_for_update().execution_options(populate_existing=True))
    db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == request.forfait_subscription_id).with_for_update())
    request = load_request(db, request_id, student_id, lock=True)
    if request.status == MakeupRequestStatus.BOOKED and request.reserved_booking_id:
        existing = db.get(Booking, request.reserved_booking_id)
        if existing and existing.session_id == target_id and existing.status in BOOKING_STATUSES_CONSUMING_CAPACITY:
            if expected_version is None or (existing.pricing_breakdown_snapshot or {}).get("confirmed_version") == expected_version:
                return existing  # Safe retry after a lost response; never a second booking.
        fail("Ce rattrapage est déjà programmé. Actualisez la fiche élève.")
    original, subscription, product = validate_target(db, request, target, now=now)
    current_version = preview_version(request, original, subscription, product, target)
    if expected_version is not None and current_version != expected_version:
        fail("Le créneau ou les conditions ont changé depuis l'aperçu. Relancez la recherche avant de confirmer.")
    check_accounting(db, original)
    booking = Booking(session_id=target.id, user_id=student_id, client_plan_subscription_id=subscription.id,
        status=BookingStatus.BOOKED, booked_at=now, makeup_request_id=request.id,
        **makeup_snapshot(original, request, now=now))
    db.add(booking); db.flush()
    mark_original(original, request)
    booking.pricing_breakdown_snapshot = {**booking.pricing_breakdown_snapshot,
        "programmed_by": str(actor_id), "programmed_at": now.isoformat(), "confirmed_version": current_version}
    request.reserved_booking_id = booking.id
    request.status = MakeupRequestStatus.BOOKED
    request.booked_at = request.updated_at = now
    ensure_booking_reminder(db, booking=booking, session_obj=target, now=now)
    return booking
