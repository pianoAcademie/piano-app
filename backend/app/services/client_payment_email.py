from __future__ import annotations

from app.services.email_delivery import send_email
from app.services.messaging_templates import render_template_content


def _render_template(template: str, context: dict[str, str]) -> str:
    return render_template_content(template, context)


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
    body_format: str = "TEXT",
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
) -> str:
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
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
