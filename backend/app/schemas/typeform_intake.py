from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TypeformFormConfigOut(BaseModel):
    id: UUID
    typeform_form_id: str
    source_code: str
    location_code: str
    school_year_label: str
    audience_segment: str
    default_quote_type: str | None = None
    default_quote_type_id: UUID | None = None
    default_pricing_catalog_id: UUID | None = None
    default_payment_plan_id: UUID | None = None
    default_legal_entity_id: UUID | None = None
    default_location_id: UUID | None = None
    default_language: str
    configuration_json: dict[str, object] = Field(default_factory=dict)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TypeformAnswerOut(BaseModel):
    key: str
    label: str
    value: str


class TypeformMatchCandidateOut(BaseModel):
    kind: str
    client_id: UUID | None = None
    adult_client_id: UUID | None = None
    child_client_id: UUID | None = None
    billing_client_id: UUID | None = None
    display_name: str
    subtitle: str | None = None
    confidence: int
    confidence_label: str
    reasons: list[str] = Field(default_factory=list)


class TypeformSessionMatchOptionOut(BaseModel):
    session_id: UUID
    activity_id: UUID
    activity_name: str
    location_id: UUID
    location_name: str
    title: str
    start_at: datetime
    start_time_label: str
    end_time_label: str
    weekday_label: str
    occurrence_label: str
    selection_label: str
    recurrence_group_id: UUID | None = None
    recurrence_label: str | None = None
    seats_remaining: int
    is_full: bool
    score: int
    reasons: list[str] = Field(default_factory=list)


class TypeformSessionRecommendationOut(BaseModel):
    activity_id: UUID
    activity_name: str
    requested_location: str | None = None
    requested_summary: str | None = None
    summary_status: str
    summary_label: str
    selected_session_id: UUID | None = None
    options: list[TypeformSessionMatchOptionOut] = Field(default_factory=list)
    manual_options: list[TypeformSessionMatchOptionOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockages: list[str] = Field(default_factory=list)


class TypeformQuotePreviewLineOut(BaseModel):
    line_category: str
    line_type: str
    master_item_type: str | None = None
    master_item_id: UUID | None = None
    activity_id: UUID | None = None
    product_id: UUID | None = None
    kit_id: UUID | None = None
    code: str | None = None
    title: str
    description: str | None = None
    pricing_unit: str
    quantity: Decimal
    vat_rate: Decimal
    unit_price_ht: Decimal
    unit_vat_amount: Decimal
    unit_price_ttc: Decimal
    amount_ht: Decimal
    amount_vat: Decimal
    amount_ttc: Decimal
    meta: dict[str, object] = Field(default_factory=dict)


class TypeformQuotePreviewOut(BaseModel):
    context_type: str
    context_label: str
    customer_label: str
    location_id: UUID | None = None
    location_name: str | None = None
    payment_plan_id: UUID | None = None
    payment_plan_name: str | None = None
    quote_type_id: UUID | None = None
    quote_type_name: str | None = None
    pricing_catalog_id: UUID | None = None
    pricing_catalog_name: str | None = None
    legal_entity_id: UUID | None = None
    legal_entity_name: str | None = None
    school_year_label: str | None = None
    language: str | None = None
    currency: str
    selected_options: list[str] = Field(default_factory=list)
    lines: list[TypeformQuotePreviewLineOut] = Field(default_factory=list)
    total_ht: Decimal = Decimal("0.00")
    total_vat: Decimal = Decimal("0.00")
    total_ttc: Decimal = Decimal("0.00")
    meta: dict[str, object] = Field(default_factory=dict)


class TypeformIntakeListOut(BaseModel):
    id: UUID
    source_form_id: str
    source_form_label: str
    source_response_id: str
    received_at: datetime
    intake_status: str
    detected_location: str | None = None
    detected_segment: str | None = None
    detected_school_year: str | None = None
    prospect_label: str | None = None
    child_label: str | None = None
    warnings: list[str] = Field(default_factory=list)
    blockages: list[str] = Field(default_factory=list)
    related_quote_id: UUID | None = None
    referral: dict[str, object] | None = None


class TypeformIntakeListPageOut(BaseModel):
    items: list[TypeformIntakeListOut] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class TypeformIntakeDetailOut(BaseModel):
    id: UUID
    source_form_id: str
    source_form_label: str
    source_response_id: str
    received_at: datetime
    intake_status: str
    detected_location: str | None = None
    detected_segment: str | None = None
    detected_school_year: str | None = None
    raw_payload_json: dict[str, object] = Field(default_factory=dict)
    normalized_payload_json: dict[str, object] = Field(default_factory=dict)
    answers: list[TypeformAnswerOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockages: list[str] = Field(default_factory=list)
    resolution: dict[str, object] = Field(default_factory=dict)
    client_candidates: list[TypeformMatchCandidateOut] = Field(default_factory=list)
    session_recommendations: list[TypeformSessionRecommendationOut] = Field(default_factory=list)
    preview_quote: TypeformQuotePreviewOut | None = None
    related_quote_id: UUID | None = None
    form_config: TypeformFormConfigOut | None = None
    referral: dict[str, object] | None = None


class TypeformIntakeResolutionRequest(BaseModel):
    resolution: dict[str, object] = Field(default_factory=dict)


class TypeformIntakeNormalizedPatchRequest(BaseModel):
    normalized_payload_json: dict[str, object | None] = Field(default_factory=dict)


class TypeformIntakeAdminStateRequest(BaseModel):
    ignored: bool = False


class TypeformIntakeReferralRequest(BaseModel):
    referrer_user_id: UUID


class TypeformWebhookOut(BaseModel):
    intake_id: UUID
    intake_status: str
    source_response_id: str


class TypeformDraftQuoteResultOut(BaseModel):
    intake_id: UUID
    quote_id: UUID
    intake_status: str


class TypeformDemoSeedOut(BaseModel):
    created_form_configs: int
    created_intakes: int
    created_core_records: list[str] = Field(default_factory=list)
    intake_ids: list[UUID] = Field(default_factory=list)
