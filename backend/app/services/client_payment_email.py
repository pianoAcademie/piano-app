from __future__ import annotations

import logging
import re

from app.services.email_delivery import send_email

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
        logger.warning("Unable to render client payment template, returning raw template")
        return normalized.strip()


def render_client_payment_email(
    *,
    subject_template: str,
    body_template: str,
    first_name: str,
    last_name: str,
    email: str,
    plan_name: str,
    amount_due: str,
    currency: str,
    payment_method: str,
    payment_url: str,
    subscription_reference: str,
    legal_terms_url: str,
) -> tuple[str, str]:
    full_name = f"{first_name} {last_name}".strip() or email
    context = {
        "first_name": first_name or email,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "plan_name": plan_name,
        "amount_due": amount_due,
        "currency": currency,
        "payment_method": payment_method,
        "payment_url": payment_url,
        "subscription_reference": subscription_reference,
        "legal_terms_url": legal_terms_url,
    }
    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)
    return subject, body


def send_client_payment_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
) -> str:
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="CLIENT_PAYMENT_REQUEST",
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        subject_prefix=subject_prefix,
    )


__all__ = [
    "render_client_payment_email",
    "send_client_payment_email",
]
