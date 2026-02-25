from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://piano:piano@db:5432/piano_academie",
    )
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_json: bool = _as_bool(os.getenv("LOG_JSON"), True)

    # Payment provider defaults and secrets (runtime fallback if DB config is empty)
    payment_provider_default: str = os.getenv("PAYMENT_PROVIDER", "PAYPLUG").upper()
    payment_mode_default: str = os.getenv("PAYMENT_MODE", "TEST").upper()
    payplug_test_secret_key: str = os.getenv("PAYPLUG_TEST_SECRET_KEY", "")
    payplug_live_secret_key: str = os.getenv("PAYPLUG_LIVE_SECRET_KEY", "")
    mollie_test_api_key: str = os.getenv("MOLLIE_TEST_API_KEY", "")
    mollie_live_api_key: str = os.getenv("MOLLIE_LIVE_API_KEY", "")
    payment_webhook_secret: str = os.getenv("PAYMENT_WEBHOOK_SECRET", "")


settings = Settings()
