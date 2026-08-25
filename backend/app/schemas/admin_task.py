from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator


AdminTaskType = Literal[
    "CLIENT_CALL",
    "PROVIDER_CALL",
    "SLOT_CHOICE",
    "PROFESSOR_CONTACT",
    "SHEET_MUSIC_DELIVERY",
    "PLANNING",
]
AdminTaskStoredStatus = Literal[
    "CREATED",
    "ASSIGNED",
    "IN_PROGRESS",
    "CONTACTED_NO_RESPONSE",
    "WAITING_CLIENT",
    "COMPLETED",
    "ARCHIVED",
]
AdminTaskEffectiveStatus = Literal[
    "CREATED",
    "ASSIGNED",
    "IN_PROGRESS",
    "CONTACTED_NO_RESPONSE",
    "WAITING_CLIENT",
    "OVERDUE",
    "COMPLETED",
    "ARCHIVED",
]


class AdminTaskCreateRequest(BaseModel):
    task_type: AdminTaskType
    description: str = Field(min_length=1, max_length=10000)
    comment: str | None = Field(default=None, max_length=10000)
    assignee_user_id: UUID | None = None
    client_id: UUID | None = None
    prospect_id: UUID | None = None
    intake_id: UUID | None = None
    quote_id: UUID | None = None
    due_at: datetime | None = None

    @field_validator("description", "comment", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip() or None

    @field_validator("due_at", mode="after")
    @classmethod
    def localize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=ZoneInfo("Europe/Paris"))
        return value

    @model_validator(mode="after")
    def validate_contact(self) -> "AdminTaskCreateRequest":
        if self.client_id is not None and self.prospect_id is not None:
            raise ValueError("Une tâche ne peut être liée qu'à un seul client ou prospect")
        return self


class AdminTaskUpdateRequest(BaseModel):
    task_type: AdminTaskType | None = None
    status: AdminTaskStoredStatus | None = None
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    comment: str | None = Field(default=None, max_length=10000)
    assignee_user_id: UUID | None = None
    clear_assignee: bool = False
    client_id: UUID | None = None
    prospect_id: UUID | None = None
    clear_contact: bool = False
    due_at: datetime | None = None
    clear_due_at: bool = False

    @field_validator("description", "comment", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip() or None

    @field_validator("due_at", mode="after")
    @classmethod
    def localize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=ZoneInfo("Europe/Paris"))
        return value

    @model_validator(mode="after")
    def validate_contact(self) -> "AdminTaskUpdateRequest":
        if self.client_id is not None and self.prospect_id is not None:
            raise ValueError("Une tâche ne peut être liée qu'à un seul client ou prospect")
        return self


class AdminTaskManagerOut(BaseModel):
    id: UUID
    name: str
    email: str


class AdminTaskCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("body", mode="before")
    @classmethod
    def strip_body(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip()


class AdminTaskCommentOut(BaseModel):
    id: UUID
    body: str
    author: AdminTaskManagerOut | None = None
    created_at: datetime


class AdminTaskContactOut(BaseModel):
    kind: Literal["CLIENT", "PROSPECT"]
    id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    linked_client_id: UUID | None = None


class AdminTaskSourceOut(BaseModel):
    intake_id: UUID | None = None
    intake_label: str | None = None
    quote_id: UUID | None = None
    quote_label: str | None = None


class AdminTaskSourcePrefillOut(BaseModel):
    contact: AdminTaskContactOut | None = None
    description: str
    source: AdminTaskSourceOut


class AdminTaskOut(BaseModel):
    id: UUID
    task_type: AdminTaskType
    status: AdminTaskStoredStatus
    effective_status: AdminTaskEffectiveStatus
    description: str
    comment: str | None = None
    comments: list[AdminTaskCommentOut] = Field(default_factory=list)
    assignee: AdminTaskManagerOut | None = None
    created_by: AdminTaskManagerOut | None = None
    contact: AdminTaskContactOut | None = None
    source: AdminTaskSourceOut
    due_at: datetime | None = None
    completed_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminTaskOptionsOut(BaseModel):
    managers: list[AdminTaskManagerOut]
    current_user_id: UUID
