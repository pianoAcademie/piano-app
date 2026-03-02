from __future__ import annotations

from uuid import UUID

from app.models.ops import CommunicationSenderCategory
from app.services.email_delivery import send_email


def send_session_operation_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    operation: str,
    session_title: str,
    sender_user_id: UUID | None = None,
    sender_label: str | None = None,
    sender_category: CommunicationSenderCategory | str | None = None,
    professor_id: UUID | None = None,
    recipient_user_id: UUID | None = None,
) -> str:
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
        context=f"{operation}:{session_title}",
        sender_user_id=sender_user_id,
        sender_label=sender_label,
        sender_category=sender_category,
        professor_id=professor_id,
        recipient_user_id=recipient_user_id,
    )
