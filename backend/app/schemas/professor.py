from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import enum
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


class ProfessorSessionOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    start_at_utc: datetime
    end_at_utc: datetime
    status: SessionStatus
    capacity_max: int
    booked_count: int
    zoom_link: str | None
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


class ProfessorSessionMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    subject: str
    body: str
    body_format: MessageFormat
    recipient_count: int
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
