import Link from "next/link";
import { redirect } from "next/navigation";

import PortalImpersonationBanner from "../../components/portal-impersonation-banner";
import { getAdminToken, getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import {
  cancelBookingAction,
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

type SearchParams = Record<string, string | string[] | undefined>;
type AgendaView = "agenda" | "week" | "day";
type DashboardTab = "home" | "planning" | "courses" | "reservations" | "offers" | "finance" | "messages" | "account";
type MessageScope = "LAST_3_MONTHS" | "CURRENT_YEAR" | "ALL";
type TimeBucket = "ALL" | "MORNING" | "AFTERNOON" | "EVENING";
type PlanningSlotFilter = "ALL" | "AVAILABLE" | "ALREADY_BOOKED";
type FinanceView = "transactions" | "invoices";
type FinanceStatusFilter = "ALL" | "TO_PAY" | "PAID" | "CANCELLED" | "FAILED";
type FinancePeriodFilter = "ALL" | "LAST_30_DAYS" | "LAST_90_DAYS" | "LAST_365_DAYS";

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
  if (value === "planning" || value === "courses" || value === "reservations" || value === "offers" || value === "finance" || value === "messages" || value === "account") {
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

function statusLabel(value: string): string {
  const normalized = normalizeStatus(value);
  if (normalized === "BOOKED") {
    return "RÉSERVÉ";
  }
  if (normalized === "WAITLISTED") {
    return "ATTENTE";
  }
  if (normalized === "CANCELLED") {
    return "ANNULE";
  }
  if (normalized === "COMPLETED") {
    return "TERMINE";
  }
  if (normalized === "ATTENDED") {
    return "PRESENT";
  }
  if (normalized === "NO_SHOW") {
    return "ABSENT";
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return "ABSENCE EXCUSEE";
  }
  if (normalized === "NOT_BILLABLE") {
    return "NON FACTURABLE";
  }
  if (normalized === "ACTIVE") {
    return "ACTIF";
  }
  if (normalized === "PAID") {
    return "PAYE";
  }
  if (
    normalized === "PENDING" ||
    normalized === "PENDING_PAYMENT" ||
    normalized === "OPEN" ||
    normalized === "CREATED" ||
    normalized === "PROCESSING" ||
    normalized === "WAITING_PAYMENT"
  ) {
    return "EN ATTENTE";
  }
  return normalized || "-";
}

function financeStatusLabel(value: string): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PAID") {
    return "Payee";
  }
  if (FINANCE_PENDING_STATUSES.has(normalized)) {
    return "A payer";
  }
  if (FINANCE_CANCELLED_STATUSES.has(normalized)) {
    return "Annulee";
  }
  if (FINANCE_FAILED_STATUSES.has(normalized)) {
    return "Echouee";
  }
  return statusLabel(value);
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

function financePeriodLabel(period: FinancePeriodFilter): string {
  if (period === "LAST_30_DAYS") {
    return "30j";
  }
  if (period === "LAST_90_DAYS") {
    return "90j";
  }
  if (period === "LAST_365_DAYS") {
    return "1 an";
  }
  return "Toutes periodes";
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

function sourceLabel(value: string): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PLAN_PURCHASE") {
    return "Facture";
  }
  if (normalized === "BOOKING") {
    return "Facture";
  }
  if (normalized === "INVOICE_RANGE") {
    return "Facture";
  }
  if (normalized === "BOOKING_CREDIT") {
    return "Rabais";
  }
  if (normalized === "REFUND") {
    return "Remboursement";
  }
  if (normalized === "MANUAL") {
    return "Paiement";
  }
  return "Transaction";
}

function planKindLabel(value: string): string {
  const normalized = normalizeStatus(value);
  if (normalized === "PACK") {
    return "Carnet";
  }
  if (normalized === "SUBSCRIPTION") {
    return "Abonnement";
  }
  if (normalized === "FORFAIT") {
    return "Forfait";
  }
  return normalized || "Forfait";
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

function paymentMethodLabel(value: string | null | undefined): string {
  const normalized = normalizeStatus(value || "");
  if (!normalized) {
    return "Mode non renseigne";
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
    return "Especes";
  }
  if (normalized.includes("TRANSFER")) {
    return "Virement";
  }
  if (normalized.includes("CHECK")) {
    return "Cheque";
  }
  return normalized;
}

function formatDate(value: string | null | undefined): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDateTime(value: string | null | undefined): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatDateInTimezone(value: string | null | undefined, timezone: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: resolveTimezone(timezone),
  });
}

function formatDateTimeInTimezone(value: string | null | undefined, timezone: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: resolveTimezone(timezone),
  });
}

function formatTimeInTimezone(value: string | null | undefined, timezone: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: resolveTimezone(timezone),
  });
}

function formatTime(value: string | null | undefined): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toMoney(amountRaw: string | null | undefined, currencyRaw: string | null | undefined): string {
  const amount = Number(amountRaw ?? "0");
  const currency = (currencyRaw || "EUR").toUpperCase();
  if (!Number.isFinite(amount)) {
    return "-";
  }
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
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

function agendaDayLabel(dayKey: string, view: AgendaView): string {
  const date = keyToUtcDate(dayKey);
  if (view === "day") {
    return new Intl.DateTimeFormat("fr-FR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function buildAgendaRange(view: AgendaView, focusDayKey: string): AgendaRange {
  const focusDate = keyToUtcDate(focusDayKey);

  if (view === "day") {
    const from = focusDate;
    const toExclusive = addUtcDays(from, 1);
    const to = new Date(toExclusive.getTime() - 1);

    return {
      from,
      to,
      dayKeys: [focusDayKey],
      title: new Intl.DateTimeFormat("fr-FR", {
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
      title: `${new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(from)} - ${new Intl.DateTimeFormat("fr-FR", {
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
    title: new Intl.DateTimeFormat("fr-FR", {
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

function memberDisplayName(member: { first_name: string | null; last_name: string | null; email: string | null }): string {
  const fullName = [member.first_name, member.last_name].filter(Boolean).join(" ");
  return fullName || member.email || "Membre";
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

function courseAudienceLabel(course: ClientContentCourseOut): string {
  if (course.member_accesses.length === 0) {
    return "Acces non determine";
  }
  if (course.member_accesses.length === 1) {
    return course.member_accesses[0].member_display_name;
  }
  return `${course.member_accesses.length} membres`;
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
    redirect("/login?error=Session%20expiree");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/clients/me", {}, token);
  if (!meResult.ok) {
    redirect(`/login?error=${encodeURIComponent("Session invalide ou role non client")}`);
  }

  const me = meResult.data;
  const tab = parseTab(readParam(searchParams, "tab"));
  const impersonationClaims = readPortalImpersonationClaims();
  const isImpersonating = Boolean(impersonationClaims?.imp);
  const impersonationReturnTo = getPortalReturnTo() ?? "/admin";
  const impersonationNameHint = readParam(searchParams, "imp_name").trim();
  const rawParams = toSingleValueSearchParams(searchParams);

  const selectedCourseType = readParam(searchParams, "course_type_id");
  const selectedLocation = readParam(searchParams, "location_id");
  const selectedCoachId = readParam(searchParams, "coach_id");
  const selectedTimeBucket = parseTimeBucket(readParam(searchParams, "time_bucket"));
  const planningSlotFilter = parsePlanningSlotFilter(readParam(searchParams, "planning_slot_filter"));
  const timezone = resolveTimezone(readParam(searchParams, "timezone") || me.timezone || DEFAULT_TIMEZONE);
  const requestedAgendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const inputAgendaDate = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(inputAgendaDate) ? inputAgendaDate : todayKeyInTimezone(timezone);
  const agendaView: AgendaView = tab === "planning" ? "week" : requestedAgendaView;
  const agendaRange = buildAgendaRange(agendaView, agendaDate);

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
  const paymentReturnParam = readParam(searchParams, "payment_return").trim().toLowerCase();
  const purchaseContextParam = readParam(searchParams, "purchase_context").trim();
  const editProfile = readParam(searchParams, "edit_profile") === "1";
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

  if (paymentSourceParam === "PLAN_PURCHASE" && paymentIdParam && paymentReturnParam === "success") {
    const normalizedPaymentId = paymentIdParam.startsWith("plan:") ? paymentIdParam.slice("plan:".length) : paymentIdParam;
    const confirm = await backendRequest<ClientPaymentConfirmOut>(
      `/api/v1/clients/me/payments/${normalizedPaymentId}/confirm`,
      { method: "POST" },
      token,
    );
    if (!confirm.ok) {
      preFetchErrors.push(`confirm-payment: ${confirm.message}`);
      paymentResultError = "Le paiement est en attente de confirmation.";
    } else if (!confirm.data.paid) {
      const reason = confirm.data.message ? ` (${confirm.data.message})` : "";
      preFetchErrors.push(`confirm-payment: paiement non confirme${reason}`);
      paymentResultError = "Le paiement n'a pas encore ete confirme.";
    } else {
      paymentResultMessage = "Paiement effectue.";
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
            paymentResultMessage = "Paiement effectue. Le membre a ete place en liste d attente.";
          } else {
            paymentResultMessage = "Paiement effectue et reservation confirmee.";
          }
        }
      }
    }
  } else if (paymentSourceParam === "PLAN_PURCHASE" && paymentIdParam && paymentReturnParam === "cancel") {
    paymentResultError = "Paiement annule.";
  }

  const [
    courseTypesResult,
    locationsResult,
    sessionsResult,
    plansResult,
    subscriptionsResult,
    ownBookingsResult,
    familyResult,
    contentCoursesResult,
    messagesResult,
    paymentsResult,
    invoicesResult,
  ] = await Promise.all([
    backendRequest<CourseTypeOut[]>("/api/v1/course-types", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<SessionOut[]>(`/api/v1/clients/me/sessions?${sessionQuery.toString()}`, {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans", {}, token),
    backendRequest<SubscriptionOut[]>("/api/v1/clients/me/subscriptions", {}, token),
    backendRequest<ClientBookingOut[]>("/api/v1/clients/me/bookings", {}, token),
    backendRequest<ClientFamilyOverviewOut>("/api/v1/clients/me/family", {}, token),
    backendRequest<ClientContentCourseOut[]>("/api/v1/clients/me/content-courses", {}, token),
    backendRequest<ClientMessageOut[]>(`/api/v1/clients/me/messages?scope=${messageScope}`, {}, token),
    backendRequest<ClientPaymentOut[]>("/api/v1/clients/me/payments", {}, token),
    backendRequest<ClientInvoiceOut[]>("/api/v1/clients/me/invoices", {}, token),
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
      display_name: memberDisplayName(candidate),
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

  const members = [...memberMap.values()].sort((a, b) => a.display_name.localeCompare(b.display_name, "fr"));
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
        ? "Toute la famille"
        : members[0]?.display_name ?? "Mon compte"
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
        owner_display_name: memberDisplayName({ first_name: me.first_name, last_name: me.last_name, email: me.email }),
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
        },
      }));

  allBookings.sort((a, b) => b.session.start_at_utc.localeCompare(a.session.start_at_utc));

  const now = new Date();
  const activeBookingStatuses = new Set(["BOOKED", "WAITLISTED"]);

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
      return activeBookingStatuses.has(normalizeStatus(booking.status)) && sessionStart >= now;
    })
    .sort((a, b) => a.session.start_at_utc.localeCompare(b.session.start_at_utc));

  const pastBookings = allBookings
    .filter((booking) => {
      const sessionStart = safeDate(booking.session.start_at_utc);
      if (!sessionStart) {
        return true;
      }
      return sessionStart < now || !activeBookingStatuses.has(normalizeStatus(booking.status));
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
    if (!isSubscriptionActiveNow(sub, now)) {
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
  const isPendingSubscription = (sub: { status: string }): boolean => {
    const normalized = normalizeStatus(sub.status);
    return (
      normalized === "PENDING" ||
      normalized === "OPEN" ||
      normalized === "CREATED" ||
      normalized === "PROCESSING" ||
      normalized === "WAITING_PAYMENT"
    );
  };
  const visibleSelectedOwnerSubscriptions = selectedOwnerSubscriptions.filter(
    (sub) =>
      (isSubscriptionActiveNow(sub, now) &&
        (sub.plan.kind === "SUBSCRIPTION" || sub.plan.kind === "FORFAIT" || (sub.credits_remaining ?? 0) > 0)) ||
      isPendingSubscription(sub),
  );
  const selectedOfferSubscription = subscriptions.find((sub) => sub.id === selectedOfferDetailId) ?? null;
  const selectedOfferInvoices = selectedOfferSubscription
    ? invoiceRows.filter((invoice) => invoice.owner_client_id === selectedOfferSubscription.owner_client_id)
    : [];
  const homeSubscriptions = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => isSubscriptionActiveNow(sub, now) || isPendingSubscription(sub))
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  const subscriptionAlerts = subscriptions
    .filter((sub) => selectedMemberFilter === "ALL" || sub.owner_client_id === selectedMemberFilter)
    .filter((sub) => {
      const normalized = normalizeStatus(sub.status);
      return normalized === "PAYMENT_ALERT" || normalized === "PRE_TERMINATION";
    })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
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
  const firstHomeBooking = homeCalendarRows[0] ?? upcomingBookings14[0] ?? null;
  const homePlanningHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    agenda_view: "week",
    agenda_date: firstHomeBooking
      ? dateKeyInTimezone(firstHomeBooking.session.start_at_utc, timezone)
      : todayKeyInTimezone(timezone),
    session_id: null,
    booking_owner_id: FAMILY_BOOKING_OWNER,
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
    label: agendaDayLabel(key, agendaView),
    sessions: sessionsByDay.get(key) ?? [],
  }));
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

    let statusLabel = "Non reservable";
    if (alreadyReserved) {
      statusLabel = bookingStatus === "WAITLISTED" ? "Liste d attente" : "Deja reserve";
    } else if (paymentPending) {
      statusLabel = "Paiement en attente";
    } else if (isFull) {
      statusLabel = "Complet";
    } else if (sessionIsPastOrStarted) {
      statusLabel = "Passe";
    } else if (!session.online_booking_enabled) {
      statusLabel = "Reservation fermee";
    } else if (canCheckout) {
      statusLabel = hasDirectPayment && !eligibleByPlan ? "Paiement requis" : "Disponible";
    } else if (hasAnySubscription) {
      statusLabel = "Offre incompatible";
    } else {
      statusLabel = "Aucune formule";
    }

    const actionLabel = paymentPending
      ? "Finaliser le paiement"
      : hasDirectPayment && !eligibleByPlan
        ? "Payer et reserver"
        : "Reserver";

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
      statusLabel,
      actionLabel,
    };
  };
  const planningStateForSession = (session: SessionOut) => {
    const sessionIsPastOrStarted = (safeDate(session.start_at_utc)?.getTime() ?? 0) <= now.getTime();
    const hasDirectPayment = sessionHasDirectPayment(session);
    if (bookingOwnerId !== FAMILY_BOOKING_OWNER) {
      const ownerState = memberPlanningStateForSession(session, bookingOwnerId);
      const ownerName = bookingOwnerMember?.display_name ?? "ce membre";
      const contextLine = ownerState.alreadyReserved
        ? "Vous etes deja inscrit sur ce creneau"
        : ownerState.paymentPending
          ? "Paiement a finaliser pour ce membre"
          : ownerState.canCheckout
            ? hasDirectPayment && !ownerState.eligibleByPlan
              ? "Paiement en ligne requis pour confirmer"
              : "Disponible pour reservation"
            : ownerState.statusLabel === "Offre incompatible"
              ? "La formule de ce membre n est pas compatible"
              : ownerState.statusLabel === "Aucune formule"
                ? `Aucune formule active pour ${ownerName}`
                : ownerState.statusLabel === "Reservation fermee"
                  ? "Reservation en ligne fermee"
                  : ownerState.statusLabel === "Passe"
                    ? "Creneau passe"
                    : ownerState.statusLabel === "Complet"
                      ? "Creneau complet"
                      : `Non reservable pour ${ownerName}`;
      return {
        ...ownerState,
        statusLabel: ownerState.statusLabel,
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

    let statusLabel = "Non reservable";
    let contextLine = "Aucune action disponible pour la famille";
    if (hasAdditionalFamilyOptions) {
      statusLabel = "Reservation possible";
      contextLine =
        reservedFamilyBookings.length > 1
          ? `${reservedFamilyBookings.length} reservations famille. Vous pouvez encore reserver pour un autre membre.`
          : `Reserve pour ${reservedNames}. Vous pouvez encore reserver pour un autre membre.`;
    } else if (reservedFamilyBookings.length > 0) {
      statusLabel = "Deja reserve";
      contextLine = `Reserve pour ${reservedNames}`;
    } else if (pendingFamilyBookings.length > 0) {
      statusLabel = "Paiement en attente";
      contextLine = `Paiement a finaliser pour ${pendingNames}`;
    } else if (session.booked_count >= session.capacity_max) {
      statusLabel = "Complet";
      contextLine = "Creneau complet";
    } else if (sessionIsPastOrStarted) {
      statusLabel = "Passe";
      contextLine = "Creneau passe";
    } else if (!session.online_booking_enabled) {
      statusLabel = "Reservation fermee";
      contextLine = "Reservation en ligne fermee";
    } else if (actionableMembers.length > 1) {
      statusLabel = "Reservation possible";
      contextLine = "Choisissez le membre a inscrire a l etape suivante.";
    } else if (actionableMembers.length === 1) {
      statusLabel = actionableMembers[0].state.statusLabel;
      contextLine =
        actionableMembers[0].state.hasDirectPayment && !actionableMembers[0].state.eligibleByPlan
          ? `Paiement requis pour ${actionableMembers[0].member.display_name}`
          : `Disponible pour ${actionableMembers[0].member.display_name}`;
    } else if (hasAnySubscription) {
      statusLabel = "Offre incompatible";
      contextLine = "Aucune formule famille compatible";
    } else if (hasDirectPayment) {
      statusLabel = "Reservation possible";
      contextLine = "Choisissez le membre a rattacher a cette reservation";
    } else {
      statusLabel = "Aucune formule";
      contextLine = "Aucune formule active dans la famille";
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
      statusLabel,
      cardStatusLabel: statusLabel,
      contextLine,
      familyBookings,
      actionableMembers,
      actionLabel:
        requiresMemberChoice
          ? "Reserver"
          : actionableMembers.length === 1
          ? actionableMembers[0].state.actionLabel
          : "Reserver",
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
          action_label: state.paymentPending ? "Finaliser le paiement" : state.actionLabel,
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
  const selectedSessionReturnTo = selectedSession
    ? withUpdatedQuery(rawParams, {
        tab: "planning",
        session_id: selectedSession.id,
        session_member_id: null,
        session_ok: null,
        session_error: null,
      })
    : withUpdatedQuery(rawParams, {
        tab: "planning",
        session_ok: null,
        session_error: null,
      });
  const selectedSessionCloseHref = withUpdatedQuery(rawParams, {
    tab: "planning",
    session_id: null,
    session_member_id: null,
    session_ok: null,
    session_error: null,
  });
  const selectedSessionModalStatusLabel = selectedReservationMemberOption?.status_label || selectedSessionPlanningState?.cardStatusLabel || "";
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
  const selectedSessionPackCreditLabel = selectedSessionPackCreditSummary
    ? `${selectedSessionPackCreditSummary.remaining} credit${selectedSessionPackCreditSummary.remaining > 1 ? "s" : ""} restant${selectedSessionPackCreditSummary.remaining > 1 ? "s" : ""}${
        selectedSessionPackCreditSummary.packCount === 1 && selectedSessionPackCreditSummary.initial > 0
          ? ` sur ${selectedSessionPackCreditSummary.initial}`
          : ""
      }`
    : null;
  const selectedSessionCoverageLabel =
    selectedReservationMemberOption?.coverage_source === "MANUAL_CREDIT"
      ? "Credit manuel disponible"
      : selectedReservationMemberOption?.coverage_source === "PACK"
        ? selectedSessionPackCreditLabel || "Carnet compatible disponible"
        : selectedReservationMemberOption?.coverage_source === "FORFAIT"
          ? "Forfait compatible disponible"
          : selectedReservationMemberOption?.coverage_source === "SUBSCRIPTION"
            ? "Abonnement compatible disponible"
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
  const reservationOptionSupportLabel = (option: ClientSessionReservationMemberOptionOut): string | null => {
    if (option.action_code === "FINALIZE_PAYMENT" && option.direct_payment_amount_ttc) {
      return `Paiement en attente · ${toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency)}`;
    }
    if (option.action_code === "BUY_FORMULA_OR_PAY_UNIT") {
      const formulaCount = option.formula_options.length;
      const parts = [];
      if (formulaCount > 0) {
        parts.push(`${formulaCount} formule${formulaCount > 1 ? "s" : ""}`);
      }
      if (option.direct_payment_amount_ttc) {
        parts.push(`Paiement unitaire ${toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency)}`);
      }
      return parts.join(" · ") || null;
    }
    if (option.action_code === "BUY_FORMULA" && option.formula_options.length > 0) {
      return `${option.formula_options.length} formule${option.formula_options.length > 1 ? "s" : ""} compatible${option.formula_options.length > 1 ? "s" : ""}`;
    }
    if (option.action_code === "PAY_UNIT" && option.direct_payment_amount_ttc) {
      return `Paiement unitaire ${toMoney(option.direct_payment_amount_ttc, option.direct_payment_currency)}`;
    }
    if (option.action_code === "BOOK_WITH_CREDIT") {
      if (option.coverage_source === "PACK") {
        const packSummary = compatiblePackCreditSummaryForMember(option.member_id);
        if (packSummary) {
          return `${packSummary.remaining} credit${packSummary.remaining > 1 ? "s" : ""} restant${packSummary.remaining > 1 ? "s" : ""}`;
        }
      }
      if (option.coverage_source === "SUBSCRIPTION") {
        return "Abonnement actif";
      }
      if (option.coverage_source === "FORFAIT") {
        return "Forfait actif";
      }
      if (option.coverage_source === "MANUAL_CREDIT") {
        return "Credit manuel disponible";
      }
      return "Reservation couverte sans paiement supplementaire";
    }
    if (option.action_code === "JOIN_WAITLIST") {
      return "Inscription possible sur liste d attente";
    }
    return null;
  };
  const selectedSessionStateTitle =
    selectedSessionRequiresMemberChoice
      ? "Choisissez le membre"
      : selectedSessionEffectiveActionCode === "FINALIZE_PAYMENT" && selectedReservationMemberOption
        ? `Finaliser le paiement pour ${selectedReservationMemberOption.member_display_name}`
        : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" && selectedReservationMemberOption
          ? selectedReservationMemberOption.coverage_source === "PACK"
            ? "Utiliser vos credits"
            : "Reserver sans payer"
        : selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
          ? "Choisir votre option"
          : selectedSessionEffectiveActionCode === "BUY_FORMULA"
            ? "Acheter une formule"
            : selectedReservationMemberOption?.action_label || "Consulter ce creneau";
  const selectedSessionStateDescription =
    selectedSessionRequiresMemberChoice
      ? "Nous vous proposerons automatiquement la meilleure option: credit, formule compatible ou paiement a l unite."
      : selectedSessionEffectiveActionCode === "FINALIZE_PAYMENT" && selectedReservationMemberOption
        ? alternativeReservationOptions.length > 0
          ? `Une reservation provisoire existe deja pour ${selectedReservationMemberOption.member_display_name}. Pour voir les formules ou le paiement a l unite d un autre membre, choisissez une autre carte ci-dessous.`
          : selectedReservationMemberOption.reason || selectedSessionPlanningState?.contextLine || ""
        : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" && selectedReservationMemberOption
          ? selectedReservationMemberOption.coverage_source === "PACK" && selectedSessionPackCreditLabel
            ? `Votre carnet couvre deja ce creneau pour ${selectedReservationMemberOption.member_display_name}. ${selectedSessionPackCreditLabel} apres cette verification.`
            : selectedReservationMemberOption.coverage_source === "SUBSCRIPTION"
              ? `Votre abonnement couvre deja ce creneau pour ${selectedReservationMemberOption.member_display_name}.`
              : `Cette reservation sera confirmee pour ${selectedReservationMemberOption.member_display_name} sans paiement supplementaire.`
        : selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT" && selectedReservationMemberOption
          ? `Aucun credit disponible pour ${selectedReservationMemberOption.member_display_name}. Vous pouvez choisir une formule compatible ou payer ce creneau a l unite.`
          : selectedSessionEffectiveActionCode === "BUY_FORMULA" && selectedReservationMemberOption
            ? `Aucun credit disponible pour ${selectedReservationMemberOption.member_display_name}. Choisissez une formule compatible pour confirmer la reservation.`
        : selectedReservationMemberOption?.reason || selectedSessionPlanningState?.contextLine || "";
  const selectedSessionPurchaseChoiceCount =
    (selectedSessionDirectPaymentAmount ? 1 : 0) + selectedSessionFormulaOptions.length;
  const selectedSessionPrimaryActionLabel =
    !selectedReservationMemberOption
      ? null
      : selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT"
        ? selectedReservationMemberOption.coverage_source === "PACK"
          ? "Utiliser mes credits"
          : selectedReservationMemberOption.coverage_source === "SUBSCRIPTION"
            ? "Utiliser mon abonnement"
            : selectedReservationMemberOption.coverage_source === "FORFAIT"
              ? "Utiliser mon forfait"
              : "Confirmer sans payer"
        : selectedReservationMemberOption.action_label;
  const selectedSessionHasBooking =
    Boolean(selectedReservationMemberOption?.booking_id) &&
    ["BOOKED", "WAITLISTED"].includes((selectedReservationMemberOption?.booking_status || "").toUpperCase());
  const selectedSessionCheckoutReturnTo =
    selectedSession && selectedReservationMemberOption
      ? buildClientSessionCheckoutHref(selectedSession.id, selectedSessionReturnTo, selectedReservationMemberOption.member_id)
      : "/buy/session/checkout";
  const agendaSessionCount = agendaDays.reduce((sum, day) => sum + day.sessions.length, 0);
  const advancedFiltersOpen =
    Boolean(selectedCourseType) ||
    Boolean(selectedCoachId) ||
    selectedTimeBucket !== "ALL" ||
    planningSlotFilter !== "ALL" ||
    timezone !== (me.timezone || DEFAULT_TIMEZONE) ||
    bookingOwnerId !== FAMILY_BOOKING_OWNER;

  const allBookingStatuses = Array.from(new Set(allBookings.map((row) => normalizeStatus(row.status)))).sort();
  const allPaymentSources = Array.from(new Set(payments.map((row) => normalizeStatus(row.source)))).sort();
  const visibleFinanceStatusOptions: Array<{ value: FinanceStatusFilter; label: string }> = [
    { value: "ALL", label: "Tous statuts" },
    { value: "TO_PAY", label: "A payer" },
    { value: "PAID", label: "Payee" },
    { value: "CANCELLED", label: "Annulee" },
    { value: "FAILED", label: "Echouee" },
  ];

  const totalCreditsByMember = new Map<string, number>();
  const positivePackSubscriptions = subscriptions.filter(
    (sub) => isSubscriptionActiveNow(sub, now) && sub.plan.kind === "PACK" && (sub.credits_remaining ?? 0) > 0,
  );
  for (const sub of positivePackSubscriptions) {
    if (sub.credits_remaining == null || sub.credits_remaining <= 0) {
      continue;
    }
    totalCreditsByMember.set(sub.owner_client_id, (totalCreditsByMember.get(sub.owner_client_id) ?? 0) + sub.credits_remaining);
  }
  const membersWithPositiveCredits = members.filter((member) => (totalCreditsByMember.get(member.id) ?? 0) > 0);

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

  const tabLinks: Array<{ id: DashboardTab; label: string; icon: string }> = [
    { id: "home", label: "Accueil", icon: "🏠" },
    { id: "planning", label: "Planning", icon: "📅" },
    { id: "courses", label: "Mes cours", icon: "📚" },
    { id: "reservations", label: "Réservations", icon: "✅" },
    { id: "offers", label: "Forfaits", icon: "🧾" },
    { id: "finance", label: "Finance", icon: "💳" },
    { id: "messages", label: "Messages", icon: "✉️" },
    { id: "account", label: "Compte", icon: "👤" },
  ];
  const mobileTabLinks = [
    { id: "home", label: "Accueil", icon: "🏠", href: withUpdatedQuery(rawParams, { tab: "home" }) },
    { id: "planning", label: "Planning", icon: "📅", href: withUpdatedQuery(rawParams, { tab: "planning" }) },
    { id: "courses", label: "Cours", icon: "📚", href: withUpdatedQuery(rawParams, { tab: "courses" }) },
    { id: "reservations", label: "Réservations", icon: "✅", href: withUpdatedQuery(rawParams, { tab: "reservations" }) },
    { id: "offers", label: "Forfaits", icon: "🧾", href: withUpdatedQuery(rawParams, { tab: "offers" }) },
    { id: "account", label: "Compte", icon: "👤", href: withUpdatedQuery(rawParams, { tab: "account" }) },
  ];
  const activeMobileTabId = mobileTabLinks.some((item) => item.id === tab)
    ? tab
    : tab === "messages" || tab === "finance"
      ? "account"
      : "home";

  const displayName = memberDisplayName({ first_name: me.first_name, last_name: me.last_name, email: me.email });
  const impersonationDisplayName = impersonationNameHint || displayName;
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");
  const sessionOkMessage = selectedSession ? readParam(searchParams, "session_ok") : "";
  const sessionErrorMessage = selectedSession ? readParam(searchParams, "session_error") : "";
  const globalOkMessage = sessionOkMessage ? "" : (okMessage || paymentResultMessage);
  const globalErrorMessage = sessionErrorMessage ? "" : (errorMessage || paymentResultError);
  const hasPhoneNumber = Boolean(me.mobile_phone_1 || me.mobile_phone_2 || me.home_phone || me.phone);
  const selectedMessageId = readParam(searchParams, "message_id");
  const selectedMessage = selectedMessageId ? messageRows.find((row) => row.id === selectedMessageId) ?? null : null;
  const communicationSummary = `Rappels: Email ${me.lesson_reminder_email_opt_in ? "ON" : "OFF"} / SMS ${
    me.lesson_reminder_sms_opt_in ? "ON" : "OFF"
  } · Communications: Email ${me.email_opt_in ? "ON" : "OFF"} / SMS ${me.sms_opt_in ? "ON" : "OFF"}`;
  const planningStatusClass = (statusLabelText: string): string => {
    switch (statusLabelText) {
      case "Deja reserve":
      case "Reserve":
      case "Liste d attente":
      case "Credit disponible":
        return "status-booked";
      case "Reservation possible":
      case "Reserver":
        return "status-scheduled";
      case "Paiement en attente":
        return "status-waitlist";
      case "Disponible":
      case "Paiement requis":
      case "Choisir le membre":
        return "status-scheduled";
      case "Complet":
        return "status-cancelled";
      case "Passe":
        return "status-completed";
      case "Reservation fermee":
      case "Offre incompatible":
      case "Aucune formule":
      case "Aucune couverture":
      case "Non reservable":
      default:
        return "status-draft";
    }
  };
  const shouldRenderPlanningStateBadge = (statusLabelText: string): boolean => {
    return new Set([
      "Paiement en attente",
      "Complet",
      "Passe",
      "Reservation fermee",
      "Offre incompatible",
      "Aucune formule",
      "Non reservable",
      "Liste d attente",
    ]).has(statusLabelText);
  };

  return (
    <main className="client-portal-shell">
      <aside className="client-portal-sidebar">
        <div className="client-brand">
          <PortalBrandLockup
            title="Piano Academie"
            subtitle="Portail client"
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
          <form action={endPortalImpersonationAction} className="client-admin-exit-form">
            <input type="hidden" name="return_to" value={impersonationReturnTo} />
            <button className="ghost client-admin-exit-btn" type="submit">
              Retour BO
            </button>
          </form>
        ) : null}

        <nav className="client-nav" aria-label="Navigation client">
          {tabLinks.map((item) => {
            const href = withUpdatedQuery(rawParams, { tab: item.id });
            return (
              <Link key={item.id} className={`client-nav-link ${tab === item.id ? "active" : ""}`} href={href}>
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <form action={logoutAction} className="client-logout">
          <button className="ghost" type="submit">
            ⎋
          </button>
          <span>Déconnexion</span>
        </form>
      </aside>

      <section className="client-portal-main">
        <MobileHeader
          title={tabLinks.find((item) => item.id === tab)?.label ?? "Portail client"}
          subtitle={`${displayName} · ${timezone}`}
          menu={
            <div className="client-mobile-menu-items">
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "home" })}>
                Accueil
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "planning" })}>
                Planning
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "reservations" })}>
                Réservations
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                Forfaits
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "finance" })}>
                Finance
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>
                Messages
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "courses" })}>
                Mes cours
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "account" })}>
                Compte
              </a>
              {isImpersonating ? (
                <form action={endPortalImpersonationAction}>
                  <input type="hidden" name="return_to" value={impersonationReturnTo} />
                  <button className="ghost client-mobile-menu-btn" type="submit">
                    Retour BO
                  </button>
                </form>
              ) : null}
              <form action={logoutAction}>
                <button className="ghost client-mobile-menu-btn" type="submit">
                  Se deconnecter
                </button>
              </form>
            </div>
          }
        />

        <header className="client-topbar">
          <div>
            <h1>{tabLinks.find((item) => item.id === tab)?.label ?? "Portail client"}</h1>
            <p className="muted">
              Réservations actives: {upcomingBookings.length} | {hasMultipleVisibleMembers ? "Membres visibles" : "Membre visible"}: {members.length}
            </p>
          </div>
          <div className="row">
            <span className="badge">Fuseau: {timezone}</span>
            <span className="badge">Devise: {me.preferred_currency}</span>
          </div>
        </header>

        <section className="client-content">
          {isImpersonating ? (
            <PortalImpersonationBanner displayName={impersonationDisplayName} returnTo={impersonationReturnTo} />
          ) : null}
          {globalOkMessage ? <Toast message={globalOkMessage} tone="ok" /> : null}
          {globalErrorMessage ? <section className="flash-err">{globalErrorMessage}</section> : null}
          {errors.length > 0 ? <section className="flash-err">Erreur backend: {errors.join(" | ")}</section> : null}
          {subscriptionAlerts.length > 0 ? (
            <section className={hasPreTerminationAlert ? "flash-err" : "flash-warn"}>
              {hasPreTerminationAlert
                ? "Votre abonnement est en attente de regularisation. Les nouvelles reservations sont temporairement indisponibles jusqu au paiement."
                : "Le renouvellement de votre abonnement n a pas pu etre finalise. Vous pouvez regulariser votre paiement des maintenant."}
              {primaryRecoveryUrl ? (
                <>
                  {" "}
                  <a className="mode-link" href={primaryRecoveryUrl} target="_blank" rel="noreferrer">
                    Regulariser mon paiement
                  </a>
                </>
              ) : null}
            </section>
          ) : null}

          {tab === "home" ? (
            <>
              <SectionCard
                title="Accueil"
                className="client-home-header-v2"
                action={<Link className="mode-link" href={homePlanningHref}>Voir le planning</Link>}
              >
                <p className="muted">Bonjour {me.first_name || displayName}</p>
                {linkedMembers.length > 0 ? (
                  <FilterChipsBar className="client-member-chips">
                    <a className={`badge ${selectedMemberFilter === "ALL" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", member_id: "ALL" })}>
                      Tous
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
                    <UrgentPayCard amountLabel={toMoney(String(homeDueTotal), me.preferred_currency)} countLabel={`${homeDueInvoices.length} facture(s)`}>
                      <div className="client-home-due-list">
                        {homeDueInvoicePreview.map((invoice) => {
                          const linkedPayment = paymentByInvoiceId.get(invoice.id);
                          const canPayInvoice = (linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(invoice.payment_url);
                          return (
                            <CompactInvoiceRow
                              key={`home-due-${invoice.id}`}
                              title={compactId(invoice.invoice_number)}
                              statusBadge={<span className={`status-pill ${statusClass(invoice.status)}`}>{financeStatusLabel(invoice.status)}</span>}
                              meta={`${toMoney(invoice.total_incl_vat, invoice.currency)} · ${formatDate(invoice.issued_at)}`}
                              subline={invoice.label}
                              actions={
                                <div className="row client-home-due-actions">
                                  {canPayInvoice ? (
                                    <form action={openClientPaymentCheckoutAction}>
                                      {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                      {invoice.payment_url ? <input type="hidden" name="payment_url" value={invoice.payment_url} /> : null}
                                      <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "home" })} />
                                      <button type="submit" className="client-card-primary-action">Payer</button>
                                    </form>
                                  ) : null}
                                  <a
                                    className="mode-link"
                                    href={clientInvoiceHref(invoice.id, { inline: true })}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Ouvrir
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
                              Payer {toMoney(String(homeDueTotal), me.preferred_currency)}
                            </button>
                          </form>
                        ) : (
                          <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", finance_status: "TO_PAY" })}>
                            Payer {toMoney(String(homeDueTotal), me.preferred_currency)}
                          </a>
                        )}
                        <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                          Voir toutes les factures
                        </a>
                      </div>
                    </UrgentPayCard>
                  ) : null}

                  <SectionCard title="À venir (14 jours)" action={<Link className="mode-link" href={homePlanningHref}>Voir le planning</Link>}>
                    {upcomingBookings14.length === 0 ? (
                      <p className="muted">Aucun cours a venir sur 14 jours.</p>
                    ) : (
                      <div className="client-home-coming-list">
                        {upcomingBookings14.slice(0, 3).map((booking) => (
                          <UpcomingLessonRow
                            key={`home-upcoming-${booking.id}`}
                            timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone)}
                            title={booking.session.title}
                            subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone)} · ${booking.owner_display_name} · ${statusLabel(booking.status)}`}
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
                                Voir
                              </a>
                            }
                          />
                        ))}
                      </div>
                    )}
                  </SectionCard>
                </div>

                <aside className="client-home-side">
                  <SectionCard title="Mes forfaits" action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>Voir tout</a>}>
                    {homeSubscriptionsPreview.length === 0 ? (
                      <p className="muted">Aucun carnet / abonnement actif.</p>
                    ) : (
                      <div className="client-forfait-preview-list">
                        {homeSubscriptionsPreview.map((sub) => {
                          const isPack = normalizeStatus(sub.plan.kind) === "PACK";
                          const initialCredits = sub.credits_initial ?? 0;
                          const remainingCredits = sub.credits_remaining ?? 0;
                          const consumedCredits = Math.max(0, initialCredits - remainingCredits);
                          const ratio = initialCredits > 0 ? Math.min(100, Math.round((consumedCredits / initialCredits) * 100)) : 0;
                          const detailLine = isPack
                            ? `Credits restants: ${remainingCredits}/${initialCredits || "?"}`
                            : `${toMoney(sub.plan.kind === "FORFAIT" ? "0" : plans.find((plan) => plan.id === sub.plan.id)?.monthly_price_excl_vat, me.preferred_currency)} / periode · ${paymentMethodLabel(sub.billing_method_code)}`;
                          const expiryLine = sub.ends_at
                            ? `Expiration: ${formatDate(sub.ends_at)}`
                            : sub.next_payment_at
                              ? `Prochain prelevement: ${formatDate(sub.next_payment_at)}`
                              : "Sans date de fin";
                          return (
                            <PlanCard
                              key={`home-sub-${sub.id}`}
                              title={sub.plan.name}
                              typeBadge={<span className="badge">{planKindLabel(sub.plan.kind)}</span>}
                              memberStatus={`${sub.owner_display_name} · ${statusLabel(sub.status)}`}
                              detailLine={detailLine}
                              expiryLine={expiryLine}
                              progressRatio={isPack ? ratio : undefined}
                              progressLabel={isPack ? `Progression: ${consumedCredits}/${initialCredits || "?"}` : undefined}
                              action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })}>Voir details</a>}
                            />
                          );
                        })}
                      </div>
                    )}
                  </SectionCard>

                  <SectionCard title="Dernieres factures" action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices" })}>Voir tout</a>}>
                    {baseInvoiceRows.length === 0 ? (
                      <p className="muted">Aucune facture.</p>
                    ) : (
                      <div className="client-home-due-list">
                        {baseInvoiceRows.slice(0, 3).map((invoice) => (
                          <CompactInvoiceRow
                            key={`home-last-invoice-${invoice.id}`}
                            title={compactId(invoice.invoice_number)}
                            statusBadge={<span className={`status-pill ${statusClass(invoice.status)}`}>{financeStatusLabel(invoice.status)}</span>}
                            meta={`${toMoney(invoice.total_incl_vat, invoice.currency)} · ${formatDate(invoice.issued_at)} · ${invoice.owner_display_name}`}
                            subline={invoice.label}
                            actions={
                              <div className="row client-home-due-actions">
                                <a
                                  className="mode-link"
                                  href={clientInvoiceHref(invoice.id, { inline: true })}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Ouvrir
                                </a>
                                {invoice.download_url ? (
                                  <a className="mode-link" href={invoice.download_url}>
                                    Télécharger
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
                title={hasMultipleVisibleMembers ? "Calendrier famille" : "Calendrier"}
                action={
                  hasMultipleVisibleMembers ? (
                    <div className="row">
                      <a className={`mode-link ${normalizedHomeCalendarView === "FAMILY" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "FAMILY" })}>
                        Vue famille
                      </a>
                      <a className={`mode-link ${normalizedHomeCalendarView === "BY_MEMBER" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "BY_MEMBER" })}>
                        Par enfant
                      </a>
                    </div>
                  ) : undefined
                }
              >
                {homeCalendarRows.length === 0 ? (
                  <p className="muted">Aucun cours a venir sur 14 jours.</p>
                ) : normalizedHomeCalendarView === "BY_MEMBER" ? (
                  <div className="client-home-calendar-groups">
                    {homeCalendarGroups.map(([memberName, rows]) => (
                      <article key={`home-calendar-group-${memberName}`} className="client-home-calendar-group">
                        <h3>{memberName}</h3>
                        <div className="client-home-calendar-list">
                          {rows.slice(0, 3).map((booking) => (
                            <UpcomingLessonRow
                              key={`home-booking-group-${booking.id}`}
                              timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone)}
                              title={booking.session.title}
                              subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone)} · ${statusLabel(booking.status)}`}
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
                                  Voir
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
                        timeLabel={formatTimeInTimezone(booking.session.start_at_utc, timezone)}
                        title={booking.session.title}
                        subtitle={`${formatDateInTimezone(booking.session.start_at_utc, timezone)} · ${booking.owner_display_name} · ${statusLabel(booking.status)}`}
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
                            Voir
                          </a>
                        }
                      />
                    ))}
                  </div>
                )}
              </SectionCard>

              <SectionCard title="Derniers rappels" action={<a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>Voir tout</a>}>
                {newsRows.length === 0 ? (
                  <p className="muted">Aucun rappel récent.</p>
                ) : (
                  <div className="list">
                    {newsRows.map((message) => (
                      <article key={`home-news-${message.id}`} className="item">
                        <strong>{message.subject_preview || "Message"}</strong>
                        <p className="muted">{formatDateTime(message.sent_at || message.scheduled_for_utc)} · {message.channel}</p>
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
                        Payer {toMoney(String(homeDueTotal), me.preferred_currency)}
                      </button>
                    </form>
                  ) : (
                    <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", finance_status: "TO_PAY" })}>
                      Payer {toMoney(String(homeDueTotal), me.preferred_currency)}
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
                    <h2>Planning hebdomadaire</h2>
                    <p className="muted">Une seule grille semaine pour distinguer vos reservations et les disponibilites en ligne.</p>
                  </div>
                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                    🛍️ Offres
                  </a>
                </div>

                <form method="get" className="client-planning-filter-form">
                  <input type="hidden" name="tab" value="planning" />
                  <input type="hidden" name="agenda_view" value="week" />

                  <div className="client-planning-hero">
                    <label className="client-planning-pill client-planning-pill-location">
                      <span>📍 Planning</span>
                      <AutoSubmitSelect
                        name="location_id"
                        defaultValue={selectedLocation}
                        options={[
                          { value: "", label: "Tous les lieux" },
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
                        ariaLabel="Date du planning"
                      />
                    </label>

                    <div className="client-planning-toolbar-actions">
                      <a
                        className="client-planning-reset"
                        href={withUpdatedQuery(rawParams, {
                          tab: "planning",
                          course_type_id: null,
                          location_id: null,
                          coach_id: null,
                          time_bucket: null,
                          planning_slot_filter: null,
                          timezone: me.timezone || DEFAULT_TIMEZONE,
                          agenda_view: "week",
                          agenda_date: todayKeyInTimezone(timezone),
                          booking_owner_id: FAMILY_BOOKING_OWNER,
                        })}
                        title="Reinitialiser"
                      >
                        ↺
                      </a>
                    </div>
                  </div>

                  <DrawerFilters title="⚙ Filtres avances" className={`client-planning-advanced ${advancedFiltersOpen ? "has-active" : ""}`} defaultOpen={advancedFiltersOpen}>
                    <div className="client-planning-advanced-grid">
                      <label>
                        Activite
                        <AutoSubmitSelect
                          name="course_type_id"
                          defaultValue={selectedCourseType}
                          options={[
                            { value: "", label: "Toutes" },
                            ...courseTypes.map((courseType) => ({ value: courseType.id, label: courseType.name })),
                          ]}
                        />
                      </label>

                      <label>
                        Coach
                        <AutoSubmitSelect
                          name="coach_id"
                          defaultValue={selectedCoachId}
                          options={[
                            { value: "", label: "Tous" },
                            ...coachOptions.map((coach) => ({ value: coach.id, label: coach.name })),
                          ]}
                        />
                      </label>

                      <label>
                        Horaire
                        <AutoSubmitSelect
                          name="time_bucket"
                          defaultValue={selectedTimeBucket}
                          options={[
                            { value: "ALL", label: "Toutes heures" },
                            { value: "MORNING", label: "Matin (6h-12h)" },
                            { value: "AFTERNOON", label: "Apres-midi (12h-18h)" },
                            { value: "EVENING", label: "Soir (18h-minuit)" },
                          ]}
                        />
                      </label>

                      <label>
                        Fuseau horaire
                        <AutoSubmitSelect
                          name="timezone"
                          defaultValue={timezone}
                          options={timezoneOptions.map((item) => ({ value: item.value, label: item.label }))}
                        />
                      </label>

                      {hasMultipleVisibleMembers ? (
                      <label>
                        Reservation pour
                          <AutoSubmitSelect
                            name="booking_owner_id"
                            defaultValue={bookingOwnerId}
                            options={[
                              { value: FAMILY_BOOKING_OWNER, label: "Toute la famille" },
                              ...members.map((member) => ({ value: member.id, label: member.display_name })),
                            ]}
                          />
                        </label>
                      ) : (
                        <input type="hidden" name="booking_owner_id" value={bookingOwnerId} />
                      )}

                      <label>
                        Statut creneaux
                        <AutoSubmitSelect
                          name="planning_slot_filter"
                          defaultValue={planningSlotFilter}
                          options={[
                            { value: "ALL", label: "Tous" },
                            { value: "AVAILABLE", label: "Disponibles uniquement" },
                            { value: "ALREADY_BOOKED", label: "Deja reserves" },
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
                      <small>{hasMultipleVisibleMembers ? "Une seule grille mobile-first pour suivre les reservations famille et les creneaux reservables." : "Une seule grille mobile-first pour suivre vos reservations et les creneaux reservables."}</small>
                    </div>
                    <div className="client-week-toolbar-actions">
                      <a
                        className="client-date-nav-btn"
                        href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: shiftDateKeyByDays(agendaDate, -7), agenda_view: "week" })}
                        aria-label="Semaine precedente"
                      >
                        ←
                      </a>
                      <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: todayKeyInTimezone(timezone), agenda_view: "week" })}>
                        Aujourd'hui
                      </a>
                      <a
                        className="client-date-nav-btn"
                        href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: shiftDateKeyByDays(agendaDate, 7), agenda_view: "week" })}
                        aria-label="Semaine suivante"
                      >
                        →
                      </a>
                    </div>
                  </div>
                  <div className="client-week-legend">
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch reserved" />
                      Mes reservations
                    </span>
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch available" />
                      Reserver ou payer
                    </span>
                    <span className="client-week-legend-item">
                      <span className="client-week-legend-swatch full" />
                      Ferme ou complet
                    </span>
                  </div>
                </div>
              </Card>

              <Card className="client-available-section client-week-planning-board">
                <div className="row spread">
                  <h2>Ma semaine de reservation</h2>
                  <span className="badge">{agendaSessionCount}</span>
                </div>
                <p className="muted">Vos creneaux reserves et les disponibilites en ligne sont reunis sur la meme grille.</p>
                <form method="get" className="client-planning-quick-filter-form">
                  <input type="hidden" name="tab" value="planning" />
                  <input type="hidden" name="agenda_view" value="week" />
                  <input type="hidden" name="agenda_date" value={agendaDate} />
                  <input type="hidden" name="location_id" value={selectedLocation} />
                  <input type="hidden" name="course_type_id" value={selectedCourseType} />
                  <input type="hidden" name="coach_id" value={selectedCoachId} />
                  <input type="hidden" name="time_bucket" value={selectedTimeBucket} />
                  <input type="hidden" name="timezone" value={timezone} />
                  <input type="hidden" name="booking_owner_id" value={bookingOwnerId} />
                  <label className="client-planning-quick-filter-label">
                    <span>Afficher</span>
                    <AutoSubmitSelect
                      name="planning_slot_filter"
                      defaultValue={planningSlotFilter}
                      options={[
                        { value: "ALL", label: "Tous les creneaux" },
                        { value: "AVAILABLE", label: "A reserver maintenant" },
                        { value: "ALREADY_BOOKED", label: "Mes reservations" },
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

                        {daySessions.length === 0 ? <p className="muted agenda-empty">Aucun cours</p> : null}

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
                              session_id: session.id,
                              session_member_id: null,
                              ok: null,
                              error: null,
                              session_ok: null,
                              session_error: null,
                            });
                            const reservationFlagLabel =
                              sessionState.familyBookings.length > 1
                                ? `${sessionState.familyBookings.length} reservations`
                                : null;
                            const bookingBadges = sessionState.familyBookings.filter((booking) =>
                              isAlreadyReservedByMember(booking.status) || isPendingPaymentBooking(booking.status),
                            );
                            const bookingSummaryLabel =
                              bookingBadges.length > 1
                                ? `${bookingBadges.length} reservations famille`
                                : bookingBadges.length === 1
                                  ? bookingOwnerId === FAMILY_BOOKING_OWNER
                                    ? isPendingPaymentBooking(bookingBadges[0].status)
                                      ? `${bookingBadges[0].owner_display_name} · Paiement`
                                      : `Reserve pour ${bookingBadges[0].owner_display_name}`
                                    : isPendingPaymentBooking(bookingBadges[0].status)
                                      ? "Paiement en attente"
                                      : "Reserve"
                                  : null;
                            const cardStatusClass = planningStatusClass(sessionState.cardStatusLabel);
                            const showPlanningStateBadge =
                              !sessionState.alreadyReserved && shouldRenderPlanningStateBadge(sessionState.cardStatusLabel);
                            const sessionCtaLabel = sessionState.alreadyReserved
                              ? sessionState.actionableMembers.length > 0
                                ? "Reserver"
                                : "Voir la reservation"
                              : sessionState.paymentPending
                                ? "Finaliser le paiement"
                                : sessionState.canCheckout
                                  ? sessionState.actionLabel
                                  : sessionState.isFull
                                  ? "Complet"
                                  : "Voir details";

                            return (
                              <a
                                key={session.id}
                                className="client-session-link"
                                href={openDetailsHref}
                                aria-label={`Ouvrir le detail du creneau ${session.title}`}
                              >
                                <article
                                  className={`client-session-card ${compactAgendaCard ? "client-session-card-compact" : ""} ${sessionState.alreadyReserved ? "client-session-card-booked" : ""} ${statusClass(session.status)}`}
                                >
                                  {!compactAgendaCard ? (
                                    <div className="client-session-timebox">
                                      <span aria-hidden="true">🕒</span>
                                      <strong>{formatTimeInTimezone(session.start_at_utc, timezone)}</strong>
                                      <small>{formatTimeInTimezone(session.end_at_utc, timezone)}</small>
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
                                    {compactAgendaCard ? <small className="event-meta">🕒 {formatTimeInTimezone(session.start_at_utc, timezone)} - {formatTimeInTimezone(session.end_at_utc, timezone)}</small> : null}
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

              {selectedSession ? (
                <section className="modal-overlay">
                  <article className="modal-panel modal-client-session-details">
                    <header className="client-session-modal-header">
                      <a
                        className="modal-close-x"
                        href={selectedSessionCloseHref}
                        aria-label="Fermer le detail du creneau"
                      >
                        ×
                      </a>
                      <h2>{selectedSession.title}</h2>
                      <p className="muted">
                        {formatDateTimeInTimezone(selectedSession.start_at_utc, timezone)} - {formatTimeInTimezone(selectedSession.end_at_utc, timezone)}
                      </p>
                      <div className="row">
                        <span className="occ-badge">
                          {selectedSession.booked_count}/{selectedSession.capacity_max}
                        </span>
                        {selectedSessionModalStatusLabel ? (
                          <span className={`status-badge ${planningStatusClass(selectedSessionModalStatusLabel)}`}>
                            {selectedSessionModalStatusLabel}
                          </span>
                        ) : null}
                        {!selectedSession.online_booking_enabled ? <span className="badge">Reservation en ligne fermee</span> : null}
                      </div>
                    </header>

                    <section className="modal-card client-session-modal-grid">
                      <article className="item">
                        <small className="muted">Coach</small>
                        <p>
                          {sessionProfessorName(selectedSession)}
                        </p>
                      </article>
                      <article className="item">
                        <small className="muted">Lieu</small>
                        <p>{selectedSession.location.name}</p>
                      </article>
                      <article className="item">
                        <small className="muted">Activite</small>
                        <p>{selectedSession.course_type.name}</p>
                      </article>
                      <article className="item">
                        <small className="muted">Duree</small>
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
                        <small className="muted">Description</small>
                        <p>{selectedSession.description}</p>
                      </section>
                    ) : null}

                    {selectedSession.zoom_link ? (
                      <section className="modal-card">
                        <small className="muted">Lien Zoom</small>
                        <p>
                          <a href={selectedSession.zoom_link} target="_blank" rel="noreferrer">
                            {selectedSession.zoom_link}
                          </a>
                        </p>
                      </section>
                    ) : null}

                    {selectedSessionPlanningState ? (
                      <section className="modal-card client-session-modal-state">
                        <div className="row spread">
                          <div className="client-session-modal-state-copy">
                            <small className="muted">Prochaine etape</small>
                            <p className="client-session-modal-state-title">
                              {selectedSessionStateTitle}
                            </p>
                            <p>{selectedSessionStateDescription}</p>
                          </div>
                          {selectedSessionModalStatusLabel ? (
                            <span className={`status-badge ${planningStatusClass(selectedSessionModalStatusLabel)}`}>
                              {selectedSessionModalStatusLabel}
                            </span>
                          ) : null}
                        </div>
                    {selectedSessionCoverageLabel ? (
                      <div className="client-session-modal-state-meta">
                        <span className="badge">{selectedSessionCoverageLabel}</span>
                        {selectedReservationMemberOption ? (
                          <span className="badge">{`Pour ${selectedReservationMemberOption.member_display_name}`}</span>
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                ) : null}

                    {reservationOptionsMembers.length > 1 ? (
                      <section className="modal-card">
                        <div className="client-session-member-picker">
                          <div className="client-session-member-picker-heading">
                            <small className="muted">Membre concerne</small>
                            <p>Choisissez le membre a inscrire. Nous adaptons ensuite automatiquement le parcours.</p>
                          </div>
                          <div className="client-session-member-grid">
                            {reservationOptionsMembers.map((option) => {
                              const isSelected = option.member_id === selectedReservationMemberId;
                              const selectionHref = withUpdatedQuery(rawParams, {
                                tab: "planning",
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
                                    <span className="client-session-member-selected-label">Membre selectionne</span>
                                  ) : null}
                                  <div className="client-session-member-card-head">
                                    <strong>{option.member_display_name}</strong>
                                    <div className="client-session-member-card-badges">
                                      <span className={`status-badge ${planningStatusClass(option.status_label)}`}>
                                        {option.status_label}
                                      </span>
                                    </div>
                                  </div>
                                  <small className="muted">{option.reason || option.action_label}</small>
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
                        <strong>Autres options disponibles dans la famille</strong>
                        <p>
                          Le paiement en attente concerne seulement {selectedReservationMemberOption.member_display_name}. Vous pouvez
                          toujours choisir un autre membre pour voir ses formules compatibles ou son paiement unitaire.
                        </p>
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

                    {selectedReservationMemberOption &&
                    selectedSessionFormulaOptions.length > 0 &&
                    selectedSessionEffectiveActionCode !== "BOOK_WITH_CREDIT" ? (
                      <section className="modal-card">
                        <div className="client-session-choice-heading">
                          <strong>
                            {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                              ? `${selectedSessionPurchaseChoiceCount} choix disponibles pour ${selectedReservationMemberOption.member_display_name}`
                              : `Formules compatibles pour ${selectedReservationMemberOption.member_display_name}`}
                          </strong>
                          <small className="muted">
                            {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                              ? "Choisissez librement une formule ou le paiement unitaire. Ces options ont le meme niveau."
                              : "Choisissez la formule la plus adaptee pour confirmer la reservation."}
                          </small>
                        </div>
                        <div className="client-plan-grid client-session-formula-grid client-session-choice-grid">
                          {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT" && selectedSessionDirectPaymentAmount ? (
                            <article className="modal-card client-plan-card client-session-formula-card client-session-choice-card">
                              <div className="client-session-formula-copy">
                                <div className="client-session-choice-card-head">
                                  <strong>Paiement unitaire</strong>
                                  <span className="badge">Reservation immediate</span>
                                </div>
                                <p className="muted">Reglez uniquement ce creneau, sans achat de formule.</p>
                                <small className="muted">
                                  {`Achat unitaire · ${toMoney(
                                    selectedSessionDirectPaymentAmount,
                                    selectedSessionDirectPaymentCurrency,
                                  )}`}
                                </small>
                              </div>
                              <form action={submitPublicSessionCheckoutAction} className="client-session-formula-action">
                                <input type="hidden" name="session_id" value={selectedSession.id} />
                                <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                                <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                  {`Payer a l unite · ${toMoney(
                                    selectedSessionDirectPaymentAmount,
                                    selectedSessionDirectPaymentCurrency,
                                  )}`}
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
                                  <span className="badge">Formule</span>
                                </div>
                                {formula.description ? <p className="muted">{formula.description}</p> : null}
                                <small className="muted">
                                  {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels].filter(Boolean).join(" · ")}
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
                                    ? `Acheter pour ${selectedReservationMemberOption.member_display_name} · ${toMoney(formula.price_ttc, formula.currency)}`
                                    : `Acheter la formule pour ${selectedReservationMemberOption.member_display_name}`}
                                </button>
                              </form>
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {selectedReservationMemberOption &&
                    selectedSessionFormulaOptions.length > 0 &&
                    selectedSessionEffectiveActionCode === "BOOK_WITH_CREDIT" ? (
                      <section className="modal-card client-session-secondary-options">
                        <details>
                          <summary>
                            <span>Autres options d achat</span>
                            <small className="muted">
                              {selectedSessionPurchaseChoiceCount > 0
                                ? `${selectedSessionPurchaseChoiceCount} option${selectedSessionPurchaseChoiceCount > 1 ? "s" : ""} secondaire${selectedSessionPurchaseChoiceCount > 1 ? "s" : ""}`
                                : "Options alternatives"}
                            </small>
                          </summary>
                          <div className="client-session-secondary-options-body">
                            <div className="client-session-choice-heading">
                              <strong>{`Autres options pour ${selectedReservationMemberOption.member_display_name}`}</strong>
                              <small className="muted">
                                Votre credit reste la meilleure option. Vous pouvez tout de meme acheter une formule ou payer a l unite.
                              </small>
                            </div>
                            <div className="client-plan-grid client-session-formula-grid client-session-choice-grid">
                              {selectedSessionDirectPaymentAmount ? (
                                <article className="modal-card client-plan-card client-session-formula-card client-session-choice-card">
                                  <div className="client-session-formula-copy">
                                    <div className="client-session-choice-card-head">
                                      <strong>Paiement unitaire</strong>
                                      <span className="badge">Option secondaire</span>
                                    </div>
                                    <p className="muted">Reglez ce creneau sans utiliser votre credit disponible.</p>
                                    <small className="muted">
                                      {`Achat unitaire · ${toMoney(
                                        selectedSessionDirectPaymentAmount,
                                        selectedSessionDirectPaymentCurrency,
                                      )}`}
                                    </small>
                                  </div>
                                  <form action={submitPublicSessionCheckoutAction} className="client-session-formula-action">
                                    <input type="hidden" name="session_id" value={selectedSession.id} />
                                    <input type="hidden" name="booking_user_id" value={selectedReservationMemberOption.member_id} />
                                    <input type="hidden" name="planning_return_to" value={selectedSessionReturnTo} />
                                    <input type="hidden" name="checkout_return_to" value={selectedSessionCheckoutReturnTo} />
                                    <button type="submit" className="client-session-secondary-button client-session-choice-button">
                                      {`Payer a l unite · ${toMoney(
                                        selectedSessionDirectPaymentAmount,
                                        selectedSessionDirectPaymentCurrency,
                                      )}`}
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
                                      <span className="badge">Formule</span>
                                    </div>
                                    {formula.description ? <p className="muted">{formula.description}</p> : null}
                                    <small className="muted">
                                      {[formula.formula_type, formula.frequency_label, ...formula.restriction_labels].filter(Boolean).join(" · ")}
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
                                        ? `Acheter pour ${selectedReservationMemberOption.member_display_name} · ${toMoney(formula.price_ttc, formula.currency)}`
                                        : `Acheter la formule pour ${selectedReservationMemberOption.member_display_name}`}
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
                        Retour au planning
                      </a>
                      <div className="client-session-modal-action-list">
                        {selectedSessionHasBooking && selectedReservationMemberOption?.booking_id ? (
                          <div className="client-session-modal-booking-actions">
                            <form action={cancelBookingAction}>
                              <input type="hidden" name="booking_id" value={selectedReservationMemberOption.booking_id} />
                              <input type="hidden" name="return_to" value={selectedSessionReturnTo} />
                              <button className="client-session-cancel-button" type="submit">
                                {`Annuler pour ${selectedReservationMemberOption.member_display_name}`}
                              </button>
                            </form>
                            {(selectedReservationMemberOption.booking_status || "").toUpperCase() === "BOOKED" ? (
                              <a className="mode-link client-session-calendar-link" href={`/client/bookings/${selectedReservationMemberOption.booking_id}/calendar`}>
                                {`Ajouter a l agenda pour ${selectedReservationMemberOption.member_display_name}`}
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
                                  )}`
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
                              {`Payer a l unite · ${toMoney(
                                selectedSessionDirectPaymentAmount,
                                selectedSessionDirectPaymentCurrency,
                              )}`}
                            </button>
                          </form>
                        ) : null}
                        {selectedReservationMemberOption && selectedSessionEffectiveActionCode === "UNAVAILABLE" ? (
                          <div className="stack-sm">
                            <span className="badge">
                              {selectedReservationMemberOption.reason || "Reservation non disponible pour ce creneau"}
                            </span>
                          </div>
                        ) : null}
                        {selectedSessionRequiresMemberChoice ? (
                          <div className="stack-sm">
                            <span className="badge">Choisissez d abord le membre a inscrire pour voir l option la plus adaptee.</span>
                          </div>
                        ) : null}
                        {!selectedReservationMemberOption && !selectedSessionRequiresMemberChoice ? (
                          <div className="stack-sm">
                            <span className="badge">
                              {selectedSessionPlanningState?.contextLine || "Reservation non disponible pour ce creneau"}
                            </span>
                            {!selectedSessionPlanningState?.hasDirectPayment &&
                            selectedSessionPlanningState?.statusLabel === "Aucune formule" ? (
                              <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                                Voir les offres compatibles
                              </a>
                            ) : null}
                          </div>
                        ) : null}
                        {selectedReservationMemberOption &&
                        ["BUY_FORMULA", "BUY_FORMULA_OR_PAY_UNIT"].includes(selectedSessionEffectiveActionCode) ? (
                          <div className="client-session-inline-note">
                            <small className="muted">
                              {selectedSessionEffectiveActionCode === "BUY_FORMULA_OR_PAY_UNIT"
                                ? "Vous pouvez reserver tout de suite a l unite ou choisir une formule plus avantageuse."
                                : "Selectionnez une formule pour activer des credits puis confirmer la reservation."}
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
                    <h2>Mes cours en ligne</h2>
                    <p className="muted">Retrouvez ici les contenus de solfege rattaches a vos activites actives.</p>
                  </div>
                  <span className="badge">{filteredContentCourses.length} cours</span>
                </div>
                <form method="get" className="client-content-filter-form">
                  <input type="hidden" name="tab" value="courses" />
                  {hasMultipleVisibleMembers ? (
                    <label className="client-content-member-filter">
                      <span>Afficher pour</span>
                      <AutoSubmitSelect
                        name="content_member_id"
                        defaultValue={contentMemberFilter}
                        options={[
                          { value: "ALL", label: "Toute la famille" },
                          ...members.map((member) => ({ value: member.id, label: member.display_name })),
                        ]}
                      />
                    </label>
                  ) : null}
                </form>
              </Card>

              <div className="client-content-layout">
                <SectionCard
                  title="Cours accessibles"
                  className="client-content-course-list-card"
                  action={selectedContentCourse ? <span className="badge">{courseAudienceLabel(selectedContentCourse)}</span> : undefined}
                >
                  {filteredContentCourses.length === 0 ? (
                    <div className="client-content-empty-state">
                      <strong>Aucun cours en ligne disponible pour le moment.</strong>
                      <p className="muted">
                        Des qu une activite en ligne avec contenu pedagogique sera active sur votre compte, elle apparaitra ici.
                      </p>
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
                              <span className="badge">{totalLessons} lecons</span>
                            </div>
                            {course.summary ? <p>{course.summary}</p> : null}
                            <div className="client-content-course-card-meta">
                              <span>{courseAudienceLabel(course)}</span>
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
                  title={selectedContentCourse ? selectedContentCourse.title : "Selectionnez un cours"}
                  className="client-content-course-detail-card"
                  action={selectedContentCourse?.level_code ? <span className="badge">{selectedContentCourse.level_code}</span> : undefined}
                >
                  {!selectedContentCourse ? (
                    <div className="client-content-empty-state">
                      <strong>Choisissez un cours pour afficher son contenu.</strong>
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
                            Accessible via{" "}
                            {selectedContentCourse.member_accesses
                              .flatMap((access) => access.course_type_names)
                              .filter((value, index, array) => array.indexOf(value) === index)
                              .join(", ")}
                          </p>
                        </div>
                        {selectedContentCourse.cover_image_url ? (
                          <img
                            className="client-content-course-cover"
                            src={selectedContentCourse.cover_image_url}
                            alt={`Illustration ${selectedContentCourse.title}`}
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
                                <h3>Lecons</h3>
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
                                    Ouvrir la video
                                  </a>
                                ) : null}
                                {selectedContentLesson.lesson.resource_url ? (
                                  <a className="mode-link" href={selectedContentLesson.lesson.resource_url} target="_blank" rel="noreferrer">
                                    Ressource jointe
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
                                  <strong>Le contenu detaille de cette lecon n est pas encore disponible.</strong>
                                  <p className="muted">Le titre et les ressources sont deja synchronises depuis WordPress / LearnDash.</p>
                                </div>
                              )}
                            </>
                          ) : (
                            <div className="client-content-empty-state">
                              <strong>Ce cours ne contient pas encore de lecon publiee.</strong>
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
                <h2>Mes reservations</h2>
                <span className="badge">{reservationRows.length}</span>
              </div>

              <form method="get" className="client-filter-grid client-reservation-filters">
                <input type="hidden" name="tab" value="reservations" />
                <label>
                  Perimetre
                  <select name="reservation_scope" defaultValue={reservationScope}>
                    <option value="CURRENT">En cours</option>
                    <option value="HISTORY">Historique</option>
                    <option value="ALL">Toutes</option>
                  </select>
                </label>
                <label>
                  Membre
                  <select name="member_id" defaultValue={selectedMemberFilter}>
                    <option value="ALL">{hasMultipleVisibleMembers ? "Tous les membres" : "Mon compte"}</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <DrawerFilters title="Filtres avancés" className="client-reservation-drawer">
                  <label>
                    Statut
                    <select name="reservation_status" defaultValue={reservationStatusFilter}>
                      <option value="">Tous</option>
                      {allBookingStatuses.map((status) => (
                        <option key={status} value={status}>
                          {statusLabel(status)}
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
                <p className="muted">Aucune reservation sur ce filtre.</p>
              ) : (
                <>
                <div className="table-wrap client-desktop-table">
                  <table className="data-table client-data-table">
                    <thead>
                      <tr>
                        <th>Membre</th>
                        <th>Cours</th>
                        <th>Debut</th>
                        <th>Montant</th>
                        <th>Statut</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {reservationRows.map((booking) => {
                        const canCancel = ["BOOKED", "WAITLISTED"].includes(normalizeStatus(booking.status));
                        return (
                          <tr key={booking.id}>
                            <td>{booking.owner_display_name}</td>
                            <td>{booking.session.title}</td>
                            <td>{formatDateTimeInTimezone(booking.session.start_at_utc, timezone)}</td>
                            <td>{toMoney(booking.total_incl_vat_snapshot, booking.currency_snapshot)}</td>
                            <td>
                              <span className={`status-pill ${statusClass(booking.status)}`}>{statusLabel(booking.status)}</span>
                            </td>
                            <td>
                              {canCancel ? (
                                <form action={cancelBookingAction}>
                                  <input type="hidden" name="booking_id" value={booking.id} />
                                  <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "reservations" })} />
                                  <button className="danger" type="submit" title="Annuler">
                                    🗑️
                                  </button>
                                </form>
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
                    const canCancel = ["BOOKED", "WAITLISTED"].includes(normalizeStatus(booking.status));
                    return (
                      <article key={`${booking.id}-mobile`} className="item client-mobile-card">
                        <div className="row spread">
                          <strong>{booking.owner_display_name}</strong>
                          <span className={`status-pill ${statusClass(booking.status)}`}>{statusLabel(booking.status)}</span>
                        </div>
                        <p className="muted">{booking.session.title}</p>
                        <p className="muted">{formatDateTimeInTimezone(booking.session.start_at_utc, timezone)}</p>
                        <div className="row spread">
                          <strong>{toMoney(booking.total_incl_vat_snapshot, booking.currency_snapshot)}</strong>
                          {canCancel ? (
                            <form action={cancelBookingAction}>
                              <input type="hidden" name="booking_id" value={booking.id} />
                              <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "reservations" })} />
                              <button className="ghost" type="submit">Annuler</button>
                            </form>
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
                  <h2>Mes forfaits</h2>
                  <span className="badge">{plans.length}</span>
                </div>
                <p className="muted">Pour reserver un nouveau creneau, ouvrez l onglet Planning puis touchez un creneau disponible.</p>
                <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "planning" })}>Aller au planning</a>

                <form method="get" className="row">
                  <input type="hidden" name="tab" value="offers" />
                  <label>
                    Beneficiaire
                    <select name="purchase_user_id" defaultValue={selectedPurchaseOwner}>
                      {members.map((member) => (
                        <option key={member.id} value={member.id}>
                          {member.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Date de demarrage
                    <input type="date" name="purchase_start_date" defaultValue={selectedPurchaseStartDate} />
                  </label>
                  <button type="submit">Afficher les offres</button>
                </form>
              </Card>

              <Card>
                <div className="row spread">
                  <h3>Abonnements et carnets actifs</h3>
                  <span className="badge">{visibleSelectedOwnerSubscriptions.length}</span>
                </div>
                {visibleSelectedOwnerSubscriptions.length === 0 ? (
                  <p className="muted">Aucun carnet / abonnement actif.</p>
                ) : (
                  <div className="list client-forfait-card-list">
                    {visibleSelectedOwnerSubscriptions.map((sub) => {
                      const isPack = normalizeStatus(sub.plan.kind) === "PACK";
                      const initialCredits = sub.credits_initial ?? 0;
                      const remainingCredits = sub.credits_remaining ?? 0;
                      const consumedCredits = Math.max(0, initialCredits - remainingCredits);
                      const ratio = initialCredits > 0 ? Math.min(100, Math.round((consumedCredits / initialCredits) * 100)) : 0;
                      const planPrice = plans.find((plan) => plan.id === sub.plan.id)?.monthly_price_excl_vat ?? null;
                      return (
                        <article key={`forfait-card-${sub.id}`} className="item client-forfait-card">
                          <div className="row spread">
                            <div>
                              <strong>{sub.plan.name}</strong>
                              <p className="muted">{sub.owner_display_name}</p>
                            </div>
                            <span className="badge">{planKindLabel(sub.plan.kind)}</span>
                          </div>
                          <div className="row spread">
                            <span className={`status-pill ${statusClass(sub.status)}`}>{statusLabel(sub.status)}</span>
                            <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: sub.id })}>
                              Voir details
                            </a>
                          </div>
                          {isPack ? (
                            <>
                              <div className="client-progress">
                                <div className="client-progress-bar" style={{ width: `${ratio}%` }} />
                              </div>
                              <p className="muted">Credits restants: {remainingCredits}/{initialCredits || "?"}</p>
                            </>
                          ) : (
                            <p className="muted">
                              {toMoney(sub.plan.kind === "FORFAIT" ? "0" : planPrice, me.preferred_currency)} / mois · {paymentMethodLabel(sub.billing_method_code)}
                            </p>
                          )}
                          <p className="muted">
                            {sub.ends_at ? `Expiration: ${formatDate(sub.ends_at)}` : sub.next_payment_at ? `Prochain prelevement: ${formatDate(sub.next_payment_at)}` : "Reconduction en cours"}
                          </p>
                        </article>
                      );
                    })}
                  </div>
                )}
              </Card>

              {selectedOfferSubscription ? (
                <Card>
                  <div className="row spread">
                    <h3>Detail forfait</h3>
                    <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "offers", offer_detail_id: null })}>
                      Fermer
                    </a>
                  </div>
                  <div className="list">
                    <article className="item">
                      <h4>Contrat</h4>
                      <p className="muted">
                        Identifiant: {compactId(selectedOfferSubscription.id)}{" "}
                        <CopyIdButton value={selectedOfferSubscription.id} label="Copier" />
                      </p>
                    </article>
                    <article className="item">
                      <h4>Formule</h4>
                      <p className="muted">{selectedOfferSubscription.plan.name} · {planKindLabel(selectedOfferSubscription.plan.kind)}</p>
                    </article>
                    <article className="item">
                      <h4>Tarif</h4>
                      <p className="muted">
                        {toMoney(
                          selectedOfferSubscription.plan.kind === "FORFAIT"
                            ? "0"
                            : plans.find((plan) => plan.id === selectedOfferSubscription.plan.id)?.monthly_price_excl_vat,
                          me.preferred_currency,
                        )}{" "}
                        / periode
                      </p>
                    </article>
                    <article className="item">
                      <h4>Moyen de paiement</h4>
                      <p className="muted">{paymentMethodLabel(selectedOfferSubscription.billing_method_code)}</p>
                    </article>
                    <article className="item">
                      <h4>Restrictions d acces</h4>
                      <p className="muted">
                        {selectedOfferSubscription.entitlement_course_type_names.length > 0
                          ? `${selectedOfferSubscription.entitlement_course_type_names.length} activite(s) autorisee(s)`
                          : "Aucune restriction declarative"}
                      </p>
                      <div className="client-chip-row">
                        {selectedOfferSubscription.entitlement_course_type_names.slice(0, 8).map((name) => (
                          <span key={`restriction-${selectedOfferSubscription.id}-${name}`} className="badge">
                            {name}
                          </span>
                        ))}
                        {selectedOfferSubscription.entitlement_course_type_names.length > 8 ? (
                          <span className="badge">+{selectedOfferSubscription.entitlement_course_type_names.length - 8}</span>
                        ) : null}
                      </div>
                    </article>
                    <article className="item">
                      <h4>Factures associees</h4>
                      {selectedOfferInvoices.length === 0 ? (
                        <p className="muted">Aucune facture associee.</p>
                      ) : (
                        <div className="list client-mobile-list">
                          {selectedOfferInvoices.slice(0, 6).map((invoice) => (
                            <ListRow
                              key={`offer-invoice-${invoice.id}`}
                              title={invoice.invoice_number}
                              subtitle={`${formatDate(invoice.issued_at)} · ${toMoney(invoice.total_incl_vat, invoice.currency)}`}
                              right={
                                <div className="row">
                                  <a
                                    className="mode-link"
                                    href={clientInvoiceHref(invoice.id, { inline: true })}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Ouvrir
                                  </a>
                                  {invoice.download_url ? (
                                    <a className="mode-link" href={invoice.download_url}>
                                      PDF
                                    </a>
                                  ) : null}
                                </div>
                              }
                            />
                          ))}
                        </div>
                      )}
                    </article>
                  </div>
                </Card>
              ) : null}

              <section className="grid cols-2">
                <Card>
                  <h3>Abonnements et credits</h3>
                  <div className="list">
                    {visibleSelectedOwnerSubscriptions.map((sub) => (
                      <article key={sub.id} className="item">
                        <h3>{sub.plan.name}</h3>
                        <small className="muted">
                          Membre: {sub.owner_display_name} | Statut: {statusLabel(sub.status)} |{" "}
                          {sub.plan.kind === "SUBSCRIPTION"
                            ? "Abonnement (tarification au forfait)"
                            : sub.plan.kind === "FORFAIT"
                              ? "Forfait (facturation au reel)"
                            : `Credits: ${sub.credits_remaining ?? 0}/${sub.credits_initial ?? sub.credits_remaining ?? 0}`}
                        </small>
                        <small className="muted">Debut: {formatDate(sub.started_at)} {sub.ends_at ? `| Fin: ${formatDate(sub.ends_at)}` : ""}</small>
                      </article>
                    ))}
                    {selectedOwnerSubscriptions.length === 0 ? (
                      <p className="muted">Aucun abonnement/carnet pour ce membre.</p>
                    ) : null}
                    {selectedOwnerSubscriptions.length > 0 && visibleSelectedOwnerSubscriptions.length === 0 ? (
                      <p className="muted">Aucun credit positif sur les carnets de ce membre.</p>
                    ) : null}
                  </div>
                </Card>

                <Card>
                  <h3>Credits cumules (positifs)</h3>
                  <div className="list">
                    {membersWithPositiveCredits.map((member) => (
                      <article key={`credit-${member.id}`} className="item row spread">
                        <span>{member.display_name}</span>
                        <strong>{totalCreditsByMember.get(member.id) ?? 0}</strong>
                      </article>
                    ))}
                    {membersWithPositiveCredits.length === 0 ? (
                      <p className="muted">Aucun credit positif a afficher.</p>
                    ) : null}
                  </div>
                </Card>
              </section>

              <Card>
                <h3>Catalogue des offres</h3>
                <div className="client-plan-grid">
                  {plans.map((plan) => (
                    <article key={plan.id} className="item client-plan-card">
                      <div>
                        <h3>{plan.name}</h3>
                        <p className="muted">{plan.kind === "PACK" ? "Carnet / seances" : plan.kind === "FORFAIT" ? "Forfait" : "Abonnement"}</p>
                        <p className="muted">
                          {plan.kind === "FORFAIT"
                            ? "Facturation: au reel selon planning"
                            : `Credits: ${plan.credits_count ?? "illimite"}`}{" "}
                          | Prix base: {toMoney(plan.monthly_price_excl_vat, plan.currency_code ?? me.preferred_currency)}
                        </p>
                      </div>
                      <form action={purchasePlanAction}>
                        <input type="hidden" name="plan_id" value={plan.id} />
                        <input type="hidden" name="purchase_user_id" value={selectedPurchaseOwner} />
                        <input type="hidden" name="start_date" value={selectedPurchaseStartDate} />
                        <button type="submit" title="Souscrire cette offre">Choisir</button>
                      </form>
                    </article>
                  ))}
                  {plans.length === 0 ? <p className="muted">Aucune offre active.</p> : null}
                </div>
              </Card>
            </>
          ) : null}

          {tab === "finance" ? (
            <>
              <SectionCard
                title="Finance"
                className="client-finance-shell"
                action={
                  financeDueTotal > 0 ? (
                    primaryDuePayableRow || primaryDuePaymentUrl ? (
                      <form action={openClientPaymentCheckoutAction}>
                        {primaryDuePayableRow ? <input type="hidden" name="payment_id" value={primaryDuePayableRow.id} /> : null}
                        {primaryDuePaymentUrl ? <input type="hidden" name="payment_url" value={primaryDuePaymentUrl} /> : null}
                        <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })} />
                        <button type="submit" className="client-pay-cta">
                          Payer {toMoney(String(financeDueTotal), me.preferred_currency)}
                        </button>
                      </form>
                    ) : (
                      <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                        Payer {toMoney(String(financeDueTotal), me.preferred_currency)}
                      </a>
                    )
                  ) : null
                }
              >
                <section className="client-kpi-grid">
                  <KPIBlock label="A payer" value={toMoney(String(financeDueTotal), me.preferred_currency)} helper="Factures en attente" />
                  <KPIBlock label="Paye" value={toMoney(String(paidTotal), me.preferred_currency)} helper="Reglements confirmes" />
                  <KPIBlock
                    label="Transactions en attente"
                    value={toMoney(String(pendingTransactionsTotal), me.preferred_currency)}
                    helper="Tous mouvements non soldes"
                  />
                </section>
                <p className="muted">Comptes arrêtés au {formatDate(financeAsOfDateKey)}.</p>

                <div className="client-finance-toolbar">
                  <div className="client-finance-tab-scroll">
                    <a
                      className={`mode-link ${financeView === "transactions" ? "active" : ""}`}
                      href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions", invoice_id: null, finance_page: "1" })}
                    >
                      Transactions
                    </a>
                    <a
                      className={`mode-link ${financeView === "invoices" ? "active" : ""}`}
                      href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_page: "1" })}
                    >
                      Factures
                    </a>
                  </div>

                  <DrawerFilters title="Filtres" className="client-finance-drawer">
                    <form method="get" className="client-finance-drawer-form">
                      <input type="hidden" name="tab" value="finance" />
                      <input type="hidden" name="finance_view" value={financeView} />
                      <input type="hidden" name="invoice_id" value="" />
                      <input type="hidden" name="finance_page" value="1" />
                      <label>
                        Membre
                        <select name="member_id" defaultValue={selectedMemberFilter}>
                          <option value="ALL">{hasMultipleVisibleMembers ? "Tous les membres" : "Mon compte"}</option>
                          {members.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Statut
                        <select name="finance_status" defaultValue={financeStatusFilter}>
                          {visibleFinanceStatusOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Periode
                        <select name="finance_period" defaultValue={financePeriodFilter}>
                          <option value="ALL">Toutes periodes</option>
                          <option value="LAST_30_DAYS">30 derniers jours</option>
                          <option value="LAST_90_DAYS">3 derniers mois</option>
                          <option value="LAST_365_DAYS">Derniere annee</option>
                        </select>
                      </label>
                      <label>
                        Date d'arrete
                        <input type="date" name="finance_as_of" defaultValue={financeAsOfDateKey} />
                      </label>
                      <label>
                        Lignes / page
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
                          Type
                          <select name="finance_source" defaultValue={financeSourceFilter}>
                            <option value="ALL">Tous types</option>
                            {allPaymentSources.map((source) => (
                              <option key={source} value={source}>
                                {sourceLabel(source)}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <input type="hidden" name="finance_source" value={financeSourceFilter} />
                      )}
                      <div className="row client-finance-drawer-actions">
                        <button type="submit">Appliquer</button>
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
                          Reinitialiser
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
                        Tous
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
                    <span className="badge active">{members[0]?.display_name ?? "Mon compte"}</span>
                  )}
                  {financeStatusFilter !== "ALL" ? <span className="badge">Statut: {visibleFinanceStatusOptions.find((item) => item.value === financeStatusFilter)?.label}</span> : null}
                  {financePeriodFilter !== "ALL" ? <span className="badge">Periode: {financePeriodLabel(financePeriodFilter)}</span> : null}
                  <span className="badge">Arrêté: {formatDate(financeAsOfDateKey)}</span>
                  {financeView === "transactions" && financeSourceFilter !== "ALL" ? <span className="badge">Type: {sourceLabel(financeSourceFilter)}</span> : null}
                </FilterChipsBar>
              </SectionCard>

              {financeView === "transactions" ? (
                <SectionCard title="Transactions" className="client-finance-list-card" action={<span className="badge">{paymentRows.length}</span>}>
                  {paymentRows.length === 0 ? (
                    <p className="muted">Aucune transaction sur cette selection.</p>
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
                            typeBadge={<span className={`status-pill ${isBilled ? "status-ok" : "status-off"}`}>{isBilled ? "Facturé" : "Non facturé"}</span>}
                            label={row.label}
                            meta={`${formatDateTime(row.occurred_at)} · ${row.owner_display_name} · ${sourceLabel(row.source)}`}
                            amount={toMoney(row.total_incl_vat, row.currency)}
                            statusBadge={<span className={`status-pill ${statusClass(row.status)}`}>{financeStatusLabel(row.status)}</span>}
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
                                    Ouvrir facture
                                  </a>
                                ) : null}
                                {canPayNow ? (
                                  <form action={openClientPaymentCheckoutAction}>
                                    <input type="hidden" name="payment_id" value={row.id} />
                                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "transactions" })} />
                                    <button type="submit">Payer</button>
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
                <SectionCard title="Factures" className="client-finance-list-card" action={<span className="badge">{invoiceRows.length}</span>}>
                  {invoiceRows.length === 0 ? (
                    <p className="muted">Aucune facture.</p>
                  ) : (
                    <div className="client-finance-list">
                      {pagedInvoiceRows.map((row) => {
                        const linkedPayment = paymentByInvoiceId.get(row.id);
                        const canPayInvoice = (linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(row.payment_url);
                        return (
                          <CompactInvoiceRow
                            key={`inv-${row.id}`}
                            title={compactId(row.invoice_number)}
                            statusBadge={<span className={`status-pill ${statusClass(row.status)}`}>{financeStatusLabel(row.status)}</span>}
                            meta={`${toMoney(row.total_incl_vat, row.currency)} · ${formatDate(row.issued_at)} · ${row.owner_display_name}`}
                            subline={row.label}
                            actions={
                              <div className="row client-finance-card-actions">
                                {canPayInvoice ? (
                                  <form action={openClientPaymentCheckoutAction}>
                                    {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                    {row.payment_url ? <input type="hidden" name="payment_url" value={row.payment_url} /> : null}
                                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices" })} />
                                    <button type="submit" className="client-card-primary-action">Payer</button>
                                  </form>
                                ) : (
                                  <a
                                    className="mode-link client-card-primary-action"
                                    href={clientInvoiceHref(row.id, { inline: true })}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    Ouvrir
                                  </a>
                                )}
                                {row.download_url ? (
                                  <a className="mode-link" href={row.download_url}>
                                    Télécharger
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
                        <span className={`status-pill ${statusClass(selectedInvoice.status)}`}>{financeStatusLabel(selectedInvoice.status)}</span>
                      </div>
                      <p className="muted">{selectedInvoice.label}</p>
                      <p className="muted">
                        Date: {formatDateTime(selectedInvoice.issued_at)} · Membre: {selectedInvoice.owner_display_name}
                      </p>
                      <p>
                        <strong>{toMoney(selectedInvoice.total_incl_vat, selectedInvoice.currency)}</strong>
                      </p>
                      <div className="row client-invoice-viewer-actions">
                        <CopyIdButton value={selectedInvoice.invoice_number} label="Copier numero" />
                        {selectedInvoice.download_url ? <a className="mode-link" href={selectedInvoice.download_url}>Télécharger PDF</a> : null}
                        <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: null })}>Fermer</a>
                      </div>
                    </article>
                  ) : null}
                </SectionCard>
              )}

              {financeTotalRows > financePageSize ? (
                <Card className="client-finance-pagination-card">
                  <div className="row spread">
                    <p className="muted">
                      Page {financePage}/{financePageCount} · {financeTotalRows} ligne(s)
                    </p>
                    <div className="row client-finance-pagination-actions">
                      {financePage > 1 ? (
                        <a
                          className="mode-link"
                          href={withUpdatedQuery(rawParams, { tab: "finance", finance_page: String(financePage - 1), invoice_id: null })}
                        >
                          Precedent
                        </a>
                      ) : (
                        <span className="mode-link disabled" aria-disabled="true">
                          Precedent
                        </span>
                      )}
                      {financePage < financePageCount ? (
                        <a
                          className="mode-link"
                          href={withUpdatedQuery(rawParams, { tab: "finance", finance_page: String(financePage + 1), invoice_id: null })}
                        >
                          Suivant
                        </a>
                      ) : (
                        <span className="mode-link disabled" aria-disabled="true">
                          Suivant
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
                        Payer {toMoney(String(financeDueTotal), me.preferred_currency)}
                      </button>
                    </form>
                  ) : (
                    <a className="client-pay-cta" href={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", finance_status: "TO_PAY" })}>
                      Payer {toMoney(String(financeDueTotal), me.preferred_currency)}
                    </a>
                  )}
                </div>
              ) : null}
            </>
          ) : null}

          {tab === "messages" ? (
            <Card>
              <div className="row spread">
                <h2>Messages envoyes</h2>
                <span className="badge">{messageRows.length}</span>
              </div>
              <p className="muted">
                Par defaut, seuls les 3 derniers mois sont affiches. Vous pouvez afficher l&apos;annee en cours ou l&apos;historique complet.
              </p>

              <form method="get" className="client-filter-grid">
                <input type="hidden" name="tab" value="messages" />
                <input type="hidden" name="message_id" value="" />
                <label>
                  Periode
                  <select name="message_scope" defaultValue={messageScope}>
                    <option value="LAST_3_MONTHS">3 derniers mois</option>
                    <option value="CURRENT_YEAR">Annee en cours</option>
                    <option value="ALL">Tous les messages</option>
                  </select>
                </label>
                <label>
                  Membre
                  <select name="member_id" defaultValue={selectedMemberFilter}>
                    <option value="ALL">{hasMultipleVisibleMembers ? "Tous les membres" : "Mon compte"}</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Rechercher
                  <input
                    type="search"
                    name="message_query"
                    defaultValue={messageQuery}
                    placeholder="Sujet, membre, email, contexte..."
                  />
                </label>
                <div className="row client-message-filter-actions">
                  <button type="submit" aria-label="Rechercher dans les messages">
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
                <p className="muted">Aucun message sur ce filtre.</p>
              ) : (
                <>
                <div className="table-wrap client-desktop-table client-messages-table-wrap">
                  <table className="data-table client-data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Membre</th>
                        <th>Canal</th>
                        <th>Sujet</th>
                        <th>Statut</th>
                        <th>Contexte</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {messageRows.map((msg) => (
                        <tr key={msg.id}>
                          <td>{formatDateTime(msg.sent_at ?? msg.scheduled_for_utc)}</td>
                          <td>{msg.owner_display_name}</td>
                          <td>{msg.channel}</td>
                          <td>{msg.subject_preview}</td>
                          <td>
                            <span className={`status-pill ${statusClass(msg.status)}`}>{statusLabel(msg.status)}</span>
                          </td>
                          <td>{msg.session_title ?? "Message transactionnel"}</td>
                          <td>
                            <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages", message_id: msg.id })}>
                              Lire
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
                        title={msg.subject_preview || "Message sans sujet"}
                        subtitle={`${formatDateTime(msg.sent_at ?? msg.scheduled_for_utc)} | ${msg.owner_display_name}`}
                        right={
                          <div className="stack-xs">
                            <span className="badge">{msg.channel}</span>
                            <span className={`status-pill ${statusClass(msg.status)}`}>{statusLabel(msg.status)}</span>
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
                          aria-label="Fermer le message"
                        >
                          ×
                        </a>
                        <h3>{selectedMessage.subject_preview || "Message sans sujet"}</h3>
                        <p className="muted">
                          {formatDateTime(selectedMessage.sent_at ?? selectedMessage.scheduled_for_utc)} · {selectedMessage.owner_display_name} · {selectedMessage.channel}
                        </p>
                      </header>

                      <section className="modal-card client-message-modal-meta">
                        <div className="client-message-meta-grid">
                          <article className="item">
                            <small className="muted">Destinataire</small>
                            <p>{selectedMessage.recipient_email || "Non affiche pour ce membre"}</p>
                          </article>
                          <article className="item">
                            <small className="muted">Statut</small>
                            <p>{statusLabel(selectedMessage.status)}</p>
                          </article>
                          <article className="item">
                            <small className="muted">Contexte</small>
                            <p>{selectedMessage.session_title ?? "Message transactionnel"}</p>
                          </article>
                          <article className="item">
                            <small className="muted">Canal</small>
                            <p>{selectedMessage.channel}</p>
                          </article>
                        </div>
                      </section>

                      <section className="modal-card client-message-detail">
                        {selectedMessage.content_html ? (
                          <div
                            className="client-message-html"
                            dangerouslySetInnerHTML={{ __html: selectedMessage.content_html }}
                          />
                        ) : (
                          <pre className="client-message-detail-content">
                            {selectedMessage.content_preview || "Contenu indisponible"}
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
                  <summary>Mon compte</summary>
                  <div className="client-account-accordion-content">
                    <div className="list client-mobile-list">
                      <ListRow title="Prenom" right={me.first_name ?? "-"} />
                      <ListRow title="Nom" right={me.last_name ?? "-"} />
                      <ListRow title="Email" right={me.email} />
                      <ListRow title="Tel mob 1" right={me.mobile_phone_1 ?? "-"} />
                      <ListRow title="Tel mob 2" right={me.mobile_phone_2 ?? "-"} />
                      <ListRow title="Tel domicile" right={me.home_phone ?? "-"} />
                      <ListRow
                        title="Adresse"
                        subtitle={`${me.address_line ?? "-"}, ${me.postal_code ?? "-"} ${me.city ?? "-"}, ${labelFromOptions(COUNTRY_OPTIONS, me.address_country)}`}
                      />
                      <ListRow title="Pays residence" right={labelFromOptions(COUNTRY_OPTIONS, me.residence_country)} />
                      <ListRow title="Devise" right={labelFromOptions(CURRENCY_OPTIONS, me.preferred_currency)} />
                      <ListRow title="Fuseau" right={labelFromOptions(TIMEZONE_OPTIONS, me.timezone)} />
                    </div>
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", edit_profile: editProfile ? null : "1" })}>
                      {editProfile ? "Fermer edition" : "Modifier mon compte"}
                    </a>
                  </div>
                </details>

                <details className="client-account-accordion card" open={linkedMembers.length > 0}>
                  <summary>
                    <span>Membres</span>
                    <span className="badge">{linkedMembers.length}</span>
                  </summary>
                  <div className="client-account-accordion-content">
                    {linkedMembers.length === 0 ? (
                      <p className="muted">Aucun membre rattache.</p>
                    ) : (
                      <div className="list client-mobile-list">
                        {linkedMembers.map((member) => (
                            <ListRow
                              key={`mob-member-${member.id}`}
                              title={member.display_name}
                              subtitle={member.email ?? undefined}
                              right={<span className="badge">{member.kind === "CHILD" ? "Enfant" : "Adulte"}</span>}
                            />
                        ))}
                      </div>
                    )}
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>Preferences</summary>
                  <div className="client-account-accordion-content">
                    <article className="item">
                      <strong>Resume</strong>
                      <p className="muted">{communicationSummary}</p>
                    </article>
                    <article className="item">
                      <strong>Rappels de cours</strong>
                      <p className="muted">Notifications automatiques avant les seances.</p>
                      <label className="client-switch-row"><span>Rappels de cours par email</span><span className={`client-switch ${me.lesson_reminder_email_opt_in ? "on" : ""}`} /></label>
                      <label className="client-switch-row"><span>Rappels de cours par SMS</span><span className={`client-switch ${me.lesson_reminder_sms_opt_in ? "on" : ""}`} /></label>
                      {me.lesson_reminder_sms_opt_in && !hasPhoneNumber ? <p className="muted">Numero requis pour les rappels SMS.</p> : null}
                    </article>
                    <article className="item">
                      <strong>Communications de l ecole</strong>
                      <p className="muted">Information generale, nouveautes et alertes importantes.</p>
                      <label className="client-switch-row"><span>Recevoir les emails de communication</span><span className={`client-switch ${me.email_opt_in ? "on" : ""}`} /></label>
                      <label className="client-switch-row"><span>Recevoir les SMS de communication</span><span className={`client-switch ${me.sms_opt_in ? "on" : ""}`} /></label>
                      {me.sms_opt_in && !hasPhoneNumber ? <p className="muted">Numero requis pour les SMS de communication.</p> : null}
                    </article>
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>Voir la messagerie</a>
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>Messages</summary>
                  <div className="client-account-accordion-content">
                    {messageRows.length === 0 ? (
                      <p className="muted">Aucun message recent.</p>
                    ) : (
                      <div className="list client-mobile-list client-inbox-list">
                        {messageRows.slice(0, 8).map((msg) => (
                          <ListRow
                            key={`account-message-${msg.id}`}
                            title={msg.subject_preview || "Message"}
                            subtitle={`${formatDateTime(msg.sent_at ?? msg.scheduled_for_utc)} · ${msg.owner_display_name}`}
                            right={<span className="badge">{msg.channel}</span>}
                          />
                        ))}
                      </div>
                    )}
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>Historique complet</a>
                  </div>
                </details>

                <details className="client-account-accordion card">
                  <summary>Credits</summary>
                  <div className="client-account-accordion-content">
                    {positivePackSubscriptions.length === 0 ? (
                      <p className="muted">Aucun credit positif.</p>
                    ) : (
                      <div className="list client-mobile-list">
                        {positivePackSubscriptions.map((sub) => (
                          <ListRow
                            key={`mob-credit-${sub.id}`}
                            title={sub.plan.name}
                            subtitle={`Debut: ${formatDate(sub.started_at)}${sub.ends_at ? ` | Fin: ${formatDate(sub.ends_at)}` : ""}`}
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
                    <h2>Mon compte</h2>
                    <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "account", edit_profile: editProfile ? null : "1" })}>
                      {editProfile ? "✖" : "✎"}
                    </a>
                  </div>

                  <div className="client-info-list">
                    <p><strong>Prenom:</strong> {me.first_name ?? "-"}</p>
                    <p><strong>Nom:</strong> {me.last_name ?? "-"}</p>
                    <p><strong>Email:</strong> {me.email}</p>
                    <p><strong>Tel mob 1:</strong> {me.mobile_phone_1 ?? "-"}</p>
                    <p><strong>Tel mob 2:</strong> {me.mobile_phone_2 ?? "-"}</p>
                    <p><strong>Tel domicile:</strong> {me.home_phone ?? "-"}</p>
                    <p>
                      <strong>Adresse:</strong> {me.address_line ?? "-"}, {me.postal_code ?? "-"} {me.city ?? "-"}, {labelFromOptions(COUNTRY_OPTIONS, me.address_country)}
                    </p>
                    <p><strong>Pays residence:</strong> {labelFromOptions(COUNTRY_OPTIONS, me.residence_country)}</p>
                    <p><strong>Devise:</strong> {labelFromOptions(CURRENCY_OPTIONS, me.preferred_currency)}</p>
                    <p><strong>Fuseau:</strong> {labelFromOptions(TIMEZONE_OPTIONS, me.timezone)}</p>
                  </div>
                </Card>

                <Card>
                  <h2>Membres rattaches</h2>
                  {linkedMembers.length === 0 ? (
                    <p className="muted">Aucun membre rattache.</p>
                  ) : (
                    <div className="list">
                      {linkedMembers.map((member) => (
                          <article key={member.id} className="item row spread">
                            <div>
                              <strong>{member.display_name}</strong>
                              {member.email ? <p className="muted">{member.email}</p> : null}
                            </div>
                            <span className="badge">{member.kind === "CHILD" ? "Enfant" : "Adulte"}</span>
                          </article>
                      ))}
                    </div>
                  )}
                </Card>
              </section>

              <Card className="client-account-desktop">
                <h2>Preferences communication</h2>
                <p className="muted">{communicationSummary}</p>
                <div className="client-preferences-list">
                  <article className="item">
                    <strong>Rappels de cours</strong>
                    <label className="client-switch-row"><span>Rappels de cours par email</span><span className={`client-switch ${me.lesson_reminder_email_opt_in ? "on" : ""}`} /></label>
                    <label className="client-switch-row"><span>Rappels de cours par SMS</span><span className={`client-switch ${me.lesson_reminder_sms_opt_in ? "on" : ""}`} /></label>
                  </article>
                  <article className="item">
                    <strong>Communications de l ecole</strong>
                    <label className="client-switch-row"><span>Recevoir les emails de communication</span><span className={`client-switch ${me.email_opt_in ? "on" : ""}`} /></label>
                    <label className="client-switch-row"><span>Recevoir les SMS de communication</span><span className={`client-switch ${me.sms_opt_in ? "on" : ""}`} /></label>
                  </article>
                </div>
              </Card>

              <Card className="client-account-desktop">
                <div className="row spread">
                  <h2>Messages</h2>
                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>
                    Voir tout
                  </a>
                </div>
                {messageRows.length === 0 ? (
                  <p className="muted">Aucun message recent.</p>
                ) : (
                  <div className="list">
                    {messageRows.slice(0, 6).map((msg) => (
                      <article key={`desktop-account-message-${msg.id}`} className="item row spread">
                        <div>
                          <strong>{msg.subject_preview || "Message"}</strong>
                          <p className="muted">{formatDateTime(msg.sent_at ?? msg.scheduled_for_utc)} · {msg.owner_display_name}</p>
                        </div>
                        <span className="badge">{msg.channel}</span>
                      </article>
                    ))}
                  </div>
                )}
              </Card>

              <Card className="client-account-desktop">
                <h2>Credits disponibles</h2>
                <p className="muted">Affichage des credits strictement positifs.</p>
                {positivePackSubscriptions.length === 0 ? (
                  <p className="muted">Aucun credit positif.</p>
                ) : (
                  <div className="list">
                    {positivePackSubscriptions.map((sub) => (
                      <article key={`account-credit-${sub.id}`} className="item">
                        <div className="row spread">
                          <strong>{sub.plan.name}</strong>
                          <span className="badge">{sub.owner_display_name}</span>
                        </div>
                        <p className="muted">
                          Credits: {sub.credits_remaining ?? 0}/{sub.credits_initial ?? sub.credits_remaining ?? 0}
                        </p>
                        <p className="muted">
                          Debut: {formatDate(sub.started_at)}
                          {sub.ends_at ? ` | Fin: ${formatDate(sub.ends_at)}` : ""}
                        </p>
                      </article>
                    ))}
                  </div>
                )}
              </Card>

              {editProfile ? (
                <Card className="client-account-edit">
                  <h2>Modifier mes informations</h2>
                  <form action={updateProfileAction} className="client-filter-grid">
                    <label>
                      Prenom
                      <input type="text" name="first_name" defaultValue={me.first_name ?? ""} maxLength={100} required />
                    </label>
                    <label>
                      Nom
                      <input type="text" name="last_name" defaultValue={me.last_name ?? ""} maxLength={100} required />
                    </label>
                    <label>
                      Email
                      <input type="email" value={me.email} disabled readOnly />
                    </label>
                    <label>
                      Tel mob 1
                      <input type="text" name="mobile_phone_1" defaultValue={me.mobile_phone_1 ?? me.phone ?? ""} maxLength={30} />
                    </label>
                    <label>
                      Tel mob 2
                      <input type="text" name="mobile_phone_2" defaultValue={me.mobile_phone_2 ?? ""} maxLength={30} />
                    </label>
                    <label>
                      Tel domicile
                      <input type="text" name="home_phone" defaultValue={me.home_phone ?? ""} maxLength={30} />
                    </label>
                    <label>
                      Adresse
                      <input type="text" name="address_line" defaultValue={me.address_line ?? ""} maxLength={255} />
                    </label>
                    <label>
                      Code postal
                      <input type="text" name="postal_code" defaultValue={me.postal_code ?? ""} maxLength={20} />
                    </label>
                    <label>
                      Ville
                      <input type="text" name="city" defaultValue={me.city ?? ""} maxLength={120} />
                    </label>
                    <label>
                      Pays adresse
                      <select name="address_country" defaultValue={me.address_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Pays residence
                      <select name="residence_country" defaultValue={me.residence_country || DEFAULT_COUNTRY} required>
                        {COUNTRY_OPTIONS.map((country) => (
                          <option key={country.value} value={country.value}>
                            {country.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Devise
                      <select name="preferred_currency" defaultValue={me.preferred_currency || DEFAULT_CURRENCY} required>
                        {CURRENCY_OPTIONS.map((currency) => (
                          <option key={currency.value} value={currency.value}>
                            {currency.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Fuseau
                      <select name="timezone" defaultValue={me.timezone || DEFAULT_TIMEZONE} required>
                        {TIMEZONE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="span-2">
                      Informations importantes
                      <textarea name="important_info" rows={3} defaultValue={me.important_info ?? ""} maxLength={1000} />
                    </label>

                    <input type="hidden" name="portal_contact_visible" value={me.portal_contact_visible ? "on" : "off"} />
                    <label className="checkline">
                      <input type="checkbox" name="email_opt_in" defaultChecked={me.email_opt_in} />
                      <span className="client-switch-label">Recevoir les emails de communication</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="sms_opt_in" defaultChecked={me.sms_opt_in} />
                      <span className="client-switch-label">Recevoir les SMS de communication</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="lesson_reminder_email_opt_in" defaultChecked={me.lesson_reminder_email_opt_in} />
                      <span className="client-switch-label">Rappels de cours par email</span>
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="lesson_reminder_sms_opt_in" defaultChecked={me.lesson_reminder_sms_opt_in} />
                      <span className="client-switch-label">Rappels de cours par SMS</span>
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

        <MobileTabs items={mobileTabLinks} activeId={activeMobileTabId} />
    </main>
  );
}
