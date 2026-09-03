from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.catalog import BookingStatus, SessionStatus
from app.models.ops import MessageFormat
from app.models.payout import PayoutStatus
from app.models.professor_contract import ProfessorContractLineMode


class ProfessorMessageChannel(str, enum.Enum):
    GROUP_STUDENTS = "GROUP_STUDENTS"


class ProfessorSessionCourseTypeOut(BaseModel):
    id: UUID
    code: str
    name: str


class ProfessorSessionLocationOut(BaseModel):
    id: UUID
    code: str
    name: str
    is_online: bool


class ProfessorSessionStudentOut(BaseModel):
    booking_id: UUID
    user_id: UUID
    first_name: str | None
    last_name: str | None
    display_name: str
    attendance_status: BookingStatus
    is_trial_course: bool
    is_first_course: bool
    internal_note: str | None = None
    repertoire: list[dict[str, Any]] = Field(default_factory=list)


class ProfessorSessionOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    internal_note: str | None = None
    start_at_utc: datetime
    end_at_utc: datetime
    status: SessionStatus
    capacity_max: int
    booked_count: int
    zoom_link: str | None
    habitual_teacher_id: UUID | None = None
    habitual_teacher_display_name: str | None = None
    substitute_teacher_id: UUID | None = None
    substitute_teacher_display_name: str | None = None
    effective_teacher_id: UUID | None = None
    effective_teacher_display_name: str | None = None
    effective_teacher_ids: list[UUID] = Field(default_factory=list)
    effective_teacher_display_names: list[str] = Field(default_factory=list)
    students: list[ProfessorSessionStudentOut] = Field(default_factory=list)
    course_type: ProfessorSessionCourseTypeOut
    location: ProfessorSessionLocationOut


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
    can_view_upcoming_trials: bool
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


class ProfessorMeOut(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone: str | None
    zoom_link: str | None
    spoken_languages: list[str]
    is_coach: bool
    active: bool
    payout_currency: str
    daily_schedule_email_enabled: bool
    daily_schedule_email_time: str
    daily_schedule_skip_if_no_course: bool
    permissions: ProfessorPermissionOut


class ProfessorAttendancePendingOut(BaseModel):
    session_id: UUID
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    location_name: str
    course_type_name: str
    pending_students_count: int
    total_students_count: int


class ProfessorSessionMessageCreateRequest(BaseModel):
    subject: str
    body: str
    body_format: MessageFormat = MessageFormat.TEXT
    recipient_scope: str = "GROUP"
    target_user_id: UUID | None = None


class ProfessorInternalNoteUpdateRequest(BaseModel):
    internal_note: str | None = Field(default=None, max_length=12000)


class ProfessorInternalNoteOut(BaseModel):
    session_id: UUID
    booking_id: UUID | None = None
    internal_note: str | None = None


class ProfessorInternalNoteListOut(BaseModel):
    id: str
    note_type: str
    body: str
    session_id: UUID
    booking_id: UUID | None = None
    student_id: UUID | None = None
    student_display_name: str | None = None
    session_title: str
    session_start_at_utc: datetime
    session_timezone: str
    course_type_name: str
    location_id: UUID
    location_name: str


class ProfessorLocalIntakeTaskOut(BaseModel):
    id: UUID
    received_at: datetime
    local_confirmation_status: str
    prospect_label: str
    child_label: str | None = None
    requested_summary: str | None = None
    detected_location: str | None = None
    local_confirmation_schedule_snapshot: str | None = None
    local_confirmation_partition_snapshot: str | None = None
    local_confirmation_confirmed_at: datetime | None = None


class ProfessorLocalIntakeSlotOut(BaseModel):
    session_id: UUID
    label: str
    start_at_utc: datetime
    end_at_utc: datetime
    timezone: str
    course_type_name: str
    location_name: str
    capacity_max: int
    booked_count: int
    seats_remaining: int
    recurrence_group_id: UUID | None = None


class ProfessorLocalIntakePartitionOut(BaseModel):
    product_id: UUID
    title: str
    category_name: str | None = None
    real_quantity: int
    estimated_quantity: int


class ProfessorLocalIntakeAnswerOut(BaseModel):
    label: str
    value: str


class ProfessorLocalIntakeDetailOut(ProfessorLocalIntakeTaskOut):
    normalized_payload_json: dict[str, object] = Field(default_factory=dict)
    answers: list[ProfessorLocalIntakeAnswerOut] = Field(default_factory=list)
    slot_options: list[ProfessorLocalIntakeSlotOut] = Field(default_factory=list)
    partition_options: list[ProfessorLocalIntakePartitionOut] = Field(default_factory=list)
    local_confirmation_session_id: UUID | None = None
    local_confirmation_product_id: UUID | None = None
    local_confirmation_partition_not_required: bool = False
    local_confirmation_comment: str | None = None


class ProfessorLocalIntakeConfirmRequest(BaseModel):
    session_id: UUID
    product_id: UUID | None = None
    custom_partition: str | None = Field(default=None, max_length=500)
    partition_not_required: bool = False
    comment: str | None = Field(default=None, max_length=2000)


class ProfessorSessionMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    subject: str
    body: str
    body_format: MessageFormat
    recipient_count: int
    sent_at: datetime


class ProfessorInboxMessageOut(BaseModel):
    id: UUID
    channel: str
    subject: str
    body: str
    body_format: MessageFormat
    status: str
    sent_at: datetime


class ProfessorSessionMessageSendOut(BaseModel):
    message_id: UUID
    session_id: UUID
    recipient_count: int
    sent_at: datetime


class ProfessorMarkAbsenceRequest(BaseModel):
    notify_students: bool = False
    students_subject: str | None = None
    students_message: str | None = None
    students_format: MessageFormat = MessageFormat.TEXT


class ProfessorSessionOperationOut(BaseModel):
    session_id: UUID
    status: SessionStatus
    cancel_reason: str | None
    notified_students: int = 0


class ProfessorPayoutOut(BaseModel):
    payout_id: UUID
    session_id: UUID
    session_title: str
    session_start_at_utc: datetime
    session_end_at_utc: datetime
    location_name: str
    course_type_name: str
    duration_hours: Decimal
    amount_snapshot: Decimal
    currency_snapshot: str
    payout_status: PayoutStatus
    paid_at: datetime | None


class ProfessorBalanceOut(BaseModel):
    currency: str
    pending_amount: Decimal
    approved_amount: Decimal
    paid_amount: Decimal
    total_amount: Decimal
    pending_sessions: int
    approved_sessions: int
    paid_sessions: int


class ProfessorContractGridRuleOut(BaseModel):
    min_students: int
    max_students: int | None
    hourly_rate: Decimal


class ProfessorContractGridLineOut(BaseModel):
    course_type_id: UUID | None
    course_type_name: str
    service_type: str
    mode: ProfessorContractLineMode
    reference_duration_minutes: int | None
    default_hourly_rate: Decimal | None
    rules: list[ProfessorContractGridRuleOut] = Field(default_factory=list)


class ProfessorContractGridOut(BaseModel):
    grid_id: UUID
    valid_from: date
    valid_to: date | None
    location_code: str | None
    location_label: str
    notes: str | None
    lines: list[ProfessorContractGridLineOut] = Field(default_factory=list)


class TeacherStatementMissingSessionOut(BaseModel):
    session_id: UUID
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    pending_students_count: int
    total_students_count: int


class TeacherStatementLineOut(BaseModel):
    course_type_id: UUID | None
    course_type_label: str
    hours: Decimal
    unit_rate_ht: Decimal
    amount_ht: Decimal
    amount_ttc: Decimal
    meta: dict[str, Any] = Field(default_factory=dict)


class TeacherStatementOut(BaseModel):
    statement_id: UUID | None
    payor_legal_entity_id: UUID
    payor_legal_entity_name: str
    year: int
    month: int
    status: str
    attendance_complete: bool
    currency: str
    totals_ht: Decimal
    totals_vat: Decimal
    totals_ttc: Decimal
    vat_applicable: bool = False
    vat_rate: Decimal | None = None
    dispute_message_last: str | None = None
    external_invoice_sent_at: datetime | None = None
    external_invoice_file_name: str | None = None
    lines: list[TeacherStatementLineOut] = Field(default_factory=list)
    missing_sessions: list[TeacherStatementMissingSessionOut] = Field(default_factory=list)


class AdminTeacherStatementSummaryOut(BaseModel):
    professor_id: UUID
    professor_name: str
    payor_legal_entity_name: str
    year: int
    month: int
    status: str
    attendance_complete: bool
    currency: str
    courses_count: int
    total_hours: Decimal
    totals_ht: Decimal
    totals_vat: Decimal
    totals_ttc: Decimal
    amount_payable: Decimal


class TeacherStatementDisputeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class TeacherStatementDisputeLinesRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    selected_lines: list[str] = Field(default_factory=list)


class TeacherStatementMissingServiceRequest(BaseModel):
    service_date: date
    course_type_id: UUID | None = None
    location_id: UUID | None = None
    attendee_count: int | None = Field(default=None, ge=0, le=300)
    service_label: str | None = Field(default=None, max_length=200)
    student_or_group: str | None = Field(default=None, max_length=200)
    duration_minutes: int | None = Field(default=None, ge=1, le=720)
    modality: str | None = Field(default=None, max_length=80)
    estimated_rate_ht: Decimal | None = None
    comment: str = Field(min_length=1, max_length=4000)


class TeacherInvoiceLineOut(BaseModel):
    id: UUID
    course_type_id: UUID | None
    course_type_label: str
    hours: Decimal
    unit_rate_ht: Decimal
    amount_ht: Decimal
    amount_ttc: Decimal
    meta: dict[str, Any] = Field(default_factory=dict)


class TeacherInvoiceOut(BaseModel):
    id: UUID
    statement_id: UUID
    payor_legal_entity_id: UUID
    payor_legal_entity_name: str
    invoice_number: str
    invoice_date: date
    due_date: date
    is_vat_applicable: bool
    vat_rate: Decimal | None
    totals_ht: Decimal
    totals_vat: Decimal
    totals_ttc: Decimal
    teacher_siret_display: str
    teacher_iban: str
    status: str
    sent_to_accounting_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    lines: list[TeacherInvoiceLineOut] = Field(default_factory=list)


class TeacherApproveStatementsOut(BaseModel):
    generated_invoices: list[TeacherInvoiceOut] = Field(default_factory=list)
    blocked_missing_sessions: list[TeacherStatementMissingSessionOut] = Field(default_factory=list)
