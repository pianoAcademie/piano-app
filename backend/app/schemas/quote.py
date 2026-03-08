from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProspectOut(BaseModel):
    id: UUID
    linked_client_id: UUID | None = None
    parent_prospect_id: UUID | None = None
    status: str
    first_name: str | None = None
    last_name: str | None = None
    email: str
    phone: str | None = None
    source: str | None = None
    notes: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProspectCreateRequest(BaseModel):
    linked_client_id: UUID | None = None
    parent_prospect_id: UUID | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)


class ProspectUpdateRequest(BaseModel):
    linked_client_id: UUID | None = None
    parent_prospect_id: UUID | None = None
    status: str | None = Field(default=None, max_length=32)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    meta: dict[str, object] | None = None


class QuoteLineIn(BaseModel):
    line_category: Literal["service", "product"]
    line_type: Literal["item", "discount", "surcharge"] = "item"
    master_item_type: Literal["activity", "product", "kit", "option", "discount_rule", "surcharge_rule"] | None = None
    master_item_id: UUID | None = None
    activity_id: UUID | None = None
    product_id: UUID | None = None
    kit_id: UUID | None = None
    code: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    pricing_unit: Literal["hour", "session", "item", "fixed"] = "item"
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0.01"))
    vat_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    unit_price_ttc: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    sort_order: int = Field(default=0, ge=0)
    meta: dict[str, object] = Field(default_factory=dict)


class QuoteLineOut(BaseModel):
    id: UUID
    quote_id: UUID
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
    duration_minutes: int | None = None
    pricing_unit: str
    quantity: Decimal
    vat_rate: Decimal
    unit_price_ht: Decimal
    unit_vat_amount: Decimal
    unit_price_ttc: Decimal
    amount_ht: Decimal
    amount_vat: Decimal
    amount_ttc: Decimal
    sort_order: int
    meta: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class QuoteOut(BaseModel):
    id: UUID
    quote_number: str
    context_type: str
    quote_type: str
    quote_type_id: UUID | None = None
    pricing_catalog_id: UUID | None = None
    prospect_id: UUID | None = None
    client_id: UUID | None = None
    location_id: UUID | None = None
    payment_plan_id: UUID | None = None
    quote_template_id: UUID | None = None
    quote_template_version_id: UUID | None = None
    terms_template_id: UUID | None = None
    terms_template_version_id: UUID | None = None
    status: str
    public_token: str | None = None
    pdf_token: str | None = None
    version_number: int
    parent_quote_id: UUID | None = None
    currency: str
    total_ttc: Decimal
    expiry_days: int
    expires_at: datetime | None = None
    sent_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    expired_at: datetime | None = None
    cancelled_at: datetime | None = None
    school_year_label: str | None = None
    language: str | None = None
    vat_rate: Decimal | None = None
    estimated_solfege_level: str | None = None
    solfege_duration_minutes: int | None = None
    selected_solfege_slot: dict[str, object] = Field(default_factory=dict)
    calendar_snapshot: dict[str, object] = Field(default_factory=dict)
    payment_terms_snapshot: dict[str, object] = Field(default_factory=dict)
    cgv_snapshot: dict[str, object] = Field(default_factory=dict)
    price_snapshot: dict[str, object] = Field(default_factory=dict)
    meta: dict[str, object] = Field(default_factory=dict)
    document_status: str = "stale"
    document_snapshot_id: UUID | None = None
    document_hash: str | None = None
    document_generated_at: datetime | None = None
    reminder_sent_at: datetime | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class QuoteDetailOut(BaseModel):
    quote: QuoteOut
    lines: list[QuoteLineOut] = Field(default_factory=list)


class QuoteCreateRequest(BaseModel):
    context_type: Literal["acquisition", "active_client"]
    quote_type: str = "forfait"
    quote_type_id: UUID | None = None
    pricing_catalog_id: UUID | None = None
    prospect_id: UUID | None = None
    client_id: UUID | None = None
    location_id: UUID | None = None
    payment_plan_id: UUID | None = None
    quote_template_uuid: UUID | None = None
    quote_template_version_id: UUID | None = None
    terms_template_id: UUID | None = None
    terms_template_version_id: UUID | None = None
    school_year_label: str | None = Field(default=None, max_length=40)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    language: str | None = Field(default=None, max_length=8)
    vat_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    expiry_days: int = Field(default=10, ge=1, le=120)
    quote_date: date | None = None
    estimated_solfege_level: str | None = Field(default=None, max_length=10)
    selected_solfege_slot: dict[str, object] = Field(default_factory=dict)
    calendar_snapshot: dict[str, object] = Field(default_factory=dict)
    payment_terms_snapshot: dict[str, object] = Field(default_factory=dict)
    cgv_snapshot: dict[str, object] = Field(default_factory=dict)
    price_snapshot: dict[str, object] = Field(default_factory=dict)
    meta: dict[str, object] = Field(default_factory=dict)
    lines: list[QuoteLineIn] = Field(default_factory=list)


class QuoteUpdateRequest(BaseModel):
    quote_type: str | None = Field(default=None, max_length=30)
    quote_type_id: UUID | None = None
    pricing_catalog_id: UUID | None = None
    location_id: UUID | None = None
    payment_plan_id: UUID | None = None
    quote_template_uuid: UUID | None = None
    quote_template_version_id: UUID | None = None
    terms_template_id: UUID | None = None
    terms_template_version_id: UUID | None = None
    school_year_label: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    language: str | None = Field(default=None, max_length=8)
    vat_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    expiry_days: int | None = Field(default=None, ge=1, le=120)
    estimated_solfege_level: str | None = Field(default=None, max_length=10)
    selected_solfege_slot: dict[str, object] | None = None
    calendar_snapshot: dict[str, object] | None = None
    payment_terms_snapshot: dict[str, object] | None = None
    cgv_snapshot: dict[str, object] | None = None
    price_snapshot: dict[str, object] | None = None
    meta: dict[str, object] | None = None
    lines: list[QuoteLineIn] | None = None


class QuoteSendRequest(BaseModel):
    recipient_email: str | None = Field(default=None, min_length=3, max_length=255)


class QuoteCalendarPreviewRequest(BaseModel):
    start_date: date
    end_date: date
    weekdays: list[int] = Field(default_factory=list)
    start_time: str = Field(min_length=4, max_length=5)
    end_time: str = Field(min_length=4, max_length=5)
    activity_id: UUID | None = None
    location_id: UUID | None = None
    modality: str | None = Field(default=None, max_length=20)
    holiday_dates: list[date] = Field(default_factory=list)
    closure_dates: list[date] = Field(default_factory=list)


class QuotePaymentSchedulePreviewRequest(BaseModel):
    payment_method_code: str = Field(min_length=2, max_length=40)
    schedule_type: str | None = Field(default=None, max_length=40)
    schedule_rules: dict[str, object] = Field(default_factory=dict)
    payment_method_label: str | None = Field(default=None, max_length=180)
    total_ttc: Decimal = Field(ge=Decimal("0"))
    registration_date: date
    currency: str = Field(default="EUR", min_length=3, max_length=3)


class QuotePublicOut(BaseModel):
    quote: QuoteOut
    lines: list[QuoteLineOut] = Field(default_factory=list)
    payment_schedule: list[dict[str, object]] = Field(default_factory=list)


class QuoteChangeRequestIn(BaseModel):
    message: str = Field(min_length=3, max_length=4000)


class QuoteFollowupOut(BaseModel):
    id: UUID
    quote_id: UUID
    target_client_id: UUID | None = None
    status: str
    payment_method_status: str
    solfege_slot_status: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class QuoteFollowupUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    payment_method_status: str | None = Field(default=None, max_length=30)
    solfege_slot_status: str | None = Field(default=None, max_length=30)
    payload: dict[str, object] | None = None


class QuoteFollowupSlotRequest(BaseModel):
    slot: dict[str, object] = Field(default_factory=dict)


class QuoteFollowupPaymentMethodRequest(BaseModel):
    payment_method_code: str = Field(min_length=2, max_length=40)
    payment_plan_id: UUID | None = None


class QuoteTypeOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    default_expiry_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QuoteTypeUpsertRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    default_expiry_days: int = Field(default=10, ge=1, le=120)
    is_active: bool = True


class PricingCatalogOut(BaseModel):
    id: UUID
    name: str
    school_year_label: str | None = None
    effective_from: datetime
    effective_to: datetime | None = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PricingCatalogUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    school_year_label: str | None = Field(default=None, max_length=40)
    effective_from: datetime
    effective_to: datetime | None = None
    is_default: bool = False
    is_active: bool = True


class PricingActivityPriceOut(BaseModel):
    id: UUID
    catalog_id: UUID
    activity_id: UUID
    location_id: UUID | None = None
    student_category: str | None = None
    pricing_unit: str
    unit_price_ttc: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PricingActivityPriceUpsertRequest(BaseModel):
    catalog_id: UUID
    activity_id: UUID
    location_id: UUID | None = None
    student_category: str | None = Field(default=None, max_length=80)
    pricing_unit: Literal["hourly", "per_session", "fixed"] = "per_session"
    unit_price_ttc: Decimal = Field(ge=Decimal("0"))
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    is_active: bool = True


class PricingProductPriceOut(BaseModel):
    id: UUID
    catalog_id: UUID
    product_id: UUID
    unit_price_ttc: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PricingProductPriceUpsertRequest(BaseModel):
    catalog_id: UUID
    product_id: UUID
    unit_price_ttc: Decimal = Field(ge=Decimal("0"))
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    is_active: bool = True


class PricingKitPriceOut(BaseModel):
    id: UUID
    catalog_id: UUID
    kit_id: UUID
    unit_price_ttc: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PricingKitPriceUpsertRequest(BaseModel):
    catalog_id: UUID
    kit_id: UUID
    unit_price_ttc: Decimal = Field(ge=Decimal("0"))
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    is_active: bool = True


class SolfegeLevelRuleOut(BaseModel):
    id: UUID
    level_code: str
    duration_minutes: int
    allowed_weekdays: list[int] = Field(default_factory=list)
    allowed_time_slots: list[dict[str, object]] = Field(default_factory=list)
    location_id: UUID | None = None
    modality: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SolfegeLevelRuleUpsertRequest(BaseModel):
    level_code: str = Field(min_length=1, max_length=10)
    duration_minutes: int = Field(ge=10, le=180)
    allowed_weekdays: list[int] = Field(default_factory=list)
    allowed_time_slots: list[dict[str, object]] = Field(default_factory=list)
    location_id: UUID | None = None
    modality: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class QuoteSchoolCalendarPeriod(BaseModel):
    start_date: date
    end_date: date
    label: str | None = Field(default=None, max_length=120)


class QuoteSchoolCalendarOut(BaseModel):
    id: UUID
    name: str
    school_year_label: str
    location_id: UUID
    vacation_periods: list[QuoteSchoolCalendarPeriod] = Field(default_factory=list)
    holiday_dates: list[date] = Field(default_factory=list)
    closure_dates: list[date] = Field(default_factory=list)
    is_active: bool
    deployment_status: str = "not_deployed"
    deployment_last_at: datetime | None = None
    deployment_last_sync_at: datetime | None = None
    deployment_source_hash: str | None = None
    deployment_generated_count: int = 0
    deployment_generated_active_count: int = 0
    created_at: datetime
    updated_at: datetime


class QuoteSchoolCalendarUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    school_year_label: str = Field(min_length=1, max_length=40)
    location_id: UUID | None = None
    location_ids: list[UUID] = Field(default_factory=list)
    vacation_periods: list[QuoteSchoolCalendarPeriod] = Field(default_factory=list)
    holiday_dates: list[date] = Field(default_factory=list)
    closure_dates: list[date] = Field(default_factory=list)
    is_active: bool = True
    apply_to_management_planning: bool = False


class QuoteSchoolCalendarResolveOut(BaseModel):
    calendar: QuoteSchoolCalendarOut | None = None
    holiday_dates: list[date] = Field(default_factory=list)
    closure_dates: list[date] = Field(default_factory=list)


class QuoteSchoolCalendarDeploymentSummaryOut(BaseModel):
    total_target_days: int = 0
    vacation_days: int = 0
    holiday_days: int = 0
    closure_days: int = 0


class QuoteSchoolCalendarDeploymentPreviewOut(BaseModel):
    calendar_id: UUID
    location_id: UUID
    deployment_status: str
    source_hash: str
    existing_generated_active_count: int = 0
    summary: QuoteSchoolCalendarDeploymentSummaryOut = Field(default_factory=QuoteSchoolCalendarDeploymentSummaryOut)
    would_create: int = 0
    would_keep: int = 0
    would_reactivate: int = 0
    would_cancel: int = 0
    sample_dates: list[date] = Field(default_factory=list)


class QuoteSchoolCalendarDeploymentActionOut(BaseModel):
    calendar_id: UUID
    deployment_status: str
    source_hash: str | None = None
    created_count: int = 0
    updated_count: int = 0
    reactivated_count: int = 0
    cancelled_count: int = 0
    deleted_count: int = 0
    active_generated_count: int = 0
    message: str


class QuoteSchoolCalendarGeneratedSlotOut(BaseModel):
    session_id: UUID
    location_id: UUID
    date: date
    reason_types: list[str] = Field(default_factory=list)
    status: str
    title: str
    start_at: datetime
    end_at: datetime


class PaymentPlanOut(BaseModel):
    id: UUID
    code: str
    name: str
    payment_method: str
    schedule_type: str
    schedule_rules: dict[str, object] = Field(default_factory=dict)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaymentPlanUpsertRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=180)
    payment_method: str = Field(min_length=2, max_length=40)
    schedule_type: str = Field(min_length=2, max_length=40)
    schedule_rules: dict[str, object] = Field(default_factory=dict)
    is_active: bool = True


class QuoteTemplateVariableOut(BaseModel):
    key: str
    label: str
    description: str
    example: str


class QuoteTemplateVersionOut(BaseModel):
    id: UUID
    quote_template_id: UUID
    version_number: int
    content_snapshot: dict[str, object] = Field(default_factory=dict)
    is_active_version: bool
    published_at: datetime | None = None
    changelog: str | None = None
    created_at: datetime
    updated_at: datetime


class QuoteTemplateV2Out(BaseModel):
    id: UUID
    code: str
    name: str
    template_type: str
    target: str | None = None
    language: str
    description: str | None = None
    is_active: bool
    is_default: bool
    status: str
    current_version_id: UUID | None = None
    current_version_number: int | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class QuoteTemplateV2UpsertRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    template_type: str = Field(default="quote_body", min_length=2, max_length=40)
    target: str | None = Field(default=None, max_length=40)
    language: str = Field(default="fr", min_length=2, max_length=8)
    description: str | None = None
    is_active: bool = True
    is_default: bool = False
    status: str = Field(default="draft", max_length=20)
    subject_template: str = Field(min_length=1, max_length=255)
    body_template: str = Field(min_length=1, max_length=20000)
    changelog: str | None = None
    publish_now: bool = True


class QuoteTemplateVersionPublishRequest(BaseModel):
    subject_template: str = Field(min_length=1, max_length=255)
    body_template: str = Field(min_length=1, max_length=20000)
    changelog: str | None = None
    activate: bool = True


class TermsTemplateVersionOut(BaseModel):
    id: UUID
    terms_template_id: UUID
    version_number: int
    content_snapshot: dict[str, object] = Field(default_factory=dict)
    is_active_version: bool
    published_at: datetime | None = None
    changelog: str | None = None
    created_at: datetime
    updated_at: datetime


class TermsTemplateOut(BaseModel):
    id: UUID
    code: str
    name: str
    terms_type: str
    target: str | None = None
    language: str
    description: str | None = None
    is_active: bool
    status: str
    current_version_id: UUID | None = None
    current_version_number: int | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class TermsTemplateUpsertRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    terms_type: str = Field(default="cgv", min_length=2, max_length=40)
    target: str | None = Field(default=None, max_length=40)
    language: str = Field(default="fr", min_length=2, max_length=8)
    description: str | None = None
    is_active: bool = True
    status: str = Field(default="draft", max_length=20)
    version_label: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1)
    changelog: str | None = None
    publish_now: bool = True


class TermsTemplateVersionPublishRequest(BaseModel):
    version_label: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1)
    changelog: str | None = None
    activate: bool = True


class QuoteDocumentBindingOut(BaseModel):
    id: UUID
    prospect_type: str | None = None
    context_type: str | None = None
    activity_family: str | None = None
    activity_id: UUID | None = None
    quote_type_id: UUID | None = None
    language: str | None = None
    currency: str | None = None
    quote_template_id: UUID | None = None
    quote_template_version_id: UUID | None = None
    terms_template_id: UUID | None = None
    terms_template_version_id: UUID | None = None
    priority: int
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class QuoteDocumentBindingUpsertRequest(BaseModel):
    prospect_type: str | None = Field(default=None, max_length=20)
    context_type: str | None = Field(default=None, max_length=30)
    activity_family: str | None = Field(default=None, max_length=80)
    activity_id: UUID | None = None
    quote_type_id: UUID | None = None
    language: str | None = Field(default=None, max_length=8)
    currency: str | None = Field(default=None, max_length=3)
    quote_template_id: UUID | None = None
    quote_template_version_id: UUID | None = None
    terms_template_id: UUID | None = None
    terms_template_version_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=9999)
    is_active: bool = True
    notes: str | None = None
