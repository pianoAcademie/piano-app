from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.catalog import BookingStatus, SessionStatus
from app.models.plan import PlanKind, SubscriptionStatus
from app.models.user import ClientKind
from app.models.user import ClientStatus, UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    first_course_at: datetime | None
    portal_contact_visible: bool
    email_opt_in: bool
    sms_opt_in: bool
    lesson_reminder_email_opt_in: bool
    lesson_reminder_sms_opt_in: bool
    residence_country: str
    preferred_currency: str
    timezone: str
    client_status: ClientStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClientMeUpdateRequest(BaseModel):
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
    important_info: str | None = Field(default=None, min_length=1, max_length=1000)
    portal_contact_visible: bool | None = None
    email_opt_in: bool | None = None
    sms_opt_in: bool | None = None
    lesson_reminder_email_opt_in: bool | None = None
    lesson_reminder_sms_opt_in: bool | None = None
    residence_country: str | None = Field(default=None, min_length=2, max_length=2)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, min_length=2, max_length=100)


class FamilyMemberOut(BaseModel):
    id: UUID
    email: str | None = None
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


class FamilyLinkOut(BaseModel):
    id: UUID
    adult: FamilyMemberOut
    child: FamilyMemberOut
    relationship_label: str | None
    is_billing_recipient: bool
    created_at: datetime
    updated_at: datetime


class FamilyPlanMiniOut(BaseModel):
    id: UUID
    code: str
    name: str
    kind: PlanKind


class FamilySessionMiniOut(BaseModel):
    id: UUID
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    status: SessionStatus


class FamilySubscriptionOut(BaseModel):
    id: UUID
    owner_client_id: UUID
    owner_display_name: str
    owner_email: str
    status: SubscriptionStatus
    started_at: datetime
    ends_at: datetime | None
    next_payment_at: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    credits_initial: int | None
    credits_remaining: int | None
    auto_renew: bool
    bookings_blocked: bool = False
    billing_method_code: str | None = None
    last_successful_charge_at: datetime | None = None
    payment_alert_started_at: datetime | None = None
    pre_termination_at: datetime | None = None
    direct_payment_recovery_url: str | None = None
    suspension_starts_at: datetime | None = None
    suspension_ends_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    cancellation_effective_at: datetime | None = None
    plan: FamilyPlanMiniOut
    entitlement_course_type_ids: list[UUID] = Field(default_factory=list)
    entitlement_course_type_names: list[str] = Field(default_factory=list)


class FamilyBookingOut(BaseModel):
    id: UUID
    owner_client_id: UUID
    owner_display_name: str
    owner_email: str
    client_plan_subscription_id: UUID | None
    status: BookingStatus
    booked_at: datetime
    cancelled_at: datetime | None
    cancellation_reason: str | None
    price_excl_vat_snapshot: Decimal
    vat_rate_snapshot: Decimal
    vat_amount_snapshot: Decimal
    total_incl_vat_snapshot: Decimal
    currency_snapshot: str
    session: FamilySessionMiniOut


class ClientFamilyOverviewOut(BaseModel):
    me: FamilyMemberOut
    links_as_adult: list[FamilyLinkOut]
    links_as_child: list[FamilyLinkOut]
    billing_recipient_adult_id: UUID | None
    managed_client_ids: list[UUID]
    subscriptions: list[FamilySubscriptionOut]
    bookings: list[FamilyBookingOut]


class ClientContentLessonOut(BaseModel):
    id: UUID
    external_id: str
    slug: str | None
    title: str
    position: int
    summary: str | None
    content_html: str | None
    video_url: str | None
    resource_url: str | None
    status: str


class ClientContentSectionOut(BaseModel):
    id: UUID
    external_id: str
    title: str
    position: int
    lessons: list[ClientContentLessonOut] = Field(default_factory=list)


class ClientContentMemberAccessOut(BaseModel):
    member_id: UUID
    member_display_name: str
    member_email: str
    course_type_ids: list[UUID] = Field(default_factory=list)
    course_type_names: list[str] = Field(default_factory=list)


class ClientContentCourseOut(BaseModel):
    id: UUID
    provider: str
    external_id: str
    slug: str | None
    title: str
    summary: str | None
    level_code: str | None
    status: str
    cover_image_url: str | None
    last_synced_at: datetime | None
    member_accesses: list[ClientContentMemberAccessOut] = Field(default_factory=list)
    sections: list[ClientContentSectionOut] = Field(default_factory=list)
    standalone_lessons: list[ClientContentLessonOut] = Field(default_factory=list)


class ClientMessageScope(str, enum.Enum):
    LAST_3_MONTHS = "LAST_3_MONTHS"
    CURRENT_YEAR = "CURRENT_YEAR"
    ALL = "ALL"


class ClientMessageOut(BaseModel):
    id: UUID
    owner_client_id: UUID
    owner_display_name: str
    recipient_email: str | None = None
    channel: str
    booking_id: UUID | None = None
    session_id: UUID | None = None
    session_title: str | None = None
    scheduled_for_utc: datetime
    sent_at: datetime | None
    status: str
    provider_message_id: str | None
    error_message: str | None
    subject_preview: str
    content_preview: str | None = None
    content_html: str | None = None


class ClientPaymentOut(BaseModel):
    id: str
    owner_client_id: UUID
    owner_display_name: str
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
    payment_url: str | None = None


class ClientInvoiceOut(BaseModel):
    id: str
    owner_client_id: UUID
    owner_display_name: str
    invoice_number: str
    issued_at: datetime
    source: str
    status: str
    label: str
    total_incl_vat: Decimal
    currency: str
    reference: str | None
    download_url: str | None = None
    payment_url: str | None = None
    included_payment_keys: list[str] = Field(default_factory=list)


class ClientPaymentCheckoutOut(BaseModel):
    payment_id: str
    checkout_url: str
    provider_reference: str | None = None


class ClientSessionCheckoutOut(BaseModel):
    booking_id: UUID
    booking_status: str
    checkout_url: str | None = None
    invoice_status: str | None = None


class ClientSessionFormulaOptionOut(BaseModel):
    formula_id: UUID
    formula_code: str
    formula_type: PlanKind
    name: str
    description: str | None = None
    price_ttc: Decimal | None = None
    currency: str
    frequency_label: str | None = None
    restriction_labels: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)


class ClientSessionReservationMemberOptionOut(BaseModel):
    member_id: UUID
    member_display_name: str
    member_kind: ClientKind
    booking_id: UUID | None = None
    booking_status: str | None = None
    action_code: str
    action_label: str
    status_label: str
    reason: str | None = None
    has_credit_coverage: bool = False
    coverage_source: str | None = None
    direct_payment_amount_ttc: Decimal | None = None
    direct_payment_currency: str | None = None
    formula_options: list[ClientSessionFormulaOptionOut] = Field(default_factory=list)


class ClientSessionReservationOptionsOut(BaseModel):
    session_id: UUID
    session_title: str
    session_status: str
    is_full: bool
    online_booking_enabled: bool
    waitlist_enabled: bool
    members: list[ClientSessionReservationMemberOptionOut] = Field(default_factory=list)


class ClientSessionPurchaseCatalogOut(BaseModel):
    session_id: UUID
    formula_options: list[ClientSessionFormulaOptionOut] = Field(default_factory=list)
    direct_payment_amount_ttc: Decimal | None = None
    direct_payment_currency: str | None = None


class ClientPaymentConfirmOut(BaseModel):
    payment_id: str
    subscription_status: str
    last_payment_status: str | None = None
    paid: bool
    cancelled: bool
    failed: bool
    processed: bool
    message: str | None = None
