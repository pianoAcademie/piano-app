from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.ops import CommunicationChannel, CommunicationDeliveryStatus, CommunicationSenderCategory, MessageFormat
from app.services.communication_journal import COMMUNICATION_TYPE_OPERATIONAL, log_communication
from app.services.messaging_templates import (
    messaging_sms_delivery_disabled_reason,
    resolve_messaging_sms_delivery_config,
)

logger = logging.getLogger(__name__)

BREVO_SMS_API_URL = "https://api.brevo.com/v3/transactionalSMS/send"


@dataclass(frozen=True)
class SmsProviderSendResult:
    ok: bool
    provider_name: str
    provider_message_id: str | None
    provider_status: str
    error_message: str | None = None


def _normalize_brevo_sms_error(raw_error: str) -> str:
    normalized = (raw_error or "").strip()
    if not normalized:
        return "Erreur SMS Brevo inconnue."
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    code = str(payload.get("code") or "").strip().lower()
    message = str(payload.get("message") or "").strip()
    if code == "unauthorized" or "key not found" in message.lower():
        return (
            "Cle API Brevo SMS invalide ou introuvable. "
            "Utilisez une cle API Brevo issue de l'onglet 'Cles API et MCP', "
            "pas un login SMTP ni une cle SMTP."
        )
    return message or normalized


def sms_delivery_disabled_reason(db: Session | None = None) -> str | None:
    return messaging_sms_delivery_disabled_reason(resolve_messaging_sms_delivery_config(db))


def normalize_sms_recipient_number(value: str | None) -> str:
    compact = re.sub(r"[^\d+]+", "", (value or "").strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact.startswith("+"):
        plus_digits = re.sub(r"\D+", "", compact[1:])
        return f"+{plus_digits}"

    digits = re.sub(r"\D+", "", compact)
    if len(digits) == 10 and digits.startswith("0"):
        return f"+33{digits[1:]}"
    if len(digits) == 11 and digits.startswith("33"):
        return f"+{digits}"
    return digits


def _log_sms(
    *,
    to_phone: str,
    message: str,
    context: str,
    provider_name: str,
    provider_message_id: str | None,
    delivery_status: CommunicationDeliveryStatus,
    subject: str | None,
    error_message: str | None = None,
    db: Session | None = None,
) -> None:
    log_communication(
        channel=CommunicationChannel.SMS,
        source=context,
        communication_type=COMMUNICATION_TYPE_OPERATIONAL,
        sender_category=CommunicationSenderCategory.SYSTEM,
        sender_label="Systeme",
        recipient=to_phone,
        subject=(subject or "").strip() or "Notification SMS",
        content=message,
        content_format=MessageFormat.TEXT,
        delivery_status=delivery_status,
        provider=provider_name,
        provider_message_id=provider_message_id,
        error_message=error_message,
        db=db,
    )


def send_provider_sms(
    *,
    to_phone: str,
    message: str,
    context: str,
    subject: str | None = None,
    db: Session | None = None,
) -> SmsProviderSendResult:
    normalized_phone = normalize_sms_recipient_number(to_phone)
    normalized_message = (message or "").strip()
    if not normalized_phone:
        return SmsProviderSendResult(
            ok=False,
            provider_name="SMS",
            provider_message_id=None,
            provider_status="FAILED",
            error_message="Missing SMS recipient",
        )
    if not normalized_message:
        return SmsProviderSendResult(
            ok=False,
            provider_name="SMS",
            provider_message_id=None,
            provider_status="FAILED",
            error_message="Missing SMS body",
        )

    config = resolve_messaging_sms_delivery_config(db)
    provider_name = config.provider or "LOG"
    provider_message_id = f"sms-{uuid4()}"

    if provider_name == "LOG":
        try:
            _log_sms(
                to_phone=normalized_phone,
                message=normalized_message,
                context=context,
                provider_name="LOG_SMS",
                provider_message_id=provider_message_id,
                delivery_status=CommunicationDeliveryStatus.SKIPPED,
                subject=subject,
                db=db,
            )
        except Exception as exc:  # pragma: no cover - defensive safety net
            return SmsProviderSendResult(
                ok=False,
                provider_name="LOG_SMS",
                provider_message_id=None,
                provider_status="FAILED",
                error_message=str(exc),
            )
        return SmsProviderSendResult(
            ok=True,
            provider_name="LOG_SMS",
            provider_message_id=provider_message_id,
            provider_status="SKIPPED",
        )

    payload = {
        "sender": config.sender,
        "recipient": normalized_phone,
        "content": normalized_message,
        "type": "transactional",
    }
    req = urllib_request.Request(
        BREVO_SMS_API_URL,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": config.brevo_api_key,
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=15) as response:  # noqa: S310 - trusted Brevo endpoint
            raw_body = response.read().decode("utf-8")
            parsed = json.loads(raw_body or "{}")
    except urllib_error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        error_message = _normalize_brevo_sms_error(raw_error.strip() or str(exc))
        logger.warning("Brevo SMS send failed | to=%s | context=%s | error=%s", normalized_phone, context, error_message)
        _log_sms(
            to_phone=normalized_phone,
            message=normalized_message,
            context=context,
            provider_name="BREVO",
            provider_message_id=provider_message_id,
            delivery_status=CommunicationDeliveryStatus.FAILED,
            subject=subject,
            error_message=error_message,
            db=db,
        )
        return SmsProviderSendResult(
            ok=False,
            provider_name="BREVO",
            provider_message_id=provider_message_id,
            provider_status="FAILED",
            error_message=error_message,
        )
    except Exception as exc:  # pragma: no cover - network/runtime safety net
        error_message = str(exc)
        logger.exception("Brevo SMS send raised an unexpected error")
        _log_sms(
            to_phone=normalized_phone,
            message=normalized_message,
            context=context,
            provider_name="BREVO",
            provider_message_id=provider_message_id,
            delivery_status=CommunicationDeliveryStatus.FAILED,
            subject=subject,
            error_message=error_message,
            db=db,
        )
        return SmsProviderSendResult(
            ok=False,
            provider_name="BREVO",
            provider_message_id=provider_message_id,
            provider_status="FAILED",
            error_message=error_message,
        )

    resolved_message_id = str(parsed.get("messageId") or parsed.get("reference") or provider_message_id).strip() or provider_message_id
    _log_sms(
        to_phone=normalized_phone,
        message=normalized_message,
        context=context,
        provider_name="BREVO",
        provider_message_id=resolved_message_id,
        delivery_status=CommunicationDeliveryStatus.SENT,
        subject=subject,
        db=db,
    )
    return SmsProviderSendResult(
        ok=True,
        provider_name="BREVO",
        provider_message_id=resolved_message_id,
        provider_status="SENT",
    )
