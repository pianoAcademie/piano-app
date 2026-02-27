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
  default_capacity: number;
  default_hourly_rate: string | null;
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
  };
};

export type PlanOut = {
  id: string;
  code: string;
  name: string;
  kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  credits_count: number | null;
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
  credits_initial: number | null;
  credits_remaining: number | null;
  auto_renew: boolean;
  billing_method_code: string | null;
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
  booking_id: string;
  session_id: string;
  session_title: string;
  scheduled_for_utc: string;
  sent_at: string | null;
  status: "PENDING" | "SENT" | "FAILED" | "SKIPPED" | string;
  provider_message_id: string | null;
  error_message: string | null;
  subject_preview: string;
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
  invoice_number: string | null;
  invoice_status: string | null;
  refunded_at: string | null;
  refund_reason: string | null;
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
    credits_initial: number | null;
    credits_remaining: number | null;
    auto_renew: boolean;
    billing_method_code: string | null;
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

export type AdminSessionOut = {
  id: string;
  course_type_id: string;
  location_id: string;
  professor_id: string;
  title: string;
  description: string | null;
  public_description: string | null;
  private_description: string | null;
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
};

export type AdminPaymentMethodOptionOut = {
  code: string;
  label: string;
  enabled: boolean;
};

export type AdminPaymentMethodsOut = {
  methods: AdminPaymentMethodOptionOut[];
};

export type AdminPaymentProviderOut = {
  provider: "PAYPLUG" | "MOLLIE" | string;
  mode: "TEST" | "LIVE" | string;
  subscriptions_supported: boolean;
  subscriptions_managed_by_psp: boolean;
  recommendation: string;
  payplug_test_secret_configured: boolean;
  payplug_live_secret_configured: boolean;
  mollie_test_api_key_configured: boolean;
  mollie_live_api_key_configured: boolean;
  payplug_test_secret_masked: string;
  payplug_live_secret_masked: string;
  mollie_test_api_key_masked: string;
  mollie_live_api_key_masked: string;
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

export type AdminMessagingChannel = "EMAIL" | "SMS";
export type AdminMessagingTemplateKind = "PREDEFINED" | "CUSTOM";

export type AdminMessagingTemplateOut = {
  id: string;
  code: string | null;
  name: string;
  channel: AdminMessagingChannel;
  kind: AdminMessagingTemplateKind;
  subject: string | null;
  body: string;
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

export type AdminActivityOut = {
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
  mode: "ONLINE" | "ONSITE" | "ANY" | string;
  default_capacity: number;
  default_hourly_rate: string | null;
  active: boolean;
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
