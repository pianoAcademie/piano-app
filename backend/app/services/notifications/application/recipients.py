from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Booking
from app.models.family import ClientFamilyLink
from app.models.user import ClientKind, User, UserRole
from app.services.notifications.domain.constants import (
    NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION,
    NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION,
    NOTIFICATION_TYPE_ADMIN_BANK_TRANSFER_REVIEW,
    NOTIFICATION_TYPE_ADMIN_QUOTES_EXPIRING_TODAY,
    NOTIFICATION_TYPE_ADMIN_SLOT_CANCELLATION,
)
from app.services.notifications.infrastructure.repository import list_admin_recipients_for_type


@dataclass(frozen=True)
class ResolvedRecipient:
    contact_type: str
    contact_id: UUID | None
    email: str | None
    phone: str | None


def _normalize_email(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate or None


def _preferred_phone(user: User) -> str | None:
    for value in (user.mobile_phone_1, user.mobile_phone_2, user.phone, user.home_phone):
        candidate = (value or "").strip()
        if candidate:
            return candidate
    return None


def _load_primary_guardian(db: Session, *, child_user_id: UUID) -> User | None:
    adult_user_id = db.scalar(
        select(ClientFamilyLink.adult_user_id)
        .where(
            ClientFamilyLink.child_user_id == child_user_id,
            ClientFamilyLink.is_billing_recipient.is_(True),
        )
        .limit(1)
    )
    if adult_user_id is None:
        adult_user_id = db.scalar(
            select(ClientFamilyLink.adult_user_id)
            .where(ClientFamilyLink.child_user_id == child_user_id)
            .order_by(ClientFamilyLink.created_at.asc())
            .limit(1)
        )
    if adult_user_id is None:
        return None
    return db.scalar(
        select(User)
        .where(
            User.id == adult_user_id,
            User.role == UserRole.CLIENT,
            User.client_kind == ClientKind.ADULT,
        )
    )


def resolve_reminder_recipients(db: Session, *, booking: Booking) -> list[ResolvedRecipient]:
    owner = db.scalar(select(User).where(User.id == booking.user_id, User.role == UserRole.CLIENT))
    if owner is None:
        return []

    if owner.client_kind == ClientKind.ADULT:
        return [
            ResolvedRecipient(
                contact_type="USER",
                contact_id=owner.id,
                email=_normalize_email(owner.email),
                phone=_preferred_phone(owner),
            )
        ]

    guardian = _load_primary_guardian(db, child_user_id=owner.id)
    if guardian is None:
        return []
    return [
        ResolvedRecipient(
            contact_type="USER",
            contact_id=guardian.id,
            email=_normalize_email(guardian.email),
            phone=_preferred_phone(guardian),
        )
    ]


def resolve_client_booking_notification_recipient(
    db: Session,
    *,
    booking: Booking,
) -> ResolvedRecipient | None:
    recipients = resolve_reminder_recipients(db, booking=booking)
    return recipients[0] if recipients else None


def _fallback_admin_recipients(db: Session) -> list[str]:
    rows = db.scalars(
        select(User.email)
        .where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            User.email.is_not(None),
        )
        .order_by(User.created_at.asc())
    ).all()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        candidate = _normalize_email(row)
        if candidate is None or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def _admin_recipients_for_type(db: Session, *, notification_type: str) -> list[str]:
    configured = list_admin_recipients_for_type(db, notification_type=notification_type)
    if configured:
        return configured
    return _fallback_admin_recipients(db)


def resolve_admin_booking_notification_recipients(db: Session, *, is_cancellation: bool) -> list[ResolvedRecipient]:
    notification_type = (
        NOTIFICATION_TYPE_ADMIN_BOOKING_CANCELLATION if is_cancellation else NOTIFICATION_TYPE_ADMIN_BOOKING_CONFIRMATION
    )
    return [
        ResolvedRecipient(contact_type="ADMIN_EMAIL", contact_id=None, email=email, phone=None)
        for email in _admin_recipients_for_type(db, notification_type=notification_type)
    ]


def resolve_admin_cancellation_recipients(db: Session) -> list[ResolvedRecipient]:
    return [
        ResolvedRecipient(contact_type="ADMIN_EMAIL", contact_id=None, email=email, phone=None)
        for email in _admin_recipients_for_type(db, notification_type=NOTIFICATION_TYPE_ADMIN_SLOT_CANCELLATION)
    ]


def resolve_admin_quote_expiry_digest_recipients(db: Session) -> list[ResolvedRecipient]:
    return [
        ResolvedRecipient(contact_type="ADMIN_EMAIL", contact_id=None, email=email, phone=None)
        for email in _admin_recipients_for_type(db, notification_type=NOTIFICATION_TYPE_ADMIN_QUOTES_EXPIRING_TODAY)
    ]


def resolve_admin_bank_transfer_review_recipients(db: Session) -> list[ResolvedRecipient]:
    return [
        ResolvedRecipient(contact_type="ADMIN_EMAIL", contact_id=None, email=email, phone=None)
        for email in _admin_recipients_for_type(db, notification_type=NOTIFICATION_TYPE_ADMIN_BANK_TRANSFER_REVIEW)
    ]
