from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.quote import Prospect, Quote, QuoteLine, QuoteTemplateVersion, TermsTemplateVersion
from app.models.user import User
from app.services.teacher_invoice_documents import render_teacher_invoice_pdf_from_html


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decimal_str(value: Decimal) -> str:
    amount = Decimal(value or Decimal("0")).quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",")


def _money(value: Decimal, currency: str) -> str:
    return f"{_decimal_str(value)} {currency}"


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


def _table_html(headers: list[str], rows: list[list[str]], *, empty_label: str) -> str:
    if not rows:
        return f"<p>{escape(empty_label)}</p>"
    head = "".join(f"<th>{escape(cell)}</th>" for cell in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>")
    body = "".join(body_rows)
    return (
        "<table border='1' cellspacing='0' cellpadding='6' width='100%'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def _line_groups(lines: list[QuoteLine]) -> tuple[list[QuoteLine], list[QuoteLine], list[QuoteLine]]:
    services: list[QuoteLine] = []
    products: list[QuoteLine] = []
    kits: list[QuoteLine] = []
    for line in lines:
        if (line.line_category or "").strip().lower() == "service":
            services.append(line)
            continue
        if line.kit_id is not None or (line.master_item_type or "").strip().lower() == "kit":
            kits.append(line)
            continue
        products.append(line)
    return services, products, kits


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
        values["adult_address"] = str(meta.get("adult_address") or "").strip()

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


TOKEN_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


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


def _as_html_fragment(content: str) -> str:
    normalized = (content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    if "<" in normalized and ">" in normalized:
        return normalized
    return "<p>" + "<br/>".join(line for line in normalized.split("\n")) + "</p>"


def _build_template_values(*, db: Session | None, quote: Quote, lines: list[QuoteLine]) -> tuple[dict[str, str], set[str]]:
    currency = (quote.currency or "EUR").upper()
    services, products, kits = _line_groups(lines)
    total_ttc = Decimal(quote.total_ttc or 0)
    vat_rate = Decimal(quote.vat_rate or 0)
    if vat_rate > Decimal("0"):
        total_ht = (total_ttc / (Decimal("1") + (vat_rate / Decimal("100")))).quantize(Decimal("0.01"))
        vat_amount = (total_ttc - total_ht).quantize(Decimal("0.01"))
    else:
        total_ht = total_ttc.quantize(Decimal("0.01"))
        vat_amount = Decimal("0.00")

    services_table_html = _table_html(
        ["Activite", "Quantite", "Duree", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in services
        ],
        empty_label="Aucune activite.",
    )
    products_table_html = _table_html(
        ["Produit", "Quantite", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in products
        ],
        empty_label="Aucun produit.",
    )
    kits_table_html = _table_html(
        ["Kit", "Quantite", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in kits
        ],
        empty_label="Aucun kit.",
    )
    lines_table_html = _table_html(
        ["Categorie", "Intitule", "Quantite", "PU TTC", "Montant TTC"],
        [
            [
                "Service" if (line.line_category or "").lower() == "service" else ("Kit" if line.kit_id else "Produit"),
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in lines
        ],
        empty_label="Aucune ligne.",
    )

    schedule = (quote.payment_terms_snapshot or {}).get("schedule", [])
    payment_schedule_table_html = _table_html(
        ["Echeance", "Montant", "Quand", "Type"],
        [
            [
                str(item.get("label") or "-"),
                f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
                str(item.get("due_label") or item.get("due_type") or "-"),
                str(item.get("payment_method") or "-"),
            ]
            for item in schedule
            if isinstance(item, dict)
        ],
        empty_label="Aucun echeancier.",
    )

    sessions = (quote.calendar_snapshot or {}).get("sessions", [])
    calendar_table_html = _table_html(
        ["Date", "Debut", "Fin", "Duree", "Modalite"],
        [
            [
                str(item.get("date") or "-"),
                str(item.get("start_time") or item.get("start_at") or "-"),
                str(item.get("end_time") or item.get("end_at") or "-"),
                f"{item.get('duration_minutes')} min" if item.get("duration_minutes") is not None else "-",
                str(item.get("modality") or "-"),
            ]
            for item in sessions
            if isinstance(item, dict)
        ],
        empty_label="Aucun cours planifie.",
    )
    calendar_summary = (
        f"{len(sessions)} seances planifiees" if isinstance(sessions, list) and sessions else "Aucune seance planifiee"
    )
    payment_schedule_summary = (
        f"{len(schedule)} echeances" if isinstance(schedule, list) and schedule else "Paiement non planifie"
    )

    cgv_label, _ = _load_terms_template_content(db=db, quote=quote)
    prospect_data = _resolve_prospect_data(db=db, quote=quote)
    client_data = _resolve_client_data(db=db, quote=quote)
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

    values: dict[str, str] = {
        "quote_number": quote.quote_number or "-",
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "total_ttc": _decimal_str(total_ttc),
        "total_ht": _decimal_str(total_ht),
        "vat_rate": _decimal_str(vat_rate),
        "vat_amount": _decimal_str(vat_amount),
        "currency": currency,
        "expires_at": _date_label(quote.expires_at),
        "sent_at": _datetime_label(quote.sent_at),
        "generated_at": _datetime_label(_utcnow()),
        "school_year_label": (quote.school_year_label or "-"),
        "calendar_summary": calendar_summary,
        "payment_schedule_summary": payment_schedule_summary,
        "cgv_version": cgv_label or "-",
        "services_count": str(len(services)),
        "products_count": str(len(products)),
        "kits_count": str(len(kits)),
        "lines_count": str(len(lines)),
        "services_table_html": services_table_html,
        "products_table_html": products_table_html,
        "kits_table_html": kits_table_html,
        "lines_table_html": lines_table_html,
        "payment_schedule_table_html": payment_schedule_table_html,
        "calendar_table_html": calendar_table_html,
    }
    values.update(prospect_data)
    values.update(client_data)

    html_keys = {
        "services_table_html",
        "products_table_html",
        "kits_table_html",
        "lines_table_html",
        "payment_schedule_table_html",
        "calendar_table_html",
    }
    return values, html_keys


def _default_quote_body_template() -> str:
    return (
        "<h1>Devis {quote_number}</h1>"
        "<p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p>"
        "<p><strong>Annee scolaire:</strong> {school_year_label}</p>"
        "<p><strong>Expiration:</strong> {expires_at}</p>"
        "<h2>Activites</h2>{services_table_html}"
        "<h2>Produits</h2>{products_table_html}"
        "<h2>Kits</h2>{kits_table_html}"
        "<h2>Echeancier de paiement</h2>{payment_schedule_table_html}"
        "<h2>Calendrier des cours</h2>{calendar_table_html}"
        "<p><strong>Total HT:</strong> {total_ht} {currency}</p>"
        "<p><strong>TVA ({vat_rate}%):</strong> {vat_amount} {currency}</p>"
        "<p><strong>Total TTC:</strong> {total_ttc} {currency}</p>"
    )


def _render_quote_body_html(*, db: Session | None, quote: Quote, lines: list[QuoteLine]) -> str:
    _, body_template = _load_quote_template_snapshot(db=db, quote=quote)
    template = body_template or _default_quote_body_template()
    values, html_keys = _build_template_values(db=db, quote=quote, lines=lines)
    rendered = _apply_template(template, values=values, html_keys=html_keys, html_output=True)
    return _as_html_fragment(rendered)


def _render_quote_terms_html(*, db: Session | None, quote: Quote, lines: list[QuoteLine]) -> str:
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    values, html_keys = _build_template_values(db=db, quote=quote, lines=lines)
    rendered_terms = _apply_template(cgv_content, values=values, html_keys=html_keys, html_output=True)
    return (
        "<section>"
        "<h2>Conditions generales</h2>"
        f"<p><strong>{escape(cgv_label or 'Version non precisee')}</strong></p>"
        f"{_as_html_fragment(rendered_terms or 'Aucune CGV snapshottee.')}"
        "</section>"
    )


def render_quote_combined_html(*, db: Session | None = None, quote: Quote, lines: list[QuoteLine]) -> str:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines)
    return (
        "<html><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"<section>{body_html}</section>"
        "<div style='page-break-before:always;'></div>"
        f"{terms_html}"
        "</body></html>"
    )


def render_quote_html(*, db: Session | None = None, quote: Quote, lines: list[QuoteLine]) -> str:
    return render_quote_combined_html(db=db, quote=quote, lines=lines)


def render_quote_parts_html(*, db: Session | None = None, quote: Quote, lines: list[QuoteLine]) -> tuple[str, str, str]:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines)
    combined_html = (
        "<html><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"<section>{body_html}</section>"
        "<div style='page-break-before:always;'></div>"
        f"{terms_html}"
        "</body></html>"
    )
    return body_html, terms_html, combined_html


def render_quote_pdf(*, db: Session | None = None, quote: Quote, lines: list[QuoteLine]) -> bytes:
    html = render_quote_combined_html(db=db, quote=quote, lines=lines)
    return render_teacher_invoice_pdf_from_html(html)
