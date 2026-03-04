from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.catalog import DeliveryMode, SessionStatus
from app.models.ops import ReminderStatus
from app.models.payout import PayoutStatus, SalaryPaymentMethod
from app.models.plan import PlanCreditGrantsRelation, PlanKind, PlanPriceTaxMode, PlanRestrictionPeriod, SubscriptionStatus
from app.models.professor_contract import ProfessorContractLineMode
from app.models.user import ClientKind, ClientStatus, UserRole


class AppSettingOut(BaseModel):
    key: str
    value: str
    updated_at: datetime


class AppSettingUpdateRequest(BaseModel):
    value: str = Field(min_length=1)


class AdminConfigAccountOut(BaseModel):
    contact_first_name: str
    contact_last_name: str
    contact_email: str
    contact_phone: str
    company_name: str
    club_name: str
    siret: str
    vat_number: str
    vat_default_rate: str
    website: str
    address_line: str
    postal_code: str
    city: str
    country: str
    allowed_currencies: list[str] = Field(default_factory=list)
    default_currency: str
    legal_terms: str
    logo_data_url: str = ""


class AdminConfigAccountUpdateRequest(BaseModel):
    contact_first_name: str = Field(default="", max_length=100)
    contact_last_name: str = Field(default="", max_length=100)
    contact_email: str = Field(default="", max_length=255)
    contact_phone: str = Field(default="", max_length=40)
    company_name: str = Field(default="", max_length=255)
    club_name: str = Field(default="", max_length=255)
    siret: str = Field(default="", max_length=30)
    vat_number: str = Field(default="", max_length=50)
    vat_default_rate: str = Field(default="", max_length=20)
    website: str = Field(default="", max_length=255)
    address_line: str = Field(default="", max_length=255)
    postal_code: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    allowed_currencies: list[str] = Field(default_factory=list)
    default_currency: str = Field(default="EUR", min_length=3, max_length=3)
    legal_terms: str = Field(default="")
    logo_data_url: str = Field(default="", max_length=2000000)


class AdminSubscriptionSettingsOut(BaseModel):
    direct_debit_day: int | None
    allow_card_subscriptions: bool
    add_contract_signature: bool
    close_expired_subscriptions: bool
    allow_promotional_start_period: bool
    allow_prorata_card: bool
    allow_prorata_sepa: bool
    online_resiliation_enabled: bool


class AdminSubscriptionSettingsUpdateRequest(BaseModel):
    direct_debit_day: int | None = Field(default=None, ge=1, le=28)
    allow_card_subscriptions: bool
    add_contract_signature: bool
    close_expired_subscriptions: bool
    allow_promotional_start_period: bool
    allow_prorata_card: bool
    allow_prorata_sepa: bool
    online_resiliation_enabled: bool


class AdminPaymentMethodOptionOut(BaseModel):
    code: str
    label: str
    enabled: bool
    default_legal_entity_id: UUID | None = None
    default_legal_entity_name: str | None = None


class AdminPaymentMethodsOut(BaseModel):
    methods: list[AdminPaymentMethodOptionOut]


class AdminPaymentMethodsUpdateRequest(BaseModel):
    enabled_codes: list[str] = Field(default_factory=list)
    legal_entity_by_method_code: dict[str, UUID | None] | None = None


class AdminProductCategoriesOut(BaseModel):
    categories: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AdminProductCategoriesUpdateRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)


class AdminPaymentProviderOut(BaseModel):
    provider: str
    mode: str
    subscriptions_supported: bool
    subscriptions_managed_by_psp: bool
    recommendation: str
    payplug_test_secret_configured: bool
    payplug_live_secret_configured: bool
    mollie_test_api_key_configured: bool
    mollie_live_api_key_configured: bool
    stripe_test_secret_configured: bool
    stripe_live_secret_configured: bool
    payplug_test_secret_masked: str
    payplug_live_secret_masked: str
    mollie_test_api_key_masked: str
    mollie_live_api_key_masked: str
    stripe_test_secret_masked: str
    stripe_live_secret_masked: str
    webhook_secret_masked: str


class AdminPaymentProviderUpdateRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=30)
    mode: str = Field(min_length=1, max_length=10)
    payplug_test_secret: str | None = Field(default=None, max_length=255)
    payplug_live_secret: str | None = Field(default=None, max_length=255)
    mollie_test_api_key: str | None = Field(default=None, max_length=255)
    mollie_live_api_key: str | None = Field(default=None, max_length=255)
    stripe_test_secret: str | None = Field(default=None, max_length=255)
    stripe_live_secret: str | None = Field(default=None, max_length=255)
    webhook_secret: str | None = Field(default=None, max_length=255)


class AdminMessagingSettingsOut(BaseModel):
    studio_email: str
    studio_sender_name: str
    teacher_sender_name: str
    use_studio_name_as_default_sender: bool
    use_studio_email_for_reminders: bool
    use_studio_email_for_lesson_notes: bool
    send_birthday_emails: bool
    updated_at: datetime | None = None


class AdminMessagingSettingsUpdateRequest(BaseModel):
    studio_email: str = Field(default="", max_length=255)
    studio_sender_name: str = Field(default="", max_length=120)
    teacher_sender_name: str = Field(default="", max_length=120)
    use_studio_name_as_default_sender: bool = True
    use_studio_email_for_reminders: bool = True
    use_studio_email_for_lesson_notes: bool = True
    send_birthday_emails: bool = False


class AdminMessagingChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    GROUP_NOTE = "GROUP_NOTE"


class AdminMessagingTemplateKind(str, enum.Enum):
    PREDEFINED = "PREDEFINED"
    CUSTOM = "CUSTOM"


AdminMessageBodyFormat = Literal["TEXT", "HTML"]


class AdminMessagingTemplateOut(BaseModel):
    id: str
    code: str | None = None
    name: str
    channel: AdminMessagingChannel
    kind: AdminMessagingTemplateKind
    subject: str | None = None
    body: str
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True
    description: str | None = None
    variables_hint: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminMessagingPredefinedTemplateUpdateRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=12000)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True


class AdminMessagingCustomTemplateCreateRequest(BaseModel):
    channel: AdminMessagingChannel
    name: str = Field(min_length=1, max_length=180)
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=12000)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True


class AdminMessagingCustomTemplateUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=12000)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True


class AdminInvoiceTemplateOut(BaseModel):
    body: str
    variables_hint: str
    updated_at: datetime | None = None


class AdminInvoiceTemplateUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class AdminTeacherInvoiceTemplateOut(BaseModel):
    key: str
    html_template: str
    version: int
    updated_at: datetime | None = None
    variables: list[str] = Field(default_factory=list)


class AdminTeacherInvoiceTemplateUpdateRequest(BaseModel):
    html_template: str = Field(min_length=1, max_length=100000)


class AdminTeacherInvoiceTemplatePreviewRequest(BaseModel):
    html_template: str | None = Field(default=None, min_length=1, max_length=100000)


class AdminInvoiceNumberingOut(BaseModel):
    format_pattern: str
    next_number: int
    preview: str
    updated_at: datetime | None = None


class AdminInvoiceNumberingUpdateRequest(BaseModel):
    format_pattern: str = Field(min_length=1, max_length=120)
    next_number: int = Field(ge=1, le=999_999_999)


class AdminProfessorDefaultGridRuleInput(BaseModel):
    min_students: int = Field(ge=0)
    max_students: int | None = Field(default=None, ge=0)
    hourly_rate: Decimal = Field(ge=0)


class AdminProfessorDefaultGridLineInput(BaseModel):
    course_type_id: UUID
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    rules: list[AdminProfessorDefaultGridRuleInput] = Field(default_factory=list)


class AdminProfessorDefaultGridUpdateRequest(BaseModel):
    lines: list[AdminProfessorDefaultGridLineInput] = Field(default_factory=list)


class AdminProfessorDefaultGridRuleOut(BaseModel):
    min_students: int
    max_students: int | None
    hourly_rate: Decimal
    display_order: int


class AdminProfessorDefaultGridLineOut(BaseModel):
    course_type_id: UUID
    course_type_name: str
    mode: ProfessorContractLineMode
    reference_duration_minutes: int | None
    default_hourly_rate: Decimal | None
    display_order: int
    rules: list[AdminProfessorDefaultGridRuleOut] = Field(default_factory=list)


class AdminProfessorDefaultGridOut(BaseModel):
    lines: list[AdminProfessorDefaultGridLineOut] = Field(default_factory=list)
    updated_at: datetime | None


class AdminFormulaRestrictionIn(BaseModel):
    period: PlanRestrictionPeriod
    max_bookings: int = Field(ge=1, le=50)
    course_type_ids: list[UUID] = Field(default_factory=list)


class AdminFormulaRestrictionOut(BaseModel):
    id: str
    period: PlanRestrictionPeriod
    max_bookings: int
    course_type_ids: list[UUID] = Field(default_factory=list)
    course_type_names: list[str] = Field(default_factory=list)


class AdminFormulaCreditGrantIn(BaseModel):
    credit_type_id: UUID
    credits_count: int = Field(ge=1, le=100000)


class AdminFormulaCreditGrantOut(BaseModel):
    id: str
    credit_type_id: UUID
    credit_type_code: str | None = None
    credit_type_name: str | None = None
    credits_count: int


class AdminFormulaOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: PlanKind
    active: bool
    is_private: bool
    description: str | None
    credits_count: int | None
    pack_validity_months: int | None
    forfait_start_date: date | None
    forfait_end_date: date | None
    credit_grants: list[AdminFormulaCreditGrantOut] = Field(default_factory=list)
    credit_grants_relation: PlanCreditGrantsRelation
    monthly_price_value: Decimal | None
    signup_fee_value: Decimal | None
    price_tax_mode: PlanPriceTaxMode
    monthly_price_excl_vat: Decimal | None
    currency_code: str | None
    signup_fee_excl_vat: Decimal | None
    options: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    entitlement_course_type_ids: list[UUID] = Field(default_factory=list)
    entitlement_course_type_names: list[str] = Field(default_factory=list)
    restrictions: list[AdminFormulaRestrictionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminFormulaUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: PlanKind
    active: bool = True
    is_private: bool = False
    description: str | None = None
    credits_count: int | None = Field(default=None, ge=1)
    pack_validity_months: int | None = Field(default=None, ge=1, le=12)
    forfait_start_date: date | None = None
    forfait_end_date: date | None = None
    credit_grants: list[AdminFormulaCreditGrantIn] = Field(default_factory=list)
    credit_grants_relation: PlanCreditGrantsRelation = PlanCreditGrantsRelation.OR
    monthly_price_value: Decimal | None = Field(default=None, ge=0)
    signup_fee_value: Decimal | None = Field(default=None, ge=0)
    price_tax_mode: PlanPriceTaxMode = PlanPriceTaxMode.HT
    monthly_price_excl_vat: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    signup_fee_excl_vat: Decimal | None = Field(default=None, ge=0)
    options: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    entitlement_course_type_ids: list[UUID] = Field(default_factory=list)
    restrictions: list[AdminFormulaRestrictionIn] = Field(default_factory=list)


class AdminFormulaUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: PlanKind | None = None
    active: bool | None = None
    is_private: bool | None = None
    description: str | None = None
    credits_count: int | None = Field(default=None, ge=1)
    pack_validity_months: int | None = Field(default=None, ge=1, le=12)
    forfait_start_date: date | None = None
    forfait_end_date: date | None = None
    credit_grants: list[AdminFormulaCreditGrantIn] | None = None
    credit_grants_relation: PlanCreditGrantsRelation | None = None
    monthly_price_value: Decimal | None = Field(default=None, ge=0)
    signup_fee_value: Decimal | None = Field(default=None, ge=0)
    price_tax_mode: PlanPriceTaxMode | None = None
    monthly_price_excl_vat: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    signup_fee_excl_vat: Decimal | None = Field(default=None, ge=0)
    options: list[str] | None = None
    payment_methods: list[str] | None = None
    entitlement_course_type_ids: list[UUID] | None = None
    restrictions: list[AdminFormulaRestrictionIn] | None = None


class AdminCreditTypeOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    active: bool
    activity_ids: list[UUID] = Field(default_factory=list)
    activity_names: list[str] = Field(default_factory=list)
    activity_count: int = 0


class AdminCreditTypeUpsertRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    active: bool = True


class AdminCreditTypeUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    active: bool | None = None


class AdminActivityOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    service_code: str
    seller_legal_entity_id: UUID | None
    seller_legal_entity_name: str | None
    payor_legal_entity_id: UUID | None
    payor_legal_entity_name: str | None
    credit_type_id: UUID | None
    credit_type_code: str | None
    credit_type_name: str | None
    duration_minutes: int
    color_hex: str
    mode: DeliveryMode
    default_capacity: int
    default_hourly_rate: Decimal | None
    default_course_rate_ttc: Decimal | None
    email_reminder_hours_before_start: int | None
    sms_reminder_hours_before_start: int | None
    min_booking_notice_hours_override: int | None
    cancellation_deadline_hours_override: int | None
    auto_cancel_if_booked_less_than_override: int | None
    auto_cancel_hours_before_start_override: int | None
    active: bool


class AdminActivityUpsertRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    service_code: str = Field(default="ACTIVITY", min_length=1, max_length=80)
    seller_legal_entity_id: UUID
    payor_legal_entity_id: UUID | None = None
    credit_type_id: UUID
    duration_minutes: int = Field(default=60, ge=5, le=600)
    color_hex: str = Field(default="#94C973", min_length=7, max_length=7)
    mode: DeliveryMode = DeliveryMode.ANY
    default_capacity: int = Field(default=8, ge=1, le=500)
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    default_course_rate_ttc: Decimal | None = Field(default=None, ge=0)
    email_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    sms_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    min_booking_notice_hours_override: int | None = Field(default=None, ge=0)
    cancellation_deadline_hours_override: int | None = Field(default=None, ge=0)
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=0)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    active: bool = True


class AdminActivityUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    service_code: str | None = Field(default=None, min_length=1, max_length=80)
    seller_legal_entity_id: UUID | None = None
    payor_legal_entity_id: UUID | None = None
    credit_type_id: UUID | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    color_hex: str | None = Field(default=None, min_length=7, max_length=7)
    mode: DeliveryMode | None = None
    default_capacity: int | None = Field(default=None, ge=1, le=500)
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    default_course_rate_ttc: Decimal | None = Field(default=None, ge=0)
    email_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    sms_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    min_booking_notice_hours_override: int | None = Field(default=None, ge=0)
    cancellation_deadline_hours_override: int | None = Field(default=None, ge=0)
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=0)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    active: bool | None = None


class AdminClientOut(BaseModel):
    id: UUID
    email: str
    role: UserRole
    client_kind: ClientKind
    first_name: str | None
    last_name: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    address_country: str
    phone: str | None
    mobile_phone_1: str | None
    mobile_phone_2: str | None
    home_phone: str | None
    birth_date: date | None
    important_info: str | None
    private_note: str | None
    residence_country: str
    preferred_currency: str
    timezone: str
    first_course_at: datetime | None = None
    portal_contact_visible: bool = True
    email_opt_in: bool = True
    sms_opt_in: bool = True
    lesson_reminder_email_opt_in: bool = True
    lesson_reminder_sms_opt_in: bool = False
    client_status: ClientStatus = ClientStatus.ACTIVE
    family_name: str | None = None
    group_ids: list[UUID] = Field(default_factory=list)
    group_names: list[str] = Field(default_factory=list)
    is_active: bool
    next_session_start_at_utc: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminLegalEntityOut(BaseModel):
    id: UUID
    name: str
    siren: str | None
    siret: str | None
    vat_number: str | None
    address_text: str | None
    accounting_email: str | None
    country_code: str
    invoice_prefix: str
    invoice_next_number: int
    default_payment_provider: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminLegalEntityCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    siren: str | None = Field(default=None, max_length=64)
    siret: str | None = Field(default=None, max_length=64)
    vat_number: str | None = Field(default=None, max_length=64)
    address_text: str | None = Field(default=None, max_length=2000)
    accounting_email: str | None = Field(default=None, max_length=320)
    country_code: str = Field(default="FR", min_length=2, max_length=2)
    invoice_prefix: str = Field(min_length=1, max_length=20)
    invoice_next_number: int = Field(default=1, ge=1)
    default_payment_provider: str = Field(default="PAYPLUG", min_length=1, max_length=30)
    is_active: bool = True


class AdminLegalEntityUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    siren: str | None = Field(default=None, max_length=64)
    siret: str | None = Field(default=None, max_length=64)
    vat_number: str | None = Field(default=None, max_length=64)
    address_text: str | None = Field(default=None, max_length=2000)
    accounting_email: str | None = Field(default=None, max_length=320)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    invoice_next_number: int | None = Field(default=None, ge=1)
    default_payment_provider: str | None = Field(default=None, min_length=1, max_length=30)
    is_active: bool | None = None


class AdminClientUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    client_kind: ClientKind | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    address_country: str | None = Field(default=None, min_length=2, max_length=2)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    mobile_phone_1: str | None = Field(default=None, min_length=3, max_length=30)
    mobile_phone_2: str | None = Field(default=None, min_length=3, max_length=30)
    home_phone: str | None = Field(default=None, min_length=3, max_length=30)
    birth_date: date | None = None
    important_info: str | None = Field(default=None, min_length=1, max_length=1000)
    private_note: str | None = Field(default=None, min_length=1, max_length=5000)
    residence_country: str | None = Field(default=None, min_length=2, max_length=2)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    portal_contact_visible: bool | None = None
    email_opt_in: bool | None = None
    sms_opt_in: bool | None = None
    lesson_reminder_email_opt_in: bool | None = None
    lesson_reminder_sms_opt_in: bool | None = None
    client_status: ClientStatus | None = None
    is_active: bool | None = None


class AdminClientCreateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    client_kind: ClientKind = ClientKind.ADULT
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    address_country: str = Field(default="FR", min_length=2, max_length=2)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    mobile_phone_1: str | None = Field(default=None, min_length=3, max_length=30)
    mobile_phone_2: str | None = Field(default=None, min_length=3, max_length=30)
    home_phone: str | None = Field(default=None, min_length=3, max_length=30)
    birth_date: date | None = None
    important_info: str | None = Field(default=None, min_length=1, max_length=1000)
    private_note: str | None = Field(default=None, min_length=1, max_length=5000)
    residence_country: str = Field(default="FR", min_length=2, max_length=2)
    preferred_currency: str = Field(default="EUR", min_length=3, max_length=3)
    timezone: str = Field(default="Europe/Paris", min_length=2, max_length=100)
    portal_contact_visible: bool = True
    email_opt_in: bool = True
    sms_opt_in: bool = True
    lesson_reminder_email_opt_in: bool = True
    lesson_reminder_sms_opt_in: bool = False
    client_status: ClientStatus | None = None
    is_active: bool = True


class AdminClientGroupsUpdateRequest(BaseModel):
    group_ids: list[UUID] = Field(default_factory=list)


class AdminClientGroupOut(BaseModel):
    id: UUID
    code: str
    name: str
    active: bool
    members_count: int = 0


class AdminClientGroupCreateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    active: bool = True


class AdminClientGroupUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class AdminClientBulkAction(str, enum.Enum):
    UPDATE_STATUS = "UPDATE_STATUS"
    ASSIGN_GROUP = "ASSIGN_GROUP"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"
    EMAIL_CLIENTS = "EMAIL_CLIENTS"
    EMAIL_PARENTS = "EMAIL_PARENTS"
    SMS_CLIENTS = "SMS_CLIENTS"
    SMS_PARENTS = "SMS_PARENTS"


class AdminClientSelectionScope(str, enum.Enum):
    PAGE = "PAGE"
    FILTERED = "FILTERED"


class AdminClientBulkRequest(BaseModel):
    client_ids: list[UUID] = Field(default_factory=list)
    selection_scope: AdminClientSelectionScope = AdminClientSelectionScope.PAGE
    action: AdminClientBulkAction
    target_status: ClientStatus | None = None
    group_id: UUID | None = None
    filter_search: str | None = Field(default=None, min_length=1, max_length=255)
    filter_status: ClientStatus | None = None
    filter_group_id: UUID | None = None
    filter_include_archived: bool = False
    filter_active_only: bool = False
    message_subject: str | None = Field(default=None, max_length=255)
    message_body: str | None = Field(default=None, max_length=12000)
    message_body_format: AdminMessageBodyFormat = "TEXT"


class AdminClientBulkOut(BaseModel):
    processed_count: int
    skipped_count: int = 0
    message: str


class AdminFamilyMemberOut(BaseModel):
    id: UUID
    email: str
    first_name: str | None
    last_name: str | None
    phone: str | None
    mobile_phone_1: str | None
    mobile_phone_2: str | None
    home_phone: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    address_country: str
    client_kind: ClientKind
    is_active: bool


class AdminClientPasswordEmailTemplateOut(BaseModel):
    subject: str
    body: str
    updated_at: datetime | None = None


class AdminClientPasswordEmailTemplateUpdateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=5000)


class AdminClientPasswordResetOut(BaseModel):
    client_id: UUID
    email: str
    message_id: str
    sent_at: datetime


class AdminClientPortalAccessOut(BaseModel):
    client_id: UUID
    access_token: str
    expires_in_seconds: int


class AdminClientFamilyLinkOut(BaseModel):
    id: UUID
    adult: AdminFamilyMemberOut
    child: AdminFamilyMemberOut
    relationship_label: str | None
    is_billing_recipient: bool
    created_at: datetime
    updated_at: datetime


class AdminClientFamilyOut(BaseModel):
    client_id: UUID
    client_kind: ClientKind
    links_as_adult: list[AdminClientFamilyLinkOut] = Field(default_factory=list)
    links_as_child: list[AdminClientFamilyLinkOut] = Field(default_factory=list)
    billing_recipient_adult_id: UUID | None = None


class AdminClientFamilyLinkCreateRequest(BaseModel):
    adult_client_id: UUID
    child_client_id: UUID
    relationship_label: str | None = Field(default=None, max_length=80)
    is_billing_recipient: bool = False


class AdminClientFamilyLinkUpdateRequest(BaseModel):
    relationship_label: str | None = Field(default=None, max_length=80)
    is_billing_recipient: bool | None = None


class AdminClientSubscriptionMiniOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: PlanKind


class AdminClientSubscriptionOut(BaseModel):
    id: UUID
    status: SubscriptionStatus
    started_at: datetime
    ends_at: datetime | None
    next_payment_at: datetime | None = None
    credits_initial: int | None
    credits_remaining: int | None
    auto_renew: bool
    billing_method_code: str | None = None
    payment_provider_subscription_ref: str | None = None
    payment_provider_customer_ref: str | None = None
    payment_provider_mandate_ref: str | None = None
    forfait_loyalty_discount_per_hour_ttc: Decimal | None = None
    forfait_family_discount_per_hour_ttc: Decimal | None = None
    forfait_short_commitment_supplement_per_hour_ttc: Decimal | None = None
    forfait_activity_pricing: list["AdminClientForfaitActivityPricingOut"] = Field(default_factory=list)
    last_payment_at: datetime | None = None
    last_payment_status: str | None = None
    suspension_starts_at: datetime | None = None
    suspension_ends_at: datetime | None = None
    suspension_duration_value: int | None = None
    suspension_duration_unit: str | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    plan: AdminClientSubscriptionMiniOut
    estimated_price_excl_vat: Decimal | None
    estimated_vat_rate: Decimal | None
    estimated_vat_amount: Decimal | None
    estimated_total_incl_vat: Decimal | None
    estimated_currency: str | None


class AdminClientSubscriptionSuspendRequest(BaseModel):
    suspension_starts_at: datetime
    duration_unit: str = Field(pattern="^(DAY|MONTH)$")
    duration_value: int = Field(ge=1, le=30)


class AdminClientSubscriptionCancelRequest(BaseModel):
    cancellation_requested_at: datetime | None = None
    immediate: bool = False
    confirm_immediate: bool = False


class AdminClientSubscriptionExpiryUpdateRequest(BaseModel):
    ends_at: datetime


class AdminClientSubscriptionBillingSetupRequest(BaseModel):
    billing_method_code: str | None = Field(default=None, max_length=40)
    payment_provider_subscription_ref: str | None = Field(default=None, max_length=120)
    payment_provider_customer_ref: str | None = Field(default=None, max_length=120)
    payment_provider_mandate_ref: str | None = Field(default=None, max_length=120)


class AdminClientSubscriptionPaymentEmailRequest(BaseModel):
    payment_method_code: str | None = Field(default=None, max_length=40)
    discounted_total_incl_vat: Decimal | None = Field(default=None, ge=0)


class AdminClientSubscriptionPaymentEmailOut(BaseModel):
    client_id: UUID
    subscription_id: UUID
    email: str
    message_id: str
    sent_at: datetime


class AdminClientPlanPurchaseRequest(BaseModel):
    payment_method_code: str | None = Field(default=None, max_length=40)
    start_date: date | None = None


class AdminClientForfaitActivityPricingIn(BaseModel):
    course_type_id: UUID
    loyalty_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    family_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    short_commitment_supplement_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    second_course_weekly_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)


class AdminClientForfaitActivityPricingOut(BaseModel):
    course_type_id: UUID
    course_type_name: str
    base_hourly_rate_ttc: Decimal | None = None
    loyalty_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    family_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    short_commitment_supplement_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    second_course_weekly_discount_per_hour_ttc: Decimal = Field(default=Decimal("0.00"), ge=0)
    effective_hourly_rate_ttc: Decimal | None = None


class AdminClientForfaitPricingUpdateRequest(BaseModel):
    activities: list[AdminClientForfaitActivityPricingIn] = Field(default_factory=list)


class AdminClientManualCreditOut(BaseModel):
    id: UUID | None
    credit_type_id: UUID
    credit_type_code: str | None
    credit_type_name: str | None
    credits_count: int
    updated_at: datetime | None


class AdminClientManualCreditUpdateRequest(BaseModel):
    credits_count: int = Field(ge=0, le=100000)


class AdminClientNoteOut(BaseModel):
    id: UUID
    user_id: UUID
    author_user_id: UUID | None
    author_display_name: str
    entry_type: str
    message: str
    created_at: datetime


class AdminClientNoteCreateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AdminRangeInvoiceCreateRequest(BaseModel):
    issued_date: date
    start_date: date
    end_date: date
    due_date: date
    no_due_date: bool = False
    include_pending: bool = True
    include_cancelled: bool = False
    layout: str = "DETAILED"
    generation_mode: Literal["MANUAL", "AUTO"] = "MANUAL"
    group_adjustments_by_type: bool = False
    include_discount_adjustments: bool = True
    include_supplement_adjustments: bool = True
    auto_cycle_start_date: date | None = None
    auto_period_scope: Literal["FUTURE", "PAST"] = "PAST"
    auto_frequency: Literal["WEEKLY", "MONTHLY"] = "MONTHLY"
    auto_repeat_every: int = Field(default=1, ge=1, le=6)
    auto_layout_style: Literal["NORMAL", "CONDENSED"] = "NORMAL"
    auto_include_previous_balance: bool = True
    auto_send_email: bool = False
    auto_footer_note: str | None = Field(default=None, max_length=2000)
    auto_exclude_pack_subscription_lines: bool = True
    invoice_number: str | None = Field(default=None, max_length=120)
    public_note: str | None = Field(default=None, max_length=2000)
    private_note: str | None = Field(default=None, max_length=2000)


class AdminRangeInvoiceReferenceOut(BaseModel):
    note_id: UUID
    invoice_number: str
    billing_entity: str | None = None
    seller_legal_entity_id: UUID | None = None
    split_part_index: int = 1
    split_part_count: int = 1


class AdminRangeInvoiceOut(BaseModel):
    note_id: UUID
    invoice_number: str
    issued_date: date
    due_date: date
    no_due_date: bool = False
    start_date: date
    end_date: date
    layout: Literal["DETAILED", "COMPILED"]
    generation_mode: Literal["MANUAL", "AUTO"] = "MANUAL"
    group_adjustments_by_type: bool = False
    include_discount_adjustments: bool = True
    include_supplement_adjustments: bool = True
    auto_cycle_start_date: date | None = None
    auto_period_scope: Literal["FUTURE", "PAST"] = "PAST"
    auto_frequency: Literal["WEEKLY", "MONTHLY"] = "MONTHLY"
    auto_repeat_every: int = Field(default=1, ge=1, le=6)
    auto_layout_style: Literal["NORMAL", "CONDENSED"] = "NORMAL"
    auto_include_previous_balance: bool = True
    auto_send_email: bool = False
    auto_footer_note: str | None = None
    auto_exclude_pack_subscription_lines: bool = True
    include_pending: bool
    include_cancelled: bool
    totals_by_currency: dict[str, str]
    invoice_status: Literal["ISSUED", "PAID", "CANCELLED"]
    emailed_at: datetime | None = None
    reminded_at: datetime | None = None
    public_note: str | None = None
    private_note: str | None = None
    related_invoices: list[AdminRangeInvoiceReferenceOut] = Field(default_factory=list)


class AdminRangeInvoiceStatusUpdateRequest(BaseModel):
    status: Literal["ISSUED", "PAID", "CANCELLED"]


class AdminRangeInvoiceEmailRequest(BaseModel):
    kind: Literal["INVOICE", "REMINDER"] = "INVOICE"
    to_emails: list[str] | None = None
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=20000)
    body_format: Literal["TEXT", "HTML"] = "TEXT"


class AdminRangeInvoiceEmailOut(BaseModel):
    note_id: UUID
    kind: Literal["INVOICE", "REMINDER"]
    sent_at: datetime
    message_id: str | None = None
    recipients: list[str] = Field(default_factory=list)


class AdminRangeInvoiceEmailPreviewOut(BaseModel):
    note_id: UUID
    kind: Literal["INVOICE", "REMINDER"]
    to_emails: list[str]
    subject: str
    body: str
    body_format: Literal["TEXT", "HTML"] = "TEXT"


class AdminClientBookingOut(BaseModel):
    id: UUID
    session_id: UUID
    session_title: str
    session_status: SessionStatus
    session_start_at_utc: datetime
    session_end_at_utc: datetime
    course_type_name: str
    location_name: str
    client_plan_subscription_id: UUID | None
    plan_name: str | None
    status: str
    booked_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    price_excl_vat_snapshot: Decimal
    vat_rate_snapshot: Decimal
    vat_amount_snapshot: Decimal
    total_incl_vat_snapshot: Decimal
    currency_snapshot: str


class AdminClientMessageOut(BaseModel):
    id: UUID
    booking_id: UUID | None = None
    session_id: UUID | None = None
    session_title: str | None = None
    channel: Literal["EMAIL", "SMS"] = "EMAIL"
    source: str | None = None
    recipient: str | None = None
    scheduled_for_utc: datetime
    sent_at: datetime | None
    status: str
    provider_message_id: str | None
    error_message: str | None
    subject_preview: str
    body_preview: str | None = None
    body_full: str | None = None
    body_format: Literal["TEXT", "HTML"] = "TEXT"
    can_forward: bool = False


class AdminClientMessageEmailRequest(BaseModel):
    to_emails: list[str] | None = None
    cc_emails: list[str] | None = None
    send_copy_to_self: bool = False
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20000)
    body_format: Literal["TEXT", "HTML"] = "HTML"
    source: str | None = Field(default=None, max_length=120)


class AdminClientMessageEmailOut(BaseModel):
    client_id: UUID
    sent_at: datetime
    to_recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)


class AdminClientPaymentOut(BaseModel):
    id: UUID
    source: str
    occurred_at: datetime
    label: str
    status: str
    amount_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
    currency: str
    reference: str | None
    seller_legal_entity_id: UUID | None = None
    billing_entity: str | None = None
    invoice_number: str | None = None
    invoice_status: str | None = None
    invoice_note_id: UUID | None = None
    refunded_at: datetime | None = None
    refund_reason: str | None = None
    payment_method_code: str | None = None
    payment_method_label: str | None = None
    manual_transaction_type: str | None = None
    student_user_id: UUID | None = None
    description: str | None = None
    category: str | None = None
    can_edit: bool = False
    can_cancel: bool = False
    locked_by_invoice_number: str | None = None


class AdminClientManualTransactionType(str, enum.Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    CHARGE = "CHARGE"
    DISCOUNT = "DISCOUNT"


class AdminClientManualTransactionCreateRequest(BaseModel):
    transaction_type: AdminClientManualTransactionType
    occurred_at: datetime | None = None
    label: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=120)
    student_id: UUID | None = None
    amount_incl_vat: Decimal = Field(gt=Decimal("0"))
    vat_rate: Decimal = Field(default=Decimal("20.000"), ge=Decimal("0"), le=Decimal("100"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_method_code: str | None = Field(default=None, max_length=40)
    legal_entity_id: UUID | None = None
    reconciled_invoice_note_ids: list[UUID] = Field(default_factory=list)
    mark_reconciled_invoices_paid: bool = False
    send_receipt_email: bool = False


class AdminClientManualTransactionUpdateRequest(BaseModel):
    occurred_at: datetime | None = None
    label: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=120)
    student_id: UUID | None = None
    amount_incl_vat: Decimal | None = Field(default=None, gt=Decimal("0"))
    vat_rate: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_method_code: str | None = Field(default=None, max_length=40)
    legal_entity_id: UUID | None = None


class AdminClientPaymentRefundRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class AdminClientPaymentRefundOut(BaseModel):
    client_id: UUID
    source: str
    payment_id: UUID
    refunded_at: datetime
    reason: str | None


class AdminProfessorOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    active: bool


class ProfessorPermissionOut(BaseModel):
    can_view_dashboard: bool
    can_view_clients: bool
    can_export_clients: bool
    can_create_clients: bool
    can_message_clients: bool
    can_view_client_reminders: bool
    can_create_subscriptions: bool
    can_close_subscriptions: bool
    can_edit_subscriptions: bool
    can_downgrade_subscriptions: bool
    can_cancel_subscriptions: bool
    can_edit_payments: bool
    can_refund_payments: bool
    can_cancel_payments: bool
    can_manage_mobile_news: bool
    can_access_cash_menu: bool
    can_view_planning: bool
    can_view_all_school_sessions: bool
    can_edit_planning: bool
    can_force_booking: bool
    can_view_admin_dashboard: bool
    can_view_admin_reservations: bool
    can_access_collaborators: bool
    can_configure_app: bool
    can_list_payments: bool
    can_manage_events: bool
    can_view_sportigo_info: bool
    can_take_attendance: bool
    can_record_payments_with_attendance: bool
    can_edit_own_sessions: bool
    can_view_pay_details: bool
    can_manage_mileage_log: bool
    can_view_other_teachers_contacts: bool
    can_manage_other_teachers_students_and_sessions: bool
    can_view_other_teachers_sessions: bool
    can_view_student_parent_addresses_phones: bool
    can_view_student_parent_emails: bool
    can_view_student_attachments: bool
    can_manage_invoices_and_accounts: bool
    can_manage_expenses_and_other_income: bool
    can_manage_shared_online_resources: bool
    can_manage_website_and_news: bool
    can_create_and_view_reports: bool


class ProfessorPermissionUpdateRequest(BaseModel):
    can_view_dashboard: bool = False
    can_view_clients: bool = False
    can_export_clients: bool = False
    can_create_clients: bool = False
    can_message_clients: bool = False
    can_view_client_reminders: bool = False
    can_create_subscriptions: bool = False
    can_close_subscriptions: bool = False
    can_edit_subscriptions: bool = False
    can_downgrade_subscriptions: bool = False
    can_cancel_subscriptions: bool = False
    can_edit_payments: bool = False
    can_refund_payments: bool = False
    can_cancel_payments: bool = False
    can_manage_mobile_news: bool = False
    can_access_cash_menu: bool = False
    can_view_planning: bool = True
    can_view_all_school_sessions: bool = False
    can_edit_planning: bool = False
    can_force_booking: bool = False
    can_view_admin_dashboard: bool = False
    can_view_admin_reservations: bool = False
    can_access_collaborators: bool = False
    can_configure_app: bool = False
    can_list_payments: bool = False
    can_manage_events: bool = False
    can_view_sportigo_info: bool = False
    can_take_attendance: bool = True
    can_record_payments_with_attendance: bool = False
    can_edit_own_sessions: bool = False
    can_view_pay_details: bool = False
    can_manage_mileage_log: bool = False
    can_view_other_teachers_contacts: bool = False
    can_manage_other_teachers_students_and_sessions: bool = False
    can_view_other_teachers_sessions: bool = False
    can_view_student_parent_addresses_phones: bool = False
    can_view_student_parent_emails: bool = False
    can_view_student_attachments: bool = False
    can_manage_invoices_and_accounts: bool = False
    can_manage_expenses_and_other_income: bool = False
    can_manage_shared_online_resources: bool = False
    can_manage_website_and_news: bool = False
    can_create_and_view_reports: bool = False
    is_admin: bool | None = None


class AdminProfessorContractOut(BaseModel):
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class AdminProfessorContractDeleteOut(BaseModel):
    deleted: bool


class AdminProfessorDetailOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    phone: str | None
    siret: str | None
    iban: str | None
    address_line: str | None
    teacher_invoice_counter: int
    teacher_is_vat_applicable: bool
    teacher_vat_rate: Decimal | None
    teacher_siret: str | None
    teacher_iban: str | None
    teacher_company_name: str | None
    teacher_company_address: str | None
    zoom_link: str | None
    spoken_languages: list[str]
    payout_currency: str
    payout_balance_amount: Decimal = Decimal("0.00")
    payout_balance_currency: str | None = None
    payout_balance_as_of: date | None = None
    role: UserRole
    is_coach: bool
    active: bool
    user_is_active: bool
    daily_schedule_email_enabled: bool
    daily_schedule_email_time: str
    daily_schedule_skip_if_no_course: bool
    contract: AdminProfessorContractOut | None = None
    permissions: ProfessorPermissionOut
    created_at: datetime
    updated_at: datetime
    last_activation_email_sent_at: datetime | None


class AdminProfessorCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    siret: str | None = Field(default=None, max_length=30)
    iban: str | None = Field(default=None, max_length=34)
    address_line: str | None = Field(default=None, max_length=255)
    teacher_invoice_counter: int = Field(default=1, ge=1)
    teacher_is_vat_applicable: bool = False
    teacher_vat_rate: Decimal | None = Field(default=None, ge=0, le=99.99)
    teacher_siret: str | None = Field(default=None, max_length=64)
    teacher_iban: str | None = Field(default=None, max_length=64)
    teacher_company_name: str | None = Field(default=None, max_length=255)
    teacher_company_address: str | None = Field(default=None, max_length=2000)
    zoom_link: str | None = Field(default=None, max_length=500)
    spoken_languages: list[str] = Field(default_factory=list)
    payout_currency: str = Field(default="EUR", min_length=3, max_length=3)
    is_coach: bool = True
    is_admin: bool = False
    daily_schedule_email_enabled: bool = False
    daily_schedule_email_time: str = Field(default="07:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    daily_schedule_skip_if_no_course: bool = True
    permissions: ProfessorPermissionUpdateRequest | None = None


class AdminProfessorUpdateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=3, max_length=30)
    siret: str | None = Field(default=None, max_length=30)
    iban: str | None = Field(default=None, max_length=34)
    address_line: str | None = Field(default=None, max_length=255)
    teacher_invoice_counter: int | None = Field(default=None, ge=1)
    teacher_is_vat_applicable: bool | None = None
    teacher_vat_rate: Decimal | None = Field(default=None, ge=0, le=99.99)
    teacher_siret: str | None = Field(default=None, max_length=64)
    teacher_iban: str | None = Field(default=None, max_length=64)
    teacher_company_name: str | None = Field(default=None, max_length=255)
    teacher_company_address: str | None = Field(default=None, max_length=2000)
    zoom_link: str | None = Field(default=None, max_length=500)
    spoken_languages: list[str] | None = None
    payout_currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_coach: bool | None = None
    is_admin: bool | None = None
    active: bool | None = None
    daily_schedule_email_enabled: bool | None = None
    daily_schedule_email_time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    daily_schedule_skip_if_no_course: bool | None = None


class AdminProfessorUpdateResult(BaseModel):
    professor: AdminProfessorDetailOut
    activation_email_sent: bool
    activation_email_message_id: str | None


class AdminCollaboratorSendPasswordOut(BaseModel):
    ok: bool
    message_id: str | None
    expires_at: datetime


class AdminProfessorRateOut(BaseModel):
    id: UUID
    course_type_id: UUID | None
    course_type_name: str
    currency_code: str
    hourly_rate: Decimal | None
    rules: list["AdminProfessorRateRuleOut"] = Field(default_factory=list)
    valid_from: date
    valid_to: date | None


class AdminProfessorRateRuleInput(BaseModel):
    min_students: int = Field(ge=0)
    max_students: int | None = Field(default=None, ge=0)
    hourly_rate: Decimal = Field(ge=0)


class AdminProfessorRateRuleOut(BaseModel):
    min_students: int
    max_students: int | None
    hourly_rate: Decimal


class AdminProfessorRateInput(BaseModel):
    course_type_id: UUID | None = None
    hourly_rate: Decimal | None = None
    rules: list[AdminProfessorRateRuleInput] = Field(default_factory=list)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AdminProfessorRatesUpdateRequest(BaseModel):
    rates: list[AdminProfessorRateInput] = Field(default_factory=list)
    effective_from: date | None = None


class AdminProfessorPayoutLedgerRowOut(BaseModel):
    session_id: UUID
    start_at_utc: datetime
    end_at_utc: datetime
    course_type_name: str
    location_name: str
    duration_hours: Decimal
    hourly_rate: Decimal | None
    amount: Decimal | None
    currency: str | None
    payout_status: PayoutStatus | None
    counted_in_due: bool
    cumulative_due: Decimal


class AdminProfessorPayoutLedgerOut(BaseModel):
    professor_id: UUID
    as_of_date: date
    currency: str
    total_due: Decimal
    rows: list[AdminProfessorPayoutLedgerRowOut] = Field(default_factory=list)


class AdminProfessorSalaryPaymentCreateRequest(BaseModel):
    reference_date: date
    payment_date: date
    invoice_number: str = Field(min_length=1, max_length=120)
    payment_method: SalaryPaymentMethod = SalaryPaymentMethod.BANK_TRANSFER
    amount_excl_vat: Decimal = Field(ge=Decimal("0"))
    amount_incl_vat: Decimal = Field(ge=Decimal("0"))


class AdminProfessorSalaryPaymentOut(BaseModel):
    id: UUID
    professor_id: UUID
    professor_first_name: str
    professor_last_name: str
    professor_email: str
    reference_date: date
    payment_date: date
    invoice_number: str
    payment_method: SalaryPaymentMethod
    amount_excl_vat: Decimal
    amount_incl_vat: Decimal
    currency_code: str
    settled_payout_count: int
    actor_user_id: UUID | None
    created_at: datetime


class AdminProfessorContractLocationOptionOut(BaseModel):
    code: str
    label: str


class AdminProfessorContractGridRuleInput(BaseModel):
    min_students: int = Field(ge=0)
    max_students: int | None = Field(default=None, ge=0)
    hourly_rate: Decimal = Field(ge=0)


class AdminProfessorContractGridRuleOut(BaseModel):
    id: UUID
    min_students: int
    max_students: int | None
    hourly_rate: Decimal
    display_order: int


class AdminProfessorContractGridLineInput(BaseModel):
    course_type_id: UUID
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    rules: list[AdminProfessorContractGridRuleInput] = Field(default_factory=list)


class AdminProfessorContractGridLineOut(BaseModel):
    id: UUID
    course_type_id: UUID | None
    course_type_name: str
    service_type: str
    mode: ProfessorContractLineMode
    reference_duration_minutes: int | None
    default_hourly_rate: Decimal | None
    display_order: int
    rules: list[AdminProfessorContractGridRuleOut] = Field(default_factory=list)


class AdminProfessorContractGridUpsertRequest(BaseModel):
    valid_from: date
    valid_to: date | None = None
    location_code: str | None = Field(default=None, max_length=60)
    notes: str | None = None
    lines: list[AdminProfessorContractGridLineInput] = Field(default_factory=list)
    clone_from_grid_id: UUID | None = None


class AdminProfessorContractGridOut(BaseModel):
    id: UUID
    professor_id: UUID
    valid_from: date
    valid_to: date | None
    location_code: str | None
    location_label: str
    notes: str | None
    is_active_today: bool
    lines: list[AdminProfessorContractGridLineOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminSessionRecurrenceRequest(BaseModel):
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY"] = "WEEKLY"
    until_date: date


class AdminSessionCreateRequest(BaseModel):
    course_type_id: UUID
    location_id: UUID
    professor_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    public_description: str | None = None
    private_description: str | None = None
    professor_reminder_note: str | None = Field(default=None, max_length=12000)
    start_at_utc: datetime
    end_at_utc: datetime | None = None
    is_all_day: bool = False
    capacity_max: int = Field(default=1, ge=0)
    auto_cancel_deadline_utc: datetime | None = None
    zoom_link: str | None = None
    is_private: bool = False
    allow_online_booking: bool = True
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    recurrence: AdminSessionRecurrenceRequest | None = None


class AdminSessionUpdateRequest(BaseModel):
    course_type_id: UUID | None = None
    location_id: UUID | None = None
    professor_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    public_description: str | None = None
    private_description: str | None = None
    professor_reminder_note: str | None = Field(default=None, max_length=12000)
    start_at_utc: datetime | None = None
    end_at_utc: datetime | None = None
    is_all_day: bool | None = None
    capacity_max: int | None = Field(default=None, ge=0)
    auto_cancel_deadline_utc: datetime | None = None
    zoom_link: str | None = None
    status: SessionStatus | None = None
    cancel_reason: str | None = None
    is_private: bool | None = None
    allow_online_booking: bool | None = None
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    recurrence: AdminSessionRecurrenceRequest | None = None


class AdminSessionOut(BaseModel):
    id: UUID
    course_type_id: UUID
    location_id: UUID
    professor_id: UUID
    teacher_id: UUID
    teacher_display_name: str
    location_label: str
    type_label: str
    status_label: str
    title: str
    description: str | None
    public_description: str | None
    private_description: str | None
    professor_reminder_note: str | None
    group_note: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    is_all_day: bool
    capacity_max: int
    booked_count: int
    status: SessionStatus
    auto_cancel_deadline_utc: datetime
    cancel_reason: str | None
    zoom_link: str | None
    is_private: bool
    allow_online_booking: bool
    timezone: str
    recurrence_group_id: UUID | None
    recurrence_rule: str | None
    created_at: datetime
    updated_at: datetime


class AdminSessionBookingOut(BaseModel):
    id: UUID
    session_id: UUID
    client_id: UUID
    client_email: str
    client_first_name: str | None
    client_last_name: str | None
    client_display_name: str
    client_plan_subscription_id: UUID | None
    status: str
    booked_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    waitlist_position: int | None
    student_note: str | None


class AdminSessionBookingCreateRequest(BaseModel):
    client_id: UUID
    client_plan_subscription_id: UUID | None = None
    recurrence_end_date: date | None = None


class AdminSessionBookingAttendanceUpdateRequest(BaseModel):
    attendance_status: Literal["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]


class AdminSessionGroupNoteUpdateRequest(BaseModel):
    group_note: str | None = Field(default=None, max_length=12000)


class AdminSessionBookingNoteUpdateRequest(BaseModel):
    student_note: str | None = Field(default=None, max_length=12000)


class AdminSessionBookingOperationOut(BaseModel):
    processed_count: int
    booked_count: int
    waitlisted_count: int
    skipped_count: int
    details: list[str] = Field(default_factory=list)


class AdminSessionDuplicateRequest(BaseModel):
    target_start_at_utc: datetime


class AdminSessionDuplicateOperationOut(BaseModel):
    processed_sessions: int
    duplicated_bookings: int


class AdminSessionBroadcastChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class AdminSessionBroadcastAudience(str, enum.Enum):
    STUDENTS = "STUDENTS"
    PARENTS = "PARENTS"
    STUDENTS_AND_PARENTS = "STUDENTS_AND_PARENTS"
    PROFESSOR = "PROFESSOR"
    ADMINS = "ADMINS"
    SELF = "SELF"


class AdminSessionMessageFormat(str, enum.Enum):
    TEXT = "TEXT"
    HTML = "HTML"


class AdminSessionBroadcastRequest(BaseModel):
    channel: AdminSessionBroadcastChannel
    audience: AdminSessionBroadcastAudience = AdminSessionBroadcastAudience.STUDENTS
    included_student_ids: list[UUID] = Field(default_factory=list)
    send_to_self: bool = False
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=12000)
    body_format: AdminSessionMessageFormat = AdminSessionMessageFormat.TEXT
    cc_emails: list[str] = Field(default_factory=list)
    cc_phone_numbers: list[str] = Field(default_factory=list)


class AdminSessionBroadcastOut(BaseModel):
    channel: AdminSessionBroadcastChannel
    recipient_count: int
    cc_count: int
    skipped_count: int
    details: list[str] = Field(default_factory=list)


class AdminCollaboratorMessageRequest(BaseModel):
    collaborator_ids: list[UUID] = Field(default_factory=list)
    channel: AdminSessionBroadcastChannel = AdminSessionBroadcastChannel.EMAIL
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    body_format: AdminSessionMessageFormat = AdminSessionMessageFormat.TEXT


class AdminCollaboratorMessageOut(BaseModel):
    channel: AdminSessionBroadcastChannel
    requested_count: int
    sent_count: int
    skipped_count: int
    details: list[str] = Field(default_factory=list)


class AdminSessionOperationNotificationRequest(BaseModel):
    notify_students: bool = False
    students_subject: str | None = Field(default=None, max_length=255)
    students_message: str | None = None
    students_format: AdminSessionMessageFormat = AdminSessionMessageFormat.TEXT
    notify_professor: bool = False
    professor_same_as_students: bool = True
    professor_subject: str | None = Field(default=None, max_length=255)
    professor_message: str | None = None
    professor_format: AdminSessionMessageFormat = AdminSessionMessageFormat.TEXT


class AdminSessionCancelOperationRequest(BaseModel):
    cancel_reason: str | None = Field(default="ADMIN_CANCELLED", max_length=255)
    notifications: AdminSessionOperationNotificationRequest | None = None


class AdminSessionDeleteOperationRequest(BaseModel):
    notifications: AdminSessionOperationNotificationRequest | None = None


class AdminSessionOperationOut(BaseModel):
    processed_sessions: int
    notified_students: int
    notified_professors: int
    notifications_enabled: bool


class AdminPlanningSettingsOut(BaseModel):
    location_id: UUID
    location_name: str
    description: str | None
    min_booking_notice_hours: int
    max_booking_horizon_months: int
    cancellation_deadline_hours: int
    max_bookings_per_client: int | None
    allow_negative_credits: bool
    waitlist_capacity: int
    auto_cancel_if_booked_less_than: int
    auto_cancel_hours_before_start: int
    is_private: bool
    allow_force_booking: bool
    allow_multi_booking: bool
    notify_coach: bool
    notify_admins: bool
    hide_booking_count: bool
    block_client_cancellation: bool
    created_at: datetime
    updated_at: datetime


class AdminPlanningSettingsUpdateRequest(BaseModel):
    description: str | None = None
    min_booking_notice_hours: int | None = Field(default=None, ge=0)
    max_booking_horizon_months: int | None = Field(default=None, ge=1)
    cancellation_deadline_hours: int | None = Field(default=None, ge=0)
    max_bookings_per_client: int | None = Field(default=None, ge=1)
    allow_negative_credits: bool | None = None
    waitlist_capacity: int | None = Field(default=None, ge=0)
    auto_cancel_if_booked_less_than: int | None = Field(default=None, ge=0)
    auto_cancel_hours_before_start: int | None = Field(default=None, ge=0)
    is_private: bool | None = None
    allow_force_booking: bool | None = None
    allow_multi_booking: bool | None = None
    notify_coach: bool | None = None
    notify_admins: bool | None = None
    hide_booking_count: bool | None = None
    block_client_cancellation: bool | None = None


class AdminPlanningActivityOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    duration_minutes: int
    color_hex: str
    mode: DeliveryMode
    default_capacity: int
    active: bool
    selected: bool
    display_order: int


class AdminPlanningActivitiesOut(BaseModel):
    location_id: UUID
    location_name: str
    selected_activity_ids: list[UUID] = Field(default_factory=list)
    activities: list[AdminPlanningActivityOut] = Field(default_factory=list)


class AdminPlanningActivitiesUpdateRequest(BaseModel):
    activity_ids: list[UUID] = Field(default_factory=list)
