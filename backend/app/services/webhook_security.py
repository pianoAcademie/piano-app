from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi import HTTPException, Request, status

from app.core.config import settings


def _required_secret(value: str, *, setting_name: str) -> bytes:
    secret = value.strip()
    if len(secret) < 32:
        raise RuntimeError(f"{setting_name} must contain at least 32 characters")
    return secret.encode("utf-8")


def assert_bearer_webhook_token(request: Request) -> None:
    try:
        secret = _required_secret(settings.brevo_webhook_secret, setting_name="BREVO_WEBHOOK_SECRET")
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook authentication unavailable") from exc

    authorization = (request.headers.get("authorization") or "").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not hmac.compare_digest(token.encode("utf-8"), secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook credentials")


def assert_typeform_signature(*, raw_body: bytes, signature: str | None) -> None:
    try:
        secret = _required_secret(settings.typeform_webhook_secret, setting_name="TYPEFORM_WEBHOOK_SECRET")
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook authentication unavailable") from exc

    expected_digest = hmac.new(secret, raw_body, hashlib.sha256).digest()
    expected_signature = f"sha256={base64.b64encode(expected_digest).decode('ascii')}"
    if not signature or not hmac.compare_digest(signature.strip(), expected_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Typeform signature")
