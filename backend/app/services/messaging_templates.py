from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ops import AppSetting

MessagingChannel = Literal["EMAIL", "SMS"]
MessagingTemplateKind = Literal["PREDEFINED", "CUSTOM"]

MESSAGING_SETTINGS_STUDIO_EMAIL_KEY = "config_messaging_studio_email"
MESSAGING_SETTINGS_STUDIO_SENDER_NAME_KEY = "config_messaging_studio_sender_name"
MESSAGING_SETTINGS_TEACHER_SENDER_NAME_KEY = "config_messaging_teacher_sender_name"
MESSAGING_SETTINGS_USE_STUDIO_NAME_DEFAULT_KEY = "config_messaging_use_studio_name_default_sender"
MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_REMINDERS_KEY = "config_messaging_use_studio_email_for_reminders"
MESSAGING_SETTINGS_USE_STUDIO_EMAIL_FOR_LESSON_NOTES_KEY = "config_messaging_use_studio_email_for_lesson_notes"
MESSAGING_SETTINGS_SEND_BIRTHDAY_EMAILS_KEY = "config_messaging_send_birthday_emails"

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
MESSAGING_CUSTOM_TEMPLATES_KEY = "config_messaging_custom_templates_v1"

LEGACY_CLIENT_PASSWORD_SUBJECT_KEY = "config_client_password_email_subject"
LEGACY_CLIENT_PASSWORD_BODY_KEY = "config_client_password_email_body"

PREDEFINED_EMAIL_TEMPLATE_CLIENT_PASSWORD = "CLIENT_PASSWORD_SETUP"
PREDEFINED_EMAIL_TEMPLATE_PASSWORD_RESET = "PASSWORD_RESET"
PREDEFINED_EMAIL_TEMPLATE_TEACHER_PASSWORD = "TEACHER_PORTAL_LOGIN_SETUP"


@dataclass(frozen=True)
class MessagingTemplateDefinition:
    code: str
    name: str
    channel: MessagingChannel
    subject: str | None
    body: str
    description: str
    variables_hint: str


@dataclass(frozen=True)
class MessagingSenderProfile:
    from_email: str
    from_name: str | None
    reply_to: str | None
    subject_prefix: str


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
        variables_hint="{first_name} {invoice_number} {invoice_url}",
    ),
    MessagingTemplateDefinition(
        code="INVOICE_REMINDER",
        name="Invoice Reminder",
        channel="EMAIL",
        subject="Rappel facture",
        body="Bonjour {first_name},\n\nCeci est un rappel concernant votre facture.\n\nPiano Academie",
        description="Relance de facture.",
        variables_hint="{first_name}",
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
            "Piano Academie"
        ),
        description="Demande de finalisation de paiement.",
        variables_hint="{first_name} {plan_name} {amount_due} {currency} {payment_method} {payment_url} {subscription_reference}",
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
        if channel not in {"EMAIL", "SMS"}:
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
                "active": bool(row.get("active", True)),
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
        "active": active,
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
    if definition.channel == "EMAIL":
        cleaned_subject = _sanitize_optional_text(subject, max_length=255)
        if not cleaned_subject:
            raise ValueError("Template subject is required")

    overrides = _predefined_overrides(db)
    now = _utcnow()
    overrides[normalized_code] = {
        "subject": cleaned_subject,
        "body": cleaned_body,
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
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []

    if kind in {None, "PREDEFINED"}:
        for definition in list_predefined_template_definitions(channel=channel):
            items.append(resolve_predefined_template(db, code=definition.code))

    if kind in {None, "CUSTOM"}:
        for row in _custom_templates(db):
            if channel is not None and row["channel"] != channel:
                continue
            items.append(
                {
                    "id": row["id"],
                    "code": None,
                    "name": row["name"] or "Modele personnalise",
                    "channel": row["channel"],
                    "kind": "CUSTOM",
                    "subject": row["subject"] if row["channel"] == "EMAIL" else None,
                    "body": row["body"],
                    "active": bool(row["active"]),
                    "description": "Modele personnalise",
                    "variables_hint": "",
                    "created_at": _parse_iso_datetime(row["created_at"]),
                    "updated_at": _parse_iso_datetime(row["updated_at"]),
                }
            )

    items.sort(key=lambda row: (str(row["channel"]), str(row["name"]).casefold(), str(row["id"])))
    return items


def create_custom_template(
    db: Session,
    *,
    channel: MessagingChannel,
    name: str,
    subject: str | None,
    body: str,
    active: bool,
) -> dict[str, object]:
    cleaned_name = _sanitize_text(name, max_length=180)
    if not cleaned_name:
        raise ValueError("Template name is required")

    cleaned_body = _sanitize_text(body, max_length=12000)
    if not cleaned_body:
        raise ValueError("Template body is required")

    cleaned_subject = _sanitize_optional_text(subject, max_length=255) if channel == "EMAIL" else None
    if channel == "EMAIL" and not cleaned_subject:
        raise ValueError("Template subject is required for email")

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
            "active": bool(active),
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
    active: bool,
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
    if channel == "EMAIL" and not cleaned_subject:
        raise ValueError("Template subject is required for email")

    match["name"] = cleaned_name
    match["subject"] = cleaned_subject
    match["body"] = cleaned_body
    match["active"] = bool(active)
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
    studio_email = str(settings_payload.get("studio_email") or "").strip() or settings.email_from
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
        reply_to=settings.email_reply_to,
        subject_prefix=settings.email_subject_prefix,
    )
