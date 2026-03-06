from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.notifications import DeliveryFeedbackWebhookRequest
from app.services.notifications.domain.constants import (
    EVENT_EMAIL_BOUNCED,
    EVENT_SMS_DELIVERY_FAILED_PERMANENT,
    QUEUE_DELIVERY_FEEDBACK,
    SOURCE_PROVIDER_WEBHOOK,
)
from app.services.notifications.infrastructure.repository import create_domain_event
from app.services.shared.queue.redis_queue import queue_push

router = APIRouter(prefix="/notifications/webhooks")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _event_type_from_payload(payload: DeliveryFeedbackWebhookRequest) -> str:
    raw_channel = (payload.channel or "").strip().upper()
    raw_event = (payload.event_type or "").strip().lower()
    if raw_channel == "EMAIL":
        if "bounce" in raw_event or "bounced" in raw_event:
            return EVENT_EMAIL_BOUNCED
    if raw_channel == "SMS":
        if "permanent" in raw_event or "failed_permanent" in raw_event or "invalid" in raw_event:
            return EVENT_SMS_DELIVERY_FAILED_PERMANENT
    if raw_event == EVENT_EMAIL_BOUNCED:
        return EVENT_EMAIL_BOUNCED
    if raw_event == EVENT_SMS_DELIVERY_FAILED_PERMANENT:
        return EVENT_SMS_DELIVERY_FAILED_PERMANENT
    return ""


def _provider_message_related_entity_id(provider_message_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"provider-message:{provider_message_id.strip()}")


@router.post("/email")
def email_feedback_webhook(
    payload: DeliveryFeedbackWebhookRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if (payload.channel or "").strip().upper() != "EMAIL":
        return {"accepted": False, "reason": "channel must be EMAIL"}
    event_type = _event_type_from_payload(payload)
    if not event_type:
        return {"accepted": False, "reason": "unsupported event"}

    occurred_at = payload.occurred_at or _utcnow()
    event = create_domain_event(
        db,
        event_type=event_type,
        source=SOURCE_PROVIDER_WEBHOOK,
        actor_type="provider",
        actor_id=None,
        related_entity_type="provider_message",
        related_entity_id=_provider_message_related_entity_id(payload.provider_message_id),
        occurred_at=occurred_at,
        payload_json={
            "provider_name": payload.provider_name,
            "provider_message_id": payload.provider_message_id,
            "provider_status": payload.provider_status,
            "bounce_type": payload.bounce_type,
            "detail": payload.detail,
        },
    )
    db.commit()
    queue_push(QUEUE_DELIVERY_FEEDBACK, {"event_id": str(event.id)})
    return {"accepted": True, "event_id": str(event.id)}


@router.post("/sms")
def sms_feedback_webhook(
    payload: DeliveryFeedbackWebhookRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if (payload.channel or "").strip().upper() != "SMS":
        return {"accepted": False, "reason": "channel must be SMS"}
    event_type = _event_type_from_payload(payload)
    if not event_type:
        return {"accepted": False, "reason": "unsupported event"}

    occurred_at = payload.occurred_at or _utcnow()
    event = create_domain_event(
        db,
        event_type=event_type,
        source=SOURCE_PROVIDER_WEBHOOK,
        actor_type="provider",
        actor_id=None,
        related_entity_type="provider_message",
        related_entity_id=_provider_message_related_entity_id(payload.provider_message_id),
        occurred_at=occurred_at,
        payload_json={
            "provider_name": payload.provider_name,
            "provider_message_id": payload.provider_message_id,
            "provider_status": payload.provider_status,
            "detail": payload.detail,
        },
    )
    db.commit()
    queue_push(QUEUE_DELIVERY_FEEDBACK, {"event_id": str(event.id)})
    return {"accepted": True, "event_id": str(event.id)}
