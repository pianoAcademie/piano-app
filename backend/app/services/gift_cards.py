from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.core.config import settings


GIFT_CARD_CONTEXT_SCOPE = "GIFT_CARD_REDEEM"
GIFT_CARD_CONTEXT_TTL = timedelta(hours=24)
GIFT_CARD_CODE_PEPPER_MIN_LENGTH = 32


def normalize_gift_card_code(raw_code: str) -> str:
    """Return the canonical code without formatting separators.

    WordPress and physical cards commonly print groups separated by spaces or
    dashes. They all resolve to the same stored HMAC without retaining the raw
    bearer code in the database.
    """

    return re.sub(r"[^A-Z0-9]", "", str(raw_code or "").strip().upper())


def gift_card_code_hash(raw_code: str) -> str:
    normalized = normalize_gift_card_code(raw_code)
    if len(normalized) < 6:
        raise ValueError("Gift card code is too short")
    pepper_value = str(settings.gift_card_code_pepper or "").strip()
    if len(pepper_value) < GIFT_CARD_CODE_PEPPER_MIN_LENGTH:
        raise RuntimeError(
            "GIFT_CARD_CODE_PEPPER must be configured with at least "
            f"{GIFT_CARD_CODE_PEPPER_MIN_LENGTH} characters"
        )
    pepper = pepper_value.encode("utf-8")
    return hmac.new(pepper, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def gift_card_code_suffix(raw_code: str) -> str:
    normalized = normalize_gift_card_code(raw_code)
    if len(normalized) < 6:
        raise ValueError("Gift card code is too short")
    return normalized[-8:]


def gift_card_external_reference_key(
    *,
    source: str,
    external_order_ref: str | None,
    external_line_ref: str | None,
) -> str | None:
    order = str(external_order_ref or "").strip()
    if not order:
        return None
    line = str(external_line_ref or "").strip() or "1"
    return f"{str(source or '').strip().upper()}:{order}:{line}"


def encode_gift_card_context(gift_card_id: UUID, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(timezone.utc)
    payload = {
        "scope": GIFT_CARD_CONTEXT_SCOPE,
        "gift_card_id": str(gift_card_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + GIFT_CARD_CONTEXT_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_gift_card_context(token: str) -> UUID:
    try:
        payload = jwt.decode(
            str(token or "").strip(),
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le lien d'activation de la carte cadeau est invalide ou a expire",
        ) from exc
    if payload.get("scope") != GIFT_CARD_CONTEXT_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le lien d'activation de la carte cadeau est invalide",
        )
    try:
        return UUID(str(payload.get("gift_card_id") or ""))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le lien d'activation de la carte cadeau est invalide",
        ) from exc
