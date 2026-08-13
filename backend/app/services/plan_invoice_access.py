from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings


PLAN_INVOICE_DOWNLOAD_SCOPE = "PLAN_INVOICE_DOWNLOAD"
PLAN_INVOICE_DOWNLOAD_LINK_TTL_DAYS = 30


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _signing_secret() -> bytes:
    secret = settings.invoice_download_secret.strip()
    if len(secret) < 32 or secret in {
        "dev-invoice-download-secret-change-me",
        "change-me-in-production",
    }:
        raise RuntimeError("INVOICE_DOWNLOAD_SECRET must contain at least 32 non-placeholder characters")
    return secret.encode("utf-8")


def create_plan_invoice_download_token(
    *,
    subscription_id: UUID,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + (expires_delta or timedelta(days=PLAN_INVOICE_DOWNLOAD_LINK_TTL_DAYS))
    payload = {
        "scope": PLAN_INVOICE_DOWNLOAD_SCOPE,
        "subscription_id": str(subscription_id),
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_signing_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def assert_plan_invoice_download_token(
    *,
    token: str,
    subscription_id: UUID,
    now: datetime | None = None,
) -> None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _signing_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        provided_signature = _b64decode(encoded_signature)
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien de facture invalide ou expire") from exc

    checked_at = now or datetime.now(timezone.utc)
    if payload.get("scope") != PLAN_INVOICE_DOWNLOAD_SCOPE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien de facture invalide ou expire")
    if payload.get("subscription_id") != str(subscription_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien de facture invalide ou expire")
    if expires_at < int(checked_at.timestamp()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien de facture invalide ou expire")
