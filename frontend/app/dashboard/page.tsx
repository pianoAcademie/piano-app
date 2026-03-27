import Link from "next/link";
import { redirect } from "next/navigation";

import PortalImpersonationBanner from "../../components/portal-impersonation-banner";
import { getAdminToken, getPortalReturnTo, getPortalToken, readPortalImpersonationClaims } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import {
  bookSessionAction,
  cancelBookingAction,
  endPortalImpersonationAction,
  logoutAction,
  openClientPaymentCheckoutAction,
  purchasePlanAction,
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
  ClientFamilyOverviewOut,
  ClientPaymentConfirmOut,
  ClientInvoiceOut,
  ClientMessageOut,
  ClientPaymentCheckoutOut,
  ClientPaymentOut,
  CourseTypeOut,
  LocationOut,
  PlanOut,
  SessionAudienceScope,
  SessionOut,
  SubscriptionOut,
  UserOut,
} from "../../lib/types";
import Card from "../../components/client-ui/card";
import DrawerFilters from "../../components/client-ui/drawer-filters";
import ListRow from "../../components/client-ui/list-row";
import MobileHeader from "../../components/client-ui/mobile-header";
import MobileTabs from "../../components/client-ui/mobile-tabs";
import CopyIdButton from "../../components/client-ui/copy-id-button";
import StatChip from "../../components/client-ui/stat-chip";
import Toast from "../../components/client-ui/toast";
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
type DashboardTab = "home" | "planning" | "reservations" | "offers" | "finance" | "messages" | "account";
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
  email: string;
  kind: string;
};

type MemberOfferAccess = {
  hasAnyActiveOffer: boolean;
  hasVisibleOffer: boolean;
  hasReservableOffer: boolean;
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
  if (value === "planning" || value === "reservations" || value === "offers" || value === "finance" || value === "messages" || value === "account") {
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

function normalizeSessionAudienceScope(raw: unknown, fallback: SessionAudienceScope): SessionAudienceScope {
  const value = String(raw ?? "").trim().toUpperCase();
  if (value === "EXTERNAL" || value === "SUBSCRIPTION" || value === "FORFAIT" || value === "PRIVATE") {
    return value;
  }
  return fallback;
}

function normalizeSessionAudienceScopes(raw: unknown, fallback: SessionAudienceScope[]): SessionAudienceScope[] {
  const source = Array.isArray(raw) ? raw : raw == null ? [] : [raw];
  const seen = new Set<SessionAudienceScope>();
  const normalized: SessionAudienceScope[] = [];
  for (const value of source) {
    const scope = normalizeSessionAudienceScope(value, "__INVALID__" as SessionAudienceScope);
    if (scope === ("__INVALID__" as SessionAudienceScope) || seen.has(scope)) {
      continue;
    }
    seen.add(scope);
    normalized.push(scope);
  }
  if (seen.has("PRIVATE")) {
    return ["PRIVATE"];
  }
  const ordered = (["EXTERNAL", "SUBSCRIPTION", "FORFAIT"] as const).filter((scope) => seen.has(scope));
  return ordered.length > 0 ? [...ordered] : [...fallback];
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
    return "Reservation";
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

function formatDate(value: string | null | undefined, timezoneName?: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(timezoneName ? { timeZone: resolveTimezone(timezoneName) } : {}),
  });
}

function formatDateTime(value: string | null | undefined, timezoneName?: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
    ...(timezoneName ? { timeZone: resolveTimezone(timezoneName) } : {}),
  });
}

function formatTime(value: string | null | undefined, timezoneName?: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    ...(timezoneName ? { timeZone: resolveTimezone(timezoneName) } : {}),
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

function agendaStripToken(dayKey: string): { weekday: string; day: string; month: string } {
  const date = keyToUtcDate(dayKey);
  const weekday = new Intl.DateTimeFormat("fr-FR", {
    weekday: "short",
    timeZone: "UTC",
  })
    .format(date)
    .replace(".", "")
    .toUpperCase();
  const day = new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
  const month = new Intl.DateTimeFormat("fr-FR", {
    month: "short",
    timeZone: "UTC",
  })
    .format(date)
    .replace(".", "")
    .toUpperCase();

  return { weekday, day, month };
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

function isVacationCourseTypeCode(code: string | null | undefined): boolean {
  const normalized = normalizeStatus(code ?? "");
  return normalized === "VACATION_DAY" || normalized.startsWith("VACATION");
}

function memberDisplayName(member: { first_name: string | null; last_name: string | null; email: string }): string {
  const fullName = [member.first_name, member.last_name].filter(Boolean).join(" ");
  return fullName || member.email;
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
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const inputAgendaDate = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(inputAgendaDate) ? inputAgendaDate : todayKeyInTimezone(timezone);
  const agendaRange = buildAgendaRange(agendaView, agendaDate);

  const reservationScope = readParam(searchParams, "reservation_scope") || "CURRENT";
  const reservationStatusFilter = readParam(searchParams, "reservation_status");
  const selectedMemberFilter = emptyAsAll(readParam(searchParams, "member_id"));
  const selectedBookingOwner = emptyAsAll(readParam(searchParams, "booking_owner_id"));
  const selectedSessionId = readParam(searchParams, "session_id");
  const selectedOfferDetailId = readParam(searchParams, "offer_detail_id");
  const messageScope = parseMessageScope(readParam(searchParams, "message_scope"));
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
  const addMember = (candidate: { id: string; first_name: string | null; last_name: string | null; email: string; client_kind: string }): void => {
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
  const validMemberIds = new Set(members.map((member) => member.id));
  const defaultPlanningOwnerSelection = members.length > 1 ? "ALL" : me.id;
  const bookingOwnerSelection =
    selectedBookingOwner === "ALL"
      ? defaultPlanningOwnerSelection
      : validMemberIds.has(selectedBookingOwner)
        ? selectedBookingOwner
        : defaultPlanningOwnerSelection;
  const planningShowsAllMembers = bookingOwnerSelection === "ALL";
  const visiblePlanningMembers = planningShowsAllMembers
    ? members
    : members.filter((member) => member.id === bookingOwnerSelection);
  const visiblePlanningMemberIds = new Set(visiblePlanningMembers.map((member) => member.id));
  const bookingOwnerId = planningShowsAllMembers ? null : bookingOwnerSelection;
  const bookingOwnerMember = bookingOwnerId ? members.find((member) => member.id === bookingOwnerId) ?? null : null;
  const planningOwnerLabel = planningShowsAllMembers ? "Toute la famille" : bookingOwnerMember?.display_name ?? "-";

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
  const bookingByPaymentKey = new Map<string, FamilyBookingRow>();
  for (const booking of allBookings) {
    const key = normalizePaymentKey(`BOOKING:${booking.id}`);
    if (!key) {
      continue;
    }
    bookingByPaymentKey.set(key, booking);
  }

  const now = new Date();
  const activeBookingStatuses = new Set(["BOOKED", "WAITLISTED"]);

  const bookingsBySessionAndMember = new Map<string, FamilyBookingRow>();
  for (const booking of allBookings) {
    const status = normalizeStatus(booking.status);
    if (status === "CANCELLED") {
      continue;
    }
    bookingsBySessionAndMember.set(`${booking.session.id}:${booking.owner_client_id}`, booking);
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

  const messageRows = messages
    .filter((row) => selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter)
    .sort((a, b) => (b.sent_at || b.scheduled_for_utc).localeCompare(a.sent_at || a.scheduled_for_utc));

  const paymentOwnerByKey = new Map<string, string>();
  for (const row of payments) {
    const paymentKey = paymentKeyFromPaymentRow(row);
    if (!paymentKey) {
      continue;
    }
    paymentOwnerByKey.set(paymentKey, row.owner_client_id);
  }

  const basePaymentRows = payments
    .filter((row) => selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter)
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));

  const baseInvoiceRows = invoices
    .filter((row) => !isCancelledFinanceStatus(row.status))
    .filter((row) => {
      if (selectedMemberFilter === "ALL" || row.owner_client_id === selectedMemberFilter) {
        return true;
      }
      return (row.included_payment_keys ?? []).some((rawKey) => {
        const normalizedKey = normalizePaymentKey(rawKey);
        if (!normalizedKey) {
          return false;
        }
        return paymentOwnerByKey.get(normalizedKey) === selectedMemberFilter;
      });
    })
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
  const paymentRowsWithFinance = basePaymentRows.map((row) => {
    const paymentKey = paymentKeyFromPaymentRow(row);
    const linkedInvoice =
      invoiceByPaymentId.get(row.id) ??
      (paymentKey ? invoiceByPaymentKey.get(paymentKey) : undefined);
    const linkedBooking = paymentKey ? bookingByPaymentKey.get(paymentKey) : undefined;
    const effectiveFinanceStatus = linkedInvoice?.status ?? row.status;
    const occurredAtForDisplay = linkedBooking?.session.start_at_utc ?? row.occurred_at;
    return {
      row,
      linkedInvoice,
      effectiveFinanceStatus,
      occurredAtForDisplay,
    };
  });
  const filteredPaymentRows = paymentRowsWithFinance
    .filter(({ row }) => financeSourceFilter === "ALL" || normalizeStatus(row.source) === normalizeStatus(financeSourceFilter))
    .filter(({ effectiveFinanceStatus }) => statusMatchesFinanceFilter(effectiveFinanceStatus, financeStatusFilter))
    .filter(({ occurredAtForDisplay }) => matchesFinancePeriod(occurredAtForDisplay, financePeriodFilter, now))
    .filter(({ occurredAtForDisplay }) => matchesFinanceAsOf(occurredAtForDisplay, financeAsOfUtcEnd));
  const financeTotalRows = financeView === "transactions" ? filteredPaymentRows.length : invoiceRows.length;
  const financePageCount = Math.max(1, Math.ceil(financeTotalRows / financePageSize));
  const financePage = Math.min(financePageRaw, financePageCount);
  const financeOffset = (financePage - 1) * financePageSize;
  const pagedPaymentRows = filteredPaymentRows.slice(financeOffset, financeOffset + financePageSize);
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
  const activeSubscriptionEntitlementsByOwner = new Map<string, Set<string>>();
  const activeForfaitEntitlementsByOwner = new Map<string, Set<string>>();
  const activeSubscriptionOfferByOwner = new Set<string>();
  const activeForfaitOfferByOwner = new Set<string>();
  for (const sub of subscriptions) {
    if (!isSubscriptionActiveNow(sub, now)) {
      continue;
    }
    const entitlementSet = activeEntitlementsByOwner.get(sub.owner_client_id) ?? new Set<string>();
    for (const courseTypeId of sub.entitlement_course_type_ids ?? []) {
      entitlementSet.add(courseTypeId);
    }
    activeEntitlementsByOwner.set(sub.owner_client_id, entitlementSet);
    const normalizedPlanKind = normalizeStatus(sub.plan.kind);
    const isSubscriptionAudiencePlan =
      normalizedPlanKind === "SUBSCRIPTION" || (normalizedPlanKind === "PACK" && (sub.credits_remaining ?? 0) > 0);
    if (isSubscriptionAudiencePlan) {
      activeSubscriptionOfferByOwner.add(sub.owner_client_id);
      const reservableEntitlementSet = activeSubscriptionEntitlementsByOwner.get(sub.owner_client_id) ?? new Set<string>();
      for (const courseTypeId of sub.entitlement_course_type_ids ?? []) {
        reservableEntitlementSet.add(courseTypeId);
      }
      activeSubscriptionEntitlementsByOwner.set(sub.owner_client_id, reservableEntitlementSet);
    }
    if (normalizedPlanKind === "FORFAIT") {
      activeForfaitOfferByOwner.add(sub.owner_client_id);
      const forfaitEntitlementSet = activeForfaitEntitlementsByOwner.get(sub.owner_client_id) ?? new Set<string>();
      for (const courseTypeId of sub.entitlement_course_type_ids ?? []) {
        forfaitEntitlementSet.add(courseTypeId);
      }
      activeForfaitEntitlementsByOwner.set(sub.owner_client_id, forfaitEntitlementSet);
    }
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
    if (homeCalendarView === "BY_MEMBER") {
      const memberDiff = a.owner_display_name.localeCompare(b.owner_display_name, "fr");
      if (memberDiff !== 0) {
        return memberDiff;
      }
    }
    return a.session.start_at_utc.localeCompare(b.session.start_at_utc);
  });
  const homeCalendarGroups =
    homeCalendarView === "BY_MEMBER"
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
    agenda_view: "agenda",
    agenda_date: firstHomeBooking
      ? dateKeyInTimezone(firstHomeBooking.session.start_at_utc, timezone)
      : todayKeyInTimezone(timezone),
    session_id: null,
    booking_owner_id: defaultPlanningOwnerSelection,
  });

  const planningUpcomingBookings = upcomingBookings.filter((booking) => visiblePlanningMemberIds.has(booking.owner_client_id));
  const visiblePlanningCourseTypeIds = new Set<string>();
  for (const member of visiblePlanningMembers) {
    for (const courseTypeId of activeEntitlementsByOwner.get(member.id) ?? []) {
      visiblePlanningCourseTypeIds.add(courseTypeId);
    }
  }
  const visiblePlanningReservedSessionIds = new Set(planningUpcomingBookings.map((booking) => booking.session.id));
  const planningCourseTypes = courseTypes.filter(
    (courseType) => !isVacationCourseTypeCode(courseType.code) && visiblePlanningCourseTypeIds.has(courseType.id),
  );
  const planningSourceSessions = sessions.filter((session) => {
    if (isVacationCourseTypeCode(session.course_type.code)) {
      return false;
    }
    return visiblePlanningCourseTypeIds.has(session.course_type.id) || visiblePlanningReservedSessionIds.has(session.id);
  });
  const coachOptions = Array.from(
    planningSourceSessions
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

  const filteredSessions = planningSourceSessions.filter((session) => {
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
  const sessionVisibilityScopes = (session: SessionOut): SessionAudienceScope[] =>
    normalizeSessionAudienceScopes(
      session.visibility_scopes,
      [session.visibility_scope || "EXTERNAL"],
    );
  const sessionBookingScopes = (session: SessionOut): SessionAudienceScope[] =>
    normalizeSessionAudienceScopes(
      session.booking_scopes,
      session.online_booking_enabled ? ["EXTERNAL"] : ["PRIVATE"],
    );
  const memberOfferAccessForSession = (session: SessionOut, ownerId: string): MemberOfferAccess => {
    const bookingScopes = sessionBookingScopes(session);
    const visibilityScopes = sessionVisibilityScopes(session);
    const hasSubscriptionEntitlement = activeSubscriptionEntitlementsByOwner.get(ownerId)?.has(session.course_type.id) ?? false;
    const hasForfaitEntitlement = activeForfaitEntitlementsByOwner.get(ownerId)?.has(session.course_type.id) ?? false;
    const hasAnyActiveOffer =
      activeSubscriptionOfferByOwner.has(ownerId) || activeForfaitOfferByOwner.has(ownerId);
    const hasVisibleOffer =
      visibilityScopes.includes("EXTERNAL") ||
      (visibilityScopes.includes("SUBSCRIPTION") && hasSubscriptionEntitlement) ||
      (visibilityScopes.includes("FORFAIT") && hasForfaitEntitlement);
    const hasReservableOffer =
      bookingScopes.includes("EXTERNAL") ||
      (bookingScopes.includes("SUBSCRIPTION") && hasSubscriptionEntitlement) ||
      (bookingScopes.includes("FORFAIT") && hasForfaitEntitlement);
    return {
      hasAnyActiveOffer,
      hasVisibleOffer,
      hasReservableOffer,
    };
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
  const canReserveSessionNowForOwner = (session: SessionOut, ownerId: string): boolean => {
    const memberBooking = bookingsBySessionAndMember.get(`${session.id}:${ownerId}`);
    const sessionIsPastOrStarted = (safeDate(session.start_at_utc)?.getTime() ?? 0) <= now.getTime();
    const eligibleByPlan = memberOfferAccessForSession(session, ownerId).hasReservableOffer;
    const isFull = session.booked_count >= session.capacity_max;
    return (
      normalizeStatus(session.status) === "SCHEDULED"
      && session.online_booking_enabled
      && !sessionIsPastOrStarted
      && !memberBooking
      && !isFull
      && eligibleByPlan
    );
  };
  const visibleReservedBookingsForSession = (sessionId: string): FamilyBookingRow[] =>
    visiblePlanningMembers.flatMap((member) => {
      const booking = bookingsBySessionAndMember.get(`${sessionId}:${member.id}`);
      return booking && isAlreadyReservedByMember(booking.status) ? [booking] : [];
    });
  const visibleCoveredMembersForSession = (session: SessionOut): MemberLite[] =>
    visiblePlanningMembers.filter((member) => memberOfferAccessForSession(session, member.id).hasVisibleOffer);
  const visibleReservableMembersForSession = (session: SessionOut): MemberLite[] =>
    visiblePlanningMembers.filter((member) => canReserveSessionNowForOwner(session, member.id));
  const filteredPlanningSessions = (sessions: SessionOut[]): SessionOut[] =>
    sessions.filter((session) => {
      const reservedBookings = visibleReservedBookingsForSession(session.id);
      const alreadyReserved = reservedBookings.length > 0;
      const availableNow = visibleReservableMembersForSession(session).length > 0;
      if (planningSlotFilter === "AVAILABLE") {
        return availableNow;
      }
      if (planningSlotFilter === "ALREADY_BOOKED") {
        return alreadyReserved;
      }
      return true;
    });
  const sessionPlanningState = (session: SessionOut) => {
    const booking = bookingOwnerId ? bookingsBySessionAndMember.get(`${session.id}:${bookingOwnerId}`) : undefined;
    const reservedBookings = visibleReservedBookingsForSession(session.id);
    const reservedMemberNames = reservedBookings.map((item) => item.owner_display_name);
    const isReservedByMember = reservedBookings.length > 0;
    const coveredMembers = visibleCoveredMembersForSession(session);
    const reservableMembers = visibleReservableMembersForSession(session);
    const reservableMemberNames = reservableMembers.map((member) => member.display_name);
    const coveredOnlyMembers = coveredMembers.filter(
      (member) => !reservableMembers.some((reservableMember) => reservableMember.id === member.id),
    );
    const coveredOnlyMemberNames = coveredOnlyMembers.map((member) => member.display_name);
    const eligibleByPlan = bookingOwnerId != null
      ? memberOfferAccessForSession(session, bookingOwnerId).hasReservableOffer
      : reservableMembers.length > 0;
    const accentColor = accentColorForId(session.course_type.id);
    const durationMinutes = Math.max(
      1,
      Math.round((new Date(session.end_at_utc).getTime() - new Date(session.start_at_utc).getTime()) / 60000),
    );
    const openDetailsHref = withUpdatedQuery(rawParams, {
      tab: "planning",
      session_id: session.id,
      ok: null,
      error: null,
      session_ok: null,
      session_error: null,
    });
    const sessionIsPastOrStarted = (safeDate(session.start_at_utc)?.getTime() ?? 0) <= now.getTime();
    const canReserveNow =
      normalizeStatus(session.status) === "SCHEDULED" &&
      session.online_booking_enabled &&
      !sessionIsPastOrStarted &&
      !booking &&
      eligibleByPlan &&
      session.booked_count < session.capacity_max;
    const isFull = session.booked_count >= session.capacity_max;
    const canReserveForFamily =
      planningShowsAllMembers &&
      normalizeStatus(session.status) === "SCHEDULED" &&
      session.online_booking_enabled &&
      !sessionIsPastOrStarted &&
      !isReservedByMember &&
      reservableMembers.length > 0 &&
      !isFull;
    const canOpenBookingFlow = canReserveNow || canReserveForFamily;
    const coveredByFamilyOffer =
      !isReservedByMember &&
      !canOpenBookingFlow &&
      !isFull &&
      !sessionIsPastOrStarted &&
      coveredOnlyMemberNames.length > 0;
    const sessionCtaLabel = isReservedByMember
      ? planningShowsAllMembers
        ? "Voir membres"
        : "Voir la reservation"
      : canOpenBookingFlow
        ? "Reserver ce creneau"
        : isFull
          ? "Complet"
          : "Voir details";
    const contextLine = isReservedByMember
      ? `Reserve pour ${reservedMemberNames.join(", ")}`
      : canOpenBookingFlow
        ? planningShowsAllMembers
          ? `Reservation possible pour ${reservableMemberNames.join(", ")}`
          : "Reservation en ligne disponible"
        : isFull
          ? "Creneau complet"
          : sessionIsPastOrStarted
            ? "Creneau deja passe"
          : coveredOnlyMemberNames.length > 0
            ? "Reservation geree hors portail."
          : planningShowsAllMembers
            ? "Aucun membre visible n'a une formule compatible avec ce creneau."
            : `Aucune formule compatible pour ${bookingOwnerMember?.display_name ?? "ce membre"}`;
    const familyHighlightLine = planningShowsAllMembers
      ? isReservedByMember
        ? `Reserve: ${reservedMemberNames.join(", ")}`
        : reservableMemberNames.length > 0
          ? `Reservable pour: ${reservableMemberNames.join(", ")}`
          : coveredOnlyMemberNames.length > 0
            ? `Inclus pour: ${coveredOnlyMemberNames.join(", ")}`
            : null
      : null;
    const bookingStatus = booking ? normalizeStatus(booking.status) : "";
    const showSemanticBadge = isReservedByMember || canOpenBookingFlow || isFull;
    const semanticBadgeLabel = isReservedByMember
      ? planningShowsAllMembers
        ? "Reserve famille"
        : bookingStatus === "WAITLISTED"
          ? "En attente"
          : "Deja reserve"
      : canOpenBookingFlow
        ? "Reservable"
        : isFull
          ? "Complet"
          : "Indisponible";
    const semanticBadgeClass = isReservedByMember
      ? bookingStatus === "WAITLISTED" && !planningShowsAllMembers
        ? "status-waitlist"
        : "status-booked"
      : canOpenBookingFlow
        ? "status-scheduled"
        : "status-waitlist";

    return {
      booking,
      reservedBookings,
      reservedMemberNames,
      isReservedByMember,
      reservableMemberNames,
      coveredOnlyMemberNames,
      accentColor,
      durationMinutes,
      openDetailsHref,
      sessionIsPastOrStarted,
      canOpenBookingFlow,
      coveredByFamilyOffer,
      sessionCtaLabel,
      contextLine,
      familyHighlightLine,
      showSemanticBadge,
      semanticBadgeLabel,
      semanticBadgeClass,
      isFull,
    };
  };
  const agendaDaySummary = new Map<string, { reservedCount: number; availableCount: number }>();
  for (const day of agendaDays) {
    let reservedCount = 0;
    let availableCount = 0;
    for (const session of day.sessions) {
      const reservedBookings = visibleReservedBookingsForSession(session.id);
      const reservableMembers = visibleReservableMembersForSession(session);
      if (reservedBookings.length > 0) {
        reservedCount += 1;
      } else if (reservableMembers.length > 0) {
        availableCount += 1;
      }
    }
    agendaDaySummary.set(day.key, { reservedCount, availableCount });
  }
  const availableSlotsCount = Array.from(agendaDaySummary.values()).reduce((sum, row) => sum + row.availableCount, 0);
  const activeReservationsCount = planningUpcomingBookings.filter((booking) => isAlreadyReservedByMember(booking.status)).length;
  const selectedAgendaDateLabel = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(keyToUtcDate(agendaDate));
  const selectedSession = filteredSessions.find((session) => session.id === selectedSessionId) ?? null;
  const selectedSessionStart = selectedSession ? safeDate(selectedSession.start_at_utc) : null;
  const selectedSessionIsPastOrStarted = selectedSessionStart ? selectedSessionStart.getTime() <= now.getTime() : false;
  const selectedSessionVisibleBookings = selectedSession ? visibleReservedBookingsForSession(selectedSession.id) : [];
  const selectedSessionAvailableMembers = selectedSession ? visibleReservableMembersForSession(selectedSession) : [];
  const selectedSessionBooking =
    selectedSession && bookingOwnerId ? bookingsBySessionAndMember.get(`${selectedSession.id}:${bookingOwnerId}`) : null;
  const selectedSessionOnlineBookingEnabled = selectedSession ? selectedSession.online_booking_enabled : false;
  const selectedSessionCoveredMembers = selectedSession ? visibleCoveredMembersForSession(selectedSession) : [];
  const selectedSessionAccess = selectedSession && bookingOwnerId
    ? memberOfferAccessForSession(selectedSession, bookingOwnerId)
    : null;
  const selectedSessionEligibleByPlan = selectedSession
    ? bookingOwnerId != null
      ? Boolean(selectedSessionAccess?.hasReservableOffer)
      : false
    : false;
  const selectedSessionCoveredByVisibleOffer = selectedSessionCoveredMembers.length > 0;
  const selectedSessionIneligibleReason = !selectedSession
    ? ""
    : !selectedSessionOnlineBookingEnabled
      ? "La reservation en ligne est desactivee pour ce creneau."
      : bookingOwnerId != null && (activeEntitlementsByOwner.get(bookingOwnerId)?.has(selectedSession.course_type.id) ?? false)
        ? "Ce creneau est bien couvert, mais la reservation en ligne n'est pas ouverte pour ce type d'offre."
      : bookingOwnerId != null && Boolean(selectedSessionAccess?.hasAnyActiveOffer)
        ? "Aucune offre active compatible avec ce type de cours."
        : "Aucune offre active pour ce membre.";
  const visiblePlanningMemberHasAnyActiveOffer = visiblePlanningMembers.some(
    (member) => activeSubscriptionOfferByOwner.has(member.id) || activeForfaitOfferByOwner.has(member.id),
  );
  const selectedSessionFamilyIneligibleReason = !selectedSession
    ? ""
    : !selectedSessionOnlineBookingEnabled
      ? "La reservation en ligne est desactivee pour ce creneau."
      : selectedSession.booked_count >= selectedSession.capacity_max
        ? "Creneau complet."
        : selectedSessionCoveredByVisibleOffer
          ? "Ce creneau est visible pour la famille, mais aucun membre n'a ici de droit de reservation en ligne."
          : visiblePlanningMemberHasAnyActiveOffer
            ? "Aucun membre visible n'a une offre compatible avec ce cours."
            : "Aucune offre active pour les membres visibles.";
  const selectedSessionBookingStatus = selectedSessionBooking ? normalizeStatus(selectedSessionBooking.status) : "";
  const selectedSessionCanCancel =
    !!selectedSessionBooking &&
    (selectedSessionBookingStatus === "BOOKED" || selectedSessionBookingStatus === "WAITLISTED") &&
    !selectedSessionIsPastOrStarted;
  const selectedSessionCanBook =
    !!selectedSession &&
    bookingOwnerId != null &&
    normalizeStatus(selectedSession.status) === "SCHEDULED" &&
    selectedSessionOnlineBookingEnabled &&
    !selectedSessionIsPastOrStarted &&
    selectedSessionBooking == null &&
    selectedSessionEligibleByPlan &&
    selectedSession.booked_count < selectedSession.capacity_max;
  const agendaSessionCount = agendaDays.reduce((sum, day) => sum + day.sessions.length, 0);
  const agendaNavigationStep = agendaView === "week" ? 7 : 1;
  const stripDayKeys =
    agendaView === "week"
      ? agendaRange.dayKeys
      : Array.from({ length: 7 }, (_, index) => utcDateToKey(addUtcDays(addUtcDays(keyToUtcDate(agendaDate), -2), index)));
  const planningSectionTitle = planningShowsAllMembers
    ? "Creneaux proposes"
    : members.length > 1
      ? `Creneaux pour ${planningOwnerLabel}`
      : "Mes creneaux";
  const planningSectionSubtitle = planningShowsAllMembers
    ? "Creneaux publics compatibles avec les offres actives de la famille. Les creneaux passes sont grises et les reservations deja prises sont mises en evidence."
    : "Creneaux publics compatibles avec les offres actives du membre selectionne.";
  const advancedFiltersOpen =
    Boolean(selectedCourseType) ||
    Boolean(selectedCoachId) ||
    selectedTimeBucket !== "ALL" ||
    timezone !== (me.timezone || DEFAULT_TIMEZONE);

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

  const paidTotal = invoiceRows
    .filter((invoice) => normalizeStatus(invoice.status) === "PAID")
    .reduce((sum, invoice) => sum + parseMoneyValue(invoice.total_incl_vat), 0);
  const pendingTransactionsTotal = filteredPaymentRows
    .filter(({ row, linkedInvoice }) => !linkedInvoice && FINANCE_PENDING_STATUSES.has(normalizeStatus(row.status)))
    .reduce((sum, { row }) => sum + Number(row.total_incl_vat || "0"), 0);
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
    { id: "reservations", label: "Réservations", icon: "✅" },
    { id: "offers", label: "Forfaits", icon: "🧾" },
    { id: "finance", label: "Finance", icon: "💳" },
    { id: "messages", label: "Messages", icon: "✉️" },
    { id: "account", label: "Compte", icon: "👤" },
  ];
  const mobileTabLinks = [
    { id: "home", label: "Accueil", icon: "🏠", href: withUpdatedQuery(rawParams, { tab: "home" }) },
    { id: "planning", label: "Planning", icon: "📅", href: withUpdatedQuery(rawParams, { tab: "planning" }) },
    { id: "reservations", label: "Réservations", icon: "✅", href: withUpdatedQuery(rawParams, { tab: "reservations" }) },
    { id: "finance", label: "Finance", icon: "💳", href: withUpdatedQuery(rawParams, { tab: "finance" }) },
    { id: "account", label: "Compte", icon: "👤", href: withUpdatedQuery(rawParams, { tab: "account" }) },
  ];
  const activeMobileTabId = mobileTabLinks.some((item) => item.id === tab) ? tab : "home";

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
  } · Communications: Email ${me.email_opt_in ? "ON" : "OFF"} / SMS ${me.sms_opt_in ? "ON" : "OFF"} · Confidentialite: ${
    me.portal_contact_visible ? "ON" : "OFF"
  }`;

  return (
    <main className="client-portal-shell">
      <aside className="client-portal-sidebar">
        <div className="client-brand">
          <strong>Piano Academie</strong>
          <small>Portail client</small>
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
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "messages" })}>
                Messages
              </a>
              <a className="client-mobile-menu-link" href={withUpdatedQuery(rawParams, { tab: "home" })}>
                Accueil
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
              Réservations actives: {upcomingBookings.length} | Membres visibles: {members.length}
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
              </SectionCard>

              <section className="client-home-layout">
                <div className="client-home-main">
                  {homeDueTotal > 0 ? (
                    <UrgentPayCard amountLabel={toMoney(String(homeDueTotal), me.preferred_currency)} countLabel={`${homeDueInvoices.length} facture(s)`}>
                      <div className="client-home-due-list">
                        {homeDueInvoicePreview.map((invoice) => {
                          const linkedPayment = paymentByInvoiceId.get(invoice.id);
                          const invoiceIsPaid = normalizeStatus(invoice.status) === "PAID";
                          const canPayInvoice =
                            !invoiceIsPaid &&
                            ((linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(invoice.payment_url));
                          return (
                            <CompactInvoiceRow
                              key={`home-due-${invoice.id}`}
                              title={compactId(invoice.invoice_number)}
                              statusBadge={<span className={`status-pill ${statusClass(invoice.status)}`}>{financeStatusLabel(invoice.status)}</span>}
                              meta={`${toMoney(invoice.total_incl_vat, invoice.currency)} · ${formatDate(invoice.issued_at)}`}
                              subline={invoice.label}
                              actions={
                                <div className="row client-home-due-actions">
                                  {invoiceIsPaid ? (
                                    <span className="mode-link client-card-primary-action disabled" aria-disabled="true">
                                      Payer
                                    </span>
                                  ) : canPayInvoice ? (
                                    <form action={openClientPaymentCheckoutAction}>
                                      {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                      {invoice.payment_url ? <input type="hidden" name="payment_url" value={invoice.payment_url} /> : null}
                                      <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "home" })} />
                                      <button type="submit" className="client-card-primary-action">Payer</button>
                                    </form>
                                  ) : null}
                                  <a
                                    className="mode-link"
                                    href={invoice.download_url || withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: invoice.id })}
                                    target={invoice.download_url ? "_blank" : undefined}
                                    rel={invoice.download_url ? "noreferrer" : undefined}
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
                            timeLabel={formatTime(booking.session.start_at_utc, timezone)}
                            title={booking.session.title}
                            subtitle={`${formatDate(booking.session.start_at_utc, timezone)} · ${booking.owner_display_name} · ${statusLabel(booking.status)}`}
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
                                  href={invoice.download_url || withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: invoice.id })}
                                  target={invoice.download_url ? "_blank" : undefined}
                                  rel={invoice.download_url ? "noreferrer" : undefined}
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
                title="Calendrier famille"
                action={
                  <div className="row">
                    <a className={`mode-link ${homeCalendarView === "FAMILY" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "FAMILY" })}>
                      Vue famille
                    </a>
                    <a className={`mode-link ${homeCalendarView === "BY_MEMBER" ? "active" : ""}`} href={withUpdatedQuery(rawParams, { tab: "home", home_calendar_view: "BY_MEMBER" })}>
                      Par enfant
                    </a>
                  </div>
                }
              >
                {homeCalendarRows.length === 0 ? (
                  <p className="muted">Aucun cours a venir sur 14 jours.</p>
                ) : homeCalendarView === "BY_MEMBER" ? (
                  <div className="client-home-calendar-groups">
                    {homeCalendarGroups.map(([memberName, rows]) => (
                      <article key={`home-calendar-group-${memberName}`} className="client-home-calendar-group">
                        <h3>{memberName}</h3>
                        <div className="client-home-calendar-list">
                          {rows.slice(0, 3).map((booking) => (
                            <UpcomingLessonRow
                              key={`home-booking-group-${booking.id}`}
                              timeLabel={formatTime(booking.session.start_at_utc, timezone)}
                              title={booking.session.title}
                              subtitle={`${formatDate(booking.session.start_at_utc, timezone)} · ${statusLabel(booking.status)}`}
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
                        timeLabel={formatTime(booking.session.start_at_utc, timezone)}
                        title={booking.session.title}
                        subtitle={`${formatDate(booking.session.start_at_utc, timezone)} · ${booking.owner_display_name} · ${statusLabel(booking.status)}`}
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
                    <h2>Planning des creneaux</h2>
                    <p className="muted">Version mobile optimisee: navigation compacte + filtres progressifs.</p>
                  </div>
                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                    🛍️ Offres
                  </a>
                </div>

                <form method="get" className="client-planning-filter-form">
                  <input type="hidden" name="tab" value="planning" />

                  <div className="client-planning-hero">
                    <label className="client-planning-pill client-planning-pill-location">
                      <span>📍 Planning</span>
                      <select name="location_id" defaultValue={selectedLocation} aria-label="Planning / lieu">
                        <option value="">Tous les lieux</option>
                        {locations.map((location) => (
                          <option key={location.id} value={location.id}>
                            {location.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="client-planning-pill client-planning-pill-date">
                      <span>📅 Date</span>
                      <input type="date" name="agenda_date" defaultValue={agendaDate} />
                    </label>

                    <div className="client-planning-toolbar-actions">
                      <button className="client-planning-apply" type="submit" title="Appliquer les filtres">
                        ✅ Appliquer
                      </button>
                      <Link
                        className="client-planning-reset"
                        scroll={false}
                        href={withUpdatedQuery(rawParams, {
                          tab: "planning",
                          course_type_id: null,
                          location_id: null,
                          coach_id: null,
                          time_bucket: null,
                          planning_slot_filter: null,
                          timezone: me.timezone || DEFAULT_TIMEZONE,
                          agenda_view: "agenda",
                          agenda_date: todayKeyInTimezone(timezone),
                          booking_owner_id: defaultPlanningOwnerSelection,
                          session_id: null,
                          session_ok: null,
                          session_error: null,
                        })}
                        title="Reinitialiser"
                      >
                        ↺
                      </Link>
                    </div>
                  </div>

                  <DrawerFilters title="⚙ Filtres avances" className={`client-planning-advanced ${advancedFiltersOpen ? "has-active" : ""}`} defaultOpen={advancedFiltersOpen}>
                    <div className="client-planning-advanced-grid">
                      <label>
                        Activite
                        <select name="course_type_id" defaultValue={selectedCourseType}>
                          <option value="">Toutes</option>
                          {planningCourseTypes.map((courseType) => (
                            <option key={courseType.id} value={courseType.id}>
                              {courseType.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Coach
                        <select name="coach_id" defaultValue={selectedCoachId}>
                          <option value="">Tous</option>
                          {coachOptions.map((coach) => (
                            <option key={coach.id} value={coach.id}>
                              {coach.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Horaire
                        <select name="time_bucket" defaultValue={selectedTimeBucket}>
                          <option value="ALL">Toutes heures</option>
                          <option value="MORNING">Matin (6h-12h)</option>
                          <option value="AFTERNOON">Apres-midi (12h-18h)</option>
                          <option value="EVENING">Soir (18h-minuit)</option>
                        </select>
                      </label>

                      <label>
                        Vue
                        <select name="agenda_view" defaultValue={agendaView}>
                          <option value="agenda">Agenda</option>
                          <option value="week">Semaine</option>
                          <option value="day">Journee</option>
                        </select>
                      </label>

                      <label>
                        Fuseau horaire
                        <select name="timezone" defaultValue={timezone}>
                          {timezoneOptions.map((item) => (
                            <option key={item.value} value={item.value}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Membre
                        <select name="booking_owner_id" defaultValue={bookingOwnerSelection}>
                          {members.length > 1 ? <option value="ALL">Toute la famille</option> : null}
                          {members.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.display_name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Statut creneaux
                        <select name="planning_slot_filter" defaultValue={planningSlotFilter}>
                          <option value="ALL">Tous</option>
                          <option value="AVAILABLE">Disponibles uniquement</option>
                          <option value="ALREADY_BOOKED">Deja reserves</option>
                        </select>
                      </label>
                    </div>
                  </DrawerFilters>
                </form>

                {members.length > 1 ? (
                  <FilterChipsBar className="client-planning-member-chips">
                    <Link
                      className={`badge ${planningShowsAllMembers ? "active" : ""}`}
                      scroll={false}
                      href={withUpdatedQuery(rawParams, {
                        tab: "planning",
                        booking_owner_id: "ALL",
                        session_id: null,
                        session_ok: null,
                        session_error: null,
                      })}
                    >
                      Toute la famille
                    </Link>
                    {members.map((member) => (
                      <Link
                        key={`planning-member-${member.id}`}
                        className={`badge ${bookingOwnerSelection === member.id ? "active" : ""}`}
                        scroll={false}
                        href={withUpdatedQuery(rawParams, {
                          tab: "planning",
                          booking_owner_id: member.id,
                          session_id: null,
                          session_ok: null,
                          session_error: null,
                        })}
                      >
                        {member.display_name}
                      </Link>
                    ))}
                  </FilterChipsBar>
                ) : null}

                <section className="client-planning-summary-banner">
                  <article className="client-planning-summary-item">
                    <small>Vue planning</small>
                    <strong>{planningOwnerLabel}</strong>
                  </article>
                  <article className="client-planning-summary-item">
                    <small>Reservations actives</small>
                    <strong>{activeReservationsCount}</strong>
                  </article>
                  <article className="client-planning-summary-item">
                    <small>Creneaux disponibles</small>
                    <strong>{availableSlotsCount}</strong>
                  </article>
                  <article className="client-planning-summary-item">
                    <small>Date selectionnee</small>
                    <strong>{selectedAgendaDateLabel}</strong>
                  </article>
                </section>

                <div className="client-planning-date-nav">
                  <Link
                    className="client-date-nav-btn"
                    scroll={false}
                    href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: shiftDateKeyByDays(agendaDate, -agendaNavigationStep) })}
                    aria-label={agendaView === "week" ? "Semaine precedente" : "Jour precedent"}
                  >
                    ←
                  </Link>
                  <div className="client-date-strip">
                    {stripDayKeys.map((dayKey) => {
                      const token = agendaStripToken(dayKey);
                      const active = dayKey === agendaDate;
                      const daySummary = agendaDaySummary.get(dayKey) ?? { reservedCount: 0, availableCount: 0 };
                      return (
                        <Link
                          key={dayKey}
                          className={`client-date-pill ${active ? "active" : ""}`}
                          scroll={false}
                          href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: dayKey })}
                        >
                          <span>{token.weekday}</span>
                          <strong>{token.day}</strong>
                          <small>{token.month}</small>
                          <small className="client-date-pill-meta">
                            Res {daySummary.reservedCount} · Dispo {daySummary.availableCount}
                          </small>
                        </Link>
                      );
                    })}
                  </div>
                  <Link
                    className="client-date-nav-btn"
                    scroll={false}
                    href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: shiftDateKeyByDays(agendaDate, agendaNavigationStep) })}
                    aria-label={agendaView === "week" ? "Semaine suivante" : "Jour suivant"}
                  >
                    →
                  </Link>
                </div>

                <div className="row spread client-planning-modes">
                  <div className="row">
                    <Link className={`mode-link ${agendaView === "day" ? "mode-active" : ""}`} scroll={false} href={withUpdatedQuery(rawParams, { tab: "planning", agenda_view: "day" })}>
                      Jour
                    </Link>
                    <Link className={`mode-link ${agendaView === "week" ? "mode-active" : ""}`} scroll={false} href={withUpdatedQuery(rawParams, { tab: "planning", agenda_view: "week" })}>
                      Semaine
                    </Link>
                    <Link className={`mode-link ${agendaView === "agenda" ? "mode-active" : ""}`} scroll={false} href={withUpdatedQuery(rawParams, { tab: "planning", agenda_view: "agenda" })}>
                      Agenda
                    </Link>
                  </div>
                  <div className="row">
                    <span className="badge">{agendaRange.title}</span>
                    <Link className="mode-link" scroll={false} href={withUpdatedQuery(rawParams, { tab: "planning", agenda_date: todayKeyInTimezone(timezone) })}>
                      Aujourd'hui
                    </Link>
                  </div>
                </div>
              </Card>

              <Card className="client-available-section">
                <div className="row spread">
                  <h2>{planningSectionTitle}</h2>
                    <span className="badge">{agendaSessionCount}</span>
                  </div>
                <p className="muted">{planningSectionSubtitle}</p>
                <div className="row client-planning-quick-filters">
                  <Link
                    className={`mode-link ${planningSlotFilter === "ALL" ? "mode-active" : ""}`}
                    scroll={false}
                    href={withUpdatedQuery(rawParams, { tab: "planning", planning_slot_filter: "ALL" })}
                  >
                    Tous
                  </Link>
                  <Link
                    className={`mode-link ${planningSlotFilter === "AVAILABLE" ? "mode-active" : ""}`}
                    scroll={false}
                    href={withUpdatedQuery(rawParams, { tab: "planning", planning_slot_filter: "AVAILABLE" })}
                  >
                    Disponibles uniquement
                  </Link>
                  <Link
                    className={`mode-link ${planningSlotFilter === "ALREADY_BOOKED" ? "mode-active" : ""}`}
                    scroll={false}
                    href={withUpdatedQuery(rawParams, { tab: "planning", planning_slot_filter: "ALREADY_BOOKED" })}
                  >
                    {planningShowsAllMembers ? "Reserves famille" : "Deja reserves"}
                  </Link>
                </div>
                <div className="client-planning-phone-surface">
                  {agendaDays.map((day) => {
                    const daySessions = filteredPlanningSessions(day.sessions);

                    return (
                      <article
                        key={`planning-phone-${day.key}`}
                        className={`client-planning-phone-day ${day.key === agendaDate ? "is-selected" : ""}`}
                      >
                        <div className="row spread agenda-day-header">
                          <h3>{day.label}</h3>
                          <span className="badge">{daySessions.length}</span>
                        </div>

                        {daySessions.length === 0 ? <p className="muted agenda-empty">Aucun cours</p> : null}

                        <div className="client-planning-phone-list">
                          {daySessions.map((session) => {
                            const sessionState = sessionPlanningState(session);
                            const {
                              accentColor,
                              canOpenBookingFlow,
                              contextLine,
                              coveredByFamilyOffer,
                              durationMinutes,
                              familyHighlightLine,
                              isReservedByMember,
                              openDetailsHref,
                              sessionIsPastOrStarted,
                            } = sessionState;
                            const primaryActionLabel = canOpenBookingFlow
                              ? "Reserver ce creneau"
                              : isReservedByMember
                                ? planningShowsAllMembers
                                  ? "Voir les membres"
                                  : "Voir la reservation"
                                : "Voir details";
                            const contextClass = isReservedByMember
                              ? "is-booked"
                              : coveredByFamilyOffer
                                ? "is-covered"
                                : sessionIsPastOrStarted
                                  ? "is-muted"
                                  : canOpenBookingFlow
                                    ? "is-open"
                                    : "is-muted";

                            return (
                              <article
                                key={`planning-phone-card-${session.id}`}
                                className={`client-planning-phone-card ${sessionIsPastOrStarted ? "is-past" : ""} ${isReservedByMember ? "is-booked" : ""}`}
                              >
                                <div className="client-planning-phone-card-head">
                                  <div className="client-planning-phone-card-copy">
                                    <h4 className="client-planning-phone-card-title">{session.title}</h4>
                                    <small className="client-planning-phone-card-line">
                                      🕒 {formatTime(session.start_at_utc, timezone)} - {formatTime(session.end_at_utc, timezone)}
                                    </small>
                                  </div>
                                  <span className="client-event-color" style={{ backgroundColor: accentColor }} aria-hidden="true" />
                                </div>

                                <small className="client-planning-phone-card-line">🎵 {session.course_type.name}</small>

                                <div className="client-planning-phone-card-stats">
                                  <span className="occ-badge">
                                    {session.booked_count}/{session.capacity_max}
                                  </span>
                                  <small className="client-planning-phone-card-stat">⏱ {durationMinutes} min</small>
                                </div>

                                {familyHighlightLine ? (
                                  <small className={`client-planning-phone-card-line ${isReservedByMember ? "is-booked" : coveredByFamilyOffer ? "is-covered" : "is-open"}`}>
                                    {familyHighlightLine}
                                  </small>
                                ) : null}

                                <small className="client-planning-phone-card-line">👨‍🏫 {sessionProfessorName(session)}</small>
                                <small className="client-planning-phone-card-line">📍 {session.location.name}</small>
                                <small className={`client-planning-phone-card-line ${contextClass}`}>{contextLine}</small>

                                <div className="client-planning-phone-card-actions">
                                  <Link className={`client-planning-phone-action ${canOpenBookingFlow ? "is-primary" : ""}`} scroll={false} href={openDetailsHref}>
                                    {primaryActionLabel}
                                  </Link>
                                </div>
                              </article>
                            );
                          })}
                        </div>
                      </article>
                    );
                  })}
                </div>
                <div className="client-planning-desktop-surface">
                <div className={`agenda-grid client-agenda-grid agenda-grid-${agendaView}`}>
                  {agendaDays.map((day) => {
                    const daySessions = filteredPlanningSessions(day.sessions);
                    const visibleSessions = agendaView === "day" ? daySessions : daySessions.slice(0, 4);
                    const hiddenSessions = agendaView === "day" ? [] : daySessions.slice(4);

                    return (
                      <article
                        key={day.key}
                        className={`agenda-day client-agenda-day client-agenda-day-${agendaView} ${agendaView === "week" && day.key === agendaDate ? "client-agenda-day-selected" : ""}`}
                      >
                        <div className="row spread agenda-day-header">
                          <h3>{day.label}</h3>
                          <span className="badge">{daySessions.length}</span>
                        </div>

                        {daySessions.length === 0 ? <p className="muted agenda-empty">Aucun cours</p> : null}

                        <div className="agenda-events">
                          {visibleSessions.map((session) => {
                            const sessionState = sessionPlanningState(session);
                            const compactAgendaCard = agendaView !== "day";
                            const {
                              accentColor,
                              canOpenBookingFlow,
                              contextLine,
                              coveredByFamilyOffer,
                              durationMinutes,
                              familyHighlightLine,
                              isReservedByMember,
                              openDetailsHref,
                              semanticBadgeClass,
                              semanticBadgeLabel,
                              sessionCtaLabel,
                              sessionIsPastOrStarted,
                              showSemanticBadge,
                            } = sessionState;

                            return (
                              <Link
                                key={session.id}
                                className="client-session-link"
                                scroll={false}
                                href={openDetailsHref}
                                aria-label={`Ouvrir le detail du creneau ${session.title}`}
                              >
                                <article
                                  className={`client-session-card ${compactAgendaCard ? "client-session-card-compact" : ""} ${isReservedByMember ? "client-session-card-booked" : ""} ${sessionIsPastOrStarted ? "client-session-card-past" : "client-session-card-upcoming"} ${statusClass(session.status)}`}
                                >
                                  {!compactAgendaCard ? (
                                    <div className="client-session-timebox">
                                      <span aria-hidden="true">🕒</span>
                                      <strong>{formatTime(session.start_at_utc, timezone)}</strong>
                                      <small>{formatTime(session.end_at_utc, timezone)}</small>
                                    </div>
                                  ) : null}

                                  {compactAgendaCard ? (
                                    <div className="client-session-card-mobile">
                                      <div className="client-session-card-mobile-head">
                                        <div className="client-session-card-mobile-head-copy">
                                          <h3 className="client-session-card-mobile-title">{session.title}</h3>
                                          <small className="client-session-card-mobile-time">
                                            🕒 {formatTime(session.start_at_utc, timezone)} - {formatTime(session.end_at_utc, timezone)}
                                          </small>
                                        </div>
                                        <span className="client-event-color" style={{ backgroundColor: accentColor }} aria-hidden="true" />
                                      </div>

                                      <small className="client-session-card-mobile-meta">🎵 {session.course_type.name}</small>

                                      <div className="client-session-card-mobile-stats">
                                        <span className="occ-badge">
                                          {session.booked_count}/{session.capacity_max}
                                        </span>
                                        <small className="client-session-card-mobile-stat-text">⏱ {durationMinutes} min</small>
                                      </div>

                                      {familyHighlightLine ? (
                                        <small className={`client-session-card-mobile-note ${isReservedByMember ? "is-booked" : "is-open"}`}>
                                          {familyHighlightLine}
                                        </small>
                                      ) : null}

                                      <small className="client-session-card-mobile-meta">👨‍🏫 {sessionProfessorName(session)}</small>
                                      <small className="client-session-card-mobile-meta">📍 {session.location.name}</small>
                                      <small
                                        className={`client-session-card-mobile-note ${
                                          sessionIsPastOrStarted ? "is-past" : coveredByFamilyOffer ? "is-covered" : ""
                                        }`}
                                      >
                                        {contextLine}
                                      </small>

                                      <div className="client-session-card-mobile-footer">
                                        {showSemanticBadge ? <span className={`status-badge ${semanticBadgeClass}`}>{semanticBadgeLabel}</span> : null}
                                        <span className={`client-session-cta ${canOpenBookingFlow ? "ready" : ""}`}>{sessionCtaLabel}</span>
                                      </div>
                                    </div>
                                  ) : null}

                                  <div
                                    className={`agenda-event client-agenda-event ${compactAgendaCard ? "client-session-card-desktop" : ""} ${statusClass(session.status)}`}
                                  >
                                    <div className="row spread client-event-head">
                                      <h3 className="event-title">{session.title}</h3>
                                      <div className="client-event-head-right">
                                        <span className="client-event-color" style={{ backgroundColor: accentColor }} aria-hidden="true" />
                                      </div>
                                    </div>
                                    {compactAgendaCard ? <small className="event-meta">🕒 {formatTime(session.start_at_utc, timezone)} - {formatTime(session.end_at_utc, timezone)}</small> : null}
                                    <small className="event-meta">🎵 {session.course_type.name}</small>
                                    <div className="row">
                                      <span className="occ-badge">{session.booked_count}/{session.capacity_max}</span>
                                      <small className="event-meta">⏱ {durationMinutes} min</small>
                                    </div>
                                    {familyHighlightLine ? (
                                      <small className={`event-meta client-planning-family-line ${isReservedByMember ? "is-booked" : "is-open"}`}>
                                        {familyHighlightLine}
                                      </small>
                                    ) : null}
                                    <small className="event-meta event-meta-secondary">👨‍🏫 {sessionProfessorName(session)}</small>
                                    <small className="event-meta event-meta-secondary">📍 {session.location.name}</small>
                                    <small className="event-meta event-meta-secondary">{contextLine}</small>

                                    <div className="row client-event-footer">
                                      {showSemanticBadge ? <span className={`status-badge ${semanticBadgeClass}`}>{semanticBadgeLabel}</span> : null}
                                      <span className={`client-session-cta ${canOpenBookingFlow ? "ready" : ""}`}>{sessionCtaLabel}</span>
                                    </div>
                                  </div>
                                </article>
                              </Link>
                            );
                          })}

                          {hiddenSessions.length > 0 ? (
                            <details className="agenda-more-block client-more-block">
                              <summary>+{hiddenSessions.length} autres</summary>
                              <div className="agenda-events">
                                {hiddenSessions.map((session) => {
                                  const href = withUpdatedQuery(rawParams, {
                                    tab: "planning",
                                    session_id: session.id,
                                    ok: null,
                                    error: null,
                                    session_ok: null,
                                    session_error: null,
                                  });
                                  return (
                                    <Link key={`${day.key}-${session.id}`} className="client-session-link client-session-link-compact" scroll={false} href={href}>
                                      <article className={`agenda-event client-agenda-event ${statusClass(session.status)}`}>
                                        <p className="muted">
                                          {formatTime(session.start_at_utc, timezone)} - {formatTime(session.end_at_utc, timezone)}
                                        </p>
                                        <h3 className="event-title">{session.title}</h3>
                                        <small className="event-meta">🎵 {session.course_type.name}</small>
                                        <small className="event-meta">📍 {session.location.name}</small>
                                      </article>
                                    </Link>
                                  );
                                })}
                              </div>
                            </details>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
                </div>
              </Card>

              {selectedSession ? (
                <section className="modal-overlay">
                  <article className="modal-panel modal-client-session-details">
                    <Link
                      className="close-link"
                      scroll={false}
                      href={withUpdatedQuery(rawParams, {
                        tab: "planning",
                        session_id: null,
                        session_ok: null,
                        session_error: null,
                      })}
                      aria-label="Fermer le detail du creneau"
                    >
                      ✕
                    </Link>

                    <header className="client-session-modal-header">
                      <h2>{selectedSession.title}</h2>
                      <p className="muted">
                        {formatDateTime(selectedSession.start_at_utc, timezone)} - {formatTime(selectedSession.end_at_utc, timezone)}
                      </p>
                      <div className="row">
                        <span className="occ-badge">
                          {selectedSession.booked_count}/{selectedSession.capacity_max}
                        </span>
                        <span className={`status-badge ${statusClass(selectedSession.status)}`}>{statusLabel(selectedSession.status)}</span>
                        {!selectedSession.online_booking_enabled ? <span className="badge">Reservation en ligne fermee</span> : null}
                        {selectedSessionBooking ? (
                          <span className={`status-badge ${statusClass(selectedSessionBooking.status)}`}>
                            {statusLabel(selectedSessionBooking.status)}
                          </span>
                        ) : null}
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

                    {sessionOkMessage ? <section className="flash-ok modal-card">{sessionOkMessage}</section> : null}
                    {sessionErrorMessage ? <section className="flash-err modal-card">{sessionErrorMessage}</section> : null}

                    <footer className="row spread modal-card">
                      <Link
                        className="reset-link"
                        scroll={false}
                        href={withUpdatedQuery(rawParams, {
                          tab: "planning",
                          session_id: null,
                          session_ok: null,
                          session_error: null,
                        })}
                      >
                        Retour au planning
                      </Link>
                      <div className="row">
                        {selectedSessionCanCancel && selectedSessionBooking ? (
                          <form action={cancelBookingAction}>
                            <input type="hidden" name="booking_id" value={selectedSessionBooking.id} />
                            <input
                              type="hidden"
                              name="return_to"
                              value={withUpdatedQuery(rawParams, { tab: "planning", session_id: selectedSession.id })}
                            />
                            <button className="danger" type="submit">
                              Annuler la reservation
                            </button>
                          </form>
                        ) : null}
                        {selectedSessionCanBook ? (
                          <form action={bookSessionAction}>
                            <input type="hidden" name="session_id" value={selectedSession.id} />
                            <input type="hidden" name="booking_user_id" value={bookingOwnerId ?? ""} />
                            <input
                              type="hidden"
                              name="return_to"
                              value={withUpdatedQuery(rawParams, { tab: "planning", session_id: selectedSession.id })}
                            />
                            <button type="submit">Reserver maintenant</button>
                          </form>
                        ) : planningShowsAllMembers ? (
                          <div className="stack-sm">
                            {selectedSessionVisibleBookings.length > 0 ? (
                              <>
                                <span className="badge">
                                  Deja reserve pour {selectedSessionVisibleBookings.map((booking) => booking.owner_display_name).join(", ")}
                                </span>
                                <div className="row client-planning-member-actions">
                                  {selectedSessionVisibleBookings.map((booking) => (
                                    <Link
                                      key={`session-member-${booking.id}`}
                                      className="mode-link"
                                      scroll={false}
                                      href={withUpdatedQuery(rawParams, {
                                        tab: "planning",
                                        booking_owner_id: booking.owner_client_id,
                                        session_id: selectedSession.id,
                                        session_ok: null,
                                        session_error: null,
                                      })}
                                    >
                                      Voir {booking.owner_display_name}
                                    </Link>
                                  ))}
                                </div>
                              </>
                            ) : selectedSessionAvailableMembers.length > 0 ? (
                              <>
                                <span className="badge">Reserver ce creneau pour :</span>
                                <div className="row client-planning-member-actions">
                                  {selectedSessionAvailableMembers.map((member) => (
                                    <Link
                                      key={`session-available-member-${member.id}`}
                                      className="mode-link"
                                      scroll={false}
                                      href={withUpdatedQuery(rawParams, {
                                        tab: "planning",
                                        booking_owner_id: member.id,
                                        session_id: selectedSession.id,
                                        session_ok: null,
                                        session_error: null,
                                      })}
                                    >
                                      {member.display_name}
                                    </Link>
                                  ))}
                                </div>
                              </>
                            ) : selectedSessionCoveredMembers.length > 0 ? (
                              <>
                                <span className="badge">
                                  Couvert par forfait pour {selectedSessionCoveredMembers.map((member) => member.display_name).join(", ")}
                                </span>
                                <span className="muted">La reservation se fait hors portail pour ce type d'offre.</span>
                              </>
                            ) : (
                              <>
                                <span className="badge">
                                  {selectedSessionIsPastOrStarted
                                    ? "Creneau passe: reservation fermee"
                                    : selectedSessionFamilyIneligibleReason || "Reservation indisponible"}
                                </span>
                                {!selectedSessionIsPastOrStarted &&
                                selectedSessionOnlineBookingEnabled &&
                                selectedSessionVisibleBookings.length === 0 &&
                                selectedSessionAvailableMembers.length === 0 ? (
                                  <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                                    Voir les offres compatibles
                                  </a>
                                ) : null}
                              </>
                            )}
                          </div>
                        ) : (
                          <div className="stack-sm">
                            <span className="badge">
                              {selectedSessionIsPastOrStarted
                                ? "Creneau passe: reservation fermee"
                                : selectedSessionBooking
                                  ? "Deja reserve pour ce membre"
                                  : selectedSessionIneligibleReason || "Reservation indisponible"}
                            </span>
                            {!selectedSessionIsPastOrStarted &&
                            !selectedSessionBooking &&
                            selectedSessionOnlineBookingEnabled &&
                            !selectedSessionEligibleByPlan &&
                            selectedSessionCoveredMembers.length === 0 ? (
                              <a className="mode-link" href={withUpdatedQuery(rawParams, { tab: "offers" })}>
                                Voir les offres compatibles
                              </a>
                            ) : null}
                          </div>
                        )}
                      </div>
                    </footer>
                  </article>
                </section>
              ) : null}

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
                    <option value="ALL">Tous les membres</option>
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
                            <td>{formatDateTime(booking.session.start_at_utc, timezone)}</td>
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
                        <p className="muted">{formatDateTime(booking.session.start_at_utc, timezone)}</p>
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
                                    href={invoice.download_url || withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: invoice.id })}
                                    target={invoice.download_url ? "_blank" : undefined}
                                    rel={invoice.download_url ? "noreferrer" : undefined}
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
                          <option value="ALL">Tous les membres</option>
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
                  {financeStatusFilter !== "ALL" ? <span className="badge">Statut: {visibleFinanceStatusOptions.find((item) => item.value === financeStatusFilter)?.label}</span> : null}
                  {financePeriodFilter !== "ALL" ? <span className="badge">Periode: {financePeriodLabel(financePeriodFilter)}</span> : null}
                  <span className="badge">Arrêté: {formatDate(financeAsOfDateKey)}</span>
                  {financeView === "transactions" && financeSourceFilter !== "ALL" ? <span className="badge">Type: {sourceLabel(financeSourceFilter)}</span> : null}
                </FilterChipsBar>
              </SectionCard>

              {financeView === "transactions" ? (
                <SectionCard title="Transactions" className="client-finance-list-card" action={<span className="badge">{filteredPaymentRows.length}</span>}>
                  {filteredPaymentRows.length === 0 ? (
                    <p className="muted">Aucune transaction sur cette selection.</p>
                  ) : (
                    <div className="client-finance-list">
                      {pagedPaymentRows.map(({ row, linkedInvoice, effectiveFinanceStatus, occurredAtForDisplay }) => {
                        const canPayNow = canPayNowForPayment(row);
                        const isBilled = Boolean(linkedInvoice);
                        return (
                          <TransactionRow
                            key={`tx-${row.id}`}
                            typeBadge={<span className={`status-pill ${isBilled ? "status-ok" : "status-off"}`}>{isBilled ? "Facturé" : "Non facturé"}</span>}
                            label={row.label}
                            meta={`${formatDateTime(occurredAtForDisplay)} · ${row.owner_display_name} · ${sourceLabel(row.source)}`}
                            amount={toMoney(row.total_incl_vat, row.currency)}
                            statusBadge={
                              <span className={`status-pill ${statusClass(effectiveFinanceStatus)}`}>
                                {financeStatusLabel(effectiveFinanceStatus)}
                              </span>
                            }
                            actions={
                              <div className="row client-finance-card-actions">
                                {linkedInvoice ? (
                                  <a
                                    className="mode-link"
                                    href={
                                      linkedInvoice.download_url ||
                                      withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: linkedInvoice.id })
                                    }
                                    target={linkedInvoice.download_url ? "_blank" : undefined}
                                    rel={linkedInvoice.download_url ? "noreferrer" : undefined}
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
                        const invoiceIsPaid = normalizeStatus(row.status) === "PAID";
                        const canPayInvoice =
                          !invoiceIsPaid &&
                          ((linkedPayment ? canPayNowForPayment(linkedPayment) : false) || Boolean(row.payment_url));
                        return (
                          <CompactInvoiceRow
                            key={`inv-${row.id}`}
                            title={compactId(row.invoice_number)}
                            statusBadge={<span className={`status-pill ${statusClass(row.status)}`}>{financeStatusLabel(row.status)}</span>}
                            meta={`${toMoney(row.total_incl_vat, row.currency)} · ${formatDate(row.issued_at)} · ${row.owner_display_name}`}
                            subline={row.label}
                            actions={
                              <div className="row client-finance-card-actions">
                                {invoiceIsPaid ? (
                                  <span className="mode-link client-card-primary-action disabled" aria-disabled="true">
                                    Payer
                                  </span>
                                ) : canPayInvoice ? (
                                  <form action={openClientPaymentCheckoutAction}>
                                    {linkedPayment ? <input type="hidden" name="payment_id" value={linkedPayment.id} /> : null}
                                    {row.payment_url ? <input type="hidden" name="payment_url" value={row.payment_url} /> : null}
                                    <input type="hidden" name="return_to" value={withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices" })} />
                                    <button type="submit" className="client-card-primary-action">Payer</button>
                                  </form>
                                ) : (
                                  <a
                                    className="mode-link client-card-primary-action"
                                    href={row.download_url || withUpdatedQuery(rawParams, { tab: "finance", finance_view: "invoices", invoice_id: row.id })}
                                    target={row.download_url ? "_blank" : undefined}
                                    rel={row.download_url ? "noreferrer" : undefined}
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
                    <option value="ALL">Tous les membres</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="row">
                  <button type="submit">🔎</button>
                  <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "messages", message_scope: "LAST_3_MONTHS", member_id: null, message_id: null })}>
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
                        <th>Creneau</th>
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
                          <td>{msg.session_title}</td>
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
                  <article className="item client-message-detail">
                    <div className="row spread">
                      <h4>{selectedMessage.subject_preview || "Message sans sujet"}</h4>
                      <a className="reset-link" href={withUpdatedQuery(rawParams, { tab: "messages", message_id: null })}>
                        Fermer
                      </a>
                    </div>
                    <p className="muted">
                      {formatDateTime(selectedMessage.sent_at ?? selectedMessage.scheduled_for_utc)} · {selectedMessage.owner_display_name} · {selectedMessage.channel}
                    </p>
                    <pre className="client-message-detail-content">
                      {selectedMessage.content_preview || "Contenu indisponible"}
                    </pre>
                  </article>
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
                              subtitle={member.email}
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
                      <strong>Confidentialite</strong>
                      <p className="muted">Choisissez la visibilite du profil dans le portail etudiant.</p>
                      <label className="client-switch-row"><span>Afficher dans les contacts du portail etudiant</span><span className={`client-switch ${me.portal_contact_visible ? "on" : ""}`} /></label>
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
                              <p className="muted">{member.email}</p>
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
                    <strong>Confidentialite</strong>
                    <label className="client-switch-row"><span>Afficher dans les contacts du portail etudiant</span><span className={`client-switch ${me.portal_contact_visible ? "on" : ""}`} /></label>
                  </article>
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

                    <label className="checkline">
                      <input type="checkbox" name="portal_contact_visible" defaultChecked={me.portal_contact_visible} />
                      <span className="client-switch-label">Afficher dans les contacts du portail etudiant</span>
                    </label>
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
