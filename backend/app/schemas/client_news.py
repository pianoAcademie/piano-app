from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AdminClientNewsBase(BaseModel):
    title_fr: str = Field(min_length=1, max_length=220)
    title_en: str | None = Field(default=None, max_length=220)
    summary_fr: str | None = Field(default=None, max_length=500)
    summary_en: str | None = Field(default=None, max_length=500)
    body_fr: str = Field(min_length=1, max_length=20000)
    body_en: str | None = Field(default=None, max_length=20000)
    link_url: str | None = Field(default=None, max_length=2000)
    link_label_fr: str | None = Field(default=None, max_length=120)
    link_label_en: str | None = Field(default=None, max_length=120)
    status: Literal["DRAFT", "PUBLISHED"] = "DRAFT"
    is_pinned: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator(
        "title_fr",
        "title_en",
        "summary_fr",
        "summary_en",
        "body_fr",
        "body_en",
        "link_url",
        "link_label_fr",
        "link_label_en",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("link_url")
    @classmethod
    def validate_link_url(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().startswith(("https://", "http://")):
            raise ValueError("Le lien doit commencer par http:// ou https://")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "AdminClientNewsBase":
        if self.expires_at is not None and self.published_at is not None and self.expires_at <= self.published_at:
            raise ValueError("La date d'expiration doit être postérieure à la publication")
        return self


class AdminClientNewsCreate(AdminClientNewsBase):
    pass


class AdminClientNewsUpdate(AdminClientNewsBase):
    pass


class AdminClientNewsOut(AdminClientNewsBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ClientNewsOut(BaseModel):
    id: UUID
    title: str
    summary: str | None = None
    body: str
    link_url: str | None = None
    link_label: str | None = None
    is_pinned: bool
    published_at: datetime
