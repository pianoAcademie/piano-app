from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


AdminToProcessStatus = Literal["a_traiter", "en_cours", "termine"]


class AdminToProcessMessageOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    source: str
    message_type: str
    status: AdminToProcessStatus
    message_body: str
    teacher_id: UUID | None = None
    teacher_name: str | None = None
    handled_by_user_id: UUID | None = None
    related_entity_type: str | None = None
    related_entity_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminToProcessStatusUpdateRequest(BaseModel):
    status: AdminToProcessStatus


class AdminToProcessStatusUpdateOut(BaseModel):
    id: UUID
    status: AdminToProcessStatus
    updated_at: datetime
