from __future__ import annotations

from app.services.email_delivery import send_email


def send_session_operation_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    operation: str,
    session_title: str,
) -> str:
    return send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        body_format=body_format,
        context=f"{operation}:{session_title}",
    )
