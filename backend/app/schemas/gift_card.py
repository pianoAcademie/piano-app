from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


class GiftCardCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=80)


class GiftCardPublicPreviewOut(BaseModel):
    redeem_token: str
    status: Literal["ACTIVE"]
    plan_id: UUID
    plan_name: str
    plan_description: str | None = None
    plan_kind: str
    recipient_name: str | None = None
    personal_message: str | None = None
    expires_at: datetime | None = None
    terms_required: bool = True


class GiftCardContextOut(GiftCardPublicPreviewOut):
    pass


class GiftCardRedeemRequest(BaseModel):
    redeem_token: str = Field(min_length=20, max_length=2000)
    user_id: UUID | None = None
    legal_terms_accepted: bool = False
    legal_terms_language: Literal["fr", "en"] = "fr"


class GiftCardRedeemOut(BaseModel):
    gift_card_id: UUID
    subscription_id: UUID
    redeemed_for_user_id: UUID
    plan_id: UUID
    plan_name: str
    credits_granted: int
    expires_at: datetime | None = None
    next_url: str = "/client?tab=planning"


class AdminGiftCardImportRequest(BaseModel):
    code: str = Field(min_length=6, max_length=80)
    plan_id: UUID
    source: Literal["ADMIN", "APP", "PHYSICAL", "WORDPRESS", "MIGRATION"] = "ADMIN"
    status: Literal["CREATED", "ACTIVE", "BLOCKED", "CANCELLED", "REFUNDED"] = "ACTIVE"
    external_order_ref: str | None = Field(default=None, max_length=120)
    external_line_ref: str | None = Field(default=None, max_length=120)
    purchaser_name: str | None = Field(default=None, max_length=255)
    purchaser_email: str | None = Field(default=None, max_length=255)
    recipient_name: str | None = Field(default=None, max_length=255)
    recipient_email: str | None = Field(default=None, max_length=255)
    personal_message: str | None = Field(default=None, max_length=1000)
    face_value_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    purchase_price_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    discount_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_rate: Decimal = Field(default=Decimal("0.000"), ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    paid_at: datetime | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    delivered_at: datetime | None = None
    terms_required: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator(
        "external_order_ref",
        "external_line_ref",
        "purchaser_name",
        "purchaser_email",
        "recipient_name",
        "recipient_email",
        "personal_message",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("paid_at", "valid_from", "expires_at", "delivered_at")
    @classmethod
    def normalize_paris_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Europe/Paris"))
        return value.astimezone(timezone.utc)


class AdminGiftCardOut(BaseModel):
    id: UUID
    code_suffix: str
    status: str
    source: str
    plan_id: UUID
    plan_name: str
    external_order_ref: str | None = None
    external_line_ref: str | None = None
    purchaser_name: str | None = None
    purchaser_email: str | None = None
    recipient_name: str | None = None
    recipient_email: str | None = None
    face_value_ttc: Decimal
    purchase_price_ttc: Decimal
    discount_ttc: Decimal
    vat_rate: Decimal
    currency: str
    paid_at: datetime | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    delivered_at: datetime | None = None
    redeemed_at: datetime | None = None
    redeemed_by_user_id: UUID | None = None
    redeemed_for_user_id: UUID | None = None
    subscription_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class AdminGiftCardStatusRequest(BaseModel):
    status: Literal["ACTIVE", "BLOCKED", "CANCELLED", "REFUNDED"]


class AdminGiftCardCsvPreviewRowOut(BaseModel):
    row_number: int
    result: Literal["READY", "ALREADY_IMPORTED", "BLOCKED"]
    code_suffix: str | None = None
    external_order_ref: str | None = None
    external_line_ref: str | None = None
    payment_status: str | None = None
    product_name: str | None = None
    face_value_ttc: Decimal | None = None
    purchase_price_ttc: Decimal | None = None
    messages: list[str] = Field(default_factory=list)


class AdminGiftCardCsvPreviewOut(BaseModel):
    plan_id: UUID
    plan_name: str
    total_rows: int
    ready_rows: int
    already_imported_rows: int
    blocked_rows: int
    rows: list[AdminGiftCardCsvPreviewRowOut]
