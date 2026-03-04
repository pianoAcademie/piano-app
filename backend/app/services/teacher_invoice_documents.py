from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import html
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.teacher_invoicing import DocumentTemplate
from app.services.invoice_documents import _SimplePdfDocument, _wrap_text

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

DEFAULT_TEACHER_INVOICE_TEMPLATE = """\
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
"""

MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context))
    except Exception:
        return normalized


def get_teacher_invoice_template(db: Session) -> tuple[str, int, Any]:
    row = db.scalar(select(DocumentTemplate).where(DocumentTemplate.key == TEACHER_INVOICE_TEMPLATE_KEY))
    if row is None:
        return DEFAULT_TEACHER_INVOICE_TEMPLATE, 1, None
    body = (row.html_template or "").strip() or DEFAULT_TEACHER_INVOICE_TEMPLATE
    return body, int(row.version or 1), row.updated_at


def save_teacher_invoice_template(db: Session, *, html_template: str) -> tuple[str, int, Any]:
    normalized = (html_template or "").strip() or DEFAULT_TEACHER_INVOICE_TEMPLATE
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


def default_teacher_invoice_context() -> dict[str, str]:
    return {
        "teacher_full_name": "Demo Professeur",
        "teacher_company_name": "Demo Professeur EI",
        "teacher_company_address": "1 rue de la Musique, 75001 Paris",
        "teacher_email": "prof@example.com",
        "teacher_phone": "+33100000000",
        "teacher_siret_display": "en cours d'immatriculation",
        "teacher_iban": "FR76 XXXX XXXX XXXX XXXX XXXX XXX",
        "payor_company_name": "PIANO ACADEMIE SERVICES",
        "payor_company_address": "40 rue de Richelieu, 75001 Paris",
        "payor_company_siret": "82816386500011",
        "payor_company_vat": "FR52828163865",
        "invoice_number_display": "PROF-DEMO-42",
        "invoice_date": "2026-03-03",
        "due_date": "2026-04-02",
        "invoice_period_label": "Mars 2026",
        "lines_by_course_type": "Cours collectif: 4.00h x 35.00 HT = 140.00 HT",
        "totals_ht": f"{Decimal('140.00')}",
        "totals_vat": f"{Decimal('28.00')}",
        "totals_ttc": f"{Decimal('168.00')}",
        "payment_instructions": "Paiement par virement sous 30 jours.",
        "late_payment_penalty_text": "Penalites de retard conformement aux CGV.",
        "comptability_email": "comptabilite@piano-academie.com",
    }


def render_teacher_invoice_html(*, html_template: str, context: dict[str, str]) -> str:
    return _render_template(html_template, context)


def render_teacher_invoice_pdf_from_html(rendered_html: str) -> bytes:
    normalized = rendered_html.replace("<br/>", "\n").replace("<br>", "\n").replace("<br />", "\n")
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
