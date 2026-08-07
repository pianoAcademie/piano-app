from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MobilePushDeviceRegisterRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    push_token: str = Field(min_length=16, max_length=512)
    platform: str = Field(pattern="^(IOS|ANDROID)$")
    app_target: str = Field(default="CLIENT", pattern="^(CLIENT|PROF)$")
    permission_status: str = Field(default="GRANTED", max_length=30)
    locale: str = Field(default="fr", max_length=8)
    app_version: str | None = Field(default=None, max_length=40)
    device_label: str | None = Field(default=None, max_length=120)


class MobilePushDeviceOut(BaseModel):
    id: UUID
    installation_id: str
    platform: str
    app_target: str
    permission_status: str
    locale: str
    app_version: str | None
    device_label: str | None
    is_enabled: bool
    last_seen_at: datetime


class MobilePushDeviceDisableRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    app_target: str = Field(default="CLIENT", pattern="^(CLIENT|PROF)$")


class MobilePushEventRequest(BaseModel):
    event: str = Field(pattern="^(RECEIVED|OPENED)$")


class AdminMobilePushRequest(BaseModel):
    title_fr: str = Field(min_length=1, max_length=120)
    body_fr: str = Field(min_length=1, max_length=1000)
    title_en: str | None = Field(default=None, max_length=120)
    body_en: str | None = Field(default=None, max_length=1000)
    deep_link: str | None = Field(default="/client", max_length=500)


class AdminSessionMobilePushRequest(AdminMobilePushRequest):
    included_student_ids: list[UUID] = Field(default_factory=list)


class AdminCollaboratorMobilePushRequest(AdminMobilePushRequest):
    collaborator_ids: list[UUID] = Field(default_factory=list)


class AdminMobilePushOut(BaseModel):
    requested_user_count: int
    device_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    details: list[str] = Field(default_factory=list)
    job_run_id: UUID


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
