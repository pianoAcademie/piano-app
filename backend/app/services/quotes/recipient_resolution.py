from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.family import ClientFamilyLink
from app.models.quote import Prospect, Quote
from app.models.user import ClientKind, User, UserRole


def _normalize_email(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate or None


def _normalize_phone(value: str | None) -> str | None:
    candidate = (value or "").strip()
    return candidate or None


def _preferred_user_phone(user: User | None) -> str | None:
    if user is None:
        return None
    for value in (user.mobile_phone_1, user.mobile_phone_2, user.phone, user.home_phone):
        candidate = _normalize_phone(value)
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


def _load_quote_prospect(db: Session, quote: Quote) -> Prospect | None:
    if quote.prospect_id is None:
        return None
    return db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))


def _load_quote_client(db: Session, quote: Quote) -> User | None:
    if quote.client_id is None:
        return None
    return db.scalar(select(User).where(User.id == quote.client_id))


def resolve_quote_recipient_email(db: Session, quote: Quote, explicit_email: str | None = None) -> str | None:
    if explicit_email and explicit_email.strip():
        return explicit_email.strip().lower()

    meta = quote.meta or {}
    from_meta = _normalize_email(str(meta.get("recipient_email") or ""))
    if from_meta:
        return from_meta

    prospect = _load_quote_prospect(db, quote)
    if prospect is not None:
        prospect_meta = prospect.meta or {}
        if str(prospect_meta.get("prospect_type") or "").strip().lower() == "child":
            parent_meta = prospect_meta.get("parent_referent") if isinstance(prospect_meta.get("parent_referent"), dict) else {}
            from_parent_meta = _normalize_email(str((parent_meta or {}).get("email") or ""))
            if from_parent_meta:
                return from_parent_meta
            if prospect.parent_prospect_id is not None:
                parent = db.scalar(select(Prospect).where(Prospect.id == prospect.parent_prospect_id))
                if parent is not None:
                    from_parent = _normalize_email(parent.email)
                    if from_parent:
                        return from_parent
        from_prospect = _normalize_email(prospect.email)
        if from_prospect:
            return from_prospect

    client = _load_quote_client(db, quote)
    if client is not None:
        from_client = _normalize_email(client.email)
        if from_client:
            return from_client
        guardian = _load_primary_guardian(db, child_user_id=client.id) if client.client_kind == ClientKind.CHILD else None
        if guardian is not None:
            from_guardian = _normalize_email(guardian.email)
            if from_guardian:
                return from_guardian

    return None


def resolve_quote_recipient_phone(db: Session, quote: Quote, explicit_phone: str | None = None) -> str | None:
    if explicit_phone and explicit_phone.strip():
        return explicit_phone.strip()

    meta = quote.meta or {}
    from_meta = _normalize_phone(str(meta.get("recipient_phone") or ""))
    if from_meta:
        return from_meta

    prospect = _load_quote_prospect(db, quote)
    if prospect is not None:
        prospect_meta = prospect.meta or {}
        if str(prospect_meta.get("prospect_type") or "").strip().lower() == "child":
            parent_meta = prospect_meta.get("parent_referent") if isinstance(prospect_meta.get("parent_referent"), dict) else {}
            from_parent_meta = _normalize_phone(str((parent_meta or {}).get("phone") or ""))
            if from_parent_meta:
                return from_parent_meta
            if prospect.parent_prospect_id is not None:
                parent = db.scalar(select(Prospect).where(Prospect.id == prospect.parent_prospect_id))
                if parent is not None:
                    from_parent = _normalize_phone(parent.phone)
                    if from_parent:
                        return from_parent
        from_prospect = _normalize_phone(prospect.phone)
        if from_prospect:
            return from_prospect

    client = _load_quote_client(db, quote)
    if client is not None:
        from_client = _preferred_user_phone(client)
        if from_client:
            return from_client
        guardian = _load_primary_guardian(db, child_user_id=client.id) if client.client_kind == ClientKind.CHILD else None
        if guardian is not None:
            from_guardian = _preferred_user_phone(guardian)
            if from_guardian:
                return from_guardian

    return None


__all__ = [
    "resolve_quote_recipient_email",
    "resolve_quote_recipient_phone",
]
