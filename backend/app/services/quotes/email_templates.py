from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.quote import Quote, QuoteLine
from app.services.email_delivery import send_email
from app.services.i18n import normalize_language
from app.services.messaging_templates import (
    QUOTE_APPROVED_TEMPLATE_REF_DEFAULT,
    QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT,
    QUOTE_CANCEL_TEMPLATE_REF_DEFAULT,
    QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT,
    QUOTE_REJECTED_TEMPLATE_REF_DEFAULT,
    QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT,
    QUOTE_REMINDER_TEMPLATE_REF_DEFAULT,
    QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT,
    QUOTE_SEND_TEMPLATE_REF_DEFAULT,
    USAGE_CONTEXT_QUOTE_APPROVED,
    USAGE_CONTEXT_QUOTE_CANCEL,
    USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED,
    USAGE_CONTEXT_QUOTE_REJECTED,
    USAGE_CONTEXT_QUOTE_REMINDER,
    USAGE_CONTEXT_QUOTE_SEND,
    load_messaging_settings,
    resolve_messaging_template_ref,
    resolve_sender_profile,
)
from app.services.providers.sms import SmsProviderSendResult, send_provider_sms
from app.services.quotes.quote_documents import (
    AUDIENCE_PUBLIC_PAGE,
    build_quote_template_values,
    display_quote_expires_at,
)

logger = logging.getLogger(__name__)
MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class QuoteRenderedEmail:
    template_ref: str
    usage_context: str
    subject: str
    body: str
    body_format: str
    recipient_email: str


@dataclass(frozen=True)
class QuoteRenderedSms:
    template_ref: str
    usage_context: str
    body: str
    recipient_phone: str


class _SafeTemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: dict[str, str]) -> str:
    normalized = MUSTACHE_PLACEHOLDER_RE.sub(r"{\1}", template or "")
    try:
        return normalized.format_map(_SafeTemplateContext(context)).strip()
    except Exception:
        logger.warning("Unable to render quote email template, returning raw template")
        return normalized.strip()


def _quote_status_label(status: str | None, *, language: str | None = None) -> str:
    normalized = (status or "").strip().lower()
    if normalize_language(language) == "en":
        if normalized == "created":
            return "Draft"
        if normalized == "sent":
            return "Sent"
        if normalized == "change_requested":
            return "Change requested"
        if normalized == "approved":
            return "Approved"
        if normalized == "rejected":
            return "Rejected"
        if normalized == "expired":
            return "Expired"
        if normalized == "cancelled":
            return "Cancelled"
        return normalized or "-"

    if normalized == "created":
        return "Brouillon"
    if normalized == "sent":
        return "Envoye"
    if normalized == "change_requested":
        return "Demande de modification"
    if normalized == "approved":
        return "Valide"
    if normalized == "rejected":
        return "Refuse"
    if normalized == "expired":
        return "Expire"
    if normalized == "cancelled":
        return "Annule"
    return normalized or "-"


def _quote_timezone_name(db: Session, quote: Quote) -> str:
    if quote.location_id is not None:
        location = db.scalar(select(Location).where(Location.id == quote.location_id))
        if location is not None and (location.timezone or "").strip():
            return str(location.timezone).strip()
    return "Europe/Paris"


def _format_local_datetime(raw_value: datetime | None, timezone_name: str) -> str:
    if raw_value is None:
        return "-"
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("Europe/Paris")
    return raw_value.astimezone(zone).strftime("%d/%m/%Y %H:%M")


def _default_template_ref_for_usage_context(usage_context: str, *, channel: str = "EMAIL") -> str:
    if channel == "SMS":
        if usage_context == USAGE_CONTEXT_QUOTE_REMINDER:
            return QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT
        if usage_context == USAGE_CONTEXT_QUOTE_CANCEL:
            return QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT
        return QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT
    if usage_context == USAGE_CONTEXT_QUOTE_APPROVED:
        return QUOTE_APPROVED_TEMPLATE_REF_DEFAULT
    if usage_context == USAGE_CONTEXT_QUOTE_REJECTED:
        return QUOTE_REJECTED_TEMPLATE_REF_DEFAULT
    if usage_context == USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED:
        return QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT
    if usage_context == USAGE_CONTEXT_QUOTE_REMINDER:
        return QUOTE_REMINDER_TEMPLATE_REF_DEFAULT
    if usage_context == USAGE_CONTEXT_QUOTE_CANCEL:
        return QUOTE_CANCEL_TEMPLATE_REF_DEFAULT
    return QUOTE_SEND_TEMPLATE_REF_DEFAULT


def _settings_template_ref_for_usage_context(
    settings_payload: dict[str, object],
    usage_context: str,
    *,
    channel: str = "EMAIL",
) -> str:
    if channel == "SMS":
        if usage_context == USAGE_CONTEXT_QUOTE_REMINDER:
            return str(settings_payload.get("quote_reminder_sms_template_ref") or QUOTE_REMINDER_SMS_TEMPLATE_REF_DEFAULT)
        if usage_context == USAGE_CONTEXT_QUOTE_CANCEL:
            return str(settings_payload.get("quote_cancel_sms_template_ref") or QUOTE_CANCEL_SMS_TEMPLATE_REF_DEFAULT)
        return str(settings_payload.get("quote_send_sms_template_ref") or QUOTE_SEND_SMS_TEMPLATE_REF_DEFAULT)
    if usage_context == USAGE_CONTEXT_QUOTE_APPROVED:
        return str(settings_payload.get("quote_approved_template_ref") or QUOTE_APPROVED_TEMPLATE_REF_DEFAULT)
    if usage_context == USAGE_CONTEXT_QUOTE_REJECTED:
        return str(settings_payload.get("quote_rejected_template_ref") or QUOTE_REJECTED_TEMPLATE_REF_DEFAULT)
    if usage_context == USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED:
        return str(
            settings_payload.get("quote_change_requested_template_ref")
            or QUOTE_CHANGE_REQUESTED_TEMPLATE_REF_DEFAULT
        )
    if usage_context == USAGE_CONTEXT_QUOTE_REMINDER:
        return str(settings_payload.get("quote_reminder_template_ref") or QUOTE_REMINDER_TEMPLATE_REF_DEFAULT)
    if usage_context == USAGE_CONTEXT_QUOTE_CANCEL:
        return str(settings_payload.get("quote_cancel_template_ref") or QUOTE_CANCEL_TEMPLATE_REF_DEFAULT)
    return str(settings_payload.get("quote_send_template_ref") or QUOTE_SEND_TEMPLATE_REF_DEFAULT)


def build_quote_email_context(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    recipient_email: str | None = None,
    recipient_phone: str | None = None,
) -> dict[str, str]:
    values, _, _ = build_quote_template_values(db=db, quote=quote, lines=lines, audience=AUDIENCE_PUBLIC_PAGE)
    timezone_name = _quote_timezone_name(db, quote)
    normalized_language = normalize_language(quote.language)
    public_url = str(values.get("quote_public_url") or "").strip()
    pdf_url = str(values.get("quote_pdf_url") or "").strip()
    if not public_url and quote.public_token:
        frontend_base = str(load_messaging_settings(db)[0].get("frontend_base_url") or "").rstrip("/")
        if frontend_base:
            public_url = f"{frontend_base}/q/{quote.id}?t={quote.public_token}"
    if not pdf_url and quote.pdf_token:
        frontend_base = str(load_messaging_settings(db)[0].get("frontend_base_url") or "").rstrip("/")
        if frontend_base:
            pdf_url = f"{frontend_base}/q/{quote.id}/pdf?t={quote.pdf_token}"

    display_expires_at = display_quote_expires_at(quote)
    context = dict(values)
    context.update(
        {
            "recipient_email": (recipient_email or "").strip().lower(),
            "recipient_phone": (recipient_phone or "").strip(),
            "quote_status": str(quote.status or "").strip(),
            "quote_status_label": _quote_status_label(quote.status, language=normalized_language),
            "quote_timezone": timezone_name,
            "quote_public_url": public_url,
            "quote_pdf_url": pdf_url,
            "expires_at_local": _format_local_datetime(display_expires_at, timezone_name),
            "sent_at_local": _format_local_datetime(quote.sent_at, timezone_name),
            "cancelled_at_local": _format_local_datetime(quote.cancelled_at, timezone_name),
        }
    )
    return {key: str(value or "") for key, value in context.items()}


def render_quote_email_template(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    recipient_email: str,
    usage_context: str,
    template_ref: str | None = None,
) -> QuoteRenderedEmail:
    settings_payload, _ = load_messaging_settings(db)
    resolved_template_ref = template_ref or _settings_template_ref_for_usage_context(settings_payload, usage_context)
    template = resolve_messaging_template_ref(
        db,
        template_ref=resolved_template_ref,
        default_ref=_default_template_ref_for_usage_context(usage_context),
        channel="EMAIL",
        usage_context=usage_context,
        active_only=True,
        language=quote.language,
    )
    context = build_quote_email_context(db, quote=quote, lines=lines, recipient_email=recipient_email)
    subject = _render_template(str(template.get("subject") or ""), context)
    body = _render_template(str(template.get("body") or ""), context)
    return QuoteRenderedEmail(
        template_ref=str(template.get("id") or resolved_template_ref),
        usage_context=usage_context,
        subject=subject,
        body=body,
        body_format=str(template.get("body_format") or "TEXT"),
        recipient_email=recipient_email.strip().lower(),
    )


def send_quote_templated_email(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    recipient_email: str,
    usage_context: str,
    template_ref: str | None = None,
    sender_kind: str = "STUDIO",
    email_context: str = "QUOTE_SENT",
    raise_on_failure: bool = False,
) -> tuple[QuoteRenderedEmail, str | None]:
    rendered = render_quote_email_template(
        db,
        quote=quote,
        lines=lines,
        recipient_email=recipient_email,
        usage_context=usage_context,
        template_ref=template_ref,
    )
    sender = resolve_sender_profile(db, sender_kind=sender_kind)
    message_id = send_email(
        to_email=rendered.recipient_email,
        subject=rendered.subject,
        body=rendered.body,
        body_format=rendered.body_format,
        context=email_context,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        raise_on_failure=raise_on_failure,
    )
    return rendered, message_id


def render_quote_sms_template(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    recipient_phone: str,
    usage_context: str,
    template_ref: str | None = None,
) -> QuoteRenderedSms:
    settings_payload, _ = load_messaging_settings(db)
    resolved_template_ref = template_ref or _settings_template_ref_for_usage_context(
        settings_payload,
        usage_context,
        channel="SMS",
    )
    template = resolve_messaging_template_ref(
        db,
        template_ref=resolved_template_ref,
        default_ref=_default_template_ref_for_usage_context(usage_context, channel="SMS"),
        channel="SMS",
        usage_context=usage_context,
        active_only=True,
        language=quote.language,
    )
    context = build_quote_email_context(db, quote=quote, lines=lines, recipient_phone=recipient_phone)
    body = _render_template(str(template.get("body") or ""), context)
    return QuoteRenderedSms(
        template_ref=str(template.get("id") or resolved_template_ref),
        usage_context=usage_context,
        body=body,
        recipient_phone=recipient_phone.strip(),
    )


def send_quote_templated_sms(
    db: Session,
    *,
    quote: Quote,
    lines: list[QuoteLine],
    recipient_phone: str,
    usage_context: str,
    template_ref: str | None = None,
    sms_context: str = "QUOTE_SMS",
) -> tuple[QuoteRenderedSms, SmsProviderSendResult]:
    rendered = render_quote_sms_template(
        db,
        quote=quote,
        lines=lines,
        recipient_phone=recipient_phone,
        usage_context=usage_context,
        template_ref=template_ref,
    )
    result = send_provider_sms(
        to_phone=rendered.recipient_phone,
        message=rendered.body,
        context=sms_context,
        subject=(f"Quote {quote.quote_number}" if normalize_language(quote.language) == "en" else f"Devis {quote.quote_number}"),
        db=db,
    )
    return rendered, result


__all__ = [
    "QuoteRenderedEmail",
    "QuoteRenderedSms",
    "USAGE_CONTEXT_QUOTE_APPROVED",
    "USAGE_CONTEXT_QUOTE_CANCEL",
    "USAGE_CONTEXT_QUOTE_CHANGE_REQUESTED",
    "USAGE_CONTEXT_QUOTE_REJECTED",
    "USAGE_CONTEXT_QUOTE_REMINDER",
    "USAGE_CONTEXT_QUOTE_SEND",
    "build_quote_email_context",
    "render_quote_email_template",
    "render_quote_sms_template",
    "send_quote_templated_email",
    "send_quote_templated_sms",
]
