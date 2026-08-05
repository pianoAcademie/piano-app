import Link from "next/link";
import { redirect } from "next/navigation";

import PortalImpersonationBanner from "../../components/portal-impersonation-banner";
import PortalReadOnlyPreviewGuard from "../../components/portal-read-only-preview-guard";
import { getAdminToken, getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import {
  cancelBookingAction,
  changePasswordAction,
  endPortalImpersonationAction,
  logoutAction,
  openClientPaymentCheckoutAction,
  purchasePlanAction,
  startFormulaPurchaseLinkAction,
  submitPublicSessionCheckoutAction,
  updateProfileAction,
} from "../../lib/actions";
import {
  COUNTRY_OPTIONS,
  CURRENCY_OPTIONS,
  DEFAULT_COUNTRY,
  DEFAULT_CURRENCY,
  DEFAULT_TIMEZONE,
  TIMEZONE_OPTIONS,
  labelFromOptions,
} from "../../lib/reference-data";
import type {
  ClientBookingOut,
  ClientCatalogProductOut,
  ClientContentCourseOut,
  ClientContentLessonOut,
  ClientFamilyOverviewOut,
  ClientPaymentConfirmOut,
  ClientInvoiceOut,
  ClientMessageOut,
  ClientPaymentCheckoutOut,
  ClientSessionReservationMemberOptionOut,
  ClientSessionPurchaseCatalogOut,
  ClientSessionReservationOptionsOut,
  ClientPaymentOut,
  PublicFormulaPurchaseContextOut,
  CourseTypeOut,
  LocationOut,
  MakeupStudentSummaryOut,
  PlanOut,
  SessionOut,
  SubscriptionOut,
  UserOut,
} from "../../lib/types";
import Card from "../../components/client-ui/card";
import AutoSubmitInput from "../../components/auto-submit-input";
import AutoSubmitSelect from "../../components/auto-submit-select";
import DrawerFilters from "../../components/client-ui/drawer-filters";
import ListRow from "../../components/client-ui/list-row";
import MobileHeader from "../../components/client-ui/mobile-header";
import MobileTabs from "../../components/client-ui/mobile-tabs";
import CopyIdButton from "../../components/client-ui/copy-id-button";
import StatChip from "../../components/client-ui/stat-chip";
import Toast from "../../components/client-ui/toast";
import PortalBrandLockup from "../../components/portal-brand-lockup";
import CompactInvoiceRow from "../../components/ui-client/compact-invoice-row";
import FilterChipsBar from "../../components/ui-client/filter-chips-bar";
import KPIBlock from "../../components/ui-client/kpi-block";
import PlanCard from "../../components/ui-client/plan-card";
import SectionCard from "../../components/ui-client/section-card";
import TransactionRow from "../../components/ui-client/transaction-row";
import UpcomingLessonRow from "../../components/ui-client/upcoming-lesson-row";
import UrgentPayCard from "../../components/ui-client/urgent-pay-card";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthErrorMessage, resolveAuthOkMessage, translateBackendMessage, type UiLanguage, uiText } from "../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type AgendaView = "agenda" | "week" | "day";
type DashboardTab = "home" | "planning" | "courses" | "reservations" | "offers" | "finance" | "messages" | "account";
type MessageScope = "LAST_3_MONTHS" | "CURRENT_YEAR" | "ALL";
type TimeBucket = "ALL" | "MORNING" | "AFTERNOON" | "EVENING";
type PlanningSlotFilter = "ALL" | "AVAILABLE" | "ALREADY_BOOKED";
type PlanningStatusCode =
  | "ALREADY_BOOKED"
  | "WAITLISTED"
  | "PAYMENT_PENDING"
  | "FULL"
  | "PAST"
  | "CLOSED"
  | "PAYMENT_REQUIRED"
  | "AVAILABLE"
  | "INCOMPATIBLE_PLAN"
  | "NO_PLAN"
  | "BOOKABLE"
  | "UNAVAILABLE";
type FinanceView = "transactions" | "invoices";
type FinanceStatusFilter = "ALL" | "TO_PAY" | "PAID" | "CANCELLED" | "FAILED";
type FinancePeriodFilter = "ALL" | "LAST_30_DAYS" | "LAST_90_DAYS" | "LAST_365_DAYS";
type OfferCatalogCategory =
  | "ALL"
  | "PIANO_ONSITE"
  | "PIANO_ONLINE"
  | "REHEARSAL_STUDIO"
  | "SHEET_MUSIC"
  | "NOTE_GAMES"
  | "THEORY_BOOKS"
  | "PASSES"
  | "OTHER";

type AgendaRange = {
  from: Date;
  to: Date;
  dayKeys: string[];
  title: string;
};

type FamilyBookingRow = {
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
    location_name?: string | null;
  };
};

type MemberLite = {
  id: string;
  display_name: string;
  email: string | null;
  kind: string;
};

const SESSION_ACCENT_COLORS = [
  "#f08a24",
  "#69b7ef",
  "#94c973",
  "#c27aa9",
  "#5fa8a0",
  "#f2c14e",
  "#90be6d",
  "#7b9acc",
];
const FINANCE_PAGE_SIZES = [20, 30] as const;
const FINANCE_PENDING_STATUSES = new Set(["PENDING", "OPEN", "CREATED", "PROCESSING", "WAITING_PAYMENT"]);
const FINANCE_CANCELLED_STATUSES = new Set(["CANCELLED", "CANCELED", "NOT_BILLABLE", "REFUNDED"]);
const FINANCE_FAILED_STATUSES = new Set(["FAILED", "ERROR", "DECLINED", "NETWORK_ERROR", "UNEXPECTED_ERROR"]);
const FAMILY_BOOKING_OWNER = "FAMILY";
const ACTIVE_CLIENT_BOOKING_STATUSES = new Set(["BOOKED", "WAITLISTED", "PENDING_PAYMENT"]);
const PORTAL_VISIBLE_SUBSCRIPTION_STATUSES = new Set(["ACTIVE", "PAYMENT_ALERT", "PAUSED", "PRE_TERMINATION"]);
const OFFER_CATALOG_CATEGORIES: Array<{
  key: Exclude<OfferCatalogCategory, "ALL">;
  labelKey: string;
  icon: string;
}> = [
  { key: "PIANO_ONSITE", labelKey: "client.offer_category_piano_onsite", icon: "♩" },
  { key: "PIANO_ONLINE", labelKey: "client.offer_category_piano_online", icon: "⌁" },
  { key: "REHEARSAL_STUDIO", labelKey: "client.offer_category_rehearsal_studio", icon: "♫" },
  { key: "SHEET_MUSIC", labelKey: "client.offer_category_sheet_music", icon: "▤" },
  { key: "NOTE_GAMES", labelKey: "client.offer_category_note_games", icon: "♬" },
  { key: "THEORY_BOOKS", labelKey: "client.offer_category_theory_books", icon: "▦" },
  { key: "PASSES", labelKey: "client.offer_category_passes", icon: "✓" },
  { key: "OTHER", labelKey: "client.offer_category_other", icon: "+" },
];

function normalizeCatalogText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function offerCategoriesFromText(value: string): Exclude<OfferCatalogCategory, "ALL">[] {
  const text = normalizeCatalogText(value);
  const categories: Exclude<OfferCatalogCategory, "ALL">[] = [];
  const hasOnline = /\b(online|en ligne|distanciel|visio)\b/.test(text);
  const hasOnsite = /\b(presentiel|sur place)\b/.test(text);

  if (/\b(pass|recup|rattrap)/.test(text)) categories.push("PASSES");
  if (/\b(studio|repetition)\b/.test(text)) categories.push("REHEARSAL_STUDIO");
  if (/\bpartition/.test(text)) categories.push("SHEET_MUSIC");
  if (/\bjeu(x)?\b.*\bnote(s)?\b|\bnote(s)?\b.*\bjeu(x)?\b/.test(text)) categories.push("NOTE_GAMES");
  if (/\bcahier(s)?\b.*\bsolfege\b|\bsolfege\b.*\bcahier(s)?\b/.test(text)) categories.push("THEORY_BOOKS");
  if (hasOnline && /\b(piano|cours|solfege|musique)\b/.test(text)) categories.push("PIANO_ONLINE");
  if ((hasOnsite || (!hasOnline && /\b(piano|cours)\b/.test(text))) && /\b(piano|cours|musique)\b/.test(text)) {
    categories.push("PIANO_ONSITE");
  }

  const categoryOrder = new Map(OFFER_CATALOG_CATEGORIES.map((category, index) => [category.key, index]));
  return Array.from(new Set(categories)).sort(
    (left, right) => (categoryOrder.get(left) ?? 99) - (categoryOrder.get(right) ?? 99),
  );
}

function planOfferCategories(plan: PlanOut): Exclude<OfferCatalogCategory, "ALL">[] {
  const categories = offerCategoriesFromText(
    [plan.name, plan.code, plan.description, ...(plan.entitlement_course_type_names ?? [])].filter(Boolean).join(" "),
  );
  return categories.length > 0 ? categories : ["OTHER"];
}

function productOfferCategories(product: ClientCatalogProductOut): Exclude<OfferCatalogCategory, "ALL">[] {
  const categories = offerCategoriesFromText(
    [product.category_name, product.title, product.short_description, product.primary_location_name].filter(Boolean).join(" "),
  );
  return categories.length > 0 ? categories : ["OTHER"];
}

function parseOfferCatalogCategory(value: string): OfferCatalogCategory {
  const normalized = normalizeStatus(value);
  if (normalized === "ALL" || OFFER_CATALOG_CATEGORIES.some((category) => category.key === normalized)) {
    return normalized as OfferCatalogCategory;
  }
  return "ALL";
}

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function toSingleValueSearchParams(params: SearchParams): URLSearchParams {
  const out = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(params)) {
    if (Array.isArray(rawValue)) {
      if (rawValue[0]) {
        out.set(key, rawValue[0]);
      }
      continue;
    }
    if (rawValue) {
      out.set(key, rawValue);
    }
  }
  return out;
}

function safeDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseTab(value: string): DashboardTab {
  if (value === "transactions") {
    return "finance";
  }
  if (value === "reservations") {
    return "planning";
  }
  if (value === "planning" || value === "courses" || value === "offers" || value === "finance" || value === "messages" || value === "account") {
    return value;
  }
  return "home";
}

function parseAgendaView(value: string): AgendaView {
  if (value === "week" || value === "day") {
    return value;
  }
  return "agenda";
}

function parseMessageScope(value: string): MessageScope {
  if (value === "CURRENT_YEAR" || value === "ALL") {
    return value;
  }
  return "LAST_3_MONTHS";
}

function parseTimeBucket(value: string): TimeBucket {
  if (value === "MORNING" || value === "AFTERNOON" || value === "EVENING") {
    return value;
  }
  return "ALL";
}

function parsePlanningSlotFilter(value: string): PlanningSlotFilter {
  if (value === "AVAILABLE" || value === "ALREADY_BOOKED") {
    return value;
  }
  return "ALL";
}

function parseFinanceView(value: string): FinanceView {
  if (value === "invoices") {
    return "invoices";
  }
  return "transactions";
}

function parseFinanceStatusFilter(value: string): FinanceStatusFilter {
  if (value === "TO_PAY" || value === "PAID" || value === "CANCELLED" || value === "FAILED") {
    return value;
  }
  return "ALL";
}

function parseFinancePeriodFilter(value: string): FinancePeriodFilter {
  if (value === "LAST_30_DAYS" || value === "LAST_90_DAYS" || value === "LAST_365_DAYS") {
    return value;
  }
  return "ALL";
}

function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

function parseFinancePageSize(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (FINANCE_PAGE_SIZES.includes(parsed as (typeof FINANCE_PAGE_SIZES)[number])) {
    return parsed;
  }
  return FINANCE_PAGE_SIZES[0];
}

function normalizeStatus(value: string): string {
  return value.trim().toUpperCase();
}

function sessionProfessorName(session: SessionOut): string {
  if (!session.professor) {
    return "Sans professeur";
  }
  const fullName = `${session.professor.first_name} ${session.professor.last_name}`.trim();
  return fullName || "Sans professeur";
}

function statusClass(value: string): string {
  const normalized = normalizeStatus(value);
  if (normalized === "BOOKED") {
    return "status-booked";
  }
  if (normalized === "WAITLISTED") {
    return "status-waitlist";
  }
  if (normalized.includes("CANCEL")) {
    return "status-cancelled";
  }
  if (normalized === "NOT_BILLABLE") {
    return "status-cancelled";
  }
  if (normalized.includes("COMPLETED") || normalized.includes("ATTENDED")) {
    return "status-completed";
  }
  if (normalized.includes("WAIT")) {
    return "status-waitlist";
  }
  if (normalized.includes("PENDING")) {
    return "status-pending";
  }
  return "status-scheduled";
}

function statusLabel(value: string, language: UiLanguage = "fr"): string {
  const normalized = normalizeStatus(value);
  if (normalized === "SKIPPED") {
    return uiText(language, "client.status_not_sent");
  }
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
  if (normalized === "NO_SHOW") {
    return uiText(language, "client.status_absent");
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return uiText(language, "client.status_excused_absence");
  }
  if (normalized === "NOT_BILLABLE") {
    return uiText(language, "client.status_not_billable");
  }
  if (normalized === "ACTIVE") {
    return uiText(language, "client.status_active");
  }
  if (normalized === "RESPONSABLE") {
    return "RESPONSABLE";
  }
  if (normalized === "PAID") {
    return uiText(language, "client.status_paid");
  }
  if (
    normalized === "PENDING" ||
    normalized === "PENDING_PAYMENT" ||
    normalized === "OPEN" ||
    normalized === "CREATED" ||
    normalized === "PROCESSING" ||
    normalized === "WAITING_PAYMENT"
  ) {
    return uiText(language, "client.status_pending");
  }
  return normalized || "-";
}

function financeStatusLabel(value: string, language: UiLanguage = "fr"): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PAID") {
    return uiText(language, "client.finance_status_paid");
  }
  if (FINANCE_PENDING_STATUSES.has(normalized)) {
    return uiText(language, "client.finance_status_to_pay");
  }
  if (FINANCE_CANCELLED_STATUSES.has(normalized)) {
    return uiText(language, "client.finance_status_cancelled");
  }
  if (FINANCE_FAILED_STATUSES.has(normalized)) {
    return uiText(language, "client.finance_status_failed");
  }
  return statusLabel(value, language);
}

function isCancelledFinanceStatus(value: string): boolean {
  return FINANCE_CANCELLED_STATUSES.has(normalizeStatus(value));
}

function statusMatchesFinanceFilter(statusValue: string, filter: FinanceStatusFilter): boolean {
  if (filter === "ALL") {
    return true;
  }
  const normalized = normalizeStatus(statusValue);
  if (filter === "TO_PAY") {
    return FINANCE_PENDING_STATUSES.has(normalized);
  }
  if (filter === "PAID") {
    return normalized === "PAID";
  }
  if (filter === "CANCELLED") {
    return FINANCE_CANCELLED_STATUSES.has(normalized);
  }
  return FINANCE_FAILED_STATUSES.has(normalized);
}

function matchesFinancePeriod(dateValue: string, period: FinancePeriodFilter, now: Date): boolean {
  if (period === "ALL") {
    return true;
  }
  const rowDate = safeDate(dateValue);
  if (!rowDate) {
    return false;
  }
  const days = period === "LAST_30_DAYS" ? 30 : period === "LAST_90_DAYS" ? 90 : 365;
  const minTime = now.getTime() - days * 24 * 60 * 60 * 1000;
  return rowDate.getTime() >= minTime;
}

function matchesFinanceAsOf(dateValue: string, asOfUtcEnd: Date): boolean {
  const rowDate = safeDate(dateValue);
  if (!rowDate) {
    return false;
  }
  return rowDate.getTime() <= asOfUtcEnd.getTime();
}

function financePeriodLabel(period: FinancePeriodFilter, language: UiLanguage = "fr"): string {
  if (period === "LAST_30_DAYS") {
    return language === "en" ? "30d" : "30j";
  }
  if (period === "LAST_90_DAYS") {
    return language === "en" ? "90d" : "90j";
  }
  if (period === "LAST_365_DAYS") {
    return language === "en" ? "1y" : "1 an";
  }
  return uiText(language, "client.all_periods");
}

function canPayNowForPayment(row: ClientPaymentOut): boolean {
  return normalizeStatus(row.source) === "PLAN_PURCHASE" && FINANCE_PENDING_STATUSES.has(normalizeStatus(row.status));
}

function normalizePaymentKey(raw: string | null | undefined): string | null {
  const value = String(raw ?? "").trim();
  if (!value) {
    return null;
  }
  const parts = value.split(":", 2);
  if (parts.length !== 2) {
    return null;
  }
  const source = parts[0].trim().toUpperCase();
  const paymentId = parts[1].trim().toLowerCase();
  if (!source || !paymentId) {
    return null;
  }
  return `${source}:${paymentId}`;
}

function paymentKeyFromPaymentRow(row: ClientPaymentOut): string | null {
  const source = normalizeStatus(row.source);
  const rawId = String(row.id || "").split(":", 2)[1] ?? "";
  if (!source || !rawId) {
    return null;
  }
  return normalizePaymentKey(`${source}:${rawId}`);
}

function parseMoneyValue(raw: string | null | undefined): number {
  const parsed = Number(raw ?? "0");
  return Number.isFinite(parsed) ? parsed : 0;
}

function sourceLabel(value: string, language: UiLanguage = "fr"): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PLAN_PURCHASE") {
    return uiText(language, "client.finance_source_invoice");
  }
  if (normalized === "BOOKING") {
    return uiText(language, "client.finance_source_invoice");
  }
  if (normalized === "INVOICE_RANGE") {
    return uiText(language, "client.finance_source_invoice");
  }
  if (normalized === "BOOKING_CREDIT") {
    return uiText(language, "client.finance_source_discount");
  }
  if (normalized === "REFUND") {
    return uiText(language, "client.finance_source_refund");
  }
  if (normalized === "MANUAL") {
    return uiText(language, "client.finance_source_payment");
  }
  return uiText(language, "client.finance_source_transaction");
}

function planKindLabel(value: string, language: UiLanguage = "fr"): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PACK") {
    return uiText(language, "client.plan_pack");
  }
  if (normalized === "SUBSCRIPTION") {
    return uiText(language, "client.plan_subscription");
  }
  if (normalized === "FORFAIT") {
    return uiText(language, "client.plan_forfait");
  }
  return normalized || uiText(language, "client.plan_forfait");
}

function compactId(value: string): string {
  if (!value) {
    return "-";
  }
  if (value.length <= 14) {
    return value;
  }
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function paymentMethodLabel(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const normalized = normalizeStatus(value || "");
  if (!normalized) {
    return language === "en" ? "Not specified" : "Mode non renseigne";
  }
  if (normalized.includes("CARD")) {
    return "CB ••••";
  }
  if (normalized.includes("SEPA")) {
    return "SEPA";
  }
  if (normalized.includes("PAYPAL")) {
    return "PayPal";
  }
  if (normalized.includes("CASH")) {
    return uiText(language, "admin.client_detail.billing.cash");
  }
  if (normalized.includes("TRANSFER")) {
    return uiText(language, "admin.client_detail.billing.bank_transfer");
  }
  if (normalized.includes("CHECK")) {
    return uiText(language, "admin.client_detail.billing.check");
  }
  return normalized;
}

function formatDate(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), { day: "2-digit", month: "short", year: "numeric" });
}

function invoicePeriodSubline(label: string | null | undefined, language: UiLanguage = "fr"): string {
  const value = String(label ?? "").trim();
  const match = value.match(/^(\d{4}-\d{2}-\d{2})(?:\s+-\s+(\d{4}-\d{2}-\d{2}))?$/);
  if (!match) {
    return value;
  }
  const [, startDate, endDate] = match;
  const periodLabel = endDate ? `${formatDate(startDate, language)} - ${formatDate(endDate, language)}` : formatDate(startDate, language);
  return `${uiText(language, "client.billed_period")}: ${periodLabel}`;
}

function formatDateTime(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDateInTimezone(value: string | null | undefined, timezone: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: resolveTimezone(timezone),
  });
}

function formatDateTimeInTimezone(value: string | null | undefined, timezone: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: resolveTimezone(timezone),
  });
}

function formatTimeInTimezone(value: string | null | undefined, timezone: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: resolveTimezone(timezone),
  });
}

function formatTime(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toMoney(amountRaw: string | null | undefined, currencyRaw: string | null | undefined, language: UiLanguage = "fr"): string {
  const amount = Number(amountRaw ?? "0");
  const currency = (currencyRaw || "EUR").toUpperCase();
  if (!Number.isFinite(amount)) {
    return "-";
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function planDisplayPrice(plan: PlanOut | null | undefined): string | null {
  if (!plan) {
    return null;
  }
  if (plan.price_ttc != null) {
    return plan.price_ttc;
  }
  if (plan.monthly_price_excl_vat != null) {
    return plan.monthly_price_excl_vat;
  }
  return null;
}

function isSubscriptionActiveNow(
  sub: { status: string; started_at: string; ends_at: string | null; bookings_blocked?: boolean | null },
  now: Date,
): boolean {
  const normalized = normalizeStatus(sub.status);
  if (normalized === "PAYMENT_ALERT") {
    if (Boolean(sub.bookings_blocked)) {
      return false;
    }
  } else if (normalized !== "ACTIVE") {
    return false;
  }
  const startedAt = safeDate(sub.started_at);
  const endsAt = safeDate(sub.ends_at);
  if (startedAt && startedAt > now) {
    return false;
  }
  if (endsAt && endsAt <= now) {
    return false;
  }
  return true;
}

function isPendingSubscriptionStatus(status: string): boolean {
  const normalized = normalizeStatus(status);
  return (
    normalized === "PENDING" ||
    normalized === "OPEN" ||
    normalized === "CREATED" ||
    normalized === "PROCESSING" ||
    normalized === "WAITING_PAYMENT"
  );
}

function isPendingSubscriptionCoveredInPreview(
  sub: { status: string; started_at: string; ends_at: string | null },
  now: Date,
): boolean {
  if (!isPendingSubscriptionStatus(sub.status)) {
    return false;
  }
  const startedAt = safeDate(sub.started_at);
  const endsAt = safeDate(sub.ends_at);
  if (startedAt && startedAt > now) {
    return false;
  }
  if (endsAt && endsAt <= now) {
    return false;
  }
  return true;
}

function isSubscriptionVisibleInPortal(
  sub: {
    status: string;
    ends_at: string | null;
    credits_remaining?: number | null;
    plan: { kind: string };
  },
  now: Date,
): boolean {
  const normalized = normalizeStatus(sub.status);
  const isPending = isPendingSubscriptionStatus(normalized);
  if (!isPending && !PORTAL_VISIBLE_SUBSCRIPTION_STATUSES.has(normalized)) {
    return false;
  }
  const endsAt = safeDate(sub.ends_at);
  if (endsAt && endsAt <= now) {
    return false;
  }
  if (normalizeStatus(sub.plan.kind) === "PACK" && !isPending && (sub.credits_remaining ?? 0) <= 0) {
    return false;
  }
  return true;
}

function nextActiveBookingDateKey(
  bookings: Array<{ status: string; session: { start_at_utc: string } }>,
  timezone: string,
  now: Date,
): string | null {
  const nextBooking = bookings
    .filter((booking) => {
      const sessionStart = safeDate(booking.session.start_at_utc);
      return sessionStart != null && sessionStart >= now && ACTIVE_CLIENT_BOOKING_STATUSES.has(normalizeStatus(booking.status));
    })
    .sort((a, b) => a.session.start_at_utc.localeCompare(b.session.start_at_utc))[0];
  return nextBooking ? dateKeyInTimezone(nextBooking.session.start_at_utc, timezone) : null;
}

function resolveTimezone(value: string | null | undefined): string {
  const fallback = DEFAULT_TIMEZONE;
  const candidate = (value ?? "").trim();
  if (!candidate) {
    return fallback;
  }
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone: candidate }).format(new Date());
    return candidate;
  } catch {
    return fallback;
  }
}

function isDateKey(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function keyToUtcDate(key: string): Date {
  return new Date(`${key}T00:00:00.000Z`);
}

function utcDateToKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addUtcDays(date: Date, days: number): Date {
  const out = new Date(date.getTime());
  out.setUTCDate(out.getUTCDate() + days);
  return out;
}

function shiftDateKeyByDays(key: string, days: number): string {
  return utcDateToKey(addUtcDays(keyToUtcDate(key), days));
}

function startOfMonthUtc(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function startOfWeekUtc(date: Date): Date {
  const day = date.getUTCDay();
  const offsetFromMonday = (day + 6) % 7;
  return addUtcDays(date, -offsetFromMonday);
}

function getDatePart(parts: Intl.DateTimeFormatPart[], type: "year" | "month" | "day"): string {
  return parts.find((part) => part.type === type)?.value ?? "";
}

function dateKeyInTimezone(value: string, timezone: string): string {
  const safeTimezone = resolveTimezone(timezone);
  const baseDate = safeDate(value) ?? new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: safeTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(baseDate);

  const year = getDatePart(parts, "year");
  const month = getDatePart(parts, "month");
  const day = getDatePart(parts, "day");
  return `${year}-${month}-${day}`;
}

function todayKeyInTimezone(timezone: string): string {
  return dateKeyInTimezone(new Date().toISOString(), resolveTimezone(timezone));
}

function isMonthKey(value: string): boolean {
  return /^\d{4}-\d{2}$/.test(value);
}

function monthKeyInTimezone(value: string, timezone: string): string {
  return dateKeyInTimezone(value, timezone).slice(0, 7);
}

function shiftMonthKey(key: string, months: number): string {
  const [yearRaw, monthRaw] = key.split("-");
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return key;
  }
  const shifted = new Date(Date.UTC(year, month - 1 + months, 1));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
}

function formatMonthKey(key: string, language: UiLanguage): string {
  const [yearRaw, monthRaw] = key.split("-");
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return key;
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function agendaDayLabel(dayKey: string, view: AgendaView, language: UiLanguage): string {
  const date = keyToUtcDate(dayKey);
  if (view === "day") {
    return new Intl.DateTimeFormat(localeForUiLanguage(language), {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function buildAgendaRange(view: AgendaView, focusDayKey: string, language: UiLanguage): AgendaRange {
  const focusDate = keyToUtcDate(focusDayKey);

  if (view === "day") {
    const from = focusDate;
    const toExclusive = addUtcDays(from, 1);
    const to = new Date(toExclusive.getTime() - 1);

    return {
      from,
      to,
      dayKeys: [focusDayKey],
      title: new Intl.DateTimeFormat(localeForUiLanguage(language), {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }).format(from),
    };
  }

  if (view === "week") {
    const from = startOfWeekUtc(focusDate);
    const dayKeys: string[] = [];

    for (let i = 0; i < 7; i += 1) {
      dayKeys.push(utcDateToKey(addUtcDays(from, i)));
    }

    const lastDay = addUtcDays(from, 6);
    const toExclusive = addUtcDays(lastDay, 1);
    const to = new Date(toExclusive.getTime() - 1);

    return {
      from,
      to,
      dayKeys,
      title: `${new Intl.DateTimeFormat(localeForUiLanguage(language), {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(from)} - ${new Intl.DateTimeFormat(localeForUiLanguage(language), {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(lastDay)}`,
    };
  }

  // In agenda mode, anchor the list on the selected date (not month start)
  // so the first rendered day is the currently selected day in the strip.
  const monthStart = startOfMonthUtc(focusDate);
  const from = focusDate;
  const nextMonth = new Date(Date.UTC(from.getUTCFullYear(), from.getUTCMonth() + 1, 1));
  const to = new Date(nextMonth.getTime() - 1);

  const dayKeys: string[] = [];
  let cursor = new Date(from.getTime());
  while (cursor < nextMonth) {
    dayKeys.push(utcDateToKey(cursor));
    cursor = addUtcDays(cursor, 1);
  }

  return {
    from,
    to,
    dayKeys,
    title: new Intl.DateTimeFormat(localeForUiLanguage(language), {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(monthStart),
  };
}

function hourInTimezone(value: string | null | undefined, timezone: string): number {
  const parsed = safeDate(value);
  if (!parsed) {
    return -1;
  }
  const hour = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    hour12: false,
    timeZone: resolveTimezone(timezone),
  }).format(parsed);
  const asNumber = Number.parseInt(hour, 10);
  return Number.isFinite(asNumber) ? asNumber : -1;
}

function matchesTimeBucket(value: string | null | undefined, timezone: string, bucket: TimeBucket): boolean {
  if (bucket === "ALL") {
    return true;
  }
  const hour = hourInTimezone(value, timezone);
  if (hour < 0) {
    return true;
  }
  if (bucket === "MORNING") {
    return hour >= 6 && hour < 12;
  }
  if (bucket === "AFTERNOON") {
    return hour >= 12 && hour < 18;
  }
  return hour >= 18;
}

function accentColorForId(id: string): string {
  if (!id) {
    return SESSION_ACCENT_COLORS[0];
  }
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  return SESSION_ACCENT_COLORS[Math.abs(hash) % SESSION_ACCENT_COLORS.length];
}

function memberDisplayName(
  member: { first_name: string | null; last_name: string | null; email: string | null },
  language: UiLanguage = "fr",
): string {
  const fullName = [member.first_name, member.last_name].filter(Boolean).join(" ");
  return fullName || member.email || uiText(language, "common.member");
}

function normalizeLooseSearch(value: string | null | undefined): string {
  return (value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function flattenCourseLessons(
  course: ClientContentCourseOut | null,
): Array<{ lesson: ClientContentLessonOut; sectionTitle: string | null }> {
  if (!course) {
    return [];
  }
  const rows: Array<{ lesson: ClientContentLessonOut; sectionTitle: string | null }> = [];
  for (const section of course.sections) {
    for (const lesson of section.lessons) {
      rows.push({ lesson, sectionTitle: section.title });
    }
  }
  for (const lesson of course.standalone_lessons) {
    rows.push({ lesson, sectionTitle: null });
  }
  return rows;
}

function courseAudienceLabel(course: ClientContentCourseOut, language: UiLanguage = "fr"): string {
  if (course.member_accesses.length === 0) {
    return uiText(language, "client.unknown_access");
  }
  if (course.member_accesses.length === 1) {
    return course.member_accesses[0].member_display_name;
  }
  return uiText(language, "client.member_count", { count: course.member_accesses.length });
}

function emptyAsAll(value: string): string {
  return value.trim() || "ALL";
}

function withUpdatedQuery(base: URLSearchParams, updates: Record<string, string | null | undefined>): string {
  const next = new URLSearchParams(base.toString());
  for (const [key, value] of Object.entries(updates)) {
    if (value == null || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  }
  const query = next.toString();
  return query ? `/client?${query}` : "/client";
}

function resolvePortalErrorMessage(
  rawError: string,
  errorCode: string,
  errorStatus: string,
  language: UiLanguage,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (rawError) {
    return translateBackendMessage(language, rawError);
  }
  const commonMessage = resolveAuthErrorMessage("", errorCode, language);
  if (commonMessage) {
    return commonMessage;
  }
  const normalizedCode = errorCode.trim().toLowerCase();
  const status = Number.parseInt(errorStatus, 10);
  if (normalizedCode === "invoice_unavailable") {
    if (Number.isFinite(status) && status > 0) {
      return t("client.error_invoice_unavailable_with_status", { status });
    }
    return t("client.error_invoice_unavailable");
  }
  if (normalizedCode === "calendar_unavailable") {
    if (Number.isFinite(status) && status > 0) {
      return t("client.error_calendar_unavailable_with_status", { status });
    }
    return t("client.error_calendar_unavailable");
  }
  return "";
}

function resolvePortalWarningMessage(
  rawWarning: string,
  warningCode: string,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (rawWarning) {
    return rawWarning;
  }
  if (warningCode.trim().toLowerCase() === "active_pack_warning") {
    return t("client.pre_purchase_default_warning");
  }
  return "";
}

function clientInvoiceHref(invoiceId: string, options?: { inline?: boolean }): string {
  const encodedId = encodeURIComponent(invoiceId);
  return options?.inline ? `/client/invoices/${encodedId}/download?inline=true` : `/client/invoices/${encodedId}/download`;
}

function buildClientSessionCheckoutHref(sessionId: string, planningReturnTo: string, bookingUserId: string | null): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  if (bookingUserId) {
    params.set("booking_user_id", bookingUserId);
  }
  return `/buy/session/checkout?${params.toString()}`;
}

export default async function DashboardPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = getPortalToken();
  if (!token) {
    if (getAdminToken()) {
      redirect("/admin?error=Ouvrir%20la%20vue%20client%20depuis%20la%20fiche%20client");
    }
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/clients/me", {}, token);
  if (!meResult.ok) {
    redirect("/login?error_code=client_access_required");
  }

  const me = meResult.data;
  const language = normalizeUiLanguage(me.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const tab = parseTab(readParam(searchParams, "tab"));
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const isReadOnlyPreview = Boolean(impersonationClaims?.imp && impersonationClaims?.preview_read_only);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const impersonationNameHint = readParam(searchParams, "imp_name").trim();
  const rawParams = toSingleValueSearchParams(searchParams);

  const selectedCourseType = readParam(searchParams, "course_type_id");
  const selectedLocation = readParam(searchParams, "location_id");
  const selectedCoachId = readParam(searchParams, "coach_id");
  const selectedTimeBucket = parseTimeBucket(readParam(searchParams, "time_bucket"));
  const planningMode = readParam(searchParams, "planning_mode") === "book" ? "book" : "reservations";
  const rawPlanningSlotFilter = parsePlanningSlotFilter(readParam(searchParams, "planning_slot_filter"));
  const planningSlotFilter =
    planningMode === "book" && rawPlanningSlotFilter === "ALL" ? "AVAILABLE" : rawPlanningSlotFilter;
  const timezone = resolveTimezone(readParam(searchParams, "timezone") || me.timezone || DEFAULT_TIMEZONE);
  const requestedAgendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const familyResultPromise = backendRequest<ClientFamilyOverviewOut>("/api/v1/clients/me/family", {}, token);
  const inputAgendaDate = readParam(searchParams, "agenda_date");
  const now = new Date();
  const defaultAgendaDate = todayKeyInTimezone(timezone);
  let autoAgendaDate = defaultAgendaDate;
  if (tab === "planning" && !isDateKey(inputAgendaDate)) {
    const earlyFamilyResult = await familyResultPromise;
    if (earlyFamilyResult.ok) {
      autoAgendaDate = nextActiveBookingDateKey(earlyFamilyResult.data.bookings, timezone, now) ?? defaultAgendaDate;
    }
  }
  const agendaDate = isDateKey(inputAgendaDate) ? inputAgendaDate : autoAgendaDate;
  const agendaView: AgendaView = tab === "planning" ? "week" : requestedAgendaView;
  const agendaRange = buildAgendaRange(agendaView, agendaDate, language);

  const reservationScope = readParam(searchParams, "reservation_scope") || "CURRENT";
  const reservationStatusFilter = readParam(searchParams, "reservation_status");
  const selectedMemberFilter = emptyAsAll(readParam(searchParams, "member_id"));
  const selectedContentMemberFilter = emptyAsAll(readParam(searchParams, "content_member_id"));
  const selectedBookingOwner = readParam(searchParams, "booking_owner_id") || FAMILY_BOOKING_OWNER;
  const selectedSessionMember = readParam(searchParams, "session_member_id");
  const selectedSessionId = readParam(searchParams, "session_id");
  const selectedContentCourseId = readParam(searchParams, "content_course_id");
  const selectedContentLessonId = readParam(searchParams, "content_lesson_id");
  const selectedOfferDetailId = readParam(searchParams, "offer_detail_id");
  const messageScope = parseMessageScope(readParam(searchParams, "message_scope"));
  const messageQuery = readParam(searchParams, "message_query").trim();
  const financeSourceFilter = readParam(searchParams, "finance_source") || "ALL";
  const financeStatusFilter = parseFinanceStatusFilter(readParam(searchParams, "finance_status"));
  const financePeriodFilter = parseFinancePeriodFilter(readParam(searchParams, "finance_period"));
  const financeAsOfInput = readParam(searchParams, "finance_as_of");
  const financeAsOfDateKey = isDateKey(financeAsOfInput) ? financeAsOfInput : todayKeyInTimezone(timezone);
  const financeAsOfUtcEnd = new Date(`${financeAsOfDateKey}T23:59:59.999Z`);
  const financeView = parseFinanceView(readParam(searchParams, "finance_view"));
  const financePageSize = parseFinancePageSize(readParam(searchParams, "finance_page_size"));
  const financePageRaw = parsePositiveInt(readParam(searchParams, "finance_page"), 1);
  const selectedInvoiceId = readParam(searchParams, "invoice_id").trim();
  const paymentSourceParam = normalizeStatus(readParam(searchParams, "source"));
  const paymentIdParam = readParam(searchParams, "payment_id").trim();
  const setupSessionIdParam = readParam(searchParams, "setup_session_id").trim();
  const paymentReturnParam = readParam(searchParams, "payment_return").trim().toLowerCase();
  const purchaseContextParam = readParam(searchParams, "purchase_context").trim();
  const warningMessage = resolvePortalWarningMessage(
    readParam(searchParams, "warning").trim(),
    readParam(searchParams, "warning_code"),
    t,
  );
  const confirmExistingPackPurchase = readParam(searchParams, "confirm_existing_pack_purchase") === "1";
  const confirmPlanId = readParam(searchParams, "confirm_plan_id").trim();
  const editProfile = readParam(searchParams, "edit_profile") === "1";
  const changePassword = readParam(searchParams, "change_password") === "1";
  const homeCalendarView = readParam(searchParams, "home_calendar_view") === "BY_MEMBER" ? "BY_MEMBER" : "FAMILY";
  const preFetchErrors: string[] = [];
  let paymentResultMessage = "";
  let paymentResultError = "";

  const sessionQuery = new URLSearchParams();
  sessionQuery.set("timezone", timezone);
  sessionQuery.set("from", agendaRange.from.toISOString());
  sessionQuery.set("to", agendaRange.to.toISOString());
  if (selectedCourseType) {
    sessionQuery.set("course_type_id", selectedCourseType);
  }
  if (selectedLocation) {
    sessionQuery.set("location_id", selectedLocation);
  }

  if (paymentSourceParam === "SEPA_SETUP" && paymentIdParam && setupSessionIdParam && paymentReturnParam === "success") {
    const normalizedPaymentId = paymentIdParam.startsWith("plan:") ? paymentIdParam.slice("plan:".length) : paymentIdParam;
    const confirm = await backendRequest<ClientPaymentConfirmOut>(
      `/api/v1/clients/me/subscriptions/${normalizedPaymentId}/payment-method-setup/confirm?checkout_session_id=${encodeURIComponent(setupSessionIdParam)}`,
      { method: "POST" },
      token,
    );
    if (!confirm.ok || !confirm.data.paid) {
      preFetchErrors.push(`confirm-sepa-setup: ${confirm.ok ? confirm.data.message : confirm.message}`);
      paymentResultError = t("client.sepa_mandate_pending");
    } else {
      paymentResultMessage = t("client.sepa_mandate_activated");
    }
  } else if (paymentSourceParam === "SEPA_SETUP" && paymentIdParam && paymentReturnParam === "cancel") {
    paymentResultError = t("client.sepa_mandate_cancelled");
  } else if (paymentSourceParam === "PLAN_PURCHASE" && paymentIdParam && paymentReturnParam === "success") {
    const normalizedPaymentId = paymentIdParam.startsWith("plan:") ? paymentIdParam.slice("plan:".length) : paymentIdParam;
    const confirm = await backendRequest<ClientPaymentConfirmOut>(
      `/api/v1/clients/me/payments/${normalizedPaymentId}/confirm`,
      { method: "POST" },
      token,
    );
    if (!confirm.ok) {
      preFetchErrors.push(`confirm-payment: ${confirm.message}`);
      paymentResultError = t("client.payment_pending_confirmation");
    } else if (!confirm.data.paid) {
      const reason = confirm.data.message ? ` (${confirm.data.message})` : "";
      preFetchErrors.push(`confirm-payment: paiement non confirme${reason}`);
      paymentResultError = t("client.payment_not_confirmed");
    } else {
      paymentResultMessage = t("client.payment_completed");
      if (purchaseContextParam) {
        const purchaseContext = await backendRequest<PublicFormulaPurchaseContextOut>(
          `/api/v1/public/formulas/purchase-context/${encodeURIComponent(purchaseContextParam)}`,
        );
        if (!purchaseContext.ok) {
          preFetchErrors.push(`purchase-context: ${purchaseContext.message}`);
        } else if (purchaseContext.data.session_id && purchaseContext.data.booking_user_id) {
          const bookingResult = await backendRequest<{ booking_status: string; invoice_status?: string | null }>(
            `/api/v1/clients/me/sessions/${purchaseContext.data.session_id}/checkout`,
            {
              method: "POST",
              body: JSON.stringify({ user_id: purchaseContext.data.booking_user_id }),
            },
            token,
          );
          if (!bookingResult.ok) {
            preFetchErrors.push(`session-checkout-after-plan: ${bookingResult.message}`);
            paymentResultError = bookingResult.message;
          } else if ((bookingResult.data.booking_status || "").toUpperCase() === "WAITLISTED") {
            paymentResultMessage = t("client.payment_completed_waitlist");
          } else {
            paymentResultMessage = t("client.payment_completed_booking_confirmed");
          }
        }
      }
    }
  } else if (paymentSourceParam === "PLAN_PURCHASE" && paymentIdParam && paymentReturnParam === "cancel") {
    paymentResultError = t("client.payment_cancelled");
  }

  const [
    courseTypesResult,
    locationsResult,
    sessionsResult,
    plansResult,
    catalogProductsResult,
    subscriptionsResult,
    ownBookingsResult,
    familyResult,
    contentCoursesResult,
    messagesResult,
    paymentsResult,
    invoicesResult,
    makeupSummaryResult,
  ] = await Promise.all([
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<SessionOut[]>(`/api/v1/clients/me/sessions?${sessionQuery.toString()}`, {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans", {}, token),
    backendRequest<ClientCatalogProductOut[]>("/api/v1/clients/catalog/products", {}, token),
    backendRequest<SubscriptionOut[]>("/api/v1/clients/me/subscriptions", {}, token),
    backendRequest<ClientBookingOut[]>("/api/v1/clients/me/bookings", {}, token),
    familyResultPromise,
    backendRequest<ClientContentCourseOut[]>("/api/v1/clients/me/content-courses", {}, token),
    backendRequest<ClientMessageOut[]>(`/api/v1/clients/me/messages?scope=${messageScope}`, {}, token),
    backendRequest<ClientPaymentOut[]>("/api/v1/clients/me/payments", {}, token),
    backendRequest<ClientInvoiceOut[]>("/api/v1/clients/me/invoices", {}, token),
    backendRequest<MakeupStudentSummaryOut[]>("/api/v1/clients/me/makeup-summary", {}, token),
  ]);

  const errors: string[] = [...preFetchErrors];

  const courseTypes = courseTypesResult.ok
    ? courseTypesResult.data
    : (() => {
        errors.push(`course-types: ${courseTypesResult.message}`);
        return [] as CourseTypeOut[];
      })();

  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        errors.push(`locations: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();

  const sessions = sessionsResult.ok
    ? sessionsResult.data
    : (() => {
        errors.push(`sessions: ${sessionsResult.message}`);
        return [] as SessionOut[];
      })();

  const coachOptions = Array.from(
    sessions
      .reduce((acc, session) => {
        if (!session.professor) {
          return acc;
        }
        const name = sessionProfessorName(session);
        acc.set(session.professor.id, { id: session.professor.id, name: name || session.professor.id });
        return acc;
      }, new Map<string, { id: string; name: string }>())
      .values(),
  ).sort((a, b) => a.name.localeCompare(b.name, "fr"));

  const plans = plansResult.ok
    ? plansResult.data
    : (() => {
        errors.push(`plans: ${plansResult.message}`);
        return [] as PlanOut[];
      })();

  const onlineProducts = catalogProductsResult.ok
    ? catalogProductsResult.data
    : (() => {
        errors.push(`catalog-products: ${catalogProductsResult.message}`);
        return [] as ClientCatalogProductOut[];
      })();

  const ownSubscriptions = subscriptionsResult.ok
    ? subscriptionsResult.data
    : (() => {
        errors.push(`subscriptions: ${subscriptionsResult.message}`);
        return [] as SubscriptionOut[];
      })();

  const ownBookings = ownBookingsResult.ok
    ? ownBookingsResult.data
    : (() => {
        errors.push(`bookings: ${ownBookingsResult.message}`);
        return [] as ClientBookingOut[];
      })();

  const family = familyResult.ok
    ? familyResult.data
    : (() => {
        errors.push(`family: ${familyResult.message}`);
        return null;
      })();

  const makeupSummaries = makeupSummaryResult.ok
    ? makeupSummaryResult.data
    : (() => {
        errors.push(`makeup-summary: ${makeupSummaryResult.message}`);
        return [] as MakeupStudentSummaryOut[];
      })();
  const makeupSummaryByMemberId = new Map(makeupSummaries.map((summary) => [summary.user_id, summary]));

  const contentCourses = contentCoursesResult.ok
    ? contentCoursesResult.data
    : (() => {
        errors.push(`content-courses: ${contentCoursesResult.message}`);
        return [] as ClientContentCourseOut[];
      })();

  const messages = messagesResult.ok
    ? messagesResult.data
    : (() => {
        errors.push(`messages: ${messagesResult.message}`);
        return [] as ClientMessageOut[];
      })();

  const payments = paymentsResult.ok
    ? paymentsResult.data
    : (() => {
        errors.push(`payments: ${paymentsResult.message}`);
        return [] as ClientPaymentOut[];
      })();

  const invoices = invoicesResult.ok
    ? invoicesResult.data
    : (() => {
        errors.push(`invoices: ${invoicesResult.message}`);
        return [] as ClientInvoiceOut[];
      })();

  if (paymentSourceParam === "PLAN_PURCHASE" && paymentIdParam && !paymentReturnParam) {
    const normalizedPaymentId = paymentIdParam.startsWith("plan:") ? paymentIdParam.slice("plan:".length) : paymentIdParam;
    const paymentRow = payments.find(
      (row) =>
        normalizeStatus(row.source) === "PLAN_PURCHASE" &&
        (row.id === paymentIdParam || row.id === `plan:${normalizedPaymentId}` || row.id === normalizedPaymentId),
    );
    const normalizedStatus = paymentRow ? normalizeStatus(paymentRow.status) : "";
    const canRedirectToCheckout =
      normalizedStatus === "PENDING" ||
      normalizedStatus === "OPEN" ||
      normalizedStatus === "CREATED" ||
      normalizedStatus === "PROCESSING" ||
      normalizedStatus === "WAITING_PAYMENT" ||
      normalizedStatus === "FAILED";
    if (canRedirectToCheckout) {
      const checkout = await backendRequest<ClientPaymentCheckoutOut>(
        `/api/v1/clients/me/payments/${normalizedPaymentId}/checkout`,
        { method: "POST" },
        token,
      );
      if (checkout.ok) {
        redirect(checkout.data.checkout_url);
      }
      errors.push(`checkout: ${checkout.message}`);
    }
  }

  const memberMap = new Map<string, MemberLite>();
  const addMember = (candidate: { id: string; first_name: string | null; last_name: string | null; email: string | null; client_kind: string }): void => {
    if (!candidate?.id) {
      return;
    }
    memberMap.set(candidate.id, {
      id: candidate.id,
      display_name: memberDisplayName(candidate, language),
      email: candidate.email,
      kind: candidate.client_kind,
    });
  };

  addMember({
    id: me.id,
    first_name: me.first_name,
    last_name: me.last_name,
    email: me.email,
    client_kind: me.client_kind,
  });

  if (family) {
    addMember(family.me);
    for (const link of family.links_as_adult) {
      addMember(link.child);
      addMember(link.adult);
    }
    for (const link of family.links_as_child) {
      addMember(link.child);
      addMember(link.adult);
    }
  }

  const members = [...memberMap.values()].sort((a, b) =>
    a.display_name.localeCompare(b.display_name, language === "en" ? "en" : "fr"),
  );
  const linkedMembers = members.filter((member) => member.id !== me.id);
  const hasMultipleVisibleMembers = members.length > 1;
  const validMemberIds = new Set(members.map((member) => member.id));
  const contentMemberFilter = selectedContentMemberFilter === "ALL" || validMemberIds.has(selectedContentMemberFilter)
    ? selectedContentMemberFilter
    : "ALL";
  const isFamilyBookingOwner = selectedBookingOwner === FAMILY_BOOKING_OWNER;
  const bookingOwnerId = isFamilyBookingOwner
    ? FAMILY_BOOKING_OWNER
    : validMemberIds.has(selectedBookingOwner)
      ? selectedBookingOwner
      : FAMILY_BOOKING_OWNER;
  const bookingOwnerMember = bookingOwnerId === FAMILY_BOOKING_OWNER
    ? null
    : members.find((member) => member.id === bookingOwnerId) ?? members[0] ?? null;
  const bookingOwnerLabel =
    bookingOwnerId === FAMILY_BOOKING_OWNER
      ? hasMultipleVisibleMembers
        ? t("client.whole_family")
        : members[0]?.display_name ?? t("client.account_self")
      : bookingOwnerMember?.display_name ?? "-";
  const normalizedHomeCalendarView = hasMultipleVisibleMembers ? homeCalendarView : "FAMILY";
  const filteredContentCourses = contentCourses.filter((course) =>
    contentMemberFilter === "ALL"
      ? true
      : course.member_accesses.some((access) => access.member_id === contentMemberFilter),
  );
  const selectedContentCourse =
    filteredContentCourses.find((course) => course.id === selectedContentCourseId)
    ?? filteredContentCourses[0]
    ?? null;
  const selectedContentLessons = flattenCourseLessons(selectedContentCourse);
  const selectedContentLesson =
    selectedContentLessons.find((entry) => entry.lesson.id === selectedContentLessonId)
    ?? selectedContentLessons[0]
    ?? null;

  const allBookings: FamilyBookingRow[] = family
    ? [...family.bookings]
    : ownBookings.map((row) => ({
        id: row.id,
        owner_client_id: me.id,
        owner_display_name: memberDisplayName({ first_name: me.first_name, last_name: me.last_name, email: me.email }, language),
        owner_email: me.email,
        client_plan_subscription_id: row.client_plan_subscription_id,
        status: row.status,
        booked_at: row.booked_at,
        cancelled_at: row.cancelled_at,
        cancellation_reason: row.cancellation_reason,
        price_excl_vat_snapshot: row.price_excl_vat_snapshot,
        vat_rate_snapshot: row.vat_rate_snapshot,
        vat_amount_snapshot: row.vat_amount_snapshot,
        total_incl_vat_snapshot: row.total_incl_vat_snapshot,
        currency_snapshot: row.currency_snapshot,
        session: {
          id: row.session.id,
          title: row.session.title,
          start_at_utc: row.session.start_at_utc,
          end_at_utc: row.session.end_at_utc,
          status: row.session.status,
          location_name: null,
        },
      }));

  allBookings.sort((a, b) => b.session.start_at_utc.localeCompare(a.session.start_at_utc));

  const bookingsBySessionAndMember = new Map<string, FamilyBookingRow>();
  const bookingsBySession = new Map<string, FamilyBookingRow[]>();
  for (const booking of allBookings) {
    const status = normalizeStatus(booking.status);
    if (status === "CANCELLED") {
      continue;
    }
    bookingsBySessionAndMember.set(`${booking.session.id}:${booking.owner_client_id}`, booking);
    const existing = bookingsBySession.get(booking.session.id) ?? [];
    existing.push(booking);
    bookingsBySession.set(booking.session.id, existing);
  }

  const upcomingBookings = allBookings
    .filter((booking) => {
      const sessionStart = safeDate(booking.session.start_at_utc);
      if (!sessionStart) {
        return false;
      }
      return ACTIVE_CLIENT_BOOKING_STATUSES.has(normalizeStatus(booking.status)) && sessionStart >= now;
    })
    .sort((a, b) => a.session.start_at_utc.localeCompare(b.session.start_at_utc));

  const defaultReservationMonth = upcomingBookings[0]
    ? monthKeyInTimezone(upcomingBookings[0].session.start_at_utc, timezone)
    : todayKeyInTimezone(timezone).slice(0, 7);
  const requestedReservationMonth = readParam(searchParams, "reservation_month");
  const selectedReservationMonth = isMonthKey(requestedReservationMonth)
    ? requestedReservationMonth
    : defaultReservationMonth;
  const selectedReservationMonthLabel = formatMonthKey(selectedReservationMonth, language);
  const selectedMonthBookings = upcomingBookings.filter(
    (booking) => monthKeyInTimezone(booking.session.start_at_utc, timezone) === selectedReservationMonth,
  );
  const reservationMonthQueryBase = {
    tab: "planning",
    planning_mode: "reservations",
    session_id: null,
    session_member_id: null,
    ok: null,
    error: null,
    ok_code: null,
    error_code: null,
    session_ok: null,
    session_error: null,
    session_ok_code: null,
    session_error_code: null,
  };
  const previousReservationMonthHref = withUpdatedQuery(rawParams, {
    ...reservationMonthQueryBase,
    reservation_month: shiftMonthKey(selectedReservationMonth, -1),
  });
  const nextReservationMonthHref = withUpdatedQuery(rawParams, {
    ...reservationMonthQueryBase,
    reservation_month: shiftMonthKey(selectedReservationMonth, 1),
  });
  const nextBookingMonthHref = withUpdatedQuery(rawParams, {
    ...reservationMonthQueryBase,
    reservation_month: defaultReservationMonth,
  });

  const pastBookings = allBookings
    .filter((booking) => {
      const sessionStart = safeDate(booking.session.start_at_utc);
      if (!sessionStart) {
        return true;
      }
      return sessionStart < now || !ACTIVE_CLIENT_BOOKING_STATUSES.has(normalizeStatus(booking.status));
    })
    .sort((a, b) => b.session.start_at_utc.localeCompare(a.session.start_at_utc));

  const reservationRows = (() => {
    let rows = allBookings;
    if (reservationScope === "CURRENT") {
      rows = upcomingBookings;
    } else if (reservationScope === "HISTORY") {
      rows = pastBookings;
    }

    if (selectedMemberFilter !== "ALL") {
      rows = rows.filter((row) => row.owner_client_id === selectedMemberFilter);
    }

    if (reservationStatusFilter) {
      rows = rows.filter((row) => normalizeStatus(row.status) === normalizeStatus(reservationStatusFilter));
    }

    return rows;
  })();

  const normalizedMessageQuery = normalizeLooseSearch(messageQuery);
  const messageRows = messages
    .filter((row) => selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter)
    .filter((row) => {
      if (!normalizedMessageQuery) {
        return true;
      }
      const haystack = normalizeLooseSearch(
        [
          row.owner_display_name,
          row.recipient_email,
          row.subject_preview,
          row.content_preview,
          row.session_title,
          row.channel,
          row.status,
        ]
          .filter(Boolean)
          .join(" "),
      );
      return haystack.includes(normalizedMessageQuery);
    })
    .sort((a, b) => (b.sent_at || b.scheduled_for_utc).localeCompare(a.sent_at || a.scheduled_for_utc));

  const basePaymentRows = payments
    .filter((row) => selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter)
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
  const paymentRows = basePaymentRows
    .filter((row) => financeSourceFilter === "ALL" || normalizeStatus(row.source) === normalizeStatus(financeSourceFilter))
    .filter((row) => statusMatchesFinanceFilter(row.status, financeStatusFilter))
    .filter((row) => matchesFinancePeriod(row.occurred_at, financePeriodFilter, now))
    .filter((row) => matchesFinanceAsOf(row.occurred_at, financeAsOfUtcEnd));

  const baseInvoiceRows = invoices
    .filter((row) => !isCancelledFinanceStatus(row.status))
    .filter((row) => selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter)
    .sort((a, b) => b.issued_at.localeCompare(a.issued_at));
  const invoiceRows = baseInvoiceRows
    .filter((row) => statusMatchesFinanceFilter(row.status, financeStatusFilter))
    .filter((row) => matchesFinancePeriod(row.issued_at, financePeriodFilter, now))
    .filter((row) => matchesFinanceAsOf(row.issued_at, financeAsOfUtcEnd));
  const invoiceByPaymentId = new Map<string, ClientInvoiceOut>();
  const invoiceByPaymentKey = new Map<string, ClientInvoiceOut>();
  for (const invoice of baseInvoiceRows) {
    const paymentId = invoice.id.startsWith("invoice:") ? invoice.id.slice("invoice:".length) : invoice.id;
    invoiceByPaymentId.set(paymentId, invoice);
    for (const rawKey of invoice.included_payment_keys ?? []) {
      const normalizedKey = normalizePaymentKey(rawKey);
      if (!normalizedKey) {
        continue;
      }
      invoiceByPaymentKey.set(normalizedKey, invoice);
    }
  }
  const paymentByInvoiceId = new Map<string, ClientPaymentOut>();
  const paymentByPaymentKey = new Map<string, ClientPaymentOut>();
  for (const row of basePaymentRows) {
    const paymentKey = paymentKeyFromPaymentRow(row);
    if (paymentKey) {
      paymentByPaymentKey.set(paymentKey, row);
      const linkedByKey = invoiceByPaymentKey.get(paymentKey);
      if (linkedByKey && !paymentByInvoiceId.has(linkedByKey.id)) {
        paymentByInvoiceId.set(linkedByKey.id, row);
      }
    }
    const linkedById = invoiceByPaymentId.get(row.id);
    if (linkedById && !paymentByInvoiceId.has(linkedById.id)) {
      paymentByInvoiceId.set(linkedById.id, row);
    }
  }
  const financeTotalRows = financeView === "transactions" ? paymentRows.length : invoiceRows.length;
  const financePageCount = Math.max(1, Math.ceil(financeTotalRows / financePageSize));
  const financePage = Math.min(financePageRaw, financePageCount);
  const financeOffset = (financePage - 1) * financePageSize;
  const pagedPaymentRows = paymentRows.slice(financeOffset, financeOffset + financePageSize);
  const pagedInvoiceRows = invoiceRows.slice(financeOffset, financeOffset + financePageSize);
  const selectedInvoice = selectedInvoiceId
    ? baseInvoiceRows.find((row) => row.id === selectedInvoiceId || row.id === `invoice:${selectedInvoiceId}`) ?? null
    : null;

  const subscriptions = family
    ? family.subscriptions
    : ownSubscriptions.map((sub) => ({
        ...sub,
        owner_client_id: me.id,
        owner_display_name: memberDisplayName({ first_name: me.first_name, last_name: me.last_name, email: me.email }),
        owner_email: me.email,
      }));
  const subscriptionsByOwner = new Map<string, typeof subscriptions>();
  for (const sub of subscriptions) {
    const existing = subscriptionsByOwner.get(sub.owner_client_id) ?? [];
    existing.push(sub);
    subscriptionsByOwner.set(sub.owner_client_id, existing);
  }

  const activeEntitlementsByOwner = new Map<string, Set<string>>();
  const activeSubscriptionByOwner = new Set<string>();
  for (const sub of subscriptions) {
    const isCoveredForPlanning =
      isSubscriptionActiveNow(sub, now)
      || (isReadOnlyPreview && isPendingSubscriptionCoveredInPreview(sub, now));
    if (!isCoveredForPlanning) {
      continue;
    }
    activeSubscriptionByOwner.add(sub.owner_client_id);
    const entitlementSet = activeEntitlementsByOwner.get(sub.owner_client_id) ?? new Set<string>();
    for (const courseTypeId of sub.entitlement_course_type_ids ?? []) {
      entitlementSet.add(courseTypeId);
    }
    activeEntitlementsByOwner.set(sub.owner_client_id, entitlementSet);
  }

  const selectedPurchaseOwner = validMemberIds.has(readParam(searchParams, "purchase_user_id"))
    ? readParam(searchParams, "purchase_user_id")
    : me.id;
  const selectedPurchaseStartDateRaw = readParam(searchParams, "purchase_start_date");
  const selectedPurchaseStartDate = isDateKey(selectedPurchaseStartDateRaw)
    ? selectedPurchaseStartDateRaw
    : todayKeyInTimezone(timezone);
  const selectedOwnerSubscriptions = subscriptionsByOwner.get(selectedPurchaseOwner) ?? [];
  const confirmPlan = confirmPlanId ? plans.find((plan) => plan.id === confirmPlanId) ?? null : null;
  const selectedPurchaseOwnerProfile = members.find((member) => member.id === selectedPurchaseOwner) ?? null;
  const selectedOfferCategory = parseOfferCatalogCategory(readParam(searchParams, "offer_category"));
  const offerCategoryCounts = new Map<Exclude<OfferCatalogCategory, "ALL">, number>();
  for (const plan of plans) {
    for (const category of planOfferCategories(plan)) {
      offerCategoryCounts.set(category, (offerCategoryCounts.get(category) ?? 0) + 1);
    }
  }
  for (const product of onlineProducts) {
    for (const category of productOfferCategories(product)) {
      offerCategoryCounts.set(category, (offerCategoryCounts.get(category) ?? 0) + 1);
    }
  }
  const visibleOfferCategories = OFFER_CATALOG_CATEGORIES.filter(
    (category) => (offerCategoryCounts.get(category.key) ?? 0) > 0,
  );
  const filteredPlans = selectedOfferCategory === "ALL"
    ? plans
    : plans.filter((plan) => planOfferCategories(plan).includes(selectedOfferCategory));
  const filteredOnlineProducts = selectedOfferCategory === "ALL"
    ? onlineProducts
    : onlineProducts.filter((product) => productOfferCategories(product).includes(selectedOfferCategory));
  const filteredOnlinePurchaseCount = filteredPlans.length + filteredOnlineProducts.length;
  const visibleOfferSubscriptions = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => isSubscriptionVisibleInPortal(sub, now));
  const onlinePurchaseCount = plans.length + onlineProducts.length;
  const selectedOfferSubscription = subscriptions.find((sub) => sub.id === selectedOfferDetailId) ?? null;
  const selectedOfferInvoices = selectedOfferSubscription
    ? baseInvoiceRows.filter(
        (invoice) => Boolean(selectedOfferSubscription.offer_quote_id) && invoice.source_quote_id === selectedOfferSubscription.offer_quote_id,
      )
    : [];
  const selectedOfferBookings = selectedOfferSubscription
    ? allBookings
        .filter((booking) => booking.client_plan_subscription_id === selectedOfferSubscription.id)
        .filter((booking) => normalizeStatus(booking.status) !== "CANCELLED")
        .sort((a, b) => a.session.start_at_utc.localeCompare(b.session.start_at_utc))
    : [];
  const selectedOfferActivityGroups = (() => {
    const groups = new Map<string, {
      title: string;
      locationName: string | null;
      firstAt: string;
      lastAt: string;
      startAt: string;
      endAt: string;
      count: number;
    }>();
    for (const booking of selectedOfferBookings) {
      const start = safeDate(booking.session.start_at_utc);
      const end = safeDate(booking.session.end_at_utc);
      if (!start || !end) {
        continue;
      }
      const localScheduleKey = new Intl.DateTimeFormat("en-GB", {
        timeZone: timezone,
        weekday: "long",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(start);
      const key = `${booking.session.title}|${localScheduleKey}|${booking.session.location_name || ""}`;
      const existing = groups.get(key);
      if (existing) {
        existing.lastAt = booking.session.start_at_utc;
        existing.count += 1;
      } else {
        groups.set(key, {
          title: booking.session.title,
          locationName: booking.session.location_name || null,
          firstAt: booking.session.start_at_utc,
          lastAt: booking.session.start_at_utc,
          startAt: booking.session.start_at_utc,
          endAt: booking.session.end_at_utc,
          count: 1,
        });
      }
    }
    return Array.from(groups.values());
  })();
  const paidOfferDeposits = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => normalizeStatus(sub.offer_deposit_status || "") === "PAID" && Number(sub.offer_deposit_amount_ttc || 0) > 0);
  const homeSubscriptions = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => isSubscriptionVisibleInPortal(sub, now))
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  const subscriptionAlerts = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => {
      const normalized = normalizeStatus(sub.status);
      return normalized === "PAYMENT_ALERT" || normalized === "PRE_TERMINATION";
    })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  const paymentMethodSetupSubscriptions = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => {
      if (!sub.payment_method_setup_required || normalizeStatus(sub.plan.kind) !== "SUBSCRIPTION") {
        return false;
      }
      const normalized = normalizeStatus(sub.status);
      if (normalized !== "ACTIVE" && normalized !== "PAYMENT_ALERT") {
        return false;
      }
      if (normalizeStatus(sub.billing_method_code || "") === "SEPA_DEBIT") {
        return true;
      }
      const dueAt = safeDate(sub.next_payment_at || sub.current_period_end);
      return dueAt !== null && dueAt <= now;
    })
    .sort((a, b) => (a.next_payment_at || "").localeCompare(b.next_payment_at || ""));
  const hasPreTerminationAlert = subscriptionAlerts.some((sub) => normalizeStatus(sub.status) === "PRE_TERMINATION");
  const primaryRecoveryUrl = subscriptionAlerts.find((sub) => Boolean(sub.direct_payment_recovery_url))?.direct_payment_recovery_url ?? null;
  const homeSubscriptionsPreview = homeSubscriptions.slice(0, 2);
  const upcomingBookings14 = upcomingBookings.filter((booking) => {
    const start = safeDate(booking.session.start_at_utc);
    if (!start) {
      return false;
    }
    return start.getTime() <= now.getTime() + 14 * 24 * 60 * 60 * 1000;
  });
  const homeDueInvoices = baseInvoiceRows
    .filter((invoice) => statusMatchesFinanceFilter(invoice.status, "TO_PAY"))
    .filter((invoice) => parseMoneyValue(invoice.total_incl_vat) > 0)
    .sort((a, b) => b.issued_at.localeCompare(a.issued_at));
  const homeDueInvoicePreview = homeDueInvoices.slice(0, 3);
  const homeDueTotal = homeDueInvoices.reduce((sum, invoice) => sum + parseMoneyValue(invoice.total_incl_vat), 0);
  const homeInvoicePaymentRows = homeDueInvoices
    .map((invoice) => paymentByInvoiceId.get(invoice.id))
    .filter((row): row is ClientPaymentOut => row != null && canPayNowForPayment(row));
  const homePrimaryPayableRow = homeInvoicePaymentRows[0] ?? null;
  const homePrimaryPayUrl = homeDueInvoices.find((invoice) => Boolean(invoice.payment_url))?.payment_url ?? null;
  const reminderRowsSource = messageRows.filter((row) =>
    `${row.subject_preview || ""} ${row.channel || ""}`.toLowerCase().includes("rappel"),
  );
  const newsRows = [...(reminderRowsSource.length > 0 ? reminderRowsSource : messageRows)]
    .sort((a, b) => (b.sent_at || b.scheduled_for_utc).localeCompare(a.sent_at || a.scheduled_for_utc))
    .slice(0, 2);
  const homeCalendarRows = [...upcomingBookings14].sort((a, b) => {
    if (normalizedHomeCalendarView === "BY_MEMBER") {
      const memberDiff = a.owner_display_name.localeCompare(b.owner_display_name, "fr");
      if (memberDiff !== 0) {
        return memberDiff;
      }
    }
    return a.session.start_at_utc.localeCompare(b.session.start_at_utc);
  });
  const homeCalendarGroups =
    normalizedHomeCalendarView === "BY_MEMBER"
      ? Array.from(
          homeCalendarRows.reduce((acc, row) => {
            const existing = acc.get(row.owner_display_name) ?? [];
            existing.push(row);
            acc.set(row.owner_display_name, existing);
            return acc;
          }, new Map<string, typeof homeCalendarRows>()),
        )
      : [];
  const firstHomeBooking = homeCalendarRows[0] ?? upcomingBookings[0] ?? null;
  const homePlanningHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    agenda_view: "week",
    agenda_date: firstHomeBooking
      ? dateKeyInTimezone(firstHomeBooking.session.start_at_utc, timezone)
      : todayKeyInTimezone(timezone),
    session_id: null,
    session_member_id: null,
    planning_mode: null,
    planning_slot_filter: null,
    booking_owner_id: FAMILY_BOOKING_OWNER,
  });
  const planningReservationsHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    planning_mode: null,
    planning_slot_filter: null,
    reservation_month: null,
    session_id: null,
    session_member_id: null,
  });
  const planningBookHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    planning_mode: "book",
    agenda_view: "week",
    planning_slot_filter: "AVAILABLE",
    reservation_month: null,
    session_id: null,
    session_member_id: null,
  });

  const filteredSessions = sessions.filter((session) => {
    if (selectedCoachId && session.professor?.id !== selectedCoachId) {
      return false;
    }
    if (!matchesTimeBucket(session.start_at_utc, timezone, selectedTimeBucket)) {
      return false;
    }
    return true;
  });
  const sessionDetailsById = new Map(sessions.map((session) => [session.id, session]));

  const sessionsByDay = new Map<string, SessionOut[]>();
  for (const session of filteredSessions) {
    const key = dateKeyInTimezone(session.start_at_utc, timezone);
    const existing = sessionsByDay.get(key) ?? [];
    existing.push(session);
    sessionsByDay.set(key, existing);
  }
  for (const list of sessionsByDay.values()) {
    list.sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  }

  const agendaDays = agendaRange.dayKeys.map((key) => ({
    key,
    label: agendaDayLabel(key, agendaView, language),
    sessions: sessionsByDay.get(key) ?? [],
  }));
  const planningStatusLabel = (code: PlanningStatusCode): string => {
    switch (code) {
      case "ALREADY_BOOKED":
        return t("client.planning_status_already_booked");
      case "WAITLISTED":
        return t("client.planning_status_waitlisted");
      case "PAYMENT_PENDING":
        return t("client.planning_status_payment_pending");
      case "FULL":
        return t("client.planning_status_full");
      case "PAST":
        return t("client.planning_status_past");
      case "CLOSED":
        return t("client.planning_status_closed");
      case "PAYMENT_REQUIRED":
        return t("client.planning_status_payment_required");
      case "AVAILABLE":
        return t("client.planning_status_available");
      case "INCOMPATIBLE_PLAN":
        return t("client.planning_status_incompatible");
      case "NO_PLAN":
        return t("client.planning_status_no_plan");
      case "BOOKABLE":
        return t("client.planning_status_bookable");
      case "UNAVAILABLE":
      default:
        return t("client.planning_status_unavailable");
    }
  };
  const planningStatusCodeFromLabel = (label: string | null | undefined): PlanningStatusCode | null => {
    const normalized = normalizeLooseSearch(label);
    switch (normalized) {
      case "deja reserve":
      case "already booked":
        return "ALREADY_BOOKED";
      case "liste d attente":
      case "on waitlist":
        return "WAITLISTED";
      case "paiement en attente":
      case "payment pending":
        return "PAYMENT_PENDING";
      case "complet":
      case "full":
        return "FULL";
      case "passe":
      case "past":
        return "PAST";
      case "reservation fermee":
      case "booking closed":
        return "CLOSED";
      case "paiement requis":
      case "payment required":
        return "PAYMENT_REQUIRED";
      case "disponible":
      case "available":
        return "AVAILABLE";
      case "offre incompatible":
      case "incompatible plan":
        return "INCOMPATIBLE_PLAN";
      case "aucune formule":
      case "no plan":
        return "NO_PLAN";
      case "reservation possible":
      case "booking available":
        return "BOOKABLE";
      case "non reservable":
      case "unavailable":
        return "UNAVAILABLE";
      default:
        return null;
    }
  };
  const planningStatusDisplayLabel = (label: string | null | undefined): string => {
    const code = planningStatusCodeFromLabel(label);
    if (!code) {
      return label || "";
    }
    return planningStatusLabel(code);
  };
  const isAlreadyReservedByMember = (status: string): boolean => {
    const normalized = normalizeStatus(status);
    return (
      normalized === "BOOKED"
      || normalized === "WAITLISTED"
      || normalized === "ATTENDED"
      || normalized === "NO_SHOW"
      || normalized === "EXCUSED_ABSENCE"
    );
  };
  const isPendingPaymentBooking = (status: string): boolean => normalizeStatus(status) === "PENDING_PAYMENT";
  const sessionHasDirectPayment = (session: SessionOut): boolean => Number(session.external_booking_price_ttc ?? "0") > 0;
  const memberPlanningStateForSession = (session: SessionOut, ownerId: string) => {
    const memberBooking = bookingsBySessionAndMember.get(`${session.id}:${ownerId}`);
    const bookingStatus = normalizeStatus(memberBooking?.status ?? "");
    const alreadyReserved = Boolean(memberBooking && isAlreadyReservedByMember(memberBooking.status));
    const paymentPending = Boolean(memberBooking && isPendingPaymentBooking(memberBooking.status));
    const sessionIsPastOrStarted = (safeDate(session.start_at_utc)?.getTime() ?? 0) <= now.getTime();
    const eligibleByPlan = activeEntitlementsByOwner.get(ownerId)?.has(session.course_type.id) ?? false;
    const hasAnySubscription = activeSubscriptionByOwner.has(ownerId);
    const isFull = session.booked_count >= session.capacity_max;
    const hasDirectPayment = sessionHasDirectPayment(session);
    const canCheckout =
      normalizeStatus(session.status) === "SCHEDULED"
      && session.online_booking_enabled
      && !sessionIsPastOrStarted
      && !isFull
      && (paymentPending || (!memberBooking && (eligibleByPlan || hasDirectPayment)));

    let statusCode: PlanningStatusCode = "UNAVAILABLE";
    if (alreadyReserved) {
      statusCode = bookingStatus === "WAITLISTED" ? "WAITLISTED" : "ALREADY_BOOKED";
    } else if (paymentPending) {
      statusCode = "PAYMENT_PENDING";
    } else if (isFull) {
      statusCode = "FULL";
    } else if (sessionIsPastOrStarted) {
      statusCode = "PAST";
    } else if (!session.online_booking_enabled) {
      statusCode = "CLOSED";
    } else if (canCheckout) {
      statusCode = hasDirectPayment && !eligibleByPlan ? "PAYMENT_REQUIRED" : "AVAILABLE";
    } else if (hasAnySubscription) {
      statusCode = "INCOMPATIBLE_PLAN";
    } else {
      statusCode = "NO_PLAN";
    }

    const actionLabel = paymentPending
      ? t("client.complete_payment_action")
      : hasDirectPayment && !eligibleByPlan
        ? t("client.pay_and_book_action")
        : t("client.book_action");

    return {
      memberBooking,
      bookingStatus,
      alreadyReserved,
      paymentPending,
      sessionIsPastOrStarted,
      eligibleByPlan,
      hasAnySubscription,
      isFull,
      hasDirectPayment,
      canCheckout,
      statusCode,
      statusLabel: planningStatusLabel(statusCode),
      actionLabel,
    };
  };
  const planningStateForSession = (session: SessionOut) => {
    const sessionIsPastOrStarted = (safeDate(session.start_at_utc)?.getTime() ?? 0) <= now.getTime();
    const hasDirectPayment = sessionHasDirectPayment(session);
    if (bookingOwnerId !== FAMILY_BOOKING_OWNER) {
      const ownerState = memberPlanningStateForSession(session, bookingOwnerId);
      const ownerName = bookingOwnerMember?.display_name ?? t("common.member");
      const contextLine = ownerState.alreadyReserved
        ? t("client.already_registered_slot")
        : ownerState.paymentPending
          ? t("client.payment_to_finalize_for_member")
          : ownerState.canCheckout
            ? hasDirectPayment && !ownerState.eligibleByPlan
              ? t("client.online_payment_required_confirmation")
              : t("client.available_for_booking")
            : ownerState.statusCode === "INCOMPATIBLE_PLAN"
              ? t("client.member_plan_incompatible")
              : ownerState.statusCode === "NO_PLAN"
                ? t("client.no_active_plan_for_member", { member: ownerName })
                : ownerState.statusCode === "CLOSED"
                  ? t("client.online_booking_closed")
                  : ownerState.statusCode === "PAST"
                    ? t("client.planning_status_past")
                    : ownerState.statusCode === "FULL"
                      ? t("client.planning_status_full")
                      : t("client.unavailable_for_member", { member: ownerName });
      return {
        ...ownerState,
        statusLabel: ownerState.statusLabel,
        cardStatusCode: ownerState.statusCode,
        cardStatusLabel: ownerState.statusLabel,
        contextLine,
        familyBookings: ownerState.memberBooking ? [ownerState.memberBooking] : [],
        actionableMembers:
          ownerState.canCheckout && bookingOwnerMember
            ? [{ member: bookingOwnerMember, state: ownerState }]
            : [],
      };
    }

    const familyBookings = (bookingsBySession.get(session.id) ?? []).filter(
      (booking) => normalizeStatus(booking.status) !== "CANCELLED",
    );
    const reservedFamilyBookings = familyBookings.filter((booking) => isAlreadyReservedByMember(booking.status));
    const pendingFamilyBookings = familyBookings.filter((booking) => isPendingPaymentBooking(booking.status));
    const actionableMembers = members
      .map((member) => ({ member, state: memberPlanningStateForSession(session, member.id) }))
      .filter((entry) => entry.state.canCheckout);
    const hasAdditionalFamilyOptions = reservedFamilyBookings.length > 0 && actionableMembers.length > 0;
    const reservedNames = reservedFamilyBookings.map((booking) => booking.owner_display_name).join(", ");
    const pendingNames = pendingFamilyBookings.map((booking) => booking.owner_display_name).join(", ");
    const hasAnySubscription = members.some((member) => activeSubscriptionByOwner.has(member.id));
    const requiresMemberChoice = actionableMembers.length > 1 || hasAdditionalFamilyOptions;

    let statusCode: PlanningStatusCode = "UNAVAILABLE";
    let contextLine = t("client.no_family_action_available");
    if (hasAdditionalFamilyOptions) {
      statusCode = "BOOKABLE";
      contextLine =
        reservedFamilyBookings.length > 1
          ? t("client.family_bookings_and_can_book_other", { count: reservedFamilyBookings.length })
          : t("client.booked_for_and_can_book_other", { members: reservedNames });
    } else if (reservedFamilyBookings.length > 0) {
      statusCode = "ALREADY_BOOKED";
      contextLine = t("client.booked_for", { members: reservedNames });
    } else if (pendingFamilyBookings.length > 0) {
      statusCode = "PAYMENT_PENDING";
      contextLine = t("client.payment_to_finalize_for_names", { members: pendingNames });
    } else if (session.booked_count >= session.capacity_max) {
      statusCode = "FULL";
      contextLine = t("client.planning_status_full");
    } else if (sessionIsPastOrStarted) {
      statusCode = "PAST";
      contextLine = t("client.planning_status_past");
    } else if (!session.online_booking_enabled) {
      statusCode = "CLOSED";
      contextLine = t("client.online_booking_closed");
    } else if (actionableMembers.length > 1) {
      statusCode = "BOOKABLE";
      contextLine = t("client.choose_member_next_step");
    } else if (actionableMembers.length === 1) {
      statusCode = actionableMembers[0].state.statusCode;
      contextLine =
        actionableMembers[0].state.hasDirectPayment && !actionableMembers[0].state.eligibleByPlan
          ? t("client.payment_required_for_member", { member: actionableMembers[0].member.display_name })
          : t("client.available_for_member", { member: actionableMembers[0].member.display_name });
    } else if (hasAnySubscription) {
      statusCode = "INCOMPATIBLE_PLAN";
      contextLine = t("client.no_compatible_family_plan");
    } else if (hasDirectPayment) {
      statusCode = "BOOKABLE";
      contextLine = t("client.choose_member_for_reservation");
    } else {
      statusCode = "NO_PLAN";
      contextLine = t("client.no_active_plan_in_family");
    }

    return {
      memberBooking: null,
      bookingStatus: "",
      alreadyReserved: reservedFamilyBookings.length > 0,
      paymentPending: pendingFamilyBookings.length > 0,
      sessionIsPastOrStarted,
      eligibleByPlan: false,
      hasAnySubscription,
      isFull: session.booked_count >= session.capacity_max,
      hasDirectPayment,
      canCheckout: actionableMembers.length > 0,
      statusCode,
      statusLabel: planningStatusLabel(statusCode),
      cardStatusCode: statusCode,
      cardStatusLabel: planningStatusLabel(statusCode),
      contextLine,
      familyBookings,
      actionableMembers,
      actionLabel:
        requiresMemberChoice
          ? t("client.book_action")
          : actionableMembers.length === 1
          ? actionableMembers[0].state.actionLabel
          : t("client.book_action"),
    };
  };
  const selectedSession = filteredSessions.find((session) => session.id === selectedSessionId) ?? null;
  const selectedSessionPlanningState = selectedSession ? planningStateForSession(selectedSession) : null;
  const shouldDeferReservationOptionsFetch = false;
  const reservationOptionsQuery = new URLSearchParams();
  const selectedSessionReservationOptionsResult =
    tab === "planning" && selectedSessionId && !shouldDeferReservationOptionsFetch
      ? await backendRequest<ClientSessionReservationOptionsOut>(
          `/api/v1/clients/me/sessions/${encodeURIComponent(selectedSessionId)}/reservation-options${
            reservationOptionsQuery.size ? `?${reservationOptionsQuery.toString()}` : ""
          }`,
          {},
          token,
        )
      : null;
  const selectedSessionReservationOptions =
    selectedSessionReservationOptionsResult?.ok ? selectedSessionReservationOptionsResult.data : null;
  const selectedSessionPurchaseCatalogResult =
    tab === "planning" && selectedSessionId
      ? await backendRequest<ClientSessionPurchaseCatalogOut>(
          `/api/v1/clients/me/sessions/${encodeURIComponent(selectedSessionId)}/purchase-catalog`,
          {},
          token,
        )
      : null;
  const selectedSessionPurchaseCatalog =
    selectedSessionPurchaseCatalogResult?.ok ? selectedSessionPurchaseCatalogResult.data : null;
  const shouldUseFallbackReservationOptions =
    Boolean(selectedSessionPlanningState) &&
    (
      shouldDeferReservationOptionsFetch ||
      (selectedSessionReservationOptionsResult != null && !selectedSessionReservationOptionsResult.ok)
    );
  if (
    selectedSessionReservationOptionsResult &&
    !selectedSessionReservationOptionsResult.ok &&
    !shouldUseFallbackReservationOptions
  ) {
    errors.push(`reservation-options: ${selectedSessionReservationOptionsResult.message}`);
  }
  const fallbackReservationOptionsMembers: ClientSessionReservationMemberOptionOut[] =
    shouldUseFallbackReservationOptions && selectedSessionPlanningState
      ? selectedSessionPlanningState.actionableMembers.map(({ member, state }) => ({
          member_id: member.id,
          member_display_name: member.display_name,
          member_kind: member.kind === "CHILD" ? "CHILD" : "ADULT",
          booking_id: state.memberBooking?.id ?? null,
          booking_status: state.bookingStatus || null,
          action_code: state.paymentPending
            ? "FINALIZE_PAYMENT"
            : state.hasDirectPayment && !state.eligibleByPlan
              ? "PAY_UNIT"
              : "BOOK_WITH_CREDIT",
          action_label: state.paymentPending ? t("client.complete_payment_action") : state.actionLabel,
          status_label: state.statusLabel,
          reason: state.paymentPending
            ? "Une reservation provisoire existe deja pour ce membre. Finalisez le paiement pour confirmer la place."
            : state.hasDirectPayment && !state.eligibleByPlan
              ? "Cette reservation peut etre payee a l unite."
              : "Cette reservation sera confirmee sans paiement supplementaire.",
          has_credit_coverage: state.eligibleByPlan,
          coverage_source: state.eligibleByPlan ? "PLAN" : null,
          direct_payment_amount_ttc:
            state.hasDirectPayment && selectedSession?.external_booking_price_ttc != null
              ? selectedSession.external_booking_price_ttc
              : null,
          direct_payment_currency:
            state.hasDirectPayment
              ? (selectedSession?.external_booking_currency || "EUR").toUpperCase()
              : null,
          formula_options: [],
        }))
      : [];
  const reservationOptionsMembers = selectedSessionReservationOptions?.members ?? fallbackReservationOptionsMembers;
  const reservationMemberOptionPriority = (option: ClientSessionReservationMemberOptionOut): number => {
    switch (option.action_code) {
      case "BOOK_WITH_CREDIT":
        return 0;
      case "FINALIZE_PAYMENT":
        return 1;
      case "BUY_FORMULA_OR_PAY_UNIT":
        return 2;
      case "BUY_FORMULA":
        return 3;
      case "PAY_UNIT":
        return 4;
      case "JOIN_WAITLIST":
        return 5;
      case "ALREADY_BOOKED":
        return 6;
      case "ALREADY_WAITLISTED":
        return 7;
      default:
        return 99;
    }
  };
  const suggestedReservationMemberOption =
    reservationOptionsMembers.length > 1
      ? (() => {
          const rankedOptions = [...reservationOptionsMembers].sort((left, right) => {
            const priorityDiff = reservationMemberOptionPriority(left) - reservationMemberOptionPriority(right);
            if (priorityDiff !== 0) {
              return priorityDiff;
            }
            return left.member_display_name.localeCompare(right.member_display_name, "fr");
          });
          const bestOption = rankedOptions[0] ?? null;
          if (bestOption == null) {
            return null;
          }
          const equallyGoodCount = rankedOptions.filter(
            (option) => reservationMemberOptionPriority(option) === reservationMemberOptionPriority(bestOption),
          ).length;
          return equallyGoodCount === 1 ? bestOption : null;
        })()
      : reservationOptionsMembers[0] ?? null;
  const selectedReservationMemberId =
    selectedSessionMember && validMemberIds.has(selectedSessionMember)
      ? selectedSessionMember
      : bookingOwnerId !== FAMILY_BOOKING_OWNER
      ? bookingOwnerId
      : reservationOptionsMembers.length === 1
        ? reservationOptionsMembers[0]?.member_id ?? ""
        : suggestedReservationMemberOption?.member_id ?? "";
  const selectedReservationMemberOption =
    reservationOptionsMembers.find((option) => option.member_id === selectedReservationMemberId) ?? null;
  const selectedReservationMakeupSummary = selectedReservationMemberOption
    ? makeupSummaryByMemberId.get(selectedReservationMemberOption.member_id)
    : null;
  const selectedReservationCanCancel = selectedReservationMemberOption
    ? normalizeStatus(selectedReservationMemberOption.booking_status || "") === "WAITLISTED"
      || (
        normalizeStatus(selectedReservationMemberOption.booking_status || "") === "BOOKED"
        && (
          !selectedReservationMakeupSummary?.has_active_restricted_forfait
          || selectedReservationMakeupSummary.credits_remaining > 0
        )
      )
    : false;
  const selectedSessionReturnTo = selectedSession
    ? withUpdatedQuery(rawParams, {
        tab: "planning",
        session_id: selectedSession.id,
        session_member_id: null,
        session_ok: null,
        session_error: null,
        session_ok_code: null,
        session_error_code: null,
      })
    : withUpdatedQuery(rawParams, {
        tab: "planning",
        session_ok: null,
        session_error: null,
        session_ok_code: null,
        session_error_code: null,
      });
  const selectedSessionCloseHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    session_id: null,
    session_member_id: null,
    session_ok: null,
    session_error: null,
    session_ok_code: null,
    session_error_code: null,
  });
  const selectedSessionModalStatusCode =
    planningStatusCodeFromLabel(selectedReservationMemberOption?.status_label) ?? selectedSessionPlanningState?.cardStatusCode ?? null;
  const selectedSessionModalStatusLabel = selectedReservationMemberOption?.status_label
    ? planningStatusDisplayLabel(selectedReservationMemberOption.status_label)
    : selectedSessionPlanningState?.cardStatusLabel || "";
  const compatiblePackCreditSummaryForMember = (memberId: string | null | undefined) => {
    if (!memberId || !selectedSession) {
      return null;
    }
    let remaining = 0;
    let initial = 0;
    let packCount = 0;
    for (const sub of subscriptionsByOwner.get(memberId) ?? []) {
      if (!isSubscriptionActiveNow(sub, now) || sub.plan.kind !== "PACK") {
        continue;
      }
      if (!(sub.entitlement_course_type_ids ?? []).includes(selectedSession.course_type.id)) {
        continue;
      }
      const subRemaining = sub.credits_remaining ?? 0;
      if (subRemaining <= 0) {
        continue;
      }
      packCount += 1;
      remaining += subRemaining;
      initial += sub.credits_initial ?? subRemaining;
    }
    if (packCount === 0 || remaining <= 0) {
      return null;
    }
    return { remaining, initial, packCount };
  };
  const selectedSessionPackCreditSummary = compatiblePackCreditSummaryForMember(selectedReservationMemberOption?.member_id);
  const formatPackCreditLabel = (
    summary: { remaining: number; initial: number; packCount: number } | null,
    includeInitial: boolean,
  ): string | null => {
    if (!summary) {
      return null;
    }
    if (includeInitial && summary.packCount === 1 && summary.initial > 0) {
      return t("client.remaining_pack_credits_with_total", {
        remaining: summary.remaining,
        initial: summary.initial,
      });
    }
    return t("client.remaining_pack_credits", { remaining: summary.remaining });
  };
  const selectedSessionPackCreditLabel = selectedSessionPackCreditSummary
    ? formatPackCreditLabel(selectedSessionPackCreditSummary, true)
    : null;
  const selectedSessionCoverageLabel =
    selectedReservationMemberOption?.coverage_source === "MANUAL_CREDIT"
      ? t("client.manual_credit_available")
      : selectedReservationMemberOption?.coverage_source === "PACK"
        ? selectedSessionPackCreditLabel || t("client.compatible_pack_available")
        : selectedReservationMemberOption?.coverage_source === "FORFAIT"
          ? t("client.compatible_fixed_plan_available")
          : selectedReservationMemberOption?.coverage_source === "SUBSCRIPTION"
            ? t("client.compatible_subscription_available")
            : null;
  const selectedSessionActionCode = selectedReservationMemberOption?.action_code ?? "";
  const selectedSessionRequiresMemberChoice = reservationOptionsMembers.length > 1 && !selectedReservationMemberOption;
  const selectedSessionCatalogFormulaOptions = selectedSessionPurchaseCatalog?.formula_options ?? [];
  const selectedSessionFormulaOptions =
    (selectedReservationMemberOption?.formula_options?.length ?? 0) > 0
      ? selectedReservationMemberOption?.formula_options ?? []
      : selectedSessionCatalogFormulaOptions;
  const selectedSessionDirectPaymentAmount =
    selectedReservationMemberOption?.direct_payment_amount_ttc ?? selectedSessionPurchaseCatalog?.direct_payment_amount_ttc ?? null;
  const selectedSessionDirectPaymentCurrency =
    selectedReservationMemberOption?.direct_payment_currency ?? selectedSessionPurchaseCatalog?.direct_payment_currency ?? null;
  const selectedSessionEffectiveActionCode =
    selectedReservationMemberOption == null
      ? selectedSessionActionCode
      : selectedSessionActionCode === "PAY_UNIT" && selectedSessionFormulaOptions.length > 0
        ? selectedSessionDirectPaymentAmount
          ? "BUY_FORMULA_OR_PAY_UNIT"
          : "BUY_FORMULA"
        : selectedSessionActionCode;
  const otherMemberOptions = reservationOptionsMembers.filter((option) => option.member_id !== selectedReservationMemberId);
  const alternativeReservationOptions = otherMemberOptions.filter((option) =>
    ["BOOK_WITH_CREDIT", "PAY_UNIT", "BUY_FORMULA", "BUY_FORMULA_OR_PAY_UNIT", "JOIN_WAITLIST"].includes(option.action_code),
  );
  const reservationOptionActionLabel = (
    option: ClientSessionReservationMemberOptionOut,
    actionCode: string = option.action_code,
  ): string => {
    switch (actionCode) {
      case "FINALIZE_PAYMENT":
        return t("client.finalize_payment_for", { member: option.member_display_name });
      case "BOOK_WITH_CREDIT":
        return option.coverage_source === "PACK" ? t("client.use_your_credits") : t("client.book_without_paying");
      case "BUY_FORMULA_OR_PAY_UNIT":
        return t("client.choose_your_option");
      case "BUY_FORMULA":
        return t("client.buy_a_plan");
      case "PAY_UNIT":
        return t("client.pay_unit");
      case "JOIN_WAITLIST":
        return t("client.waitlist_available");
      default:
        return option.action_label || t("client.view_this_slot");
    }
  };
  const reservationOptionReasonLabel = (option: ClientSessionReservationMemberOptionOut): string | null => {
    if (option.action_code === "FINALIZE_PAYMENT") {
      return t("client.finalize_payment_for", { member: option.member_display_name });
    }
    if (option.action_code === "BOOK_WITH_CREDIT") {
      if (option.coverage_source === "PACK") {
        const packSummary = compatiblePackCreditSummaryForMember(option.member_id);
        const credits = formatPackCreditLabel(packSummary, true);
        if (credits) {
          return t("client.pack_covers_slot", { member: option.member_display_name, credits });
        }
      }
      if (option.coverage_source === "SUBSCRIPTION") {
        return t("client.subscription_covers_slot", { member: option.member_display_name });
      }
      return t("client.booking_confirmed_without_payment", { member: option.member_display_name });
    }
    if (option.action_code === "BUY_FORMULA_OR_PAY_UNIT") {
      return t("client.no_credit_choose_plan_or_unit", { member: option.member_display_name });
    }
    if (option.action_code === "BUY_FORMULA") {
      return t("client.no_credit_choose_plan", { member: option.member_display_name });
    }
    if (option.action_code === "JOIN_WAITLIST") {
      return t("client.waitlist_available");
    }
    if (option.action_code === "ALREADY_WAITLISTED") {
      return t("client.waitlist_confirmed_for", { member: option.member_display_name });
    }
    if (option.action_code === "ALREADY_BOOKED") {
      return t("client.booking_confirmed_for", { member: option.member_display_name });
    }
    return option.reason || option.action_label || null;
  };
  const reservationOptionSupportLabel = (option: ClientSessionReservationMemberOptionOut): string | null => {
    if (option.action_code === "FINALIZE_PAYMENT" && option.direct_payment_amount_ttc) {
      return t("client.pending_payment_support", {
        amount: toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency, language),
      });
    }
    if (option.action_code === "BUY_FORMULA_OR_PAY_UNIT") {
      const formulaCount = option.formula_options.length;
      const parts = [];
      if (formulaCount > 0) {
        parts.push(t("client.compatible_plan_count", { count: formulaCount }));
      }
      if (option.direct_payment_amount_ttc) {
        parts.push(
          t("client.unit_payment_support", {
            amount: toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency, language),
          }),
        );
      }
      return parts.join(" · ") || null;
    }
    if (option.action_code === "BUY_FORMULA" && option.formula_options.length > 0) {
      return t("client.compatible_plan_count", { count: option.formula_options.length });
    }
    if (option.action_code === "PAY_UNIT" && option.direct_payment_amount_ttc) {
      return t("client.unit_payment_support", {
        amount: toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency, language),
      });
    }
    if (option.action_code === "BOOK_WITH_CREDIT") {
      if (option.coverage_source === "PACK") {
        const packSummary = compatiblePackCreditSummaryForMember(option.member_id);
        if (packSummary) {
          return formatPackCreditLabel(packSummary, false);
        }
      }
      if (option.coverage_source === "SUBSCRIPTION") {
        return t("client.active_subscription");
      }
      if (option.coverage_source === "FORFAIT") {
        return t("client.active_fixed_plan");
      }
      if (option.coverage_source === "MANUAL_CREDIT") {
        return t("client.manual_credit_available");
      }
      return t("client.booking_covered_no_payment");
    }
    if (option.action_code === "JOIN_WAITLIST") {
      return t("client.waitlist_available");
    }
    return null;
  };
  const selectedSessionStateTitle =
    selectedSessionRequiresMemberChoice
      ? t("client.member_concerned")
      : selectedSessionEffectiveActionCode === "FINALIZE_PAYMENT" && selectedReservationMemberOption
        ? t("client.finalize_payment_for", { member: selectedReservationMemberOption.member_display_name })
        : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" && selectedReservationMemberOption
          ? selectedReservationMemberOption.coverage_source === "PACK"
            ? t("client.use_your_credits")
            : t("client.book_without_paying")
        : selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
          ? t("client.choose_your_option")
          : selectedSessionEffectiveActionCode === "BUY_FORMULA"
            ? t("client.buy_a_plan")
            : selectedReservationMemberOption
              ? reservationOptionActionLabel(selectedReservationMemberOption, selectedSessionEffectiveActionCode)
              : t("client.view_this_slot");
  const selectedSessionStateDescription =
    selectedSessionRequiresMemberChoice
      ? t("client.best_option_auto")
      : selectedSessionEffectiveActionCode === "FINALIZE_PAYMENT" && selectedReservationMemberOption
        ? alternativeReservationOptions.length > 0
          ? t("client.pending_payment_other_member", { member: selectedReservationMemberOption.member_display_name })
          : reservationOptionReasonLabel(selectedReservationMemberOption) || selectedSessionPlanningState?.contextLine || ""
        : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" && selectedReservationMemberOption
          ? selectedReservationMemberOption.coverage_source === "PACK" && selectedSessionPackCreditLabel
            ? t("client.pack_covers_slot", {
                member: selectedReservationMemberOption.member_display_name,
                credits: selectedSessionPackCreditLabel,
              })
            : selectedReservationMemberOption.coverage_source === "SUBSCRIPTION"
              ? t("client.subscription_covers_slot", { member: selectedReservationMemberOption.member_display_name })
              : t("client.booking_confirmed_without_payment", { member: selectedReservationMemberOption.member_display_name })
        : selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT" && selectedReservationMemberOption
          ? t("client.no_credit_choose_plan_or_unit", { member: selectedReservationMemberOption.member_display_name })
          : selectedSessionEffectiveActionCode === "BUY_FORMULA" && selectedReservationMemberOption
            ? t("client.no_credit_choose_plan", { member: selectedReservationMemberOption.member_display_name })
        : selectedReservationMemberOption ? reservationOptionReasonLabel(selectedReservationMemberOption) : selectedSessionPlanningState?.contextLine || "";
  const selectedSessionPurchaseChoiceCount =
    (selectedSessionDirectPaymentAmount ? 1 : 0) + selectedSessionFormulaOptions.length;
  const selectedSessionPrimaryActionLabel =
    !selectedReservationMemberOption
      ? null
      : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT"
        ? selectedReservationMemberOption.coverage_source === "PACK"
          ? t("client.use_my_credits")
          : selectedReservationMemberOption.coverage_source === "SUBSCRIPTION"
            ? t("client.use_my_subscription")
            : selectedReservationMemberOption.coverage_source === "FORFAIT"
              ? t("client.use_my_fixed_plan")
              : t("client.confirm_without_paying")
        : reservationOptionActionLabel(selectedReservationMemberOption, selectedSessionEffectiveActionCode);
  const selectedSessionBookingStatus = (selectedReservationMemberOption?.booking_status || "").toUpperCase();
  const selectedSessionHasBooking =
    Boolean(selectedReservationMemberOption?.booking_id) &&
    ["BOOKED", "WAITLISTED"].includes(selectedSessionBookingStatus);
  const selectedSessionBookedStateTitle =
    selectedSessionBookingStatus === "WAITLISTED" ? t("client.waitlist_confirmed") : t("client.booking_confirmed");
  const selectedSessionBookedStateDescription =
    selectedReservationMemberOption == null
      ? ""
      : selectedSessionBookingStatus === "WAITLISTED"
        ? t("client.waitlist_confirmed_for", { member: selectedReservationMemberOption.member_display_name })
        : t("client.booking_confirmed_for", { member: selectedReservationMemberOption.member_display_name });
  const selectedSessionCheckoutReturnTo =
    selectedSession && selectedReservationMemberOption
      ? buildClientSessionCheckoutHref(selectedSession.id, selectedSessionReturnTo, selectedReservationMemberOption.member_id)
      : "/buy/session/checkout";
  const agendaSessionCount = agendaDays.reduce((sum, day) => sum + day.sessions.length, 0);
  const advancedFiltersOpen =
    Boolean(selectedCourseType) ||
    Boolean(selectedCoachId) ||
    selectedTimeBucket !== "ALL" ||
    rawPlanningSlotFilter !== "ALL" ||
    timezone !== (me.timezone || DEFAULT_TIMEZONE) ||
    bookingOwnerId !== FAMILY_BOOKING_OWNER;

  const allBookingStatuses = Array.from(new Set(allBookings.map((row) => normalizeStatus(row.status)))).sort();
  const allPaymentSources = Array.from(new Set(payments.map((row) => normalizeStatus(row.source)))).sort();
  const visibleFinanceStatusOptions: Array<{ value: FinanceStatusFilter; label: string }> = [
    { value: "ALL", label: t("client.all_statuses") },
    { value: "TO_PAY", label: t("client.finance_status_to_pay") },
    { value: "PAID", label: t("client.finance_status_paid") },
    { value: "CANCELLED", label: t("client.finance_status_cancelled") },
    { value: "FAILED", label: t("client.finance_status_failed") },
  ];

  const positivePackSubscriptions = subscriptions.filter(
    (sub) => isSubscriptionActiveNow(sub, now) && sub.plan.kind === "PACK" && (sub.credits_remaining ?? 0) > 0,
  );

  const paidTotal = paymentRows
    .filter((row) => normalizeStatus(row.status) === "PAID")
    .reduce((sum, row) => sum + Number(row.total_incl_vat || "0"), 0);
  const pendingTransactionsTotal = paymentRows
    .filter((row) => FINANCE_PENDING_STATUSES.has(normalizeStatus(row.status)))
    .reduce((sum, row) => sum + Number(row.total_incl_vat || "0"), 0);
  const financePendingInvoices = invoiceRows
    .filter((invoice) => statusMatchesFinanceFilter(invoice.status, "TO_PAY"))
    .filter((invoice) => parseMoneyValue(invoice.total_incl_vat) > 0);
  const financeDueTotal = financePendingInvoices.reduce((sum, invoice) => sum + parseMoneyValue(invoice.total_incl_vat), 0);
  const financeDuePaymentRows = financePendingInvoices
    .map((invoice) => paymentByInvoiceId.get(invoice.id))
    .filter((row): row is ClientPaymentOut => row != null && canPayNowForPayment(row));
  const primaryDuePayableRow = financeDuePaymentRows[0] ?? null;
  const primaryDuePaymentUrl = financePendingInvoices.find((invoice) => Boolean(invoice.payment_url))?.payment_url ?? null;
  const timezoneOptions = TIMEZONE_OPTIONS.some((item) => item.value === timezone)
    ? TIMEZONE_OPTIONS
    : [{ value: timezone, label: `${timezone} (personnalise)` }, ...TIMEZONE_OPTIONS];

  const tabLabels: Record<DashboardTab, string> = {
    home: uiText(language, "client.home"),
    planning: uiText(language, "client.planning"),
    courses: uiText(language, "client.courses"),
    reservations: uiText(language, "client.bookings"),
    offers: uiText(language, "client.offers"),
    finance: uiText(language, "client.finance"),
    messages: uiText(language, "client.messages"),
    account: uiText(language, "client.account"),
  };
  const tabLinks: Array<{ id: DashboardTab; label: string; icon: string }> = [
    { id: "home", label: tabLabels.home, icon: "🏠" },
    { id: "planning", label: tabLabels.planning, icon: "📅" },
    { id: "courses", label: tabLabels.courses, icon: "📚" },
    { id: "offers", label: tabLabels.offers, icon: "🧾" },
    { id: "finance", label: tabLabels.finance, icon: "💳" },
    { id: "messages", label: tabLabels.messages, icon: "✉️" },
    { id: "account", label: tabLabels.account, icon: "👤" },
  ];
  const mobileTabLinks = [
    { id: "home", label: tabLabels.home, icon: "🏠", href: withUpdatedQuery(rawParams, { tab: "home" }) },
    { id: "planning", label: tabLabels.planning, icon: "📅", href: withUpdatedQuery(rawParams, { tab: "planning" }) },
    { id: "offers", label: tabLabels.offers, icon: "🧾", href: withUpdatedQuery(rawParams, { tab: "offers" }) },
    { id: "finance", label: tabLabels.finance, icon: "💳", href: withUpdatedQuery(rawParams, { tab: "finance" }) },
    { id: "account", label: tabLabels.account, icon: "👤", href: withUpdatedQuery(rawParams, { tab: "account" }) },
  ];
  const activeMobileTabId = mobileTabLinks.some((item) => item.id === tab) ? tab : "home";

  const displayName = memberDisplayName({ first_name: me.first_name, last_name: me.last_name, email: me.email }, language);
  const impersonationDisplayName = impersonationNameHint || displayName;
  const okMessage = resolveAuthOkMessage(readParam(searchParams, "ok"), readParam(searchParams, "ok_code"), language);
  const errorMessage = readParam(searchParams, "error");
  const errorCode = readParam(searchParams, "error_code");
  const errorStatus = readParam(searchParams, "error_status");
  const sessionOkMessage = selectedSession
    ? resolveAuthOkMessage(readParam(searchParams, "session_ok"), readParam(searchParams, "session_ok_code"), language)
    : "";
  const sessionErrorMessage = selectedSession
    ? resolveAuthErrorMessage(readParam(searchParams, "session_error"), readParam(searchParams, "session_error_code"), language)
    : "";
  const globalOkMessage = sessionOkMessage ? "" : (okMessage || paymentResultMessage);
  const portalErrorMessage = resolvePortalErrorMessage(errorMessage, errorCode, errorStatus, language, t);
  const globalErrorMessage = sessionErrorMessage ? "" : (portalErrorMessage || paymentResultError);
  const hasPhoneNumber = Boolean(me.mobile_phone_1 || me.mobile_phone_2 || me.home_phone || me.phone);
  const selectedMessageId = readParam(searchParams, "message_id");
  const selectedMessage = selectedMessageId ? messageRows.find((row) => row.id === selectedMessageId) ?? null : null;
  const communicationSummary = t("client.communication_summary", {
    lessonEmail: t(me.lesson_reminder_email_opt_in ? "common.on" : "common.off"),
    lessonSms: t(me.lesson_reminder_sms_opt_in ? "common.on" : "common.off"),
    communicationEmail: t(me.email_opt_in ? "common.on" : "common.off"),
    communicationSms: t(me.sms_opt_in ? "common.on" : "common.off"),
  });
  const planningStatusClass = (statusCode: PlanningStatusCode | null | undefined): string => {
    switch (statusCode) {
      case "ALREADY_BOOKED":
      case "WAITLISTED":
        return "status-booked";
      case "BOOKABLE":
      case "AVAILABLE":
      case "PAYMENT_REQUIRED":
        return "status-scheduled";
      case "PAYMENT_PENDING":
        return "status-waitlist";
      case "FULL":
        return "status-cancelled";
      case "PAST":
        return "status-completed";
      case "CLOSED":
      case "INCOMPATIBLE_PLAN":
      case "NO_PLAN":
      case "UNAVAILABLE":
      default:
        return "status-draft";
    }
  };
  const shouldRenderPlanningStateBadge = (statusCode: PlanningStatusCode | null | undefined): boolean => {
    return new Set<PlanningStatusCode>([
      "PAYMENT_PENDING",
      "FULL",
      "PAST",
      "CLOSED",
      "INCOMPATIBLE_PLAN",
      "NO_PLAN",
      "UNAVAILABLE",
      "WAITLISTED",
    ]).has(statusCode ?? "UNAVAILABLE");
  };

  return (
    <main className="client-portal-shell">
      <aside className="client-portal-sidebar">
        <div className="client-brand">
          <PortalBrandLockup
            title={uiText(language, "common.app_name")}
            subtitle={uiText(language, "client.portal_subtitle")}
            eyebrow="Mi-Young Lee"
            tone="dark"
            compact
          />
        </div>

        <article className="client-user-card">
          <strong>{displayName}</strong>
          <small>{me.email}</small>
        </article>

        {isImpersonating ? (
          <form action={endPortalImpersonationAction} className="client-admin-exit-form" data-read-only-preview-allow="true">
            <input type="hidden" name="return_to" value={impersonationReturnTo} />
            <button className="ghost client-admin-exit-btn" type="submit">
              {uiText(language, "common.back_office")}
            </button>
          </form>
        ) : null}

        <nav className="client-nav" aria-label={uiText(language, "portal.client")}>
          {tabLinks.map((item) => {
            const href = withUpdatedQuery(rawParams, { tab: item.id });
            return (
              <Link key={item.id} className={`client-nav-link ${tab === item.id ? "active" : ""}`} href={href}>
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
          <Link className="client-nav-link" href="/events">
            <span aria-hidden="true">🎟️</span>
            <span>{language === "en" ? "Events" : "Événements"}</span>
          </Link>
        </nav>

        <form action={logoutAction} className="client-logout" data-read-only-preview-allow="true">
          <button className="ghost" type="submit">
            ⎋
          </button>
          <span>{uiText(language, "common.logout")}</span>
        </form>
      </aside>

      <section className="client-portal-main">
        <MobileHeader
          title={tabLabels[tab] ?? uiText(language, "portal.client")}
          subtitle={`${displayName} · ${timezone}`}
          menuLabel={uiText(language, "portal.client_menu")}
          menu={
            <div className="client-mobile-menu-items">
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "home" })}>
                {tabLabels.home}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "planning" })}>
                {tabLabels.planning}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "courses" })}>
                {tabLabels.courses}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                {tabLabels.offers}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "finance" })}>
                {tabLabels.finance}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>
                {tabLabels.messages}
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "account" })}>
                {tabLabels.account}
              </a>
              <a className="client-mobile-menu-link" href="/events">
                {language === "en" ? "Events" : "Événements"}
              </a>
              {isImpersonating ? (
                <form action={endPortalImpersonationAction} data-read-only-preview-allow="true">
                  <input type="hidden" name="return_to" value={impersonationReturnTo} />
                  <button className="ghost client-mobile-menu-btn" type="submit">
                    {uiText(language, "common.back_office")}
                  </button>
                </form>
              ) : null}
              <form action={logoutAction} data-read-only-preview-allow="true">
                <button className="ghost client-mobile-menu-btn" type="submit">
                  {uiText(language, "common.logout")}
                </button>
              </form>
            </div>
          }
        />

        <header className="client-topbar">
          <div>
            <h1>{tabLabels[tab] ?? uiText(language, "client.default_title")}</h1>
            <p className="muted">
              {uiText(language, "client.active_bookings")}: {upcomingBookings.length} | {uiText(
                language,
                hasMultipleVisibleMembers ? "client.visible_members_plural" : "client.visible_members_singular",
              )}: {members.length}
            </p>
          </div>
          <div className="row">
            <span className="badge">{uiText(language, "client.timezone")}: {timezone}</span>
            <span className="badge">{uiText(language, "client.currency")}: {me.preferred_currency}</span>
          </div>
        </header>

        <section className="client-content">
          <PortalReadOnlyPreviewGuard enabled={isReadOnlyPreview} language={language} />
          {isImpersonating ? (
            <PortalImpersonationBanner
              displayName={impersonationDisplayName}
              returnTo={impersonationReturnTo}
              language={language}
              readOnly={isReadOnlyPreview}
            />
          ) : null}
          {globalOkMessage ? <Toast message={globalOkMessage} tone="ok" /> : null}
          {globalErrorMessage ? <section className="flash-err">{globalErrorMessage}</section> : null}
          {errors.length > 0 ? <section className="flash-err">{t("client.backend_error")}: {errors.join(" | ")}</section> : null}
          {subscriptionAlerts.length > 0 ? (
            <section className={hasPreTerminationAlert ? "flash-err" : "flash-warn"}>
              {hasPreTerminationAlert
                ? t("client.subscription_regularization_blocked")
                : t("client.subscription_regularization_failed")}
              {primaryRecoveryUrl ? (
                <>
                  {" "}
                  <a
                    className="mode-link"
                    href={primaryRecoveryUrl}
                    target="_blank"
                    rel="noreferrer"
                    data-read-only-preview-block="true"
                  >
                    {t("client.regularize_payment")}
                  </a>
                </>
              ) : null}
            </section>
          ) : null}
          {paymentMethodSetupSubscriptions.length > 0 ? (
            <section className="flash-warn">
              <p>{t("client.payment_method_required_at_renewal")}</p>
              <div className="row">
                {paymentMethodSetupSubscriptions.map((sub) => (
                  <form action={openClientPaymentCheckoutAction} key={`payment-method-setup-${sub.id}`}>
                    {sub.direct_payment_recovery_url ? (
                      <input type="hidden" name="payment_url" value={sub.direct_payment_recovery_url} />
                    ) : (
                      <input type="hidden" name="payment_id" value={`plan:${sub.id}`} />
                    )}
                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })} />
                    <button type="submit" className="client-pay-cta">
                      {t("client.enter_payment_method")} · {sub.owner_display_name}
                    </button>
                  </form>
                ))}
              </div>
            </section>
          ) : null}

          {tab === "home" ? (
            <>
              <SectionCard
                title={t("client.home")}
                className="client-home-header-v2"
                action={<Link className="mode-link" href={homePlanningHref}>{t("client.view_schedule")}</Link>}
              >
                <p className="muted">{t("client.hello", { name: me.first_name || displayName })}</p>
                {linkedMembers.length > 0 ? (
                  <FilterChipsBar className="client-member-chips">
                    <a className={`badge ${selectedMemberFilter === "ALL" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", member_id: "ALL" })}>
                      {t("common.all")}
                    </a>
                    {linkedMembers.map((member) => (
                      <a
                        key={`home-chip-${member.id}`}
                        className={`badge ${selectedMemberFilter === member.id ? "active" : ""}`}
                        href={withUpdatedQuery(rawParams, { tab: "home", member_id: member.id })}
                      >
                        {member.display_name}
                      </a>
                    ))}
                  </FilterChipsBar>
                ) : null}
              </SectionCard>

              <section className="client-home-layout">
                <div className="client-home-main">
                  {homeDueTotal > 0 ? (
                    <UrgentPayCard
                      titleLabel={t("client.amount_due")}
                      amountLabel={toMoney(String(homeDueTotal), me.preferred_currency, language)}
                      countLabel={t("client.invoice_count", { count: homeDueInvoices.length })}
                    >
                      <div className="client-home-due-list">
                        {homeDueInvoicePreview.map((invoice) => {
                          const linkedPayment = paymentByInvoiceId.get(invoice.id);
                          const canPayInvoice = (linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(invoice.payment_url);
                          return (
                            <CompactInvoiceRow
                              key={`home-due-${invoice.id}`}
                              title={compactId(invoice.invoice_number)}
                              statusBadge={<span className={`status-pill ${statusClass(invoice.status)}`}>{financeStatusLabel(invoice.status, language)}</span>}
                              meta={`${toMoney(invoice.total_incl_vat, invoice.currency, language)} · ${formatDate(invoice.issued_at, language)}`}
                              subline={invoicePeriodSubline(invoice.label, language)}
                              actions={
                                <div className="row client-home-due-actions">
                                  {canPayInvoice ? (
                                    <form action={openClientPaymentCheckoutAction}>
                                      {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                      {invoice.payment_url ? <input type="hidden" name="payment_url" value={invoice.payment_url} /> : null}
                                      <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "home" })} />
                                      <button type="submit" className="client-card-primary-action">{t("common.pay")}</button>
                                    </form>
                                  ) : null}
                                  <a
                                    className="mode-link"
                                    href={clientInvoiceHref(invoice.id, { inline: true })}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {t("common.view")}
                                  </a>
                                </div>
                              }
                            />
                          );
                        })}
                      </div>
                      <div className="row client-home-urgent-actions">
                        {homePrimaryPayableRow || homePrimaryPayUrl ? (
                          <form action={openClientPaymentCheckoutAction}>
                            {homePrimaryPayableRow ? <input type="hidden" name="payment_id" value={homePrimaryPayableRow.id} /> : null}
                            {homePrimaryPayUrl ? <input type="hidden" name="payment_url" value={homePrimaryPayUrl} /> : null}
                            <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "home" })} />
                            <button type="submit" className="client-pay-cta">
                              {t("common.pay")} {toMoney(String(homeDueTotal), me.preferred_currency, language)}
                            </button>
                          </form>
                        ) : (
                          <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", finance_status: "TO_PAY" })}>
                            {t("common.pay")} {toMoney(String(homeDueTotal), me.preferred_currency, language)}
                          </a>
                        )}
                        <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                          {t("client.view_all_invoices")}
                        </a>
                      </div>
                    </UrgentPayCard>
                  ) : null}

                  <SectionCard title={t("client.upcoming_14_days")} action={<Link className="mode-link" href={homePlanningHref}>{t("client.view_schedule")}</Link>}>
                    {upcomingBookings14.length === 0 ? (
                      <p className="muted">{t("client.no_upcoming_14_days")}</p>
                    ) : (
                      <div className="client-home-coming-list">
                        {upcomingBookings14.slice(0, 3).map((booking) => (
                          <UpcomingLessonRow
                            key={`home-upcoming-${booking.id}`}
                            timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone, language)}
                            title={booking.session.title}
                            subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone, language)} · ${booking.owner_display_name} · ${statusLabel(booking.status, language)}`}
                            action={
                              <a
                                className="mode-link"
                                href={withUpdatedQuery(rawParams, {
                                  tab: "planning",
                                  agenda_view: "day",
                                  agenda_date: dateKeyInTimezone(booking.session.start_at_utc, timezone),
                                  session_id: booking.session.id,
                                  booking_owner_id: booking.owner_client_id,
                                })}
                              >
                                {t("common.view")}
                              </a>
                            }
                          />
                        ))}
                      </div>
                    )}
                  </SectionCard>
                </div>

                <aside className="client-home-side">
                  <SectionCard title={t("client.my_plans")} action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>{t("common.view_all")}</a>}>
                    {homeSubscriptionsPreview.length === 0 ? (
                      <p className="muted">{t("client.no_active_subscription_preview")}</p>
                    ) : (
                      <div className="client-forfait-preview-list">
                        {homeSubscriptionsPreview.map((sub) => {
                          const isPack = normalizeStatus(sub.plan.kind) === "PACK";
                          const initialCredits = sub.credits_initial ?? 0;
                          const remainingCredits = sub.credits_remaining ?? 0;
                          const consumedCredits = Math.max(0, initialCredits - remainingCredits);
                          const ratio = initialCredits > 0 ? Math.min(100, Math.round((consumedCredits / initialCredits) * 100)) : 0;
                          const linkedPlan = plans.find((plan) => plan.id === sub.plan.id);
                          const subscriptionPrice = planDisplayPrice(linkedPlan) ?? sub.plan.price_ttc;
                          const subscriptionCurrency = linkedPlan?.currency_code ?? sub.plan.currency_code ?? me.preferred_currency;
                          const offerBookings = allBookings.filter(
                            (booking) => booking.client_plan_subscription_id === sub.id && normalizeStatus(booking.status) !== "CANCELLED",
                          );
                          const offerActivityCount = new Set(offerBookings.map((booking) => booking.session.title)).size;
                          const detailLine = isPack
                            ? t("client.remaining_credits", { remaining: remainingCredits, initial: initialCredits || "?" })
                            : offerActivityCount > 0
                              ? t("client.offer_program_summary", { activities: offerActivityCount, sessions: offerBookings.length })
                              : `${toMoney(sub.plan.kind === "FORFAIT" ? "0" : subscriptionPrice, subscriptionCurrency, language)} ${language === "en" ? "/ period" : "/ periode"} · ${paymentMethodLabel(sub.billing_method_code, language)}`;
                          const expiryLine = sub.offer_deposit_amount_ttc && normalizeStatus(sub.offer_deposit_status || "") === "PAID"
                            ? t("client.deposit_paid_amount", { amount: toMoney(sub.offer_deposit_amount_ttc, sub.offer_currency || subscriptionCurrency, language) })
                            : sub.ends_at
                            ? t("client.expiration", { date: formatDate(sub.ends_at, language) })
                            : sub.next_payment_at
                              ? t("client.next_debit", { date: formatDate(sub.next_payment_at, language) })
                              : t("client.no_end_date");
                          return (
                            <PlanCard
                              key={`home-sub-${sub.id}`}
                              title={sub.plan.name}
                              typeBadge={<span className="badge">{planKindLabel(sub.plan.kind, language)}</span>}
                              memberStatus={`${sub.owner_display_name} · ${statusLabel(sub.status, language)}`}
                              detailLine={detailLine}
                              expiryLine={expiryLine}
                              progressRatio={isPack ? ratio : undefined}
                              progressLabel={isPack ? t("client.progress", { consumed: consumedCredits, initial: initialCredits || "?" }) : undefined}
                              action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })}>{t("client.view_details")}</a>}
                            />
                          );
                        })}
                      </div>
                    )}
                  </SectionCard>

                  <SectionCard title={t("client.latest_invoices")} action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices" })}>{t("common.view_all")}</a>}>
                    {baseInvoiceRows.length === 0 ? (
                      <p className="muted">{t("client.no_invoice")}</p>
                    ) : (
                      <div className="client-home-due-list">
                        {baseInvoiceRows.slice(0, 3).map((invoice) => (
                          <CompactInvoiceRow
                            key={`home-last-invoice-${invoice.id}`}
                            title={compactId(invoice.invoice_number)}
                            statusBadge={<span className={`status-pill ${statusClass(invoice.status)}`}>{financeStatusLabel(invoice.status, language)}</span>}
                            meta={`${toMoney(invoice.total_incl_vat, invoice.currency, language)} · ${formatDate(invoice.issued_at, language)} · ${invoice.owner_display_name}`}
                            subline={invoicePeriodSubline(invoice.label, language)}
                            actions={
                              <div className="row client-home-due-actions">
                                <a
                                  className="mode-link"
                                  href={clientInvoiceHref(invoice.id, { inline: true })}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {t("common.view")}
                                </a>
                                {invoice.download_url ? (
                                  <a className="mode-link" href={invoice.download_url}>
                                    {t("common.download")}
                                  </a>
                                ) : null}
                              </div>
                            }
                          />
                        ))}
                      </div>
                    )}
                  </SectionCard>
                </aside>
              </section>

              <SectionCard
                title={hasMultipleVisibleMembers ? t("client.family_calendar") : t("client.calendar")}
                action={
                  hasMultipleVisibleMembers ? (
                    <div className="row">
                      <a className={`mode-link ${normalizedHomeCalendarView === "FAMILY" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "FAMILY" })}>
                        {t("client.family_view")}
                      </a>
                      <a className={`mode-link ${normalizedHomeCalendarView === "BY_MEMBER" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "BY_MEMBER" })}>
                        {t("client.by_child")}
                      </a>
                    </div>
                  ) : undefined
                }
              >
                {homeCalendarRows.length === 0 ? (
                  <p className="muted">{t("client.no_upcoming_14_days")}</p>
                ) : normalizedHomeCalendarView === "BY_MEMBER" ? (
                  <div className="client-home-calendar-groups">
                    {homeCalendarGroups.map(([memberName, rows]) => (
                      <article key={`home-calendar-group-${memberName}`} className="client-home-calendar-group">
                        <h3>{memberName}</h3>
                        <div className="client-home-calendar-list">
                          {rows.slice(0, 3).map((booking) => (
                            <UpcomingLessonRow
                              key={`home-booking-group-${booking.id}`}
                              timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone, language)}
                              title={booking.session.title}
                              subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone, language)} · ${statusLabel(booking.status, language)}`}
                              action={
                                <a
                                  className="mode-link"
                                  href={withUpdatedQuery(rawParams, {
                                    tab: "planning",
                                    agenda_view: "day",
                                    agenda_date: dateKeyInTimezone(booking.session.start_at_utc, timezone),
                                    session_id: booking.session.id,
                                    booking_owner_id: booking.owner_client_id,
                                  })}
                                >
                                  {t("common.view")}
                                </a>
                              }
                            />
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="client-home-calendar-list">
                    {homeCalendarRows.slice(0, 6).map((booking) => (
                      <UpcomingLessonRow
                        key={`home-booking-${booking.id}`}
                        timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone, language)}
                        title={booking.session.title}
                        subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone, language)} · ${booking.owner_display_name} · ${statusLabel(booking.status, language)}`}
                        action={
                          <a
                            className="mode-link"
                            href={withUpdatedQuery(rawParams, {
                              tab: "planning",
                              agenda_view: "day",
                              agenda_date: dateKeyInTimezone(booking.session.start_at_utc, timezone),
                              session_id: booking.session.id,
                              booking_owner_id: booking.owner_client_id,
                            })}
                          >
                            {t("common.view")}
                          </a>
                        }
                      />
                    ))}
                  </div>
                )}
              </SectionCard>

              <SectionCard title={t("client.latest_reminders")} action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>{t("common.view_all")}</a>}>
                {newsRows.length === 0 ? (
                  <p className="muted">{t("client.no_recent_reminder")}</p>
                ) : (
                  <div className="list">
                    {newsRows.map((message) => (
                      <article key={`home-news-${message.id}`} className="item">
                        <strong>{message.subject_preview || t("client.message_fallback")}</strong>
                        <p className="muted">{formatDateTime(message.sent_at || message.scheduled_for_utc, language)} · {message.channel}</p>
                      </article>
                    ))}
                  </div>
                )}
              </SectionCard>

              {homeDueTotal > 0 ? (
                <div className="client-home-sticky-pay">
                  {homePrimaryPayableRow || homePrimaryPayUrl ? (
                    <form action={openClientPaymentCheckoutAction}>
                      {homePrimaryPayableRow ? <input type="hidden" name="payment_id" value={homePrimaryPayableRow.id} /> : null}
                      {homePrimaryPayUrl ? <input type="hidden" name="payment_url" value={homePrimaryPayUrl} /> : null}
                      <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "home" })} />
                      <button type="submit" className="client-pay-cta">
                        {t("common.pay")} {toMoney(String(homeDueTotal), me.preferred_currency, language)}
                      </button>
                    </form>
                  ) : (
                    <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", finance_status: "TO_PAY" })}>
                      {t("common.pay")} {toMoney(String(homeDueTotal), me.preferred_currency, language)}
                    </a>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

          {tab === "planning" ? (
            <>
              <Card className="client-planning-shell">
                <div className="row spread client-planning-heading">
                  <div>
                    <h2>{t("client.weekly_schedule")}</h2>
                    <p className="muted">{t("client.weekly_schedule_help")}</p>
                  </div>
                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                    🛍️ {t("client.offers")}
                  </a>
                </div>

                <div className="client-planning-mode-switch" aria-label={t("client.planning_mode_label")}>
                  <a
                    className={`client-planning-mode-card ${planningMode === "reservations" ? "active" : ""}`}
                    href={planningReservationsHref}
                  >
                    <strong>{t("client.planning_mode_reservations")}</strong>
                    <small>{t("client.planning_mode_reservations_help")}</small>
                  </a>
                  <a className={`client-planning-mode-card ${planningMode === "book" ? "active" : ""}`} href={planningBookHref}>
                    <strong>{t("client.planning_mode_book")}</strong>
                    <small>{t("client.planning_mode_book_help")}</small>
                  </a>
                </div>

                {planningMode === "book" ? (
                <>
                <form method="get" className="client-planning-filter-form">
                  <input type="hidden" name="tab" value="planning" />
                  <input type="hidden" name="planning_mode" value="book" />
                  <input type="hidden" name="agenda_view" value="week" />

                  <div className="client-planning-hero">
                    <label className="client-planning-pill client-planning-pill-location">
                      <span>📍 {t("client.planning")}</span>
                      <AutoSubmitSelect
                        name="location_id"
                        defaultValue={selectedLocation}
                        options={[
                          { value: "", label: t("client.all_locations") },
                          ...locations.map((location) => ({ value: location.id, label: location.name })),
                        ]}
                      />
                    </label>

                    <label className="client-planning-pill client-planning-pill-date">
                      <span>📅 Date</span>
                      <AutoSubmitInput
                        type="date"
                        name="agenda_date"
                        defaultValue={agendaDate}
                        ariaLabel={t("client.schedule_date")}
                      />
                    </label>

                    <div className="client-planning-toolbar-actions">
                      <a
                        className="client-planning-reset"
                        href={withUpdatedQuery(rawParams, {
                          tab: "planning",
                          planning_mode: "book",
                          course_type_id: null,
                          location_id: null,
                          coach_id: null,
                          time_bucket: null,
                          planning_slot_filter: null,
                          timezone: me.timezone || DEFAULT_TIMEZONE,
                          agenda_view: "week",
                          agenda_date: todayKeyInTimezone(timezone),
                          booking_owner_id: FAMILY_BOOKING_OWNER,
                          session_id: null,
                          session_member_id: null,
                        })}
                        title={t("common.reset")}
                      >
                        ↺
                      </a>
                    </div>
                  </div>

                  <DrawerFilters title={`⚙ ${t("client.advanced_filters")}`} className={`client-planning-advanced ${advancedFiltersOpen ? "has-active" : ""}`} defaultOpen={advancedFiltersOpen}>
                    <div className="client-planning-advanced-grid">
                      <label>
                        {t("client.activity")}
                        <AutoSubmitSelect
                          name="course_type_id"
                          defaultValue={selectedCourseType}
                          options={[
                            { value: "", label: t("common.all") },
                            ...courseTypes.map((courseType) => ({ value: courseType.id, label: courseType.name })),
                          ]}
                        />
                      </label>

                      <label>
                        {t("client.coach")}
                        <AutoSubmitSelect
                          name="coach_id"
                          defaultValue={selectedCoachId}
                          options={[
                            { value: "", label: t("common.all") },
                            ...coachOptions.map((coach) => ({ value: coach.id, label: coach.name })),
                          ]}
                        />
                      </label>

                      <label>
                        {t("client.time_label")}
                        <AutoSubmitSelect
                          name="time_bucket"
                          defaultValue={selectedTimeBucket}
                          options={[
                            { value: "ALL", label: t("client.all_hours") },
                            { value: "MORNING", label: t("client.morning") },
                            { value: "AFTERNOON", label: t("client.afternoon") },
                            { value: "EVENING", label: t("client.evening") },
                          ]}
                        />
                      </label>

                      <label>
                        {t("client.timezone_label")}
                        <AutoSubmitSelect
                          name="timezone"
                          defaultValue={timezone}
                          options={timezoneOptions.map((item) => ({ value: item.value, label: item.label }))}
                        />
                      </label>

                      {hasMultipleVisibleMembers ? (
                      <label>
                        {t("client.booking_for")}
                          <AutoSubmitSelect
                            name="booking_owner_id"
                            defaultValue={bookingOwnerId}
                            options={[
                              { value: FAMILY_BOOKING_OWNER, label: t("client.whole_family") },
                              ...members.map((member) => ({ value: member.id, label: member.display_name })),
                            ]}
                          />
                        </label>
                      ) : (
                        <input type="hidden" name="booking_owner_id" value={bookingOwnerId} />
                      )}

                      <label>
                        {t("client.slot_status")}
                        <AutoSubmitSelect
                          name="planning_slot_filter"
                          defaultValue={planningSlotFilter}
                          options={[
                            { value: "ALL", label: t("common.all") },
                            { value: "AVAILABLE", label: t("client.available_only") },
                            { value: "ALREADY_BOOKED", label: t("client.already_booked") },
                          ]}
                        />
                      </label>
                    </div>
                  </DrawerFilters>
                </form>

                <div className="client-week-toolbar">
                  <div className="client-week-toolbar-head">
                    <div className="client-week-title-group">
                      <span className="badge">{bookingOwnerLabel}</span>
                      <strong>{agendaRange.title}</strong>
                      <small>{hasMultipleVisibleMembers ? t("client.week_toolbar_family_help") : t("client.week_toolbar_single_help")}</small>
                    </div>
                    <div className="client-week-toolbar-actions">
                      <a
                        className="client-date-nav-btn"
                        href={withUpdatedQuery(rawParams, { tab: "planning", planning_mode: "book", agenda_date: shiftDateKeyByDays(agendaDate, -7), agenda_view: "week" })}
                        aria-label={t("client.previous_week")}
                      >
                        ←
                      </a>
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "planning", planning_mode: "book", agenda_date: todayKeyInTimezone(timezone), agenda_view: "week" })}>
                        {t("client.today")}
                      </a>
                      <a
                        className="client-date-nav-btn"
                        href={withUpdatedQuery(rawParams, { tab: "planning", planning_mode: "book", agenda_date: shiftDateKeyByDays(agendaDate, 7), agenda_view: "week" })}
                        aria-label={t("client.next_week")}
                      >
                        →
                      </a>
                    </div>
                  </div>
                  <div className="client-week-legend">
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch reserved" />
                      {t("client.my_bookings")}
                    </span>
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch available" />
                      {t("client.book_or_pay")}
                    </span>
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch full" />
                      {t("client.closed_or_full")}
                    </span>
                  </div>
                </div>
                </>
                ) : null}
              </Card>

              {planningMode === "reservations" ? (
                <Card className="client-reserved-section client-planning-reservations-panel">
                  <div className="row spread">
                    <div>
                      <h2>{t("client.upcoming_reservations")}</h2>
                      <p className="muted">{t("client.upcoming_reservations_help")}</p>
                    </div>
                    <span className="badge">{upcomingBookings.length}</span>
                  </div>

                  {upcomingBookings.length === 0 ? (
                    <div className="client-planning-empty">
                      <strong>{t("client.no_upcoming_reservation")}</strong>
                      <p className="muted">{t("client.no_upcoming_reservation_help")}</p>
                      <a className="mode-link" href={planningBookHref}>
                        {t("client.book_another_lesson")}
                      </a>
                    </div>
                  ) : (
                    <>
                      <div className="client-planning-month-nav">
                        <a
                          className="client-date-nav-btn"
                          href={previousReservationMonthHref}
                          aria-label={t("client.previous_month")}
                        >
                          ←
                        </a>
                        <div className="client-planning-month-summary">
                          <span>{t("client.reservation_month_label")}</span>
                          <strong>{selectedReservationMonthLabel}</strong>
                          <small>
                            {t("client.reservation_month_count", {
                              count: selectedMonthBookings.length,
                              total: upcomingBookings.length,
                            })}
                          </small>
                        </div>
                        <a
                          className="client-date-nav-btn"
                          href={nextReservationMonthHref}
                          aria-label={t("client.next_month")}
                        >
                          →
                        </a>
                        <a className="mode-link" href={nextBookingMonthHref}>
                          {t("client.next_booking_month")}
                        </a>
                      </div>

                      {selectedMonthBookings.length === 0 ? (
                        <div className="client-planning-empty">
                          <strong>{t("client.no_reservation_this_month")}</strong>
                          <p className="muted">{t("client.no_reservation_this_month_help")}</p>
                        </div>
                      ) : (
                        <div className="client-planning-reservation-list">
                          {selectedMonthBookings.map((booking) => {
                            const bookingSessionDetails = sessionDetailsById.get(booking.session.id);
                            const bookingStatus = normalizeStatus(booking.status);
                            const bookingStatusLabel =
                              bookingStatus === "PENDING_PAYMENT"
                                ? t("client.planning_status_payment_pending")
                                : bookingStatus === "WAITLISTED"
                                  ? t("client.planning_status_waitlisted")
                                  : t("client.planning_status_already_booked");
                            const bookingHref = withUpdatedQuery(rawParams, {
                              tab: "planning",
                              planning_mode: "reservations",
                              agenda_view: "week",
                              agenda_date: dateKeyInTimezone(booking.session.start_at_utc, timezone),
                              reservation_month: selectedReservationMonth,
                              session_id: booking.session.id,
                              session_member_id: booking.owner_client_id,
                              ok: null,
                              error: null,
                              ok_code: null,
                              error_code: null,
                              session_ok: null,
                              session_error: null,
                              session_ok_code: null,
                              session_error_code: null,
                            });

                            return (
                              <article key={`booking-${booking.id}`} className="client-planning-reservation-card">
                                <div className="client-planning-reservation-time">
                                  <strong>{formatTimeInTimezone(booking.session.start_at_utc, timezone, language)}</strong>
                                  <small>{formatTimeInTimezone(booking.session.end_at_utc, timezone, language)}</small>
                                </div>
                                <div className="client-planning-reservation-main">
                                  <strong>{booking.session.title}</strong>
                                  <small>{formatDateTimeInTimezone(booking.session.start_at_utc, timezone, language)}</small>
                                  <div className="client-planning-reservation-meta">
                                    <span className="badge">{t("client.reserved_for_member", { member: booking.owner_display_name })}</span>
                                    {bookingSessionDetails?.location.name ? <span className="badge">{bookingSessionDetails.location.name}</span> : null}
                                    <span className={`status-badge ${bookingStatus === "BOOKED" ? "status-booked" : "status-waitlist"}`}>
                                      {bookingStatusLabel}
                                    </span>
                                  </div>
                                </div>
                                <div className="client-planning-reservation-actions">
                                  <a className="mode-link" href={bookingHref}>
                                    {t("client.view_booking_detail")}
                                  </a>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}

                  {upcomingBookings.length > 0 ? (
                    <div className="client-planning-reservation-footer">
                      <a className="mode-link" href={planningBookHref}>
                        {t("client.book_another_lesson")}
                      </a>
                    </div>
                  ) : null}
                </Card>
              ) : null}

              {planningMode === "book" ? (
              <Card className="client-available-section client-week-planning-board">
                <div className="row spread">
                  <h2>{t("client.additional_booking_week")}</h2>
                  <span className="badge">{agendaSessionCount}</span>
                </div>
                <p className="muted">{t("client.additional_booking_week_help")}</p>
                <form method="get" className="client-planning-quick-filter-form">
                  <input type="hidden" name="tab" value="planning" />
                  <input type="hidden" name="planning_mode" value="book" />
                  <input type="hidden" name="agenda_view" value="week" />
                  <input type="hidden" name="agenda_date" value={agendaDate} />
                  <input type="hidden" name="location_id" value={selectedLocation} />
                  <input type="hidden" name="course_type_id" value={selectedCourseType} />
                  <input type="hidden" name="coach_id" value={selectedCoachId} />
                  <input type="hidden" name="time_bucket" value={selectedTimeBucket} />
                  <input type="hidden" name="timezone" value={timezone} />
                  <input type="hidden" name="booking_owner_id" value={bookingOwnerId} />
                  <label className="client-planning-quick-filter-label">
                    <span>{t("client.show")}</span>
                    <AutoSubmitSelect
                      name="planning_slot_filter"
                      defaultValue={planningSlotFilter}
                      options={[
                        { value: "ALL", label: t("client.all_slots") },
                        { value: "AVAILABLE", label: t("client.book_now") },
                        { value: "ALREADY_BOOKED", label: t("client.my_bookings") },
                      ]}
                    />
                  </label>
                </form>
                <div className={`agenda-grid client-agenda-grid agenda-grid-${agendaView}`}>
                  {agendaDays.map((day) => {
                    const daySessions = day.sessions.filter((session) => {
                      const sessionState = planningStateForSession(session);
                      if (planningSlotFilter === "AVAILABLE") {
                        return sessionState.canCheckout;
                      }
                      if (planningSlotFilter === "ALREADY_BOOKED") {
                        return sessionState.alreadyReserved || sessionState.paymentPending;
                      }
                      return true;
                    });

                    return (
                      <article key={day.key} className={`agenda-day client-agenda-day client-agenda-day-${agendaView}`}>
                        <div className="row spread agenda-day-header">
                          <div className="client-agenda-day-headings">
                            <h3>{day.label}</h3>
                          </div>
                          <span className="badge">{daySessions.length}</span>
                        </div>

                        {daySessions.length === 0 ? <p className="muted agenda-empty">{t("client.no_course")}</p> : null}

                        <div className="agenda-events">
                          {daySessions.map((session) => {
                            const sessionState = planningStateForSession(session);
                            const compactAgendaCard = true;
                            const accentColor = accentColorForId(session.course_type.id);
                            const durationMinutes = Math.max(
                              1,
                              Math.round((new Date(session.end_at_utc).getTime() - new Date(session.start_at_utc).getTime()) / 60000),
                            );
                            const openDetailsHref = withUpdatedQuery(rawParams, {
                              tab: "planning",
                              planning_mode: "book",
                              session_id: session.id,
                              session_member_id: null,
                              ok: null,
                              error: null,
                              ok_code: null,
                              error_code: null,
                              session_ok: null,
                              session_error: null,
                              session_ok_code: null,
                              session_error_code: null,
                            });
                            const reservationFlagLabel =
                              sessionState.familyBookings.length > 1
                                ? t("client.bookings_count", { count: sessionState.familyBookings.length })
                                : null;
                            const bookingBadges = sessionState.familyBookings.filter((booking) =>
                              isAlreadyReservedByMember(booking.status) || isPendingPaymentBooking(booking.status),
                            );
                            const bookingSummaryLabel =
                              bookingBadges.length > 1
                                ? t("client.family_bookings_badge", { count: bookingBadges.length })
                                : bookingBadges.length === 1
                                  ? bookingOwnerId === FAMILY_BOOKING_OWNER
                                    ? isPendingPaymentBooking(bookingBadges[0].status)
                                      ? `${bookingBadges[0].owner_display_name} · ${t("client.payment_short")}`
                                      : t("client.booked_for", { members: bookingBadges[0].owner_display_name })
                                    : isPendingPaymentBooking(bookingBadges[0].status)
                                      ? t("client.planning_status_payment_pending")
                                      : t("client.reserved_short")
                                  : null;
                            const cardStatusClass = planningStatusClass(sessionState.cardStatusCode);
                            const showPlanningStateBadge =
                              !sessionState.alreadyReserved && shouldRenderPlanningStateBadge(sessionState.cardStatusCode);
                            const sessionCtaLabel = sessionState.alreadyReserved
                              ? sessionState.actionableMembers.length > 0
                                ? t("client.book_action")
                                : t("client.view_booking")
                              : sessionState.paymentPending
                                ? t("client.complete_payment_action")
                                : sessionState.canCheckout
                                  ? sessionState.actionLabel
                                  : sessionState.isFull
                                  ? planningStatusLabel("FULL")
                                  : t("client.view_details");

                            return (
                              <a
                                key={session.id}
                                className="client-session-link"
                                href={openDetailsHref}
                                aria-label={t("client.open_slot_detail", { title: session.title })}
                              >
                                <article
                                  className={`client-session-card ${compactAgendaCard ? "client-session-card-compact" : ""} ${sessionState.alreadyReserved ? "client-session-card-booked" : ""} ${statusClass(session.status)}`}
                                >
                                  {!compactAgendaCard ? (
                                    <div className="client-session-timebox">
                                      <span aria-hidden="true">🕒</span>
                                      <strong>{formatTimeInTimezone(session.start_at_utc, timezone, language)}</strong>
                                      <small>{formatTimeInTimezone(session.end_at_utc, timezone, language)}</small>
                                    </div>
                                  ) : null}

                                  <div className={`agenda-event client-agenda-event ${statusClass(session.status)}`}>
                                    <div className="client-event-topline">
                                      {sessionState.alreadyReserved ? <span className="client-session-owned-flag">{reservationFlagLabel}</span> : null}
                                      <span className="client-session-location-chip">{session.location.name}</span>
                                    </div>
                                    <div className="row spread client-event-head">
                                      <h3 className="event-title">{session.title}</h3>
                                      <span className="client-event-color" style={{ backgroundColor: accentColor }} aria-hidden="true" />
                                    </div>
                                    {compactAgendaCard ? <small className="event-meta">🕒 {formatTimeInTimezone(session.start_at_utc, timezone, language)} - {formatTimeInTimezone(session.end_at_utc, timezone, language)}</small> : null}
                                    <small className="event-meta">🎵 {session.course_type.name}</small>
                                    <div className="row">
                                      <span className="occ-badge">{session.booked_count}/{session.capacity_max}</span>
                                      <small className="event-meta">⏱ {durationMinutes} min</small>
                                    </div>
                                    {session.professor ? <small className="event-meta event-meta-secondary">👨‍🏫 {sessionProfessorName(session)}</small> : null}
                                    <small className="event-meta event-meta-secondary">📍 {session.location.name}</small>
                                    {!(sessionState.alreadyReserved && bookingSummaryLabel) ? (
                                      <small className="event-meta event-meta-secondary">{sessionState.contextLine}</small>
                                    ) : null}

                                    <div className="row client-event-footer">
                                      {bookingSummaryLabel ? (
                                        <span className={`status-badge ${sessionState.paymentPending ? "status-waitlist" : "status-booked"}`}>
                                          {bookingSummaryLabel}
                                        </span>
                                      ) : null}
                                      {showPlanningStateBadge ? (
                                        <span className={`status-badge ${cardStatusClass}`}>
                                          {sessionState.cardStatusLabel}
                                        </span>
                                      ) : null}
                                      <span className={`client-session-cta ${sessionState.canCheckout || sessionState.paymentPending ? "ready" : ""}`}>
                                        {sessionCtaLabel}
                                      </span>
                                    </div>
                                  </div>
                                </article>
                              </a>
                            );
                          })}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </Card>
              ) : null}

              {selectedSession ? (
                <section className="modal-overlay">
                  <article className="modal-panel modal-client-session-details">
                    <header className="client-session-modal-header">
                      <a
                        className="modal-close-x"
                        href={selectedSessionCloseHref}
                        aria-label={t("client.close_slot_detail")}
                      >
                        ×
                      </a>
                      <h2>{selectedSession.title}</h2>
                      <p className="muted">
                        {formatDateTimeInTimezone(selectedSession.start_at_utc, timezone, language)} - {formatTimeInTimezone(selectedSession.end_at_utc, timezone, language)}
                      </p>
                      <div className="row">
                        <span className="occ-badge">
                          {selectedSession.booked_count}/{selectedSession.capacity_max}
                        </span>
                        {selectedSessionModalStatusLabel ? (
                          <span className={`status-badge ${planningStatusClass(selectedSessionModalStatusCode)}`}>
                            {selectedSessionModalStatusLabel}
                          </span>
                        ) : null}
                        {!selectedSession.online_booking_enabled ? <span className="badge">{t("client.online_booking_closed")}</span> : null}
                      </div>
                    </header>

                    <section className="modal-card client-session-modal-grid">
                      <article className="item">
                        <small className="muted">{t("client.coach_label")}</small>
                        <p>
                          {sessionProfessorName(selectedSession)}
                        </p>
                      </article>
                      <article className="item">
                        <small className="muted">{t("client.location_label")}</small>
                        <p>{selectedSession.location.name}</p>
                      </article>
                      <article className="item">
                        <small className="muted">{t("client.activity_label")}</small>
                        <p>{selectedSession.course_type.name}</p>
                      </article>
                      <article className="item">
                        <small className="muted">{t("client.duration_label")}</small>
                        <p>
                          {Math.max(
                            1,
                            Math.round((new Date(selectedSession.end_at_utc).getTime() - new Date(selectedSession.start_at_utc).getTime()) / 60000),
                          )}{" "}
                          min
                        </p>
                      </article>
                    </section>

                    {selectedSession.description ? (
                      <section className="modal-card">
                        <small className="muted">{t("client.description_label")}</small>
                        <p>{selectedSession.description}</p>
                      </section>
                    ) : null}

                    {selectedSession.zoom_link ? (
                      <section className="modal-card">
                        <small className="muted">{t("client.zoom_link_label")}</small>
                        <p>
                          <a href={selectedSession.zoom_link} target="_blank" rel="noreferrer">
                            {selectedSession.zoom_link}
                          </a>
                        </p>
                      </section>
                    ) : null}

                    {selectedSessionHasBooking && selectedReservationMemberOption ? (
                      <section className="modal-card client-session-modal-state">
                        <div className="row spread">
                          <div className="client-session-modal-state-copy">
                            <small className="muted">{t("client.booking_status_label")}</small>
                            <p className="client-session-modal-state-title">{selectedSessionBookedStateTitle}</p>
                            <p>{selectedSessionBookedStateDescription}</p>
                          </div>
                          {selectedSessionModalStatusLabel ? (
                            <span className={`status-badge ${planningStatusClass(selectedSessionModalStatusCode)}`}>
                              {selectedSessionModalStatusLabel}
                            </span>
                          ) : null}
                        </div>
                      </section>
                    ) : selectedSessionPlanningState ? (
                      <section className="modal-card client-session-modal-state">
                        <div className="row spread">
                          <div className="client-session-modal-state-copy">
                            <small className="muted">{t("client.next_step_label")}</small>
                            <p className="client-session-modal-state-title">
                              {selectedSessionStateTitle}
                            </p>
                            <p>{selectedSessionStateDescription}</p>
                          </div>
                          {selectedSessionModalStatusLabel ? (
                            <span className={`status-badge ${planningStatusClass(selectedSessionModalStatusCode)}`}>
                              {selectedSessionModalStatusLabel}
                            </span>
                          ) : null}
                        </div>
                        {selectedSessionCoverageLabel ? (
                          <div className="client-session-modal-state-meta">
                            <span className="badge">{selectedSessionCoverageLabel}</span>
                            {selectedReservationMemberOption ? (
                              <span className="badge">
                                {t("client.for_member", { member: selectedReservationMemberOption.member_display_name })}
                              </span>
                            ) : null}
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {reservationOptionsMembers.length > 1 ? (
                      <section className="modal-card">
                        <div className="client-session-member-picker">
                          <div className="client-session-member-picker-heading">
                            <small className="muted">{t("client.member_concerned")}</small>
                            <p>{t("client.member_picker_help")}</p>
                          </div>
                          <div className="client-session-member-grid">
                            {reservationOptionsMembers.map((option) => {
                              const isSelected = option.member_id === selectedReservationMemberId;
                              const selectionHref = withUpdatedQuery(rawParams, {
                                tab: "planning",
                                planning_mode: planningMode,
                                agenda_view: "week",
                                agenda_date: agendaDate,
                                location_id: selectedLocation || null,
                                course_type_id: selectedCourseType || null,
                                coach_id: selectedCoachId || null,
                                time_bucket: selectedTimeBucket || null,
                                timezone,
                                planning_slot_filter: planningSlotFilter,
                                session_id: selectedSession.id,
                                session_member_id: option.member_id,
                              });
                              return (
                                <a
                                  key={option.member_id}
                                  className={`client-session-member-card ${isSelected ? "active" : ""}`}
                                  href={selectionHref}
                                  aria-current={isSelected ? "true" : undefined}
                                >
                                  {isSelected ? (
                                    <span className="client-session-member-selected-label">{t("client.selected_member")}</span>
                                  ) : null}
                                  <div className="client-session-member-card-head">
                                    <strong>{option.member_display_name}</strong>
                                    <div className="client-session-member-card-badges">
                                      <span className={`status-badge ${planningStatusClass(planningStatusCodeFromLabel(option.status_label))}`}>
                                        {planningStatusDisplayLabel(option.status_label)}
                                      </span>
                                    </div>
                                  </div>
                                  <small className="muted">{reservationOptionReasonLabel(option) || reservationOptionActionLabel(option)}</small>
                                  {reservationOptionSupportLabel(option) ? (
                                    <small className={`client-session-member-support ${isSelected ? "active" : ""}`}>
                                      {reservationOptionSupportLabel(option)}
                                    </small>
                                  ) : null}
                                </a>
                              );
                            })}
                          </div>
                        </div>
                      </section>
                    ) : null}

                    {selectedReservationMemberOption &&
                    selectedSessionActionCode === "FINALIZE_PAYMENT" &&
                    alternativeReservationOptions.length > 0 ? (
                      <section className="modal-card client-session-inline-warning">
                        <strong>{t("client.alternative_family_options_title")}</strong>
                        <p>{t("client.alternative_family_options_help", { member: selectedReservationMemberOption.member_display_name })}</p>
                        <div className="client-session-inline-warning-list">
                          {alternativeReservationOptions.map((option) => (
                            <span key={`alt-option-${option.member_id}`} className="badge">
                              {option.member_display_name}
                              {reservationOptionSupportLabel(option) ? ` · ${reservationOptionSupportLabel(option)}` : ""}
                            </span>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {sessionOkMessage ? <section className="flash-ok modal-card">{sessionOkMessage}</section> : null}
                    {sessionErrorMessage ? <section className="flash-err modal-card">{sessionErrorMessage}</section> : null}

                    {!selectedSessionHasBooking &&
                    selectedReservationMemberOption &&
                    selectedSessionFormulaOptions.length > 0 &&
                    selectedSessionEffectiveActionCode !== "BOOK_WITH_CREDIT" ? (
                      <section className="modal-card">
                        <div className="client-session-choice-heading">
                          <strong>
                            {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                              ? t("client.available_choices_for", {
                                  count: selectedSessionPurchaseChoiceCount,
                                  member: selectedReservationMemberOption.member_display_name,
                                })
                              : t("client.compatible_plans_for", {
                                  member: selectedReservationMemberOption.member_display_name,
                                })}
                          </strong>
                          <small className="muted">
                            {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                              ? t("client.choose_freely_plan_or_unit")
                              : t("client.choose_best_plan")}
                          </small>
                        </div>
                        <div className="client-plan-grid client-session-formula-grid client-session-choice-grid">
                          {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT" && selectedSessionDirectPaymentAmount ? (
                            <article className="modal-card client-plan-card client-session-formula-card client-session-choice-card">
                              <div className="client-session-formula-copy">
                                <div className="client-session-choice-card-head">
                                  <strong>{t("client.unit_payment")}</strong>
                                  <span className="badge">{t("client.immediate_booking")}</span>
                                </div>
                                <p className="muted">{t("client.pay_current_slot_only")}</p>
                                <small className="muted">
                                  {`${t("client.unit_purchase")} · ${toMoney(
                                    selectedSessionDirectPaymentAmount,
                                    selectedSessionDirectPaymentCurrency,
                                   language)}`}
                                </small>
                              </div>
                              <form action={submitPublicSessionCheckoutAction} className="client-session-formula-action">
                                <input type="hidden" name="session_id" value={selectedSession.id} />
                                <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                                <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                  {`${t("client.pay_unit")} · ${toMoney(
                                    selectedSessionDirectPaymentAmount,
                                    selectedSessionDirectPaymentCurrency,
                                   language)}`}
                                </button>
                              </form>
                            </article>
                          ) : null}
                          {selectedSessionFormulaOptions.map((formula) => (
                            <article
                              key={`formula-${formula.formula_id}`}
                              className="modal-card client-plan-card client-session-formula-card client-session-choice-card"
                            >
                              <div className="client-session-formula-copy">
                                <div className="client-session-choice-card-head">
                                  <strong>{formula.name}</strong>
                                  <span className="badge">{t("client.plan_badge")}</span>
                                </div>
                                {formula.description ? <p className="muted">{formula.description}</p> : null}
                                <small className="muted">
                                  {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels]
                                    .filter(Boolean)
                                    .map((item) => translateBackendMessage(language, item))
                                    .join(" · ")}
                                </small>
                              </div>
                              <form action={startFormulaPurchaseLinkAction} className="client-session-formula-action">
                                <input type="hidden" name="formula_id" value={formula.formula_id} />
                                <input type="hidden" name="email" value={me.email} />
                                <input type="hidden" name="session_id" value={selectedSession.id} />
                                <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                  {formula.price_ttc
                                    ? `${t("client.buy_for_member", { member: selectedReservationMemberOption.member_display_name })} · ${toMoney(formula.price_ttc, formula.currency, language)}`
                                    : t("client.buy_plan_for_member", { member: selectedReservationMemberOption.member_display_name })}
                                </button>
                              </form>
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {!selectedSessionHasBooking &&
                    selectedReservationMemberOption &&
                    selectedSessionFormulaOptions.length > 0 &&
                    selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" ? (
                      <section className="modal-card client-session-secondary-options">
                        <details>
                          <summary>
                            <span>{t("client.other_purchase_options")}</span>
                            <small className="muted">
                              {selectedSessionPurchaseChoiceCount > 0
                                ? t("client.secondary_options_count", { count: selectedSessionPurchaseChoiceCount })
                                : t("client.alternative_options")}
                            </small>
                          </summary>
                          <div className="client-session-secondary-options-body">
                            <div className="client-session-choice-heading">
                              <strong>{t("client.other_options_for", { member: selectedReservationMemberOption.member_display_name })}</strong>
                              <small className="muted">{t("client.credit_best_option_help")}</small>
                            </div>
                            <div className="client-plan-grid client-session-formula-grid client-session-choice-grid">
                              {selectedSessionDirectPaymentAmount ? (
                                <article className="modal-card client-plan-card client-session-formula-card client-session-choice-card">
                                  <div className="client-session-formula-copy">
                                    <div className="client-session-choice-card-head">
                                      <strong>{t("client.unit_payment")}</strong>
                                      <span className="badge">{t("client.secondary_option")}</span>
                                    </div>
                                    <p className="muted">{t("client.pay_without_credit")}</p>
                                    <small className="muted">
                                      {`${t("client.unit_purchase")} · ${toMoney(
                                        selectedSessionDirectPaymentAmount,
                                        selectedSessionDirectPaymentCurrency,
                                       language)}`}
                                    </small>
                                  </div>
                                  <form action={submitPublicSessionCheckoutAction} className="client-session-formula-action">
                                    <input type="hidden" name="session_id" value={selectedSession.id} />
                                    <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                    <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                    <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                                    <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                      {`${t("client.pay_unit")} · ${toMoney(
                                        selectedSessionDirectPaymentAmount,
                                        selectedSessionDirectPaymentCurrency,
                                       language)}`}
                                    </button>
                                  </form>
                                </article>
                              ) : null}
                              {selectedSessionFormulaOptions.map((formula) => (
                                <article
                                  key={`secondary-formula-${formula.formula_id}`}
                                  className="modal-card client-plan-card client-session-formula-card client-session-choice-card"
                                >
                                  <div className="client-session-formula-copy">
                                    <div className="client-session-choice-card-head">
                                      <strong>{formula.name}</strong>
                                      <span className="badge">{t("client.plan_badge")}</span>
                                    </div>
                                    {formula.description ? <p className="muted">{formula.description}</p> : null}
                                    <small className="muted">
                                      {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels]
                                        .filter(Boolean)
                                        .map((item) => translateBackendMessage(language, item))
                                        .join(" · ")}
                                    </small>
                                  </div>
                                  <form action={startFormulaPurchaseLinkAction} className="client-session-formula-action">
                                    <input type="hidden" name="formula_id" value={formula.formula_id} />
                                    <input type="hidden" name="email" value={me.email} />
                                    <input type="hidden" name="session_id" value={selectedSession.id} />
                                    <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                    <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                    <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                      {formula.price_ttc
                                        ? `${t("client.buy_for_member", { member: selectedReservationMemberOption.member_display_name })} · ${toMoney(formula.price_ttc, formula.currency, language)}`
                                        : t("client.buy_plan_for_member", { member: selectedReservationMemberOption.member_display_name })}
                                    </button>
                                  </form>
                                </article>
                              ))}
                            </div>
                          </div>
                        </details>
                      </section>
                    ) : null}

                    <footer className="modal-card client-session-modal-actions">
                      <a
                        className="mode-link client-session-modal-back-link"
                        href={selectedSessionCloseHref}
                      >
                        {t("client.back_to_schedule")}
                      </a>
                      <div className="client-session-modal-action-list">
                        {selectedSessionHasBooking && selectedReservationMemberOption?.booking_id ? (
                          <div className="client-session-modal-booking-actions">
                            {selectedReservationCanCancel ? (
                              <form action={cancelBookingAction}>
                                <input type="hidden" name="booking_id" value={selectedReservationMemberOption.booking_id} />
                                <input type="hidden" name="return_to" value={selectedSessionReturnTo} />
                                <button className="client-session-cancel-button" type="submit">
                                  {t("client.cancel_for", { member: selectedReservationMemberOption.member_display_name })}
                                </button>
                              </form>
                            ) : (
                              <small className="muted">{t("client.makeup_cancel_blocked")}</small>
                            )}
                            {(selectedReservationMemberOption.booking_status || "").toUpperCase() === "BOOKED" ? (
                              <a className="mode-link client-session-calendar-link" href={`/client/bookings/${selectedReservationMemberOption.booking_id}/calendar`}>
                                {t("client.add_to_calendar_for", { member: selectedReservationMemberOption.member_display_name })}
                              </a>
                            ) : null}
                          </div>
                        ) : null}
                        {selectedReservationMemberOption && ["BOOK_WITH_CREDIT", "FINALIZE_PAYMENT", "JOIN_WAITLIST"].includes(selectedSessionEffectiveActionCode) ? (
                          <form action={submitPublicSessionCheckoutAction}>
                            <input type="hidden" name="session_id" value={selectedSession.id} />
                            <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                            <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                            <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                            <button
                              type="submit"
                              className={
                                ["PAY_UNIT", "FINALIZE_PAYMENT"].includes(selectedSessionEffectiveActionCode)
                                  ? "client-session-primary-button"
                                  : "client-session-secondary-button"
                              }
                            >
                              {selectedSessionPrimaryActionLabel || selectedReservationMemberOption.action_label}
                              {selectedSessionEffectiveActionCode !== "BOOK_WITH_CREDIT" && selectedSessionDirectPaymentAmount
                                ? ` · ${toMoney(
                                    selectedSessionDirectPaymentAmount,
                                    selectedSessionDirectPaymentCurrency,
                                   language)}`
                                : ""}
                            </button>
                          </form>
                        ) : null}
                        {selectedReservationMemberOption &&
                        selectedSessionEffectiveActionCode === "PAY_UNIT" &&
                        selectedSessionDirectPaymentAmount ? (
                          <form action={submitPublicSessionCheckoutAction}>
                            <input type="hidden" name="session_id" value={selectedSession.id} />
                            <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                            <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                            <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                            <button type="submit" className="client-session-primary-button">
                              {`${t("client.pay_unit")} · ${toMoney(
                                selectedSessionDirectPaymentAmount,
                                selectedSessionDirectPaymentCurrency,
                               language)}`}
                            </button>
                          </form>
                        ) : null}
                        {selectedReservationMemberOption && selectedSessionEffectiveActionCode === "UNAVAILABLE" ? (
                          <div className="stack-sm">
                            <span className="badge">
                              {reservationOptionReasonLabel(selectedReservationMemberOption) || t("client.unavailable_slot")}
                            </span>
                          </div>
                        ) : null}
                        {selectedSessionRequiresMemberChoice ? (
                          <div className="stack-sm">
                            <span className="badge">{t("client.choose_member_first")}</span>
                          </div>
                        ) : null}
                        {!selectedReservationMemberOption && !selectedSessionRequiresMemberChoice ? (
                          <div className="stack-sm">
                            <span className="badge">
                              {selectedSessionPlanningState?.contextLine || t("client.unavailable_slot")}
                            </span>
                            {!selectedSessionPlanningState?.hasDirectPayment &&
                            selectedSessionPlanningState?.statusCode === "NO_PLAN" ? (
                              <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                                {t("client.view_compatible_offers")}
                              </a>
                            ) : null}
                          </div>
                        ) : null}
                        {selectedReservationMemberOption &&
                        ["BUY_FORMULA", "BUY_FORMULA_OR_PAY_UNIT"].includes(selectedSessionEffectiveActionCode) ? (
                          <div className="client-session-inline-note">
                            <small className="muted">
                              {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                                ? t("client.unit_or_plan_note")
                                : t("client.select_plan_then_confirm")}
                            </small>
                          </div>
                        ) : null}
                      </div>
                    </footer>
                  </article>
                </section>
              ) : null}

            </>
          ) : null}

          {tab === "courses" ? (
            <>
              <Card className="client-content-shell">
                <div className="row spread client-content-heading">
                  <div>
                    <h2>{t("client.online_courses_title")}</h2>
                    <p className="muted">{t("client.online_courses_help")}</p>
                  </div>
                  <span className="badge">{t("client.course_count", { count: filteredContentCourses.length })}</span>
                </div>
                <form method="get" className="client-content-filter-form">
                  <input type="hidden" name="tab" value="courses" />
                  {hasMultipleVisibleMembers ? (
                    <label className="client-content-member-filter">
                      <span>{t("client.show_for")}</span>
                      <AutoSubmitSelect
                        name="content_member_id"
                        defaultValue={contentMemberFilter}
                        options={[
                          { value: "ALL", label: t("client.whole_family") },
                          ...members.map((member) => ({ value: member.id, label: member.display_name })),
                        ]}
                      />
                    </label>
                  ) : null}
                </form>
              </Card>

              <div className="client-content-layout">
                <SectionCard
                  title={t("client.accessible_courses")}
                  className="client-content-course-list-card"
                  action={selectedContentCourse ? <span className="badge">{courseAudienceLabel(selectedContentCourse, language)}</span> : undefined}
                >
                  {filteredContentCourses.length === 0 ? (
                    <div className="client-content-empty-state">
                      <strong>{t("client.no_online_course")}</strong>
                      <p className="muted">{t("client.no_online_course_help")}</p>
                    </div>
                  ) : (
                    <div className="client-content-course-list">
                      {filteredContentCourses.map((course) => {
                        const totalLessons =
                          course.standalone_lessons.length +
                          course.sections.reduce((sum, section) => sum + section.lessons.length, 0);
                        return (
                          <a
                            key={course.id}
                            className={`client-content-course-card ${selectedContentCourse?.id === course.id ? "active" : ""}`}
                            href={withUpdatedQuery(rawParams, {
                              tab: "courses",
                              content_member_id: contentMemberFilter === "ALL" ? null : contentMemberFilter,
                              content_course_id: course.id,
                              content_lesson_id: null,
                            })}
                          >
                            <div className="client-content-course-card-top">
                              <div>
                                {course.level_code ? <span className="badge">{course.level_code}</span> : null}
                                <h3>{course.title}</h3>
                              </div>
                              <span className="badge">{t("client.lesson_count", { count: totalLessons })}</span>
                            </div>
                            {course.summary ? <p>{course.summary}</p> : null}
                            <div className="client-content-course-card-meta">
                              <span>{courseAudienceLabel(course, language)}</span>
                              <span>
                                {course.member_accesses
                                  .flatMap((access) => access.course_type_names)
                                  .filter((value, index, array) => array.indexOf(value) === index)
                                  .join(" · ")}
                              </span>
                            </div>
                          </a>
                        );
                      })}
                    </div>
                  )}
                </SectionCard>

                <SectionCard
                  title={selectedContentCourse ? selectedContentCourse.title : t("client.select_course")}
                  className="client-content-course-detail-card"
                  action={selectedContentCourse?.level_code ? <span className="badge">{selectedContentCourse.level_code}</span> : undefined}
                >
                  {!selectedContentCourse ? (
                    <div className="client-content-empty-state">
                      <strong>{t("client.choose_course_to_view")}</strong>
                    </div>
                  ) : (
                    <>
                      <div className="client-content-course-hero">
                        <div className="client-content-course-hero-copy">
                          <FilterChipsBar className="client-content-access-chips">
                            {selectedContentCourse.member_accesses.map((access) => (
                              <span key={`course-member-${access.member_id}`} className="badge">
                                {access.member_display_name}
                              </span>
                            ))}
                          </FilterChipsBar>
                          {selectedContentCourse.summary ? (
                            <p className="client-content-course-summary">{selectedContentCourse.summary}</p>
                          ) : null}
                          <p className="muted client-content-course-bridge">
                            {t("client.accessible_via", {
                              values: selectedContentCourse.member_accesses
                                .flatMap((access) => access.course_type_names)
                                .filter((value, index, array) => array.indexOf(value) === index)
                                .join(", "),
                            })}
                          </p>
                        </div>
                        {selectedContentCourse.cover_image_url ? (
                          <img
                            className="client-content-course-cover"
                            src={selectedContentCourse.cover_image_url}
                            alt={t("client.course_illustration", { title: selectedContentCourse.title })}
                          />
                        ) : null}
                      </div>

                      <div className="client-content-detail-grid">
                        <aside className="client-content-outline">
                          {selectedContentCourse.sections.map((section) => (
                            <section key={`section-${section.id}`} className="client-content-outline-section">
                              <header>
                                <span className="badge">{section.lessons.length}</span>
                                <h3>{section.title}</h3>
                              </header>
                              <div className="client-content-outline-lessons">
                                {section.lessons.map((lesson) => (
                                  <a
                                    key={`lesson-${lesson.id}`}
                                    className={`client-content-lesson-link ${selectedContentLesson?.lesson.id === lesson.id ? "active" : ""}`}
                                    href={withUpdatedQuery(rawParams, {
                                      tab: "courses",
                                      content_member_id: contentMemberFilter === "ALL" ? null : contentMemberFilter,
                                      content_course_id: selectedContentCourse.id,
                                      content_lesson_id: lesson.id,
                                    })}
                                  >
                                    <strong>{lesson.title}</strong>
                                    {lesson.summary ? <span>{lesson.summary}</span> : null}
                                  </a>
                                ))}
                              </div>
                            </section>
                          ))}

                          {selectedContentCourse.standalone_lessons.length > 0 ? (
                            <section className="client-content-outline-section">
                              <header>
                                <span className="badge">{selectedContentCourse.standalone_lessons.length}</span>
                                <h3>{t("client.lessons")}</h3>
                              </header>
                              <div className="client-content-outline-lessons">
                                {selectedContentCourse.standalone_lessons.map((lesson) => (
                                  <a
                                    key={`standalone-${lesson.id}`}
                                    className={`client-content-lesson-link ${selectedContentLesson?.lesson.id === lesson.id ? "active" : ""}`}
                                    href={withUpdatedQuery(rawParams, {
                                      tab: "courses",
                                      content_member_id: contentMemberFilter === "ALL" ? null : contentMemberFilter,
                                      content_course_id: selectedContentCourse.id,
                                      content_lesson_id: lesson.id,
                                    })}
                                  >
                                    <strong>{lesson.title}</strong>
                                    {lesson.summary ? <span>{lesson.summary}</span> : null}
                                  </a>
                                ))}
                              </div>
                            </section>
                          ) : null}
                        </aside>

                        <article className="client-content-lesson-panel">
                          {selectedContentLesson ? (
                            <>
                              <header className="client-content-lesson-header">
                                {selectedContentLesson.sectionTitle ? (
                                  <span className="badge">{selectedContentLesson.sectionTitle}</span>
                                ) : null}
                                <h3>{selectedContentLesson.lesson.title}</h3>
                                {selectedContentLesson.lesson.summary ? (
                                  <p className="muted">{selectedContentLesson.lesson.summary}</p>
                                ) : null}
                              </header>

                              <div className="client-content-lesson-actions">
                                {selectedContentLesson.lesson.video_url ? (
                                  <a className="mode-link" href={selectedContentLesson.lesson.video_url} target="_blank" rel="noreferrer">
                                    {t("client.open_video")}
                                  </a>
                                ) : null}
                                {selectedContentLesson.lesson.resource_url ? (
                                  <a className="mode-link" href={selectedContentLesson.lesson.resource_url} target="_blank" rel="noreferrer">
                                    {t("client.attached_resource")}
                                  </a>
                                ) : null}
                              </div>

                              {selectedContentLesson.lesson.content_html ? (
                                <div
                                  className="client-content-lesson-body"
                                  dangerouslySetInnerHTML={{ __html: selectedContentLesson.lesson.content_html }}
                                />
                              ) : (
                                <div className="client-content-empty-state">
                                  <strong>{t("client.lesson_content_unavailable")}</strong>
                                  <p className="muted">{t("client.lesson_content_pending_help")}</p>
                                </div>
                              )}
                            </>
                          ) : (
                            <div className="client-content-empty-state">
                              <strong>{t("client.no_published_lesson")}</strong>
                            </div>
                          )}
                        </article>
                      </div>
                    </>
                  )}
                </SectionCard>
              </div>
            </>
          ) : null}

          {tab === "reservations" ? (
            <Card>
              <div className="row spread">
                <h2>{t("client.my_bookings")}</h2>
                <span className="badge">{reservationRows.length}</span>
              </div>

              {makeupSummaries.length > 0 ? (
                <section className="client-makeup-summary" aria-label={t("client.makeup_pass_title")}>
                  <div className="row spread">
                    <div>
                      <strong>{t("client.makeup_pass_title")}</strong>
                      <p className="muted">{t("client.makeup_pass_help")}</p>
                    </div>
                  </div>
                  <div className="client-makeup-summary-grid">
                    {makeupSummaries.map((summary) => (
                      <article className="item" key={summary.user_id}>
                        <div className="row spread">
                          <strong>{summary.display_name}</strong>
                          <span className="badge">
                            {t("client.makeup_pass_remaining", {
                              remaining: summary.credits_remaining,
                              initial: summary.credits_initial,
                            })}
                          </span>
                        </div>
                        <p className="muted">
                          {t("client.makeup_pending_count", { count: summary.pending_makeups.length })}
                        </p>
                        {summary.pending_makeups.map((credit) => (
                          <p className="muted" key={credit.id}>
                            {t("client.makeup_pending_from", {
                              course: credit.original_session_title,
                              date: formatDateTimeInTimezone(credit.original_session_start_at_utc, timezone, language),
                            })}
                          </p>
                        ))}
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <form method="get" className="client-filter-grid client-reservation-filters">
                <input type="hidden" name="tab" value="reservations" />
                <label>
                  {t("client.scope")}
                  <select name="reservation_scope" defaultValue={reservationScope}>
                    <option value="CURRENT">{t("client.current")}</option>
                    <option value="HISTORY">{t("client.history")}</option>
                    <option value="ALL">{t("common.all")}</option>
                  </select>
                </label>
                <label>
                  {t("common.member")}
                  <select name="member_id" defaultValue={selectedMemberFilter}>
                    <option value="ALL">{hasMultipleVisibleMembers ? t("client.all_members") : t("client.account_self")}</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <DrawerFilters title={t("client.advanced_filters_reservations")} className="client-reservation-drawer">
                  <label>
                    {t("common.status")}
                    <select name="reservation_status" defaultValue={reservationStatusFilter}>
                      <option value="">{t("common.all")}</option>
                      {allBookingStatuses.map((status) => (
                        <option key={status} value={status}>
                          {statusLabel(status, language)}
                        </option>
                      ))}
                    </select>
                  </label>
                </DrawerFilters>
                <div className="row">
                  <button type="submit">🔎</button>
                  <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "reservations", reservation_scope: "CURRENT", member_id: null, reservation_status: null })}>
                    ↺
                  </a>
                </div>
              </form>

              {reservationRows.length === 0 ? (
                <p className="muted">{t("client.no_reservation_filter")}</p>
              ) : (
                <>
                <div className="table-wrap client-desktop-table">
                  <table className="data-table client-data-table">
                    <thead>
                      <tr>
                        <th>{t("common.member")}</th>
                        <th>{t("common.course")}</th>
                        <th>{t("common.start")}</th>
                        <th>{t("common.amount")}</th>
                        <th>{t("common.status")}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {reservationRows.map((booking) => {
                        const normalizedBookingStatus = normalizeStatus(booking.status);
                        const makeupSummary = makeupSummaryByMemberId.get(booking.owner_client_id);
                        const canCancel = normalizedBookingStatus === "WAITLISTED"
                          || (
                            normalizedBookingStatus === "BOOKED"
                            && (!makeupSummary?.has_active_restricted_forfait || makeupSummary.credits_remaining > 0)
                          );
                        return (
                          <tr key={booking.id}>
                            <td>{booking.owner_display_name}</td>
                            <td>{booking.session.title}</td>
                            <td>{formatDateTimeInTimezone(booking.session.start_at_utc, timezone, language)}</td>
                            <td>{toMoney(booking.total_incl_vat_snapshot, booking.currency_snapshot, language)}</td>
                            <td>
                              <span className={`status-pill ${statusClass(booking.status)}`}>{statusLabel(booking.status, language)}</span>
                            </td>
                            <td>
                              {canCancel ? (
                                <form action={cancelBookingAction}>
                                  <input type="hidden" name="booking_id" value={booking.id} />
                                  <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "reservations" })} />
                                  <button className="danger" type="submit" title={t("common.cancel")}>
                                    🗑️
                                  </button>
                                </form>
                              ) : normalizedBookingStatus === "BOOKED" && makeupSummary?.has_active_restricted_forfait ? (
                                <small className="muted">{t("client.makeup_cancel_blocked")}</small>
                              ) : (
                                <span className="muted">-</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="list client-mobile-list">
                  {reservationRows.map((booking) => {
                    const normalizedBookingStatus = normalizeStatus(booking.status);
                    const makeupSummary = makeupSummaryByMemberId.get(booking.owner_client_id);
                    const canCancel = normalizedBookingStatus === "WAITLISTED"
                      || (
                        normalizedBookingStatus === "BOOKED"
                        && (!makeupSummary?.has_active_restricted_forfait || makeupSummary.credits_remaining > 0)
                      );
                    return (
                      <article key={`${booking.id}-mobile`} className="item client-mobile-card">
                        <div className="row spread">
                          <strong>{booking.owner_display_name}</strong>
                          <span className={`status-pill ${statusClass(booking.status)}`}>{statusLabel(booking.status, language)}</span>
                        </div>
                        <p className="muted">{booking.session.title}</p>
                        <p className="muted">{formatDateTimeInTimezone(booking.session.start_at_utc, timezone, language)}</p>
                        <div className="row spread">
                          <strong>{toMoney(booking.total_incl_vat_snapshot, booking.currency_snapshot, language)}</strong>
                          {canCancel ? (
                            <form action={cancelBookingAction}>
                              <input type="hidden" name="booking_id" value={booking.id} />
                              <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "reservations" })} />
                              <button className="ghost" type="submit">{t("common.cancel")}</button>
                            </form>
                          ) : normalizedBookingStatus === "BOOKED" && makeupSummary?.has_active_restricted_forfait ? (
                            <small className="muted">{t("client.makeup_cancel_blocked")}</small>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
                </>
              )}
            </Card>
          ) : null}

          {tab === "offers" ? (
            <>
              <Card className="client-offers-header">
                <div className="row spread">
                  <h2>{t("client.offers_page_title")}</h2>
                  <span className="badge">{t("client.offers_available_count", { count: onlinePurchaseCount })}</span>
                </div>
                <p className="muted">{t("client.offers_help")}</p>
                <div className="client-offers-summary">
                  <a className="client-offers-summary-tile" href="#client-owned-purchases">
                    <strong>{visibleOfferSubscriptions.length}</strong>
                    <span>{t("client.active_subscriptions_and_packs")}</span>
                  </a>
                  <a className="client-offers-summary-tile" href="#client-offer-catalog">
                    <strong>{onlinePurchaseCount}</strong>
                    <span>{t("client.offer_catalog")}</span>
                  </a>
                </div>
              </Card>

              {confirmExistingPackPurchase && confirmPlan ? (
                <Card className="client-offers-confirm-card">
                  <section className="flash-warn client-offers-confirm-alert">
                    <strong>{t("client.pre_purchase_check")}</strong>
                    <span>{warningMessage || t("client.pre_purchase_default_warning")}</span>
                  </section>
                  <div className="client-offers-confirm-head">
                    <div>
                      <p className="client-offers-confirm-kicker">{t("client.purchase_confirmation")}</p>
                      <h3>{t("client.final_check_before_payment")}</h3>
                      <p className="muted">
                        {t("client.adding_new_plan_to_account", { beneficiary: selectedPurchaseOwnerProfile?.display_name || t("client.this_beneficiary") })}
                      </p>
                    </div>
                    <div className="client-offers-confirm-price">
                      {toMoney(planDisplayPrice(confirmPlan), confirmPlan.currency_code ?? me.preferred_currency, language)}
                    </div>
                  </div>
                  <div className="client-offers-confirm-summary">
                    <article className="item">
                      <h4>{t("client.beneficiary")}</h4>
                      <p>{selectedPurchaseOwnerProfile?.display_name || t("client.beneficiary")}</p>
                    </article>
                    <article className="item">
                      <h4>{t("client.selected_offer")}</h4>
                      <p>{confirmPlan.name}</p>
                    </article>
                    <article className="item">
                      <h4>{t("common.type")}</h4>
                      <p>{confirmPlan.kind === "PACK" ? t("client.pack_sessions") : confirmPlan.kind === "FORFAIT" ? t("client.plan_fixed") : t("client.subscription")}</p>
                    </article>
                    <article className="item">
                      <h4>{t("common.payment")}</h4>
                      <p>{Number(planDisplayPrice(confirmPlan) ?? "0") > 0 ? t("client.secure_online_payment") : t("client.no_payment_required")}</p>
                    </article>
                  </div>
                  <div className="client-offers-confirm-note">
                    <strong>{t("client.next_steps_after_purchase")}</strong>
                    <p>{Number(planDisplayPrice(confirmPlan) ?? "0") > 0 ? t("client.redirect_to_secure_payment") : t("client.immediate_plan_addition")}</p>
                  </div>
                  <div className="client-offers-confirm-actions">
                    <form action={purchasePlanAction}>
                      <input type="hidden" name="plan_id" value={confirmPlan.id} />
                      <input type="hidden" name="purchase_user_id" value={selectedPurchaseOwner} />
                      <input type="hidden" name="start_date" value={selectedPurchaseStartDate} />
                      <input type="hidden" name="confirm_existing_pack_purchase" value="1" />
                      <button type="submit">
                        {Number(planDisplayPrice(confirmPlan) ?? "0") > 0 ? t("client.confirm_and_pay_online") : t("client.confirm_purchase")}
                      </button>
                    </form>
                    <a
                      className="ghost"
                      href={withUpdatedQuery(rawParams, {
                        tab: "offers",
                        warning: null,
                        warning_code: null,
                        confirm_existing_pack_purchase: null,
                        confirm_plan_id: null,
                        error: null,
                        error_code: null,
                      })}
                    >
                      {t("common.cancel")}
                    </a>
                  </div>
                </Card>
              ) : null}

              <section id="client-owned-purchases">
                <Card>
                  <div className="row spread">
                    <h3>{t("client.active_subscriptions_and_packs")}</h3>
                    <span className="badge">{visibleOfferSubscriptions.length}</span>
                  </div>
                  {visibleOfferSubscriptions.length === 0 ? (
                    <p className="muted">{t("client.no_active_subscription_preview")}</p>
                  ) : (
                    <div className="list client-forfait-card-list">
                      {visibleOfferSubscriptions.map((sub) => {
                        const isPack = normalizeStatus(sub.plan.kind) === "PACK";
                        const initialCredits = sub.credits_initial ?? 0;
                        const remainingCredits = sub.credits_remaining ?? 0;
                        const consumedCredits = Math.max(0, initialCredits - remainingCredits);
                        const ratio = initialCredits > 0 ? Math.min(100, Math.round((consumedCredits / initialCredits) * 100)) : 0;
                        const linkedPlan = plans.find((plan) => plan.id === sub.plan.id);
                        const planPrice = planDisplayPrice(linkedPlan) ?? sub.plan.price_ttc;
                        const planCurrency = linkedPlan?.currency_code ?? sub.plan.currency_code ?? me.preferred_currency;
                        const offerBookings = allBookings.filter(
                          (booking) => booking.client_plan_subscription_id === sub.id && normalizeStatus(booking.status) !== "CANCELLED",
                        );
                        const activityCount = new Set(offerBookings.map((booking) => booking.session.title)).size;
                        return (
                          <article key={`forfait-card-${sub.id}`} className="item client-forfait-card">
                            <div className="row spread">
                              <div>
                                <strong>{sub.plan.name}</strong>
                                <p className="muted">{sub.owner_display_name}</p>
                              </div>
                              <span className="badge">{planKindLabel(sub.plan.kind, language)}</span>
                            </div>
                            {activityCount > 0 ? (
                              <p className="client-offer-program-preview">
                                {t("client.offer_program_summary", { activities: activityCount, sessions: offerBookings.length })}
                              </p>
                            ) : null}
                            {sub.offer_deposit_amount_ttc && normalizeStatus(sub.offer_deposit_status || "") === "PAID" ? (
                              <p className="client-offer-deposit-preview">
                                <span aria-hidden="true">✓</span>
                                {t("client.deposit_paid_amount", {
                                  amount: toMoney(sub.offer_deposit_amount_ttc, sub.offer_currency || planCurrency, language),
                                })}
                              </p>
                            ) : null}
                            <div className="row spread">
                              <span className={`status-pill ${statusClass(sub.status)}`}>{statusLabel(sub.status, language)}</span>
                              <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })}>
                                {t("client.view_details")}
                              </a>
                            </div>
                            {isPack ? (
                              <>
                                <div className="client-progress">
                                  <div className="client-progress-bar" style={{ width: `${ratio}%` }} />
                                </div>
                                <p className="muted">{t("client.remaining_credits", { remaining: remainingCredits, initial: initialCredits || "?" })}</p>
                              </>
                            ) : (
                              <p className="muted">
                                {sub.offer_total_ttc
                                  ? t("client.offer_total_amount", { amount: toMoney(sub.offer_total_ttc, sub.offer_currency || planCurrency, language) })
                                  : `${toMoney(sub.plan.kind === "FORFAIT" ? "0" : planPrice, planCurrency, language)} ${t("client.per_month_suffix")}`} · {paymentMethodLabel(sub.billing_method_code, language)}
                              </p>
                            )}
                            <p className="muted">
                              {sub.ends_at ? t("client.expiration", { date: formatDate(sub.ends_at, language) }) : sub.next_payment_at ? t("client.next_debit", { date: formatDate(sub.next_payment_at, language) }) : t("client.renewal_in_progress")}
                            </p>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </Card>
              </section>

              {selectedOfferSubscription ? (
                <Card className="client-offer-detail">
                  <header className="client-offer-detail-hero">
                    <div>
                      <p className="client-offer-detail-kicker">{t("client.your_enrollment")}</p>
                      <h2>{selectedOfferSubscription.offer_school_year_label || selectedOfferSubscription.plan.name}</h2>
                      <p>{selectedOfferSubscription.owner_display_name} · {selectedOfferSubscription.plan.name}</p>
                    </div>
                    <div className="client-offer-detail-hero-actions">
                      <span className={`status-pill ${statusClass(selectedOfferSubscription.status)}`}>{statusLabel(selectedOfferSubscription.status, language)}</span>
                      <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: null })}>
                        {t("common.close")}
                      </a>
                    </div>
                  </header>

                  <section className="client-offer-detail-section">
                    <div className="client-offer-section-heading">
                      <div>
                        <p className="client-offer-section-kicker">{t("client.your_program")}</p>
                        <h3>{t("client.scheduled_activities")}</h3>
                      </div>
                      <span className="badge">{t("client.offer_program_summary", { activities: selectedOfferActivityGroups.length, sessions: selectedOfferBookings.length })}</span>
                    </div>
                    {selectedOfferActivityGroups.length === 0 ? (
                      <p className="muted">{t("client.no_scheduled_activity")}</p>
                    ) : (
                      <div className="client-offer-activity-grid">
                        {selectedOfferActivityGroups.map((activity) => (
                          <article key={`${activity.title}-${activity.startAt}`} className="client-offer-activity-card">
                            <h4>{activity.title}</h4>
                            <dl>
                              <div>
                                <dt>{t("client.schedule")}</dt>
                                <dd>{new Intl.DateTimeFormat(localeForUiLanguage(language), { timeZone: timezone, weekday: "long", hour: "2-digit", minute: "2-digit" }).format(new Date(activity.startAt))} – {formatTimeInTimezone(activity.endAt, timezone, language)}</dd>
                              </div>
                              <div>
                                <dt>{t("common.period")}</dt>
                                <dd>{formatDateInTimezone(activity.firstAt, timezone, language)} – {formatDateInTimezone(activity.lastAt, timezone, language)}</dd>
                              </div>
                              <div>
                                <dt>{t("client.location")}</dt>
                                <dd>{activity.locationName || t("client.location_not_specified")}</dd>
                              </div>
                              <div>
                                <dt>{t("client.sessions")}</dt>
                                <dd>{activity.count}</dd>
                              </div>
                            </dl>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className="client-offer-detail-section">
                    <div className="client-offer-section-heading">
                      <div>
                        <p className="client-offer-section-kicker">{t("client.included_with_offer")}</p>
                        <h3>{t("client.selected_options")}</h3>
                      </div>
                    </div>
                    {(selectedOfferSubscription.offer_options ?? []).length === 0 ? (
                      <p className="muted">{t("client.no_selected_option")}</p>
                    ) : (
                      <div className="client-offer-option-list">
                        {(selectedOfferSubscription.offer_options ?? []).map((option) => (
                          <article key={option.id} className="client-offer-option-card">
                            <span className="client-offer-option-check" aria-hidden="true">✓</span>
                            <div>
                              <h4>{option.title}</h4>
                              {option.description ? <p className="muted">{option.description}</p> : null}
                            </div>
                            {Number(option.amount_ttc) > 0 ? <strong>{toMoney(option.amount_ttc, selectedOfferSubscription.offer_currency || me.preferred_currency, language)}</strong> : null}
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className="client-offer-detail-section client-offer-finance-section">
                    <div className="client-offer-section-heading">
                      <div>
                        <p className="client-offer-section-kicker">{t("client.payment_tracking")}</p>
                        <h3>{t("client.your_financing")}</h3>
                      </div>
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", member_id: selectedOfferSubscription.owner_client_id })}>{t("client.open_finance")}</a>
                    </div>
                    <div className="client-offer-finance-grid">
                      <div>
                        <span>{t("client.offer_total")}</span>
                        <strong>{selectedOfferSubscription.offer_total_ttc ? toMoney(selectedOfferSubscription.offer_total_ttc, selectedOfferSubscription.offer_currency || me.preferred_currency, language) : "—"}</strong>
                      </div>
                      <div className={normalizeStatus(selectedOfferSubscription.offer_deposit_status || "") === "PAID" ? "is-paid" : ""}>
                        <span>{t("client.deposit")}</span>
                        <strong>{selectedOfferSubscription.offer_deposit_amount_ttc ? toMoney(selectedOfferSubscription.offer_deposit_amount_ttc, selectedOfferSubscription.offer_currency || me.preferred_currency, language) : "—"}</strong>
                        {normalizeStatus(selectedOfferSubscription.offer_deposit_status || "") === "PAID" ? <small>✓ {t("client.paid")}</small> : null}
                      </div>
                      <div>
                        <span>{t("client.remaining_amount")}</span>
                        <strong>{selectedOfferSubscription.offer_remaining_ttc ? toMoney(selectedOfferSubscription.offer_remaining_ttc, selectedOfferSubscription.offer_currency || me.preferred_currency, language) : "—"}</strong>
                      </div>
                    </div>
                    {selectedOfferInvoices.length > 0 ? (
                      <div className="client-offer-invoices">
                        {selectedOfferInvoices.map((invoice) => (
                          <a key={invoice.id} href={clientInvoiceHref(invoice.id, { inline: true })} target="_blank" rel="noreferrer">
                            <span>{invoice.invoice_kind === "DEPOSIT" ? t("client.deposit_invoice") : t("client.finance_source_invoice")} · {invoice.invoice_number}</span>
                            <strong>{toMoney(invoice.total_incl_vat, invoice.currency, language)}</strong>
                          </a>
                        ))}
                      </div>
                    ) : null}
                  </section>

                  <details className="client-offer-technical">
                    <summary>{t("client.technical_information")}</summary>
                    <div>
                      <p>{t("client.contract")}: {compactId(selectedOfferSubscription.id)} <CopyIdButton value={selectedOfferSubscription.id} label={t("common.copy")} /></p>
                      {selectedOfferSubscription.offer_quote_number ? <p>{t("client.quote")}: {selectedOfferSubscription.offer_quote_number}</p> : null}
                      <p>{t("client.payment_method")}: {paymentMethodLabel(selectedOfferSubscription.billing_method_code, language)}</p>
                    </div>
                  </details>
                </Card>
              ) : null}

              <section id="client-offer-catalog">
                <Card>
                  <div className="row spread">
                    <h3>{t("client.offer_catalog")}</h3>
                    <span className="badge">{t("client.offers_available_count", { count: onlinePurchaseCount })}</span>
                  </div>
                  <div className="client-purchase-toolbar">
                    <div>
                      <h3>{t("client.offers_purchase_title")}</h3>
                      <p className="muted">{t("client.offers_purchase_help")}</p>
                    </div>
                    <form method="get" className="row">
                      <input type="hidden" name="tab" value="offers" />
                      <input type="hidden" name="offer_category" value={selectedOfferCategory} />
                      <label>
                        {t("client.beneficiary")}
                        <select name="purchase_user_id" defaultValue={selectedPurchaseOwner}>
                          {members.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("client.start_date_input")}
                        <input type="date" name="purchase_start_date" defaultValue={selectedPurchaseStartDate} />
                      </label>
                      <button type="submit">{t("client.show_offers")}</button>
                    </form>
                  </div>

                  <section className="client-catalog-section client-catalog-browser">
                    <div className="client-catalog-filter-heading">
                      <div>
                        <p className="client-offer-section-kicker">{t("client.offer_catalog_categories")}</p>
                        <h4>{t("client.filter_offers_by_category")}</h4>
                      </div>
                      <span className="client-catalog-total">{t("client.catalog_result_count", { count: filteredOnlinePurchaseCount })}</span>
                    </div>

                    <nav className="client-offer-category-filter" aria-label={t("client.filter_offers_by_category")}>
                      <a
                        className={selectedOfferCategory === "ALL" ? "is-active" : ""}
                        href={withUpdatedQuery(rawParams, { offer_category: "ALL", offer_detail_id: null })}
                        aria-current={selectedOfferCategory === "ALL" ? "page" : undefined}
                      >
                        <span className="client-offer-category-icon" aria-hidden="true">⌂</span>
                        <span>{t("client.offer_category_all")}</span>
                        <strong>{onlinePurchaseCount}</strong>
                      </a>
                      {visibleOfferCategories.map((category) => (
                        <a
                          key={category.key}
                          className={selectedOfferCategory === category.key ? "is-active" : ""}
                          href={withUpdatedQuery(rawParams, { offer_category: category.key, offer_detail_id: null })}
                          aria-current={selectedOfferCategory === category.key ? "page" : undefined}
                        >
                          <span className="client-offer-category-icon" aria-hidden="true">{category.icon}</span>
                          <span>{t(category.labelKey)}</span>
                          <strong>{offerCategoryCounts.get(category.key) ?? 0}</strong>
                        </a>
                      ))}
                    </nav>

                    <div className="client-catalog-results-head">
                      <h4>
                        {selectedOfferCategory === "ALL"
                          ? t("client.offer_category_all")
                          : t(OFFER_CATALOG_CATEGORIES.find((category) => category.key === selectedOfferCategory)?.labelKey ?? "client.offer_category_other")}
                      </h4>
                      <p>{t("client.catalog_mixed_help")}</p>
                    </div>

                    <div className="client-offer-catalog-grid">
                      {filteredPlans.map((plan) => {
                        const categories = planOfferCategories(plan);
                        const primaryCategory = OFFER_CATALOG_CATEGORIES.find((category) => category.key === categories[0]) ?? OFFER_CATALOG_CATEGORIES[7];
                        const recurringPaymentMethods = (plan.payment_methods ?? []).filter(
                          (method) => method === "CARD_ONLINE" || method === "SEPA_DEBIT",
                        );
                        const price = planDisplayPrice(plan);
                        const planTypeLabel = plan.kind === "PACK"
                          ? t("client.pack_sessions")
                          : plan.kind === "FORFAIT"
                            ? t("client.plan_fixed")
                            : t("client.subscription");
                        return (
                          <article key={plan.id} className="client-catalog-offer-card">
                            <div className="client-catalog-offer-topline">
                              <span className="client-catalog-category-badge">
                                <span aria-hidden="true">{primaryCategory.icon}</span>
                                {t(primaryCategory.labelKey)}
                              </span>
                              <span className="client-catalog-kind">{t("client.catalog_formula")}</span>
                            </div>
                            <div className="client-catalog-offer-content">
                              <h3>{plan.name}</h3>
                              <p className="client-catalog-offer-description">
                                {plan.description || (plan.entitlement_course_type_names ?? []).join(" · ") || planTypeLabel}
                              </p>
                              <div className="client-catalog-offer-meta">
                                <span>{planTypeLabel}</span>
                                {plan.kind === "PACK" && plan.credits_count != null ? (
                                  <span>{t("client.catalog_sessions_included", { count: plan.credits_count })}</span>
                                ) : null}
                                {plan.kind === "FORFAIT" ? <span>{t("client.catalog_schedule_billing")}</span> : null}
                              </div>
                            </div>
                            <div className="client-catalog-offer-footer">
                              <div className="client-catalog-price">
                                <span>{t("client.price")}</span>
                                <strong>{price != null ? toMoney(price, plan.currency_code ?? me.preferred_currency, language) : "—"}</strong>
                                {plan.kind === "SUBSCRIPTION" ? <small>{t("client.per_month_suffix")}</small> : null}
                              </div>
                              <form action={purchasePlanAction} className="client-catalog-purchase-form">
                                <input type="hidden" name="plan_id" value={plan.id} />
                                <input type="hidden" name="purchase_user_id" value={selectedPurchaseOwner} />
                                <input type="hidden" name="start_date" value={selectedPurchaseStartDate} />
                                {plan.kind === "SUBSCRIPTION" && recurringPaymentMethods.length > 1 ? (
                                  <label>
                                    <span>{t("client.catalog_renewal_method")}</span>
                                    <select name="billing_method_code" defaultValue="CARD_ONLINE">
                                      {recurringPaymentMethods.map((method) => (
                                        <option key={method} value={method}>{paymentMethodLabel(method, language)}</option>
                                      ))}
                                    </select>
                                    <small>{t("client.sepa_first_card_notice")}</small>
                                  </label>
                                ) : plan.kind === "SUBSCRIPTION" && recurringPaymentMethods.length === 1 ? (
                                  <input type="hidden" name="billing_method_code" value={recurringPaymentMethods[0]} />
                                ) : null}
                                <button type="submit" title={t("client.subscribe_offer_title")}>{t("common.choose")}</button>
                              </form>
                            </div>
                          </article>
                        );
                      })}

                      {filteredOnlineProducts.map((product) => {
                        const categories = productOfferCategories(product);
                        const primaryCategory = OFFER_CATALOG_CATEGORIES.find((category) => category.key === categories[0]) ?? OFFER_CATALOG_CATEGORIES[7];
                        return (
                          <article key={product.id} className="client-catalog-offer-card client-catalog-product-card">
                            <div className="client-catalog-offer-topline">
                              <span className="client-catalog-category-badge">
                                <span aria-hidden="true">{primaryCategory.icon}</span>
                                {t(primaryCategory.labelKey)}
                              </span>
                              <span className="client-catalog-kind">{t("client.catalog_product")}</span>
                            </div>
                            <div className="client-catalog-offer-content">
                              <h3>{product.title}</h3>
                              <p className="client-catalog-offer-description">
                                {product.short_description || product.category_name || t("client.product")}
                              </p>
                              <div className="client-catalog-offer-meta">
                                {product.category_name ? <span>{product.category_name}</span> : null}
                                {product.primary_location_name ? <span>{product.primary_location_name}</span> : null}
                                <span>{t("client.online_product")}</span>
                              </div>
                            </div>
                            <div className="client-catalog-offer-footer">
                              <div className="client-catalog-price">
                                <span>{t("client.price")}</span>
                                <strong>{toMoney(product.price_incl_vat, me.preferred_currency, language)}</strong>
                              </div>
                              {product.web_link ? (
                                <a className="client-catalog-product-link" href={product.web_link} target="_blank" rel="noreferrer">
                                  {t("client.open_product_link")}
                                </a>
                              ) : (
                                <span className="client-catalog-unavailable">{t("client.online_product")}</span>
                              )}
                            </div>
                          </article>
                        );
                      })}

                      {filteredOnlinePurchaseCount === 0 ? (
                        <div className="client-catalog-empty">
                          <span aria-hidden="true">⌕</span>
                          <h4>{t("client.no_offer_in_category")}</h4>
                          <a href={withUpdatedQuery(rawParams, { offer_category: "ALL" })}>{t("client.view_all_offers")}</a>
                        </div>
                      ) : null}
                    </div>
                  </section>
                </Card>
              </section>
            </>
          ) : null}

          {tab === "finance" ? (
            <>
              <SectionCard
                title={t("client.finance")}
                className="client-finance-shell"
                action={
                  financeDueTotal > 0 ? (
                    primaryDuePayableRow || primaryDuePaymentUrl ? (
                      <form action={openClientPaymentCheckoutAction}>
                        {primaryDuePayableRow ? <input type="hidden" name="payment_id" value={primaryDuePayableRow.id} /> : null}
                        {primaryDuePaymentUrl ? <input type="hidden" name="payment_url" value={primaryDuePaymentUrl} /> : null}
                        <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })} />
                        <button type="submit" className="client-pay-cta">
                          {t("common.pay")} {toMoney(String(financeDueTotal), me.preferred_currency, language)}
                        </button>
                      </form>
                    ) : (
                      <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                        {t("common.pay")} {toMoney(String(financeDueTotal), me.preferred_currency, language)}
                      </a>
                    )
                  ) : null
                }
              >
                <section className="client-kpi-grid">
                  <KPIBlock label={t("client.amount_due")} value={toMoney(String(financeDueTotal), me.preferred_currency, language)} helper={t("client.pending_invoices")} />
                  <KPIBlock label={t("client.paid_total")} value={toMoney(String(paidTotal), me.preferred_currency, language)} helper={t("client.confirmed_payments")} />
                  <KPIBlock
                    label={t("client.pending_transactions")}
                    value={toMoney(String(pendingTransactionsTotal), me.preferred_currency, language)}
                    helper={t("client.unsettled_movements")}
                  />
                </section>
                {paidOfferDeposits.length > 0 ? (
                  <section className="client-finance-deposits" aria-label={t("client.paid_deposits")}>
                    <div className="client-finance-deposits-heading">
                      <div>
                        <p className="client-offer-section-kicker">{t("client.payments_received")}</p>
                        <h3>{t("client.paid_deposits")}</h3>
                      </div>
                      <span className="status-pill success">✓ {t("client.paid")}</span>
                    </div>
                    {paidOfferDeposits.map((sub) => (
                      <article key={`finance-deposit-${sub.id}`}>
                        <div>
                          <strong>{t("client.deposit_for", { name: sub.owner_display_name })}</strong>
                          <p>{sub.offer_quote_number ? `${t("client.quote")} ${sub.offer_quote_number} · ` : ""}{sub.plan.name}</p>
                        </div>
                        <div className="client-finance-deposit-amount">
                          <strong>{toMoney(sub.offer_deposit_amount_ttc, sub.offer_currency || me.preferred_currency, language)}</strong>
                          {sub.offer_deposit_paid_at ? <small>{t("client.paid_on", { date: formatDate(sub.offer_deposit_paid_at, language) })}</small> : null}
                        </div>
                        <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })}>{t("client.view_offer")}</a>
                      </article>
                    ))}
                  </section>
                ) : null}
                <p className="muted">{t("client.accounts_as_of", { date: formatDate(financeAsOfDateKey, language) })}</p>

                <div className="client-finance-toolbar">
                  <div className="client-finance-tab-scroll">
                    <a
                      className={`mode-link ${financeView === "transactions" ? "active" : ""}`}
                      href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", invoice_id: null, finance_page: "1" })}
                    >
                      {t("common.transactions")}
                    </a>
                    <a
                      className={`mode-link ${financeView === "invoices" ? "active" : ""}`}
                      href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_page: "1" })}
                    >
                      {t("common.invoices")}
                    </a>
                  </div>

                  <DrawerFilters title={t("common.filters")} className="client-finance-drawer">
                    <form method="get" className="client-finance-drawer-form">
                      <input type="hidden" name="tab" value="finance" />
                      <input type="hidden" name="finance_view" value={financeView} />
                      <input type="hidden" name="invoice_id" value="" />
                      <input type="hidden" name="finance_page" value="1" />
                      <label>
                        {t("common.member")}
                        <select name="member_id" defaultValue={selectedMemberFilter}>
                          <option value="ALL">{hasMultipleVisibleMembers ? t("client.all_members") : t("client.account_self")}</option>
                          {members.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("common.status")}
                        <select name="finance_status" defaultValue={financeStatusFilter}>
                          {visibleFinanceStatusOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("common.period")}
                        <select name="finance_period" defaultValue={financePeriodFilter}>
                          <option value="ALL">{t("client.all_periods")}</option>
                          <option value="LAST_30_DAYS">{t("client.last_30_days")}</option>
                          <option value="LAST_90_DAYS">{t("client.last_90_days")}</option>
                          <option value="LAST_365_DAYS">{t("client.last_365_days")}</option>
                        </select>
                      </label>
                      <label>
                        {t("client.as_of_date")}
                        <input type="date" name="finance_as_of" defaultValue={financeAsOfDateKey} />
                      </label>
                      <label>
                        {t("client.lines_per_page")}
                        <select name="finance_page_size" defaultValue={String(financePageSize)}>
                          {FINANCE_PAGE_SIZES.map((size) => (
                            <option key={size} value={size}>
                              {size}
                            </option>
                          ))}
                        </select>
                      </label>
                      {financeView === "transactions" ? (
                        <label>
                          {t("common.type")}
                          <select name="finance_source" defaultValue={financeSourceFilter}>
                            <option value="ALL">{t("client.all_types")}</option>
                            {allPaymentSources.map((source) => (
                              <option key={source} value={source}>
                                {sourceLabel(source, language)}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <input type="hidden" name="finance_source" value={financeSourceFilter} />
                      )}
                      <div className="row client-finance-drawer-actions">
                        <button type="submit">{t("common.apply")}</button>
                        <a
                          className="reset-link"
                          href={withUpdatedQuery(rawParams, {
                            tab: "finance",
                            finance_view: financeView,
                            member_id: null,
                            finance_source: "ALL",
                            finance_status: "ALL",
                            finance_period: "ALL",
                            finance_as_of: todayKeyInTimezone(timezone),
                            finance_page: "1",
                            invoice_id: null,
                          })}
                        >
                          {t("common.reset")}
                        </a>
                      </div>
                    </form>
                  </DrawerFilters>
                </div>

                <FilterChipsBar className="client-finance-member-chips">
                  {hasMultipleVisibleMembers ? (
                    <>
                      <a
                        className={`badge ${selectedMemberFilter === "ALL" ? "active" : ""}`}
                        href={withUpdatedQuery(rawParams, { tab: "finance", member_id: "ALL", finance_page: "1", invoice_id: null })}
                      >
                        {t("common.all")}
                      </a>
                      {members.map((member) => (
                        <a
                          key={`finance-member-${member.id}`}
                          className={`badge ${selectedMemberFilter === member.id ? "active" : ""}`}
                          href={withUpdatedQuery(rawParams, { tab: "finance", member_id: member.id, finance_page: "1", invoice_id: null })}
                        >
                          {member.display_name}
                        </a>
                      ))}
                    </>
                  ) : (
                    <span className="badge active">{members[0]?.display_name ?? t("client.account_self")}</span>
                  )}
                  {financeStatusFilter !== "ALL" ? <span className="badge">{t("client.status_filter_badge", { status: visibleFinanceStatusOptions.find((item) => item.value === financeStatusFilter)?.label ?? financeStatusFilter })}</span> : null}
                  {financePeriodFilter !== "ALL" ? <span className="badge">{t("client.period_filter_badge", { period: financePeriodLabel(financePeriodFilter, language) })}</span> : null}
                  <span className="badge">{t("client.as_of_filter_badge", { date: formatDate(financeAsOfDateKey, language) })}</span>
                  {financeView === "transactions" && financeSourceFilter !== "ALL" ? <span className="badge">{t("client.type_filter_badge", { type: sourceLabel(financeSourceFilter, language) })}</span> : null}
                </FilterChipsBar>
              </SectionCard>

              {financeView === "transactions" ? (
                <SectionCard title={t("common.transactions")} className="client-finance-list-card" action={<span className="badge">{paymentRows.length}</span>}>
                  {paymentRows.length === 0 ? (
                    <p className="muted">{t("client.no_transaction_selection")}</p>
                  ) : (
                    <div className="client-finance-list">
                      {pagedPaymentRows.map((row) => {
                        const paymentKey = paymentKeyFromPaymentRow(row);
                        const linkedInvoice =
                          invoiceByPaymentId.get(row.id) ??
                          (paymentKey ? invoiceByPaymentKey.get(paymentKey) : undefined);
                        const canPayNow = canPayNowForPayment(row);
                        const isBilled = Boolean(linkedInvoice);
                        return (
                          <TransactionRow
                            key={`tx-${row.id}`}
                            typeBadge={<span className={`status-pill ${isBilled ? "status-ok" : "status-off"}`}>{isBilled ? t("client.billed") : t("client.unbilled")}</span>}
                            label={row.label}
                            meta={`${formatDateTime(row.occurred_at, language)} · ${row.owner_display_name} · ${sourceLabel(row.source, language)}`}
                            amount={toMoney(row.total_incl_vat, row.currency, language)}
                            statusBadge={<span className={`status-pill ${statusClass(row.status)}`}>{financeStatusLabel(row.status, language)}</span>}
                            actions={
                              <div className="row client-finance-card-actions">
                                {linkedInvoice ? (
                                  <a
                                    className="mode-link"
                                    href={
                                      clientInvoiceHref(linkedInvoice.id, { inline: true })
                                    }
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {t("client.open_invoice")}
                                  </a>
                                ) : null}
                                {canPayNow ? (
                                  <form action={openClientPaymentCheckoutAction}>
                                    <input type="hidden" name="payment_id" value={row.id} />
                                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions" })} />
                                    <button type="submit">{t("common.pay")}</button>
                                  </form>
                                ) : null}
                              </div>
                            }
                          />
                        );
                      })}
                    </div>
                  )}
                </SectionCard>
              ) : (
                <SectionCard title={t("common.invoices")} className="client-finance-list-card" action={<span className="badge">{invoiceRows.length}</span>}>
                  {invoiceRows.length === 0 ? (
                    <p className="muted">{t("client.no_invoice")}</p>
                  ) : (
                    <div className="client-finance-list">
                      {pagedInvoiceRows.map((row) => {
                        const linkedPayment = paymentByInvoiceId.get(row.id);
                        const canPayInvoice = (linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(row.payment_url);
                        return (
                          <CompactInvoiceRow
                            key={`inv-${row.id}`}
                            title={compactId(row.invoice_number)}
                            statusBadge={<span className={`status-pill ${statusClass(row.status)}`}>{financeStatusLabel(row.status, language)}</span>}
                            meta={`${toMoney(row.total_incl_vat, row.currency, language)} · ${formatDate(row.issued_at, language)} · ${row.owner_display_name}`}
                            subline={invoicePeriodSubline(row.label, language)}
                            actions={
                              <div className="row client-finance-card-actions">
                                {canPayInvoice ? (
                                  <form action={openClientPaymentCheckoutAction}>
                                    {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                    {row.payment_url ? <input type="hidden" name="payment_url" value={row.payment_url} /> : null}
                                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices" })} />
                                    <button type="submit" className="client-card-primary-action">{t("common.pay")}</button>
                                  </form>
                                ) : (
                                  <a
                                    className="mode-link client-card-primary-action"
                                    href={clientInvoiceHref(row.id, { inline: true })}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {t("common.view")}
                                  </a>
                                )}
                                {row.download_url ? (
                                  <a className="mode-link" href={row.download_url}>
                                    {t("common.download")}
                                  </a>
                                ) : null}
                              </div>
                            }
                          />
                        );
                      })}
                    </div>
                  )}

                  {selectedInvoice ? (
                    <article className="item client-invoice-viewer">
                      <div className="row spread">
                        <h4>{selectedInvoice.invoice_number}</h4>
                        <span className={`status-pill ${statusClass(selectedInvoice.status)}`}>{financeStatusLabel(selectedInvoice.status, language)}</span>
                      </div>
                      <p className="muted">{invoicePeriodSubline(selectedInvoice.label, language)}</p>
                      <p className="muted">
                        {t("common.date")}: {formatDateTime(selectedInvoice.issued_at, language)} · {t("common.member")}: {selectedInvoice.owner_display_name}
                      </p>
                      <p>
                        <strong>{toMoney(selectedInvoice.total_incl_vat, selectedInvoice.currency, language)}</strong>
                      </p>
                      <div className="row client-invoice-viewer-actions">
                        <CopyIdButton value={selectedInvoice.invoice_number} label={t("client.copy_number")} />
                        {selectedInvoice.download_url ? <a className="mode-link" href={selectedInvoice.download_url}>{t("client.download_pdf")}</a> : null}
                        <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: null })}>{t("common.close")}</a>
                      </div>
                    </article>
                  ) : null}
                </SectionCard>
              )}

              {financeTotalRows > financePageSize ? (
                <Card className="client-finance-pagination-card">
                  <div className="row spread">
                    <p className="muted">
                      {t("client.page_summary", { page: financePage, count: financePageCount, rows: financeTotalRows })}
                    </p>
                    <div className="row client-finance-pagination-actions">
                      {financePage > 1 ? (
                        <a
                          className="mode-link"
                          href={withUpdatedQuery(rawParams, { tab: "finance", finance_page: String(financePage - 1), invoice_id: null })}
                        >
                          {t("common.previous")}
                        </a>
                      ) : (
                        <span className="mode-link disabled" aria-disabled="true">
                          {t("common.previous")}
                        </span>
                      )}
                      {financePage < financePageCount ? (
                        <a
                          className="mode-link"
                          href={withUpdatedQuery(rawParams, { tab: "finance", finance_page: String(financePage + 1), invoice_id: null })}
                        >
                          {t("common.next")}
                        </a>
                      ) : (
                        <span className="mode-link disabled" aria-disabled="true">
                          {t("common.next")}
                        </span>
                      )}
                    </div>
                  </div>
                </Card>
              ) : null}

              {financeDueTotal > 0 ? (
                <div className="client-finance-sticky-pay">
                  {primaryDuePayableRow || primaryDuePaymentUrl ? (
                    <form action={openClientPaymentCheckoutAction}>
                      {primaryDuePayableRow ? <input type="hidden" name="payment_id" value={primaryDuePayableRow.id} /> : null}
                      {primaryDuePaymentUrl ? <input type="hidden" name="payment_url" value={primaryDuePaymentUrl} /> : null}
                      <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })} />
                      <button type="submit" className="client-pay-cta">
                        {t("common.pay")} {toMoney(String(financeDueTotal), me.preferred_currency, language)}
                      </button>
                    </form>
                  ) : (
                    <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                      {t("common.pay")} {toMoney(String(financeDueTotal), me.preferred_currency, language)}
                    </a>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

          {tab === "messages" ? (
            <Card>
              <div className="row spread">
                <h2>{t("client.messages_sent")}</h2>
                <span className="badge">{messageRows.length}</span>
              </div>
              <p className="muted">{t("client.messages_scope_help")}</p>

              <form method="get" className="client-filter-grid">
                <input type="hidden" name="tab" value="messages" />
                <input type="hidden" name="message_id" value="" />
                <label>
                  {t("common.period")}
                  <select name="message_scope" defaultValue={messageScope}>
                    <option value="LAST_3_MONTHS">{t("client.last_90_days")}</option>
                    <option value="CURRENT_YEAR">{t("client.current_year")}</option>
                    <option value="ALL">{t("client.all_messages")}</option>
                  </select>
                </label>
                <label>
                  {t("common.member")}
                  <select name="member_id" defaultValue={selectedMemberFilter}>
                    <option value="ALL">{hasMultipleVisibleMembers ? t("client.all_members") : t("client.account_self")}</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("client.search")}
                  <input
                    type="search"
                    name="message_query"
                    defaultValue={messageQuery}
                    placeholder={t("client.message_search_placeholder")}
                  />
                </label>
                <div className="row client-message-filter-actions">
                  <button type="submit" aria-label={t("client.search_messages_aria")}>
                    🔎
                  </button>
                  <a
                    className="reset-link"
                    href={withUpdatedQuery(rawParams, {
                      tab: "messages",
                      message_scope: "LAST_3_MONTHS",
                      member_id: null,
                      message_id: null,
                      message_query: null,
                    })}
                  >
                    ↺
                  </a>
                </div>
              </form>

              {messageRows.length === 0 ? (
                <p className="muted">{t("client.no_message_filter")}</p>
              ) : (
                <>
                <div className="table-wrap client-desktop-table client-messages-table-wrap">
                  <table className="data-table client-data-table">
                    <thead>
                      <tr>
                        <th>{t("common.date")}</th>
                        <th>{t("common.member")}</th>
                        <th>{t("client.channel")}</th>
                        <th>{t("client.subject")}</th>
                        <th>{t("common.status")}</th>
                        <th>{t("client.context")}</th>
                        <th>{t("client.action")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {messageRows.map((msg) => (
                        <tr key={msg.id}>
                          <td>{formatDateTime(msg.sent_at ?? msg.scheduled_for_utc, language)}</td>
                          <td>{msg.owner_display_name}</td>
                          <td>{msg.channel}</td>
                          <td>{msg.subject_preview}</td>
                          <td>
                            <span className={`status-pill ${statusClass(msg.status)}`}>{statusLabel(msg.status, language)}</span>
                          </td>
                          <td>{msg.session_title ?? t("client.transactional_message")}</td>
                          <td>
                            <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages", message_id: msg.id })}>
                              {t("client.read")}
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="list client-mobile-list client-inbox-list">
                  {messageRows.map((msg) => (
                    <a key={`${msg.id}-mobile`} href={withUpdatedQuery(rawParams, { tab: "messages", message_id: msg.id })} className="mode-link">
                      <ListRow
                        title={msg.subject_preview || t("client.message_without_subject")}
                        subtitle={`${formatDateTime(msg.sent_at ?? msg.scheduled_for_utc, language)} | ${msg.owner_display_name}`}
                        right={
                          <div className="stack-xs">
                            <span className="badge">{msg.channel}</span>
                            <span className={`status-pill ${statusClass(msg.status)}`}>{statusLabel(msg.status, language)}</span>
                          </div>
                        }
                      />
                    </a>
                  ))}
                </div>
                {selectedMessage ? (
                  <section className="modal-overlay">
                    <article className="modal-panel modal-client-message-details">
                      <header className="client-message-modal-header">
                        <a
                          className="modal-close-x"
                          href={withUpdatedQuery(rawParams, { tab: "messages", message_id: null })}
                          aria-label={t("client.close_message")}
                        >
                          ×
                        </a>
                        <h3>{selectedMessage.subject_preview || t("client.message_without_subject")}</h3>
                        <p className="muted">
                          {formatDateTime(selectedMessage.sent_at ?? selectedMessage.scheduled_for_utc, language)} · {selectedMessage.owner_display_name} · {selectedMessage.channel}
                        </p>
                      </header>

                      <section className="modal-card client-message-modal-meta">
                        <div className="client-message-meta-grid">
                          <article className="item">
                            <small className="muted">{t("client.recipient")}</small>
                            <p>{selectedMessage.recipient_email || t("client.hidden_for_member")}</p>
                          </article>
                          <article className="item">
                            <small className="muted">{t("common.status")}</small>
                            <p>{statusLabel(selectedMessage.status, language)}</p>
                          </article>
                          <article className="item">
                            <small className="muted">{t("client.context")}</small>
                            <p>{selectedMessage.session_title ?? t("client.transactional_message")}</p>
                          </article>
                          <article className="item">
                            <small className="muted">{t("client.channel")}</small>
                            <p>{selectedMessage.channel}</p>
                          </article>
                        </div>
                      </section>

                      <section className="modal-card client-message-detail">
                        {selectedMessage.content_html ? (
                          <iframe
                            title={selectedMessage.subject_preview || t("client.messages")}
                            className="client-message-html"
                            sandbox=""
                            srcDoc={selectedMessage.content_html}
                          />
                        ) : (
                          <pre className="client-message-detail-content">
                            {selectedMessage.content_text || selectedMessage.content_preview || t("client.content_unavailable")}
                          </pre>
                        )}
                      </section>
                    </article>
                  </section>
                ) : null}
                </>
              )}
            </Card>
          ) : null}

          {tab === "account" ? (
            <>
              <section className="client-account-mobile">
                <details className="client-account-accordion card" open>
                  <summary>{t("client.account_title")}</summary>
                  <div className="client-account-accordion-content">
                    <div className="list client-mobile-list">
                      <ListRow title={t("client.first_name_label")} right={me.first_name ?? "-"} />
                      <ListRow title={t("client.last_name_label")} right={me.last_name ?? "-"} />
                      <ListRow title={t("common.email")} right={me.email} />
                      <ListRow title={t("client.mobile_phone_1")} right={me.mobile_phone_1 ?? "-"} />
                      <ListRow title={t("client.mobile_phone_2")} right={me.mobile_phone_2 ?? "-"} />
                      <ListRow title={t("client.home_phone_label")} right={me.home_phone ?? "-"} />
                      <ListRow
                        title={t("client.address_label")}
                        subtitle={`${me.address_line ?? "-"}, ${me.postal_code ?? "-"} ${me.city ?? "-"}, ${labelFromOptions(COUNTRY_OPTIONS, me.address_country)}`}
                      />
                      <ListRow title={t("client.residence_country_label")} right={labelFromOptions(COUNTRY_OPTIONS, me.residence_country)} />
                      <ListRow title={t("client.currency")} right={labelFromOptions(CURRENCY_OPTIONS, me.preferred_currency)} />
                      <ListRow title={t("common.language")} right={me.preferred_language === "en" ? t("common.english") : t("common.french")} />
                      <ListRow title={t("client.timezone_label")} right={labelFromOptions(TIMEZONE_OPTIONS, me.timezone)} />
                    </div>
                    <div className="row">
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", edit_profile: editProfile ? null : "1" })}>
                        {editProfile ? t("client.edit_profile_close") : t("client.edit_profile_open")}
                      </a>
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", change_password: changePassword ? null : "1" })}>
                        🔒 {changePassword ? t("client.close_password_change") : t("client.change_password")}
                      </a>
                    </div>
                  </div>
                </details>

                <details className="client-account-accordion card" open={linkedMembers.length > 0}>
                  <summary>
                    <span>{t("client.members")}</span>
                    <span className="badge">{linkedMembers.length}</span>
                  </summary>
                  <div className="client-account-accordion-content">
                    {linkedMembers.length === 0 ? (
                      <p className="muted">{t("client.no_linked_member")}</p>
                    ) : (
                      <div className="list client-mobile-list">
                        {linkedMembers.map((member) => (
                            <ListRow
                              key={`mob-member-${member.id}`}
                              title={member.display_name}
                              subtitle={member.email ?? undefined}
                              right={<span className="badge">{member.kind === "CHILD" ? t("client.child") : t("client.adult")}</span>}
                            />
                        ))}
                      </div>
                    )}
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>{t("common.preferences")}</summary>
                  <div className="client-account-accordion-content">
                    <article className="item">
                      <strong>{t("common.summary")}</strong>
                      <p className="muted">{communicationSummary}</p>
                    </article>
                    <article className="item">
                      <strong>{t("client.lesson_reminders")}</strong>
                      <p className="muted">{t("client.lesson_reminders_help")}</p>
                      <label className="client-switch-row"><span>{t("client.lesson_reminders_email")}</span><span className={`client-switch ${me.lesson_reminder_email_opt_in ? "on" : ""}`} /></label>
                      <label className="client-switch-row"><span>{t("client.lesson_reminders_sms")}</span><span className={`client-switch ${me.lesson_reminder_sms_opt_in ? "on" : ""}`} /></label>
                      {me.lesson_reminder_sms_opt_in && !hasPhoneNumber ? <p className="muted">{t("client.phone_required_sms_reminders")}</p> : null}
                    </article>
                    <article className="item">
                      <strong>{t("client.school_communications")}</strong>
                      <p className="muted">{t("client.school_communications_help")}</p>
                      <label className="client-switch-row"><span>{t("client.communication_email")}</span><span className={`client-switch ${me.email_opt_in ? "on" : ""}`} /></label>
                      <label className="client-switch-row"><span>{t("client.communication_sms")}</span><span className={`client-switch ${me.sms_opt_in ? "on" : ""}`} /></label>
                      {me.sms_opt_in && !hasPhoneNumber ? <p className="muted">{t("client.phone_required_sms_communications")}</p> : null}
                    </article>
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>{t("client.view_messaging")}</a>
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>{t("client.recent_messages")}</summary>
                  <div className="client-account-accordion-content">
                    {messageRows.length === 0 ? (
                      <p className="muted">{t("client.recent_messages_empty")}</p>
                    ) : (
                      <div className="list client-mobile-list client-inbox-list">
                        {messageRows.slice(0, 8).map((msg) => (
                          <ListRow
                            key={`account-message-${msg.id}`}
                            title={msg.subject_preview || t("client.message_fallback")}
                            subtitle={`${formatDateTime(msg.sent_at ?? msg.scheduled_for_utc, language)} · ${msg.owner_display_name}`}
                            right={<span className="badge">{msg.channel}</span>}
                          />
                        ))}
                      </div>
                    )}
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>{t("client.full_history")}</a>
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>{t("common.credits")}</summary>
                  <div className="client-account-accordion-content">
                    {positivePackSubscriptions.length === 0 ? (
                      <p className="muted">{t("client.no_positive_credit")}</p>
                    ) : (
                      <div className="list client-mobile-list">
                        {positivePackSubscriptions.map((sub) => (
                          <ListRow
                            key={`mob-credit-${sub.id}`}
                            title={sub.plan.name}
                            subtitle={`${t("client.start_date_label", { date: formatDate(sub.started_at, language) })}${sub.ends_at ? ` | ${t("client.end_date_label", { date: formatDate(sub.ends_at, language) })}` : ""}`}
                            right={`${sub.credits_remaining ?? 0}/${sub.credits_initial ?? sub.credits_remaining ?? 0}`}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </details>
              </section>

              <section className="grid cols-2 client-account-desktop">
                <Card>
                  <div className="row spread">
                    <h2>{t("client.account_title")}</h2>
                    <div className="row">
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", change_password: changePassword ? null : "1" })}>
                        🔒 {changePassword ? t("client.close_password_change") : t("client.change_password")}
                      </a>
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", edit_profile: editProfile ? null : "1" })}>
                        {editProfile ? "✖" : "✎"}
                      </a>
                    </div>
                  </div>

                  <div className="client-info-list">
                    <p><strong>{t("client.first_name_label")}:</strong> {me.first_name ?? "-"}</p>
                    <p><strong>{t("client.last_name_label")}:</strong> {me.last_name ?? "-"}</p>
                    <p><strong>{t("common.email")}:</strong> {me.email}</p>
                    <p><strong>{t("client.mobile_phone_1")}:</strong> {me.mobile_phone_1 ?? "-"}</p>
                    <p><strong>{t("client.mobile_phone_2")}:</strong> {me.mobile_phone_2 ?? "-"}</p>
                    <p><strong>{t("client.home_phone_label")}:</strong> {me.home_phone ?? "-"}</p>
                    <p>
                      <strong>{t("client.address_label")}:</strong> {me.address_line ?? "-"}, {me.postal_code ?? "-"} {me.city ?? "-"}, {labelFromOptions(COUNTRY_OPTIONS, me.address_country)}
                    </p>
                    <p><strong>{t("client.residence_country_label")}:</strong> {labelFromOptions(COUNTRY_OPTIONS, me.residence_country)}</p>
                    <p><strong>{t("client.currency")}:</strong> {labelFromOptions(CURRENCY_OPTIONS, me.preferred_currency)}</p>
                    <p><strong>{t("common.language")}:</strong> {me.preferred_language === "en" ? t("common.english") : t("common.french")}</p>
                    <p><strong>{t("client.timezone_label")}:</strong> {labelFromOptions(TIMEZONE_OPTIONS, me.timezone)}</p>
                  </div>
                </Card>

                <Card>
                  <h2>{t("client.linked_members")}</h2>
                  {linkedMembers.length === 0 ? (
                    <p className="muted">{t("client.no_linked_member")}</p>
                  ) : (
                    <div className="list">
                      {linkedMembers.map((member) => (
                          <article key={member.id} className="item row spread">
                            <div>
                              <strong>{member.display_name}</strong>
                              {member.email ? <p className="muted">{member.email}</p> : null}
                            </div>
                            <span className="badge">{member.kind === "CHILD" ? t("client.child") : t("client.adult")}</span>
                          </article>
                      ))}
                    </div>
                  )}
                </Card>
              </section>

              <Card className="client-account-desktop">
                <h2>{t("client.communication_preferences")}</h2>
                <p className="muted">{communicationSummary}</p>
                <div className="client-preferences-list">
                  <article className="item">
                    <strong>{t("client.lesson_reminders")}</strong>
                    <label className="client-switch-row"><span>{t("client.lesson_reminders_email")}</span><span className={`client-switch ${me.lesson_reminder_email_opt_in ? "on" : ""}`} /></label>
                    <label className="client-switch-row"><span>{t("client.lesson_reminders_sms")}</span><span className={`client-switch ${me.lesson_reminder_sms_opt_in ? "on" : ""}`} /></label>
                  </article>
                  <article className="item">
                    <strong>{t("client.school_communications")}</strong>
                    <label className="client-switch-row"><span>{t("client.communication_email")}</span><span className={`client-switch ${me.email_opt_in ? "on" : ""}`} /></label>
                    <label className="client-switch-row"><span>{t("client.communication_sms")}</span><span className={`client-switch ${me.sms_opt_in ? "on" : ""}`} /></label>
                  </article>
                </div>
              </Card>

              <Card className="client-account-desktop">
                <div className="row spread">
                  <h2>{t("client.recent_messages")}</h2>
                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>
                    {t("common.view_all")}
                  </a>
                </div>
                {messageRows.length === 0 ? (
                  <p className="muted">{t("client.recent_messages_empty")}</p>
                ) : (
                  <div className="list">
                    {messageRows.slice(0, 6).map((msg) => (
                      <article key={`desktop-account-message-${msg.id}`} className="item row spread">
                        <div>
                          <strong>{msg.subject_preview || t("client.message_fallback")}</strong>
                          <p className="muted">{formatDateTime(msg.sent_at ?? msg.scheduled_for_utc, language)} · {msg.owner_display_name}</p>
                        </div>
                        <span className="badge">{msg.channel}</span>
                      </article>
                    ))}
                  </div>
                )}
              </Card>

              <Card className="client-account-desktop">
                <h2>{t("client.available_credits")}</h2>
                <p className="muted">{t("client.positive_credits_only")}</p>
                {positivePackSubscriptions.length === 0 ? (
                  <p className="muted">{t("client.no_positive_credit")}</p>
                ) : (
                  <div className="list">
                    {positivePackSubscriptions.map((sub) => (
                      <article key={`account-credit-${sub.id}`} className="item">
                        <div className="row spread">
                          <strong>{sub.plan.name}</strong>
                          <span className="badge">{sub.owner_display_name}</span>
                        </div>
                        <p className="muted">
                          {t("client.credit_line", { remaining: sub.credits_remaining ?? 0, initial: sub.credits_initial ?? sub.credits_remaining ?? 0 })}
                        </p>
                        <p className="muted">
                          {t("client.start_date_label", { date: formatDate(sub.started_at, language) })}
                          {sub.ends_at ? ` | ${t("client.end_date_label", { date: formatDate(sub.ends_at, language) })}` : ""}
                        </p>
                      </article>
                    ))}
                  </div>
                )}
              </Card>

              {changePassword ? (
                <Card className="client-account-edit client-password-edit">
                  <h2>{t("client.password_security_title")}</h2>
                  <p className="muted">{t("client.password_security_help")}</p>
                  <form action={changePasswordAction} className="client-filter-grid">
                    <label className="span-2">
                      {t("client.current_password")}
                      <input
                        type="password"
                        name="current_password"
                        autoComplete="current-password"
                        minLength={8}
                        maxLength={128}
                        required
                      />
                    </label>
                    <label>
                      {t("client.new_password")}
                      <input
                        type="password"
                        name="new_password"
                        autoComplete="new-password"
                        minLength={8}
                        maxLength={128}
                        required
                      />
                    </label>
                    <label>
                      {t("client.confirm_new_password")}
                      <input
                        type="password"
                        name="new_password_confirm"
                        autoComplete="new-password"
                        minLength={8}
                        maxLength={128}
                        required
                      />
                    </label>
                    <div className="row span-2">
                      <button type="submit">{t("client.save_new_password")}</button>
                      <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "account", change_password: null })}>
                        {t("common.cancel")}
                      </a>
                    </div>
                  </form>
                </Card>
              ) : null}

              {editProfile ? (
                <Card className="client-account-edit">
                  <h2>{t("client.edit_my_information")}</h2>
                  <form action={updateProfileAction} className="client-filter-grid">
                    <label>
                      {t("client.first_name_label")}
                      <input type="text" name="first_name" defaultValue={me.first_name ?? ""} maxLength={100} required />
                    </label>
                    <label>
                      {t("client.last_name_label")}
                      <input type="text" name="last_name" defaultValue={me.last_name ?? ""} maxLength={100} required />
                    </label>
                    <label>
                      {t("common.email")}
                      <input type="email" value={me.email} disabled readOnly />
                    </label>
                    <label>
                      {t("client.mobile_phone_1")}
                      <input type="text" name="mobile_phone_1" defaultValue={me.mobile_phone_1 ?? me.phone ?? ""} maxLength={30} />
                    </label>
                    <label>
                      {t("client.mobile_phone_2")}
                      <input type="text" name="mobile_phone_2" defaultValue={me.mobile_phone_2 ?? ""} maxLength={30} />
                    </label>
                    <label>
                      {t("client.home_phone_label")}
                      <input type="text" name="home_phone" defaultValue={me.home_phone ?? ""} maxLength={30} />
                    </label>
                    <label>
                      {t("client.address_label")}
                      <input type="text" name="address_line" defaultValue={me.address_line ?? ""} maxLength={255} />
                    </label>
                    <label>
                      {t("client.postal_code_label")}
                      <input type="text" name="postal_code" defaultValue={me.postal_code ?? ""} maxLength={20} />
                    </label>
                    <label>
                      {t("client.city_label")}
                      <input type="text" name="city" defaultValue={me.city ?? ""} maxLength={120} />
                    </label>
                    <label>
                      {t("client.address_country_label")}
                      <select name="address_country" defaultValue={me.address_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("client.residence_country_label")}
                      <select name="residence_country" defaultValue={me.residence_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("client.currency")}
                      <select name="preferred_currency" defaultValue={me.preferred_currency || DEFAULT_CURRENCY} required>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("common.language")}
                      <select name="preferred_language" defaultValue={me.preferred_language || "fr"} required>
                        <option value="fr">{t("common.french")}</option>
                        <option value="en">{t("common.english")}</option>
                      </select>
                    </label>
                    <label>
                      {t("client.timezone_label")}
                      <select name="timezone" defaultValue={me.timezone || DEFAULT_TIMEZONE} required>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="span-2">
                      {t("client.important_information")}
                      <textarea name="important_info" rows={3} defaultValue={me.important_info ?? ""} maxLength={1000} />
                    </label>

                    <input type="hidden" name="portal_contact_visible" value={me.portal_contact_visible ? "on" : "off"} />
                    <label className="checkline">
                      <input type="checkbox" name="email_opt_in" defaultChecked={me.email_opt_in} />
                      <span className="client-switch-label">{t("client.communication_email")}</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="sms_opt_in" defaultChecked={me.sms_opt_in} />
                      <span className="client-switch-label">{t("client.communication_sms")}</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="lesson_reminder_email_opt_in" defaultChecked={me.lesson_reminder_email_opt_in} />
                      <span className="client-switch-label">{t("client.lesson_reminders_email")}</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="lesson_reminder_sms_opt_in" defaultChecked={me.lesson_reminder_sms_opt_in} />
                      <span className="client-switch-label">{t("client.lesson_reminders_sms")}</span>
                    </label>

                    <input type="hidden" name="phone" value={me.mobile_phone_1 ?? me.phone ?? ""} readOnly />

                    <div className="row span-2">
                      <button type="submit">💾</button>
                      <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "account", edit_profile: null })}>
                        ✖
                      </a>
                    </div>
                  </form>
                </Card>
              ) : null}
            </>
          ) : null}
        </section>
      </section>

        <MobileTabs items={mobileTabLinks} activeId={activeMobileTabId} ariaLabel={uiText(language, "portal.mobile_client_nav")} />
    </main>
  );
}
