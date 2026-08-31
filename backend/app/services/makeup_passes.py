from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, CourseSession, Location
from app.models.makeup import MakeupPassPurchase, MakeupRequest, MakeupRequestStatus
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.user import ClientKind, User
from app.services.makeup_accounting import mark_original, clear_original, makeup_role

RESTRICTED_FORFAIT_NAME = "annee 2026 2027"


def _normalized(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()


def is_restricted_annual_forfait(plan: Plan) -> bool:
    return plan.kind == PlanKind.FORFAIT and _normalized(plan.name) == RESTRICTED_FORFAIT_NAME


def pending_makeup_request_for_subscription(
    db: Session,
    *,
    user_id: UUID,
    subscription_id: UUID,
    lock: bool = False,
) -> MakeupRequest | None:
    query = (
        select(MakeupRequest)
        .where(
            MakeupRequest.user_id == user_id,
            MakeupRequest.forfait_subscription_id == subscription_id,
            MakeupRequest.status == MakeupRequestStatus.PROPOSED,
            MakeupRequest.reserved_booking_id.is_(None),
        )
        .order_by(MakeupRequest.proposed_at.asc(), MakeupRequest.created_at.asc(), MakeupRequest.id.asc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def claim_pending_makeup_request(
    db: Session,
    *,
    booking: Booking,
    subscription: ClientPlanSubscription,
    now: datetime,
) -> MakeupRequest:
    request = pending_makeup_request_for_subscription(
        db,
        user_id=booking.user_id,
        subscription_id=subscription.id,
        lock=True,
    )
    if request is None:
        raise ValueError("MAKEUP_REQUEST_REQUIRED")
    from app.services.makeup_booking import attach_replacement
    attach_replacement(db, request, booking, now=now)
    request.reserved_booking_id = booking.id
    request.status = MakeupRequestStatus.BOOKED
    request.booked_at = now
    request.updated_at = now
    booking.makeup_request_id = request.id
    db.add(request)
    return request


def active_restricted_forfait_for_booking(
    db: Session,
    *,
    booking: Booking,
    now: datetime,
    lock: bool = False,
) -> ClientPlanSubscription | None:
    owner = db.scalar(select(User).where(User.id == booking.user_id))
    if owner is None or owner.client_kind != ClientKind.CHILD:
        return None

    query = (
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id == booking.user_id,
            ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPlanSubscription.started_at <= now,
            (ClientPlanSubscription.ends_at.is_(None) | (ClientPlanSubscription.ends_at >= now)),
            Plan.kind == PlanKind.FORFAIT,
        )
        .order_by(
            (ClientPlanSubscription.id == booking.client_plan_subscription_id).desc(),
            ClientPlanSubscription.created_at.desc(),
        )
    )
    if lock:
        query = query.with_for_update(of=ClientPlanSubscription)
    for subscription, plan in db.execute(query).all():
        if is_restricted_annual_forfait(plan):
            return subscription
    return None


def consume_pass_and_create_makeup(
    db: Session,
    *,
    booking: Booking,
    subscription: ClientPlanSubscription,
    actor_user_id: UUID,
    now: datetime,
) -> MakeupRequest:
    if makeup_role(booking) == "replacement":
        from app.services.makeup_booking import release_replacement
        request = release_replacement(db, booking, now=now)
        if request is None:
            raise ValueError("MAKEUP_REQUEST_REQUIRED")
        return request
    purchase = db.scalar(
        select(MakeupPassPurchase)
        .where(
            MakeupPassPurchase.user_id == booking.user_id,
            MakeupPassPurchase.forfait_subscription_id == subscription.id,
            MakeupPassPurchase.credits_remaining > 0,
        )
        .order_by(MakeupPassPurchase.created_at.asc(), MakeupPassPurchase.id.asc())
        .with_for_update()
        .limit(1)
    )
    if purchase is None:
        raise ValueError("MAKEUP_PASS_REQUIRED")

    purchase.credits_remaining -= 1
    purchase.updated_at = now
    request = MakeupRequest(
        user_id=booking.user_id,
        original_booking_id=booking.id,
        forfait_subscription_id=subscription.id,
        used_pass_purchase_id=purchase.id,
        created_by_user_id=actor_user_id,
        status=MakeupRequestStatus.PROPOSED,
        proposed_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add_all([purchase, request])
    db.flush()
    booking.makeup_request_id = request.id
    booking.makeup_credit_consumed = True
    mark_original(booking, request)
    return request


def grant_makeup_for_excused_absence(
    db: Session,
    *,
    booking: Booking,
    actor_user_id: UUID,
    now: datetime,
) -> bool:
    if makeup_role(booking) == "replacement":
        from app.services.makeup_booking import release_replacement
        return release_replacement(db, booking, now=now) is not None
    existing_request = db.scalar(
        select(MakeupRequest.id).where(MakeupRequest.original_booking_id == booking.id).limit(1)
    )
    if existing_request is not None:
        return False
    subscription = active_restricted_forfait_for_booking(db, booking=booking, now=now, lock=True)
    if subscription is None:
        return False
    try:
        consume_pass_and_create_makeup(
            db,
            booking=booking,
            subscription=subscription,
            actor_user_id=actor_user_id,
            now=now,
        )
    except ValueError as exc:
        if str(exc) == "MAKEUP_PASS_REQUIRED":
            return False
        raise
    return True


def revoke_pending_makeup_for_corrected_absence(
    db: Session,
    *,
    booking: Booking,
    now: datetime,
) -> bool:
    from fastapi import HTTPException
    request = db.scalar(
        select(MakeupRequest)
        .where(
            MakeupRequest.original_booking_id == booking.id,
        )
        .with_for_update()
        .limit(1)
    )
    if request is None:
        return False
    if request.status == MakeupRequestStatus.BOOKED:
        raise HTTPException(409, "Un rattrapage est déjà réservé pour cette absence. Annulez d'abord le rattrapage avant de corriger la présence.")
    if request.status != MakeupRequestStatus.PROPOSED:
        return False
    purchase = None
    if request.used_pass_purchase_id is not None:
        purchase = db.scalar(
            select(MakeupPassPurchase)
            .where(MakeupPassPurchase.id == request.used_pass_purchase_id)
            .with_for_update()
        )
    if purchase is not None:
        purchase.credits_remaining = min(purchase.credits_remaining + 1, purchase.credits_initial)
        purchase.updated_at = now
        db.add(purchase)
    request.status = MakeupRequestStatus.CANCELLED
    request.updated_at = now
    booking.makeup_request_id = None
    booking.makeup_credit_consumed = False
    clear_original(booking)
    db.add(request)
    return True


def makeup_summaries(
    db: Session,
    *,
    user_ids: set[UUID],
    now: datetime | None = None,
) -> list[dict[str, object]]:
    if not user_ids:
        return []
    reference_time = now or datetime.now(timezone.utc)
    users = {row.id: row for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    subscription_rows = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id.in_(user_ids),
            ClientPlanSubscription.status == SubscriptionStatus.ACTIVE,
            ClientPlanSubscription.started_at <= reference_time,
            (ClientPlanSubscription.ends_at.is_(None) | (ClientPlanSubscription.ends_at >= reference_time)),
        )
    ).all()
    purchase_rows = db.execute(
        select(MakeupPassPurchase, ClientPlanSubscription, Plan)
        .join(ClientPlanSubscription, ClientPlanSubscription.id == MakeupPassPurchase.forfait_subscription_id)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(MakeupPassPurchase.user_id.in_(user_ids))
        .order_by(MakeupPassPurchase.created_at.asc())
    ).all()
    requests = db.execute(
        select(MakeupRequest, Booking, CourseSession)
        .join(Booking, Booking.id == MakeupRequest.original_booking_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(MakeupRequest.user_id.in_(user_ids))
        .order_by(MakeupRequest.created_at.desc())
    ).all()
    purchases_by_user: dict[UUID, list[MakeupPassPurchase]] = {user_id: [] for user_id in user_ids}
    active_by_user: dict[UUID, bool] = {user_id: False for user_id in user_ids}
    for subscription, plan in subscription_rows:
        if is_restricted_annual_forfait(plan):
            active_by_user[subscription.user_id] = True
    for purchase, subscription, plan in purchase_rows:
        is_currently_usable = (
            subscription.status == SubscriptionStatus.ACTIVE
            and subscription.started_at <= reference_time
            and (subscription.ends_at is None or subscription.ends_at >= reference_time)
            and is_restricted_annual_forfait(plan)
        )
        if is_currently_usable:
            purchases_by_user.setdefault(purchase.user_id, []).append(purchase)
            active_by_user[purchase.user_id] = True
    requests_by_user: dict[UUID, list[dict[str, object]]] = {user_id: [] for user_id in user_ids}
    for request, booking, session in requests:
        replacement = db.get(Booking, request.reserved_booking_id) if request.reserved_booking_id else None
        replacement_session = db.get(CourseSession, replacement.session_id) if replacement else None
        replacement_location = db.get(Location, replacement_session.location_id) if replacement_session else None
        requests_by_user.setdefault(request.user_id, []).append(
            {
                "id": request.id,
                "status": request.status,
                "original_booking_id": booking.id,
                "original_session_title": session.title,
                "original_session_start_at_utc": session.start_at_utc,
                "created_at": request.created_at,
                "reserved_booking_id": request.reserved_booking_id,
                "reserved_session_title": replacement_session.title if replacement_session else None,
                "reserved_session_start_at_utc": replacement_session.start_at_utc if replacement_session else None,
                "reserved_location": replacement_location.name if replacement_location else None,
                "replacement_covered_by_pass": makeup_role(replacement) == "replacement" if replacement else False,
            }
        )
    result: list[dict[str, object]] = []
    for user_id in sorted(user_ids, key=str):
        user = users.get(user_id)
        purchases = purchases_by_user.get(user_id, [])
        if not purchases and not requests_by_user.get(user_id) and not active_by_user.get(user_id):
            continue
        result.append(
            {
                "user_id": user_id,
                "display_name": " ".join(part for part in ((user.first_name if user else None), (user.last_name if user else None)) if part).strip() or (user.email if user else str(user_id)),
                "has_active_restricted_forfait": active_by_user.get(user_id, False),
                "credits_initial": sum(row.credits_initial for row in purchases),
                "credits_remaining": sum(row.credits_remaining for row in purchases),
                "pending_makeups": [
                    row for row in requests_by_user.get(user_id, []) if row["status"] == MakeupRequestStatus.PROPOSED
                ],
                "history": requests_by_user.get(user_id, []),
            }
        )
    return result
