from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.models.ops import CommunicationChannel, CommunicationDeliveryStatus, CommunicationSenderCategory, MessageFormat
from app.services.communication_journal import COMMUNICATION_TYPE_OPERATIONAL, log_communication


@dataclass(frozen=True)
class SmsProviderSendResult:
    ok: bool
    provider_name: str
    provider_message_id: str | None
    provider_status: str
    error_message: str | None = None


def send_provider_sms(
    *,
    to_phone: str,
    message: str,
    context: str,
) -> SmsProviderSendResult:
    provider_name = "LOG_SMS"
    provider_message_id = f"sms-{uuid4()}"
    try:
        log_communication(
            channel=CommunicationChannel.SMS,
            source=context,
            communication_type=COMMUNICATION_TYPE_OPERATIONAL,
            sender_category=CommunicationSenderCategory.SYSTEM,
            sender_label="Systeme",
            recipient=to_phone,
            subject="Notification SMS",
            content=message,
            content_format=MessageFormat.TEXT,
            delivery_status=CommunicationDeliveryStatus.SENT,
            provider=provider_name,
            provider_message_id=provider_message_id,
        )
    except Exception as exc:  # pragma: no cover - defensive safety net
        return SmsProviderSendResult(
            ok=False,
            provider_name=provider_name,
            provider_message_id=None,
            provider_status="FAILED",
            error_message=str(exc),
        )
    return SmsProviderSendResult(
        ok=True,
        provider_name=provider_name,
        provider_message_id=provider_message_id,
        provider_status="SENT",
    )
