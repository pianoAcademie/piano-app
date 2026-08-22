from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging
import re
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import CourseType
from app.services.email_delivery import send_email
from app.services.i18n import normalize_language
from app.services.messaging_templates import (
    recipient_display_name,
    render_template_content,
    resolve_frontend_base_url,
    resolve_predefined_template,
    resolve_sender_profile,
)
from app.services.notifications.application.recipients import resolve_admin_plan_purchase_recipients
from app.services.plan_invoice_access import create_plan_invoice_download_token

logger = logging.getLogger(__name__)


def _render_template(template: str, context: dict[str, str]) -> str:
    return render_template_content(template, context)


def _frontend_url(path: str) -> str:
    candidate = resolve_frontend_base_url()
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


def _is_studio_booking_purchase(plan_name: str) -> bool:
    return "studio" in plan_name.casefold()


def _studio_booking_url(db: Session) -> str:
    course_type_id = db.scalar(select(CourseType.id).where(CourseType.code == "STUDIO_REHEARSAL"))
    if course_type_id is None:
        return _frontend_url("/embed/planning")
    query = urlencode(
        {
            "course_type_id": str(course_type_id),
            "location_group": "paris",
        }
    )
    return _frontend_url(f"/embed/planning?{query}")


def plan_purchase_notification_label(*, plan_name: str, price_breakdown: object) -> str:
    """Return the activity-specific label stored for a trial purchase."""

    candidate = ""
    if isinstance(price_breakdown, list):
        for row in price_breakdown:
            if not isinstance(row, dict):
                continue
            if str(row.get("code") or "").strip().upper() != "TRIAL_COURSE":
                continue
            candidate = str(row.get("label") or "").strip()
            if candidate:
                break

    label = candidate or plan_name.strip() or "Formule Piano Académie"
    label = re.sub(r"^Cours d'essai\s*-\s*", "Cours d’essai – ", label, flags=re.IGNORECASE)
    return re.sub(r"\bEveil\b", "Éveil", label, flags=re.IGNORECASE)


def _invoice_number_for_subscription(subscription_id: UUID, occurred_at: datetime) -> str:
    compact = str(subscription_id).replace("-", "").upper()
    short = compact[:8] if compact else "XXXX0000"
    return f"FAC-{occurred_at.strftime('%Y%m%d')}-{short}"


def _send_template_email(
    db: Session,
    *,
    template_code: str,
    context: dict[str, str],
    to_email: str,
    delivery_context: str,
    language: str | None = None,
    recipient_user_id: UUID | None = None,
) -> str | None:
    try:
        template = resolve_predefined_template(db, code=template_code, language=normalize_language(language))
    except KeyError:
        logger.warning("Unknown predefined template for purchase notifications: %s", template_code)
        return None

    if not bool(template.get("active", True)):
        return None

    subject_template = str(template.get("subject") or "").strip()
    body_template = str(template.get("body") or "").strip()
    if not subject_template or not body_template:
        logger.warning("Template %s is incomplete (subject/body empty)", template_code)
        return None

    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)
    body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
        context=delivery_context,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        recipient_user_id=recipient_user_id,
    )


def send_payment_success_notifications(
    db: Session,
    *,
    to_email: str,
    first_name: str | None,
    last_name: str | None,
    payment_label: str,
    payment_reference: str,
    paid_at: datetime,
    transactions_url: str,
    invoice_url: str,
    invoice_number: str,
    amount_paid: Decimal | None = None,
    currency: str | None = None,
    payment_url: str | None = None,
    issued_date: str | None = None,
    due_date: str | None = None,
    studio_booking_url: str | None = None,
    language: str | None = None,
    recipient_user_id: UUID | None = None,
) -> dict[str, str | None]:
    safe_first_name = (first_name or "").strip() or to_email
    safe_last_name = (last_name or "").strip()
    full_name = f"{safe_first_name} {safe_last_name}".strip() or to_email
    recipient_name = recipient_display_name(first_name=first_name, last_name=last_name, email=to_email)
    normalized_currency = (currency or "EUR").strip().upper() or "EUR"
    amount_text = ""
    if amount_paid is not None:
        amount_text = f"{amount_paid.quantize(Decimal('0.01')):.2f}"

    normalized_payment_label = payment_label.strip() or invoice_number.strip() or "Paiement"
    normalized_payment_reference = payment_reference.strip() or invoice_number.strip() or "-"
    normalized_invoice_number = invoice_number.strip() or normalized_payment_reference
    normalized_payment_url = (payment_url or "").strip() or invoice_url
    normalized_studio_booking_url = (studio_booking_url or "").strip()

    context = {
        "first_name": safe_first_name,
        "last_name": safe_last_name,
        "full_name": full_name,
        "client_name": full_name,
        "recipient_name": recipient_name,
        "email": to_email,
        "plan_name": normalized_payment_label,
        "payment_label": normalized_payment_label,
        "subscription_reference": normalized_payment_reference,
        "payment_reference": normalized_payment_reference,
        "amount_paid": amount_text,
        "amount_due": amount_text,
        "total_incl_vat": amount_text,
        "currency": normalized_currency,
        "transactions_url": transactions_url.strip(),
        "invoice_url": invoice_url.strip(),
        "invoice_number": normalized_invoice_number,
        "paid_at": paid_at.strftime("%d/%m/%Y %H:%M"),
        "payment_url": normalized_payment_url,
        "issued_date": (issued_date or "").strip(),
        "due_date": (due_date or "").strip(),
        "account_url": _frontend_url("/client?tab=finance"),
        "booking_url": normalized_studio_booking_url,
    }

    return {
        "payment_confirmation_message_id": _send_template_email(
            db,
            template_code=("STUDIO_PAYMENT_CONFIRMED" if normalized_studio_booking_url else "PAYMENT_CONFIRMED"),
            context=context,
            to_email=to_email,
            delivery_context="CLIENT_PAYMENT_CONFIRMED",
            language=language,
            recipient_user_id=recipient_user_id,
        ),
        "invoice_message_id": _send_template_email(
            db,
            template_code="INVOICE_PAID",
            context=context,
            to_email=to_email,
            delivery_context="CLIENT_INVOICE_PAID",
            language=language,
            recipient_user_id=recipient_user_id,
        ),
    }


def send_client_payment_success_notifications(
    db: Session,
    *,
    to_email: str,
    first_name: str | None,
    last_name: str | None,
    plan_name: str,
    subscription_id: UUID,
    paid_at: datetime,
    amount_paid: Decimal | None = None,
    currency: str | None = None,
    language: str | None = None,
) -> dict[str, str | None]:
    transactions_url = _frontend_url(f"/dashboard?tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}")
    invoice_token = create_plan_invoice_download_token(subscription_id=subscription_id)
    invoice_query = urlencode({"token": invoice_token})
    invoice_url = _frontend_url(f"/api/v1/public/invoices/plans/{subscription_id}/download?{invoice_query}")
    invoice_number = _invoice_number_for_subscription(subscription_id, paid_at)
    studio_booking_url = _studio_booking_url(db) if _is_studio_booking_purchase(plan_name) else None
    return send_payment_success_notifications(
        db,
        to_email=to_email,
        first_name=first_name,
        last_name=last_name,
        payment_label=plan_name,
        payment_reference=str(subscription_id),
        paid_at=paid_at,
        amount_paid=amount_paid,
        currency=currency,
        transactions_url=transactions_url,
        invoice_url=invoice_url,
        invoice_number=invoice_number,
        issued_date=paid_at.strftime("%d/%m/%Y"),
        due_date=paid_at.strftime("%d/%m/%Y"),
        studio_booking_url=studio_booking_url,
        language=language,
    )


def send_plan_purchase_admin_notifications(
    db: Session,
    *,
    client_id: UUID,
    client_email: str,
    first_name: str | None,
    last_name: str | None,
    plan_name: str,
    subscription_id: UUID,
    payment_reference: str,
    payment_method: str | None,
    paid_at: datetime,
    amount_paid: Decimal | None = None,
    currency: str | None = None,
    student_name: str | None = None,
) -> list[str]:
    client_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip() or client_email
    normalized_currency = (currency or "EUR").strip().upper() or "EUR"
    amount_text = ""
    if amount_paid is not None:
        amount_text = f"{amount_paid.quantize(Decimal('0.01')):.2f}"
    try:
        local_paid_at = paid_at.astimezone(ZoneInfo("Europe/Paris"))
    except (ValueError, KeyError):
        local_paid_at = paid_at
    context = {
        "client_name": client_name,
        "client_email": client_email,
        "student_name": (student_name or "").strip() or client_name,
        "plan_name": plan_name.strip() or "Formule Piano Académie",
        "amount_paid": amount_text,
        "currency": normalized_currency,
        "paid_at": local_paid_at.strftime("%d/%m/%Y %H:%M"),
        "payment_reference": payment_reference.strip() or "-",
        "payment_method": (payment_method or "Paiement en ligne").strip() or "Paiement en ligne",
        "subscription_reference": str(subscription_id),
        "client_url": _frontend_url(f"/admin/clients/{client_id}?tab=fiche"),
    }
    message_ids: list[str] = []
    sent_to: set[str] = set()
    for recipient in resolve_admin_plan_purchase_recipients(db):
        admin_email = (recipient.email or "").strip().lower()
        if not admin_email or admin_email in sent_to:
            continue
        sent_to.add(admin_email)
        message_id = _send_template_email(
            db,
            template_code="PLAN_PURCHASE_ADMIN",
            context=context,
            to_email=admin_email,
            delivery_context="ADMIN_PLAN_PURCHASE_CONFIRMED",
            language="fr",
        )
        if message_id:
            message_ids.append(message_id)
    return message_ids


__all__ = [
    "plan_purchase_notification_label",
    "send_client_payment_success_notifications",
    "send_payment_success_notifications",
    "send_plan_purchase_admin_notifications",
]
