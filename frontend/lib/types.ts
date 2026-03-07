export type AuthLoginResponse = {
  access_token: string;
  token_type: string;
};

export type UserOut = {
  id: string;
  email: string;
  role: "admin" | "prof" | "client";
  client_kind: "ADULT" | "CHILD" | string;
  client_status: "ACTIVE" | "INACTIVE" | "TRIAL" | "PENDING" | "ARCHIVED" | string;
  first_name: string | null;
  last_name: string | null;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  address_country: string;
  phone: string | null;
  mobile_phone_1: string | null;
  mobile_phone_2: string | null;
  home_phone: string | null;
  birth_date: string | null;
  important_info: string | null;
  first_course_at: string | null;
  portal_contact_visible: boolean;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  lesson_reminder_email_opt_in: boolean;
  lesson_reminder_sms_opt_in: boolean;
  email_delivery_status: string;
  email_suspended_at: string | null;
  email_suspension_reason: string | null;
  phone_delivery_status: string;
  phone_suspended_at: string | null;
  phone_suspension_reason: string | null;
  residence_country: string;
  preferred_currency: string;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type CourseTypeOut = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  service_code: string;
  credit_type_id: string | null;
  credit_type_code: string | null;
  credit_type_name: string | null;
  duration_minutes: number;
  color_hex: string;
  mode: string;
  requires_professor: boolean;
  default_capacity: number;
  default_hourly_rate: string | null;
  default_course_rate_ttc: string | null;
  email_reminder_hours_before_start: number | null;
  sms_reminder_hours_before_start: number | null;
  min_booking_notice_hours_override: number | null;
  cancellation_deadline_hours_override: number | null;
  auto_cancel_if_booked_less_than_override: number | null;
  auto_cancel_hours_before_start_override: number | null;
  active: boolean;
};

export type LocationOut = {
  id: string;
  code: string;
  name: string;
  address_line: string | null;
  city: string | null;
  country_code: string;
  is_online: boolean;
  timezone: string;
  active: boolean;
};

export type SessionOut = {
  id: string;
  title: string;
  description: string | null;
  start_at_utc: string;
  end_at_utc: string;
  start_at_local: string;
  end_at_local: string;
  timezone: string;
  session_timezone: string;
  status: string;
  capacity_max: number;
  booked_count: number;
  seats_remaining: number;
  online_booking_enabled: boolean;
  zoom_link: string | null;
  substitute_teacher_id: string | null;
  substitute_teacher_display_name: string | null;
  effective_teacher_id: string | null;
  effective_teacher_display_name: string | null;
  course_type: {
    id: string;
    code: string;
    name: string;
  };
  location: {
    id: string;
    code: string;
    name: string;
    is_online: boolean;
  };
  professor: {
    id: string;
    first_name: string;
    last_name: string;
  } | null;
};

export type PlanOut = {
  id: string;
  code: string;
  name: string;
  kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  credits_count: number | null;
  forfait_start_date: string | null;
  forfait_end_date: string | null;
  monthly_price_excl_vat: string | null;
  currency_code: string | null;
  active: boolean;
};

export type SubscriptionOut = {
  id: string;
  status: string;
  started_at: string;
  ends_at: string | null;
  next_payment_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  credits_initial: number | null;
  credits_remaining: number | null;
  auto_renew: boolean;
  bookings_blocked: boolean;
  billing_method_code: string | null;
  last_successful_charge_at: string | null;
  payment_alert_started_at: string | null;
  pre_termination_at: string | null;
  direct_payment_recovery_url: string | null;
  suspension_starts_at: string | null;
  suspension_ends_at: string | null;
  cancellation_requested_at: string | null;
  cancellation_effective_at: string | null;
  entitlement_course_type_ids: string[];
  entitlement_course_type_names: string[];
  plan: {
    id: string;
    code: string;
    name: string;
    kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  };
};

export type ClientBookingOut = {
  id: string;
  client_plan_subscription_id: string | null;
  status: string;
  booked_at: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  price_excl_vat_snapshot: string;
  vat_rate_snapshot: string;
  vat_amount_snapshot: string;
  total_incl_vat_snapshot: string;
  currency_snapshot: string;
  session: {
    id: string;
    title: string;
    start_at_utc: string;
    end_at_utc: string;
    status: string;
  };
};

export type AdminClientOut = {
  id: string;
  email: string;
  role: "admin" | "prof" | "client";
  client_kind: "ADULT" | "CHILD" | string;
  client_status: "ACTIVE" | "INACTIVE" | "TRIAL" | "PENDING" | "ARCHIVED" | string;
  first_name: string | null;
  last_name: string | null;
  family_name: string | null;
  group_ids: string[];
  group_names: string[];
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  address_country: string;
  phone: string | null;
  mobile_phone_1: string | null;
  mobile_phone_2: string | null;
  home_phone: string | null;
  birth_date: string | null;
  important_info: string | null;
  private_note: string | null;
  first_course_at: string | null;
  portal_contact_visible: boolean;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  lesson_reminder_email_opt_in: boolean;
  lesson_reminder_sms_opt_in: boolean;
  email_delivery_status: string;
  email_suspended_at: string | null;
  email_suspension_reason: string | null;
  phone_delivery_status: string;
  phone_suspended_at: string | null;
  phone_suspension_reason: string | null;
  residence_country: string;
  preferred_currency: string;
  timezone: string;
  is_active: boolean;
  next_session_start_at_utc: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminClientGroupOut = {
  id: string;
  code: string;
  name: string;
  active: boolean;
  members_count: number;
};

export type AdminClientSubscriptionOut = {
  id: string;
  status: "ACTIVE" | "PAUSED" | "CANCELLED" | "EXPIRED" | string;
  started_at: string;
  ends_at: string | null;
  next_payment_at: string | null;
  credits_initial: number | null;
  credits_remaining: number | null;
  auto_renew: boolean;
  billing_method_code: string | null;
  payment_provider_subscription_ref: string | null;
  payment_provider_customer_ref: string | null;
  payment_provider_mandate_ref: string | null;
  forfait_loyalty_discount_per_hour_ttc: string | null;
  forfait_family_discount_per_hour_ttc: string | null;
  forfait_short_commitment_supplement_per_hour_ttc: string | null;
  forfait_activity_pricing: Array<{
    course_type_id: string;
    course_type_name: string;
    base_hourly_rate_ttc: string | null;
    loyalty_discount_per_hour_ttc: string;
    family_discount_per_hour_ttc: string;
    short_commitment_supplement_per_hour_ttc: string;
    second_course_weekly_discount_per_hour_ttc: string;
    effective_hourly_rate_ttc: string | null;
  }>;
  last_payment_at: string | null;
  last_payment_status: string | null;
  suspension_starts_at: string | null;
  suspension_ends_at: string | null;
  suspension_duration_value: number | null;
  suspension_duration_unit: string | null;
  cancellation_requested_at: string | null;
  cancellation_effective_at: string | null;
  plan: {
    id: string;
    code: string;
    name: string;
    kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  };
  estimated_price_excl_vat: string | null;
  estimated_vat_rate: string | null;
  estimated_vat_amount: string | null;
  estimated_total_incl_vat: string | null;
  estimated_currency: string | null;
};

export type AdminImpersonationStartOut = {
  target_user_id: string;
  target_role: "client" | "teacher";
  target_display_name: string;
  access_token: string;
  expires_in_seconds: number;
  redirect_path: string;
};

export type AdminClientBookingOut = {
  id: string;
  session_id: string;
  session_title: string;
  session_status: string;
  session_start_at_utc: string;
  session_end_at_utc: string;
  course_type_name: string;
  location_name: string;
  client_plan_subscription_id: string | null;
  plan_name: string | null;
  status: string;
  booked_at: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  price_excl_vat_snapshot: string;
  vat_rate_snapshot: string;
  vat_amount_snapshot: string;
  total_incl_vat_snapshot: string;
  currency_snapshot: string;
};

export type AdminClientMessageOut = {
  id: string;
  booking_id: string | null;
  session_id: string | null;
  session_title: string | null;
  channel: "EMAIL" | "SMS";
  source: string | null;
  recipient: string | null;
  scheduled_for_utc: string;
  sent_at: string | null;
  status: string;
  provider_message_id: string | null;
  error_message: string | null;
  subject_preview: string;
  body_preview: string | null;
  body_full: string | null;
  body_format: "TEXT" | "HTML";
  can_forward: boolean;
};

export type AdminClientPaymentOut = {
  id: string;
  source: "PLAN_PURCHASE" | "BOOKING" | "MANUAL" | string;
  occurred_at: string;
  label: string;
  status: string;
  amount_excl_vat: string;
  vat_rate: string;
  vat_amount: string;
  total_incl_vat: string;
  currency: string;
  reference: string | null;
  seller_legal_entity_id: string | null;
  billing_entity: string | null;
  invoice_number: string | null;
  invoice_status: string | null;
  invoice_note_id: string | null;
  refunded_at: string | null;
  refund_reason: string | null;
  payment_method_code: string | null;
  payment_method_label: string | null;
  manual_transaction_type: string | null;
  student_user_id: string | null;
  description: string | null;
  category: string | null;
  can_edit: boolean;
  can_cancel: boolean;
  locked_by_invoice_number: string | null;
};

export type AdminClientManualCreditOut = {
  id: string | null;
  credit_type_id: string;
  credit_type_code: string | null;
  credit_type_name: string | null;
  credits_count: number;
  updated_at: string | null;
};

export type AdminClientNoteOut = {
  id: string;
  user_id: string;
  author_user_id: string | null;
  author_display_name: string;
  entry_type: string;
  message: string;
  created_at: string;
};

export type AdminRangeInvoiceOut = {
  note_id: string;
  invoice_number: string;
  issued_date: string;
  due_date: string;
  no_due_date: boolean;
  start_date: string;
  end_date: string;
  layout: "DETAILED" | "COMPILED";
  generation_mode: "MANUAL" | "AUTO";
  group_adjustments_by_type: boolean;
  include_discount_adjustments: boolean;
  include_supplement_adjustments: boolean;
  auto_cycle_start_date: string | null;
  auto_period_scope: "FUTURE" | "PAST";
  auto_frequency: "WEEKLY" | "MONTHLY";
  auto_repeat_every: number;
  auto_layout_style: "NORMAL" | "CONDENSED";
  auto_include_previous_balance: boolean;
  auto_send_email: boolean;
  auto_footer_note: string | null;
  auto_exclude_pack_subscription_lines: boolean;
  include_pending: boolean;
  include_cancelled: boolean;
  totals_by_currency: Record<string, string>;
  invoice_status: "ISSUED" | "PAID" | "CANCELLED";
  emailed_at: string | null;
  reminded_at: string | null;
  public_note: string | null;
  private_note: string | null;
  related_invoices: AdminRangeInvoiceReferenceOut[];
};

export type AdminClientAutoInvoiceRuleOut = {
  id: string;
  client_id: string;
  legal_entity_id: string;
  cycle_start_date: string;
  frequency: "MONTHLY" | "QUARTERLY" | "YEARLY";
  billing_timing: "UPCOMING_LESSONS" | "PREVIOUS_LESSONS";
  due_date_rule_type: "SAME_DAY_ISSUE" | "X_DAYS_AFTER_ISSUE";
  due_date_days_offset: number | null;
  include_pending_lines: boolean;
  include_cancelled_lines: boolean;
  next_run_date: string;
  preview_period_start_date: string;
  preview_period_end_date: string;
  preview_due_date: string;
  last_generated_at: string | null;
  status: "ACTIVE" | "PAUSED" | "ARCHIVED";
  created_at: string;
  updated_at: string;
};

export type AdminRangeInvoiceReferenceOut = {
  note_id: string;
  invoice_number: string;
  billing_entity: string | null;
  seller_legal_entity_id: string | null;
  split_part_index: number;
  split_part_count: number;
};

export type AdminRangeInvoiceEmailOut = {
  note_id: string;
  kind: "INVOICE" | "REMINDER";
  sent_at: string;
  message_id: string | null;
  recipients: string[];
};

export type AdminRangeInvoiceEmailPreviewOut = {
  note_id: string;
  kind: "INVOICE" | "REMINDER";
  to_emails: string[];
  subject: string;
  body: string;
  body_format: "TEXT" | "HTML";
};

export type FamilyMemberOut = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  mobile_phone_1: string | null;
  mobile_phone_2: string | null;
  home_phone: string | null;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  address_country: string;
  client_kind: "ADULT" | "CHILD" | string;
  is_active: boolean;
};

export type AdminClientPasswordEmailTemplateOut = {
  subject: string;
  body: string;
  updated_at: string | null;
};

export type FamilyLinkOut = {
  id: string;
  adult: FamilyMemberOut;
  child: FamilyMemberOut;
  relationship_label: string | null;
  is_billing_recipient: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminClientFamilyOut = {
  client_id: string;
  client_kind: "ADULT" | "CHILD" | string;
  links_as_adult: FamilyLinkOut[];
  links_as_child: FamilyLinkOut[];
  billing_recipient_adult_id: string | null;
};

export type ClientFamilyOverviewOut = {
  me: FamilyMemberOut;
  links_as_adult: FamilyLinkOut[];
  links_as_child: FamilyLinkOut[];
  billing_recipient_adult_id: string | null;
  managed_client_ids: string[];
  subscriptions: Array<{
    id: string;
    owner_client_id: string;
    owner_display_name: string;
    owner_email: string;
    status: string;
    started_at: string;
    ends_at: string | null;
    next_payment_at: string | null;
    current_period_start: string | null;
    current_period_end: string | null;
    credits_initial: number | null;
    credits_remaining: number | null;
    auto_renew: boolean;
    bookings_blocked: boolean;
    billing_method_code: string | null;
    last_successful_charge_at: string | null;
    payment_alert_started_at: string | null;
    pre_termination_at: string | null;
    direct_payment_recovery_url: string | null;
    suspension_starts_at: string | null;
    suspension_ends_at: string | null;
    cancellation_requested_at: string | null;
    cancellation_effective_at: string | null;
    entitlement_course_type_ids: string[];
    entitlement_course_type_names: string[];
    plan: {
      id: string;
      code: string;
      name: string;
      kind: "PACK" | "SUBSCRIPTION" | string;
    };
  }>;
  bookings: Array<{
    id: string;
    owner_client_id: string;
    owner_display_name: string;
    owner_email: string;
    client_plan_subscription_id: string | null;
    status: string;
    booked_at: string;
    cancelled_at: string | null;
    cancellation_reason: string | null;
    price_excl_vat_snapshot: string;
    vat_rate_snapshot: string;
    vat_amount_snapshot: string;
    total_incl_vat_snapshot: string;
    currency_snapshot: string;
    session: {
      id: string;
      title: string;
      start_at_utc: string;
      end_at_utc: string;
      status: string;
    };
  }>;
};

export type ClientMessageOut = {
  id: string;
  owner_client_id: string;
  owner_display_name: string;
  channel: string;
  booking_id: string;
  session_id: string;
  session_title: string;
  scheduled_for_utc: string;
  sent_at: string | null;
  status: string;
  provider_message_id: string | null;
  error_message: string | null;
  subject_preview: string;
  content_preview: string | null;
};

export type ClientPaymentOut = {
  id: string;
  owner_client_id: string;
  owner_display_name: string;
  source: string;
  occurred_at: string;
  label: string;
  status: string;
  amount_excl_vat: string;
  vat_rate: string;
  vat_amount: string;
  total_incl_vat: string;
  currency: string;
  reference: string | null;
  payment_url: string | null;
};

export type ClientInvoiceOut = {
  id: string;
  owner_client_id: string;
  owner_display_name: string;
  invoice_number: string;
  issued_at: string;
  source: string;
  status: string;
  label: string;
  total_incl_vat: string;
  currency: string;
  reference: string | null;
  download_url: string | null;
  payment_url: string | null;
  included_payment_keys: string[];
};

export type ClientPaymentCheckoutOut = {
  payment_id: string;
  checkout_url: string;
  provider_reference: string | null;
};

export type ClientPaymentConfirmOut = {
  payment_id: string;
  subscription_status: string;
  last_payment_status: string | null;
  paid: boolean;
  cancelled: boolean;
  failed: boolean;
  processed: boolean;
  message: string | null;
};

export type AdminProfessorOut = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  zoom_link: string | null;
  active: boolean;
};

export type ProfessorPermissionOut = {
  can_view_dashboard: boolean;
  can_view_clients: boolean;
  can_export_clients: boolean;
  can_create_clients: boolean;
  can_message_clients: boolean;
  can_view_client_reminders: boolean;
  can_create_subscriptions: boolean;
  can_close_subscriptions: boolean;
  can_edit_subscriptions: boolean;
  can_downgrade_subscriptions: boolean;
  can_cancel_subscriptions: boolean;
  can_edit_payments: boolean;
  can_refund_payments: boolean;
  can_cancel_payments: boolean;
  can_manage_mobile_news: boolean;
  can_access_cash_menu: boolean;
  can_view_planning: boolean;
  can_view_all_school_sessions: boolean;
  can_edit_planning: boolean;
  can_force_booking: boolean;
  can_view_admin_dashboard: boolean;
  can_view_admin_reservations: boolean;
  can_access_collaborators: boolean;
  can_configure_app: boolean;
  can_list_payments: boolean;
  can_manage_events: boolean;
  can_view_sportigo_info: boolean;
  can_take_attendance: boolean;
  can_record_payments_with_attendance: boolean;
  can_edit_own_sessions: boolean;
  can_view_pay_details: boolean;
  can_manage_mileage_log: boolean;
  can_view_other_teachers_contacts: boolean;
  can_manage_other_teachers_students_and_sessions: boolean;
  can_view_other_teachers_sessions: boolean;
  can_view_student_parent_addresses_phones: boolean;
  can_view_student_parent_emails: boolean;
  can_view_student_attachments: boolean;
  can_manage_invoices_and_accounts: boolean;
  can_manage_expenses_and_other_income: boolean;
  can_manage_shared_online_resources: boolean;
  can_manage_website_and_news: boolean;
  can_create_and_view_reports: boolean;
};

export type AdminProfessorContractOut = {
  file_name: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
};

export type AdminProfessorContractDeleteOut = {
  deleted: boolean;
};

export type AdminProfessorDetailOut = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  siret: string | null;
  iban: string | null;
  address_line: string | null;
  teacher_invoice_counter: number;
  teacher_is_vat_applicable: boolean;
  teacher_vat_rate: string | null;
  teacher_siret: string | null;
  teacher_iban: string | null;
  teacher_company_name: string | null;
  teacher_company_address: string | null;
  zoom_link: string | null;
  spoken_languages: string[];
  payout_currency: string;
  payout_balance_amount: string;
  payout_balance_currency: string | null;
  payout_balance_as_of: string | null;
  role: "admin" | "prof" | "client";
  is_coach: boolean;
  active: boolean;
  user_is_active: boolean;
  daily_schedule_email_enabled: boolean;
  daily_schedule_email_time: string;
  daily_schedule_skip_if_no_course: boolean;
  contract: AdminProfessorContractOut | null;
  permissions: ProfessorPermissionOut;
  created_at: string;
  updated_at: string;
  last_activation_email_sent_at: string | null;
};

export type AdminProfessorUpdateResult = {
  professor: AdminProfessorDetailOut;
  activation_email_sent: boolean;
  activation_email_message_id: string | null;
};

export type AdminCollaboratorSendPasswordOut = {
  ok: boolean;
  message_id: string | null;
  expires_at: string;
};

export type AdminProfessorRateOut = {
  id: string;
  course_type_id: string | null;
  course_type_name: string;
  currency_code: string;
  hourly_rate: string | null;
  rules: Array<{
    min_students: number;
    max_students: number | null;
    hourly_rate: string;
  }>;
  valid_from: string;
  valid_to: string | null;
};

export type AdminProfessorPayoutLedgerRowOut = {
  session_id: string;
  start_at_utc: string;
  end_at_utc: string;
  course_type_name: string;
  location_name: string;
  duration_hours: string;
  hourly_rate: string | null;
  amount: string | null;
  currency: string | null;
  payout_status: "PENDING" | "APPROVED" | "PAID" | null;
  counted_in_due: boolean;
  cumulative_due: string;
};

export type AdminProfessorPayoutLedgerOut = {
  professor_id: string;
  as_of_date: string;
  currency: string;
  total_due: string;
  rows: AdminProfessorPayoutLedgerRowOut[];
};

export type SalaryPaymentMethod = "BANK_TRANSFER" | "CHEQUE" | "CASH";

export type AdminProfessorSalaryPaymentOut = {
  id: string;
  professor_id: string;
  professor_first_name: string;
  professor_last_name: string;
  professor_email: string;
  reference_date: string;
  payment_date: string;
  invoice_number: string;
  payment_method: SalaryPaymentMethod;
  amount_excl_vat: string;
  amount_incl_vat: string;
  currency_code: string;
  settled_payout_count: number;
  actor_user_id: string | null;
  created_at: string;
};

export type AdminProfessorContractLocationOptionOut = {
  code: string;
  label: string;
};

export type AdminProfessorContractGridRuleOut = {
  id: string;
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
  display_order: number;
};

export type AdminProfessorContractGridLineOut = {
  id: string;
  course_type_id: string | null;
  course_type_name: string;
  service_type: string;
  mode: "PRESENTIEL" | "EN_LIGNE" | "AUTRE" | string;
  reference_duration_minutes: number | null;
  default_hourly_rate: string | null;
  display_order: number;
  rules: AdminProfessorContractGridRuleOut[];
};

export type AdminProfessorContractGridOut = {
  id: string;
  professor_id: string;
  valid_from: string;
  valid_to: string | null;
  location_code: string | null;
  location_label: string;
  notes: string | null;
  is_active_today: boolean;
  lines: AdminProfessorContractGridLineOut[];
  created_at: string;
  updated_at: string;
};

export type ProfessorMeOut = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  zoom_link: string | null;
  spoken_languages: string[];
  is_coach: boolean;
  active: boolean;
  payout_currency: string;
  daily_schedule_email_enabled: boolean;
  daily_schedule_email_time: string;
  daily_schedule_skip_if_no_course: boolean;
  permissions: ProfessorPermissionOut;
};

export type ProfessorSessionStudentOut = {
  booking_id: string;
  user_id: string;
  first_name: string | null;
  last_name: string | null;
  display_name: string;
  attendance_status: "BOOKED" | "WAITLISTED" | "ATTENDED" | "NO_SHOW" | "EXCUSED_ABSENCE" | string;
  is_trial_course: boolean;
  is_first_course: boolean;
};

export type ProfessorSessionOut = {
  id: string;
  title: string;
  description: string | null;
  start_at_utc: string;
  end_at_utc: string;
  status: "SCHEDULED" | "CANCELLED" | "COMPLETED" | string;
  capacity_max: number;
  booked_count: number;
  zoom_link: string | null;
  habitual_teacher_id: string | null;
  habitual_teacher_display_name: string | null;
  substitute_teacher_id: string | null;
  substitute_teacher_display_name: string | null;
  effective_teacher_id: string | null;
  effective_teacher_display_name: string | null;
  students: ProfessorSessionStudentOut[];
  course_type: {
    id: string;
    code: string;
    name: string;
  };
  location: {
    id: string;
    code: string;
    name: string;
    is_online: boolean;
  };
};

export type ProfessorAttendancePendingOut = {
  session_id: string;
  title: string;
  start_at_utc: string;
  end_at_utc: string;
  location_name: string;
  course_type_name: string;
  pending_students_count: number;
  total_students_count: number;
};

export type ProfessorSessionMessageOut = {
  id: string;
  session_id: string;
  subject: string;
  body: string;
  body_format: "TEXT" | "HTML" | string;
  recipient_count: number;
  sent_at: string;
};

export type ProfessorPayoutOut = {
  payout_id: string;
  session_id: string;
  session_title: string;
  session_start_at_utc: string;
  session_end_at_utc: string;
  location_name: string;
  course_type_name: string;
  duration_hours: string;
  amount_snapshot: string;
  currency_snapshot: string;
  payout_status: "PENDING" | "APPROVED" | "PAID" | string;
  paid_at: string | null;
};

export type ProfessorBalanceOut = {
  currency: string;
  pending_amount: string;
  approved_amount: string;
  paid_amount: string;
  total_amount: string;
  pending_sessions: number;
  approved_sessions: number;
  paid_sessions: number;
};

export type ProfessorContractGridRuleOut = {
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
};

export type ProfessorContractGridLineOut = {
  course_type_id: string | null;
  course_type_name: string;
  service_type: string;
  mode: "PRESENTIEL" | "EN_LIGNE" | "AUTRE" | string;
  reference_duration_minutes: number | null;
  default_hourly_rate: string | null;
  rules: ProfessorContractGridRuleOut[];
};

export type ProfessorContractGridOut = {
  grid_id: string;
  valid_from: string;
  valid_to: string | null;
  location_code: string | null;
  location_label: string;
  notes: string | null;
  lines: ProfessorContractGridLineOut[];
};

export type TeacherStatementMissingSessionOut = {
  session_id: string;
  title: string;
  start_at_utc: string;
  end_at_utc: string;
  pending_students_count: number;
  total_students_count: number;
};

export type TeacherStatementLineOut = {
  course_type_id: string | null;
  course_type_label: string;
  hours: string;
  unit_rate_ht: string;
  amount_ht: string;
  amount_ttc: string;
  meta: Record<string, unknown>;
};

export type TeacherStatementOut = {
  statement_id: string | null;
  payor_legal_entity_id: string;
  payor_legal_entity_name: string;
  year: number;
  month: number;
  status: string;
  attendance_complete: boolean;
  currency: string;
  totals_ht: string;
  totals_vat: string;
  totals_ttc: string;
  dispute_message_last: string | null;
  lines: TeacherStatementLineOut[];
  missing_sessions: TeacherStatementMissingSessionOut[];
};

export type TeacherInvoiceLineOut = {
  id: string;
  course_type_id: string | null;
  course_type_label: string;
  hours: string;
  unit_rate_ht: string;
  amount_ht: string;
  amount_ttc: string;
  meta: Record<string, unknown>;
};

export type TeacherInvoiceOut = {
  id: string;
  statement_id: string;
  payor_legal_entity_id: string;
  payor_legal_entity_name: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  is_vat_applicable: boolean;
  vat_rate: string | null;
  totals_ht: string;
  totals_vat: string;
  totals_ttc: string;
  teacher_siret_display: string;
  teacher_iban: string;
  status: string;
  sent_to_accounting_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  lines: TeacherInvoiceLineOut[];
};

export type TeacherApproveStatementsOut = {
  generated_invoices: TeacherInvoiceOut[];
  blocked_missing_sessions: TeacherStatementMissingSessionOut[];
};

export type AdminToProcessStatus = "a_traiter" | "en_cours" | "termine";

export type AdminToProcessMessageOut = {
  id: string;
  created_at: string;
  updated_at: string;
  source: string;
  message_type: string;
  status: AdminToProcessStatus;
  message_body: string;
  teacher_id: string | null;
  teacher_name: string | null;
  handled_by_user_id: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  metadata: Record<string, unknown>;
};

export type AdminToProcessStatusUpdateOut = {
  id: string;
  status: AdminToProcessStatus;
  updated_at: string;
};

export type AdminSessionOut = {
  id: string;
  course_type_id: string;
  location_id: string;
  professor_id: string | null;
  substitute_teacher_id: string | null;
  substitute_set_at: string | null;
  substitute_set_by: string | null;
  substitute_note: string | null;
  teacher_id: string | null;
  teacher_display_name: string;
  habitual_teacher_id: string | null;
  habitual_teacher_display_name: string;
  substitute_teacher_display_name: string | null;
  effective_teacher_id: string | null;
  effective_teacher_display_name: string;
  location_label: string;
  type_label: string;
  status_label: string;
  title: string;
  description: string | null;
  public_description: string | null;
  private_description: string | null;
  professor_reminder_note: string | null;
  group_note: string | null;
  start_at_utc: string;
  end_at_utc: string;
  is_all_day: boolean;
  capacity_max: number;
  booked_count: number;
  status: "SCHEDULED" | "CANCELLED" | "COMPLETED" | string;
  auto_cancel_deadline_utc: string;
  cancel_reason: string | null;
  zoom_link: string | null;
  is_private: boolean;
  allow_online_booking: boolean;
  timezone: string;
  recurrence_group_id: string | null;
  recurrence_rule: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminSessionBookingOut = {
  id: string;
  session_id: string;
  client_id: string;
  client_email: string;
  client_first_name: string | null;
  client_last_name: string | null;
  client_display_name: string;
  client_plan_subscription_id: string | null;
  status: string;
  booked_at: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  waitlist_position: number | null;
  student_note: string | null;
};

export type AdminSessionBookingOperationOut = {
  processed_count: number;
  booked_count: number;
  waitlisted_count: number;
  skipped_count: number;
  details: string[];
};

export type AppSettingOut = {
  key: string;
  value: string;
  updated_at: string;
};

export type AdminConfigAccountOut = {
  contact_first_name: string;
  contact_last_name: string;
  contact_email: string;
  contact_phone: string;
  company_name: string;
  club_name: string;
  siret: string;
  vat_number: string;
  vat_default_rate: string;
  website: string;
  address_line: string;
  postal_code: string;
  city: string;
  country: string;
  allowed_currencies: string[];
  default_currency: string;
  legal_terms: string;
  logo_data_url: string;
};

export type AdminSubscriptionSettingsOut = {
  direct_debit_day: number | null;
  allow_card_subscriptions: boolean;
  add_contract_signature: boolean;
  close_expired_subscriptions: boolean;
  allow_promotional_start_period: boolean;
  allow_prorata_card: boolean;
  allow_prorata_sepa: boolean;
  online_resiliation_enabled: boolean;
  allow_booking_during_payment_alert: boolean;
  retry_first_delay_days: number;
  retry_max_auto_attempts: number;
  retry_move_to_pre_termination_after_failed_attempts: number;
  notify_success_customer_enabled: boolean;
  notify_success_admin_enabled: boolean;
  notify_first_failure_customer_enabled: boolean;
  notify_first_failure_admin_enabled: boolean;
  notify_final_failure_customer_enabled: boolean;
  notify_final_failure_admin_enabled: boolean;
};

export type AdminPaymentMethodOptionOut = {
  code: string;
  label: string;
  enabled: boolean;
  default_legal_entity_id: string | null;
  default_legal_entity_name: string | null;
};

export type AdminPaymentMethodsOut = {
  methods: AdminPaymentMethodOptionOut[];
};

export type AdminProductCategoriesOut = {
  categories: string[];
  updated_at: string | null;
};

export type AdminCatalogCategoryOut = {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  display_order: number;
  can_be_requested_by_professor: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminCatalogProductOut = {
  id: string;
  category_id: string | null;
  category_name: string | null;
  primary_location_id: string | null;
  primary_location_name: string | null;
  title: string;
  barcode: string | null;
  price_excl_vat: string;
  price_incl_vat: string;
  vat_rate: string;
  stock_global_quantity: number;
  reserve_stock: number;
  reorder_status: "NORMAL" | "TO_ORDER" | "ORDERED" | "RECEIVED" | string;
  reorder_status_updated_at: string;
  image_url: string | null;
  short_description: string | null;
  long_description: string | null;
  web_link: string | null;
  is_virtual: boolean;
  purchasable_online: boolean;
  is_public: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminCatalogProductImageUploadOut = {
  image_url: string;
  storage_key: string;
};

export type AdminCatalogReorderProductOut = {
  product_id: string;
  title: string;
  category_name: string | null;
  stock_global_quantity: number;
  reserve_stock: number;
  reorder_status: "NORMAL" | "TO_ORDER" | "ORDERED" | "RECEIVED" | string;
  reorder_status_updated_at: string;
  primary_location_id: string | null;
  primary_location_name: string | null;
};

export type AdminCatalogTransferStatus = "PENDING" | "DONE" | "CANCELLED" | string;

export type AdminCatalogStockTransferOut = {
  id: string;
  product_id: string;
  product_title: string;
  source_location_id: string;
  source_location_name: string;
  target_location_id: string;
  target_location_name: string;
  quantity: number;
  planned_transfer_date: string | null;
  assigned_to_user_id: string | null;
  assigned_to_name: string | null;
  requested_by_user_id: string | null;
  requested_by_name: string | null;
  status: AdminCatalogTransferStatus;
  completed_by_user_id: string | null;
  completed_by_name: string | null;
  completed_at: string | null;
  completed_transfer_date: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminCatalogKitItemOut = {
  product_id: string;
  product_title: string;
  quantity: number;
  display_order: number;
  unit_price_incl_vat: string;
  line_total_incl_vat: string;
};

export type AdminCatalogKitOut = {
  id: string;
  category_id: string | null;
  category_name: string | null;
  code: string | null;
  title: string;
  image_url: string | null;
  short_description: string | null;
  long_description: string | null;
  price_mode: "calculated" | "forced" | string;
  forced_price: string | null;
  currency: string;
  price_effective_incl_vat: string;
  price_incl_vat: string;
  vat_rate: string;
  computed_price_incl_vat: string;
  use_in_manual_billing: boolean;
  use_in_enrollments: boolean;
  purchasable_online: boolean;
  is_public: boolean;
  active: boolean;
  items: AdminCatalogKitItemOut[];
  created_at: string;
  updated_at: string;
};

export type AdminCatalogStockOut = {
  product_id: string;
  product_title: string;
  location_id: string;
  location_name: string;
  inventory_quantity: number;
  inventory_date: string | null;
  real_quantity: number;
  estimated_quantity: number;
  inventory_updated_at: string;
  real_updated_at: string;
  estimated_updated_at: string;
  updated_at: string;
};

export type AdminStockMovementType = "STOCK_IN" | "ADJUSTMENT" | string;
export type AdminStockMovementSourceType = "purchase" | "delivery" | "correction" | "return" | "other" | string;

export type AdminStockMovementOut = {
  id: string;
  product_id: string;
  product_title: string;
  location_id: string;
  location_name: string;
  movement_type: AdminStockMovementType;
  quantity: string;
  occurred_at: string;
  source_type: AdminStockMovementSourceType;
  source_reference: string | null;
  note: string | null;
  attachment_key: string | null;
  created_by: string | null;
  created_by_name: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AdminStockSnapshotOut = {
  product_id: string;
  product_title: string;
  stock_global: number;
  stock_location: number;
  stock_reserved: number;
};

export type AdminStockEntryCreateOut = {
  movement_id: string;
  stock_snapshot: AdminStockSnapshotOut;
};

export type AdminStockMovementListOut = {
  items: AdminStockMovementOut[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminCatalogProductStockOut = {
  product_id: string;
  product_title: string;
  stock_global: number;
  stock_reserved: number;
  stock_by_location: AdminCatalogStockOut[];
  recent_movements: AdminStockMovementOut[];
};

export type AdminCatalogRequestStatus = "PROCESSING" | "REJECTED" | "INVOICE_TO_SEND" | "TO_DELIVER" | "DELIVERED" | string;
export type AdminCatalogRequestSource = "ADMIN" | "PROFESSOR" | string;

export type AdminCatalogRequestOut = {
  id: string;
  student_user_id: string;
  student_name: string;
  product_id: string;
  product_title: string;
  location_id: string;
  location_name: string;
  quantity: number;
  requested_by_user_id: string | null;
  requested_by_name: string | null;
  request_source: AdminCatalogRequestSource;
  status: AdminCatalogRequestStatus;
  requested_at: string;
  admin_reviewed_by_user_id: string | null;
  admin_reviewed_by_name: string | null;
  admin_reviewed_at: string | null;
  accepted: boolean | null;
  should_bill: boolean | null;
  manual_transaction_id: string | null;
  delivered_by_user_id: string | null;
  delivered_by_name: string | null;
  delivery_marked_by_user_id: string | null;
  delivery_marked_by_name: string | null;
  delivery_marked_at: string | null;
  note: string | null;
  stock_real_quantity: number | null;
  stock_estimated_quantity: number | null;
};

export type ProfessorCatalogStudentOut = {
  user_id: string;
  display_name: string;
};

export type AdminPaymentProviderOut = {
  provider: "PAYPLUG" | "MOLLIE" | "STRIPE" | string;
  mode: "TEST" | "LIVE" | string;
  subscriptions_supported: boolean;
  subscriptions_managed_by_psp: boolean;
  recommendation: string;
  payplug_test_secret_configured: boolean;
  payplug_live_secret_configured: boolean;
  mollie_test_api_key_configured: boolean;
  mollie_live_api_key_configured: boolean;
  stripe_test_secret_configured: boolean;
  stripe_live_secret_configured: boolean;
  payplug_test_secret_masked: string;
  payplug_live_secret_masked: string;
  mollie_test_api_key_masked: string;
  mollie_live_api_key_masked: string;
  stripe_test_secret_masked: string;
  stripe_live_secret_masked: string;
  webhook_secret_masked: string;
};

export type AdminMessagingSettingsOut = {
  studio_email: string;
  studio_sender_name: string;
  teacher_sender_name: string;
  use_studio_name_as_default_sender: boolean;
  use_studio_email_for_reminders: boolean;
  use_studio_email_for_lesson_notes: boolean;
  send_birthday_emails: boolean;
  updated_at: string | null;
};

export type AdminMessagingChannel = "EMAIL" | "SMS" | "GROUP_NOTE";
export type AdminMessagingTemplateKind = "PREDEFINED" | "CUSTOM";

export type AdminMessagingTemplateOut = {
  id: string;
  code: string | null;
  name: string;
  channel: AdminMessagingChannel;
  kind: AdminMessagingTemplateKind;
  subject: string | null;
  body: string;
  body_format: "TEXT" | "HTML";
  active: boolean;
  description: string | null;
  variables_hint: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminInvoiceTemplateOut = {
  body: string;
  variables_hint: string;
  updated_at: string | null;
};

export type AdminTeacherInvoiceTemplateOut = {
  key: string;
  html_template: string;
  version: number;
  updated_at: string | null;
  variables: string[];
};

export type AdminInvoiceNumberingOut = {
  format_pattern: string;
  next_number: number;
  preview: string;
  updated_at: string | null;
};

export type AdminProfessorDefaultGridRuleOut = {
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
  display_order: number;
};

export type AdminProfessorDefaultGridLineOut = {
  course_type_id: string;
  course_type_name: string;
  mode: "PRESENTIEL" | "EN_LIGNE" | "AUTRE" | string;
  reference_duration_minutes: number | null;
  default_hourly_rate: string | null;
  display_order: number;
  rules: AdminProfessorDefaultGridRuleOut[];
};

export type AdminProfessorDefaultGridOut = {
  lines: AdminProfessorDefaultGridLineOut[];
  updated_at: string | null;
  active_period_id?: string | null;
  active_period_start_date?: string | null;
  active_period_end_date?: string | null;
};

export type AdminProfessorPayGridPeriodOut = {
  id: string;
  start_date: string;
  end_date: string | null;
  status: string;
  notes: string | null;
  is_active: boolean;
  is_future: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  rules_count: number;
};

export type AdminProfessorPayGridPeriodDetailOut = {
  period: AdminProfessorPayGridPeriodOut;
  lines: AdminProfessorDefaultGridLineOut[];
};

export type AdminFormulaRestrictionPeriod = "DAY" | "WEEK" | "MONTH" | "ROLLING_MONTH" | "SEMESTER";

export type AdminFormulaPriceTaxMode = "HT" | "TTC";
export type AdminFormulaCreditGrantsRelation = "AND" | "OR";

export type AdminFormulaRestrictionOut = {
  id: string;
  period: AdminFormulaRestrictionPeriod;
  max_bookings: number;
  course_type_ids: string[];
  course_type_names: string[];
};

export type AdminFormulaCreditGrantOut = {
  id: string;
  credit_type_id: string;
  credit_type_code: string | null;
  credit_type_name: string | null;
  credits_count: number;
};

export type AdminFormulaOut = {
  id: string;
  code: string;
  name: string;
  kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  active: boolean;
  is_private: boolean;
  description: string | null;
  credits_count: number | null;
  pack_validity_months: number | null;
  forfait_start_date: string | null;
  forfait_end_date: string | null;
  credit_grants: AdminFormulaCreditGrantOut[];
  credit_grants_relation: AdminFormulaCreditGrantsRelation;
  monthly_price_value: string | null;
  signup_fee_value: string | null;
  price_tax_mode: AdminFormulaPriceTaxMode;
  monthly_price_excl_vat: string | null;
  currency_code: string | null;
  signup_fee_excl_vat: string | null;
  options: string[];
  payment_methods: string[];
  entitlement_course_type_ids: string[];
  entitlement_course_type_names: string[];
  restrictions: AdminFormulaRestrictionOut[];
  created_at: string;
  updated_at: string;
};

export type PublicFormulaPurchaseSummaryOut = {
  formula_id: string;
  formula_code: string;
  formula_type: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  name: string;
  description: string | null;
  active: boolean;
  is_private: boolean;
  purchase_link_allowed: boolean;
  purchase_url: string;
  price_ttc: string | null;
  currency: string;
  frequency_label: string | null;
  includes: string[];
  restriction_labels: string[];
  payment_methods: string[];
};

export type PublicFormulaPurchaseStartOut = {
  existing_user: boolean;
  redirect_mode: "login" | "signup";
  purchase_context: string;
};

export type PublicFormulaPurchaseContextOut = {
  purchase_context: string;
  email: string;
  formula_id: string;
  formula_code: string;
  formula_type: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  price_snapshot: string | null;
  currency: string;
  summary: PublicFormulaPurchaseSummaryOut;
};

export type AdminActivityOut = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  service_code: string;
  seller_legal_entity_id: string | null;
  seller_legal_entity_name: string | null;
  payor_legal_entity_id: string | null;
  payor_legal_entity_name: string | null;
  credit_type_id: string | null;
  credit_type_code: string | null;
  credit_type_name: string | null;
  duration_minutes: number;
  color_hex: string;
  mode: "ONLINE" | "ONSITE" | "ANY" | string;
  requires_professor: boolean;
  default_capacity: number;
  default_hourly_rate: string | null;
  default_course_rate_ttc: string | null;
  email_reminder_hours_before_start: number | null;
  sms_reminder_hours_before_start: number | null;
  min_booking_notice_hours_override: number | null;
  cancellation_deadline_hours_override: number | null;
  auto_cancel_if_booked_less_than_override: number | null;
  auto_cancel_hours_before_start_override: number | null;
  active: boolean;
};

export type AdminLegalEntityOut = {
  id: string;
  name: string;
  siren: string | null;
  siret: string | null;
  vat_number: string | null;
  address_text: string | null;
  accounting_email: string | null;
  country_code: string;
  invoice_prefix: string;
  invoice_next_number: number;
  default_payment_provider: "PAYPLUG" | "MOLLIE" | "STRIPE" | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminCreditTypeOut = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  active: boolean;
  activity_ids: string[];
  activity_names: string[];
  activity_count: number;
};

export type AdminPlanningSettingsOut = {
  location_id: string;
  location_name: string;
  description: string | null;
  min_booking_notice_hours: number;
  max_booking_horizon_months: number;
  cancellation_deadline_hours: number;
  max_bookings_per_client: number | null;
  allow_negative_credits: boolean;
  waitlist_capacity: number;
  auto_cancel_if_booked_less_than: number;
  auto_cancel_hours_before_start: number;
  is_private: boolean;
  allow_force_booking: boolean;
  allow_multi_booking: boolean;
  notify_coach: boolean;
  notify_admins: boolean;
  hide_booking_count: boolean;
  block_client_cancellation: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminPlanningActivityOut = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  color_hex: string;
  mode: "ONLINE" | "ONSITE" | "ANY" | string;
  default_capacity: number;
  active: boolean;
  selected: boolean;
  display_order: number;
};

export type AdminPlanningActivitiesOut = {
  location_id: string;
  location_name: string;
  selected_activity_ids: string[];
  activities: AdminPlanningActivityOut[];
};

export type ReservationReportRow = {
  session_id: string;
  start_at_utc: string;
  end_at_utc: string;
  session_status: string;
  course_type_id: string;
  course_type_code: string;
  course_type_name: string;
  location_id: string;
  location_name: string;
  professor_id: string;
  professor_name: string;
  booking_id: string;
  client_email: string;
  booking_status: string;
  total_incl_vat_snapshot: string;
  currency_snapshot: string;
};

export type AttendanceReportRow = {
  session_id: string;
  start_at_utc: string;
  course_type_name: string;
  location_name: string;
  professor_name: string;
  booking_id: string;
  client_email: string;
  attendance_status: string;
};

export type ProfessorStatementRow = {
  session_id: string;
  professor_id: string;
  professor_name: string;
  start_at_utc: string;
  end_at_utc: string;
  session_status: string;
  course_type_name: string;
  location_name: string;
  duration_hours: number;
  booked_students: number;
  attended_students: number;
  no_show_students: number;
  excused_absence_students: number;
  hourly_rate_snapshot: string | null;
  amount_snapshot: string | null;
  currency_snapshot: string | null;
  payout_status: "PENDING" | "APPROVED" | "PAID" | null;
};

export type CommunicationReportRow = {
  id: string;
  channel: "EMAIL" | "SMS";
  source: string;
  communication_type: string;
  communication_type_label: string;
  sender_category: "PROFESSOR" | "SYSTEM" | "OTHER_USER";
  sender_label: string;
  sender_user_id: string | null;
  professor_id: string | null;
  occurred_at: string;
  subject: string;
  recipient: string;
  recipient_user_id: string | null;
  delivery_status: "DELIVERED" | "SENT" | "FAILED" | "PENDING" | "SKIPPED" | "UNKNOWN";
  provider_message_id: string | null;
  provider: string | null;
  content: string;
  content_format: "TEXT" | "HTML";
  error_message: string | null;
};

export type CommunicationPeriod = "TODAY" | "WEEK" | "MONTH" | "SEMESTER" | "YEAR" | "ALL";

export type CommunicationReportPageOut = {
  items: CommunicationReportRow[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
};

export type CommunicationTypeFilterOut = {
  code: string;
  label: string;
};

export type CommunicationProfessorFilterOut = {
  id: string;
  label: string;
};

export type CommunicationFiltersOut = {
  communication_types: CommunicationTypeFilterOut[];
  professors: CommunicationProfessorFilterOut[];
};

export type NotificationJobRunOut = {
  id: string;
  job_name: string;
  triggered_by: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  duration_seconds: number | null;
  items_scanned: number;
  items_processed: number;
  items_sent: number;
  items_skipped: number;
  items_failed: number;
  summary_text: string | null;
  error_text: string | null;
};

export type NotificationJobRunPageOut = {
  items: NotificationJobRunOut[];
  total: number;
};

export type NotificationJobRunLogOut = {
  id: string;
  level: string;
  message: string;
  context_json: Record<string, unknown>;
  created_at: string;
};

export type NotificationJobRelatedEntityOut = {
  id: string;
  notification_type: string;
  channel: string;
  status: string;
  related_entity_type: string;
  related_entity_id: string;
  recipient_email: string | null;
  recipient_phone: string | null;
  scheduled_for: string;
  sent_at: string | null;
  failed_at: string | null;
  skipped_at: string | null;
  failure_reason: string | null;
};

export type NotificationIncidentOut = {
  id: string;
  contact_type: string;
  contact_id: string;
  channel: string;
  incident_type: string;
  severity: string;
  provider_name: string | null;
  provider_message_id: string | null;
  detail_text: string | null;
  notification_id: string | null;
  detected_at: string;
};

export type NotificationJobRunDetailOut = {
  run: NotificationJobRunOut;
  metadata_json: Record<string, unknown>;
  logs: NotificationJobRunLogOut[];
  notifications: NotificationJobRelatedEntityOut[];
  incidents: NotificationIncidentOut[];
};

export type ContactDeliveryStatusOut = {
  contact_type: string;
  contact_id: string;
  email: string | null;
  email_status: string;
  email_suspended_at: string | null;
  email_suspension_reason: string | null;
  phone: string | null;
  phone_status: string;
  phone_suspended_at: string | null;
  phone_suspension_reason: string | null;
};

export type AdminSubscriptionEngineRowOut = {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_email: string;
  plan_id: string;
  plan_name: string;
  status: string;
  bookings_blocked: boolean;
  next_billing_date: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  last_attempt_at: string | null;
  last_successful_charge_at: string | null;
  last_cycle_status: string | null;
  recovery_url: string | null;
  amount: string | null;
  currency: string | null;
};

export type AdminSubscriptionEngineListOut = {
  items: AdminSubscriptionEngineRowOut[];
  total: number;
};

export type AdminSubscriptionCycleOut = {
  id: string;
  period_start: string;
  period_end: string;
  billing_date: string;
  status: string;
  attempt_count: number;
  first_attempt_at: string | null;
  last_attempt_at: string | null;
  next_retry_at: string | null;
  paid_at: string | null;
  amount: string;
  currency: string;
  payment_recovery_url: string | null;
};

export type AdminSubscriptionAttemptOut = {
  id: string;
  billing_cycle_id: string;
  attempt_number: number;
  attempted_at: string;
  amount: string;
  currency: string;
  status: string;
  provider_name: string | null;
  provider_payment_id: string | null;
  provider_status: string | null;
  failure_code: string | null;
  failure_reason: string | null;
};

export type AdminSubscriptionNotificationOut = {
  id: string;
  notification_type: string;
  status: string;
  recipient_email: string | null;
  scheduled_for: string;
  sent_at: string | null;
  failed_at: string | null;
  failure_reason: string | null;
};

export type AdminSubscriptionEngineDetailOut = {
  subscription: AdminSubscriptionEngineRowOut;
  cycles: AdminSubscriptionCycleOut[];
  attempts: AdminSubscriptionAttemptOut[];
  notifications: AdminSubscriptionNotificationOut[];
};
