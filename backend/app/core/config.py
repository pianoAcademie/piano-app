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
    invoice_download_secret: str = os.getenv(
        "INVOICE_DOWNLOAD_SECRET",
        "dev-invoice-download-secret-change-me",
    )
    # Stable HMAC secret used to store gift-card bearer codes without keeping
    # their raw value. Production must use a dedicated random value.
    gift_card_code_pepper: str = os.getenv("GIFT_CARD_CODE_PEPPER", "")
    typeform_webhook_secret: str = os.getenv("TYPEFORM_WEBHOOK_SECRET", "")
    brevo_webhook_secret: str = os.getenv("BREVO_WEBHOOK_SECRET", "")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    admin_access_token_expire_minutes: int = int(
        os.getenv(
            "ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES",
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"),
        )
    )

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
    stripe_test_secret_key: str = os.getenv("STRIPE_TEST_SECRET_KEY", "")
    stripe_live_secret_key: str = os.getenv("STRIPE_LIVE_SECRET_KEY", "")
    payment_webhook_secret: str = os.getenv("PAYMENT_WEBHOOK_SECRET", "")

    # Outbound email delivery
    # Providers:
    # - LOG: no real send (dev fallback)
    # - SMTP: generic SMTP relay
    # - BREVO: SMTP with Brevo defaults when host is omitted
    email_provider: str = os.getenv("EMAIL_PROVIDER", "LOG").upper()
    email_from: str = os.getenv("EMAIL_FROM", "no-reply@piano-academie.com")
    email_reply_to: str | None = os.getenv("EMAIL_REPLY_TO")
    email_subject_prefix: str = os.getenv("EMAIL_SUBJECT_PREFIX", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_use_tls: bool = _as_bool(os.getenv("SMTP_USE_TLS"), True)
    smtp_use_ssl: bool = _as_bool(os.getenv("SMTP_USE_SSL"), False)
    smtp_timeout_seconds: int = int(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
    sms_provider: str = os.getenv("SMS_PROVIDER", "LOG").upper()
    sms_sender: str = os.getenv("SMS_SENDER", "PianoAcad")
    brevo_sms_api_key: str = os.getenv("BREVO_SMS_API_KEY", "")
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
    password_reset_token_expire_minutes: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30"))
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Native mobile push notifications. iOS uses APNs directly; Android uses
    # Firebase Cloud Messaging HTTP v1. Secrets are injected at runtime only.
    push_notifications_enabled: bool = _as_bool(os.getenv("PUSH_NOTIFICATIONS_ENABLED"), False)
    apns_team_id: str = os.getenv("APNS_TEAM_ID", "")
    apns_key_id: str = os.getenv("APNS_KEY_ID", "")
    apns_private_key: str = os.getenv("APNS_PRIVATE_KEY", "")
    apns_client_bundle_id: str = os.getenv("APNS_CLIENT_BUNDLE_ID", "com.pianoacademie.client")
    apns_use_sandbox: bool = _as_bool(os.getenv("APNS_USE_SANDBOX"), False)
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    firebase_client_email: str = os.getenv("FIREBASE_CLIENT_EMAIL", "")
    firebase_private_key: str = os.getenv("FIREBASE_PRIVATE_KEY", "")

    # One-way contact synchronization from Piano Academie to Zendesk. The
    # scheduled worker stays dormant until an initial explicit apply run has
    # created the synchronization cursor.
    zendesk_subdomain: str = os.getenv("ZENDESK_SUBDOMAIN", "")
    zendesk_admin_email: str = os.getenv("ZENDESK_ADMIN_EMAIL", "")
    zendesk_api_token: str = os.getenv("ZENDESK_API_TOKEN", "")
    zendesk_sync_interval_minutes: int = int(os.getenv("ZENDESK_SYNC_INTERVAL_MINUTES", "15"))


settings = Settings()
