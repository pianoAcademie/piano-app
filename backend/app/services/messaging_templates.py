from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ops import AppSetting
from app.services.i18n import (
    DEFAULT_LANGUAGE,
    build_translations_payload,
    normalize_language,
    normalize_text,
    normalize_translations,
    translations_for_storage,
)

MessagingChannel = Literal["EMAIL", "SMS", "GROUP_NOTE"]
MessagingTemplateKind = Literal["PREDEFINED", "CUSTOM"]
MessagingTemplateUsageContext = Literal[
    "QUOTE_SEND",
    "QUOTE_REMINDER",
    "QUOTE_CANCEL",
    "QUOTE_EXPIRED",
    "QUOTE_APPROVED",
    "QUOTE_REJECTED",
    "QUOTE_CHANGE_REQUESTED",
    "INVOICE_SEND",
    "INVOICE_REMINDER",
]

MESSAGING_SETTINGS_STUDIO_EMAIL_KEY = "config_messaging_studio_email"
MESSAGING_SETTINGS_STUDIO_SENDER_NAME_KEY = "config_messaging_studio_sender_name"
MESSAGING_SETTINGS_TEACHER_SENDER_NAME_KEY = "config_messaging_teacher_sender_name"
MESSAGING_SETTINGS_USE_STUDIO_NAME_DEFAULT_KEY = "config_messaging_use_studio_name_default_sender"
MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_REMINDERS_KEY = "config_messaging_use_studio_email_for_reminders"
MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_LESSON_NOTES_KEY = "config_messaging_use_studio_email_for_lesson_notes"
MESSAGING_SETTINGS_SEND_BIRTHDAY_EMAILS_KEY = "config_messaging_send_birthday_emails"
MESSAGING_SETTINGS_EMAIL_PROVIDER_KEY = "config_messaging_email_provider"
MESSAGING_SETTINGS_EMAIL_REPLY_TO_KEY = "config_messaging_email_reply_to"
MESSAGING_SETTINGS_EMAIL_SUBJECT_PREFIX_KEY = "config_messaging_email_subject_prefix"
MESSAGING_SETTINGS_SMTP_HOST_KEY = "config_messaging_smtp_host"
MESSAGING_SETTINGS_SMTP_PORT_KEY = "config_messaging_smtp_port"
MESSAGING_SETTINGS_SMTP_USERNAME_KEY = "config_messaging_smtp_username"
MESSAGING_SETTINGS_SMTP_PASSWORD_KEY = "config_messaging_smtp_password"
MESSAGING_SETTINGS_SMTP_USE_TLS_KEY = "config_messaging_smtp_use_tls"
MESSAGING_SETTINGS_SMTP_USE_SSL_KEY = "config_messaging_smtp_use_ssl"
MESSAGING_SETTINGS_SMTP_TIMEOUT_SECONDS_KEY = "config_messaging_smtp_timeout_seconds"
MESSAGING_SETTINGS_SMS_PROVIDER_KEY = "config_messaging_sms_provider"
MESSAGING_SETTINGS_SMS_SENDER_KEY = "config_messaging_sms_sender"
MESSAGING_SETTINGS_BREVO_SMS_API_KEY = "config_messaging_brevo_sms_api_key"
MESSAGING_SETTINGS_FRONTEND_BASE_URL_KEY = "config_messaging_frontend_base_url"
MESSAGING_SETTINGS_QUOTE_SEND_TEMPLATE_REF_KEY = "config_messaging_quote_send_template_ref"
MESSAGING_SETTINGS_QUOTE_SEND_SMS_TEMPLATE_REF_KEY = "config_messaging_quote_send_sms_template_ref"
MESSAGING_SETTINGS_QUOTE_REMINDER_TEMPLATE_REF_KEY = "config_messaging_quote_reminder_template_ref"
MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_TEMPLATE_REF_KEY = "config_messaging_quote_reminder_sms_template_ref"
MESSAGING_SETTINGS_QUOTE_CANCEL_TEMPLATE_REF_KEY = "config_messaging_quote_cancel_template_ref"
MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_TEMPLATE_REF_KEY = "config_messaging_quote_cancel_sms_template_ref"
MESSAGING_SETTINGS_QUOTE_EXPIRED_TEMPLATE_REF_KEY = "config_messaging_quote_expired_template_ref"
MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_TEMPLATE_REF_KEY = "config_messaging_quote_expired_sms_template_ref"
MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY = "config_messaging_quote_approved_template_ref"
MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY = "config_messaging_quote_rejected_template_ref"
MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY = "config_messaging_quote_change_requested_template_ref"
MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY = "config_messaging_quote_reminder_enabled"
MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY = "config_messaging_quote_reminder_sms_enabled"
MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY = "config_messaging_quote_reminder_lead_hours"
MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_CSV_KEY = "config_messaging_quote_reminder_lead_hours_csv"
QUOTE_REMINDER_LEAD_HOURS_DEFAULT = "72,24"
MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY = "config_messaging_quote_daily_job_local_time"
MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY = "config_messaging_quote_auto_cancel_enabled"
MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY = "config_messaging_quote_auto_cancel_delay_hours"
MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_cancel_notification_enabled"
MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_cancel_sms_notification_enabled"
MESSAGING_SETTINGS_QUOTE_EXPIRED_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_expired_notification_enabled"
MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_expired_sms_notification_enabled"

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
MESSAGING_CUSTOM_TEMPLATES_KEY = "config_messaging_custom_templates_v1"

LEGACY_CLIENT_PASSWORD_SUBJECT_KEY = "config_client_password_email_subject"
LEGACY_CLIENT_PASSWORD_BODY_KEY = "config_client_password_email_body"

PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD = "CLIENT_PASSWORD_SETUP"
PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET = "PASSWORD_RESET"
PREDEFINED_EMAIL_TEMPLATE_TEACHER_PASSWORD = "TEACHER_PORTAL_LOGIN_SETUP"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_SEND_DEFAULT = "QUOTE_SEND_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_REMINDER_DEFAULT = "QUOTE_REMINDER_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_CANCEL_DEFAULT = "QUOTE_CANCEL_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_EXPIRED_DEFAULT = "QUOTE_EXPIRED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT = "QUOTE_APPROVED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT = "QUOTE_REJECTED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT = "QUOTE_CHANGE_REQUESTED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_CLIENT_BOOKING_CONFIRMATION = "CLIENT_BOOKING_CONFIRMATION"
PREDEFINED_EMAIL_TEMPLATE_ADMIN_BOOKING_CONFIRMATION = "ADMIN_BOOKING_CONFIRMATION"
PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT = "QUOTE_SEND_SMS_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT = "QUOTE_REMINDER_SMS_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT = "QUOTE_CANCEL_SMS_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_EXPIRED_DEFAULT = "QUOTE_EXPIRED_SMS_DEFAULT"

USAGE_CONTEXT_QUOTE_SEND = "QUOTE_SEND"
USAGE_CONTEXT_QUOTE_REMINDER = "QUOTE_REMINDER"
USAGE_CONTEXT_QUOTE_CANCEL = "QUOTE_CANCEL"
USAGE_CONTEXT_QUOTE_EXPIRED = "QUOTE_EXPIRED"
USAGE_CONTEXT_QUOTE_APPROVED = "QUOTE_APPROVED"
USAGE_CONTEXT_QUOTE_REJECTED = "QUOTE_REJECTED"
USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED = "QUOTE_CHANGE_REQUESTED"

QUOTE_SEND_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_SEND_DEFAULT}"
QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT}"
QUOTE_REMINDER_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_REMINDER_DEFAULT}"
QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT}"
QUOTE_CANCEL_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_CANCEL_DEFAULT}"
QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT}"
QUOTE_EXPIRED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_EXPIRED_DEFAULT}"
QUOTE_EXPIRED_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_EXPIRED_DEFAULT}"
QUOTE_APPROVED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT}"
QUOTE_REJECTED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT}"
QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT}"


@dataclass(frozen=True)
class MessagingTemplateDefinition:
    code: str
    name: str
    channel: MessagingChannel
    subject: str | None
    body: str
    description: str
    variables_hint: str
    body_format: str = "TEXT"
    usage_contexts: tuple[MessagingTemplateUsageContext, ...] = ()


@dataclass(frozen=True)
class MessagingSenderProfile:
    from_email: str
    from_name: str | None
    reply_to: str | None
    subject_prefix: str


@dataclass(frozen=True)
class MessagingDeliveryConfig:
    provider: str
    from_email: str
    reply_to: str | None
    subject_prefix: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_timeout_seconds: int
    frontend_base_url: str


@dataclass(frozen=True)
class MessagingSmsDeliveryConfig:
    provider: str
    sender: str
    brevo_api_key: str
    frontend_base_url: str


def recipient_display_name(
    *,
    civility: object | None = None,
    first_name: object | None = None,
    last_name: object | None = None,
    email: object | None = None,
    fallback: str = "Client",
) -> str:
    parts = [
        str(value or "").strip()
        for value in (civility, first_name, last_name)
        if str(value or "").strip()
    ]
    value = " ".join(parts).strip()
    return value or str(email or "").strip() or fallback


def _resolve_template_text(
    base_value: object,
    translations: dict[str, object] | None,
    *,
    language: str | None = None,
    max_length: int | None = None,
) -> str | None:
    normalized_language = normalize_language(language)
    normalized_translations = normalize_translations(translations, max_length=max_length)
    translated = normalized_translations.get(normalized_language)
    if translated is not None:
        return translated

    base_text = normalize_text(base_value, max_length=max_length)
    if base_text is not None:
        return base_text

    fallback = normalized_translations.get(DEFAULT_LANGUAGE)
    if fallback is not None:
        return fallback

    for value in normalized_translations.values():
        return value
    return None


def _merge_template_translations(
    default_translations: dict[str, object] | None,
    override_translations: dict[str, object] | None,
    *,
    max_length: int | None = None,
) -> dict[str, str]:
    merged = normalize_translations(default_translations, max_length=max_length)
    merged.update(normalize_translations(override_translations, max_length=max_length))
    return dict(sorted(merged.items()))


def resolve_brevo_email_webhook_url(db: Session | None = None) -> str:
    base_url = resolve_frontend_base_url(db).rstrip("/")
    return f"{base_url}/api/v1/notifications/webhooks/brevo/email"


def resolve_brevo_sms_webhook_url(db: Session | None = None) -> str:
    base_url = resolve_frontend_base_url(db).rstrip("/")
    return f"{base_url}/api/v1/notifications/webhooks/brevo/sms"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_text(raw: str | None, *, max_length: int) -> str:
    value = (raw or "").strip()
    if len(value) > max_length:
        return value[:max_length]
    return value


def _sanitize_optional_text(raw: object, *, max_length: int) -> str | None:
    value = _sanitize_text(None if raw is None else str(raw), max_length=max_length)
    return value or None


def _sanitize_int(raw: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _sanitize_int_list(
    raw: object,
    *,
    default: list[int],
    minimum: int,
    maximum: int,
    max_items: int = 8,
) -> list[int]:
    if raw is None:
        values = default
    elif isinstance(raw, (list, tuple, set)):
        values = [str(item).strip() for item in raw]
    else:
        text = str(raw).strip()
        if not text:
            values = default
        else:
            values = [chunk.strip() for chunk in text.replace(";", ",").split(",")]
    normalized: list[int] = []
    for item in values:
        try:
            parsed = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        parsed = max(minimum, min(maximum, parsed))
        if parsed in normalized:
            continue
        normalized.append(parsed)
        if len(normalized) >= max_items:
            break
    if not normalized:
        normalized = [max(minimum, min(maximum, value)) for value in default]
    return sorted(normalized, reverse=True)


def _format_int_list_csv(raw: list[int]) -> str:
    return ",".join(str(item) for item in raw)


def _mask_secret(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _db_or_env(db_value: str | None, env_value: str) -> str:
    normalized_db_value = (db_value or "").strip()
    if normalized_db_value:
        return normalized_db_value
    return (env_value or "").strip()


def _normalize_email_provider(raw: str | None) -> str:
    candidate = (raw or "").strip().upper()
    if candidate in {"SMTP", "BREVO"}:
        return candidate
    return "LOG"


def _normalize_sms_provider(raw: str | None) -> str:
    candidate = (raw or "").strip().upper()
    if candidate == "BREVO":
        return "BREVO"
    return "LOG"


def _normalize_usage_context(raw: object) -> str | None:
    candidate = str(raw or "").strip().upper()
    if candidate in {
        USAGE_CONTEXT_QUOTE_SEND,
        USAGE_CONTEXT_QUOTE_REMINDER,
        USAGE_CONTEXT_QUOTE_CANCEL,
        USAGE_CONTEXT_QUOTE_EXPIRED,
        USAGE_CONTEXT_QUOTE_APPROVED,
        USAGE_CONTEXT_QUOTE_REJECTED,
        USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED,
    }:
        return candidate
    return None


def _normalize_usage_contexts(raw_values: Iterable[object] | None) -> list[str]:
    normalized: list[str] = []
    for raw_value in raw_values or ():
        candidate = _normalize_usage_context(raw_value)
        if candidate is None or candidate in normalized:
            continue
        normalized.append(candidate)
    return normalized


def _sanitize_template_ref(raw: object, *, default: str) -> str:
    candidate = _sanitize_text(None if raw is None else str(raw), max_length=120)
    return candidate or default


def _sanitize_local_time(raw: object, *, default: str) -> str:
    candidate = _sanitize_text(None if raw is None else str(raw), max_length=5)
    if len(candidate) != 5 or candidate[2] != ":":
        return default
    hour_part, minute_part = candidate.split(":", 1)
    if not (hour_part.isdigit() and minute_part.isdigit()):
        return default
    hour = int(hour_part)
    minute = int(minute_part)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


@contextmanager
def _session_scope(db: Session | None = None) -> Iterator[Session]:
    if db is not None:
        yield db
        return
    managed_db = SessionLocal()
    try:
        yield managed_db
    finally:
        managed_db.close()


def _get_setting(db: Session, key: str) -> AppSetting | None:
    return db.scalar(select(AppSetting).where(AppSetting.key == key))


def _get_setting_value(db: Session, key: str, default: str) -> str:
    setting = _get_setting(db, key)
    if setting is None:
        return default
    return setting.value


def _set_setting_value(db: Session, key: str, value: str) -> datetime:
    now = _utcnow()
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    if setting is None:
        db.add(AppSetting(key=key, value=value, updated_at=now))
        return now
    setting.value = value
    setting.updated_at = now
    return now


def resolve_messaging_delivery_config(db: Session | None = None) -> MessagingDeliveryConfig:
    with _session_scope(db) as active_db:
        provider = _normalize_email_provider(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_EMAIL_PROVIDER_KEY, ""),
                settings.email_provider,
            )
        )
        from_email = _sanitize_text(
            _get_setting_value(active_db, MESSAGING_SETTINGS_STUDIO_EMAIL_KEY, settings.email_from),
            max_length=255,
        )
        reply_to = _sanitize_optional_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_EMAIL_REPLY_TO_KEY, ""),
                settings.email_reply_to or "",
            ),
            max_length=255,
        )
        subject_prefix = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_EMAIL_SUBJECT_PREFIX_KEY, ""),
                settings.email_subject_prefix,
            ),
            max_length=120,
        )
        smtp_host = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_HOST_KEY, ""),
                settings.smtp_host,
            ),
            max_length=255,
        )
        if provider == "BREVO" and not smtp_host:
            smtp_host = "smtp-relay.brevo.com"

        smtp_port = _sanitize_int(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_PORT_KEY, ""),
                str(settings.smtp_port),
            ),
            default=587,
            minimum=1,
            maximum=65535,
        )
        smtp_username = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_USERNAME_KEY, ""),
                settings.smtp_username,
            ),
            max_length=255,
        )
        smtp_password = _db_or_env(
            _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_PASSWORD_KEY, ""),
            settings.smtp_password,
        )
        smtp_use_tls = _as_bool(
            _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_USE_TLS_KEY, str(settings.smtp_use_tls).lower()),
            settings.smtp_use_tls,
        )
        smtp_use_ssl = _as_bool(
            _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_USE_SSL_KEY, str(settings.smtp_use_ssl).lower()),
            settings.smtp_use_ssl,
        )
        smtp_timeout_seconds = _sanitize_int(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMTP_TIMEOUT_SECONDS_KEY, ""),
                str(settings.smtp_timeout_seconds),
            ),
            default=15,
            minimum=1,
            maximum=120,
        )
        frontend_base_url = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_FRONTEND_BASE_URL_KEY, ""),
                settings.frontend_base_url,
            ),
            max_length=255,
        ).rstrip("/")
        if not frontend_base_url:
            frontend_base_url = "http://localhost:3000"

    return MessagingDeliveryConfig(
        provider=provider,
        from_email=from_email,
        reply_to=reply_to,
        subject_prefix=subject_prefix,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=smtp_use_tls,
        smtp_use_ssl=smtp_use_ssl,
        smtp_timeout_seconds=smtp_timeout_seconds,
        frontend_base_url=frontend_base_url,
    )


def resolve_messaging_sms_delivery_config(db: Session | None = None) -> MessagingSmsDeliveryConfig:
    with _session_scope(db) as active_db:
        provider = _normalize_sms_provider(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMS_PROVIDER_KEY, ""),
                settings.sms_provider,
            )
        )
        sender = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_SMS_SENDER_KEY, ""),
                settings.sms_sender,
            ),
            max_length=60,
        )
        brevo_api_key = _db_or_env(
            _get_setting_value(active_db, MESSAGING_SETTINGS_BREVO_SMS_API_KEY, ""),
            settings.brevo_sms_api_key,
        )
        frontend_base_url = _sanitize_text(
            _db_or_env(
                _get_setting_value(active_db, MESSAGING_SETTINGS_FRONTEND_BASE_URL_KEY, ""),
                settings.frontend_base_url,
            ),
            max_length=255,
        ).rstrip("/")
        if not frontend_base_url:
            frontend_base_url = "http://localhost:3000"

    return MessagingSmsDeliveryConfig(
        provider=provider,
        sender=sender,
        brevo_api_key=brevo_api_key,
        frontend_base_url=frontend_base_url,
    )


def messaging_delivery_disabled_reason(config: MessagingDeliveryConfig) -> str | None:
    if config.provider == "LOG":
        return "Envoi email reel desactive sur ce serveur (EMAIL_PROVIDER=LOG)."
    if config.provider == "SMTP" and not config.smtp_host.strip():
        return "Configuration email incomplete: SMTP_HOST manquant."
    if not config.smtp_username.strip() or not config.smtp_password.strip():
        return "Configuration email incomplete: identifiants SMTP manquants."
    return None


def messaging_sms_delivery_disabled_reason(config: MessagingSmsDeliveryConfig) -> str | None:
    if config.provider == "LOG":
        return "Envoi SMS reel desactive sur ce serveur (SMS_PROVIDER=LOG)."
    if not config.sender.strip():
        return "Configuration SMS incomplete: expediteur SMS manquant."
    if not config.brevo_api_key.strip():
        return "Configuration SMS incomplete: cle API Brevo manquante."
    return None


def resolve_frontend_base_url(db: Session | None = None) -> str:
    return resolve_messaging_delivery_config(db).frontend_base_url


def _load_json_value(db: Session, key: str, fallback: object) -> object:
    raw = _get_setting_value(db, key, "")
    if not raw.strip():
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return value


def _save_json_value(db: Session, key: str, value: object) -> datetime:
    return _set_setting_value(db, key, json.dumps(value, ensure_ascii=True))


def _parse_iso_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _normalize_body_format(raw: object, *, default: str = "TEXT") -> str:
    candidate = str(raw or default).strip().upper()
    return "HTML" if candidate == "HTML" else "TEXT"


MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
SINGLE_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def render_template_content(template: str, context: dict[str, object] | None = None) -> str:
    values = {str(key): "" if value is None else str(value) for key, value in (context or {}).items()}

    def _replace_mustache(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    def _replace_single(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    normalized = MUSTACHE_PLACEHOLDER_RE.sub(_replace_mustache, template or "")
    normalized = SINGLE_PLACEHOLDER_RE.sub(_replace_single, normalized)
    return normalized.strip()


def _email_layout(*sections: str) -> str:
    return (
        "<div style=\"margin:0;padding:0;background:#f8fafc;\">"
        "<div style=\"max-width:680px;margin:0 auto;padding:24px 16px;"
        "font-family:Arial,'Helvetica Neue',sans-serif;color:#172033;line-height:1.6;\">"
        "<div style=\"background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:28px;\">"
        "<p style=\"margin:0 0 8px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;"
        "font-weight:700;color:#b7791f;\">Piano Academie</p>"
        + "".join(sections)
        + "<p style=\"margin:28px 0 0;font-size:14px;color:#6b7280;\">"
        "Besoin d aide ? Repondez simplement a cet e-mail."
        "</p>"
        "</div>"
        "</div>"
        "</div>"
    )


def _email_title(title: str, intro: str) -> str:
    return (
        f"<h1 style=\"margin:0 0 12px;font-size:30px;line-height:1.2;color:#172033;\">{title}</h1>"
        f"<p style=\"margin:0 0 20px;font-size:16px;color:#374151;\">{intro}</p>"
    )


def _email_summary(rows: list[tuple[str, str]]) -> str:
    html_rows = "".join(
        (
            "<tr>"
            f"<td style=\"padding:8px 0;vertical-align:top;font-weight:700;color:#374151;\">{label}</td>"
            f"<td style=\"padding:8px 0 8px 18px;vertical-align:top;color:#111827;\">{value}</td>"
            "</tr>"
        )
        for label, value in rows
    )
    return (
        "<div style=\"margin:22px 0;padding:18px 20px;background:#fff8ef;"
        "border:1px solid #edd7b3;border-radius:14px;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"border-collapse:collapse;font-size:15px;\">"
        f"{html_rows}"
        "</table>"
        "</div>"
    )


def _email_button(url: str, label: str) -> str:
    return (
        "<p style=\"margin:24px 0 0;\">"
        f"<a href=\"{url}\" style=\"display:inline-block;padding:12px 18px;background:#c98a3d;"
        "color:#ffffff;text-decoration:none;border-radius:10px;font-weight:700;\">"
        f"{label}</a>"
        "</p>"
    )


def _email_secondary(text: str) -> str:
    return f"<p style=\"margin:18px 0 0;font-size:14px;color:#4b5563;\">{text}</p>"


PREDEFINED_TEMPLATE_DEFINITIONS: tuple[MessagingTemplateDefinition, ...] = (
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD,
        name="Student Portal Login Setup",
        channel="EMAIL",
        subject="Activation de votre compte client Piano Academie",
        body=_email_layout(
            _email_title(
                "Votre espace client est pret",
                "Bonjour {first_name}, votre acces Piano Academie est maintenant active.",
            ),
            _email_summary(
                [
                    ("Identifiant", "{email}"),
                    ("Mot de passe temporaire", "{temporary_password}"),
                ]
            ),
            _email_button("{login_url}", "Acceder a mon espace client"),
            _email_secondary(
                "Lors de votre premiere connexion, nous vous invitons a modifier ce mot de passe afin de securiser votre compte."
            ),
        ),
        description="Activation du portail client et envoi du mot de passe temporaire.",
        variables_hint="{first_name} {last_name} {full_name} {email} {temporary_password} {login_url}",
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET,
        name="Password Reset",
        channel="EMAIL",
        subject="Reinitialisez votre mot de passe Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Vous avez demande la reinitialisation de votre mot de passe pour votre espace Piano Academie.\n\n"
            "Pour choisir un nouveau mot de passe, cliquez sur le lien ci-dessous :\n"
            "{reset_url}\n\n"
            "Par mesure de securite, ce lien est personnel et valable pendant une duree limitee.\n\n"
            "Si vous n etes pas a l origine de cette demande, vous pouvez simplement ignorer cet email. "
            "Aucun changement ne sera effectue sur votre compte.\n\n"
            "Bien a vous,\n\n"
            "L equipe Piano Academie"
        ),
        description="Lien de reinitialisation de mot de passe client.",
        variables_hint="{first_name} {last_name} {full_name} {email} {reset_url} {login_url}",
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_TEACHER_PASSWORD,
        name="Teacher Portal Login Setup",
        channel="EMAIL",
        subject="Activation de votre compte professeur Piano Academie",
        body=(
            "Bonjour {full_name},\n\n"
            "Votre compte professeur est active.\n"
            "Identifiant: {email}\n"
            "Mot de passe temporaire: {temporary_password}\n"
            "Connexion: {login_url}\n\n"
            "Merci de vous connecter puis de changer ce mot de passe.\n\n"
            "Piano Academie"
        ),
        description="Activation du portail professeur et envoi du mot de passe temporaire.",
        variables_hint="{first_name} {last_name} {full_name} {email} {temporary_password} {login_url}",
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_SEND_DEFAULT,
        name="Devis - Envoi / renvoi",
        channel="EMAIL",
        subject="Votre devis {quote_number} Piano Academie",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Votre devis <strong>{quote_number}</strong> est disponible.</p>"
            "<p><strong>Total TTC :</strong> {total_ttc} {currency}<br>"
            "<strong>Expiration :</strong> {expires_at_local}</p>"
            "<p><a href=\"{quote_public_url}\">Consulter et agir sur le devis</a><br>"
            "<a href=\"{quote_pdf_url}\">Telecharger le PDF</a></p>"
            "<p>Piano Academie</p>"
        ),
        description="Envoi initial et renvoi manuel d un devis.",
        variables_hint=(
            "{quote_number} {recipient_name} {recipient_email} {total_ttc} {currency} "
            "{expires_at_local} {quote_public_url} {quote_pdf_url} {school_year_label} {calendar_summary}"
        ),
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_SEND,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_REMINDER_DEFAULT,
        name="Devis - Rappel avant expiration",
        channel="EMAIL",
        subject="Rappel : votre devis {quote_number} expire bientot",
        body=_email_layout(
            _email_title(
                "Votre devis arrive bientot a expiration",
                "Bonjour {recipient_name}, voici un rappel avant l expiration de votre devis Piano Academie.",
            ),
            _email_summary(
                [
                    ("Devis", "{quote_number}"),
                    ("Expiration", "{expires_at_local}"),
                    ("Total TTC", "{total_ttc} {currency}"),
                ]
            ),
            _email_button("{quote_public_url}", "Consulter le devis"),
            _email_secondary(
                "Vous pouvez aussi retrouver votre document en version PDF : "
                "<a href=\"{quote_pdf_url}\">telecharger le PDF</a>."
            ),
            _email_secondary(
                "Si vous avez besoin d un ajustement ou d un nouvel echange, notre equipe reste a votre disposition."
            ),
        ),
        description="Rappel automatique avant expiration d un devis.",
        variables_hint=(
            "{quote_number} {recipient_name} {recipient_email} {expires_at_local} {total_ttc} "
            "{currency} {quote_public_url} {quote_pdf_url}"
        ),
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_REMINDER,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_CANCEL_DEFAULT,
        name="Devis - Annulation",
        channel="EMAIL",
        subject="Votre devis {quote_number} n est plus valable",
        body=_email_layout(
            _email_title(
                "Votre devis n est plus valable",
                "Bonjour {recipient_name}, le devis ci-dessous a ete annule et n est plus disponible a la validation.",
            ),
            _email_summary(
                [
                    ("Devis", "{quote_number}"),
                    ("Statut", "{quote_status_label}"),
                    ("Date d annulation", "{cancelled_at_local}"),
                ]
            ),
            _email_secondary(
                "Si vous souhaitez poursuivre votre inscription, notre equipe peut vous preparer une nouvelle proposition."
            ),
        ),
        description="Notification d annulation manuelle ou automatique d un devis.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {cancelled_at_local}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_CANCEL,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_EXPIRED_DEFAULT,
        name="Devis - Expiration client",
        channel="EMAIL",
        subject="Votre devis {quote_number} est expire",
        body=_email_layout(
            _email_title(
                "Votre devis est arrive a expiration",
                (
                    "Bonjour {recipient_name}, votre devis Piano Academie est desormais expire "
                    "car il n a pas ete valide dans les delais."
                ),
            ),
            _email_summary(
                [
                    ("Devis", "{quote_number}"),
                    ("Expiration", "{expires_at_local}"),
                    ("Statut", "{quote_status_label}"),
                ]
            ),
            _email_secondary(
                "Le creneau qui avait ete reserve pour ce devis est donc maintenant libere."
            ),
            _email_secondary(
                "Si vous souhaitez poursuivre votre inscription, notre equipe peut vous preparer une nouvelle proposition."
            ),
        ),
        description="Notification envoyee au client a J+1 apres expiration faute de validation du devis.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {expires_at_local} {expired_at_local}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_EXPIRED,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT,
        name="Devis - Confirmation d approbation",
        channel="EMAIL",
        subject="Votre approbation du devis {quote_number} est bien enregistree",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Nous vous confirmons que votre approbation du devis <strong>{quote_number}</strong> a bien ete prise en compte.</p>"
            "<p><strong>Statut :</strong> {quote_status_label}</p>"
            "<p>Vous pouvez conserver votre lien d acces si besoin : <a href=\"{quote_public_url}\">consulter le devis</a>.</p>"
            "<p>Piano Academie</p>"
        ),
        description="Confirmation envoyee au prospect apres approbation du devis depuis l interface publique.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {quote_public_url} {approved_at_local}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_APPROVED,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT,
        name="Devis - Confirmation de refus",
        channel="EMAIL",
        subject="Votre refus du devis {quote_number} est bien enregistre",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Nous vous confirmons que votre refus du devis <strong>{quote_number}</strong> a bien ete pris en compte.</p>"
            "<p><strong>Statut :</strong> {quote_status_label}</p>"
            "<p>Si votre situation evolue, notre equipe pourra vous preparer une nouvelle proposition.</p>"
            "<p>Piano Academie</p>"
        ),
        description="Confirmation envoyee au prospect apres refus du devis depuis l interface publique.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {rejected_at_local}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_REJECTED,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT,
        name="Devis - Confirmation de demande de modification",
        channel="EMAIL",
        subject="Votre demande de modification du devis {quote_number} a bien ete recue",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Nous vous confirmons que votre demande de modification du devis <strong>{quote_number}</strong> a bien ete prise en compte.</p>"
            "<p>Notre equipe reviendra vers vous apres analyse de votre demande.</p>"
            "<p>Vous pouvez relire le devis ici : <a href=\"{quote_public_url}\">consulter le devis</a>.</p>"
            "<p>Piano Academie</p>"
        ),
        description="Confirmation envoyee au prospect apres demande de modification depuis l interface publique.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {quote_public_url}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT,
        name="Devis - Envoi / renvoi (SMS)",
        channel="SMS",
        subject=None,
        body=(
            "Bonjour {recipient_name}, votre devis {quote_number} ({total_ttc} {currency}) est disponible: "
            "{quote_public_url}"
        ),
        description="Envoi initial et renvoi manuel d un devis par SMS.",
        variables_hint="{quote_number} {recipient_name} {total_ttc} {currency} {quote_public_url} {expires_at_local}",
        usage_contexts=(USAGE_CONTEXT_QUOTE_SEND,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT,
        name="Devis - Rappel avant expiration (SMS)",
        channel="SMS",
        subject=None,
        body=(
            "Piano Academie : votre devis {quote_number} expire le {expires_at_local}. "
            "Consultez-le ici : {quote_public_url}"
        ),
        description="Rappel automatique par SMS avant expiration d un devis.",
        variables_hint="{quote_number} {expires_at_local} {quote_public_url} {recipient_name}",
        usage_contexts=(USAGE_CONTEXT_QUOTE_REMINDER,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT,
        name="Devis - Annulation (SMS)",
        channel="SMS",
        subject=None,
        body=(
            "Piano Academie : votre devis {quote_number} n est plus valable. "
            "Nous pouvons vous adresser un nouveau devis si besoin."
        ),
        description="Notification SMS d annulation manuelle ou automatique d un devis.",
        variables_hint="{quote_number} {quote_status_label} {cancelled_at_local} {recipient_name}",
        usage_contexts=(USAGE_CONTEXT_QUOTE_CANCEL,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_SMS_TEMPLATE_QUOTE_EXPIRED_DEFAULT,
        name="Devis - Expiration client (SMS)",
        channel="SMS",
        subject=None,
        body=(
            "Piano Academie : votre devis {quote_number} est expire. "
            "Le creneau reserve est libere. Contactez-nous si vous souhaitez un nouveau devis."
        ),
        description="Notification SMS envoyee au client a J+1 apres expiration faute de validation du devis.",
        variables_hint="{quote_number} {expires_at_local} {recipient_name}",
        usage_contexts=(USAGE_CONTEXT_QUOTE_EXPIRED,),
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_BOOKING_CONFIRMATION,
        name="Reservation - Confirmation client",
        channel="EMAIL",
        subject="Confirmation de votre reservation - {activity_name}",
        body=_email_layout(
            _email_title(
                "Reservation confirmee",
                "Bonjour {recipient_name}, nous avons bien enregistre votre reservation.",
            ),
            _email_summary(
                [
                    ("Eleve", "{student_name}"),
                    ("Activite", "{activity_name}"),
                    ("Date", "{session_date}"),
                    ("Horaire", "{session_time}"),
                    ("Lieu", "{location_name}"),
                    ("Professeur", "{teacher_name}"),
                ]
            ),
            _email_button("{account_url}", "Acceder a mon espace client"),
            _email_secondary(
                "Vous y retrouverez vos reservations et toutes les informations utiles avant le cours."
            ),
        ),
        description="Confirmation de reservation envoyee au client ou au responsable legal.",
        variables_hint=(
            "{recipient_name} {student_name} {activity_name} {session_date} {session_time} "
            "{session_start_local} {location_name} {teacher_name} {account_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_ADMIN_BOOKING_CONFIRMATION,
        name="Reservation - Confirmation admin",
        channel="EMAIL",
        subject="Nouvelle reservation confirmee - {activity_name}",
        body=(
            "<p>Une reservation a ete confirmee.</p>"
            "<ul>"
            "<li><strong>Eleve :</strong> {student_name}</li>"
            "<li><strong>Activite :</strong> {activity_name}</li>"
            "<li><strong>Date :</strong> {session_date}</li>"
            "<li><strong>Heure :</strong> {session_time}</li>"
            "<li><strong>Lieu :</strong> {location_name}</li>"
            "<li><strong>Professeur :</strong> {teacher_name}</li>"
            "</ul>"
            "<p>Piano Academie</p>"
        ),
        description="Confirmation de reservation envoyee aux administrateurs.",
        variables_hint="{student_name} {activity_name} {session_date} {session_time} {session_start_local} {location_name} {teacher_name}",
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="EVENT_REMINDER",
        name="Event Reminder",
        channel="EMAIL",
        subject="Rappel de votre cours",
        body=(
            "Bonjour {first_name},\n\n"
            "Ceci est un rappel pour votre cours {session_title} le {session_start_human}.\n"
            "Lieu: {location_label}\n\n"
            "Piano Academie"
        ),
        description="Rappel automatique avant un cours.",
        variables_hint="{first_name} {session_title} {session_start_human} {location_label}",
    ),
    MessagingTemplateDefinition(
        code="EVENT_CANCELLED",
        name="Event Cancelled",
        channel="EMAIL",
        subject="Votre cours a ete annule",
        body="Bonjour {first_name},\n\nLe cours {session_title} a ete annule.\n\nPiano Academie",
        description="Information d annulation d un cours.",
        variables_hint="{first_name} {session_title}",
    ),
    MessagingTemplateDefinition(
        code="INVOICE",
        name="Invoice",
        channel="EMAIL",
        subject="Votre facture {invoice_number} est disponible",
        body=_email_layout(
            _email_title(
                "Votre facture est disponible",
                "Bonjour {recipient_name}, vous pouvez consulter votre facture et proceder au reglement en ligne.",
            ),
            _email_summary(
                [
                    ("Facture", "{invoice_number}"),
                    ("Date d emission", "{issued_date}"),
                    ("Echeance", "{due_date}"),
                    ("Montant a regler", "{amount_due} {currency}"),
                ]
            ),
            _email_button("{payment_url}", "Consulter et regler la facture"),
            _email_secondary(
                "Pour payer par virement bancaire, cliquez sur le bouton puis choisissez Virement bancaire. "
                "Une reference unique vous sera communiquee afin de suivre votre paiement."
            ),
            _email_secondary(
                "Lien direct vers la facture : <a href=\"{invoice_url}\">telecharger la facture</a>. "
                "Vous pouvez aussi la retrouver dans votre espace client : "
                "<a href=\"{account_url}\">acceder a mon compte</a>."
            ),
        ),
        description="Envoi de facture.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {invoice_number} {invoice_url} "
            "{recipient_name} "
            "{payment_url} {amount_due} {amount_paid} {total_incl_vat} {currency} {due_date} {issued_date} "
            "{invoice_status} {account_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="INVOICE_PAID",
        name="Invoice Paid",
        channel="EMAIL",
        subject="Votre facture {invoice_number} est disponible et deja reglee",
        body=_email_layout(
            _email_title(
                "Votre facture est disponible",
                "Bonjour {recipient_name}, cette facture est deja reglee. Aucun paiement supplementaire n est attendu.",
            ),
            _email_summary(
                [
                    ("Facture", "{invoice_number}"),
                    ("Date d emission", "{issued_date}"),
                    ("Montant TTC", "{total_incl_vat} {currency}"),
                    ("Paiement deja recu", "{amount_paid} {currency}"),
                ]
            ),
            _email_button("{invoice_url}", "Telecharger la facture"),
            _email_secondary(
                "Retrouvez egalement cette facture dans votre espace client : "
                "<a href=\"{account_url}\">acceder a mon compte</a>."
            ),
        ),
        description="Envoi de facture deja integralement reglee.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {invoice_number} {invoice_url} "
            "{recipient_name} "
            "{payment_url} {amount_due} {amount_paid} {total_incl_vat} {currency} {due_date} {issued_date} "
            "{invoice_status} {account_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="INVOICE_REMINDER",
        name="Invoice Reminder",
        channel="EMAIL",
        subject="Rappel - facture {invoice_number}",
        body=_email_layout(
            _email_title(
                "Rappel de facture",
                "Bonjour {recipient_name}, votre facture est toujours disponible et reste a regler avant son echeance.",
            ),
            _email_summary(
                [
                    ("Facture", "{invoice_number}"),
                    ("Date d emission", "{issued_date}"),
                    ("Echeance", "{due_date}"),
                    ("Montant restant du", "{amount_due} {currency}"),
                ]
            ),
            _email_button("{payment_url}", "Regler ma facture"),
            _email_secondary(
                "Pour payer par virement bancaire, cliquez sur le bouton puis choisissez Virement bancaire. "
                "Une reference unique vous sera communiquee afin de suivre votre paiement."
            ),
            _email_secondary(
                "Lien direct vers la facture : <a href=\"{invoice_url}\">telecharger la facture</a>. "
                "Vous pouvez egalement la retrouver dans votre espace client : "
                "<a href=\"{account_url}\">acceder a mon compte</a>."
            ),
        ),
        description="Relance de facture.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {invoice_number} {invoice_url} "
            "{recipient_name} "
            "{payment_url} {amount_due} {total_incl_vat} {currency} {due_date} {issued_date} {account_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="PAYMENT",
        name="Payment",
        channel="EMAIL",
        subject="Finalisez votre paiement - {plan_name}",
        body=_email_layout(
            _email_title(
                "Votre paiement est pret",
                "Bonjour {first_name}, vous pouvez finaliser votre reglement en ligne pour confirmer votre achat.",
            ),
            _email_summary(
                [
                    ("Offre concernee", "{plan_name}"),
                    ("Montant a regler", "{amount_due} {currency}"),
                    ("Mode de paiement", "{payment_method}"),
                    ("Reference", "{subscription_reference}"),
                ]
            ),
            _email_button("{payment_url}", "Payer en ligne"),
            _email_secondary(
                "Les conditions generales de vente sont disponibles ici : "
                "<a href=\"{legal_terms_url}\">consulter les CGV</a>."
            ),
        ),
        description="Demande de finalisation de paiement.",
        variables_hint=(
            "{first_name} {plan_name} {amount_due} {currency} {payment_method} {payment_url} "
            "{subscription_reference} {legal_terms_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="PAYMENT_CONFIRMED",
        name="Payment Confirmed",
        channel="EMAIL",
        subject="Confirmation de reception de votre paiement - {payment_label}",
        body=_email_layout(
            _email_title(
                "Paiement confirme",
                "Bonjour {first_name}, nous confirmons la reception de votre paiement.",
            ),
            _email_summary(
                [
                    ("Prestation / offre", "{payment_label}"),
                    ("Montant regle", "{amount_paid} {currency}"),
                    ("Date de paiement", "{paid_at}"),
                    ("Reference", "{payment_reference}"),
                ]
            ),
            _email_button("{transactions_url}", "Voir mes transactions"),
            _email_secondary(
                "Votre facture {invoice_number} est disponible ici : "
                "<a href=\"{invoice_url}\">telecharger la facture</a>."
            ),
        ),
        description="Confirmation apres paiement valide.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} "
            "{payment_label} {payment_reference} {plan_name} {subscription_reference} "
            "{amount_paid} {currency} {paid_at} {transactions_url} "
            "{invoice_number} {invoice_url} {payment_url} {account_url}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="PAYMENT_RECEIPT",
        name="Payment Receipt",
        channel="EMAIL",
        subject="Confirmation de reception de votre paiement",
        body=_email_layout(
            _email_title(
                "Justificatif de paiement",
                "Bonjour {first_name}, nous confirmons la reception de votre paiement pour une prestation prevue ulterieurement.",
            ),
            _email_summary(
                [
                    ("Beneficiaire", "{student_name}"),
                    ("Prestation", "{reservation_label}"),
                    ("Date prevue", "{scheduled_service_date}"),
                    ("Horaire", "{session_time_label}"),
                    ("Lieu", "{location_label}"),
                    ("Montant recu", "{amount_paid} {currency}"),
                    ("Reference de paiement", "{payment_reference}"),
                    ("Reference du justificatif", "{receipt_number}"),
                ]
            ),
            _email_button("{account_url}", "Acceder a mon espace client"),
            _email_secondary(
                "Ce document confirme la reception de votre paiement. Il ne constitue pas une facture de prestation. "
                "La facture definitive sera emise a la realisation de la prestation."
            ),
        ),
        description="Justificatif de paiement envoye immediatement apres paiement d une prestation future.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {student_name} "
            "{receipt_number} {amount_paid} {currency} {paid_at} {payment_date} "
            "{payment_method} {payment_provider} {payment_reference} "
            "{reservation_label} {scheduled_service_date} {session_time_label} {location_label} {account_url} "
            "{transactions_url} {payment_document_notice}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="PAYMENT_RECEIPT_ADMIN",
        name="Payment Receipt Admin",
        channel="EMAIL",
        subject="Paiement recu - {reservation_label}",
        body=(
            "Un paiement a ete recu.\n\n"
            "Client: {client_name}\n"
            "Eleve / beneficiaire: {student_name}\n"
            "Montant: {amount_paid} {currency}\n"
            "Date de paiement: {paid_at}\n"
            "Prestation: {reservation_label}\n"
            "Date prevue: {scheduled_service_date}\n"
            "Lieu: {location_label}\n"
            "Reference PSP: {payment_reference}\n\n"
            "Piano Academie"
        ),
        description="Notification interne pour un paiement recu sur une reservation future.",
        variables_hint=(
            "{client_name} {student_name} {amount_paid} {currency} {paid_at} "
            "{reservation_label} {scheduled_service_date} {location_label} {payment_reference}"
        ),
    ),
    MessagingTemplateDefinition(
        code="INVOICE_PAYMENT_ADMIN",
        name="Invoice Payment Admin",
        channel="EMAIL",
        subject="Paiement facture recu - {invoice_number}",
        body=(
            "Un paiement de facture a ete recu.\n\n"
            "Client: {client_name}\n"
            "Email client: {client_email}\n"
            "Facture: {invoice_number}\n"
            "Montant recu: {amount_paid} {currency}\n"
            "Date de paiement: {paid_at}\n"
            "Reference PSP: {payment_reference}\n\n"
            "Facture: {invoice_url}\n"
            "Compte client: {transactions_url}\n\n"
            "Piano Academie"
        ),
        description="Notification interne pour un paiement recu sur une facture.",
        variables_hint=(
            "{client_name} {client_email} {invoice_number} {amount_paid} {currency} "
            "{paid_at} {payment_reference} {invoice_url} {transactions_url}"
        ),
    ),
    MessagingTemplateDefinition(
        code="REFUND_ISSUED",
        name="Refund Issued",
        channel="EMAIL",
        subject="Confirmation de votre remboursement Piano Academie",
        body=_email_layout(
            _email_title(
                "Remboursement confirme",
                "Bonjour {first_name}, nous confirmons l enregistrement de votre remboursement.",
            ),
            _email_summary(
                [
                    ("Beneficiaire", "{student_name}"),
                    ("Prestation", "{reservation_label}"),
                    ("Date prevue", "{scheduled_service_date}"),
                    ("Horaire", "{session_time_label}"),
                    ("Lieu", "{location_label}"),
                    ("Montant rembourse", "{refund_amount} {currency}"),
                    ("Date du remboursement", "{refund_date}"),
                    ("Reference du paiement", "{payment_reference}"),
                    ("Motif", "{refund_reason}"),
                ]
            ),
            _email_button("{account_url}", "Acceder a mon espace client"),
            _email_secondary(
                "Votre reservation est desormais cloturee sur le plan financier. "
                "Vous pouvez retrouver le detail dans votre espace client."
            ),
        ),
        description="Confirmation de remboursement d une reservation ou d un paiement client.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {student_name} "
            "{reservation_label} {scheduled_service_date} {session_time_label} {location_label} "
            "{refund_amount} {currency} {refund_date} {refunded_at} {payment_reference} {refund_reason} "
            "{account_url} {transactions_url} {receipt_number}"
        ),
        body_format="HTML",
    ),
    MessagingTemplateDefinition(
        code="REFUND_ISSUED_ADMIN",
        name="Refund Issued Admin",
        channel="EMAIL",
        subject="Remboursement enregistre - {reservation_label}",
        body=(
            "Un remboursement a ete enregistre.\n\n"
            "Client: {client_name}\n"
            "Eleve / beneficiaire: {student_name}\n"
            "Prestation: {reservation_label}\n"
            "Date prevue: {scheduled_service_date}\n"
            "Lieu: {location_label}\n"
            "Montant rembourse: {refund_amount} {currency}\n"
            "Date du remboursement: {refund_date}\n"
            "Reference du paiement: {payment_reference}\n"
            "Motif: {refund_reason}\n\n"
            "Piano Academie"
        ),
        description="Notification interne lors d un remboursement de reservation.",
        variables_hint=(
            "{client_name} {student_name} {reservation_label} {scheduled_service_date} {location_label} "
            "{refund_amount} {currency} {refund_date} {payment_reference} {refund_reason}"
        ),
    ),
    MessagingTemplateDefinition(
        code="AUTOMATIC_PAYMENT_FAILED",
        name="Automatic Payment Failed",
        channel="EMAIL",
        subject="Echec du paiement automatique",
        body="Bonjour {first_name},\n\nLe dernier paiement automatique a echoue.\n\nPiano Academie",
        description="Notification d echec de prelevement automatique.",
        variables_hint="{first_name}",
    ),
    MessagingTemplateDefinition(
        code="BANK_TRANSFER_FAILED",
        name="Bank Transfer Failed",
        channel="EMAIL",
        subject="Echec du virement",
        body="Bonjour {first_name},\n\nLe dernier virement n a pas pu etre valide.\n\nPiano Academie",
        description="Notification d echec de virement.",
        variables_hint="{first_name}",
    ),
    MessagingTemplateDefinition(
        code="BIRTHDAY_EMAIL",
        name="Birthday Email",
        channel="EMAIL",
        subject="Joyeux anniversaire",
        body=(
            "Bonjour {first_name},\n\n"
            "Toute l equipe de Piano Academie vous souhaite un tres bon anniversaire.\n\n"
            "Piano Academie"
        ),
        description="Email automatique d anniversaire.",
        variables_hint="{first_name}",
    ),
    MessagingTemplateDefinition(
        code="LESSON_NOTES",
        name="Lesson Notes",
        channel="EMAIL",
        subject="Notes de cours",
        body="Bonjour {first_name},\n\nVous trouverez ci-dessous les notes du cours.\n\nPiano Academie",
        description="Envoi des notes de cours.",
        variables_hint="{first_name}",
    ),
    MessagingTemplateDefinition(
        code="NEW_FILE_ADDED",
        name="New File Added",
        channel="EMAIL",
        subject="Nouveau document disponible",
        body="Bonjour {first_name},\n\nUn nouveau document a ete ajoute a votre espace.\n\nPiano Academie",
        description="Notification d ajout de fichier.",
        variables_hint="{first_name}",
    ),
    MessagingTemplateDefinition(
        code="SMS_AUTOMATIC_PAYMENT_FAILED",
        name="Automatic Payment Failed",
        channel="SMS",
        subject=None,
        body="Paiement automatique en echec. Merci de contacter Piano Academie.",
        description="SMS d echec de paiement automatique.",
        variables_hint="",
    ),
    MessagingTemplateDefinition(
        code="SMS_CANCELLED_EVENT",
        name="Cancelled Event",
        channel="SMS",
        subject=None,
        body="Votre cours {session_title} est annule.",
        description="SMS d annulation de cours.",
        variables_hint="{session_title}",
    ),
    MessagingTemplateDefinition(
        code="SMS_EVENT_REMINDER",
        name="Event Reminder",
        channel="SMS",
        subject=None,
        body="Rappel: cours {session_title} le {session_start_human}.",
        description="SMS de rappel de cours.",
        variables_hint="{session_title} {session_start_human}",
    ),
    MessagingTemplateDefinition(
        code="SMS_INVOICE",
        name="Facture - Envoi (SMS)",
        channel="SMS",
        subject=None,
        body="Piano Academie : votre facture {invoice_number} de {amount_due} {currency} est disponible. Reglement : {payment_url}",
        description="SMS envoye avec une facture.",
        variables_hint="{invoice_number} {amount_due} {currency} {payment_url} {invoice_url} {due_date} {issued_date} {client_name} {recipient_name}",
        usage_contexts=("INVOICE_SEND",),
    ),
    MessagingTemplateDefinition(
        code="SMS_INVOICE_REMINDER",
        name="Facture - Relance (SMS)",
        channel="SMS",
        subject=None,
        body="Rappel Piano Academie : la facture {invoice_number} de {amount_due} {currency} est en attente. Reglement : {payment_url}",
        description="SMS de relance facture.",
        variables_hint="{invoice_number} {amount_due} {currency} {payment_url} {invoice_url} {due_date} {issued_date} {client_name} {recipient_name}",
        usage_contexts=("INVOICE_REMINDER",),
    ),
    MessagingTemplateDefinition(
        code="SMS_PAYMENT",
        name="Payment",
        channel="SMS",
        subject=None,
        body="Paiement en attente pour {plan_name}: {amount_due} {currency}. {payment_url}",
        description="SMS de demande de paiement.",
        variables_hint="{plan_name} {amount_due} {currency} {payment_url}",
    ),
    MessagingTemplateDefinition(
        code="SMS_REFUND_ISSUED",
        name="Refund Issued",
        channel="SMS",
        subject=None,
        body="Votre remboursement a ete emis.",
        description="SMS confirmation de remboursement.",
        variables_hint="",
    ),
)

PREDEFINED_TEMPLATE_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD: {
        "subject": {"en": "Activate your Piano Academie client account"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "Your client access is ready.\n"
                "Login: {email}\n"
                "Temporary password: {temporary_password}\n"
                "Sign in: {login_url}\n\n"
                "Please sign in and change this password.\n\n"
                "Piano Academie"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET: {
        "subject": {"en": "Reset your Piano Academie password"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "We received a password reset request.\n"
                "To set a new password, click this link:\n"
                "{reset_url}\n\n"
                "If you did not request this, you can safely ignore this email.\n\n"
                "Piano Academie"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_TEACHER_PASSWORD: {
        "subject": {"en": "Activate your Piano Academie teacher account"},
        "body": {
            "en": (
                "Hello {full_name},\n\n"
                "Your teacher account is active.\n"
                "Login: {email}\n"
                "Temporary password: {temporary_password}\n"
                "Sign in: {login_url}\n\n"
                "Please sign in and update this password.\n\n"
                "Piano Academie"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_SEND_DEFAULT: {
        "subject": {"en": "Your Piano Academie quote {quote_number}"},
        "body": {
            "en": (
                "<p>Hello {recipient_name},</p>"
                "<p>Your quote <strong>{quote_number}</strong> is now available.</p>"
                "<p><strong>Total incl. VAT:</strong> {total_ttc} {currency}<br>"
                "<strong>Expiry:</strong> {expires_at_local}</p>"
                "<p><a href=\"{quote_public_url}\">View and respond to the quote</a><br>"
                "<a href=\"{quote_pdf_url}\">Download the PDF</a></p>"
                "<p>Piano Academie</p>"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_REMINDER_DEFAULT: {
        "subject": {"en": "Reminder: your quote {quote_number} expires soon"},
        "body": {
            "en": _email_layout(
                _email_title(
                    "Your quote will expire soon",
                    "Hello {recipient_name}, this is a reminder before your Piano Academie quote expires.",
                ),
                _email_summary(
                    [
                        ("Quote", "{quote_number}"),
                        ("Expiry", "{expires_at_local}"),
                        ("Total incl. VAT", "{total_ttc} {currency}"),
                    ]
                ),
                _email_button("{quote_public_url}", "View quote"),
                _email_secondary(
                    "You can also access the PDF version here: "
                    "<a href=\"{quote_pdf_url}\">download the PDF</a>."
                ),
                _email_secondary(
                    "If you need any adjustment or would like to discuss the quote, our team is here to help."
                ),
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_CANCEL_DEFAULT: {
        "subject": {"en": "Your quote {quote_number} is no longer valid"},
        "body": {
            "en": _email_layout(
                _email_title(
                    "Your quote is no longer valid",
                    "Hello {recipient_name}, the quote below has been cancelled and can no longer be approved.",
                ),
                _email_summary(
                    [
                        ("Quote", "{quote_number}"),
                        ("Status", "{quote_status_label}"),
                        ("Cancellation date", "{cancelled_at_local}"),
                    ]
                ),
                _email_secondary(
                    "If you would still like to continue your enrolment, our team can prepare a new proposal for you."
                ),
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_EXPIRED_DEFAULT: {
        "subject": {"en": "Your quote {quote_number} has expired"},
        "body": {
            "en": _email_layout(
                _email_title(
                    "Your quote has expired",
                    (
                        "Hello {recipient_name}, your Piano Academie quote has now expired "
                        "because it was not approved before the deadline."
                    ),
                ),
                _email_summary(
                    [
                        ("Quote", "{quote_number}"),
                        ("Expiry", "{expires_at_local}"),
                        ("Status", "{quote_status_label}"),
                    ]
                ),
                _email_secondary("The time slot that was held for this quote has now been released."),
                _email_secondary("If you would still like to continue, our team can prepare a new proposal for you."),
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT: {
        "subject": {"en": "Your approval of quote {quote_number} has been recorded"},
        "body": {
            "en": (
                "<p>Hello {recipient_name},</p>"
                "<p>We confirm that your approval of quote <strong>{quote_number}</strong> has been recorded.</p>"
                "<p><strong>Status:</strong> {quote_status_label}</p>"
                "<p>You can keep your access link here if needed: "
                "<a href=\"{quote_public_url}\">view the quote</a>.</p>"
                "<p>Piano Academie</p>"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT: {
        "subject": {"en": "Your rejection of quote {quote_number} has been recorded"},
        "body": {
            "en": (
                "<p>Hello {recipient_name},</p>"
                "<p>We confirm that your rejection of quote <strong>{quote_number}</strong> has been recorded.</p>"
                "<p><strong>Status:</strong> {quote_status_label}</p>"
                "<p>If your plans change, our team can prepare a new proposal.</p>"
                "<p>Piano Academie</p>"
            )
        },
    },
    PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT: {
        "subject": {"en": "Your change request for quote {quote_number} has been received"},
        "body": {
            "en": (
                "<p>Hello {recipient_name},</p>"
                "<p>We confirm that your request to update quote <strong>{quote_number}</strong> has been received.</p>"
                "<p>Our team will review it and get back to you shortly.</p>"
                "<p>You can review the quote here: <a href=\"{quote_public_url}\">view the quote</a>.</p>"
                "<p>Piano Academie</p>"
            )
        },
    },
    PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT: {
        "body": {
            "en": (
                "Hello {recipient_name}, your quote {quote_number} ({total_ttc} {currency}) is available: "
                "{quote_public_url}"
            )
        }
    },
    PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT: {
        "body": {
            "en": (
                "Piano Academie: your quote {quote_number} expires on {expires_at_local}. "
                "View it here: {quote_public_url}"
            )
        }
    },
    PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT: {
        "body": {
            "en": (
                "Piano Academie: your quote {quote_number} is no longer valid. "
                "We can prepare a new quote for you if needed."
            )
        }
    },
    PREDEFINED_SMS_TEMPLATE_QUOTE_EXPIRED_DEFAULT: {
        "body": {
            "en": (
                "Piano Academie: your quote {quote_number} has expired. "
                "The held time slot has been released. Contact us if you would like a new quote."
            )
        }
    },
    "EVENT_REMINDER": {
        "subject": {"en": "Lesson reminder"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "This is a reminder for your lesson {session_title} on {session_start_human}.\n"
                "Location: {location_label}\n\n"
                "Piano Academie"
            )
        },
    },
    "EVENT_CANCELLED": {
        "subject": {"en": "Your lesson has been cancelled"},
        "body": {
            "en": "Hello {first_name},\n\nThe lesson {session_title} has been cancelled.\n\nPiano Academie"
        },
    },
    "INVOICE": {
        "subject": {"en": "Your Piano Academie invoice"},
        "body": {
            "en": (
                "Hello {recipient_name},\n\n"
                "Your invoice {invoice_number} is now available.\n"
                "Download: {invoice_url}\n\n"
                "Piano Academie"
            )
        },
    },
    "INVOICE_PAID": {
        "subject": {"en": "Your invoice {invoice_number} is available and already paid"},
        "body": {
            "en": (
                "Hello {recipient_name},\n\n"
                "Your invoice {invoice_number} is available and has already been paid.\n"
                "Download: {invoice_url}\n\n"
                "Piano Academie"
            )
        },
    },
    "INVOICE_REMINDER": {
        "subject": {"en": "Invoice reminder"},
        "body": {
            "en": (
                "Hello {recipient_name},\n\n"
                "This is a reminder regarding your invoice.\n\n"
                "Piano Academie"
            )
        },
    },
    "PAYMENT": {
        "subject": {"en": "Complete your Piano Academie payment"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "Your purchase for {plan_name} is ready.\n"
                "Amount due: {amount_due} {currency}\n"
                "Payment method: {payment_method}\n\n"
                "Payment link: {payment_url}\n"
                "Subscription reference: {subscription_reference}\n\n"
                "View terms and conditions: {legal_terms_url}\n\n"
                "Piano Academie"
            )
        },
    },
    "PAYMENT_CONFIRMED": {
        "subject": {"en": "Piano Academie payment confirmation"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "We confirm receipt of your payment for {plan_name}.\n"
                "Amount paid: {amount_paid} {currency}\n"
                "Subscription reference: {subscription_reference}\n"
                "Payment date: {paid_at}\n\n"
                "View your transactions: {transactions_url}\n"
                "Download your invoice ({invoice_number}): {invoice_url}\n\n"
                "Piano Academie"
            )
        },
    },
    "REFUND_ISSUED": {
        "subject": {"en": "Refund confirmation"},
        "body": {"en": "Hello {first_name},\n\nYour refund has been approved.\n\nPiano Academie"},
    },
    "AUTOMATIC_PAYMENT_FAILED": {
        "subject": {"en": "Automatic payment failed"},
        "body": {
            "en": "Hello {first_name},\n\nThe latest automatic payment has failed.\n\nPiano Academie"
        },
    },
    "BANK_TRANSFER_FAILED": {
        "subject": {"en": "Bank transfer failed"},
        "body": {"en": "Hello {first_name},\n\nThe latest bank transfer could not be validated.\n\nPiano Academie"},
    },
    "BIRTHDAY_EMAIL": {
        "subject": {"en": "Happy birthday"},
        "body": {
            "en": (
                "Hello {first_name},\n\n"
                "The whole Piano Academie team wishes you a very happy birthday.\n\n"
                "Piano Academie"
            )
        },
    },
    "LESSON_NOTES": {
        "subject": {"en": "Lesson notes"},
        "body": {"en": "Hello {first_name},\n\nPlease find your lesson notes below.\n\nPiano Academie"},
    },
    "NEW_FILE_ADDED": {
        "subject": {"en": "New document available"},
        "body": {"en": "Hello {first_name},\n\nA new document has been added to your space.\n\nPiano Academie"},
    },
    "SMS_AUTOMATIC_PAYMENT_FAILED": {
        "body": {"en": "Automatic payment failed. Please contact Piano Academie."}
    },
    "SMS_CANCELLED_EVENT": {"body": {"en": "Your lesson {session_title} has been cancelled."}},
    "SMS_EVENT_REMINDER": {"body": {"en": "Reminder: lesson {session_title} on {session_start_human}."}},
    "SMS_INVOICE": {
        "body": {
            "en": "Piano Academie: your invoice {invoice_number} for {amount_due} {currency} is available. Payment: {payment_url}"
        }
    },
    "SMS_INVOICE_REMINDER": {
        "body": {
            "en": "Piano Academie reminder: invoice {invoice_number} for {amount_due} {currency} is pending. Payment: {payment_url}"
        }
    },
    "SMS_PAYMENT": {"body": {"en": "Payment pending for {plan_name}: {amount_due} {currency}. {payment_url}"}},
    "SMS_REFUND_ISSUED": {"body": {"en": "Your refund has been issued."}},
}

PREDEFINED_TEMPLATE_BY_CODE: dict[str, MessagingTemplateDefinition] = {
    template.code: template for template in PREDEFINED_TEMPLATE_DEFINITIONS
}


def list_predefined_template_definitions(*, channel: MessagingChannel | None = None) -> list[MessagingTemplateDefinition]:
    items = list(PREDEFINED_TEMPLATE_DEFINITIONS)
    if channel is not None:
        items = [item for item in items if item.channel == channel]
    return items


def load_messaging_settings(db: Session) -> tuple[dict[str, object], datetime | None]:
    keys = [
        MESSAGING_SETTINGS_STUDIO_EMAIL_KEY,
        MESSAGING_SETTINGS_STUDIO_SENDER_NAME_KEY,
        MESSAGING_SETTINGS_TEACHER_SENDER_NAME_KEY,
        MESSAGING_SETTINGS_USE_STUDIO_NAME_DEFAULT_KEY,
        MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_REMINDERS_KEY,
        MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_LESSON_NOTES_KEY,
        MESSAGING_SETTINGS_SEND_BIRTHDAY_EMAILS_KEY,
        MESSAGING_SETTINGS_EMAIL_PROVIDER_KEY,
        MESSAGING_SETTINGS_EMAIL_REPLY_TO_KEY,
        MESSAGING_SETTINGS_EMAIL_SUBJECT_PREFIX_KEY,
        MESSAGING_SETTINGS_SMTP_HOST_KEY,
        MESSAGING_SETTINGS_SMTP_PORT_KEY,
        MESSAGING_SETTINGS_SMTP_USERNAME_KEY,
        MESSAGING_SETTINGS_SMTP_PASSWORD_KEY,
        MESSAGING_SETTINGS_SMTP_USE_TLS_KEY,
        MESSAGING_SETTINGS_SMTP_USE_SSL_KEY,
        MESSAGING_SETTINGS_SMTP_TIMEOUT_SECONDS_KEY,
        MESSAGING_SETTINGS_SMS_PROVIDER_KEY,
        MESSAGING_SETTINGS_SMS_SENDER_KEY,
        MESSAGING_SETTINGS_BREVO_SMS_API_KEY,
        MESSAGING_SETTINGS_FRONTEND_BASE_URL_KEY,
        MESSAGING_SETTINGS_QUOTE_SEND_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_SEND_SMS_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_CSV_KEY,
        MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_NOTIFICATION_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_NOTIFICATION_ENABLED_KEY,
    ]

    updated_at: datetime | None = None
    for key in keys:
        row = _get_setting(db, key)
        if row is None:
            continue
        if updated_at is None or row.updated_at > updated_at:
            updated_at = row.updated_at

    studio_email = _sanitize_text(
        _get_setting_value(db, MESSAGING_SETTINGS_STUDIO_EMAIL_KEY, settings.email_from),
        max_length=255,
    )
    studio_sender_name = _sanitize_text(
        _get_setting_value(db, MESSAGING_SETTINGS_STUDIO_SENDER_NAME_KEY, "Piano Academie"),
        max_length=120,
    )
    teacher_sender_name = _sanitize_text(
        _get_setting_value(db, MESSAGING_SETTINGS_TEACHER_SENDER_NAME_KEY, "Service ADMINISTRATION"),
        max_length=120,
    )
    delivery_config = resolve_messaging_delivery_config(db)
    delivery_error = messaging_delivery_disabled_reason(delivery_config)
    sms_delivery_config = resolve_messaging_sms_delivery_config(db)
    sms_delivery_error = messaging_sms_delivery_disabled_reason(sms_delivery_config)

    payload = {
        "studio_email": studio_email,
        "studio_sender_name": studio_sender_name,
        "teacher_sender_name": teacher_sender_name,
        "use_studio_name_as_default_sender": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_USE_STUDIO_NAME_DEFAULT_KEY, "true"),
            True,
        ),
        "use_studio_email_for_reminders": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_REMINDERS_KEY, "true"),
            True,
        ),
        "use_studio_email_for_lesson_notes": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_LESSON_NOTES_KEY, "true"),
            True,
        ),
        "send_birthday_emails": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_SEND_BIRTHDAY_EMAILS_KEY, "false"),
            False,
        ),
        "email_provider": delivery_config.provider,
        "email_reply_to": delivery_config.reply_to or "",
        "email_subject_prefix": delivery_config.subject_prefix,
        "smtp_host": delivery_config.smtp_host,
        "smtp_port": delivery_config.smtp_port,
        "smtp_username": delivery_config.smtp_username,
        "smtp_password_configured": bool(delivery_config.smtp_password.strip()),
        "smtp_password_masked": _mask_secret(delivery_config.smtp_password),
        "smtp_use_tls": delivery_config.smtp_use_tls,
        "smtp_use_ssl": delivery_config.smtp_use_ssl,
        "smtp_timeout_seconds": delivery_config.smtp_timeout_seconds,
        "sms_provider": sms_delivery_config.provider,
        "sms_sender": sms_delivery_config.sender,
        "brevo_sms_api_key_configured": bool(sms_delivery_config.brevo_api_key.strip()),
        "brevo_sms_api_key_masked": _mask_secret(sms_delivery_config.brevo_api_key),
        "frontend_base_url": delivery_config.frontend_base_url,
        "brevo_email_webhook_url": resolve_brevo_email_webhook_url(db),
        "brevo_sms_webhook_url": resolve_brevo_sms_webhook_url(db),
        "quote_send_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_SEND_TEMPLATE_REF_KEY, QUOTE_SEND_TEMPLATE_REF_DEFAULT),
            default=QUOTE_SEND_TEMPLATE_REF_DEFAULT,
        ),
        "quote_send_sms_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_SEND_SMS_TEMPLATE_REF_KEY, QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT),
            default=QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT,
        ),
        "quote_reminder_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_TEMPLATE_REF_KEY, QUOTE_REMINDER_TEMPLATE_REF_DEFAULT),
            default=QUOTE_REMINDER_TEMPLATE_REF_DEFAULT,
        ),
        "quote_reminder_sms_template_ref": _sanitize_template_ref(
            _get_setting_value(
                db,
                MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_TEMPLATE_REF_KEY,
                QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT,
            ),
            default=QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT,
        ),
        "quote_cancel_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_CANCEL_TEMPLATE_REF_KEY, QUOTE_CANCEL_TEMPLATE_REF_DEFAULT),
            default=QUOTE_CANCEL_TEMPLATE_REF_DEFAULT,
        ),
        "quote_cancel_sms_template_ref": _sanitize_template_ref(
            _get_setting_value(
                db,
                MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_TEMPLATE_REF_KEY,
                QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT,
            ),
            default=QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT,
        ),
        "quote_expired_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_EXPIRED_TEMPLATE_REF_KEY, QUOTE_EXPIRED_TEMPLATE_REF_DEFAULT),
            default=QUOTE_EXPIRED_TEMPLATE_REF_DEFAULT,
        ),
        "quote_expired_sms_template_ref": _sanitize_template_ref(
            _get_setting_value(
                db,
                MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_TEMPLATE_REF_KEY,
                QUOTE_EXPIRED_SMS_TEMPLATE_REF_DEFAULT,
            ),
            default=QUOTE_EXPIRED_SMS_TEMPLATE_REF_DEFAULT,
        ),
        "quote_approved_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY, QUOTE_APPROVED_TEMPLATE_REF_DEFAULT),
            default=QUOTE_APPROVED_TEMPLATE_REF_DEFAULT,
        ),
        "quote_rejected_template_ref": _sanitize_template_ref(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY, QUOTE_REJECTED_TEMPLATE_REF_DEFAULT),
            default=QUOTE_REJECTED_TEMPLATE_REF_DEFAULT,
        ),
        "quote_change_requested_template_ref": _sanitize_template_ref(
            _get_setting_value(
                db,
                MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY,
                QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT,
            ),
            default=QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT,
        ),
        "quote_reminder_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY, "true"),
            True,
        ),
        "quote_reminder_sms_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY, "false"),
            False,
        ),
        "quote_reminder_lead_hours": _sanitize_int(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY, "24"),
            default=24,
            minimum=1,
            maximum=168,
        ),
        "quote_reminder_lead_hours_values": _sanitize_int_list(
            _get_setting_value(
                db,
                MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_CSV_KEY,
                _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY, QUOTE_REMINDER_LEAD_HOURS_DEFAULT),
            ),
            default=[24],
            minimum=1,
            maximum=168,
        ),
        "quote_reminder_lead_hours_csv": _format_int_list_csv(
            _sanitize_int_list(
                _get_setting_value(
                    db,
                    MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_CSV_KEY,
                    _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY, QUOTE_REMINDER_LEAD_HOURS_DEFAULT),
                ),
                default=[24],
                minimum=1,
                maximum=168,
            )
        ),
        "quote_daily_job_local_time": _sanitize_local_time(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY, "07:00"),
            default="07:00",
        ),
        "quote_auto_cancel_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY, "true"),
            True,
        ),
        "quote_auto_cancel_delay_hours": _sanitize_int(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY, "24"),
            default=24,
            minimum=0,
            maximum=720,
        ),
        "quote_cancel_notification_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY, "true"),
            True,
        ),
        "quote_cancel_sms_notification_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY, "false"),
            False,
        ),
        "quote_expired_notification_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_EXPIRED_NOTIFICATION_ENABLED_KEY, "true"),
            True,
        ),
        "quote_expired_sms_notification_enabled": _as_bool(
            _get_setting_value(db, MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_NOTIFICATION_ENABLED_KEY, "false"),
            False,
        ),
        "delivery_enabled": delivery_error is None,
        "delivery_error_message": delivery_error,
        "sms_delivery_enabled": sms_delivery_error is None,
        "sms_delivery_error_message": sms_delivery_error,
        "updated_at": updated_at,
    }
    return payload, updated_at


def save_messaging_settings(
    db: Session,
    *,
    studio_email: str,
    studio_sender_name: str,
    teacher_sender_name: str,
    use_studio_name_as_default_sender: bool,
    use_studio_email_for_reminders: bool,
    use_studio_email_for_lesson_notes: bool,
    send_birthday_emails: bool,
    email_provider: str,
    email_reply_to: str,
    email_subject_prefix: str,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str | None,
    smtp_use_tls: bool,
    smtp_use_ssl: bool,
    smtp_timeout_seconds: int,
    sms_provider: str,
    sms_sender: str,
    brevo_sms_api_key: str | None,
    frontend_base_url: str,
    quote_send_template_ref: str,
    quote_send_sms_template_ref: str,
    quote_reminder_template_ref: str,
    quote_reminder_sms_template_ref: str,
    quote_cancel_template_ref: str,
    quote_cancel_sms_template_ref: str,
    quote_expired_template_ref: str,
    quote_expired_sms_template_ref: str,
    quote_approved_template_ref: str,
    quote_rejected_template_ref: str,
    quote_change_requested_template_ref: str,
    quote_reminder_enabled: bool,
    quote_reminder_sms_enabled: bool,
    quote_reminder_lead_hours: int,
    quote_reminder_lead_hours_csv: str,
    quote_daily_job_local_time: str,
    quote_auto_cancel_enabled: bool,
    quote_auto_cancel_delay_hours: int,
    quote_cancel_notification_enabled: bool,
    quote_cancel_sms_notification_enabled: bool,
    quote_expired_notification_enabled: bool,
    quote_expired_sms_notification_enabled: bool,
) -> dict[str, object]:
    _set_setting_value(db, MESSAGING_SETTINGS_STUDIO_EMAIL_KEY, _sanitize_text(studio_email, max_length=255))
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_STUDIO_SENDER_NAME_KEY,
        _sanitize_text(studio_sender_name, max_length=120),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_TEACHER_SENDER_NAME_KEY,
        _sanitize_text(teacher_sender_name, max_length=120),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_USE_STUDIO_NAME_DEFAULT_KEY,
        "true" if use_studio_name_as_default_sender else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_REMINDERS_KEY,
        "true" if use_studio_email_for_reminders else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_LESSON_NOTES_KEY,
        "true" if use_studio_email_for_lesson_notes else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SEND_BIRTHDAY_EMAILS_KEY,
        "true" if send_birthday_emails else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_EMAIL_PROVIDER_KEY,
        _normalize_email_provider(email_provider),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_EMAIL_REPLY_TO_KEY,
        _sanitize_text(email_reply_to, max_length=255),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_EMAIL_SUBJECT_PREFIX_KEY,
        _sanitize_text(email_subject_prefix, max_length=120),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_HOST_KEY,
        _sanitize_text(smtp_host, max_length=255),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_PORT_KEY,
        str(_sanitize_int(smtp_port, default=587, minimum=1, maximum=65535)),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_USERNAME_KEY,
        _sanitize_text(smtp_username, max_length=255),
    )
    normalized_password = _sanitize_text(smtp_password, max_length=255)
    if normalized_password:
        _set_setting_value(
            db,
            MESSAGING_SETTINGS_SMTP_PASSWORD_KEY,
            normalized_password,
        )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_USE_TLS_KEY,
        "true" if smtp_use_tls else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_USE_SSL_KEY,
        "true" if smtp_use_ssl else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMTP_TIMEOUT_SECONDS_KEY,
        str(_sanitize_int(smtp_timeout_seconds, default=15, minimum=1, maximum=120)),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMS_PROVIDER_KEY,
        _normalize_sms_provider(sms_provider),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_SMS_SENDER_KEY,
        _sanitize_text(sms_sender, max_length=60),
    )
    normalized_sms_api_key = _sanitize_text(brevo_sms_api_key, max_length=255)
    if normalized_sms_api_key:
        _set_setting_value(
            db,
            MESSAGING_SETTINGS_BREVO_SMS_API_KEY,
            normalized_sms_api_key,
        )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_FRONTEND_BASE_URL_KEY,
        _sanitize_text(frontend_base_url, max_length=255).rstrip("/"),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_SEND_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_send_template_ref, default=QUOTE_SEND_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_SEND_SMS_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_send_sms_template_ref, default=QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_reminder_template_ref, default=QUOTE_REMINDER_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_reminder_sms_template_ref, default=QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_CANCEL_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_cancel_template_ref, default=QUOTE_CANCEL_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_cancel_sms_template_ref, default=QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_expired_template_ref, default=QUOTE_EXPIRED_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_expired_sms_template_ref, default=QUOTE_EXPIRED_SMS_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_approved_template_ref, default=QUOTE_APPROVED_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY,
        _sanitize_template_ref(quote_rejected_template_ref, default=QUOTE_REJECTED_TEMPLATE_REF_DEFAULT),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY,
        _sanitize_template_ref(
            quote_change_requested_template_ref,
            default=QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT,
        ),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY,
        "true" if quote_reminder_enabled else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY,
        "true" if quote_reminder_sms_enabled else "false",
    )
    normalized_reminder_lead_hours = _sanitize_int_list(
        quote_reminder_lead_hours_csv or quote_reminder_lead_hours,
        default=[quote_reminder_lead_hours],
        minimum=1,
        maximum=168,
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY,
        str(min(normalized_reminder_lead_hours)),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_CSV_KEY,
        _format_int_list_csv(normalized_reminder_lead_hours),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY,
        _sanitize_local_time(quote_daily_job_local_time, default="07:00"),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY,
        "true" if quote_auto_cancel_enabled else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY,
        str(_sanitize_int(quote_auto_cancel_delay_hours, default=24, minimum=0, maximum=720)),
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY,
        "true" if quote_cancel_notification_enabled else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY,
        "true" if quote_cancel_sms_notification_enabled else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_NOTIFICATION_ENABLED_KEY,
        "true" if quote_expired_notification_enabled else "false",
    )
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_EXPIRED_SMS_NOTIFICATION_ENABLED_KEY,
        "true" if quote_expired_sms_notification_enabled else "false",
    )
    payload, _ = load_messaging_settings(db)
    return payload


def _predefined_overrides(db: Session) -> dict[str, dict[str, object]]:
    raw = _load_json_value(db, MESSAGING_PREDEFINED_TEMPLATES_KEY, {})
    if not isinstance(raw, dict):
        return {}

    out: dict[str, dict[str, object]] = {}
    for code, value in raw.items():
        if not isinstance(code, str) or not isinstance(value, dict):
            continue
        out[code.strip().upper()] = value
    return out


def _save_predefined_overrides(db: Session, payload: dict[str, dict[str, object]]) -> datetime:
    return _save_json_value(db, MESSAGING_PREDEFINED_TEMPLATES_KEY, payload)


def _custom_templates(db: Session) -> list[dict[str, object]]:
    raw = _load_json_value(db, MESSAGING_CUSTOM_TEMPLATES_KEY, [])
    if not isinstance(raw, list):
        return []

    out: list[dict[str, object]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        channel = str(row.get("channel", "")).strip().upper()
        if channel not in {"EMAIL", "SMS", "GROUP_NOTE"}:
            continue
        template_id = str(row.get("id", "")).strip()
        if not template_id:
            continue
        out.append(
            {
                "id": template_id,
                "name": _sanitize_text(str(row.get("name", "")), max_length=180),
                "channel": channel,
                "subject": _sanitize_optional_text(row.get("subject"), max_length=255),
                "subject_translations": normalize_translations(row.get("subject_translations"), max_length=255),
                "body": _sanitize_text(str(row.get("body", "")), max_length=12000),
                "body_translations": normalize_translations(row.get("body_translations"), max_length=12000),
                "body_format": _normalize_body_format(row.get("body_format"), default="TEXT"),
                "active": bool(row.get("active", True)),
                "usage_contexts": _normalize_usage_contexts(row.get("usage_contexts")),
                "created_at": str(row.get("created_at", "")),
                "updated_at": str(row.get("updated_at", "")),
            }
        )
    return out


def _save_custom_templates(db: Session, payload: list[dict[str, object]]) -> datetime:
    return _save_json_value(db, MESSAGING_CUSTOM_TEMPLATES_KEY, payload)


def resolve_predefined_template(
    db: Session,
    *,
    code: str,
    language: str | None = None,
) -> dict[str, object]:
    normalized_code = code.strip().upper()
    definition = PREDEFINED_TEMPLATE_BY_CODE.get(normalized_code)
    if definition is None:
        raise KeyError(f"Unknown predefined template: {code}")

    override = _predefined_overrides(db).get(normalized_code, {})

    legacy_subject: str | None = None
    legacy_body: str | None = None
    if normalized_code == PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD:
        legacy_subject = _sanitize_optional_text(
            _get_setting_value(db, LEGACY_CLIENT_PASSWORD_SUBJECT_KEY, ""),
            max_length=255,
        )
        legacy_body = _sanitize_optional_text(
            _get_setting_value(db, LEGACY_CLIENT_PASSWORD_BODY_KEY, ""),
            max_length=12000,
        )

    default_translations = PREDEFINED_TEMPLATE_TRANSLATIONS.get(normalized_code, {})

    subject: str | None
    subject_translations: dict[str, str] = {}
    if definition.channel == "EMAIL":
        subject_base = _sanitize_optional_text(override.get("subject"), max_length=255) or legacy_subject or definition.subject
        subject_translations = _merge_template_translations(
            default_translations.get("subject"),
            override.get("subject_translations") if isinstance(override.get("subject_translations"), dict) else None,
            max_length=255,
        )
        subject = _resolve_template_text(subject_base, subject_translations, language=language, max_length=255)
        subject_translations = build_translations_payload(subject_base, subject_translations, max_length=255)
    else:
        subject = None

    body_base = _sanitize_text(str(override.get("body") or legacy_body or definition.body), max_length=12000) or definition.body
    body_translations = _merge_template_translations(
        default_translations.get("body"),
        override.get("body_translations") if isinstance(override.get("body_translations"), dict) else None,
        max_length=12000,
    )
    body = _resolve_template_text(body_base, body_translations, language=language, max_length=12000) or definition.body
    body_translations = build_translations_payload(body_base, body_translations, max_length=12000)
    body_format = _normalize_body_format(override.get("body_format"), default=definition.body_format)
    if definition.channel != "EMAIL":
        body_format = "TEXT"
    active = bool(override.get("active", True))
    updated_at = _parse_iso_datetime(override.get("updated_at"))

    return {
        "id": f"predefined:{normalized_code}",
        "code": normalized_code,
        "name": definition.name,
        "channel": definition.channel,
        "kind": "PREDEFINED",
        "subject": subject,
        "subject_translations": subject_translations,
        "body": body,
        "body_translations": body_translations,
        "body_format": body_format,
        "active": active,
        "usage_contexts": list(definition.usage_contexts),
        "description": definition.description,
        "variables_hint": definition.variables_hint,
        "created_at": None,
        "updated_at": updated_at,
    }


def upsert_predefined_template(
    db: Session,
    *,
    code: str,
    subject: str | None,
    body: str,
    body_format: str,
    active: bool,
    subject_translations: dict[str, object] | None = None,
    body_translations: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_code = code.strip().upper()
    definition = PREDEFINED_TEMPLATE_BY_CODE.get(normalized_code)
    if definition is None:
        raise KeyError(f"Unknown predefined template: {code}")

    cleaned_body = _sanitize_text(body, max_length=12000)
    if not cleaned_body:
        raise ValueError("Template body is required")

    cleaned_subject: str | None = None
    cleaned_body_format = _normalize_body_format(body_format, default="TEXT")
    if definition.channel == "EMAIL":
        cleaned_subject = _sanitize_optional_text(subject, max_length=255)
        if not cleaned_subject:
            raise ValueError("Template subject is required")
    else:
        cleaned_body_format = "TEXT"

    overrides = _predefined_overrides(db)
    now = _utcnow()
    overrides[normalized_code] = {
        "subject": cleaned_subject,
        "subject_translations": (
            translations_for_storage(cleaned_subject, subject_translations, max_length=255)
            if definition.channel == "EMAIL"
            else {}
        ),
        "body": cleaned_body,
        "body_translations": translations_for_storage(cleaned_body, body_translations, max_length=12000),
        "body_format": cleaned_body_format,
        "active": bool(active),
        "updated_at": now.isoformat(),
    }
    _save_predefined_overrides(db, overrides)

    if normalized_code == PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD and cleaned_subject is not None:
        _set_setting_value(db, LEGACY_CLIENT_PASSWORD_SUBJECT_KEY, cleaned_subject)
        _set_setting_value(db, LEGACY_CLIENT_PASSWORD_BODY_KEY, cleaned_body)

    return resolve_predefined_template(db, code=normalized_code)


def reset_predefined_template(
    db: Session,
    *,
    code: str,
) -> dict[str, object]:
    normalized_code = code.strip().upper()
    definition = PREDEFINED_TEMPLATE_BY_CODE.get(normalized_code)
    if definition is None:
        raise KeyError(f"Unknown predefined template: {code}")

    overrides = _predefined_overrides(db)
    if normalized_code in overrides:
        overrides.pop(normalized_code, None)
        _save_predefined_overrides(db, overrides)

    if normalized_code == PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD:
        _set_setting_value(db, LEGACY_CLIENT_PASSWORD_SUBJECT_KEY, "")
        _set_setting_value(db, LEGACY_CLIENT_PASSWORD_BODY_KEY, "")

    return resolve_predefined_template(db, code=normalized_code)


def list_messaging_templates(
    db: Session,
    *,
    channel: MessagingChannel | None = None,
    kind: MessagingTemplateKind | None = None,
    usage_context: str | None = None,
    active_only: bool = False,
    language: str | None = None,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    normalized_usage_context = _normalize_usage_context(usage_context)

    if kind in {None, "PREDEFINED"}:
        for definition in list_predefined_template_definitions(channel=channel):
            template = resolve_predefined_template(db, code=definition.code, language=language)
            if active_only and not template["active"]:
                continue
            if normalized_usage_context and normalized_usage_context not in list(template.get("usage_contexts") or []):
                continue
            items.append(template)

    if kind in {None, "CUSTOM"}:
        for row in _custom_templates(db):
            if channel is not None and row["channel"] != channel:
                continue
            subject_translations = build_translations_payload(
                row.get("subject"),
                row.get("subject_translations") if isinstance(row.get("subject_translations"), dict) else None,
                max_length=255,
            )
            body_translations = build_translations_payload(
                row.get("body"),
                row.get("body_translations") if isinstance(row.get("body_translations"), dict) else None,
                max_length=12000,
            )
            template = {
                "id": row["id"],
                "code": None,
                "name": row["name"] or "Modele personnalise",
                "channel": row["channel"],
                "kind": "CUSTOM",
                "subject": (
                    _resolve_template_text(
                        row.get("subject"),
                        row.get("subject_translations") if isinstance(row.get("subject_translations"), dict) else None,
                        language=language,
                        max_length=255,
                    )
                    if row["channel"] == "EMAIL"
                    else None
                ),
                "subject_translations": subject_translations if row["channel"] == "EMAIL" else {},
                "body": _resolve_template_text(
                    row.get("body"),
                    row.get("body_translations") if isinstance(row.get("body_translations"), dict) else None,
                    language=language,
                    max_length=12000,
                )
                or "",
                "body_translations": body_translations,
                "body_format": _normalize_body_format(row.get("body_format"), default="TEXT"),
                "active": bool(row["active"]),
                "usage_contexts": list(row.get("usage_contexts") or []),
                "description": "Modele personnalise",
                "variables_hint": "",
                "created_at": _parse_iso_datetime(row["created_at"]),
                "updated_at": _parse_iso_datetime(row["updated_at"]),
            }
            if active_only and not template["active"]:
                continue
            if normalized_usage_context and normalized_usage_context not in list(template.get("usage_contexts") or []):
                continue
            items.append(template)

    items.sort(key=lambda row: (str(row["channel"]), str(row["name"]).casefold(), str(row["id"])))
    return items


def create_custom_template(
    db: Session,
    *,
    channel: MessagingChannel,
    name: str,
    subject: str | None,
    body: str,
    body_format: str,
    active: bool,
    usage_contexts: list[str] | None = None,
    subject_translations: dict[str, object] | None = None,
    body_translations: dict[str, object] | None = None,
) -> dict[str, object]:
    cleaned_name = _sanitize_text(name, max_length=180)
    if not cleaned_name:
        raise ValueError("Template name is required")

    cleaned_body = _sanitize_text(body, max_length=12000)
    if not cleaned_body:
        raise ValueError("Template body is required")

    cleaned_subject = _sanitize_optional_text(subject, max_length=255) if channel == "EMAIL" else None
    cleaned_body_format = _normalize_body_format(body_format, default="TEXT")
    if channel == "EMAIL" and not cleaned_subject:
        raise ValueError("Template subject is required for email")
    if channel == "SMS":
        cleaned_body_format = "TEXT"

    now = _utcnow()
    template_id = uuid4().hex
    rows = _custom_templates(db)
    rows.append(
        {
            "id": template_id,
            "name": cleaned_name,
            "channel": channel,
            "subject": cleaned_subject,
            "subject_translations": (
                translations_for_storage(cleaned_subject, subject_translations, max_length=255)
                if channel == "EMAIL"
                else {}
            ),
            "body": cleaned_body,
            "body_translations": translations_for_storage(cleaned_body, body_translations, max_length=12000),
            "body_format": cleaned_body_format,
            "active": bool(active),
            "usage_contexts": _normalize_usage_contexts(usage_contexts),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    )
    _save_custom_templates(db, rows)
    for item in list_messaging_templates(db, channel=channel, kind="CUSTOM"):
        if item["id"] == template_id:
            return item
    raise KeyError("Custom template could not be created")


def update_custom_template(
    db: Session,
    *,
    template_id: str,
    name: str,
    subject: str | None,
    body: str,
    body_format: str,
    active: bool,
    usage_contexts: list[str] | None = None,
    subject_translations: dict[str, object] | None = None,
    body_translations: dict[str, object] | None = None,
) -> dict[str, object]:
    rows = _custom_templates(db)
    now = _utcnow()
    match: dict[str, object] | None = None
    for row in rows:
        if row["id"] == template_id:
            match = row
            break
    if match is None:
        raise KeyError("Custom template not found")

    cleaned_name = _sanitize_text(name, max_length=180)
    if not cleaned_name:
        raise ValueError("Template name is required")

    cleaned_body = _sanitize_text(body, max_length=12000)
    if not cleaned_body:
        raise ValueError("Template body is required")

    channel = str(match.get("channel", "")).strip().upper()
    cleaned_subject = _sanitize_optional_text(subject, max_length=255) if channel == "EMAIL" else None
    cleaned_body_format = _normalize_body_format(body_format, default="TEXT")
    if channel == "EMAIL" and not cleaned_subject:
        raise ValueError("Template subject is required for email")
    if channel == "SMS":
        cleaned_body_format = "TEXT"

    match["name"] = cleaned_name
    match["subject"] = cleaned_subject
    match["subject_translations"] = (
        translations_for_storage(cleaned_subject, subject_translations, max_length=255)
        if channel == "EMAIL"
        else {}
    )
    match["body"] = cleaned_body
    match["body_translations"] = translations_for_storage(cleaned_body, body_translations, max_length=12000)
    match["body_format"] = cleaned_body_format
    match["active"] = bool(active)
    match["usage_contexts"] = _normalize_usage_contexts(usage_contexts)
    match["updated_at"] = now.isoformat()
    _save_custom_templates(db, rows)

    for item in list_messaging_templates(db, kind="CUSTOM"):
        if item["id"] == template_id:
            return item
    raise KeyError("Custom template not found")


def delete_custom_template(db: Session, *, template_id: str) -> bool:
    rows = _custom_templates(db)
    initial_length = len(rows)
    rows = [row for row in rows if str(row.get("id")) != template_id]
    if len(rows) == initial_length:
        return False
    _save_custom_templates(db, rows)
    return True


def resolve_sender_profile(
    db: Session,
    *,
    sender_kind: Literal["STUDIO", "TEACHER"] = "STUDIO",
) -> MessagingSenderProfile:
    settings_payload, _ = load_messaging_settings(db)
    delivery_config = resolve_messaging_delivery_config(db)
    studio_email = delivery_config.from_email
    use_studio_name = bool(settings_payload.get("use_studio_name_as_default_sender", True))
    studio_name = str(settings_payload.get("studio_sender_name") or "").strip()
    teacher_name = str(settings_payload.get("teacher_sender_name") or "").strip()

    from_name: str | None = None
    if use_studio_name:
        if sender_kind == "TEACHER":
            from_name = teacher_name or studio_name or None
        else:
            from_name = studio_name or None

    return MessagingSenderProfile(
        from_email=studio_email,
        from_name=from_name,
        reply_to=delivery_config.reply_to,
        subject_prefix=delivery_config.subject_prefix,
    )


def resolve_messaging_template_ref(
    db: Session,
    *,
    template_ref: str | None,
    default_ref: str,
    channel: MessagingChannel = "EMAIL",
    usage_context: str | None = None,
    active_only: bool = True,
    language: str | None = None,
) -> dict[str, object]:
    normalized_ref = _sanitize_template_ref(template_ref, default=default_ref)
    kind, separator, raw_identifier = normalized_ref.partition(":")
    if not separator:
        kind = "predefined"
        raw_identifier = normalized_ref
    normalized_kind = kind.strip().lower()
    identifier = _sanitize_text(raw_identifier, max_length=120)
    if normalized_kind == "predefined":
        template = resolve_predefined_template(db, code=identifier, language=language)
    elif normalized_kind == "custom":
        template = next(
            (item for item in list_messaging_templates(db, kind="CUSTOM", language=language) if item["id"] == identifier),
            None,
        )
        if template is None:
            raise KeyError("Custom template not found")
    else:
        raise KeyError("Unknown template reference")

    if template.get("channel") != channel:
        raise ValueError("Template channel mismatch")
    if active_only and not bool(template.get("active", True)):
        raise ValueError("Template inactive")
    normalized_usage_context = _normalize_usage_context(usage_context)
    if normalized_usage_context and normalized_usage_context not in list(template.get("usage_contexts") or []):
        raise ValueError("Template not usable for this context")
    return template
