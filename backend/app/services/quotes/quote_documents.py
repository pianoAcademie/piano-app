from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.models.quote import Quote, QuoteLine
from app.services.teacher_invoice_documents import render_teacher_invoice_pdf_from_html


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _money(value: Decimal, currency: str) -> str:
    amount = Decimal(value or Decimal("0")).quantize(Decimal("0.01"))
    return f"{amount} {currency}"


def _render_quote_body_html(*, quote: Quote, lines: list[QuoteLine]) -> str:
    currency = (quote.currency or "EUR").upper()
    line_rows = "".join(
        (
            f"<tr>"
            f"<td>{(line.title or '-')}</td>"
            f"<td>{Decimal(line.quantity or 0).quantize(Decimal('0.01'))}</td>"
            f"<td>{_money(Decimal(line.unit_price_ttc or 0), currency)}</td>"
            f"<td>{_money(Decimal(line.amount_ttc or 0), currency)}</td>"
            f"</tr>"
        )
        for line in lines
    )
    if not line_rows:
        line_rows = "<tr><td colspan='4'>Aucune ligne</td></tr>"

    calendar_snapshot = quote.calendar_snapshot or {}
    payment_terms = quote.payment_terms_snapshot or {}
    expires_at = quote.expires_at.strftime("%d/%m/%Y") if quote.expires_at else "-"
    sent_at = quote.sent_at.strftime("%d/%m/%Y %H:%M") if quote.sent_at else "-"
    generated_at = _utcnow().strftime("%d/%m/%Y %H:%M")
    calendar_items = calendar_snapshot.get("sessions", [])
    calendar_html = "".join(
        (
            "<li>"
            f"{session.get('date', '-')} "
            f"{session.get('start_time', '-')}-{session.get('end_time', '-')}"
            "</li>"
        )
        for session in calendar_items[:40]
    )
    if not calendar_html:
        calendar_html = "<li>Aucune seance planifiee</li>"

    payment_schedule_html = "".join(
        (
            "<li>"
            f"{item.get('label', '-')} : {item.get('amount_ttc', '0')} {item.get('currency', currency)}"
            f"{' (' + str(item.get('due_label')) + ')' if item.get('due_label') else ''}"
            "</li>"
        )
        for item in payment_terms.get("schedule", [])
    )
    if not payment_schedule_html:
        payment_schedule_html = "<li>Paiement a definir</li>"

    return (
        f"<h1>Devis {quote.quote_number}</h1>"
        f"<p><strong>Statut :</strong> {quote.status}</p>"
        f"<p><strong>Date envoi :</strong> {sent_at}</p>"
        f"<p><strong>Date expiration :</strong> {expires_at}</p>"
        f"<p><strong>Genere le :</strong> {generated_at}</p>"
        "<h2>Lignes</h2>"
        "<table border='1' cellspacing='0' cellpadding='6' width='100%'>"
        "<thead><tr><th>Intitule</th><th>Quantite</th><th>Prix unitaire TTC</th><th>Montant TTC</th></tr></thead>"
        f"<tbody>{line_rows}</tbody>"
        "</table>"
        f"<p><strong>Total TTC :</strong> {_money(Decimal(quote.total_ttc or 0), currency)}</p>"
        "<h2>Calendrier</h2>"
        f"<ul>{calendar_html}</ul>"
        "<h2>Echeancier</h2>"
        f"<ul>{payment_schedule_html}</ul>"
    )


def _render_quote_terms_html(*, quote: Quote) -> str:
    cgv_snapshot = quote.cgv_snapshot or {}
    cgv_label = cgv_snapshot.get("version_label") or "Version non precisee"
    cgv_content = str(cgv_snapshot.get("content") or "").strip()
    return (
        "<section>"
        "<h2>Conditions generales</h2>"
        f"<p><strong>{cgv_label}</strong></p>"
        f"<p>{cgv_content or 'Aucune CGV snapshottee.'}</p>"
        "</section>"
    )


def render_quote_combined_html(*, quote: Quote, lines: list[QuoteLine]) -> str:
    body_html = _render_quote_body_html(quote=quote, lines=lines)
    terms_html = _render_quote_terms_html(quote=quote)
    return (
        "<html><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"<section>{body_html}</section>"
        "<div style='page-break-before:always;'></div>"
        f"{terms_html}"
        "</body></html>"
    )


def render_quote_html(*, quote: Quote, lines: list[QuoteLine]) -> str:
    return render_quote_combined_html(quote=quote, lines=lines)


def render_quote_parts_html(*, quote: Quote, lines: list[QuoteLine]) -> tuple[str, str, str]:
    body_html = _render_quote_body_html(quote=quote, lines=lines)
    terms_html = _render_quote_terms_html(quote=quote)
    combined_html = (
        "<html><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"<section>{body_html}</section>"
        "<div style='page-break-before:always;'></div>"
        f"{terms_html}"
        "</body></html>"
    )
    return body_html, terms_html, combined_html


def render_quote_pdf(*, quote: Quote, lines: list[QuoteLine]) -> bytes:
    html = render_quote_combined_html(quote=quote, lines=lines)
    return render_teacher_invoice_pdf_from_html(html)
