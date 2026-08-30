from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupplyOrderItemIn(BaseModel):
    product_id: UUID | None = None
    product_title: str | None = Field(default=None, max_length=255)
    quantity: int = Field(ge=1, le=1000000, strict=True)

    @model_validator(mode="after")
    def validate_product(self):
        if not self.product_id and not (self.product_title or "").strip():
            raise ValueError("Indiquez le nom du produit non référencé.")
        return self


class SupplyOrderCreate(BaseModel):
    submission_id: UUID
    location_id: UUID
    reference: str | None = Field(default=None, max_length=255)
    supplier: str | None = Field(default=None, max_length=255)
    ordered_date: date
    expected_delivery_date: date
    note: str | None = Field(default=None, max_length=2000)
    items: list[SupplyOrderItemIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_order(self):
        if self.expected_delivery_date < self.ordered_date:
            raise ValueError("La livraison prévue doit être postérieure ou égale à la date de commande.")
        keys = [str(item.product_id) if item.product_id else (item.product_title or "").strip().casefold() for item in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("Chaque produit doit figurer sur une seule ligne de commande.")
        return self


class SupplyOrderReceive(BaseModel):
    received_date: date
    product_links: dict[UUID, UUID] = Field(default_factory=dict)


class SupplyOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID | None
    product_title: str
    quantity: int
    stock_movement_id: UUID | None


class SupplyOrderOut(BaseModel):
    id: UUID
    reference: str | None
    supplier: str | None
    location_id: UUID
    location_name: str
    ordered_date: date
    expected_delivery_date: date
    status: Literal["ORDERED", "RECEIVED", "CANCELLED"]
    note: str | None
    received_date: date | None
    created_at: datetime
    completed_at: datetime | None
    items: list[SupplyOrderItemOut]
