from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ops import AppSetting

MessagingChannel = Literal["EMAIL", "SMS", "GROUP_NOTE"]
MessagingTemplateKind = Literal["PREDEFINED", "CUSTOM"]
MessagingTemplateUsageContext = Literal[
    "QUOTE_SEND",
    "QUOTE_REMINDER",
    "QUOTE_CANCEL",
    "QUOTE_APPROVED",
    "QUOTE_REJECTED",
    "QUOTE_CHANGE_REQUESTED",
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
MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY = "config_messaging_quote_approved_template_ref"
MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY = "config_messaging_quote_rejected_template_ref"
MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY = "config_messaging_quote_change_requested_template_ref"
MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY = "config_messaging_quote_reminder_enabled"
MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY = "config_messaging_quote_reminder_sms_enabled"
MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY = "config_messaging_quote_reminder_lead_hours"
MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY = "config_messaging_quote_daily_job_local_time"
MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY = "config_messaging_quote_auto_cancel_enabled"
MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY = "config_messaging_quote_auto_cancel_delay_hours"
MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_cancel_notification_enabled"
MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY = "config_messaging_quote_cancel_sms_notification_enabled"
MESSAGING_SETTINGS_QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_KEY = "config_messaging_quote_pass_recup_non_subscribed_text"

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
PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT = "QUOTE_APPROVED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT = "QUOTE_REJECTED_DEFAULT"
PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT = "QUOTE_CHANGE_REQUESTED_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT = "QUOTE_SEND_SMS_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT = "QUOTE_REMINDER_SMS_DEFAULT"
PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT = "QUOTE_CANCEL_SMS_DEFAULT"

USAGE_CONTEXT_QUOTE_SEND = "QUOTE_SEND"
USAGE_CONTEXT_QUOTE_REMINDER = "QUOTE_REMINDER"
USAGE_CONTEXT_QUOTE_CANCEL = "QUOTE_CANCEL"
USAGE_CONTEXT_QUOTE_APPROVED = "QUOTE_APPROVED"
USAGE_CONTEXT_QUOTE_REJECTED = "QUOTE_REJECTED"
USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED = "QUOTE_CHANGE_REQUESTED"

QUOTE_SEND_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_SEND_DEFAULT}"
QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_SEND_DEFAULT}"
QUOTE_REMINDER_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_REMINDER_DEFAULT}"
QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_REMINDER_DEFAULT}"
QUOTE_CANCEL_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_CANCEL_DEFAULT}"
QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_SMS_TEMPLATE_QUOTE_CANCEL_DEFAULT}"
QUOTE_APPROVED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_APPROVED_DEFAULT}"
QUOTE_REJECTED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_REJECTED_DEFAULT}"
QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT = f"predefined:{PREDEFINED_EMAIL_TEMPLATE_QUOTE_CHANGE_REQUESTED_DEFAULT}"
QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_DEFAULT = (
    "Ce pass permet de rattraper un cours collectif manque, dans la limite de 4 rattrapages par an. "
    "Le rattrapage peut se faire : sur un cours collectif en presentiel, si un creneau est disponible, "
    "ou sur un cours collectif en ligne, sur des creneaux dedies. Le pass est utilisable uniquement "
    "en cas d'absence signalee. Il est valable pour l'annee scolaire en cours et non remboursable. "
    "Sans ce pass, aucun rattrapage ne peut etre propose, quelle que soit la raison de l'absence."
)


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


PREDEFINED_TEMPLATE_DEFINITIONS: tuple[MessagingTemplateDefinition, ...] = (
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD,
        name="Student Portal Login Setup",
        channel="EMAIL",
        subject="Activation de votre compte client Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Votre acces client est pret.\n"
            "Identifiant: {email}\n"
            "Mot de passe temporaire: {temporary_password}\n"
            "Connexion: {login_url}\n\n"
            "Merci de vous connecter puis de modifier ce mot de passe.\n\n"
            "Piano Academie"
        ),
        description="Activation du portail client et envoi du mot de passe temporaire.",
        variables_hint="{first_name} {last_name} {full_name} {email} {temporary_password} {login_url}",
    ),
    MessagingTemplateDefinition(
        code=PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET,
        name="Password Reset",
        channel="EMAIL",
        subject="Reinitialisation de votre mot de passe Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Nous avons recu une demande de reinitialisation de mot de passe.\n"
            "Pour definir un nouveau mot de passe, cliquez sur ce lien:\n"
            "{reset_url}\n\n"
            "Si vous n etes pas a l origine de cette demande, ignorez simplement cet email.\n\n"
            "Piano Academie"
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
        subject="Rappel: votre devis {quote_number} expire bientot",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Votre devis <strong>{quote_number}</strong> arrive a expiration.</p>"
            "<p><strong>Expiration :</strong> {expires_at_local}<br>"
            "<strong>Total TTC :</strong> {total_ttc} {currency}</p>"
            "<p><a href=\"{quote_public_url}\">Consulter le devis</a><br>"
            "<a href=\"{quote_pdf_url}\">Telecharger le PDF</a></p>"
            "<p>Piano Academie</p>"
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
        subject="Votre devis {quote_number} a ete annule",
        body=(
            "<p>Bonjour {recipient_name},</p>"
            "<p>Votre devis <strong>{quote_number}</strong> a ete annule.</p>"
            "<p><strong>Statut :</strong> {quote_status_label}</p>"
            "<p>Si besoin, notre equipe peut vous preparer une nouvelle proposition.</p>"
            "<p>Piano Academie</p>"
        ),
        description="Notification d annulation manuelle ou automatique d un devis.",
        variables_hint="{quote_number} {recipient_name} {quote_status_label} {cancelled_at_local}",
        body_format="HTML",
        usage_contexts=(USAGE_CONTEXT_QUOTE_CANCEL,),
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
            "Rappel Piano Academie: votre devis {quote_number} expire le {expires_at_local}. "
            "Consulter: {quote_public_url}"
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
            "Votre devis {quote_number} a ete annule. Si besoin, Piano Academie peut vous preparer une nouvelle proposition."
        ),
        description="Notification SMS d annulation manuelle ou automatique d un devis.",
        variables_hint="{quote_number} {quote_status_label} {cancelled_at_local} {recipient_name}",
        usage_contexts=(USAGE_CONTEXT_QUOTE_CANCEL,),
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
        subject="Votre facture Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Votre facture {invoice_number} est disponible.\n"
            "Telechargement: {invoice_url}\n\n"
            "Piano Academie"
        ),
        description="Envoi de facture.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {invoice_number} {invoice_url} "
            "{payment_url} {amount_due} {total_incl_vat} {currency} {due_date} {issued_date}"
        ),
    ),
    MessagingTemplateDefinition(
        code="INVOICE_REMINDER",
        name="Invoice Reminder",
        channel="EMAIL",
        subject="Rappel facture",
        body="Bonjour {first_name},\n\nCeci est un rappel concernant votre facture.\n\nPiano Academie",
        description="Relance de facture.",
        variables_hint=(
            "{first_name} {last_name} {full_name} {client_name} {invoice_number} {invoice_url} "
            "{payment_url} {amount_due} {total_incl_vat} {currency} {due_date} {issued_date}"
        ),
    ),
    MessagingTemplateDefinition(
        code="PAYMENT",
        name="Payment",
        channel="EMAIL",
        subject="Finalisez votre paiement Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Votre achat {plan_name} a ete prepare.\n"
            "Montant a regler: {amount_due} {currency}\n"
            "Mode de reglement: {payment_method}\n\n"
            "Lien de paiement: {payment_url}\n"
            "Reference abonnement: {subscription_reference}\n\n"
            "Consulter les CGV: {legal_terms_url}\n\n"
            "Piano Academie"
        ),
        description="Demande de finalisation de paiement.",
        variables_hint=(
            "{first_name} {plan_name} {amount_due} {currency} {payment_method} {payment_url} "
            "{subscription_reference} {legal_terms_url}"
        ),
    ),
    MessagingTemplateDefinition(
        code="PAYMENT_CONFIRMED",
        name="Payment Confirmed",
        channel="EMAIL",
        subject="Confirmation de paiement Piano Academie",
        body=(
            "Bonjour {first_name},\n\n"
            "Nous confirmons la reception de votre paiement pour {plan_name}.\n"
            "Montant regle: {amount_paid} {currency}\n"
            "Reference abonnement: {subscription_reference}\n"
            "Date de paiement: {paid_at}\n\n"
            "Voir vos transactions: {transactions_url}\n"
            "Telecharger votre facture ({invoice_number}): {invoice_url}\n\n"
            "Piano Academie"
        ),
        description="Confirmation apres paiement valide.",
        variables_hint=(
            "{first_name} {plan_name} {amount_paid} {currency} {subscription_reference} "
            "{paid_at} {transactions_url} {invoice_number} {invoice_url}"
        ),
    ),
    MessagingTemplateDefinition(
        code="REFUND_ISSUED",
        name="Refund Issued",
        channel="EMAIL",
        subject="Confirmation de remboursement",
        body="Bonjour {first_name},\n\nVotre remboursement a ete valide.\n\nPiano Academie",
        description="Confirmation de remboursement.",
        variables_hint="{first_name}",
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
        name="Invoice",
        channel="SMS",
        subject=None,
        body="Votre facture Piano Academie est disponible.",
        description="SMS facture.",
        variables_hint="",
    ),
    MessagingTemplateDefinition(
        code="SMS_INVOICE_REMINDER",
        name="Invoice Reminder",
        channel="SMS",
        subject=None,
        body="Rappel facture Piano Academie.",
        description="SMS relance facture.",
        variables_hint="",
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
        MESSAGING_SETTINGS_QUOTE_APPROVED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REJECTED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_SMS_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY,
        MESSAGING_SETTINGS_QUOTE_DAILY_JOB_LOCAL_TIME_KEY,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_AUTO_CANCEL_DELAY_HOURS_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_NOTIFICATION_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_CANCEL_SMS_NOTIFICATION_ENABLED_KEY,
        MESSAGING_SETTINGS_QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_KEY,
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
    pass_recup_non_subscribed_setting = _get_setting(db, MESSAGING_SETTINGS_QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_KEY)

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
        "quote_pass_recup_non_subscribed_text": _sanitize_text(
            (
                pass_recup_non_subscribed_setting.value
                if pass_recup_non_subscribed_setting is not None
                else QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_DEFAULT
            ),
            max_length=4000,
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
    quote_approved_template_ref: str,
    quote_rejected_template_ref: str,
    quote_change_requested_template_ref: str,
    quote_reminder_enabled: bool,
    quote_reminder_sms_enabled: bool,
    quote_reminder_lead_hours: int,
    quote_daily_job_local_time: str,
    quote_auto_cancel_enabled: bool,
    quote_auto_cancel_delay_hours: int,
    quote_cancel_notification_enabled: bool,
    quote_cancel_sms_notification_enabled: bool,
    quote_pass_recup_non_subscribed_text: str,
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
    _set_setting_value(
        db,
        MESSAGING_SETTINGS_QUOTE_REMINDER_LEAD_HOURS_KEY,
        str(_sanitize_int(quote_reminder_lead_hours, default=24, minimum=1, maximum=168)),
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
        MESSAGING_SETTINGS_QUOTE_PASS_RECUP_NON_SUBSCRIBED_TEXT_KEY,
        _sanitize_text(quote_pass_recup_non_subscribed_text, max_length=4000),
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
                "body": _sanitize_text(str(row.get("body", "")), max_length=12000),
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

    subject: str | None
    if definition.channel == "EMAIL":
        subject = _sanitize_optional_text(override.get("subject"), max_length=255) or legacy_subject or definition.subject
    else:
        subject = None

    body = _sanitize_text(str(override.get("body") or legacy_body or definition.body), max_length=12000) or definition.body
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
        "body": body,
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
        "body": cleaned_body,
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
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    normalized_usage_context = _normalize_usage_context(usage_context)

    if kind in {None, "PREDEFINED"}:
        for definition in list_predefined_template_definitions(channel=channel):
            template = resolve_predefined_template(db, code=definition.code)
            if active_only and not template["active"]:
                continue
            if normalized_usage_context and normalized_usage_context not in list(template.get("usage_contexts") or []):
                continue
            items.append(template)

    if kind in {None, "CUSTOM"}:
        for row in _custom_templates(db):
            if channel is not None and row["channel"] != channel:
                continue
            template = {
                "id": row["id"],
                "code": None,
                "name": row["name"] or "Modele personnalise",
                "channel": row["channel"],
                "kind": "CUSTOM",
                "subject": row["subject"] if row["channel"] == "EMAIL" else None,
                "body": row["body"],
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
            "body": cleaned_body,
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
    match["body"] = cleaned_body
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
) -> dict[str, object]:
    normalized_ref = _sanitize_template_ref(template_ref, default=default_ref)
    kind, separator, raw_identifier = normalized_ref.partition(":")
    if not separator:
        kind = "predefined"
        raw_identifier = normalized_ref
    normalized_kind = kind.strip().lower()
    identifier = _sanitize_text(raw_identifier, max_length=120)
    if normalized_kind == "predefined":
        template = resolve_predefined_template(db, code=identifier)
    elif normalized_kind == "custom":
        template = next((item for item in list_messaging_templates(db, kind="CUSTOM") if item["id"] == identifier), None)
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
