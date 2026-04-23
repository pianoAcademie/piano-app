from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import html
import io
import logging
import re
from decimal import InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from xhtml2pdf import pisa

from app.models.teacher_invoicing import DocumentTemplate
from app.services.i18n import normalize_language
from app.services.invoice_documents import _SimplePdfDocument, _wrap_text

logger = logging.getLogger(__name__)

TEACHER_INVOICE_TEMPLATE_KEY = "teacher_invoice"
TEACHER_INVOICE_TEMPLATE_VARIABLES: tuple[str, ...] = (
    "teacher_full_name",
    "teacher_company_name",
    "teacher_company_address",
    "teacher_email",
    "teacher_phone",
    "teacher_siret_display",
    "teacher_iban",
    "payor_company_name",
    "payor_company_address",
    "payor_company_siret",
    "payor_company_vat",
    "invoice_number_display",
    "invoice_date",
    "due_date",
    "invoice_period_label",
    "lines_by_course_type",
    "totals_ht",
    "totals_vat",
    "totals_ttc",
    "payment_instructions",
    "late_payment_penalty_text",
    "comptability_email",
)

DEFAULT_TEACHER_INVOICE_TEMPLATES = {
    "fr": """\
<h1>Facture professeur</h1>
<p><strong>Numero:</strong> {{invoice_number_display}}</p>
<p><strong>Date:</strong> {{invoice_date}} | <strong>Echeance:</strong> {{due_date}}</p>
<p><strong>Periode:</strong> {{invoice_period_label}}</p>
<hr />
<h2>Emetteur (professeur)</h2>
<p>{{teacher_full_name}}<br/>{{teacher_company_name}}<br/>{{teacher_company_address}}<br/>SIRET: {{teacher_siret_display}}<br/>IBAN: {{teacher_iban}}</p>
<h2>Payeur</h2>
<p>{{payor_company_name}}<br/>{{payor_company_address}}<br/>SIRET: {{payor_company_siret}}<br/>TVA: {{payor_company_vat}}</p>
<h2>Lignes</h2>
<p>{{lines_by_course_type}}</p>
<h2>Totaux</h2>
<p>HT: {{totals_ht}} | TVA: {{totals_vat}} | TTC: {{totals_ttc}}</p>
<p>{{payment_instructions}}</p>
<p>{{late_payment_penalty_text}}</p>
<p>Compta: {{comptability_email}}</p>
""",
    "en": """\
<h1>Teacher invoice</h1>
<p><strong>Number:</strong> {{invoice_number_display}}</p>
<p><strong>Date:</strong> {{invoice_date}} | <strong>Due date:</strong> {{due_date}}</p>
<p><strong>Period:</strong> {{invoice_period_label}}</p>
<hr />
<h2>Issuer (teacher)</h2>
<p>{{teacher_full_name}}<br/>{{teacher_company_name}}<br/>{{teacher_company_address}}<br/>SIRET: {{teacher_siret_display}}<br/>IBAN: {{teacher_iban}}</p>
<h2>Payor</h2>
<p>{{payor_company_name}}<br/>{{payor_company_address}}<br/>SIRET: {{payor_company_siret}}<br/>VAT: {{payor_company_vat}}</p>
<h2>Lines</h2>
<p>{{lines_by_course_type}}</p>
<h2>Totals</h2>
<p>Net: {{totals_ht}} | VAT: {{totals_vat}} | Gross: {{totals_ttc}}</p>
<p>{{payment_instructions}}</p>
<p>{{late_payment_penalty_text}}</p>
<p>Accounting: {{comptability_email}}</p>
""",
}

MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\s*\}\}")
MUSTACHE_EACH_BLOCK_RE = re.compile(
    r"\{\{\s*#each\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}(.*?)\{\{\s*/each\s*\}\}",
    flags=re.IGNORECASE | re.DOTALL,
)
LIQUID_FOR_BLOCK_RE = re.compile(
    r"\{%\s*for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%\}(.*?)\{%\s*endfor\s*%\}",
    flags=re.IGNORECASE | re.DOTALL,
)
CSS_VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*(?:,\s*([^)]+?)\s*)?\)")
CSS_VAR_DEFAULTS: dict[str, str] = {
    "--line-soft": "#d6d9de",
    "--line": "#cfd3da",
    "--ink": "#1f2937",
    "--text": "#1f2937",
    "--text-muted": "#6b7280",
    "--muted": "#6b7280",
    "--bg": "#ffffff",
    "--panel": "#ffffff",
    "--panel-2": "#f9fafb",
    "--accent": "#c9872a",
    "--accent-ink": "#ffffff",
}


def default_teacher_invoice_template(*, language: str | None = None) -> str:
    normalized_language = normalize_language(language)
    return DEFAULT_TEACHER_INVOICE_TEMPLATES.get(normalized_language, DEFAULT_TEACHER_INVOICE_TEMPLATES["fr"])


def _format_decimal_like(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        rendered_items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("course_type_label") or "-")
                quantity = _format_decimal_like(item.get("quantity") or item.get("hours") or "0")
                unit = _format_decimal_like(item.get("unit_price_ht") or item.get("unit_rate_ht") or "0")
                total = _format_decimal_like(item.get("total_ht") or item.get("amount_ht") or "0")
                rendered_items.append(f"{label}: {quantity} x {unit} = {total} HT")
            else:
                rendered_items.append(str(item))
        return " | ".join(rendered_items)
    return str(value)


def _resolve_path(path: str, *, root_context: dict[str, Any], row_context: dict[str, Any] | None = None) -> Any:
    chunks = [chunk for chunk in (path or "").split(".") if chunk]
    if not chunks:
        return ""
    head = chunks[0]
    if row_context and head in row_context:
        value: Any = row_context[head]
    else:
        value = root_context.get(head)
    for key in chunks[1:]:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            value = getattr(value, key, None)
    return value


def _render_mustache_placeholders(template: str, *, root_context: dict[str, Any], row_context: dict[str, Any] | None = None) -> str:
    def replace(match: re.Match[str]) -> str:
        key = (match.group(1) or "").strip()
        value = _resolve_path(key, root_context=root_context, row_context=row_context)
        return _stringify(value)

    return MUSTACHE_PLACEHOLDER_RE.sub(replace, template)


def _render_each_blocks(template: str, context: dict[str, Any]) -> str:
    def replace_each(match: re.Match[str]) -> str:
        list_name = (match.group(1) or "").strip()
        block = match.group(2) or ""
        items = context.get(list_name)
        if not isinstance(items, list):
            return ""
        rendered: list[str] = []
        for item in items:
            row = item if isinstance(item, dict) else {"value": item}
            rendered.append(
                _render_mustache_placeholders(
                    block,
                    root_context=context,
                    row_context={"this": row, **row},
                )
            )
        return "".join(rendered)

    return MUSTACHE_EACH_BLOCK_RE.sub(replace_each, template)


def _render_liquid_for_blocks(template: str, context: dict[str, Any]) -> str:
    def replace_for(match: re.Match[str]) -> str:
        alias = (match.group(1) or "").strip()
        list_name = (match.group(2) or "").strip()
        block = match.group(3) or ""
        items = context.get(list_name)
        if not isinstance(items, list):
            return ""
        rendered: list[str] = []
        for item in items:
            row = item if isinstance(item, dict) else {"value": item}
            rendered.append(
                _render_mustache_placeholders(
                    block,
                    root_context=context,
                    row_context={alias: row, **row},
                )
            )
        return "".join(rendered)

    return LIQUID_FOR_BLOCK_RE.sub(replace_for, template)


def _render_template(template: str, context: dict[str, Any]) -> str:
    rendered = template
    rendered = _render_liquid_for_blocks(rendered, context)
    rendered = _render_each_blocks(rendered, context)
    rendered = _render_mustache_placeholders(rendered, root_context=context)
    return rendered


def get_teacher_invoice_template(db: Session, *, language: str | None = None) -> tuple[str, int, Any]:
    row = db.scalar(select(DocumentTemplate).where(DocumentTemplate.key == TEACHER_INVOICE_TEMPLATE_KEY))
    if row is None:
        return default_teacher_invoice_template(language=language), 1, None
    body = (row.html_template or "").strip() or default_teacher_invoice_template(language=language)
    return body, int(row.version or 1), row.updated_at


def save_teacher_invoice_template(db: Session, *, html_template: str) -> tuple[str, int, Any]:
    normalized = (html_template or "").strip() or default_teacher_invoice_template()
    row = db.scalar(
        select(DocumentTemplate).where(DocumentTemplate.key == TEACHER_INVOICE_TEMPLATE_KEY).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = DocumentTemplate(
            key=TEACHER_INVOICE_TEMPLATE_KEY,
            html_template=normalized,
            version=1,
        )
        db.add(row)
    else:
        row.html_template = normalized
        row.version = int(row.version or 1) + 1
    row.updated_at = now
    db.flush()
    return row.html_template, int(row.version or 1), row.updated_at


def default_teacher_invoice_context(*, language: str | None = None) -> dict[str, Any]:
    normalized_language = normalize_language(language)
    return {
        "teacher_full_name": "Demo Teacher" if normalized_language == "en" else "Demo Professeur",
        "teacher_company_name": "Demo Teacher Sole Trader" if normalized_language == "en" else "Demo Professeur EI",
        "teacher_company_address": "1 rue de la Musique, 75001 Paris",
        "teacher_email": "prof@example.com",
        "teacher_phone": "+33100000000",
        "teacher_siret_display": "registration pending" if normalized_language == "en" else "en cours d'immatriculation",
        "teacher_iban": "FR76 XXXX XXXX XXXX XXXX XXXX XXX",
        "payor_company_name": "PIANO ACADEMIE SERVICES",
        "payor_company_address": "40 rue de Richelieu, 75001 Paris",
        "payor_company_siret": "82816386500011",
        "payor_company_vat": "FR52828163865",
        "invoice_number_display": "PROF-DEMO-42",
        "invoice_date": "2026-03-03",
        "due_date": "2026-04-02",
        "invoice_period_label": "March 2026" if normalized_language == "en" else "Mars 2026",
        "lines_by_course_type": [
            {
                "ref": "CC",
                "label": "Group course" if normalized_language == "en" else "Cours collectif",
                "unit_price_ht": "35.00",
                "quantity": "4.00",
                "total_ht": "140.00",
            }
        ],
        "totals_ht": f"{Decimal('140.00')}",
        "totals_vat": f"{Decimal('28.00')}",
        "totals_ttc": f"{Decimal('168.00')}",
        "payment_instructions": "Payment by bank transfer within 30 days." if normalized_language == "en" else "Paiement par virement sous 30 jours.",
        "late_payment_penalty_text": "Late-payment penalties apply according to the terms and conditions." if normalized_language == "en" else "Penalites de retard conformement aux CGV.",
        "comptability_email": "comptabilite@piano-academie.com",
    }


def render_teacher_invoice_html(*, html_template: str, context: dict[str, Any]) -> str:
    return _render_template(html_template, context)


def _ensure_full_html_document(rendered_html: str) -> str:
    candidate = (rendered_html or "").strip()
    if not candidate:
        return "<html><body><p>Facture</p></body></html>"
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
    except Exception:  # pragma: no cover - defensive fallback to plain-text PDF
        logger.exception("Teacher invoice HTML PDF rendering crashed; using fallback renderer")
        return None
    if status.err:
        logger.warning("Teacher invoice HTML PDF rendering failed with xhtml2pdf; using fallback renderer")
        return None
    return output.getvalue()


def _render_plain_text_pdf_from_html(rendered_html: str) -> bytes:
    normalized = rendered_html.replace("<br/>", "\n").replace("<br>", "\n").replace("<br />", "\n")
    normalized = re.sub(r"<style[^>]*>.*?</style>", "", normalized, flags=re.IGNORECASE | re.DOTALL)
    normalized = re.sub(r"<script[^>]*>.*?</script>", "", normalized, flags=re.IGNORECASE | re.DOTALL)
    normalized = re.sub(r"</(p|div|h[1-6]|li|tr|td|th|ul|ol|table|hr)>", "\n", normalized, flags=re.IGNORECASE)
    plain = re.sub(r"<[^>]+>", "", normalized)
    plain = html.unescape(plain)
    lines = [line.strip() for line in plain.splitlines() if line.strip()]

    pdf = _SimplePdfDocument()
    left = 34.0
    current_top = 36.0
    for line in lines:
        for chunk in _wrap_text(line, max_chars=95):
            if current_top > 790.0:
                pdf.new_page()
                current_top = 36.0
            pdf.text(x=left, top_y=current_top, value=chunk, size=10)
            current_top += 14.0
        current_top += 4.0

    return pdf.build()


def render_teacher_invoice_pdf_from_html(rendered_html: str) -> bytes:
    html_pdf = _render_html_pdf_with_xhtml2pdf(rendered_html)
    if html_pdf:
        return html_pdf
    return _render_plain_text_pdf_from_html(rendered_html)
