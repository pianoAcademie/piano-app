from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_predefined_template, resolve_sender_profile

logger = logging.getLogger(__name__)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template)
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render purchase template, returning raw template")
        return normalized.strip()


def _frontend_url(path: str) -> str:
    candidate = (settings.frontend_base_url or "").strip() or "http://localhost:3000"
    if not candidate.startswith("http://") and not candidate.startswith("https://"):
        candidate = "https://" + candidate
    return candidate.rstrip("/") + path


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
) -> str | None:
    try:
        template = resolve_predefined_template(db, code=template_code)
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
    )


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
) -> dict[str, str | None]:
    safe_first_name = (first_name or "").strip() or to_email
    safe_last_name = (last_name or "").strip()
    full_name = f"{safe_first_name} {safe_last_name}".strip() or to_email
    normalized_currency = (currency or "EUR").strip().upper() or "EUR"
    amount_text = ""
    if amount_paid is not None:
        amount_text = f"{amount_paid.quantize(Decimal('0.01')):.2f}"

    transactions_url = _frontend_url(f"/dashboard?tab=transactions&source=PLAN_PURCHASE&payment_id={subscription_id}")
    invoice_url = _frontend_url(f"/dashboard/invoices/plan:{subscription_id}/download")
    invoice_number = _invoice_number_for_subscription(subscription_id, paid_at)

    context = {
        "first_name": safe_first_name,
        "last_name": safe_last_name,
        "full_name": full_name,
        "email": to_email,
        "plan_name": plan_name,
        "subscription_reference": str(subscription_id),
        "amount_paid": amount_text,
        "currency": normalized_currency,
        "transactions_url": transactions_url,
        "invoice_url": invoice_url,
        "invoice_number": invoice_number,
        "paid_at": paid_at.strftime("%d/%m/%Y %H:%M"),
    }

    return {
        "payment_confirmation_message_id": _send_template_email(
            db,
            template_code="PAYMENT_CONFIRMED",
            context=context,
            to_email=to_email,
            delivery_context="CLIENT_PAYMENT_CONFIRMED",
        ),
        "invoice_message_id": _send_template_email(
            db,
            template_code="INVOICE",
            context=context,
            to_email=to_email,
            delivery_context="CLIENT_INVOICE",
        ),
    }


__all__ = ["send_client_payment_success_notifications"]
