from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationJobRunOut(BaseModel):
    id: UUID
    job_name: str
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    duration_seconds: int | None
    items_scanned: int
    items_processed: int
    items_sent: int
    items_skipped: int
    items_failed: int
    summary_text: str | None
    error_text: str | None


class NotificationJobRunPageOut(BaseModel):
    items: list[NotificationJobRunOut] = Field(default_factory=list)
    total: int


class NotificationJobRunLogOut(BaseModel):
    id: UUID
    level: str
    message: str
    context_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NotificationJobRelatedEntityOut(BaseModel):
    id: UUID
    notification_type: str
    channel: str
    status: str
    related_entity_type: str
    related_entity_id: UUID
    recipient_email: str | None
    recipient_phone: str | None
    scheduled_for: datetime
    sent_at: datetime | None
    failed_at: datetime | None
    skipped_at: datetime | None
    failure_reason: str | None


class NotificationIncidentOut(BaseModel):
    id: UUID
    contact_type: str
    contact_id: UUID
    channel: str
    incident_type: str
    severity: str
    provider_name: str | None
    provider_message_id: str | None
    detail_text: str | None
    notification_id: UUID | None
    detected_at: datetime


class NotificationJobRunDetailOut(BaseModel):
    run: NotificationJobRunOut
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    logs: list[NotificationJobRunLogOut] = Field(default_factory=list)
    notifications: list[NotificationJobRelatedEntityOut] = Field(default_factory=list)
    incidents: list[NotificationIncidentOut] = Field(default_factory=list)


class ContactDeliveryStatusOut(BaseModel):
    contact_type: str
    contact_id: UUID
    email: str | None
    email_status: str
    email_suspended_at: datetime | None
    email_suspension_reason: str | None
    phone: str | None
    phone_status: str
    phone_suspended_at: datetime | None
    phone_suspension_reason: str | None


class ContactDeliveryReactivateRequest(BaseModel):
    reactivate_email: bool = True
    reactivate_phone: bool = True


class DeliveryFeedbackWebhookRequest(BaseModel):
    provider_name: str | None = None
    provider_message_id: str
    channel: str
    event_type: str
    provider_status: str | None = None
    bounce_type: str | None = None
    detail: str | None = None
    occurred_at: datetime | None = None
