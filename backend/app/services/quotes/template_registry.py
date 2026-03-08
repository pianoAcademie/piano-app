from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TypedDict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting

QUOTE_TEMPLATES_SETTING_KEY = "config_quote_templates_v1"


class QuoteTemplateVariableDef(TypedDict):
    key: str
    label: str
    description: str
    example: str


class QuoteTemplateRecord(TypedDict):
    id: str
    code: str
    name: str
    language: str
    subject_template: str
    body_template: str
    is_active: bool
    is_default: bool
    created_at: str
    updated_at: str


QUOTE_TEMPLATE_VARIABLES: tuple[QuoteTemplateVariableDef, ...] = (
    {
        "key": "quote_number",
        "label": "Numero devis",
        "description": "Identifiant unique du devis.",
        "example": "DV-20260307094500-AB12",
    },
    {
        "key": "recipient_name",
        "label": "Nom destinataire",
        "description": "Nom du prospect ou client cible.",
        "example": "Marie Dupont",
    },
    {
        "key": "recipient_email",
        "label": "Email destinataire",
        "description": "Email de contact du devis.",
        "example": "marie@example.com",
    },
    {
        "key": "total_ttc",
        "label": "Total TTC",
        "description": "Montant total TTC du devis.",
        "example": "1290.00",
    },
    {
        "key": "total_ht",
        "label": "Total HT",
        "description": "Montant total HT calcule selon la TVA.",
        "example": "1075.00",
    },
    {
        "key": "vat_rate",
        "label": "TVA (%)",
        "description": "Taux de TVA applique au devis.",
        "example": "20.00",
    },
    {
        "key": "vat_amount",
        "label": "Montant TVA",
        "description": "Montant de TVA calcule.",
        "example": "215.00",
    },
    {
        "key": "currency",
        "label": "Devise",
        "description": "Devise du devis.",
        "example": "EUR",
    },
    {
        "key": "expires_at",
        "label": "Date expiration",
        "description": "Date d'expiration du devis.",
        "example": "31/08/2026",
    },
    {
        "key": "sent_at",
        "label": "Date envoi",
        "description": "Date d'envoi du devis.",
        "example": "07/03/2026 14:15",
    },
    {
        "key": "generated_at",
        "label": "Date generation",
        "description": "Date de generation du document.",
        "example": "07/03/2026 14:20",
    },
    {
        "key": "school_year_label",
        "label": "Annee scolaire",
        "description": "Annee scolaire du devis.",
        "example": "2026-2027",
    },
    {
        "key": "calendar_summary",
        "label": "Resume planning",
        "description": "Resume du calendrier calcule.",
        "example": "Lundi 17:00-18:00, 32 seances",
    },
    {
        "key": "payment_schedule_summary",
        "label": "Resume echeancier",
        "description": "Resume des echeances de paiement.",
        "example": "2 cheques: inscription + fevrier",
    },
    {
        "key": "cgv_version",
        "label": "Version CGV",
        "description": "Version CGV associee au devis.",
        "example": "CGV 2026.1",
    },
    {
        "key": "prospect_type_label",
        "label": "Type prospect",
        "description": "Type de prospect (Adulte/Enfant).",
        "example": "Enfant",
    },
    {
        "key": "adult_full_name",
        "label": "Nom adulte",
        "description": "Nom complet du prospect adulte.",
        "example": "Paul Martin",
    },
    {
        "key": "adult_email",
        "label": "Email adulte",
        "description": "Email du prospect adulte.",
        "example": "paul@example.com",
    },
    {
        "key": "adult_phone",
        "label": "Telephone adulte",
        "description": "Telephone du prospect adulte.",
        "example": "0601020304",
    },
    {
        "key": "adult_address",
        "label": "Adresse adulte",
        "description": "Adresse du prospect adulte.",
        "example": "12 rue de Paris, 75010 Paris",
    },
    {
        "key": "parent_full_name",
        "label": "Nom parent",
        "description": "Nom complet du parent referent.",
        "example": "Sophie Dupont",
    },
    {
        "key": "parent_email",
        "label": "Email parent",
        "description": "Email du parent referent.",
        "example": "sophie@example.com",
    },
    {
        "key": "parent_phone",
        "label": "Telephone parent",
        "description": "Telephone du parent referent.",
        "example": "0601020304",
    },
    {
        "key": "parent_address",
        "label": "Adresse parent",
        "description": "Adresse du parent referent.",
        "example": "12 rue Victor Hugo, 75015 Paris",
    },
    {
        "key": "child_full_name",
        "label": "Nom enfant",
        "description": "Nom complet de l'eleve enfant.",
        "example": "Emma Dupont",
    },
    {
        "key": "child_birth_date",
        "label": "Date naissance enfant",
        "description": "Date de naissance de l'eleve enfant.",
        "example": "2017-03-11",
    },
    {
        "key": "services_count",
        "label": "Nombre activites",
        "description": "Nombre de lignes activites du devis.",
        "example": "2",
    },
    {
        "key": "products_count",
        "label": "Nombre produits",
        "description": "Nombre de produits du devis.",
        "example": "1",
    },
    {
        "key": "kits_count",
        "label": "Nombre kits",
        "description": "Nombre de kits du devis.",
        "example": "1",
    },
    {
        "key": "lines_count",
        "label": "Nombre total lignes",
        "description": "Nombre total de lignes du devis.",
        "example": "4",
    },
    {
        "key": "prospect_identity_block_html",
        "label": "Bloc identite prospect (HTML)",
        "description": "Bloc deja structure (adulte ou enfant/parent selon le type de prospect).",
        "example": "<p><strong>Eleve:</strong> Emma Dupont</p>",
    },
    {
        "key": "payment_method_block_html",
        "label": "Bloc mode de paiement (HTML)",
        "description": "Bloc compact avec le mode de paiement choisi.",
        "example": "<p><strong>Mode de paiement:</strong> Cheque en 4 fois</p>",
    },
    {
        "key": "solfege_block_html",
        "label": "Bloc solfege (HTML)",
        "description": "Bloc conditionnel: details solfege ou mention non souscrit.",
        "example": "<p>Solfege souscrit - Niveau 1</p>",
    },
    {
        "key": "masterclass_block_html",
        "label": "Bloc masterclass (HTML)",
        "description": "Bloc conditionnel: details masterclass ou mention non souscrite.",
        "example": "<p>Masterclass du samedi : non souscrite.</p>",
    },
    {
        "key": "pass_recup_block_html",
        "label": "Bloc Pass Recup (HTML)",
        "description": "Bloc conditionnel: details Pass Recup ou mention non souscrit.",
        "example": "<p>Option Pass Recup : non souscrite.</p>",
    },
    {
        "key": "services_table_html",
        "label": "Tableau activites (HTML)",
        "description": "Tableau HTML des activites du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "products_table_html",
        "label": "Tableau produits (HTML)",
        "description": "Tableau HTML des produits du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "kits_table_html",
        "label": "Tableau kits (HTML)",
        "description": "Tableau HTML des kits du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "lines_table_html",
        "label": "Tableau lignes (HTML)",
        "description": "Tableau HTML global des lignes du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "payment_schedule_table_html",
        "label": "Tableau echeancier (HTML)",
        "description": "Tableau HTML de l'echeancier de paiement.",
        "example": "<table>...</table>",
    },
    {
        "key": "calendar_table_html",
        "label": "Calendrier visuel (HTML)",
        "description": "Calendrier visuel par activite, semestres, mois et nombre de cours.",
        "example": "<div>1er semestre ...</div>",
    },
    {
        "key": "calendar_activity_semesters_html",
        "label": "Calendrier visuel par activite (HTML)",
        "description": "Alias du calendrier visuel par activite (1er/2e semestre).",
        "example": "<div>1er semestre ...</div>",
    },
    {
        "key": "calendar_sessions_table_html",
        "label": "Tableau seances detaillees (HTML)",
        "description": "Tableau detaille de toutes les seances (date/heure/modalite).",
        "example": "<table>...</table>",
    },
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_setting(db: Session) -> AppSetting | None:
    return db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_TEMPLATES_SETTING_KEY))


def _default_templates(now: datetime | None = None) -> list[QuoteTemplateRecord]:
    ts = (now or _utcnow()).isoformat()
    return [
        {
            "id": "quote-template-default-fr",
            "code": "QUOTE_DEFAULT_FR",
            "name": "Template devis FR",
            "language": "fr",
            "subject_template": "Votre devis {quote_number} Piano Academie",
            "body_template": (
                "Bonjour {recipient_name},\\n\\n"
                "Votre devis {quote_number} est pret.\\n"
                "Montant total: {total_ttc} {currency}.\\n"
                "Expiration: {expires_at}.\\n\\n"
                "Piano Academie"
            ),
            "is_active": True,
            "is_default": True,
            "created_at": ts,
            "updated_at": ts,
        }
    ]


def _sanitize_text(value: object, *, max_length: int, fallback: str = "") -> str:
    raw = str(value if value is not None else "").strip()
    if not raw:
        return fallback
    return raw[:max_length]


def _sanitize_language(value: object) -> str:
    raw = _sanitize_text(value, max_length=8, fallback="fr").lower()
    if not raw:
        return "fr"
    return raw


def _sanitize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    return default


def _sanitize_row(row: object, *, now_iso: str) -> QuoteTemplateRecord | None:
    if not isinstance(row, dict):
        return None
    identifier = _sanitize_text(row.get("id"), max_length=80)
    if not identifier:
        return None
    code = _sanitize_text(row.get("code"), max_length=80, fallback="QUOTE_TEMPLATE")
    name = _sanitize_text(row.get("name"), max_length=180, fallback="Template devis")
    language = _sanitize_language(row.get("language"))
    subject_template = _sanitize_text(row.get("subject_template"), max_length=255, fallback="Votre devis {quote_number}")
    body_template = _sanitize_text(row.get("body_template"), max_length=20000, fallback="{quote_number}")
    created_at = _sanitize_text(row.get("created_at"), max_length=64, fallback=now_iso)
    updated_at = _sanitize_text(row.get("updated_at"), max_length=64, fallback=now_iso)
    return {
        "id": identifier,
        "code": code,
        "name": name,
        "language": language,
        "subject_template": subject_template,
        "body_template": body_template,
        "is_active": _sanitize_bool(row.get("is_active"), default=True),
        "is_default": _sanitize_bool(row.get("is_default"), default=False),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _load_templates(db: Session) -> list[QuoteTemplateRecord]:
    setting = _read_setting(db)
    now_iso = _utcnow().isoformat()
    if setting is None or not setting.value.strip():
        return _default_templates()

    try:
        payload = json.loads(setting.value)
    except json.JSONDecodeError:
        return _default_templates()

    if not isinstance(payload, list):
        return _default_templates()

    rows = [item for item in (_sanitize_row(entry, now_iso=now_iso) for entry in payload) if item is not None]
    if not rows:
        return _default_templates()

    if not any(row["is_default"] for row in rows):
        rows[0]["is_default"] = True
    if not any(row["is_active"] for row in rows):
        rows[0]["is_active"] = True

    return rows


def _save_templates(db: Session, rows: list[QuoteTemplateRecord]) -> datetime:
    now = _utcnow()
    serialized = json.dumps(rows, ensure_ascii=True)
    setting = db.scalar(select(AppSetting).where(AppSetting.key == QUOTE_TEMPLATES_SETTING_KEY).with_for_update())
    if setting is None:
        db.add(AppSetting(key=QUOTE_TEMPLATES_SETTING_KEY, value=serialized, updated_at=now))
        return now
    setting.value = serialized
    setting.updated_at = now
    return now


def list_quote_template_variables() -> list[QuoteTemplateVariableDef]:
    return [dict(item) for item in QUOTE_TEMPLATE_VARIABLES]


def list_quote_templates(db: Session, *, active_only: bool = False) -> list[QuoteTemplateRecord]:
    rows = _load_templates(db)
    if active_only:
        rows = [row for row in rows if row["is_active"]]
    return rows


def find_quote_template(db: Session, *, template_id: str) -> QuoteTemplateRecord | None:
    identifier = _sanitize_text(template_id, max_length=80)
    if not identifier:
        return None
    for row in _load_templates(db):
        if row["id"] == identifier:
            return row
    return None


def upsert_quote_template(
    db: Session,
    *,
    template_id: str | None,
    code: str,
    name: str,
    language: str,
    subject_template: str,
    body_template: str,
    is_active: bool,
    is_default: bool,
) -> QuoteTemplateRecord:
    rows = _load_templates(db)
    now = _utcnow()
    now_iso = now.isoformat()

    normalized_id = _sanitize_text(template_id, max_length=80) if template_id else ""
    normalized_code = _sanitize_text(code, max_length=80, fallback="QUOTE_TEMPLATE")
    normalized_name = _sanitize_text(name, max_length=180, fallback="Template devis")
    normalized_language = _sanitize_language(language)
    normalized_subject = _sanitize_text(subject_template, max_length=255, fallback="Votre devis {quote_number}")
    normalized_body = _sanitize_text(body_template, max_length=20000, fallback="{quote_number}")

    existing_index: int | None = None
    for index, row in enumerate(rows):
        if row["id"] == normalized_id and normalized_id:
            existing_index = index
            break

    if existing_index is None:
        record_id = normalized_id or str(uuid4())
        row: QuoteTemplateRecord = {
            "id": record_id,
            "code": normalized_code,
            "name": normalized_name,
            "language": normalized_language,
            "subject_template": normalized_subject,
            "body_template": normalized_body,
            "is_active": is_active,
            "is_default": is_default,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        rows.append(row)
    else:
        row = rows[existing_index]
        row["code"] = normalized_code
        row["name"] = normalized_name
        row["language"] = normalized_language
        row["subject_template"] = normalized_subject
        row["body_template"] = normalized_body
        row["is_active"] = is_active
        row["is_default"] = is_default
        row["updated_at"] = now_iso

    if row["is_default"]:
        for item in rows:
            if item["id"] != row["id"]:
                item["is_default"] = False
    if not any(item["is_default"] for item in rows):
        row["is_default"] = True
    if not any(item["is_active"] for item in rows):
        row["is_active"] = True

    _save_templates(db, rows)
    return row


def delete_quote_template(db: Session, *, template_id: str) -> bool:
    identifier = _sanitize_text(template_id, max_length=80)
    if not identifier:
        return False

    rows = _load_templates(db)
    previous_length = len(rows)
    rows = [row for row in rows if row["id"] != identifier]
    if len(rows) == previous_length:
        return False
    if not rows:
        rows = _default_templates()
    if not any(item["is_default"] for item in rows):
        rows[0]["is_default"] = True
    if not any(item["is_active"] for item in rows):
        rows[0]["is_active"] = True
    _save_templates(db, rows)
    return True


def resolve_quote_template_for_quote(db: Session, *, template_id: str | None) -> QuoteTemplateRecord | None:
    rows = _load_templates(db)
    if template_id:
        wanted = _sanitize_text(template_id, max_length=80)
        for row in rows:
            if row["id"] == wanted and row["is_active"]:
                return row
    for row in rows:
        if row["is_default"] and row["is_active"]:
            return row
    for row in rows:
        if row["is_active"]:
            return row
    return rows[0] if rows else None
