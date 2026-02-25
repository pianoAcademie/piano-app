from __future__ import annotations

import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


def send_session_operation_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    operation: str,
    session_title: str,
) -> str:
    message_id = f"session-op-{uuid4()}"
    logger.info(
        "Session operation email sent | id=%s | to=%s | operation=%s | format=%s | session=%s | subject=%s | body=%s",
        message_id,
        to_email,
        operation,
        body_format,
        session_title,
        subject,
        body,
    )
    return message_id

