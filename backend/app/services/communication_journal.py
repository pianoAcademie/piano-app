from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.ops import (
    CommunicationChannel,
    CommunicationDeliveryStatus,
    CommunicationLog,
    CommunicationSenderCategory,
    MessageFormat,
)

logger = logging.getLogger(__name__)

COMMUNICATION_TYPE_COURSE_REMINDER = "COURSE_REMINDER"
COMMUNICATION_TYPE_OPERATIONAL = "OPERATIONAL"
COMMUNICATION_TYPE_BILLING = "BILLING"
COMMUNICATION_TYPE_PROFESSOR_STUDENT = "PROFESSOR_STUDENT"
COMMUNICATION_TYPE_OTHER = "OTHER"

COMMUNICATION_TYPE_LABELS: dict[str, str] = {
    COMMUNICATION_TYPE_COURSE_REMINDER: "Rappel de cours",
    COMMUNICATION_TYPE_OPERATIONAL: "Mail operationnel",
    COMMUNICATION_TYPE_BILLING: "Facturation / Paiement",
    COMMUNICATION_TYPE_PROFESSOR_STUDENT: "Communication professeur-eleve",
    COMMUNICATION_TYPE_OTHER: "Autre",
}

KNOWN_COMMUNICATION_TYPES: tuple[str, ...] = (
    COMMUNICATION_TYPE_COURSE_REMINDER,
    COMMUNICATION_TYPE_OPERATIONAL,
    COMMUNICATION_TYPE_BILLING,
    COMMUNICATION_TYPE_PROFESSOR_STUDENT,
    COMMUNICATION_TYPE_OTHER,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def infer_communication_type(
    *,
    source: str | None,
    context: str | None,
    sender_category: CommunicationSenderCategory,
    channel: CommunicationChannel,
) -> str:
    if channel == CommunicationChannel.SMS:
        return COMMUNICATION_TYPE_OPERATIONAL

    normalized_source = (source or "").strip().upper()
    normalized_context = (context or "").strip().upper()

    if sender_category == CommunicationSenderCategory.PROFESSOR:
        return COMMUNICATION_TYPE_PROFESSOR_STUDENT

    if "REMINDER" in normalized_source or "REMINDER" in normalized_context:
        return COMMUNICATION_TYPE_COURSE_REMINDER

    billing_markers: Iterable[str] = (
        "INVOICE",
        "PAYMENT",
        "SUBSCRIPTION",
        "CHECKOUT",
        "BILLING",
    )
    if any(marker in normalized_source for marker in billing_markers) or any(
        marker in normalized_context for marker in billing_markers
    ):
        return COMMUNICATION_TYPE_BILLING

    if normalized_source or normalized_context:
        return COMMUNICATION_TYPE_OPERATIONAL

    return COMMUNICATION_TYPE_OTHER


def communication_type_label(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        return COMMUNICATION_TYPE_LABELS[COMMUNICATION_TYPE_OTHER]
    return COMMUNICATION_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())


def normalize_communication_type(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        return COMMUNICATION_TYPE_OTHER
    if normalized in KNOWN_COMMUNICATION_TYPES:
        return normalized
    return normalized


def log_communication(
    *,
    channel: CommunicationChannel | str,
    source: str,
    sender_category: CommunicationSenderCategory | str,
    sender_label: str,
    recipient: str,
    subject: str,
    content: str,
    content_format: MessageFormat | str = MessageFormat.TEXT,
    delivery_status: CommunicationDeliveryStatus | str = CommunicationDeliveryStatus.UNKNOWN,
    provider: str | None = None,
    provider_message_id: str | None = None,
    error_message: str | None = None,
    communication_type: str | None = None,
    occurred_at: datetime | None = None,
    delivered_at: datetime | None = None,
    failed_at: datetime | None = None,
    sender_user_id: UUID | None = None,
    recipient_user_id: UUID | None = None,
    professor_id: UUID | None = None,
    db: Session | None = None,
) -> UUID | None:
    own_session = db is None
    session = db or SessionLocal()
    now = _utcnow()
    try:
        normalized_channel = CommunicationChannel((channel.value if isinstance(channel, CommunicationChannel) else str(channel)).strip().upper())
        normalized_sender_category = CommunicationSenderCategory(
            (sender_category.value if isinstance(sender_category, CommunicationSenderCategory) else str(sender_category)).strip().upper()
        )
        normalized_format = MessageFormat((content_format.value if isinstance(content_format, MessageFormat) else str(content_format)).strip().upper())
        normalized_delivery = CommunicationDeliveryStatus(
            (delivery_status.value if isinstance(delivery_status, CommunicationDeliveryStatus) else str(delivery_status)).strip().upper()
        )

        resolved_type = normalize_communication_type(
            communication_type
            or infer_communication_type(
                source=source,
                context=source,
                sender_category=normalized_sender_category,
                channel=normalized_channel,
            )
        )

        row = CommunicationLog(
            channel=normalized_channel,
            source=(source or "").strip() or "GENERIC",
            communication_type=resolved_type,
            sender_category=normalized_sender_category,
            sender_user_id=sender_user_id,
            sender_label=(sender_label or "").strip() or "Systeme",
            professor_id=professor_id,
            recipient_user_id=recipient_user_id,
            recipient=(recipient or "").strip() or "-",
            subject=(subject or "").strip() or "Communication systeme",
            content=content or "",
            content_format=normalized_format,
            delivery_status=normalized_delivery,
            provider=(provider or "").strip() or None,
            provider_message_id=(provider_message_id or "").strip() or None,
            error_message=(error_message or "").strip() or None,
            occurred_at=occurred_at or now,
            delivered_at=delivered_at,
            failed_at=failed_at,
            updated_at=now,
        )
        session.add(row)
        if own_session:
            session.commit()
            session.refresh(row)
        return row.id
    except Exception:  # pragma: no cover - defensive fallback for logging
        if own_session:
            session.rollback()
        logger.exception("Unable to persist communication log event")
        return None
    finally:
        if own_session:
            session.close()


def update_communication_delivery_status(
    *,
    provider_message_id: str,
    channel: CommunicationChannel | str,
    delivery_status: CommunicationDeliveryStatus | str,
    provider: str | None = None,
    error_message: str | None = None,
    delivered_at: datetime | None = None,
    failed_at: datetime | None = None,
    db: Session | None = None,
) -> UUID | None:
    provider_message = (provider_message_id or "").strip()
    if not provider_message:
        return None

    own_session = db is None
    session = db or SessionLocal()
    try:
        normalized_channel = CommunicationChannel((channel.value if isinstance(channel, CommunicationChannel) else str(channel)).strip().upper())
        normalized_delivery = CommunicationDeliveryStatus(
            (delivery_status.value if isinstance(delivery_status, CommunicationDeliveryStatus) else str(delivery_status)).strip().upper()
        )
        row = session.scalar(
            select(CommunicationLog)
            .where(
                CommunicationLog.provider_message_id == provider_message,
                CommunicationLog.channel == normalized_channel,
            )
            .order_by(CommunicationLog.occurred_at.desc())
            .limit(1)
        )
        if row is None:
            return None

        row.delivery_status = normalized_delivery
        if provider is not None:
            row.provider = provider.strip() or None
        if error_message is not None:
            row.error_message = error_message.strip() or None
        row.delivered_at = delivered_at if delivered_at is not None else (row.delivered_at or (_utcnow() if normalized_delivery == CommunicationDeliveryStatus.DELIVERED else None))
        row.failed_at = failed_at if failed_at is not None else (row.failed_at or (_utcnow() if normalized_delivery == CommunicationDeliveryStatus.FAILED else None))
        row.updated_at = _utcnow()
        session.add(row)
        if own_session:
            session.commit()
            session.refresh(row)
        return row.id
    except Exception:  # pragma: no cover - defensive fallback
        if own_session:
            session.rollback()
        logger.exception("Unable to update communication delivery status")
        return None
    finally:
        if own_session:
            session.close()

