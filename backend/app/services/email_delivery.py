from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalized_provider() -> str:
    provider = (settings.email_provider or "LOG").strip().upper()
    if provider not in {"LOG", "SMTP", "BREVO"}:
        return "LOG"
    return provider


def _smtp_host_port(provider: str) -> tuple[str, int]:
    host = settings.smtp_host.strip()
    port = settings.smtp_port
    if provider == "BREVO":
        if not host:
            host = "smtp-relay.brevo.com"
        if not settings.smtp_port:
            port = 587
    return host, port


def _subject_with_prefix(subject: str) -> str:
    prefix = (settings.email_subject_prefix or "").strip()
    if not prefix:
        return subject
    if subject.startswith(prefix):
        return subject
    return f"{prefix} {subject}".strip()


def _build_message(*, to_email: str, subject: str, body: str, body_format: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to_email
    message["Subject"] = _subject_with_prefix(subject)
    if settings.email_reply_to:
        message["Reply-To"] = settings.email_reply_to

    normalized_format = (body_format or "TEXT").strip().lower()
    if normalized_format == "html":
        message.set_content("This message requires an HTML compatible client.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    return message


def send_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str = "TEXT",
    context: str = "GENERIC",
) -> str:
    message_id = f"mail-{uuid4()}"
    provider = _normalized_provider()

    if provider == "LOG":
        logger.info(
            "Email delivery skipped (LOG mode) | id=%s | to=%s | context=%s | subject=%s",
            message_id,
            to_email,
            context,
            subject,
        )
        return message_id

    host, port = _smtp_host_port(provider)
    username = settings.smtp_username.strip()
    password = settings.smtp_password

    if not host:
        logger.error(
            "Email provider misconfigured: missing SMTP_HOST | id=%s | provider=%s | to=%s | context=%s",
            message_id,
            provider,
            to_email,
            context,
        )
        return message_id

    if not username or not password:
        logger.error(
            "Email provider misconfigured: missing SMTP credentials | id=%s | provider=%s | to=%s | context=%s",
            message_id,
            provider,
            to_email,
            context,
        )
        return message_id

    message = _build_message(to_email=to_email, subject=subject, body=body, body_format=body_format)

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                host=host,
                port=port,
                timeout=settings.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host=host, port=port, timeout=settings.smtp_timeout_seconds) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(username, password)
                smtp.send_message(message)
    except Exception:
        logger.exception(
            "Email delivery failed | id=%s | provider=%s | host=%s | port=%s | to=%s | context=%s",
            message_id,
            provider,
            host,
            port,
            to_email,
            context,
        )
        return message_id

    logger.info(
        "Email delivered | id=%s | provider=%s | to=%s | context=%s | subject=%s",
        message_id,
        provider,
        to_email,
        context,
        subject,
    )
    return message_id

