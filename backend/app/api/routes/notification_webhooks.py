from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.ops import CommunicationChannel, CommunicationDeliveryStatus
from app.schemas.notifications import DeliveryFeedbackWebhookRequest
from app.services.communication_journal import update_communication_delivery_status
from app.services.notifications.domain.constants import (
    EVENT_EMAIL_BOUNCED,
    EVENT_SMS_DELIVERY_FAILED_PERMANENT,
    QUEUE_DELIVERY_FEEDBACK,
    SOURCE_PROVIDER_WEBHOOK,
)
from app.services.notifications.infrastructure.repository import create_domain_event
from app.services.shared.queue.redis_queue import queue_push
from app.services.webhook_security import assert_bearer_webhook_token

router = APIRouter(prefix="/notifications/webhooks")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _event_type_from_payload(payload: DeliveryFeedbackWebhookRequest) -> str:
    raw_channel = (payload.channel or "").strip().upper()
    raw_event = (payload.event_type or "").strip().lower()
    if raw_channel == "EMAIL":
        if "deliver" in raw_event:
            return "email_delivered"
        if "bounce" in raw_event or "bounced" in raw_event:
            return EVENT_EMAIL_BOUNCED
    if raw_channel == "SMS":
        if "deliver" in raw_event:
            return "sms_delivered"
        if "permanent" in raw_event or "failed_permanent" in raw_event or "invalid" in raw_event:
            return EVENT_SMS_DELIVERY_FAILED_PERMANENT
    if raw_event == EVENT_EMAIL_BOUNCED:
        return EVENT_EMAIL_BOUNCED
    if raw_event == "email_delivered":
        return "email_delivered"
    if raw_event == EVENT_SMS_DELIVERY_FAILED_PERMANENT:
        return EVENT_SMS_DELIVERY_FAILED_PERMANENT
    return ""


def _provider_message_related_entity_id(provider_message_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"provider-message:{provider_message_id.strip()}")


def _iter_payload_items(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        yield payload


def _normalize_brevo_event_name(raw_value: Any) -> str:
    return str(raw_value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def _parse_brevo_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in ("ts_event", "ts_epoch", "ts"):
        raw_value = payload.get(key)
        if raw_value in (None, ""):
            continue
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
    raw_date = str(payload.get("date") or "").strip()
    if not raw_date:
        return None
    normalized = raw_date.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_brevo_custom_value(payload: dict[str, Any], key: str) -> str | None:
    raw_custom = payload.get("X-Mailin-custom")
    if raw_custom in (None, ""):
        raw_custom = payload.get("X-Mailin-Custom")
    if raw_custom in (None, ""):
        return None
    for item in str(raw_custom).split("|"):
        candidate_key, separator, candidate_value = item.partition(":")
        if not separator:
            continue
        if candidate_key.strip().lower() == key.strip().lower():
            normalized = candidate_value.strip()
            return normalized or None
    return None


def _brevo_delivery_status(payload: dict[str, Any]) -> CommunicationDeliveryStatus | None:
    event_name = _normalize_brevo_event_name(payload.get("event"))
    if event_name == "delivered":
        return CommunicationDeliveryStatus.DELIVERED
    if event_name in {"request", "sent"}:
        return CommunicationDeliveryStatus.SENT
    if event_name in {"hardbounce", "softbounce", "bounce", "blocked", "invalid", "error"}:
        return CommunicationDeliveryStatus.FAILED
    return None


def _brevo_error_detail(payload: dict[str, Any]) -> str | None:
    for key in ("reason", "detail", "description"):
        raw_value = str(payload.get(key) or "").strip()
        if raw_value:
            return raw_value
    event_name = _normalize_brevo_event_name(payload.get("event"))
    if event_name in {"hardbounce", "softbounce", "bounce"}:
        return "email bounced"
    if event_name == "blocked":
        return "email blocked"
    if event_name == "invalid":
        return "invalid recipient"
    if event_name == "error":
        return "provider delivery error"
    return None


def _brevo_sms_message_id(payload: dict[str, Any]) -> str | None:
    for key in ("messageId", "message_id", "message-id", "id", "reference"):
        candidate = str(payload.get(key) or "").strip()
        if candidate:
            return candidate
    return None


def _brevo_sms_delivery_status(payload: dict[str, Any]) -> CommunicationDeliveryStatus | None:
    event_name = _normalize_brevo_event_name(payload.get("event") or payload.get("status"))
    if event_name in {"delivered", "deliverysucceeded", "success"}:
        return CommunicationDeliveryStatus.DELIVERED
    if event_name in {"sent", "request", "queued", "accepted"}:
        return CommunicationDeliveryStatus.SENT
    if event_name in {"hardbounce", "softbounce", "bounce", "blocked", "invalid", "error", "failed", "rejected"}:
        return CommunicationDeliveryStatus.FAILED
    return None


@router.post("/email")
def email_feedback_webhook(
    request: Request,
    payload: DeliveryFeedbackWebhookRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    assert_bearer_webhook_token(request)
    if (payload.channel or "").strip().upper() != "EMAIL":
        return {"accepted": False, "reason": "channel must be EMAIL"}
    event_type = _event_type_from_payload(payload)
    if not event_type:
        return {"accepted": False, "reason": "unsupported event"}

    if event_type == "email_delivered":
        delivered_at = payload.occurred_at or _utcnow()
        communication_id = update_communication_delivery_status(
            provider_message_id=payload.provider_message_id,
            channel=CommunicationChannel.EMAIL,
            delivery_status=CommunicationDeliveryStatus.DELIVERED,
            provider=(payload.provider_name or "").strip() or None,
            delivered_at=delivered_at,
            db=db,
        )
        db.commit()
        return {"accepted": True, "communication_id": str(communication_id) if communication_id is not None else None}

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


@router.post("/brevo/email")
def brevo_email_webhook(
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    assert_bearer_webhook_token(request)
    accepted = 0
    updated = 0
    queued = 0

    for item in _iter_payload_items(payload):
        local_message_id = _extract_brevo_custom_value(item, "piano_message_id")
        if local_message_id is None:
            continue
        delivery_status = _brevo_delivery_status(item)
        if delivery_status is None:
            continue
        accepted += 1
        occurred_at = _parse_brevo_timestamp(item) or _utcnow()
        communication_id = update_communication_delivery_status(
            provider_message_id=local_message_id,
            channel=CommunicationChannel.EMAIL,
            delivery_status=delivery_status,
            provider="BREVO",
            error_message=_brevo_error_detail(item) if delivery_status == CommunicationDeliveryStatus.FAILED else None,
            delivered_at=occurred_at if delivery_status == CommunicationDeliveryStatus.DELIVERED else None,
            failed_at=occurred_at if delivery_status == CommunicationDeliveryStatus.FAILED else None,
            db=db,
        )
        if communication_id is not None:
            updated += 1

        if delivery_status == CommunicationDeliveryStatus.FAILED:
            event_name = _normalize_brevo_event_name(item.get("event"))
            if event_name in {"hardbounce", "softbounce", "bounce"}:
                event = create_domain_event(
                    db,
                    event_type=EVENT_EMAIL_BOUNCED,
                    source=SOURCE_PROVIDER_WEBHOOK,
                    actor_type="provider",
                    actor_id=None,
                    related_entity_type="provider_message",
                    related_entity_id=_provider_message_related_entity_id(local_message_id),
                    occurred_at=occurred_at,
                    payload_json={
                        "provider_name": "BREVO",
                        "provider_message_id": local_message_id,
                        "provider_status": str(item.get("event") or "").strip() or None,
                        "bounce_type": "soft" if event_name == "softbounce" else "hard",
                        "detail": _brevo_error_detail(item),
                    },
                )
                queue_push(QUEUE_DELIVERY_FEEDBACK, {"event_id": str(event.id)})
                queued += 1

    db.commit()
    return {
        "accepted": True,
        "events_received": accepted,
        "communications_updated": updated,
        "feedback_events_queued": queued,
    }


@router.post("/sms")
def sms_feedback_webhook(
    request: Request,
    payload: DeliveryFeedbackWebhookRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    assert_bearer_webhook_token(request)
    if (payload.channel or "").strip().upper() != "SMS":
        return {"accepted": False, "reason": "channel must be SMS"}
    event_type = _event_type_from_payload(payload)
    if not event_type:
        return {"accepted": False, "reason": "unsupported event"}

    if event_type == "sms_delivered":
        delivered_at = payload.occurred_at or _utcnow()
        communication_id = update_communication_delivery_status(
            provider_message_id=payload.provider_message_id,
            channel=CommunicationChannel.SMS,
            delivery_status=CommunicationDeliveryStatus.DELIVERED,
            provider=(payload.provider_name or "").strip() or None,
            delivered_at=delivered_at,
            db=db,
        )
        db.commit()
        return {"accepted": True, "communication_id": str(communication_id) if communication_id is not None else None}

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


@router.post("/brevo/sms")
def brevo_sms_webhook(
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    assert_bearer_webhook_token(request)
    accepted = 0
    updated = 0
    queued = 0

    for item in _iter_payload_items(payload):
        provider_message_id = _brevo_sms_message_id(item)
        if provider_message_id is None:
            continue
        delivery_status = _brevo_sms_delivery_status(item)
        if delivery_status is None:
            continue
        accepted += 1
        occurred_at = _parse_brevo_timestamp(item) or _utcnow()
        communication_id = update_communication_delivery_status(
            provider_message_id=provider_message_id,
            channel=CommunicationChannel.SMS,
            delivery_status=delivery_status,
            provider="BREVO",
            error_message=_brevo_error_detail(item) if delivery_status == CommunicationDeliveryStatus.FAILED else None,
            delivered_at=occurred_at if delivery_status == CommunicationDeliveryStatus.DELIVERED else None,
            failed_at=occurred_at if delivery_status == CommunicationDeliveryStatus.FAILED else None,
            db=db,
        )
        if communication_id is not None:
            updated += 1

        if delivery_status == CommunicationDeliveryStatus.FAILED:
            event = create_domain_event(
                db,
                event_type=EVENT_SMS_DELIVERY_FAILED_PERMANENT,
                source=SOURCE_PROVIDER_WEBHOOK,
                actor_type="provider",
                actor_id=None,
                related_entity_type="provider_message",
                related_entity_id=_provider_message_related_entity_id(provider_message_id),
                occurred_at=occurred_at,
                payload_json={
                    "provider_name": "BREVO",
                    "provider_message_id": provider_message_id,
                    "provider_status": str(item.get("event") or item.get("status") or "").strip() or None,
                    "detail": _brevo_error_detail(item),
                },
            )
            queue_push(QUEUE_DELIVERY_FEEDBACK, {"event_id": str(event.id)})
            queued += 1

    db.commit()
    return {
        "accepted": True,
        "events_received": accepted,
        "communications_updated": updated,
        "feedback_events_queued": queued,
    }
