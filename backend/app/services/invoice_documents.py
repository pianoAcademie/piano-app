from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting

INVOICE_TEMPLATE_SETTING_KEY = "config_invoice_template_text_v1"
INVOICE_TEMPLATE_VARIABLES_HINT = (
    "{invoice_number} {issued_at} {client_name} {client_id} {payment_type} {label} {payment_status} "
    "{amount_excl_vat} {vat_amount} {total_incl_vat} {currency} {reference} {refund_info} "
    "{company_name} {company_email} {company_address}"
)

DEFAULT_INVOICE_TEMPLATE = (
    "Piano Academie - Facture\n"
    "Numero: {invoice_number}\n"
    "Date: {issued_at}\n"
    "Client: {client_name} ({client_id})\n"
    "Type: {payment_type}\n"
    "Libelle: {label}\n"
    "Statut: {payment_status}\n"
    "Montant HT: {amount_excl_vat} {currency}\n"
    "TVA: {vat_amount} {currency}\n"
    "Total TTC: {total_incl_vat} {currency}\n"
    "Reference: {reference}\n"
    "{refund_info}\n"
    "\n"
    "{company_name}\n"
    "Contact: {company_email}\n"
    "{company_address}\n"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _setting_value(db: Session, key: str, default: str) -> str:
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        return default
    value = row.value.strip()
    return value or default


def get_invoice_template(db: Session) -> tuple[str, datetime | None]:
    row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_TEMPLATE_SETTING_KEY))
    if row is None:
        return DEFAULT_INVOICE_TEMPLATE, None
    value = row.value.strip() or DEFAULT_INVOICE_TEMPLATE
    return value, row.updated_at


def save_invoice_template(db: Session, *, body: str) -> datetime:
    normalized = body.strip()
    if not normalized:
        normalized = DEFAULT_INVOICE_TEMPLATE
    row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_TEMPLATE_SETTING_KEY).with_for_update())
    now = _utcnow()
    if row is None:
        db.add(AppSetting(key=INVOICE_TEMPLATE_SETTING_KEY, value=normalized, updated_at=now))
        return now
    row.value = normalized
    row.updated_at = now
    return now


def render_invoice_text(
    db: Session,
    *,
    invoice_number: str,
    issued_at: datetime,
    client_id: str,
    client_name: str,
    payment_type: str,
    label: str,
    payment_status: str,
    amount_excl_vat: Decimal,
    vat_amount: Decimal,
    total_incl_vat: Decimal,
    currency: str,
    reference: str | None,
    refunded_at: datetime | None,
    refund_reason: str | None,
) -> str:
    template, _ = get_invoice_template(db)
    company_name = _setting_value(db, "config_account_club_name", "Piano Academie")
    company_email = _setting_value(db, "config_account_contact_email", "")
    address_parts = [
        _setting_value(db, "config_account_address_line", ""),
        _setting_value(db, "config_account_postal_code", ""),
        _setting_value(db, "config_account_city", ""),
        _setting_value(db, "config_account_country", ""),
    ]
    company_address = " ".join(part for part in address_parts if part).strip() or "-"

    refund_info = ""
    if refunded_at is not None:
        reason = refund_reason or "-"
        refund_info = f"Rembourse le: {refunded_at.strftime('%d/%m/%Y %H:%M')} | Motif: {reason}"

    values = {
        "invoice_number": invoice_number,
        "issued_at": issued_at.strftime("%d/%m/%Y %H:%M"),
        "client_name": client_name,
        "client_id": client_id,
        "payment_type": payment_type,
        "label": label,
        "payment_status": payment_status,
        "amount_excl_vat": f"{Decimal(amount_excl_vat).quantize(Decimal('0.01'))}",
        "vat_amount": f"{Decimal(vat_amount).quantize(Decimal('0.01'))}",
        "total_incl_vat": f"{Decimal(total_incl_vat).quantize(Decimal('0.01'))}",
        "currency": (currency or "EUR").upper(),
        "reference": reference or "-",
        "refund_info": refund_info,
        "company_name": company_name,
        "company_email": company_email or "-",
        "company_address": company_address,
    }

    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered.rstrip() + "\n"
