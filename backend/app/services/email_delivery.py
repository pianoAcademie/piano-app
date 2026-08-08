from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable
from uuid import uuid4
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ops import CommunicationChannel, CommunicationDeliveryStatus, CommunicationSenderCategory, MessageFormat
from app.services.communication_journal import infer_communication_type, log_communication
from app.services.messaging_templates import MessagingDeliveryConfig, messaging_delivery_disabled_reason, resolve_messaging_delivery_config

logger = logging.getLogger(__name__)


EmailAttachment = tuple[str, bytes, str]


class EmailDeliveryError(RuntimeError):
    """Raised when a caller explicitly wants delivery failures surfaced."""


def email_delivery_disabled_reason() -> str | None:
    return messaging_delivery_disabled_reason(resolve_messaging_delivery_config())


def _smtp_host_port(delivery_config: MessagingDeliveryConfig) -> tuple[str, int]:
    return delivery_config.smtp_host, delivery_config.smtp_port


def _subject_with_prefix(
    subject: str,
    *,
    delivery_config: MessagingDeliveryConfig,
    subject_prefix: str | None = None,
) -> str:
    prefix = (subject_prefix if subject_prefix is not None else delivery_config.subject_prefix or "").strip()
    if not prefix:
        return subject
    if subject.startswith(prefix):
        return subject
    return f"{prefix} {subject}".strip()


def _build_message(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
    attachments: Iterable[EmailAttachment] | None = None,
    delivery_config: MessagingDeliveryConfig,
    provider_message_id: str | None = None,
    context: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    sender_email = (from_email or delivery_config.from_email).strip()
    sender_name = (from_name or "").strip()
    message["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    message["To"] = to_email
    message["Subject"] = _subject_with_prefix(subject, delivery_config=delivery_config, subject_prefix=subject_prefix)
    message_reply_to = (reply_to if reply_to is not None else delivery_config.reply_to) or ""
    if message_reply_to.strip():
        message["Reply-To"] = message_reply_to.strip()
    if provider_message_id:
        message["X-Piano-Message-Id"] = provider_message_id
        mailin_parts = [f"piano_message_id:{provider_message_id}"]
        normalized_context = (context or "").strip().replace("|", "/").replace(":", "=")
        if normalized_context:
            mailin_parts.append(f"context:{normalized_context}")
        message["X-Mailin-custom"] = "|".join(mailin_parts)

    normalized_format = (body_format or "TEXT").strip().lower()
    if normalized_format == "html":
        message.set_content("This message requires an HTML compatible client.")
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    for attachment in attachments or ():
        file_name, content, mime_type = attachment
        maintained_name = (file_name or "").strip() or "attachment.bin"
        maintained_mime = (mime_type or "").strip().lower() or "application/octet-stream"
        maintype, _, subtype = maintained_mime.partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=maintained_name)

    return message


def send_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str = "TEXT",
    context: str = "GENERIC",
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    subject_prefix: str | None = None,
    attachments: Iterable[EmailAttachment] | None = None,
    sender_user_id: UUID | None = None,
    sender_label: str | None = None,
    sender_category: CommunicationSenderCategory | str | None = None,
    professor_id: UUID | None = None,
    recipient_user_id: UUID | None = None,
    communication_type: str | None = None,
    raise_on_failure: bool = False,
    db: Session | None = None,
) -> str | None:
    message_id = f"mail-{uuid4()}"
    delivery_config = resolve_messaging_delivery_config()
    provider = delivery_config.provider
    normalized_format = "HTML" if (body_format or "").strip().lower() == "html" else "TEXT"
    raw_sender_category = (
        sender_category.value
        if isinstance(sender_category, CommunicationSenderCategory)
        else str(sender_category or CommunicationSenderCategory.SYSTEM.value)
    )
    resolved_sender_category = CommunicationSenderCategory(raw_sender_category.strip().upper())
    resolved_sender_label = (sender_label or "").strip() or (
        "Systeme" if resolved_sender_category == CommunicationSenderCategory.SYSTEM else "Autre utilisateur"
    )
    resolved_type = communication_type or infer_communication_type(
        source=context,
        context=context,
        sender_category=resolved_sender_category,
        channel=CommunicationChannel.EMAIL,
    )

    if provider == "LOG":
        logger.info(
            "Email delivery skipped (LOG mode) | id=%s | to=%s | context=%s | subject=%s",
            message_id,
            to_email,
            context,
            subject,
        )
        log_communication(
            channel=CommunicationChannel.EMAIL,
            source=context,
            communication_type=resolved_type,
            sender_category=resolved_sender_category,
            sender_user_id=sender_user_id,
            sender_label=resolved_sender_label,
            professor_id=professor_id,
            recipient_user_id=recipient_user_id,
            recipient=to_email,
            subject=subject,
            content=body,
            content_format=MessageFormat.HTML if normalized_format == "HTML" else MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.SKIPPED,
            provider=provider,
            provider_message_id=message_id,
            db=db,
        )
        if raise_on_failure:
            raise EmailDeliveryError("Email delivery skipped (LOG mode)")
        return None

    host, port = _smtp_host_port(delivery_config)
    username = delivery_config.smtp_username.strip()
    password = delivery_config.smtp_password

    if not host:
        logger.error(
            "Email provider misconfigured: missing SMTP_HOST | id=%s | provider=%s | to=%s | context=%s",
            message_id,
            provider,
            to_email,
            context,
        )
        log_communication(
            channel=CommunicationChannel.EMAIL,
            source=context,
            communication_type=resolved_type,
            sender_category=resolved_sender_category,
            sender_user_id=sender_user_id,
            sender_label=resolved_sender_label,
            professor_id=professor_id,
            recipient_user_id=recipient_user_id,
            recipient=to_email,
            subject=subject,
            content=body,
            content_format=MessageFormat.HTML if normalized_format == "HTML" else MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.FAILED,
            provider=provider,
            provider_message_id=message_id,
            error_message="Missing SMTP host",
            db=db,
        )
        if raise_on_failure:
            raise EmailDeliveryError("Missing SMTP host")
        return None

    if not username or not password:
        logger.error(
            "Email provider misconfigured: missing SMTP credentials | id=%s | provider=%s | to=%s | context=%s",
            message_id,
            provider,
            to_email,
            context,
        )
        log_communication(
            channel=CommunicationChannel.EMAIL,
            source=context,
            communication_type=resolved_type,
            sender_category=resolved_sender_category,
            sender_user_id=sender_user_id,
            sender_label=resolved_sender_label,
            professor_id=professor_id,
            recipient_user_id=recipient_user_id,
            recipient=to_email,
            subject=subject,
            content=body,
            content_format=MessageFormat.HTML if normalized_format == "HTML" else MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.FAILED,
            provider=provider,
            provider_message_id=message_id,
            error_message="Missing SMTP credentials",
            db=db,
        )
        if raise_on_failure:
            raise EmailDeliveryError("Missing SMTP credentials")
        return None

    message = _build_message(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        subject_prefix=subject_prefix,
        attachments=attachments,
        delivery_config=delivery_config,
        provider_message_id=message_id,
        context=context,
    )

    try:
        if delivery_config.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                host=host,
                port=port,
                timeout=delivery_config.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host=host, port=port, timeout=delivery_config.smtp_timeout_seconds) as smtp:
                if delivery_config.smtp_use_tls:
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
        log_communication(
            channel=CommunicationChannel.EMAIL,
            source=context,
            communication_type=resolved_type,
            sender_category=resolved_sender_category,
            sender_user_id=sender_user_id,
            sender_label=resolved_sender_label,
            professor_id=professor_id,
            recipient_user_id=recipient_user_id,
            recipient=to_email,
            subject=subject,
            content=body,
            content_format=MessageFormat.HTML if normalized_format == "HTML" else MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.FAILED,
            provider=provider,
            provider_message_id=message_id,
            error_message="SMTP send exception",
            db=db,
        )
        if raise_on_failure:
            raise EmailDeliveryError("SMTP send exception")
        return None

    logger.info(
        "Email delivered | id=%s | provider=%s | to=%s | context=%s | subject=%s",
        message_id,
        provider,
        to_email,
        context,
        subject,
    )
    log_communication(
        channel=CommunicationChannel.EMAIL,
        source=context,
        communication_type=resolved_type,
        sender_category=resolved_sender_category,
        sender_user_id=sender_user_id,
        sender_label=resolved_sender_label,
        professor_id=professor_id,
        recipient_user_id=recipient_user_id,
        recipient=to_email,
        subject=subject,
        content=body,
        content_format=MessageFormat.HTML if normalized_format == "HTML" else MessageFormat.TEXT,
        delivery_status=CommunicationDeliveryStatus.SENT,
        provider=provider,
        provider_message_id=message_id,
        db=db,
    )
    return message_id
