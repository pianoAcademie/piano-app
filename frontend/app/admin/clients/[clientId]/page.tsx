import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  cancelAdminClientInvoiceAction,
  createAdultForChildAction,
  createAdminClientNoteAction,
  createChildForAdultAction,
  adminFinalizeClientPurchaseAction,
  adminClientActionPlaceholder,
  adminOpenClientPurchaseTermsAction,
  cancelAdminClientSubscriptionAction,
  linkExistingFamilyMembersAction,
  adminPurchasePlanForClientAction,
  createAdminClientRangeInvoiceAction,
  createAdminClientManualTransactionAction,
  refundAdminClientPaymentAction,
  sendAdminClientRangeInvoiceEmailAction,
  sendAdminClientPasswordAction,
  setFamilyBillingRecipientAction,
  setupAdminClientSubscriptionBillingAction,
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
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  DEFAULT_COUNTRY,
  DEFAULT_CURRENCY,
  DEFAULT_TIMEZONE,
  TIMEZONE_OPTIONS,
  labelFromOptions,
} from "../../../../lib/reference-data";
import RichMessageEditor from "../../../../components/rich-message-editor";
import type {
  AdminClientBookingOut,
  AdminClientFamilyOut,
  AdminClientGroupOut,
  AdminClientMessageOut,
  AdminClientManualCreditOut,
  AdminClientNoteOut,
  AdminClientOut,
  AdminClientPaymentOut,
  AdminRangeInvoiceEmailPreviewOut,
  AdminClientSubscriptionOut,
  AdminPaymentMethodsOut,
  AdminProductCategoriesOut,
  PlanOut,
} from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type PageProps = {
  params: { clientId: string };
  searchParams: SearchParams;
};

type ClientTab = "fiche" | "infos" | "famille" | "messages" | "paiements" | "factures" | "reservations";

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
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
  if (value === "infos" || value === "famille" || value === "messages" || value === "paiements" || value === "factures" || value === "reservations") {
    return value;
  }
  return "fiche";
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDateOnly(value: string | null): string {
  if (!value) {
    return "Non renseignee";
  }
  return new Date(value).toLocaleDateString("fr-FR", {
    dateStyle: "medium",
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

function endOfDateUtcMs(value: string): number {
  if (!isDateInput(value)) {
    return Number.POSITIVE_INFINITY;
  }
  return new Date(`${value}T23:59:59.999Z`).getTime();
}

function formatDateInputLabel(value: string): string {
  if (!isDateInput(value)) {
    return value;
  }
  return new Date(`${value}T00:00:00.000Z`).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatMoney(value: string | null | undefined, currency: string): string {
  const amount = Number(value ?? "0");
  return new Intl.NumberFormat("fr-FR", {
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

function formatVatRateLabel(value: string | null | undefined): string {
  const rate = Number(value ?? "0");
  if (!Number.isFinite(rate) || rate <= 0) {
    return "0%";
  }
  const hasDecimals = Math.abs(rate % 1) > 0.0001;
  return `${new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: hasDecimals ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(rate)}%`;
}

function billingMethodLabel(code: string | null): string {
  const normalized = (code ?? "").toUpperCase();
  if (normalized === "CARD_ONLINE") {
    return "CB en ligne (Mollie / Payplug)";
  }
  if (normalized === "SEPA_DEBIT") {
    return "Prelevement SEPA";
  }
  if (normalized === "CARD_TERMINAL") {
    return "CB sur TPE";
  }
  if (normalized === "BANK_TRANSFER") {
    return "Virement";
  }
  if (normalized === "CASH") {
    return "Especes";
  }
  if (normalized === "CHECK") {
    return "Cheque";
  }
  if (normalized === "PAYPAL") {
    return "PayPal";
  }
  return code || "Non defini";
}

function paymentSourceLabel(source: string): string {
  const normalized = source.trim().toUpperCase();
  if (normalized === "PLAN_PURCHASE") {
    return "Achat formule";
  }
  if (normalized === "BOOKING") {
    return "Reservation";
  }
  if (normalized === "MANUAL") {
    return "Manuel";
  }
  return normalized || "Paiement";
}

function paymentStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "REFUNDED") {
    return "Rembourse";
  }
  if (normalized === "PAID") {
    return "Paye";
  }
  if (normalized === "INCLUDED_PLAN") {
    return "Inclus formule";
  }
  if (normalized === "BOOKED" || normalized === "ATTENDED" || normalized === "NO_SHOW") {
    return "A facturer";
  }
  if (normalized === "FAILED") {
    return "Echec";
  }
  if (normalized === "PENDING" || normalized === "WAITLISTED" || normalized === "TRIAL") {
    return "En attente";
  }
  if (normalized === "ACTIVE") {
    return "Actif";
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return "Absence excusee";
  }
  if (normalized === "NOT_BILLABLE") {
    return "Non facturable";
  }
  if (normalized === "CANCELLED" || normalized === "EXPIRED" || normalized === "ARCHIVED" || normalized === "INACTIVE") {
    return "Annule";
  }
  return normalized || "Inconnu";
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

function paymentStatusDisplayLabel(row: AdminClientPaymentOut): string {
  return isIncludedPlanBooking(row) ? "Inclus formule" : paymentStatusLabel(row.status);
}

const PAID_PAYMENT_STATUSES = new Set(["PAID", "SUCCEEDED", "COMPLETED"]);
const PENDING_PAYMENT_STATUSES = new Set([
  "PENDING",
  "WAITLISTED",
  "TRIAL",
  "OPEN",
  "CREATED",
  "PROCESSING",
  "WAITING_PAYMENT",
  "FAILED",
  "BOOKED",
  "ATTENDED",
  "NO_SHOW",
]);
const CANCELLED_PAYMENT_STATUSES = new Set(["CANCELLED", "EXPIRED", "INACTIVE", "ARCHIVED"]);
const ACTIVE_SUBSCRIPTION_BOOKING_STATUSES = new Set(["BOOKED", "WAITLISTED"]);

function normalizePaymentStatus(status: string): string {
  return (status || "").trim().toUpperCase();
}

function shouldCountInClientBalance(row: AdminClientPaymentOut): boolean {
  const status = normalizePaymentStatus(row.status);
  if (status === "NOT_BILLABLE" || status === "INCLUDED_PLAN" || status === "REFUNDED" || CANCELLED_PAYMENT_STATUSES.has(status)) {
    return false;
  }

  if (row.source.trim().toUpperCase() === "MANUAL") {
    return true;
  }

  return PENDING_PAYMENT_STATUSES.has(status);
}

function invoiceStatusLabel(status: string | null): string {
  const normalized = (status ?? "").trim().toUpperCase();
  if (normalized === "PAID") {
    return "Facture payee";
  }
  if (normalized === "CANCELLED") {
    return "Facture annulee";
  }
  if (normalized === "PENDING") {
    return "Facture en attente";
  }
  return "Facture";
}

const INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::";

type RangeInvoiceNotePayload = {
  kind: "INVOICE_RANGE";
  invoice_number: string;
  issued_date: string;
  due_date: string;
  start_date: string;
  end_date: string;
  layout: "DETAILED" | "COMPILED";
  include_pending: boolean;
  include_cancelled: boolean;
  totals_by_currency: Record<string, string>;
  invoice_status: "ISSUED" | "PAID" | "CANCELLED";
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
      kind: "range";
      key: string;
      noteId: string;
      occurredAt: string;
      invoiceNumber: string;
      typeLabel: string;
      label: string;
      status: string;
      emailedAt: string | null;
      remindedAt: string | null;
      totalLabel: string;
      downloadHref: string;
      viewHref: string;
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
    if (payload.layout !== "DETAILED" && payload.layout !== "COMPILED") {
      return null;
    }
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
      start_date: payload.start_date,
      end_date: payload.end_date,
      layout: payload.layout,
      include_pending: Boolean(payload.include_pending),
      include_cancelled: Boolean(payload.include_cancelled),
      totals_by_currency: totals,
      invoice_status:
        payload.invoice_status === "PAID" || payload.invoice_status === "CANCELLED" || payload.invoice_status === "ISSUED"
          ? payload.invoice_status
          : "ISSUED",
      emailed_at: typeof payload.emailed_at === "string" ? payload.emailed_at : undefined,
      reminded_at: typeof payload.reminded_at === "string" ? payload.reminded_at : undefined,
      public_note: typeof payload.public_note === "string" ? payload.public_note : undefined,
      private_note: typeof payload.private_note === "string" ? payload.private_note : undefined,
    };
  } catch {
    return null;
  }
}

function rangeInvoiceTotalLabel(totalsByCurrency: Record<string, string>): string {
  const entries = Object.entries(totalsByCurrency);
  if (entries.length === 0) {
    return "-";
  }
  return entries
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(" | ");
}

function rangeInvoicePdfHref(clientId: string, payload: RangeInvoiceNotePayload, inline = false): string {
  const params = new URLSearchParams({
    payment_return_tab: "factures",
    start_date: payload.start_date,
    end_date: payload.end_date,
    issued_date: payload.issued_date,
    due_date: payload.due_date,
    include_pending: payload.include_pending ? "true" : "false",
    include_cancelled: payload.include_cancelled ? "true" : "false",
    layout: payload.layout,
    invoice_number: payload.invoice_number,
    persist_note: "false",
    invoice_status: payload.invoice_status,
    inline: inline ? "true" : "false",
  });
  if (payload.public_note) {
    params.set("public_note", payload.public_note);
  }
  return `/admin/clients/${clientId}/payments/invoice-range?${params.toString()}`;
}

function rangeInvoiceStatusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PAID") {
    return "Paye";
  }
  if (normalized === "CANCELLED") {
    return "Annulee";
  }
  return "Emise";
}

function rangeInvoiceStatusClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "CANCELLED") {
    return "status-off";
  }
  return "status-warn";
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

const MANUAL_TRANSACTION_MODAL_TYPES = ["payment", "refund", "charge", "discount"] as const;
type ManualTransactionModalType = (typeof MANUAL_TRANSACTION_MODAL_TYPES)[number];

const DEFAULT_PAYMENT_METHOD_OPTIONS: Array<{ code: string; label: string }> = [
  { code: "CARD_ONLINE", label: "CB en ligne (Mollie / Payplug)" },
  { code: "CARD_TERMINAL", label: "CB sur place (TPE)" },
  { code: "CHECK", label: "Cheque" },
  { code: "CASH", label: "Especes" },
  { code: "PAYPAL", label: "PayPal" },
  { code: "SEPA_DEBIT", label: "Prelevement SEPA" },
  { code: "BANK_TRANSFER", label: "Virement bancaire" },
];

function statusClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ACTIVE" || normalized === "BOOKED" || normalized === "ATTENDED" || normalized === "SENT" || normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "WAITLISTED" || normalized === "PENDING" || normalized === "TRIAL" || normalized === "FAILED") {
    return "status-warn";
  }
  return "status-off";
}

function paymentStatusClass(status: string): string {
  const normalized = normalizePaymentStatus(status);
  if (normalized === "NOT_BILLABLE" || normalized === "REFUNDED" || CANCELLED_PAYMENT_STATUSES.has(normalized)) {
    return "status-off";
  }
  if (PAID_PAYMENT_STATUSES.has(normalized)) {
    return "status-ok";
  }
  return "status-warn";
}

function subscriptionStatusPill(sub: AdminClientSubscriptionOut): { label: string; toneClass: string } {
  const normalized = (sub.status ?? "").toUpperCase();
  if (normalized === "CANCELLED" || normalized === "EXPIRED" || normalized === "ARCHIVED" || normalized === "INACTIVE") {
    return { label: "RESILIE", toneClass: "status-off" };
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

function planKindLabel(kind: string): string {
  const normalized = kind.trim().toUpperCase();
  if (normalized === "PACK") {
    return "Carnet";
  }
  if (normalized === "FORFAIT") {
    return "Forfait";
  }
  return "Abonnement";
}

export default async function AdminClientDetailPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const currentTab = parseTab(readParam(searchParams, "tab"));
  const openEditInfosModal = readParam(searchParams, "edit_infos") === "1";
  const subscriptionModalAction = readParam(searchParams, "subscription_modal");
  const subscriptionModalId = readParam(searchParams, "subscription_id");
  const openManualCreditModal = readParam(searchParams, "edit_credit") === "1";
  const creditTypeModalId = readParam(searchParams, "credit_type_id");
  const paymentModalAction = readParam(searchParams, "payment_modal");
  const manualTransactionModalTypeRaw = readParam(searchParams, "manual_type").toLowerCase();
  const manualTransactionModalType = MANUAL_TRANSACTION_MODAL_TYPES.includes(
    manualTransactionModalTypeRaw as ManualTransactionModalType,
  )
    ? (manualTransactionModalTypeRaw as ManualTransactionModalType)
    : null;
  const paymentModalSource = readParam(searchParams, "payment_source").toUpperCase();
  const paymentModalId = readParam(searchParams, "payment_id");
  const invoiceNoteId = readParam(searchParams, "invoice_note_id");
  const invoiceEmailKindRaw = readParam(searchParams, "invoice_email_kind").toUpperCase();
  const invoiceEmailKind = invoiceEmailKindRaw === "REMINDER" ? "REMINDER" : "INVOICE";
  const paymentReturnTabRaw = readParam(searchParams, "payment_return_tab");
  const cancelConflictAlert = readParam(searchParams, "cancel_conflict") === "1";
  const purchaseModalAction = readParam(searchParams, "purchase_modal");
  const purchasePlanId = readParam(searchParams, "purchase_plan_id");
  const purchaseType = readParam(searchParams, "purchase_type").toUpperCase() || "FORMULA";
  const purchasePaymentMethod = readParam(searchParams, "purchase_payment_method").toUpperCase();
  const purchaseDiscountedTotalRaw = readParam(searchParams, "purchase_discounted_total").replace(",", ".");
  const purchaseStartDateRaw = readParam(searchParams, "purchase_start_date").trim();
  const purchaseReturnTab = parseTab(readParam(searchParams, "purchase_return_tab") || currentTab);
  const paymentReturnTab = parseTab(paymentReturnTabRaw || currentTab);
  const balanceDateParam = readParam(searchParams, "balance_date");
  const paymentFilterQuery = readParam(searchParams, "payment_filter_q").trim();
  const paymentFilterAmountRaw = readParam(searchParams, "payment_filter_amount").trim();
  const paymentFilterAmount = parseAmountFilter(paymentFilterAmountRaw);
  const hasPaymentFilters = paymentFilterQuery.length > 0 || paymentFilterAmount !== null;

  const [
    clientResult,
    plansResult,
    subscriptionsResult,
    bookingsResult,
    messagesResult,
    paymentsResult,
    productCategoriesResult,
    paymentMethodsResult,
    familyResult,
    allClientsResult,
    groupsResult,
    manualCreditsResult,
    notesResult,
  ] = await Promise.all([
    backendRequest<AdminClientOut>(`/api/v1/admin/clients/${params.clientId}`, {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans", {}, token),
    backendRequest<AdminClientSubscriptionOut[]>(`/api/v1/admin/clients/${params.clientId}/subscriptions`, {}, token),
    backendRequest<AdminClientBookingOut[]>(`/api/v1/admin/clients/${params.clientId}/bookings`, {}, token),
    backendRequest<AdminClientMessageOut[]>(`/api/v1/admin/clients/${params.clientId}/messages`, {}, token),
    backendRequest<AdminClientPaymentOut[]>(`/api/v1/admin/clients/${params.clientId}/payments`, {}, token),
    backendRequest<AdminProductCategoriesOut>("/api/v1/admin/config/product-categories", {}, token),
    backendRequest<AdminPaymentMethodsOut>("/api/v1/admin/config/payment-methods", {}, token),
    backendRequest<AdminClientFamilyOut>(`/api/v1/admin/clients/${params.clientId}/family`, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000", {}, token),
    backendRequest<AdminClientGroupOut[]>("/api/v1/admin/clients/groups?include_inactive=false", {}, token),
    backendRequest<AdminClientManualCreditOut[]>(`/api/v1/admin/clients/${params.clientId}/manual-credits`, {}, token),
    backendRequest<AdminClientNoteOut[]>(`/api/v1/admin/clients/${params.clientId}/notes`, {}, token),
  ]);

  if (!clientResult.ok) {
    if (clientResult.status === 404) {
      redirect("/admin/clients?error=Client%20introuvable");
    }
    return <section className="flash-err">Erreur backend: {clientResult.message}</section>;
  }

  const client = clientResult.data;
  const fullName = [client.first_name, client.last_name].filter(Boolean).join(" ");
  const todayInputValue = formatDateInput(new Date());
  const dueDateInputValue = formatDateInput(addDays(new Date(), 10));
  const purchaseStartDateInputValue = isDateInput(purchaseStartDateRaw) ? purchaseStartDateRaw : todayInputValue;
  const selectedBalanceDate = isDateInput(balanceDateParam) ? balanceDateParam : todayInputValue;
  const selectedBalanceDateEndMs = endOfDateUtcMs(selectedBalanceDate);
  const monthStartInputValue = `${todayInputValue.slice(0, 8)}01`;

  const errors: string[] = [];

  const plans = plansResult.ok
    ? plansResult.data.filter((plan) => plan.active)
    : (() => {
        errors.push(`plans: ${plansResult.message}`);
        return [] as PlanOut[];
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

  const productCategories = productCategoriesResult.ok
    ? productCategoriesResult.data.categories
    : (() => {
        errors.push(`product_categories: ${productCategoriesResult.message}`);
        return [] as string[];
      })();

  const enabledPaymentMethods = paymentMethodsResult.ok
    ? paymentMethodsResult.data.methods.filter((method) => method.enabled)
    : (() => {
        errors.push(`payment_methods: ${paymentMethodsResult.message}`);
        return DEFAULT_PAYMENT_METHOD_OPTIONS.map((item) => ({ ...item, enabled: true }));
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
        } as AdminClientFamilyOut;
      })();

  if (currentTab === "factures" && client.client_kind === "CHILD") {
    if (family.billing_recipient_adult_id) {
      const redirectSearch = cloneSearchParams(searchParams);
      redirectSearch.set("tab", "factures");
      redirect(`/admin/clients/${family.billing_recipient_adult_id}?${redirectSearch.toString()}`);
    }
    redirect(`/admin/clients/${client.id}?tab=famille&error=Definir%20un%20destinataire%20de%20facture%20pour%20cet%20enfant`);
  }

  const allClients = allClientsResult.ok
    ? allClientsResult.data
    : (() => {
        errors.push(`clients: ${allClientsResult.message}`);
        return [] as AdminClientOut[];
      })();

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

  const messageRows = [
    ...messages.map((msg) => ({
      id: `reminder:${msg.id}`,
      occurredAt: msg.sent_at ?? msg.scheduled_for_utc,
      subject: msg.subject_preview,
      status: msg.status,
      session: msg.session_title,
    })),
    ...notes
      .filter((note) => (note.entry_type || "").toUpperCase() === "EMAIL")
      .map((note) => ({
        id: `email-note:${note.id}`,
        occurredAt: note.created_at,
        subject: note.message,
        status: "SENT",
        session: "-",
      })),
  ].sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());

  const selectedPlanForPurchase = purchasePlanId ? plans.find((plan) => plan.id === purchasePlanId) ?? null : null;
  const discountedTotalForPurchase = purchaseDiscountedTotalRaw ? Number(purchaseDiscountedTotalRaw) : Number.NaN;
  const hasDiscountedTotalForPurchase = Number.isFinite(discountedTotalForPurchase) && discountedTotalForPurchase >= 0;
  const selectedPlanBaseTotal = selectedPlanForPurchase?.monthly_price_excl_vat ?? null;
  const selectedPlanCurrency = selectedPlanForPurchase?.currency_code || client.preferred_currency || "EUR";
  const isCardOnlinePurchase = purchasePaymentMethod === "CARD_ONLINE";
  const purchaseTypeLabel = purchaseType === "PRODUCT" ? "Produits catalogues" : "Formule de cours";
  const purchaseWizardReturnSearch = new URLSearchParams({
    tab: purchaseReturnTab,
    purchase_modal: "wizard",
    purchase_return_tab: purchaseReturnTab,
    purchase_start_date: purchaseStartDateInputValue,
  });
  const purchaseWizardReturnHref = `/admin/clients/${client.id}?${purchaseWizardReturnSearch.toString()}`;

  const activeSubscriptions = subscriptions.filter(
    (sub) => (sub.status === "ACTIVE" || sub.status === "PAUSED") && !isPendingSubscriptionCancellation(sub),
  );
  const endingSubscriptions = subscriptions.filter(
    (sub) => (sub.status === "ACTIVE" || sub.status === "PAUSED") && isPendingSubscriptionCancellation(sub),
  );
  const archivedSubscriptions = subscriptions.filter(
    (sub) => (sub.status !== "ACTIVE" && sub.status !== "PAUSED") || isCancellationAlreadyEffective(sub),
  );
  const hasForfaitPlan = subscriptions.some((sub) => sub.plan.kind === "FORFAIT");
  const visibleCurrentSubscriptions = [...activeSubscriptions, ...endingSubscriptions];
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
  const selectedCreditForModal = openManualCreditModal
    ? manualCredits.find((row) => row.credit_type_id === creditTypeModalId) ?? null
    : null;
  const selectedPaymentForModal =
    paymentModalAction === "refund"
      ? payments.find((row) => row.id === paymentModalId && row.source.toUpperCase() === paymentModalSource) ?? null
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
  const openManualTransactionSelector = paymentModalAction === "manual" && manualTransactionModalType === null;
  const openManualTransactionForm = paymentModalAction === "manual" && manualTransactionModalType !== null;
  const openPaymentFiltersModal = paymentModalAction === "filters";

  const totalRemainingCredits = activeSubscriptions.reduce((acc, sub) => {
    if (sub.plan.kind !== "PACK") {
      return acc;
    }
    return acc + Number(sub.credits_remaining ?? 0);
  }, 0);

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
        paymentSourceLabel(row.source),
        row.label,
        row.reference ?? "",
        paymentStatusDisplayLabel(row),
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

  const paymentInvoices: InvoiceListRow[] = payments
    .filter((row) => {
      const normalizedInvoiceStatus = (row.invoice_status ?? "").toUpperCase();
      return normalizedInvoiceStatus === "PAID" || normalizedInvoiceStatus === "CANCELLED";
    })
    .map((row) => ({
      kind: "payment",
      key: `payment-${row.source}-${row.id}`,
      occurredAt: row.occurred_at,
      invoiceNumber: row.invoice_number,
      typeLabel: paymentSourceLabel(row.source),
      label: row.label,
      status: row.invoice_status,
      total: row.total_incl_vat,
      currency: row.currency,
      source: row.source,
      paymentId: row.id,
      paymentStatus: row.status,
    }));

  const generatedRangeInvoices: RangeInvoiceListRow[] = notes.reduce<RangeInvoiceListRow[]>((acc, note) => {
    const payload = parseRangeInvoiceNote(note);
    if (!payload) {
      return acc;
    }
    acc.push({
      kind: "range",
      key: `range-${payload.invoice_number}-${note.id}`,
      noteId: note.id,
      occurredAt: `${payload.issued_date}T00:00:00.000Z`,
      invoiceNumber: payload.invoice_number,
      typeLabel: "Facture periode",
      label: `${formatDateInputLabel(payload.start_date)} - ${formatDateInputLabel(payload.end_date)}`,
      status: payload.invoice_status,
      emailedAt: payload.emailed_at ?? null,
      remindedAt: payload.reminded_at ?? null,
      totalLabel: rangeInvoiceTotalLabel(payload.totals_by_currency),
      downloadHref: rangeInvoicePdfHref(client.id, payload, false),
      viewHref: rangeInvoicePdfHref(client.id, payload, true),
    });
    return acc;
  }, []);

  const invoices = [...generatedRangeInvoices, ...paymentInvoices].sort(
    (a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt),
  );
  const selectedRangeInvoiceForModal =
    paymentModalAction === "invoice_email" && invoiceNoteId
      ? generatedRangeInvoices.find((row) => row.noteId === invoiceNoteId) ?? null
      : null;
  let invoiceEmailPreviewResult: unknown = null;
  if (paymentModalAction === "invoice_email" && selectedRangeInvoiceForModal) {
    invoiceEmailPreviewResult = await backendRequest(
      `/api/v1/admin/clients/${params.clientId}/invoices/range/${selectedRangeInvoiceForModal.noteId}/email/preview?kind=${encodeURIComponent(
        invoiceEmailKind,
      )}`,
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

  const totalsByCurrency = new Map<string, number>();
  const paidTotalsByCurrency = new Map<string, number>();
  const pendingTotalsByCurrency = new Map<string, number>();
  const cancelledOrNotBillableTotalsByCurrency = new Map<string, number>();
  for (const row of paymentsAsOfDate) {
    const currency = row.currency || "EUR";
    const amount = Number(row.total_incl_vat || "0");
    const status = normalizePaymentStatus(row.status);

    const dueCurrent = totalsByCurrency.get(currency) ?? 0;
    totalsByCurrency.set(currency, dueCurrent + (shouldCountInClientBalance(row) ? amount : 0));

    if (status === "NOT_BILLABLE" || status === "REFUNDED" || CANCELLED_PAYMENT_STATUSES.has(status)) {
      const current = cancelledOrNotBillableTotalsByCurrency.get(currency) ?? 0;
      cancelledOrNotBillableTotalsByCurrency.set(currency, current + amount);
    } else if (PAID_PAYMENT_STATUSES.has(status)) {
      const current = paidTotalsByCurrency.get(currency) ?? 0;
      paidTotalsByCurrency.set(currency, current + amount);
    } else {
      const current = pendingTotalsByCurrency.get(currency) ?? 0;
      pendingTotalsByCurrency.set(currency, current + amount);
    }
  }

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const linkedChildren = family.links_as_adult;
  const linkedAdults = family.links_as_child;
  const linkedChildIds = new Set(linkedChildren.map((link) => link.child.id));
  const linkedAdultIds = new Set(linkedAdults.map((link) => link.adult.id));

  const candidateChildren = allClients.filter(
    (candidate) => candidate.id !== client.id && candidate.client_kind === "CHILD" && !linkedChildIds.has(candidate.id),
  );
  const candidateAdults = allClients.filter(
    (candidate) => candidate.id !== client.id && candidate.client_kind === "ADULT" && !linkedAdultIds.has(candidate.id),
  );

  const tabs: Array<{ id: ClientTab; label: string }> = [
    { id: "fiche", label: "Fiche" },
    { id: "infos", label: "Infos" },
    { id: "famille", label: "Famille" },
    { id: "messages", label: "Messages" },
    { id: "paiements", label: "Compte" },
    { id: "factures", label: "Factures" },
    { id: "reservations", label: "Reservations" },
  ];

  const manualTransactionTypeCodeByModal: Record<ManualTransactionModalType, "PAYMENT" | "REFUND" | "CHARGE" | "DISCOUNT"> = {
    payment: "PAYMENT",
    refund: "REFUND",
    charge: "CHARGE",
    discount: "DISCOUNT",
  };
  const manualTransactionTitleByModal: Record<ManualTransactionModalType, string> = {
    payment: "Ajouter un paiement",
    refund: "Ajouter un remboursement",
    charge: "Ajouter des frais",
    discount: "Ajouter une remise",
  };
  const manualTransactionHelpByModal: Record<ManualTransactionModalType, string> = {
    payment: "Utiliser cette vue lorsque la famille paie.",
    refund: "Utiliser cette vue lorsque vous remettez de l argent a la famille.",
    charge: "Utiliser cette vue pour ajouter un montant facture sans encaissement.",
    discount: "Utiliser cette vue pour ajouter un rabais (transaction negative).",
  };
  const manualTransactionDefaultLabelByModal: Record<ManualTransactionModalType, string> = {
    payment: "Paiement manuel",
    refund: "Remboursement",
    charge: "Montant facture",
    discount: "Rabais manuel",
  };
  const manualTransactionTypeCode =
    manualTransactionModalType === null ? null : manualTransactionTypeCodeByModal[manualTransactionModalType];
  const manualTransactionTitle =
    manualTransactionModalType === null ? "Ajouter une transaction" : manualTransactionTitleByModal[manualTransactionModalType];
  const manualTransactionHelp =
    manualTransactionModalType === null ? "" : manualTransactionHelpByModal[manualTransactionModalType];
  const manualTransactionDefaultLabel =
    manualTransactionModalType === null ? "" : manualTransactionDefaultLabelByModal[manualTransactionModalType];
  const manualIsCashFlow = manualTransactionModalType === "payment" || manualTransactionModalType === "refund";
  const manualVatDefault = manualIsCashFlow ? "0" : "20";

  return (
    <section className="admin-page-grid client-detail-page">
      <section className="client-hero card">
        <div className="row spread">
          <div className="row">
            <Link className="reset-link" href="/admin/clients">
              Retour liste clients
            </Link>
            <Link className="mode-link" href="/admin/clients?new_client=1">
              Nouveau client
            </Link>
          </div>
          <small className="muted">Cree le {formatDate(client.created_at)} | Maj {formatDate(client.updated_at)}</small>
        </div>

        <div className="client-hero-main">
          <div className="client-avatar">{initials(client)}</div>
          <div>
            <h2>{fullName || client.email}</h2>
            <p className="muted">
              {client.email} | Mobile 1: {client.mobile_phone_1 ?? "-"} | {client.residence_country} | {client.preferred_currency} |{" "}
              {client.client_kind === "CHILD" ? "Enfant" : "Adulte"}
            </p>
          </div>
        </div>

        <nav className="client-tabs">
          {tabs.map((tab) => (
            <Link
              key={tab.id}
              href={tabHref(client.id, tab.id)}
              className={`client-tab ${currentTab === tab.id ? "active" : ""}`}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">Erreur backend: {errors.join(" | ")}</section> : null}

      {currentTab === "fiche" ? (
        <section className="grid cols-2 client-sheet-grid">
          <article className="card client-summary-card">
            <h3>Solde de l&apos;adherent</h3>
            <p className="client-balance-main">{totalRemainingCredits}</p>
            <p className="muted">credits restants (packs actifs)</p>
            <div className="client-summary-stats">
              <span className="badge">Abonnements actifs: {activeMonthlySubscriptions}</span>
              <span className="badge">Reservations en cours: {bookedReservations.length}</span>
            </div>
          </article>

          <article className="card">
            <div className="row spread">
              <h3>Ajouter un produit</h3>
              <Link
                className="client-action-icon payment-add-icon"
                href={ficheHref(client.id, { purchase_modal: "wizard", purchase_return_tab: "fiche" })}
                title="Nouveau achat"
              >
                +
              </Link>
            </div>
            <p className="muted">Associer une formule de cours ou un produit catalogue, avec mode de reglement et validation CGV.</p>
            <p className="muted top-gap-sm">
              Flux: Type d&apos;achat -&gt; Offre -&gt; Prix remisé -&gt; Reglement -&gt; Validation.
            </p>
            <p className="muted">
              Regles appliquees: pas de doublon d&apos;abonnement sur le mois, pas de nouveau carnet si credits restants.
            </p>
          </article>

          <article className="card span-2">
            <div className="row spread">
              <h3>Abonnements et produits en cours</h3>
              <div className="row">
                <span className="badge">Actifs: {activeSubscriptions.length}</span>
                <span className="badge">Fin de periode: {endingSubscriptions.length}</span>
              </div>
            </div>

            {visibleCurrentSubscriptions.length === 0 ? (
              <p className="muted top-gap-sm">Aucun produit en cours.</p>
            ) : (
              <div className="subscription-stack top-gap-sm">
                {visibleCurrentSubscriptions.map((sub) => {
                  const statusPill = subscriptionStatusPill(sub);
                  const pendingCancellation = isPendingSubscriptionCancellation(sub);
                  return (
                    <article key={sub.id} className="subscription-detail-card">
                    <header className="row spread subscription-head">
                      <div className="stack-sm">
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? pendingCancellation
                              ? "Abonnement en fin de periode"
                              : "Abonnement en cours"
                            : sub.plan.kind === "PACK"
                              ? "Carnet actif"
                              : "Forfait actif"}
                        </small>
                        <h4>{sub.plan.name}</h4>
                        <span className="muted">
                          Numero de contrat: {shortContractRef(sub.id)} ({sub.id})
                        </span>
                      </div>
                      <div className="row subscription-head-actions">
                        <span className={`status-pill ${statusPill.toneClass}`}>{statusPill.label}</span>
                        {sub.plan.kind === "SUBSCRIPTION" ? (
                          <>
                            <Link
                              className="client-action-icon"
                              href={ficheHref(client.id, { subscription_modal: "billing", subscription_id: sub.id })}
                              title="Configurer les references de prelevement"
                            >
                              ✎
                            </Link>
                            {sub.status !== "CANCELLED" ? (
                              <>
                                <Link
                                  className="client-action-icon"
                                  href={ficheHref(client.id, { subscription_modal: "suspend", subscription_id: sub.id })}
                                  title="Suspendre l abonnement"
                                >
                                  ⏸
                                </Link>
                                <Link
                                  className="client-action-icon danger"
                                  href={ficheHref(client.id, { subscription_modal: "cancel", subscription_id: sub.id })}
                                  title="Resilier a fin de periode"
                                >
                                  ✕
                                </Link>
                                <Link
                                  className="client-action-icon danger"
                                  href={ficheHref(client.id, { subscription_modal: "cancel_now", subscription_id: sub.id })}
                                  title="Resilier immediatement"
                                >
                                  ⚠
                                </Link>
                              </>
                            ) : null}
                          </>
                        ) : sub.status !== "CANCELLED" ? (
                          <>
                            {sub.plan.kind === "FORFAIT" ? (
                              <Link
                                className="client-action-icon"
                                href={ficheHref(client.id, { subscription_modal: "forfait_pricing", subscription_id: sub.id })}
                                title="Modifier la surcouche tarifaire forfait"
                              >
                                €
                              </Link>
                            ) : null}
                            <Link
                              className="client-action-icon"
                              href={ficheHref(client.id, { subscription_modal: "expiry", subscription_id: sub.id })}
                              title="Modifier la date d expiration"
                            >
                              ✎
                            </Link>
                            <Link
                              className="client-action-icon danger"
                              href={ficheHref(client.id, { subscription_modal: "cancel_now", subscription_id: sub.id })}
                              title="Annuler le carnet / forfait"
                            >
                              ✕
                            </Link>
                          </>
                        ) : null}
                      </div>
                    </header>

                    <section className="subscription-meta-grid">
                      <article className="subscription-field">
                        <p className="muted">Formule</p>
                        <strong>{sub.plan.name}</strong>
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? "Reconduction tacite"
                            : sub.plan.kind === "PACK"
                              ? "Carnet de credits"
                              : "Forfait facture au reel"}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">Prix / Tarif TTC</p>
                        <strong>
                          {sub.estimated_total_incl_vat
                            ? `${formatMoney(sub.estimated_total_incl_vat, sub.estimated_currency || client.preferred_currency)} TTC`
                            : "n/a"}
                        </strong>
                        <small className="muted">
                          TVA {sub.estimated_vat_rate ?? "-"}% incluse
                          {sub.plan.kind === "FORFAIT"
                            ? ` | Activites configurees: ${
                                sub.forfait_activity_pricing.filter(
                                  (row) =>
                                    Number.parseFloat(row.loyalty_discount_per_hour_ttc || "0") > 0 ||
                                    Number.parseFloat(row.family_discount_per_hour_ttc || "0") > 0 ||
                                    Number.parseFloat(row.short_commitment_supplement_per_hour_ttc || "0") > 0,
                                ).length
                              }/${sub.forfait_activity_pricing.length}`
                            : ""}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">Moyen de paiement</p>
                        <strong>{billingMethodLabel(sub.billing_method_code)}</strong>
                        <small className="muted">
                          Auto-renouvellement: {sub.auto_renew ? "Oui" : "Non"} | Dernier statut: {sub.last_payment_status ?? "n/a"}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">Credits</p>
                        <strong>
                          {sub.credits_remaining ?? "-"}/{sub.credits_initial ?? "-"}
                        </strong>
                        <small className="muted">restants / initial</small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">References PSP</p>
                        <strong>{sub.payment_provider_customer_ref ?? "-"}</strong>
                        <small className="muted">
                          Mandat: {sub.payment_provider_mandate_ref ?? "-"} | Subscription:{" "}
                          {sub.payment_provider_subscription_ref ?? "-"}
                        </small>
                      </article>
                      <article className="subscription-field">
                        <p className="muted">Periode</p>
                        <strong>
                          Debut: {formatDate(sub.started_at)}
                          {sub.ends_at ? ` | Fin: ${formatDate(sub.ends_at)}` : ""}
                        </strong>
                        <small className="muted">
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? `Prochain prelevement: ${sub.next_payment_at ? formatDate(sub.next_payment_at) : "Non programme"}`
                            : "Pas de prelevement recurrent"}
                        </small>
                      </article>
                    </section>

                    {sub.suspension_starts_at && sub.suspension_ends_at ? (
                      <p className="muted top-gap-sm">
                        Suspension active: du {formatDate(sub.suspension_starts_at)} au {formatDate(sub.suspension_ends_at)} (
                        {sub.suspension_duration_value ?? 0} {sub.suspension_duration_unit === "MONTH" ? "mois" : "jours"}).
                      </p>
                    ) : null}
                    {sub.cancellation_requested_at ? (
                      <p className="muted">
                        Resiliation demandee le {formatDate(sub.cancellation_requested_at)} | Fin effective:{" "}
                        {sub.cancellation_effective_at ? formatDate(sub.cancellation_effective_at) : "a definir"}.
                      </p>
                    ) : null}

                    {sub.plan.kind === "SUBSCRIPTION" ? (
                      <p className="muted">
                        Actions rapides: utilisez les icones pour configurer le prelevement, suspendre ou resilier.
                      </p>
                    ) : (
                      <p className="muted">Actions rapides: modifiez la date d expiration ou cloturez immediatement.</p>
                    )}
                    </article>
                  );
                })}
              </div>
            )}
          </article>

          <article className="card span-2">
            <h3>Produits termines</h3>
            {archivedSubscriptions.length === 0 ? (
              <p className="muted">Aucun produit termine.</p>
            ) : (
              <div className="list top-gap-sm">
                {archivedSubscriptions.map((sub) => (
                  <article key={sub.id} className="item row spread">
                    <div className="stack-sm">
                      <strong>{sub.plan.name}</strong>
                      <small className="muted">
                        Contrat {shortContractRef(sub.id)} | Debut: {formatDate(sub.started_at)}
                        {sub.ends_at ? ` | Fin: ${formatDate(sub.ends_at)}` : ""}
                      </small>
                    </div>
                    <span className={`status-pill ${statusClass(sub.status)}`}>{sub.status}</span>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="card">
            <h3>Credits manuels</h3>
            {manualCredits.length === 0 ? (
              <p className="muted">Aucun type de credit configure.</p>
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
                        title="Modifier le nombre de credits"
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
            <h3>Notes</h3>
            {notes.length === 0 ? (
              <p className="muted">Aucune note.</p>
            ) : (
              <div className="table-wrap top-gap-sm">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Type</th>
                      <th>Auteur</th>
                      <th>Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notes.map((row) => (
                      <tr key={row.id}>
                        <td>{formatDate(row.created_at)}</td>
                        <td>{row.entry_type}</td>
                        <td>{row.author_display_name}</td>
                        <td>{row.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <form action={createAdminClientNoteAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <label>
                Ajouter une note
                <textarea name="message" rows={4} maxLength={4000} required />
              </label>
              <div className="row">
                <button type="submit">Enregistrer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "fiche" || currentTab === "paiements") && purchaseModalAction === "wizard" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, purchaseReturnTab)} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Nouvel achat</h3>
            <p className="muted">Selectionnez l offre, le prix et le reglement avant validation.</p>
            <form action={adminOpenClientPurchaseTermsAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value={purchaseReturnTab} />
              <label>
                Type d achat
                <select name="purchase_type" defaultValue="FORMULA">
                  <option value="FORMULA">Formule de cours</option>
                  <option value="PRODUCT">Produits catalogues</option>
                </select>
              </label>
              <label>
                Offre
                <select name="plan_id" required defaultValue="">
                  <option value="" disabled>
                    Selectionner une offre active
                  </option>
                  {plans.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} ({planKindLabel(plan.kind)})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Prix remisé (optionnel)
                <input
                  type="text"
                  name="discounted_total_incl_vat"
                  placeholder="Ex: 115.00"
                  defaultValue={hasDiscountedTotalForPurchase ? discountedTotalForPurchase.toFixed(2) : ""}
                />
              </label>
              <label>
                Date de debut (abonnement)
                <input type="date" name="start_date" defaultValue={purchaseStartDateInputValue} />
              </label>
              <label>
                Reglement
                <select name="payment_method_code" required defaultValue="">
                  <option value="" disabled>
                    Choisir un moyen de paiement
                  </option>
                  {enabledPaymentMethods.length > 0 ? (
                    enabledPaymentMethods.map((method) => (
                      <option key={method.code} value={method.code}>
                        {method.label}
                      </option>
                    ))
                  ) : (
                    <>
                      <option value="CHECK">Cheque</option>
                      <option value="CASH">Especes</option>
                      <option value="BANK_TRANSFER">Virement bancaire</option>
                      <option value="CARD_ONLINE">CB en ligne (Mollie / Payplug)</option>
                      <option value="PAYPAL">PayPal</option>
                      <option value="CARD_TERMINAL">CB sur place (TPE)</option>
                    </>
                  )}
                </select>
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, purchaseReturnTab)}>
                  Annuler
                </Link>
                <button type="submit">Continuer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "fiche" || currentTab === "paiements") && purchaseModalAction === "terms" && selectedPlanForPurchase ? (
        <section className="modal-overlay">
          <article className="modal-panel">
            <Link
              className="modal-close-x"
              href={purchaseWizardReturnHref}
              aria-label="Fermer"
            >
              ×
            </Link>
            <h3 className="modal-title">{selectedPlanForPurchase.name}</h3>
            <p className="muted">
              Reglement: {billingMethodLabel(purchasePaymentMethod)} | Type d achat: {purchaseTypeLabel}
            </p>
            <p className="muted">
              {selectedPlanForPurchase.kind === "FORFAIT"
                ? `Periode forfait: ${selectedPlanForPurchase.forfait_start_date ? formatDateInputLabel(selectedPlanForPurchase.forfait_start_date) : "-"} - ${selectedPlanForPurchase.forfait_end_date ? formatDateInputLabel(selectedPlanForPurchase.forfait_end_date) : "-"}`
                : `Demarrage souhaite: ${formatDateInputLabel(purchaseStartDateInputValue)}`}
            </p>
            <article className="card modal-card">
              <h4>Recapitulatif de la commande</h4>
              <p className="muted">
                Offre: {selectedPlanForPurchase.name} ({planKindLabel(selectedPlanForPurchase.kind)})
              </p>
              <p className="muted">
                Prix catalogue: {selectedPlanBaseTotal ? formatMoney(selectedPlanBaseTotal, selectedPlanCurrency) : "n/a"}
              </p>
              {hasDiscountedTotalForPurchase ? (
                <p className="muted">Prix remisé: {formatMoney(String(discountedTotalForPurchase), selectedPlanCurrency)}</p>
              ) : (
                <p className="muted">Prix remisé: aucun</p>
              )}
              <p className="purchase-total-line">
                Total a payer aujourd hui:{" "}
                {hasDiscountedTotalForPurchase
                  ? formatMoney(String(discountedTotalForPurchase), selectedPlanCurrency)
                  : selectedPlanBaseTotal
                    ? formatMoney(selectedPlanBaseTotal, selectedPlanCurrency)
                    : "n/a"}
              </p>
            </article>

            <form action={adminFinalizeClientPurchaseAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="plan_id" value={selectedPlanForPurchase.id} />
              <input type="hidden" name="plan_kind" value={selectedPlanForPurchase.kind} />
              <input type="hidden" name="plan_name" value={selectedPlanForPurchase.name} />
              <input type="hidden" name="purchase_type" value={purchaseType} />
              <input type="hidden" name="payment_method_code" value={purchasePaymentMethod} />
              <input type="hidden" name="return_tab" value={purchaseReturnTab} />
              <input type="hidden" name="start_date" value={purchaseStartDateInputValue} />
              {hasDiscountedTotalForPurchase ? (
                <input type="hidden" name="discounted_total_incl_vat" value={discountedTotalForPurchase.toFixed(2)} />
              ) : null}

              {isCardOnlinePurchase ? (
                <label>
                  Canal d envoi du lien de paiement
                  <select name="signature_channel" defaultValue="EMAIL">
                    <option value="EMAIL">Envoyer par email</option>
                    <option value="SMS">Envoyer par SMS</option>
                  </select>
                </label>
              ) : (
                <>
                  <input type="hidden" name="signature_channel" value="NONE" />
                  <p className="muted">
                    Paiement hors carte: la transaction sera enregistree sans envoi de lien de paiement.
                  </p>
                </>
              )}

              <div className="row modal-actions-end">
                <Link
                  className="reset-link"
                  href={purchaseWizardReturnHref}
                >
                  Retour
                </Link>
                <button type="submit">
                  {isCardOnlinePurchase ? "Envoyer le lien de paiement par mail ou SMS" : "Valider le paiement"}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "billing" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Configurer le prelevement</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={setupAdminClientSubscriptionBillingAction} className="grid cols-2 top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                Methode de paiement
                <select name="billing_method_code" defaultValue={selectedSubscriptionForModal.billing_method_code ?? "CARD_ONLINE"}>
                  <option value="CARD_ONLINE">CARD_ONLINE (CB en ligne - Mollie / Payplug)</option>
                  <option value="SEPA_DEBIT">SEPA_DEBIT</option>
                  <option value="CARD_TERMINAL">CARD_TERMINAL</option>
                  <option value="BANK_TRANSFER">BANK_TRANSFER</option>
                </select>
              </label>
              <label>
                Ref abonnement PSP
                <input
                  type="text"
                  name="payment_provider_subscription_ref"
                  defaultValue={selectedSubscriptionForModal.payment_provider_subscription_ref ?? ""}
                />
              </label>
              <label>
                Ref client PSP
                <input
                  type="text"
                  name="payment_provider_customer_ref"
                  defaultValue={selectedSubscriptionForModal.payment_provider_customer_ref ?? ""}
                />
              </label>
              <label>
                Ref mandat PSP
                <input type="text" name="payment_provider_mandate_ref" defaultValue={selectedSubscriptionForModal.payment_provider_mandate_ref ?? ""} />
              </label>
              <div className="row span-2 modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit">Enregistrer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "expiry" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">
              {selectedSubscriptionForModal.plan.kind === "PACK" ? "Modifier l expiration du carnet" : "Modifier l expiration du forfait"}
            </h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={updateAdminClientSubscriptionExpiryAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                Date d expiration
                <input
                  type="date"
                  name="ends_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.ends_at, todayInputValue)}
                  required
                />
              </label>
              <p className="muted">
                Si la date est deja passee, le produit est automatiquement marque comme termine et les credits du carnet deviennent
                inutilisables.
              </p>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit">Enregistrer</button>
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
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Tarification client (forfait)</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <p className="muted">Etape optionnelle: laissez vide pour conserver 0 sur chaque activite.</p>
            <form action={updateAdminClientForfaitPricingAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              {selectedSubscriptionForModal.forfait_activity_pricing.length === 0 ? (
                <p className="muted">Aucune activite associee a cette formule forfait.</p>
              ) : (
                selectedSubscriptionForModal.forfait_activity_pricing.map((row) => (
                  <article key={row.course_type_id} className="card modal-card">
                    <input type="hidden" name="forfait_activity_row_key" value={row.course_type_id} />
                    <input type="hidden" name={`forfait_course_type_id_${row.course_type_id}`} value={row.course_type_id} />
                    <h4>{row.course_type_name}</h4>
                    <p className="muted">
                      Tarif activite:{" "}
                      {row.base_hourly_rate_ttc
                        ? `${formatMoney(row.base_hourly_rate_ttc, selectedSubscriptionForModal.estimated_currency || client.preferred_currency)}/h`
                        : "n/a"}{" "}
                      |
                      Apres surcouche:{" "}
                      {row.effective_hourly_rate_ttc
                        ? `${formatMoney(
                            row.effective_hourly_rate_ttc,
                            selectedSubscriptionForModal.estimated_currency || client.preferred_currency,
                          )}/h`
                        : "n/a"}
                    </p>
                    <div className="grid cols-3 config-form-grid">
                      <label>
                        Remise fidelite / h TTC
                        <input
                          type="text"
                          name={`forfait_loyalty_discount_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.loyalty_discount_per_hour_ttc ?? "0"}
                        />
                      </label>
                      <label>
                        Remise famille / h TTC
                        <input
                          type="text"
                          name={`forfait_family_discount_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.family_discount_per_hour_ttc ?? "0"}
                        />
                      </label>
                      <label>
                        Supplement sans engagement / h TTC
                        <input
                          type="text"
                          name={`forfait_short_commitment_supplement_per_hour_ttc_${row.course_type_id}`}
                          defaultValue={row.short_commitment_supplement_per_hour_ttc ?? "0"}
                        />
                      </label>
                    </div>
                  </article>
                ))
              )}
              <p className="muted">
                Cette surcouche s applique uniquement aux reservations facturees dans la periode active du forfait.
              </p>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit">Enregistrer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "suspend" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Suspendre l abonnement</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={suspendAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <label>
                Debut suspension
                <input
                  type="date"
                  name="suspension_starts_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.suspension_starts_at, todayInputValue)}
                  required
                />
              </label>
              <label>
                Duree
                <input
                  type="number"
                  name="duration_value"
                  min={1}
                  max={30}
                  defaultValue={selectedSubscriptionForModal.suspension_duration_value ?? 7}
                  required
                />
              </label>
              <label>
                Unite
                <select name="duration_unit" defaultValue={selectedSubscriptionForModal.suspension_duration_unit ?? "DAY"}>
                  <option value="DAY">Jours (1-30)</option>
                  <option value="MONTH">Mois (1-12)</option>
                </select>
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit" className="ghost">
                  Suspendre
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "cancel" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Resilier a fin de periode</h3>
            <p className="muted">{selectedSubscriptionForModal.plan.name}</p>
            <form action={cancelAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              {hasBlockingFutureBookingsForCancellation ? (
                <p className="muted">
                  <strong>Annulation impossible.</strong> {blockingFutureBookingsForCancellation.length} reservation(s) future(s) sont deja
                  rattachee(s) a cet abonnement apres la date effective de fin. Supprimez-les d abord.
                  {cancellationConflictPreview ? ` Exemples: ${cancellationConflictPreview}.` : ""}
                </p>
              ) : null}
              {cancelConflictAlert ? (
                <p className="muted">
                  <strong>Annulation refusee.</strong> Des reservations futures liees a ce produit existent encore apres la date de fin.
                </p>
              ) : null}
              <label>
                Date de resiliation
                <input
                  type="date"
                  name="cancellation_requested_at"
                  defaultValue={formatDateForInput(selectedSubscriptionForModal.cancellation_requested_at, todayInputValue)}
                  required
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit" className="danger" disabled={hasBlockingFutureBookingsForCancellation}>
                  Confirmer la resiliation
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedSubscriptionForModal && subscriptionModalAction === "cancel_now" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">
              {selectedSubscriptionForModal.plan.kind === "PACK"
                ? "Annulation immediate du carnet"
                : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                  ? "Cloture immediate du forfait"
                  : "Resiliation immediate"}
            </h3>
            <p className="muted">
              {selectedSubscriptionForModal.plan.kind === "PACK"
                ? `${selectedSubscriptionForModal.plan.name} - cette action cloture le carnet maintenant et annule les credits restants.`
                : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                  ? `${selectedSubscriptionForModal.plan.name} - cette action cloture le forfait maintenant et arrete toute facturation future.`
                  : `${selectedSubscriptionForModal.plan.name} - cette action coupe l abonnement maintenant et desactive tout prochain prelevement.`}
            </p>
            <form action={cancelAdminClientSubscriptionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="subscription_id" value={selectedSubscriptionForModal.id} />
              <input type="hidden" name="immediate_cancel" value="on" />
              {hasBlockingFutureBookingsForCancellation ? (
                <p className="muted">
                  <strong>Annulation impossible.</strong> {blockingFutureBookingsForCancellation.length} reservation(s) future(s) sont deja
                  rattachee(s) a ce produit apres la date effective de fin. Supprimez-les d abord.
                  {cancellationConflictPreview ? ` Exemples: ${cancellationConflictPreview}.` : ""}
                </p>
              ) : null}
              {cancelConflictAlert ? (
                <p className="muted">
                  <strong>Annulation refusee.</strong> Des reservations futures liees a ce produit existent encore apres la date de fin.
                </p>
              ) : null}
              <label>
                Date de demande
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
                  ? "Je confirme l annulation immediate et irreversible du carnet."
                  : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                    ? "Je confirme la cloture immediate et irreversible du forfait."
                    : "Je confirme la resiliation immediate et irreversible."}
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit" className="danger" disabled={hasBlockingFutureBookingsForCancellation}>
                  {selectedSubscriptionForModal.plan.kind === "PACK"
                    ? "Annuler immediatement"
                    : selectedSubscriptionForModal.plan.kind === "FORFAIT"
                      ? "Cloturer immediatement"
                      : "Resilier immediatement"}
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "fiche" && selectedCreditForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "fiche")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Modifier le credit manuel</h3>
            <p className="muted">{selectedCreditForModal.credit_type_name ?? selectedCreditForModal.credit_type_code}</p>
            <form action={updateAdminClientManualCreditAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="credit_type_id" value={selectedCreditForModal.credit_type_id} />
              <label>
                Nombre de credits
                <input type="number" name="credits_count" min={0} max={100000} defaultValue={selectedCreditForModal.credits_count} required />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "fiche")}>
                  Annuler
                </Link>
                <button type="submit">Enregistrer</button>
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
                <h3>Informations personnelles</h3>
                <Link className="mode-link" href={`/admin/clients/${client.id}?tab=infos&edit_infos=1`}>
                  Modifier
                </Link>
              </div>
              <div className="list">
                <article className="item row spread">
                  <span className="muted">Nom complet</span>
                  <strong>{fullName || "Non renseigne"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Email</span>
                  <strong>{client.email}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Tel mob 1</span>
                  <strong>{client.mobile_phone_1 ?? "Non renseigne"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Tel mob 2</span>
                  <strong>{client.mobile_phone_2 ?? "Non renseigne"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Tel domicile</span>
                  <strong>{client.home_phone ?? "Non renseigne"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Adresse</span>
                  <strong>
                    {client.address_line ?? "Non renseignee"}, {client.postal_code ?? "-"} {client.city ?? "-"} ({client.address_country})
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Date de naissance</span>
                  <strong>{formatDateOnly(client.birth_date)}</strong>
                </article>
                <article className="item">
                  <span className="muted">Informations a connaitre</span>
                  <p>{client.important_info ?? "Aucune information specifique"}</p>
                </article>
              </div>
            </article>

            <article className="card">
              <h3>Inscription et rattachements</h3>
              <div className="list">
                <article className="item row spread">
                  <span className="muted">Type adherent</span>
                  <strong>{client.client_kind === "CHILD" ? "Enfant" : "Adulte"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Statut</span>
                  <span className={`status-pill ${statusClass(client.client_status)}`}>{client.client_status}</span>
                </article>
                <article className="item row spread">
                  <span className="muted">Pays residence</span>
                  <strong>{labelFromOptions(COUNTRY_OPTIONS, client.residence_country)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Devise</span>
                  <strong>{labelFromOptions(CURRENCY_OPTIONS, client.preferred_currency)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Fuseau horaire</span>
                  <strong>{client.timezone}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Date du premier cours</span>
                  <strong>{client.first_course_at ? formatDate(client.first_course_at) : "Aucun cours reserve"}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Cree le</span>
                  <strong>{formatDate(client.created_at)}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Mis a jour le</span>
                  <strong>{formatDate(client.updated_at)}</strong>
                </article>
              </div>

              <form action={updateAdminClientGroupsAction} className="grid top-gap-sm">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="return_tab" value="infos" />
                <label>
                  Groupes adherent
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
                <p className="muted">Maintenir Ctrl/Cmd pour selection multiple.</p>
                <button type="submit" className="ghost">
                  Enregistrer les groupes
                </button>
              </form>
            </article>
          </section>

          <section className="grid cols-2">
            <article className="card">
              <h3>Preferences de communication (opt-in)</h3>
              <div className="list">
                <article className="item row spread">
                  <span>Afficher dans les contacts du portail etudiant</span>
                  <span className={`status-pill ${client.portal_contact_visible ? "status-ok" : "status-off"}`}>
                    {client.portal_contact_visible ? "Actif" : "Desactive"}
                  </span>
                </article>
                <article className="item row spread">
                  <span>Recevoir les emails d information</span>
                  <span className={`status-pill ${client.email_opt_in ? "status-ok" : "status-off"}`}>
                    {client.email_opt_in ? "Opt-in" : "Opt-out"}
                  </span>
                </article>
                <article className="item row spread">
                  <span>Recevoir les SMS d information</span>
                  <span className={`status-pill ${client.sms_opt_in ? "status-ok" : "status-off"}`}>
                    {client.sms_opt_in ? "Opt-in" : "Opt-out"}
                  </span>
                </article>
                <article className="item row spread">
                  <span>Rappels de cours par email</span>
                  <span className={`status-pill ${client.lesson_reminder_email_opt_in ? "status-ok" : "status-off"}`}>
                    {client.lesson_reminder_email_opt_in ? "Opt-in" : "Opt-out"}
                  </span>
                </article>
                <article className="item row spread">
                  <span>Rappels de cours par SMS</span>
                  <span className={`status-pill ${client.lesson_reminder_sms_opt_in ? "status-ok" : "status-off"}`}>
                    {client.lesson_reminder_sms_opt_in ? "Opt-in" : "Opt-out"}
                  </span>
                </article>
              </div>
            </article>

            <article className="card">
              <h3>Operations fiche client</h3>
              <form action={sendAdminClientPasswordAction} className="grid">
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="return_tab" value="infos" />
                <button type="submit">Generer et envoyer le mot de passe</button>
                <p className="muted">
                  Le mot de passe est genere automatiquement puis envoye par email avec le template configure.
                </p>
              </form>

              <article className="item top-gap-sm">
                <h4>Note privee interne</h4>
                <p className="muted">Cette note n est jamais visible par le client.</p>
                <p>{client.private_note ?? "Aucune note privee."}</p>
              </article>
            </article>
          </section>

          {openEditInfosModal ? (
            <section className="modal-overlay">
              <article className="modal-panel client-info-modal">
                <Link className="modal-close-x" href={tabHref(client.id, "infos")} aria-label="Fermer">
                  ×
                </Link>
                <header className="activity-modal-header">
                  <h2 className="modal-title">Modifier la fiche client</h2>
                  <p className="muted">Les champs marques * sont obligatoires.</p>
                </header>

                <section className="card modal-card">
                  <form action={updateAdminClientAction} className="grid cols-2">
                    <input type="hidden" name="client_id" value={client.id} />
                    <input type="hidden" name="return_tab" value="infos" />

                    <label>
                      Email (optionnel)
                      <input type="email" name="email" defaultValue={client.email} />
                    </label>

                    <label>
                      Prenom <span className="required-star">*</span>
                      <input type="text" name="first_name" defaultValue={client.first_name ?? ""} maxLength={100} required />
                    </label>

                    <label>
                      Nom <span className="required-star">*</span>
                      <input type="text" name="last_name" defaultValue={client.last_name ?? ""} maxLength={100} required />
                    </label>

                    <label>
                      Tel mob 1
                      <input type="text" name="mobile_phone_1" defaultValue={client.mobile_phone_1 ?? ""} maxLength={30} />
                    </label>

                    <label>
                      Tel mob 2
                      <input type="text" name="mobile_phone_2" defaultValue={client.mobile_phone_2 ?? ""} maxLength={30} />
                    </label>

                    <label>
                      Tel domicile
                      <input type="text" name="home_phone" defaultValue={client.home_phone ?? ""} maxLength={30} />
                    </label>

                    <label className="span-2">
                      Adresse postale
                      <input type="text" name="address_line" defaultValue={client.address_line ?? ""} maxLength={255} />
                    </label>

                    <label>
                      Code postal
                      <input type="text" name="postal_code" defaultValue={client.postal_code ?? ""} maxLength={20} />
                    </label>

                    <label>
                      Ville
                      <input type="text" name="city" defaultValue={client.city ?? ""} maxLength={120} />
                    </label>

                    <label>
                      Pays taxation <span className="required-star">*</span>
                      <select name="address_country" defaultValue={client.address_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Type adherent
                      <select name="client_kind" defaultValue={client.client_kind === "CHILD" ? "CHILD" : "ADULT"} required>
                        <option value="ADULT">Adulte</option>
                        <option value="CHILD">Enfant</option>
                      </select>
                    </label>

                    <label>
                      Statut
                      <select name="client_status" defaultValue={client.client_status || "ACTIVE"} required>
                        <option value="ACTIVE">ACTIF</option>
                        <option value="TRIAL">ESSAI</option>
                        <option value="PENDING">EN ATTENTE</option>
                        <option value="INACTIVE">INACTIF</option>
                        <option value="ARCHIVED">ARCHIVE</option>
                      </select>
                    </label>

                    <label>
                      Pays residence
                      <select name="residence_country" defaultValue={client.residence_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Devise
                      <select name="preferred_currency" defaultValue={client.preferred_currency || DEFAULT_CURRENCY} required>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Fuseau horaire
                      <select name="timezone" defaultValue={client.timezone || DEFAULT_TIMEZONE} required>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Date de naissance
                      <input type="date" name="birth_date" defaultValue={client.birth_date ?? ""} />
                    </label>

                    <label className="span-2">
                      Informations a connaitre
                      <textarea name="important_info" defaultValue={client.important_info ?? ""} rows={4} maxLength={1000} />
                    </label>

                    <label className="span-2">
                      Note privee interne
                      <textarea name="private_note" defaultValue={client.private_note ?? ""} rows={4} maxLength={5000} />
                    </label>

                    <fieldset className="span-2 config-payment-fieldset">
                      <legend>Preferences de communication</legend>
                      <label className="checkline">
                        <input type="checkbox" name="portal_contact_visible" defaultChecked={client.portal_contact_visible} />
                        Afficher dans les contacts du portail etudiant
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="email_opt_in" defaultChecked={client.email_opt_in} />
                        Recevoir les emails d information
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="sms_opt_in" defaultChecked={client.sms_opt_in} />
                        Recevoir les SMS d information
                      </label>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="lesson_reminder_email_opt_in"
                          defaultChecked={client.lesson_reminder_email_opt_in}
                        />
                        Recevoir les rappels de cours par email
                      </label>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="lesson_reminder_sms_opt_in"
                          defaultChecked={client.lesson_reminder_sms_opt_in}
                        />
                        Recevoir les rappels de cours par SMS
                      </label>
                    </fieldset>

                    <div className="row span-2 modal-actions-end">
                      <Link className="reset-link" href={tabHref(client.id, "infos")}>
                        Annuler
                      </Link>
                      <button type="submit">Enregistrer</button>
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
            <h3>Liens familiaux</h3>
            {client.client_kind === "ADULT" ? (
              linkedChildren.length === 0 ? (
                <p className="muted">Aucun enfant rattache a cet adulte.</p>
              ) : (
                <div className="list">
                  {linkedChildren.map((link) => (
                    <article key={link.id} className="item">
                      <div className="row spread">
                        <strong>
                          Enfant:{" "}
                          <Link className="client-name-link" href={tabHref(link.child.id, "fiche")}>
                            {([link.child.first_name, link.child.last_name].filter(Boolean).join(" ") || link.child.email)}
                          </Link>
                        </strong>
                        <span className={`status-pill ${link.is_billing_recipient ? "status-ok" : "status-off"}`}>
                          {link.is_billing_recipient ? "Destinataire facture" : "Facture autre adulte"}
                        </span>
                      </div>
                      <p className="muted">
                        {link.child.email} | Mobile 1: {link.child.mobile_phone_1 ?? "-"} | Relation: {link.relationship_label ?? "non precisee"}
                      </p>
                      <div className="row">
                        {!link.is_billing_recipient ? (
                          <form action={setFamilyBillingRecipientAction}>
                            <input type="hidden" name="link_id" value={link.id} />
                            <input type="hidden" name="return_client_id" value={client.id} />
                            <button className="ghost" type="submit">
                              Definir destinataire facture
                            </button>
                          </form>
                        ) : null}
                        <form action={unlinkFamilyMembersAction}>
                          <input type="hidden" name="link_id" value={link.id} />
                          <input type="hidden" name="return_client_id" value={client.id} />
                          <button className="danger" type="submit">
                            Retirer le lien
                          </button>
                        </form>
                      </div>
                    </article>
                  ))}
                </div>
              )
            ) : linkedAdults.length === 0 ? (
              <p className="muted">Aucun adulte rattache a cet enfant.</p>
            ) : (
              <div className="list">
                {linkedAdults.map((link) => (
                  <article key={link.id} className="item">
                    <div className="row spread">
                      <strong>
                        Adulte: {([link.adult.first_name, link.adult.last_name].filter(Boolean).join(" ") || link.adult.email)}
                      </strong>
                      <span className={`status-pill ${link.is_billing_recipient ? "status-ok" : "status-off"}`}>
                        {link.is_billing_recipient ? "Destinataire facture" : "Coparent"}
                      </span>
                    </div>
                    <p className="muted">
                      {link.adult.email} | Mobile 1: {link.adult.mobile_phone_1 ?? "-"} | Adresse: {link.adult.address_line ?? "-"}
                    </p>
                    <div className="row">
                      {!link.is_billing_recipient ? (
                        <form action={setFamilyBillingRecipientAction}>
                          <input type="hidden" name="link_id" value={link.id} />
                          <input type="hidden" name="return_client_id" value={client.id} />
                          <button className="ghost" type="submit">
                            Definir destinataire facture
                          </button>
                        </form>
                      ) : null}
                      <form action={unlinkFamilyMembersAction}>
                        <input type="hidden" name="link_id" value={link.id} />
                        <input type="hidden" name="return_client_id" value={client.id} />
                        <button className="danger" type="submit">
                          Retirer le lien
                        </button>
                      </form>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="card">
            <h3>Rattacher un compte existant</h3>
            {client.client_kind === "ADULT" ? (
              candidateChildren.length === 0 ? (
                <p className="muted">Aucun profil enfant disponible a rattacher.</p>
              ) : (
                <form action={linkExistingFamilyMembersAction} className="grid">
                  <input type="hidden" name="adult_client_id" value={client.id} />
                  <input type="hidden" name="return_client_id" value={client.id} />
                  <label>
                    Enfant a rattacher
                    <select name="child_client_id" required defaultValue="">
                      <option value="" disabled>
                        Selectionner un enfant
                      </option>
                      {candidateChildren.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {[candidate.first_name, candidate.last_name].filter(Boolean).join(" ") || candidate.email}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Lien de relation
                    <input name="relationship_label" type="text" maxLength={80} placeholder="ex: parent, pere, mere..." />
                  </label>
                  <label className="checkline">
                    <input name="is_billing_recipient" type="checkbox" defaultChecked />
                    Destinataire des factures pour cet enfant
                  </label>
                  <button type="submit">Rattacher enfant existant</button>
                </form>
              )
            ) : candidateAdults.length === 0 ? (
              <p className="muted">Aucun profil adulte disponible a rattacher.</p>
            ) : (
              <form action={linkExistingFamilyMembersAction} className="grid">
                <input type="hidden" name="child_client_id" value={client.id} />
                <input type="hidden" name="return_client_id" value={client.id} />
                <label>
                  Adulte a rattacher
                  <select name="adult_client_id" required defaultValue="">
                    <option value="" disabled>
                      Selectionner un adulte
                    </option>
                    {candidateAdults.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {[candidate.first_name, candidate.last_name].filter(Boolean).join(" ") || candidate.email}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lien de relation
                  <input name="relationship_label" type="text" maxLength={80} placeholder="ex: parent, pere, mere..." />
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" />
                  Definir cet adulte comme destinataire facture
                </label>
                <button type="submit">Rattacher adulte existant</button>
              </form>
            )}
          </article>

          {client.client_kind === "ADULT" ? (
            <article className="card span-2">
              <h3>Creer un enfant et le rattacher</h3>
              <p className="muted">
                Utiliser ce formulaire pour creer un compte enfant (avec ses informations) et le relier directement a cet adulte.
              </p>
              <form action={createChildForAdultAction} className="grid cols-3">
                <input type="hidden" name="adult_client_id" value={client.id} />
                <label>
                  Email (optionnel)
                  <input type="email" name="child_email" />
                </label>
                <label>
                  Prenom <span className="required-star">*</span>
                  <input type="text" name="child_first_name" maxLength={100} required />
                </label>
                <label>
                  Nom <span className="required-star">*</span>
                  <input type="text" name="child_last_name" maxLength={100} required />
                </label>
                <label>
                  Tel mob 1
                  <input type="text" name="child_mobile_phone_1" maxLength={30} />
                </label>
                <label>
                  Tel mob 2
                  <input type="text" name="child_mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  Tel domicile
                  <input type="text" name="child_home_phone" maxLength={30} />
                </label>
                <label className="span-2">
                  Adresse
                  <input type="text" name="child_address_line" maxLength={255} />
                </label>
                <label>
                  Code postal
                  <input type="text" name="child_postal_code" maxLength={20} />
                </label>
                <label>
                  Ville
                  <input type="text" name="child_city" maxLength={120} />
                </label>
                <label>
                  Pays adresse
                  <select name="child_address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Pays residence
                  <select name="child_residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Devise
                  <select name="child_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Fuseau
                  <select name="child_timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Date de naissance
                  <input type="date" name="child_birth_date" />
                </label>
                <label>
                  Lien de relation
                  <input type="text" name="relationship_label" maxLength={80} placeholder="ex: parent" />
                </label>
                <label className="span-2">
                  Informations a connaitre
                  <textarea name="child_important_info" rows={3} maxLength={1000} />
                </label>
                <label>
                  Statut
                  <select name="child_client_status" defaultValue="ACTIVE">
                    <option value="ACTIVE">ACTIF</option>
                    <option value="TRIAL">ESSAI</option>
                    <option value="PENDING">EN ATTENTE</option>
                    <option value="INACTIVE">INACTIF</option>
                    <option value="ARCHIVED">ARCHIVE</option>
                  </select>
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" defaultChecked />
                  Cet adulte recoit les factures
                </label>
                <div className="row span-2">
                  <button type="submit">Creer et rattacher</button>
                </div>
              </form>
            </article>
          ) : (
            <article className="card span-2">
              <h3>Creer un adulte et le rattacher</h3>
              <p className="muted">
                Permet de creer un compte adulte (parent/representant) depuis la fiche enfant puis de choisir le destinataire des factures.
              </p>
              <form action={createAdultForChildAction} className="grid cols-3">
                <input type="hidden" name="child_client_id" value={client.id} />
                <label>
                  Email (optionnel)
                  <input type="email" name="adult_email" />
                </label>
                <label>
                  Prenom <span className="required-star">*</span>
                  <input type="text" name="adult_first_name" maxLength={100} required />
                </label>
                <label>
                  Nom <span className="required-star">*</span>
                  <input type="text" name="adult_last_name" maxLength={100} required />
                </label>
                <label>
                  Tel mob 1
                  <input type="text" name="adult_mobile_phone_1" maxLength={30} />
                </label>
                <label>
                  Tel mob 2
                  <input type="text" name="adult_mobile_phone_2" maxLength={30} />
                </label>
                <label>
                  Tel domicile
                  <input type="text" name="adult_home_phone" maxLength={30} />
                </label>
                <label className="span-2">
                  Adresse
                  <input type="text" name="adult_address_line" maxLength={255} />
                </label>
                <label>
                  Code postal
                  <input type="text" name="adult_postal_code" maxLength={20} />
                </label>
                <label>
                  Ville
                  <input type="text" name="adult_city" maxLength={120} />
                </label>
                <label>
                  Pays adresse
                  <select name="adult_address_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Pays residence
                  <select name="adult_residence_country" defaultValue={DEFAULT_COUNTRY}>
                    {COUNTRY_OPTIONS.map((country) => (
                      <option key={country.value} value={country.value}>
                        {country.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Devise
                  <select name="adult_preferred_currency" defaultValue={DEFAULT_CURRENCY}>
                    {CURRENCY_OPTIONS.map((currency) => (
                      <option key={currency.value} value={currency.value}>
                        {currency.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Fuseau
                  <select name="adult_timezone" defaultValue={DEFAULT_TIMEZONE}>
                    {TIMEZONE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lien de relation
                  <input type="text" name="relationship_label" maxLength={80} placeholder="ex: mere, pere..." />
                </label>
                <label>
                  Statut
                  <select name="adult_client_status" defaultValue="ACTIVE">
                    <option value="ACTIVE">ACTIF</option>
                    <option value="TRIAL">ESSAI</option>
                    <option value="PENDING">EN ATTENTE</option>
                    <option value="INACTIVE">INACTIF</option>
                    <option value="ARCHIVED">ARCHIVE</option>
                  </select>
                </label>
                <label className="checkline">
                  <input name="is_billing_recipient" type="checkbox" defaultChecked />
                  Cet adulte recoit les factures
                </label>
                <div className="row span-2">
                  <button type="submit">Creer adulte et rattacher</button>
                </div>
              </form>
            </article>
          )}
        </section>
      ) : null}

      {currentTab === "messages" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>Communiquer</h3>
            <div className="grid">
              <a className="mode-link" href={`mailto:${encodeURIComponent(client.email)}`}>
                Envoyer un email
              </a>
              <form action={adminClientActionPlaceholder}>
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="action_name" value="Envoi SMS" />
                <button type="submit">Envoyer un SMS</button>
              </form>
              <form action={adminClientActionPlaceholder}>
                <input type="hidden" name="client_id" value={client.id} />
                <input type="hidden" name="action_name" value="Envoi push" />
                <button className="ghost" type="submit">
                  Envoyer un push
                </button>
              </form>
            </div>
          </article>

          <article className="card">
            <h3>Messages envoyes</h3>
            {messageRows.length === 0 ? (
              <p className="muted">Aucun message pour ce client.</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Sujet</th>
                      <th>Statut</th>
                      <th>Session</th>
                    </tr>
                  </thead>
                  <tbody>
                    {messageRows.map((msg) => (
                      <tr key={msg.id}>
                        <td>{formatDate(msg.occurredAt)}</td>
                        <td>{msg.subject}</td>
                        <td>
                          <span className={`status-pill ${statusClass(msg.status)}`}>{msg.status}</span>
                        </td>
                        <td>{msg.session}</td>
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
              <h3>Factures emises et annulees</h3>
              <div className="row">
                <Link
                  className="mode-link"
                  href={invoicesHref(client.id, { payment_modal: "invoice_range", payment_return_tab: "factures" })}
                >
                  Generer une facture
                </Link>
              </div>
            </div>

            {invoices.length === 0 ? (
              <p className="muted">Aucune facture emise/annulee pour ce client.</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Numero</th>
                      <th>Type</th>
                      <th>Libelle</th>
                      <th>Statut facture</th>
                      <th>Total</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((row) => (
                      <tr key={row.key}>
                        <td>{formatDate(row.occurredAt)}</td>
                        <td>{row.invoiceNumber ?? "-"}</td>
                        <td>{row.typeLabel}</td>
                        <td>{row.label}</td>
                        <td>
                          {row.kind === "range" ? (
                            <div className="stack-xs">
                              <span className={`status-pill ${rangeInvoiceStatusClass(row.status)}`}>
                                {rangeInvoiceStatusLabel(row.status)}
                              </span>
                              {row.emailedAt ? (
                                <span className="status-pill status-ok" title={`Envoye le ${formatDate(row.emailedAt)}`}>
                                  Envoye par mail
                                </span>
                              ) : null}
                              {row.remindedAt ? (
                                <span className="status-pill status-warn" title={`Relance le ${formatDate(row.remindedAt)}`}>
                                  Relance
                                </span>
                              ) : null}
                            </div>
                          ) : (
                            invoiceStatusLabel(row.status)
                          )}
                        </td>
                        <td>{row.kind === "range" ? row.totalLabel : formatMoney(row.total, row.currency)}</td>
                        <td>
                          {row.kind === "range" ? (
                            <div className="row payment-row-actions">
                              <a className="client-action-icon" href={row.viewHref} target="_blank" rel="noreferrer" title="Voir la facture">
                                V
                              </a>
                              <a className="client-action-icon" href={row.downloadHref} title="Telecharger la facture">
                                ↓
                              </a>
                              <Link
                                className="client-action-icon"
                                href={invoicesHref(client.id, {
                                  payment_modal: "invoice_email",
                                  payment_return_tab: "factures",
                                  invoice_note_id: row.noteId,
                                  invoice_email_kind: "INVOICE",
                                })}
                                title="Envoyer la facture par courriel"
                              >
                                ✉
                              </Link>
                              <Link
                                className="client-action-icon"
                                href={invoicesHref(client.id, {
                                  payment_modal: "invoice_email",
                                  payment_return_tab: "factures",
                                  invoice_note_id: row.noteId,
                                  invoice_email_kind: "REMINDER",
                                })}
                                title="Envoyer une relance"
                              >
                                R
                              </Link>
                              {row.status !== "PAID" ? (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="PAID" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title="Marquer comme payee">
                                    €
                                  </button>
                                </form>
                              ) : (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="ISSUED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title="Retirer la mention payee (remettre en emise)">
                                    ↺
                                  </button>
                                </form>
                              )}
                              {row.status !== "CANCELLED" ? (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="CANCELLED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon danger" title="Annuler la facture">
                                    ×
                                  </button>
                                </form>
                              ) : (
                                <form action={updateAdminClientRangeInvoiceStatusAction}>
                                  <input type="hidden" name="client_id" value={client.id} />
                                  <input type="hidden" name="note_id" value={row.noteId} />
                                  <input type="hidden" name="status" value="ISSUED" />
                                  <input type="hidden" name="return_tab" value="factures" />
                                  <button type="submit" className="client-action-icon" title="Remettre en statut emise">
                                    ↺
                                  </button>
                                </form>
                              )}
                            </div>
                          ) : (
                            <div className="row payment-row-actions">
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/payments/${encodeURIComponent(row.source)}/${row.paymentId}/invoice?inline=true`}
                                target="_blank"
                                rel="noreferrer"
                                title="Voir la facture"
                              >
                                V
                              </a>
                              <a
                                className="client-action-icon"
                                href={`/admin/clients/${client.id}/payments/${encodeURIComponent(row.source)}/${row.paymentId}/invoice`}
                                title="Telecharger la facture"
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
                                      title="Creer un avoir"
                                    >
                                      A
                                    </Link>
                                  ) : null}
                                  <form action={cancelAdminClientInvoiceAction}>
                                    <input type="hidden" name="client_id" value={client.id} />
                                    <input type="hidden" name="payment_source" value={row.source.toUpperCase()} />
                                    <input type="hidden" name="payment_id" value={row.paymentId} />
                                    <input type="hidden" name="return_tab" value="factures" />
                                    <button type="submit" className="client-action-icon danger" title="Annuler la facture">
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
              <h3>Paiements et transactions</h3>
              <div className="row">
                <span className="badge">Solde en date du {formatDateInputLabel(selectedBalanceDate)}</span>
                {[...totalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={currency} className="badge">
                    Solde {currency}: {formatMoney(String(total), currency)}
                  </span>
                ))}
                {[...pendingTotalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={`pending-${currency}`} className="badge">
                    En attente {currency}: {formatMoney(String(total), currency)}
                  </span>
                ))}
                {[...paidTotalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={`paid-${currency}`} className="badge">
                    Paye {currency}: {formatMoney(String(total), currency)}
                  </span>
                ))}
                {[...cancelledOrNotBillableTotalsByCurrency.entries()].map(([currency, total]) => (
                  <span key={`cancelled-${currency}`} className="badge">
                    Annule/non facturable {currency}: {formatMoney(String(total), currency)}
                  </span>
                ))}
                {hasPaymentFilters ? (
                  <span className="badge">
                    Filtres actifs
                    {paymentFilterQuery ? ` | texte: ${paymentFilterQuery}` : ""}
                    {paymentFilterAmount !== null ? ` | montant: ${paymentFilterAmount.toFixed(2)}` : ""}
                  </span>
                ) : null}
                <form method="get" className="row balance-date-form">
                  <input type="hidden" name="tab" value="paiements" />
                  {paymentFilterQuery ? <input type="hidden" name="payment_filter_q" value={paymentFilterQuery} /> : null}
                  {paymentFilterAmountRaw ? <input type="hidden" name="payment_filter_amount" value={paymentFilterAmountRaw} /> : null}
                  <label className="balance-date-label">
                    Date solde
                    <input type="date" name="balance_date" defaultValue={selectedBalanceDate} />
                  </label>
                  <button type="submit" className="ghost">
                    Mettre a jour
                  </button>
                </form>
                <Link
                  className="mode-link"
                  href={paymentsHref(client.id, { payment_modal: "manual", balance_date: selectedBalanceDate })}
                >
                  Ajouter une transaction
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
                  Filtrer
                </Link>
                <Link
                  className="mode-link"
                  href={paymentsHref(client.id, { payment_modal: "invoice_range", balance_date: selectedBalanceDate })}
                >
                  Generer une facture
                </Link>
                <Link
                  className="client-action-icon payment-add-icon"
                  href={paymentsHref(client.id, {
                    purchase_modal: "wizard",
                    purchase_return_tab: "paiements",
                    balance_date: selectedBalanceDate,
                  })}
                  title="Ajouter un achat"
                >
                  +
                </Link>
              </div>
            </div>

            {payments.length === 0 ? (
              <p className="muted">Aucune transaction pour ce client.</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Type</th>
                      <th>Libelle</th>
                      <th>Formule liee</th>
                      <th>Tarif prestation</th>
                      <th>Statut</th>
                      <th>Total</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPayments.map((row) => (
                      <tr key={`${row.source}-${row.id}`}>
                        <td>{formatDate(row.occurred_at)}</td>
                        <td>{paymentSourceLabel(row.source)}</td>
                        <td>
                          <div className="stack-xs">
                            <span>{row.label}</span>
                            <small className="muted">
                              {row.invoice_number ?? "Sans facture"} | {invoiceStatusLabel(row.invoice_status)}
                            </small>
                          </div>
                        </td>
                        <td>{row.source.toUpperCase() === "BOOKING" ? row.reference ?? "-" : "-"}</td>
                        <td>
                          <div className="stack-xs">
                            <span>{formatMoney(row.total_incl_vat, row.currency)}</span>
                            <small className="muted">
                              HT {formatMoney(row.amount_excl_vat, row.currency)} + TVA {formatMoney(row.vat_amount, row.currency)} (
                              {formatVatRateLabel(row.vat_rate)})
                            </small>
                          </div>
                        </td>
                        <td>
                          <span className={`status-pill ${isIncludedPlanBooking(row) ? "status-off" : paymentStatusClass(row.status)}`}>
                            {paymentStatusDisplayLabel(row)}
                          </span>
                        </td>
                        <td>{formatMoney(row.total_incl_vat, row.currency)}</td>
                        <td>
                          <div className="row payment-row-actions">
                            <a
                              className="client-action-icon"
                              href={`/admin/clients/${client.id}/payments/${encodeURIComponent(row.source)}/${row.id}/invoice`}
                              title="Telecharger la facture"
                            >
                              ↓
                            </a>
                            {row.status !== "REFUNDED" && row.source.toUpperCase() === "PLAN_PURCHASE" ? (
                              <Link
                                className="client-action-icon danger"
                                href={paymentsHref(client.id, {
                                  payment_modal: "refund",
                                  payment_source: row.source.toUpperCase(),
                                  payment_id: row.id,
                                  payment_return_tab: "paiements",
                                })}
                                title="Lancer un remboursement"
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
                  <p className="muted top-gap-sm">Aucune ligne ne correspond aux filtres.</p>
                ) : null}
              </div>
            )}
          </article>

          <article id="payments-history" className="card">
            <h3>Historique des abonnements</h3>
            {subscriptions.length === 0 ? (
              <p className="muted">Aucun abonnement.</p>
            ) : (
              <div className="list top-gap-sm">
                {subscriptions.map((sub) => {
                  const statusPill = subscriptionStatusPill(sub);
                  return (
                    <article key={sub.id} className="item row spread">
                    <div className="stack-sm">
                      <div className="row">
                        <span className={`status-pill ${statusPill.toneClass}`}>{statusPill.label}</span>
                        <strong>{sub.plan.name}</strong>
                      </div>
                      <small className="muted">
                        Debut: {formatDate(sub.started_at)} | Prochain paiement: {sub.next_payment_at ? formatDate(sub.next_payment_at) : "Non programme"}
                      </small>
                    </div>
                    <div className="row">
                      <span className="muted">ID: {sub.id}</span>
                    </div>
                    </article>
                  );
                })}
              </div>
            )}
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && paymentModalAction === "add" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "paiements")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Ajouter un achat</h3>
            <p className="muted">Associer une formule ou un produit au client.</p>
            <form action={adminPurchasePlanForClientAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value="paiements" />
              <label>
                Produit
                <select name="plan_id" required defaultValue="">
                  <option value="" disabled>
                    Selectionner un produit
                  </option>
                  {plans.map((plan) => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} ({planKindLabel(plan.kind)})
                    </option>
                  ))}
                </select>
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "paiements")}>
                  Annuler
                </Link>
                <button type="submit">Ajouter</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openManualTransactionSelector ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "paiements")} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Ajouter une transaction</h3>
            <p className="muted">Paiement, remboursement, montant facture ou rabais.</p>
            <div className="manual-transaction-choice-grid top-gap-sm">
              <Link className="manual-transaction-choice" href={paymentsHref(client.id, { payment_modal: "manual", manual_type: "payment" })}>
                <strong>Paiement</strong>
                <small className="muted">Quand une famille vous regle.</small>
              </Link>
              <Link className="manual-transaction-choice" href={paymentsHref(client.id, { payment_modal: "manual", manual_type: "refund" })}>
                <strong>Remboursement</strong>
                <small className="muted">Quand vous redonnez de l argent a la famille.</small>
              </Link>
              <Link className="manual-transaction-choice" href={paymentsHref(client.id, { payment_modal: "manual", manual_type: "charge" })}>
                <strong>Montant facture</strong>
                <small className="muted">Ajouter un montant du, sans encaissement.</small>
              </Link>
              <Link className="manual-transaction-choice" href={paymentsHref(client.id, { payment_modal: "manual", manual_type: "discount" })}>
                <strong>Rabais</strong>
                <small className="muted">Reduire le montant du (transaction negative).</small>
              </Link>
            </div>
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
              aria-label="Fermer"
            >
              ×
            </Link>
            <h3 className="modal-title">Filtrer les transactions</h3>
            <p className="muted">Recherche libre (libelle, statut, formule) et/ou montant exact TTC.</p>
            <form method="get" action={`/admin/clients/${client.id}`} className="grid top-gap-sm">
              <input type="hidden" name="tab" value="paiements" />
              <input type="hidden" name="balance_date" value={selectedBalanceDate} />
              <label>
                Recherche
                <input type="text" name="payment_filter_q" defaultValue={paymentFilterQuery} placeholder="Ex: collectif, inclus formule..." />
              </label>
              <label>
                Montant TTC
                <input
                  type="number"
                  name="payment_filter_amount"
                  step="0.01"
                  min="-999999"
                  defaultValue={paymentFilterAmountRaw}
                  placeholder="Ex: 38.00"
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={paymentsHref(client.id, { balance_date: selectedBalanceDate })}>
                  Reinitialiser
                </Link>
                <button type="submit">Appliquer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "paiements" && openManualTransactionForm && manualTransactionTypeCode ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, "paiements")} aria-label="Fermer">
              ×
            </Link>
            <Link className="mode-link manual-transaction-back-link" href={paymentsHref(client.id, { payment_modal: "manual" })}>
              Retour aux types
            </Link>
            <h3 className="modal-title">{manualTransactionTitle}</h3>
            <p className="muted">{manualTransactionHelp}</p>
            <form action={createAdminClientManualTransactionAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="currency" value={client.preferred_currency || "EUR"} />
              <input type="hidden" name="transaction_type" value={manualTransactionTypeCode} />
              {manualIsCashFlow ? <input type="hidden" name="vat_rate" value={manualVatDefault} /> : null}
              <label>
                Etudiant (optionnel)
                <select name="student_id" defaultValue="">
                  <option value="">(Non precise)</option>
                  <option value={client.id}>{fullName || client.email}</option>
                  {family.links_as_adult.map((link) => (
                    <option key={link.child.id} value={link.child.id}>
                      {[link.child.first_name, link.child.last_name].filter(Boolean).join(" ") || link.child.email}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Date
                <input type="date" name="occurred_at" defaultValue={todayInputValue} required />
              </label>
              {manualIsCashFlow ? (
                <label>
                  Mode de paiement (optionnel)
                  <select name="payment_method_code" defaultValue="">
                    <option value="">(Non precise)</option>
                    {enabledPaymentMethods.map((method) => (
                      <option key={method.code} value={method.code}>
                        {method.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label>
                {manualTransactionModalType === "discount" ? "Le montant" : "Montant TTC"}
                <input type="number" name="amount_incl_vat" step="0.01" min="0.01" placeholder="0.00" required />
              </label>
              {!manualIsCashFlow ? (
                <>
                  <label>
                    TVA (%)
                    <input type="number" name="vat_rate" step="0.001" min="0" max="100" defaultValue={manualVatDefault} required />
                  </label>
                  <label>
                    Categorie (optionnel)
                    <select name="category" defaultValue="">
                      <option value="">Selectionner...</option>
                      {productCategories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              ) : null}
              <label>
                Libelle (optionnel)
                <input type="text" name="label" maxLength={255} defaultValue={manualTransactionDefaultLabel} placeholder="Ex: Frais de dossier" />
              </label>
              <label>
                Reference (optionnelle)
                <input type="text" name="reference" maxLength={120} placeholder="Ex: CHEQUE-1024 / VIREMENT-2026-02" />
              </label>
              <label>
                Description (optionnel)
                <textarea name="description" rows={3} maxLength={2000} placeholder="Ce texte apparaitra dans la facture." />
              </label>
              {!manualIsCashFlow && productCategories.length === 0 ? (
                <p className="muted">
                  Aucune categorie disponible. Configurez-les dans{" "}
                  <Link className="mode-link" href="/admin/config?section=products">
                    Les produits
                  </Link>
                  .
                </p>
              ) : null}
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, "paiements")}>
                  Annuler
                </Link>
                <button type="submit">Ajouter la transaction</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") && paymentModalAction === "invoice_range" ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Generer une facture</h3>
            <p className="muted">Genere un document pour une plage de dates.</p>
            <form action={createAdminClientRangeInvoiceAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="return_tab" value="factures" />
              <label>
                Date d emission (obligatoire)
                <input type="date" name="issued_date" defaultValue={todayInputValue} required />
              </label>
              <label>
                Date de debut
                <input type="date" name="start_date" defaultValue={monthStartInputValue} required />
              </label>
              <label>
                Date de fin
                <input type="date" name="end_date" defaultValue={todayInputValue} required />
              </label>
              <label>
                Date d echeance (obligatoire)
                <input type="date" name="due_date" defaultValue={dueDateInputValue} required />
              </label>
              <label>
                Lignes en attente
                <select name="include_pending" defaultValue="true">
                  <option value="true">Inclure</option>
                  <option value="false">Exclure</option>
                </select>
              </label>
              <label>
                Lignes annulees
                <select name="include_cancelled" defaultValue="false">
                  <option value="false">Exclure</option>
                  <option value="true">Inclure</option>
                </select>
              </label>
              {hasForfaitPlan ? (
                <label className="span-2">
                  Format de facture (forfait)
                  <select name="layout" defaultValue="COMPILED">
                    <option value="DETAILED">Facture detaillee (toutes les lignes)</option>
                    <option value="COMPILED">Facture compilee (regroupee par prestation)</option>
                  </select>
                </label>
              ) : (
                <input type="hidden" name="layout" value="DETAILED" />
              )}
              <label className="span-2">
                Note publique (optionnel)
                <textarea name="public_note" rows={3} maxLength={2000} placeholder="Cette note apparaitra en bas de la facture." />
              </label>
              <label className="span-2">
                Note privee (optionnel)
                <textarea
                  name="private_note"
                  rows={3}
                  maxLength={2000}
                  placeholder="Visible uniquement dans le back-office (admin/comptable)."
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  Annuler
                </Link>
                <button type="submit">Creer</button>
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
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Courriel facture</h3>
            <p className="muted">Facture {selectedRangeInvoiceForModal.invoiceNumber}. Vous pouvez modifier destinataires, objet et message.</p>
            <form action={sendAdminClientRangeInvoiceEmailAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="note_id" value={selectedRangeInvoiceForModal.noteId} />
              <input type="hidden" name="return_tab" value={paymentReturnTab} />
              <label>
                Type d envoi
                <select name="kind" defaultValue={invoiceEmailKind}>
                  <option value="INVOICE">Facture</option>
                  <option value="REMINDER">Relance facture</option>
                </select>
              </label>
              <label className="span-2">
                Destinataires (un email par ligne)
                <textarea
                  name="to_emails"
                  rows={3}
                  defaultValue={(invoiceEmailPreview?.to_emails ?? []).join("\n")}
                  placeholder="client@exemple.com"
                />
              </label>
              <label className="span-2">
                Objet
                <input type="text" name="subject" maxLength={255} defaultValue={invoiceEmailPreview?.subject ?? ""} />
              </label>
              <label className="span-2">
                Message
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  defaultValue={invoiceEmailPreview?.body ?? ""}
                  defaultFormat={invoiceEmailPreview?.body_format ?? "TEXT"}
                  rows={12}
                  maxLength={20000}
                  placeholder="Contenu du courriel"
                />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  Annuler
                </Link>
                <button type="submit">Envoyer</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {(currentTab === "paiements" || currentTab === "factures") && selectedPaymentForModal ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <Link className="modal-close-x" href={tabHref(client.id, paymentReturnTab)} aria-label="Fermer">
              ×
            </Link>
            <h3 className="modal-title">Rembourser le paiement</h3>
            <p className="muted">
              {selectedPaymentForModal.label} | {formatMoney(selectedPaymentForModal.total_incl_vat, selectedPaymentForModal.currency)}
            </p>
            <form action={refundAdminClientPaymentAction} className="grid top-gap-sm">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="payment_source" value={selectedPaymentForModal.source.toUpperCase()} />
              <input type="hidden" name="payment_id" value={selectedPaymentForModal.id} />
              <input type="hidden" name="return_tab" value={paymentReturnTab} />
              <label>
                Motif (optionnel)
                <textarea name="reason" rows={3} maxLength={1000} placeholder="Ex: remboursement commercial" />
              </label>
              <div className="row modal-actions-end">
                <Link className="reset-link" href={tabHref(client.id, paymentReturnTab)}>
                  Annuler
                </Link>
                <button type="submit" className="danger">
                  Confirmer le remboursement
                </button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {currentTab === "reservations" ? (
        <section className="grid cols-2">
          <article className="card">
            <h3>Stats reservations</h3>
            <div className="list">
              <article className="item row spread">
                <span className="muted">Taux de presence</span>
                <strong>{formatPercent(attendanceRate)}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Reservations a venir</span>
                <strong>{upcomingBookings.length}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Historique reservations</span>
                <strong>{pastBookings.length}</strong>
              </article>
            </div>

            <form action={adminClientActionPlaceholder} className="grid">
              <input type="hidden" name="client_id" value={client.id} />
              <input type="hidden" name="action_name" value="Rattachement de cours" />
              <button type="submit">Rattacher un cours</button>
            </form>
          </article>

          <article className="card">
            <h3>Planning du client</h3>
            <h4>Prochains cours</h4>
            {upcomingBookings.length === 0 ? (
              <p className="muted">Aucune reservation a venir.</p>
            ) : (
              <div className="list">
                {upcomingBookings.slice(0, 12).map((row) => (
                  <article key={row.id} className="item">
                    <div className="row spread">
                      <strong>{row.session_title}</strong>
                      <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
                    </div>
                    <p className="muted">
                      {formatDate(row.session_start_at_utc)} | {row.course_type_name} | {row.location_name}
                    </p>
                  </article>
                ))}
              </div>
            )}

            <h4>Historique recent</h4>
            {pastBookings.length === 0 ? (
              <p className="muted">Pas encore d&apos;historique.</p>
            ) : (
              <div className="list">
                {pastBookings.slice(0, 10).map((row) => (
                  <article key={row.id} className="item row spread">
                    <div>
                      <strong>{row.session_title}</strong>
                      <p className="muted">{formatDate(row.session_start_at_utc)}</p>
                    </div>
                    <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
                  </article>
                ))}
              </div>
            )}
          </article>
        </section>
      ) : null}
    </section>
  );
}
