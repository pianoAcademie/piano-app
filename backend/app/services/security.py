from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

PBKDF2_ITERATIONS = 390000
PBKDF2_ALGORITHM = "sha256"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password.startswith(f"pbkdf2_{PBKDF2_ALGORITHM}$"):
        return False

    try:
        _, rounds_str, salt_b64, digest_b64 = hashed_password.split("$", 3)
        rounds = int(rounds_str)
        salt = _b64decode(salt_b64)
        expected_digest = _b64decode(digest_b64)
    except (ValueError, TypeError):
        return False

    candidate_digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        plain_password.encode("utf-8"),
        salt,
        rounds,
    )

    return hmac.compare_digest(candidate_digest, expected_digest)


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, object] | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload: dict[str, object] = {
        "sub": subject,
        "role": role,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
