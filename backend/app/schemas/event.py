from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from app.models.event import (
    SchoolEventAudience,
    SchoolEventPaymentMode,
    SchoolEventRegistrationMode,
    SchoolEventRegistrationStatus,
    SchoolEventSlotStatus,
    SchoolEventStatus,
)


class SchoolEventCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=160)
    title_fr: str = Field(min_length=2, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    description_fr: str | None = None
    description_en: str | None = None
    category: str = Field(default="AUTRE", min_length=2, max_length=80)
    image_url: str | None = None
    status: SchoolEventStatus = SchoolEventStatus.DRAFT
    audience: SchoolEventAudience = SchoolEventAudience.CLIENTS
    registration_mode: SchoolEventRegistrationMode = SchoolEventRegistrationMode.GROUP_SESSION
    payment_mode: SchoolEventPaymentMode = SchoolEventPaymentMode.FREE
    location_id: UUID | None = None
    event_venue_id: UUID | None = None
    booking_opens_at: datetime | None = None
    booking_closes_at: datetime | None = None
    price_ttc: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    max_per_family: int = Field(default=6, ge=1, le=100)
    waitlist_enabled: bool = True
    show_remaining_seats: bool = True
    cancellation_deadline_hours: int = Field(default=24, ge=0, le=8760)
    collect_piece_info: bool = False
    collect_photo_consent: bool = False
    collect_performer_booking: bool = False
    confirmation_message_fr: str | None = None
    confirmation_message_en: str | None = None

    @model_validator(mode="after")
    def validate_booking_window(self) -> "SchoolEventCreateRequest":
        paris_timezone = ZoneInfo("Europe/Paris")
        if self.booking_opens_at and self.booking_opens_at.tzinfo is None:
            self.booking_opens_at = self.booking_opens_at.replace(tzinfo=paris_timezone).astimezone(timezone.utc)
        if self.booking_closes_at and self.booking_closes_at.tzinfo is None:
            self.booking_closes_at = self.booking_closes_at.replace(tzinfo=paris_timezone).astimezone(timezone.utc)
        if self.booking_opens_at and self.booking_closes_at and self.booking_opens_at >= self.booking_closes_at:
            raise ValueError("booking_opens_at must be before booking_closes_at")
        if self.payment_mode == SchoolEventPaymentMode.FREE:
            self.price_ttc = Decimal("0")
        return self


class SchoolEventUpdateRequest(SchoolEventCreateRequest):
    pass


class SchoolEventSlotCreateRequest(BaseModel):
    start_at_utc: datetime
    end_at_utc: datetime
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=100)
    capacity_max: int = Field(ge=1, le=10000)
    admin_capacity_max: int | None = Field(default=None, ge=1, le=10000)
    location_id: UUID | None = None
    event_venue_id: UUID | None = None
    label: str | None = Field(default=None, max_length=180)

    @model_validator(mode="after")
    def validate_dates(self) -> "SchoolEventSlotCreateRequest":
        try:
            event_timezone = ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("timezone is invalid") from exc
        if self.start_at_utc.tzinfo is None:
            self.start_at_utc = self.start_at_utc.replace(tzinfo=event_timezone).astimezone(timezone.utc)
        if self.end_at_utc.tzinfo is None:
            self.end_at_utc = self.end_at_utc.replace(tzinfo=event_timezone).astimezone(timezone.utc)
        if self.start_at_utc >= self.end_at_utc:
            raise ValueError("start_at_utc must be before end_at_utc")
        if self.admin_capacity_max is None:
            self.admin_capacity_max = self.capacity_max
        if self.admin_capacity_max < self.capacity_max:
            raise ValueError("admin_capacity_max must be greater than or equal to capacity_max")
        return self


class SchoolEventSlotCapacityUpdateRequest(BaseModel):
    capacity_max: int = Field(ge=1, le=10000)
    admin_capacity_max: int = Field(ge=1, le=10000)

    @model_validator(mode="after")
    def validate_capacities(self) -> "SchoolEventSlotCapacityUpdateRequest":
        if self.admin_capacity_max < self.capacity_max:
            raise ValueError("admin_capacity_max must be greater than or equal to capacity_max")
        return self


class SchoolEventLocationOut(BaseModel):
    id: UUID
    name: str
    timezone: str
    is_online: bool
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country_code: str | None = None


class SchoolEventVenueCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    address_line: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=120)
    country_code: str = Field(default="FR", min_length=2, max_length=2)
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=100)
    is_online: bool = False

    @model_validator(mode="after")
    def validate_timezone(self) -> "SchoolEventVenueCreateRequest":
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("timezone is invalid") from exc
        return self


class SchoolEventVenueOut(SchoolEventLocationOut):
    is_active: bool


class SchoolEventPriceTierCreateRequest(BaseModel):
    label_fr: str = Field(min_length=1, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    price_ttc: Decimal = Field(ge=0)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_online_booking_enabled: bool = True


class SchoolEventPriceTierUpdateRequest(BaseModel):
    is_online_booking_enabled: bool


class SchoolEventPriceTierOut(BaseModel):
    id: UUID
    event_id: UUID
    label_fr: str
    label_en: str | None
    price_ttc: Decimal
    sort_order: int
    is_online_booking_enabled: bool
    is_active: bool


class SchoolEventImageUploadOut(BaseModel):
    image_url: str
    storage_key: str


class SchoolEventSlotOut(BaseModel):
    id: UUID
    event_id: UUID
    label: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    timezone: str
    capacity_max: int
    admin_capacity_max: int
    booked_count: int
    seats_remaining: int
    admin_seats_remaining: int
    waitlist_count: int
    status: SchoolEventSlotStatus
    location: SchoolEventLocationOut | None


class SchoolEventOut(BaseModel):
    id: UUID
    slug: str
    title_fr: str
    title_en: str | None
    description_fr: str | None
    description_en: str | None
    category: str
    image_url: str | None
    status: SchoolEventStatus
    audience: SchoolEventAudience
    registration_mode: SchoolEventRegistrationMode
    payment_mode: SchoolEventPaymentMode
    location: SchoolEventLocationOut | None
    booking_opens_at: datetime | None
    booking_closes_at: datetime | None
    price_ttc: Decimal
    price_tiers: list[SchoolEventPriceTierOut]
    currency: str
    max_per_family: int
    waitlist_enabled: bool
    show_remaining_seats: bool
    cancellation_deadline_hours: int
    collect_piece_info: bool
    collect_photo_consent: bool
    collect_performer_booking: bool
    confirmation_message_fr: str | None
    confirmation_message_en: str | None
    reminder_hours_before_start: int
    reminder_sent_count: int
    slots: list[SchoolEventSlotOut]
    registration_count: int
    waitlist_count: int
    created_at: datetime
    updated_at: datetime


class SchoolEventGuestTicketRequest(BaseModel):
    participant_name: str = Field(min_length=2, max_length=255)
    price_tier_id: UUID | None = None


class SchoolEventRegistrationCreateRequest(BaseModel):
    slot_id: UUID
    participant_user_ids: list[UUID] = Field(default_factory=list, max_length=100)
    guest_names: list[str] = Field(default_factory=list, max_length=100)
    guest_tickets: list[SchoolEventGuestTicketRequest] = Field(default_factory=list, max_length=100)
    price_tier_id: UUID | None = None
    participant_price_tier_ids: dict[UUID, UUID] = Field(default_factory=dict)
    guest_price_tier_id: UUID | None = None
    piece_info: str | None = Field(default=None, max_length=1000)
    photo_consent: bool | None = None


class SchoolEventPublicTicketRequest(BaseModel):
    participant_name: str = Field(min_length=2, max_length=255)
    price_tier_id: UUID | None = None


class SchoolEventPublicRegistrationCreateRequest(BaseModel):
    request_id: UUID
    slot_id: UUID
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str | None = Field(default=None, max_length=30)
    language: str = Field(default="fr", max_length=8)
    tickets: list[SchoolEventPublicTicketRequest] = Field(min_length=1, max_length=20)
    terms_accepted: bool
    website: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_public_booking(self) -> "SchoolEventPublicRegistrationCreateRequest":
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()
        self.email = self.email.strip().lower()
        self.phone = self.phone.strip() if self.phone else None
        self.language = "en" if self.language.strip().lower().startswith("en") else "fr"
        for ticket in self.tickets:
            ticket.participant_name = ticket.participant_name.strip()
        return self


class SchoolEventRegistrationOut(BaseModel):
    id: UUID
    group_id: UUID
    event_id: UUID
    event_slug: str
    event_title_fr: str
    event_title_en: str | None
    slot_id: UUID
    slot_label: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    timezone: str
    location_name: str | None
    booker_user_id: UUID | None
    public_booker_first_name: str | None
    public_booker_last_name: str | None
    public_booker_email: str | None
    public_booker_phone: str | None
    participant_user_id: UUID | None
    participant_display_name: str
    party_size: int
    guest_names: list[str]
    answers: dict[str, object]
    status: SchoolEventRegistrationStatus
    unit_price_ttc_snapshot: Decimal
    price_tier_id: UUID | None
    price_tier_label_snapshot: str | None
    total_ttc_snapshot: Decimal
    currency_snapshot: str
    payment_provider: str | None
    payment_reference: str | None
    payment_hold_expires_at: datetime | None
    booked_at: datetime
    cancelled_at: datetime | None
    checked_in_at: datetime | None


class SchoolEventRegistrationCreateOut(BaseModel):
    group_id: UUID
    status: SchoolEventRegistrationStatus
    registrations: list[SchoolEventRegistrationOut]
    checkout_url: str | None = None


class SchoolEventRegistrationStatusUpdateRequest(BaseModel):
    status: SchoolEventRegistrationStatus


class SchoolEventAdminRegistrationCreateRequest(BaseModel):
    slot_id: UUID
    participant_user_id: UUID
    price_tier_id: UUID | None = None
    send_confirmation: bool = True


class SchoolEventAdminParticipantOptionOut(BaseModel):
    id: UUID
    display_name: str
    email: str
    client_kind: str
