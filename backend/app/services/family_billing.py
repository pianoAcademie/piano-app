from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.family import ClientFamilyLink
from app.models.user import ClientKind, User, UserRole


def resolve_billing_profile(db: Session, client: User) -> User:
    """Return the profile used for billing/VAT resolution.

    For child accounts, use the linked adult marked as billing recipient when available.
    """
    if client.role != UserRole.CLIENT or client.client_kind != ClientKind.CHILD:
        return client

    billing_adult_id = db.scalar(
        select(ClientFamilyLink.adult_user_id)
        .where(
            ClientFamilyLink.child_user_id == client.id,
            ClientFamilyLink.is_billing_recipient.is_(True),
        )
        .limit(1)
    )
    if billing_adult_id is None:
        # Safety net: if no explicit billing recipient is flagged, keep billing on an
        # attached adult rather than falling back to the child profile.
        billing_adult_id = db.scalar(
            select(ClientFamilyLink.adult_user_id)
            .where(ClientFamilyLink.child_user_id == client.id)
            .order_by(ClientFamilyLink.created_at.asc())
            .limit(1)
        )
        if billing_adult_id is None:
            return client

    adult = db.scalar(
        select(User).where(
            User.id == billing_adult_id,
            User.role == UserRole.CLIENT,
            User.client_kind == ClientKind.ADULT,
        )
    )
    if adult is None:
        return client
    return adult
