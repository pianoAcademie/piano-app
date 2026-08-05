from __future__ import annotations

from pydantic import BaseModel, Field


class SportigoCatalogItem(BaseModel):
    code: str
    name: str
    kind: str | None = None


class SportigoImportCatalogOut(BaseModel):
    subscription_plans: list[SportigoCatalogItem] = Field(default_factory=list)
    credit_types: list[SportigoCatalogItem] = Field(default_factory=list)


class SportigoImportOut(BaseModel):
    dry_run: bool
    activate: bool
    batch_reference: str
    rows_seen: int = 0
    rows_valid: int = 0
    clients_created: int = 0
    clients_reused_by_sportigo_id: int = 0
    clients_reused_by_email: int = 0
    clients_updated: int = 0
    subscriptions_created: int = 0
    subscriptions_updated: int = 0
    credit_lots_created: int = 0
    credit_lots_updated: int = 0
    credit_lots_zeroed: int = 0
    imported_clients_total: int = 0
    imported_monthly_total: int = 0
    imported_credit_clients_total: int = 0
    studio_credits_total: int = 0
    collective_credits_total: int = 0
    online_credits_total: int = 0
    solfege_credits_total: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
