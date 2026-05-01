from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, SubscriptionStatus
from app.models.user import ClientKind, ClientStatus, User, UserRole

LEARNING_BOOKING_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}

LEARNING_SUBSCRIPTION_STATUSES = {
    SubscriptionStatus.PENDING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAYMENT_ALERT,
    SubscriptionStatus.PRE_TERMINATION,
    SubscriptionStatus.PAUSED,
}


def client_status_keeps_portal_enabled(status: ClientStatus) -> bool:
    return status not in {ClientStatus.INACTIVE, ClientStatus.ARCHIVED}


def is_student_like_client_status(status: ClientStatus) -> bool:
    return status in {ClientStatus.ACTIVE, ClientStatus.TRIAL}


def promote_client_to_active_student(user: User) -> bool:
    changed = False
    if user.client_status != ClientStatus.ACTIVE:
        user.client_status = ClientStatus.ACTIVE
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if changed:
        user.updated_at = datetime.now(timezone.utc)
    return changed


def refresh_responsable_status(db: Session, user: User) -> bool:
    if user.role != UserRole.CLIENT or user.client_kind != ClientKind.ADULT:
        desired_active = client_status_keeps_portal_enabled(user.client_status)
        if user.is_active != desired_active:
            user.is_active = desired_active
            user.updated_at = datetime.now(timezone.utc)
            return True
        return False

    has_family_role = _adult_has_family_role(db, user.id)
    has_learning_activity = _adult_has_learning_activity(db, user)

    changed = False
    if has_learning_activity:
        if user.client_status == ClientStatus.RESPONSABLE:
            user.client_status = ClientStatus.ACTIVE
            changed = True
    elif has_family_role:
        if user.client_status not in {ClientStatus.INACTIVE, ClientStatus.ARCHIVED, ClientStatus.RESPONSABLE}:
            user.client_status = ClientStatus.RESPONSABLE
            changed = True
    elif user.client_status == ClientStatus.RESPONSABLE:
        user.client_status = ClientStatus.ACTIVE
        changed = True

    desired_active = client_status_keeps_portal_enabled(user.client_status)
    if user.is_active != desired_active:
        user.is_active = desired_active
        changed = True

    if changed:
        user.updated_at = datetime.now(timezone.utc)
    return changed


def _adult_has_family_role(db: Session, user_id) -> bool:
    return (
        db.scalar(
            select(ClientFamilyLink.id)
            .where(ClientFamilyLink.adult_user_id == user_id)
            .limit(1)
        )
        is not None
    )


def _adult_has_learning_activity(db: Session, user: User) -> bool:
    if user.first_course_at is not None:
        return True
    if (
        db.scalar(
            select(ClientPlanSubscription.id)
            .where(
                ClientPlanSubscription.user_id == user.id,
                ClientPlanSubscription.status.in_(list(LEARNING_SUBSCRIPTION_STATUSES)),
            )
            .limit(1)
        )
        is not None
    ):
        return True
    return (
        db.scalar(
            select(Booking.id)
            .where(
                Booking.user_id == user.id,
                Booking.status.in_(list(LEARNING_BOOKING_STATUSES)),
            )
            .limit(1)
        )
        is not None
    )
