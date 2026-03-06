from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.services.email_delivery import send_email


@dataclass(frozen=True)
class EmailProviderSendResult:
    ok: bool
    provider_name: str
    provider_message_id: str | None
    provider_status: str
    error_message: str | None = None


def send_provider_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    context: str,
) -> EmailProviderSendResult:
    provider_name = (settings.email_provider or "LOG").strip().upper()
    try:
        provider_message_id = send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            body_format=body_format,
            context=context,
        )
    except Exception as exc:  # pragma: no cover - defensive safety net
        return EmailProviderSendResult(
            ok=False,
            provider_name=provider_name,
            provider_message_id=None,
            provider_status="FAILED",
            error_message=str(exc),
        )

    if provider_message_id:
        return EmailProviderSendResult(
            ok=True,
            provider_name=provider_name,
            provider_message_id=provider_message_id,
            provider_status="SENT",
        )
    return EmailProviderSendResult(
        ok=False,
        provider_name=provider_name,
        provider_message_id=None,
        provider_status="FAILED",
        error_message="email provider returned empty message id",
    )
