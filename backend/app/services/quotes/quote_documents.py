from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape, unescape as html_unescape
from html.parser import HTMLParser
import io
import logging
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session
from xhtml2pdf import pisa

from app.models.ops import AppSetting
from app.models.product_catalog import CatalogKit, CatalogKitItem, CatalogProduct
from app.models.quote import Prospect, Quote, QuoteLine, QuoteTemplate, QuoteTemplateVersion, TermsTemplateVersion
from app.models.typeform_intake import TypeformIntake
from app.models.user import User


AUDIENCE_ADMIN_PREVIEW = "admin_preview"
AUDIENCE_PUBLIC_PAGE = "public_page"
AUDIENCE_CLIENT_PDF = "client_pdf"
DEFAULT_AUDIENCE = AUDIENCE_CLIENT_PDF
ACCOUNT_LOGO_SETTING_KEY = "config_account_logo_data_url"
logger = logging.getLogger(__name__)
CSS_VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*(?:,\s*([^)]+?)\s*)?\)")
CSS_VAR_DEFAULTS: dict[str, str] = {
    "--line-soft": "#d6d9de",
    "--line": "#cfd3da",
    "--ink": "#1f1f1f",
    "--text": "#1f1f1f",
    "--text-muted": "#6b7280",
    "--muted": "#6b7280",
    "--bg": "#ffffff",
    "--panel": "#ffffff",
    "--panel-2": "#f9fafb",
    "--accent": "#c9872a",
    "--accent-ink": "#ffffff",
}


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _typeform_parent_address_from_normalized_payload(normalized: dict[str, Any]) -> str:
    normalized = _json_object(normalized)
    direct = str(normalized.get("parent_address") or "").strip()
    if direct:
        return direct
    line_1 = str(normalized.get("parent_address_line_1") or "").strip()
    line_2 = str(normalized.get("parent_address_line_2") or "").strip()
    city = str(normalized.get("parent_city") or "").strip()
    postal_code = str(normalized.get("parent_postal_code") or "").strip()
    country = str(normalized.get("parent_country") or "").strip()
    locality = " ".join(part for part in [postal_code, city] if part).strip()
    parts = [part for part in [line_1, line_2, locality or None, country] if part]
    return ", ".join(parts)


def _typeform_simplified_answer_value(simplified_answers: list[Any], *labels: str) -> str:
    expected = {str(label or "").strip().lower() for label in labels if str(label or "").strip()}
    if not expected:
        return ""
    for item in simplified_answers:
        row = _json_object(item)
        label = str(row.get("label") or row.get("field_label") or row.get("question") or "").strip().lower()
        if label not in expected:
            continue
        value = str(row.get("value") or "").strip()
        if value:
            return value
    return ""


def _typeform_parent_address_from_intake(intake: TypeformIntake | None) -> str:
    if intake is None:
        return ""
    parent_address = _typeform_parent_address_from_normalized_payload(_json_object(intake.normalized_payload_json)).strip()
    if parent_address:
        return parent_address
    simplified_answers = _json_list(intake.simplified_response_json)
    line_1 = _typeform_simplified_answer_value(simplified_answers, "Address", "address", "Adresse", "adresse")
    line_2 = _typeform_simplified_answer_value(
        simplified_answers,
        "Address line 2",
        "address line 2",
        "Adresse ligne 2",
        "Complement d'adresse",
        "Complément d'adresse",
    )
    city = _typeform_simplified_answer_value(simplified_answers, "City/Town", "city/town", "Ville", "ville")
    postal_code = _typeform_simplified_answer_value(
        simplified_answers,
        "Zip/Post Code",
        "zip/post code",
        "Code postal",
        "code postal",
    )
    country = _typeform_simplified_answer_value(simplified_answers, "Country", "country", "Pays", "pays")
    locality = " ".join(part for part in [postal_code, city] if part).strip()
    parts = [part for part in [line_1, line_2, locality or None, country] if part]
    return ", ".join(parts)


def _typeform_parent_address_from_quote(*, db: Session | None, quote: Quote) -> str:
    quote_meta = _json_object(quote.meta)
    typeform_meta = _json_object(quote_meta.get("typeform_intake"))
    parent_address = _typeform_parent_address_from_normalized_payload(_json_object(typeform_meta.get("normalized_payload"))).strip()
    if parent_address:
        return parent_address
    intake_id = str(typeform_meta.get("intake_id") or "").strip()
    if not intake_id and db is not None and quote.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
        if prospect is not None:
            prospect_meta = _json_object(prospect.meta)
            intake_id = str(prospect_meta.get("typeform_intake_id") or "").strip()
    if db is None or not intake_id:
        return ""
    try:
        intake_uuid = UUID(intake_id)
    except ValueError:
        return ""
    intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == intake_uuid))
    return _typeform_parent_address_from_intake(intake)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decimal_str(value: Decimal) -> str:
    amount = Decimal(value or Decimal("0")).quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",")


def _decimal_from_any(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return default
    if not parsed.is_finite():
        return default
    return parsed


def _split_ttc_with_rate(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    ttc_amount = Decimal(total_ttc or Decimal("0")).quantize(Decimal("0.01"))
    rate = Decimal(vat_rate or Decimal("0")).quantize(Decimal("0.01"))
    if rate <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    divisor = Decimal("1.00") + (rate / Decimal("100"))
    if divisor <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    ht_amount = (ttc_amount / divisor).quantize(Decimal("0.01"))
    vat_amount = (ttc_amount - ht_amount).quantize(Decimal("0.01"))
    return ht_amount, vat_amount


def _resolve_display_vat_rate(
    *,
    quote: Quote,
    lines: list[QuoteLine],
    total_ht: Decimal,
    total_vat: Decimal,
) -> Decimal:
    non_zero_line_rates = {
        Decimal(getattr(line, "vat_rate", 0) or 0).quantize(Decimal("0.01"))
        for line in lines
        if Decimal(getattr(line, "amount_ttc", 0) or 0) != Decimal("0.00")
    }
    if len(non_zero_line_rates) == 1:
        return next(iter(non_zero_line_rates))

    explicit_quote_rate = _decimal_from_any(quote.vat_rate, default=Decimal("-1"))
    if explicit_quote_rate >= Decimal("0.00"):
        return explicit_quote_rate.quantize(Decimal("0.01"))

    quote_meta = _json_object(quote.meta)
    explicit_meta_rate = _decimal_from_any(quote_meta.get("tva_rate"), default=Decimal("-1"))
    if explicit_meta_rate >= Decimal("0.00"):
        return explicit_meta_rate.quantize(Decimal("0.01"))

    if total_ht <= Decimal("0.00"):
        return Decimal("0.00")
    return ((total_vat / total_ht) * Decimal("100")).quantize(Decimal("0.01"))


def _money(value: Decimal, currency: str) -> str:
    return f"{_decimal_str(value)} {currency}"


def _compact_quantity_label(value: Any) -> str:
    quantity = _decimal_from_any(value, Decimal("0"))
    if quantity == quantity.to_integral_value():
        return str(int(quantity))
    return _decimal_str(quantity)


def _schedule_due_label(item: dict[str, Any]) -> str:
    due_type = str(item.get("due_type") or "").strip().lower()
    due_label = str(item.get("due_label") or "").strip()
    normalized = due_label.lower()
    if due_type == "on_registration":
        return "à réception de votre facture"
    if due_type == "on_quote_validation_before_first_course":
        return "à la validation du devis, avant votre 1er cours"
    if normalized in {
        "a reception",
        "a reception du dossier",
        "a reception de votre facture",
        "à reception",
        "à reception du dossier",
        "à reception de votre facture",
        "à réception",
        "à réception du dossier",
        "à réception de votre facture",
    }:
        return "à réception de votre facture"
    if normalized in {
        "a la validation du devis, avant votre 1er cours",
        "à la validation du devis, avant votre 1er cours",
    }:
        return "à la validation du devis, avant votre 1er cours"
    if due_label:
        return due_label
    return due_type or "-"


def _payment_schedule_method_subject(method_label: str, *, count: int) -> str:
    normalized = str(method_label or "").strip().lower()
    if "virement" in normalized:
        return "virement bancaire"
    if "cheque" in normalized or "chèque" in normalized:
        return "cheque" if count == 1 else "cheques"
    if "carte" in normalized:
        return "reglement par carte bancaire"
    return "reglement"


def _is_bank_transfer_payment_method(method_label: str) -> bool:
    return "virement" in str(method_label or "").strip().lower()


def _is_card_payment_method(method_label: str) -> bool:
    return "carte" in str(method_label or "").strip().lower()


def _bank_transfer_deposit_schedule_lines(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
) -> list[str]:
    if not has_deposit or deposit_amount_ttc <= Decimal("0.00") or remaining_ttc_after_deposit <= Decimal("0.00"):
        return []
    if len(schedule) != 1:
        return []
    item = schedule[0]
    item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
    if not _is_bank_transfer_payment_method(item_method_label):
        return []
    if _schedule_due_label(item) != "à réception de votre facture":
        return []
    deposit_amount = _money(deposit_amount_ttc, currency)
    remaining_amount = _money(remaining_ttc_after_deposit, currency)
    return [
        f"Afin de bloquer définitivement le créneau, un acompte de {deposit_amount} devra être réglé par virement bancaire dès validation du devis.",
        "Une facture d’acompte sera émise après validation du devis.",
        f"Le solde de {remaining_amount} devra être réglé par virement bancaire à réception de la facture de solde, avant le démarrage des cours.",
    ]


def _card_deposit_schedule_lines(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
) -> list[str]:
    if not has_deposit or deposit_amount_ttc <= Decimal("0.00") or remaining_ttc_after_deposit <= Decimal("0.00"):
        return []
    if len(schedule) != 1:
        return []
    item = schedule[0]
    item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
    if not _is_card_payment_method(item_method_label):
        return []
    if _schedule_due_label(item) != "à réception de votre facture":
        return []
    deposit_amount = _money(deposit_amount_ttc, currency)
    remaining_amount = _money(remaining_ttc_after_deposit, currency)
    return [
        f"Paiement d’un acompte de {deposit_amount} dès validation du devis, afin de bloquer le créneau.",
        "Une facture d’acompte sera envoyée et devra être réglée rapidement après validation en ligne.",
        f"Le solde de {remaining_amount} devra être réglé par carte bancaire à réception de la facture correspondante, avant le démarrage des cours.",
    ]


def _payment_schedule_summary_text(
    *,
    schedule: list[dict[str, Any]],
    has_deposit: bool,
    deposit_amount_ttc: Decimal,
    currency: str,
    payment_method_label: str,
    remaining_ttc_after_deposit: Decimal,
) -> str:
    if special_lines := _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=payment_method_label,
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
    ):
        return " ".join(special_lines)
    if special_lines := _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=payment_method_label,
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
    ):
        return " ".join(special_lines)

    if schedule:
        if len(schedule) == 1:
            item = schedule[0]
            amount = _money(
                _decimal_from_any(item.get("amount_ttc"), Decimal("0.00")),
                str(item.get("currency") or currency or "EUR"),
            )
            item_method_label = str(item.get("payment_method") or payment_method_label or "").strip()
            method_subject = _payment_schedule_method_subject(item_method_label, count=1)
            due_label = _schedule_due_label(item)
            if _is_bank_transfer_payment_method(item_method_label) and due_label == "à réception de votre facture":
                remaining_sentence = (
                    f"reglement du solde de {amount} par virement bancaire à réception de votre facture, "
                    "avant le démarrage des cours"
                )
            else:
                remaining_sentence = f"{method_subject} de {amount} à regler {due_label}"
            if has_deposit:
                return (
                    f"Paiement de l acompte de {_decimal_str(deposit_amount_ttc)} {currency} dès validation du devis "
                    "pour bloquer le créneau, puis "
                    f"{remaining_sentence}."
                )
            return f"{remaining_sentence}."

        unit_label = "échéances"
        if has_deposit:
            return (
                f"Paiement de l acompte de {_decimal_str(deposit_amount_ttc)} {currency} dès validation du devis "
                "pour bloquer le créneau, "
                f"puis echeancier de {len(schedule)} {unit_label} selon le detail ci-dessous."
            )
        return f"Echeancier de {len(schedule)} {unit_label} selon le detail ci-dessous."

    if has_deposit and remaining_ttc_after_deposit <= Decimal("0.00"):
        return (
            f"Paiement de l acompte de {_decimal_str(deposit_amount_ttc)} {currency} dès validation du devis "
            "pour bloquer le créneau "
            "(solde regle)."
        )
    return "Paiement non planifié"


def _name(first_name: str | None, last_name: str | None, fallback: str = "-") -> str:
    value = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return value or fallback


def _date_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y")


def _datetime_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")


def _paris_datetime_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    try:
        paris_zone = ZoneInfo("Europe/Paris")
    except Exception:
        paris_zone = timezone.utc
    return value.astimezone(paris_zone).strftime("%d/%m/%Y %H:%M")


def _quote_status_date_display(quote: Quote) -> tuple[str, str, str]:
    normalized_status = str(quote.status or "").strip().lower()
    if normalized_status == "approved" and quote.approved_at is not None:
        approval_value = _paris_datetime_label(quote.approved_at)
        return ("Approuvé le", approval_value, f"Approuvé le {approval_value}")
    expiry_value = _date_label(quote.expires_at)
    return ("Validité", expiry_value, f"Valable jusqu’au {expiry_value}")


def _replace_expiration_mentions_for_approved_quote(content: str, quote: Quote) -> str:
    normalized_status = str(quote.status or "").strip().lower()
    if normalized_status != "approved" or quote.approved_at is None:
        return content
    rendered = str(content or "")
    if not rendered:
        return rendered
    expiry_value = _date_label(quote.expires_at)
    approval_value = _paris_datetime_label(quote.approved_at)
    replacements = {
        f"Validité : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Validite : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Validité : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Validite : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Expiration : <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Expiration: <strong>{expiry_value}</strong>": f"Approuvé le : <strong>{approval_value}</strong>",
        f"Expiration : {expiry_value}": f"Approuvé le : {approval_value}",
        f"Expiration: {expiry_value}": f"Approuvé le : {approval_value}",
        f"Valable jusqu’au {expiry_value}": f"Approuvé le {approval_value}",
        f"Valable jusqu au {expiry_value}": f"Approuvé le {approval_value}",
    }
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    return rendered


def _birth_date_label(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def _document_style_html() -> str:
    return (
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.4;}"
        "h1,h2,h3{color:#111827;margin:0 0 8px 0;page-break-after:avoid;}"
        "p{margin:0 0 8px 0;}"
        ".quote-muted{color:#5b6470;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-identity-grid{display:block;width:100%;}"
        ".quote-identity-card{border:1px solid #d3dbe7;background:#ffffff;padding:10px 12px;margin:0 0 10px 0;page-break-inside:avoid;}"
        ".quote-identity-card h3{margin:0 0 8px 0;font-size:13px;color:#111827;}"
        ".quote-identity-meta{width:100%;border-collapse:collapse;font-size:11px;}"
        ".quote-identity-meta td{padding:6px 8px;border-bottom:1px solid #edf2f7;vertical-align:top;}"
        ".quote-identity-meta tr:last-child td{border-bottom:none;}"
        ".quote-identity-meta td:first-child{width:36%;font-weight:700;color:#1f2937;background:#f8fafc;}"
        ".quote-header{width:100%;border-collapse:collapse;margin:0 0 10px 0;}"
        ".quote-header td{vertical-align:top;}"
        ".quote-brand-logo{display:inline-block;min-width:84px;padding:7px 9px;background:#111111;color:#d2b04c;font-size:10px;line-height:1.2;font-weight:700;letter-spacing:0.5px;text-align:center;}"
        ".quote-brand-logo-img{display:inline-block;max-width:140px;max-height:70px;object-fit:contain;}"
        ".quote-cover{text-align:center;min-height:220mm;padding-top:30mm;}"
        ".quote-cover-title{font-size:28px;letter-spacing:0.3px;text-transform:uppercase;margin-bottom:6mm;}"
        ".quote-cover-subtitle{font-size:14px;color:#4b5563;margin-bottom:9mm;}"
        ".quote-cover-name{font-size:22px;margin-bottom:4mm;}"
        ".quote-cover-meta{font-size:12px;color:#4b5563;line-height:1.6;}"
        ".quote-table{width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;}"
        ".quote-table thead{display:table-header-group;}"
        ".quote-table tfoot{display:table-footer-group;}"
        ".quote-table tr{page-break-inside:avoid;}"
        ".quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td>*{margin-top:0;margin-bottom:0;}"
        "font[size='10']{font-size:10px !important;line-height:1.45 !important;color:#6b7280 !important;}"
        ".quote-footer{width:100%;border-collapse:collapse;margin-top:12px;padding-top:8px;border-top:1px solid #cdd4de;font-size:10px;color:#475467;}"
        ".quote-footer td{vertical-align:top;}"
        ".quote-terms-title{margin-top:0;}"
        "</style>"
    )


def _account_logo_data_url(*, db: Session | None) -> str:
    if db is None:
        return ""
    row = db.scalar(select(AppSetting).where(AppSetting.key == ACCOUNT_LOGO_SETTING_KEY))
    if row is None:
        return ""
    value = str(row.value or "").strip()
    if not value.lower().startswith("data:image/"):
        return ""
    return value


def _brand_logo_html(*, db: Session | None, variant: str = "header") -> str:
    logo_data_url = _account_logo_data_url(db=db)
    if logo_data_url:
        width_px = "118" if variant == "cover" else "86"
        return (
            "<img "
            "class='quote-brand-logo-img' "
            f"src='{escape(logo_data_url)}' "
            f"width='{width_px}' "
            "style='display:block;width:auto;height:auto;' "
            "alt='Piano Academie'/>"
        )
    return "<div class='quote-brand-logo'>PIANO<br/>ACADEMIE</div>"


MONTH_LABELS_FR = (
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)


def _session_date_parts(value: object) -> tuple[int, int, int] | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if parsed is None:
        return None
    year = int(parsed.group(1))
    month = int(parsed.group(2))
    day = int(parsed.group(3))
    if year < 1900 or year > 3000 or month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return year, month, day


def _session_month_day(value: object) -> tuple[int, int] | None:
    parsed = _session_date_parts(value)
    if parsed is None:
        return None
    _, month, day = parsed
    return month, day


def _calendar_semester_rows(month_map: dict[tuple[int, int], set[int]], *, semester: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for year, month in sorted(month_map.keys()):
        if semester == 1 and not (month >= 9 or month <= 1):
            continue
        if semester == 2 and not (2 <= month <= 8):
            continue
        days = sorted(month_map.get((year, month)) or set())
        if not days:
            continue
        rows.append((f"{MONTH_LABELS_FR[month - 1]} {year}", ", ".join(str(day) for day in days)))
    return rows


def _calendar_group_heading(title: Any, index: int) -> str:
    cleaned = str(title or "").strip()
    if not cleaned or cleaned.lower() in {"activite", "activité", "cours"}:
        return f"Cours {index}"
    return cleaned


def _calendar_summary_text(*, session_count: int, activity_count: int) -> str:
    if session_count <= 0:
        return "Aucune séance planifiée"
    session_label = "séance planifiée" if session_count == 1 else "séances planifiées"
    activity_label = "activité" if activity_count == 1 else "activités"
    return f"{session_count} {session_label} pour {activity_count} {activity_label}"


def _calendar_visual_summary(sessions: list[dict[str, Any]]) -> tuple[str, int]:
    grouped: dict[str, dict[tuple[int, int], set[int]]] = {}
    for session in sessions:
        parsed = _session_date_parts(session.get("date"))
        if parsed is None:
            continue
        year, month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or "Cours"
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        if title not in grouped:
            grouped[title] = {}
        if (year, month) not in grouped[title]:
            grouped[title][(year, month)] = set()
        grouped[title][(year, month)].add(day)

    if not grouped:
        return "<p>Aucune séance planifiée.</p>", 0

    blocks: list[str] = []
    for index, title in enumerate(sorted(grouped.keys()), start=1):
        heading = _calendar_group_heading(title, index)
        month_map = grouped[title]
        count = sum(len(values) for values in month_map.values())
        sem1 = _calendar_semester_rows(month_map, semester=1)
        sem2 = _calendar_semester_rows(month_map, semester=2)

        semester_rows: list[tuple[str, str, str]] = []
        for month_label, days in sem1:
            semester_rows.append(("1er semestre", month_label, days))
        for month_label, days in sem2:
            semester_rows.append(("2e semestre", month_label, days))
        if not semester_rows:
            semester_rows.append(("-", "-", "Aucune séance"))
        semesters_html = "".join(
            "<tr>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'>{escape(semester)}</td>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'><strong>{escape(month_label)}</strong></td>"
            f"<td valign='top' style='border:1px solid #d8dee7;padding:10px;vertical-align:top;'>{escape(days)}</td>"
            "</tr>"
            for semester, month_label, days in semester_rows
        )

        separator_html = (
            "<div style='height:8px;margin:6px 0 10px 0;border-top:2px dashed #d8deea;'></div>"
            if index > 1
            else ""
        )
        blocks.append(
            separator_html
            + "<div style='border:2px solid #cfd6e2;padding:0;margin:0 0 22px 0;page-break-inside:auto;background:#ffffff;'>"
            "<div style='background:#f8fafc;border-bottom:1px solid #d6d9de;padding:8px 10px;font-weight:700;color:#0f172a;'>"
            f"{escape(heading)}"
            "</div>"
            "<div style='padding:8px;'>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0 0 8px 0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#DDE8FA' "
            "style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:left;font-weight:700;'>Cours / lieu</td>"
            "<td bgcolor='#DDE8FA' align='right' "
            "style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:right;font-weight:700;'>Nombre de cours</td>"
            "</tr>"
            f"<tr><td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{escape(heading)}</strong></td><td align='right' valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{count} cours</strong></td></tr>"
            "</tbody>"
            "</table>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#EEF3FC' width='22%' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Semestre</td>"
            "<td bgcolor='#EEF3FC' width='24%' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Mois</td>"
            "<td bgcolor='#EEF3FC' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Dates de cours</td>"
            "</tr>"
            f"{semesters_html}"
            "</tbody>"
            "</table>"
            "</div>"
            "</div>"
        )

    return "".join(blocks), len(grouped)


def _table_html(headers: list[str], rows: list[list[Any]], *, empty_label: str) -> str:
    if not rows:
        return ""

    def _cell_html(value: Any) -> str:
        if isinstance(value, dict):
            raw_html = value.get("html")
            if raw_html is not None:
                return str(raw_html)
            if "text" in value:
                return escape(str(value.get("text") or ""))
        return escape(str(value if value is not None else "-"))

    head = "".join(
        "<th bgcolor='#E7EDF7' "
        "style='background-color:#E7EDF7;color:#111827;border:1px solid #c2ccda;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;text-align:left;font-weight:700;line-height:1.4;vertical-align:middle;height:auto;white-space:nowrap;word-break:normal;overflow-wrap:normal;'>"
        f"{escape(cell)}"
        "</th>"
        for cell in headers
    )
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            + "".join(
                "<td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;vertical-align:middle;color:#111827;line-height:1.45;height:auto;white-space:normal;word-break:normal;overflow-wrap:break-word;'>"
                f"{_cell_html(cell)}"
                "</td>"
                for cell in row
            )
            + "</tr>"
        )
    body = "".join(body_rows)
    return (
        "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
        "style='width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def _section_html(title: str, content_html: str, *, level: int = 2) -> str:
    content = str(content_html or "").strip()
    if not content:
        return ""
    tag = "h3" if level == 3 else "h2"
    return f"<{tag}>{escape(title)}</{tag}>{content}"


def _weekday_label(value: Any) -> str:
    labels = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
    try:
        day = int(value)
    except (TypeError, ValueError):
        return "-"
    if day < 0 or day > 6:
        return "-"
    return labels[day]


def _parse_hhmm_to_minutes(value: Any) -> int | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^(\d{2}):(\d{2})$", raw)
    if parsed is None:
        return None
    hours = int(parsed.group(1))
    minutes = int(parsed.group(2))
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return hours * 60 + minutes


def _duration_label(*, start_time: Any, end_time: Any, fallback_minutes: Any) -> str:
    try:
        fallback = int(fallback_minutes)
    except (TypeError, ValueError):
        fallback = 0
    if fallback > 0:
        return f"{fallback} min"
    start_minutes = _parse_hhmm_to_minutes(start_time)
    end_minutes = _parse_hhmm_to_minutes(end_time)
    if start_minutes is None or end_minutes is None:
        return "-"
    delta = end_minutes - start_minutes
    if delta <= 0:
        delta += 24 * 60
    return f"{delta} min"


def _modality_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Cours"
    mapping = {
        "ONLINE": "En ligne",
        "ONSITE": "Présentiel",
        "HYBRID": "Hybride",
    }
    return mapping.get(raw.upper(), raw)


def _slot_mode_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    mapping = {
        "ONLINE": "Mode : cours en ligne",
        "ONSITE": "Mode : cours en présentiel",
        "HYBRID": "Mode : cours en présentiel ou en ligne",
        "ANY": "",
    }
    return mapping.get(raw.upper(), "")


def _extract_slot_label_parts(value: Any) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    cleaned_parts: list[str] = []
    mode_label = ""
    for part in raw.split("·"):
        text = " ".join(part.strip().split())
        if not text:
            continue
        normalized = text.casefold()
        upper = text.upper()
        if upper == "ANY":
            continue
        if normalized in {
            "online",
            "en ligne",
            "cours en ligne",
            "mode : cours en ligne",
            "mode: cours en ligne",
            "mode : en ligne",
            "mode: en ligne",
        }:
            mode_label = "Mode : cours en ligne"
            continue
        if normalized in {
            "onsite",
            "présentiel",
            "presentiel",
            "cours en présentiel",
            "cours en presentiel",
            "mode : cours en présentiel",
            "mode : cours en presentiel",
            "mode: cours en présentiel",
            "mode: cours en presentiel",
        }:
            mode_label = "Mode : cours en présentiel"
            continue
        if normalized in {
            "hybrid",
            "hybride",
            "mode : cours en présentiel ou en ligne",
            "mode: cours en présentiel ou en ligne",
        }:
            mode_label = "Mode : cours en présentiel ou en ligne"
            continue
        cleaned_parts.append(text)
    return " · ".join(cleaned_parts), mode_label


def _sanitize_slot_label_text(value: Any) -> str:
    cleaned_label, mode_label = _extract_slot_label_parts(value)
    if cleaned_label and mode_label:
        return f"{cleaned_label} · {mode_label}"
    return cleaned_label or mode_label or str(value or "").strip()


def _replace_word_preserving_case(value: str, pattern: str, replacement: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        matched = match.group(0)
        if matched.isupper():
            return replacement.upper()
        if matched[:1].isupper():
            return replacement.capitalize()
        return replacement

    return re.sub(pattern, _repl, value, flags=re.IGNORECASE)


def _harmonize_display_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    text = _replace_word_preserving_case(text, r"\bsolfege\b", "solfège")
    text = _replace_word_preserving_case(text, r"\bpresentiel\b", "présentiel")
    text = _replace_word_preserving_case(text, r"\bcontrole\b", "contrôle")
    return text


def _factorize_slot_labels(labels: list[str]) -> tuple[list[str], str]:
    sanitized_labels = [_sanitize_slot_label_text(item) for item in labels if str(item or "").strip()]
    if not sanitized_labels:
        return [], ""
    cleaned_labels: list[str] = []
    mode_labels: list[str] = []
    for item in sanitized_labels:
        cleaned_label, mode_label = _extract_slot_label_parts(item)
        if cleaned_label:
            cleaned_labels.append(cleaned_label)
        elif item:
            cleaned_labels.append(item)
        if mode_label:
            mode_labels.append(mode_label)
    unique_cleaned_labels = list(dict.fromkeys(cleaned_labels))
    unique_mode_labels = list(dict.fromkeys(mode_labels))
    if unique_mode_labels and len(unique_mode_labels) == 1 and len(mode_labels) == len(sanitized_labels):
        return unique_cleaned_labels, unique_mode_labels[0]
    return sanitized_labels, ""


def _slot_label(value: dict[str, Any], *, fallback_location_label: str = "") -> str:
    label = _sanitize_slot_label_text(value.get("label"))
    if label:
        return label
    weekday = str(value.get("weekday_label") or "").strip() or _weekday_label(value.get("weekday"))
    start = str(value.get("start_time") or value.get("start") or "").strip()
    end = str(value.get("end_time") or value.get("end") or "").strip()
    location_label = str(value.get("location_label") or fallback_location_label or "").strip()
    modality_label = _slot_mode_label(value.get("modality"))

    parts: list[str] = []
    if weekday and weekday != "-":
        parts.append(f"{weekday} {start}-{end}".strip() if start and end else weekday)
    elif start and end:
        parts.append(f"{start}-{end}")
    if modality_label:
        parts.append(modality_label)
    if location_label:
        parts.append(location_label)
    return _sanitize_slot_label_text(" · ".join(part for part in parts if part).strip()) or "-"


def _is_solfege_planning_block(block: dict[str, Any]) -> bool:
    activity_label = str(block.get("activity_label") or "").strip()
    activity_code = str(block.get("activity_code") or block.get("activity_service_code") or "").strip()
    pending_level = str(block.get("pending_solfege_level") or "").strip()
    haystack = f"{activity_label} {activity_code}".strip().lower()
    return bool(pending_level) or "solfege" in haystack


def _solfege_included_pending_notice_text() -> str:
    return "Le tarif total du présent devis inclut le solfège en ligne. Seul le choix du créneau reste à confirmer."


def _pending_planning_block_display(block: dict[str, Any]) -> tuple[str, str, str, str]:
    if _is_solfege_planning_block(block):
        level_label = str(block.get("pending_solfege_level") or "").strip() or _extract_solfege_level_from_text(
            block.get("activity_label")
        )
        activity_label = "Cours de solfège"
        if str(block.get("modality") or "").strip().upper() == "ONLINE":
            activity_label += " en ligne"
        if level_label:
            activity_label += f" – niveau {level_label}"
        activity_label += " (inclus dans le devis)"
        return activity_label, "-", "Créneau à sélectionner", "-"
    return _harmonize_display_text(str(block.get("activity_label") or "-").strip() or "-"), "à sélectionner", "à sélectionner", "-"


def _planning_blocks_table_html(snapshot: dict[str, Any]) -> tuple[str, int]:
    blocks = [item for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    rows: list[list[str]] = []
    for block in blocks:
        pending_slot_labels: list[str] = []
        for raw_slot in _json_list(block.get("pending_slot_options")):
            if not isinstance(raw_slot, dict):
                continue
            label = _slot_label(raw_slot, fallback_location_label=str(block.get("location_label") or "").strip())
            if label:
                pending_slot_labels.append(label)
                continue
            weekday_text = str(raw_slot.get("weekday_label") or "").strip() or _weekday_label(raw_slot.get("weekday"))
            start = str(raw_slot.get("start_time") or raw_slot.get("start") or "").strip()
            end = str(raw_slot.get("end_time") or raw_slot.get("end") or "").strip()
            if weekday_text and start and end:
                pending_slot_labels.append(f"{weekday_text} {start}-{end}")
        deduped_pending_slots = list(dict.fromkeys(pending_slot_labels))
        try:
            weekday_value = int(block.get("weekday") or -99)
        except (TypeError, ValueError):
            weekday_value = -99
        selection_pending = bool(block.get("selection_pending")) or weekday_value == -1
        activity_label = _harmonize_display_text(str(block.get("activity_label") or "-").strip() or "-")
        activity_type = str(block.get("activity_type_label") or "").strip()
        if not activity_type:
            activity_type = _modality_label(block.get("modality"))
        activity_type = _harmonize_display_text(activity_type)
        location_label = str(block.get("location_label") or "-").strip() or "-"
        if selection_pending:
            activity_label, weekday, time_range, duration = _pending_planning_block_display(block)
            if _is_solfege_planning_block(block):
                activity_type = "Solfège"
            elif deduped_pending_slots:
                time_range = "à sélectionner"
        else:
            weekday = str(block.get("weekday_label") or "").strip() or _weekday_label(block.get("weekday"))
            start_time = str(block.get("start_time") or "").strip()
            end_time = str(block.get("end_time") or "").strip()
            time_range = f"{start_time} - {end_time}" if start_time and end_time else "-"
            duration = _duration_label(
                start_time=start_time,
                end_time=end_time,
                fallback_minutes=block.get("duration_minutes"),
            )
        rows.append([activity_type, activity_label, location_label, weekday, time_range, duration])
    return (
        _table_html(
            ["Type activité", "Activité", "Lieu", "Jour", "Horaire", "Durée"],
            rows,
            empty_label="Aucun bloc planning.",
        ),
        len(rows),
    )


def _is_adjustment_line(line: QuoteLine) -> bool:
    line_type = (line.line_type or "").strip().lower()
    master_item_type = (line.master_item_type or "").strip().lower()
    return line_type in {"discount", "surcharge"} or master_item_type in {"discount_rule", "surcharge_rule"}


def _line_groups(
    lines: list[QuoteLine],
) -> tuple[list[QuoteLine], list[QuoteLine], list[QuoteLine], list[QuoteLine], list[QuoteLine]]:
    services: list[QuoteLine] = []
    products: list[QuoteLine] = []
    kits: list[QuoteLine] = []
    adjustments: list[QuoteLine] = []
    other_fees: list[QuoteLine] = []
    for line in lines:
        if _is_adjustment_line(line):
            adjustments.append(line)
            continue
        category = (line.line_category or "").strip().lower()
        if _line_matches_pass_recup(line) or category in {"other_fee", "fee", "immaterial_fee"}:
            other_fees.append(line)
            continue
        if (line.line_category or "").strip().lower() == "service":
            services.append(line)
            continue
        if line.kit_id is not None or (line.master_item_type or "").strip().lower() == "kit":
            kits.append(line)
            continue
        products.append(line)
    return services, products, kits, adjustments, other_fees


def _small_description_html(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        "<div style='font-size:10px;line-height:1.35;color:#64748b;margin-top:4px;'>"
        f"{escape(text).replace(chr(10), '<br/>')}"
        "</div>"
    )


def _unique_text_parts(*parts: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        raw = str(part or "").replace("\r\n", "\n").strip()
        if not raw:
            continue
        kept_lines: list[str] = []
        for line in raw.split("\n"):
            text = line.strip()
            if not text:
                continue
            normalized = " ".join(text.split()).casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            kept_lines.append(text)
        if kept_lines:
            result.extend(kept_lines)
    return result


def _product_long_descriptions_by_id(*, db: Session | None, products: list[QuoteLine]) -> dict[Any, str]:
    if db is None:
        return {}
    product_ids = [line.product_id for line in products if line.product_id is not None]
    if not product_ids:
        return {}
    rows = db.execute(
        select(CatalogProduct.id, CatalogProduct.long_description).where(CatalogProduct.id.in_(product_ids))
    ).all()
    result: dict[Any, str] = {}
    for product_id, long_description in rows:
        text = str(long_description or "").strip()
        if text:
            result[product_id] = text
    return result


def _kit_long_descriptions_by_id(*, db: Session | None, kits: list[QuoteLine]) -> dict[Any, str]:
    if db is None:
        return {}
    kit_ids = [line.kit_id for line in kits if line.kit_id is not None]
    if not kit_ids:
        return {}
    rows = db.execute(
        select(CatalogKit.id, CatalogKit.long_description).where(CatalogKit.id.in_(kit_ids))
    ).all()
    result: dict[Any, str] = {}
    for kit_id, long_description in rows:
        text = str(long_description or "").strip()
        if text:
            result[kit_id] = text
    return result


def _kit_composition_by_id(*, db: Session | None, kits: list[QuoteLine]) -> dict[Any, list[str]]:
    if db is None:
        return {}
    kit_ids = [line.kit_id for line in kits if line.kit_id is not None]
    if not kit_ids:
        return {}
    rows = db.execute(
        select(CatalogKitItem.kit_id, CatalogKitItem.quantity, CatalogProduct.title)
        .select_from(CatalogKitItem)
        .outerjoin(CatalogProduct, CatalogProduct.id == CatalogKitItem.product_id)
        .where(CatalogKitItem.kit_id.in_(kit_ids))
        .order_by(CatalogKitItem.kit_id.asc(), CatalogKitItem.display_order.asc(), CatalogKitItem.created_at.asc())
    ).all()
    result: dict[Any, list[str]] = {}
    for kit_id, quantity, product_title in rows:
        label = str(product_title or "Produit").strip() or "Produit"
        quantity_value = _decimal_from_any(quantity, Decimal("1"))
        quantity_label = _compact_quantity_label(quantity)
        rendered_label = f"{label} x {quantity_label}" if quantity_value > Decimal("1") else label
        result.setdefault(kit_id, []).append(rendered_label)
    return result


def _kit_composition_html(items: list[str]) -> str:
    if not items:
        return ""
    rendered_items = "<br/>".join(escape(item) for item in items)
    return (
        "<div style='font-size:10px;line-height:1.35;color:#475467;margin-top:4px;'>"
        "<strong>Comprend :</strong><br/>"
        f"{rendered_items}"
        "</div>"
    )


def _load_quote_template_snapshot(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.quote_template_version_id is not None:
        version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            subject = str(snapshot.get("subject_template") or "").strip()
            body = str(snapshot.get("body_template") or "").strip()
            if subject or body:
                return subject, body
    meta = quote.meta or {}
    subject = str(meta.get("template_subject") or "").strip()
    body = str(meta.get("template_body") or "").strip()
    return subject, body


def _quote_template_disables_pass_recup(*, db: Session | None, quote: Quote) -> bool:
    candidates: list[str] = []
    target = ""
    if db is not None:
        template: QuoteTemplate | None = None
        if quote.quote_template_id is not None:
            template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == quote.quote_template_id))
        elif quote.quote_template_version_id is not None:
            version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
            if version is not None:
                template = db.scalar(select(QuoteTemplate).where(QuoteTemplate.id == version.quote_template_id))
        if template is not None:
            target = str(template.target or "").strip().lower()
            candidates.extend(
                [
                    str(template.name or "").strip().lower(),
                    str(template.code or "").strip().lower(),
                ]
            )
    meta = _json_object(quote.meta)
    candidates.extend(
        [
            str(meta.get("quote_template_name") or "").strip().lower(),
            str(meta.get("quote_template_code") or "").strip().lower(),
            str(meta.get("template_name") or "").strip().lower(),
        ]
    )
    if target in {"eveil", "initiation"}:
        return True
    return any(("eveil" in item) or ("initiation" in item) for item in candidates if item)


def _load_terms_template_content(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.terms_template_version_id is not None:
        version = db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == quote.terms_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            label = str(snapshot.get("version_label") or "").strip()
            content = str(snapshot.get("content") or "").strip()
            if label or content:
                return label, content
    cgv_snapshot = quote.cgv_snapshot or {}
    return str(cgv_snapshot.get("version_label") or "").strip(), str(cgv_snapshot.get("content") or "").strip()


def _resolve_prospect_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "prospect_type": "adult",
        "prospect_type_label": "Adulte",
        "adult_first_name": "",
        "adult_last_name": "",
        "adult_full_name": "",
        "adult_email": "",
        "adult_phone": "",
        "adult_address": "",
        "parent_first_name": "",
        "parent_last_name": "",
        "parent_full_name": "",
        "parent_email": "",
        "parent_phone": "",
        "parent_address": "",
        "child_first_name": "",
        "child_last_name": "",
        "child_full_name": "",
        "child_birth_date": "",
    }
    if db is None or quote.prospect_id is None:
        return values

    prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
    if prospect is None:
        return values

    meta = prospect.meta or {}
    typeform_parent_address = _typeform_parent_address_from_quote(db=db, quote=quote).strip()
    prospect_type = "child" if str(meta.get("prospect_type") or "").strip().lower() == "child" else "adult"
    values["prospect_type"] = prospect_type
    values["prospect_type_label"] = "Enfant" if prospect_type == "child" else "Adulte"

    if prospect_type == "child":
        child_meta = meta.get("child") if isinstance(meta.get("child"), dict) else {}
        parent_meta = meta.get("parent_referent") if isinstance(meta.get("parent_referent"), dict) else {}
        child_first_name = str((child_meta or {}).get("first_name") or prospect.first_name or "").strip()
        child_last_name = str((child_meta or {}).get("last_name") or prospect.last_name or "").strip()
        values["child_first_name"] = child_first_name
        values["child_last_name"] = child_last_name
        values["child_full_name"] = _name(child_first_name, child_last_name, fallback="")
        values["child_birth_date"] = str((child_meta or {}).get("birth_date") or "").strip()

        parent_first_name = str((parent_meta or {}).get("first_name") or "").strip()
        parent_last_name = str((parent_meta or {}).get("last_name") or "").strip()
        parent_email = str((parent_meta or {}).get("email") or prospect.email or "").strip().lower()
        parent_phone = str((parent_meta or {}).get("phone") or prospect.phone or "").strip()
        parent_address = str((parent_meta or {}).get("address") or "").strip()
        if prospect.parent_prospect_id is not None:
            parent = db.scalar(select(Prospect).where(Prospect.id == prospect.parent_prospect_id))
            if parent is not None:
                parent_first_name = parent.first_name or parent_first_name
                parent_last_name = parent.last_name or parent_last_name
                parent_email = (parent.email or parent_email).strip().lower()
                parent_phone = (parent.phone or parent_phone).strip()
                if not parent_address:
                    parent_meta_data = parent.meta or {}
                    parent_address = str(parent_meta_data.get("adult_address") or "").strip()
        if not parent_address:
            parent_address = typeform_parent_address

        values["parent_first_name"] = parent_first_name
        values["parent_last_name"] = parent_last_name
        values["parent_full_name"] = _name(parent_first_name, parent_last_name, fallback="")
        values["parent_email"] = parent_email
        values["parent_phone"] = parent_phone
        values["parent_address"] = parent_address
    else:
        values["adult_first_name"] = (prospect.first_name or "").strip()
        values["adult_last_name"] = (prospect.last_name or "").strip()
        values["adult_full_name"] = _name(prospect.first_name, prospect.last_name, fallback="")
        values["adult_email"] = (prospect.email or "").strip().lower()
        values["adult_phone"] = (prospect.phone or "").strip()
        values["adult_address"] = str(meta.get("adult_address") or typeform_parent_address or "").strip()

    return values


def _resolve_client_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "client_first_name": "",
        "client_last_name": "",
        "client_full_name": "",
        "client_email": "",
        "client_phone": "",
        "client_address": "",
    }
    if db is None or quote.client_id is None:
        return values
    user = db.scalar(select(User).where(User.id == quote.client_id))
    if user is None:
        return values
    values["client_first_name"] = (user.first_name or "").strip()
    values["client_last_name"] = (user.last_name or "").strip()
    values["client_full_name"] = _name(user.first_name, user.last_name, fallback="")
    values["client_email"] = (user.email or "").strip().lower()
    values["client_phone"] = (user.mobile_phone_1 or user.phone or "").strip()
    values["client_address"] = " ".join(
        part for part in [user.address_line or "", user.postal_code or "", user.city or ""] if part
    ).strip()
    return values


def _resolve_schedule_visibility_by_audience(*, quote: Quote) -> dict[str, bool]:
    default_visibility = {
        AUDIENCE_ADMIN_PREVIEW: True,
        AUDIENCE_PUBLIC_PAGE: False,
        AUDIENCE_CLIENT_PDF: False,
    }
    payment_snapshot = _json_object(quote.payment_terms_snapshot)
    snapshot_visibility = _json_object(payment_snapshot.get("schedule_visibility"))
    if snapshot_visibility:
        return {
            AUDIENCE_ADMIN_PREVIEW: _is_true(
                snapshot_visibility.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])
            ),
            AUDIENCE_PUBLIC_PAGE: _is_true(
                snapshot_visibility.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])
            ),
            AUDIENCE_CLIENT_PDF: _is_true(
                snapshot_visibility.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])
            ),
        }
    meta = _json_object(quote.meta)
    visibility_root = _json_object(meta.get("document_visibility"))
    raw = _json_object(visibility_root.get("payment_schedule_detailed"))
    if not raw:
        raw = _json_object(meta.get("payment_schedule_visibility"))
    if not raw:
        return default_visibility
    return {
        AUDIENCE_ADMIN_PREVIEW: _is_true(raw.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])),
        AUDIENCE_PUBLIC_PAGE: _is_true(raw.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])),
        AUDIENCE_CLIENT_PDF: _is_true(raw.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])),
    }


def _resolve_payment_method_label(*, quote: Quote) -> str:
    snapshot = _json_object(quote.payment_terms_snapshot)
    for key in ("payment_method_label", "plan_name", "payment_plan_name", "payment_method"):
        value = str(snapshot.get(key) or "").strip()
        if value:
            return value
    meta = _json_object(quote.meta)
    for key in ("payment_plan_label", "payment_method_label", "payment_method", "payment_plan_name"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return "Paiement non précisé"


def _line_matches_pass_recup(line: QuoteLine) -> bool:
    tokens = [
        str(line.title or ""),
        str(line.code or ""),
        str(line.line_type or ""),
        str(line.line_category or ""),
        str(line.master_item_type or ""),
    ]
    haystack = " ".join(tokens).strip().lower()
    return "pass recup" in haystack or "pass_recup" in haystack or "passrecup" in haystack


def _line_matches_masterclass(line: QuoteLine) -> bool:
    tokens = [
        str(line.title or ""),
        str(line.code or ""),
        str(line.line_type or ""),
        str(line.line_category or ""),
        str(line.master_item_type or ""),
    ]
    haystack = " ".join(tokens).strip().lower()
    return "masterclass" in haystack or "master class" in haystack


def _masterclass_blocks_from_calendar_snapshot(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in _json_list(snapshot.get("blocks")):
        if not isinstance(raw, dict):
            continue
        activity_label = str(raw.get("activity_label") or "").strip()
        activity_code = str(raw.get("activity_code") or raw.get("activity_service_code") or "").strip()
        haystack = f"{activity_label} {activity_code}".strip().lower()
        if "masterclass" not in haystack and "master class" not in haystack:
            continue
        location_label = str(raw.get("location_label") or "").strip()
        selection_pending = bool(raw.get("selection_pending"))
        weekday_label = str(raw.get("weekday_label") or "").strip() or _weekday_label(raw.get("weekday"))
        start_time = str(raw.get("start_time") or "").strip()
        end_time = str(raw.get("end_time") or "").strip()
        session_label = str(raw.get("session_label") or "").strip()
        if not session_label:
            if selection_pending:
                session_label = "à sélectionner"
            elif weekday_label and start_time and end_time:
                session_label = f"{weekday_label} {start_time}-{end_time}"
            elif weekday_label:
                session_label = weekday_label
        rows.append(
            {
                "session": session_label,
                "location_label": location_label,
                "activity_label": activity_label or "Masterclass",
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in rows:
        key = (
            str(item.get("session") or "").strip().lower(),
            str(item.get("location_label") or "").strip().lower(),
            str(item.get("activity_label") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_solfege_level_from_text(value: Any) -> str:
    raw = str(value or "").strip()
    match = re.search(r"niveau\s*([1-5])", raw, flags=re.IGNORECASE)
    if match and match.group(1):
        return match.group(1)
    return ""


def _solfege_pending_block_info(snapshot: dict[str, Any]) -> dict[str, Any]:
    has_pending_selection = False
    level_code = ""
    slot_labels: list[str] = []

    for raw in _json_list(snapshot.get("blocks")):
        if not isinstance(raw, dict):
            continue
        activity_label = str(raw.get("activity_label") or "").strip()
        activity_code = str(raw.get("activity_code") or raw.get("activity_service_code") or "").strip()
        haystack = f"{activity_label} {activity_code}".strip().lower()
        if "solfege" not in haystack:
            continue
        try:
            weekday_value = int(raw.get("weekday") or -99)
        except (TypeError, ValueError):
            weekday_value = -99
        selection_pending = bool(raw.get("selection_pending")) or weekday_value == -1
        if selection_pending:
            has_pending_selection = True
        if not level_code:
            level_code = str(raw.get("pending_solfege_level") or "").strip() or _extract_solfege_level_from_text(activity_label)
        for raw_slot in _json_list(raw.get("pending_slot_options")):
            if not isinstance(raw_slot, dict):
                continue
            label = _slot_label(raw_slot, fallback_location_label=str(raw.get("location_label") or "").strip())
            if label:
                slot_labels.append(label)
                continue
            weekday_text = str(raw_slot.get("weekday_label") or "").strip() or _weekday_label(raw_slot.get("weekday"))
            start = str(raw_slot.get("start_time") or raw_slot.get("start") or "").strip()
            end = str(raw_slot.get("end_time") or raw_slot.get("end") or "").strip()
            if weekday_text and start and end:
                slot_labels.append(f"{weekday_text} {start}-{end}")

    for raw_recommendation in _json_list(snapshot.get("typeform_recommendations")):
        recommendation = _json_object(raw_recommendation)
        if str(recommendation.get("selected_session_id") or "").strip():
            continue
        activity_name = str(recommendation.get("activity_name") or "").strip()
        if "solfege" not in activity_name.lower():
            continue
        has_pending_selection = True
        if not level_code:
            level_code = _extract_solfege_level_from_text(activity_name)
        for raw_option in _json_list(recommendation.get("options")):
            option = _json_object(raw_option)
            weekday_text = str(option.get("weekday_label") or "").strip()
            start = str(option.get("start_time_label") or "").strip()
            location = str(option.get("location_name") or "").strip()
            label = " · ".join(
                part
                for part in (" ".join(part for part in (weekday_text, start) if part), location)
                if part
            )
            if label:
                slot_labels.append(_sanitize_slot_label_text(label))

    return {
        "has_pending_selection": has_pending_selection,
        "level_code": level_code,
        "slot_labels": _unique_text_parts(*slot_labels),
    }


def _resolve_pass_recup_enabled(*, meta: dict[str, Any], lines: list[QuoteLine]) -> bool:
    mode = str(meta.get("pass_recup_mode") or "").strip().lower()
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    if _is_true(meta.get("pass_recup_enabled")):
        return True
    return any(_line_matches_pass_recup(line) for line in lines)


def _extract_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> dict[str, Any]:
    prospect_data = _resolve_prospect_data(db=db, quote=quote)
    client_data = _resolve_client_data(db=db, quote=quote)

    payment_snapshot = _json_object(quote.payment_terms_snapshot)
    schedule = [item for item in _json_list(payment_snapshot.get("schedule")) if isinstance(item, dict)]
    has_installment_schedule = len(schedule) > 1
    schedule_visibility = _resolve_schedule_visibility_by_audience(quote=quote)
    deposit_data = _json_object(payment_snapshot.get("deposit"))
    meta = _json_object(quote.meta)
    if not deposit_data:
        deposit_data = _json_object(meta.get("pre_registration_deposit"))
    deposit_enabled = _is_true(deposit_data.get("enabled"))
    deposit_amount_ttc = _decimal_from_any(
        payment_snapshot.get("deposit_amount_ttc"),
        _decimal_from_any(deposit_data.get("amount_ttc"), Decimal("0.00")),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if deposit_amount_ttc <= Decimal("0.00"):
        deposit_enabled = False
        deposit_amount_ttc = Decimal("0.00")
    total_after_adjustment = _decimal_from_any(payment_snapshot.get("total_ttc_after_adjustment"), quote.total_ttc)
    if deposit_amount_ttc > total_after_adjustment:
        deposit_amount_ttc = total_after_adjustment
    remaining_ttc_after_deposit = _decimal_from_any(
        payment_snapshot.get("remaining_ttc_after_deposit"),
        total_after_adjustment - deposit_amount_ttc,
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if remaining_ttc_after_deposit < Decimal("0.00"):
        remaining_ttc_after_deposit = Decimal("0.00")

    calendar_snapshot = _json_object(quote.calendar_snapshot)
    calendar_solfege = _json_object(calendar_snapshot.get("solfege"))
    solfege_selected_slot = _json_object(calendar_solfege.get("selected_slot"))
    selected_solfege_slot = _json_object(quote.selected_solfege_slot)
    if not selected_solfege_slot:
        selected_solfege_slot = solfege_selected_slot

    pending_solfege_info = _solfege_pending_block_info(calendar_snapshot)
    activity_solfege = [item for item in _json_list(meta.get("activity_solfege")) if isinstance(item, dict)]
    masterclass_blocks_meta = [item for item in _json_list(meta.get("masterclass_blocks")) if isinstance(item, dict)]
    masterclass_blocks_calendar = _masterclass_blocks_from_calendar_snapshot(calendar_snapshot)
    masterclass_blocks = [*masterclass_blocks_meta, *masterclass_blocks_calendar]
    masterclass_blocks_deduped: list[dict[str, Any]] = []
    seen_masterclass: set[tuple[str, str, str]] = set()
    for item in masterclass_blocks:
        key = (
            str(item.get("session") or "").strip().lower(),
            str(item.get("location_label") or "").strip().lower(),
            str(item.get("activity_label") or "").strip().lower(),
        )
        if key in seen_masterclass:
            continue
        seen_masterclass.add(key)
        masterclass_blocks_deduped.append(item)
    masterclass_blocks = masterclass_blocks_deduped
    pass_recup_mode = str(meta.get("pass_recup_mode") or "").strip().lower() or "auto"
    pass_recup_allowed = not _quote_template_disables_pass_recup(db=db, quote=quote)
    pass_recup_enabled = pass_recup_allowed and _resolve_pass_recup_enabled(meta=meta, lines=lines)

    solfege_enabled = bool(
        quote.estimated_solfege_level
        or quote.solfege_duration_minutes
        or selected_solfege_slot
        or activity_solfege
        or pending_solfege_info.get("has_pending_selection")
    )
    masterclass_enabled = (
        bool(masterclass_blocks)
        or _is_true(meta.get("masterclass_enabled"))
        or any(_line_matches_masterclass(line) for line in lines)
    )

    schedule_allowed_for_audience = bool(schedule_visibility.get(audience, False))
    show_schedule_detailed = has_installment_schedule and schedule_allowed_for_audience
    payment_schedule_compact_notice = ""
    if schedule and not show_schedule_detailed:
        if len(schedule) == 1:
            payment_schedule_compact_notice = f"1 échéance : {_schedule_due_label(schedule[0])}"
        else:
            payment_schedule_compact_notice = (
                f"Paiement en {len(schedule)} échéances. Le détail des échéances est communiqué séparément."
            )
    payment_instruction = str(_json_object(quote.payment_terms_snapshot).get("payment_instruction") or "").strip()

    prospect_type = str(prospect_data.get("prospect_type") or "adult").strip().lower()
    show_child_block = prospect_type == "child"
    show_adult_block = not show_child_block

    display_flags: dict[str, bool] = {
        "showAdultBlock": show_adult_block,
        "showChildBlock": show_child_block,
        "showPaymentMethodBlock": True,
        "showPaymentScheduleDetailed": show_schedule_detailed,
        "showPaymentScheduleCompactNotice": bool(payment_schedule_compact_notice),
        "showDepositBlock": deposit_enabled and deposit_amount_ttc > Decimal("0.00"),
        "showSolfegeSection": solfege_enabled,
        "showSolfegeCompactNotice": not solfege_enabled,
        "showMasterclassSection": masterclass_enabled,
        "showMasterclassCompactNotice": not masterclass_enabled,
        "showPassRecupSection": pass_recup_enabled,
        "showPassRecupCompactNotice": pass_recup_allowed and not pass_recup_enabled,
    }
    return {
        "audience": audience,
        "prospect_type": prospect_type,
        "schedule": schedule,
        "schedule_visibility": schedule_visibility,
        "payment_method_label": _resolve_payment_method_label(quote=quote),
        "payment_schedule_compact_notice": payment_schedule_compact_notice,
        "payment_instruction": payment_instruction,
        "deposit_enabled": deposit_enabled and deposit_amount_ttc > Decimal("0.00"),
        "deposit_amount_ttc": deposit_amount_ttc,
        "remaining_ttc_after_deposit": remaining_ttc_after_deposit,
        "solfege_enabled": solfege_enabled,
        "solfege_level": str(quote.estimated_solfege_level or pending_solfege_info.get("level_code") or "").strip(),
        "solfege_duration_minutes": quote.solfege_duration_minutes,
        "solfege_selected_slot": selected_solfege_slot,
        "solfege_pending_selection": bool(pending_solfege_info.get("has_pending_selection")),
        "solfege_available_slots": [item for item in pending_solfege_info.get("slot_labels", []) if isinstance(item, str)],
        "masterclass_enabled": masterclass_enabled,
        "masterclass_blocks": masterclass_blocks,
        "pass_recup_mode": pass_recup_mode,
        "pass_recup_allowed": pass_recup_allowed,
        "pass_recup_enabled": pass_recup_enabled,
        "display_flags": display_flags,
        "prospect_data": prospect_data,
        "client_data": client_data,
    }


def build_quote_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    context = _extract_document_context(db=db, quote=quote, lines=lines, audience=audience)
    visible_blocks: list[str] = []
    hidden_blocks: list[str] = []
    for block_name, flag_key in (
        ("adult_identity", "showAdultBlock"),
        ("child_parent_identity", "showChildBlock"),
        ("payment_method", "showPaymentMethodBlock"),
        ("payment_schedule_detailed", "showPaymentScheduleDetailed"),
        ("payment_schedule_compact_notice", "showPaymentScheduleCompactNotice"),
        ("solfege", "showSolfegeSection"),
        ("solfege_compact_notice", "showSolfegeCompactNotice"),
        ("masterclass", "showMasterclassSection"),
        ("masterclass_compact_notice", "showMasterclassCompactNotice"),
        ("pass_recup", "showPassRecupSection"),
        ("pass_recup_compact_notice", "showPassRecupCompactNotice"),
    ):
        if bool(context["display_flags"].get(flag_key)):
            visible_blocks.append(block_name)
        else:
            hidden_blocks.append(block_name)
    context["visible_blocks"] = visible_blocks
    context["hidden_blocks"] = hidden_blocks
    return context


TOKEN_RE = re.compile(r"\{[\s\xa0]*([a-zA-Z0-9_]+)[\s\xa0]*\}")


def _apply_template(
    template: str,
    *,
    values: dict[str, str],
    html_keys: set[str],
    html_output: bool,
) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        raw_value = values.get(key, "")
        if html_output:
            if key in html_keys:
                return raw_value
            return escape(raw_value)
        return raw_value

    return TOKEN_RE.sub(repl, template)


def _normalize_block_placeholder_wrappers(template: str, *, keys: set[str]) -> str:
    raw = str(template or "")
    if not raw or not keys:
        return raw
    normalized = raw
    for key in keys:
        key_pattern = r"\{[\s\xa0]*" + re.escape(key) + r"[\s\xa0]*\}"
        for tag in ("p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6"):
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*{key_pattern}\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*{key_pattern}(?:\s*(?:<br\s*/?>|&nbsp;))*\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
    return normalized


def _as_html_fragment(content: str) -> str:
    normalized = (content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    if "<" in normalized and ">" in normalized:
        return normalized
    return "<p>" + "<br/>".join(line for line in normalized.split("\n")) + "</p>"


def _cleanup_rendered_block_markup(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    cleaned = raw
    patterns = (
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<div\b.*?</div>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<table\b.*?</table>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<section\b.*?</section>)\s*</p>",
    )
    for _ in range(3):
        previous = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, r"\1", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if cleaned == previous:
            break

    cleaned = re.sub(
        r"<p\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<h[1-6]\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</h[1-6]>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned


def _normalize_template_source(template: str) -> str:
    raw = (template or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1].strip()
    if any(token in raw for token in ("&lt;", "&gt;", "&#60;", "&#62;", "&#123;", "&#125;", "&#x7b;", "&#x7d;")):
        for _ in range(3):
            decoded = html_unescape(raw)
            if decoded == raw:
                break
            raw = decoded
    raw = raw.replace("\uFF5B", "{").replace("\uFF5D", "}")
    raw = raw.replace("\u00A0", " ")
    raw = raw.replace("\u200B", "").replace("\u200C", "").replace("\u200D", "")
    return raw


def _strip_legacy_recipient_email_markup(template: str) -> str:
    raw = str(template or "")
    if re.search(r"\{[\s\xa0]*recipient_email[\s\xa0]*\}", raw, flags=re.IGNORECASE) is None:
        return raw

    paragraph_pattern = re.compile(
        r"<p\b[^>]*>.*?\{[\s\xa0]*recipient_email[\s\xa0]*\}.*?</p>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _replace_paragraph(match: re.Match[str]) -> str:
        block = match.group(0)
        plain = re.sub(r"<[^>]+>", " ", block, flags=re.IGNORECASE)
        plain = re.sub(r"\{\s*recipient_email\s*\}", " ", plain, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", html_unescape(plain)).strip().lower()

        if "destinataire" in normalized:
            updated = re.sub(r"\s*\(\s*\{recipient_email\}\s*\)", "", block, flags=re.IGNORECASE)
            updated = re.sub(r"\s*[-–—,:]\s*\{recipient_email\}", "", updated, flags=re.IGNORECASE)
            updated = re.sub(r"\{\s*recipient_email\s*\}", "", updated, flags=re.IGNORECASE)
            return updated

        if "email" in normalized or "contact" in normalized:
            return ""

        return re.sub(r"\{\s*recipient_email\s*\}", "", block, flags=re.IGNORECASE)

    cleaned = paragraph_pattern.sub(_replace_paragraph, raw)
    cleaned = re.sub(r"\s*\(\s*\{recipient_email\}\s*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-–—,:]\s*\{recipient_email\}", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\{\s*recipient_email\s*\}", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _dedupe_retained_activities_tables(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    pattern = re.compile(
        r"(<h[1-3][^>]*>\s*Les\s+Activites?\s+retenues\s*</h[1-3]>\s*)"
        r"(<table\b.*?</table>\s*)"
        r"(<table\b.*?</table>)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _replace(match: re.Match[str]) -> str:
        heading = match.group(1)
        first_table = match.group(2)
        second_table = match.group(3)
        first_is_services = bool(
            re.search(r"<th[^>]*>\s*Activite\s*</th>", first_table, flags=re.IGNORECASE)
            and not re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", first_table, flags=re.IGNORECASE)
        )
        second_is_planning = bool(
            re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", second_table, flags=re.IGNORECASE)
            and re.search(r"<th[^>]*>\s*Lieu\s*</th>", second_table, flags=re.IGNORECASE)
        )
        if first_is_services and second_is_planning:
            return f"{heading}{second_table}"
        return match.group(0)

    return pattern.sub(_replace, raw)


def _cleanup_legacy_terms_layout(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw
    has_table = "<table" in raw.lower()
    if not has_table:
        return raw
    has_table_headers = "<th" in raw.lower()
    table_count = len(re.findall(r"<table\b", raw, flags=re.IGNORECASE))
    if has_table_headers or table_count != 1:
        return raw

    row_pattern = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    rows = row_pattern.findall(raw)
    if len(rows) < 4:
        return raw

    flattened = "".join(f"<p>{cell.strip()}</p>" for cell in rows if cell.strip())
    if not flattened:
        return raw
    return flattened


def _enforce_family_page_break(content: str) -> str:
    marker = "quote-page-break"
    pattern = re.compile(r"(<h[1-3][^>]*>\s*Informations?\s+(de\s+la\s+)?famille\s*</h[1-3]>)", re.IGNORECASE)
    match = pattern.search(content or "")
    if match is None:
        return content
    prefix = (content or "")[max(0, match.start() - 260):match.start()]
    if marker in prefix:
        return content
    return (content or "")[:match.start()] + "<div class='quote-page-break'></div>" + (content or "")[match.start():]


def _ensure_full_html_document(content: str) -> str:
    candidate = (content or "").strip()
    if not candidate:
        return "<html><body><p>Devis</p></body></html>"
    if "<html" in candidate.lower():
        return candidate
    return f"<html><body>{candidate}</body></html>"


def _normalize_css_vars_for_pdf(html_document: str) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = (match.group(1) or "").strip().lower()
        explicit_fallback = (match.group(2) or "").strip()
        if explicit_fallback:
            return explicit_fallback
        return CSS_VAR_DEFAULTS.get(variable_name, "inherit")

    return CSS_VAR_RE.sub(replace, html_document)


def _render_html_pdf_with_xhtml2pdf(rendered_html: str) -> bytes | None:
    html_document = _normalize_css_vars_for_pdf(_ensure_full_html_document(rendered_html))
    output = io.BytesIO()
    try:
        status = pisa.CreatePDF(src=html_document, dest=output, encoding="utf-8")
    except Exception:
        logger.exception("Quote HTML PDF rendering crashed; falling back to block renderer")
        return None
    if status.err:
        logger.warning("Quote HTML PDF rendering failed; falling back to block renderer")
        return None
    return output.getvalue()


_INLINE_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", flags=re.IGNORECASE | re.DOTALL)


def _strip_inline_footers(content: str) -> str:
    without_table = _INLINE_FOOTER_RE.sub("", content or "")
    return _INLINE_RUNNING_FOOTER_RE.sub("", without_table)


def _strip_inline_headers(content: str) -> str:
    without_table = _INLINE_HEADER_RE.sub("", content or "")
    return _INLINE_RUNNING_HEADER_RE.sub("", without_table)


def _strip_overriding_page_styles(content: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        style_body = match.group(1) or ""
        if "@page" in style_body.lower():
            return ""
        return match.group(0)

    return _INLINE_STYLE_RE.sub(_replace, content or "")


def _strip_inline_style_blocks(content: str) -> str:
    return _INLINE_STYLE_RE.sub("", content or "")


def _extract_body_inner_html(content: str) -> str:
    raw = str(content or "")
    matched = re.search(r"<body[^>]*>(.*)</body>", raw, flags=re.IGNORECASE | re.DOTALL)
    if matched is None:
        return raw
    return matched.group(1)


def _normalize_tables_for_pdf(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    def _normalize_table_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        lowered = tag.lower()
        if (
            "quote-running-header" in lowered
            or "quote-running-footer" in lowered
            or "quote-header" in lowered
            or "quote-footer" in lowered
        ):
            return tag

        updated = tag
        class_match = re.search(r"class\s*=\s*(['\"])(.*?)\1", updated, flags=re.IGNORECASE | re.DOTALL)
        if class_match:
            classes = class_match.group(2)
            if "quote-table" not in classes.split():
                next_classes = f"{classes} quote-table".strip()
                updated = (
                    updated[: class_match.start(2)]
                    + next_classes
                    + updated[class_match.end(2) :]
                )
        else:
            updated = updated[:-1] + " class='quote-table'>"

        if not re.search(r"\bcellpadding\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellpadding='10'>"
        if not re.search(r"\bcellspacing\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellspacing='0'>"
        return updated

    def _append_style(existing: str) -> str:
        base = existing.strip()
        if base and not base.endswith(";"):
            base = base + ";"
        extra = (
            "padding:12px 10px 12px 10px;"
            "padding-top:12px;"
            "padding-right:10px;"
            "padding-bottom:12px;"
            "padding-left:10px;"
            "vertical-align:middle;"
        )
        return (base + extra).strip()

    def _normalize_cell_tag(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        attrs = match.group(2) or ""
        updated_attrs = attrs

        style_match = re.search(r"style\s*=\s*(['\"])(.*?)\1", updated_attrs, flags=re.IGNORECASE | re.DOTALL)
        if style_match:
            next_style = _append_style(style_match.group(2))
            updated_attrs = (
                updated_attrs[: style_match.start(2)]
                + next_style
                + updated_attrs[style_match.end(2) :]
            )
        else:
            updated_attrs = f"{updated_attrs} style='{_append_style('')}'"

        if not re.search(r"\bvalign\s*=", updated_attrs, flags=re.IGNORECASE):
            updated_attrs = f"{updated_attrs} valign='middle'"

        return f"<{tag_name}{updated_attrs}>"

    normalized = re.sub(r"<table\b[^>]*>", _normalize_table_tag, raw, flags=re.IGNORECASE)
    normalized = re.sub(r"<(th|td)([^>]*)>", _normalize_cell_tag, normalized, flags=re.IGNORECASE)
    return normalized


def _simplify_rich_text_to_pdf_paragraphs(content: str, *, values: dict[str, str]) -> str:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return "<p>Aucune condition générale.</p>"
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        return "<p>Aucune condition générale.</p>"
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def _build_quote_pdf_blocks_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> str:
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    terms_html = _simplify_rich_text_to_pdf_paragraphs(cgv_content, values=values)

    template = (
        "<section class='quote-block'>"
        "<h1>Votre devis d’inscription</h1>"
        "<p><strong>Devis :</strong> {quote_number}</p>"
        "<p><strong>Année scolaire :</strong> {school_year_label}</p>"
        "<p><strong>{quote_status_date_label} :</strong> {quote_status_date_value}</p>"
        "<p><strong>Élève :</strong> {child_full_name}</p>"
        "</section>"
        "{page_break_html}"
        "<h2>Informations de l’élève et du responsable</h2>"
        "<div class='quote-block'>{prospect_identity_block_html}</div>"
        "{page_break_html}"
        "<h2>Cours et options choisis</h2>"
        "{activities_planning_table_html}"
        "{services_section_html}"
        "{adjustments_section_html}"
        "{products_section_html}"
        "{kits_section_html}"
        "{other_fees_section_html}"
        "{financial_recap_block_html}"
        "<h2>Règlement et échéancier</h2>"
        "{payment_method_block_html}"
        "<p>{payment_schedule_summary}</p>"
        "{payment_schedule_table_html}"
        "{options_section_html}"
        "{page_break_html}"
        "<h2>Calendrier prévisionnel des cours</h2>"
        "<p><strong>Vue d’ensemble du calendrier :</strong> {calendar_summary}</p>"
        "{calendar_activity_semesters_html}"
        "{page_break_html}"
        "<h2>Conditions d’inscription 2026–2027</h2>"
        "<div class='quote-block'>"
        "<p><strong>{cgv_version}</strong></p>"
        "{terms_plain_pdf_html}"
        "</div>"
    )
    block_values = dict(values)
    block_values["cgv_version"] = cgv_label or values.get("cgv_version", "-")
    block_values["terms_plain_pdf_html"] = terms_html
    local_html_keys = set(html_keys)
    local_html_keys.add("terms_plain_pdf_html")
    rendered = _apply_template(template, values=block_values, html_keys=local_html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _normalize_tables_for_pdf(rendered)
    return rendered


def _pdf_shell_html(*, content_html: str, header_html: str, footer_html: str) -> str:
    return (
        "<html><head><meta charset='utf-8'/>"
        "<style>"
        "@page {"
        "  size: a4 portrait;"
        "  margin: 0;"
        "  @frame header_frame { -pdf-frame-content: header_content; left: 36pt; top: 14pt; width: 523pt; height: 44pt; }"
        "  @frame content_frame { left: 36pt; top: 64pt; width: 523pt; height: 700pt; }"
        "  @frame footer_frame { -pdf-frame-content: footer_content; left: 36pt; top: 770pt; width: 523pt; height: 58pt; }"
        "}"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.42;}"
        "h1,h2,h3{color:#101828;margin:0 0 8px 0;}"
        "p{margin:0 0 7px 0;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-content table,.quote-table{width:100%;border-collapse:collapse;border-spacing:0;table-layout:auto;margin:8px 0 12px 0;font-size:10.9px;}"
        ".quote-content th,.quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td,.quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;word-break:break-word !important;white-space:normal !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td>*{margin-top:0 !important;margin-bottom:0 !important;}"
        ".quote-content font[size='10'],font[size='10']{font-size:10px !important;line-height:1.45 !important;color:#6b7280 !important;}"
        ".quote-content thead,thead{display:table-header-group !important;}"
        ".quote-content tfoot,tfoot{display:table-footer-group !important;}"
        ".quote-content tr,tr{page-break-inside:auto !important;break-inside:auto !important;height:auto !important;}"
        ".quote-brand-logo-img{display:inline-block;max-width:120px;max-height:34px;object-fit:contain;}"
        ".quote-running-header{width:100%;border-collapse:collapse;font-size:10px;color:#334155;border-bottom:1px solid #d7dee8;}"
        ".quote-running-header td{vertical-align:middle;padding:0 0 4px 0;}"
        ".quote-running-footer{width:100%;border-collapse:collapse;font-size:9.4px;color:#475467;border-top:1px solid #d7dee8;}"
        ".quote-running-footer td{vertical-align:top;padding-top:5px;line-height:1.35;}"
        "</style>"
        "</head><body>"
        "<div id='header_content'>"
        f"{header_html}"
        "</div>"
        "<div id='footer_content'>"
        f"{footer_html}"
        "</div>"
        "<div class='quote-content'>"
        f"{content_html}"
        "</div>"
        "</body></html>"
    )


def _build_template_values(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    currency = (quote.currency or "EUR").upper()
    services, products, kits, adjustments, other_fees = _line_groups(lines)
    document_context = build_quote_document_context(db=db, quote=quote, lines=lines, audience=audience)
    display_flags = document_context["display_flags"]
    total_ttc = Decimal(quote.total_ttc or 0).quantize(Decimal("0.01"))
    total_ht_before_from_lines = sum(
        (Decimal(getattr(line, "amount_ht", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    vat_amount_before_from_lines = sum(
        (Decimal(getattr(line, "amount_vat", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    vat_rate = _resolve_display_vat_rate(
        quote=quote,
        lines=lines,
        total_ht=total_ht_before_from_lines,
        total_vat=vat_amount_before_from_lines,
    )

    payment_terms_snapshot = _json_object(quote.payment_terms_snapshot)
    adjustment_data = _json_object(payment_terms_snapshot.get("adjustment"))
    if not adjustment_data:
        adjustment_data = _json_object(_json_object(quote.meta).get("financial_adjustment"))
    adjustment_type = str(adjustment_data.get("type") or "").strip().lower()
    if adjustment_type not in {"credit", "debt"}:
        adjustment_type = "none"
    adjustment_amount = _decimal_from_any(adjustment_data.get("amount_ttc"), Decimal("0")).quantize(Decimal("0.01"))
    if adjustment_amount <= Decimal("0"):
        adjustment_amount = Decimal("0.00")
        adjustment_type = "none"
    adjustment_signed_amount = (
        -adjustment_amount
        if adjustment_type == "credit"
        else adjustment_amount
        if adjustment_type == "debt"
        else Decimal("0.00")
    )
    total_before_adjustment = (total_ttc - adjustment_signed_amount).quantize(Decimal("0.01"))
    total_after_adjustment = total_ttc
    schedule = [item for item in _json_list(document_context.get("schedule")) if isinstance(item, dict)]
    has_deposit = bool(document_context.get("deposit_enabled"))
    deposit_amount_ttc = _decimal_from_any(document_context.get("deposit_amount_ttc"), Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if deposit_amount_ttc <= Decimal("0.00"):
        has_deposit = False
        deposit_amount_ttc = Decimal("0.00")
    if deposit_amount_ttc > total_after_adjustment:
        deposit_amount_ttc = total_after_adjustment
    remaining_ttc_after_deposit = _decimal_from_any(
        document_context.get("remaining_ttc_after_deposit"),
        total_after_adjustment - deposit_amount_ttc,
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if remaining_ttc_after_deposit < Decimal("0.00"):
        remaining_ttc_after_deposit = Decimal("0.00")
    adjustment_effective_date = _birth_date_label(str(adjustment_data.get("effective_date") or ""))
    adjustment_label = str(adjustment_data.get("label") or "").strip()
    adjustment_type_label = (
        "Avoir" if adjustment_type == "credit" else "Dette" if adjustment_type == "debt" else "Aucun"
    )
    adjustment_impact_label = (
        "Deduit du total facture"
        if adjustment_type == "credit"
        else "Ajoute au total facture"
        if adjustment_type == "debt"
        else ""
    )
    adjustment_display_title = adjustment_type_label if adjustment_type != "none" else ""
    adjustment_display_line = (
        f"{adjustment_display_title} : {_money(adjustment_amount, currency)}"
        if adjustment_type != "none"
        else ""
    )
    has_financial_adjustment = adjustment_type in {"credit", "debt"}
    has_credit_adjustment = adjustment_type == "credit"
    has_debt_adjustment = adjustment_type == "debt"

    total_ht_before_adjustment = total_ht_before_from_lines
    vat_amount_before_adjustment = vat_amount_before_from_lines
    if adjustment_type == "none":
        total_ht_after_adjustment = total_ht_before_from_lines
        vat_amount_after_adjustment = vat_amount_before_from_lines
    else:
        total_ht_after_adjustment, vat_amount_after_adjustment = _split_ttc_with_rate(total_after_adjustment, vat_rate)
    remaining_ht_after_deposit, remaining_vat_after_deposit = _split_ttc_with_rate(remaining_ttc_after_deposit, vat_rate)
    deposit_ht_amount, deposit_vat_amount = _split_ttc_with_rate(deposit_amount_ttc, vat_rate)

    if adjustment_type == "none":
        financial_adjustment_block_html = ""
        financial_adjustment_section_html = ""
        financial_adjustment_none_html = "<p>Aucun avoir ou dette applique.</p>"
        total_ttc_before_adjustment_html = ""
    else:
        adjustment_parts = [
            f"<p><strong>{escape(adjustment_display_title)}</strong> : {escape(_money(adjustment_amount, currency))}</p>",
            f"<p><strong>Impact:</strong> {escape(adjustment_impact_label)}</p>",
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            adjustment_parts.append(f"<p><strong>Date:</strong> {escape(adjustment_effective_date)}</p>")
        normalized_adjustment_label = adjustment_label.strip().lower()
        normalized_type_label = adjustment_type_label.strip().lower()
        if (
            adjustment_label
            and normalized_adjustment_label not in {"avoir", "dette"}
            and normalized_adjustment_label != normalized_type_label
        ):
            adjustment_parts.append(f"<p><strong>Libelle:</strong> {escape(adjustment_label)}</p>")
        financial_adjustment_block_html = "".join(adjustment_parts)
        # Keep this block content-only (no heading) so it can be safely inserted in WYSIWYG flows.
        financial_adjustment_section_html = financial_adjustment_block_html
        financial_adjustment_none_html = ""
        total_ttc_before_adjustment_html = (
            f"<p><strong>Total TTC avant ajustement :</strong> {_decimal_str(total_before_adjustment)} {escape(currency)}</p>"
        )
    if adjustment_type == "none":
        financial_recap_rows: list[tuple[str, str]] = [
            ("Total HT", f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
            (f"TVA ({_decimal_str(vat_rate)} %)", f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
            ("Total TTC du devis", f"{_decimal_str(total_after_adjustment)} {currency}"),
        ]
    else:
        financial_recap_rows = [
            ("Total TTC avant ajustement", f"{_decimal_str(total_before_adjustment)} {currency}"),
            (adjustment_display_title, f"{_decimal_str(adjustment_amount)} {currency}"),
            ("Impact", adjustment_impact_label),
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            financial_recap_rows.append(("Date ajustement", adjustment_effective_date))
        financial_recap_rows.extend(
            [
                ("Total HT facture", f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
                (f"TVA facture ({_decimal_str(vat_rate)} %)", f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
                ("Total TTC du devis", f"{_decimal_str(total_after_adjustment)} {currency}"),
            ]
        )
    if has_deposit:
        financial_recap_rows.extend(
            [
                ("Acompte preinscription", f"{_decimal_str(deposit_amount_ttc)} {currency}"),
                ("Reste a payer apres acompte", f"{_decimal_str(remaining_ttc_after_deposit)} {currency}"),
                ("Total HT restant", f"{_decimal_str(remaining_ht_after_deposit)} {currency}"),
                (f"TVA restante ({_decimal_str(vat_rate)} %)", f"{_decimal_str(remaining_vat_after_deposit)} {currency}"),
            ]
        )

    financial_recap_lines_html = "".join(
        "<p>"
        f"<strong>{escape(label)} :</strong> {escape(value)}"
        "</p>"
        for label, value in financial_recap_rows
    )
    financial_recap_block_html = (
        "<div class='quote-block'>"
        "<h2>Montant total du devis</h2>"
        f"{financial_recap_lines_html}"
        "</div>"
    )
    if has_deposit:
        balance_due_text = ""
        if schedule and len(schedule) == 1 and remaining_ttc_after_deposit > Decimal("0.00"):
            due_label = _schedule_due_label(schedule[0])
            item_method_label = str(schedule[0].get("payment_method") or document_context.get("payment_method_label") or "").strip()
            if _is_bank_transfer_payment_method(item_method_label) and due_label == "à réception de votre facture":
                balance_due_text = (
                    f"Le solde de {_decimal_str(remaining_ttc_after_deposit)} {escape(currency)} sera à régler par virement bancaire "
                    "à réception de votre facture, avant le démarrage des cours."
                )
            else:
                balance_due_text = (
                    f"Le solde de {_decimal_str(remaining_ttc_after_deposit)} {escape(currency)} sera à régler {escape(due_label)}."
                )
        elif remaining_ttc_after_deposit > Decimal("0.00"):
            balance_due_text = "Le solde sera à régler selon l échéancier indiqué ci-dessous."
        deposit_block_html = (
            "<p>Pour confirmer votre inscription et bloquer votre creneau, un acompte est requis dès validation du devis.</p>"
            + (f"<p>{balance_due_text}</p>" if balance_due_text else "")
            +
            f"<p><strong>Acompte a payer pour valider l inscription :</strong> {_decimal_str(deposit_amount_ttc)} {escape(currency)}</p>"
        )
    else:
        deposit_block_html = ""
    deposit_section_html = _section_html("Acompte preinscription", deposit_block_html)
    deposit_none_html = "" if has_deposit else "<p>Aucun acompte preinscription.</p>"

    services_table_html = _table_html(
        ["Activité", "Quantité", "Durée", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                _harmonize_display_text(line.title or "-"),
                _decimal_str(Decimal(line.quantity or 0)),
                f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in services
        ],
        empty_label="Aucune activité.",
    )
    product_long_descriptions = _product_long_descriptions_by_id(db=db, products=products)
    products_table_html = _table_html(
        ["Matériel", "Quantité", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                {
                    "html": (
                        f"<div>{escape(line.title or '-')}</div>"
                        + _small_description_html(
                            "\n".join(
                                _unique_text_parts(
                                    line.description,
                                    product_long_descriptions.get(line.product_id),
                                )
                            )
                        )
                    )
                },
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in products
        ],
        empty_label="Aucun matériel.",
    )
    kit_long_descriptions = _kit_long_descriptions_by_id(db=db, kits=kits)
    kit_composition = _kit_composition_by_id(db=db, kits=kits)
    kits_table_html = _table_html(
        ["Kit", "Quantité", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                {
                    "html": (
                        f"<div>{escape(line.title or '-')}</div>"
                        + _small_description_html(
                            "\n".join(
                                _unique_text_parts(
                                    line.description,
                                    kit_long_descriptions.get(line.kit_id),
                                )
                            )
                        )
                        + _kit_composition_html(kit_composition.get(line.kit_id, []))
                    )
                },
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in kits
        ],
        empty_label="Aucun kit.",
    )
    adjustments_table_html = _table_html(
        ["Type", "Intitulé", "Quantité", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                "Remise"
                if (line.line_type or "").strip().lower() == "discount"
                else "Supplément"
                if (line.line_type or "").strip().lower() == "surcharge"
                else (
                    "Remise"
                    if (line.master_item_type or "").strip().lower() == "discount_rule"
                    else "Supplément"
                ),
                _harmonize_display_text(line.title or "-"),
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in adjustments
        ],
        empty_label="Aucune remise ni supplément.",
    )
    other_fees_table_html = _table_html(
        ["Intitulé", "Quantité", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                _harmonize_display_text(line.title or "-"),
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in other_fees
        ],
        empty_label="Aucun autre frais.",
    )
    lines_table_html = _table_html(
        ["Catégorie", "Intitulé", "Quantité", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                "Remise"
                if (line.line_type or "").strip().lower() == "discount"
                else "Supplément"
                if (line.line_type or "").strip().lower() == "surcharge"
                else ("Service" if (line.line_category or "").lower() == "service" else ("Kit" if line.kit_id else "Matériel")),
                _harmonize_display_text(line.title or "-"),
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in lines
        ],
        empty_label="Aucune ligne.",
    )

    schedule = document_context["schedule"]
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
    )
    special_card_deposit_lines = _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
    )
    special_deposit_lines = special_bank_transfer_deposit_lines or special_card_deposit_lines
    payment_schedule_rows = [
        [
            str(item.get("label") or "-"),
            f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
            _schedule_due_label(item),
            str(item.get("payment_method") or "-"),
        ]
        for item in schedule
    ]
    payment_schedule_table_html = _table_html(
        ["Échéance", "Montant", "Quand", "Type"],
        payment_schedule_rows,
        empty_label="Aucun échéancier.",
    )
    if special_deposit_lines:
        payment_schedule_table_html = ""
    elif not display_flags["showPaymentScheduleDetailed"]:
        compact_notice = str(document_context["payment_schedule_compact_notice"] or "").strip()
        if schedule and len(schedule) <= 1:
            payment_schedule_table_html = ""
        elif compact_notice:
            payment_schedule_table_html = f"<p>{escape(compact_notice)}</p>"
        elif not schedule:
            payment_schedule_table_html = "<p>Aucun échéancier.</p>"
        else:
            payment_schedule_table_html = ""

    sessions = [item for item in _json_list(_json_object(quote.calendar_snapshot).get("sessions")) if isinstance(item, dict)]
    planning_blocks_table_html, _ = _planning_blocks_table_html(_json_object(quote.calendar_snapshot))
    calendar_sessions_table_html = _table_html(
        ["Date", "Début", "Fin", "Durée", "Modalité"],
        [
            [
                str(item.get("date") or "-"),
                str(item.get("start_time") or item.get("start_at") or "-"),
                str(item.get("end_time") or item.get("end_at") or "-"),
                f"{item.get('duration_minutes')} min" if item.get("duration_minutes") is not None else "-",
                str(item.get("modality") or "-"),
            ]
            for item in sessions
        ],
        empty_label="Aucun cours planifié.",
    )
    calendar_table_html, calendar_activities_count = _calendar_visual_summary(sessions)
    calendar_summary = _calendar_summary_text(
        session_count=len(sessions),
        activity_count=calendar_activities_count,
    )
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=has_deposit,
        deposit_amount_ttc=deposit_amount_ttc,
        currency=currency,
        payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
        remaining_ttc_after_deposit=remaining_ttc_after_deposit,
    )
    payment_schedule_summary = (
        ""
        if special_deposit_lines
        else _payment_schedule_summary_text(
            schedule=schedule,
            has_deposit=has_deposit,
            deposit_amount_ttc=deposit_amount_ttc,
            currency=currency,
            payment_method_label=str(document_context.get("payment_method_label") or _resolve_payment_method_label(quote=quote)),
            remaining_ttc_after_deposit=remaining_ttc_after_deposit,
        )
    )

    activities_planning_section_html = _section_html(
        "Cours et options choisis",
        planning_blocks_table_html,
    )
    services_section_html = _section_html("Cours inclus dans le devis", services_table_html)
    adjustments_section_html = _section_html("Remises appliquées", adjustments_table_html)
    products_section_html = _section_html("Matériel pédagogique", products_table_html)
    kits_section_html = _section_html("Frais et services inclus dans l’inscription", kits_table_html)
    other_fees_section_html = _section_html("Autres frais", other_fees_table_html)
    payment_schedule_section_html = _section_html("Échéancier de paiement", payment_schedule_table_html)
    calendar_section_html = _section_html("Calendrier prévisionnel des cours", calendar_table_html)

    cgv_label, _ = _load_terms_template_content(db=db, quote=quote)
    prospect_data = document_context["prospect_data"]
    client_data = document_context["client_data"]
    recipient_name = (
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or client_data.get("client_full_name")
        or "-"
    )
    recipient_email = (
        prospect_data.get("parent_email")
        or prospect_data.get("adult_email")
        or client_data.get("client_email")
        or "-"
    )
    payment_method_label = str(document_context["payment_method_label"] or "Paiement non précisé")
    solfege_slot = _json_object(document_context.get("solfege_selected_slot"))
    solfege_slot_label = _slot_label(solfege_slot) if solfege_slot else ""
    solfege_duration = document_context.get("solfege_duration_minutes")
    solfege_duration_label = f" ({solfege_duration} min)" if solfege_duration else ""
    solfege_slot_suffix = f" · {solfege_slot_label}" if solfege_slot_label else ""
    solfege_available_slots = [
        _sanitize_slot_label_text(item)
        for item in _json_list(document_context.get("solfege_available_slots"))
        if str(item).strip()
    ]
    solfege_display_slots, solfege_mode_label = _factorize_slot_labels(solfege_available_slots)
    solfege_full = (
        f"Solfege souscrit - Niveau {document_context.get('solfege_level') or '-'}"
        f"{solfege_duration_label}"
        f"{solfege_slot_suffix}"
    )
    show_solfege_pending_notice = bool(document_context.get("solfege_pending_selection")) and not solfege_slot_label
    masterclass_blocks = _json_list(document_context.get("masterclass_blocks"))
    masterclass_full = "Masterclass du samedi souscrite."
    if masterclass_blocks:
        labels: list[str] = []
        for block in masterclass_blocks[:3]:
            if not isinstance(block, dict):
                continue
            session = str(block.get("session") or "").strip()
            location = str(block.get("location_label") or "").strip()
            label = " · ".join(part for part in (session, location) if part)
            if label:
                labels.append(label)
        if labels:
            masterclass_full = f"Masterclass du samedi souscrite - {'; '.join(labels)}"

    def _identity_row_cells(label: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or normalized == "-":
            return ""
        return (
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(normalized)}</td>"
            "</tr>"
        )

    def _identity_card(title: str, rows: list[str], empty_label: str) -> str:
        body = "".join(row for row in rows if row)
        if not body:
            body = (
                "<tr>"
                f"<td>{escape(empty_label)}</td>"
                "<td>-</td>"
                "</tr>"
            )
        return (
            "<section class='quote-identity-card'>"
            f"<h3>{escape(title)}</h3>"
            "<table class='quote-identity-meta' cellspacing='0' cellpadding='0'>"
            f"{body}"
            "</table>"
            "</section>"
        )

    adult_email_value = prospect_data.get("adult_email") or recipient_email
    adult_phone_value = str(prospect_data.get("adult_phone") or client_data.get("client_phone") or "").strip()
    adult_address_value = str(prospect_data.get("adult_address") or client_data.get("client_address") or "").strip()

    child_birth_date_value = _birth_date_label(str(prospect_data.get("child_birth_date") or ""))
    parent_email_value = prospect_data.get("parent_email") or recipient_email
    parent_phone_value = str(prospect_data.get("parent_phone") or "").strip()
    parent_address_value = str(prospect_data.get("parent_address") or "").strip()
    responsible_name_value = str(
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or recipient_name
        or "-"
    ).strip()
    responsible_email_value = str(parent_email_value or adult_email_value or "").strip()
    responsible_phone_value = str(parent_phone_value or adult_phone_value or "").strip()
    responsible_address_value = str(parent_address_value or adult_address_value or "").strip()

    child_identity_card_html = _identity_card(
        "Informations de l’élève",
        [
            _identity_row_cells("Élève", str(prospect_data.get("child_full_name") or "-")),
            _identity_row_cells("Date de naissance", child_birth_date_value),
        ],
        "Élève",
    )
    responsible_identity_card_html = _identity_card(
        "Informations de l’adulte responsable",
        [
            _identity_row_cells("Adulte responsable", responsible_name_value),
            _identity_row_cells("Email", responsible_email_value),
            _identity_row_cells("Téléphone", responsible_phone_value),
            _identity_row_cells("Adresse", responsible_address_value),
        ],
        "Adulte responsable",
    )
    adult_identity_card_html = _identity_card(
        "Informations de l’adulte responsable",
        [
            _identity_row_cells("Adulte responsable", str(prospect_data.get("adult_full_name") or recipient_name or "-")),
            _identity_row_cells("Email", str(adult_email_value or "")),
            _identity_row_cells("Téléphone", adult_phone_value),
            _identity_row_cells("Adresse", adult_address_value),
        ],
        "Adulte responsable",
    )
    prospect_identity_block_html = (
        "<div class='quote-identity-grid'>"
        + (child_identity_card_html + responsible_identity_card_html if display_flags["showChildBlock"] else adult_identity_card_html)
        + "</div>"
    )
    # Solfege et masterclass restent des activites planning, mais on expose un resume optionnel pour le document.
    solfege_block_html = ""
    if show_solfege_pending_notice:
        solfege_lines = [
            "<strong>Option solfège : incluse dans le présent devis.</strong>",
            f"Niveau estimé : {escape(str(document_context.get('solfege_level') or '-'))}{escape(solfege_duration_label)}",
            "Créneau retenu : à sélectionner",
        ]
        if solfege_display_slots:
            solfege_lines.append(f"Créneaux disponibles : {escape(' ; '.join(solfege_display_slots))}")
        if solfege_mode_label:
            solfege_lines.append(escape(solfege_mode_label))
        solfege_lines.append(escape(_solfege_included_pending_notice_text()))
        solfege_block_html = "<p>" + "<br/>".join(solfege_lines) + "</p>"
    elif display_flags["showSolfegeSection"]:
        solfege_block_html = f"<p><strong>Option solfège : incluse dans le présent devis.</strong><br/>{escape(solfege_full)}</p>"
    masterclass_common_text = (
        "Masterclass du samedi (complément aux 2 cours collectifs hebdomadaires) : une session de 3h dédiée à la "
        "pratique au piano, avec un focus approfondi sur la musicalité et l’interprétation."
    )
    masterclass_detail_text = escape(masterclass_full) if masterclass_full else ""
    masterclass_block_html = (
        "<p><strong>Option Masterclass du samedi : souscrite.</strong><br/>"
        f"<i>{masterclass_detail_text}</i><br/>"
        f"<i>{escape(masterclass_common_text)}</i></p>"
        if display_flags["showMasterclassSection"]
        else ""
    )
    pass_recup_common_text = (
        "Le Pass Récup’ permet de rattraper un cours collectif manqué, dans la limite de 4 rattrapages par année "
        "scolaire. Le rattrapage peut s’effectuer soit sur un cours collectif en présentiel, sous réserve de "
        "disponibilité d’un créneau, soit sur un cours collectif en ligne, sur des créneaux dédiés. Le pass est "
        "utilisable uniquement en cas d’absence signalée. Il est valable pour l’année scolaire en cours et n’est "
        "pas remboursable. Sans souscription à ce pass, aucun rattrapage ne pourra être proposé, quelle que soit la "
        "raison de l’absence."
    )
    pass_recup_block_html = (
        "<p><strong>Option Pass Récup : souscrite.</strong><br/>"
        f"<i>{escape(pass_recup_common_text)}</i></p>"
        if display_flags["showPassRecupSection"]
        else ""
    )
    pass_recup_compact_notice_html = (
        "<p><strong>Option Pass Récup : non souscrite.</strong>"
        "<br/><font size='10' color='#6b7280'><i>"
        "Ce pass permet de rattraper un cours collectif manqué sur un créneau en présentiel "
        "(si une place est disponible), ou à défaut, sur un créneau collectif en ligne dédié."
        "<br/>&bull; Limité à 4 rattrapages par an"
        "</i></font></p>"
        if display_flags["showPassRecupCompactNotice"]
        else ""
    )
    options_section_html = _section_html(
        "Vos options",
        "".join(
            fragment
            for fragment in (solfege_block_html, masterclass_block_html, pass_recup_block_html, pass_recup_compact_notice_html)
            if str(fragment or "").strip()
        ),
    )
    payment_instruction = str(document_context.get("payment_instruction") or "").strip()
    payment_method_display_label = payment_method_label.lower() if special_bank_transfer_deposit_lines else payment_method_label
    payment_method_block_html = f"<p><strong>Mode de paiement :</strong> {escape(payment_method_display_label)}</p>"
    if special_deposit_lines:
        payment_method_block_html += "".join(f"<p>{escape(line)}</p>" for line in special_deposit_lines)
    if payment_instruction:
        payment_method_block_html = (
            f"{payment_method_block_html}<p><strong>Consignes :</strong> {escape(payment_instruction)}</p>"
        )
    quote_status_date_label, quote_status_date_value, quote_status_cover_line = _quote_status_date_display(quote)

    brand_logo_html = _brand_logo_html(db=db, variant="header")
    cover_logo_html = _brand_logo_html(db=db, variant="cover")
    header_standard_html = (
        "<table class='quote-running-header' width='100%' cellspacing='0' cellpadding='0'>"
        "<tr>"
        "<td width='68%' align='left' valign='middle'>"
        "<span style='font-size:11px;font-weight:700;color:#111827;'>PIANO ACADEMIE</span>"
        "</td>"
        "<td width='32%' align='right' valign='middle' style='font-size:10px;color:#334155;'>"
        f"<strong>Devis {escape(quote.quote_number or '-')}</strong>"
        "</td>"
        "</tr>"
        "</table>"
    )
    cover_page_standard_html = (
        "<section class='quote-cover'>"
        f"{cover_logo_html}"
        "<h1 class='quote-cover-title'>Votre devis d’inscription</h1>"
        f"<p class='quote-cover-subtitle'>Année scolaire {escape(quote.school_year_label or '-')}</p>"
        f"<p class='quote-cover-name'>{escape(prospect_data.get('child_full_name') or recipient_name)}</p>"
        "<div class='quote-cover-meta'>"
        f"<p>Type de prospect: {escape(str(prospect_data.get('prospect_type_label') or '-'))}</p>"
        f"<p>Document généré le {escape(_datetime_label(_utcnow()))}</p>"
        f"<p>{escape(quote_status_cover_line)}</p>"
        "</div>"
        "</section>"
        "<div class='quote-page-break'></div>"
    )

    values: dict[str, str] = {
        "quote_number": quote.quote_number or "-",
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "total_ttc": _decimal_str(total_ttc),
        "total_ttc_before_adjustment": _decimal_str(total_before_adjustment),
        "total_ttc_after_adjustment": _decimal_str(total_after_adjustment),
        "total_ht": _decimal_str(total_ht_after_adjustment),
        "total_ht_before_adjustment": _decimal_str(total_ht_before_adjustment),
        "total_ht_after_adjustment": _decimal_str(total_ht_after_adjustment),
        "vat_rate": _decimal_str(vat_rate),
        "vat_amount": _decimal_str(vat_amount_after_adjustment),
        "vat_amount_before_adjustment": _decimal_str(vat_amount_before_adjustment),
        "vat_amount_after_adjustment": _decimal_str(vat_amount_after_adjustment),
        "currency": currency,
        "expires_at": _date_label(quote.expires_at),
        "sent_at": _datetime_label(quote.sent_at),
        "generated_at": _datetime_label(_utcnow()),
        "school_year_label": (quote.school_year_label or "-"),
        "quote_status_date_label": quote_status_date_label,
        "quote_status_date_value": quote_status_date_value,
        "calendar_summary": calendar_summary,
        "payment_schedule_summary": payment_schedule_summary,
        "financial_adjustment_type": adjustment_type,
        "financial_adjustment_type_label": adjustment_type_label,
        "financial_adjustment_amount_ttc": _decimal_str(adjustment_amount),
        "financial_adjustment_signed_amount_ttc": _decimal_str(adjustment_signed_amount),
        "financial_adjustment_effective_date": adjustment_effective_date,
        "financial_adjustment_label": adjustment_label,
        "financial_adjustment_display_title": adjustment_display_title if has_financial_adjustment else "",
        "financial_adjustment_display_line": adjustment_display_line,
        "financial_adjustment_impact_label": adjustment_impact_label,
        "has_financial_adjustment": "true" if has_financial_adjustment else "false",
        "has_credit_adjustment": "true" if has_credit_adjustment else "false",
        "has_debt_adjustment": "true" if has_debt_adjustment else "false",
        "financial_adjustment_block_html": financial_adjustment_block_html,
        "financial_adjustment_section_html": financial_adjustment_section_html,
        "financial_adjustment_none_html": financial_adjustment_none_html,
        "financial_recap_block_html": financial_recap_block_html,
        "total_ttc_before_adjustment_html": total_ttc_before_adjustment_html,
        "total_before_adjustment": _decimal_str(total_before_adjustment),
        "total_after_adjustment": _decimal_str(total_after_adjustment),
        "has_deposit": "true" if has_deposit else "false",
        "deposit_enabled": "true" if has_deposit else "false",
        "deposit_amount_ttc": _decimal_str(deposit_amount_ttc),
        "deposit_ht_amount": _decimal_str(deposit_ht_amount),
        "deposit_vat_amount": _decimal_str(deposit_vat_amount),
        "remaining_ttc_after_deposit": _decimal_str(remaining_ttc_after_deposit),
        "remaining_ht_after_deposit": _decimal_str(remaining_ht_after_deposit),
        "remaining_vat_after_deposit": _decimal_str(remaining_vat_after_deposit),
        "deposit_block_html": deposit_block_html,
        "deposit_section_html": deposit_section_html,
        "deposit_none_html": deposit_none_html,
        "payment_method_label": payment_method_label,
        "payment_instruction": payment_instruction,
        "payment_schedule_compact_notice": document_context["payment_schedule_compact_notice"] or "",
        "document_style_html": _document_style_html(),
        "brand_logo_html": brand_logo_html,
        "header_standard_html": header_standard_html,
        "cover_page_standard_html": cover_page_standard_html,
        "page_break_html": "<div class='quote-page-break'></div>",
        "footer_standard_html": (
            "<table class='quote-running-footer' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr>"
            "<td width='33%' align='left' valign='top'>"
            "Piano Academie<br/>"
            "1 rue de Richelieu<br/>"
            "75001 Paris"
            "</td>"
            "<td width='34%' align='center' valign='top'>"
            "SIRET 82805141700032<br/>"
            "FR 74828051417"
            "</td>"
            f"<td width='33%' align='right' valign='top'>{escape(quote.quote_number or '-')}</td>"
            "</tr>"
            "</table>"
        ),
        "cgv_version": cgv_label or "-",
        "services_count": str(len(services)),
        "products_count": str(len(products)),
        "kits_count": str(len(kits)),
        "adjustments_count": str(len(adjustments)),
        "other_fees_count": str(len(other_fees)),
        "lines_count": str(len(lines)),
        "prospect_identity_block_html": prospect_identity_block_html,
        "solfege_block_html": solfege_block_html,
        "masterclass_block_html": masterclass_block_html,
        "pass_recup_block_html": pass_recup_block_html,
        "pass_recup_compact_notice_html": pass_recup_compact_notice_html,
        "options_section_html": options_section_html,
        "payment_method_block_html": payment_method_block_html,
        "activities_planning_section_html": activities_planning_section_html,
        "services_section_html": services_section_html,
        "adjustments_section_html": adjustments_section_html,
        "products_section_html": products_section_html,
        "kits_section_html": kits_section_html,
        "other_fees_section_html": other_fees_section_html,
        "payment_schedule_section_html": payment_schedule_section_html,
        "calendar_section_html": calendar_section_html,
        "services_table_html": services_table_html,
        "activities_planning_table_html": planning_blocks_table_html,
        "products_table_html": products_table_html,
        "kits_table_html": kits_table_html,
        "adjustments_table_html": adjustments_table_html,
        "other_fees_table_html": other_fees_table_html,
        "lines_table_html": lines_table_html,
        "payment_schedule_table_html": payment_schedule_table_html,
        "calendar_table_html": calendar_table_html,
        "calendar_activity_semesters_html": calendar_table_html,
        "calendar_sessions_table_html": calendar_sessions_table_html,
        "show_adult_block": "true" if display_flags["showAdultBlock"] else "false",
        "show_child_block": "true" if display_flags["showChildBlock"] else "false",
        "show_solfege_section": "true" if display_flags["showSolfegeSection"] else "false",
        "show_masterclass_section": "true" if display_flags["showMasterclassSection"] else "false",
        "show_pass_recup_section": "true" if display_flags["showPassRecupSection"] else "false",
        "show_payment_schedule_detailed": "true" if display_flags["showPaymentScheduleDetailed"] else "false",
    }
    values.update(prospect_data)
    values.update(client_data)

    html_keys = {
        "prospect_identity_block_html",
        "solfege_block_html",
        "masterclass_block_html",
        "pass_recup_block_html",
        "pass_recup_compact_notice_html",
        "options_section_html",
        "payment_method_block_html",
        "activities_planning_section_html",
        "services_section_html",
        "adjustments_section_html",
        "products_section_html",
        "kits_section_html",
        "other_fees_section_html",
        "payment_schedule_section_html",
        "calendar_section_html",
        "financial_adjustment_block_html",
        "financial_adjustment_section_html",
        "financial_adjustment_none_html",
        "financial_recap_block_html",
        "deposit_block_html",
        "deposit_section_html",
        "deposit_none_html",
        "total_ttc_before_adjustment_html",
        "services_table_html",
        "activities_planning_table_html",
        "products_table_html",
        "kits_table_html",
        "adjustments_table_html",
        "other_fees_table_html",
        "lines_table_html",
        "payment_schedule_table_html",
        "calendar_table_html",
        "calendar_activity_semesters_html",
        "calendar_sessions_table_html",
        "document_style_html",
        "brand_logo_html",
        "header_standard_html",
        "cover_page_standard_html",
        "page_break_html",
        "footer_standard_html",
    }
    return values, html_keys, document_context


def build_quote_template_values(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    values, html_keys, document_context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    return dict(values), set(html_keys), dict(document_context)


def _default_quote_body_template() -> str:
    return (
        "{document_style_html}"
        "{cover_page_standard_html}"
        "{header_standard_html}"
        "<h1>Devis {quote_number}</h1>"
        "<p><strong>Destinataire:</strong> {recipient_name}</p>"
        "<p><strong>Année scolaire:</strong> {school_year_label}</p>"
        "<p><strong>{quote_status_date_label}:</strong> {quote_status_date_value}</p>"
        "{page_break_html}"
        "<h2>Informations de l’élève et du responsable</h2>"
        "<div class='quote-block'>"
        "{prospect_identity_block_html}"
        "</div>"
        "{activities_planning_section_html}"
        "{services_section_html}"
        "{adjustments_section_html}"
        "{products_section_html}"
        "{kits_section_html}"
        "{other_fees_section_html}"
        "{deposit_section_html}"
        "{financial_recap_block_html}"
        "<h2>Règlement et échéancier</h2>"
        "{payment_method_block_html}"
        "<p>{payment_schedule_summary}</p>"
        "{payment_schedule_table_html}"
        "{financial_adjustment_section_html}"
        "{options_section_html}"
        "<h2>Calendrier prévisionnel des cours</h2>"
        "<p><strong>Vue d’ensemble du calendrier :</strong> {calendar_summary}</p>"
        "{calendar_activity_semesters_html}"
        "{footer_standard_html}"
    )


def _render_quote_body_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    _, body_template = _load_quote_template_snapshot(db=db, quote=quote)
    template = _normalize_template_source(body_template or _default_quote_body_template())
    template = _strip_legacy_recipient_email_markup(template)
    lowered_template = template.lower()
    if "{deposit_section_html}" not in lowered_template and "{deposit_block_html}" not in lowered_template:
        if "{payment_method_block_html}" in lowered_template:
            template = template.replace("{payment_method_block_html}", "{deposit_section_html}{payment_method_block_html}", 1)
        else:
            template += "{deposit_section_html}"
    if "{other_fees_section_html}" not in lowered_template and "{other_fees_table_html}" not in lowered_template:
        if "{kits_section_html}" in lowered_template:
            template = template.replace("{kits_section_html}", "{kits_section_html}{other_fees_section_html}", 1)
        elif "{kits_table_html}" in lowered_template:
            template = template.replace("{kits_table_html}", "{kits_table_html}{other_fees_section_html}", 1)
        else:
            template += "{other_fees_section_html}"
    if "{financial_recap_block_html}" not in template:
        legacy_financial_tokens = (
            "{total_ttc_before_adjustment_html}",
            "{total_ht_before_adjustment}",
            "{vat_amount_before_adjustment}",
            "{total_ht_after_adjustment}",
            "{vat_amount_after_adjustment}",
            "{total_ttc_after_adjustment}",
            "{total_ht}",
            "{vat_amount}",
            "{total_after_adjustment}",
            "{total_ttc}",
        )
        if any(token in template for token in legacy_financial_tokens):
            template = re.sub(
                r"<p[^>]*>\s*<strong>\s*"
                r"(?:Total(?:\s+TTC(?:\s+avant\s+ajustement|\s+facture)?|\s+HT(?:\s+avant\s+ajustement)?|"
                r"\s+avant\s+ajustement)|TVA(?:\s*\([^)]+\))?(?:\s+avant\s+ajustement|\s+facture)?)"
                r"\s*:?\s*</strong>.*?</p>",
                "",
                template,
                flags=re.IGNORECASE | re.DOTALL,
            )
            template += "{financial_recap_block_html}"
    template = _normalize_block_placeholder_wrappers(
        template,
        keys={
            "document_style_html",
            "brand_logo_html",
            "header_standard_html",
            "cover_page_standard_html",
            "page_break_html",
            "footer_standard_html",
            "prospect_identity_block_html",
            "solfege_block_html",
            "masterclass_block_html",
            "pass_recup_block_html",
            "options_section_html",
            "payment_method_block_html",
            "activities_planning_section_html",
            "services_section_html",
            "adjustments_section_html",
            "products_section_html",
            "kits_section_html",
            "other_fees_section_html",
            "payment_schedule_section_html",
            "calendar_section_html",
            "services_table_html",
            "activities_planning_table_html",
            "products_table_html",
            "kits_table_html",
            "adjustments_table_html",
            "other_fees_table_html",
            "lines_table_html",
            "payment_schedule_table_html",
            "calendar_table_html",
            "calendar_activity_semesters_html",
            "calendar_sessions_table_html",
            "financial_adjustment_block_html",
            "financial_adjustment_section_html",
            "financial_adjustment_none_html",
            "financial_recap_block_html",
            "deposit_block_html",
            "deposit_section_html",
            "deposit_none_html",
        },
    )
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    rendered = _apply_template(template, values=values, html_keys=html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _dedupe_retained_activities_tables(rendered)
    if not str(values.get("adjustments_section_html") or "").strip():
        rendered = re.sub(
            r"<h[1-6]\b[^>]*>\s*Remises\s+et\s+suppl(?:e|é)ments\s*</h[1-6]>\s*",
            "",
            rendered,
            flags=re.IGNORECASE,
        )
    if not str(values.get("options_section_html") or "").strip():
        rendered = re.sub(
            r"<h[1-6]\b[^>]*>\s*Vos\s+options\s*</h[1-6]>\s*",
            "",
            rendered,
            flags=re.IGNORECASE,
        )
    lowered_template = template.lower()
    if "{activities_planning_table_html}" not in lowered_template and "{activities_planning_section_html}" not in lowered_template:
        rendered += values.get("activities_planning_section_html", "")
    rendered = _replace_expiration_mentions_for_approved_quote(rendered, quote)
    rendered = _enforce_family_page_break(rendered)
    return _as_html_fragment(rendered)


def _render_quote_terms_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    rendered_terms = _render_terms_content_html(content=cgv_content, values=values, html_keys=html_keys)
    header_html = values.get("header_standard_html", "")
    footer_html = values.get("footer_standard_html", "")
    return (
        "<section>"
        f"{header_html}"
        "<h2 class='quote-terms-title'>Conditions d’inscription 2026–2027</h2>"
        "<div class='quote-block'>"
        f"<p><strong>{escape(cgv_label or 'Version non précisée')}</strong></p>"
        f"{_as_html_fragment(rendered_terms or 'Aucune CGV snapshotée.')}"
        "</div>"
        f"{footer_html}"
        "</section>"
    )


def render_quote_combined_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience)
    base_css = _document_style_html()
    return (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )


def render_quote_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    return render_quote_combined_html(db=db, quote=quote, lines=lines, audience=audience)


def render_quote_parts_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[str, str, str]:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience)
    base_css = _document_style_html()
    combined_html = (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )
    return body_html, terms_html, combined_html


def render_quote_document_bundle(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    values, _, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    body_html, terms_html, combined_html = render_quote_parts_html(db=db, quote=quote, lines=lines, audience=audience)
    return {
        "audience": audience,
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "body_html": body_html,
        "terms_html": terms_html,
        "combined_html": combined_html,
        "display_flags": context.get("display_flags", {}),
        "visible_blocks": context.get("visible_blocks", []),
        "hidden_blocks": context.get("hidden_blocks", []),
        "payment_method_label": values.get("payment_method_label", ""),
        "payment_schedule_compact_notice": values.get("payment_schedule_compact_notice", ""),
    }


def render_quote_pdf(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    _, _, combined_html = render_quote_parts_html(db=db, quote=quote, lines=lines, audience=audience)
    return render_quote_pdf_from_combined_html(
        db=db,
        quote=quote,
        lines=lines,
        combined_html=combined_html,
        audience=audience,
    )


def _safe_logo_reader(data_url: str) -> ImageReader | None:
    raw = str(data_url or "").strip()
    if not raw.startswith("data:image/") or "," not in raw:
        return None
    payload = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(payload, validate=False)
    except Exception:
        return None
    try:
        return ImageReader(io.BytesIO(content))
    except Exception:
        return None


def _quote_pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475467"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=2,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceBefore=2,
            spaceAfter=5,
        ),
        "text": ParagraphStyle(
            "text",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "text_center": ParagraphStyle(
            "text_center",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "small_muted": ParagraphStyle(
            "small_muted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#667085"),
            spaceAfter=4,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12.5,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
            wordWrap="LTR",
            splitLongWords=False,
            spaceAfter=0,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            wordWrap="LTR",
            splitLongWords=False,
            spaceAfter=0,
        ),
    }


def _table_for_pdf(
    headers: list[str],
    rows: list[list[Any]],
    *,
    width: float,
    styles: dict[str, ParagraphStyle],
    col_widths: list[float] | None = None,
) -> Table:
    def _as_cell(value: Any, style: ParagraphStyle) -> Paragraph:
        if isinstance(value, Paragraph):
            return value
        if isinstance(value, dict):
            raw_html = value.get("html")
            if raw_html is not None:
                return Paragraph(str(raw_html), style)
            text = escape(str(value.get("text") or "")).replace("\n", "<br/>")
            subtext = str(value.get("subtext") or "").strip()
            if subtext:
                text += (
                    "<br/><font size='9' color='#64748b'>"
                    + escape(subtext).replace("\n", "<br/>")
                    + "</font>"
                )
            return Paragraph(text or "-", style)
        text = str(value if value is not None else "-")
        text = escape(text).replace("\n", "<br/>")
        return Paragraph(text, style)

    normalized_rows = rows if rows else [["-"] * max(1, len(headers))]
    data: list[list[Any]] = [
        [_as_cell(cell, styles["table_header"]) for cell in headers],
        *[[_as_cell(cell, styles["table_cell"]) for cell in row] for row in normalized_rows],
    ]
    col_count = len(headers) if headers else 1
    if col_widths and len(col_widths) == col_count:
        total_ratio = sum(max(0.0, float(value)) for value in col_widths)
        if total_ratio > 0:
            final_widths = [width * (max(0.0, float(value)) / total_ratio) for value in col_widths]
        else:
            col_width = width / col_count
            final_widths = [col_width] * col_count
    else:
        col_width = width / col_count
        final_widths = [col_width] * col_count
    table = Table(data, colWidths=final_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF7")),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.9, colors.HexColor("#c4cfde")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _terms_lines_for_pdf(content: str, *, values: dict[str, str]) -> list[str]:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return ["Aucune condition générale."]
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return lines or ["Aucune condition générale."]


_TERMS_RENDER_BLOCK_KEYS = {
    "document_style_html",
    "brand_logo_html",
    "header_standard_html",
    "cover_page_standard_html",
    "page_break_html",
    "footer_standard_html",
    "prospect_identity_block_html",
    "solfege_block_html",
    "masterclass_block_html",
    "pass_recup_block_html",
    "pass_recup_compact_notice_html",
    "options_section_html",
    "payment_method_block_html",
    "activities_planning_section_html",
    "services_section_html",
    "adjustments_section_html",
    "products_section_html",
    "kits_section_html",
    "other_fees_section_html",
    "payment_schedule_section_html",
    "calendar_section_html",
    "payment_schedule_table_html",
    "calendar_table_html",
    "calendar_activity_semesters_html",
    "financial_recap_block_html",
    "deposit_block_html",
    "deposit_section_html",
    "deposit_none_html",
    "other_fees_table_html",
}


def _render_terms_content_html(*, content: str, values: dict[str, str], html_keys: set[str]) -> str:
    normalized_terms = _normalize_template_source(content or "")
    normalized_terms = _strip_legacy_recipient_email_markup(normalized_terms)
    normalized_terms = _normalize_block_placeholder_wrappers(
        normalized_terms,
        keys=_TERMS_RENDER_BLOCK_KEYS,
    )
    rendered_terms = _apply_template(normalized_terms, values=values, html_keys=html_keys, html_output=True)
    rendered_terms = _cleanup_rendered_block_markup(rendered_terms)
    rendered_terms = _normalize_template_source(rendered_terms)
    return _cleanup_legacy_terms_layout(rendered_terms)


def _reportlab_font_size(value: str) -> str | None:
    raw = str(value or "").strip().lower()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(px|pt)?", raw)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = match.group(2) or "pt"
    if unit == "px":
        amount *= 0.75
    if amount <= 0:
        return None
    rounded = round(amount, 1)
    return str(int(rounded)) if float(rounded).is_integer() else str(rounded)


def _reportlab_font_face(*, family: str, bold: bool, italic: bool) -> str | None:
    raw = str(family or "").strip().strip("'\"")
    if not raw:
        return None
    normalized = raw.casefold()
    base = "Helvetica"
    if any(token in normalized for token in ("courier", "mono", "menlo", "monaco", "consolas")):
        base = "Courier"
    elif any(token in normalized for token in ("times", "georgia", "serif")):
        base = "Times"
    if base == "Helvetica":
        if bold and italic:
            return "Helvetica-BoldOblique"
        if bold:
            return "Helvetica-Bold"
        if italic:
            return "Helvetica-Oblique"
        return "Helvetica"
    if base == "Times":
        if bold and italic:
            return "Times-BoldItalic"
        if bold:
            return "Times-Bold"
        if italic:
            return "Times-Italic"
        return "Times-Roman"
    if bold and italic:
        return "Courier-BoldOblique"
    if bold:
        return "Courier-Bold"
    if italic:
        return "Courier-Oblique"
    return "Courier"


def _inline_style_map(style_value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in str(style_value or "").split(";"):
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            out[normalized_key] = normalized_value
    return out


def _reportlab_markup_from_attrs(tag: str, attrs: dict[str, str]) -> tuple[str, str]:
    style_map = _inline_style_map(attrs.get("style", ""))
    bold = False
    weight = style_map.get("font-weight", "").strip().lower()
    if weight == "bold":
        bold = True
    elif weight.isdigit():
        bold = int(weight) >= 600
    italic = "italic" in style_map.get("font-style", "").strip().lower()
    underline = "underline" in style_map.get("text-decoration", "").strip().lower()
    family = attrs.get("face") or style_map.get("font-family", "")
    size = attrs.get("size") or style_map.get("font-size", "")
    color = attrs.get("color") or style_map.get("color", "")

    font_attrs: list[str] = []
    face = _reportlab_font_face(family=family, bold=bold, italic=italic) if family else None
    if face:
        font_attrs.append(f"face='{escape(face)}'")
        bold = False
        italic = False
    parsed_size = _reportlab_font_size(size) if size else None
    if parsed_size:
        font_attrs.append(f"size='{escape(parsed_size)}'")
    normalized_color = str(color or "").strip()
    if normalized_color and re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+", normalized_color):
        font_attrs.append(f"color='{escape(normalized_color)}'")

    open_parts: list[str] = []
    close_parts: list[str] = []
    if font_attrs:
        open_parts.append(f"<font {' '.join(font_attrs)}>")
        close_parts.insert(0, "</font>")
    if bold:
        open_parts.append("<b>")
        close_parts.insert(0, "</b>")
    if italic:
        open_parts.append("<i>")
        close_parts.insert(0, "</i>")
    if underline:
        open_parts.append("<u>")
        close_parts.insert(0, "</u>")
    return "".join(open_parts), "".join(close_parts)


class _ReportLabTermsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._current: list[str] = []
        self._current_style = "text"
        self._open_tags: list[tuple[str, str]] = []
        self._ignored_depth = 0
        self._list_item_depth = 0

    def _begin_block(self, style: str) -> None:
        self._flush_block()
        self._current_style = style

    def _append(self, markup: str) -> None:
        if markup:
            self._current.append(markup)

    def _current_markup(self) -> str:
        return "".join(self._current).strip()

    def _close_tag(self, tag: str) -> None:
        if self._open_tags and self._open_tags[-1][0] == tag:
            _, closer = self._open_tags.pop()
            self._append(closer)

    def _flush_block(self) -> None:
        while self._open_tags:
            _, closer = self._open_tags.pop()
            self._append(closer)
        markup = "".join(self._current).strip()
        markup = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br/><br/>", markup, flags=re.IGNORECASE)
        if markup:
            self.blocks.append((self._current_style, markup))
        self._current = []
        self._current_style = "text"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"style", "script"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        attrs_dict = {str(key or "").lower(): str(value or "") for key, value in attrs}
        if normalized_tag == "li":
            self._begin_block("text")
            self._list_item_depth += 1
            self._append("• ")
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"}:
            if self._list_item_depth > 0:
                current = self._current_markup()
                if current and current != "•" and current != "• " and not current.endswith("<br/>"):
                    self._append("<br/>")
                return
            style = "h1" if normalized_tag == "h1" else "h2" if normalized_tag == "h2" else "h3" if normalized_tag.startswith("h") else "text"
            self._begin_block(style)
            return
        if normalized_tag == "br":
            self._append("<br/>")
            return
        if normalized_tag in {"strong", "b"}:
            self._append("<b>")
            self._open_tags.append((normalized_tag, "</b>"))
            return
        if normalized_tag in {"em", "i"}:
            self._append("<i>")
            self._open_tags.append((normalized_tag, "</i>"))
            return
        if normalized_tag == "u":
            self._append("<u>")
            self._open_tags.append((normalized_tag, "</u>"))
            return
        if normalized_tag == "th":
            if not self._current:
                self._begin_block("text")
            self._append("<b>")
            self._open_tags.append((normalized_tag, "</b>"))
            return
        if normalized_tag in {"td", "span", "font"}:
            if not self._current and normalized_tag == "td":
                self._begin_block("text")
            open_markup, close_markup = _reportlab_markup_from_attrs(normalized_tag, attrs_dict)
            self._append(open_markup)
            if close_markup:
                self._open_tags.append((normalized_tag, close_markup))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"style", "script"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if normalized_tag in {"strong", "b", "em", "i", "u", "span", "font", "th"}:
            self._close_tag(normalized_tag)
            return
        if normalized_tag == "td":
            self._append("  ")
            return
        if normalized_tag == "li":
            if self._list_item_depth > 0:
                self._list_item_depth -= 1
            self._flush_block()
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"}:
            if self._list_item_depth > 0:
                return
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = str(data or "")
        if not text.strip():
            if self._current and ("\n" in text or "\r" in text):
                self._append(" ")
            return
        if not self._current:
            self._begin_block("text")
        self._append(escape(text))

    def close(self) -> None:
        super().close()
        self._flush_block()


def _terms_flowables_for_pdf(
    content: str,
    *,
    values: dict[str, str],
    html_keys: set[str],
    styles: dict[str, ParagraphStyle],
) -> list[Paragraph]:
    rendered_terms = _render_terms_content_html(content=content, values=values, html_keys=html_keys)
    if not rendered_terms:
        return [Paragraph("Aucune condition générale.", styles["text"])]
    parser = _ReportLabTermsParser()
    parser.feed(rendered_terms)
    parser.close()
    blocks = parser.blocks or [("text", "Aucune condition générale.")]
    return [Paragraph(markup, styles.get(style_name, styles["text"])) for style_name, markup in blocks]


def _draw_quote_pdf_header_footer(
    canvas_obj: Any,
    doc: SimpleDocTemplate,
    *,
    quote_number: str,
    logo_reader: ImageReader | None,
) -> None:
    canvas_obj.saveState()
    page_width, page_height = A4
    left_x = doc.leftMargin
    right_x = page_width - doc.rightMargin

    # Header band: center visual elements vertically between top band and separator line.
    header_band_top = page_height - 10 * mm
    header_rule_y = page_height - 24 * mm
    header_band_center_y = (header_band_top + header_rule_y) / 2

    logo_width = 28 * mm
    logo_height = 10 * mm
    logo_y = header_band_center_y - (logo_height / 2)
    if logo_reader is not None:
        try:
            canvas_obj.drawImage(
                logo_reader,
                left_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            logo_reader = None

    title_baseline_y = header_band_center_y - (3.2 * mm)
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.setFillColor(colors.HexColor("#0f172a"))
    if logo_reader is None:
        canvas_obj.drawString(left_x, title_baseline_y, "PIANO ACADEMIE")
    canvas_obj.drawRightString(right_x, title_baseline_y, f"Devis {quote_number or '-'}")
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, header_rule_y, right_x, header_rule_y)

    footer_y = 15 * mm
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, footer_y + 11 * mm, right_x, footer_y + 11 * mm)
    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.setFillColor(colors.HexColor("#334155"))
    canvas_obj.drawString(left_x, footer_y + 6 * mm, "Piano Academie")
    canvas_obj.drawString(left_x, footer_y + 2 * mm, "1 rue de Richelieu")
    canvas_obj.drawString(left_x, footer_y - 2 * mm, "75001 Paris")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 6 * mm, "SIRET 82805141700032")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 2 * mm, "FR 74828051417")
    canvas_obj.drawRightString(right_x, footer_y + 6 * mm, quote_number or "-")
    canvas_obj.restoreState()


def _render_quote_pdf_blocks(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> bytes:
    values, html_keys, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    prospect_data = context.get("prospect_data", {})
    calendar_snapshot = _json_object(quote.calendar_snapshot)
    sessions = [item for item in _json_list(calendar_snapshot.get("sessions")) if isinstance(item, dict)]
    planning_blocks = [item for item in _json_list(calendar_snapshot.get("blocks")) if isinstance(item, dict)]
    services, products, kits, adjustments, other_fees = _line_groups(lines)
    product_long_descriptions = _product_long_descriptions_by_id(db=db, products=products)
    kit_long_descriptions = _kit_long_descriptions_by_id(db=db, kits=kits)
    kit_composition = _kit_composition_by_id(db=db, kits=kits)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    schedule = [item for item in _json_list(context.get("schedule")) if isinstance(item, dict)]
    styles = _quote_pdf_styles()
    terms_flowables = _terms_flowables_for_pdf(cgv_content, values=values, html_keys=html_keys, styles=styles)
    logo_reader = _safe_logo_reader(_account_logo_data_url(db=db))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=24 * mm,
        title=f"Devis {quote.quote_number or '-'}",
        author="Piano Academie",
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin
    story: list[Any] = []

    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph("Votre devis d’inscription", styles["cover_title"]))
    story.append(Paragraph(f"Devis : {escape(values.get('quote_number', '-'))}", styles["cover_subtitle"]))
    story.append(Paragraph(f"Année scolaire : {escape(values.get('school_year_label', '-'))}", styles["cover_subtitle"]))
    story.append(
        Paragraph(
            f"{escape(values.get('quote_status_date_label', 'Validité'))} : {escape(values.get('quote_status_date_value', values.get('expires_at', '-')))}",
            styles["cover_subtitle"],
        )
    )
    story.append(
        Paragraph(
            f"Élève : {escape(prospect_data.get('child_full_name') or values.get('recipient_name', '-'))}",
            styles["cover_subtitle"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Informations de l’élève et du responsable", styles["h1"]))
    identity_rows: list[list[str]] = []
    if str(prospect_data.get("prospect_type") or "").lower() == "child":
        identity_rows.extend(
            [
                ["Élève", str(prospect_data.get("child_full_name") or "-")],
                ["Date de naissance", _birth_date_label(str(prospect_data.get("child_birth_date") or ""))],
                ["Adulte responsable", str(prospect_data.get("parent_full_name") or "-")],
                ["Email adulte responsable", str(prospect_data.get("parent_email") or values.get("recipient_email") or "-")],
                ["Téléphone adulte responsable", str(prospect_data.get("parent_phone") or "-")],
                ["Adresse adulte responsable", str(prospect_data.get("parent_address") or "-")],
            ]
        )
    else:
        identity_rows.extend(
            [
                ["Adulte responsable", str(prospect_data.get("adult_full_name") or values.get("recipient_name") or "-")],
                ["Email", str(prospect_data.get("adult_email") or values.get("recipient_email") or "-")],
                ["Téléphone", str(prospect_data.get("adult_phone") or "-")],
                ["Adresse", str(prospect_data.get("adult_address") or "-")],
            ]
        )
    story.append(
        _table_for_pdf(
            ["", ""],
            identity_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.32, 0.68],
        )
    )
    story.append(Spacer(1, 5))
    story.append(PageBreak())

    story.append(Paragraph("Cours et options choisis", styles["h1"]))
    planning_rows: list[list[str]] = []
    for block in planning_blocks:
        activity = _harmonize_display_text(str(block.get("activity_label") or "-"))
        location = str(block.get("location_label") or "-")
        day = str(block.get("weekday_label") or _weekday_label(block.get("weekday")) or "-")
        start = str(block.get("start_time") or "").strip()
        end = str(block.get("end_time") or "").strip()
        time_range = f"{start} - {end}" if start and end else "-"
        duration = _duration_label(
            start_time=block.get("start_time"),
            end_time=block.get("end_time"),
            fallback_minutes=block.get("duration_minutes"),
        )
        try:
            weekday_value = int(block.get("weekday") or -99)
        except (TypeError, ValueError):
            weekday_value = -99
        selection_pending = bool(block.get("selection_pending")) or weekday_value == -1
        if selection_pending:
            activity, day, time_range, duration = _pending_planning_block_display(block)
        planning_rows.append([activity, location, day, time_range, duration])
    story.append(
        _table_for_pdf(
            ["Activité", "Lieu", "Jour", "Horaire", "Durée"],
            planning_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.37, 0.23, 0.12, 0.17, 0.11],
        )
    )

    story.append(Spacer(1, 6))
    story.append(Paragraph("Cours inclus dans le devis", styles["h2"]))
    service_rows = [
        [
            _harmonize_display_text(line.title or "-"),
            _decimal_str(Decimal(line.quantity or 0)),
            f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in services
    ]
    story.append(
        _table_for_pdf(
            ["Activité", "Quantité", "Durée", "TVA", "PU TTC", "Montant TTC"],
            service_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.32, 0.12, 0.11, 0.11, 0.16, 0.18],
        )
    )

    adjustment_rows = [
        [
            "Remise"
            if (line.line_type or "").strip().lower() == "discount"
            else "Supplément"
            if (line.line_type or "").strip().lower() == "surcharge"
            else (
                "Remise"
                if (line.master_item_type or "").strip().lower() == "discount_rule"
                else "Supplément"
            ),
            _harmonize_display_text(line.title or "-"),
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in adjustments
    ]
    if adjustment_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Remises appliquées", styles["h2"]))
        story.append(
            _table_for_pdf(
                ["Type", "Intitulé", "Quantité", "TVA", "PU TTC", "Montant TTC"],
                adjustment_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.12, 0.28, 0.11, 0.11, 0.17, 0.21],
            )
        )

    product_rows = [
        [
            {
                "text": _harmonize_display_text(line.title or "-"),
                "subtext": "\n".join(
                    _unique_text_parts(
                        line.description,
                        (
                            str(product_long_descriptions.get(line.product_id) or "").strip()
                            if line.product_id is not None
                            else ""
                        ),
                    )
                ),
            },
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in products
    ]
    if product_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Matériel pédagogique", styles["h2"]))
        story.append(
            _table_for_pdf(
                ["Matériel", "Quantité", "TVA", "PU TTC", "Montant TTC"],
                product_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    kit_rows = [
        [
            {
                "text": _harmonize_display_text(line.title or "-"),
                "subtext": "\n".join(
                    _unique_text_parts(
                        line.description,
                        (
                            str(kit_long_descriptions.get(line.kit_id) or "").strip()
                            if line.kit_id is not None
                            else ""
                        ),
                        (
                            "Comprend :\n" + "\n".join(kit_composition.get(line.kit_id, []))
                            if line.kit_id is not None and kit_composition.get(line.kit_id)
                            else ""
                        ),
                    )
                ),
            },
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in kits
    ]
    if kit_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Frais et services inclus dans l’inscription", styles["h2"]))
        story.append(
            _table_for_pdf(
                ["Kit", "Quantité", "TVA", "PU TTC", "Montant TTC"],
                kit_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    other_fee_rows = [
        [
            _harmonize_display_text(line.title or "-"),
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))}%",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in other_fees
    ]
    if other_fee_rows:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Autres frais", styles["h2"]))
        story.append(
            _table_for_pdf(
                ["Intitulé", "Quantité", "TVA", "PU TTC", "Montant TTC"],
                other_fee_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.35, 0.12, 0.11, 0.18, 0.24],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph("Montant total du devis", styles["h2"]))
    financial_rows: list[list[str]] = []
    if values.get("has_financial_adjustment") == "true":
        financial_rows.append(["Total TTC avant ajustement", f"{values.get('total_ttc_before_adjustment', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([values.get("financial_adjustment_type_label", "Ajustement"), f"{values.get('financial_adjustment_amount_ttc', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Impact", values.get("financial_adjustment_impact_label", "-")])
        effective_date = values.get("financial_adjustment_effective_date", "")
        if effective_date and effective_date != "-":
            financial_rows.append(["Date ajustement", effective_date])
        financial_rows.append(["Total HT facture", f"{values.get('total_ht_after_adjustment', values.get('total_ht', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append([f"TVA facture ({values.get('vat_rate', '0,00')} %)", f"{values.get('vat_amount_after_adjustment', values.get('vat_amount', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Total TTC du devis", f"{values.get('total_ttc_after_adjustment', values.get('total_ttc', '0,00'))} {values.get('currency', 'EUR')}"])
    else:
        financial_rows.append(["Total HT", f"{values.get('total_ht', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([f"TVA ({values.get('vat_rate', '0,00')} %)", f"{values.get('vat_amount', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Total TTC du devis", f"{values.get('total_ttc', '0,00')} {values.get('currency', 'EUR')}"])
    story.append(
        _table_for_pdf(
            ["", ""],
            financial_rows,
            width=content_width,
            styles=styles,
            col_widths=[0.58, 0.42],
        )
    )

    story.append(Spacer(1, 8))
    story.append(Paragraph("Règlement et échéancier", styles["h1"]))
    special_bank_transfer_deposit_lines = _bank_transfer_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=bool(context.get("deposit_enabled")),
        deposit_amount_ttc=_decimal_from_any(context.get("deposit_amount_ttc"), Decimal("0.00")),
        currency=str(values.get("currency") or "EUR"),
        payment_method_label=str(values.get("payment_method_label") or "-"),
        remaining_ttc_after_deposit=_decimal_from_any(context.get("remaining_ttc_after_deposit"), Decimal("0.00")),
    )
    special_card_deposit_lines = _card_deposit_schedule_lines(
        schedule=schedule,
        has_deposit=bool(context.get("deposit_enabled")),
        deposit_amount_ttc=_decimal_from_any(context.get("deposit_amount_ttc"), Decimal("0.00")),
        currency=str(values.get("currency") or "EUR"),
        payment_method_label=str(values.get("payment_method_label") or "-"),
        remaining_ttc_after_deposit=_decimal_from_any(context.get("remaining_ttc_after_deposit"), Decimal("0.00")),
    )
    special_deposit_lines = special_bank_transfer_deposit_lines or special_card_deposit_lines
    payment_method_display_label = (
        str(values.get("payment_method_label", "-")).lower()
        if special_bank_transfer_deposit_lines
        else str(values.get("payment_method_label", "-"))
    )
    story.append(Paragraph(f"Mode de paiement : {escape(payment_method_display_label)}", styles["text"]))
    if special_deposit_lines:
        for line in special_deposit_lines:
            story.append(Paragraph(escape(line), styles["text"]))
    else:
        story.append(Paragraph(escape(values.get("payment_schedule_summary", "Paiement non planifié")), styles["text"]))
    if not special_deposit_lines and len(schedule) > 1:
        schedule_rows = [
            [
                str(item.get("label") or "-"),
                f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
                _schedule_due_label(item),
                str(item.get("payment_method") or "-"),
            ]
            for item in schedule
        ]
        story.append(
            _table_for_pdf(
                ["Échéance", "Montant", "Quand", "Type"],
                schedule_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.29, 0.18, 0.31, 0.22],
            )
        )
    option_blocks = [
        _apply_template("{solfege_block_html}", values=values, html_keys={"solfege_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template("{masterclass_block_html}", values=values, html_keys={"masterclass_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template("{pass_recup_block_html}", values=values, html_keys={"pass_recup_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
        _apply_template("{pass_recup_compact_notice_html}", values=values, html_keys={"pass_recup_compact_notice_html"}, html_output=True).replace("<p>", "").replace("</p>", ""),
    ]
    option_blocks = [block.strip() for block in option_blocks if str(block or "").strip()]
    if option_blocks:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Vos options", styles["h2"]))
        for block_html in option_blocks:
            story.append(Paragraph(block_html, styles["text"]))

    story.append(PageBreak())
    story.append(Paragraph("Calendrier prévisionnel des cours", styles["h1"]))
    story.append(Paragraph(f"Vue d’ensemble du calendrier : {escape(values.get('calendar_summary', '-'))}", styles["text"]))
    grouped: dict[str, dict[tuple[int, int], set[int]]] = {}
    for session in sessions:
        parsed = _session_date_parts(session.get("date"))
        if parsed is None:
            continue
        year, month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or "Cours"
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        grouped.setdefault(title, {}).setdefault((year, month), set()).add(day)
    for idx, title in enumerate(sorted(grouped.keys()), start=1):
        heading = _calendar_group_heading(title, idx)
        month_map = grouped[title]
        count = sum(len(days) for days in month_map.values())
        story.append(Spacer(1, 5))
        story.append(Paragraph(heading, styles["h3"]))
        story.append(
            _table_for_pdf(
                ["Cours / lieu", "Nombre de cours"],
                [[heading, f"{count} cours"]],
                width=content_width,
                styles=styles,
                col_widths=[0.70, 0.30],
            )
        )
        sem_rows: list[list[str]] = []
        for month_label, days in _calendar_semester_rows(month_map, semester=1):
            sem_rows.append(["1er semestre", month_label, days])
        for month_label, days in _calendar_semester_rows(month_map, semester=2):
            sem_rows.append(["2e semestre", month_label, days])
        if not sem_rows:
            sem_rows.append(["-", "-", "Aucune séance"])
        story.append(
            _table_for_pdf(
                ["Semestre", "Mois", "Dates de cours"],
                sem_rows,
                width=content_width,
                styles=styles,
                col_widths=[0.20, 0.20, 0.60],
            )
        )

    story.append(PageBreak())
    story.append(Paragraph("Conditions d’inscription 2026–2027", styles["h1"]))
    story.append(Paragraph(escape(cgv_label or "Version non précisée"), styles["h3"]))
    story.extend(terms_flowables)

    def _on_page(canvas_obj: Any, document: SimpleDocTemplate) -> None:
        _draw_quote_pdf_header_footer(
            canvas_obj,
            document,
            quote_number=quote.quote_number or "-",
            logo_reader=logo_reader,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def render_quote_pdf_from_combined_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    combined_html: str,
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    if audience == AUDIENCE_ADMIN_PREVIEW:
        html_pdf = _render_html_pdf_with_xhtml2pdf(combined_html)
        if html_pdf:
            return html_pdf
    return _render_quote_pdf_blocks(db=db, quote=quote, lines=lines, audience=audience)
