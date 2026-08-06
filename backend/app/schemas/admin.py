from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.catalog import DeliveryMode, SessionAudienceScope, SessionStatus
from app.models.ops import ReminderStatus
from app.models.payout import PayoutStatus, SalaryPaymentMethod
from app.models.plan import PlanCreditGrantsRelation, PlanKind, PlanPriceTaxMode, PlanRestrictionPeriod, SubscriptionStatus
from app.models.professor_contract import ProfessorContractLineMode
from app.models.user import ClientKind, ClientStatus, StudentSite, UserRole


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
    client_balance_default_date_mode: Literal["TODAY", "PACKAGE_END"] = "TODAY"
    bank_transfer_account_holder: str = ""
    bank_transfer_iban: str = ""
    bank_transfer_bic: str = ""
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
    client_balance_default_date_mode: Literal["TODAY", "PACKAGE_END"] = "TODAY"
    bank_transfer_account_holder: str = Field(default="", max_length=255)
    bank_transfer_iban: str = Field(default="", max_length=80)
    bank_transfer_bic: str = Field(default="", max_length=40)
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
    allow_booking_during_payment_alert: bool
    retry_first_delay_days: int
    retry_max_auto_attempts: int
    retry_move_to_pre_termination_after_failed_attempts: int
    notify_success_customer_enabled: bool
    notify_success_admin_enabled: bool
    notify_first_failure_customer_enabled: bool
    notify_first_failure_admin_enabled: bool
    notify_final_failure_customer_enabled: bool
    notify_final_failure_admin_enabled: bool


class AdminSubscriptionSettingsUpdateRequest(BaseModel):
    direct_debit_day: int | None = Field(default=None, ge=1, le=28)
    allow_card_subscriptions: bool
    add_contract_signature: bool
    close_expired_subscriptions: bool
    allow_promotional_start_period: bool
    allow_prorata_card: bool
    allow_prorata_sepa: bool
    online_resiliation_enabled: bool
    allow_booking_during_payment_alert: bool = True
    retry_first_delay_days: int = Field(default=1, ge=1, le=30)
    retry_max_auto_attempts: int = Field(default=2, ge=1, le=10)
    retry_move_to_pre_termination_after_failed_attempts: int = Field(default=2, ge=1, le=10)
    notify_success_customer_enabled: bool = True
    notify_success_admin_enabled: bool = True
    notify_first_failure_customer_enabled: bool = True
    notify_first_failure_admin_enabled: bool = True
    notify_final_failure_customer_enabled: bool = True
    notify_final_failure_admin_enabled: bool = True


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


class AdminReferralCategorySettingsOut(BaseModel):
    label: str
    amount: Decimal
    active: bool = True


class AdminReferralProgramSettingsOut(BaseModel):
    enabled: bool
    currency: str
    trigger_ratio: Decimal
    announcement_email_enabled: bool
    credit_email_enabled: bool
    categories: dict[str, AdminReferralCategorySettingsOut] = Field(default_factory=dict)


class AdminReferralCategorySettingsIn(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    amount: Decimal = Field(ge=Decimal("0"))
    active: bool = True


class AdminReferralProgramSettingsUpdateRequest(BaseModel):
    enabled: bool = True
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    trigger_ratio: Decimal = Field(default=Decimal("0.50"), gt=Decimal("0"), le=Decimal("1"))
    announcement_email_enabled: bool = True
    credit_email_enabled: bool = True
    categories: dict[str, AdminReferralCategorySettingsIn] = Field(default_factory=dict)


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
    stripe_webhook_secret_configured: bool
    payplug_test_secret_masked: str
    payplug_live_secret_masked: str
    mollie_test_api_key_masked: str
    mollie_live_api_key_masked: str
    stripe_test_secret_masked: str
    stripe_live_secret_masked: str
    stripe_webhook_secret_masked: str
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
    stripe_webhook_secret: str | None = Field(default=None, max_length=255)
    webhook_secret: str | None = Field(default=None, max_length=255)


class AdminMessagingSettingsOut(BaseModel):
    studio_email: str
    studio_sender_name: str
    teacher_sender_name: str
    use_studio_name_as_default_sender: bool
    use_studio_email_for_reminders: bool
    use_studio_email_for_lesson_notes: bool
    send_birthday_emails: bool
    email_provider: str
    email_reply_to: str
    email_subject_prefix: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_configured: bool
    smtp_password_masked: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_timeout_seconds: int
    sms_provider: str
    sms_sender: str
    brevo_sms_api_key_configured: bool
    brevo_sms_api_key_masked: str
    frontend_base_url: str
    brevo_email_webhook_url: str
    brevo_sms_webhook_url: str
    quote_send_template_ref: str
    quote_send_sms_template_ref: str
    quote_reminder_template_ref: str
    quote_reminder_sms_template_ref: str
    quote_cancel_template_ref: str
    quote_cancel_sms_template_ref: str
    quote_expired_template_ref: str
    quote_expired_sms_template_ref: str
    quote_approved_template_ref: str
    quote_rejected_template_ref: str
    quote_change_requested_template_ref: str
    quote_reminder_enabled: bool
    quote_reminder_sms_enabled: bool
    quote_reminder_lead_hours: int
    quote_reminder_lead_hours_csv: str
    quote_reminder_lead_hours_values: list[int]
    quote_daily_job_local_time: str
    quote_auto_cancel_enabled: bool
    quote_auto_cancel_delay_hours: int
    quote_cancel_notification_enabled: bool
    quote_cancel_sms_notification_enabled: bool
    quote_expired_notification_enabled: bool
    quote_expired_sms_notification_enabled: bool
    delivery_enabled: bool
    delivery_error_message: str | None = None
    sms_delivery_enabled: bool
    sms_delivery_error_message: str | None = None
    updated_at: datetime | None = None


class AdminMessagingSettingsUpdateRequest(BaseModel):
    studio_email: str = Field(default="", max_length=255)
    studio_sender_name: str = Field(default="", max_length=120)
    teacher_sender_name: str = Field(default="", max_length=120)
    use_studio_name_as_default_sender: bool = True
    use_studio_email_for_reminders: bool = True
    use_studio_email_for_lesson_notes: bool = True
    send_birthday_emails: bool = False
    email_provider: str = Field(default="LOG", max_length=20)
    email_reply_to: str = Field(default="", max_length=255)
    email_subject_prefix: str = Field(default="", max_length=120)
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="", max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = Field(default=15, ge=1, le=120)
    sms_provider: str = Field(default="LOG", max_length=20)
    sms_sender: str = Field(default="", max_length=60)
    brevo_sms_api_key: str | None = Field(default=None, max_length=255)
    frontend_base_url: str = Field(default="", max_length=255)
    quote_send_template_ref: str = Field(default="predefined:QUOTE_SEND_DEFAULT", max_length=120)
    quote_send_sms_template_ref: str = Field(default="predefined:QUOTE_SEND_SMS_DEFAULT", max_length=120)
    quote_reminder_template_ref: str = Field(default="predefined:QUOTE_REMINDER_DEFAULT", max_length=120)
    quote_reminder_sms_template_ref: str = Field(default="predefined:QUOTE_REMINDER_SMS_DEFAULT", max_length=120)
    quote_cancel_template_ref: str = Field(default="predefined:QUOTE_CANCEL_DEFAULT", max_length=120)
    quote_cancel_sms_template_ref: str = Field(default="predefined:QUOTE_CANCEL_SMS_DEFAULT", max_length=120)
    quote_expired_template_ref: str = Field(default="predefined:QUOTE_EXPIRED_DEFAULT", max_length=120)
    quote_expired_sms_template_ref: str = Field(default="predefined:QUOTE_EXPIRED_SMS_DEFAULT", max_length=120)
    quote_approved_template_ref: str = Field(default="predefined:QUOTE_APPROVED_DEFAULT", max_length=120)
    quote_rejected_template_ref: str = Field(default="predefined:QUOTE_REJECTED_DEFAULT", max_length=120)
    quote_change_requested_template_ref: str = Field(default="predefined:QUOTE_CHANGE_REQUESTED_DEFAULT", max_length=120)
    quote_reminder_enabled: bool = True
    quote_reminder_sms_enabled: bool = False
    quote_reminder_lead_hours: int = Field(default=24, ge=1, le=168)
    quote_reminder_lead_hours_csv: str = Field(default="72,24", max_length=120)
    quote_daily_job_local_time: str = Field(default="07:00", max_length=5)
    quote_auto_cancel_enabled: bool = True
    quote_auto_cancel_delay_hours: int = Field(default=24, ge=0, le=720)
    quote_cancel_notification_enabled: bool = True
    quote_cancel_sms_notification_enabled: bool = False
    quote_expired_notification_enabled: bool = True
    quote_expired_sms_notification_enabled: bool = False


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
    subject_translations: dict[str, str] = Field(default_factory=dict)
    body: str
    body_translations: dict[str, str] = Field(default_factory=dict)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True
    usage_contexts: list[str] = Field(default_factory=list)
    description: str | None = None
    variables_hint: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminMessagingPredefinedTemplateUpdateRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    subject_translations: dict[str, str] = Field(default_factory=dict)
    body: str = Field(min_length=1, max_length=12000)
    body_translations: dict[str, str] = Field(default_factory=dict)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True


class AdminMessagingCustomTemplateCreateRequest(BaseModel):
    channel: AdminMessagingChannel
    name: str = Field(min_length=1, max_length=180)
    subject: str | None = Field(default=None, max_length=255)
    subject_translations: dict[str, str] = Field(default_factory=dict)
    body: str = Field(min_length=1, max_length=12000)
    body_translations: dict[str, str] = Field(default_factory=dict)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True
    usage_contexts: list[str] = Field(default_factory=list)


class AdminMessagingCustomTemplateUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    subject: str | None = Field(default=None, max_length=255)
    subject_translations: dict[str, str] = Field(default_factory=dict)
    body: str = Field(min_length=1, max_length=12000)
    body_translations: dict[str, str] = Field(default_factory=dict)
    body_format: AdminMessageBodyFormat = "TEXT"
    active: bool = True
    usage_contexts: list[str] = Field(default_factory=list)


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


class AdminProfessorPayGridPeriodOut(BaseModel):
    id: UUID
    start_date: date
    end_date: date | None
    status: str
    notes: str | None = None
    is_active: bool
    is_future: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    rules_count: int = 0


class AdminProfessorPayGridPeriodCreateRequest(BaseModel):
    start_date: date
    end_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    clone_from_period_id: UUID | None = None


class AdminProfessorPayGridPeriodUpdateRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    status: str | None = None


class AdminProfessorPayGridPeriodRulesUpdateRequest(BaseModel):
    lines: list[AdminProfessorDefaultGridLineInput] = Field(default_factory=list)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AdminProfessorPayGridPeriodDetailOut(BaseModel):
    period: AdminProfessorPayGridPeriodOut
    lines: list["AdminProfessorDefaultGridLineOut"] = Field(default_factory=list)


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
    active_period_id: UUID | None = None
    active_period_start_date: date | None = None
    active_period_end_date: date | None = None


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
    first_purchase_signup_fee_enabled: bool
    first_purchase_partitions_enabled: bool
    first_purchase_partitions_price_value: Decimal | None
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
    first_purchase_signup_fee_enabled: bool = False
    first_purchase_partitions_enabled: bool = False
    first_purchase_partitions_price_value: Decimal | None = Field(default=None, ge=0)
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
    first_purchase_signup_fee_enabled: bool | None = None
    first_purchase_partitions_enabled: bool | None = None
    first_purchase_partitions_price_value: Decimal | None = Field(default=None, ge=0)
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
    requires_professor: bool
    allows_student_bookings: bool
    supports_student_time_overrides: bool
    default_capacity: int
    default_hourly_rate: Decimal | None
    default_course_rate_ttc: Decimal | None
    email_reminder_hours_before_start: int | None
    sms_reminder_hours_before_start: int | None
    min_booking_notice_hours_override: int | None
    cancellation_deadline_hours_override: int | None
    auto_cancel_if_booked_less_than_override: int | None
    auto_cancel_hours_before_start_override: int | None
    auto_cancel_rule_enabled: bool
    exclude_holidays_in_recurrence: bool
    exclude_school_vacations_in_recurrence: bool
    active: bool
    content_course_ids: list[UUID] = Field(default_factory=list)
    content_course_titles: list[str] = Field(default_factory=list)


class AdminActivityUpsertRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    service_code: str = Field(default="ACTIVITY", min_length=1, max_length=80)
    seller_legal_entity_id: UUID
    payor_legal_entity_id: UUID | None = None
    credit_type_id: UUID | None = None
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    color_hex: str = Field(default="#94C973", min_length=7, max_length=7)
    mode: DeliveryMode = DeliveryMode.ANY
    requires_professor: bool = True
    allows_student_bookings: bool = True
    supports_student_time_overrides: bool = False
    default_capacity: int = Field(default=8, ge=0, le=500)
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    default_course_rate_ttc: Decimal | None = Field(default=None, ge=0)
    email_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    sms_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    min_booking_notice_hours_override: int | None = Field(default=None, ge=0)
    cancellation_deadline_hours_override: int | None = Field(default=None, ge=0)
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=0)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    auto_cancel_rule_enabled: bool = False
    exclude_holidays_in_recurrence: bool = True
    exclude_school_vacations_in_recurrence: bool = True
    active: bool = True


class AdminActivityUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    service_code: str | None = Field(default=None, min_length=1, max_length=80)
    seller_legal_entity_id: UUID | None = None
    payor_legal_entity_id: UUID | None = None
    credit_type_id: UUID | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    color_hex: str | None = Field(default=None, min_length=7, max_length=7)
    mode: DeliveryMode | None = None
    requires_professor: bool | None = None
    allows_student_bookings: bool | None = None
    supports_student_time_overrides: bool | None = None
    default_capacity: int | None = Field(default=None, ge=0, le=500)
    default_hourly_rate: Decimal | None = Field(default=None, ge=0)
    default_course_rate_ttc: Decimal | None = Field(default=None, ge=0)
    email_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    sms_reminder_hours_before_start: int | None = Field(default=None, ge=0)
    min_booking_notice_hours_override: int | None = Field(default=None, ge=0)
    cancellation_deadline_hours_override: int | None = Field(default=None, ge=0)
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=0)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    auto_cancel_rule_enabled: bool | None = None
    exclude_holidays_in_recurrence: bool | None = None
    exclude_school_vacations_in_recurrence: bool | None = None
    active: bool | None = None


class AdminExternalContentCourseOut(BaseModel):
    id: UUID
    provider: str
    external_id: str
    slug: str | None
    title: str
    summary: str | None
    level_code: str | None
    status: str
    cover_image_url: str | None
    sections_count: int
    lessons_count: int
    last_synced_at: datetime | None


class AdminActivityContentMappingsReplaceRequest(BaseModel):
    content_course_ids: list[UUID] = Field(default_factory=list)
    access_rule: Literal["ACTIVE_ENROLLMENT", "MANUAL_OVERRIDE"] = "ACTIVE_ENROLLMENT"


class AdminActivityContentMappingOut(BaseModel):
    id: UUID
    course_type_id: UUID
    content_course_id: UUID
    access_rule: str
    sort_order: int
    active: bool
    content_course_title: str
    content_course_level_code: str | None
    content_course_status: str
    content_course_provider: str
    content_course_external_id: str


class AdminExternalContentSyncOut(BaseModel):
    provider: str
    fetched_at: datetime
    courses_seen: int
    courses_created: int
    courses_updated: int
    sections_seen: int
    sections_created: int
    sections_updated: int
    sections_deleted: int
    lessons_seen: int
    lessons_created: int
    lessons_updated: int
    lessons_deleted: int


class AdminExternalContentSettingsOut(BaseModel):
    base_url: str
    courses_endpoint: str
    resolved_endpoint_url: str | None = None
    bearer_token_configured: bool
    bearer_token_masked: str
    timeout_seconds: int
    updated_at: datetime | None = None


class AdminExternalContentSettingsUpdateRequest(BaseModel):
    base_url: str = Field(default="", max_length=500)
    courses_endpoint: str = Field(default="", max_length=500)
    bearer_token: str | None = Field(default=None, max_length=500)
    clear_bearer_token: bool = False
    timeout_seconds: int = Field(default=20, ge=5, le=120)


class AdminClientOut(BaseModel):
    id: UUID
    email: str
    role: UserRole
    client_kind: ClientKind
    photo_url: str | None = None
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
    preferred_language: str = "fr"
    preferred_currency: str
    timezone: str
    first_course_at: datetime | None = None
    portal_contact_visible: bool = True
    email_opt_in: bool = True
    sms_opt_in: bool = True
    lesson_reminder_email_opt_in: bool = True
    lesson_reminder_sms_opt_in: bool = False
    email_delivery_status: str = "active"
    email_suspended_at: datetime | None = None
    email_suspension_reason: str | None = None
    phone_delivery_status: str = "active"
    phone_suspended_at: datetime | None = None
    phone_suspension_reason: str | None = None
    client_status: ClientStatus = ClientStatus.ACTIVE
    student_site: StudentSite | None = None
    family_name: str | None = None
    linked_children_count: int = 0
    linked_children_names: list[str] = Field(default_factory=list)
    linked_adults_count: int = 0
    linked_adult_names: list[str] = Field(default_factory=list)
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
    phone: str | None
    legal_form: Literal["SAS", "SA", "SARL", "EURL"] | None
    share_capital: str | None
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
    phone: str | None = Field(default=None, max_length=30)
    legal_form: Literal["SAS", "SA", "SARL", "EURL"] | None = None
    share_capital: str | None = Field(default=None, max_length=120)
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
    phone: str | None = Field(default=None, max_length=30)
    legal_form: Literal["SAS", "SA", "SARL", "EURL"] | None = None
    share_capital: str | None = Field(default=None, max_length=120)
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
    preferred_language: str | None = Field(default=None, min_length=2, max_length=8)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    portal_contact_visible: bool | None = None
    email_opt_in: bool | None = None
    sms_opt_in: bool | None = None
    lesson_reminder_email_opt_in: bool | None = None
    lesson_reminder_sms_opt_in: bool | None = None
    client_status: ClientStatus | None = None
    student_site: StudentSite | None = None
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
    preferred_language: str = Field(default="fr", min_length=2, max_length=8)
    preferred_currency: str = Field(default="EUR", min_length=3, max_length=3)
    timezone: str = Field(default="Europe/Paris", min_length=2, max_length=100)
    portal_contact_visible: bool = True
    email_opt_in: bool = True
    sms_opt_in: bool = True
    lesson_reminder_email_opt_in: bool = True
    lesson_reminder_sms_opt_in: bool = False
    client_status: ClientStatus | None = None
    student_site: StudentSite | None = None
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
    EMAIL_CLIENTS_OPERATIONAL = "EMAIL_CLIENTS_OPERATIONAL"
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
    filter_student_site: StudentSite | None = None
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


class AdminMyMusicStaffImportOut(BaseModel):
    dry_run: bool
    rows_seen: int = 0
    rows_imported: int = 0
    families_seen: int = 0
    parent_contacts_seen: int = 0
    parents_created: int = 0
    parents_updated: int = 0
    parents_reused: int = 0
    children_created: int = 0
    children_updated: int = 0
    children_reused: int = 0
    family_links_created: int = 0
    family_links_existing: int = 0
    group_id: UUID | None = None
    group_name: str = "Base 2025-2026 - My Music Staff"
    warnings: list[str] = Field(default_factory=list)


class AdminMyMusicStaffImportStatusOut(BaseModel):
    group_id: UUID | None = None
    group_name: str = "Base 2025-2026 - My Music Staff"
    group_found: bool = False
    members_count: int = 0
    parents_count: int = 0
    children_count: int = 0
    imported_note_count: int = 0
    imported_parents_note_count: int = 0
    imported_children_note_count: int = 0
    family_links_count: int = 0
    active_children_count: int = 0
    inactive_children_count: int = 0
    responsible_parents_count: int = 0


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


class AdminImpersonationStartOut(BaseModel):
    target_user_id: UUID
    target_role: Literal["client", "teacher", "manager"]
    target_display_name: str
    access_token: str
    expires_in_seconds: int
    redirect_path: str


class AdminImpersonationEndOut(BaseModel):
    message: str


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
    payment_provider_code: str | None = None
    payment_method_setup_required: bool = False
    payment_method_setup_completed_at: datetime | None = None
    forfait_loyalty_discount_per_hour_ttc: Decimal | None = None
    forfait_family_discount_per_hour_ttc: Decimal | None = None
    forfait_short_commitment_supplement_per_hour_ttc: Decimal | None = None
    forfait_activity_pricing: list["AdminClientForfaitActivityPricingOut"] = Field(default_factory=list)
    last_payment_at: datetime | None = None
    last_payment_status: str | None = None
    suspension_starts_at: datetime | None = None
    suspension_ends_at: datetime | None = None
    suspension_start_date: date | None = None
    suspension_end_date: date | None = None
    suspension_duration_value: int | None = None
    suspension_duration_unit: str | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    cancellation_request_status: str | None = None
    cancellation_request_note: str | None = None
    cancellation_request_reviewed_at: datetime | None = None
    plan: AdminClientSubscriptionMiniOut
    estimated_price_excl_vat: Decimal | None
    estimated_vat_rate: Decimal | None
    estimated_vat_amount: Decimal | None
    estimated_total_incl_vat: Decimal | None
    estimated_currency: str | None


class AdminClientSubscriptionSuspendRequest(BaseModel):
    suspension_start_date: date
    suspension_end_date: date


class AdminClientSubscriptionCancellationDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


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


class AdminClientBillingAdjustmentOut(BaseModel):
    id: UUID
    client_id: UUID
    student_id: UUID | None = None
    change_id: UUID | None = None
    quote_id: UUID | None = None
    quote_number: str | None = None
    status: Literal["READY", "DISMISSED", "CONVERTED"]
    adjustment_type: Literal["INVOICE", "CREDIT_NOTE"]
    label: str
    description: str | None = None
    amount_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
    currency: str
    legal_entity_id: UUID | None = None
    converted_manual_transaction_id: UUID | None = None
    dismissed_reason: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminClientBillingAdjustmentQueueOut(AdminClientBillingAdjustmentOut):
    client_display_name: str
    student_display_name: str | None = None
    change_title: str | None = None
    change_type: str | None = None


class AdminStudentQuoteChangeOut(BaseModel):
    id: UUID
    client_id: UUID
    student_id: UUID | None = None
    student_display_name: str | None = None
    quote_id: UUID | None = None
    quote_number: str | None = None
    quote_line_id: UUID | None = None
    change_type: Literal[
        "SLOT_CHANGE",
        "COURSE_CANCELLED",
        "COURSE_ADDED",
        "COURSE_REMOVED",
        "FORMULA_CHANGE",
        "EXCEPTIONAL_ADJUSTMENT",
        "OTHER",
    ]
    status: Literal["DRAFT", "VALIDATED", "CANCELLED"]
    requested_by: str | None = None
    requested_at: datetime
    effective_date: date | None = None
    title: str
    description: str | None = None
    before_snapshot: dict[str, object] = Field(default_factory=dict)
    after_snapshot: dict[str, object] = Field(default_factory=dict)
    financial_impact_ttc: Decimal | None = None
    currency: str
    billing_action: Literal["NONE", "TO_INVOICE", "TO_CREDIT", "MANUAL_REVIEW"]
    client_visible_note: str | None = None
    internal_note: str | None = None
    billing_adjustments: list[AdminClientBillingAdjustmentOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminStudentQuoteChangeCreateRequest(BaseModel):
    student_id: UUID | None = None
    quote_id: UUID | None = None
    quote_line_id: UUID | None = None
    change_type: Literal[
        "SLOT_CHANGE",
        "COURSE_CANCELLED",
        "COURSE_ADDED",
        "COURSE_REMOVED",
        "FORMULA_CHANGE",
        "EXCEPTIONAL_ADJUSTMENT",
        "OTHER",
    ] = "OTHER"
    status: Literal["DRAFT", "VALIDATED"] = "VALIDATED"
    requested_by: str | None = Field(default=None, max_length=120)
    requested_at: datetime | None = None
    effective_date: date | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    before_snapshot: dict[str, object] = Field(default_factory=dict)
    after_snapshot: dict[str, object] = Field(default_factory=dict)
    financial_impact_ttc: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    billing_action: Literal["NONE", "TO_INVOICE", "TO_CREDIT", "MANUAL_REVIEW"] = "NONE"
    vat_rate: Decimal = Field(default=Decimal("20.000"), ge=Decimal("0"), le=Decimal("100"))
    legal_entity_id: UUID | None = None
    client_visible_note: str | None = Field(default=None, max_length=4000)
    internal_note: str | None = Field(default=None, max_length=4000)


class AdminClientBillingAdjustmentDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class AdminClientQuoteReferenceOut(BaseModel):
    id: UUID
    quote_number: str
    total_ttc: Decimal
    currency: str
    approved_at: datetime | None = None
    school_year_label: str | None = None


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
    auto_repeat_every: int = Field(default=1, ge=1, le=12)
    auto_layout_style: Literal["NORMAL", "CONDENSED"] = "NORMAL"
    auto_include_previous_balance: bool = True
    auto_send_email: bool = False
    auto_footer_note: str | None = Field(default=None, max_length=2000)
    auto_exclude_pack_subscription_lines: bool = True
    invoice_number: str | None = Field(default=None, max_length=120)
    selected_payment_keys: list[str] | None = None
    public_note: str | None = Field(default=None, max_length=2000)
    private_note: str | None = Field(default=None, max_length=2000)


class AdminClientAutoInvoiceRuleUpsertRequest(BaseModel):
    cycle_start_date: date
    frequency: Literal["MONTHLY", "QUARTERLY", "YEARLY"] = "MONTHLY"
    billing_timing: Literal["UPCOMING_LESSONS", "PREVIOUS_LESSONS"] = "UPCOMING_LESSONS"
    due_date_rule_type: Literal["SAME_DAY_ISSUE", "X_DAYS_AFTER_ISSUE"] = "SAME_DAY_ISSUE"
    due_date_days_offset: int | None = Field(default=None, ge=0, le=365)
    include_pending_lines: bool = True
    include_cancelled_lines: bool = False
    legal_entity_id: UUID
    status: Literal["ACTIVE", "PAUSED"] = "ACTIVE"


class AdminClientAutoInvoiceRuleOut(BaseModel):
    id: UUID
    client_id: UUID
    legal_entity_id: UUID
    cycle_start_date: date
    frequency: Literal["MONTHLY", "QUARTERLY", "YEARLY"]
    billing_timing: Literal["UPCOMING_LESSONS", "PREVIOUS_LESSONS"]
    due_date_rule_type: Literal["SAME_DAY_ISSUE", "X_DAYS_AFTER_ISSUE"]
    due_date_days_offset: int | None = None
    include_pending_lines: bool
    include_cancelled_lines: bool
    next_run_date: date
    preview_period_start_date: date
    preview_period_end_date: date
    preview_due_date: date
    last_generated_at: datetime | None = None
    status: Literal["ACTIVE", "PAUSED", "ARCHIVED"]
    created_at: datetime
    updated_at: datetime


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
    seller_legal_entity_id: UUID | None = None
    billing_entity: str | None = None
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
    auto_repeat_every: int = Field(default=1, ge=1, le=12)
    auto_layout_style: Literal["NORMAL", "CONDENSED"] = "NORMAL"
    auto_include_previous_balance: bool = True
    auto_send_email: bool = False
    auto_footer_note: str | None = None
    auto_exclude_pack_subscription_lines: bool = True
    include_pending: bool
    include_cancelled: bool
    included_payment_keys: list[str] = Field(default_factory=list)
    totals_by_currency: dict[str, str]
    total_to_pay_by_currency: dict[str, str] = Field(default_factory=dict)
    invoice_status: Literal["ISSUED", "PAID", "CANCELLED"]
    emailed_at: datetime | None = None
    reminded_at: datetime | None = None
    bank_transfer_order_id: UUID | None = None
    bank_transfer_order_reference: str | None = None
    bank_transfer_order_status: str | None = None
    bank_transfer_order_expires_at: datetime | None = None
    bank_transfer_order_paid_at: datetime | None = None
    public_note: str | None = None
    private_note: str | None = None
    related_invoices: list[AdminRangeInvoiceReferenceOut] = Field(default_factory=list)


class AdminRangeInvoiceStatusUpdateRequest(BaseModel):
    status: Literal["ISSUED", "PAID", "CANCELLED"]


class AdminRangeInvoiceBankTransferManualPaymentRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=120)


class AdminRangeInvoiceEmailRequest(BaseModel):
    kind: Literal["INVOICE", "REMINDER"] = "INVOICE"
    to_emails: list[str] | None = None
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=20000)
    body_format: Literal["TEXT", "HTML"] = "TEXT"
    include_change_summary: bool = False
    reference_invoice_note_id: UUID | None = None
    send_sms: bool = False
    sms_phone: str | None = Field(default=None, max_length=40)
    sms_body: str | None = Field(default=None, max_length=1000)


class AdminRangeInvoiceEmailOut(BaseModel):
    note_id: UUID
    kind: Literal["INVOICE", "REMINDER"]
    sent_at: datetime
    message_id: str | None = None
    recipients: list[str] = Field(default_factory=list)
    sms_message_id: str | None = None
    sms_recipient: str | None = None


class AdminRangeInvoiceEmailPreviewOut(BaseModel):
    note_id: UUID
    kind: Literal["INVOICE", "REMINDER"]
    to_emails: list[str]
    subject: str
    body: str
    body_format: Literal["TEXT", "HTML"] = "TEXT"
    sms_body: str | None = None


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
    scheduled_service_date: date | None = None
    service_completed_at: datetime | None = None
    payment_received: bool = False
    payment_received_at: datetime | None = None
    payment_received_amount: Decimal | None = None
    payment_refunded: bool = False
    payment_refunded_at: datetime | None = None
    payment_refunded_amount: Decimal | None = None
    payment_refund_reason: str | None = None
    payment_refund_email_sent_at: datetime | None = None
    payment_receipt_id: UUID | None = None
    payment_receipt_number: str | None = None
    payment_receipt_status: str | None = None
    payment_receipt_sent_at: datetime | None = None
    final_invoice_generated: bool = False
    final_invoice_note_id: UUID | None = None
    final_invoice_number: str | None = None
    final_invoice_status: str | None = None


class AdminPaymentReceiptOut(BaseModel):
    id: UUID
    receipt_number: str | None = None
    status: str
    customer_id: UUID
    student_id: UUID | None = None
    booking_id: UUID
    amount_paid: Decimal
    currency: str
    paid_at: datetime | None = None
    payment_method: str | None = None
    payment_provider: str | None = None
    payment_transaction_reference: str | None = None
    reservation_label: str
    scheduled_service_date: date | None = None
    location_label: str | None = None
    email_sent_at: datetime | None = None
    final_invoice_note_id: UUID | None = None
    final_invoice_generated_at: datetime | None = None


class AdminPaymentReceiptEmailOut(BaseModel):
    receipt_id: UUID
    sent_at: datetime


class AdminClientMessageOut(BaseModel):
    id: UUID
    booking_id: UUID | None = None
    session_id: UUID | None = None
    session_title: str | None = None
    channel: Literal["EMAIL", "SMS", "PUSH"] = "EMAIL"
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
    check_deposit_label: str | None = Field(default=None, max_length=80)


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


class AdminClientManualTransactionStatusUpdateRequest(BaseModel):
    status: Literal["CHECK_RECEIVED", "CHECK_DEPOSITED", "CHECK_REFUSED", "PAID", "COMPLETED", "CANCELLED"]


class AdminCheckDepositPaymentOut(BaseModel):
    transaction_id: UUID
    client_id: UUID
    client_name: str
    occurred_at: datetime
    label: str
    reference: str | None = None
    amount_incl_vat: Decimal
    currency: str
    status: str
    invoice_number: str | None = None
    invoice_note_id: UUID | None = None
    tracking_note: str | None = None


class AdminCheckDepositImportRowIn(BaseModel):
    row_number: int | None = None
    transaction_id: UUID | None = None
    reference: str | None = Field(default=None, max_length=120)
    amount_incl_vat: Decimal | None = Field(default=None, gt=Decimal("0"))
    client_name: str | None = Field(default=None, max_length=255)
    payer_name: str | None = Field(default=None, max_length=255)


class AdminCheckDepositBulkUpdateRequest(BaseModel):
    transaction_ids: list[UUID] = Field(default_factory=list)
    rows: list[AdminCheckDepositImportRowIn] = Field(default_factory=list)
    target_status: Literal["CHECK_DEPOSITED", "CHECK_REFUSED", "PAID"] = "CHECK_DEPOSITED"
    batch_reference: str | None = Field(default=None, max_length=120)
    effective_date: date | None = None


class AdminCheckDepositBulkUpdateOut(BaseModel):
    matched_count: int
    updated_count: int
    updated_transaction_ids: list[UUID] = Field(default_factory=list)
    unmatched_rows: list[str] = Field(default_factory=list)


class AdminReferralRewardOut(BaseModel):
    id: UUID
    typeform_intake_id: UUID | None = None
    quote_id: UUID | None = None
    declared_referrer_text: str
    category: str | None = None
    status: str
    match_status: str
    match_confidence: int
    referrer_user_id: UUID | None = None
    referrer_name: str | None = None
    referrer_email: str | None = None
    referred_client_id: UUID | None = None
    referred_client_name: str | None = None
    referred_student_id: UUID | None = None
    referred_student_name: str | None = None
    referred_prospect_name: str | None = None
    reward_amount: Decimal
    currency: str
    trigger_ratio: Decimal
    invoice_total: Decimal | None = None
    paid_total: Decimal | None = None
    threshold_amount: Decimal | None = None
    payment_progress_ratio: Decimal | None = None
    credit_transaction_id: UUID | None = None
    trigger_invoice_note_id: UUID | None = None
    announcement_email_sent_at: datetime | None = None
    credit_email_sent_at: datetime | None = None
    validated_at: datetime | None = None
    credit_granted_at: datetime | None = None
    updated_at: datetime
    match_candidates: list[dict[str, object]] = Field(default_factory=list)


class AdminReferralBulkRecomputeOut(BaseModel):
    scanned_count: int
    updated_count: int
    credit_granted_count: int


class AdminReferralRewardManualMatchRequest(BaseModel):
    referrer_user_id: UUID


class AdminReferralRewardManualCreateRequest(BaseModel):
    referrer_user_id: UUID
    referred_user_id: UUID
    category: str | None = Field(default=None, max_length=40)
    reward_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=500)


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
    zoom_link: str | None = None
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
    can_view_planning_simulation: bool
    planning_simulation_location_id: UUID | None = None
    can_manage_check_deposits: bool
    check_deposits_location_id: UUID | None = None
    can_view_intakes: bool
    can_view_quotes: bool
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
    can_view_planning_simulation: bool = False
    planning_simulation_location_id: UUID | None = None
    can_manage_check_deposits: bool = False
    check_deposits_location_id: UUID | None = None
    can_view_intakes: bool = False
    can_view_quotes: bool = False
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
    teacher_profile: bool = False
    manager_profile: bool = False


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
    valid_from: date | None = None
    valid_to: date | None = None


class AdminProfessorRatesUpdateRequest(BaseModel):
    rates: list[AdminProfessorRateInput] = Field(default_factory=list)
    effective_from: date | None = None
    clear_course_type_ids: list[UUID] = Field(default_factory=list)


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
    interval: int = Field(default=1, ge=1, le=52)
    until_date: date
    time_basis: Literal["LOCAL", "UTC"] = "LOCAL"


class AdminSessionCreateRequest(BaseModel):
    course_type_id: UUID
    location_id: UUID
    professor_id: UUID | None = None
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
    auto_cancel_rule_enabled_override: bool | None = None
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=1)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    zoom_link: str | None = None
    visibility_scopes: list[SessionAudienceScope] = Field(default_factory=lambda: [SessionAudienceScope.EXTERNAL])
    booking_scopes: list[SessionAudienceScope] = Field(default_factory=lambda: [SessionAudienceScope.EXTERNAL])
    visibility_scope: SessionAudienceScope | None = None
    booking_scope: SessionAudienceScope | None = None
    is_private: bool | None = None
    allow_online_booking: bool | None = None
    external_booking_price_ttc: Decimal | None = Field(default=None, ge=0)
    show_external_remaining_seats: bool = True
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    recurrence: AdminSessionRecurrenceRequest | None = None


class AdminSessionUpdateRequest(BaseModel):
    course_type_id: UUID | None = None
    location_id: UUID | None = None
    professor_id: UUID | None = None
    substitute_teacher_id: UUID | None = None
    substitute_note: str | None = Field(default=None, max_length=12000)
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
    auto_cancel_rule_enabled_override: bool | None = None
    auto_cancel_if_booked_less_than_override: int | None = Field(default=None, ge=1)
    auto_cancel_hours_before_start_override: int | None = Field(default=None, ge=0)
    zoom_link: str | None = None
    status: SessionStatus | None = None
    cancel_reason: str | None = None
    visibility_scopes: list[SessionAudienceScope] | None = None
    booking_scopes: list[SessionAudienceScope] | None = None
    visibility_scope: SessionAudienceScope | None = None
    booking_scope: SessionAudienceScope | None = None
    is_private: bool | None = None
    allow_online_booking: bool | None = None
    external_booking_price_ttc: Decimal | None = Field(default=None, ge=0)
    show_external_remaining_seats: bool | None = None
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    recurrence: AdminSessionRecurrenceRequest | None = None


class AdminSessionOut(BaseModel):
    id: UUID
    course_type_id: UUID
    location_id: UUID
    professor_id: UUID | None
    substitute_teacher_id: UUID | None
    substitute_set_at: datetime | None
    substitute_set_by: UUID | None
    substitute_note: str | None
    teacher_id: UUID | None
    teacher_display_name: str
    habitual_teacher_id: UUID | None
    habitual_teacher_display_name: str
    substitute_teacher_display_name: str | None
    effective_teacher_id: UUID | None
    effective_teacher_display_name: str
    requires_professor: bool
    allows_student_bookings: bool
    supports_student_time_overrides: bool
    location_label: str
    type_label: str
    status_label: str
    title: str
    description: str | None
    public_description: str | None
    private_description: str | None
    professor_reminder_note: str | None
    group_note: str | None
    internal_note: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    is_all_day: bool
    capacity_max: int
    booked_count: int
    status: SessionStatus
    auto_cancel_deadline_utc: datetime
    auto_cancel_rule_enabled_override: bool | None
    auto_cancel_if_booked_less_than_override: int | None
    auto_cancel_hours_before_start_override: int | None
    cancel_reason: str | None
    zoom_link: str | None
    visibility_scopes: list[SessionAudienceScope] = Field(default_factory=list)
    booking_scopes: list[SessionAudienceScope] = Field(default_factory=list)
    visibility_scope: SessionAudienceScope
    booking_scope: SessionAudienceScope
    is_private: bool
    allow_online_booking: bool
    external_booking_price_ttc: Decimal | None
    show_external_remaining_seats: bool
    timezone: str
    recurrence_group_id: UUID | None
    recurrence_rule: str | None
    recurrence_end_date: date | None
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
    student_start_at_utc: datetime | None
    student_end_at_utc: datetime | None
    waitlist_position: int | None
    student_note: str | None
    internal_note: str | None


class AdminSessionBookingCreateRequest(BaseModel):
    client_id: UUID
    client_plan_subscription_id: UUID | None = None
    recurrence_end_date: date | None = None
    student_start_time_local: str | None = Field(default=None, max_length=5)
    student_end_time_local: str | None = Field(default=None, max_length=5)


class AdminSessionBookingAttendanceUpdateRequest(BaseModel):
    attendance_status: Literal["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]
    internal_note: str | None = Field(default=None, max_length=12000)


class AdminSessionGroupNoteUpdateRequest(BaseModel):
    group_note: str | None = Field(default=None, max_length=12000)


class AdminSessionBookingNoteUpdateRequest(BaseModel):
    student_note: str | None = Field(default=None, max_length=12000)


class AdminInternalNoteUpdateRequest(BaseModel):
    internal_note: str | None = Field(default=None, max_length=12000)


class AdminSessionBookingStudentTimeUpdateRequest(BaseModel):
    student_start_time_local: str | None = Field(default=None, max_length=5)
    student_end_time_local: str | None = Field(default=None, max_length=5)


class AdminSessionBookingOperationOut(BaseModel):
    processed_count: int
    booked_count: int
    waitlisted_count: int
    skipped_count: int
    details: list[str] = Field(default_factory=list)


class AdminPlanningReorganizationLocationOut(BaseModel):
    id: UUID
    name: str
    timezone: str


class AdminPlanningReorganizationBookingOut(BaseModel):
    id: UUID
    client_id: UUID
    client_display_name: str
    status: str
    student_note: str | None = None


class AdminPlanningReorganizationSessionOut(BaseModel):
    id: UUID
    title: str
    type_label: str
    location_id: UUID
    location_label: str
    teacher_display_name: str
    start_at_utc: datetime
    end_at_utc: datetime
    timezone: str
    capacity_max: int
    booked_count: int
    recurrence_group_id: UUID | None
    recurrence_rule: str | None
    status: SessionStatus
    bookings: list[AdminPlanningReorganizationBookingOut] = Field(default_factory=list)


class AdminPlanningReorganizationOut(BaseModel):
    school_years: list[str] = Field(default_factory=list)
    locations: list[AdminPlanningReorganizationLocationOut] = Field(default_factory=list)
    available_days: list[date] = Field(default_factory=list)
    selected_school_year: str
    selected_location_id: UUID | None
    selected_day: date | None
    sessions: list[AdminPlanningReorganizationSessionOut] = Field(default_factory=list)


class AdminPlanningReorganizationMoveRequest(BaseModel):
    booking_id: UUID
    target_session_id: UUID
    scope: Literal["single", "series_future"] = "single"


class AdminPlanningReorganizationMoveOut(BaseModel):
    moved_count: int
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


class AdminPlanningSimulationSlotOut(BaseModel):
    slot_key: str
    location_id: UUID | None = None
    location_name: str
    location_timezone: str | None = None
    course_type_id: UUID | None = None
    course_type_name: str
    course_type_color_hex: str | None = None
    course_type_mode: DeliveryMode | None = None
    weekday: int
    weekday_label: str
    start_time: str
    end_time: str
    first_date: date | None = None
    last_date: date | None = None
    occurrence_count: int = 0
    live_session_count: int = 0
    capacity: int | None = None
    capacity_min: int | None = None
    capacity_max: int | None = None
    booked_count: int = 0
    approved_quotes_count: int = 0
    pending_quotes_count: int = 0
    draft_quotes_count: int = 0
    projected_count: int = 0
    remaining_capacity: int | None = None
    fill_rate: float | None = None
    projected_fill_rate: float | None = None
    quote_only: bool = False
    booked_students: list[str] = Field(default_factory=list)
    approved_quote_students: list[str] = Field(default_factory=list)
    pending_quote_students: list[str] = Field(default_factory=list)
    draft_quote_students: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AdminPlanningSimulationSummaryOut(BaseModel):
    location_count: int
    slot_count: int
    course_type_count: int
    booked_count: int
    approved_quotes_count: int
    pending_quotes_count: int
    draft_quotes_count: int
    quote_only_slot_count: int


class AdminPlanningSimulationOut(BaseModel):
    school_year_label: str
    available_school_years: list[str] = Field(default_factory=list)
    location_filter_id: UUID | None = None
    activity_filter_id: UUID | None = None
    activity_group_filter: str | None = None
    generated_at: datetime
    summary: AdminPlanningSimulationSummaryOut
    slots: list[AdminPlanningSimulationSlotOut] = Field(default_factory=list)
