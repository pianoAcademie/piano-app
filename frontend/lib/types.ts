export type AuthLoginResponse = {
  access_token: string;
  token_type: string;
};

export type LocalizedTextMap = Record<string, string>;

export type UserOut = {
  id: string;
  email: string;
  role: "admin" | "prof" | "client";
  client_kind: "ADULT" | "CHILD" | string;
  client_status: "ACTIVE" | "RESPONSABLE" | "INACTIVE" | "TRIAL" | "PENDING" | "ARCHIVED" | string;
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
  admin_permissions: Partial<ProfessorPermissionOut> | null;
  admin_access_profile: "admin" | "manager" | "professor" | string | null;
  residence_country: string;
  preferred_language: string;
  preferred_currency: string;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminTaskType =
  | "CLIENT_CALL"
  | "PROVIDER_CALL"
  | "SLOT_CHOICE"
  | "PROFESSOR_CONTACT"
  | "SHEET_MUSIC_DELIVERY"
  | "PLANNING";

export type AdminTaskStoredStatus = "CREATED" | "ASSIGNED" | "IN_PROGRESS" | "CONTACTED_NO_RESPONSE" | "WAITING_CLIENT" | "COMPLETED" | "ARCHIVED";
export type AdminTaskEffectiveStatus = AdminTaskStoredStatus | "OVERDUE";

export type AdminTaskManagerOut = {
  id: string;
  name: string;
  email: string;
};

export type AdminTaskCommentOut = {
  id: string;
  body: string;
  author: AdminTaskManagerOut | null;
  created_at: string;
};

export type AdminTaskContactOut = {
  kind: "CLIENT" | "PROSPECT";
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  linked_client_id: string | null;
};

export type AdminTaskOut = {
  id: string;
  task_type: AdminTaskType;
  status: AdminTaskStoredStatus;
  effective_status: AdminTaskEffectiveStatus;
  description: string;
  comment: string | null;
  comments: AdminTaskCommentOut[];
  assignee: AdminTaskManagerOut | null;
  created_by: AdminTaskManagerOut | null;
  contact: AdminTaskContactOut | null;
  source: {
    intake_id: string | null;
    intake_label: string | null;
    quote_id: string | null;
    quote_label: string | null;
  };
  due_at: string | null;
  completed_at: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminTaskOptionsOut = {
  managers: AdminTaskManagerOut[];
  current_user_id: string;
};

export type AdminTaskSourcePrefillOut = {
  contact: AdminTaskContactOut | null;
  description: string;
  source: AdminTaskOut["source"];
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
  lesson_format: "INDIVIDUAL" | "GROUP" | string;
  requires_professor: boolean;
  allows_student_bookings: boolean;
  supports_student_time_overrides: boolean;
  default_capacity: number;
  default_hourly_rate: string | null;
  default_course_rate_ttc: string | null;
  email_reminder_hours_before_start: number | null;
  sms_reminder_hours_before_start: number | null;
  min_booking_notice_hours_override: number | null;
  cancellation_deadline_hours_override: number | null;
  auto_cancel_if_booked_less_than_override: number | null;
  auto_cancel_hours_before_start_override: number | null;
  auto_cancel_rule_enabled: boolean;
  exclude_holidays_in_recurrence: boolean;
  exclude_school_vacations_in_recurrence: boolean;
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

export type SessionAudienceScope = "EXTERNAL" | "SUBSCRIPTION" | "FORFAIT" | "PRIVATE";

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
  child_bookings_enabled: boolean;
  adult_bookings_enabled: boolean;
  adult_capacity_max: number | null;
  adult_booked_count: number;
  child_trial_bookings_enabled: boolean;
  adult_trial_bookings_enabled: boolean;
  visibility_scopes: SessionAudienceScope[];
  booking_scopes: SessionAudienceScope[];
  visibility_scope: SessionAudienceScope;
  booking_scope: SessionAudienceScope;
  online_booking_enabled: boolean;
  external_booking_price_ttc: string | null;
  external_booking_currency: string | null;
  show_external_remaining_seats: boolean;
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
  description: string | null;
  kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  credits_count: number | null;
  forfait_start_date: string | null;
  forfait_end_date: string | null;
  monthly_price_excl_vat: string | null;
  price_ttc: string | null;
  base_price_ttc: string | null;
  currency_code: string | null;
  active: boolean;
  is_trial_offer: boolean;
  first_purchase_required: boolean;
  first_purchase_fee_ttc: string | null;
  first_purchase_partitions_price_ttc: string | null;
  first_purchase_breakdown: Array<{
    code: string;
    label: string;
    amount_ttc: string;
  }>;
  payment_methods: string[];
  entitlement_course_type_names: string[];
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
  credit_allocations: Array<{
    credit_type_id: string;
    credit_type_code: string;
    credit_type_name: string;
    credits_initial: number;
    credits_remaining: number;
  }>;
  auto_renew: boolean;
  bookings_blocked: boolean;
  billing_method_code: string | null;
  payment_method_type: string | null;
  payment_method_brand: string | null;
  payment_method_last4: string | null;
  payment_method_exp_month: number | null;
  payment_method_exp_year: number | null;
  payment_method_setup_required: boolean;
  payment_method_setup_completed_at: string | null;
  last_successful_charge_at: string | null;
  payment_alert_started_at: string | null;
  pre_termination_at: string | null;
  direct_payment_recovery_url: string | null;
  suspension_starts_at: string | null;
  suspension_ends_at: string | null;
  suspension_start_date: string | null;
  suspension_end_date: string | null;
  cancellation_requested_at: string | null;
  cancellation_effective_at: string | null;
  cancellation_request_status: string | null;
  cancellation_request_note: string | null;
  cancellation_request_reviewed_at: string | null;
  entitlement_course_type_ids: string[];
  entitlement_course_type_names: string[];
  offer_quote_id?: string | null;
  offer_quote_number?: string | null;
  offer_school_year_label?: string | null;
  offer_total_ttc?: string | null;
  offer_currency?: string | null;
  offer_options?: Array<{
    id: string;
    title: string;
    description: string | null;
    quantity: string;
    amount_ttc: string;
  }>;
  offer_deposit_amount_ttc?: string | null;
  offer_deposit_status?: string | null;
  offer_deposit_paid_at?: string | null;
  offer_deposit_invoice_id?: string | null;
  offer_paid_ttc?: string | null;
  offer_payment_status?: string | null;
  offer_remaining_ttc?: string | null;
  plan: {
    id: string;
    code: string;
    name: string;
    kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
    price_ttc: string | null;
    currency_code: string | null;
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
  student_start_at_utc: string | null;
  student_end_at_utc: string | null;
  session: {
    id: string;
    title: string;
    start_at_utc: string;
    end_at_utc: string;
    status: string;
  };
};

export type ClientManualCreditOut = {
  id: string;
  owner_client_id: string;
  owner_display_name: string;
  credit_type_id: string;
  credit_type_code: string;
  credit_type_name: string;
  credits_count: number;
  updated_at: string;
};

export type MakeupCreditOut = {
  id: string;
  status: string;
  original_booking_id: string;
  original_session_title: string;
  original_session_start_at_utc: string;
  created_at: string;
};

export type MakeupStudentSummaryOut = {
  user_id: string;
  display_name: string;
  has_active_restricted_forfait: boolean;
  credits_initial: number;
  credits_remaining: number;
  pending_makeups: MakeupCreditOut[];
  history: MakeupCreditOut[];
};

export type AdminClientOut = {
  id: string;
  email: string;
  role: "admin" | "prof" | "client";
  client_kind: "ADULT" | "CHILD" | string;
  photo_url: string | null;
  client_status: "ACTIVE" | "RESPONSABLE" | "INACTIVE" | "TRIAL" | "PENDING" | "ARCHIVED" | string;
  student_site: "PARIS" | "BAR_LE_DUC" | "ONLINE" | string | null;
  first_name: string | null;
  last_name: string | null;
  family_name: string | null;
  linked_children_count: number;
  linked_children_names: string[];
  linked_adults_count: number;
  linked_adult_names: string[];
  group_ids: string[];
  group_names: string[];
  address_line: string | null;
  home_access_instructions: string | null;
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
  preferred_language: string;
  preferred_currency: string;
  timezone: string;
  is_active: boolean;
  next_session_start_at_utc: string | null;
  last_login_at: string | null;
  last_seen_at: string | null;
  last_seen_channel: "WEB" | "MOBILE_APP" | string | null;
  created_at: string;
  updated_at: string;
};

export type AdminClientStatsOut = {
  total: number;
  by_status: Record<string, number>;
};

export type AdminAdultCandidateOut = {
  id: string;
  display_name: string;
  email: string;
  mobile_phone_1: string | null;
  mobile_phone_2: string | null;
  home_phone: string | null;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  address_country: string;
  residence_country: string;
};

export type AdminOnlinePresenceOut = {
  generated_at: string;
  active_window_seconds: number;
  total: number;
  web: number;
  mobile_app: number;
  web_desktop: number;
  web_mobile: number;
  installed_web: number;
  native_app: number;
  legacy_unclassified: number;
  clients: number;
  professors: number;
  admins: number;
  history_timezone: string;
  history_date: string;
  hourly_history: AdminPresenceHourlyBucketOut[];
  daily_visitors: AdminDailyPresenceUserOut[];
  online_users: AdminOnlinePresenceUserOut[];
};

export type AdminPresenceHourlyBucketOut = {
  hour_started_at: string;
  hour_label: string;
  total: number;
  web: number;
  mobile_app: number;
  web_desktop: number;
  web_mobile: number;
  installed_web: number;
  native_app: number;
  legacy_unclassified: number;
  clients: number;
  professors: number;
  admins: number;
};

export type AdminOnlinePresenceUserOut = {
  user_id: string;
  display_name: string;
  role: "admin" | "prof" | "client" | string;
  channel: "WEB" | "MOBILE_APP" | "WEB_DESKTOP" | "WEB_MOBILE" | "INSTALLED_WEB" | "NATIVE_APP";
  current_path: string | null;
  origin: string | null;
  last_action: string | null;
  device_type: "DESKTOP" | "MOBILE" | "TABLET" | "APP" | string | null;
  residence_country: string | null;
  student_site: string | null;
  last_seen_at: string;
};

export type AdminDailyPresenceUserOut = {
  user_id: string;
  display_name: string;
  role: "admin" | "prof" | "client" | string;
  channels: ("WEB" | "MOBILE_APP" | "WEB_DESKTOP" | "WEB_MOBILE" | "INSTALLED_WEB" | "NATIVE_APP")[];
  first_seen_at: string;
  last_seen_at: string;
  active_hour_labels: string[];
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
  payment_provider_code: string | null;
  payment_method_setup_required: boolean;
  payment_method_setup_completed_at: string | null;
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
  suspension_start_date: string | null;
  suspension_end_date: string | null;
  suspension_duration_value: number | null;
  suspension_duration_unit: string | null;
  cancellation_requested_at: string | null;
  cancellation_effective_at: string | null;
  cancellation_request_status: string | null;
  cancellation_request_note: string | null;
  cancellation_request_reviewed_at: string | null;
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
  target_role: "client" | "teacher" | "manager";
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
  scheduled_service_date: string | null;
  service_completed_at: string | null;
  payment_received: boolean;
  payment_received_at: string | null;
  payment_received_amount: string | null;
  payment_refunded: boolean;
  payment_refunded_at: string | null;
  payment_refunded_amount: string | null;
  payment_refund_reason: string | null;
  payment_refund_email_sent_at: string | null;
  payment_receipt_id: string | null;
  payment_receipt_number: string | null;
  payment_receipt_status: string | null;
  payment_receipt_sent_at: string | null;
  final_invoice_generated: boolean;
  final_invoice_note_id: string | null;
  final_invoice_number: string | null;
  final_invoice_status: string | null;
};

export type AdminPaymentReceiptOut = {
  id: string;
  receipt_number: string | null;
  status: string;
  customer_id: string;
  student_id: string | null;
  booking_id: string;
  amount_paid: string;
  currency: string;
  paid_at: string | null;
  payment_method: string | null;
  payment_provider: string | null;
  payment_transaction_reference: string | null;
  reservation_label: string;
  scheduled_service_date: string | null;
  location_label: string | null;
  email_sent_at: string | null;
  final_invoice_note_id: string | null;
  final_invoice_generated_at: string | null;
};

export type AdminClientMessageOut = {
  id: string;
  booking_id: string | null;
  session_id: string | null;
  session_title: string | null;
  channel: "EMAIL" | "SMS" | "PUSH";
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

export type AdminCheckDepositPaymentOut = {
  transaction_id: string;
  client_id: string;
  client_name: string;
  occurred_at: string;
  label: string;
  reference: string | null;
  amount_incl_vat: string;
  currency: string;
  status: string;
  invoice_number: string | null;
  invoice_note_id: string | null;
  tracking_note: string | null;
  receipt_location_id: string | null;
  receipt_location_code: string | null;
  receipt_location_name: string | null;
  custody_status: string | null;
  custody_updated_at: string | null;
};

export type AdminCheckDepositBulkUpdateOut = {
  matched_count: number;
  updated_count: number;
  updated_transaction_ids: string[];
  unmatched_rows: string[];
};

export type AdminCheckCustodyBulkUpdateOut = {
  updated_count: number;
  updated_transaction_ids: string[];
};

export type AdminReferralRewardOut = {
  id: string;
  typeform_intake_id: string | null;
  quote_id: string | null;
  declared_referrer_text: string;
  category: string | null;
  status: string;
  match_status: string;
  match_confidence: number;
  referrer_user_id: string | null;
  referrer_name: string | null;
  referrer_email: string | null;
  referred_client_id: string | null;
  referred_client_name: string | null;
  referred_student_id: string | null;
  referred_student_name: string | null;
  referred_prospect_name: string | null;
  reward_amount: string;
  currency: string;
  trigger_ratio: string;
  invoice_total: string | null;
  paid_total: string | null;
  threshold_amount: string | null;
  payment_progress_ratio: string | null;
  credit_transaction_id: string | null;
  trigger_invoice_note_id: string | null;
  announcement_email_sent_at: string | null;
  credit_email_sent_at: string | null;
  validated_at: string | null;
  credit_granted_at: string | null;
  updated_at: string;
  match_candidates: Array<Record<string, unknown>>;
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

export type AdminClientBillingAdjustmentOut = {
  id: string;
  client_id: string;
  student_id: string | null;
  change_id: string | null;
  quote_id: string | null;
  quote_number: string | null;
  status: "READY" | "DISMISSED" | "CONVERTED";
  adjustment_type: "INVOICE" | "CREDIT_NOTE";
  label: string;
  description: string | null;
  amount_excl_vat: string;
  vat_rate: string;
  vat_amount: string;
  total_incl_vat: string;
  currency: string;
  legal_entity_id: string | null;
  converted_manual_transaction_id: string | null;
  dismissed_reason: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminClientBillingAdjustmentQueueOut = AdminClientBillingAdjustmentOut & {
  client_display_name: string;
  student_display_name: string | null;
  change_title: string | null;
  change_type: string | null;
};

export type AdminStudentQuoteChangeOut = {
  id: string;
  client_id: string;
  student_id: string | null;
  student_display_name: string | null;
  quote_id: string | null;
  quote_number: string | null;
  quote_line_id: string | null;
  change_type:
    | "SLOT_CHANGE"
    | "COURSE_CANCELLED"
    | "COURSE_ADDED"
    | "COURSE_REMOVED"
    | "FORMULA_CHANGE"
    | "EXCEPTIONAL_ADJUSTMENT"
    | "OTHER";
  status: "DRAFT" | "VALIDATED" | "CANCELLED";
  requested_by: string | null;
  requested_at: string;
  effective_date: string | null;
  title: string;
  description: string | null;
  before_snapshot: Record<string, unknown>;
  after_snapshot: Record<string, unknown>;
  financial_impact_ttc: string | null;
  currency: string;
  billing_action: "NONE" | "TO_INVOICE" | "TO_CREDIT" | "MANUAL_REVIEW";
  client_visible_note: string | null;
  internal_note: string | null;
  billing_adjustments: AdminClientBillingAdjustmentOut[];
  created_at: string;
  updated_at: string;
};

export type AdminRangeInvoiceOut = {
  note_id: string;
  invoice_number: string;
  seller_legal_entity_id: string | null;
  billing_entity: string | null;
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
  included_payment_keys: string[];
  totals_by_currency: Record<string, string>;
  total_to_pay_by_currency: Record<string, string>;
  invoice_status: "ISSUED" | "PAID" | "CANCELLED" | "CREDIT_NOTE";
  document_type: "INVOICE" | "CREDIT_NOTE";
  original_invoice_note_id: string | null;
  original_invoice_number: string | null;
  credit_note_note_id: string | null;
  credit_note_number: string | null;
  check_coverage_status: "NONE" | "PARTIAL" | "COVERED";
  pending_check_amounts_by_currency: Record<string, string>;
  pending_check_count: number;
  reminders_suspended: boolean;
  emailed_at: string | null;
  reminded_at: string | null;
  bank_transfer_order_id: string | null;
  bank_transfer_order_reference: string | null;
  bank_transfer_order_status: string | null;
  bank_transfer_order_expires_at: string | null;
  bank_transfer_order_paid_at: string | null;
  public_note: string | null;
  private_note: string | null;
  recipient_client_name: string | null;
  family_billing_payer_client_id: string | null;
  related_invoices: AdminRangeInvoiceReferenceOut[];
};

export type AdminLegacyInvoiceOut = {
  id: string;
  invoice_number: string;
  issued_at: string;
  source: string;
  status: "PAID" | "CREDIT_NOTE";
  label: string;
  total_incl_vat: string;
  currency: string;
  original_file_name: string;
};

export type AdminClientAutoInvoiceRuleOut = {
  id: string;
  client_id: string;
  legal_entity_id: string;
  cycle_start_date: string;
  frequency: "MONTHLY" | "BIMONTHLY" | "QUARTERLY" | "YEARLY";
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
  sms_message_id: string | null;
  sms_recipient: string | null;
};

export type AdminRangeInvoiceEmailPreviewOut = {
  note_id: string;
  kind: "INVOICE" | "REMINDER";
  to_emails: string[];
  subject: string;
  body: string;
  body_format: "TEXT" | "HTML";
  sms_body: string | null;
};

export type FamilyMemberOut = {
  id: string;
  email: string | null;
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

export type FamilyBillingAllocationOut = {
  id: string;
  child_client_id: string;
  payer_client_id: string;
  allocation_type: "PERCENT" | "FIXED" | "REMAINDER";
  allocation_value: string | null;
};

export type FamilyBillingChildOut = {
  child: FamilyMemberOut;
  payers: Array<{
    adult: FamilyMemberOut;
    is_primary_billing_recipient: boolean;
    allocation: FamilyBillingAllocationOut | null;
  }>;
};

export type AdminClientFamilyOut = {
  client_id: string;
  client_kind: "ADULT" | "CHILD" | string;
  links_as_adult: FamilyLinkOut[];
  links_as_child: FamilyLinkOut[];
  billing_recipient_adult_id: string | null;
  billing_children: FamilyBillingChildOut[];
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
    credit_allocations: Array<{
      credit_type_id: string;
      credit_type_code: string;
      credit_type_name: string;
      credits_initial: number;
      credits_remaining: number;
    }>;
    auto_renew: boolean;
    bookings_blocked: boolean;
    billing_method_code: string | null;
    payment_method_type: string | null;
    payment_method_brand: string | null;
    payment_method_last4: string | null;
    payment_method_exp_month: number | null;
    payment_method_exp_year: number | null;
    payment_method_setup_required: boolean;
    payment_method_setup_completed_at: string | null;
    last_successful_charge_at: string | null;
    payment_alert_started_at: string | null;
    pre_termination_at: string | null;
    direct_payment_recovery_url: string | null;
    suspension_starts_at: string | null;
    suspension_ends_at: string | null;
    suspension_start_date: string | null;
    suspension_end_date: string | null;
    cancellation_requested_at: string | null;
    cancellation_effective_at: string | null;
    cancellation_request_status: string | null;
    cancellation_request_note: string | null;
    cancellation_request_reviewed_at: string | null;
    entitlement_course_type_ids: string[];
    entitlement_course_type_names: string[];
    offer_quote_id: string | null;
    offer_quote_number: string | null;
    offer_school_year_label: string | null;
    offer_total_ttc: string | null;
    offer_currency: string | null;
    offer_options: Array<{
      id: string;
      title: string;
      description: string | null;
      quantity: string;
      amount_ttc: string;
    }>;
    offer_deposit_amount_ttc: string | null;
    offer_deposit_status: string | null;
    offer_deposit_paid_at: string | null;
    offer_deposit_invoice_id: string | null;
    offer_paid_ttc: string | null;
    offer_payment_status: string | null;
    offer_remaining_ttc: string | null;
    plan: {
      id: string;
      code: string;
      name: string;
      kind: "PACK" | "SUBSCRIPTION" | "FORFAIT";
      price_ttc: string | null;
      currency_code: string | null;
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
      location_name: string | null;
    };
  }>;
};

export type ClientMessageOut = {
  id: string;
  owner_client_id: string;
  owner_display_name: string;
  recipient_email: string | null;
  channel: string;
  booking_id: string | null;
  session_id: string | null;
  session_title: string | null;
  scheduled_for_utc: string;
  sent_at: string | null;
  status: string;
  provider_message_id: string | null;
  error_message: string | null;
  subject_preview: string;
  content_preview: string | null;
  content_text: string | null;
  content_html: string | null;
};

export type ClientNewsOut = {
  id: string;
  title: string;
  summary: string | null;
  body: string;
  link_url: string | null;
  link_label: string | null;
  is_pinned: boolean;
  published_at: string;
};

export type AdminClientNewsOut = {
  id: string;
  title_fr: string;
  title_en: string | null;
  summary_fr: string | null;
  summary_en: string | null;
  body_fr: string;
  body_en: string | null;
  link_url: string | null;
  link_label_fr: string | null;
  link_label_en: string | null;
  status: "DRAFT" | "PUBLISHED";
  is_pinned: boolean;
  published_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ClientContentLessonOut = {
  id: string;
  external_id: string;
  slug: string | null;
  title: string;
  position: number;
  summary: string | null;
  content_html: string | null;
  video_url: string | null;
  resource_url: string | null;
  status: string;
};

export type ClientContentSectionOut = {
  id: string;
  external_id: string;
  title: string;
  position: number;
  lessons: ClientContentLessonOut[];
};

export type ClientContentMemberAccessOut = {
  member_id: string;
  member_display_name: string;
  member_email: string;
  course_type_ids: string[];
  course_type_names: string[];
  next_release_at: string | null;
};

export type ClientContentCourseOut = {
  id: string;
  provider: string;
  external_id: string;
  slug: string | null;
  title: string;
  summary: string | null;
  level_code: string | null;
  status: string;
  cover_image_url: string | null;
  last_synced_at: string | null;
  member_accesses: ClientContentMemberAccessOut[];
  sections: ClientContentSectionOut[];
  standalone_lessons: ClientContentLessonOut[];
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
  source_quote_id: string | null;
  source_quote_number: string | null;
  invoice_kind: string | null;
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
  can_view_planning_simulation: boolean;
  planning_simulation_location_id: string | null;
  can_manage_check_deposits: boolean;
  check_deposits_location_id: string | null;
  can_view_intakes: boolean;
  can_view_quotes: boolean;
  can_view_upcoming_trials: boolean;
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
  last_login_at: string | null;
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
  internal_note: string | null;
};

export type ProfessorSessionOut = {
  id: string;
  title: string;
  description: string | null;
  internal_note: string | null;
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

export type ProfessorInternalNoteListOut = {
  id: string;
  note_type: "SESSION" | "STUDENT" | string;
  body: string;
  session_id: string;
  booking_id: string | null;
  student_id: string | null;
  student_display_name: string | null;
  session_title: string;
  session_start_at_utc: string;
  session_timezone: string;
  course_type_name: string;
  location_id: string;
  location_name: string;
};

export type ProfessorLocalIntakeTaskOut = {
  id: string;
  received_at: string;
  local_confirmation_status: "PENDING" | "CONFIRMED" | string;
  prospect_label: string;
  child_label: string | null;
  requested_summary: string | null;
  detected_location: string | null;
  local_confirmation_schedule_snapshot: string | null;
  local_confirmation_partition_snapshot: string | null;
  local_confirmation_confirmed_at: string | null;
};

export type ProfessorLocalIntakeSlotOut = {
  session_id: string;
  label: string;
  start_at_utc: string;
  end_at_utc: string;
  timezone: string;
  course_type_name: string;
  location_name: string;
  capacity_max: number;
  booked_count: number;
  seats_remaining: number;
  recurrence_group_id: string | null;
};

export type ProfessorLocalIntakePartitionOut = {
  product_id: string;
  title: string;
  category_name: string | null;
  real_quantity: number;
  estimated_quantity: number;
};

export type ProfessorLocalIntakeAnswerOut = {
  label: string;
  value: string;
};

export type ProfessorLocalIntakeDetailOut = ProfessorLocalIntakeTaskOut & {
  normalized_payload_json: Record<string, unknown>;
  answers: ProfessorLocalIntakeAnswerOut[];
  slot_options: ProfessorLocalIntakeSlotOut[];
  partition_options: ProfessorLocalIntakePartitionOut[];
  local_confirmation_session_id: string | null;
  local_confirmation_product_id: string | null;
  local_confirmation_partition_not_required: boolean;
  local_confirmation_comment: string | null;
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

export type ProfessorInboxMessageOut = {
  id: string;
  channel: "EMAIL" | "SMS" | "PUSH" | string;
  subject: string;
  body: string;
  body_format: "TEXT" | "HTML" | string;
  status: string;
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
  professor_ids: string[];
  professor_display_names: string[];
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
  effective_teacher_ids: string[];
  effective_teacher_display_names: string[];
  requires_professor: boolean;
  allows_student_bookings: boolean;
  supports_student_time_overrides: boolean;
  location_label: string;
  type_label: string;
  status_label: string;
  title: string;
  description: string | null;
  public_description: string | null;
  private_description: string | null;
  professor_reminder_note: string | null;
  group_note: string | null;
  internal_note: string | null;
  start_at_utc: string;
  end_at_utc: string;
  is_all_day: boolean;
  capacity_max: number;
  booked_count: number;
  child_bookings_enabled: boolean;
  adult_bookings_enabled: boolean;
  adult_capacity_max: number | null;
  child_trial_bookings_enabled: boolean;
  adult_trial_bookings_enabled: boolean;
  status: "SCHEDULED" | "CANCELLED" | "COMPLETED" | string;
  auto_cancel_deadline_utc: string;
  auto_cancel_rule_enabled_override: boolean | null;
  auto_cancel_if_booked_less_than_override: number | null;
  auto_cancel_hours_before_start_override: number | null;
  cancel_reason: string | null;
  zoom_link: string | null;
  visibility_scopes: SessionAudienceScope[];
  booking_scopes: SessionAudienceScope[];
  visibility_scope: SessionAudienceScope;
  booking_scope: SessionAudienceScope;
  is_private: boolean;
  allow_online_booking: boolean;
  external_booking_price_ttc: string | null;
  show_external_remaining_seats: boolean;
  timezone: string;
  recurrence_group_id: string | null;
  recurrence_rule: string | null;
  recurrence_end_date: string | null;
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
  client_kind: "ADULT" | "CHILD";
  client_plan_subscription_id: string | null;
  status: string;
  booked_at: string;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  student_start_at_utc: string | null;
  student_end_at_utc: string | null;
  waitlist_position: number | null;
  student_note: string | null;
  internal_note: string | null;
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
  client_balance_default_date_mode: "TODAY" | "PACKAGE_END" | "FIXED_DATE";
  client_balance_default_date: string | null;
  bank_transfer_account_holder: string;
  bank_transfer_iban: string;
  bank_transfer_bic: string;
  legal_terms: string;
  legal_terms_en: string;
  logo_data_url: string;
};

export type PublicLegalTermsOut = {
  language: "fr" | "en";
  content: string;
  content_hash: string;
  version: string;
  updated_at: string | null;
  used_fallback: boolean;
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

export type AdminReferralCategorySettingsOut = {
  label: string;
  amount: string;
  active: boolean;
};

export type AdminReferralProgramSettingsOut = {
  enabled: boolean;
  currency: string;
  trigger_ratio: string;
  announcement_email_enabled: boolean;
  credit_email_enabled: boolean;
  categories: Record<string, AdminReferralCategorySettingsOut>;
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
  nature: "material" | "service" | string;
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

export type AdminCatalogRequestStatus = "PROCESSING" | "REJECTED" | "WAITING_STOCK" | "INVOICE_TO_SEND" | "TO_DELIVER" | "DELIVERED" | string;
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
  assigned_session_id: string | null;
  assigned_session_start_at: string | null;
  assigned_professor_id: string | null;
  assigned_professor_name: string | null;
  stock_transfer_id: string | null;
  stock_reserved_quantity: number;
  ready_at: string | null;
  professor_notified_at: string | null;
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
  stripe_webhook_secret_configured: boolean;
  payplug_test_secret_masked: string;
  payplug_live_secret_masked: string;
  mollie_test_api_key_masked: string;
  mollie_live_api_key_masked: string;
  stripe_test_secret_masked: string;
  stripe_live_secret_masked: string;
  stripe_webhook_secret_masked: string;
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
  email_provider: string;
  email_reply_to: string;
  email_subject_prefix: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_configured: boolean;
  smtp_password_masked: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_timeout_seconds: number;
  frontend_base_url: string;
  brevo_email_webhook_url: string;
  sms_provider: string;
  sms_sender: string;
  brevo_sms_api_key_configured: boolean;
  brevo_sms_api_key_masked: string;
  brevo_sms_webhook_url: string;
  quote_send_template_ref: string;
  quote_send_sms_template_ref: string;
  quote_reminder_template_ref: string;
  quote_reminder_sms_template_ref: string;
  quote_cancel_template_ref: string;
  quote_cancel_sms_template_ref: string;
  quote_expired_template_ref: string;
  quote_expired_sms_template_ref: string;
  quote_approved_template_ref: string;
  quote_rejected_template_ref: string;
  quote_change_requested_template_ref: string;
  quote_reminder_enabled: boolean;
  quote_reminder_sms_enabled: boolean;
  quote_reminder_lead_hours: number;
  quote_reminder_lead_hours_csv: string;
  quote_reminder_lead_hours_values: number[];
  quote_daily_job_local_time: string;
  quote_auto_cancel_enabled: boolean;
  quote_auto_cancel_delay_hours: number;
  quote_cancel_notification_enabled: boolean;
  quote_cancel_sms_notification_enabled: boolean;
  quote_expired_notification_enabled: boolean;
  quote_expired_sms_notification_enabled: boolean;
  delivery_enabled: boolean;
  delivery_error_message: string | null;
  sms_delivery_enabled: boolean;
  sms_delivery_error_message: string | null;
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
  subject_translations: LocalizedTextMap;
  body: string;
  body_translations: LocalizedTextMap;
  body_format: "TEXT" | "HTML";
  active: boolean;
  usage_contexts: string[];
  description: string | null;
  variables_hint: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type QuoteTemplateVariableOut = {
  key: string;
  label: string;
  description: string;
  example: string | null;
  category: string;
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

export type AdminFormulaRestrictionPeriod = "ACTIVE_BOOKINGS" | "DAY" | "WEEK" | "MONTH" | "ROLLING_MONTH" | "SEMESTER";

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
  is_trial_offer: boolean;
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
  first_purchase_signup_fee_enabled: boolean;
  first_purchase_partitions_enabled: boolean;
  first_purchase_partitions_price_value: string | null;
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
  is_trial_offer: boolean;
  purchase_link_allowed: boolean;
  purchase_url: string;
  price_ttc: string | null;
  currency: string;
  frequency_label: string | null;
  includes: string[];
  restriction_labels: string[];
  payment_methods: string[];
  base_price_ttc: string | null;
  first_purchase_fee_ttc: string | null;
  first_purchase_partitions_price_ttc: string | null;
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
  session_id: string | null;
  booking_user_id: string | null;
  planning_return_to: string | null;
  summary: PublicFormulaPurchaseSummaryOut;
};

export type GiftCardPublicPreviewOut = {
  redeem_token: string;
  status: "ACTIVE";
  plan_id: string;
  plan_name: string;
  plan_description: string | null;
  plan_kind: string;
  recipient_name: string | null;
  personal_message: string | null;
  expires_at: string | null;
  terms_required: boolean;
};

export type GiftCardRedeemOut = {
  gift_card_id: string;
  subscription_id: string;
  redeemed_for_user_id: string;
  plan_id: string;
  plan_name: string;
  credits_granted: number;
  expires_at: string | null;
  next_url: string;
};

export type AdminGiftCardOut = {
  id: string;
  code_suffix: string;
  status: string;
  source: string;
  plan_id: string;
  plan_name: string;
  external_order_ref: string | null;
  external_line_ref: string | null;
  purchaser_name: string | null;
  purchaser_email: string | null;
  recipient_name: string | null;
  recipient_email: string | null;
  face_value_ttc: string;
  purchase_price_ttc: string;
  discount_ttc: string;
  vat_rate: string;
  currency: string;
  paid_at: string | null;
  valid_from: string | null;
  expires_at: string | null;
  delivered_at: string | null;
  redeemed_at: string | null;
  redeemed_by_user_id: string | null;
  redeemed_for_user_id: string | null;
  subscription_id: string | null;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type AdminGiftCardCsvPreviewRowOut = {
  row_number: number;
  result: "READY" | "ALREADY_IMPORTED" | "BLOCKED";
  code_suffix: string | null;
  external_order_ref: string | null;
  external_line_ref: string | null;
  payment_status: string | null;
  product_name: string | null;
  face_value_ttc: string | null;
  purchase_price_ttc: string | null;
  messages: string[];
};

export type AdminGiftCardCsvPreviewOut = {
  plan_id: string;
  plan_name: string;
  total_rows: number;
  ready_rows: number;
  already_imported_rows: number;
  blocked_rows: number;
  rows: AdminGiftCardCsvPreviewRowOut[];
};

export type ClientSessionFormulaOptionOut = {
  formula_id: string;
  formula_code: string;
  formula_type: "PACK" | "SUBSCRIPTION" | "FORFAIT";
  is_trial_offer: boolean;
  name: string;
  description: string | null;
  price_ttc: string | null;
  currency: string;
  frequency_label: string | null;
  restriction_labels: string[];
  payment_methods: string[];
};

export type ClientSessionReservationMemberOptionOut = {
  member_id: string;
  member_display_name: string;
  member_kind: "ADULT" | "CHILD";
  booking_id: string | null;
  booking_status: string | null;
  action_code: string;
  action_label: string;
  status_label: string;
  reason: string | null;
  reason_code?: string | null;
  has_credit_coverage: boolean;
  coverage_source: string | null;
  direct_payment_amount_ttc: string | null;
  direct_payment_currency: string | null;
  formula_options: ClientSessionFormulaOptionOut[];
};

export type ClientSessionReservationOptionsOut = {
  session_id: string;
  session_title: string;
  session_status: string;
  is_full: boolean;
  online_booking_enabled: boolean;
  waitlist_enabled: boolean;
  members: ClientSessionReservationMemberOptionOut[];
};

export type ClientSessionPurchaseCatalogOut = {
  session_id: string;
  formula_options: ClientSessionFormulaOptionOut[];
  direct_payment_amount_ttc: string | null;
  direct_payment_currency: string | null;
};

export type ClientCatalogProductOut = {
  id: string;
  category_name: string | null;
  primary_location_name: string | null;
  title: string;
  price_incl_vat: string;
  vat_rate: string;
  stock_global_quantity: number;
  image_url: string | null;
  short_description: string | null;
  web_link: string | null;
  nature: string;
  is_virtual: boolean;
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
  lesson_format: "INDIVIDUAL" | "GROUP" | string;
  requires_professor: boolean;
  allows_student_bookings: boolean;
  supports_student_time_overrides: boolean;
  default_capacity: number;
  default_hourly_rate: string | null;
  default_course_rate_ttc: string | null;
  trial_course_enabled: boolean;
  trial_course_price_ttc: string | null;
  email_reminder_hours_before_start: number | null;
  sms_reminder_hours_before_start: number | null;
  min_booking_notice_hours_override: number | null;
  cancellation_deadline_hours_override: number | null;
  auto_cancel_if_booked_less_than_override: number | null;
  auto_cancel_hours_before_start_override: number | null;
  auto_cancel_rule_enabled: boolean;
  exclude_holidays_in_recurrence: boolean;
  exclude_school_vacations_in_recurrence: boolean;
  active: boolean;
  content_course_ids: string[];
  content_course_titles: string[];
};

export type AdminExternalContentCourseOut = {
  id: string;
  provider: string;
  external_id: string;
  slug: string | null;
  title: string;
  summary: string | null;
  level_code: string | null;
  status: string;
  cover_image_url: string | null;
  sections_count: number;
  lessons_count: number;
  last_synced_at: string | null;
};

export type AdminActivityContentMappingOut = {
  id: string;
  course_type_id: string;
  content_course_id: string;
  access_rule: string;
  sort_order: number;
  active: boolean;
  content_course_title: string;
  content_course_level_code: string | null;
  content_course_status: string;
  content_course_provider: string;
  content_course_external_id: string;
};

export type AdminExternalContentSyncOut = {
  provider: string;
  fetched_at: string;
  courses_seen: number;
  courses_created: number;
  courses_updated: number;
  sections_seen: number;
  sections_created: number;
  sections_updated: number;
  sections_deleted: number;
  lessons_seen: number;
  lessons_created: number;
  lessons_updated: number;
  lessons_deleted: number;
};

export type AdminExternalContentSettingsOut = {
  base_url: string;
  courses_endpoint: string;
  resolved_endpoint_url: string | null;
  bearer_token_configured: boolean;
  bearer_token_masked: string;
  timeout_seconds: number;
  updated_at: string | null;
};

export type AdminLegalEntityOut = {
  id: string;
  name: string;
  siren: string | null;
  siret: string | null;
  vat_number: string | null;
  address_text: string | null;
  accounting_email: string | null;
  phone: string | null;
  legal_form: "SAS" | "SA" | "SARL" | "EURL" | null;
  share_capital: string | null;
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
  lesson_format: "INDIVIDUAL" | "GROUP" | string;
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

export type AdminPlanningSimulationSlotOut = {
  slot_key: string;
  location_id: string | null;
  location_name: string;
  location_timezone: string | null;
  course_type_id: string | null;
  course_type_name: string;
  course_type_color_hex: string | null;
  course_type_mode: "ONLINE" | "ONSITE" | "ANY" | string | null;
  weekday: number;
  weekday_label: string;
  start_time: string;
  end_time: string;
  first_date: string | null;
  last_date: string | null;
  occurrence_count: number;
  live_session_count: number;
  capacity: number | null;
  capacity_min: number | null;
  capacity_max: number | null;
  booked_count: number;
  approved_quotes_count: number;
  pending_quotes_count: number;
  draft_quotes_count: number;
  projected_count: number;
  remaining_capacity: number | null;
  fill_rate: number | null;
  projected_fill_rate: number | null;
  quote_only: boolean;
  booked_students: string[];
  approved_quote_students: string[];
  pending_quote_students: string[];
  draft_quote_students: string[];
  notes: string[];
  teacher_assignment_id: string | null;
  teacher_assignment_professor_id: string | null;
  teacher_assignment_label: string | null;
  teacher_assignment_status: "PREVISIONAL" | "CONFIRMED" | null;
  teacher_assignment_ids: string[];
  teacher_assignment_professor_ids: Array<string | null>;
  teacher_assignment_labels: string[];
  teacher_assignment_statuses: Array<"PREVISIONAL" | "CONFIRMED">;
  teacher_assignment_warnings: Array<"TIME_OVERLAP" | "MULTI_SITE_HALF_DAY" | string>;
};

export type AdminPlanningSimulationSummaryOut = {
  location_count: number;
  slot_count: number;
  course_type_count: number;
  booked_count: number;
  approved_quotes_count: number;
  pending_quotes_count: number;
  draft_quotes_count: number;
  quote_only_slot_count: number;
};

export type AdminPlanningSimulationTeacherActivityNeedOut = {
  course_type_id: string | null;
  course_type_name: string;
  course_type_color_hex: string | null;
  slot_count: number;
  teaching_minutes: number;
  peak_concurrent_teachers: number;
  mobilized_teachers: number;
};

export type AdminPlanningSimulationTeacherTimeBucketOut = {
  start_time: string;
  end_time: string;
  total_teachers: number;
};

export type AdminPlanningSimulationTeacherTimelineRowOut = {
  location_id: string | null;
  location_name: string;
  course_type_id: string | null;
  course_type_name: string;
  course_type_color_hex: string | null;
  morning_peak_teachers: number;
  afternoon_peak_teachers: number;
  bucket_teachers: number[];
};

export type AdminPlanningSimulationTeacherDayNeedOut = {
  weekday: number;
  weekday_label: string;
  slot_count: number;
  teaching_minutes: number;
  peak_concurrent_teachers: number;
  mobilized_teachers: number;
  first_start_time: string | null;
  last_end_time: string | null;
  activities: AdminPlanningSimulationTeacherActivityNeedOut[];
  time_buckets: AdminPlanningSimulationTeacherTimeBucketOut[];
  timeline_rows: AdminPlanningSimulationTeacherTimelineRowOut[];
};

export type AdminPlanningSimulationTeacherNeedsOut = {
  summary: {
    active_day_count: number;
    slot_count: number;
    teaching_minutes: number;
    peak_concurrent_teachers: number;
    mobilized_teachers: number;
  };
  days: AdminPlanningSimulationTeacherDayNeedOut[];
  activities: AdminPlanningSimulationTeacherActivityNeedOut[];
};

export type AdminPlanningSimulationOut = {
  school_year_label: string;
  available_school_years: string[];
  location_filter_id: string | null;
  activity_filter_id: string | null;
  activity_group_filter: string | null;
  generated_at: string;
  summary: AdminPlanningSimulationSummaryOut;
  teacher_needs: AdminPlanningSimulationTeacherNeedsOut;
  slots: AdminPlanningSimulationSlotOut[];
};

export type AdminQuotePlanningAuditItemOut = {
  quote_id: string;
  quote_number: string;
  student_id: string;
  student_name: string;
  series_id: string;
  activity_name: string;
  location_name: string;
  slot_label: string;
  issue_codes: string[];
  expected_sessions: number;
  booked_sessions: number;
  invoiced_sessions: number;
  expected_start: string | null;
  expected_end: string | null;
  booked_start: string | null;
  booked_end: string | null;
  missing_dates: string[];
  unexpected_dates: string[];
  repairable: boolean;
  approved_for_automatic_repair: boolean;
};

export type AdminQuotePlanningAuditOut = {
  checked_at: string;
  school_year: string;
  checked_quotes: number;
  affected_series: number;
  issue_count: number;
  repairable_count: number;
  approved_repair_count: number;
  items: AdminQuotePlanningAuditItemOut[];
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

export type IntakeFamilyChildSummary = {
  intake_id: string;
  received_at: string;
  source_form_id: string;
  source_form_label: string | null;
  child_name: string;
  segment: string | null;
  status: string;
  course_1: string | null;
  course_2: string | null;
  solfege: string | null;
  masterclass: string | null;
  pass_recup: string | null;
};

export type IntakeFamilySummaryRow = {
  family_key: string;
  family_label: string;
  parent_name: string | null;
  parent_email: string | null;
  parent_phone: string | null;
  intake_count: number;
  children: IntakeFamilyChildSummary[];
};

export type GeneratedReportOut = {
  id: string;
  report_type: string;
  report_label: string;
  file_format: string;
  period_start: string | null;
  period_end: string | null;
  note: string | null;
  row_count: number;
  created_by_user_id: string | null;
  created_at: string;
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
  recipient_display_name: string | null;
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
  initial_payment_refundable: boolean;
  initial_payment_refunded: boolean;
};

export type SchoolEventStatus = "DRAFT" | "PUBLISHED" | "CLOSED" | "CANCELLED" | "COMPLETED";
export type SchoolEventAudience = "PUBLIC" | "CLIENTS";
export type SchoolEventRegistrationMode = "INDIVIDUAL_SLOT" | "GROUP_SESSION";
export type SchoolEventPaymentMode = "FREE" | "ON_SITE" | "ONLINE";
export type SchoolEventSlotStatus = "SCHEDULED" | "CANCELLED" | "COMPLETED";
export type SchoolEventRegistrationStatus =
  | "PENDING_PAYMENT"
  | "CONFIRMED"
  | "WAITLISTED"
  | "CANCELLED"
  | "ATTENDED"
  | "NO_SHOW";

export type SchoolEventLocationOut = {
  id: string;
  name: string;
  timezone: string;
  is_online: boolean;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: string | null;
};

export type SchoolEventVenueOut = SchoolEventLocationOut & { is_active: boolean };

export type SchoolEventPriceTierOut = {
  id: string;
  event_id: string;
  label_fr: string;
  label_en: string | null;
  price_ttc: string;
  sort_order: number;
  is_online_booking_enabled: boolean;
  is_active: boolean;
};

export type SchoolEventImageUploadOut = {
  image_url: string;
  storage_key: string;
};

export type SchoolEventSlotOut = {
  id: string;
  event_id: string;
  label: string | null;
  start_at_utc: string;
  end_at_utc: string;
  timezone: string;
  capacity_max: number;
  admin_capacity_max: number;
  booked_count: number;
  seats_remaining: number;
  admin_seats_remaining: number;
  waitlist_count: number;
  status: SchoolEventSlotStatus;
  location: SchoolEventLocationOut | null;
};

export type SchoolEventOut = {
  id: string;
  slug: string;
  title_fr: string;
  title_en: string | null;
  description_fr: string | null;
  description_en: string | null;
  category: string;
  image_url: string | null;
  status: SchoolEventStatus;
  audience: SchoolEventAudience;
  registration_mode: SchoolEventRegistrationMode;
  payment_mode: SchoolEventPaymentMode;
  location: SchoolEventLocationOut | null;
  booking_opens_at: string | null;
  booking_closes_at: string | null;
  price_ttc: string;
  price_tiers: SchoolEventPriceTierOut[];
  currency: string;
  max_per_family: number;
  waitlist_enabled: boolean;
  show_remaining_seats: boolean;
  cancellation_deadline_hours: number;
  collect_piece_info: boolean;
  collect_photo_consent: boolean;
  collect_performer_booking: boolean;
  confirmation_message_fr: string | null;
  confirmation_message_en: string | null;
  reminder_hours_before_start: number;
  reminder_sent_count: number;
  slots: SchoolEventSlotOut[];
  registration_count: number;
  waitlist_count: number;
  created_at: string;
  updated_at: string;
};

export type SchoolEventRegistrationOut = {
  id: string;
  group_id: string;
  event_id: string;
  event_slug: string;
  event_title_fr: string;
  event_title_en: string | null;
  slot_id: string;
  slot_label: string | null;
  start_at_utc: string;
  end_at_utc: string;
  timezone: string;
  location_name: string | null;
  booker_user_id: string | null;
  public_booker_first_name: string | null;
  public_booker_last_name: string | null;
  public_booker_email: string | null;
  public_booker_phone: string | null;
  participant_user_id: string | null;
  participant_display_name: string;
  party_size: number;
  guest_names: string[];
  answers: Record<string, unknown>;
  status: SchoolEventRegistrationStatus;
  unit_price_ttc_snapshot: string;
  price_tier_id: string | null;
  price_tier_label_snapshot: string | null;
  total_ttc_snapshot: string;
  currency_snapshot: string;
  payment_provider: string | null;
  payment_reference: string | null;
  payment_hold_expires_at: string | null;
  booked_at: string;
  cancelled_at: string | null;
  checked_in_at: string | null;
};

export type SchoolEventRegistrationCreateOut = {
  group_id: string;
  status: SchoolEventRegistrationStatus;
  registrations: SchoolEventRegistrationOut[];
  checkout_url: string | null;
};

export type SchoolEventAdminParticipantOptionOut = {
  id: string;
  display_name: string;
  email: string;
  client_kind: "ADULT" | "CHILD" | string;
};
