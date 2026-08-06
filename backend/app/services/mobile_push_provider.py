from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import threading
from typing import Any

import httpx
import jwt

from app.core.config import settings


@dataclass(frozen=True)
class MobilePushProviderResult:
    accepted: bool
    provider_name: str
    provider_message_id: str | None = None
    provider_status: str | None = None
    error_message: str | None = None
    invalid_token: bool = False


_firebase_lock = threading.Lock()
_firebase_access_token: str | None = None
_firebase_access_token_expires_at: datetime | None = None


def _secret_value(raw: str) -> str:
    value = (raw or "").strip()
    if value.startswith("base64:"):
        return base64.b64decode(value.removeprefix("base64:")).decode("utf-8")
    return value.replace("\\n", "\n")


def _send_apns(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> MobilePushProviderResult:
    private_key = _secret_value(settings.apns_private_key)
    if not settings.apns_team_id or not settings.apns_key_id or not private_key:
        return MobilePushProviderResult(
            accepted=False,
            provider_name="APNS",
            provider_status="NOT_CONFIGURED",
            error_message="Configuration Apple APNs manquante",
        )

    now = datetime.now(timezone.utc)
    auth_token = jwt.encode(
        {"iss": settings.apns_team_id, "iat": int(now.timestamp())},
        private_key,
        algorithm="ES256",
        headers={"kid": settings.apns_key_id},
    )
    host = "https://api.sandbox.push.apple.com" if settings.apns_use_sandbox else "https://api.push.apple.com"
    payload: dict[str, Any] = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        },
        **data,
    }
    headers = {
        "authorization": f"bearer {auth_token}",
        "apns-topic": settings.apns_client_bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    try:
        with httpx.Client(http2=True, timeout=12.0) as client:
            response = client.post(f"{host}/3/device/{token}", headers=headers, json=payload)
    except Exception as exc:  # pragma: no cover - network/provider failure
        return MobilePushProviderResult(
            accepted=False,
            provider_name="APNS",
            provider_status="NETWORK_ERROR",
            error_message=str(exc),
        )

    message_id = response.headers.get("apns-id")
    if response.status_code == 200:
        return MobilePushProviderResult(
            accepted=True,
            provider_name="APNS",
            provider_message_id=message_id,
            provider_status="ACCEPTED",
        )

    try:
        reason = str(response.json().get("reason") or f"HTTP_{response.status_code}")
    except Exception:
        reason = f"HTTP_{response.status_code}"
    return MobilePushProviderResult(
        accepted=False,
        provider_name="APNS",
        provider_message_id=message_id,
        provider_status=reason,
        error_message=reason,
        invalid_token=response.status_code in {400, 410} and reason in {
            "BadDeviceToken",
            "DeviceTokenNotForTopic",
            "Unregistered",
        },
    )


def _firebase_token() -> str:
    global _firebase_access_token, _firebase_access_token_expires_at

    now = datetime.now(timezone.utc)
    with _firebase_lock:
        if (
            _firebase_access_token
            and _firebase_access_token_expires_at
            and _firebase_access_token_expires_at > now + timedelta(minutes=2)
        ):
            return _firebase_access_token

        private_key = _secret_value(settings.firebase_private_key)
        if not settings.firebase_project_id or not settings.firebase_client_email or not private_key:
            raise RuntimeError("Configuration Firebase manquante")

        assertion = jwt.encode(
            {
                "iss": settings.firebase_client_email,
                "scope": "https://www.googleapis.com/auth/firebase.messaging",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=55)).timestamp()),
            },
            private_key,
            algorithm="RS256",
        )
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=12.0,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise RuntimeError("Jeton OAuth Firebase absent")
        expires_in = max(300, int(payload.get("expires_in") or 3600))
        _firebase_access_token = access_token
        _firebase_access_token_expires_at = now + timedelta(seconds=expires_in)
        return access_token


def _send_firebase(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> MobilePushProviderResult:
    try:
        access_token = _firebase_token()
    except Exception as exc:
        status = "NOT_CONFIGURED" if "manquante" in str(exc).lower() else "AUTH_ERROR"
        return MobilePushProviderResult(
            accepted=False,
            provider_name="FCM",
            provider_status=status,
            error_message=str(exc),
        )

    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": data,
            "android": {
                "priority": "high",
                "notification": {"sound": "default", "channel_id": "piano_academie_general"},
            },
        }
    }
    try:
        response = httpx.post(
            f"https://fcm.googleapis.com/v1/projects/{settings.firebase_project_id}/messages:send",
            headers={"authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=12.0,
        )
    except Exception as exc:  # pragma: no cover - network/provider failure
        return MobilePushProviderResult(
            accepted=False,
            provider_name="FCM",
            provider_status="NETWORK_ERROR",
            error_message=str(exc),
        )

    if response.status_code == 200:
        message_id = str((response.json() or {}).get("name") or "") or None
        return MobilePushProviderResult(
            accepted=True,
            provider_name="FCM",
            provider_message_id=message_id,
            provider_status="ACCEPTED",
        )

    error_text = response.text[:1000] or f"HTTP_{response.status_code}"
    invalid_token = response.status_code == 404 or "UNREGISTERED" in error_text or "INVALID_ARGUMENT" in error_text
    return MobilePushProviderResult(
        accepted=False,
        provider_name="FCM",
        provider_status=f"HTTP_{response.status_code}",
        error_message=error_text,
        invalid_token=invalid_token,
    )


def send_mobile_push(
    *,
    platform: str,
    token: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> MobilePushProviderResult:
    if not settings.push_notifications_enabled:
        return MobilePushProviderResult(
            accepted=False,
            provider_name="PUSH",
            provider_status="DISABLED",
            error_message="Notifications push non activees sur le serveur",
        )

    normalized_platform = platform.strip().upper()
    if normalized_platform == "IOS":
        return _send_apns(token=token, title=title, body=body, data=data)
    if normalized_platform == "ANDROID":
        return _send_firebase(token=token, title=title, body=body, data=data)
    return MobilePushProviderResult(
        accepted=False,
        provider_name="PUSH",
        provider_status="UNSUPPORTED_PLATFORM",
        error_message=f"Plateforme non prise en charge: {platform}",
    )


__all__ = ["MobilePushProviderResult", "send_mobile_push"]
