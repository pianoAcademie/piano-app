from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


AutomationEventType = Literal[
    "PLAN_PURCHASE_CONFIRMED",
    "TRIAL_COURSE_ATTENDED",
    "FIRST_STUDIO_BOOKING_CREATED",
]
AutomationClientKind = Literal["ADULT", "CHILD"]


class AdminAutomationRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    event_type: AutomationEventType
    template_ref: str = Field(min_length=1, max_length=140)
    plan_id: UUID | None = None
    course_type_id: UUID | None = None
    location_id: UUID | None = None
    client_kind: AutomationClientKind | None = None
    delay_minutes: int = Field(default=0, ge=0, le=10080)
    active: bool = True

    @model_validator(mode="after")
    def validate_event_filters(self) -> "AdminAutomationRuleBase":
        if self.event_type == "PLAN_PURCHASE_CONFIRMED" and self.plan_id is None:
            raise ValueError("Une formule doit etre selectionnee pour un achat")
        if self.event_type != "PLAN_PURCHASE_CONFIRMED" and self.plan_id is not None:
            raise ValueError("Le filtre formule est reserve aux achats")
        return self


class AdminAutomationRuleCreate(AdminAutomationRuleBase):
    pass


class AdminAutomationRuleUpdate(AdminAutomationRuleBase):
    pass


class AdminAutomationRuleOut(AdminAutomationRuleBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
