import Link from "next/link";
import ProgramMakeup from "../../../../components/program-makeup";
import { randomUUID } from "node:crypto";
import InvoicePartialPaymentModal from "../../../../components/invoice-partial-payment-modal";
import type { PartialPaymentContext } from "../../../../lib/invoice-partial-payment";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  approveAdminClientBillingAdjustmentAction,
  cancelAdminClientInvoiceAction,
  createAdultForChildAction,
  createAdminClientNoteAction,
  createAdminClientQuoteChangeAction,
  createChildForAdultAction,
  adminFinalizeClientPurchaseAction,
  adminClientActionPlaceholder,
  adminSendClientPushAction,
  adminOpenClientPurchaseTermsAction,
  cancelAdminClientSubscriptionAction,
  linkExistingFamilyMembersAction,
  adminPurchasePlanForClientAction,
  adminViewClientPortalAction,
  createAdminClientRangeInvoiceAction,
  createAdminClientRangeInvoiceCreditNoteAction,
  deleteAdminClientRangeInvoiceAction,
  markAdminClientRangeInvoiceBankTransferPaidAction,
  markAdminClientRangeInvoiceManualBankTransferPaidAction,
  reissueAdminClientRangeInvoiceAction,
  createAdminClientManualTransactionAction,
  updateAdminClientManualTransactionAction,
  reconcileAdminClientChecksAction,
  updateAdminClientManualTransactionStatusAction,
  deleteAdminClientManualTransactionAction,
  dismissAdminClientBillingAdjustmentAction,
  decideAdminClientSubscriptionCancellationAction,
  generateAdminClientBookingFinalInvoiceAction,
  refundAdminClientPaymentAction,
  refundAdminClientPaymentReceiptAction,
  sendAdminClientPaymentReceiptAction,
  sendAdminClientRangeInvoiceEmailAction,
  sendAdminClientPartialPaymentAction,
  splitAdminClientRangeInvoiceByFamilyAction,
  sendAdminClientMessageAction,
  setFamilyBillingRecipientAction,
  setupAdminClientSubscriptionBillingAction,
  reactivateAdminClientDeliveryAction,
  suspendAdminClientSubscriptionAction,
  unlinkFamilyMembersAction,
  updateAdminClientForfaitPricingAction,
  updateAdminClientSubscriptionExpiryAction,
  updateAdminClientRangeInvoiceStatusAction,
  updateAdminClientManualCreditAction,
  updateAdminClientAction,
  updateAdminClientGroupsAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { regularScheduleSummaries } from "../../../../lib/client-schedule-summary";
import { hasAdminPermission } from "../../../../lib/admin-access";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  DEFAULT_COUNTRY,
  DEFAULT_CURRENCY,
  DEFAULT_TIMEZONE,
  TIMEZONE_OPTIONS,
  labelFromOptions,
} from "../../../../lib/reference-data";
import ManualTransactionNonCashFlowFields from "../../../../components/manual-transaction-noncashflow-fields";
import ManualTransactionLegalEntityFields from "../../../../components/manual-transaction-legal-entity-fields";
import ManualCheckSubmitButtons from "../../../../components/manual-check-submit-buttons";
import RichMessageEditor from "../../../../components/rich-message-editor";
import ModalFirstErrorFocus from "../../../../components/modal-first-error-focus";
import ClientLookupSingleSelect from "../../../../components/client-lookup-single-select";
import ClientActionSubmitButton from "../../../../components/client-action-submit-button";
import SendClientAccessLink from "../../../../components/send-client-access-link";
import InvoiceLineSelection from "../../../../components/invoice-line-selection";
import FamilyBillingSplitEditor from "../../../../components/family-billing-split-editor";
import ConfirmSubmitButton from "../../../../components/confirm-submit-button";
import AutomaticInvoicePreview from "../../../../components/automatic-invoice-preview";
import ClientTabNavigation from "../../../../components/client-tab-navigation";
import type {
  AdminClientBookingOut,
  AdminClientFamilyOut,
  AdminClientGroupOut,
  AdminClientMessageOut,
  AdminClientManualCreditOut,
  AdminClientNoteOut,
  AdminClientOut,
  AdminClientPaymentOut,
  AdminStudentQuoteChangeOut,
  AdminConfigAccountOut,
  AdminFormulaOut,
  AdminLegalEntityOut,
  AdminLegacyInvoiceOut,
  AdminRangeInvoiceOut,
  AdminRangeInvoiceEmailPreviewOut,
  AdminClientSubscriptionOut,
  AdminPaymentMethodsOut,
  AdminCatalogProductOut,
  AdminProductCategoriesOut,
  PlanOut,
  MakeupStudentSummaryOut,
  LocationOut,
  UserOut,
} from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, translateBackendMessage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type PageProps = {
  params: { clientId: string };
  searchParams: SearchParams;
};

type ClientTab = "fiche" | "infos" | "famille" | "messages" | "paiements" | "factures" | "reservations" | "changements";
type ApprovedQuoteOption = {
  id: string;
  quote_number: string;
  total_ttc: string;
  currency: string;
  approved_at: string | null;
  school_year_label: string | null;
};
type BookingWorkflowTone = "status-ok" | "status-warn" | "status-off" | "status-info" | "status-cancelled";
type BookingWorkflowStep = {
  label: string;
  value: string;
  toneClass: BookingWorkflowTone;
  helper: string;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function readParams(params: SearchParams, key: string): string[] {
  const value = params[key];
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  const normalized = String(value || "").trim();
  return normalized ? [normalized] : [];
}

function immediateBackendResult<T>(data: T): Promise<{ ok: true; status: 200; data: T }> {
  return Promise.resolve({ ok: true, status: 200, data });
}

function parseToggleParam(value: string, fallback: boolean): boolean {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (!normalized) {
    return fallback;
  }
  if (normalized === "1" || normalized === "true" || normalized === "on" || normalized === "yes") {
    return true;
  }
  if (normalized === "0" || normalized === "false" || normalized === "off" || normalized === "no") {
    return false;
  }
  return fallback;
}

function parseInvoiceFieldErrors(raw: string): Record<string, string> {
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      const normalizedKey = String(key || "").trim();
      const normalizedValue = String(value || "").trim();
      if (!normalizedKey || !normalizedValue) {
        continue;
      }
      out[normalizedKey] = normalizedValue;
    }
    return out;
  } catch {
    return {};
  }
}

function cloneSearchParams(params: SearchParams): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(params)) {
    if (Array.isArray(rawValue)) {
      for (const value of rawValue) {
        if (value !== undefined) {
          search.append(key, value);
        }
      }
      continue;
    }
    if (rawValue !== undefined) {
      search.set(key, rawValue);
    }
  }
  return search;
}

function parseTab(value: string): ClientTab {
  if (value === "infos" || value === "famille" || value === "messages" || value === "paiements" || value === "factures" || value === "reservations" || value === "changements") {
    return value;
  }
  return "fiche";
}

function formatDate(value: string, language: UiLanguage = "fr"): string {
  return new Date(value).toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  });
}

function formatDateOnly(value: string | null, language: UiLanguage = "fr"): string {
  if (!value) {
    return uiText(language, "admin.client_detail.not_provided_feminine");
  }
  return new Date(value).toLocaleDateString(localeForUiLanguage(language), {
    dateStyle: "medium",
  });
}

function formatDateOnlyNumeric(value: string, language: UiLanguage = "fr"): string {
  return new Date(value).toLocaleDateString(localeForUiLanguage(language), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatDateInput(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value.getTime());
  next.setDate(next.getDate() + days);
  return next;
}

function addMonths(value: Date, months: number): Date {
  const next = new Date(value.getTime());
  const sourceDay = next.getDate();
  next.setDate(1);
  next.setMonth(next.getMonth() + months);
  const daysInMonth = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
  next.setDate(Math.min(sourceDay, daysInMonth));
  return next;
}

type InvoiceFrequency = "MONTHLY" | "BIMONTHLY" | "QUARTERLY" | "YEARLY";

function formatDateForInput(value: string | null | undefined, fallback: string): string {
  if (!value) {
    return fallback;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }
  return parsed.toISOString().slice(0, 10);
}

function isDateInput(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function dateInputFromMaybeIso(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const datePart = value.slice(0, 10);
  return isDateInput(datePart) ? datePart : null;
}

function latestDateInput(values: Array<string | null | undefined>): string | null {
  const dates = values
    .map((value) => dateInputFromMaybeIso(value))
    .filter((value): value is string => Boolean(value))
    .sort();
  return dates.length > 0 ? dates[dates.length - 1] : null;
}

function endOfDateUtcMs(value: string): number {
  if (!isDateInput(value)) {
    return Number.POSITIVE_INFINITY;
  }
  return new Date(`${value}T23:59:59.999Z`).getTime();
}

function formatDateInputLabel(value: string, language: UiLanguage = "fr"): string {
  if (!isDateInput(value)) {
    return value;
  }
  return new Date(`${value}T00:00:00.000Z`).toLocaleDateString(localeForUiLanguage(language), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
}

function truncatePreview(value: string, maxLength = 100): string {
  const normalized = String(value ?? "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength).trimEnd()}...`;
}

function formatMoney(value: string | null | undefined, currency: string, language: UiLanguage = "fr"): string {
  const amount = Number(value ?? "0");
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return "0%";
  }
  return `${Math.round(value)}%`;
}

function formatVatRateLabel(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const rate = Number(value ?? "0");
  if (!Number.isFinite(rate) || rate <= 0) {
    return "0%";
  }
  const hasDecimals = Math.abs(rate % 1) > 0.0001;
  return `${new Intl.NumberFormat(localeForUiLanguage(language), {
    minimumFractionDigits: hasDecimals ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(rate)}%`;
}

function billingMethodLabel(code: string | null, language: UiLanguage = "fr"): string {
  const normalized = (code ?? "").toUpperCase();
  if (normalized === "CARD_ONLINE") {
    return uiText(language, "admin.client_detail.billing.card_online");
  }
  if (normalized === "SEPA_DEBIT") {
    return uiText(language, "admin.client_detail.billing.sepa_debit");
  }
  if (normalized === "CARD_TERMINAL") {
    return uiText(language, "admin.client_detail.billing.card_terminal");
  }
  if (normalized === "BANK_TRANSFER") {
    return uiText(language, "admin.client_detail.billing.bank_transfer");
  }
  if (normalized === "CASH") {
    return uiText(language, "admin.client_detail.billing.cash");
  }
  if (normalized === "CHECK") {
    return uiText(language, "admin.client_detail.billing.check");
  }
  if (normalized === "PAYPAL") {
    return "PayPal";
  }
  if (normalized === "GIFT_CARD") {
    return uiText(language, "admin.client_detail.billing.gift_card");
  }
  if (normalized === "FACTURATION_AUTO") {
    return uiText(language, "admin.client_detail.billing.invoice");
  }
  return code || uiText(language, "admin.client_detail.not_defined");
}

function paymentMethodOptionLabel(method: { code: string; label: string }, language: UiLanguage = "fr"): string {
  const normalized = (method.code || "").trim().toUpperCase();
  if (
    normalized === "CARD_ONLINE" ||
    normalized === "SEPA_DEBIT" ||
    normalized === "CARD_TERMINAL" ||
    normalized === "BANK_TRANSFER" ||
    normalized === "CASH" ||
    normalized === "CHECK" ||
    normalized === "PAYPAL" ||
    normalized === "GIFT_CARD" ||
    normalized === "FACTURATION_AUTO"
  ) {
    return billingMethodLabel(normalized, language);
  }
  return method.label;
}

function paymentSourceLabel(source: string, language: UiLanguage = "fr"): string {
  const normalized = source.trim().toUpperCase();
  if (normalized === "PLAN_PURCHASE") {
    return uiText(language, "admin.client_detail.payment_source.plan_purchase");
  }
  if (normalized === "BOOKING") {
    return uiText(language, "admin.client_detail.payment_source.booking");
  }
  if (normalized === "BOOKING_CREDIT") {
    return uiText(language, "admin.client_detail.payment_source.booking_credit");
  }
  if (normalized === "MANUAL") {
    return uiText(language, "admin.client_detail.payment_source.manual");
  }
  if (normalized === "LEGACY_INVOICE") {
    return uiText(language, "admin.client_detail.payment_source.legacy_invoice");
  }
  return normalized || uiText(language, "admin.client_detail.payment_source.payment");
}

function isLegacyInvoicePayment(row: AdminClientPaymentOut): boolean {
  return (row.source || "").trim().toUpperCase() === "LEGACY_INVOICE";
}

function invoicePaymentKey(row: AdminClientPaymentOut): string {
  return `${String(row.source || "").trim().toUpperCase()}:${row.id}`;
}

function paymentStatusLabel(status: string, language: UiLanguage = "fr"): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "REFUNDED") {
    return uiText(language, "admin.client_detail.payment_status.refunded");
  }
  if (normalized === "PAID") {
    return uiText(language, "admin.client_detail.payment_status.paid");
  }
  if (normalized === "CREDIT_NOTE") {
    return uiText(language, "admin.client_detail.payment_status.credit_note");
  }
  if (normalized === "CHECK_RECEIVED") {
    return uiText(language, "admin.client_detail.payment_status.check_received");
  }
  if (normalized === "CHECK_DEPOSITED") {
    return uiText(language, "admin.client_detail.payment_status.check_deposited");
  }
  if (normalized === "CHECK_REFUSED") {
    return uiText(language, "admin.client_detail.payment_status.check_refused");
  }
  if (normalized === "INCLUDED_PLAN") {
    return uiText(language, "admin.client_detail.payment_status.included_plan");
  }
  if (normalized === "BOOKED" || normalized === "ATTENDED" || normalized === "NO_SHOW") {
    return uiText(language, "admin.client_detail.payment_status.to_bill");
  }
  if (normalized === "INVOICED") {
    return uiText(language, "admin.client_detail.payment_status.invoiced");
  }
  if (normalized === "FAILED") {
    return uiText(language, "admin.client_detail.payment_status.failed");
  }
  if (normalized === "PENDING" || normalized === "PENDING_PAYMENT" || normalized === "WAITLISTED" || normalized === "TRIAL") {
    return uiText(language, "admin.client_detail.payment_status.pending");
  }
  if (normalized === "RESPONSABLE") {
    return "Responsable";
  }
  if (normalized === "ACTIVE") {
    return uiText(language, "admin.client_detail.payment_status.active");
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return uiText(language, "admin.client_detail.payment_status.excused_absence");
  }
  if (normalized === "NOT_BILLABLE") {
    return uiText(language, "admin.client_detail.payment_status.not_billable");
  }
  if (normalized === "CANCELLED" || normalized === "EXPIRED" || normalized === "ARCHIVED" || normalized === "INACTIVE") {
    return uiText(language, "admin.client_detail.payment_status.cancelled");
  }
  return normalized || uiText(language, "admin.client_detail.unknown");
}

function parseAmountFilter(value: string): number | null {
  const normalized = value.replace(",", ".").trim();
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.round(parsed * 100) / 100;
}

function isIncludedPlanBooking(row: AdminClientPaymentOut): boolean {
  const source = (row.source || "").trim().toUpperCase();
  const status = (row.status || "").trim().toUpperCase();
  if (source !== "BOOKING") {
    return false;
  }
  if (status === "INCLUDED_PLAN") {
    return true;
  }
  if (status !== "BOOKED" && status !== "ATTENDED" && status !== "NO_SHOW") {
    return false;
  }
  const total = Number(row.total_incl_vat || "0");
  return Number.isFinite(total) && Math.abs(total) < 0.01 && Boolean(row.reference);
}

function isManualChargeAwaitingInvoice(row: AdminClientPaymentOut): boolean {
  const source = (row.source || "").trim().toUpperCase();
  if (source !== "MANUAL") {
    return false;
  }
  const status = normalizePaymentStatus(row.status);
  if (status !== "PENDING") {
    return false;
  }
  const manualType = (row.manual_transaction_type || "").trim().toUpperCase();
  if (manualType !== "CHARGE") {
    return false;
  }
  const invoiceNumber = (row.invoice_number || "").trim();
  if (invoiceNumber) {
    return false;
  }
  const total = Number(row.total_incl_vat || "0");
  return Number.isFinite(total) && total > 0;
}

function paymentStatusDisplayLabel(row: AdminClientPaymentOut, language: UiLanguage = "fr"): string {
  if (isIncludedPlanBooking(row)) {
    return uiText(language, "admin.client_detail.payment_status.included_plan");
  }
  if (isManualChargeAwaitingInvoice(row)) {
    return uiText(language, "admin.client_detail.payment_status.to_bill");
  }
  return paymentStatusLabel(row.status, language);
}

const PAID_PAYMENT_STATUSES = new Set(["PAID", "SUCCEEDED", "COMPLETED"]);
const PENDING_PAYMENT_STATUSES = new Set([
  "PENDING",
  "PENDING_PAYMENT",
  "WAITLISTED",
  "TRIAL",
  "OPEN",
  "CREATED",
  "PROCESSING",
  "WAITING_PAYMENT",
  "FAILED",
  "CHECK_RECEIVED",
  "CHECK_DEPOSITED",
  "CHECK_REFUSED",
  "BOOKED",
  "ATTENDED",
  "NO_SHOW",
  "INVOICED",
]);
const CANCELLED_PAYMENT_STATUSES = new Set(["CANCELLED", "EXPIRED", "INACTIVE", "ARCHIVED"]);
const ACTIVE_SUBSCRIPTION_BOOKING_STATUSES = new Set(["BOOKED", "WAITLISTED"]);

function normalizePaymentStatus(status: string): string {
  return (status || "").trim().toUpperCase();
}

function shouldCountInClientBalance(row: AdminClientPaymentOut): boolean {
  if (isLegacyInvoicePayment(row)) {
    return false;
  }
  const status = normalizePaymentStatus(row.status);
  if (
    status === "NOT_BILLABLE" ||
    status === "INCLUDED_PLAN" ||
    status === "REFUNDED" ||
    status === "FAILED" ||
    CANCELLED_PAYMENT_STATUSES.has(status)
  ) {
    return false;
  }
  if (isPaidPreRegistrationDepositCharge(row)) {
    return false;
  }

  if (row.source.trim().toUpperCase() === "MANUAL") {
    return true;
  }

  return PENDING_PAYMENT_STATUSES.has(status);
}

function isRefundablePlanPurchase(row: AdminClientPaymentOut): boolean {
  return (
    (row.source || "").trim().toUpperCase() === "PLAN_PURCHASE" &&
    PAID_PAYMENT_STATUSES.has(normalizePaymentStatus(row.status)) &&
    !isRecordedClientRefund(row)
  );
}

function isManualPaymentMovement(row: AdminClientPaymentOut): boolean {
  if ((row.source || "").trim().toUpperCase() !== "MANUAL") {
    return false;
  }
  const status = normalizePaymentStatus(row.status);
  if (!PAID_PAYMENT_STATUSES.has(status)) {
    return false;
  }
  const manualType = (row.manual_transaction_type || "").trim().toUpperCase();
  if (manualType === "PAYMENT") {
    return true;
  }
  return false;
}

function isManualRefundMovement(row: AdminClientPaymentOut): boolean {
  return (
    (row.source || "").trim().toUpperCase() === "MANUAL" &&
    (row.manual_transaction_type || "").trim().toUpperCase() === "REFUND" &&
    PAID_PAYMENT_STATUSES.has(normalizePaymentStatus(row.status))
  );
}

function isTrackedCheckPayment(row: AdminClientPaymentOut): boolean {
  return (
    (row.source || "").trim().toUpperCase() === "MANUAL" &&
    (row.manual_transaction_type || "").trim().toUpperCase() === "PAYMENT" &&
    (row.payment_method_code || "").trim().toUpperCase() === "CHECK"
  );
}

function isReceivedManualPaymentMovement(row: AdminClientPaymentOut): boolean {
  if ((row.source || "").trim().toUpperCase() !== "MANUAL") {
    return false;
  }
  if ((row.manual_transaction_type || "").trim().toUpperCase() !== "PAYMENT") {
    return false;
  }
  const status = normalizePaymentStatus(row.status);
  return PAID_PAYMENT_STATUSES.has(status) || status === "CHECK_RECEIVED" || status === "CHECK_DEPOSITED";
}

function isReceivedClientPayment(row: AdminClientPaymentOut): boolean {
  const source = (row.source || "").trim().toUpperCase();
  const status = normalizePaymentStatus(row.status);
  const total = Number(row.total_incl_vat || "0");
  if (!Number.isFinite(total) || total <= 0) {
    return false;
  }
  if (source === "BOOKING") {
    // Booking receipts are counted from AdminClientBookingOut to avoid
    // counting the same payment twice in the consolidated overview.
    return false;
  }
  if (source === "MANUAL") {
    return isReceivedManualPaymentMovement(row);
  }
  return PAID_PAYMENT_STATUSES.has(status);
}

function isRecordedClientRefund(row: AdminClientPaymentOut): boolean {
  return Boolean(row.refunded_at) || normalizePaymentStatus(row.status) === "REFUNDED";
}

function paymentNeedsFinalInvoice(row: AdminClientPaymentOut): boolean {
  const source = (row.source || "").trim().toUpperCase();
  if (source === "BOOKING" || source === "BOOKING_CREDIT" || source === "LEGACY_INVOICE") {
    return false;
  }
  if (row.invoice_number || row.invoice_note_id) {
    return false;
  }
  if (isManualChargeAwaitingInvoice(row)) {
    return true;
  }
  if (source === "MANUAL") {
    return false;
  }
  return isReceivedClientPayment(row);
}

function isPaidPreRegistrationDepositCharge(row: AdminClientPaymentOut): boolean {
  if ((row.source || "").trim().toUpperCase() !== "MANUAL") {
    return false;
  }
  const status = normalizePaymentStatus(row.status);
  if (!PAID_PAYMENT_STATUSES.has(status)) {
    return false;
  }
  const manualType = (row.manual_transaction_type || "").trim().toUpperCase();
  const category = (row.category || "").trim().toUpperCase();
  return manualType === "CHARGE" && category === "PRE_REGISTRATION_DEPOSIT";
}

function isManualDiscountMovement(row: AdminClientPaymentOut): boolean {
  return (
    (row.source || "").trim().toUpperCase() === "MANUAL" &&
    (row.manual_transaction_type || "").trim().toUpperCase() === "DISCOUNT"
  );
}

function invoiceStatusLabel(status: string | null, language: UiLanguage = "fr"): string {
  const normalized = (status ?? "").trim().toUpperCase();
  if (normalized === "CREDIT_NOTE") {
    return uiText(language, "admin.client_detail.invoice_status.credit_note");
  }
  if (normalized === "PAID") {
    return uiText(language, "admin.client_detail.invoice_status.paid");
  }
  if (normalized === "CANCELLED") {
    return uiText(language, "admin.client_detail.invoice_status.cancelled");
  }
  if (normalized === "PENDING") {
    return uiText(language, "admin.client_detail.invoice_status.pending");
  }
  return uiText(language, "admin.client_detail.invoice_status.default");
}

function bookingStatusLabel(status: string | null, language: UiLanguage = "fr"): string {
  const normalized = (status ?? "").trim().toUpperCase();
  if (normalized === "BOOKED") {
    return uiText(language, "client.status_booked");
  }
  if (normalized === "WAITLISTED") {
    return uiText(language, "client.status_waitlisted");
  }
  if (normalized === "CANCELLED") {
    return uiText(language, "client.status_cancelled");
  }
  if (normalized === "COMPLETED") {
    return uiText(language, "client.status_completed");
  }
  if (normalized === "ATTENDED") {
    return uiText(language, "client.status_attended");
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return uiText(language, "client.status_excused_absence");
  }
  if (normalized === "NO_SHOW") {
    return uiText(language, "admin.client_detail.booking_status.no_show");
  }
  if (normalized === "PENDING_PAYMENT") {
    return uiText(language, "admin.client_detail.booking_status.pending_payment");
  }
  if (normalized === "SCHEDULED") {
    return uiText(language, "admin.client_detail.booking_status.scheduled");
  }
  if (normalized === "PAID") {
    return uiText(language, "client.status_paid");
  }
  if (normalized === "PENDING") {
    return uiText(language, "client.status_pending");
  }
  return normalized || uiText(language, "admin.client_detail.unknown");
}

function normalizedBookingStatus(row: AdminClientBookingOut): string {
  return (row.status || "").trim().toUpperCase();
}

function normalizedSessionStatus(row: AdminClientBookingOut): string {
  return (row.session_status || "").trim().toUpperCase();
}

function bookingHasNoCharge(row: AdminClientBookingOut): boolean {
  const total = Number(row.total_incl_vat_snapshot || "0");
  return Number.isFinite(total) && Math.abs(total) < 0.01;
}

function bookingIsIncludedInPlan(row: AdminClientBookingOut): boolean {
  return bookingHasNoCharge(row) && Boolean(row.client_plan_subscription_id);
}

function bookingCannotGenerateFinalInvoice(row: AdminClientBookingOut): boolean {
  const bookingStatus = normalizedBookingStatus(row);
  return (
    bookingStatus === "CANCELLED" ||
    bookingStatus === "EXCUSED_ABSENCE" ||
    row.payment_refunded ||
    bookingHasNoCharge(row)
  );
}

function canGenerateFinalInvoiceForBooking(row: AdminClientBookingOut): boolean {
  return !row.final_invoice_generated && !bookingCannotGenerateFinalInvoice(row) && normalizedSessionStatus(row) === "COMPLETED";
}

function waitsForServiceCompletion(row: AdminClientBookingOut): boolean {
  return !row.final_invoice_generated && !bookingCannotGenerateFinalInvoice(row) && normalizedSessionStatus(row) !== "COMPLETED";
}

function bookingWorkflowSteps(row: AdminClientBookingOut, language: UiLanguage = "fr"): BookingWorkflowStep[] {
  const bookingStatus = normalizedBookingStatus(row);
  const sessionStatus = normalizedSessionStatus(row);
  const hasNoCharge = bookingHasNoCharge(row);
  const includedInPlan = bookingIsIncludedInPlan(row);
  const receiptStatus = (row.payment_receipt_status || "").trim().toUpperCase();
  const finalInvoiceStatus = (row.final_invoice_status || "").trim().toUpperCase();
  const paymentLabel = uiText(language, "admin.client_detail.booking_workflow.payment");
  const receiptLabel = uiText(language, "admin.client_detail.booking_workflow.receipt");
  const refundLabel = uiText(language, "admin.client_detail.booking_workflow.refund");
  const finalInvoiceLabel = uiText(language, "admin.client_detail.booking_workflow.final_invoice");

  if (row.payment_refunded) {
    const refundedAmount = formatMoney(
      row.payment_refunded_amount ?? row.payment_received_amount ?? row.total_incl_vat_snapshot,
      row.currency_snapshot,
      language,
    );
    return [
      {
        label: paymentLabel,
        value: uiText(language, "admin.client_detail.booking_workflow.value_refunded"),
        toneClass: "status-cancelled",
        helper: `${refundedAmount}${row.payment_refunded_at ? ` · ${formatDate(row.payment_refunded_at, language)}` : ""}`,
      },
      {
        label: refundLabel,
        value: row.payment_refund_email_sent_at
          ? uiText(language, "admin.client_detail.booking_workflow.value_sent")
          : uiText(language, "admin.client_detail.booking_workflow.value_notify"),
        toneClass: row.payment_refund_email_sent_at ? "status-ok" : "status-warn",
        helper:
          row.payment_refund_reason ||
          (row.payment_refund_email_sent_at
            ? uiText(language, "admin.client_detail.booking_workflow.helper_client_received_refund")
            : uiText(language, "admin.client_detail.booking_workflow.helper_refund_confirmation_to_send")),
      },
      {
        label: finalInvoiceLabel,
        value: uiText(language, "admin.client_detail.booking_workflow.value_not_invoiced"),
        toneClass: "status-off",
        helper: uiText(language, "admin.client_detail.booking_workflow.helper_cancelled_refunded"),
      },
    ];
  }

  if (hasNoCharge && bookingStatus !== "CANCELLED") {
    return [
      {
        label: paymentLabel,
        value: includedInPlan
          ? uiText(language, "admin.client_detail.booking_workflow.value_included_plan")
          : uiText(language, "admin.client_detail.booking_workflow.value_no_charge"),
        toneClass: "status-ok",
        helper: includedInPlan
          ? uiText(language, "admin.client_detail.booking_workflow.helper_included_plan", {
              plan: row.plan_name || uiText(language, "admin.client_detail.booking_workflow.plan_fallback"),
            })
          : uiText(language, "admin.client_detail.booking_workflow.helper_no_charge"),
      },
      {
        label: receiptLabel,
        value: uiText(language, "admin.client_detail.booking_workflow.value_not_applicable"),
        toneClass: "status-off",
        helper: uiText(language, "admin.client_detail.booking_workflow.helper_no_receipt_required"),
      },
      {
        label: finalInvoiceLabel,
        value: uiText(language, "admin.client_detail.booking_workflow.value_not_invoiced"),
        toneClass: "status-off",
        helper: includedInPlan
          ? uiText(language, "admin.client_detail.booking_workflow.helper_plan_already_invoiced")
          : uiText(language, "admin.client_detail.booking_workflow.helper_no_invoice_required"),
      },
    ];
  }

  const paymentStep: BookingWorkflowStep = row.payment_received
    ? {
        label: paymentLabel,
        value: uiText(language, "admin.client_detail.booking_workflow.value_received"),
        toneClass: "status-ok",
        helper: `${formatMoney(row.payment_received_amount ?? row.total_incl_vat_snapshot, row.currency_snapshot, language)}${
          row.payment_received_at ? ` · ${formatDate(row.payment_received_at, language)}` : ""
        }`,
      }
      : bookingStatus === "CANCELLED"
      ? {
          label: paymentLabel,
          value: uiText(language, "admin.client_detail.booking_workflow.value_not_applicable"),
          toneClass: "status-off",
          helper: uiText(language, "admin.client_detail.booking_workflow.helper_cancelled_before_payment"),
        }
      : bookingStatus === "PENDING_PAYMENT"
        ? {
            label: paymentLabel,
            value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
            toneClass: "status-warn",
            helper: uiText(language, "admin.client_detail.booking_workflow.helper_pending_psp"),
          }
      : {
          label: paymentLabel,
          value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
          toneClass: "status-warn",
          helper: uiText(language, "admin.client_detail.booking_workflow.helper_no_confirmed_payment"),
        };

  let receiptStep: BookingWorkflowStep;
  if (row.payment_receipt_sent_at) {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_sent"),
      toneClass: "status-ok",
      helper: `${row.payment_receipt_number || uiText(language, "admin.client_detail.booking_workflow.receipt_created_fallback")} · ${formatDate(
        row.payment_receipt_sent_at,
        language,
      )}`,
    };
  } else if (receiptStatus === "COMPLETED") {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_resend"),
      toneClass: "status-warn",
      helper: row.payment_receipt_number || uiText(language, "admin.client_detail.booking_workflow.helper_receipt_ready"),
    };
  } else if (row.payment_received) {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_create"),
      toneClass: "status-warn",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_receipt_missing"),
    };
  } else if (bookingStatus === "CANCELLED") {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_not_applicable"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_receipt_not_applicable"),
    };
  } else if (bookingStatus === "PENDING_PAYMENT") {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_receipt_after_validation"),
    };
  } else {
    receiptStep = {
      label: receiptLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_receipt_after_payment"),
    };
  }

  let invoiceStep: BookingWorkflowStep;
  if (row.final_invoice_generated) {
    invoiceStep = {
      label: finalInvoiceLabel,
      value:
        finalInvoiceStatus === "PAID"
          ? uiText(language, "admin.client_detail.booking_workflow.value_issued_paid")
          : finalInvoiceStatus === "CANCELLED"
            ? uiText(language, "admin.client_detail.booking_workflow.value_cancelled")
            : uiText(language, "admin.client_detail.booking_workflow.value_issued"),
      toneClass:
        finalInvoiceStatus === "PAID"
          ? "status-ok"
          : finalInvoiceStatus === "CANCELLED"
            ? "status-cancelled"
            : "status-info",
      helper: row.final_invoice_number || invoiceStatusLabel(row.final_invoice_status, language),
    };
  } else if (bookingStatus === "EXCUSED_ABSENCE") {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_not_invoiced"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_excused_absence_no_invoice"),
    };
  } else if (bookingStatus === "CANCELLED") {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_not_invoiced"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_cancelled_no_invoice"),
    };
  } else if (bookingStatus === "PENDING_PAYMENT") {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_pay_then_complete"),
    };
  } else if (sessionStatus === "COMPLETED") {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_to_issue"),
      toneClass: "status-warn",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_invoice_ready"),
    };
  } else if (row.payment_received) {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_on_completion"),
      toneClass: "status-info",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_invoice_on_completion"),
    };
  } else {
    invoiceStep = {
      label: finalInvoiceLabel,
      value: uiText(language, "admin.client_detail.booking_workflow.value_pending"),
      toneClass: "status-off",
      helper: uiText(language, "admin.client_detail.booking_workflow.helper_invoice_follows_completion"),
    };
  }

  return [paymentStep, receiptStep, invoiceStep];
}

const INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::";

type RangeInvoiceNotePayload = {
  kind: "INVOICE_RANGE";
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
  auto_cycle_start_date?: string;
  auto_period_scope: "FUTURE" | "PAST";
  auto_frequency: "WEEKLY" | "MONTHLY";
  auto_repeat_every: number;
  auto_layout_style: "NORMAL" | "CONDENSED";
  auto_include_previous_balance: boolean;
  auto_send_email: boolean;
  auto_footer_note?: string;
  auto_exclude_pack_subscription_lines: boolean;
  include_pending: boolean;
  include_cancelled: boolean;
  included_payment_keys: string[];
  totals_by_currency: Record<string, string>;
  total_to_pay_by_currency?: Record<string, string>;
  seller_legal_entity_id?: string;
  billing_entity?: string;
  invoice_status: "ISSUED" | "PAID" | "CANCELLED" | "CREDIT_NOTE";
  document_type?: "INVOICE" | "CREDIT_NOTE";
  original_invoice_number?: string;
  credit_note_number?: string;
  emailed_at?: string;
  reminded_at?: string;
  public_note?: string;
  private_note?: string;
};

type InvoiceListRow =
  | {
      kind: "payment";
      key: string;
      occurredAt: string;
      invoiceNumber: string | null;
      typeLabel: string;
      label: string;
      status: string | null;
      total: string;
      currency: string;
      source: string;
      paymentId: string;
      paymentStatus: string;
    }
  | {
      kind: "legacy";
      key: string;
      invoiceId: string;
      occurredAt: string;
      invoiceNumber: string;
      typeLabel: string;
      label: string;
      status: "PAID" | "CREDIT_NOTE";
      total: string;
      currency: string;
    }
  | {
      kind: "range";
      key: string;
      noteId: string;
      occurredAt: string;
      invoiceNumber: string;
      typeLabel: string;
      modeLabel: string;
      label: string;
      status: string;
      issuedDate: string;
      startDate: string;
      endDate: string;
      dueDate: string;
      noDueDate: boolean;
      layout: "DETAILED" | "COMPILED";
      groupAdjustmentsByType: boolean;
      includeDiscountAdjustments: boolean;
      includeSupplementAdjustments: boolean;
      includePending: boolean;
      includeCancelled: boolean;
      publicNote: string | null;
      privateNote: string | null;
      emailedAt: string | null;
      remindedAt: string | null;
      bankTransferOrderId: string | null;
      bankTransferOrderReference: string | null;
      bankTransferOrderStatus: string | null;
      bankTransferOrderExpiresAt: string | null;
      bankTransferOrderPaidAt: string | null;
      includedPaymentKeys: string[];
      totalLabel: string;
      balanceLabel: string | null;
      checkCoverageStatus: "NONE" | "PARTIAL" | "COVERED";
      pendingCheckAmountLabel: string | null;
      pendingCheckCount: number;
      remindersSuspended: boolean;
      downloadHref: string;
      viewHref: string;
      sellerLegalEntityId: string | null;
      billingEntity: string | null;
      familyBillingPayerName: string | null;
      documentType: "INVOICE" | "CREDIT_NOTE";
      originalInvoiceNumber: string | null;
      creditNoteNumber: string | null;
    };

type RangeInvoiceListRow = Extract<InvoiceListRow, { kind: "range" }>;

function parseRangeInvoiceNote(note: AdminClientNoteOut): RangeInvoiceNotePayload | null {
  const rawMessage = (note.message || "").trim();
  const prefixIndex = rawMessage.indexOf(INVOICE_RANGE_NOTE_PREFIX);
  if (prefixIndex < 0) {
    return null;
  }
  const rawPayload = rawMessage.slice(prefixIndex + INVOICE_RANGE_NOTE_PREFIX.length).trim();
  if (!rawPayload) {
    return null;
  }
  try {
    const payload = JSON.parse(rawPayload) as Partial<RangeInvoiceNotePayload>;
    if (payload.kind !== "INVOICE_RANGE") {
      return null;
    }
    if (
      typeof payload.invoice_number !== "string" ||
      typeof payload.issued_date !== "string" ||
      typeof payload.due_date !== "string" ||
      typeof payload.start_date !== "string" ||
      typeof payload.end_date !== "string"
    ) {
      return null;
    }
    const layoutRaw = typeof payload.layout === "string" ? payload.layout.trim().toUpperCase() : "";
    const normalizedLayout =
      layoutRaw === "COMPILED" || layoutRaw === "CONDENSED" || layoutRaw === "GROUPED" ? "COMPILED" : layoutRaw;
    if (normalizedLayout !== "DETAILED" && normalizedLayout !== "NORMAL" && normalizedLayout !== "DETAIL" && normalizedLayout !== "COMPILED") {
      return null;
    }
    const normalizedGenerationMode =
      typeof payload.generation_mode === "string" && payload.generation_mode.trim().toUpperCase() === "AUTO" ? "AUTO" : "MANUAL";
    const resolvedLayout = normalizedLayout === "COMPILED" ? "COMPILED" : "DETAILED";
    if (!payload.totals_by_currency || typeof payload.totals_by_currency !== "object") {
      return null;
    }

    const totals: Record<string, string> = {};
    for (const [currency, amount] of Object.entries(payload.totals_by_currency)) {
      if (typeof amount !== "string") {
        continue;
      }
      totals[currency.toUpperCase()] = amount;
    }
    if (Object.keys(totals).length === 0) {
      return null;
    }

    return {
      kind: "INVOICE_RANGE",
      invoice_number: payload.invoice_number,
      issued_date: payload.issued_date,
      due_date: payload.due_date,
      no_due_date: Boolean(payload.no_due_date),
      start_date: payload.start_date,
      end_date: payload.end_date,
      layout: resolvedLayout,
      generation_mode: normalizedGenerationMode,
      group_adjustments_by_type: Boolean(payload.group_adjustments_by_type),
      include_discount_adjustments:
        typeof payload.include_discount_adjustments === "boolean" ? payload.include_discount_adjustments : true,
      include_supplement_adjustments:
        typeof payload.include_supplement_adjustments === "boolean" ? payload.include_supplement_adjustments : true,
      auto_cycle_start_date: typeof payload.auto_cycle_start_date === "string" ? payload.auto_cycle_start_date : undefined,
      auto_period_scope:
        typeof payload.auto_period_scope === "string" && payload.auto_period_scope.trim().toUpperCase() === "FUTURE"
          ? "FUTURE"
          : "PAST",
      auto_frequency:
        typeof payload.auto_frequency === "string" && payload.auto_frequency.trim().toUpperCase() === "WEEKLY"
          ? "WEEKLY"
          : "MONTHLY",
      auto_repeat_every:
        typeof payload.auto_repeat_every === "number" && Number.isFinite(payload.auto_repeat_every)
          ? Math.max(1, Math.min(12, Math.trunc(payload.auto_repeat_every)))
          : 1,
      auto_layout_style:
        typeof payload.auto_layout_style === "string" && payload.auto_layout_style.trim().toUpperCase() === "CONDENSED"
          ? "CONDENSED"
          : "NORMAL",
      auto_include_previous_balance:
        typeof payload.auto_include_previous_balance === "boolean" ? payload.auto_include_previous_balance : true,
      auto_send_email: Boolean(payload.auto_send_email),
      auto_footer_note: typeof payload.auto_footer_note === "string" ? payload.auto_footer_note : undefined,
      auto_exclude_pack_subscription_lines:
        typeof payload.auto_exclude_pack_subscription_lines === "boolean"
          ? payload.auto_exclude_pack_subscription_lines
          : true,
      include_pending: Boolean(payload.include_pending),
      include_cancelled: Boolean(payload.include_cancelled),
      totals_by_currency: totals,
      total_to_pay_by_currency:
        payload.total_to_pay_by_currency && typeof payload.total_to_pay_by_currency === "object"
          ? Object.fromEntries(
              Object.entries(payload.total_to_pay_by_currency)
                .filter((entry): entry is [string, string] => typeof entry[1] === "string")
                .map(([currency, amount]) => [currency.toUpperCase(), amount]),
            )
          : undefined,
      seller_legal_entity_id: typeof payload.seller_legal_entity_id === "string" ? payload.seller_legal_entity_id : undefined,
      billing_entity: typeof payload.billing_entity === "string" ? payload.billing_entity : undefined,
      invoice_status:
        payload.invoice_status === "PAID" ||
        payload.invoice_status === "CANCELLED" ||
        payload.invoice_status === "CREDIT_NOTE" ||
        payload.invoice_status === "ISSUED"
          ? payload.invoice_status
          : "ISSUED",
      document_type:
        payload.document_type === "CREDIT_NOTE" ? "CREDIT_NOTE" : "INVOICE",
      original_invoice_number:
        typeof payload.original_invoice_number === "string" ? payload.original_invoice_number : undefined,
      credit_note_number:
        typeof payload.credit_note_number === "string" ? payload.credit_note_number : undefined,
      emailed_at: typeof payload.emailed_at === "string" ? payload.emailed_at : undefined,
      reminded_at: typeof payload.reminded_at === "string" ? payload.reminded_at : undefined,
      included_payment_keys: Array.isArray(payload.included_payment_keys)
        ? payload.included_payment_keys.map((value) => String(value || "").trim()).filter(Boolean)
        : [],
      public_note: typeof payload.public_note === "string" ? payload.public_note : undefined,
      private_note: typeof payload.private_note === "string" ? payload.private_note : undefined,
    };
  } catch {
    return null;
  }
}

function rangeInvoiceTotalLabel(totalsByCurrency: Record<string, string>, language: UiLanguage = "fr"): string {
  const entries = Object.entries(totalsByCurrency);
  if (entries.length === 0) {
    return "-";
  }
  return entries
    .map(([currency, amount]) => formatMoney(amount, currency, language))
    .join(" | ");
}

function rangeInvoiceNoteSummary(note: AdminClientNoteOut, language: UiLanguage = "fr"): string | null {
  const payload = parseRangeInvoiceNote(note);
  if (!payload) {
    return null;
  }
  return [
    payload.invoice_number ? `Facture ${payload.invoice_number}` : "Facture",
    `${formatDateInputLabel(payload.start_date, language)} - ${formatDateInputLabel(payload.end_date, language)}`,
    `emise le ${formatDateInputLabel(payload.issued_date, language)}`,
    payload.no_due_date ? "sans echeance" : `echeance ${formatDateInputLabel(payload.due_date, language)}`,
    rangeInvoiceStatusLabel(payload.invoice_status, language),
  ].join(" | ");
}

function rangeInvoiceNoteDetails(note: AdminClientNoteOut, language: UiLanguage = "fr"): Array<{ label: string; value: string }> | null {
  const payload = parseRangeInvoiceNote(note);
  if (!payload) {
    return null;
  }
  const totalMap = Object.keys(payload.total_to_pay_by_currency || {}).length > 0
    ? payload.total_to_pay_by_currency || {}
    : payload.totals_by_currency;
  return [
    { label: "Numero", value: payload.invoice_number || "-" },
    { label: "Periode", value: `${formatDateInputLabel(payload.start_date, language)} - ${formatDateInputLabel(payload.end_date, language)}` },
    { label: "Date d'emission", value: formatDateInputLabel(payload.issued_date, language) },
    { label: "Echeance", value: payload.no_due_date ? "Sans echeance" : formatDateInputLabel(payload.due_date, language) },
    { label: "Statut", value: rangeInvoiceStatusLabel(payload.invoice_status, language) },
    { label: "Montant", value: rangeInvoiceTotalLabel(totalMap, language) },
  ];
}

function rangeInvoicePdfHref(clientId: string, noteId: string, inline = false): string {
  const params = new URLSearchParams({
    inline: inline ? "true" : "false",
    payment_return_tab: "factures",
  });
  if (inline) {
    params.set("raw", "1");
  }
  return `/admin/clients/${clientId}/invoices/range/${noteId}/pdf?${params.toString()}`;
}

function paymentReceiptPdfHref(clientId: string, receiptId: string, inline = false): string {
  const params = new URLSearchParams({
    inline: inline ? "true" : "false",
    payment_return_tab: "reservations",
  });
  return `/admin/clients/${clientId}/payment-receipts/${receiptId}/pdf?${params.toString()}`;
}

function rangeInvoiceStatusLabel(status: string, language: UiLanguage = "fr"): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "CREDIT_NOTE") {
    return language === "en" ? "Credit note" : "Avoir";
  }
  if (normalized === "PAID") {
    return uiText(language, "admin.client_detail.range_invoice_status.paid");
  }
  if (normalized === "CANCELLED") {
    return uiText(language, "admin.client_detail.range_invoice_status.cancelled");
  }
  return uiText(language, "admin.client_detail.range_invoice_status.issued");
}

function rangeInvoiceStatusClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "CANCELLED") {
    return "status-off";
  }
  if (normalized === "CREDIT_NOTE") {
    return "status-ok";
  }
  return "status-warn";
}

function quoteChangeTypeLabel(type: string): string {
  const normalized = (type || "").trim().toUpperCase();
  if (normalized === "SLOT_CHANGE") return "Changement de creneau";
  if (normalized === "COURSE_CANCELLED") return "Cours annule";
  if (normalized === "COURSE_ADDED") return "Cours ajoute";
  if (normalized === "COURSE_REMOVED") return "Cours supprime";
  if (normalized === "FORMULA_CHANGE") return "Changement de formule";
  if (normalized === "EXCEPTIONAL_ADJUSTMENT") return "Ajustement exceptionnel";
  return "Autre changement";
}

function billingActionLabel(action: string): string {
  const normalized = (action || "").trim().toUpperCase();
  if (normalized === "TO_INVOICE") return "A facturer";
  if (normalized === "TO_CREDIT") return "Avoir a preparer";
  if (normalized === "MANUAL_REVIEW") return "A verifier";
  return "Sans impact";
}

function adjustmentStatusClass(status: string): string {
  const normalized = (status || "").trim().toUpperCase();
  if (normalized === "CONVERTED") return "status-ok";
  if (normalized === "DISMISSED") return "status-off";
  return "status-warn";
}

function snapshotText(value: Record<string, unknown>): string {
  const rawText = value.text;
  if (typeof rawText === "string" && rawText.trim()) {
    return rawText.trim();
  }
  return "-";
}

function buildQuoteChangesRecap(
  changes: AdminStudentQuoteChangeOut[],
  clientName: string,
  language: UiLanguage,
): string {
  if (changes.length === 0) {
    return "";
  }
  const lines = [
    `Recapitulatif des changements - ${clientName}`,
    "",
    "Reference: les factures emises restent figees. Les lignes ci-dessous retracent les changements intervenus depuis le dernier document de facturation.",
    "",
  ];
  for (const change of changes) {
    lines.push(`- ${formatDate(change.created_at, language)} | ${change.student_display_name ?? clientName}`);
    lines.push(`  Origine: ${change.quote_number ? `devis ${change.quote_number}` : "changement manuel"}`);
    lines.push(`  Changement: ${quoteChangeTypeLabel(change.change_type)} - ${change.title}`);
    lines.push(`  Avant: ${snapshotText(change.before_snapshot)}`);
    lines.push(`  Apres: ${snapshotText(change.after_snapshot)}`);
    lines.push(`  Impact: ${formatMoney(change.financial_impact_ttc ?? "0", change.currency, language)} (${billingActionLabel(change.billing_action)})`);
    if (change.client_visible_note) {
      lines.push(`  Note: ${change.client_visible_note}`);
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}

function shortContractRef(value: string): string {
  const head = value.split("-")[0] ?? value;
  return `#${head}`;
}

function initials(client: AdminClientOut): string {
  const first = (client.first_name ?? "").trim().slice(0, 1);
  const last = (client.last_name ?? "").trim().slice(0, 1);
  const candidate = `${first}${last}`.toUpperCase();
  if (candidate) {
    return candidate;
  }
  return client.email.slice(0, 2).toUpperCase();
}

function visibleClientEmail(email: string | null | undefined): string | null {
  const normalized = String(email ?? "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized.endsWith("@piano-academie.invalid") || normalized.endsWith("@no-email.local")) {
    return null;
  }
  return String(email ?? "").trim() || null;
}

function tabHref(clientId: string, tab: ClientTab): string {
  return `/admin/clients/${clientId}?tab=${tab}`;
}

function ficheHref(clientId: string, params: Record<string, string>): string {
  const search = new URLSearchParams({ tab: "fiche", ...params });
  return `/admin/clients/${clientId}?${search.toString()}`;
}

function paymentsHref(clientId: string, params: Record<string, string>): string {
  const search = new URLSearchParams({ tab: "paiements", ...params });
  return `/admin/clients/${clientId}?${search.toString()}`;
}

function invoicesHref(clientId: string, params: Record<string, string>): string {
  const search = new URLSearchParams({ tab: "factures", ...params });
  return `/admin/clients/${clientId}?${search.toString()}`;
}

function reservationsHref(clientId: string, params: Record<string, string>): string {
  const search = new URLSearchParams({ tab: "reservations", ...params });
  return `/admin/clients/${clientId}?${search.toString()}`;
}

function messagesHref(clientId: string, params: Record<string, string>): string {
  const search = new URLSearchParams({ tab: "messages", ...params });
  return `/admin/clients/${clientId}?${search.toString()}`;
}

const MANUAL_TRANSACTION_MODAL_TYPES = ["payment", "refund", "charge", "discount", "fees"] as const;
type ManualTransactionModalType = (typeof MANUAL_TRANSACTION_MODAL_TYPES)[number];
const CLIENT_STATUS_OPTIONS = ["ACTIVE", "RESPONSABLE", "TRIAL", "PENDING", "INACTIVE", "ARCHIVED"] as const;
const STUDENT_SITE_OPTIONS = ["PARIS", "BAR_LE_DUC", "ONLINE"] as const;

const DEFAULT_PAYMENT_METHOD_OPTIONS: Array<{
  code: string;
  label: string;
  default_legal_entity_id: string | null;
  default_legal_entity_name: string | null;
}> = [
  { code: "CARD_ONLINE", label: "Online card (Mollie / Payplug)" },
  { code: "CARD_TERMINAL", label: "Card terminal" },
  { code: "CHECK", label: "Check" },
  { code: "CASH", label: "Cash" },
  { code: "PAYPAL", label: "PayPal" },
  { code: "SEPA_DEBIT", label: "SEPA direct debit" },
  { code: "BANK_TRANSFER", label: "Bank transfer" },
  { code: "GIFT_CARD", label: "Gift card (paid by a third party)" },
  { code: "FACTURATION_AUTO", label: "Invoice billing" },
].map((row) => ({ ...row, default_legal_entity_id: null, default_legal_entity_name: null }));

function statusClass(status: string): string {
  const normalized = status.toUpperCase();
  if (
    normalized === "ACTIVE" ||
    normalized === "BOOKED" ||
    normalized === "ATTENDED" ||
    normalized === "SENT" ||
    normalized === "DELIVERED" ||
    normalized === "PAID"
  ) {
    return "status-ok";
  }
  if (normalized === "RESPONSABLE") {
    return "status-info";
  }
  if (
    normalized === "WAITLISTED" ||
    normalized === "PENDING" ||
    normalized === "PENDING_PAYMENT" ||
    normalized === "TRIAL" ||
    normalized === "FAILED"
  ) {
    return "status-warn";
  }
  return "status-off";
}

function messageStatusMeta(
  status: string,
  errorMessage?: string | null,
  language: UiLanguage = "fr",
): { label: string; toneClass: string; helpText: string } {
  const normalized = String(status || "").trim().toUpperCase();
  const normalizedError = String(errorMessage || "").toLowerCase();
  const looksLikeBounce =
    normalized === "BOUNCED" ||
    normalizedError.includes("bounce") ||
    normalizedError.includes("bounced") ||
    normalizedError.includes("undeliverable") ||
    normalizedError.includes("mailbox unavailable");
  if (normalized === "DELIVERED" || normalized === "SENT") {
    return {
      label: uiText(language, "admin.client_detail.message_status.delivered"),
      toneClass: "status-ok",
      helpText: uiText(language, "admin.client_detail.message_status.delivered_help"),
    };
  }
  if (looksLikeBounce) {
    return {
      label: uiText(language, "admin.client_detail.message_status.bounced"),
      toneClass: "status-warn",
      helpText: uiText(language, "admin.client_detail.message_status.bounced_help"),
    };
  }
  if (normalized === "FAILED") {
    return {
      label: uiText(language, "admin.client_detail.message_status.failed"),
      toneClass: "status-warn",
      helpText: uiText(language, "admin.client_detail.message_status.failed_help"),
    };
  }
  if (normalized === "SKIPPED") {
    return {
      label: uiText(language, "admin.client_detail.message_status.skipped"),
      toneClass: "status-off",
      helpText: uiText(language, "admin.client_detail.message_status.skipped_help"),
    };
  }
  if (normalized === "PENDING") {
    return {
      label: uiText(language, "admin.client_detail.message_status.pending"),
      toneClass: "status-warn",
      helpText: uiText(language, "admin.client_detail.message_status.pending_help"),
    };
  }
  return {
    label: normalized || uiText(language, "admin.client_detail.unknown").toUpperCase(),
    toneClass: statusClass(normalized || "UNKNOWN"),
    helpText: uiText(language, "admin.client_detail.message_status.provider_help"),
  };
}

function messageSourceLabel(source: string | null, channel: string | null | undefined, language: UiLanguage = "fr"): string {
  const normalized = String(source || "").trim().toUpperCase();
  if (!normalized) {
    const normalizedChannel = String(channel || "").trim().toUpperCase();
    if (normalizedChannel === "SMS") {
      return uiText(language, "common.sms");
    }
    if (normalizedChannel === "EMAIL") {
      return uiText(language, "common.email");
    }
    return uiText(language, "common.message");
  }
  if (normalized === "ADMIN_CLIENT_DIRECT_MESSAGE") {
    return uiText(language, "admin.client_detail.message_source.direct");
  }
  if (normalized === "ADMIN_CLIENT_FORWARD_MESSAGE") {
    return uiText(language, "admin.client_detail.message_source.forward");
  }
  if (normalized === "COURSE_REMINDER" || normalized.includes("REMINDER")) {
    return uiText(language, "admin.client_detail.message_source.course_reminder");
  }
  if (normalized.includes("PAYMENT_RECEIPT")) {
    return uiText(language, "admin.client_detail.message_source.payment_receipt");
  }
  if (normalized.includes("REFUND")) {
    return uiText(language, "admin.client_detail.message_source.refund");
  }
  if (normalized.includes("INVOICE") && normalized.includes("REMINDER")) {
    return uiText(language, "admin.client_detail.message_source.invoice_reminder");
  }
  if (normalized.includes("INVOICE")) {
    return uiText(language, "admin.client_detail.message_source.invoice");
  }
  if (normalized.includes("PASSWORD")) {
    return uiText(language, "admin.client_detail.message_source.password");
  }
  return normalized.replace(/_/g, " ");
}

function buildForwardSubject(subject: string, language: UiLanguage = "fr"): string {
  const normalized = String(subject || "").trim();
  const prefix = uiText(language, "admin.client_detail.message_forward_prefix");
  if (!normalized) {
    return `${prefix} ${uiText(language, "common.message")}`;
  }
  if (/^(TR:|FWD:|FW:)/i.test(normalized)) {
    return normalized;
  }
  return `${prefix} ${normalized}`;
}

function buildForwardBody(message: AdminClientMessageOut, language: UiLanguage = "fr"): string {
  const dateLabel = formatDate(message.sent_at ?? message.scheduled_for_utc, language);
  const statusLabel = messageStatusMeta(message.status, message.error_message, language).label;
  const recipientLabel = message.recipient || "-";
  const subjectLabel = message.subject_preview || uiText(language, "common.message");
  const content = message.body_full || message.body_preview || "";
  const introLabel = uiText(language, "admin.client_detail.message_forward_intro");
  if ((message.body_format || "TEXT").toUpperCase() === "HTML") {
    return `<p><strong>${introLabel}</strong></p>
<p><strong>${uiText(language, "common.date")}:</strong> ${dateLabel}<br><strong>${uiText(language, "common.status")}:</strong> ${statusLabel}<br><strong>${uiText(language, "admin.client_detail.recipient")}:</strong> ${recipientLabel}<br><strong>${uiText(language, "common.subject")}:</strong> ${subjectLabel}</p>
<hr>
${content}`;
  }
  return `${introLabel}
${uiText(language, "common.date")}: ${dateLabel}
${uiText(language, "common.status")}: ${statusLabel}
${uiText(language, "admin.client_detail.recipient")}: ${recipientLabel}
${uiText(language, "common.subject")}: ${subjectLabel}

${content}`;
}

function paymentStatusClass(status: string): string {
  const normalized = normalizePaymentStatus(status);
  if (normalized === "CHECK_REFUSED") {
    return "status-off";
  }
  if (normalized === "NOT_BILLABLE" || normalized === "REFUNDED" || CANCELLED_PAYMENT_STATUSES.has(normalized)) {
    return "status-off";
  }
  if (PAID_PAYMENT_STATUSES.has(normalized)) {
    return "status-ok";
  }
  if (normalized === "CREDIT_NOTE") {
    return "status-ok";
  }
  return "status-warn";
}

function subscriptionStatusPill(sub: AdminClientSubscriptionOut): { label: string; toneClass: string } {
  const normalized = (sub.status ?? "").toUpperCase();
  if (normalized === "CANCELLED" || normalized === "EXPIRED" || normalized === "ARCHIVED" || normalized === "INACTIVE") {
    return { label: "RESILIE", toneClass: "status-off" };
  }
  if (sub.cancellation_request_status === "PENDING") {
    return { label: "A VALIDER", toneClass: "status-warn" };
  }
  if (sub.cancellation_requested_at) {
    const effectiveAt = sub.cancellation_effective_at ? Date.parse(sub.cancellation_effective_at) : Number.NaN;
    if (Number.isFinite(effectiveAt) && effectiveAt <= Date.now()) {
      return { label: "RESILIE", toneClass: "status-off" };
    }
    return { label: "FIN DE PERIODE", toneClass: "status-warn" };
  }
  if (normalized === "PAUSED") {
    return { label: "SUSPENDU", toneClass: "status-warn" };
  }
  return { label: normalized || "INCONNU", toneClass: statusClass(normalized || "INCONNU") };
}

function isPendingSubscriptionCancellation(sub: AdminClientSubscriptionOut): boolean {
  if (!sub.cancellation_requested_at) {
    return false;
  }
  if (!sub.cancellation_effective_at) {
    return true;
  }
  const effectiveAt = Date.parse(sub.cancellation_effective_at);
  if (!Number.isFinite(effectiveAt)) {
    return true;
  }
  return effectiveAt > Date.now();
}

function isCancellationAlreadyEffective(sub: AdminClientSubscriptionOut): boolean {
  if (!sub.cancellation_effective_at) {
    return false;
  }
  const effectiveAt = Date.parse(sub.cancellation_effective_at);
  if (!Number.isFinite(effectiveAt)) {
    return false;
  }
  return effectiveAt <= Date.now();
}

function planKindLabel(kind: string, language: UiLanguage = "fr"): string {
  const normalized = kind.trim().toUpperCase();
  if (normalized === "PACK") {
    return uiText(language, "admin.client_detail.plan_kind.pack");
  }
  if (normalized === "FORFAIT") {
    return uiText(language, "admin.client_detail.plan_kind.forfait");
  }
  return uiText(language, "admin.client_detail.plan_kind.subscription");
}

function contactDisplayLabel(firstName: string | null | undefined, lastName: string | null | undefined, email: string): string {
  const name = [String(firstName || "").trim(), String(lastName || "").trim()].filter(Boolean).join(" ").trim();
  return name ? `${name} <${email}>` : email;
}

function formatLocalizedDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Paris",
  });
}

function formatLocalizedDateOnly(value: string | null, language: UiLanguage): string {
  if (!value) {
    return uiText(language, "admin.client_detail.not_provided_feminine");
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return uiText(language, "admin.client_detail.not_provided_feminine");
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), {
    dateStyle: "medium",
  });
}

function formatLocalizedMoney(value: string | null | undefined, currency: string, language: UiLanguage): string {
  const amount = Number(value ?? "0");
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function clientDetailTabLabel(tab: ClientTab, language: UiLanguage): string {
  if (tab === "infos") return uiText(language, "admin.client_detail.tab_info");
  if (tab === "famille") return uiText(language, "admin.client_detail.tab_family");
  if (tab === "messages") return uiText(language, "admin.client_detail.tab_messages");
  if (tab === "paiements") return uiText(language, "admin.client_detail.tab_account");
  if (tab === "factures") return uiText(language, "admin.client_detail.tab_invoices");
  if (tab === "reservations") return uiText(language, "admin.client_detail.tab_bookings");
  if (tab === "changements") return "Changements";
  return uiText(language, "admin.client_detail.tab_sheet");
}

function clientKindLabel(kind: string, language: UiLanguage): string {
  return kind.trim().toUpperCase() === "CHILD"
    ? uiText(language, "admin.client_detail.kind_child")
    : uiText(language, "admin.client_detail.kind_adult");
}

function clientStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ACTIVE") return uiText(language, "admin.clients.status_active");
  if (normalized === "RESPONSABLE") return uiText(language, "admin.clients.status_responsable");
  if (normalized === "TRIAL") return uiText(language, "admin.clients.status_trial");
  if (normalized === "PENDING") return uiText(language, "admin.clients.status_pending");
  if (normalized === "INACTIVE") return uiText(language, "admin.clients.status_inactive");
  if (normalized === "ARCHIVED") return uiText(language, "admin.clients.status_archived");
  return normalized || uiText(language, "admin.client_detail.unknown");
}

function studentSiteLabel(site: string | null | undefined): string {
  if (site === "PARIS") return "Paris";
  if (site === "BAR_LE_DUC") return "Bar-le-Duc";
  if (site === "ONLINE") return "En ligne";
  return "-";
}

function localizedBillingMethodLabel(code: string | null, language: UiLanguage): string {
  const normalized = (code ?? "").toUpperCase();
  if (normalized === "CARD_ONLINE") return uiText(language, "admin.client_detail.billing.card_online");
  if (normalized === "SEPA_DEBIT") return uiText(language, "admin.client_detail.billing.sepa_debit");
  if (normalized === "CARD_TERMINAL") return uiText(language, "admin.client_detail.billing.card_terminal");
  if (normalized === "BANK_TRANSFER") return uiText(language, "admin.client_detail.billing.bank_transfer");
  if (normalized === "CASH") return uiText(language, "admin.client_detail.billing.cash");
  if (normalized === "CHECK") return uiText(language, "admin.client_detail.billing.check");
  if (normalized === "PAYPAL") return "PayPal";
  if (normalized === "GIFT_CARD") return uiText(language, "admin.client_detail.billing.gift_card");
  if (normalized === "FACTURATION_AUTO") return uiText(language, "admin.client_detail.billing.invoice");
  return code || uiText(language, "admin.client_detail.not_defined");
}

function localizedSubscriptionStatusPill(sub: AdminClientSubscriptionOut, language: UiLanguage): { label: string; toneClass: string } {
  const normalized = (sub.status ?? "").toUpperCase();
  if (normalized === "CANCELLED" || normalized === "EXPIRED" || normalized === "ARCHIVED" || normalized === "INACTIVE") {
    return { label: uiText(language, "admin.client_detail.subscription_cancelled"), toneClass: "status-off" };
  }
  if (sub.cancellation_request_status === "PENDING") {
    return { label: uiText(language, "admin.client_detail.subscription_cancellation_to_review"), toneClass: "status-warn" };
  }
  if (sub.cancellation_requested_at) {
    const effectiveAt = sub.cancellation_effective_at ? Date.parse(sub.cancellation_effective_at) : Number.NaN;
    if (Number.isFinite(effectiveAt) && effectiveAt <= Date.now()) {
      return { label: uiText(language, "admin.client_detail.subscription_cancelled"), toneClass: "status-off" };
    }
    return { label: uiText(language, "admin.client_detail.subscription_end_of_period"), toneClass: "status-warn" };
  }
  if (normalized === "PAUSED") {
    return { label: uiText(language, "admin.client_detail.subscription_paused"), toneClass: "status-warn" };
  }
  return { label: clientStatusLabel(normalized, language), toneClass: statusClass(normalized || "UNKNOWN") };
}

function localizedClientPhotoAlt(fullName: string, language: UiLanguage): string {
  if (fullName) {
    return uiText(language, "admin.client_detail.photo_of", { name: fullName });
  }
  return uiText(language, "admin.client_detail.photo");
}

function deliveryStatusLabel(status: string, language: UiLanguage): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "suspended") {
    return uiText(language, "admin.client_detail.delivery_suspended");
  }
  if (normalized === "active") {
    return uiText(language, "admin.client_detail.delivery_active");
  }
  return status || uiText(language, "admin.client_detail.unknown");
}

function booleanEnabledLabel(value: boolean, language: UiLanguage): string {
  return value ? uiText(language, "admin.client_detail.active") : uiText(language, "admin.client_detail.disabled");
}

function optInLabel(value: boolean, language: UiLanguage): string {
  return value ? uiText(language, "admin.client_detail.opt_in") : uiText(language, "admin.client_detail.opt_out");
}

export default async function AdminClientDetailPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const currentTab = parseTab(readParam(searchParams, "tab"));
  const openEditInfosModal = readParam(searchParams, "edit_infos") === "1";
  const subscriptionModalAction = readParam(searchParams, "subscription_modal");
  const subscriptionModalId = readParam(searchParams, "subscription_id");
  const openManualCreditModal = readParam(searchParams, "edit_credit") === "1";
  const creditTypeModalId = readParam(searchParams, "credit_type_id");
  const paymentModalAction = readParam(searchParams, "payment_modal");
  const invoiceWizardStepRaw = readParam(searchParams, "invoice_step").trim();
  const invoiceGenerationModeRaw = readParam(searchParams, "generation_mode").trim().toUpperCase();
  const invoiceIssuedDateRaw = readParam(searchParams, "issued_date").trim();
  const invoiceStartDateRaw = readParam(searchParams, "start_date").trim();
  const invoiceEndDateRaw = readParam(searchParams, "end_date").trim();
  const invoiceDueDateRaw = readParam(searchParams, "due_date").trim();
  const invoiceNoDueDateRaw = readParam(searchParams, "no_due_date");
  const invoiceIncludePendingRaw = readParam(searchParams, "include_pending");
  const invoiceIncludeCancelledRaw = readParam(searchParams, "include_cancelled");
  const invoiceLayoutRaw = readParam(searchParams, "layout").trim().toUpperCase();
  const invoiceGroupAdjustmentsRaw = readParam(searchParams, "group_adjustments_by_type");
  const invoiceIncludeDiscountRaw = readParam(searchParams, "include_discount_adjustments");
  const invoiceIncludeSupplementRaw = readParam(searchParams, "include_supplement_adjustments");
  const invoiceSelectedPaymentKeysRaw = readParams(searchParams, "selected_payment_keys");
  const invoiceAutoCycleStartRaw = readParam(searchParams, "auto_cycle_start_date").trim();
  const invoiceAutoFrequencyRaw = readParam(searchParams, "auto_frequency").trim().toUpperCase();
  const invoiceAutoBillingTimingRaw = readParam(searchParams, "auto_billing_timing").trim().toUpperCase();
  const invoiceAutoDueDateRuleTypeRaw = readParam(searchParams, "auto_due_date_rule_type").trim().toUpperCase();
  const invoiceAutoDueDateDaysOffsetRaw = readParam(searchParams, "auto_due_date_days_offset").trim();
  const invoiceAutoLegalEntityIdRaw = readParam(searchParams, "auto_legal_entity_id").trim();
  const invoicePublicNoteRaw = readParam(searchParams, "public_note");
  const invoicePrivateNoteRaw = readParam(searchParams, "private_note");
  const manualTransactionModalTypeRaw = readParam(searchParams, "manual_type").toLowerCase();
  const manualTransactionModalType = MANUAL_TRANSACTION_MODAL_TYPES.includes(
    manualTransactionModalTypeRaw as ManualTransactionModalType,
  )
    ? (manualTransactionModalTypeRaw as ManualTransactionModalType)
    : null;
  const manualStepRaw = readParam(searchParams, "manual_step").trim();
  const manualAmountRaw = readParam(searchParams, "manual_amount").trim().replace(",", ".");
  const manualVatRaw = readParam(searchParams, "manual_vat").trim().replace(",", ".");
  const manualDateRaw = readParam(searchParams, "manual_date").trim();
  const manualRepeatStudentId = readParam(searchParams, "manual_student_id").trim();
  const manualRepeatPaymentMethodCode = readParam(searchParams, "manual_payment_method_code").trim().toUpperCase();
  const manualRepeatLegalEntityId = readParam(searchParams, "manual_legal_entity_id").trim();
  const manualRepeatCheckReceiptLocationId = readParam(searchParams, "manual_check_receipt_location_id").trim();
  const manualRepeatInvoiceNoteIds = readParam(searchParams, "manual_invoice_note_ids")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const manualCheckBatchIds = readParam(searchParams, "manual_check_batch_ids")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const paymentModalSource = readParam(searchParams, "payment_source").toUpperCase();
  const paymentModalId = readParam(searchParams, "payment_id");
  const invoiceNoteId = readParam(searchParams, "invoice_note_id");
  const invoiceEmailKindRaw = readParam(searchParams, "invoice_email_kind").toUpperCase();
  const invoiceEmailKind = invoiceEmailKindRaw === "REMINDER" ? "REMINDER" : "INVOICE";
  const includeInvoiceChangeSummary = readParam(searchParams, "include_change_summary") === "1";
  const referenceInvoiceNoteId = readParam(searchParams, "reference_invoice_note_id");
  const paymentReturnTabRaw = readParam(searchParams, "payment_return_tab");
  const cancelConflictAlert = readParam(searchParams, "cancel_conflict") === "1";
  const purchaseModalAction = readParam(searchParams, "purchase_modal");
  const purchasePlanId = readParam(searchParams, "purchase_plan_id");
  const purchaseType = readParam(searchParams, "purchase_type").toUpperCase() || "FORMULA";
  const purchasePaymentMethod = readParam(searchParams, "purchase_payment_method").toUpperCase();
  const purchaseDiscountedTotalRaw = readParam(searchParams, "purchase_discounted_total").replace(",", ".");
  const purchaseStartDateRaw = readParam(searchParams, "purchase_start_date").trim();
  const noteModalAction = readParam(searchParams, "note_modal").toLowerCase();
  const noteModalId = readParam(searchParams, "note_id");
  const purchaseReturnTab = parseTab(readParam(searchParams, "purchase_return_tab") || currentTab);
  const paymentReturnTab = parseTab(paymentReturnTabRaw || currentTab);
  const balanceDateParam = readParam(searchParams, "balance_date");
  const paymentFilterQuery = readParam(searchParams, "payment_filter_q").trim();
  const paymentFilterAmountRaw = readParam(searchParams, "payment_filter_amount").trim();
  const paymentFilterAmount = parseAmountFilter(paymentFilterAmountRaw);
  const hasPaymentFilters = paymentFilterQuery.length > 0 || paymentFilterAmount !== null;
  const messageModalAction = readParam(searchParams, "message_modal").toLowerCase();
  const messageModalId = readParam(searchParams, "message_id");
  const messageQuery = readParam(searchParams, "messages_q").trim();
  const messageMonthsRaw = readParam(searchParams, "messages_months").trim();
  const messageMonths = messageMonthsRaw === "6" || messageMonthsRaw === "12" ? Number.parseInt(messageMonthsRaw, 10) : 3;
  const messageApiSearch = new URLSearchParams({ months: String(messageMonths) });
  if (messageQuery) {
    messageApiSearch.set("q", messageQuery);
  }
  const messagesApiPath = `/api/v1/admin/clients/${params.clientId}/messages?${messageApiSearch.toString()}`;

  const isSummaryTab = currentTab === "fiche";
  const isInfoTab = currentTab === "infos";
  const isFamilyTab = currentTab === "famille";
  const isMessagesTab = currentTab === "messages";
  const isPaymentsTab = currentTab === "paiements";
  const isInvoicesTab = currentTab === "factures";
  const isBookingsTab = currentTab === "reservations";
  const isChangesTab = currentTab === "changements";
  const needsPurchaseData = (isSummaryTab || isPaymentsTab) && purchaseModalAction.length > 0;
  const needsPaymentEditorData = isPaymentsTab && paymentModalAction.length > 0;
  const needsFinancialHistory = isPaymentsTab || isInvoicesTab;
  const needsFamilyData = isFamilyTab || isMessagesTab || isPaymentsTab || isInvoicesTab || isBookingsTab;

  const [
    meResult,
    accountConfigResult,
    clientResult,
    plansResult,
    formulasResult,
    subscriptionsResult,
    bookingsResult,
    messagesResult,
    paymentsResult,
    rangeInvoicesResult,
    legacyInvoicesResult,
    productCategoriesResult,
    catalogProductsResult,
    paymentMethodsResult,
    legalEntitiesResult,
    locationsResult,
    familyResult,
    groupsResult,
    manualCreditsResult,
    notesResult,
    quoteChangesResult,
    approvedQuotesResult,
    makeupSummaryResult,
  ] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    needsFinancialHistory
      ? backendRequest<AdminConfigAccountOut>("/api/v1/admin/config/account", {}, token)
      : immediateBackendResult<AdminConfigAccountOut | null>(null),
    backendRequest<AdminClientOut>(`/api/v1/admin/clients/${params.clientId}`, {}, token),
    needsPurchaseData
      ? backendRequest<PlanOut[]>(`/api/v1/plans?purchase_user_id=${encodeURIComponent(params.clientId)}`, {}, token)
      : immediateBackendResult<PlanOut[]>([]),
    needsPurchaseData
      ? backendRequest<AdminFormulaOut[]>("/api/v1/admin/formulas", {}, token)
      : immediateBackendResult<AdminFormulaOut[]>([]),
    (isSummaryTab || isPaymentsTab)
      ? backendRequest<AdminClientSubscriptionOut[]>(`/api/v1/admin/clients/${params.clientId}/subscriptions`, {}, token)
      : immediateBackendResult<AdminClientSubscriptionOut[]>([]),
    (isSummaryTab || isBookingsTab)
      ? backendRequest<AdminClientBookingOut[]>(`/api/v1/admin/clients/${params.clientId}/bookings`, {}, token)
      : immediateBackendResult<AdminClientBookingOut[]>([]),
    isMessagesTab
      ? backendRequest<AdminClientMessageOut[]>(messagesApiPath, {}, token)
      : immediateBackendResult<AdminClientMessageOut[]>([]),
    (needsFinancialHistory || isBookingsTab)
      ? backendRequest<AdminClientPaymentOut[]>(`/api/v1/admin/clients/${params.clientId}/payments`, {}, token)
      : immediateBackendResult<AdminClientPaymentOut[]>([]),
    needsFinancialHistory
      ? backendRequest<AdminRangeInvoiceOut[]>(`/api/v1/admin/clients/${params.clientId}/invoices/range`, {}, token)
      : immediateBackendResult<AdminRangeInvoiceOut[]>([]),
    isInvoicesTab
      ? backendRequest<AdminLegacyInvoiceOut[]>(`/api/v1/admin/clients/${params.clientId}/invoices/legacy`, {}, token)
      : immediateBackendResult<AdminLegacyInvoiceOut[]>([]),
    needsPaymentEditorData
      ? backendRequest<AdminProductCategoriesOut>("/api/v1/admin/config/product-categories", {}, token)
      : immediateBackendResult<AdminProductCategoriesOut>({ categories: [], updated_at: null }),
    (needsPurchaseData || needsPaymentEditorData)
      ? backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=false", {}, token)
      : immediateBackendResult<AdminCatalogProductOut[]>([]),
    (needsPurchaseData || needsPaymentEditorData)
      ? backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token)
      : immediateBackendResult<AdminPaymentMethodsOut>({ methods: [] }),
    (needsFinancialHistory || isChangesTab)
      ? backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=false", {}, token)
      : immediateBackendResult<AdminLegalEntityOut[]>([]),
    needsPaymentEditorData
      ? backendRequest<LocationOut[]>("/api/v1/locations", {}, token)
      : immediateBackendResult<LocationOut[]>([]),
    needsFamilyData
      ? backendRequest<AdminClientFamilyOut>(`/api/v1/admin/clients/${params.clientId}/family`, {}, token)
      : immediateBackendResult<AdminClientFamilyOut>({
          client_id: params.clientId,
          client_kind: "ADULT",
          links_as_adult: [],
          links_as_child: [],
          billing_recipient_adult_id: null,
          billing_children: [],
        }),
    isInfoTab
      ? backendRequest<AdminClientGroupOut[]>("/api/v1/admin/clients/groups?include_inactive=false", {}, token)
      : immediateBackendResult<AdminClientGroupOut[]>([]),
    isSummaryTab
      ? backendRequest<AdminClientManualCreditOut[]>(`/api/v1/admin/clients/${params.clientId}/manual-credits`, {}, token)
      : immediateBackendResult<AdminClientManualCreditOut[]>([]),
    isSummaryTab
      ? backendRequest<AdminClientNoteOut[]>(`/api/v1/admin/clients/${params.clientId}/notes`, {}, token)
      : immediateBackendResult<AdminClientNoteOut[]>([]),
    isChangesTab
      ? backendRequest<AdminStudentQuoteChangeOut[]>(`/api/v1/admin/clients/${params.clientId}/quote-changes`, {}, token)
      : immediateBackendResult<AdminStudentQuoteChangeOut[]>([]),
    isChangesTab
      ? backendRequest<ApprovedQuoteOption[]>(`/api/v1/admin/clients/${params.clientId}/approved-quotes`, {}, token)
      : immediateBackendResult<ApprovedQuoteOption[]>([]),
    isSummaryTab
      ? backendRequest<MakeupStudentSummaryOut[]>(`/api/v1/admin/clients/${params.clientId}/makeup-summary`, {}, token)
      : immediateBackendResult<MakeupStudentSummaryOut[]>([]),
  ]);

  const language = meResult.ok ? normalizeUiLanguage(meResult.data.preferred_language) : "fr";
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const sortLocale = localeForUiLanguage(language);

  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_clients")) {
    redirect("/login?error_code=admin_access_required");
  }

  if (!clientResult.ok) {
    if (clientResult.status === 404) {
      redirect(`/admin/clients?error=${encodeURIComponent(t("admin.client_detail.client_not_found"))}`);
    }
    return <section className="flash-err">{t("admin.client_detail.backend_error", { message: clientResult.message })}</section>;
  }

  const client = clientResult.data;
  const fullName = [client.first_name, client.last_name].filter(Boolean).join(" ");
  const todayInputValue = formatDateInput(new Date());
  const dueDateInputValue = formatDateInput(addDays(new Date(), 10));
  const purchaseStartDateInputValue = isDateInput(purchaseStartDateRaw) ? purchaseStartDateRaw : todayInputValue;
  const monthStartInputValue = `${todayInputValue.slice(0, 8)}01`;
  const nextMonthCycleStartInputValue = formatDateInput(addMonths(new Date(`${monthStartInputValue}T00:00:00.000Z`), 1));
  const invoiceWizardStep = invoiceWizardStepRaw === "2" ? 2 : 1;
  const invoiceGenerationMode = invoiceGenerationModeRaw === "AUTO" ? "AUTO" : "MANUAL";
  const invoiceIssuedDateInputValue = isDateInput(invoiceIssuedDateRaw) ? invoiceIssuedDateRaw : todayInputValue;
  const invoiceStartDateInputValue = isDateInput(invoiceStartDateRaw) ? invoiceStartDateRaw : monthStartInputValue;
  const invoiceEndDateInputValue = isDateInput(invoiceEndDateRaw) ? invoiceEndDateRaw : todayInputValue;
  const invoiceDueDateInputValue = isDateInput(invoiceDueDateRaw) ? invoiceDueDateRaw : dueDateInputValue;
  const invoiceNoDueDate = parseToggleParam(invoiceNoDueDateRaw, false);
  const invoiceIncludePending = parseToggleParam(invoiceIncludePendingRaw, true);
  const invoiceIncludeCancelled = parseToggleParam(invoiceIncludeCancelledRaw, false);
  const invoiceLayout =
    invoiceLayoutRaw === "COMPILED" || invoiceLayoutRaw === "CONDENSED" || invoiceLayoutRaw === "GROUPED" ? "COMPILED" : "DETAILED";
  const invoiceGroupAdjustmentsByType = parseToggleParam(invoiceGroupAdjustmentsRaw, false);
  const invoiceIncludeDiscountAdjustments = parseToggleParam(invoiceIncludeDiscountRaw, true);
  const invoiceIncludeSupplementAdjustments = parseToggleParam(invoiceIncludeSupplementRaw, true);
  const invoiceAutoCycleStartDateInputValue = isDateInput(invoiceAutoCycleStartRaw)
    ? invoiceAutoCycleStartRaw
    : nextMonthCycleStartInputValue;
  const invoiceAutoFrequency: InvoiceFrequency =
    invoiceAutoFrequencyRaw === "BIMONTHLY" ||
    invoiceAutoFrequencyRaw === "QUARTERLY" ||
    invoiceAutoFrequencyRaw === "YEARLY"
      ? invoiceAutoFrequencyRaw
      : "MONTHLY";
  const invoiceAutoBillingTiming: "UPCOMING_LESSONS" | "PREVIOUS_LESSONS" =
    invoiceAutoBillingTimingRaw === "PREVIOUS_LESSONS" ? "PREVIOUS_LESSONS" : "UPCOMING_LESSONS";
  const invoiceAutoDueDateRuleType: "SAME_DAY_ISSUE" | "X_DAYS_AFTER_ISSUE" =
    invoiceAutoDueDateRuleTypeRaw === "X_DAYS_AFTER_ISSUE" ? "X_DAYS_AFTER_ISSUE" : "SAME_DAY_ISSUE";
  const invoiceAutoDueDateDaysOffsetParsed = Number.parseInt(invoiceAutoDueDateDaysOffsetRaw, 10);
  const invoiceAutoDueDateDaysOffset =
    Number.isFinite(invoiceAutoDueDateDaysOffsetParsed) && invoiceAutoDueDateDaysOffsetParsed >= 0
      ? invoiceAutoDueDateDaysOffsetParsed
      : 10;
  const invoiceAutoLegalEntityId = invoiceAutoLegalEntityIdRaw;
  const invoicePublicNote = invoicePublicNoteRaw;
  const invoicePrivateNote = invoicePrivateNoteRaw;
  const manualAmountParsed = Number(manualAmountRaw);
  const manualAmountInputValue =
    Number.isFinite(manualAmountParsed) && manualAmountParsed > 0 ? manualAmountParsed.toFixed(2) : "";
  const manualVatParsed = Number(manualVatRaw);
  const manualVatInputValue =
    Number.isFinite(manualVatParsed) && manualVatParsed >= 0 ? String(manualVatParsed) : "";
  const manualDateInputValue = isDateInput(manualDateRaw) ? manualDateRaw : todayInputValue;

  const errors: string[] = [];
  const accountConfig = accountConfigResult.ok
    ? accountConfigResult.data
    : (() => {
        errors.push(`account_config: ${accountConfigResult.message}`);
        return null;
      })();

  const plans = plansResult.ok
    ? plansResult.data.filter((plan) => plan.active)
    : (() => {
        errors.push(`plans: ${plansResult.message}`);
        return [] as PlanOut[];
      })();

  const formulas = formulasResult.ok
    ? formulasResult.data.filter((formula) => formula.active)
    : (() => {
        errors.push(`formulas: ${formulasResult.message}`);
        return [] as AdminFormulaOut[];
      })();

  const subscriptions = subscriptionsResult.ok
    ? subscriptionsResult.data
    : (() => {
        errors.push(`subscriptions: ${subscriptionsResult.message}`);
        return [] as AdminClientSubscriptionOut[];
      })();

  const bookings = bookingsResult.ok
    ? bookingsResult.data
    : (() => {
        errors.push(`bookings: ${bookingsResult.message}`);
        return [] as AdminClientBookingOut[];
      })();
  const makeupSummaries = makeupSummaryResult.ok
    ? makeupSummaryResult.data
    : (() => {
        errors.push(`makeup-summary: ${makeupSummaryResult.message}`);
        return [] as MakeupStudentSummaryOut[];
      })();

  const messages = messagesResult.ok
    ? messagesResult.data
    : (() => {
        errors.push(`messages: ${messagesResult.message}`);
        return [] as AdminClientMessageOut[];
      })();

  const payments = paymentsResult.ok
    ? paymentsResult.data
    : (() => {
        errors.push(`payments: ${paymentsResult.message}`);
        return [] as AdminClientPaymentOut[];
      })();
  const rangeInvoices = rangeInvoicesResult.ok
    ? rangeInvoicesResult.data
    : (() => {
        errors.push(`range_invoices: ${rangeInvoicesResult.message}`);
        return [] as AdminRangeInvoiceOut[];
      })();
  const legacyInvoices = legacyInvoicesResult.ok
    ? legacyInvoicesResult.data
    : (() => {
        errors.push(`legacy_invoices: ${legacyInvoicesResult.message}`);
        return [] as AdminLegacyInvoiceOut[];
      })();
  const configuredFixedBalanceDate = dateInputFromMaybeIso(accountConfig?.client_balance_default_date);
  const defaultBalanceDate =
    accountConfig?.client_balance_default_date_mode === "FIXED_DATE" && configuredFixedBalanceDate
      ? configuredFixedBalanceDate
      : accountConfig?.client_balance_default_date_mode === "PACKAGE_END"
        ? latestDateInput([
            ...rangeInvoices
              .filter((row) => (row.invoice_status || "").toUpperCase() !== "CANCELLED")
              .map((row) => row.end_date),
            ...subscriptions
              .filter((row) => row.plan?.kind === "FORFAIT" && (row.status || "").toUpperCase() !== "CANCELLED")
              .map((row) => row.ends_at),
            ...payments.map((row) => row.occurred_at),
          ]) ?? todayInputValue
        : todayInputValue;
  const selectedBalanceDate = isDateInput(balanceDateParam) ? balanceDateParam : defaultBalanceDate;
  const selectedBalanceDateEndMs = endOfDateUtcMs(selectedBalanceDate);

  const productCategories = productCategoriesResult.ok
    ? productCategoriesResult.data.categories
    : (() => {
        errors.push(`product_categories: ${productCategoriesResult.message}`);
        return [] as string[];
      })();
  const catalogProducts = catalogProductsResult.ok
    ? catalogProductsResult.data
    : (() => {
        errors.push(`catalog_products: ${catalogProductsResult.message}`);
        return [] as AdminCatalogProductOut[];
      })();
  const purchaseCatalogProducts = catalogProducts.filter((product) => product.active);
  const manualChargeProductOptions = catalogProducts
    .filter((product) => product.active && product.category_name)
    .map((product) => ({
      id: product.id,
      title: product.title,
      categoryName: product.category_name,
      priceInclVat: product.price_incl_vat,
      vatRate: product.vat_rate,
    }));
  const manualChargeCategories = Array.from(
    new Set([
      ...productCategories,
      ...manualChargeProductOptions.map((product) => String(product.categoryName ?? "").trim()).filter((value) => value.length > 0),
    ]),
  ).sort((a, b) => a.localeCompare(b, sortLocale));

  const enabledPaymentMethods = paymentMethodsResult.ok
    ? paymentMethodsResult.data.methods.filter((method) => method.enabled)
    : (() => {
        errors.push(`payment_methods: ${paymentMethodsResult.message}`);
        return DEFAULT_PAYMENT_METHOD_OPTIONS.map((item) => ({ ...item, enabled: true }));
      })();
  const legalEntities = legalEntitiesResult.ok
    ? legalEntitiesResult.data.filter((row) => row.is_active)
    : (() => {
        errors.push(`legal_entities: ${legalEntitiesResult.message}`);
        return [] as AdminLegalEntityOut[];
      })();
  const checkReceiptLocations = locationsResult.ok
    ? locationsResult.data
        .filter((row) => row.active && ["RICHELIEU", "BAR_LE_DUC"].includes(String(row.code || "").trim().toUpperCase()))
        .sort((a, b) => a.name.localeCompare(b.name, sortLocale))
        .map((row) => ({ id: row.id, code: row.code, name: row.name }))
    : (() => {
        errors.push(`locations: ${locationsResult.message}`);
        return [] as Array<{ id: string; code: string; name: string }>;
      })();

  const family = familyResult.ok
    ? familyResult.data
    : (() => {
        errors.push(`family: ${familyResult.message}`);
        return {
          client_id: client.id,
          client_kind: client.client_kind,
          links_as_adult: [],
          links_as_child: [],
          billing_recipient_adult_id: null,
          billing_children: [],
        } as AdminClientFamilyOut;
      })();
  const hasConfiguredFamilyBillingSplit = family.billing_children.some(
    (billingChild) => billingChild.payers.filter((payer) => payer.allocation !== null).length >= 2,
  );

  if (currentTab === "factures" && client.client_kind === "CHILD") {
    if (family.billing_recipient_adult_id) {
      const redirectSearch = cloneSearchParams(searchParams);
      redirectSearch.set("tab", "factures");
      redirect(`/admin/clients/${family.billing_recipient_adult_id}?${redirectSearch.toString()}`);
    }
    redirect(
      `/admin/clients/${client.id}?tab=famille&error=${encodeURIComponent(t("admin.client_detail.family_missing_billing_recipient"))}`,
    );
  }

  const groups = groupsResult.ok
    ? groupsResult.data
    : (() => {
        errors.push(`groups: ${groupsResult.message}`);
        return [] as AdminClientGroupOut[];
      })();

  const manualCredits = manualCreditsResult.ok
    ? manualCreditsResult.data
    : (() => {
        errors.push(`manual_credits: ${manualCreditsResult.message}`);
        return [] as AdminClientManualCreditOut[];
      })();

  const notes = notesResult.ok
    ? notesResult.data
    : (() => {
        errors.push(`notes: ${notesResult.message}`);
        return [] as AdminClientNoteOut[];
      })();

  const quoteChanges = quoteChangesResult.ok
    ? quoteChangesResult.data
    : (() => {
        errors.push(`quote_changes: ${quoteChangesResult.message}`);
        return [] as AdminStudentQuoteChangeOut[];
      })();

  const approvedQuotes = approvedQuotesResult.ok
    ? approvedQuotesResult.data
    : (() => {
        errors.push(`approved_quotes: ${approvedQuotesResult.message}`);
        return [] as ApprovedQuoteOption[];
      })();

  const messageRecipientOptions = (() => {
    const byEmail = new Map<string, { email: string; label: string }>();
    const addOption = (emailRaw: string | null | undefined, firstName?: string | null, lastName?: string | null) => {
      const email = String(emailRaw || "").trim();
      if (!email) {
        return;
      }
      const key = email.toLowerCase();
      if (byEmail.has(key)) {
        return;
      }
      byEmail.set(key, {
        email,
        label: contactDisplayLabel(firstName, lastName, email),
      });
    };

    addOption(client.email, client.first_name, client.last_name);
    for (const link of family.links_as_adult) {
      addOption(link.adult.email, link.adult.first_name, link.adult.last_name);
      addOption(link.child.email, link.child.first_name, link.child.last_name);
    }
    for (const link of family.links_as_child) {
      addOption(link.adult.email, link.adult.first_name, link.adult.last_name);
      addOption(link.child.email, link.child.first_name, link.child.last_name);
    }

    return Array.from(byEmail.values()).sort((a, b) => a.label.localeCompare(b.label, sortLocale));
  })();
  const billingRecipientEmail = (() => {
    const billingId = family.billing_recipient_adult_id;
    if (!billingId) {
      return null;
    }
    for (const link of family.links_as_child) {
      if (link.adult.id === billingId) {
        return String(link.adult.email || "").trim() || null;
      }
    }
    for (const link of family.links_as_adult) {
      if (link.adult.id === billingId) {
        return String(link.adult.email || "").trim() || null;
      }
    }
    return null;
  })();

  const quoteChangeStudentOptions = (() => {
    const byId = new Map<string, { id: string; label: string }>();
    const addUser = (user: { id: string; first_name: string | null; last_name: string | null; email: string | null }) => {
      if (!user.id || byId.has(user.id)) {
        return;
      }
      byId.set(user.id, {
        id: user.id,
        label: contactDisplayLabel(user.first_name, user.last_name, user.email || user.id),
      });
    };
    addUser(client);
    for (const link of family.links_as_adult) {
      addUser(link.child);
    }
    for (const link of family.links_as_child) {
      addUser(link.child);
    }
    return Array.from(byId.values()).sort((a, b) => a.label.localeCompare(b.label, sortLocale));
  })();

  const readyBillingAdjustmentsCount = quoteChanges.reduce(
    (count, change) => count + change.billing_adjustments.filter((adjustment) => adjustment.status === "READY").length,
    0,
  );
  const quoteChangesRecap = buildQuoteChangesRecap(quoteChanges, fullName || client.email, language);

  const messageRows = messages
    .map((msg) => ({
      id: msg.id,
      occurredAt: msg.sent_at ?? msg.scheduled_for_utc,
      subject: msg.subject_preview,
      preview: truncatePreview(msg.body_preview || msg.subject_preview || "", 100),
      status: msg.status,
      statusMeta: messageStatusMeta(msg.status, msg.error_message, language),
      session: msg.session_title ?? "-",
      recipient: msg.recipient ?? "-",
      source: msg.source ?? "-",
      bodyFull: msg.body_full ?? "",
      bodyFormat: msg.body_format,
      errorMessage: msg.error_message,
      canForward: Boolean(msg.can_forward && msg.channel === "EMAIL"),
    }))
    .sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());
  const selectedMessageForModal = messageModalId ? messages.find((row) => row.id === messageModalId) ?? null : null;
  const openMessageViewModal = currentTab === "messages" && messageModalAction === "view" && selectedMessageForModal !== null;
  const openMessageComposeModal =
    currentTab === "messages" &&
    (messageModalAction === "compose" || (messageModalAction === "forward" && selectedMessageForModal !== null));
  const isForwardCompose = messageModalAction === "forward" && selectedMessageForModal !== null;
  const messageComposeDefaultToEmails = (() => {
    const defaults = new Set<string>();
    const add = (emailRaw: string | null | undefined) => {
      const email = String(emailRaw || "").trim().toLowerCase();
      if (email) {
        defaults.add(email);
      }
    };
    if (isForwardCompose && selectedMessageForModal?.recipient) {
      add(selectedMessageForModal.recipient);
      return defaults;
    }
    add(client.email);
    add(billingRecipientEmail);
    if (defaults.size === 0 && messageRecipientOptions.length > 0) {
      add(messageRecipientOptions[0].email);
    }
    return defaults;
  })();
  const messageComposeDefaultToFree = (() => {
    if (!isForwardCompose || !selectedMessageForModal?.recipient) {
      return "";
    }
    const recipient = selectedMessageForModal.recipient.trim();
    if (!recipient) {
      return "";
    }
    const existsInOptions = messageRecipientOptions.some((option) => option.email.toLowerCase() === recipient.toLowerCase());
    return existsInOptions ? "" : recipient;
  })();
  const messageComposeSubject =
    isForwardCompose && selectedMessageForModal ? buildForwardSubject(selectedMessageForModal.subject_preview, language) : "";
  const messageComposeBody =
    isForwardCompose && selectedMessageForModal ? buildForwardBody(selectedMessageForModal, language) : "";
  const messageComposeBodyFormat =
    isForwardCompose && selectedMessageForModal
      ? selectedMessageForModal.body_format === "TEXT"
        ? "TEXT"
        : "HTML"
      : "HTML";
  const messageComposeSource = isForwardCompose ? "ADMIN_CLIENT_FORWARD_MESSAGE" : "ADMIN_CLIENT_DIRECT_MESSAGE";

  const openNoteViewModal = currentTab === "fiche" && noteModalAction === "view" && noteModalId.length > 0;
  const selectedNoteForView = openNoteViewModal ? notes.find((row) => row.id === noteModalId) ?? null : null;
  const selectedNoteInvoiceDetails = selectedNoteForView ? rangeInvoiceNoteDetails(selectedNoteForView, language) : null;

  const normalizedPurchaseType = purchaseType === "PRODUCT" ? "PRODUCT" : "FORMULA";
  const selectedFormulaForPurchase = purchasePlanId ? formulas.find((formula) => formula.id === purchasePlanId) ?? null : null;
  const selectedCatalogProductForPurchase =
    purchasePlanId ? purchaseCatalogProducts.find((product) => product.id === purchasePlanId) ?? null : null;
  const selectedPlanForPurchase = purchasePlanId ? plans.find((plan) => plan.id === purchasePlanId) ?? null : null;
  const purchaseOfferOptions =
    normalizedPurchaseType === "PRODUCT"
      ? purchaseCatalogProducts.map((product) => ({
          id: product.id,
          label: `${product.title}${product.category_name ? ` · ${product.category_name}` : ""}`,
          helper: `${formatMoney(product.price_incl_vat, client.preferred_currency || "EUR", language)} · ${t("admin.client_detail.purchase_type.product")}`,
        }))
      : formulas.map((formula) => ({
          id: formula.id,
          label: `${formula.name} (${planKindLabel(formula.kind, language)})`,
          helper:
            formula.monthly_price_excl_vat !== null
              ? `${formatMoney(formula.monthly_price_excl_vat, formula.currency_code || client.preferred_currency || "EUR", language)} · ${planKindLabel(formula.kind, language)}`
              : planKindLabel(formula.kind, language),
        }));
  const selectedPurchaseOfferHelper =
    purchaseOfferOptions.find((offer) => offer.id === purchasePlanId)?.helper ?? purchaseOfferOptions[0]?.helper ?? null;
  const formulaPaymentMethodCodes = (() => {
    if (selectedFormulaForPurchase && selectedFormulaForPurchase.payment_methods.length > 0) {
      return selectedFormulaForPurchase.payment_methods;
    }
    const seen = new Set<string>();
    const out: string[] = [];
    for (const formula of formulas) {
      for (const method of formula.payment_methods) {
        const code = method.trim().toUpperCase();
        if (!code || seen.has(code)) {
          continue;
        }
        seen.add(code);
        out.push(code);
      }
    }
    return out;
  })();
  const purchasePaymentMethodOptions = (() => {
    const fallbackCodes = DEFAULT_PAYMENT_METHOD_OPTIONS.map((method) => method.code.toUpperCase());
    const sourceCodes =
      normalizedPurchaseType === "FORMULA"
        ? formulaPaymentMethodCodes.length > 0
          ? formulaPaymentMethodCodes
          : enabledPaymentMethods.map((method) => method.code)
        : enabledPaymentMethods.map((method) => method.code);
    const uniqueCodes = Array.from(new Set((sourceCodes.length > 0 ? sourceCodes : fallbackCodes).map((code) => code.toUpperCase())));
    const giftCardAllowed = normalizedPurchaseType === "PRODUCT" || selectedPlanForPurchase?.kind === "PACK";
    if (giftCardAllowed && !uniqueCodes.includes("GIFT_CARD")) {
      uniqueCodes.push("GIFT_CARD");
    }
    return uniqueCodes.map((code) => ({
      code,
      label: localizedBillingMethodLabel(code, language),
    }));
  })();
  const selectedPurchaseOfferForTerms =
    normalizedPurchaseType === "PRODUCT"
      ? selectedCatalogProductForPurchase
        ? {
            id: selectedCatalogProductForPurchase.id,
            name: selectedCatalogProductForPurchase.title,
          }
        : null
      : selectedPlanForPurchase
        ? {
            id: selectedPlanForPurchase.id,
            name: selectedPlanForPurchase.name,
          }
        : null;
  const discountedTotalForPurchase = purchaseDiscountedTotalRaw ? Number(purchaseDiscountedTotalRaw) : Number.NaN;
  const hasDiscountedTotalForPurchase = Number.isFinite(discountedTotalForPurchase) && discountedTotalForPurchase >= 0;
  const selectedPlanBaseTotal =
    normalizedPurchaseType === "PRODUCT"
      ? selectedCatalogProductForPurchase?.price_incl_vat ?? null
      : selectedPlanForPurchase?.base_price_ttc ?? selectedPlanForPurchase?.monthly_price_excl_vat ?? null;
  const selectedPlanPurchaseTotal =
    normalizedPurchaseType === "PRODUCT"
      ? selectedCatalogProductForPurchase?.price_incl_vat ?? null
      : selectedPlanForPurchase?.price_ttc ?? selectedPlanBaseTotal;
  const selectedPlanCurrency =
    normalizedPurchaseType === "PRODUCT"
      ? client.preferred_currency || "EUR"
      : selectedPlanForPurchase?.currency_code || client.preferred_currency || "EUR";
  const isCardOnlinePurchase = purchasePaymentMethod === "CARD_ONLINE";
  const canSendPaymentLink = isCardOnlinePurchase && normalizedPurchaseType === "FORMULA";
  const purchaseTypeLabel =
    normalizedPurchaseType === "PRODUCT"
      ? t("admin.client_detail.purchase_type.product_plural")
      : t("admin.client_detail.purchase_type.formula");
  const purchaseWizardReturnSearch = new URLSearchParams({
    tab: purchaseReturnTab,
    purchase_modal: "wizard",
    purchase_return_tab: purchaseReturnTab,
    purchase_type: normalizedPurchaseType,
    purchase_plan_id: purchasePlanId,
    purchase_payment_method: purchasePaymentMethod,
    purchase_start_date: purchaseStartDateInputValue,
  });
  if (hasDiscountedTotalForPurchase) {
    purchaseWizardReturnSearch.set("purchase_discounted_total", discountedTotalForPurchase.toFixed(2));
  }
  const purchaseWizardReturnHref = `/admin/clients/${client.id}?${purchaseWizardReturnSearch.toString()}`;
  const purchaseTypeFormulaHref = (() => {
    const search = new URLSearchParams({
      tab: purchaseReturnTab,
      purchase_modal: "wizard",
      purchase_return_tab: purchaseReturnTab,
      purchase_type: "FORMULA",
      purchase_start_date: purchaseStartDateInputValue,
    });
    if (hasDiscountedTotalForPurchase) {
      search.set("purchase_discounted_total", discountedTotalForPurchase.toFixed(2));
    }
    return `/admin/clients/${client.id}?${search.toString()}`;
  })();
  const purchaseTypeProductHref = (() => {
    const search = new URLSearchParams({
      tab: purchaseReturnTab,
      purchase_modal: "wizard",
      purchase_return_tab: purchaseReturnTab,
      purchase_type: "PRODUCT",
      purchase_start_date: purchaseStartDateInputValue,
    });
    if (hasDiscountedTotalForPurchase) {
      search.set("purchase_discounted_total", discountedTotalForPurchase.toFixed(2));
    }
    return `/admin/clients/${client.id}?${search.toString()}`;
  })();

  const activeSubscriptions = subscriptions.filter(
    (sub) => (sub.status === "ACTIVE" || sub.status === "PAUSED") && !isPendingSubscriptionCancellation(sub),
  );
  const endingSubscriptions = subscriptions.filter(
    (sub) => (sub.status === "ACTIVE" || sub.status === "PAUSED") && isPendingSubscriptionCancellation(sub),
  );
  const pendingSubscriptions = subscriptions.filter((sub) => sub.status === "PENDING");
  const archivedSubscriptions = subscriptions.filter(
    (sub) =>
      (sub.status !== "ACTIVE" && sub.status !== "PAUSED" && sub.status !== "PENDING") ||
      isCancellationAlreadyEffective(sub),
  );
  const hasForfaitPlan = subscriptions.some((sub) => sub.plan.kind === "FORFAIT");
  const visibleCurrentSubscriptions = [...activeSubscriptions, ...endingSubscriptions, ...pendingSubscriptions];
  const selectedSubscriptionForModal =
    subscriptionModalId &&
    (subscriptionModalAction === "suspend" ||
      subscriptionModalAction === "cancel" ||
      subscriptionModalAction === "cancel_now" ||
      subscriptionModalAction === "billing" ||
      subscriptionModalAction === "expiry" ||
      subscriptionModalAction === "forfait_pricing")
      ? subscriptions.find((sub) => sub.id === subscriptionModalId) ?? null
      : null;
  const selectedSubscriptionHasEditablePause = Boolean(
    selectedSubscriptionForModal?.suspension_ends_at &&
      Date.parse(selectedSubscriptionForModal.suspension_ends_at) > Date.now(),
  );
  const selectedCreditForModal = openManualCreditModal
    ? manualCredits.find((row) => row.credit_type_id === creditTypeModalId) ?? null
    : null;
  const selectedPaymentForModal =
    paymentModalAction === "refund"
      ? payments.find((row) => row.id === paymentModalId && row.source.toUpperCase() === paymentModalSource) ?? null
      : null;
  const selectedBookingReceiptForRefund =
    currentTab === "reservations" && paymentModalAction === "receipt_refund"
      ? bookings.find((row) => row.payment_receipt_id === paymentModalId) ?? null
      : null;
  const selectedManualTransactionForEdit =
    paymentModalAction === "edit_manual"
      ? payments.find((row) => row.id === paymentModalId && row.source.toUpperCase() === "MANUAL") ?? null
      : null;
  const cancellationEffectiveAtMs = (() => {
    if (!selectedSubscriptionForModal) {
      return Number.NaN;
    }
    if (subscriptionModalAction === "cancel_now") {
      return Date.now();
    }
    if (selectedSubscriptionForModal.plan.kind === "SUBSCRIPTION") {
      const cycleEndRaw =
        selectedSubscriptionForModal.next_payment_at ??
        selectedSubscriptionForModal.ends_at ??
        addMonths(new Date(selectedSubscriptionForModal.started_at), 1).toISOString();
      const parsed = Date.parse(cycleEndRaw);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
      return Date.now();
    }
    const fallbackRequestedDate = formatDateForInput(selectedSubscriptionForModal.cancellation_requested_at, todayInputValue);
    const requestedAt = Date.parse(`${fallbackRequestedDate}T00:00:00.000Z`);
    const now = Date.now();
    if (!Number.isFinite(requestedAt)) {
      return now;
    }
    return Math.max(requestedAt, now);
  })();
  const blockingFutureBookingsForCancellation = selectedSubscriptionForModal
    ? bookings
        .filter((row) => {
          if (row.client_plan_subscription_id !== selectedSubscriptionForModal.id) {
            return false;
          }
          if (!ACTIVE_SUBSCRIPTION_BOOKING_STATUSES.has((row.status || "").trim().toUpperCase())) {
            return false;
          }
          if ((row.session_status || "").trim().toUpperCase() === "CANCELLED") {
            return false;
          }
          const startAtMs = Date.parse(row.session_start_at_utc);
          if (!Number.isFinite(startAtMs) || !Number.isFinite(cancellationEffectiveAtMs)) {
            return false;
          }
          return startAtMs > cancellationEffectiveAtMs;
        })
        .sort((a, b) => a.session_start_at_utc.localeCompare(b.session_start_at_utc))
    : [];
  const hasBlockingFutureBookingsForCancellation = blockingFutureBookingsForCancellation.length > 0;
  const cancellationConflictPreview = blockingFutureBookingsForCancellation
    .slice(0, 3)
    .map((row) => formatDate(row.session_start_at_utc))
    .join(", ");
  const openManualTransactionWizard = paymentModalAction === "manual";
  const openInvoiceRangeWizard = paymentModalAction === "invoice_range" && (currentTab === "paiements" || currentTab === "factures");
  const manualTransactionSelectedType = manualTransactionModalType ?? "payment";
  const manualWizardStep = manualStepRaw === "2" && manualTransactionModalType !== null ? 2 : 1;
  const openManualTransactionStepOne = openManualTransactionWizard && manualWizardStep === 1;
  const openManualTransactionStepTwo = openManualTransactionWizard && manualWizardStep === 2 && manualTransactionModalType !== null;
  const openManualTransactionEditModal = paymentModalAction === "edit_manual" && selectedManualTransactionForEdit !== null;
  const openPaymentFiltersModal = paymentModalAction === "filters";

  const totalRemainingCredits = [...activeSubscriptions, ...endingSubscriptions].reduce((acc, sub) => {
    if (sub.plan.kind !== "PACK") {
      return acc;
    }
    return acc + Number(sub.credits_remaining ?? 0);
  }, 0);
  const subscribedMakeupSummaries = makeupSummaries.filter((summary) => summary.credits_initial > 0);

  const activeMonthlySubscriptions = activeSubscriptions.filter((sub) => sub.plan.kind === "SUBSCRIPTION").length;
  const bookedReservations = bookings.filter((row) => row.status === "BOOKED" || row.status === "WAITLISTED");

  const closedAttendances = bookings.filter(
    (row) => row.status === "ATTENDED" || row.status === "NO_SHOW" || row.status === "EXCUSED_ABSENCE",
  );
  const attendedCount = closedAttendances.filter((row) => row.status === "ATTENDED").length;
  const attendanceRate = closedAttendances.length === 0 ? 0 : (attendedCount / closedAttendances.length) * 100;

  const upcomingBookings = bookings
    .filter((row) => Date.parse(row.session_start_at_utc) >= Date.now())
    .sort((a, b) => a.session_start_at_utc.localeCompare(b.session_start_at_utc));

  const pastBookings = bookings
    .filter((row) => Date.parse(row.session_start_at_utc) < Date.now())
    .sort((a, b) => b.session_start_at_utc.localeCompare(a.session_start_at_utc));
  const regularSchedules = regularScheduleSummaries(bookings);
  const reservationRows = [...upcomingBookings, ...pastBookings];
  const includedPlanBookingsCount = bookings.filter((row) => bookingIsIncludedInPlan(row)).length;
  const receiptsSentCount = bookings.filter((row) => Boolean(row.payment_receipt_sent_at)).length;

  const paymentsAsOfDate = payments.filter((row) => {
    const occurredAtMs = Date.parse(row.occurred_at);
    if (!Number.isFinite(occurredAtMs)) {
      return false;
    }
    return occurredAtMs <= selectedBalanceDateEndMs;
  });

  const filteredPayments = payments.filter((row) => {
    if (paymentFilterQuery.length > 0) {
      const searchable = [
        paymentSourceLabel(row.source, language),
        row.payment_method_code ? localizedBillingMethodLabel(row.payment_method_code, language) : row.payment_method_label ?? "",
        row.label,
        row.reference ?? "",
        paymentStatusDisplayLabel(row, language),
        row.invoice_number ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!searchable.includes(paymentFilterQuery.toLowerCase())) {
        return false;
      }
    }
    if (paymentFilterAmount !== null) {
      const rowAmount = Number(row.total_incl_vat || "0");
      if (!Number.isFinite(rowAmount) || Math.abs(rowAmount - paymentFilterAmount) > 0.009) {
        return false;
      }
    }
    return true;
  });
  const invoicePeriodStartMs = isDateInput(invoiceStartDateInputValue)
    ? Date.parse(`${invoiceStartDateInputValue}T00:00:00.000Z`)
    : Number.NaN;
  const invoicePeriodEndMs = isDateInput(invoiceEndDateInputValue)
    ? Date.parse(`${invoiceEndDateInputValue}T23:59:59.999Z`)
    : Number.NaN;
  const invoiceCandidatePayments = payments.filter((row) => {
    if (isLegacyInvoicePayment(row)) {
      return false;
    }
    const occurredAtMs = Date.parse(row.occurred_at);
    if (!Number.isFinite(invoicePeriodStartMs) || !Number.isFinite(invoicePeriodEndMs) || !Number.isFinite(occurredAtMs)) {
      return false;
    }
    if (occurredAtMs < invoicePeriodStartMs || occurredAtMs > invoicePeriodEndMs) {
      return false;
    }
    const invoiceStatus = String(row.invoice_status || "").trim().toUpperCase();
    if (invoiceStatus === "ISSUED" || invoiceStatus === "PAID") {
      return false;
    }
    const statusForInvoice = invoiceStatus || String(row.status || "").trim().toUpperCase();
    if (!invoiceIncludePending && statusForInvoice === "PENDING") {
      return false;
    }
    if (!invoiceIncludeCancelled && (statusForInvoice === "CANCELLED" || statusForInvoice === "REFUNDED" || statusForInvoice === "NOT_BILLABLE")) {
      return false;
    }
    return true;
  });
  const invoiceSelectedPaymentKeys = new Set(
    invoiceSelectedPaymentKeysRaw.length > 0
      ? invoiceSelectedPaymentKeysRaw
      : invoiceCandidatePayments.map((row) => invoicePaymentKey(row)),
  );
  const invoiceParticipantLabelsById = new Map<string, string>();
  const addInvoiceParticipant = (member: { id: string; first_name: string | null; last_name: string | null; email: string | null }) => {
    if (!member.id || invoiceParticipantLabelsById.has(member.id)) {
      return;
    }
    invoiceParticipantLabelsById.set(
      member.id,
      contactDisplayLabel(member.first_name, member.last_name, member.email || member.id),
    );
  };
  addInvoiceParticipant(client);
  for (const link of family.links_as_adult) {
    addInvoiceParticipant(link.adult);
    addInvoiceParticipant(link.child);
  }
  for (const link of family.links_as_child) {
    addInvoiceParticipant(link.adult);
    addInvoiceParticipant(link.child);
  }
  const invoiceSelectionRows = invoiceCandidatePayments.map((row) => ({
    key: invoicePaymentKey(row),
    participantId: row.student_user_id,
    participantLabel: row.student_user_id
      ? invoiceParticipantLabelsById.get(row.student_user_id) ?? t("admin.client_detail.invoice_unknown_participant")
      : t("admin.client_detail.invoice_unassigned_participant"),
    dateLabel: formatDate(row.occurred_at, language),
    sourceLabel: paymentSourceLabel(row.source, language),
    label: row.label,
    reference: row.reference,
    statusLabel: paymentStatusDisplayLabel(row, language),
    totalLabel: formatMoney(row.total_incl_vat, row.currency, language),
    totalInclVat: row.total_incl_vat,
    currency: row.currency,
  }));

  const paymentInvoices: InvoiceListRow[] = payments
    .filter((row) => {
      if (row.invoice_note_id) {
        return false;
      }
      if (isManualDiscountMovement(row)) {
        return false;
      }
      const normalizedInvoiceStatus = (row.invoice_status ?? "").toUpperCase();
      return normalizedInvoiceStatus === "PAID" || normalizedInvoiceStatus === "CANCELLED";
    })
    .map((row) => ({
      kind: "payment",
      key: `payment-${row.source}-${row.id}`,
      occurredAt: row.occurred_at,
      invoiceNumber: row.invoice_number,
      typeLabel: paymentSourceLabel(row.source, language),
      label: row.label,
      status: row.invoice_status,
      total: row.total_incl_vat,
      currency: row.currency,
      source: row.source,
      paymentId: row.id,
      paymentStatus: row.status,
    }));

  const generatedRangeInvoices: RangeInvoiceListRow[] = rangeInvoices.map((row) => ({
      kind: "range",
      key: `range-${row.invoice_number}-${row.note_id}`,
      noteId: row.note_id,
      occurredAt: `${row.issued_date}T00:00:00.000Z`,
      invoiceNumber: row.invoice_number,
      typeLabel:
        row.generation_mode === "AUTO"
          ? t("admin.client_detail.invoice_generation_type_auto")
          : t("admin.client_detail.invoice_generation_type_manual"),
      modeLabel:
        row.generation_mode === "AUTO"
          ? t("admin.client_detail.invoice_generation_auto")
          : t("admin.client_detail.invoice_generation_manual"),
      label: `${formatDateInputLabel(row.start_date, language)} - ${formatDateInputLabel(row.end_date, language)}${
        row.generation_mode === "AUTO"
          ? row.auto_period_scope === "FUTURE"
            ? ` | ${t("admin.client_detail.invoice_scope_upcoming")}`
            : ` | ${t("admin.client_detail.invoice_scope_previous")}`
          : ""
      }${row.family_billing_payer_client_id && row.recipient_client_name ? ` | Payeur : ${row.recipient_client_name}` : ""}`,
      status: row.invoice_status,
      issuedDate: row.issued_date,
      startDate: row.start_date,
      endDate: row.end_date,
      dueDate: row.due_date,
      noDueDate: row.no_due_date,
      layout: row.layout,
      groupAdjustmentsByType: row.group_adjustments_by_type,
      includeDiscountAdjustments: row.include_discount_adjustments,
      includeSupplementAdjustments: row.include_supplement_adjustments,
      includePending: row.include_pending,
      includeCancelled: row.include_cancelled,
      publicNote: row.public_note,
      privateNote: row.private_note,
      emailedAt: row.emailed_at ?? null,
      remindedAt: row.reminded_at ?? null,
      bankTransferOrderId: row.bank_transfer_order_id ?? null,
      bankTransferOrderReference: row.bank_transfer_order_reference ?? null,
      bankTransferOrderStatus: row.bank_transfer_order_status ?? null,
      bankTransferOrderExpiresAt: row.bank_transfer_order_expires_at ?? null,
      bankTransferOrderPaidAt: row.bank_transfer_order_paid_at ?? null,
      includedPaymentKeys: row.included_payment_keys ?? [],
      totalLabel: rangeInvoiceTotalLabel(row.totals_by_currency, language),
      balanceLabel:
        row.invoice_status === "ISSUED" && Object.keys(row.total_to_pay_by_currency || {}).length > 0
          ? rangeInvoiceTotalLabel(row.total_to_pay_by_currency, language)
          : null,
      checkCoverageStatus: row.check_coverage_status ?? "NONE",
      pendingCheckAmountLabel:
        Object.keys(row.pending_check_amounts_by_currency || {}).length > 0
          ? rangeInvoiceTotalLabel(row.pending_check_amounts_by_currency, language)
          : null,
      pendingCheckCount: row.pending_check_count ?? 0,
      remindersSuspended: Boolean(row.reminders_suspended),
      downloadHref: rangeInvoicePdfHref(client.id, row.note_id, false),
      viewHref: rangeInvoicePdfHref(client.id, row.note_id, true),
      sellerLegalEntityId: row.seller_legal_entity_id ?? null,
      billingEntity: row.billing_entity ?? null,
      familyBillingPayerName: row.family_billing_payer_client_id ? row.recipient_client_name ?? null : null,
      documentType: row.document_type ?? (row.invoice_status === "CREDIT_NOTE" ? "CREDIT_NOTE" : "INVOICE"),
      originalInvoiceNumber: row.original_invoice_number ?? null,
      creditNoteNumber: row.credit_note_number ?? null,
    }));

  const historicalInvoices: InvoiceListRow[] = legacyInvoices.map((row) => ({
    kind: "legacy",
    key: `legacy-${row.id}`,
    invoiceId: row.id,
    occurredAt: row.issued_at,
    invoiceNumber: row.invoice_number,
    typeLabel: t("admin.client_detail.invoice_generation_type_legacy", { source: row.source }),
    label: row.label,
    status: row.status,
    total: row.total_incl_vat,
    currency: row.currency,
  }));

  const invoicesByIdentity = new Map<string, InvoiceListRow>();
  for (const row of [...generatedRangeInvoices, ...paymentInvoices, ...historicalInvoices]) {
    const normalizedInvoiceNumber = (row.invoiceNumber || "").trim().toUpperCase();
    const identity = normalizedInvoiceNumber ? `invoice:${normalizedInvoiceNumber}` : row.key;
    invoicesByIdentity.set(identity, row);
  }
  const invoices = Array.from(invoicesByIdentity.values()).sort(
    (a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt),
  );
  const bookingPaymentsReceivedCount = bookings.filter((row) => row.payment_received).length;
  const otherPaymentsReceivedCount = payments.filter((row) => isReceivedClientPayment(row)).length;
  const paymentsReceivedCount = bookingPaymentsReceivedCount + otherPaymentsReceivedCount;
  const bookingRefundsRecordedCount = bookings.filter((row) => row.payment_refunded).length;
  const otherRefundsRecordedCount = payments.filter((row) => isRecordedClientRefund(row)).length;
  const refundsRecordedCount = bookingRefundsRecordedCount + otherRefundsRecordedCount;
  const finalInvoicesGeneratedCount = invoices.filter((row) => {
    const status = (row.status || "").trim().toUpperCase();
    return status !== "CANCELLED" && status !== "CREDIT_NOTE";
  }).length;
  const bookingInvoicesReadyCount = bookings.filter((row) => canGenerateFinalInvoiceForBooking(row)).length;
  const otherInvoicesReadyCount = payments.filter((row) => paymentNeedsFinalInvoice(row)).length;
  const finalInvoicesReadyCount = bookingInvoicesReadyCount + otherInvoicesReadyCount;
  const finalInvoicesWaitingCount = bookings.filter((row) => waitsForServiceCompletion(row) && row.payment_received).length;
  const reconcilableRangeInvoices = generatedRangeInvoices.filter((row) => (row.status || "").trim().toUpperCase() === "ISSUED");
  const manualTransactionLegalEntities = legalEntities.map((row) => ({ id: row.id, name: row.name }));
  const manualTransactionPaymentMethods = enabledPaymentMethods.map((row) => ({
    code: row.code,
    label: paymentMethodOptionLabel(row, language),
    defaultLegalEntityId: row.default_legal_entity_id,
    defaultLegalEntityName: row.default_legal_entity_name,
  }));
  const manualReconcilableInvoices = reconcilableRangeInvoices.map((row) => ({
    noteId: row.noteId,
    occurredAtLabel: formatDateOnlyNumeric(row.occurredAt),
    totalLabel: row.totalLabel,
    invoiceNumber: row.invoiceNumber,
    sellerLegalEntityId: row.sellerLegalEntityId,
    sellerLegalEntityName:
      manualTransactionLegalEntities.find((entity) => entity.id === row.sellerLegalEntityId)?.name ?? row.billingEntity ?? null,
  }));
  const selectedRangeInvoiceForModal =
    (paymentModalAction === "invoice_email" || paymentModalAction === "invoice_bank_transfer" || paymentModalAction === "invoice_partial_payment") && invoiceNoteId
      ? generatedRangeInvoices.find((row) => row.noteId === invoiceNoteId) ?? null
      : null;
  const partialPaymentContext = paymentModalAction === "invoice_partial_payment" && selectedRangeInvoiceForModal
    ? await backendRequest<PartialPaymentContext>(`/api/v1/admin/clients/${params.clientId}/invoices/range/${selectedRangeInvoiceForModal.noteId}/partial-payments`, {}, token)
    : null;
  if (partialPaymentContext && !partialPaymentContext.ok) errors.push(partialPaymentContext.message);
  const invoiceSmsDefaultPhone = client.mobile_phone_1 || client.mobile_phone_2 || client.phone || client.home_phone || "";
  const invoiceChangeSummaryReferenceOptions = selectedRangeInvoiceForModal
    ? generatedRangeInvoices
        .filter((row) => row.noteId !== selectedRangeInvoiceForModal.noteId && row.status !== "CANCELLED")
        .filter((row) => Date.parse(row.occurredAt) <= Date.parse(selectedRangeInvoiceForModal.occurredAt))
    : [];
  const selectedReferenceInvoiceNoteId =
    referenceInvoiceNoteId && invoiceChangeSummaryReferenceOptions.some((row) => row.noteId === referenceInvoiceNoteId)
      ? referenceInvoiceNoteId
      : invoiceChangeSummaryReferenceOptions[0]?.noteId ?? "";
  let invoiceEmailPreviewResult: unknown = null;
  if (paymentModalAction === "invoice_email" && selectedRangeInvoiceForModal) {
    const invoiceEmailPreviewSearch = new URLSearchParams({
        kind: invoiceEmailKind,
        include_change_summary: includeInvoiceChangeSummary ? "true" : "false",
    });
    if (includeInvoiceChangeSummary && selectedReferenceInvoiceNoteId) {
      invoiceEmailPreviewSearch.set("reference_invoice_note_id", selectedReferenceInvoiceNoteId);
    }
    invoiceEmailPreviewResult = await backendRequest(
      `/api/v1/admin/clients/${params.clientId}/invoices/range/${selectedRangeInvoiceForModal.noteId}/email/preview?${invoiceEmailPreviewSearch.toString()}`,
      {},
      token,
    );
  }
  const invoiceEmailPreviewResultRecord =
    invoiceEmailPreviewResult && typeof invoiceEmailPreviewResult === "object"
      ? (invoiceEmailPreviewResult as { ok?: boolean; data?: AdminRangeInvoiceEmailPreviewOut; message?: string })
      : null;
  const invoiceEmailPreview =
    invoiceEmailPreviewResultRecord && invoiceEmailPreviewResultRecord.ok ? invoiceEmailPreviewResultRecord.data ?? null : null;
  if (invoiceEmailPreviewResultRecord && invoiceEmailPreviewResultRecord.ok === false) {
    errors.push(`invoice_email_preview: ${invoiceEmailPreviewResultRecord.message ?? "Erreur preview courriel"}`);
  }

  const settledManualPaymentInvoiceNumbers = new Set(
    paymentsAsOfDate
      .filter((row) => isManualPaymentMovement(row))
      .map((row) => (row.invoice_number || "").trim())
      .filter((value) => value.length > 0),
  );

  const totalsByCurrency = new Map<string, number>();
  const paidTotalsByCurrency = new Map<string, number>();
  const cancelledOrNotBillableTotalsByCurrency = new Map<string, number>();
  const rangeInvoicesAsOfDate = rangeInvoices.filter((row) => {
    if ((row.invoice_status || "").trim().toUpperCase() === "CANCELLED") {
      return false;
    }
    return endOfDateUtcMs(row.issued_date) <= selectedBalanceDateEndMs;
  });
  const activeIssuedRangeInvoicesAsOfDate = rangeInvoices.filter((row) => {
    if ((row.invoice_status || "").trim().toUpperCase() !== "ISSUED") {
      return false;
    }
    return endOfDateUtcMs(row.issued_date) <= selectedBalanceDateEndMs;
  });
  const activeIssuedRangeInvoiceNoteIds = new Set(activeIssuedRangeInvoicesAsOfDate.map((row) => row.note_id));
  const nonCancelledRangeInvoiceNoteIds = new Set(rangeInvoicesAsOfDate.map((row) => row.note_id));

  for (const invoice of activeIssuedRangeInvoicesAsOfDate) {
    const remainingByCurrency =
      Object.keys(invoice.total_to_pay_by_currency || {}).length > 0
        ? invoice.total_to_pay_by_currency
        : invoice.totals_by_currency;
    for (const [currency, rawAmount] of Object.entries(remainingByCurrency || {})) {
      const amount = Number(rawAmount || "0");
      if (!Number.isFinite(amount)) {
        continue;
      }
      totalsByCurrency.set(currency || "EUR", (totalsByCurrency.get(currency || "EUR") ?? 0) + amount);
    }
  }

  for (const row of paymentsAsOfDate) {
    const currency = row.currency || "EUR";
    const amount = Number(row.total_incl_vat || "0");
    const status = normalizePaymentStatus(row.status);
    const coveredByActiveRangeInvoice =
      Boolean(row.invoice_note_id) && activeIssuedRangeInvoiceNoteIds.has(row.invoice_note_id || "");
    const coveredByNonCancelledRangeInvoice =
      Boolean(row.invoice_note_id) && nonCancelledRangeInvoiceNoteIds.has(row.invoice_note_id || "");
    const excludePaidDepositCharge =
      isPaidPreRegistrationDepositCharge(row) &&
      settledManualPaymentInvoiceNumbers.has((row.invoice_number || "").trim());
    const shouldApplyReceivedPaymentToIssuedInvoice = coveredByActiveRangeInvoice && isReceivedManualPaymentMovement(row);

    const dueCurrent = totalsByCurrency.get(currency) ?? 0;
    totalsByCurrency.set(
      currency,
      dueCurrent +
        ((shouldApplyReceivedPaymentToIssuedInvoice || !coveredByNonCancelledRangeInvoice) &&
        shouldCountInClientBalance(row) &&
        !excludePaidDepositCharge
          ? amount
          : 0),
    );

    if (status === "NOT_BILLABLE" || status === "REFUNDED" || CANCELLED_PAYMENT_STATUSES.has(status)) {
      const current = cancelledOrNotBillableTotalsByCurrency.get(currency) ?? 0;
      cancelledOrNotBillableTotalsByCurrency.set(currency, current + amount);
    } else if (isManualPaymentMovement(row)) {
      const current = paidTotalsByCurrency.get(currency) ?? 0;
      paidTotalsByCurrency.set(currency, current + Math.abs(amount));
    } else if (isManualRefundMovement(row)) {
      const current = paidTotalsByCurrency.get(currency) ?? 0;
      paidTotalsByCurrency.set(currency, current - Math.abs(amount));
    }
  }

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = translateBackendMessage(language, readParam(searchParams, "error"));
  const invoiceErrorGlobal = readParam(searchParams, "invoice_error_global");
  const invoiceErrorFieldPayload = readParam(searchParams, "invoice_error_fields");
  const invoiceQueryFieldErrors = parseInvoiceFieldErrors(invoiceErrorFieldPayload);
  const invoiceStepValidationErrors: Record<string, string> = {};
  if (openInvoiceRangeWizard && invoiceGenerationMode === "MANUAL" && invoiceWizardStep === 2) {
    const issuedDateForValidation = invoiceIssuedDateRaw.trim();
    const startDateForValidation = invoiceStartDateRaw.trim();
    const endDateForValidation = invoiceEndDateRaw.trim();
    const dueDateForValidation = invoiceDueDateRaw.trim();
    if (!isDateInput(issuedDateForValidation)) {
      invoiceStepValidationErrors.issued_date = t("admin.client_detail.invoice_error_issued_date_required");
    }
    if (!isDateInput(startDateForValidation)) {
      invoiceStepValidationErrors.start_date = t("admin.client_detail.invoice_error_start_date_required");
    }
    if (!isDateInput(endDateForValidation)) {
      invoiceStepValidationErrors.end_date = t("admin.client_detail.invoice_error_end_date_required");
    }
    if (!invoiceNoDueDate && !isDateInput(dueDateForValidation)) {
      invoiceStepValidationErrors.due_date = t("admin.client_detail.invoice_error_due_date_required");
    }
    if (isDateInput(startDateForValidation) && isDateInput(endDateForValidation)) {
      const startMs = Date.parse(`${startDateForValidation}T00:00:00.000Z`);
      const endMs = Date.parse(`${endDateForValidation}T00:00:00.000Z`);
      if (Number.isFinite(startMs) && Number.isFinite(endMs) && endMs < startMs) {
        invoiceStepValidationErrors.end_date = t("admin.client_detail.invoice_error_end_before_start");
      }
    }
    const dueInputForCheck = invoiceNoDueDate ? issuedDateForValidation : dueDateForValidation;
    if (isDateInput(issuedDateForValidation) && isDateInput(dueInputForCheck)) {
      const issuedMs = Date.parse(`${issuedDateForValidation}T00:00:00.000Z`);
      const dueMs = Date.parse(`${dueInputForCheck}T00:00:00.000Z`);
      if (Number.isFinite(issuedMs) && Number.isFinite(dueMs) && dueMs < issuedMs) {
        invoiceStepValidationErrors.due_date = t("admin.client_detail.invoice_error_due_before_issued");
      }
    }
  }
  const invoiceErrorFieldMap = { ...invoiceStepValidationErrors, ...invoiceQueryFieldErrors };
  const hasInvoiceStepValidationErrors = Object.keys(invoiceStepValidationErrors).length > 0;
  const invoiceLegacyGlobalError = openInvoiceRangeWizard ? errorMessage : "";
  const invoiceModalGlobalError =
    invoiceErrorGlobal ||
    invoiceLegacyGlobalError ||
    (hasInvoiceStepValidationErrors ? t("admin.client_detail.invoice_fix_errors") : "");
  const pageLevelErrorMessage = openInvoiceRangeWizard ? "" : errorMessage;
  const invoiceErrorFields = Object.keys(invoiceErrorFieldMap);
  const invoiceFirstInvalidField = invoiceErrorFields.length > 0 ? invoiceErrorFields[0] : null;
  const openInvoiceRangeStepOne =
    openInvoiceRangeWizard &&
    (invoiceGenerationMode === "AUTO" || invoiceWizardStep === 1 || hasInvoiceStepValidationErrors);
  const openInvoiceRangeStepTwo =
    openInvoiceRangeWizard && invoiceGenerationMode === "MANUAL" && invoiceWizardStep === 2 && !hasInvoiceStepValidationErrors;

  const linkedChildren = family.links_as_adult;
  const linkedAdults = family.links_as_child;
  const linkedChildIds = linkedChildren.map((link) => link.child.id);
  const linkedAdultIds = linkedAdults.map((link) => link.adult.id);
  const familyAttachSearchPlaceholder =
    language === "en" ? "Type a last name, first name, or email..." : "Tapez un nom, prenom ou email...";

  const tabs: Array<{ id: ClientTab; label: string }> = [
    { id: "fiche", label: clientDetailTabLabel("fiche", language) },
    { id: "infos", label: clientDetailTabLabel("infos", language) },
    { id: "famille", label: clientDetailTabLabel("famille", language) },
    { id: "messages", label: clientDetailTabLabel("messages", language) },
    { id: "paiements", label: clientDetailTabLabel("paiements", language) },
    { id: "factures", label: clientDetailTabLabel("factures", language) },
    { id: "reservations", label: clientDetailTabLabel("reservations", language) },
    { id: "changements", label: clientDetailTabLabel("changements", language) },
  ];

  const manualTransactionTypeCodeByModal: Record<ManualTransactionModalType, "PAYMENT" | "REFUND" | "CHARGE" | "DISCOUNT"> = {
    payment: "PAYMENT",
    refund: "REFUND",
    charge: "CHARGE",
    discount: "DISCOUNT",
    fees: "CHARGE",
  };
  const manualTransactionTitleByModal: Record<ManualTransactionModalType, string> = {
    payment: t("admin.client_detail.manual_type.payment_title"),
    refund: t("admin.client_detail.manual_type.refund_title"),
    charge: t("admin.client_detail.manual_type.charge_title"),
    discount: t("admin.client_detail.manual_type.discount_title"),
    fees: t("admin.client_detail.manual_type.fees_title"),
  };
  const manualTransactionHelpByModal: Record<ManualTransactionModalType, string> = {
    payment: t("admin.client_detail.manual_type.payment_help"),
    refund: t("admin.client_detail.manual_type.refund_help"),
    charge: t("admin.client_detail.manual_type.charge_help"),
    discount: t("admin.client_detail.manual_type.discount_help"),
    fees: t("admin.client_detail.manual_type.fees_help"),
  };
  const manualTransactionDefaultLabelByModal: Record<ManualTransactionModalType, string> = {
    payment: t("admin.client_detail.manual_default.payment"),
    refund: t("admin.client_detail.manual_default.refund"),
    charge: t("admin.client_detail.manual_default.charge"),
    discount: t("admin.client_detail.manual_default.discount"),
    fees: t("admin.client_detail.manual_default.fees"),
  };
  const manualTransactionSubmitLabelByModal: Record<ManualTransactionModalType, string> = {
    payment: t("admin.client_detail.manual_submit.payment"),
    refund: t("admin.client_detail.manual_submit.refund"),
    charge: t("admin.client_detail.manual_submit.charge"),
    discount: t("admin.client_detail.manual_submit.discount"),
    fees: t("admin.client_detail.manual_submit.fees"),
  };
  const manualTransactionTypeCode =
    manualTransactionModalType === null ? null : manualTransactionTypeCodeByModal[manualTransactionModalType];
  const manualTransactionTitle = manualTransactionTitleByModal[manualTransactionSelectedType];
  const manualTransactionDefaultLabel = manualTransactionDefaultLabelByModal[manualTransactionSelectedType];
  const manualTransactionSubmitLabel = manualTransactionSubmitLabelByModal[manualTransactionSelectedType];
  const manualIsCashFlow = manualTransactionSelectedType === "payment" || manualTransactionSelectedType === "refund";
  const manualIsPayment = manualTransactionSelectedType === "payment";
  const manualVatDefault = manualIsCashFlow ? "0" : "20";
  const manualNonCashFlowType = manualTransactionTypeCode === "CHARGE" || manualTransactionTypeCode === "DISCOUNT" ? manualTransactionTypeCode : null;
  const manualStepOneBackHref = paymentsHref(client.id, { balance_date: selectedBalanceDate });
  const manualStepOneTypeHref = (type: ManualTransactionModalType): string => {
    const params: Record<string, string> = {
      payment_modal: "manual",
      manual_type: type,
      manual_step: "1",
      balance_date: selectedBalanceDate,
    };
    if (manualAmountInputValue) {
      params.manual_amount = manualAmountInputValue;
    }
    if (manualVatInputValue) {
      params.manual_vat = manualVatInputValue;
    }
    if (manualDateInputValue) {
      params.manual_date = manualDateInputValue;
    }
    return paymentsHref(client.id, params);
  };
  const manualStepTwoBackHref = paymentsHref(client.id, {
    payment_modal: "manual",
    manual_type: manualTransactionSelectedType,
    manual_step: "1",
    balance_date: selectedBalanceDate,
    manual_amount: manualAmountInputValue,
    manual_vat: manualVatInputValue || manualVatDefault,
    manual_date: manualDateInputValue,
  });
  const invoiceWizardCloseHref = paymentReturnTab === "paiements"
    ? paymentsHref(client.id, {
        balance_date: selectedBalanceDate,
        payment_filter_q: paymentFilterQuery,
        payment_filter_amount: paymentFilterAmountRaw,
      })
    : tabHref(client.id, "factures");
  const invoiceAutoLegalEntityIdInputValue =
    legalEntities.some((entity) => entity.id === invoiceAutoLegalEntityId) ? invoiceAutoLegalEntityId : legalEntities[0]?.id ?? "";
  const invoiceWizardModeHref = (mode: "MANUAL" | "AUTO"): string => {
    const params: Record<string, string> = {
      payment_modal: "invoice_range",
      payment_return_tab: paymentReturnTab,
      invoice_step: "1",
      generation_mode: mode,
      issued_date: invoiceIssuedDateInputValue,
      start_date: invoiceStartDateInputValue,
      end_date: invoiceEndDateInputValue,
      due_date: invoiceDueDateInputValue,
      no_due_date: invoiceNoDueDate ? "true" : "false",
      include_pending: invoiceIncludePending ? "true" : "false",
      include_cancelled: invoiceIncludeCancelled ? "true" : "false",
      layout: invoiceLayout,
      group_adjustments_by_type: invoiceGroupAdjustmentsByType ? "true" : "false",
      include_discount_adjustments: invoiceIncludeDiscountAdjustments ? "true" : "false",
      include_supplement_adjustments: invoiceIncludeSupplementAdjustments ? "true" : "false",
      auto_cycle_start_date: invoiceAutoCycleStartDateInputValue,
      auto_frequency: invoiceAutoFrequency,
      auto_billing_timing: invoiceAutoBillingTiming,
      auto_due_date_rule_type: invoiceAutoDueDateRuleType,
      auto_due_date_days_offset: String(invoiceAutoDueDateDaysOffset),
      auto_legal_entity_id: invoiceAutoLegalEntityIdInputValue,
      public_note: invoicePublicNote,
      private_note: invoicePrivateNote,
    };
    if (paymentReturnTab === "paiements") {
      params.balance_date = selectedBalanceDate;
      if (paymentFilterQuery) {
        params.payment_filter_q = paymentFilterQuery;
      }
      if (paymentFilterAmountRaw) {
        params.payment_filter_amount = paymentFilterAmountRaw;
      }
      return paymentsHref(client.id, params);
    }
    return invoicesHref(client.id, params);
  };
  const invoiceWizardBackToStepOneHref = (() => {
    const params: Record<string, string> = {
      payment_modal: "invoice_range",
      payment_return_tab: paymentReturnTab,
      invoice_step: "1",
      generation_mode: invoiceGenerationMode,
      issued_date: invoiceIssuedDateInputValue,
      start_date: invoiceStartDateInputValue,
      end_date: invoiceEndDateInputValue,
      due_date: invoiceDueDateInputValue,
      no_due_date: invoiceNoDueDate ? "true" : "false",
      include_pending: invoiceIncludePending ? "true" : "false",
      include_cancelled: invoiceIncludeCancelled ? "true" : "false",
      layout: invoiceLayout,
      group_adjustments_by_type: invoiceGroupAdjustmentsByType ? "true" : "false",
      include_discount_adjustments: invoiceIncludeDiscountAdjustments ? "true" : "false",
      include_supplement_adjustments: invoiceIncludeSupplementAdjustments ? "true" : "false",
      auto_cycle_start_date: invoiceAutoCycleStartDateInputValue,
      auto_frequency: invoiceAutoFrequency,
      auto_billing_timing: invoiceAutoBillingTiming,
      auto_due_date_rule_type: invoiceAutoDueDateRuleType,
      auto_due_date_days_offset: String(invoiceAutoDueDateDaysOffset),
      auto_legal_entity_id: invoiceAutoLegalEntityIdInputValue,
      public_note: invoicePublicNote,
      private_note: invoicePrivateNote,
    };
    if (paymentReturnTab === "paiements") {
      params.balance_date = selectedBalanceDate;
      if (paymentFilterQuery) {
        params.payment_filter_q = paymentFilterQuery;
      }
      if (paymentFilterAmountRaw) {
        params.payment_filter_amount = paymentFilterAmountRaw;
      }
      return paymentsHref(client.id, params);
    }
    return invoicesHref(client.id, params);
  })();
  const editManualTransactionTypeCode = (selectedManualTransactionForEdit?.manual_transaction_type || "").trim().toUpperCase();
  const editManualIsPayment = editManualTransactionTypeCode === "PAYMENT";
  const editManualVatDefault = selectedManualTransactionForEdit?.vat_rate
    ? String(selectedManualTransactionForEdit.vat_rate)
    : editManualIsPayment
      ? "0"
      : "20";
  const editManualAmountAbs = selectedManualTransactionForEdit
    ? Math.abs(Number(selectedManualTransactionForEdit.total_incl_vat || "0")).toFixed(2)
    : "0.00";
  const editManualOccurredAt = selectedManualTransactionForEdit
    ? formatDateForInput(selectedManualTransactionForEdit.occurred_at, todayInputValue)
    : todayInputValue;
  const editManualCategory = (selectedManualTransactionForEdit?.category ?? "").trim();
  const editManualCategoryIsConfigured =
    editManualCategory.length > 0 &&
    manualChargeCategories.some((category) => category.toLocaleLowerCase(sortLocale) === editManualCategory.toLocaleLowerCase(sortLocale));
  const invoiceFieldError = (fieldName: string): string | null => invoiceErrorFieldMap[fieldName] ?? null;
  const invoiceFieldInvalid = (fieldName: string): boolean => invoiceFieldError(fieldName) !== null;
  const invoiceFieldAutoFocus = (fieldName: string): boolean => invoiceFirstInvalidField === fieldName;
  const formatDateUi = (value: string): string => formatLocalizedDate(value, language);
  const formatDateOnlyUi = (value: string | null): string => formatLocalizedDateOnly(value, language);
  const formatMoneyUi = (value: string | null | undefined, currency: string): string => formatLocalizedMoney(value, currency, language);
  const visibleEmail = visibleClientEmail(client.email);
  const fullNameLabel = fullName || t("admin.client_detail.client_fallback");
  const clientKindText = clientKindLabel(client.client_kind, language);
  const clientLanguageText = client.preferred_language === "en"
    ? uiText(language, "admin.client_detail.language_name_en")
    : uiText(language, "admin.client_detail.language_name_fr");
  const heroMeta = [
    visibleEmail,
    client.mobile_phone_1 ? `${t("admin.client_detail.mobile_1")}: ${client.mobile_phone_1}` : null,
    labelFromOptions(COUNTRY_OPTIONS, client.residence_country),
    labelFromOptions(CURRENCY_OPTIONS, client.preferred_currency),
    clientKindText,
  ].filter(Boolean) as string[];

  return (
    <section className="admin-page-grid client-detail-page">
      <section className="client-hero card">
        <div className="row spread">
          <div className="row">
            <Link className="reset-link" href="/admin/clients">
              {t("admin.client_detail.back_to_clients")}
            </Link>
            <Link className="mode-link" href="/admin/clients?new_client=1">
              {t("admin.client_detail.new_client")}
            </Link>
            <form action={adminViewClientPortalAction} target="_blank" rel="noopener noreferrer">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_to" value={`/admin/clients/${client.id}?tab=${currentTab}`} />
              <button type="submit" className="mode-link">
                {t("admin.client_detail.client_view")}
              </button>
            </form>
          </div>
          <small className="muted">
            {t("admin.client_detail.created_on")} {formatDateUi(client.created_at)} | {t("admin.client_detail.updated_on")} {formatDateUi(client.updated_at)} | {language === "en" ? "Last login" : "Dernière connexion"} {client.last_login_at ? formatDateUi(client.last_login_at) : "–"}
          </small>
        </div>

        <div className="client-hero-main">
          <div className="client-photo-shell">
            {client.photo_url ? (
              <img
                className="client-photo"
                src={client.photo_url}
                alt={localizedClientPhotoAlt(fullName, language)}
              />
            ) : (
              <div className="client-avatar" aria-hidden="true">
                {initials(client)}
              </div>
            )}
            <div className="client-photo-caption">{t("admin.client_detail.photo")}</div>
          </div>
          <div className="client-hero-identity">
            <h2>{fullNameLabel}</h2>
            <div className="client-hero-meta" aria-label={t("admin.client_detail.client_information_aria")}>
              {heroMeta.map((item) => (
                <span key={item} className="client-hero-meta-chip">
                  {item}
                </span>
              ))}
            </div>
          </div>
        </div>

        <ClientTabNavigation
          ariaLabel={language === "en" ? "Client profile navigation" : "Navigation de la fiche client"}
          clientId={client.id}
          currentTab={currentTab}
          tabs={tabs}
        />
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {pageLevelErrorMessage ? <section className="flash-err">{pageLevelErrorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">{t("admin.client_detail.backend_error", { message: errors.join(" | ") })}</section> : null}

      {currentTab === "fiche" ? (
        <section className="grid cols-2 client-sheet-grid">
          <article className="card client-summary-card">
            <h3>{t("admin.client_detail.member_balance")}</h3>
            <p className="client-balance-main">{totalRemainingCredits}</p>
            <p className="muted">{t("admin.client_detail.remaining_credits_active_packs")}</p>
            {subscribedMakeupSummaries.length > 0 ? (
              <div className="client-makeup-pass-overview">
                {subscribedMakeupSummaries.map((summary) => (
                  <article key={summary.user_id}>
                    <div className="row spread">
                      <div>
                        <strong>{t("admin.client_detail.makeup_pass_subscribed")}</strong>
                        <small>{summary.display_name}</small>
                      </div>
                      <span className="status-pill status-ok">{t("admin.client_detail.active")}</span>
                    </div>
                    <p>
                      {t("admin.client_detail.makeup_pass_balance", {
                        remaining: summary.credits_remaining,
                        initial: summary.credits_initial,
                      })}
                    </p>
                    <small>
                      {t("admin.client_detail.makeup_pending_count", { count: summary.pending_makeups.length })}
                    </small>
                  </article>
                ))}
                <Link href={tabHref(client.id, "reservations")}>
                  {t("admin.client_detail.makeup_pass_view_details")}
                </Link>
              </div>
            ) : null}
            <div className="client-summary-stats">
              <span className="badge">{t("admin.client_detail.active_subscriptions_count", { count: activeMonthlySubscriptions })}</span>
              <span className="badge">{t("admin.client_detail.current_bookings_count", { count: bookedReservations.length })}</span>
            </div>
          </article>

          <article className="card">
            <div className="row spread">
              <h3>{t("admin.client_detail.add_product")}</h3>
              <Link
                className="client-action-icon payment-add-icon"
                href={ficheHref(client.id, { purchase_modal: "wizard", purchase_return_tab: "fiche" })}
                title={t("admin.client_detail.new_purchase_title")}
              >
                +
              </Link>
            </div>
            <p className="muted">{t("admin.client_detail.add_product_help")}</p>
            <p className="muted top-gap-sm">
              {t("admin.client_detail.add_product_flow")}
            </p>
            <p className="muted">
              {t("admin.client_detail.add_product_rules")}
            </p>
          </article>

          <article className="card span-2 client-regular-schedules">
            <div className="row spread">
              <div>
                <h3>{t("admin.client_detail.regular_schedules_title")}</h3>
                <p className="muted">{t("admin.client_detail.regular_schedules_help")}</p>
              </div>
              <Link className="mode-link" href={tabHref(client.id, "reservations")}>
                {t("admin.client_detail.regular_schedules_details")}
              </Link>
            </div>
            {regularSchedules.length === 0 ? (
              <p className="muted top-gap-sm">{t("admin.client_detail.regular_schedules_empty")}</p>
            ) : (
              <div className="client-regular-schedule-list top-gap-sm">
                {regularSchedules.map((schedule) => {
                  const start = new Date(schedule.startAt);
                  const end = new Date(schedule.endAt);
                  const weekday = start.toLocaleDateString(localeForUiLanguage(language), {
                    weekday: "long",
                    timeZone: "Europe/Paris",
                  });
                  const startTime = start.toLocaleTimeString(localeForUiLanguage(language), {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "Europe/Paris",
                  });
                  const endTime = end.toLocaleTimeString(localeForUiLanguage(language), {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "Europe/Paris",
                  });
                  return (
                    <article key={schedule.key} className="client-regular-schedule-row">
                      <div className="client-regular-schedule-activity">
                        <strong>{schedule.courseTypeName}</strong>
                        <div className="row gap-sm">
                          <span className={`status-pill ${schedule.waitlisted ? "status-warn" : "status-ok"}`}>
                            {t(schedule.waitlisted ? "admin.client_detail.regular_schedule_waitlisted" : "admin.client_detail.regular_schedule_active")}
                          </span>
                          <span className="badge">
                            {t("admin.client_detail.regular_schedule_occurrences", { count: schedule.occurrenceCount })}
                          </span>
                        </div>
                      </div>
                      <div>
                        <small>{t("admin.client_detail.regular_schedule_slot")}</small>
                        <strong>{weekday} · {startTime}–{endTime}</strong>
                      </div>
                      <div>
                        <small>{t("admin.client_detail.regular_schedule_location")}</small>
                        <strong>{schedule.locationName}</strong>
                      </div>
                      <div>
                        <small>{t("admin.client_detail.regular_schedule_professor")}</small>
                        <strong>{schedule.professorName || t("admin.client_detail.regular_schedule_unassigned")}</strong>
                      </div>
                      <div>
                        <small>{t("admin.client_detail.regular_schedule_period")}</small>
                        <strong>{formatDateOnlyNumeric(schedule.firstDate, language)}–{formatDateOnlyNumeric(schedule.lastDate, language)}</strong>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </article>

          <article className="card span-2">
            <div className="row spread">
              <h3>{t("admin.client_detail.current_products")}</h3>
              <div className="row">
                <span className="badge">{t("admin.client_detail.active_count", { count: activeSubscriptions.length })}</span>
                <span className="badge">{t("admin.client_detail.ending_period_count", { count: endingSubscriptions.length })}</span>
                {pendingSubscriptions.length > 0 ? (
                  <span className="badge">
                    {clientStatusLabel("PENDING", language)}: {pendingSubscriptions.length}
                  </span>
                ) : null}
              </div>
            </div>

            {visibleCurrentSubscriptions.length === 0 ? (
              <p className="muted top-gap-sm">{t("admin.client_detail.no_current_product")}</p>
            ) : (
              <div className="subscription-stack top-gap-sm">
                {visibleCurrentSubscriptions.map((sub) => {
                  const statusPill = localizedSubscriptionStatusPill(sub, language);
                  const pendingCancellation = isPendingSubscriptionCancellation(sub);
                  const hasEditablePause = Boolean(
                    sub.suspension_ends_at && Date.parse(sub.suspension_ends_at) > Date.now(),
                  );
                  return (
                    <article key={sub.id} className="subscription-detail-card">
                    <header className="row spread subscription-head">
                      <div className="stack-sm">
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? sub.cancellation_request_status === "PENDING"
                              ? t("admin.client_detail.cancellation_request_pending")
                              : pendingCancellation
                              ? t("admin.client_detail.subscription_ending_period")
                              : t("admin.client_detail.subscription_current")
                            : sub.plan.kind === "PACK"
                              ? t("admin.client_detail.active_pack")
                              : t("admin.client_detail.active_forfait")}
                        </small>
                        <h4>{sub.plan.name}</h4>
                        <span className="muted">
                          {t("admin.client_detail.contract_number")}: {shortContractRef(sub.id)} ({sub.id})
                        </span>
                      </div>
                      <div className="row subscription-head-actions">
                        <span className={`status-pill ${statusPill.toneClass}`}>{statusPill.label}</span>
                        {sub.plan.kind === "SUBSCRIPTION" ? (
                          <>
                            <Link
                              className="client-action-icon"
                              href={ficheHref(client.id, { subscription_modal: "billing", subscription_id: sub.id })}
                              title={t("admin.client_detail.configure_sepa_refs")}
                            >
                              ✎
                            </Link>
                            {sub.status !== "CANCELLED" ? (
                              <>
                                <Link
                                  className="client-action-icon"
                                  href={ficheHref(client.id, { subscription_modal: "suspend", subscription_id: sub.id })}
                                  title={t(
                                    hasEditablePause
                                      ? "admin.client_detail.edit_subscription_pause"
                                      : "admin.client_detail.suspend_subscription",
                                  )}
                                >
                                  ⏸
                                </Link>
                                {sub.cancellation_request_status !== "PENDING" ? (
                                  <>
                                    <Link
                                      className="client-action-icon danger"
                                      href={ficheHref(client.id, { subscription_modal: "cancel", subscription_id: sub.id })}
                                      title={t("admin.client_detail.cancel_end_of_period")}
                                    >
                                      ✕
                                    </Link>
                                    <Link
                                      className="client-action-icon danger"
                                      href={ficheHref(client.id, { subscription_modal: "cancel_now", subscription_id: sub.id })}
                                      title={t("admin.client_detail.cancel_now")}
                                    >
                                      ⚠
                                    </Link>
                                  </>
                                ) : null}
                              </>
                            ) : null}
                          </>
                        ) : sub.status !== "CANCELLED" ? (
                          <>
                            {sub.plan.kind === "FORFAIT" ? (
                              <Link
                                className="client-action-icon"
                                href={ficheHref(client.id, { subscription_modal: "billing", subscription_id: sub.id })}
                                title={t("admin.client_detail.edit_forfait_payment_method")}
                              >
                                $
                              </Link>
                            ) : null}
                            {sub.plan.kind === "FORFAIT" ? (
                              <Link
                                className="client-action-icon"
                                href={ficheHref(client.id, { subscription_modal: "forfait_pricing", subscription_id: sub.id })}
                                title={t("admin.client_detail.edit_forfait_pricing")}
                              >
                                €
                              </Link>
                            ) : null}
                            <Link
                              className="client-action-icon"
                              href={ficheHref(client.id, { subscription_modal: "expiry", subscription_id: sub.id })}
                              title={t("admin.client_detail.edit_expiry_date")}
                            >
                              ✎
                            </Link>
                            <Link
                              className="client-action-icon danger"
                              href={ficheHref(client.id, { subscription_modal: "cancel_now", subscription_id: sub.id })}
                              title={t("admin.client_detail.cancel_pack_forfait")}
                            >
                              ✕
                            </Link>
                          </>
                        ) : null}
                      </div>
                    </header>

                    <section className="subscription-meta-grid">
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_plan")}</p>
                        <strong>{sub.plan.name}</strong>
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? t("admin.client_detail.tacit_renewal")
                            : sub.plan.kind === "PACK"
                              ? t("admin.client_detail.credit_pack")
                              : t("admin.client_detail.forfait_billed_actual")}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_price_ttc")}</p>
                        <strong>
                          {sub.estimated_total_incl_vat
                            ? `${formatMoneyUi(sub.estimated_total_incl_vat, sub.estimated_currency || client.preferred_currency)} TTC`
                            : t("admin.client_detail.not_available")}
                        </strong>
                        <small className="muted">
                          {t("admin.client_detail.vat_included", { rate: sub.estimated_vat_rate ?? "-" })}
                          {sub.plan.kind === "FORFAIT"
                            ? ` | ${t("admin.client_detail.configured_activities")}: ${
                                sub.forfait_activity_pricing.filter(
                                  (row) =>
                                    Number.parseFloat(row.loyalty_discount_per_hour_ttc || "0") > 0 ||
                                    Number.parseFloat(row.family_discount_per_hour_ttc || "0") > 0 ||
                                    Number.parseFloat(row.short_commitment_supplement_per_hour_ttc || "0") > 0 ||
                                    Number.parseFloat(row.second_course_weekly_discount_per_hour_ttc || "0") > 0,
                                ).length
                              }/${sub.forfait_activity_pricing.length}`
                            : ""}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_billing_method")}</p>
                        <strong>{localizedBillingMethodLabel(sub.billing_method_code, language)}</strong>
                        <small className="muted">
                          {t("admin.client_detail.auto_renewal")}: {sub.auto_renew ? t("admin.client_detail.yes") : t("admin.client_detail.no")} | {t("admin.client_detail.last_status")}: {sub.last_payment_status ?? "n/a"}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_credits")}</p>
                        <strong>
                          {sub.credits_remaining ?? "-"}/{sub.credits_initial ?? "-"}
                        </strong>
                        <small className="muted">{t("admin.client_detail.remaining_initial")}</small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_psp_refs")}</p>
                        <strong>{sub.payment_provider_customer_ref ?? "-"}</strong>
                        <small className="muted">
                          {t("admin.client_detail.mandate")}: {sub.payment_provider_mandate_ref ?? "-"} | {t("admin.client_detail.subscription_ref")}:{" "}
                          {sub.payment_provider_subscription_ref ?? "-"}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">{t("admin.client_detail.field_period")}</p>
                        <strong>
                          {t("admin.client_detail.start")}: {formatDateUi(sub.started_at)}
                          {sub.ends_at ? ` | ${t("admin.client_detail.end")}: ${formatDateUi(sub.ends_at)}` : ""}
                        </strong>
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? `${t("admin.client_detail.next_payment")}: ${sub.next_payment_at ? formatDateUi(sub.next_payment_at) : t("admin.client_detail.not_scheduled")}`
                            : t("admin.client_detail.no_recurring_debit")}
                        </small>
                      </article>
                    </section>

                    {sub.suspension_starts_at && sub.suspension_ends_at && Date.parse(sub.suspension_ends_at) > Date.now() ? (
                      <p className="muted top-gap-sm">
                        {t("admin.client_detail.suspension_active")} {t("admin.client_detail.start").toLowerCase()} {formatDateUi(sub.suspension_start_date || sub.suspension_starts_at)} {t("admin.client_detail.end").toLowerCase()} {formatDateUi(sub.suspension_end_date || sub.suspension_ends_at)} {sub.suspension_end_date ? t("admin.client_detail.inclusive_suffix") : ""}.
                      </p>
                    ) : null}
                    {sub.cancellation_requested_at ? (
                      <p className="muted">
                        {t("admin.client_detail.cancellation_requested")} {formatDateUi(sub.cancellation_requested_at)} | {t("admin.client_detail.effective_end")}:{" "}
                        {sub.cancellation_effective_at ? formatDateUi(sub.cancellation_effective_at) : t("admin.client_detail.to_define")}.
                      </p>
                    ) : null}
                    {sub.cancellation_request_status === "PENDING" ? (
                      <section className="flash-warn top-gap-sm">
                        <strong>{t("admin.client_detail.cancellation_request_pending")}</strong>
                        {sub.cancellation_request_note ? (
                          <p>{t("admin.client_detail.cancellation_request_note")}: {sub.cancellation_request_note}</p>
                        ) : null}
                        <div className="row top-gap-sm">
                          <form action={decideAdminClientSubscriptionCancellationAction}>
                            <input type="hidden" name="client_id" value={client.id} />
                            <input type="hidden" name="subscription_id" value={sub.id} />
                            <input type="hidden" name="decision" value="APPROVE" />
                            <button type="submit">{t("admin.client_detail.approve_cancellation_request")}</button>
                          </form>
                          <form action={decideAdminClientSubscriptionCancellationAction}>
                            <input type="hidden" name="client_id" value={client.id} />
                            <input type="hidden" name="subscription_id" value={sub.id} />
                            <input type="hidden" name="decision" value="REJECT" />
                            <button type="submit" className="ghost">{t("admin.client_detail.reject_cancellation_request")}</button>
                          </form>
                        </div>
                      </section>
                    ) : null}

                    {sub.plan.kind === "SUBSCRIPTION" ? (
                      <p className="muted">
                        {t("admin.client_detail.quick_actions_subscription")}
                      </p>
                    ) : sub.plan.kind === "FORFAIT" ? (
                      <p className="muted">
                        {t("admin.client_detail.quick_actions_forfait")}
                      </p>
                    ) : (
                      <p className="muted">{t("admin.client_detail.quick_actions_pack")}</p>
                    )}
                    </article>
                  );
                })}
              </div>
            )}
          </article>

          <article className="card span-2">
            <h3>{t("admin.client_detail.finished_products")}</h3>
            {archivedSubscriptions.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_finished_product")}</p>
            ) : (
              <div className="list top-gap-sm">
                {archivedSubscriptions.map((sub) => (
                  <article key={sub.id} className="item row spread">
                    <div className="stack-sm">
                      <strong>{sub.plan.name}</strong>
                      <small className="muted">
                        {sub.ends_at
                          ? t("admin.client_detail.contract_start_end", {
                              contract: shortContractRef(sub.id),
                              start: formatDateUi(sub.started_at),
                              end: formatDateUi(sub.ends_at),
                            })
                          : `${t("admin.client_detail.contract_number")} ${shortContractRef(sub.id)} | ${t("admin.client_detail.start")}: ${formatDateUi(sub.started_at)}`}
                      </small>
                    </div>
                    <span className={`status-pill ${statusClass(sub.status)}`}>{clientStatusLabel(sub.status, language)}</span>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="card">
            <h3>{t("admin.client_detail.manual_credits")}</h3>
            {manualCredits.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_manual_credit_types")}</p>
            ) : (
              <div className="list top-gap-sm">
                {manualCredits.map((row) => (
                  <article key={row.credit_type_id} className="item row spread credit-row">
                    <strong>{row.credit_type_name ?? row.credit_type_code ?? row.credit_type_id}</strong>
                    <div className="row">
                      <span className="credit-count-badge">{row.credits_count}</span>
                      <Link
                        className="client-action-icon"
                        href={ficheHref(client.id, { edit_credit: "1", credit_type_id: row.credit_type_id })}
                        title={t("admin.client_detail.edit_credit_count")}
                      >
                        ✎
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="card span-2">
            <h3>{t("admin.client_detail.notes")}</h3>
            {notes.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_notes")}</p>
            ) : (
              <div className="table-wrap top-gap-sm">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("admin.client_detail.col_date")}</th>
                      <th>{t("admin.client_detail.col_type")}</th>
                      <th>{t("admin.client_detail.col_author")}</th>
                      <th>{t("admin.client_detail.col_message")}</th>
                      <th>{t("admin.client_detail.col_view")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notes.map((row) => (
                      <tr key={row.id}>
                        <td>{formatDateUi(row.created_at)}</td>
                        <td>{row.entry_type}</td>
                        <td>{row.author_display_name}</td>
                        <td title={rangeInvoiceNoteSummary(row, language) || row.message}>
                          {rangeInvoiceNoteSummary(row, language) || truncatePreview(row.message, 100)}
                        </td>
                        <td>
                          <Link
                            className="client-action-icon"
                            href={ficheHref(client.id, { note_modal: "view", note_id: row.id })}
                            title={t("admin.client_detail.view_message_full")}
                          >
                            {t("admin.client_detail.view_short")}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <form action={createAdminClientNoteAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <label>
                {t("admin.client_detail.add_note")}
                <textarea name="message" rows={4} maxLength={4000} required />
              </label>
              <div className="row">
                <button type="submit">{t("admin.client_detail.save")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {openNoteViewModal && selectedNoteForView ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("admin.client_detail.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.note_detail")}</h3>
            <p className="muted">
              {formatDateUi(selectedNoteForView.created_at)} | {selectedNoteForView.entry_type} | {selectedNoteForView.author_display_name}
            </p>
            {selectedNoteInvoiceDetails ? (
              <div className="item top-gap-sm">
                <strong>Facture generee</strong>
                <dl className="invoice-note-details">
                  {selectedNoteInvoiceDetails.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="muted">Le contenu exact des emails envoyes est disponible dans l'onglet Messages.</p>
              </div>
            ) : (
              <textarea readOnly rows={12} value={selectedNoteForView.message} />
            )}
            <div className="row modal-actions-end top-gap-sm">
              <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                {t("admin.client_detail.close")}
              </Link>
            </div>
          </article>
        </section>
      ) : null}

      {(currentTab === "fiche" || currentTab === "paiements") && purchaseModalAction === "wizard" ? (
        <section className="modal-overlay">
          <article className="modal-panel purchase-wizard-modal">
            <Link className="modal-close-x" href={tabHref(client.id, purchaseReturnTab)} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="purchase-wizard-header">
              <h3 className="modal-title">{t("admin.client_detail.purchase_modal_title")}</h3>
              <div className="purchase-wizard-stepper" aria-label={t("admin.client_detail.purchase_stepper_aria")}>
                <span className="active">{t("admin.client_detail.purchase_step_offer")}</span>
                <span>{t("admin.client_detail.purchase_step_payment")}</span>
              </div>
              <p className="muted">{t("admin.client_detail.purchase_intro")}</p>
            </header>
            <form action={adminOpenClientPurchaseTermsAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value={purchaseReturnTab} />
              <input type="hidden" name="purchase_type" value={normalizedPurchaseType} />
              <section className="purchase-type-toggle" aria-label={t("admin.client_detail.purchase_type_aria")}>
                <Link
                  href={purchaseTypeFormulaHref}
                  className={`purchase-type-chip${normalizedPurchaseType === "FORMULA" ? " active" : ""}`}
                >
                  {t("admin.client_detail.purchase_type.formula")}
                </Link>
                <Link
                  href={purchaseTypeProductHref}
                  className={`purchase-type-chip${normalizedPurchaseType === "PRODUCT" ? " active" : ""}`}
                >
                  {t("admin.client_detail.purchase_type.product_plural")}
                </Link>
              </section>
              <label>
                {t("admin.client_detail.purchase_offer_label")}
                <select name="plan_id" required defaultValue={purchasePlanId || ""}>
                  <option value="" disabled>
                    {normalizedPurchaseType === "PRODUCT"
                      ? t("admin.client_detail.purchase_offer_placeholder_product")
                      : t("admin.client_detail.purchase_offer_placeholder_formula")}
                  </option>
                  {purchaseOfferOptions.map((offer) => (
                    <option key={offer.id} value={offer.id}>
                      {offer.label}
                    </option>
                  ))}
                </select>
                {selectedPurchaseOfferHelper ? (
                  <small className="muted">{selectedPurchaseOfferHelper}</small>
                ) : (
                  <small className="muted">{t("admin.client_detail.purchase_offer_empty")}</small>
                )}
              </label>
              <label>
                {t("admin.client_detail.discounted_price_label")}
                <input
                  type="text"
                  name="discounted_total_incl_vat"
                  placeholder={t("admin.client_detail.discounted_price_placeholder")}
                  defaultValue={hasDiscountedTotalForPurchase ? discountedTotalForPurchase.toFixed(2) : ""}
                />
                <small className="muted">{t("admin.client_detail.discounted_price_help")}</small>
              </label>
              {normalizedPurchaseType === "FORMULA" ? (
                <label>
                  {t("admin.client_detail.purchase_start_date")}
                  <input type="date" name="start_date" defaultValue={purchaseStartDateInputValue} />
                </label>
              ) : (
                <input type="hidden" name="start_date" value="" />
              )}
              <label>
                {t("admin.client_detail.purchase_payment_method")}
                <select name="payment_method_code" required defaultValue={purchasePaymentMethod || ""}>
                  <option value="" disabled>
                    {t("admin.client_detail.purchase_payment_method_placeholder")}
                  </option>
                  {purchasePaymentMethodOptions.map((method) => (
                    <option key={method.code} value={method.code}>
                      {method.label}
                    </option>
                  ))}
                </select>
                {purchasePaymentMethod === "CARD_ONLINE" ? (
                  <small className="muted">{t("admin.client_detail.purchase_payment_link_help")}</small>
                ) : (
                  <small className="muted">{t("admin.client_detail.purchase_payment_no_link_help")}</small>
                )}
              </label>
              <div className="row modal-actions-end purchase-wizard-footer">
                <Link className="reset-link" href={tabHref(client.id, purchaseReturnTab)}>
                  {t("common.cancel")}
                </Link>
                <button type="submit" disabled={purchaseOfferOptions.length === 0}>
                  {t("common.continue")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "fiche" || currentTab === "paiements") && purchaseModalAction === "terms" && selectedPurchaseOfferForTerms ? (
        <section className="modal-overlay">
          <article className="modal-panel purchase-wizard-modal purchase-wizard-terms-modal">
            <Link
              className="modal-close-x"
              href={purchaseWizardReturnHref}
              aria-label={t("common.close")}
            >
              ×
            </Link>
            <header className="purchase-wizard-header">
              <h3 className="modal-title">{t("admin.client_detail.purchase_modal_title")}</h3>
              <div className="purchase-wizard-stepper" aria-label={t("admin.client_detail.purchase_stepper_aria")}>
                <span>{t("admin.client_detail.purchase_step_offer")}</span>
                <span className="active">{t("admin.client_detail.purchase_step_payment")}</span>
              </div>
            </header>
            <h4 className="purchase-wizard-offer-title">{selectedPurchaseOfferForTerms.name}</h4>
            <p className="muted">
              {t("admin.client_detail.purchase_terms_summary", {
                method: billingMethodLabel(purchasePaymentMethod, language),
                type: purchaseTypeLabel,
              })}
            </p>
            {normalizedPurchaseType === "FORMULA" && selectedPlanForPurchase ? (
              <p className="muted">
                {selectedPlanForPurchase.kind === "FORFAIT"
                  ? t("admin.client_detail.purchase_forfait_period", {
                      start: selectedPlanForPurchase.forfait_start_date
                        ? formatDateInputLabel(selectedPlanForPurchase.forfait_start_date, language)
                        : "-",
                      end: selectedPlanForPurchase.forfait_end_date
                        ? formatDateInputLabel(selectedPlanForPurchase.forfait_end_date, language)
                        : "-",
                    })
                  : t("admin.client_detail.purchase_requested_start", {
                      date: formatDateInputLabel(purchaseStartDateInputValue, language),
                    })}
              </p>
            ) : null}
            <article className="card modal-card purchase-summary-card">
              <h4>{t("admin.client_detail.purchase_summary_title")}</h4>
              <p className="muted">
                {t("admin.client_detail.purchase_summary_offer", {
                  offer: selectedPurchaseOfferForTerms.name,
                  kind:
                    normalizedPurchaseType === "PRODUCT"
                      ? t("admin.client_detail.purchase_type.product")
                      : planKindLabel(selectedPlanForPurchase?.kind ?? "SUBSCRIPTION", language),
                })}
              </p>
              {selectedPlanBaseTotal ? (
                <p className="muted">
                  {t("admin.client_detail.purchase_catalog_price", {
                    amount: formatMoney(selectedPlanBaseTotal, selectedPlanCurrency, language),
                  })}
                </p>
              ) : null}
              {hasDiscountedTotalForPurchase ? (
                <p className="muted">
                  {t("admin.client_detail.purchase_discounted_price", {
                    amount: formatMoney(String(discountedTotalForPurchase), selectedPlanCurrency, language),
                  })}
                </p>
              ) : (
                <p className="muted">{t("admin.client_detail.purchase_no_discount")}</p>
              )}
              {!hasDiscountedTotalForPurchase && normalizedPurchaseType === "FORMULA"
                ? selectedPlanForPurchase?.first_purchase_breakdown
                    .filter((line) => line.code !== "FORMULA")
                    .map((line) => (
                      <p className="muted" key={line.code}>
                        {line.label}: {formatMoney(line.amount_ttc, selectedPlanCurrency, language)}
                      </p>
                    ))
                : null}
              <p className="purchase-total-line">
                {t("admin.client_detail.purchase_total_due", {
                  amount: hasDiscountedTotalForPurchase
                    ? formatMoney(String(discountedTotalForPurchase), selectedPlanCurrency, language)
                    : selectedPlanPurchaseTotal
                      ? formatMoney(selectedPlanPurchaseTotal, selectedPlanCurrency, language)
                      : formatMoney("0", selectedPlanCurrency, language),
                })}
              </p>
            </article>

            <form action={adminFinalizeClientPurchaseAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="plan_id" value={selectedPurchaseOfferForTerms.id} />
              <input
                type="hidden"
                name="plan_kind"
                value={normalizedPurchaseType === "FORMULA" ? selectedPlanForPurchase?.kind ?? "SUBSCRIPTION" : "PRODUCT"}
              />
              <input type="hidden" name="plan_name" value={selectedPurchaseOfferForTerms.name} />
              <input type="hidden" name="purchase_type" value={normalizedPurchaseType} />
              <input type="hidden" name="payment_method_code" value={purchasePaymentMethod} />
              <input type="hidden" name="return_tab" value={purchaseReturnTab} />
              <input type="hidden" name="start_date" value={normalizedPurchaseType === "FORMULA" ? purchaseStartDateInputValue : ""} />
              {hasDiscountedTotalForPurchase ? (
                <input type="hidden" name="discounted_total_incl_vat" value={discountedTotalForPurchase.toFixed(2)} />
              ) : null}

              {canSendPaymentLink ? (
                <label>
                  {t("admin.client_detail.purchase_signature_channel")}
                  <select name="signature_channel" defaultValue="EMAIL">
                    <option value="EMAIL">{t("admin.client_detail.purchase_signature_email")}</option>
                    <option value="SMS">{t("admin.client_detail.purchase_signature_sms")}</option>
                  </select>
                </label>
              ) : (
                <>
                  <input type="hidden" name="signature_channel" value="NONE" />
                  <p className="muted">
                    {normalizedPurchaseType === "PRODUCT"
                      ? t("admin.client_detail.purchase_product_saved_no_link")
                      : t("admin.client_detail.purchase_non_card_saved_no_link")}
                  </p>
                </>
              )}

              {purchasePaymentMethod === "GIFT_CARD" ? (
                <article className="card modal-card purchase-summary-card">
                  <h4>{t("admin.client_detail.gift_card_details_title")}</h4>
                  <p className="muted">{t("admin.client_detail.gift_card_details_help")}</p>
                  <label>
                    {t("admin.client_detail.gift_purchaser_name")}
                    <input name="gift_purchaser_name" required maxLength={160} />
                  </label>
                  <label>
                    {t("admin.client_detail.gift_reference")}
                    <input name="gift_reference" maxLength={160} placeholder={t("admin.client_detail.gift_reference_placeholder")} />
                  </label>
                </article>
              ) : null}

              <div className="row modal-actions-end">
                <Link
                  className="reset-link"
                  href={purchaseWizardReturnHref}
                >
                  {t("common.previous")}
                </Link>
                <button type="submit">
                  {canSendPaymentLink ? t("admin.client_detail.purchase_send_link") : t("admin.client_detail.purchase_validate")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "billing" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">
              {selectedSubscriptionForModal.plan.kind === "FORFAIT"
                ? t("admin.client_detail.subscription_billing_title_forfait")
                : t("admin.client_detail.subscription_billing_title_subscription")}
            </h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={setupAdminClientSubscriptionBillingAction} className="grid cols-2 top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                {t("admin.client_detail.field_billing_method")}
                <select
                  name="billing_method_code"
                  defaultValue={
                    selectedSubscriptionForModal.billing_method_code ??
                    (selectedSubscriptionForModal.plan.kind === "FORFAIT" ? "FACTURATION_AUTO" : "CARD_ONLINE")
                  }
                >
                  {enabledPaymentMethods.length > 0 ? (
                    enabledPaymentMethods.map((method) => (
                      <option key={method.code} value={method.code}>
                        {paymentMethodOptionLabel(method, language)}
                      </option>
                    ))
                  ) : (
                    DEFAULT_PAYMENT_METHOD_OPTIONS.map((method) => (
                      <option key={method.code} value={method.code}>
                        {paymentMethodOptionLabel(method, language)}
                      </option>
                    ))
                  )}
                </select>
              </label>
              <label>
                {t("admin.client_detail.psp_subscription_ref")}
                <input
                  type="text"
                  name="payment_provider_subscription_ref"
                  defaultValue={selectedSubscriptionForModal.payment_provider_subscription_ref ?? ""}
                />
              </label>
              <label>
                {t("admin.client_detail.psp_customer_ref")}
                <input
                  type="text"
                  name="payment_provider_customer_ref"
                  defaultValue={selectedSubscriptionForModal.payment_provider_customer_ref ?? ""}
                />
              </label>
              <label>
                {t("admin.client_detail.psp_mandate_ref")}
                <input type="text" name="payment_provider_mandate_ref" defaultValue={selectedSubscriptionForModal.payment_provider_mandate_ref ?? ""} />
              </label>
              <div className="row span-2 modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">
                  {selectedSubscriptionForModal.plan.kind === "FORFAIT"
                    ? t("admin.client_detail.subscription_billing_save_forfait")
                    : t("common.save")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "expiry" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">
              {selectedSubscriptionForModal.plan.kind === "PACK"
                ? t("admin.client_detail.expiry_title_pack")
                : t("admin.client_detail.expiry_title_forfait")}
            </h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={updateAdminClientSubscriptionExpiryAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                {t("admin.client_detail.expiry_date_label")}
                <input
                  type="date"
                  name="ends_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.ends_at, todayInputValue)}
                  required
                />
              </label>
              <p className="muted">{t("admin.client_detail.expiry_help")}</p>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("common.save")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" &&
      selectedSubscriptionForModal &&
      subscriptionModalAction === "forfait_pricing" &&
      selectedSubscriptionForModal.plan.kind === "FORFAIT" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.forfait_pricing_title")}</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <p className="muted">{t("admin.client_detail.forfait_pricing_optional_help")}</p>
            <form action={updateAdminClientForfaitPricingAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              {selectedSubscriptionForModal.forfait_activity_pricing.length === 0 ? (
                <p className="muted">{t("admin.client_detail.forfait_pricing_empty")}</p>
              ) : (
                selectedSubscriptionForModal.forfait_activity_pricing.map((row) => (
                  <article key={row.course_type_id} className="card modal-card">
                    <input type="hidden" name="forfait_activity_row_key" value={row.course_type_id} />
                    <input type="hidden" name={`forfait_course_type_id_${row.course_type_id}`} value={row.course_type_id} />
                    <h4>{row.course_type_name}</h4>
                    <p className="muted">
                      {t("admin.client_detail.forfait_pricing_rate_summary", {
                        base: row.base_hourly_rate_ttc
                          ? `${formatMoney(
                              row.base_hourly_rate_ttc,
                              selectedSubscriptionForModal.estimated_currency || client.preferred_currency,
                              language,
                            )}/h`
                          : t("admin.client_detail.not_available"),
                        effective: row.effective_hourly_rate_ttc
                          ? `${formatMoney(
                              row.effective_hourly_rate_ttc,
                              selectedSubscriptionForModal.estimated_currency || client.preferred_currency,
                              language,
                            )}/h`
                          : t("admin.client_detail.not_available"),
                      })}
                    </p>
                    <div className="grid cols-4 config-form-grid">
                      <label>
                        {t("admin.client_detail.forfait_loyalty_discount")}
                        <input
                          type="text"
                          name={`forfait_loyalty_discount_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.loyalty_discount_per_hour_ttc ?? "0"}
                        />
                      </label>
                      <label>
                        {t("admin.client_detail.forfait_family_discount")}
                        <input
                          type="text"
                          name={`forfait_family_discount_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.family_discount_per_hour_ttc ?? "0"}
                        />
                      </label>
                      <label>
                        {t("admin.client_detail.forfait_short_commitment_supplement")}
                        <input
                          type="text"
                          name={`forfait_short_commitment_supplement_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.short_commitment_supplement_per_hour_ttc ?? "0"}
                        />
                      </label>
                      <label>
                        {t("admin.client_detail.forfait_second_course_discount")}
                        <input
                          type="text"
                          name={`forfait_second_course_weekly_discount_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.second_course_weekly_discount_per_hour_ttc ?? "0"}
                        />
                      </label>
                    </div>
                  </article>
                ))
              )}
              <p className="muted">{t("admin.client_detail.forfait_pricing_scope_help")}</p>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("common.save")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "suspend" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">
              {t(
                selectedSubscriptionHasEditablePause
                  ? "admin.client_detail.edit_subscription_pause"
                  : "admin.client_detail.suspend_subscription_title",
              )}
            </h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={suspendAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                {t("admin.client_detail.suspension_start")}
                <input
                  type="date"
                  name="suspension_starts_at"
                  min={selectedSubscriptionHasEditablePause ? undefined : todayInputValue}
                  defaultValue={selectedSubscriptionForModal.suspension_start_date || formatDateForInput(selectedSubscriptionForModal.suspension_starts_at, todayInputValue)}
                  required
                />
              </label>
              <label>
                {t("admin.client_detail.suspension_end_inclusive")}
                <input
                  type="date"
                  name="suspension_ends_at"
                  min={selectedSubscriptionHasEditablePause ? undefined : todayInputValue}
                  defaultValue={selectedSubscriptionForModal.suspension_end_date || selectedSubscriptionForModal.suspension_start_date || formatDateForInput(selectedSubscriptionForModal.suspension_starts_at, todayInputValue)}
                  required
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit" className="ghost">
                  {t(
                    selectedSubscriptionHasEditablePause
                      ? "admin.client_detail.save_subscription_pause"
                      : "admin.client_detail.suspend_subscription",
                  )}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "cancel" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.cancel_end_of_period_title")}</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={cancelAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              {hasBlockingFutureBookingsForCancellation ? (
                <p className="muted">
                  <strong>{t("admin.client_detail.cancellation_impossible_title")}</strong>{" "}
                  {t("admin.client_detail.cancellation_blocked_help", {
                    count: blockingFutureBookingsForCancellation.length,
                  })}
                  {cancellationConflictPreview
                    ? ` ${t("admin.client_detail.examples_label")}: ${cancellationConflictPreview}.`
                    : ""}
                </p>
              ) : null}
              {cancelConflictAlert ? (
                <p className="muted">
                  <strong>{t("admin.client_detail.cancellation_refused_title")}</strong>{" "}
                  {t("admin.client_detail.cancellation_refused_help")}
                </p>
              ) : null}
              <label>
                {t("admin.client_detail.cancellation_date")}
                <input
                  type="date"
                  name="cancellation_requested_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.cancellation_requested_at, todayInputValue)}
                  required
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit" className="danger" disabled={hasBlockingFutureBookingsForCancellation}>
                  {t("admin.client_detail.confirm_cancellation")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "cancel_now" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">
              {selectedSubscriptionForModal.plan.kind === "PACK"
                ? t("admin.client_detail.cancel_now_title_pack")
                : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                  ? t("admin.client_detail.cancel_now_title_forfait")
                  : t("admin.client_detail.cancel_now_title_subscription")}
            </h3>
            <p className="muted">
              {selectedSubscriptionForModal.plan.kind === "PACK"
                ? t("admin.client_detail.cancel_now_help_pack", { name: selectedSubscriptionForModal.plan.name })
                : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                  ? t("admin.client_detail.cancel_now_help_forfait", { name: selectedSubscriptionForModal.plan.name })
                  : t("admin.client_detail.cancel_now_help_subscription", { name: selectedSubscriptionForModal.plan.name })}
            </p>
            <form action={cancelAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <input type="hidden" name="immediate_cancel" value="on" />
              {hasBlockingFutureBookingsForCancellation ? (
                <p className="muted">
                  <strong>{t("admin.client_detail.cancellation_impossible_title")}</strong>{" "}
                  {t("admin.client_detail.cancellation_blocked_help", {
                    count: blockingFutureBookingsForCancellation.length,
                  })}
                  {cancellationConflictPreview
                    ? ` ${t("admin.client_detail.examples_label")}: ${cancellationConflictPreview}.`
                    : ""}
                </p>
              ) : null}
              {cancelConflictAlert ? (
                <p className="muted">
                  <strong>{t("admin.client_detail.cancellation_refused_title")}</strong>{" "}
                  {t("admin.client_detail.cancellation_refused_help")}
                </p>
              ) : null}
              <label>
                {t("admin.client_detail.cancellation_request_date")}
                <input
                  type="date"
                  name="cancellation_requested_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.cancellation_requested_at, todayInputValue)}
                  required
                />
              </label>
              <label className="checkline">
                <input type="checkbox" name="confirm_immediate" required />
                {selectedSubscriptionForModal.plan.kind === "PACK"
                  ? t("admin.client_detail.confirm_immediate_pack")
                  : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                    ? t("admin.client_detail.confirm_immediate_forfait")
                    : t("admin.client_detail.confirm_immediate_subscription")}
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit" className="danger" disabled={hasBlockingFutureBookingsForCancellation}>
                  {selectedSubscriptionForModal.plan.kind === "PACK"
                    ? t("admin.client_detail.cancel_now_submit_pack")
                    : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                      ? t("admin.client_detail.cancel_now_submit_forfait")
                      : t("admin.client_detail.cancel_now_submit_subscription")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedCreditForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.manual_credit_edit_title")}</h3>
            <p className="muted">{selectedCreditForModal.credit_type_name ?? selectedCreditForModal.credit_type_code}</p>
            <form action={updateAdminClientManualCreditAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="credit_type_id" value={selectedCreditForModal.credit_type_id} />
              <label>
                {t("admin.client_detail.manual_credit_count")}
                <input type="number" name="credits_count" min={0} max={100000} defaultValue={selectedCreditForModal.credits_count} required />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("common.save")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "infos" ? (
        <section className="admin-page-grid">
          <section className="grid cols-2">
            <article className="card">
              <div className="row spread">
                <h3>{t("admin.client_detail.personal_info")}</h3>
                <Link className="mode-link" href={`/admin/clients/${client.id}?tab=infos&edit_infos=1`}>
                  {t("admin.client_detail.edit")}
                </Link>
              </div>
              <div className="list">
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.full_name")}</span>
                  <strong>{fullName || t("admin.client_detail.not_provided")}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.email")}</span>
                  <strong>{client.email}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.mobile_1_short")}</span>
                  <strong>{client.mobile_phone_1 ?? t("admin.client_detail.not_provided")}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.mobile_2_short")}</span>
                  <strong>{client.mobile_phone_2 ?? t("admin.client_detail.not_provided")}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.home_phone")}</span>
                  <strong>{client.home_phone ?? t("admin.client_detail.not_provided")}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.address")}</span>
                  <strong>
                    {client.address_line ?? t("admin.client_detail.not_provided_feminine")}, {client.postal_code ?? "-"} {client.city ?? "-"} ({client.address_country})
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.birth_date")}</span>
                  <strong>{formatDateOnlyUi(client.birth_date)}</strong>
                </article>
                <article className="item">
                  <span className="muted">{t("admin.client_detail.important_info_label")}</span>
                  <p>{client.important_info ?? t("admin.client_detail.no_specific_info")}</p>
                </article>
              </div>
            </article>

            <article className="card">
              <h3>{t("admin.client_detail.registration_links")}</h3>
              <div className="list">
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.member_type")}</span>
                  <strong>{clientKindText}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.status")}</span>
                  <span className={`status-pill ${statusClass(client.client_status)}`}>{clientStatusLabel(client.client_status, language)}</span>
                </article>
                <article className="item row spread">
                  <span className="muted">Site</span>
                  <strong>{studentSiteLabel(client.student_site)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.country_residence")}</span>
                  <strong>{labelFromOptions(COUNTRY_OPTIONS, client.residence_country)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.currency")}</span>
                  <strong>{labelFromOptions(CURRENCY_OPTIONS, client.preferred_currency)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.language")}</span>
                  <strong>{clientLanguageText}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.timezone")}</span>
                  <strong>{client.timezone}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.first_lesson_date")}</span>
                  <strong>{client.first_course_at ? formatDateUi(client.first_course_at) : t("admin.client_detail.no_booked_lesson")}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{language === "en" ? "Last login" : "Dernière connexion"}</span>
                  <strong>
                    {client.last_login_at
                      ? formatDateUi(client.last_login_at)
                      : (language === "en" ? "No login recorded" : "Aucune connexion enregistrée")}
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{language === "en" ? "Last activity" : "Dernière activité"}</span>
                  <strong>
                    {client.last_seen_at
                      ? `${formatDateUi(client.last_seen_at)} · ${(() => {
                        if (client.last_seen_channel === "NATIVE_APP") return language === "en" ? "Native iOS app" : "App iOS native";
                        if (client.last_seen_channel === "INSTALLED_WEB") return language === "en" ? "Installed website" : "Site installé";
                        if (client.last_seen_channel === "WEB_MOBILE") return language === "en" ? "Mobile website" : "Site web mobile";
                        if (client.last_seen_channel === "WEB_DESKTOP") return language === "en" ? "Desktop website" : "Site web ordinateur";
                        if (client.last_seen_channel === "MOBILE_APP") return language === "en" ? "Legacy app/PWA" : "Ancien classement app/site installé";
                        return language === "en" ? "Legacy website" : "Ancien classement site web";
                      })()}`
                      : (language === "en" ? "No activity recorded" : "Aucune activité enregistrée")}
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.created_on")}</span>
                  <strong>{formatDateUi(client.created_at)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.updated_on")}</span>
                  <strong>{formatDateUi(client.updated_at)}</strong>
                </article>
              </div>

              <form action={updateAdminClientGroupsAction} className="grid top-gap-sm">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="return_tab" value="infos" />
                <label>
                  {t("admin.client_detail.groups")}
                  <select
                    name="group_ids"
                    multiple
                    defaultValue={client.group_ids}
                    size={Math.min(8, Math.max(4, groups.length))}
                  >
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="muted">{t("admin.client_detail.multi_select_hint")}</p>
                <button type="submit" className="ghost">
                  {t("admin.client_detail.save_groups")}
                </button>
              </form>
            </article>
          </section>

          <section className="grid cols-2">
            <article className="card">
              <h3>{uiText(language, "admin.clients.communication_preferences")}</h3>
              {client.email_delivery_status.toLowerCase() === "suspended" ? (
                <p className="flash-err">
                  {t("admin.client_detail.email_suspended")} {client.email_suspended_at ? formatDateUi(client.email_suspended_at) : "-"}.
                </p>
              ) : null}
              {client.phone_delivery_status.toLowerCase() === "suspended" ? (
                <p className="flash-err">
                  {t("admin.client_detail.phone_suspended")} {client.phone_suspended_at ? formatDateUi(client.phone_suspended_at) : "-"}.
                </p>
              ) : null}
              <div className="list">
                <article className="item row spread">
                  <span>{uiText(language, "admin.clients.portal_contact_visible")}</span>
                  <span className={`status-pill ${client.portal_contact_visible ? "status-ok" : "status-off"}`}>
                    {booleanEnabledLabel(client.portal_contact_visible, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{uiText(language, "admin.clients.email_info_opt_in")}</span>
                  <span className={`status-pill ${client.email_opt_in ? "status-ok" : "status-off"}`}>
                    {optInLabel(client.email_opt_in, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{uiText(language, "admin.clients.sms_info_opt_in")}</span>
                  <span className={`status-pill ${client.sms_opt_in ? "status-ok" : "status-off"}`}>
                    {optInLabel(client.sms_opt_in, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{uiText(language, "admin.clients.email_reminders_opt_in")}</span>
                  <span className={`status-pill ${client.lesson_reminder_email_opt_in ? "status-ok" : "status-off"}`}>
                    {optInLabel(client.lesson_reminder_email_opt_in, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{uiText(language, "admin.clients.sms_reminders_opt_in")}</span>
                  <span className={`status-pill ${client.lesson_reminder_sms_opt_in ? "status-ok" : "status-off"}`}>
                    {optInLabel(client.lesson_reminder_sms_opt_in, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{t("admin.client_detail.email_delivery_status")}</span>
                  <span className={`status-pill ${client.email_delivery_status.toLowerCase() === "suspended" ? "status-cancelled" : "status-ok"}`}>
                    {deliveryStatusLabel(client.email_delivery_status, language)}
                  </span>
                </article>
                <article className="item row spread">
                  <span>{t("admin.client_detail.phone_delivery_status")}</span>
                  <span className={`status-pill ${client.phone_delivery_status.toLowerCase() === "suspended" ? "status-cancelled" : "status-ok"}`}>
                    {deliveryStatusLabel(client.phone_delivery_status, language)}
                  </span>
                </article>
              </div>
              <form action={reactivateAdminClientDeliveryAction} className="grid top-gap-sm">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="return_tab" value="infos" />
                <label className="row">
                  <input type="checkbox" name="reactivate_email" defaultChecked={client.email_delivery_status.toLowerCase() === "suspended"} />
                  <span>{t("admin.client_detail.reactivate_email")}</span>
                </label>
                <label className="row">
                  <input type="checkbox" name="reactivate_phone" defaultChecked={client.phone_delivery_status.toLowerCase() === "suspended"} />
                  <span>{t("admin.client_detail.reactivate_phone")}</span>
                </label>
                <div className="row top-gap-sm">
                  <button type="submit" className="ghost">{t("admin.client_detail.reactivate_contacts")}</button>
                  <Link className="ghost" href="/admin/notifications/incidents">
                    {t("admin.client_detail.incident_history")}
                  </Link>
                </div>
              </form>
            </article>

            <article className="card">
              <h3>{t("admin.client_detail.profile_operations")}</h3>
              <div className="grid">
                <SendClientAccessLink clientId={client.id} email={client.email} language={language} />
                <p className="muted">
                  {t("admin.client_detail.password_help")}
                </p>
              </div>

              <article className="item top-gap-sm">
                <h4>{t("admin.client_detail.private_note_internal")}</h4>
                <p className="muted">{t("admin.client_detail.private_note_hidden")}</p>
                <p>{client.private_note ?? t("admin.client_detail.no_private_note")}</p>
              </article>
              {client.client_kind === "ADULT" ? (
                <article className="item top-gap-sm">
                  <h4>{t("admin.clients.home_access_instructions")}</h4>
                  <p className="muted">{t("admin.clients.home_access_instructions_help")}</p>
                  <p>{client.home_access_instructions ?? t("admin.clients.no_home_access_instructions")}</p>
                </article>
              ) : null}
            </article>
          </section>

          {openEditInfosModal ? (
            <section className="modal-overlay">
              <article className="modal-panel client-info-modal">
                <Link className="modal-close-x" href={tabHref(client.id, "infos")} aria-label={t("admin.client_detail.close")}>
                  ×
                </Link>
                <header className="activity-modal-header">
                  <h2 className="modal-title">{t("admin.client_detail.edit_client_record")}</h2>
                  <p className="muted">{t("admin.client_detail.required_fields_help")}</p>
                </header>

                <section className="card modal-card">
                  <form action={updateAdminClientAction} className="grid cols-2">
                    <input type="hidden" name="client_id" value={client.id} />
                    <input type="hidden" name="return_tab" value="infos" />

                    <label>
                      {uiText(language, "admin.clients.email_optional")}
                      <input type="email" name="email" defaultValue={client.email} />
                    </label>

                    <label>
                      {t("admin.client_detail.first_name")} <span className="required-star">*</span>
                      <input type="text" name="first_name" defaultValue={client.first_name ?? ""} maxLength={100} required />
                    </label>

                    <label>
                      {t("admin.client_detail.last_name")} <span className="required-star">*</span>
                      <input type="text" name="last_name" defaultValue={client.last_name ?? ""} maxLength={100} required />
                    </label>

                    <label>
                      {t("admin.client_detail.mobile_1_short")}
                      <input type="text" name="mobile_phone_1" defaultValue={client.mobile_phone_1 ?? ""} maxLength={30} />
                    </label>

                    <label>
                      {t("admin.client_detail.mobile_2_short")}
                      <input type="text" name="mobile_phone_2" defaultValue={client.mobile_phone_2 ?? ""} maxLength={30} />
                    </label>

                    <label>
                      {t("admin.client_detail.home_phone")}
                      <input type="text" name="home_phone" defaultValue={client.home_phone ?? ""} maxLength={30} />
                    </label>

                    <label className="span-2">
                      {t("admin.client_detail.postal_address")}
                      <input type="text" name="address_line" defaultValue={client.address_line ?? ""} maxLength={255} />
                    </label>

                    {client.client_kind === "ADULT" ? (
                      <label className="span-2">
                        {t("admin.clients.home_access_instructions")}
                        <textarea
                          name="home_access_instructions"
                          defaultValue={client.home_access_instructions ?? ""}
                          rows={3}
                          maxLength={2000}
                          placeholder={t("admin.clients.home_access_instructions_placeholder")}
                        />
                        <span className="muted">{t("admin.clients.home_access_instructions_help")}</span>
                      </label>
                    ) : null}

                    <label>
                      {t("admin.client_detail.postal_code")}
                      <input type="text" name="postal_code" defaultValue={client.postal_code ?? ""} maxLength={20} />
                    </label>

                    <label>
                      {t("admin.client_detail.city")}
                      <input type="text" name="city" defaultValue={client.city ?? ""} maxLength={120} />
                    </label>

                    <label>
                      {uiText(language, "admin.clients.tax_country")} <span className="required-star">*</span>
                      <select name="address_country" defaultValue={client.address_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {uiText(language, "admin.clients.client_type")}
                      <select name="client_kind" defaultValue={client.client_kind === "CHILD" ? "CHILD" : "ADULT"} required>
                        <option value="ADULT">{t("admin.client_detail.kind_adult")}</option>
                        <option value="CHILD">{t("admin.client_detail.kind_child")}</option>
                      </select>
                    </label>

                    <label>
                      {t("admin.client_detail.status")}
                      <select name="client_status" defaultValue={client.client_status || "ACTIVE"} required>
                        <option value="ACTIVE">{uiText(language, "admin.clients.status_active")}</option>
                        {client.client_kind === "ADULT" ? <option value="RESPONSABLE">{uiText(language, "admin.clients.status_responsable")}</option> : null}
                        <option value="TRIAL">{uiText(language, "admin.clients.status_trial")}</option>
                        <option value="PENDING">{uiText(language, "admin.clients.status_pending")}</option>
                        <option value="INACTIVE">{uiText(language, "admin.clients.status_inactive")}</option>
                        <option value="ARCHIVED">{uiText(language, "admin.clients.status_archived")}</option>
                      </select>
                    </label>

                    <label>
                      Site
                      <select name="student_site" defaultValue={client.student_site ?? ""}>
                        <option value="">Non renseigne</option>
                        {STUDENT_SITE_OPTIONS.map((siteValue) => (
                          <option key={siteValue} value={siteValue}>
                            {studentSiteLabel(siteValue)}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("admin.client_detail.country_residence")}
                      <select name="residence_country" defaultValue={client.residence_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("admin.client_detail.currency")}
                      <select name="preferred_currency" defaultValue={client.preferred_currency || DEFAULT_CURRENCY} required>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.client_detail.language")}
                      <select name="preferred_language" defaultValue={client.preferred_language || "fr"} required>
                        <option value="fr">{uiText(language, "admin.client_detail.language_name_fr")}</option>
                        <option value="en">{uiText(language, "admin.client_detail.language_name_en")}</option>
                      </select>
                    </label>

                    <label>
                      {t("admin.client_detail.timezone")}
                      <select name="timezone" defaultValue={client.timezone || DEFAULT_TIMEZONE} required>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {uiText(language, "admin.clients.birth_date")}
                      <input type="date" name="birth_date" defaultValue={client.birth_date ?? ""} />
                    </label>

                    <label className="span-2">
                      {uiText(language, "admin.clients.important_info")}
                      <textarea name="important_info" defaultValue={client.important_info ?? ""} rows={4} maxLength={1000} />
                    </label>

                    <label className="span-2">
                      {uiText(language, "admin.clients.private_note")}
                      <textarea name="private_note" defaultValue={client.private_note ?? ""} rows={4} maxLength={5000} />
                    </label>

                    <fieldset className="span-2 config-payment-fieldset">
                      <legend>{uiText(language, "admin.clients.communication_preferences")}</legend>
                      <label className="checkline">
                        <input type="checkbox" name="portal_contact_visible" defaultChecked={client.portal_contact_visible} />
                        {uiText(language, "admin.clients.portal_contact_visible")}
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="email_opt_in" defaultChecked={client.email_opt_in} />
                        {uiText(language, "admin.clients.email_info_opt_in")}
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="sms_opt_in" defaultChecked={client.sms_opt_in} />
                        {uiText(language, "admin.clients.sms_info_opt_in")}
                      </label>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="lesson_reminder_email_opt_in"
                          defaultChecked={client.lesson_reminder_email_opt_in}
                        />
                        {uiText(language, "admin.clients.email_reminders_opt_in")}
                      </label>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="lesson_reminder_sms_opt_in"
                          defaultChecked={client.lesson_reminder_sms_opt_in}
                        />
                        {uiText(language, "admin.clients.sms_reminders_opt_in")}
                      </label>
                    </fieldset>

                    <div className="row span-2 modal-actions-end">
                      <Link className="reset-link" href={tabHref(client.id, "infos")}>
                        {t("admin.client_detail.cancel")}
                      </Link>
                      <button type="submit">{t("admin.client_detail.save")}</button>
                    </div>
                  </form>
                </section>
              </article>
            </section>
          ) : null}
        </section>
      ) : null}

      {currentTab === "famille" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>{t("admin.client_detail.family_links_title")}</h3>
            {client.client_kind === "ADULT" ? (
              linkedChildren.length === 0 ? (
                <p className="muted">{t("admin.client_detail.no_child_linked")}</p>
              ) : (
                <div className="list">
                  {linkedChildren.map((link) => (
                    <article key={link.id} className="item">
                      <div className="row spread">
                        <strong>
                          {t("admin.client_detail.kind_child")}:{" "}
                          <Link className="client-name-link" href={tabHref(link.child.id, "fiche")}>
                            {([link.child.first_name, link.child.last_name].filter(Boolean).join(" ") || link.child.email)}
                          </Link>
                        </strong>
                        <span className={`status-pill ${link.is_billing_recipient ? "status-ok" : "status-off"}`}>
                          {link.is_billing_recipient
                            ? t("admin.client_detail.billing_sent_to_this_adult")
                            : t("admin.client_detail.billing_sent_to_other_adult")}
                        </span>
                      </div>
                      <p className="muted">
                        {link.child.email} | {t("admin.client_detail.mobile_1_short")}: {link.child.mobile_phone_1 ?? "-"} |{" "}
                        {uiText(language, "admin.clients.relationship_label")}:{" "}
                        {link.relationship_label ?? t("admin.client_detail.relationship_not_specified")}
                      </p>
                      <div className="row">
                        {!link.is_billing_recipient ? (
                          <form action={setFamilyBillingRecipientAction}>
                            <input type="hidden" name="link_id" value={link.id} />
                            <input type="hidden" name="return_client_id" value={client.id} />
                            <button className="ghost" type="submit">
                              {t("admin.client_detail.set_billing_recipient")}
                            </button>
                          </form>
                        ) : null}
                        <form action={unlinkFamilyMembersAction}>
                          <input type="hidden" name="link_id" value={link.id} />
                          <input type="hidden" name="return_client_id" value={client.id} />
                          <button className="danger" type="submit">
                            {t("admin.client_detail.remove_link")}
                          </button>
                        </form>
                      </div>
                    </article>
                  ))}
                </div>
              )
            ) : linkedAdults.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_adult_linked")}</p>
            ) : (
              <div className="list">
                {linkedAdults.map((link) => (
                  <article key={link.id} className="item">
                    <div className="row spread">
                      <strong>
                        {t("admin.client_detail.kind_adult")}:{" "}
                        <Link className="client-name-link" href={tabHref(link.adult.id, "fiche")}>
                          {([link.adult.first_name, link.adult.last_name].filter(Boolean).join(" ") || link.adult.email)}
                        </Link>
                      </strong>
                      <span className={`status-pill ${link.is_billing_recipient ? "status-ok" : "status-off"}`}>
                        {link.is_billing_recipient ? t("admin.client_detail.adult_billing_recipient") : t("admin.client_detail.coparent")}
                      </span>
                    </div>
                    <p className="muted">
                      {link.adult.email} | {t("admin.client_detail.mobile_1_short")}: {link.adult.mobile_phone_1 ?? "-"} |{" "}
                      {t("admin.client_detail.address")}: {link.adult.address_line ?? "-"}
                    </p>
                    <div className="row">
                      {!link.is_billing_recipient ? (
                        <form action={setFamilyBillingRecipientAction}>
                          <input type="hidden" name="link_id" value={link.id} />
                          <input type="hidden" name="return_client_id" value={client.id} />
                          <button className="ghost" type="submit">
                            {t("admin.client_detail.set_billing_recipient")}
                          </button>
                        </form>
                      ) : null}
                      <form action={unlinkFamilyMembersAction}>
                        <input type="hidden" name="link_id" value={link.id} />
                        <input type="hidden" name="return_client_id" value={client.id} />
                        <button className="danger" type="submit">
                          {t("admin.client_detail.remove_link")}
                        </button>
                      </form>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>

          {family.billing_children.length > 0 ? (
            <article className="card span-2">
              <div className="row spread">
                <div>
                  <h3>Répartition de facturation</h3>
                  <p className="muted">
                    Attribuez un pourcentage, un montant fixe ou le solde à chaque parent. Les valeurs sont contrôlées avant enregistrement.
                  </p>
                </div>
              </div>
              <div className="billing-split-list">
                {family.billing_children.map((billingChild) => {
                  const payerIds = new Set(billingChild.payers.map((payer) => payer.adult.id));
                  const eligibleSiblings = family.billing_children
                    .filter(
                      (candidate) =>
                        candidate.child.id !== billingChild.child.id &&
                        [...payerIds].every((payerId) => candidate.payers.some((payer) => payer.adult.id === payerId)),
                    )
                    .map((candidate) => ({
                      id: candidate.child.id,
                      label:
                        [candidate.child.first_name, candidate.child.last_name].filter(Boolean).join(" ") ||
                        candidate.child.email || "Enfant",
                    }));
                  return (
                    <FamilyBillingSplitEditor
                      key={billingChild.child.id}
                      billingChild={billingChild}
                      returnClientId={client.id}
                      eligibleSiblings={eligibleSiblings}
                    />
                  );
                })}
              </div>
            </article>
          ) : null}

          <article className="card">
            <h3>{t("admin.client_detail.attach_existing_account_title")}</h3>
            {client.client_kind === "ADULT" ? (
                <form action={linkExistingFamilyMembersAction} className="grid">
                  <input type="hidden" name="adult_client_id" value={client.id} />
                  <input type="hidden" name="return_client_id" value={client.id} />
                  <ClientLookupSingleSelect
                    kind="CHILD"
                    label={t("admin.client_detail.child_to_attach")}
                    name="child_client_id"
                    placeholder={familyAttachSearchPlaceholder}
                    emptyLabel={t("admin.client_detail.select_child")}
                    noResultsLabel={t("admin.client_detail.no_child_candidate")}
                    searchingLabel={language === "en" ? "Searching..." : "Recherche..."}
                    excludedIds={[client.id, ...linkedChildIds]}
                  />
                  <label>
                    {uiText(language, "admin.clients.relationship_label")}
                    <input
                      name="relationship_label"
                      type="text"
                      maxLength={80}
                      placeholder={uiText(language, "admin.clients.relationship_placeholder")}
                    />
                  </label>
                  <label className="checkline">
                    <input name="is_billing_recipient" type="checkbox" defaultChecked />
                    {t("admin.client_detail.billing_recipient_child_checkbox")}
                  </label>
                  <button type="submit">{t("admin.client_detail.attach_existing_child")}</button>
                </form>
            ) : (
              <form action={linkExistingFamilyMembersAction} className="grid">
                <input type="hidden" name="child_client_id" value={client.id} />
                <input type="hidden" name="return_client_id" value={client.id} />
                <ClientLookupSingleSelect
                  kind="ADULT"
                  label={t("admin.client_detail.adult_to_attach")}
                  name="adult_client_id"
                  placeholder={familyAttachSearchPlaceholder}
                  emptyLabel={t("admin.client_detail.select_adult")}
                  noResultsLabel={t("admin.client_detail.no_adult_candidate")}
                  searchingLabel={language === "en" ? "Searching..." : "Recherche..."}
                  excludedIds={[client.id, ...linkedAdultIds]}
                />
                <label>
                  {uiText(language, "admin.clients.relationship_label")}
                  <input
                    name="relationship_label"
                    type="text"
                    maxLength={80}
                    placeholder={uiText(language, "admin.clients.relationship_placeholder")}
                  />
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" />
                  {t("admin.client_detail.billing_recipient_adult_checkbox")}
                </label>
                <button type="submit">{t("admin.client_detail.attach_existing_adult")}</button>
              </form>
            )}
          </article>

          {client.client_kind === "ADULT" ? (
            <article className="card span-2">
              <h3>{t("admin.client_detail.create_child_and_link_title")}</h3>
              <p className="muted">{t("admin.client_detail.create_child_and_link_help")}</p>
              <form action={createChildForAdultAction} className="grid cols-3">
                <input type="hidden" name="adult_client_id" value={client.id} />
                <label>
                  {uiText(language, "admin.clients.email_optional")}
                  <input type="email" name="child_email" />
                </label>
                <label>
                  {t("admin.client_detail.first_name")} <span className="required-star">*</span>
                  <input type="text" name="child_first_name" maxLength={100} required />
                </label>
                <label>
                  {t("admin.client_detail.last_name")} <span className="required-star">*</span>
                  <input type="text" name="child_last_name" maxLength={100} required />
                </label>
                <label>
                  {t("admin.client_detail.mobile_1_short")}
                  <input type="text" name="child_mobile_phone_1" maxLength={30} />
                </label>
                <label>
                  {t("admin.client_detail.mobile_2_short")}
                  <input type="text" name="child_mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  {t("admin.client_detail.home_phone")}
                  <input type="text" name="child_home_phone" maxLength={30} />
                </label>
                <label className="span-2">
                  {t("admin.client_detail.address")}
                  <input type="text" name="child_address_line" maxLength={255} />
                </label>
                <label>
                  {t("admin.client_detail.postal_code")}
                  <input type="text" name="child_postal_code" maxLength={20} />
                </label>
                <label>
                  {t("admin.client_detail.city")}
                  <input type="text" name="child_city" maxLength={120} />
                </label>
                <label>
                  {t("admin.clients.address_country")}
                  <select name="child_address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.country_residence")}
                  <select name="child_residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.currency")}
                  <select name="child_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.language")}
                  <select name="child_preferred_language" defaultValue="fr">
                    <option value="fr">{uiText(language, "common.french")}</option>
                    <option value="en">{uiText(language, "common.english")}</option>
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.timezone")}
                  <select name="child_timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.birth_date")}
                  <input type="date" name="child_birth_date" />
                </label>
                <label>
                  {uiText(language, "admin.clients.relationship_label")}
                  <input type="text" name="relationship_label" maxLength={80} placeholder={t("admin.client_detail.relationship_placeholder_short")} />
                </label>
                <label className="span-2">
                  {t("admin.client_detail.important_info_label")}
                  <textarea name="child_important_info" rows={3} maxLength={1000} />
                </label>
                <label>
                  {t("admin.client_detail.status")}
                  <select name="child_client_status" defaultValue="ACTIVE">
                    {CLIENT_STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {clientStatusLabel(status, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Site
                  <select name="child_student_site" defaultValue={client.student_site ?? ""}>
                    <option value="">Non renseigne</option>
                    {STUDENT_SITE_OPTIONS.map((siteValue) => (
                      <option key={siteValue} value={siteValue}>
                        {studentSiteLabel(siteValue)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" defaultChecked />
                  {t("admin.client_detail.adult_receives_invoices")}
                </label>
                <div className="row span-2">
                  <button type="submit">{t("admin.client_detail.create_and_link")}</button>
                </div>
              </form>
            </article>
          ) : (
            <article className="card span-2">
              <h3>{t("admin.client_detail.create_adult_and_link_title")}</h3>
              <p className="muted">{t("admin.client_detail.create_adult_and_link_help")}</p>
              <form action={createAdultForChildAction} className="grid cols-3">
                <input type="hidden" name="child_client_id" value={client.id} />
                <label>
                  {uiText(language, "admin.clients.email_optional")}
                  <input type="email" name="adult_email" />
                </label>
                <label>
                  {t("admin.client_detail.first_name")} <span className="required-star">*</span>
                  <input type="text" name="adult_first_name" maxLength={100} required />
                </label>
                <label>
                  {t("admin.client_detail.last_name")} <span className="required-star">*</span>
                  <input type="text" name="adult_last_name" maxLength={100} required />
                </label>
                <label>
                  {t("admin.client_detail.mobile_1_short")}
                  <input type="text" name="adult_mobile_phone_1" maxLength={30} />
                </label>
                <label>
                  {t("admin.client_detail.mobile_2_short")}
                  <input type="text" name="adult_mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  {t("admin.client_detail.home_phone")}
                  <input type="text" name="adult_home_phone" maxLength={30} />
                </label>
                <label className="span-2">
                  {t("admin.client_detail.address")}
                  <input type="text" name="adult_address_line" maxLength={255} />
                </label>
                <label className="span-3">
                  {t("admin.clients.parent_home_access_instructions")}
                  <textarea
                    name="adult_home_access_instructions"
                    rows={2}
                    maxLength={2000}
                    placeholder={t("admin.clients.home_access_instructions_placeholder")}
                  />
                  <span className="muted">{t("admin.clients.home_access_instructions_help")}</span>
                </label>
                <label>
                  {t("admin.client_detail.postal_code")}
                  <input type="text" name="adult_postal_code" maxLength={20} />
                </label>
                <label>
                  {t("admin.client_detail.city")}
                  <input type="text" name="adult_city" maxLength={120} />
                </label>
                <label>
                  {t("admin.clients.address_country")}
                  <select name="adult_address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.country_residence")}
                  <select name="adult_residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.currency")}
                  <select name="adult_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.language")}
                  <select name="adult_preferred_language" defaultValue="fr">
                    <option value="fr">{uiText(language, "common.french")}</option>
                    <option value="en">{uiText(language, "common.english")}</option>
                  </select>
                </label>
                <label>
                  {t("admin.client_detail.timezone")}
                  <select name="adult_timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {uiText(language, "admin.clients.relationship_label")}
                  <input
                    type="text"
                    name="relationship_label"
                    maxLength={80}
                    placeholder={uiText(language, "admin.clients.relationship_placeholder")}
                  />
                </label>
                <label>
                  {t("admin.client_detail.status")}
                  <select name="adult_client_status" defaultValue="RESPONSABLE">
                    {CLIENT_STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {clientStatusLabel(status, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Site
                  <select name="adult_student_site" defaultValue={client.student_site ?? ""}>
                    <option value="">Non renseigne</option>
                    {STUDENT_SITE_OPTIONS.map((siteValue) => (
                      <option key={siteValue} value={siteValue}>
                        {studentSiteLabel(siteValue)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" defaultChecked />
                  {t("admin.client_detail.adult_receives_invoices")}
                </label>
                <div className="row span-2">
                  <button type="submit">{t("admin.client_detail.create_adult_and_link_button")}</button>
                </div>
              </form>
            </article>
          )}
        </section>
      ) : null}

      {currentTab === "messages" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>{t("admin.client_detail.communicate_title")}</h3>
            <div className="grid">
              <Link
                className="mode-link"
                href={messagesHref(client.id, {
                  message_modal: "compose",
                  messages_months: String(messageMonths),
                  messages_q: messageQuery,
                })}
              >
                {t("admin.client_detail.send_email")}
              </Link>
              <form action={adminClientActionPlaceholder}>
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="language" value={language} />
                <input type="hidden" name="action_name" value={t("admin.client_detail.send_sms")} />
                <button type="submit">{t("admin.client_detail.send_sms")}</button>
              </form>
              <details>
                <summary className="mode-link">{t("admin.client_detail.send_push")}</summary>
                <form action={adminSendClientPushAction} className="grid" style={{ marginTop: 12 }}>
                <input type="hidden" name="client_id" value={client.id} />
                  <input type="hidden" name="return_to" value={messagesHref(client.id, { messages_months: String(messageMonths), messages_q: messageQuery })} />
                  <input type="hidden" name="deep_link" value="/client" />
                  <p className="muted">
                    {language === "en"
                      ? "Sent to this client's active app devices. For a child, the notification is sent to the billing guardian."
                      : "Envoyee sur les appareils actifs de ce client. Pour un enfant, la notification est adressee au responsable de facturation."}
                  </p>
                  <label>
                    {language === "en" ? "French title" : "Titre francais"}
                    <input name="title_fr" type="text" maxLength={120} required />
                  </label>
                  <label>
                    {language === "en" ? "French message" : "Message francais"}
                    <textarea name="body_fr" rows={4} maxLength={1000} required />
                  </label>
                  <label>
                    {language === "en" ? "English title (optional)" : "Titre anglais (optionnel)"}
                    <input name="title_en" type="text" maxLength={120} />
                  </label>
                  <label>
                    {language === "en" ? "English message (optional)" : "Message anglais (optionnel)"}
                    <textarea name="body_en" rows={4} maxLength={1000} />
                  </label>
                  <button type="submit">{language === "en" ? "Send notification" : "Envoyer la notification"}</button>
                </form>
              </details>
            </div>
          </article>

          <article className="card">
            <div className="row spread">
              <h3>{t("admin.client_detail.sent_messages_title")}</h3>
              <span className="muted">{t("admin.client_detail.sent_messages_history_help")}</span>
            </div>
            <form method="get" className="row">
              <input type="hidden" name="tab" value="messages" />
              <label className="balance-date-label">
                {uiText(language, "common.period")}
                <select name="messages_months" defaultValue={String(messageMonths)}>
                  <option value="3">{t("admin.client_detail.messages_period_last_3_months")}</option>
                  <option value="6">{t("admin.client_detail.messages_period_last_6_months")}</option>
                  <option value="12">{t("admin.client_detail.messages_period_last_12_months")}</option>
                </select>
              </label>
              <label className="balance-date-label" style={{ minWidth: 240 }}>
                {uiText(language, "common.search")}
                <input
                  type="text"
                  name="messages_q"
                  defaultValue={messageQuery}
                  placeholder={t("admin.client_detail.messages_search_placeholder")}
                />
              </label>
              <button type="submit">{t("admin.client_detail.filter_transactions")}</button>
              <Link className="reset-link" href={messagesHref(client.id, { messages_months: "3" })}>
                {uiText(language, "common.reset")}
              </Link>
            </form>
            {messageRows.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_message_for_client")}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{uiText(language, "common.date")}</th>
                      <th>{uiText(language, "common.subject")}</th>
                      <th>{uiText(language, "common.message")}</th>
                      <th>{uiText(language, "common.status")}</th>
                      <th>{t("admin.client_detail.session_label")}</th>
                      <th>{uiText(language, "common.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {messageRows.map((msg) => (
                      <tr key={msg.id}>
                        <td>{formatDate(msg.occurredAt, language)}</td>
                        <td>{msg.subject}</td>
                        <td>{msg.preview || "-"}</td>
                        <td>
                          <span
                            className={`status-pill ${msg.statusMeta.toneClass}`}
                            title={`${msg.statusMeta.helpText}${msg.errorMessage ? ` (${msg.errorMessage})` : ""}`}
                          >
                            {msg.statusMeta.label}
                          </span>
                        </td>
                        <td>{msg.session}</td>
                        <td>
                          <div className="row payment-row-actions">
                            <Link
                              className="client-action-icon"
                              href={messagesHref(client.id, {
                                message_modal: "view",
                                message_id: msg.id,
                                messages_months: String(messageMonths),
                                messages_q: messageQuery,
                              })}
                              title={t("admin.client_detail.view_full_message")}
                            >
                              👁
                            </Link>
                            {msg.canForward ? (
                              <Link
                                className="client-action-icon"
                                href={messagesHref(client.id, {
                                  message_modal: "forward",
                                  message_id: msg.id,
                                  messages_months: String(messageMonths),
                                  messages_q: messageQuery,
                                })}
                                title={t("admin.client_detail.forward_message")}
                              >
                                ↪
                              </Link>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {openMessageViewModal && selectedMessageForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link
              className="modal-close-x"
              href={messagesHref(client.id, { messages_months: String(messageMonths), messages_q: messageQuery })}
              aria-label={uiText(language, "common.close")}
            >
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.message_detail_title")}</h3>
            <div className="stack-sm top-gap-sm">
              <p className="muted">
                {formatDate(selectedMessageForModal.sent_at ?? selectedMessageForModal.scheduled_for_utc, language)} |{" "}
                {messageStatusMeta(selectedMessageForModal.status, selectedMessageForModal.error_message, language).label}
              </p>
              <p>
                <strong>{uiText(language, "common.subject")} :</strong> {selectedMessageForModal.subject_preview || "-"}
              </p>
              <p>
                <strong>{t("admin.client_detail.recipient")} :</strong> {selectedMessageForModal.recipient || "-"}
              </p>
              <p>
                <strong>{uiText(language, "common.type")} :</strong>{" "}
                {messageSourceLabel(selectedMessageForModal.source, selectedMessageForModal.channel, language)}
              </p>
              {selectedMessageForModal.error_message ? (
                <p className="flash-err" style={{ margin: 0 }}>
                  {selectedMessageForModal.error_message}
                </p>
              ) : null}
              <div className="item">
                <strong>{t("admin.client_detail.content")}</strong>
                {(selectedMessageForModal.body_format || "TEXT").toUpperCase() === "HTML" ? (
                  <iframe
                    title={selectedMessageForModal.subject_preview || t("admin.client_detail.message_detail_title")}
                    className="message-html-preview top-gap-sm"
                    sandbox=""
                    srcDoc={selectedMessageForModal.body_full || "<p>-</p>"}
                  />
                ) : (
                  <pre className="message-full-text">{selectedMessageForModal.body_full || "-"}</pre>
                )}
              </div>
            </div>
            <div className="row modal-actions-end">
              <Link className="reset-link" href={messagesHref(client.id, { messages_months: String(messageMonths), messages_q: messageQuery })}>
                {uiText(language, "common.close")}
              </Link>
            </div>
          </article>
        </section>
      ) : null}

      {openMessageComposeModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link
              className="modal-close-x"
              href={messagesHref(client.id, { messages_months: String(messageMonths), messages_q: messageQuery })}
              aria-label={uiText(language, "common.close")}
            >
              ×
            </Link>
            <h3 className="modal-title">
              {isForwardCompose ? t("admin.client_detail.message_forward_title") : t("admin.client_detail.message_compose_title")}
            </h3>
            <p className="muted">
              {isForwardCompose ? t("admin.client_detail.message_forward_help") : t("admin.client_detail.message_compose_help")}
            </p>
            <form action={sendAdminClientMessageAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value="messages" />
              <input type="hidden" name="source" value={messageComposeSource} />
              <input type="hidden" name="messages_months" value={String(messageMonths)} />
              <input type="hidden" name="messages_q" value={messageQuery} />
              <label className="span-2">
                {t("admin.client_detail.recipients")}
                <div className="item top-gap-sm">
                  <div className="grid">
                    {messageRecipientOptions.map((option) => (
                      <label key={`to-${option.email}`} className="checkbox">
                        <input
                          type="checkbox"
                          name="to_emails"
                          value={option.email}
                          defaultChecked={messageComposeDefaultToEmails.has(option.email.toLowerCase())}
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </div>
              </label>
              <label className="span-2">
                {t("admin.client_detail.other_recipients")}
                <textarea
                  name="to_emails_free"
                  rows={2}
                  defaultValue={messageComposeDefaultToFree}
                  placeholder={t("admin.client_detail.email_placeholder")}
                />
              </label>
              <label className="span-2">
                {t("admin.client_detail.cc")}
                <div className="item top-gap-sm">
                  <div className="grid">
                    {messageRecipientOptions.map((option) => (
                      <label key={`cc-${option.email}`} className="checkbox">
                        <input type="checkbox" name="cc_emails" value={option.email} />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </div>
              </label>
              <label className="span-2">
                {t("admin.client_detail.other_cc")}
                <textarea name="cc_emails_free" rows={2} placeholder={t("admin.client_detail.email_placeholder")} />
              </label>
              <input type="hidden" name="send_copy_to_self" value="off" />
              <label className="checkbox span-2">
                <input type="checkbox" name="send_copy_to_self" value="on" />
                {t("admin.client_detail.send_copy_to_self")}
              </label>
              <label className="span-2">
                {uiText(language, "common.subject")}
                <input type="text" name="subject" maxLength={255} defaultValue={messageComposeSubject} required />
              </label>
              <label className="span-2">
                {uiText(language, "common.message")}
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  defaultValue={messageComposeBody}
                  defaultFormat={messageComposeBodyFormat}
                  rows={12}
                  maxLength={20000}
                  placeholder={t("admin.client_detail.email_body_placeholder")}
                  language={language}
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={messagesHref(client.id, { messages_months: String(messageMonths), messages_q: messageQuery })}>
                  {uiText(language, "common.cancel")}
                </Link>
                <button type="submit">{uiText(language, "common.send")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "changements" ? (
        <section className="admin-page-grid">
          <article className="card">
            <div className="row spread">
              <div>
                <h3>Changements de parcours</h3>
                <p className="muted">Les devis et factures emis restent figes. Chaque changement est historise puis, si besoin, transforme en regularisation a valider.</p>
              </div>
              {readyBillingAdjustmentsCount > 0 ? (
                <span className="badge">{readyBillingAdjustmentsCount} ajustement(s) a valider</span>
              ) : null}
            </div>

            <form action={createAdminClientQuoteChangeAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="currency" value={client.preferred_currency || "EUR"} />
              <label>
                Eleve
                <select name="student_id" defaultValue={client.id}>
                  {quoteChangeStudentOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Origine commerciale
                <select name="quote_id" defaultValue="">
                  <option value="">Non rattache</option>
                  {approvedQuotes.map((quote) => (
                    <option key={quote.id} value={quote.id}>
                      {quote.quote_number} - {formatMoney(quote.total_ttc, quote.currency, language)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Type de changement
                <select name="change_type" defaultValue="SLOT_CHANGE">
                  <option value="SLOT_CHANGE">Changement de creneau</option>
                  <option value="COURSE_CANCELLED">Cours annule</option>
                  <option value="COURSE_ADDED">Cours ajoute</option>
                  <option value="COURSE_REMOVED">Cours supprime</option>
                  <option value="FORMULA_CHANGE">Changement de formule</option>
                  <option value="EXCEPTIONAL_ADJUSTMENT">Ajustement exceptionnel</option>
                  <option value="OTHER">Autre</option>
                </select>
              </label>
              <label>
                Date d'effet
                <input type="date" name="effective_date" defaultValue={todayInputValue} />
              </label>
              <label>
                Demandeur
                <input type="text" name="requested_by" maxLength={120} placeholder="Parent, professeur, admin..." />
              </label>
              <label>
                Impact TTC
                <input type="number" name="financial_impact_ttc" step="0.01" placeholder="0.00" />
              </label>
              <label>
                Action facturation
                <select name="billing_action" defaultValue="NONE">
                  <option value="NONE">Sans impact financier</option>
                  <option value="TO_INVOICE">A facturer</option>
                  <option value="TO_CREDIT">Avoir / deduction</option>
                  <option value="MANUAL_REVIEW">A verifier</option>
                </select>
              </label>
              <label>
                TVA
                <input type="number" name="vat_rate" step="0.001" min="0" max="100" defaultValue="20" />
              </label>
              <label>
                Entite juridique
                <select name="legal_entity_id" defaultValue={legalEntities[0]?.id ?? ""}>
                  <option value="">A determiner</option>
                  {legalEntities.map((entity) => (
                    <option key={entity.id} value={entity.id}>
                      {entity.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-2">
                Titre
                <input type="text" name="title" maxLength={255} required placeholder="Ex. Deplacement du cours de piano du mercredi au samedi" />
              </label>
              <label className="span-2">
                Situation precedente
                <textarea name="before_text" rows={2} maxLength={2000} placeholder="Ce qui etait prevu avant le changement ou dans la derniere facture" />
              </label>
              <label className="span-2">
                Situation nouvelle
                <textarea name="after_text" rows={2} maxLength={2000} placeholder="Ce qui est applique apres accord" />
              </label>
              <label className="span-2">
                Note client
                <textarea name="client_visible_note" rows={2} maxLength={4000} placeholder="Justification reutilisable sur un recapitulatif client" />
              </label>
              <label className="span-2">
                Note interne
                <textarea name="internal_note" rows={2} maxLength={4000} />
              </label>
              <div className="row modal-actions-end span-2">
                <button type="submit">Tracer le changement</button>
              </div>
            </form>
          </article>

          {quoteChangesRecap ? (
            <article className="card">
              <h3>Recapitulatif client</h3>
              <textarea className="code-textarea" rows={10} readOnly value={quoteChangesRecap} />
            </article>
          ) : null}

          <article className="card">
            <h3>Historique et facturation a valider</h3>
            {quoteChanges.length === 0 ? (
              <p className="muted">Aucun changement trace pour le moment.</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Eleve / devis</th>
                      <th>Changement</th>
                      <th>Avant / apres</th>
                      <th>Impact</th>
                      <th>Validation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quoteChanges.map((change) => (
                      <tr key={change.id}>
                        <td>{formatDate(change.created_at, language)}</td>
                        <td>
                          <strong>{change.student_display_name ?? fullName}</strong>
                          <div className="muted">{change.quote_number ?? "Sans devis rattache"}</div>
                        </td>
                        <td>
                          <span className="status-pill status-info">{quoteChangeTypeLabel(change.change_type)}</span>
                          <div className="top-gap-xs">{change.title}</div>
                          {change.client_visible_note ? <div className="muted">{change.client_visible_note}</div> : null}
                        </td>
                        <td>
                          <div className="muted">Avant: {snapshotText(change.before_snapshot)}</div>
                          <div>Apres: {snapshotText(change.after_snapshot)}</div>
                        </td>
                        <td>
                          <strong>{formatMoney(change.financial_impact_ttc ?? "0", change.currency, language)}</strong>
                          <div className="muted">{billingActionLabel(change.billing_action)}</div>
                        </td>
                        <td>
                          {change.billing_adjustments.length === 0 ? (
                            <span className="status-pill status-off">Aucun ajustement</span>
                          ) : (
                            <div className="stack-xs">
                              {change.billing_adjustments.map((adjustment) => (
                                <div key={adjustment.id} className="stack-xs">
                                  <span className={`status-pill ${adjustmentStatusClass(adjustment.status)}`}>
                                    {adjustment.status === "READY"
                                      ? "A valider"
                                      : adjustment.status === "CONVERTED"
                                        ? "Ajoute aux lignes a facturer"
                                        : "Ignore"}
                                  </span>
                                  <span>{formatMoney(adjustment.total_incl_vat, adjustment.currency, language)}</span>
                                  {adjustment.status === "READY" ? (
                                    <div className="row payment-row-actions">
                                      <form action={approveAdminClientBillingAdjustmentAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="adjustment_id" value={adjustment.id} />
                                        <button type="submit" className="client-action-icon" title="Ajouter aux lignes a facturer">
                                          ✓
                                        </button>
                                      </form>
                                      <form action={dismissAdminClientBillingAdjustmentAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="adjustment_id" value={adjustment.id} />
                                        <button type="submit" className="client-action-icon danger" title="Ignorer cet ajustement">
                                          ×
                                        </button>
                                      </form>
                                    </div>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {currentTab === "factures" ? (
        <section className="admin-page-grid">
          <article className="card">
            <div className="row spread">
              <h3>{t("admin.client_detail.invoices_section_title")}</h3>
              <div className="row">
                <Link
                  className="mode-link"
                  href={invoicesHref(client.id, { payment_modal: "invoice_range", payment_return_tab: "factures" })}
                >
                  {t("admin.client_detail.invoice_create")}
                </Link>
              </div>
            </div>

            {invoices.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_invoices")}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("common.date")}</th>
                      <th>{t("admin.client_detail.invoices_column_number")}</th>
                      <th>{t("common.type")}</th>
                      <th>{t("admin.client_detail.invoices_column_label")}</th>
                      <th>{t("admin.client_detail.invoices_column_status")}</th>
                      <th>{t("common.total")}</th>
                      <th>{t("common.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((row) => (
                      <tr key={row.key}>
                        <td>{formatDate(row.occurredAt, language)}</td>
                        <td>{row.invoiceNumber ?? "-"}</td>
                        <td>
                          {row.typeLabel}
                          {row.kind === "range" ? (
                            <div className="stack-xs">
                              <span className={`status-pill ${row.modeLabel === "Auto" ? "status-warn" : "status-off"}`}>{row.modeLabel}</span>
                            </div>
                          ) : null}
                        </td>
                        <td>
                          {row.label}
                          {row.kind === "range" && row.originalInvoiceNumber ? (
                            <div className="muted">
                              {language === "en" ? "Original invoice" : "Facture d’origine"} : {row.originalInvoiceNumber}
                            </div>
                          ) : null}
                          {row.kind === "range" && row.creditNoteNumber ? (
                            <div className="muted">
                              {language === "en" ? "Credit note" : "Avoir"} : {row.creditNoteNumber}
                            </div>
                          ) : null}
                        </td>
                        <td>
                          {row.kind === "range" ? (
                            <div className="stack-xs">
                              <span className={`status-pill ${rangeInvoiceStatusClass(row.status)}`}>
                                {rangeInvoiceStatusLabel(row.status, language)}
                              </span>
                              {row.emailedAt ? (
                                <span
                                  className="status-pill status-ok"
                                  title={t("admin.client_detail.invoice_emailed_on", { date: formatDate(row.emailedAt, language) })}
                                >
                                  {t("admin.client_detail.invoice_emailed")}
                                </span>
                              ) : null}
                              {row.remindedAt ? (
                                <span
                                  className="status-pill status-warn"
                                  title={t("admin.client_detail.invoice_reminded_on", { date: formatDate(row.remindedAt, language) })}
                                >
                                  {t("admin.client_detail.invoice_reminder")}
                                </span>
                              ) : null}
                              {row.checkCoverageStatus !== "NONE" ? (
                                <span
                                  className={`status-pill ${row.checkCoverageStatus === "COVERED" ? "status-ok" : "status-warn"}`}
                                  title={
                                    row.checkCoverageStatus === "COVERED"
                                      ? language === "en"
                                        ? "The invoice remains issued until the checks are cashed. Payment reminders are suspended."
                                        : "La facture reste émise jusqu’à l’encaissement des chèques. Les relances sont suspendues."
                                      : language === "en"
                                        ? "The received checks cover only part of the outstanding balance."
                                        : "Les chèques reçus ne couvrent qu’une partie du solde."
                                  }
                                >
                                  {row.checkCoverageStatus === "COVERED"
                                    ? language === "en"
                                      ? `Covered by ${row.pendingCheckCount} pending check(s)`
                                      : `Couverte par ${row.pendingCheckCount} chèque(s) en attente`
                                    : language === "en"
                                      ? `${row.pendingCheckCount} pending check(s): partial coverage`
                                      : `${row.pendingCheckCount} chèque(s) en attente : couverture partielle`}
                                  {row.pendingCheckAmountLabel ? ` · ${row.pendingCheckAmountLabel}` : ""}
                                </span>
                              ) : null}
                              {row.bankTransferOrderReference ? (
                                <span
                                  className={`status-pill ${
                                    row.bankTransferOrderStatus === "paid"
                                      ? "status-ok"
                                      : row.bankTransferOrderStatus === "expired"
                                        ? "status-cancelled"
                                        : "status-warn"
                                  }`}
                                  title={row.bankTransferOrderExpiresAt ? formatDate(row.bankTransferOrderExpiresAt, language) : undefined}
                                >
                                  Virement {row.bankTransferOrderReference}
                                </span>
                              ) : null}
                            </div>
                          ) : (
                            invoiceStatusLabel(row.status, language)
                          )}
                        </td>
                        <td>
                          {row.kind === "range" ? (
                            <div className="stack-xs">
                              <span>{row.totalLabel}</span>
                              {row.balanceLabel ? (
                                <small className="muted">
                                  {language === "en" ? "Outstanding balance" : "Solde restant"} : {row.balanceLabel}
                                </small>
                              ) : null}
                            </div>
                          ) : (
                            formatMoney(row.total, row.currency, language)
                          )}
                        </td>
                        <td>
                          {row.kind === "range" ? (
                            <div className="row payment-row-actions">
                              <a
                                className="client-action-icon"
                                href={row.viewHref}
                                target="_blank"
                                rel="noreferrer"
                                title={t("admin.client_detail.view_invoice")}
                              >
                                V
                              </a>
                              <a className="client-action-icon" href={row.downloadHref} title={t("admin.client_detail.download_invoice")}>
                                ↓
                              </a>
                              {row.status !== "CREDIT_NOTE" ? <Link
                                className="client-action-icon"
                                href={invoicesHref(client.id, {
                                  payment_modal: "invoice_email",
                                  payment_return_tab: "factures",
                                  invoice_note_id: row.noteId,
                                  invoice_email_kind: "INVOICE",
                                })}
                                title={t("admin.client_detail.email_invoice")}
                              >
                                ✉
                              </Link> : null}
                              {row.status === "ISSUED" ? <Link className="mode-link" href={invoicesHref(client.id, {
                                payment_modal: "invoice_partial_payment", payment_return_tab: "factures", invoice_note_id: row.noteId,
                              })}>Envoyer un lien de paiement partiel</Link> : null}
                              {row.status !== "CREDIT_NOTE" && (row.remindersSuspended ? (
                                <button
                                  type="button"
                                  className="client-action-icon"
                                  disabled
                                  title={
                                    language === "en"
                                      ? "Reminder suspended: the balance is covered by pending checks"
                                      : "Relance suspendue : le solde est couvert par des chèques en attente d’encaissement"
                                  }
                                >
                                  R
                                </button>
                              ) : (
                                <Link
                                  className="client-action-icon"
                                  href={invoicesHref(client.id, {
                                    payment_modal: "invoice_email",
                                    payment_return_tab: "factures",
                                    invoice_note_id: row.noteId,
                                    invoice_email_kind: "REMINDER",
                                  })}
                                  title={t("admin.client_detail.send_invoice_reminder")}
                                >
                                  R
                                </Link>
                              ))}
                              {row.bankTransferOrderStatus === "pending_bank_transfer" ? (
                                <form action={markAdminClientRangeInvoiceBankTransferPaidAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <ClientActionSubmitButton
                                    className="client-action-icon"
                                    title="Valider le virement recu"
                                    pendingLabel="..."
                                  >
                                    V€
                                  </ClientActionSubmitButton>
                                </form>
                              ) : null}
                              {row.status === "ISSUED" && row.bankTransferOrderStatus !== "pending_bank_transfer" ? (
                                <Link
                                  className="client-action-icon"
                                  href={invoicesHref(client.id, {
                                    payment_modal: "invoice_bank_transfer",
                                    payment_return_tab: "factures",
                                    invoice_note_id: row.noteId,
                                  })}
                                  title="Receptionner un virement"
                                >
                                  V€
                                </Link>
                              ) : null}
                              {row.status !== "CREDIT_NOTE" ? (row.status !== "PAID" ? (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="PAID" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title={t("admin.client_detail.mark_invoice_paid")}>
                                    €
                                  </button>
                                </form>
                              ) : (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="ISSUED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title={t("admin.client_detail.reopen_invoice_paid")}>
                                    ↺
                                  </button>
                                </form>
                              )) : null}
                              {row.status !== "CREDIT_NOTE" ? (row.status !== "CANCELLED" ? (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="CANCELLED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon danger" title={t("admin.client_detail.cancel_invoice")}>
                                    ×
                                  </button>
                                </form>
                              ) : (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="ISSUED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title={t("admin.client_detail.restore_invoice_issued")}>
                                    ↺
                                  </button>
                                </form>
                              )) : null}
                              {(row.status === "ISSUED" || row.status === "PAID") && row.documentType === "INVOICE" ? (
                                <form id={`range-credit-note-${row.noteId}`} action={createAdminClientRangeInvoiceCreditNoteAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="issued_date" value={todayInputValue} />
                                  <input
                                    type="hidden"
                                    name="reason"
                                    value={`Annulation de la facture ${row.invoiceNumber} et remplacement par un nouveau mode de facturation.`}
                                  />
                                  <ConfirmSubmitButton
                                    formId={`range-credit-note-${row.noteId}`}
                                    label="A"
                                    title={language === "en" ? "Create a credit note" : "Créer un avoir"}
                                    description={
                                      language === "en"
                                        ? `A numbered credit note will be created for invoice ${row.invoiceNumber}, which will then be cancelled. No email will be sent automatically.`
                                        : `Un avoir numéroté sera créé pour la facture ${row.invoiceNumber}, qui sera ensuite annulée. Aucun e-mail ne sera envoyé automatiquement.`
                                    }
                                    confirmLabel={language === "en" ? "Create credit note" : "Créer l’avoir"}
                                    language={language}
                                    className="client-action-icon"
                                    pendingLabel="…"
                                  />
                                </form>
                              ) : null}
                              {row.status === "ISSUED" && hasConfiguredFamilyBillingSplit ? (
                                <form
                                  id={`family-invoice-split-${row.noteId}`}
                                  action={splitAdminClientRangeInvoiceByFamilyAction}
                                >
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <ConfirmSubmitButton
                                    formId={`family-invoice-split-${row.noteId}`}
                                    label="%"
                                    title="Répartir cette facture entre les payeurs ?"
                                    description="La facture d’origine sera annulée et remplacée par une facture distincte pour chaque payeur, selon la répartition enregistrée dans l’onglet Famille. Les acomptes déjà reçus sont répartis selon la même clé afin que chaque payeur règle sa part du solde restant. Aucun e-mail ne sera envoyé automatiquement."
                                    confirmLabel="Créer les factures"
                                    language={language}
                                    className="client-action-icon"
                                    pendingLabel="…"
                                  />
                                </form>
                              ) : null}
                              {(row.status === "ISSUED" || row.status === "PAID") ? (
                                <form action={reissueAdminClientRangeInvoiceAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="issued_date" value={todayInputValue} />
                                  <input type="hidden" name="start_date" value={row.startDate} />
                                  <input type="hidden" name="end_date" value={row.endDate} />
                                  <input type="hidden" name="due_date" value={row.noDueDate ? todayInputValue : dueDateInputValue} />
                                  <input type="hidden" name="no_due_date" value={row.noDueDate ? "true" : "false"} />
                                  <input type="hidden" name="include_pending" value={row.includePending ? "true" : "false"} />
                                  <input type="hidden" name="include_cancelled" value={row.includeCancelled ? "true" : "false"} />
                                  <input type="hidden" name="layout" value={row.layout} />
                                  <input type="hidden" name="group_adjustments_by_type" value={row.groupAdjustmentsByType ? "true" : "false"} />
                                  <input type="hidden" name="include_discount_adjustments" value={row.includeDiscountAdjustments ? "true" : "false"} />
                                  <input type="hidden" name="include_supplement_adjustments" value={row.includeSupplementAdjustments ? "true" : "false"} />
                                  <input type="hidden" name="public_note" value={row.publicNote ?? ""} />
                                  <input type="hidden" name="private_note" value={row.privateNote ?? ""} />
                                  {row.includedPaymentKeys.map((key) => (
                                    <input key={`reissue-${row.noteId}-${key}`} type="hidden" name="selected_payment_keys" value={key} />
                                  ))}
                                  <button type="submit" className="client-action-icon" title="Annuler et refaire cette facture avec une nouvelle date">
                                    ⧉
                                  </button>
                                </form>
                              ) : null}
                              {!row.emailedAt && !row.remindedAt && row.status !== "PAID" && row.status !== "CREDIT_NOTE" ? (
                                <form action={deleteAdminClientRangeInvoiceAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon danger" title="Supprimer la facture non envoyee">
                                    S
                                  </button>
                                </form>
                              ) : null}
                            </div>
                          ) : row.kind === "legacy" ? (
                            <div className="row payment-row-actions">
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/invoices/legacy/${row.invoiceId}/pdf?inline=true`}
                                target="_blank"
                                rel="noreferrer"
                                title={t("admin.client_detail.view_invoice")}
                              >
                                V
                              </a>
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/invoices/legacy/${row.invoiceId}/pdf`}
                                title={t("admin.client_detail.download_invoice")}
                              >
                                ↓
                              </a>
                            </div>
                          ) : (
                            <div className="row payment-row-actions">
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/payments/${encodeURIComponent(row.source)}/${row.paymentId}/invoice?inline=true`}
                                target="_blank"
                                rel="noreferrer"
                                title={t("admin.client_detail.view_invoice")}
                              >
                                V
                              </a>
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/payments/${encodeURIComponent(row.source)}/${row.paymentId}/invoice`}
                                title={t("admin.client_detail.download_invoice")}
                              >
                                ↓
                              </a>
                              {row.paymentStatus !== "REFUNDED" ? (
                                <>
                                  {row.source.toUpperCase() === "PLAN_PURCHASE" ? (
                                    <Link
                                      className="client-action-icon"
                                      href={invoicesHref(client.id, {
                                        payment_modal: "refund",
                                        payment_source: row.source.toUpperCase(),
                                        payment_id: row.paymentId,
                                        payment_return_tab: "factures",
                                      })}
                                      title={t("admin.client_detail.create_credit_note")}
                                    >
                                      A
                                    </Link>
                                  ) : null}
                                  <form action={cancelAdminClientInvoiceAction}>
                                    <input type="hidden" name="client_id" value={client.id} />
                                    <input type="hidden" name="payment_source" value={row.source.toUpperCase()} />
                                    <input type="hidden" name="payment_id" value={row.paymentId} />
                                    <input type="hidden" name="return_tab" value="factures" />
                                    <button type="submit" className="client-action-icon danger" title={t("admin.client_detail.cancel_invoice")}>
                                      ×
                                    </button>
                                  </form>
                                </>
                              ) : null}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" ? (
        <section className="admin-page-grid">
          <article className="card">
            <div className="row spread">
              <h3>{t("admin.client_detail.payments_section_title")}</h3>
              <div className="row">
                <span className="badge">{t("admin.client_detail.balance_as_of", { date: formatDateInputLabel(selectedBalanceDate, language) })}</span>
                {[...totalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={currency} className="badge">
                    {t(total < -0.005 ? "admin.client_detail.credit_currency" : "admin.client_detail.balance_currency", {
                      currency,
                      amount: formatMoney(String(total < -0.005 ? Math.abs(total) : total), currency, language),
                    })}
                  </span>
                ))}
                {[...paidTotalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={`paid-${currency}`} className="badge">
                    {t("admin.client_detail.paid_currency", {
                      currency,
                      amount: formatMoney(String(total), currency, language),
                    })}
                  </span>
                ))}
                {[...cancelledOrNotBillableTotalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={`cancelled-${currency}`} className="badge">
                    {t("admin.client_detail.cancelled_currency", {
                      currency,
                      amount: formatMoney(String(total), currency, language),
                    })}
                  </span>
                ))}
                {hasPaymentFilters ? (
                  <span className="badge">
                    {t("admin.client_detail.active_filters")}
                    {paymentFilterQuery ? ` | ${t("admin.client_detail.active_filters_text", { value: paymentFilterQuery })}` : ""}
                    {paymentFilterAmount !== null ? ` | ${t("admin.client_detail.active_filters_amount", { value: paymentFilterAmount.toFixed(2) })}` : ""}
                  </span>
                ) : null}
                <form method="get" className="row balance-date-form">
                  <input type="hidden" name="tab" value="paiements" />
                  {paymentFilterQuery ? <input type="hidden" name="payment_filter_q" value={paymentFilterQuery} /> : null}
                  {paymentFilterAmountRaw ? <input type="hidden" name="payment_filter_amount" value={paymentFilterAmountRaw} /> : null}
                  <label className="balance-date-label">
                    {t("admin.client_detail.balance_date")}
                    <input type="date" name="balance_date" defaultValue={selectedBalanceDate} />
                  </label>
                  <button type="submit" className="ghost">
                    {t("admin.client_detail.refresh")}
                  </button>
                </form>
                <Link
                  className="mode-link"
                  href={paymentsHref(client.id, { payment_modal: "manual", balance_date: selectedBalanceDate })}
                >
                  {t("admin.client_detail.add_transaction")}
                </Link>
                <Link
                  className="mode-link"
                  href={paymentsHref(client.id, {
                    payment_modal: "filters",
                    balance_date: selectedBalanceDate,
                    payment_filter_q: paymentFilterQuery,
                    payment_filter_amount: paymentFilterAmountRaw,
                  })}
                >
                  {t("admin.client_detail.filter_transactions")}
                </Link>
                <Link
                  className="mode-link"
                  href={paymentsHref(client.id, { payment_modal: "invoice_range", balance_date: selectedBalanceDate })}
                >
                  {t("admin.client_detail.invoice_create")}
                </Link>
                <Link
                  className="client-action-icon payment-add-icon"
                  href={paymentsHref(client.id, {
                    purchase_modal: "wizard",
                    purchase_return_tab: "paiements",
                    balance_date: selectedBalanceDate,
                  })}
                  title={t("admin.client_detail.add_purchase_title")}
                >
                  +
                </Link>
              </div>
            </div>

            {payments.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_transactions")}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("common.date")}</th>
                      <th>{t("common.type")}</th>
                      <th>{t("admin.client_detail.payment_method_column")}</th>
                      <th>{t("admin.client_detail.invoices_column_label")}</th>
                      <th>{t("admin.client_detail.linked_plan_column")}</th>
                      <th>{t("admin.client_detail.service_rate_column")}</th>
                      <th>{t("common.status")}</th>
                      <th>{t("common.total")}</th>
                      <th>{t("common.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPayments.map((row) => (
                      <tr key={`${row.source}-${row.id}`}>
                        <td>{formatDate(row.occurred_at, language)}</td>
                        <td>{paymentSourceLabel(row.source, language)}</td>
                        <td>{row.payment_method_code ? localizedBillingMethodLabel(row.payment_method_code, language) : row.payment_method_label ?? "-"}</td>
                        <td>
                          <div className="stack-xs">
                            <span>{row.label}</span>
                            <small className="muted">
                              {row.invoice_number ?? t("admin.client_detail.no_invoice")} | {invoiceStatusLabel(row.invoice_status, language)}
                            </small>
                          </div>
                        </td>
                        <td>{row.source.toUpperCase() === "BOOKING" ? row.reference ?? "-" : "-"}</td>
                        <td>
                          <div className="stack-xs">
                            <span>{formatMoney(row.total_incl_vat, row.currency, language)}</span>
                            {isLegacyInvoicePayment(row) ? (
                              <small className="muted">{t("admin.client_detail.legacy_invoice_total_only")}</small>
                            ) : (
                              <small className="muted">
                                {t("admin.client_detail.price_breakdown", {
                                  excl: formatMoney(row.amount_excl_vat, row.currency, language),
                                  vat: formatMoney(row.vat_amount, row.currency, language),
                                  rate: formatVatRateLabel(row.vat_rate, language),
                                })}
                              </small>
                            )}
                          </div>
                        </td>
                        <td>
                          <span className={`status-pill ${isIncludedPlanBooking(row) ? "status-off" : paymentStatusClass(row.status)}`}>
                            {paymentStatusDisplayLabel(row, language)}
                          </span>
                        </td>
                        <td>{formatMoney(row.total_incl_vat, row.currency, language)}</td>
                        <td>
                          <div className="row payment-row-actions">
                            {isLegacyInvoicePayment(row) ? (
                              <>
                                <a
                                  className="client-action-icon"
                                  href={`/admin/clients/${client.id}/invoices/legacy/${row.id}/pdf?inline=true`}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={t("admin.client_detail.view_invoice")}
                                >
                                  V
                                </a>
                                <a
                                  className="client-action-icon"
                                  href={`/admin/clients/${client.id}/invoices/legacy/${row.id}/pdf`}
                                  title={t("admin.client_detail.download_invoice")}
                                >
                                  ↓
                                </a>
                              </>
                            ) : null}
                            {row.source.toUpperCase() === "MANUAL" ? (
                              <>
                                {row.can_edit ? (
                                  <Link
                                    className="client-action-icon"
                                    href={paymentsHref(client.id, {
                                      payment_modal: "edit_manual",
                                      payment_id: row.id,
                                      payment_source: "MANUAL",
                                      payment_return_tab: "paiements",
                                    })}
                                    title={t("admin.client_detail.edit_transaction")}
                                  >
                                    ✎
                                  </Link>
                                ) : row.locked_by_invoice_number ? (
                                  <span
                                    className="client-action-icon"
                                    title={t("admin.client_detail.transaction_locked_by_invoice", {
                                      invoice: row.locked_by_invoice_number,
                                    })}
                                  >
                                    🔒
                                  </span>
                                ) : null}
                                {row.can_cancel ? (
                                  <form action={deleteAdminClientManualTransactionAction}>
                                    <input type="hidden" name="client_id" value={client.id} />
                                    <input type="hidden" name="transaction_id" value={row.id} />
                                    <button type="submit" className="client-action-icon danger" title={t("admin.client_detail.delete_transaction")}>
                                      ×
                                    </button>
                                  </form>
                                ) : null}
                                {isTrackedCheckPayment(row) ? (
                                  <>
                                    {normalizePaymentStatus(row.status) !== "CHECK_RECEIVED" ? (
                                      <form action={updateAdminClientManualTransactionStatusAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="transaction_id" value={row.id} />
                                        <input type="hidden" name="status" value="CHECK_RECEIVED" />
                                        <button type="submit" className="client-action-icon" title={t("admin.client_detail.mark_checks_received")}>
                                          R
                                        </button>
                                      </form>
                                    ) : null}
                                    {normalizePaymentStatus(row.status) !== "CHECK_DEPOSITED" ? (
                                      <form action={updateAdminClientManualTransactionStatusAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="transaction_id" value={row.id} />
                                        <input type="hidden" name="status" value="CHECK_DEPOSITED" />
                                        <button type="submit" className="client-action-icon" title={t("admin.client_detail.mark_checks_deposited")}>
                                          D
                                        </button>
                                      </form>
                                    ) : null}
                                    {normalizePaymentStatus(row.status) !== "PAID" ? (
                                      <form action={updateAdminClientManualTransactionStatusAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="transaction_id" value={row.id} />
                                        <input type="hidden" name="status" value="PAID" />
                                        <button type="submit" className="client-action-icon" title={t("admin.client_detail.mark_checks_cashed")}>
                                          OK
                                        </button>
                                      </form>
                                    ) : null}
                                    {normalizePaymentStatus(row.status) !== "CHECK_REFUSED" ? (
                                      <form action={updateAdminClientManualTransactionStatusAction}>
                                        <input type="hidden" name="client_id" value={client.id} />
                                        <input type="hidden" name="transaction_id" value={row.id} />
                                        <input type="hidden" name="status" value="CHECK_REFUSED" />
                                        <button type="submit" className="client-action-icon" title={t("admin.client_detail.mark_check_refused")}>
                                          REF
                                        </button>
                                      </form>
                                    ) : null}
                                  </>
                                ) : null}
                              </>
                            ) : null}
                            {isRefundablePlanPurchase(row) ? (
                              <Link
                                className="client-action-icon danger"
                                href={paymentsHref(client.id, {
                                  payment_modal: "refund",
                                  payment_source: row.source.toUpperCase(),
                                  payment_id: row.id,
                                  payment_return_tab: "paiements",
                                })}
                                title={t("admin.client_detail.refund_payment_action")}
                              >
                                ↔
                              </Link>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredPayments.length === 0 ? (
                  <p className="muted top-gap-sm">{t("admin.client_detail.no_filtered_rows")}</p>
                ) : null}
              </div>
            )}
          </article>

          <article id="payments-history" className="card">
            <h3>{t("admin.client_detail.subscription_history")}</h3>
            {subscriptions.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_subscriptions")}</p>
            ) : (
              <div className="list top-gap-sm">
                {subscriptions.map((sub) => {
                  const statusPill = localizedSubscriptionStatusPill(sub, language);
                  return (
                    <article key={sub.id} className="item row spread">
                    <div className="stack-sm">
                      <div className="row">
                        <span className={`status-pill ${statusPill.toneClass}`}>{statusPill.label}</span>
                        <strong>{sub.plan.name}</strong>
                      </div>
                      <small className="muted">
                        {t("admin.client_detail.subscription_history_line", {
                          start: formatDate(sub.started_at, language),
                          next: sub.next_payment_at ? formatDate(sub.next_payment_at, language) : t("admin.client_detail.not_scheduled"),
                        })}
                      </small>
                    </div>
                    <div className="row">
                      <span className="muted">{t("admin.client_detail.subscription_id", { id: sub.id })}</span>
                    </div>
                    </article>
                  );
                })}
              </div>
            )}
          </article>
        </section>
      ) : null}

      {paymentModalAction === "invoice_partial_payment" && selectedRangeInvoiceForModal && partialPaymentContext?.ok ? (
        <InvoicePartialPaymentModal clientId={client.id} noteId={selectedRangeInvoiceForModal.noteId}
          requestId={randomUUID()} closeHref={invoicesHref(client.id, {})} context={partialPaymentContext.data} action={sendAdminClientPartialPaymentAction} />
      ) : null}
      {currentTab === "paiements" && paymentModalAction === "add" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "paiements")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.add_purchase_title")}</h3>
            <p className="muted">{t("admin.client_detail.add_purchase_help")}</p>
            <form action={adminPurchasePlanForClientAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value="paiements" />
              <label>
                {t("admin.client_detail.product_label")}
                <select name="plan_id" required defaultValue="">
                  <option value="" disabled>
                    {t("admin.client_detail.select_product")}
                  </option>
                  {plans.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} ({planKindLabel(plan.kind, language)})
                    </option>
                  ))}
                </select>
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "paiements")}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("admin.client_detail.add")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openManualTransactionStepOne ? (
        <section className="modal-overlay">
          <article className="modal-panel transaction-wizard-modal">
            <Link className="modal-close-x" href={manualStepOneBackHref} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="transaction-wizard-header">
              <h3 className="modal-title">{t("admin.client_detail.transaction_modal_title")}</h3>
              <div className="purchase-wizard-stepper" aria-label={t("admin.client_detail.transaction_progress_aria")}>
                <span className="active">{t("admin.client_detail.transaction_step_amount")}</span>
                <span>{t("admin.client_detail.transaction_step_details")}</span>
              </div>
            </header>
            <form method="get" action={`/admin/clients/${client.id}`} className="grid top-gap-sm transaction-step-form">
              <input type="hidden" name="tab" value="paiements" />
              <input type="hidden" name="payment_modal" value="manual" />
              <input type="hidden" name="manual_step" value="2" />
              <input type="hidden" name="balance_date" value={selectedBalanceDate} />

              <section className="transaction-type-segmented span-2" aria-label={t("admin.client_detail.transaction_type_aria")}>
                {(["payment", "refund", "charge", "discount", "fees"] as ManualTransactionModalType[]).map((type) => (
                  <Link
                    key={`manual-type-${type}`}
                    href={manualStepOneTypeHref(type)}
                    className={`transaction-type-chip${manualTransactionSelectedType === type ? " active" : ""}`}
                  >
                    <strong>{manualTransactionTitleByModal[type]}</strong>
                    <small className="muted">{manualTransactionHelpByModal[type]}</small>
                  </Link>
                ))}
              </section>
              <input type="hidden" name="manual_type" value={manualTransactionSelectedType} />

              <label>
                {manualIsCashFlow ? t("admin.client_detail.transaction_amount_required") : t("admin.client_detail.transaction_amount_optional")}
                <input
                  type="number"
                  name="manual_amount"
                  step="0.01"
                  min="0.01"
                  defaultValue={manualAmountInputValue}
                  required={manualIsCashFlow}
                />
                {!manualIsCashFlow ? (
                  <small className="muted">
                    {t("admin.client_detail.transaction_catalog_amount_help")}
                  </small>
                ) : null}
              </label>
              <label>
                {t("admin.client_detail.transaction_date_required")}
                <input type="date" name="manual_date" defaultValue={manualDateInputValue} required />
              </label>

              {!manualIsCashFlow ? (
                <label className="transaction-vat-field">
                  {t("admin.client_detail.transaction_vat_optional")}
                  <input type="number" name="manual_vat" step="0.001" min="0" max="100" defaultValue={manualVatInputValue || manualVatDefault} />
                </label>
              ) : null}

              <div className="row modal-actions-end transaction-wizard-footer">
                <Link className="reset-link" href={manualStepOneBackHref}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("common.continue")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openPaymentFiltersModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link
              className="modal-close-x"
              href={paymentsHref(client.id, {
                balance_date: selectedBalanceDate,
                payment_filter_q: paymentFilterQuery,
                payment_filter_amount: paymentFilterAmountRaw,
              })}
              aria-label={t("common.close")}
            >
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.filters_title")}</h3>
            <p className="muted">{t("admin.client_detail.filters_help")}</p>
            <form method="get" action={`/admin/clients/${client.id}`} className="grid top-gap-sm">
              <input type="hidden" name="tab" value="paiements" />
              <input type="hidden" name="balance_date" value={selectedBalanceDate} />
              <label>
                {t("common.search")}
                <input
                  type="text"
                  name="payment_filter_q"
                  defaultValue={paymentFilterQuery}
                  placeholder={t("admin.client_detail.filter_search_placeholder")}
                />
              </label>
              <label>
                {t("common.amount")} {t("common.ttc")}
                <input
                  type="number"
                  name="payment_filter_amount"
                  step="0.01"
                  min="-999999"
                  defaultValue={paymentFilterAmountRaw}
                  placeholder={t("admin.client_detail.filter_amount_placeholder")}
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={paymentsHref(client.id, { balance_date: selectedBalanceDate })}>
                  {t("common.reset")}
                </Link>
                <button type="submit">{t("common.apply")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openManualTransactionStepTwo && manualTransactionTypeCode ? (
        <section className="modal-overlay">
          <article className="modal-panel transaction-wizard-modal">
            <Link className="modal-close-x" href={manualStepOneBackHref} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="transaction-wizard-header">
              <h3 className="modal-title">{t("admin.client_detail.transaction_modal_title")}</h3>
              <div className="purchase-wizard-stepper" aria-label={t("admin.client_detail.transaction_progress_aria")}>
                <span>{t("admin.client_detail.transaction_step_amount")}</span>
                <span className="active">{t("admin.client_detail.transaction_step_details")}</span>
              </div>
              <p className="muted">
                {t("common.type")}: <strong>{manualTransactionTitle}</strong> · {t("common.amount")}:{" "}
                <strong>{manualAmountInputValue ? formatMoney(manualAmountInputValue, client.preferred_currency || "EUR", language) : "-"}</strong>
              </p>
            </header>
            {manualCheckBatchIds.length > 0 ? (
              <section className="flash-ok manual-check-batch-confirmation" role="status">
                <strong>
                  {language === "en"
                    ? `Check no. ${manualCheckBatchIds.length} saved.`
                    : `Chèque n°${manualCheckBatchIds.length} enregistré.`}
                </strong>
                <span>
                  {language === "en"
                    ? " This check has been created. You can now enter the next one."
                    : " Ce chèque a bien été créé. Vous pouvez maintenant saisir le suivant."}
                </span>
              </section>
            ) : null}
            <form action={createAdminClientManualTransactionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="currency" value={client.preferred_currency || "EUR"} />
              <input type="hidden" name="transaction_type" value={manualTransactionTypeCode} />
              <input type="hidden" name="occurred_at" value={manualDateInputValue} />
              {manualCheckBatchIds.map((transactionId) => (
                <input key={transactionId} type="hidden" name="receipt_batch_transaction_ids" value={transactionId} />
              ))}
              {manualIsCashFlow ? (
                <>
                  {manualAmountInputValue ? (
                    <input type="hidden" name="amount_incl_vat" value={manualAmountInputValue} />
                  ) : (
                    <label>
                      {t("admin.client_detail.transaction_amount_required")}
                      <input type="number" name="amount_incl_vat" step="0.01" min="0.01" placeholder="0.00" required />
                    </label>
                  )}
                  <input type="hidden" name="vat_rate" value="0" />
                </>
              ) : manualNonCashFlowType ? (
                <ManualTransactionNonCashFlowFields
                  transactionType={manualNonCashFlowType}
                  amountLabel={t("admin.client_detail.transaction_amount_required")}
                  defaultVatRate={manualVatDefault}
                  initialAmountInclVat={manualAmountInputValue}
                  initialVatRate={manualVatInputValue}
                  categories={manualChargeCategories}
                  products={manualChargeProductOptions}
                  currencyCode={client.preferred_currency || "EUR"}
                  language={language}
                />
              ) : null}
              <label>
                {t("admin.client_detail.student_optional")}
                <select name="student_id" defaultValue={manualRepeatStudentId}>
                  <option value="">{t("admin.client_detail.not_specified")}</option>
                  <option value={client.id}>{fullName || client.email}</option>
                  {family.links_as_adult.map((link) => (
                    <option key={link.child.id} value={link.child.id}>
                      {[link.child.first_name, link.child.last_name].filter(Boolean).join(" ") || link.child.email}
                    </option>
                  ))}
                </select>
              </label>
              {manualIsPayment ? (
                <ManualTransactionLegalEntityFields
                  legalEntities={manualTransactionLegalEntities}
                  paymentMethods={manualTransactionPaymentMethods}
                  paymentMethodRequired
                  initialPaymentMethodCode={manualRepeatPaymentMethodCode}
                  initialLegalEntityId={manualRepeatLegalEntityId || null}
                  reconcilableInvoices={manualReconcilableInvoices}
                  initialReconciledInvoiceNoteIds={manualRepeatInvoiceNoteIds}
                  showReconciliation
                  showReceiptEmailOption
                  clientDisplayName={fullName || visibleEmail || client.email}
                  language={language}
                  checkReceiptLocations={checkReceiptLocations}
                  initialCheckReceiptLocationId={manualRepeatCheckReceiptLocationId}
                  checkBatchPreviousCount={manualCheckBatchIds.length}
                />
              ) : (
                <ManualTransactionLegalEntityFields legalEntities={manualTransactionLegalEntities} language={language} />
              )}
              <small className="muted span-2">
                {t("admin.client_detail.legal_entity_help")}
              </small>
              <label>
                {t("admin.client_detail.label_optional")}
                <input
                  type="text"
                  name="label"
                  maxLength={255}
                  defaultValue={manualTransactionDefaultLabel}
                  placeholder={t("admin.client_detail.fees_label_placeholder")}
                />
              </label>
              <label>
                {t("admin.client_detail.reference_optional")}
                <input type="text" name="reference" maxLength={120} placeholder={t("admin.client_detail.reference_placeholder")} />
              </label>
              <label>
                {t("admin.client_detail.description_optional")}
                <textarea
                  name="description"
                  rows={3}
                  maxLength={2000}
                  placeholder={t("admin.client_detail.description_invoice_help")}
                />
              </label>
              {!manualIsCashFlow && manualChargeCategories.length === 0 ? (
                <p className="muted">
                  {t("admin.client_detail.no_catalog_items_help")}{" "}
                  <Link className="mode-link" href="/admin/products">
                    {t("admin.client_detail.products_link")}
                  </Link>
                  .
                </p>
              ) : null}
              <div className="row modal-actions-end transaction-wizard-footer">
                <Link className="reset-link" href={manualStepTwoBackHref}>
                  {t("common.previous")}
                </Link>
                {manualIsPayment ? (
                  <ManualCheckSubmitButtons
                    repeatLabel={language === "en" ? "Save and enter the next check" : "Enregistrer et saisir le chèque suivant"}
                    finishLabel={
                      manualCheckBatchIds.length > 0
                        ? (language === "en" ? "Finish and send the summary" : "Terminer et envoyer le récapitulatif")
                        : manualTransactionSubmitLabel
                    }
                    pendingLabel={language === "en" ? "Saving payment…" : "Enregistrement du paiement…"}
                  />
                ) : (
                  <ClientActionSubmitButton pendingLabel={language === "en" ? "Saving…" : "Enregistrement…"}>
                    {manualTransactionSubmitLabel}
                  </ClientActionSubmitButton>
                )}
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openManualTransactionEditModal && selectedManualTransactionForEdit ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "paiements")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.edit_transaction_title")}</h3>
            {selectedManualTransactionForEdit.payment_method_code === "CHECK" &&
              selectedManualTransactionForEdit.can_edit &&
              ["CHECK_RECEIVED", "CHECK_DEPOSITED"].includes(selectedManualTransactionForEdit.status) ? (
              <form action={reconcileAdminClientChecksAction} className="card grid top-gap-sm">
                <input type="hidden" name="client_id" value={client.id} />
                <h4>Rattacher les chèques existants à une facture</h4>
                <p className="muted">Sélectionnez les chèques et la facture, puis confirmez. Aucun nouveau paiement ne sera créé. Les montants, les dates de dépôt et les statuts d’encaissement seront conservés. Les autres modifications de cette fenêtre ne seront pas enregistrées par ce bouton.</p>
                <label>Facture à couvrir
                  <select name="invoice_note_id" defaultValue="" required>
                    <option value="" disabled>Choisir une facture</option>
                    {reconcilableRangeInvoices.filter((invoice) => invoice.sellerLegalEntityId === selectedManualTransactionForEdit.seller_legal_entity_id).map((invoice) => (
                      <option key={invoice.noteId} value={invoice.noteId}>{invoice.invoiceNumber} · Solde : {invoice.balanceLabel ?? invoice.totalLabel}</option>
                    ))}
                  </select>
                </label>
                <fieldset>
                  <legend>Chèques à rattacher (sélection explicite)</legend>
                  {payments.filter((payment) => payment.source === "MANUAL" && payment.manual_transaction_type === "PAYMENT" &&
                    payment.payment_method_code === "CHECK" && payment.can_edit &&
                    ["CHECK_RECEIVED", "CHECK_DEPOSITED"].includes(payment.status) &&
                    payment.seller_legal_entity_id === selectedManualTransactionForEdit.seller_legal_entity_id &&
                    payment.student_user_id === selectedManualTransactionForEdit.student_user_id).map((payment) => (
                    <label className="checkbox" key={payment.id}>
                      <input type="checkbox" name="transaction_ids" value={payment.id} defaultChecked={payment.id === selectedManualTransactionForEdit.id} />
                      {formatMoney(String(Math.abs(Number(payment.total_incl_vat))), payment.currency, language)} · {payment.description || payment.label}
                    </label>
                  ))}
                </fieldset>
                <ClientActionSubmitButton pendingLabel="Rattachement…">Confirmer le rattachement à la facture</ClientActionSubmitButton>
              </form>
            ) : null}
            {selectedManualTransactionForEdit.can_edit ? (
              <form action={updateAdminClientManualTransactionAction} className="grid top-gap-sm">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="transaction_id" value={selectedManualTransactionForEdit.id} />
                <input type="hidden" name="currency" value={selectedManualTransactionForEdit.currency || client.preferred_currency || "EUR"} />
                <input type="hidden" name="transaction_type" value={editManualTransactionTypeCode} />

                <label>
                  {t("admin.client_detail.student_optional")}
                  <select name="student_id" defaultValue={selectedManualTransactionForEdit.student_user_id ?? ""}>
                    <option value="">{t("admin.client_detail.not_specified")}</option>
                    <option value={client.id}>{fullName || client.email}</option>
                    {family.links_as_adult.map((link) => (
                      <option key={link.child.id} value={link.child.id}>
                        {[link.child.first_name, link.child.last_name].filter(Boolean).join(" ") || link.child.email}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("common.date")}
                  <input type="date" name="occurred_at" defaultValue={editManualOccurredAt} required />
                </label>
                <label>
                  {t("common.amount")} {t("common.ttc")}
                  <input type="number" name="amount_incl_vat" step="0.01" min="0.01" defaultValue={editManualAmountAbs} required />
                </label>
                {!editManualIsPayment ? (
                  <label>
                    {t("common.vat")} (%)
                    <input type="number" name="vat_rate" step="0.001" min="0" max="100" defaultValue={editManualVatDefault} required />
                  </label>
                ) : (
                  <input type="hidden" name="vat_rate" value="0" />
                )}
                {editManualIsPayment ? (
                  <ManualTransactionLegalEntityFields
                    legalEntities={manualTransactionLegalEntities}
                    paymentMethods={manualTransactionPaymentMethods}
                    paymentMethodRequired
                    initialPaymentMethodCode={selectedManualTransactionForEdit.payment_method_code ?? ""}
                    initialLegalEntityId={selectedManualTransactionForEdit.seller_legal_entity_id}
                    language={language}
                  />
                ) : (
                  <ManualTransactionLegalEntityFields
                    legalEntities={manualTransactionLegalEntities}
                    initialLegalEntityId={selectedManualTransactionForEdit.seller_legal_entity_id}
                    language={language}
                  />
                )}
                <label>
                  {t("admin.client_detail.label_optional")}
                  <input type="text" name="label" maxLength={255} defaultValue={selectedManualTransactionForEdit.label} />
                </label>
                {!editManualIsPayment ? (
                  <label>
                    {t("admin.client_detail.category_required")}
                    <select
                      name="category"
                      defaultValue={editManualCategoryIsConfigured ? editManualCategory : ""}
                      required
                    >
                      <option value="">{t("admin.client_detail.manual_select_placeholder")}</option>
                      {manualChargeCategories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                    {editManualCategory && !editManualCategoryIsConfigured ? (
                      <small className="muted">
                        {t("admin.client_detail.unknown_transaction_category_help", { category: editManualCategory })}
                      </small>
                    ) : null}
                  </label>
                ) : null}
                <label>
                  {t("admin.client_detail.reference_optional")}
                  <input type="text" name="reference" maxLength={120} defaultValue={selectedManualTransactionForEdit.reference ?? ""} />
                </label>
                <label>
                  {t("admin.client_detail.description_optional")}
                  <textarea name="description" rows={3} maxLength={2000} defaultValue={selectedManualTransactionForEdit.description ?? ""} />
                </label>

                <div className="row modal-actions-end">
                  <Link className="reset-link" href={tabHref(client.id, "paiements")}>
                    {t("common.cancel")}
                  </Link>
                  <button type="submit">{t("common.save")}</button>
                </div>
              </form>
            ) : (
              <div className="stack-sm top-gap-sm">
                <p className="muted">
                  {t("admin.client_detail.transaction_locked_help")}
                </p>
                {selectedManualTransactionForEdit.locked_by_invoice_number ? (
                  <p className="muted">{t("admin.client_detail.invoice_prefix", { invoice: selectedManualTransactionForEdit.locked_by_invoice_number })}</p>
                ) : null}
                <div className="row modal-actions-end">
                  <Link className="reset-link" href={tabHref(client.id, "paiements")}>
                    {t("common.close")}
                  </Link>
                </div>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") && paymentModalAction === "invoice_range" ? (
        <section className="modal-overlay">
          <article className="modal-panel invoice-wizard-modal">
            <Link className="modal-close-x" href={invoiceWizardCloseHref} aria-label={t("common.close")}>
              ×
            </Link>
            <header className="invoice-wizard-header">
              <h3 className="modal-title">{t("admin.client_detail.new_invoice_title")}</h3>
              {invoiceGenerationMode === "MANUAL" ? (
                <div className="purchase-wizard-stepper" aria-label={t("admin.client_detail.invoice_progress_aria")}>
                  <span className={openInvoiceRangeStepOne ? "active" : ""}>{t("admin.client_detail.invoice_step_details")}</span>
                  <span className={openInvoiceRangeStepTwo ? "active" : ""}>{t("admin.client_detail.invoice_step_preferences")}</span>
                </div>
              ) : (
                <p className="muted">{t("admin.client_detail.invoice_auto_help")}</p>
              )}
            </header>
            <div className="invoice-wizard-body">
              {invoiceErrorFields.length > 0 ? <ModalFirstErrorFocus modalBodySelector=".invoice-wizard-body" /> : null}

              <div className="invoice-mode-segmented span-2">
                <Link className={`invoice-mode-chip ${invoiceGenerationMode === "MANUAL" ? "active" : ""}`} href={invoiceWizardModeHref("MANUAL")}>
                  <strong>{t("admin.client_detail.invoice_mode_manual_title")}</strong>
                  <small className="muted">{t("admin.client_detail.invoice_mode_manual_help")}</small>
                </Link>
                <Link className={`invoice-mode-chip ${invoiceGenerationMode === "AUTO" ? "active" : ""}`} href={invoiceWizardModeHref("AUTO")}>
                  <strong>{t("admin.client_detail.invoice_mode_auto_title")}</strong>
                  <small className="muted">{t("admin.client_detail.invoice_mode_auto_help")}</small>
                </Link>
              </div>

              {invoiceModalGlobalError ? (
                <section className="flash-err invoice-modal-error" role="alert">
                  {invoiceModalGlobalError}
                </section>
              ) : invoiceErrorFields.length > 0 ? (
                <section className="flash-err invoice-modal-error" role="alert">
                  {t("admin.client_detail.invoice_fix_errors")}
                </section>
              ) : null}

              {invoiceGenerationMode === "AUTO" ? (
                <form action={createAdminClientRangeInvoiceAction} id="invoice-wizard-form-main" className="grid top-gap-sm invoice-wizard-form">
                  <input type="hidden" name="client_id" value={client.id} />
                  <input type="hidden" name="return_tab" value={paymentReturnTab} />
                  <input type="hidden" name="invoice_step" value="1" />
                  <input type="hidden" name="generation_mode" value="AUTO" />
                  <input type="hidden" name="layout" value={invoiceLayout} />
                  <input type="hidden" name="group_adjustments_by_type" value={invoiceGroupAdjustmentsByType ? "true" : "false"} />
                  <input type="hidden" name="include_discount_adjustments" value={invoiceIncludeDiscountAdjustments ? "true" : "false"} />
                  <input type="hidden" name="include_supplement_adjustments" value={invoiceIncludeSupplementAdjustments ? "true" : "false"} />
                  <input type="hidden" name="public_note" value={invoicePublicNote} />
                  <input type="hidden" name="private_note" value={invoicePrivateNote} />

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_section_cycle")}</h4>
                    <div className="grid cols-2">
                      <label>
                        {t("admin.client_detail.invoice_cycle_start_required")}
                        <input
                          type="date"
                          name="auto_cycle_start_date"
                          defaultValue={invoiceAutoCycleStartDateInputValue}
                          aria-invalid={invoiceFieldInvalid("auto_cycle_start_date")}
                          data-invalid={invoiceFieldInvalid("auto_cycle_start_date") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("auto_cycle_start_date")}
                        />
                        {invoiceFieldError("auto_cycle_start_date") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("auto_cycle_start_date")}
                          </small>
                        ) : null}
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_frequency_required")}
                        <select name="auto_frequency" defaultValue={invoiceAutoFrequency}>
                          <option value="MONTHLY">{t("admin.client_detail.invoice_frequency_monthly")}</option>
                          <option value="BIMONTHLY">{t("admin.client_detail.invoice_frequency_bimonthly")}</option>
                          <option value="QUARTERLY">{t("admin.client_detail.invoice_frequency_quarterly")}</option>
                          <option value="YEARLY">{t("admin.client_detail.invoice_frequency_yearly")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_billing_mode_required")}
                        <select name="auto_billing_timing" defaultValue={invoiceAutoBillingTiming}>
                          <option value="UPCOMING_LESSONS">{t("admin.client_detail.invoice_billing_upcoming")}</option>
                          <option value="PREVIOUS_LESSONS">{t("admin.client_detail.invoice_billing_previous")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_legal_entity_required")}
                        <select
                          name="auto_legal_entity_id"
                          defaultValue={invoiceAutoLegalEntityIdInputValue}
                          aria-invalid={invoiceFieldInvalid("auto_legal_entity_id")}
                          data-invalid={invoiceFieldInvalid("auto_legal_entity_id") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("auto_legal_entity_id")}
                        >
                          <option value="">{t("admin.quote_config.select_option")}</option>
                          {legalEntities.map((entity) => (
                            <option key={entity.id} value={entity.id}>
                              {entity.name}
                            </option>
                          ))}
                        </select>
                        {invoiceFieldError("auto_legal_entity_id") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("auto_legal_entity_id")}
                          </small>
                        ) : null}
                      </label>
                    </div>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_due_section")}</h4>
                    <div className="grid cols-2">
                      <label>
                        {t("admin.client_detail.invoice_due_rule_required")}
                        <select name="auto_due_date_rule_type" defaultValue={invoiceAutoDueDateRuleType}>
                          <option value="SAME_DAY_ISSUE">{t("admin.client_detail.invoice_due_same_day")}</option>
                          <option value="X_DAYS_AFTER_ISSUE">{t("admin.client_detail.invoice_due_after_days")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_due_days_label")}
                        <input
                          type="number"
                          name="auto_due_date_days_offset"
                          min={0}
                          max={365}
                          step={1}
                          defaultValue={String(invoiceAutoDueDateDaysOffset)}
                          aria-invalid={invoiceFieldInvalid("auto_due_date_days_offset")}
                          data-invalid={invoiceFieldInvalid("auto_due_date_days_offset") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("auto_due_date_days_offset")}
                        />
                        {invoiceFieldError("auto_due_date_days_offset") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("auto_due_date_days_offset")}
                          </small>
                        ) : null}
                      </label>
                    </div>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_content_section")}</h4>
                    <div className="grid cols-2">
                      <label>
                        {t("admin.client_detail.invoice_pending_lines")}
                        <select name="include_pending" defaultValue={invoiceIncludePending ? "true" : "false"}>
                          <option value="true">{t("admin.client_detail.invoice_include")}</option>
                          <option value="false">{t("admin.client_detail.invoice_exclude")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_cancelled_lines")}
                        <select name="include_cancelled" defaultValue={invoiceIncludeCancelled ? "true" : "false"}>
                          <option value="false">{t("admin.client_detail.invoice_exclude")}</option>
                          <option value="true">{t("admin.client_detail.invoice_include")}</option>
                        </select>
                      </label>
                    </div>
                  </article>

                  <AutomaticInvoicePreview
                    language={language}
                    today={todayInputValue}
                    initialCycleStart={invoiceAutoCycleStartDateInputValue}
                    initialFrequency={invoiceAutoFrequency}
                    initialBillingTiming={invoiceAutoBillingTiming}
                    initialDueDateRule={invoiceAutoDueDateRuleType}
                    initialDueDateDaysOffset={invoiceAutoDueDateDaysOffset}
                  />
                </form>
              ) : null}

              {invoiceGenerationMode === "MANUAL" && openInvoiceRangeStepOne ? (
                <form method="get" action={`/admin/clients/${client.id}`} id="invoice-wizard-form-main" className="grid top-gap-sm invoice-wizard-form">
                  <input type="hidden" name="tab" value={paymentReturnTab} />
                  <input type="hidden" name="payment_modal" value="invoice_range" />
                  <input type="hidden" name="payment_return_tab" value={paymentReturnTab} />
                  <input type="hidden" name="invoice_step" value="2" />
                  <input type="hidden" name="generation_mode" value="MANUAL" />
                  {paymentReturnTab === "paiements" ? <input type="hidden" name="balance_date" value={selectedBalanceDate} /> : null}
                  {paymentFilterQuery ? <input type="hidden" name="payment_filter_q" value={paymentFilterQuery} /> : null}
                  {paymentFilterAmountRaw ? <input type="hidden" name="payment_filter_amount" value={paymentFilterAmountRaw} /> : null}
                  <input type="hidden" name="layout" value={invoiceLayout} />
                  <input type="hidden" name="group_adjustments_by_type" value={invoiceGroupAdjustmentsByType ? "true" : "false"} />
                  <input type="hidden" name="include_discount_adjustments" value={invoiceIncludeDiscountAdjustments ? "true" : "false"} />
                  <input type="hidden" name="include_supplement_adjustments" value={invoiceIncludeSupplementAdjustments ? "true" : "false"} />
                  <input type="hidden" name="auto_cycle_start_date" value={invoiceAutoCycleStartDateInputValue} />
                  <input type="hidden" name="auto_frequency" value={invoiceAutoFrequency} />
                  <input type="hidden" name="auto_billing_timing" value={invoiceAutoBillingTiming} />
                  <input type="hidden" name="auto_due_date_rule_type" value={invoiceAutoDueDateRuleType} />
                  <input type="hidden" name="auto_due_date_days_offset" value={String(invoiceAutoDueDateDaysOffset)} />
                  <input type="hidden" name="auto_legal_entity_id" value={invoiceAutoLegalEntityIdInputValue} />
                  <input type="hidden" name="public_note" value={invoicePublicNote} />
                  <input type="hidden" name="private_note" value={invoicePrivateNote} />

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_date_section")}</h4>
                    <label>
                      {t("admin.client_detail.invoice_issue_date_required")}
                      <input
                        type="date"
                        name="issued_date"
                        defaultValue={invoiceIssuedDateInputValue}
                        aria-invalid={invoiceFieldInvalid("issued_date")}
                        data-invalid={invoiceFieldInvalid("issued_date") ? "true" : undefined}
                        autoFocus={invoiceFieldAutoFocus("issued_date")}
                      />
                      {invoiceFieldError("issued_date") ? (
                        <small className="invoice-field-error" role="alert">
                          {invoiceFieldError("issued_date")}
                        </small>
                      ) : null}
                    </label>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_content_period_section")}</h4>
                    <div className="grid cols-2">
                      <label>
                        {t("admin.client_detail.invoice_start_date")}
                        <input
                          type="date"
                          name="start_date"
                          defaultValue={invoiceStartDateInputValue}
                          aria-invalid={invoiceFieldInvalid("start_date")}
                          data-invalid={invoiceFieldInvalid("start_date") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("start_date")}
                        />
                        {invoiceFieldError("start_date") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("start_date")}
                          </small>
                        ) : null}
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_end_date")}
                        <input
                          type="date"
                          name="end_date"
                          defaultValue={invoiceEndDateInputValue}
                          aria-invalid={invoiceFieldInvalid("end_date")}
                          data-invalid={invoiceFieldInvalid("end_date") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("end_date")}
                        />
                        {invoiceFieldError("end_date") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("end_date")}
                          </small>
                        ) : null}
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_due_date")}
                        <input
                          type="date"
                          name="due_date"
                          defaultValue={invoiceDueDateInputValue}
                          aria-invalid={invoiceFieldInvalid("due_date")}
                          data-invalid={invoiceFieldInvalid("due_date") ? "true" : undefined}
                          autoFocus={invoiceFieldAutoFocus("due_date")}
                        />
                        {invoiceFieldError("due_date") ? (
                          <small className="invoice-field-error" role="alert">
                            {invoiceFieldError("due_date")}
                          </small>
                        ) : null}
                      </label>
                      <label className="checkbox">
                        <input type="checkbox" name="no_due_date" value="true" defaultChecked={invoiceNoDueDate} />
                        {t("admin.client_detail.invoice_no_due_date")}
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_pending_lines")}
                        <select name="include_pending" defaultValue={invoiceIncludePending ? "true" : "false"}>
                          <option value="true">{t("admin.client_detail.invoice_include")}</option>
                          <option value="false">{t("admin.client_detail.invoice_exclude")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.client_detail.invoice_cancelled_lines")}
                        <select name="include_cancelled" defaultValue={invoiceIncludeCancelled ? "true" : "false"}>
                          <option value="false">{t("admin.client_detail.invoice_exclude")}</option>
                          <option value="true">{t("admin.client_detail.invoice_include")}</option>
                        </select>
                      </label>
                    </div>
                  </article>
                </form>
              ) : null}

              {invoiceGenerationMode === "MANUAL" && openInvoiceRangeStepTwo ? (
                <form action={createAdminClientRangeInvoiceAction} id="invoice-wizard-form-main" className="grid top-gap-sm invoice-wizard-form">
                  <input type="hidden" name="client_id" value={client.id} />
                  <input type="hidden" name="return_tab" value={paymentReturnTab} />
                  <input type="hidden" name="invoice_step" value="2" />
                  <input type="hidden" name="generation_mode" value="MANUAL" />
                  <input type="hidden" name="issued_date" value={invoiceIssuedDateInputValue} />
                  <input type="hidden" name="start_date" value={invoiceStartDateInputValue} />
                  <input type="hidden" name="end_date" value={invoiceEndDateInputValue} />
                  <input type="hidden" name="due_date" value={invoiceNoDueDate ? invoiceIssuedDateInputValue : invoiceDueDateInputValue} />
                  <input type="hidden" name="no_due_date" value={invoiceNoDueDate ? "on" : "off"} />
                  <input type="hidden" name="include_pending" value={invoiceIncludePending ? "true" : "false"} />
                  <input type="hidden" name="include_cancelled" value={invoiceIncludeCancelled ? "true" : "false"} />
                  <input type="hidden" name="auto_cycle_start_date" value={invoiceAutoCycleStartDateInputValue} />
                  <input type="hidden" name="auto_frequency" value={invoiceAutoFrequency} />
                  <input type="hidden" name="auto_billing_timing" value={invoiceAutoBillingTiming} />
                  <input type="hidden" name="auto_due_date_rule_type" value={invoiceAutoDueDateRuleType} />
                  <input type="hidden" name="auto_due_date_days_offset" value={String(invoiceAutoDueDateDaysOffset)} />
                  <input type="hidden" name="auto_legal_entity_id" value={invoiceAutoLegalEntityIdInputValue} />
                  <input type="hidden" name="line_selection_enabled" value="1" />

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_lines_to_bill")}</h4>
                    {invoiceCandidatePayments.length === 0 ? (
                      <p className="muted">{t("admin.client_detail.invoice_no_lines_available")}</p>
                    ) : (
                      <InvoiceLineSelection
                        rows={invoiceSelectionRows}
                        initialSelectedKeys={[...invoiceSelectedPaymentKeys]}
                        locale={localeForUiLanguage(language)}
                        labels={{
                          quickSelection: t("admin.client_detail.invoice_quick_selection"),
                          quickSelectionHelp: t("admin.client_detail.invoice_quick_selection_help"),
                          selectAll: t("admin.client_detail.invoice_select_all"),
                          deselectAll: t("admin.client_detail.invoice_deselect_all"),
                          selectOnly: t("admin.client_detail.invoice_select_only"),
                          selectedCount: t("admin.client_detail.invoice_selected_count"),
                          lineSingular: t("admin.client_detail.invoice_line_singular"),
                          linePlural: t("admin.client_detail.invoice_line_plural"),
                          include: t("admin.client_detail.invoice_include_column"),
                          participant: t("admin.client_detail.invoice_participant_column"),
                          date: t("common.date"),
                          type: t("common.type"),
                          description: t("admin.client_detail.invoices_column_label"),
                          status: t("common.status"),
                          total: t("common.total"),
                        }}
                      />
                    )}
                    <p className="muted">{t("admin.client_detail.invoice_line_selection_help")}</p>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_display_style_section")}</h4>
                    <label>
                      {t("admin.client_detail.invoice_style_label")}
                      <select name="layout" defaultValue={invoiceLayout}>
                        <option value="DETAILED">{t("admin.client_detail.invoice_style_detailed")}</option>
                        <option value="COMPILED">{t("admin.client_detail.invoice_style_compiled")}</option>
                      </select>
                    </label>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("admin.client_detail.invoice_preferences_section")}</h4>
                    <input type="hidden" name="group_adjustments_by_type" value="off" />
                    <label className="checkbox">
                      <input type="checkbox" name="group_adjustments_by_type" value="on" defaultChecked={invoiceGroupAdjustmentsByType} />
                      {t("admin.client_detail.invoice_group_adjustments")}
                    </label>
                    <input type="hidden" name="include_discount_adjustments" value="off" />
                    <label className="checkbox">
                      <input type="checkbox" name="include_discount_adjustments" value="on" defaultChecked={invoiceIncludeDiscountAdjustments} />
                      {t("admin.client_detail.invoice_include_discounts")}
                    </label>
                    <input type="hidden" name="include_supplement_adjustments" value="off" />
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        name="include_supplement_adjustments"
                        value="on"
                        defaultChecked={invoiceIncludeSupplementAdjustments}
                      />
                      {t("admin.client_detail.invoice_include_supplements")}
                    </label>
                  </article>

                  <article className="card modal-card invoice-wizard-card span-2">
                    <h4>{t("common.notes")}</h4>
                    <label>
                      {t("admin.client_detail.invoice_public_note_optional")}
                      <textarea
                        name="public_note"
                        rows={3}
                        maxLength={2000}
                        defaultValue={invoicePublicNote}
                        placeholder={t("admin.client_detail.invoice_public_note_placeholder")}
                      />
                    </label>
                    <label>
                      {t("admin.client_detail.invoice_private_note_optional")}
                      <textarea
                        name="private_note"
                        rows={3}
                        maxLength={2000}
                        defaultValue={invoicePrivateNote}
                        placeholder={t("admin.client_detail.invoice_private_note_placeholder")}
                      />
                    </label>
                  </article>
                </form>
              ) : null}
            </div>

            <footer className="row spread invoice-wizard-footer">
              <Link className="reset-link" href={invoiceWizardCloseHref}>
                {t("common.cancel")}
              </Link>
              {invoiceGenerationMode === "AUTO" ? (
                <button type="submit" form="invoice-wizard-form-main">
                  {t("admin.client_detail.invoice_save_auto_rule")}
                </button>
              ) : openInvoiceRangeStepOne ? (
                <button type="submit" form="invoice-wizard-form-main">
                  {t("common.next")}
                </button>
              ) : (
                <div className="row modal-actions-end">
                  <Link className="reset-link" href={invoiceWizardBackToStepOneHref}>
                    {t("common.previous")}
                  </Link>
                  <button type="submit" form="invoice-wizard-form-main">
                    {t("admin.client_detail.invoice_create")}
                  </button>
                </div>
              )}
            </footer>
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") &&
      paymentModalAction === "invoice_bank_transfer" &&
      selectedRangeInvoiceForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">Receptionner un virement</h3>
            <p className="muted">
              Facture {selectedRangeInvoiceForModal.invoiceNumber} | {selectedRangeInvoiceForModal.totalLabel}
            </p>
            <form action={markAdminClientRangeInvoiceManualBankTransferPaidAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="note_id" value={selectedRangeInvoiceForModal.noteId} />
              <input type="hidden" name="return_tab" value={paymentReturnTab} />
              <label className="span-2">
                Reference du virement
                <input
                  type="text"
                  name="reference"
                  maxLength={120}
                  required
                  autoFocus
                  placeholder="Ex. nom du client, reference bancaire, libelle recu"
                />
              </label>
              <p className="muted span-2">
                Cette action cree un paiement manuel par virement, rapproche la facture et la marque comme payee.
              </p>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">Valider le virement</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") &&
      paymentModalAction === "invoice_email" &&
      selectedRangeInvoiceForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.invoice_email_title")}</h3>
            <p className="muted">
              {t("admin.client_detail.invoice_email_help", { invoice: selectedRangeInvoiceForModal.invoiceNumber })}
            </p>
            {includeInvoiceChangeSummary ? (
              <form method="get" action={`/admin/clients/${client.id}`} className="grid top-gap-sm">
                <input type="hidden" name="tab" value={paymentReturnTab} />
                <input type="hidden" name="payment_modal" value="invoice_email" />
                <input type="hidden" name="payment_return_tab" value={paymentReturnTab} />
                <input type="hidden" name="invoice_note_id" value={selectedRangeInvoiceForModal.noteId} />
                <input type="hidden" name="invoice_email_kind" value={invoiceEmailKind} />
                <input type="hidden" name="include_change_summary" value="1" />
                <label className="span-2">
                  Facture de comparaison
                  <select name="reference_invoice_note_id" defaultValue={selectedReferenceInvoiceNoteId}>
                    {invoiceChangeSummaryReferenceOptions.length === 0 ? (
                      <option value="">Aucune facture anterieure disponible</option>
                    ) : null}
                    {invoiceChangeSummaryReferenceOptions.map((row) => (
                      <option key={row.noteId} value={row.noteId}>
                        {row.invoiceNumber} | {formatDateOnlyNumeric(row.occurredAt)} | {invoiceStatusLabel(row.status, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="row modal-actions-end span-2">
                  <button type="submit" className="secondary">
                    Actualiser l'aperçu
                  </button>
                </div>
              </form>
            ) : null}
            <form action={sendAdminClientRangeInvoiceEmailAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="note_id" value={selectedRangeInvoiceForModal.noteId} />
              <input type="hidden" name="return_tab" value={paymentReturnTab} />
              <input type="hidden" name="include_change_summary" value={includeInvoiceChangeSummary ? "1" : "0"} />
              <input type="hidden" name="reference_invoice_note_id" value={selectedReferenceInvoiceNoteId} />
              <label>
                {t("admin.client_detail.invoice_send_type")}
                <select name="kind" defaultValue={invoiceEmailKind}>
                  <option value="INVOICE">{t("admin.client_detail.invoice_send_type_invoice")}</option>
                  <option value="REMINDER">{t("admin.client_detail.invoice_send_type_reminder")}</option>
                </select>
              </label>
              <div className="span-2 row">
                <Link
                  className={`mode-link ${includeInvoiceChangeSummary ? "" : "active"}`}
                  href={invoicesHref(client.id, {
                    payment_modal: "invoice_email",
                    payment_return_tab: paymentReturnTab,
                    invoice_note_id: selectedRangeInvoiceForModal.noteId,
                    invoice_email_kind: invoiceEmailKind,
                    include_change_summary: "0",
                  })}
                >
                  Mail standard
                </Link>
                <Link
                  className={`mode-link ${includeInvoiceChangeSummary ? "active" : ""}`}
                  href={invoicesHref(client.id, {
                    payment_modal: "invoice_email",
                    payment_return_tab: paymentReturnTab,
                    invoice_note_id: selectedRangeInvoiceForModal.noteId,
                    invoice_email_kind: invoiceEmailKind,
                    include_change_summary: "1",
                    reference_invoice_note_id: selectedReferenceInvoiceNoteId,
                  })}
                >
                  Avec recapitulatif des changements
                </Link>
              </div>
              <label className="span-2">
                {t("admin.client_detail.invoice_recipients_help")}
                <textarea
                  name="to_emails"
                  rows={3}
                  defaultValue={(invoiceEmailPreview?.to_emails ?? []).join("\n")}
                  placeholder={t("admin.client_detail.email_placeholder")}
                />
              </label>
              <label className="span-2">
                {t("common.subject")}
                <input type="text" name="subject" maxLength={255} defaultValue={invoiceEmailPreview?.subject ?? ""} />
              </label>
              <label className="span-2">
                {t("common.message")}
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  defaultValue={invoiceEmailPreview?.body ?? ""}
                  defaultFormat={invoiceEmailPreview?.body_format ?? "TEXT"}
                  rows={12}
                  maxLength={20000}
                  placeholder={t("admin.client_detail.email_body_placeholder")}
                  language={language}
                />
              </label>
              <fieldset className="span-2 invoice-option-box">
                <label className="checkbox-line">
                  <input type="checkbox" name="send_sms" value="1" />
                  Envoyer aussi un SMS
                </label>
                <label>
                  Numero SMS
                  <input type="text" name="sms_phone" defaultValue={invoiceSmsDefaultPhone} maxLength={40} placeholder="+33600000000" />
                </label>
                <label>
                  Message SMS
                  <textarea
                    name="sms_body"
                    rows={3}
                    maxLength={1000}
                    defaultValue={invoiceEmailPreview?.sms_body ?? ""}
                    placeholder="Message SMS facture"
                  />
                </label>
              </fieldset>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  {t("common.cancel")}
                </Link>
                <button type="submit">{t("common.send")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") && selectedPaymentForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.refund_payment_title")}</h3>
            <p className="muted">
              {selectedPaymentForModal.label} | {formatMoney(selectedPaymentForModal.total_incl_vat, selectedPaymentForModal.currency, language)}
            </p>
            <form action={refundAdminClientPaymentAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="payment_source" value={selectedPaymentForModal.source.toUpperCase()} />
              <input type="hidden" name="payment_id" value={selectedPaymentForModal.id} />
              <input type="hidden" name="return_tab" value={paymentReturnTab} />
              <label>
                {t("admin.client_detail.refund_reason_optional")}
                <textarea name="reason" rows={3} maxLength={1000} placeholder={t("admin.client_detail.refund_reason_placeholder")} />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  {t("common.cancel")}
                </Link>
                <button type="submit" className="danger">
                  {t("admin.client_detail.refund_confirm")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "reservations" && selectedBookingReceiptForRefund ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "reservations")} aria-label={t("common.close")}>
              ×
            </Link>
            <h3 className="modal-title">{t("admin.client_detail.booking_refund_title")}</h3>
            <p className="muted">
              {selectedBookingReceiptForRefund.session_title} |{" "}
              {formatMoney(
                selectedBookingReceiptForRefund.payment_received_amount ??
                  selectedBookingReceiptForRefund.total_incl_vat_snapshot,
                selectedBookingReceiptForRefund.currency_snapshot,
                language,
              )}
            </p>
            <div className="stack-xs">
              <small className="muted">{t("admin.client_detail.booking_refund_help")}</small>
              <small className="muted">{t("admin.client_detail.booking_refund_help_email")}</small>
            </div>
            <form action={refundAdminClientPaymentReceiptAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="receipt_id" value={selectedBookingReceiptForRefund.payment_receipt_id ?? ""} />
              <input type="hidden" name="return_tab" value="reservations" />
              <label>
                {t("admin.client_detail.refund_reason_optional")}
                <textarea name="reason" rows={3} maxLength={1000} placeholder={t("admin.client_detail.booking_refund_reason_placeholder")} />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "reservations")}>
                  {uiText(language, "common.cancel")}
                </Link>
                <button type="submit" className="danger">
                  {t("admin.client_detail.booking_refund_confirm")}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "reservations" ? (
        <section className="admin-page-grid">
          {makeupSummaries.map((summary) => (
            <article className="card" key={summary.user_id}>
              <div className="row spread">
                <div>
                  <h3>{t("admin.client_detail.makeup_pass_title")}</h3>
                  <p className="muted">{summary.display_name}</p>
                </div>
                <span className="badge">
                  {t("admin.client_detail.makeup_pass_balance", {
                    remaining: summary.credits_remaining,
                    initial: summary.credits_initial,
                  })}
                </span>
              </div>
              <p>{t("admin.client_detail.makeup_pending_count", { count: summary.pending_makeups.length })}</p>
              {summary.pending_makeups.map((credit) => (
                <article className="item" key={credit.id}>
                  <strong>{credit.original_session_title}</strong>
                  <p className="muted">{formatDate(credit.original_session_start_at_utc, language)}</p>
                  <ProgramMakeup studentId={summary.user_id} requestId={credit.id} studentName={summary.display_name} />
                </article>
              ))}
              {summary.history.filter(credit => credit.status === "BOOKED").map(credit => (
                <article className="item" key={credit.id}>
                  <strong>Rattrapage programmé</strong>
                  <p>Absence : {credit.original_session_title} · {formatDate(credit.original_session_start_at_utc, language)}</p>
                  <p>Remplacement : {credit.reserved_session_title} · {credit.reserved_session_start_at_utc ? formatDate(credit.reserved_session_start_at_utc, language) : ""} · {credit.reserved_location}</p>
                  {credit.replacement_covered_by_pass ? <span className="badge">Sans supplément</span> : null}
                </article>
              ))}
            </article>
          ))}
          <section className="grid cols-2">
            <article className="card">
              <h3>{t("admin.client_detail.bookings_stats_title")}</h3>
              <div className="list">
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_attendance_rate")}</span>
                  <strong>{formatPercent(attendanceRate)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_upcoming_count")}</span>
                  <strong>{upcomingBookings.length}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_history_count")}</span>
                  <strong>{pastBookings.length}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_payments_received_count")}</span>
                  <strong>{paymentsReceivedCount}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_included_plan_count")}</span>
                  <strong>{includedPlanBookingsCount}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">{t("admin.client_detail.bookings_final_invoices_generated_count")}</span>
                  <strong>{finalInvoicesGeneratedCount}</strong>
                </article>
              </div>

              <form action={adminClientActionPlaceholder} className="grid">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="language" value={language} />
                <input type="hidden" name="action_name" value={t("admin.client_detail.attach_course")} />
                <button type="submit">{t("admin.client_detail.attach_course")}</button>
              </form>
            </article>

            <article className="card">
              <h3>{t("admin.client_detail.bookings_schedule_title")}</h3>
              <h4>{t("admin.client_detail.upcoming_lessons")}</h4>
              {upcomingBookings.length === 0 ? (
                <p className="muted">{t("admin.client_detail.no_upcoming_bookings")}</p>
              ) : (
                <div className="list">
                  {upcomingBookings.slice(0, 12).map((row) => (
                    <article key={row.id} className="item">
                      <div className="row spread">
                        <strong>{row.session_title}</strong>
                        <span className={`status-pill ${statusClass(row.status)}`}>{bookingStatusLabel(row.status, language)}</span>
                      </div>
                      <p className="muted">
                        {formatDate(row.session_start_at_utc, language)} | {row.course_type_name} | {row.location_name}
                      </p>
                    </article>
                  ))}
                </div>
              )}

              <h4>{t("admin.client_detail.recent_history")}</h4>
              {pastBookings.length === 0 ? (
                <p className="muted">{t("admin.client_detail.no_recent_history")}</p>
              ) : (
                <div className="list">
                  {pastBookings.slice(0, 10).map((row) => (
                    <article key={row.id} className="item row spread">
                      <div>
                        <strong>{row.session_title}</strong>
                        <p className="muted">{formatDate(row.session_start_at_utc, language)}</p>
                      </div>
                      <span className={`status-pill ${statusClass(row.status)}`}>{bookingStatusLabel(row.status, language)}</span>
                    </article>
                  ))}
                </div>
              )}
            </article>
          </section>

          <article className="card">
            <div className="row spread">
              <div className="stack-xs">
                <h3>{t("admin.client_detail.booking_billing_title")}</h3>
                <p className="muted">{t("admin.client_detail.booking_billing_help")}</p>
              </div>
            </div>

            <div className="booking-billing-overview">
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_payments_received")}</span>
                <strong className="booking-billing-card-value">{paymentsReceivedCount}</strong>
                <small className="muted">{t("admin.client_detail.booking_overview_payments_received_help")}</small>
              </article>
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_included_plan")}</span>
                <strong className="booking-billing-card-value">{includedPlanBookingsCount}</strong>
                <small className="muted">{t("admin.client_detail.booking_overview_included_plan_help")}</small>
              </article>
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_receipts_sent")}</span>
                <strong className="booking-billing-card-value">{receiptsSentCount}</strong>
                <small className="muted">{t("admin.client_detail.booking_overview_receipts_sent_help")}</small>
              </article>
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_refunds_recorded")}</span>
                <strong className="booking-billing-card-value">{refundsRecordedCount}</strong>
                <small className="muted">{t("admin.client_detail.booking_overview_refunds_recorded_help")}</small>
              </article>
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_final_invoices_generated")}</span>
                <strong className="booking-billing-card-value">{finalInvoicesGeneratedCount}</strong>
                <small className="muted">{t("admin.client_detail.booking_overview_final_invoices_generated_help")}</small>
              </article>
              <article className="booking-billing-card">
                <span className="booking-billing-card-label">{t("admin.client_detail.booking_overview_final_invoices_to_issue")}</span>
                <strong className="booking-billing-card-value">{finalInvoicesReadyCount}</strong>
                <small className="muted">
                  {t("admin.client_detail.booking_overview_final_invoices_to_issue_help", {
                    waiting: finalInvoicesWaitingCount,
                    ready: finalInvoicesReadyCount,
                  })}
                </small>
              </article>
            </div>

            {reservationRows.length === 0 ? (
              <p className="muted">{t("admin.client_detail.no_booking_for_client")}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{uiText(language, "common.date")}</th>
                      <th>{t("admin.client_detail.service_column")}</th>
                      <th>{t("admin.client_detail.booking_column")}</th>
                      <th>{t("admin.client_detail.financial_follow_up_column")}</th>
                      <th>{uiText(language, "common.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reservationRows.map((row) => {
                      const canGenerateFinalInvoice = canGenerateFinalInvoiceForBooking(row);
                      const workflowSteps = bookingWorkflowSteps(row, language);
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="stack-xs">
                              <strong>{formatDateOnlyNumeric(row.scheduled_service_date ?? row.session_start_at_utc, language)}</strong>
                              <small className="muted">{formatDate(row.session_start_at_utc, language)}</small>
                              {row.service_completed_at ? (
                                <small className="muted">
                                  {t("admin.client_detail.completed_on", { date: formatDate(row.service_completed_at, language) })}
                                </small>
                              ) : null}
                            </div>
                          </td>
                          <td>
                            <div className="stack-xs">
                              <strong>{row.session_title}</strong>
                              <small className="muted">
                                {row.course_type_name} | {row.location_name}
                              </small>
                              <small className="muted">
                                {t("admin.client_detail.service_rate_vat", {
                                  amount: formatMoney(row.total_incl_vat_snapshot, row.currency_snapshot, language),
                                  vat: formatVatRateLabel(row.vat_rate_snapshot),
                                })}
                              </small>
                              {row.pricing_snapshot_locked ? (
                                <small
                                  className="muted"
                                  title={row.pricing_source_snapshot ?? undefined}
                                >
                                  {language === "en" ? "Locked price" : "Tarif figé"}
                                  {row.pricing_channel_snapshot ? ` · ${row.pricing_channel_snapshot}` : ""}
                                  {row.price_book_version_snapshot ? ` · ${row.price_book_version_snapshot}` : ""}
                                </small>
                              ) : null}
                            </div>
                          </td>
                          <td>
                            <div className="stack-xs">
                              <span className={`status-pill ${statusClass(row.status)}`}>{bookingStatusLabel(row.status, language)}</span>
                              <small className="muted">
                                {t("admin.client_detail.session_prefix", { status: bookingStatusLabel(row.session_status, language) })}
                              </small>
                            </div>
                          </td>
                          <td>
                            <div className="booking-billing-progress">
                              {workflowSteps.map((step) => (
                                <article key={step.label} className="booking-billing-step">
                                  <div className="booking-billing-step-head">
                                    <span className="booking-billing-step-label">{step.label}</span>
                                    <span className={`status-pill ${step.toneClass}`}>{step.value}</span>
                                  </div>
                                  <small className="muted">{step.helper}</small>
                                </article>
                              ))}
                            </div>
                          </td>
                          <td>
                            <div className="row payment-row-actions">
                              {row.status === "BOOKED" && new Date(row.session_start_at_utc).getTime() > Date.now() ? (
                                <Link className="button secondary" href={`/admin/planning-reorganization?booking_id=${encodeURIComponent(row.id)}&scope=single`}>Déplacer</Link>
                              ) : null}
                              {row.payment_receipt_id &&
                              (row.payment_receipt_status === "COMPLETED" || row.payment_receipt_status === "REFUNDED") ? (
                                <>
                                  <a
                                    className="client-action-icon"
                                    href={paymentReceiptPdfHref(client.id, row.payment_receipt_id)}
                                    title={t("admin.client_detail.download_receipt")}
                                  >
                                    ↓
                                  </a>
                                  {row.payment_receipt_status === "COMPLETED" ? (
                                    <form action={sendAdminClientPaymentReceiptAction}>
                                      <input type="hidden" name="client_id" value={client.id} />
                                      <input type="hidden" name="receipt_id" value={row.payment_receipt_id} />
                                      <input type="hidden" name="return_tab" value="reservations" />
                                      <button type="submit" className="client-action-icon" title={t("admin.client_detail.resend_receipt")}>
                                        ✉
                                      </button>
                                    </form>
                                  ) : null}
                                </>
                              ) : null}
                              {row.payment_receipt_id &&
                              row.payment_receipt_status === "COMPLETED" &&
                              !row.payment_refunded &&
                              !row.final_invoice_generated ? (
                                <Link
                                  className="client-action-icon danger"
                                  href={reservationsHref(client.id, {
                                    payment_modal: "receipt_refund",
                                    payment_id: row.payment_receipt_id,
                                  })}
                                  title={t("admin.client_detail.cancel_and_refund_booking")}
                                >
                                  ↺
                                </Link>
                              ) : null}
                              {row.final_invoice_generated && row.final_invoice_note_id ? (
                                <>
                                  <a
                                    className="client-action-icon"
                                    href={rangeInvoicePdfHref(client.id, row.final_invoice_note_id, true)}
                                    target="_blank"
                                    rel="noreferrer"
                                    title={t("admin.client_detail.view_final_invoice")}
                                  >
                                    V
                                  </a>
                                  <a
                                    className="client-action-icon"
                                    href={rangeInvoicePdfHref(client.id, row.final_invoice_note_id, false)}
                                    title={t("admin.client_detail.download_final_invoice")}
                                  >
                                    ↓
                                  </a>
                                </>
                              ) : null}
                              {canGenerateFinalInvoice ? (
                                <form action={generateAdminClientBookingFinalInvoiceAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="booking_id" value={row.id} />
                                  <input type="hidden" name="return_tab" value="reservations" />
                                  <button type="submit" className="client-action-icon" title={t("admin.client_detail.generate_final_invoice")}>
                                    F
                                  </button>
                                </form>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        </section>
      ) : null}
    </section>
  );
}
