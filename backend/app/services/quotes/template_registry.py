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
        "key": "recipient_phone",
        "label": "Telephone destinataire",
        "description": "Numero de telephone utilise pour les notifications SMS du devis.",
        "example": "+33601020304",
    },
    {
        "key": "total_ttc",
        "label": "Total TTC",
        "description": "Montant total TTC facture (apres avoir/dette).",
        "example": "1290.00",
    },
    {
        "key": "total_ttc_before_adjustment",
        "label": "Total TTC avant ajustement",
        "description": "Total TTC des lignes avant application de l'avoir/dette.",
        "example": "1320.00",
    },
    {
        "key": "total_ttc_before_adjustment_html",
        "label": "Ligne Total TTC avant ajustement (conditionnelle HTML)",
        "description": "Ligne HTML affichee uniquement si un avoir/dette est applique.",
        "example": "<p><strong>Total TTC avant ajustement :</strong> 1320,00 EUR</p>",
    },
    {
        "key": "total_ttc_after_adjustment",
        "label": "Total TTC apres ajustement",
        "description": "Alias explicite du total TTC facture (apres ajustement).",
        "example": "1290.00",
    },
    {
        "key": "total_ht",
        "label": "Total HT",
        "description": "Montant total HT facture (apres ajustement).",
        "example": "1050.00",
    },
    {
        "key": "total_ht_before_adjustment",
        "label": "Total HT avant ajustement",
        "description": "Montant HT calcule avant application de l'avoir/dette.",
        "example": "1075.00",
    },
    {
        "key": "total_ht_after_adjustment",
        "label": "Total HT apres ajustement",
        "description": "Alias explicite du total HT facture (apres ajustement).",
        "example": "1050.00",
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
        "description": "Montant TVA facture (apres ajustement).",
        "example": "215.00",
    },
    {
        "key": "vat_amount_before_adjustment",
        "label": "TVA avant ajustement",
        "description": "Montant TVA calcule avant application de l'avoir/dette.",
        "example": "215.00",
    },
    {
        "key": "vat_amount_after_adjustment",
        "label": "TVA apres ajustement",
        "description": "Alias explicite du montant TVA facture (apres ajustement).",
        "example": "210.00",
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
        "key": "expires_at_local",
        "label": "Expiration locale",
        "description": "Date et heure d expiration dans le fuseau horaire du devis.",
        "example": "31/08/2026 15:27",
    },
    {
        "key": "sent_at_local",
        "label": "Envoi local",
        "description": "Date et heure d envoi dans le fuseau horaire du devis.",
        "example": "07/03/2026 14:15",
    },
    {
        "key": "cancelled_at_local",
        "label": "Annulation locale",
        "description": "Date et heure d annulation dans le fuseau horaire du devis.",
        "example": "24/03/2026 07:00",
    },
    {
        "key": "quote_status",
        "label": "Code statut devis",
        "description": "Statut technique du devis.",
        "example": "sent",
    },
    {
        "key": "quote_status_label",
        "label": "Libelle statut devis",
        "description": "Libelle lisible du statut du devis.",
        "example": "Envoye",
    },
    {
        "key": "quote_public_url",
        "label": "Lien public devis",
        "description": "Lien public securise pour consulter le devis.",
        "example": "https://app.piano-academie.com/q/uuid?t=token",
    },
    {
        "key": "quote_pdf_url",
        "label": "Lien PDF devis",
        "description": "Lien public securise de telechargement du PDF.",
        "example": "https://app.piano-academie.com/api/v1/public/quotes/uuid/pdf?t=token",
    },
    {
        "key": "quote_timezone",
        "label": "Fuseau horaire devis",
        "description": "Fuseau horaire associe au devis, derive du lieu si possible.",
        "example": "Europe/Paris",
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
        "key": "financial_adjustment_type_label",
        "label": "Type ajustement financier",
        "description": "Aucun, Avoir ou Dette.",
        "example": "Avoir",
    },
    {
        "key": "financial_adjustment_amount_ttc",
        "label": "Montant ajustement TTC",
        "description": "Montant de l avoir ou de la dette.",
        "example": "100,00",
    },
    {
        "key": "financial_adjustment_display_title",
        "label": "Titre ajustement",
        "description": "Libelle affiche (libelle ajuste ou type Avoir/Dette).",
        "example": "Avoir au 30 juin 2025",
    },
    {
        "key": "financial_adjustment_display_line",
        "label": "Ligne ajustement prete",
        "description": "Texte pret a afficher, vide si aucun ajustement.",
        "example": "Avoir au 30 juin 2025 : 30,00 EUR",
    },
    {
        "key": "financial_adjustment_effective_date",
        "label": "Date ajustement",
        "description": "Date d effet de l ajustement (si renseignee).",
        "example": "15/09/2026",
    },
    {
        "key": "financial_adjustment_impact_label",
        "label": "Impact ajustement",
        "description": "Impact metier de l ajustement (deduit/ajoute au total facture).",
        "example": "Deduit du total facture",
    },
    {
        "key": "financial_adjustment_label",
        "label": "Libelle ajustement",
        "description": "Libelle libre associe a l ajustement.",
        "example": "Avoir fidelite",
    },
    {
        "key": "financial_adjustment_block_html",
        "label": "Bloc ajustement financier (HTML)",
        "description": "Bloc detail ajustement (avoir/dette), vide si aucun ajustement.",
        "example": "<p><strong>Avoir</strong> : 100,00 EUR</p>",
    },
    {
        "key": "financial_adjustment_section_html",
        "label": "Section ajustement (HTML)",
        "description": "Section complete (titre + details), vide si aucun ajustement.",
        "example": "<h2>Ajustement financier</h2><p><strong>Avoir</strong> : 100,00 EUR</p>",
    },
    {
        "key": "financial_adjustment_none_html",
        "label": "Bloc aucun ajustement (HTML)",
        "description": "Texte de fallback si aucun ajustement n est applique.",
        "example": "<p>Aucun avoir ou dette applique.</p>",
    },
    {
        "key": "financial_recap_block_html",
        "label": "Bloc recapitulatif financier (HTML)",
        "description": "Bloc complet pret a l affichage (totaux et ajustement), stable pour PDF/apercu.",
        "example": "<div class='quote-block'><h2>Recapitulatif financier</h2>...</div>",
    },
    {
        "key": "has_financial_adjustment",
        "label": "Ajustement present",
        "description": "Flag true/false si un avoir ou une dette est applique.",
        "example": "true",
    },
    {
        "key": "has_credit_adjustment",
        "label": "Avoir present",
        "description": "Flag true/false si l ajustement est un avoir.",
        "example": "true",
    },
    {
        "key": "has_debt_adjustment",
        "label": "Dette presente",
        "description": "Flag true/false si l ajustement est une dette.",
        "example": "false",
    },
    {
        "key": "total_before_adjustment",
        "label": "Total avant ajustement",
        "description": "Total TTC des lignes avant application de l avoir/dette.",
        "example": "450,00",
    },
    {
        "key": "total_after_adjustment",
        "label": "Total TTC facture",
        "description": "Total TTC final facture apres ajustement financier.",
        "example": "350,00",
    },
    {
        "key": "has_deposit",
        "label": "Acompte active",
        "description": "Flag true/false si un acompte de preinscription est applique.",
        "example": "true",
    },
    {
        "key": "deposit_enabled",
        "label": "Acompte active (alias)",
        "description": "Alias de has_deposit pour compatibilite des templates.",
        "example": "true",
    },
    {
        "key": "deposit_amount_ttc",
        "label": "Montant acompte TTC",
        "description": "Montant TTC de l acompte a regler en ligne.",
        "example": "200,00",
    },
    {
        "key": "deposit_ht_amount",
        "label": "Montant acompte HT",
        "description": "Part HT de l acompte.",
        "example": "166,67",
    },
    {
        "key": "deposit_vat_amount",
        "label": "Montant TVA acompte",
        "description": "Part TVA de l acompte.",
        "example": "33,33",
    },
    {
        "key": "remaining_ttc_after_deposit",
        "label": "Reste TTC apres acompte",
        "description": "Montant TTC restant a payer via le plan de paiement apres acompte.",
        "example": "800,00",
    },
    {
        "key": "remaining_ht_after_deposit",
        "label": "Reste HT apres acompte",
        "description": "Montant HT restant a payer apres acompte.",
        "example": "666,67",
    },
    {
        "key": "remaining_vat_after_deposit",
        "label": "Reste TVA apres acompte",
        "description": "Montant TVA restant a payer apres acompte.",
        "example": "133,33",
    },
    {
        "key": "deposit_block_html",
        "label": "Bloc acompte (HTML)",
        "description": "Bloc HTML court de l acompte (vide si acompte non active).",
        "example": "<p><strong>Acompte preinscription :</strong> 200,00 EUR</p>",
    },
    {
        "key": "deposit_section_html",
        "label": "Section acompte (HTML)",
        "description": "Section complete Acompte preinscription (vide si acompte non active).",
        "example": "<h2>Acompte preinscription</h2><p>...</p>",
    },
    {
        "key": "deposit_none_html",
        "label": "Bloc aucun acompte (HTML)",
        "description": "Texte de fallback quand aucun acompte n est active.",
        "example": "<p>Aucun acompte de preinscription.</p>",
    },
    {
        "key": "payment_instruction",
        "label": "Consignes de paiement",
        "description": "Consigne textuelle associee au plan de paiement (envoi cheques, adresse, etc.).",
        "example": "Tous les cheques doivent etre envoyes en meme temps a Piano Academie.",
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
        "label": "Nom adulte responsable",
        "description": "Nom complet de l adulte responsable.",
        "example": "Sophie Dupont",
    },
    {
        "key": "parent_email",
        "label": "Email adulte responsable",
        "description": "Email de l adulte responsable.",
        "example": "sophie@example.com",
    },
    {
        "key": "parent_phone",
        "label": "Telephone adulte responsable",
        "description": "Telephone de l adulte responsable.",
        "example": "0601020304",
    },
    {
        "key": "parent_address",
        "label": "Adresse adulte responsable",
        "description": "Adresse de l adulte responsable.",
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
        "description": "Bloc deja structure (enfant + adulte responsable, ou adulte responsable seul).",
        "example": "<p><strong>Eleve:</strong> Emma Dupont</p>",
    },
    {
        "key": "payment_method_block_html",
        "label": "Bloc mode de paiement (HTML)",
        "description": "Bloc compact avec le mode de paiement choisi.",
        "example": "<p><strong>Mode de paiement:</strong> Cheque en 4 fois</p>",
    },
    {
        "key": "pass_recup_block_html",
        "label": "Bloc Pass Recup (HTML)",
        "description": "Bloc conditionnel: details Pass Recup, vide si non souscrit.",
        "example": "<p>Option Pass Recup : souscrite.</p>",
    },
    {
        "key": "options_section_html",
        "label": "Section options (HTML)",
        "description": "Section complete (titre + options souscrites) masquee automatiquement si vide.",
        "example": "<h2>Vos options</h2><p>Option Pass Recup : souscrite.</p>",
    },
    {
        "key": "services_table_html",
        "label": "Tableau activites (HTML)",
        "description": "Tableau HTML des activites du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "activities_planning_table_html",
        "label": "Tableau planning activites (HTML)",
        "description": "Tableau type activite, lieu, jour, horaire et duree (issu des blocs planning du devis).",
        "example": "<table>...</table>",
    },
    {
        "key": "activities_planning_section_html",
        "label": "Section activites retenues (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Les Activites retenues</h2><table>...</table>",
    },
    {
        "key": "products_table_html",
        "label": "Tableau materiel (HTML)",
        "description": "Tableau HTML du materiel du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "kits_table_html",
        "label": "Tableau kits (HTML)",
        "description": "Tableau HTML des kits du devis.",
        "example": "<table>...</table>",
    },
    {
        "key": "adjustments_table_html",
        "label": "Tableau remises/supplements (HTML)",
        "description": "Tableau HTML dedie aux remises et supplements (separe du materiel).",
        "example": "<table>...</table>",
    },
    {
        "key": "services_section_html",
        "label": "Section prestations (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Prestations</h2><table>...</table>",
    },
    {
        "key": "adjustments_section_html",
        "label": "Section remises et supplements (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Remises et supplements</h2><table>...</table>",
    },
    {
        "key": "products_section_html",
        "label": "Section materiel (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Materiel</h2><table>...</table>",
    },
    {
        "key": "kits_section_html",
        "label": "Section kits (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Kits</h2><table>...</table>",
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
        "key": "payment_schedule_section_html",
        "label": "Section echeancier (HTML)",
        "description": "Section complete (titre + tableau) masquee automatiquement si vide.",
        "example": "<h2>Echeancier de paiement</h2><table>...</table>",
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
        "key": "calendar_section_html",
        "label": "Section calendrier des cours (HTML)",
        "description": "Section complete (titre + calendrier) masquee automatiquement si vide.",
        "example": "<h2>Calendrier des cours</h2><div>...</div>",
    },
    {
        "key": "calendar_sessions_table_html",
        "label": "Tableau seances detaillees (HTML)",
        "description": "Tableau detaille de toutes les seances (date/heure/modalite).",
        "example": "<table>...</table>",
    },
    {
        "key": "document_style_html",
        "label": "Style documentaire (HTML)",
        "description": "Feuille de style print-safe (tables lisibles, sauts de page, blocs).",
        "example": "<style>...</style>",
    },
    {
        "key": "brand_logo_html",
        "label": "Logo Piano Academie (HTML)",
        "description": "Bloc logo/wordmark a inserer sur la couverture ou dans les en-tetes.",
        "example": "<div class='quote-brand-logo'>PIANO<br/>ACADEMIE</div>",
    },
    {
        "key": "header_standard_html",
        "label": "Entete standard (HTML)",
        "description": "Entete avec logo et numero de devis, reutilisable en haut de page.",
        "example": "<table class='quote-header'>...</table>",
    },
    {
        "key": "cover_page_standard_html",
        "label": "Couverture standard (HTML)",
        "description": "Page de couverture precomposee avec logo et informations dossier.",
        "example": "<section class='quote-cover'>...</section>",
    },
    {
        "key": "page_break_html",
        "label": "Saut de page (HTML)",
        "description": "Bloc HTML pour forcer un saut de page dans le PDF.",
        "example": "<div style='page-break-before:always;'></div>",
    },
    {
        "key": "footer_standard_html",
        "label": "Pied de page standard (HTML)",
        "description": "Pied de page Piano Academie pret a inserer.",
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
