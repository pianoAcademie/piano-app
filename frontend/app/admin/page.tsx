import Link from "next/link";
import { redirect } from "next/navigation";

import {
  adminAddClientToSessionAction,
  adminRemoveClientFromSessionAction,
  adminSendSessionBroadcastAction,
  adminUpdateSessionAttendanceAction,
  adminUpdateSessionBookingNoteAction,
  adminUpdateSessionGroupNoteAction,
  cancelAdminSessionAction,
  createAdminSessionAction,
  deleteAdminSessionAction,
  duplicateAdminSessionAction,
  shiftAdminSessionAction,
  updateAdminSessionAction,
} from "../../lib/actions";
import { getAdminToken } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import AutoSubmitSelect from "../../components/auto-submit-select";
import RichMessageEditor from "../../components/rich-message-editor";
import SearchMultiSelect from "../../components/search-multi-select";
import SessionTimeFields from "../../components/session-time-fields";
import SessionVisibilityFields from "../../components/session-visibility-fields";
import ModalA11yFrame from "../../components/modal-a11y-frame";
import PresenceButtonsGroup from "../../components/presence-buttons-group";
import DayEventsDrawer from "../../components/planning/day-events-drawer";
import MonthDayCard from "../../components/planning/month-day-card";
import SessionEditModalBridge from "../../components/planning/session-edit-modal-bridge";
import SessionCreateMainFields from "../../components/planning/session-create-main-fields";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../lib/ui-i18n";
import type {
  AdminClientOut,
  AdminMessagingTemplateOut,
  AdminProfessorOut,
  AdminSessionBookingOut,
  AdminSessionOut,
  CourseTypeOut,
  LocationOut,
  SessionAudienceScope,
  UserOut,
} from "../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type AgendaView = "month" | "week" | "day";
type ApplyScope = "ONE" | "SERIES_FUTURE" | "SERIES_ALL";
type SlotEditTab = "general" | "schedule" | "visibility" | "notes";
type AttendanceFilter = "all" | "missing";
type ComposerTab = "content" | "recipients" | "send";

type CreateSessionDraft = {
  title: string;
  course_type_id: string;
  professor_id: string;
  location_id: string;
  session_timezone: string;
  start_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: string;
  capacity_max: string;
  is_all_day: "1" | "0";
  zoom_link: string;
  recurrence_mode: string;
  recurrence_frequency: string;
  recurrence_interval: string;
  recurrence_until_date: string;
  recurrence_time_basis: string;
  visibility_scopes: SessionAudienceScope[];
  booking_scopes: SessionAudienceScope[];
  external_booking_price_ttc: string;
  show_external_remaining_seats: "1" | "0";
  public_description: string;
  private_description: string;
  professor_reminder_note: string;
};

type AgendaRange = {
  from: Date;
  to: Date;
  dayKeys: string[];
  title: string;
};

type PlanningQuery = {
  agendaView: AgendaView;
  agendaDate: string;
  timezone: string;
  locationId: string;
  locationIds: string[];
  activityIds: string[];
  courseTypeId: string;
  professorIds: string[];
  status: string;
  clientStatus: string;
  clientIds: string[];
  createOpen: boolean;
  showFilters: boolean;
  dayDetails: string;
};

const PLANNING_TIMEZONES: Array<{ value: string; label: string }> = [
  { value: "Europe/Paris", label: "France (Europe/Paris)" },
  { value: "Europe/Brussels", label: "Belgique (Europe/Brussels)" },
  { value: "Europe/Zurich", label: "Suisse (Europe/Zurich)" },
  { value: "Europe/London", label: "Royaume-Uni (Europe/London)" },
  { value: "Europe/Madrid", label: "Espagne (Europe/Madrid)" },
  { value: "America/New_York", label: "Etats-Unis Est (America/New_York)" },
  { value: "America/Los_Angeles", label: "Etats-Unis Ouest (America/Los_Angeles)" },
];

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function readMultiParam(params: SearchParams, key: string): string[] {
  const value = params[key];
  const tokens = Array.isArray(value) ? value : value ? [value] : [];
  const entries = tokens
    .flatMap((token) => String(token).split(","))
    .map((token) => token.trim())
    .filter((token) => token.length > 0);
  return Array.from(new Set(entries));
}

function hasQueryParam(params: SearchParams, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(params, key);
}

function parseAgendaView(value: string): AgendaView {
  if (value === "week" || value === "day") {
    return value;
  }
  return "month";
}

function safeDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function resolveTimezone(value: string | null | undefined): string {
  const fallback = "Europe/Paris";
  const candidate = (value ?? "").trim();
  if (!candidate) {
    return fallback;
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: candidate }).format(new Date());
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

function startOfMonthUtc(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function startOfWeekUtc(date: Date): Date {
  const day = date.getUTCDay();
  const offsetFromMonday = (day + 6) % 7;
  return addUtcDays(date, -offsetFromMonday);
}

function endOfWeekSundayUtc(date: Date): Date {
  return addUtcDays(startOfWeekUtc(date), 6);
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

function agendaDayLabel(dayKey: string, view: AgendaView, language: UiLanguage = "fr"): string {
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

function agendaDayLongLabel(dayKey: string, language: UiLanguage = "fr"): string {
  const date = keyToUtcDate(dayKey);
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function buildAgendaRange(view: AgendaView, focusDayKey: string, language: UiLanguage = "fr"): AgendaRange {
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

  const monthStart = startOfMonthUtc(focusDate);
  const nextMonth = new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + 1, 1));
  const monthEnd = addUtcDays(nextMonth, -1);
  const from = startOfWeekUtc(monthStart);
  const visibleLastDay = endOfWeekSundayUtc(monthEnd);
  const toExclusive = addUtcDays(visibleLastDay, 1);
  const to = new Date(toExclusive.getTime() - 1);

  const dayKeys: string[] = [];
  let cursor = new Date(from.getTime());
  while (cursor < toExclusive) {
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

function shiftAgendaDate(view: AgendaView, agendaDate: string, direction: -1 | 1): string {
  const focusDate = keyToUtcDate(agendaDate);

  if (view === "month") {
    return utcDateToKey(new Date(Date.UTC(focusDate.getUTCFullYear(), focusDate.getUTCMonth() + direction, 1)));
  }

  const dayStep = view === "week" ? 7 : 1;
  return utcDateToKey(addUtcDays(focusDate, direction * dayStep));
}

function agendaNavigationHint(view: AgendaView, language: UiLanguage = "fr"): string {
  if (view === "month") {
    return uiText(language, "admin.planning.navigation.month");
  }
  if (view === "week") {
    return uiText(language, "admin.planning.navigation.week");
  }
  return uiText(language, "admin.planning.navigation.day");
}

function toDateTimeLocalUtcValue(value: string): string {
  return safeDate(value)?.toISOString().slice(0, 16) ?? "";
}

function toDateInputInTimezone(value: string, timezone: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "";
  }
  const safeTimezone = resolveTimezone(timezone);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: safeTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(parsed);
  const year = getDatePart(parts, "year");
  const month = getDatePart(parts, "month");
  const day = getDatePart(parts, "day");
  return `${year}-${month}-${day}`;
}

function toTimeInputInTimezone(value: string, timezone: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "";
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    timeZone: resolveTimezone(timezone),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatDateKeyLabel(value: string, language: UiLanguage = "fr"): string {
  if (!isDateKey(value)) {
    return "-";
  }
  return new Intl.DateTimeFormat(localeForUiLanguage(language), {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(keyToUtcDate(value));
}

function formatDate(value: string, timezone?: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  const resolvedTimezone = timezone ? resolveTimezone(timezone) : "";
  if (resolvedTimezone) {
    const dateKey = toDateInputInTimezone(value, resolvedTimezone);
    const timeKey = toTimeInputInTimezone(value, resolvedTimezone, language);
    if (dateKey && timeKey) {
      return `${formatDateKeyLabel(dateKey, language)}, ${timeKey}`;
    }
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string, timezone?: string, language: UiLanguage = "fr"): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
  }
  const resolvedTimezone = timezone ? resolveTimezone(timezone) : "";
  if (resolvedTimezone) {
    const timeKey = toTimeInputInTimezone(value, resolvedTimezone, language);
    if (timeKey) {
      return timeKey;
    }
  }
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stripHtml(raw: string): string {
  return raw
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\s*\/\s*p\s*>/gi, "\n")
    .replace(/<\s*\/\s*div\s*>/gi, "\n")
    .replace(/<\s*li\b[^>]*>/gi, "- ")
    .replace(/<[^>]+>/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function sessionTimeRangeLabel(session: AdminSessionOut, language: UiLanguage = "fr"): string {
  if (session.is_all_day) {
    return uiText(language, "admin.planning.all_day");
  }
  return `${formatTime(session.start_at_utc, session.timezone, language)} - ${formatTime(session.end_at_utc, session.timezone, language)}`;
}

function sessionDurationMinutes(session: AdminSessionOut): number | null {
  if (session.is_all_day) {
    return null;
  }
  const startMs = Date.parse(session.start_at_utc);
  const endMs = Date.parse(session.end_at_utc);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return null;
  }
  return Math.floor((endMs - startMs) / 60000);
}

function occupancyClass(bookedCount: number, capacityMax: number): string {
  if (capacityMax <= 0) {
    return "occ-low";
  }
  const ratio = bookedCount / capacityMax;
  if (ratio >= 0.9) {
    return "occ-high";
  }
  if (ratio >= 0.5) {
    return "occ-medium";
  }
  return "occ-low";
}

function statusClass(status: string): string {
  if (status === "CANCELLED") {
    return "status-cancelled";
  }
  if (status === "NO_SHOW") {
    return "status-cancelled";
  }
  if (status === "EXCUSED_ABSENCE" || status === "WAITLISTED") {
    return "status-waitlist";
  }
  if (status === "BOOKED") {
    return "status-booked";
  }
  if (status === "COMPLETED") {
    return "status-completed";
  }
  if (status === "ATTENDED") {
    return "status-completed";
  }
  return "status-scheduled";
}

function bookingEnrollmentLabel(status: string, language: UiLanguage = "fr"): string {
  if (status === "WAITLISTED") {
    return uiText(language, "admin.planning.enrollment.waitlist");
  }
  if (status === "BOOKED") {
    return uiText(language, "admin.planning.enrollment.booked");
  }
  if (status === "CANCELLED") {
    return uiText(language, "admin.planning.enrollment.cancelled");
  }
  return uiText(language, "admin.planning.enrollment.booked");
}

function bookingPresenceLabel(status: string, language: UiLanguage = "fr"): string | null {
  if (status === "ATTENDED") {
    return uiText(language, "admin.planning.presence.attended");
  }
  if (status === "NO_SHOW") {
    return uiText(language, "admin.planning.presence.absent");
  }
  if (status === "EXCUSED_ABSENCE") {
    return uiText(language, "admin.planning.presence.excused");
  }
  return null;
}

function attendanceChoiceLabel(status: string, language: UiLanguage = "fr"): string {
  if (status === "ATTENDED") {
    return uiText(language, "admin.planning.attendance.attended");
  }
  if (status === "NO_SHOW") {
    return uiText(language, "admin.planning.attendance.no_show");
  }
  if (status === "EXCUSED_ABSENCE") {
    return uiText(language, "admin.planning.attendance.excused");
  }
  return uiText(language, "admin.planning.attendance.to_fill");
}

function canEditAttendance(status: string): boolean {
  return ["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(status);
}

function attendanceBadgeToneClass(status: string): string {
  if (status === "ATTENDED") {
    return "status-ok";
  }
  if (status === "NO_SHOW") {
    return "status-cancelled";
  }
  if (status === "EXCUSED_ABSENCE") {
    return "status-scheduled";
  }
  return "status-waitlist";
}

function sessionTypeLabel(session: AdminSessionOut, locationLabel: string, language: UiLanguage = "fr"): string {
  const lowerLocation = locationLabel.toLowerCase();
  if (lowerLocation.includes("online") || lowerLocation.includes("ligne")) {
    return uiText(language, "admin.planning.session_type.online");
  }
  if (lowerLocation.includes("domicile")) {
    return uiText(language, "admin.planning.session_type.home");
  }
  if (session.is_private) {
    return uiText(language, "admin.planning.session_type.private");
  }
  return uiText(language, "admin.planning.session_type.group");
}

function normalizeSessionAudienceScope(raw: unknown, fallback: SessionAudienceScope): SessionAudienceScope {
  const value = String(raw ?? "")
    .trim()
    .toUpperCase();
  if (value === "EXTERNAL" || value === "SUBSCRIPTION" || value === "FORFAIT" || value === "PRIVATE") {
    return value;
  }
  return fallback;
}

function normalizeSessionAudienceScopes(raw: unknown, fallback: SessionAudienceScope[]): SessionAudienceScope[] {
  const values = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(",") : raw == null ? [] : [raw];
  const seen = new Set<SessionAudienceScope>();
  const normalized: SessionAudienceScope[] = [];
  for (const value of values) {
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

function sessionAudienceScopeLabel(scope: SessionAudienceScope, language: UiLanguage = "fr"): string {
  if (scope === "EXTERNAL") return uiText(language, "admin.planning.audience.external");
  if (scope === "SUBSCRIPTION") return uiText(language, "admin.planning.audience.subscription");
  if (scope === "FORFAIT") return uiText(language, "admin.planning.audience.forfait");
  if (scope === "PRIVATE") return uiText(language, "admin.planning.audience.private");
  return scope;
}

function sessionAudienceScopesLabel(scopes: SessionAudienceScope[], language: UiLanguage = "fr"): string {
  if (scopes.length === 1 && scopes[0] === "PRIVATE") {
    return uiText(language, "admin.planning.audience.private");
  }
  return scopes.map((scope) => sessionAudienceScopeLabel(scope, language)).join(" + ");
}

function messageAudienceLabel(
  audience: "STUDENTS" | "PARENTS" | "STUDENTS_AND_PARENTS" | "PROFESSOR" | "ADMINS" | "SELF",
  language: UiLanguage = "fr",
): string {
  if (audience === "STUDENTS") return uiText(language, "admin.planning.message_audience.students");
  if (audience === "PARENTS") return uiText(language, "admin.planning.message_audience.parents");
  if (audience === "STUDENTS_AND_PARENTS") return uiText(language, "admin.planning.message_audience.students_and_parents");
  if (audience === "PROFESSOR") return uiText(language, "admin.planning.message_audience.professor");
  if (audience === "ADMINS") return uiText(language, "admin.planning.message_audience.admins");
  return uiText(language, "admin.planning.message_audience.self");
}

function noteDestinationLabel(
  destination: "PRIVATE" | "STUDENTS" | "PARENTS" | "STUDENTS_AND_PARENTS" | "PROFESSOR" | "ADMINS" | "SELF",
  language: UiLanguage = "fr",
): string {
  if (destination === "PRIVATE") return uiText(language, "admin.planning.message_audience.private");
  return messageAudienceLabel(destination, language);
}

function isBookingRemovable(session: AdminSessionOut, booking: AdminSessionBookingOut): boolean {
  if (booking.status === "CANCELLED") {
    return false;
  }

  const lockedStatuses = new Set(["ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"]);
  if (!lockedStatuses.has(booking.status)) {
    return true;
  }

  const startsAtMs = Date.parse(session.start_at_utc);
  return session.status === "SCHEDULED" && Number.isFinite(startsAtMs) && startsAtMs > Date.now();
}

function buildPlanningHref(query: PlanningQuery): string {
  const sp = new URLSearchParams();
  sp.set("agenda_view", query.agendaView);
  sp.set("agenda_date", query.agendaDate);
  sp.set("timezone", query.timezone);

  if (query.locationId) {
    sp.set("location_id", query.locationId);
  }
  if (query.courseTypeId) {
    sp.set("course_type_id", query.courseTypeId);
  }
  for (const locationId of query.locationIds) {
    if (locationId) {
      sp.append("location_ids", locationId);
    }
  }
  for (const activityId of query.activityIds) {
    if (activityId) {
      sp.append("activity_ids", activityId);
    }
  }
  for (const professorId of query.professorIds) {
    if (professorId) {
      sp.append("professor_ids", professorId);
    }
  }
  for (const clientId of query.clientIds) {
    if (clientId) {
      sp.append("client_ids", clientId);
    }
  }
  if (query.status && query.status !== "ALL") {
    sp.set("status", query.status);
  }
  if (query.clientStatus && query.clientStatus !== "ALL") {
    sp.set("client_status", query.clientStatus);
  }
  if (query.createOpen) {
    sp.set("create", "1");
  }
  if (query.showFilters) {
    sp.set("filters", "1");
  }
  if (query.dayDetails && isDateKey(query.dayDetails)) {
    sp.set("day_details", query.dayDetails);
  }

  return `/admin?${sp.toString()}`;
}

function withSessionInHref(href: string, sessionId: string): string {
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}session_id=${encodeURIComponent(sessionId)}`;
}

function withQueryParam(href: string, key: string, value: string): string {
  try {
    const url = new URL(href, "http://localhost");
    url.searchParams.set(key, value);
    return `${url.pathname}${url.search}`;
  } catch {
    return href;
  }
}

function removeQueryParam(href: string, key: string): string {
  try {
    const url = new URL(href, "http://localhost");
    url.searchParams.delete(key);
    return `${url.pathname}${url.search}`;
  } catch {
    return href;
  }
}

function recurrenceLabel(session: AdminSessionOut, language: UiLanguage = "fr"): string {
  if (!session.recurrence_rule) {
    return uiText(language, "admin.planning.recurrence.one_off");
  }
  const { frequency, interval, timeBasis } = parseRecurrenceRuleDefaults(session.recurrence_rule);

  let label = uiText(language, "admin.planning.recurrence.weekly_short");
  if (frequency === "DAILY") {
    label =
      interval > 1
        ? uiText(language, "admin.planning.recurrence.every_days", { count: interval })
        : uiText(language, "admin.planning.recurrence.daily_short");
  } else if (frequency === "WEEKLY") {
    label =
      interval > 1
        ? uiText(language, "admin.planning.recurrence.every_weeks", { count: interval })
        : uiText(language, "admin.planning.recurrence.weekly_short");
  } else if (frequency === "MONTHLY") {
    label =
      interval > 1
        ? uiText(language, "admin.planning.recurrence.every_months", { count: interval })
        : uiText(language, "admin.planning.recurrence.monthly_short");
  }
  if (timeBasis === "LOCAL") {
    return `${label} · ${uiText(language, "admin.planning.recurrence.fixed_local_time")}`;
  }
  return `${label} · ${uiText(language, "admin.planning.recurrence.fixed_utc_time")}`;
}

function isRecurringSession(session: AdminSessionOut): boolean {
  return Boolean(session.recurrence_group_id || session.recurrence_rule);
}

function recurrenceSummaryLabel(session: AdminSessionOut, language: UiLanguage = "fr"): string {
  if (!isRecurringSession(session)) {
    return uiText(language, "admin.planning.one_off_slot");
  }
  const parts = [recurrenceLabel(session, language)];
  if (session.recurrence_end_date) {
    parts.push(uiText(language, "admin.planning.recurrence.until_label", { date: formatDateKeyLabel(session.recurrence_end_date, language) }));
  }
  return `${uiText(language, "admin.planning.recurring_series")} · ${parts.join(" · ")}`;
}

function defaultApplyScope(session: AdminSessionOut): ApplyScope {
  if (session.recurrence_group_id) {
    return "SERIES_FUTURE";
  }
  return "ONE";
}

function parseSlotEditTab(value: string): SlotEditTab {
  if (value === "schedule" || value === "visibility" || value === "notes") {
    return value;
  }
  return "general";
}

function parseAttendanceFilter(value: string): AttendanceFilter {
  return value === "missing" ? "missing" : "all";
}

function parseComposerTab(value: string): ComposerTab {
  if (value === "recipients" || value === "send") {
    return value;
  }
  return "content";
}

function parseCreateSessionDraft(raw: string): CreateSessionDraft | null {
  const token = String(raw || "").trim();
  if (!token) {
    return null;
  }
  try {
    const decoded = Buffer.from(token, "base64url").toString("utf-8");
    const parsed = JSON.parse(decoded) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    const legacyVisibilityRaw = String(parsed.session_visibility ?? "")
      .trim()
      .toUpperCase();
    const legacyVisibilityScope: SessionAudienceScope = legacyVisibilityRaw === "PUBLIC" ? "EXTERNAL" : "PRIVATE";
    const visibilityScopes = normalizeSessionAudienceScopes(
      parsed.visibility_scopes ?? parsed.visibility_scope,
      [legacyVisibilityScope],
    );
    const legacyBookingScope: SessionAudienceScope =
      String(parsed.allow_online_booking ?? "") === "1" ? "EXTERNAL" : "PRIVATE";
    const bookingScopes: SessionAudienceScope[] =
      visibilityScopes.length === 1 && visibilityScopes[0] === "PRIVATE"
        ? ["PRIVATE"]
        : normalizeSessionAudienceScopes(
            parsed.booking_scopes ?? parsed.booking_scope,
            [legacyBookingScope],
          );
    return {
      title: String(parsed.title ?? ""),
      course_type_id: String(parsed.course_type_id ?? ""),
      professor_id: String(parsed.professor_id ?? ""),
      location_id: String(parsed.location_id ?? ""),
      session_timezone: String(parsed.session_timezone ?? ""),
      start_date: String(parsed.start_date ?? ""),
      start_time: String(parsed.start_time ?? ""),
      end_time: String(parsed.end_time ?? ""),
      duration_minutes: String(parsed.duration_minutes ?? ""),
      capacity_max: String(parsed.capacity_max ?? ""),
      is_all_day: String(parsed.is_all_day ?? "") === "1" ? "1" : "0",
      zoom_link: String(parsed.zoom_link ?? ""),
      recurrence_mode: String(parsed.recurrence_mode ?? "NONE"),
      recurrence_frequency: String(parsed.recurrence_frequency ?? "WEEKLY"),
      recurrence_interval: String(parsed.recurrence_interval ?? "1"),
      recurrence_until_date: String(parsed.recurrence_until_date ?? ""),
      recurrence_time_basis: String(parsed.recurrence_time_basis ?? "LOCAL"),
      visibility_scopes: visibilityScopes,
      booking_scopes: bookingScopes,
      external_booking_price_ttc: String(parsed.external_booking_price_ttc ?? ""),
      show_external_remaining_seats: String(parsed.show_external_remaining_seats ?? "1") === "0" ? "0" : "1",
      public_description: String(parsed.public_description ?? ""),
      private_description: String(parsed.private_description ?? ""),
      professor_reminder_note: String(parsed.professor_reminder_note ?? ""),
    };
  } catch {
    return null;
  }
}

function draftPositiveInteger(raw: string): number | null {
  const value = String(raw || "").trim();
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function draftNonNegativeInteger(raw: string): number | null {
  const value = String(raw || "").trim();
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function shouldShowLocationCue(sessions: AdminSessionOut[]): boolean {
  return new Set(sessions.map((session) => session.location_id)).size > 1;
}

function parseRecurrenceRuleDefaults(
  rawRule: string | null | undefined,
): { frequency: "DAILY" | "WEEKLY" | "MONTHLY"; interval: number; timeBasis: "LOCAL" | "UTC" } {
  const raw = String(rawRule || "").trim().toUpperCase();
  if (!raw) {
    return { frequency: "WEEKLY", interval: 1, timeBasis: "LOCAL" };
  }
  const [rulePart, basisPart] = raw.includes("@") ? raw.split("@", 2) : [raw, "UTC"];
  const [frequencyRaw, intervalRaw] = rulePart.includes(":") ? rulePart.split(":", 2) : [rulePart, "1"];
  const frequency = frequencyRaw === "DAILY" || frequencyRaw === "MONTHLY" ? frequencyRaw : "WEEKLY";
  const intervalParsed = Number.parseInt(intervalRaw || "1", 10);
  const interval = Number.isFinite(intervalParsed) && intervalParsed > 0 ? intervalParsed : 1;
  const timeBasis = basisPart === "LOCAL" ? "LOCAL" : "UTC";
  return { frequency, interval, timeBasis };
}

function clientDisplayName(client: AdminClientOut): string {
  const fullName = `${client.first_name ?? ""} ${client.last_name ?? ""}`.trim();
  return fullName || client.email;
}

function compactList(values: string[], limit = 2): string {
  if (values.length <= limit) {
    return values.join(", ");
  }
  return `${values.slice(0, limit).join(", ")} +${values.length - limit}`;
}

export default async function AdminPlanningPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const selectedCourseType = readParam(searchParams, "course_type_id");
  const selectedActivityIds = readMultiParam(searchParams, "activity_ids");
  const rawLocation = readParam(searchParams, "location_id");
  const hasQuickLocationParam = hasQueryParam(searchParams, "location_id");
  const selectedLocationIdsFromQuery = readMultiParam(searchParams, "location_ids");
  const selectedProfessorLegacy = readParam(searchParams, "professor_id");
  const selectedProfessorIdsFromQuery = readMultiParam(searchParams, "professor_ids");
  const selectedProfessorIds = selectedProfessorIdsFromQuery.length
    ? selectedProfessorIdsFromQuery
    : selectedProfessorLegacy
      ? [selectedProfessorLegacy]
      : [];
  const selectedClientIds = readMultiParam(searchParams, "client_ids");
  const selectedStatus = readParam(searchParams, "status") || "ALL";
  const selectedClientStatus = readParam(searchParams, "client_status") || "ALL";
  const timezone = resolveTimezone(readParam(searchParams, "timezone") || "Europe/Paris");
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const inputAgendaDate = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(inputAgendaDate) ? inputAgendaDate : todayKeyInTimezone(timezone);
  const createDraftRaw = readParam(searchParams, "create_draft");
  const createDraft = parseCreateSessionDraft(createDraftRaw);
  const filtersOpen = readParam(searchParams, "filters") === "1";
  const createOpen = readParam(searchParams, "create") === "1";
  const dayDetailsRaw = readParam(searchParams, "day_details");
  const dayDetails = isDateKey(dayDetailsRaw) ? dayDetailsRaw : "";
  const selectedSessionId = readParam(searchParams, "session_id");
  const attendanceModalOpen = readParam(searchParams, "attendance") === "1";
  const attendanceFilter = parseAttendanceFilter(readParam(searchParams, "attendance_filter").trim().toLowerCase());
  const notesModal = readParam(searchParams, "notes").toLowerCase();
  const groupNotesModalOpen = notesModal === "group";
  const groupNoteTab = parseComposerTab(readParam(searchParams, "note_tab").trim().toLowerCase());
  const groupNoteAdvancedMode = readParam(searchParams, "group_note_mode").trim().toLowerCase() === "advanced";
  const groupNoteTemplateId = readParam(searchParams, "group_note_template_id");
  const groupNoteDestinationRaw = readParam(searchParams, "note_destination").trim().toUpperCase();
  const groupNoteDestination =
    groupNoteDestinationRaw === "STUDENTS" ||
    groupNoteDestinationRaw === "PARENTS" ||
    groupNoteDestinationRaw === "STUDENTS_AND_PARENTS" ||
    groupNoteDestinationRaw === "PROFESSOR" ||
    groupNoteDestinationRaw === "ADMINS" ||
    groupNoteDestinationRaw === "SELF" ||
    groupNoteDestinationRaw === "PRIVATE"
      ? groupNoteDestinationRaw
      : "PRIVATE";
  const duplicateModalOpen = readParam(searchParams, "duplicate") === "1";
  const messageModalRaw = readParam(searchParams, "message").trim().toLowerCase();
  const sessionEmailModalOpen = messageModalRaw === "email";
  const sessionSmsModalOpen = messageModalRaw === "sms";
  const emailAudienceRaw = readParam(searchParams, "email_audience").trim().toUpperCase();
  const emailAudience =
    emailAudienceRaw === "PARENTS" ||
    emailAudienceRaw === "STUDENTS_AND_PARENTS" ||
    emailAudienceRaw === "PROFESSOR" ||
    emailAudienceRaw === "ADMINS" ||
    emailAudienceRaw === "SELF"
      ? emailAudienceRaw
      : "STUDENTS";
  const emailTab = parseComposerTab(readParam(searchParams, "email_tab").trim().toLowerCase());
  const emailAdvancedMode = readParam(searchParams, "email_mode").trim().toLowerCase() === "advanced";
  const bookingFocusId = readParam(searchParams, "booking_focus");
  const editSessionOpen = readParam(searchParams, "edit") === "1";
  const editTab = parseSlotEditTab(readParam(searchParams, "edit_tab").trim().toLowerCase());
  const notesAdvancedMode = readParam(searchParams, "notes_mode").trim().toLowerCase() === "advanced";
  const confirmActionRaw = readParam(searchParams, "confirm_action").toLowerCase();
  const confirmAction: "" | "cancel" | "delete" = confirmActionRaw === "cancel" || confirmActionRaw === "delete" ? confirmActionRaw : "";

  const selectedLocationIds = hasQuickLocationParam
    ? rawLocation
      ? [rawLocation]
      : []
    : selectedLocationIdsFromQuery.length
      ? selectedLocationIdsFromQuery
      : rawLocation
        ? [rawLocation]
        : [];

  const sessionsQuery = new URLSearchParams();
  const locationFilterIdsForApi = selectedLocationIds;
  for (const locationId of locationFilterIdsForApi) {
    sessionsQuery.append("location_ids", locationId);
  }
  if (selectedActivityIds.length === 0 && selectedCourseType) {
    sessionsQuery.set("course_type_id", selectedCourseType);
  }
  for (const professorId of selectedProfessorIds) {
    sessionsQuery.append("professor_ids", professorId);
  }
  for (const clientId of selectedClientIds) {
    sessionsQuery.append("client_ids", clientId);
  }
  if (selectedStatus !== "ALL") {
    sessionsQuery.set("status", selectedStatus);
  }
  if (selectedClientStatus !== "ALL") {
    sessionsQuery.set("client_status", selectedClientStatus);
  }
  const sessionsEndpoint = sessionsQuery.toString() ? `/api/v1/admin/sessions?${sessionsQuery.toString()}` : "/api/v1/admin/sessions";

  const [locationsResult, professorsResult, sessionsResult, clientsResult, groupNoteTemplatesResult] = await Promise.all([
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors", {}, token),
    backendRequest<AdminSessionOut[]>(sessionsEndpoint, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?active_only=true&limit=500", {}, token),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?kind=CUSTOM&channel=GROUP_NOTE",
      {},
      token,
    ),
  ]);

  const errors: string[] = [];

  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        errors.push(`locations: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();

  const professors = professorsResult.ok
    ? professorsResult.data
    : (() => {
        errors.push(`professors: ${professorsResult.message}`);
        return [] as AdminProfessorOut[];
      })();

  const sessions = sessionsResult.ok
    ? sessionsResult.data
    : (() => {
        errors.push(`sessions: ${sessionsResult.message}`);
        return [] as AdminSessionOut[];
      })();

  const clients = clientsResult.ok
    ? clientsResult.data
    : (() => {
        errors.push(`clients: ${clientsResult.message}`);
        return [] as AdminClientOut[];
      })();
  const groupNoteTemplates = groupNoteTemplatesResult.ok
    ? groupNoteTemplatesResult.data.filter((template) => template.active)
    : (() => {
        errors.push(`group-note-templates: ${groupNoteTemplatesResult.message}`);
        return [] as AdminMessagingTemplateOut[];
      })();

  const focusedLocationId = hasQuickLocationParam ? rawLocation : rawLocation || selectedLocationIdsFromQuery[0] || "";
  const focusedLocation = locations.find((location) => location.id === focusedLocationId) ?? null;

  const courseTypesEndpoint = focusedLocationId
    ? `/api/v1/course-types?location_id=${encodeURIComponent(focusedLocationId)}`
    : "/api/v1/course-types";
  const courseTypesResult = await backendRequest<CourseTypeOut[]>(courseTypesEndpoint, {}, token);
  const courseTypes = courseTypesResult.ok
    ? courseTypesResult.data
    : (() => {
        errors.push(`course-types: ${courseTypesResult.message}`);
        return [] as CourseTypeOut[];
      })();

  const queryForLinks: PlanningQuery = {
    agendaView,
    agendaDate,
    timezone,
    locationId: hasQuickLocationParam ? rawLocation : "",
    locationIds: selectedLocationIds,
    activityIds: selectedActivityIds,
    courseTypeId: selectedCourseType,
    professorIds: selectedProfessorIds,
    status: selectedStatus,
    clientStatus: selectedClientStatus,
    clientIds: selectedClientIds,
    createOpen,
    showFilters: filtersOpen,
    dayDetails,
  };

  const lectureHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const createHrefBase = buildPlanningHref({ ...queryForLinks, createOpen: true, showFilters: false, dayDetails: "" });
  const createHref = createDraftRaw ? withQueryParam(createHrefBase, "create_draft", createDraftRaw) : createHrefBase;
  const createCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const createFeedbackDismissHref = removeQueryParam(removeQueryParam(createHref, "ok"), "error");
  const baseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const sessionModalBaseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const dayDetailsCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const filtersHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: true, dayDetails: "" });
  const filtersCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const filtersResetHref = buildPlanningHref({
    ...queryForLinks,
    locationId: "",
    activityIds: [],
    courseTypeId: "",
    locationIds: [],
    professorIds: [],
    status: "ALL",
    clientStatus: "ALL",
    clientIds: [],
    createOpen: false,
    showFilters: false,
    dayDetails: "",
  });

  const previousAgendaDate = shiftAgendaDate(agendaView, agendaDate, -1);
  const nextAgendaDate = shiftAgendaDate(agendaView, agendaDate, 1);
  const todayAgendaKey = todayKeyInTimezone(timezone);

  const previousHref = buildPlanningHref({ ...queryForLinks, agendaDate: previousAgendaDate, createOpen: false, dayDetails: "" });
  const nextHref = buildPlanningHref({ ...queryForLinks, agendaDate: nextAgendaDate, createOpen: false, dayDetails: "" });
  const todayHref = buildPlanningHref({ ...queryForLinks, agendaDate: todayAgendaKey, createOpen: false, dayDetails: "" });
  const quickJumpLabel = agendaView === "month" ? t("admin.planning.quick_jump.month") : t("admin.planning.quick_jump.direct");
  const quickJumpHelp =
    agendaView === "month"
      ? t("admin.planning.quick_jump_help.month")
      : t("admin.planning.quick_jump_help.direct");

  const agendaRange = buildAgendaRange(agendaView, agendaDate, language);
  const fromMs = agendaRange.from.getTime();
  const toMs = agendaRange.to.getTime();

  const courseTypeById = new Map(courseTypes.map((row) => [row.id, row]));
  const locationById = new Map(locations.map((row) => [row.id, row]));
  const professorById = new Map(professors.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));
  const selectedLocationSet = new Set(selectedLocationIds);
  const selectedActivitySet = new Set(selectedActivityIds);
  const quickSelectedActivityIds = selectedActivityIds.length > 0 ? selectedActivityIds : selectedCourseType ? [selectedCourseType] : [];
  const selectedProfessorSet = new Set(selectedProfessorIds);
  const selectedActivityLabels = selectedActivityIds
    .map((activityId) => courseTypeById.get(activityId)?.name ?? "")
    .filter((name) => name.length > 0);
  const selectedLocationLabels = selectedLocationIds
    .map((locationId) => locationById.get(locationId)?.name ?? "")
    .filter((name) => name.length > 0);
  const selectedProfessorLabels = selectedProfessorIds
    .map((professorId) => {
      const professor = professorById.get(professorId);
      return professor ? `${professor.first_name} ${professor.last_name}`.trim() : "";
    })
    .filter((name) => name.length > 0);
  const selectedClientLabels = selectedClientIds
    .map((clientId) => clientById.get(clientId))
    .filter((client): client is AdminClientOut => Boolean(client))
    .map((client) => clientDisplayName(client));
  const hasAdvancedFilters =
    selectedActivityIds.length > 0 ||
    (!hasQuickLocationParam && selectedLocationIdsFromQuery.length > 0) ||
    selectedProfessorIds.length > 0 ||
    selectedClientIds.length > 0 ||
    selectedStatus !== "ALL" ||
    selectedClientStatus !== "ALL" ||
    timezone !== "Europe/Paris";
  const planningLocationLabel =
    selectedLocationLabels.length > 1
      ? t("admin.planning.multi_locations", { count: selectedLocationLabels.length })
      : selectedLocationLabels[0]
        ? selectedLocationLabels[0]
        : focusedLocation?.name
          ? focusedLocation.name
          : t("admin.planning.all_locations");
  const planningViewLabel =
    agendaView === "month"
      ? t("admin.planning.view_month")
      : agendaView === "week"
        ? t("admin.planning.view_week")
        : t("admin.planning.view_day");
  const planningSubtitle = `${planningViewLabel} · ${planningLocationLabel} · ${timezone}`;

  const filteredSessions = sessions
    .filter((session) => {
      if (selectedLocationSet.size > 0 && !selectedLocationSet.has(session.location_id)) {
        return false;
      }
      if (selectedActivitySet.size > 0 && !selectedActivitySet.has(session.course_type_id)) {
        return false;
      }
      if (selectedActivitySet.size === 0 && selectedCourseType && session.course_type_id !== selectedCourseType) {
        return false;
      }
      if (selectedProfessorSet.size > 0 && (!session.teacher_id || !selectedProfessorSet.has(session.teacher_id))) {
        return false;
      }
      if (selectedStatus !== "ALL" && session.status !== selectedStatus) {
        return false;
      }
      const startMs = Date.parse(session.start_at_utc);
      if (!Number.isFinite(startMs)) {
        return false;
      }
      return startMs >= fromMs && startMs <= toMs;
    })
    .sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc, localeForUiLanguage(language)));

  const sessionsByDay = new Map<string, AdminSessionOut[]>();
  for (const session of filteredSessions) {
    const key = dateKeyInTimezone(session.start_at_utc, timezone);
    const existing = sessionsByDay.get(key) ?? [];
    existing.push(session);
    sessionsByDay.set(key, existing);
  }

  const agendaDays = agendaRange.dayKeys.map((dayKey) => ({
    key: dayKey,
    label: agendaDayLabel(dayKey, agendaView, language),
    sessions: sessionsByDay.get(dayKey) ?? [],
  }));
  const showLocationCue = agendaView === "month" && shouldShowLocationCue(filteredSessions);
  const visibleLocationToneById = new Map(
    Array.from(
      new Map(
        filteredSessions.map((session) => [
          session.location_id,
          locationById.get(session.location_id)?.name ?? session.location_label ?? session.location_id,
        ]),
      ).entries(),
    )
      .sort((a, b) => a[1].localeCompare(b[1], localeForUiLanguage(language)))
      .map(([locationId], index) => [locationId, `location-tone-${(index % 6) + 1}`]),
  );
  const agendaDayCards = agendaDays.map((day) => ({
    key: day.key,
    label: day.label,
    events: day.sessions.map((session) => ({
      ...session,
      show_location_badge: showLocationCue,
      location_tone: visibleLocationToneById.get(session.location_id) ?? "location-tone-1",
    })),
  }));
  const selectedDayDetails = dayDetails ? agendaDayCards.find((day) => day.key === dayDetails) ?? null : null;
  const visibleEventsByView = agendaView === "month" ? 5 : agendaView === "week" ? 8 : 24;

  let selectedSession = filteredSessions.find((session) => session.id === selectedSessionId) ?? null;
  if (!selectedSession && selectedSessionId) {
    const selectedSessionResult = await backendRequest<AdminSessionOut>(`/api/v1/admin/sessions/${selectedSessionId}`, {}, token);
    if (selectedSessionResult.ok) {
      selectedSession = selectedSessionResult.data;
    } else {
      errors.push(`session: ${selectedSessionResult.message}`);
    }
  }

  let selectedSessionBookings: AdminSessionBookingOut[] = [];
  if (selectedSession) {
    const sessionBookingsResult = await backendRequest<AdminSessionBookingOut[]>(
      `/api/v1/admin/sessions/${selectedSession.id}/bookings`,
      {},
      token,
    );
    if (sessionBookingsResult.ok) {
      selectedSessionBookings = sessionBookingsResult.data;
    } else {
      errors.push(`session-bookings: ${sessionBookingsResult.message}`);
    }
  }

  const clientsSorted = [...clients]
    .filter((client) => client.is_active)
    .sort((a, b) => clientDisplayName(a).localeCompare(clientDisplayName(b), localeForUiLanguage(language)));
  const locationFilterOptions = locations.map((location) => ({ id: location.id, label: location.name }));
  const professorFilterOptions = professors.map((professor) => ({
    id: professor.id,
    label: `${professor.first_name} ${professor.last_name}`.trim(),
  }));
  const clientFilterOptions = clientsSorted.map((client) => ({
    id: client.id,
    label: clientDisplayName(client),
  }));
  const bookingClientOptions = clientsSorted.map((client) => ({
    id: client.id,
    label: clientDisplayName(client),
  }));
  const sessionRecipientStudents = Array.from(
    new Map(
      selectedSessionBookings
        .filter((booking) => Boolean(booking.client_id))
        .map((booking) => [
          booking.client_id,
          {
            id: booking.client_id,
            label: `${booking.client_display_name || booking.client_email} <${booking.client_email}>`,
          },
        ]),
    ).values(),
  );
  const sessionRecipientStudentIds = sessionRecipientStudents.map((item) => item.id);
  const sessionRecipientStudentNames = sessionRecipientStudents.map((item) => item.label.split(" <")[0] || item.label);
  const sessionRecipientSummary = compactList(sessionRecipientStudentNames, 2);

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const modalHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const attendanceModalHref = selectedSession ? withQueryParam(modalHref, "attendance", "1") : modalHref;
  const attendanceModalBaseHref = removeQueryParam(removeQueryParam(attendanceModalHref, "booking_focus"), "attendance_filter");
  const attendanceFilteredHref = (filter: AttendanceFilter): string => withQueryParam(attendanceModalBaseHref, "attendance_filter", filter);
  const groupNotesModalHref = selectedSession ? withQueryParam(modalHref, "notes", "group") : modalHref;
  const groupNotesModalBaseHref = removeQueryParam(
    removeQueryParam(removeQueryParam(groupNotesModalHref, "group_note_template_id"), "note_tab"),
    "group_note_mode",
  );
  const groupNoteTabHref = (tab: ComposerTab): string => withQueryParam(groupNotesModalBaseHref, "note_tab", tab);
  const groupNoteAdvancedHref = withQueryParam(groupNoteTabHref("content"), "group_note_mode", "advanced");
  const groupNoteSimpleHref = removeQueryParam(groupNoteTabHref("content"), "group_note_mode");
  const selectedGroupNoteTemplate =
    groupNoteTemplateId && groupNoteTemplates.length > 0
      ? groupNoteTemplates.find((template) => template.id === groupNoteTemplateId) ?? null
      : null;
  const duplicateModalHref = selectedSession ? withQueryParam(modalHref, "duplicate", "1") : modalHref;
  const sessionEmailModalHref = selectedSession ? withQueryParam(modalHref, "message", "email") : modalHref;
  const sessionEmailModalBaseHref = removeQueryParam(removeQueryParam(sessionEmailModalHref, "email_tab"), "email_mode");
  const sessionEmailTabHref = (tab: ComposerTab): string =>
    withQueryParam(withQueryParam(sessionEmailModalBaseHref, "email_tab", tab), "email_audience", emailAudience);
  const sessionEmailAdvancedHref = withQueryParam(sessionEmailTabHref("content"), "email_mode", "advanced");
  const sessionEmailSimpleHref = removeQueryParam(sessionEmailTabHref("content"), "email_mode");
  const sessionSmsModalHref = selectedSession ? withQueryParam(modalHref, "message", "sms") : modalHref;
  const editSessionHref = selectedSession ? withQueryParam(modalHref, "edit", "1") : modalHref;
  const editTabHref = (tab: SlotEditTab): string => withQueryParam(editSessionHref, "edit_tab", tab);
  const notesAdvancedHref = withQueryParam(editTabHref("notes"), "notes_mode", "advanced");
  const notesSimpleHref = removeQueryParam(editTabHref("notes"), "notes_mode");
  const editTabHrefs: Record<SlotEditTab, string> = {
    general: editTabHref("general"),
    schedule: editTabHref("schedule"),
    visibility: editTabHref("visibility"),
    notes: editTabHref("notes"),
  };
  const activeEditTabHref = (() => {
    const base = editTabHref(editTab);
    if (editTab === "notes" && notesAdvancedMode) {
      return withQueryParam(base, "notes_mode", "advanced");
    }
    return removeQueryParam(base, "notes_mode");
  })();
  const attendanceBookingHref = (bookingId: string): string =>
    withQueryParam(attendanceFilteredHref(attendanceFilter), "booking_focus", bookingId);
  const confirmCloseHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const cancelConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "cancel") : baseHref;
  const deleteConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "delete") : baseHref;
  const attendanceBookings = attendanceFilter === "missing"
    ? selectedSessionBookings.filter((booking) => bookingPresenceLabel(booking.status, language) === null)
    : selectedSessionBookings;
  const focusedAttendanceBooking =
    attendanceBookings.find((booking) => booking.id === bookingFocusId) ?? attendanceBookings[0] ?? null;
  const selectedSessionHasBookings = selectedSessionBookings.length > 0;
  const isGroupNoteStudentAudience =
    groupNoteDestination === "STUDENTS" ||
    groupNoteDestination === "PARENTS" ||
    groupNoteDestination === "STUDENTS_AND_PARENTS";
  const groupNotePrefill = selectedGroupNoteTemplate?.body ?? selectedSession?.group_note ?? "";
  const groupNotesModalClearTemplateHref = groupNotesModalBaseHref;
  const focusedAttendanceIndex = focusedAttendanceBooking
    ? attendanceBookings.findIndex((booking) => booking.id === focusedAttendanceBooking.id)
    : -1;
  const previousAttendanceBooking =
    focusedAttendanceIndex > 0 ? attendanceBookings[focusedAttendanceIndex - 1] : null;
  const nextAttendanceBooking =
    focusedAttendanceIndex >= 0 && focusedAttendanceIndex < attendanceBookings.length - 1
      ? attendanceBookings[focusedAttendanceIndex + 1]
      : null;
  const attendanceMissingCount = selectedSessionBookings.filter((booking) => bookingPresenceLabel(booking.status, language) === null).length;
  const attendanceCompletedCount = selectedSessionBookings.length - attendanceMissingCount;
  const selectedCourseTypeName = selectedSession ? courseTypeById.get(selectedSession.course_type_id)?.name ?? t("admin.planning.course_type_undefined") : "";
  const selectedLocationName = selectedSession ? locationById.get(selectedSession.location_id)?.name ?? t("admin.planning.location_undefined") : "";
  const selectedHabitualProfessorDetail =
    selectedSession && selectedSession.habitual_teacher_id ? professorById.get(selectedSession.habitual_teacher_id) : null;
  const selectedSubstituteProfessorDetail =
    selectedSession && selectedSession.substitute_teacher_id ? professorById.get(selectedSession.substitute_teacher_id) : null;
  const selectedEffectiveProfessorDetail =
    selectedSession && selectedSession.effective_teacher_id ? professorById.get(selectedSession.effective_teacher_id) : null;
  const selectedSessionIsOnline = selectedSession
    ? (locationById.get(selectedSession.location_id)?.is_online ?? false) || selectedSession.type_label.toLowerCase().includes("online")
    : false;
  const selectedSessionRequiresProfessor = selectedSession ? selectedSession.requires_professor !== false : true;
  const selectedSessionAllowsStudentBookings = selectedSession ? selectedSession.allows_student_bookings !== false : true;
  const selectedHabitualProfessorName = selectedSession
    ? (selectedSession.habitual_teacher_display_name || "").trim() ||
      (selectedHabitualProfessorDetail ? `${selectedHabitualProfessorDetail.first_name} ${selectedHabitualProfessorDetail.last_name}`.trim() : "") ||
      t("admin.planning.teacher_undefined")
    : "";
  const selectedSubstituteProfessorName = selectedSession
    ? (selectedSession.substitute_teacher_display_name || "").trim() ||
      (selectedSubstituteProfessorDetail ? `${selectedSubstituteProfessorDetail.first_name} ${selectedSubstituteProfessorDetail.last_name}`.trim() : "")
    : "";
  const selectedEffectiveProfessorName = selectedSession
    ? (selectedSession.effective_teacher_display_name || "").trim() ||
      (selectedEffectiveProfessorDetail ? `${selectedEffectiveProfessorDetail.first_name} ${selectedEffectiveProfessorDetail.last_name}`.trim() : "") ||
      selectedHabitualProfessorName
    : "";
  const selectedHabitualProfessorLabel = !selectedSession
    ? ""
    : !selectedSessionRequiresProfessor
      ? selectedHabitualProfessorName === t("admin.planning.teacher_undefined")
        ? t("admin.planning.no_teacher_required")
        : t("admin.planning.optional_teacher_label", { name: selectedHabitualProfessorName })
      : selectedHabitualProfessorName;
  const selectedSubstituteProfessorLabel = !selectedSession
    ? ""
    : !selectedSessionRequiresProfessor
      ? selectedSubstituteProfessorName
        ? t("admin.planning.optional_teacher_label", { name: selectedSubstituteProfessorName })
        : t("admin.planning.none")
      : selectedSubstituteProfessorName || t("admin.planning.none");
  const selectedSessionIsSubstituted = Boolean(selectedSession?.substitute_teacher_id);
  const selectedEffectiveProfessorLabel = !selectedSession
    ? ""
    : !selectedSessionRequiresProfessor
      ? selectedEffectiveProfessorName && selectedEffectiveProfessorName !== t("admin.planning.teacher_undefined")
        ? selectedSessionIsSubstituted
          ? t("admin.planning.optional_substitute_teacher_label", { name: selectedEffectiveProfessorName })
          : t("admin.planning.optional_teacher_label", { name: selectedEffectiveProfessorName })
        : t("admin.planning.no_teacher_required")
      : selectedSessionIsSubstituted
        ? t("admin.planning.substitute_teacher_label", { name: selectedEffectiveProfessorName })
        : selectedEffectiveProfessorName;
  const selectedEffectiveProfessorZoomLink = (selectedEffectiveProfessorDetail?.zoom_link ?? "").trim();
  const selectedSessionZoomLink =
    selectedSession && ((selectedSession.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      ? ((selectedSession?.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      : null;
  const selectedSessionTypeName = selectedSession ? sessionTypeLabel(selectedSession, selectedLocationName, language) : "";
  const selectedSessionHeaderTitle = selectedSession ? `${selectedCourseTypeName} - ${selectedLocationName}` : "";
  const selectedSessionSubtitle = selectedSession
    ? `${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · ${sessionTimeRangeLabel(selectedSession, language)} · ${selectedSession.timezone} · ${t("admin.planning.teacher_short")}: ${selectedEffectiveProfessorLabel || t("admin.planning.no_teacher_required")}`
    : "";
  const timezoneOptionValues = new Set(PLANNING_TIMEZONES.map((option) => option.value));
  const timezoneOptions = timezoneOptionValues.has(timezone)
    ? PLANNING_TIMEZONES
    : [{ value: timezone, label: `${timezone} (personnalise)` }, ...PLANNING_TIMEZONES];
  const sessionTimezoneValues = new Set<string>([
    ...PLANNING_TIMEZONES.map((option) => option.value),
    ...locations.map((row) => row.timezone),
    selectedSession?.timezone ?? timezone,
  ]);
  const sessionTimezoneOptions = Array.from(sessionTimezoneValues)
    .filter((value) => value && value.trim().length > 0)
    .sort((a, b) => a.localeCompare(b, localeForUiLanguage(language)))
    .map((value) => {
      const known = PLANNING_TIMEZONES.find((option) => option.value === value);
      return { value, label: known?.label ?? value };
    });
  const createDraftCourseTypeId = createDraft?.course_type_id || selectedCourseType;
  const createAllowsStudentBookings = createDraftCourseTypeId
    ? courseTypeById.get(createDraftCourseTypeId)?.allows_student_bookings !== false
    : true;
  const createInitialVisibilityScopes: SessionAudienceScope[] = createDraft?.visibility_scopes ?? ["PRIVATE"];
  const createInitialBookingScopes: SessionAudienceScope[] =
    createDraft?.booking_scopes ??
    (createAllowsStudentBookings && !(createInitialVisibilityScopes.length === 1 && createInitialVisibilityScopes[0] === "PRIVATE")
      ? ["EXTERNAL"]
      : ["PRIVATE"]);
  const createShowExternalRemainingSeats = createDraft?.show_external_remaining_seats !== "0";
  const selectedVisibilityScopes: SessionAudienceScope[] = selectedSession
    ? normalizeSessionAudienceScopes(
        selectedSession.visibility_scopes ?? selectedSession.visibility_scope,
        [selectedSession.is_private ? "PRIVATE" : "EXTERNAL"],
      )
    : ["PRIVATE"];
  const selectedBookingScopes: SessionAudienceScope[] = selectedSession
    ? normalizeSessionAudienceScopes(
        selectedSession.booking_scopes ?? selectedSession.booking_scope,
        [selectedSession.allow_online_booking ? "EXTERNAL" : "PRIVATE"],
      )
    : ["PRIVATE"];
  const selectedShowExternalRemainingSeats = selectedSession?.show_external_remaining_seats !== false;
  const createDraftDuration = createDraft ? draftPositiveInteger(createDraft.duration_minutes) : null;
  const createDraftCapacity = createDraft ? draftNonNegativeInteger(createDraft.capacity_max) : null;
  const createRecurrenceMode = createDraft?.recurrence_mode?.trim().toUpperCase() === "RECURRING" ? "RECURRING" : "NONE";
  const createRecurrenceFrequencyRaw = createDraft?.recurrence_frequency?.trim().toUpperCase() ?? "WEEKLY";
  const createRecurrenceFrequency =
    createRecurrenceFrequencyRaw === "DAILY" || createRecurrenceFrequencyRaw === "MONTHLY"
      ? createRecurrenceFrequencyRaw
      : "WEEKLY";
  const createRecurrenceInterval = createDraft ? draftPositiveInteger(createDraft.recurrence_interval) ?? 1 : 1;
  const createRecurrenceTimeBasis = createDraft?.recurrence_time_basis?.trim().toUpperCase() === "UTC" ? "UTC" : "LOCAL";
  const editRecurrenceDefaults = parseRecurrenceRuleDefaults(selectedSession?.recurrence_rule);
  const editDefaultRecurrenceMode = selectedSession?.recurrence_group_id ? "RECURRING" : "NONE";
  const editRecurrenceUntilDate = selectedSession
    ? selectedSession.recurrence_end_date ??
      toDateInputInTimezone(addUtcDays(new Date(selectedSession.start_at_utc), 84).toISOString(), selectedSession.timezone)
    : agendaDate;

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">{t("admin.planning.backend_error", { message: errors.join(" | ") })}</section> : null}

      <section className="card planning-header-card">
        <div className="row spread planning-header-row">
          <div className="stack-xs">
            <h2>{t("admin.planning.page_title")}</h2>
            <p className="muted planning-subtitle">{planningSubtitle}</p>
          </div>
          <div className="row planning-header-actions">
            <a className={`mode-link ${!createOpen ? "mode-active" : ""}`} href={lectureHref}>
              {t("admin.planning.mode_read")}
            </a>
            <a className={`mode-link ${createOpen ? "mode-active" : ""}`} href={createHref}>
              {t("admin.planning.mode_edit")}
            </a>
            <a className="icon-add-button" href={createHref}>
              <span className="icon-add-button-plus" aria-hidden="true">
                +
              </span>
              {t("admin.planning.add_slot")}
            </a>
            {focusedLocationId ? (
              <Link className="mode-link" href={`/admin/plannings/${focusedLocationId}/settings`}>
                {t("admin.planning.settings")}
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card planning-filters-card">
        <form method="get" className="planning-quick-form">
          <input type="hidden" name="course_type_id" value="" />
          <input type="hidden" name="status" value={selectedStatus} />
          <input type="hidden" name="client_status" value={selectedClientStatus} />
          <input type="hidden" name="agenda_date" value={agendaDate} />
          <input type="hidden" name="timezone" value={timezone} />
          {quickSelectedActivityIds.map((activityId) => (
            <input key={`quick-activity-${activityId}`} type="hidden" name="activity_ids" value={activityId} />
          ))}
          {selectedLocationIdsFromQuery.map((locationId) => (
            <input key={`quick-location-${locationId}`} type="hidden" name="location_ids" value={locationId} />
          ))}
          {selectedProfessorIds.map((professorId) => (
            <input key={`quick-professor-${professorId}`} type="hidden" name="professor_ids" value={professorId} />
          ))}
          {selectedClientIds.map((clientId) => (
            <input key={`quick-client-${clientId}`} type="hidden" name="client_ids" value={clientId} />
          ))}
          {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

          <label>
            {t("admin.planning.filter.location")}
            <AutoSubmitSelect
              name="location_id"
              defaultValue={focusedLocationId}
              options={[{ value: "", label: t("admin.planning.filter.all_locations") }, ...locations.map((row) => ({ value: row.id, label: row.name }))]}
            />
          </label>

          <label>
            {t("admin.planning.filter.activity")}
            <AutoSubmitSelect
              name="activity_ids"
              defaultValue=""
              options={[{ value: "", label: t("admin.planning.filter.add_activity") }, ...courseTypes.map((row) => ({ value: row.id, label: row.name }))]}
            />
          </label>

          <label>
            {t("admin.planning.filter.agenda_view")}
            <AutoSubmitSelect
              name="agenda_view"
              defaultValue={agendaView}
              options={[
                { value: "month", label: t("admin.planning.view_month") },
                { value: "week", label: t("admin.planning.view_week") },
                { value: "day", label: t("admin.planning.view_day") },
              ]}
            />
          </label>

          <div className="row">
            <a className="planning-reset-link" href={filtersResetHref}>
              {t("common.reset")}
            </a>
            <a className="mode-link planning-advanced-link" href={filtersHref}>
              {t("admin.planning.advanced_filters")}
            </a>
          </div>
        </form>
        <div className="row planning-active-filters">
          {selectedActivityLabels.length > 0 ? (
            <span className="badge">{t("admin.planning.active.activities", { value: compactList(selectedActivityLabels) })}</span>
          ) : null}
          {selectedCourseType && selectedActivityIds.length === 0 ? (
            <span className="badge">{t("admin.planning.active.course_type", { value: courseTypeById.get(selectedCourseType)?.name ?? t("admin.planning.selection") })}</span>
          ) : null}
          {selectedLocationLabels.length > 0 ? (
            <span className="badge">{t("admin.planning.active.locations", { value: compactList(selectedLocationLabels) })}</span>
          ) : null}
          {timezone !== "Europe/Paris" ? <span className="badge">{t("admin.planning.active.timezone", { value: timezone })}</span> : null}
          {selectedProfessorLabels.length > 0 ? (
            <span className="badge">{t("admin.planning.active.teachers", { value: compactList(selectedProfessorLabels) })}</span>
          ) : null}
          {selectedClientLabels.length > 0 ? (
            <span className="badge">{t("admin.planning.active.students", { value: compactList(selectedClientLabels) })}</span>
          ) : null}
          {selectedStatus !== "ALL" ? <span className="badge">{t("admin.planning.active.lesson_status", { value: selectedStatus })}</span> : null}
          {selectedClientStatus !== "ALL" ? <span className="badge">{t("admin.planning.active.member_status", { value: selectedClientStatus })}</span> : null}
          {!hasAdvancedFilters ? (
            <span className="muted">{t("admin.planning.active.none")}</span>
          ) : null}
        </div>
      </section>

      {filtersOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact planning-filters-modal">
            <a className="modal-close-x" href={filtersCloseHref} aria-label={t("common.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.planning.filters_title")}</h2>
            <p className="muted">{t("admin.planning.filters_help")}</p>
            <form method="get" className="grid cols-2">
              <input type="hidden" name="agenda_view" value={agendaView} />
              <input type="hidden" name="agenda_date" value={agendaDate} />
              {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

              <label className="span-2">
                {t("admin.planning.filter.course_type")}
                <select name="course_type_id" defaultValue={selectedCourseType}>
                  <option value="">{t("common.all")}</option>
                  {courseTypes.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>

              <SearchMultiSelect
                className="span-2"
                label={t("admin.planning.filter.by_activities")}
                name="activity_ids"
                options={courseTypes.map((row) => ({ id: row.id, label: row.name }))}
                selectedIds={selectedActivityIds}
                placeholder={t("admin.planning.filter.search_activity")}
                emptySelectionLabel={t("admin.planning.filter.no_activity")}
              />

              <SearchMultiSelect
                label={t("admin.planning.filter.by_rooms")}
                name="location_ids"
                options={locationFilterOptions}
                selectedIds={selectedLocationIds}
                placeholder={t("admin.planning.filter.search_room")}
                emptySelectionLabel={t("admin.planning.filter.no_room")}
              />

              <SearchMultiSelect
                label={t("admin.planning.filter.by_teachers")}
                name="professor_ids"
                options={professorFilterOptions}
                selectedIds={selectedProfessorIds}
                placeholder={t("admin.planning.filter.search_teacher")}
                emptySelectionLabel={t("admin.planning.filter.no_teacher")}
              />

              <SearchMultiSelect
                className="span-2"
                label={t("admin.planning.filter.by_students")}
                name="client_ids"
                options={clientFilterOptions}
                selectedIds={selectedClientIds}
                placeholder={t("admin.planning.filter.search_student")}
                emptySelectionLabel={t("admin.planning.filter.no_student")}
              />

              <label>
                {t("admin.planning.filter.session_timezone")}
                <select name="timezone" defaultValue={timezone}>
                  {timezoneOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("admin.planning.filter.lesson_status")}
                <select name="status" defaultValue={selectedStatus}>
                  <option value="ALL">{t("common.all")}</option>
                  <option value="SCHEDULED">SCHEDULED</option>
                  <option value="CANCELLED">CANCELLED</option>
                  <option value="COMPLETED">COMPLETED</option>
                </select>
              </label>

              <label>
                {t("admin.planning.filter.member_status")}
                <select name="client_status" defaultValue={selectedClientStatus}>
                  <option value="ALL">{t("common.all")}</option>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="RESPONSABLE">RESPONSABLE</option>
                  <option value="TRIAL">TRIAL</option>
                  <option value="PENDING">PENDING</option>
                  <option value="INACTIVE">INACTIVE</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </label>

              <div className="row span-2">
                <button type="submit">{t("common.apply")}</button>
                <a className="reset-link" href={filtersResetHref}>
                  {t("common.reset")}
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {createOpen && !filtersOpen && !selectedDayDetails && !selectedSession ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-create-session">
            <a className="modal-close-x" href={createCloseHref} aria-label={t("common.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.planning.create_title")}</h2>
            <p className="muted">{t("admin.planning.create_help")}</p>
            {(okMessage || errorMessage) ? (
              <section className="modal-overlay modal-overlay-front">
                <article className="modal-panel modal-compact">
                  <a className="modal-close-x" href={errorMessage ? createFeedbackDismissHref : createCloseHref} aria-label={t("common.close")}>
                    ×
                  </a>
                  <h3 className="modal-title">{errorMessage ? t("admin.planning.create_impossible") : t("admin.planning.create_done")}</h3>
                  {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
                  {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
                  <div className="row modal-actions-end">
                    {errorMessage ? (
                      <a className="ghost" href={createFeedbackDismissHref}>
                        {t("admin.planning.fix_entry")}
                      </a>
                    ) : null}
                    <a className="mode-link" href={createCloseHref}>
                      {t("common.close")}
                    </a>
                  </div>
                </article>
              </section>
            ) : null}
            <form action={createAdminSessionAction} className="create-session-form">
              <input type="hidden" name="return_to" value={createHref} />
              <section className="create-session-section">
                <div className="row spread">
                  <h3 className="create-session-section-title">{t("admin.planning.main_information")}</h3>
                  <span className="badge">{t("admin.planning.required_badge")}</span>
                </div>
                <SessionCreateMainFields
                  language={language}
                  courseTypes={courseTypes.map((row) => ({
                    id: row.id,
                    name: row.name,
                    durationMinutes: row.duration_minutes,
                    defaultCapacity: row.default_capacity,
                    requiresProfessor: row.requires_professor,
                    allowsStudentBookings: row.allows_student_bookings,
                  }))}
                  professors={professors.map((row) => ({
                    id: row.id,
                    firstName: row.first_name,
                    lastName: row.last_name,
                  }))}
                  locations={locations.map((row) => ({
                    id: row.id,
                    name: row.name,
                  }))}
                  sessionTimezoneOptions={sessionTimezoneOptions}
                  defaultCourseTypeId={selectedCourseType}
                  defaultLocationId={focusedLocationId || (locations[0]?.id ?? "")}
                  defaultSessionTimezone={timezone}
                  defaultStartDate={agendaDate}
                  draft={
                    createDraft
                      ? {
                        title: createDraft.title,
                        courseTypeId: createDraft.course_type_id,
                        professorId: createDraft.professor_id,
                        locationId: createDraft.location_id,
                        sessionTimezone: createDraft.session_timezone,
                        startDate: createDraft.start_date,
                        isAllDay: createDraft.is_all_day === "1",
                        startTime: createDraft.start_time,
                        endTime: createDraft.end_time,
                        durationMinutes: createDraftDuration,
                        capacityMax: createDraftCapacity,
                        zoomLink: createDraft.zoom_link,
                      }
                      : undefined
                  }
                />
              </section>

              <fieldset className="create-session-section recurrence-panel">
                <legend>{t("admin.planning.recurrence")}</legend>
                <div className="recurrence-mode-row">
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="NONE" defaultChecked={createRecurrenceMode === "NONE"} />
                    {t("admin.planning.recurrence.single")}
                  </label>
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="RECURRING" defaultChecked={createRecurrenceMode === "RECURRING"} />
                    {t("admin.planning.recurrence.recurring")}
                  </label>
                </div>

                <div className="recurrence-settings">
                  <div className="grid cols-3 recurrence-grid">
                    <label>
                      {t("admin.planning.recurrence.frequency")}
                      <select name="recurrence_frequency" defaultValue={createRecurrenceFrequency}>
                        <option value="DAILY">{t("admin.planning.recurrence.daily")}</option>
                        <option value="WEEKLY">{t("admin.planning.recurrence.weekly")}</option>
                        <option value="MONTHLY">{t("admin.planning.recurrence.monthly")}</option>
                      </select>
                    </label>

                    <label>
                      {t("admin.planning.recurrence.every")}
                      <input type="number" name="recurrence_interval" min={1} defaultValue={createRecurrenceInterval} />
                      <small className="muted">{t("admin.planning.recurrence.every_help")}</small>
                    </label>

                    <label>
                      {t("admin.planning.recurrence.until")}
                      <input type="date" name="recurrence_until_date" defaultValue={createDraft?.recurrence_until_date || ""} />
                    </label>
                  </div>
                  <label className="checkline">
                    <input
                      type="checkbox"
                      name="recurrence_keep_local_time"
                      value="1"
                      defaultChecked={createRecurrenceTimeBasis === "LOCAL"}
                    />
                    {t("admin.planning.recurrence.keep_local_time")}
                  </label>
                  <p className="muted">
                    {t("admin.planning.recurrence.keep_local_time_help")}
                  </p>
                  <p className="muted">{t("admin.planning.recurrence.until_included")}</p>
                </div>
              </fieldset>

              <section className="create-session-section">
                <h3 className="create-session-section-title">{t("admin.planning.visibility_descriptions")}</h3>
                <div className="grid cols-2 create-session-visibility-grid">
                  <SessionVisibilityFields
                    language={language}
                    initialVisibilityScopes={createInitialVisibilityScopes}
                    initialBookingScopes={createInitialBookingScopes}
                    allowsStudentBookings={createAllowsStudentBookings}
                    initialShowExternalRemainingSeats={createShowExternalRemainingSeats}
                  />

                  <label>
                    {t("admin.planning.external_price")}
                    <input
                      type="text"
                      name="external_booking_price_ttc"
                      inputMode="decimal"
                      defaultValue={createDraft?.external_booking_price_ttc || ""}
                      placeholder={t("admin.planning.external_price_placeholder")}
                    />
                    <small className="muted">{t("admin.planning.external_price_help")}</small>
                  </label>

                  <label>
                    {t("admin.planning.public_description")}
                    <textarea name="public_description" rows={4} defaultValue={createDraft?.public_description || ""} />
                  </label>

                  <label>
                    {t("admin.planning.private_description")}
                    <textarea name="private_description" rows={4} defaultValue={createDraft?.private_description || ""} />
                  </label>

                  <label className="span-2">
                    {t("admin.planning.professor_note")}
                    <RichMessageEditor
                      name="professor_reminder_note"
                      formatName="professor_reminder_note_format"
                      rows={6}
                      maxLength={12000}
                      defaultFormat="HTML"
                      defaultValue={createDraft?.professor_reminder_note || ""}
                      placeholder={t("admin.planning.professor_note_placeholder")}
                    />
                  </label>
                </div>
              </section>

              <div className="row spread create-session-actions">
                <p className="muted">{t("admin.planning.required_fields_help")}</p>
                <div className="row">
                  <a className="reset-link" href={createCloseHref}>
                    {t("common.cancel")}
                  </a>
                  <button type="submit">{t("admin.planning.add_slot")}</button>
                </div>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread">
          <h2>{t("admin.planning.agenda_title")}</h2>
          <div className="row planning-agenda-nav">
            <a className="mode-link" href={previousHref}>
              ←
            </a>
            <details className="planning-jump-menu">
              <summary className="badge planning-jump-trigger" aria-label={quickJumpLabel}>
                {agendaRange.title}
              </summary>
              <form method="get" className="planning-jump-form">
                <input type="hidden" name="agenda_view" value={agendaView} />
                <input type="hidden" name="timezone" value={timezone} />
                <input type="hidden" name="location_id" value={focusedLocationId} />
                <input type="hidden" name="course_type_id" value={selectedCourseType} />
                <input type="hidden" name="status" value={selectedStatus} />
                <input type="hidden" name="client_status" value={selectedClientStatus} />
                {selectedActivityIds.map((activityId) => (
                  <input key={`jump-activity-${activityId}`} type="hidden" name="activity_ids" value={activityId} />
                ))}
                {selectedLocationIdsFromQuery.map((locationId) => (
                  <input key={`jump-location-${locationId}`} type="hidden" name="location_ids" value={locationId} />
                ))}
                {selectedProfessorIds.map((professorId) => (
                  <input key={`jump-professor-${professorId}`} type="hidden" name="professor_ids" value={professorId} />
                ))}
                {selectedClientIds.map((clientId) => (
                  <input key={`jump-client-${clientId}`} type="hidden" name="client_ids" value={clientId} />
                ))}

                <label className="planning-jump-field">
                  <span>{quickJumpLabel}</span>
                  <input type="date" name="agenda_date" defaultValue={agendaDate} required />
                </label>
                <p className="muted planning-jump-help">{quickJumpHelp}</p>
                <div className="row planning-jump-actions">
                  <button type="submit">{t("admin.planning.go")}</button>
                </div>
              </form>
            </details>
            <a className="mode-link" href={nextHref}>
              →
            </a>
            <a className="mode-link" href={todayHref}>
              {t("admin.planning.today")}
            </a>
          </div>
        </div>
        <p className="muted">{agendaNavigationHint(agendaView, language)}</p>

        <div className={`agenda-grid agenda-grid-${agendaView}`}>
          {agendaDayCards.map((day) => (
            <MonthDayCard
              language={language}
              key={day.key}
              dayLabel={day.label}
              events={day.events}
              isToday={day.key === todayAgendaKey}
              maxVisibleEvents={visibleEventsByView}
              expanded={agendaView !== "month"}
              dayDetailsHref={buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: day.key })}
              openSessionHref={(sessionId) => withSessionInHref(sessionModalBaseHref, sessionId)}
            />
          ))}
        </div>
      </section>

      <DayEventsDrawer
        isOpen={Boolean(selectedDayDetails && !selectedSession)}
        language={language}
        dayLabel={selectedDayDetails ? agendaDayLongLabel(selectedDayDetails.key, language) : ""}
        events={selectedDayDetails ? selectedDayDetails.events : []}
        closeHref={dayDetailsCloseHref}
        openSessionHref={(sessionId) => withSessionInHref(sessionModalBaseHref, sessionId)}
      />

      {selectedSession && !editSessionOpen ? (
        <ModalA11yFrame className="modal-overlay session-slot-overlay" closeHref={baseHref} label={t("admin.planning.detail_label")}>
          <article className="modal-panel session-slot-modal">
            <header className="session-slot-header">
              <div className="session-slot-header-main">
                <h2 className="modal-title session-slot-title">{selectedSessionHeaderTitle}</h2>
                <p className="muted session-slot-subtitle">{selectedSessionSubtitle}</p>
              </div>
              <div className="session-slot-header-actions">
                <span className={`status-badge ${statusClass(selectedSession.status)}`}>{selectedSession.status_label}</span>
                <details className="session-slot-overflow-menu">
                  <summary aria-label={t("admin.planning.more_options")}>⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <p className="muted">{t("admin.planning.actions")}</p>
                    <a className="mode-link" href={attendanceModalHref}>
                      {t("admin.planning.take_attendance")}
                    </a>
                    <a className="mode-link" href={groupNotesModalHref}>
                      {t("admin.planning.group_note")}
                    </a>
                    <a className="mode-link" href={sessionEmailModalHref}>
                      {t("admin.planning.send_email")}
                    </a>
                    <a className="mode-link" href={sessionSmsModalHref}>
                      {t("admin.planning.send_sms")}
                    </a>
                    <a className="mode-link" href={duplicateModalHref}>
                      {t("common.duplicate")}
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      {t("admin.planning.delete_slot")}
                    </a>
                    <hr />
                    <p className="muted">{t("admin.planning.info")}</p>
                    <span className="badge">{t("admin.planning.teacher_badge", { value: selectedEffectiveProfessorLabel || t("admin.planning.no_teacher_required") })}</span>
                    {selectedSessionIsSubstituted ? <span className="badge">{t("admin.planning.substitute_badge")}</span> : null}
                    <span className="badge">{t("admin.planning.display_badge", { value: sessionAudienceScopesLabel(selectedVisibilityScopes, language) })}</span>
                    <span className="badge">
                      {t("admin.planning.booking_badge", { value: selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : t("admin.planning.closed") })}
                    </span>
                    {!selectedSessionAllowsStudentBookings ? <span className="badge">{t("admin.planning.no_student")}</span> : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={baseHref} aria-label={t("common.close")}>
                  ×
                </a>
              </div>
            </header>

            {okMessage ? <section className="flash-ok modal-flash">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err modal-flash">{errorMessage}</section> : null}

            <div className="session-slot-badges">
              <span className={`occ-badge ${occupancyClass(selectedSession.booked_count, selectedSession.capacity_max)}`}>
                {selectedSession.booked_count}/{selectedSession.capacity_max}
              </span>
              <span className="badge">{selectedSessionTypeName}</span>
              <span className="badge">{isRecurringSession(selectedSession) ? t("admin.planning.recurring_series") : t("admin.planning.one_off_slot")}</span>
              {isRecurringSession(selectedSession) ? <span className="badge">{recurrenceLabel(selectedSession, language)}</span> : null}
              <span className="badge">{t("admin.planning.display_inline", { value: sessionAudienceScopesLabel(selectedVisibilityScopes, language) })}</span>
              <span className="badge">
                {t("admin.planning.booking_inline", { value: selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : t("admin.planning.closed") })}
              </span>
              {!selectedSessionAllowsStudentBookings ? <span className="badge">{t("admin.planning.no_student")}</span> : null}
            </div>

            <div className="session-slot-toolbar">
              <a className="mode-link" href={editSessionHref}>
                {t("common.edit")}
              </a>
              {selectedSession.status !== "CANCELLED" ? (
                <a className="danger-link" href={cancelConfirmHref}>
                  {t("common.cancel")}
                </a>
              ) : null}
              <details className="session-slot-overflow-menu session-slot-toolbar-menu">
                <summary aria-label={t("admin.planning.more_actions")}>⋯</summary>
                <div className="session-slot-overflow-panel">
                  <a className="mode-link" href={attendanceModalHref}>
                    {t("admin.planning.take_attendance")}
                  </a>
                  <a className="mode-link" href={groupNotesModalHref}>
                    {t("admin.planning.group_note")}
                  </a>
                  <a className="mode-link" href={sessionEmailModalHref}>
                    {t("admin.planning.send_email")}
                  </a>
                  <a className="mode-link" href={sessionSmsModalHref}>
                    {t("admin.planning.send_sms")}
                  </a>
                  <a className="mode-link" href={duplicateModalHref}>
                    {t("common.duplicate")}
                  </a>
                  <a className="danger-link" href={deleteConfirmHref}>
                    {t("common.delete")}
                  </a>
                </div>
              </details>
            </div>

            <div className="session-slot-body">
              <details className="session-slot-section session-slot-section-attendees" open>
                <summary>{t("admin.planning.attendees_count", { count: selectedSessionBookings.length })}</summary>
                <div className="session-slot-section-body">
                  {selectedSessionBookings.length === 0 ? (
                    <p className="muted">{t("admin.planning.no_attendee")}</p>
                  ) : (
                    <div className="session-bookings-summary-list session-slot-attendees-list">
                      {selectedSessionBookings.map((booking, index) => {
                        const presence = bookingPresenceLabel(booking.status, language);
                        const enrollment = bookingEnrollmentLabel(booking.status, language);
                        return (
                          <article key={booking.id} className="session-slot-attendee-row">
                            <div className="session-slot-attendee-identity">
                              {booking.client_id ? (
                                <Link
                                  className="client-name-link"
                                  href={`/admin/clients/${booking.client_id}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={t("admin.planning.open_client_record_new_tab")}
                                >
                                  {booking.client_display_name || t("admin.planning.participant_number", { count: index + 1 })}
                                </Link>
                              ) : (
                                <strong>{booking.client_display_name || t("admin.planning.participant_number", { count: index + 1 })}</strong>
                              )}
                              <small className="muted">{booking.client_email}</small>
                            </div>
                            <div className="session-slot-attendee-badges">
                              <span className={`status-pill ${statusClass(booking.status)}`}>
                                {enrollment}
                                {booking.waitlist_position ? ` #${booking.waitlist_position}` : ""}
                              </span>
                              <span className={`status-pill ${presence ? "status-ok" : "status-off"}`}>{presence ?? t("admin.planning.presence.missing")}</span>
                            </div>
                            <div className="session-slot-attendee-actions">
                              <a className="mode-link" href={attendanceBookingHref(booking.id)}>
                                {t("admin.planning.presence_and_note")}
                              </a>
                              {isBookingRemovable(selectedSession, booking) ? (
                                <details className="session-slot-inline-confirm">
                                  <summary className="session-slot-delete-icon" aria-label={t("admin.planning.remove_attendee")} title={t("admin.planning.remove_attendee")}>
                                    🗑
                                  </summary>
                                  <form action={adminRemoveClientFromSessionAction} className="session-slot-inline-confirm-panel">
                                    <input type="hidden" name="session_id" value={selectedSession.id} />
                                    <input type="hidden" name="booking_id" value={booking.id} />
                                    <input type="hidden" name="return_to" value={modalHref} />
                                    {selectedSession.recurrence_group_id ? (
                                      <fieldset className="scope-inline compact">
                                        <label className="checkline">
                                          <input type="radio" name="scope" value="OCCURRENCE" defaultChecked />
                                          {t("admin.planning.this_session")}
                                        </label>
                                        <label className="checkline">
                                          <input type="radio" name="scope" value="SERIES_FUTURE" />
                                          {t("admin.planning.future_series")}
                                        </label>
                                      </fieldset>
                                    ) : (
                                      <input type="hidden" name="scope" value="OCCURRENCE" />
                                    )}
                                    <button className="danger" type="submit">
                                      {t("admin.planning.confirm")}
                                    </button>
                                  </form>
                                </details>
                              ) : (
                                <span className="muted">{t("admin.planning.locked")}</span>
                              )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                  {selectedSession.group_note ? (
                    <p className="muted top-gap-sm">
                      <strong>{t("admin.planning.group_note_label")}:</strong> {stripHtml(selectedSession.group_note)}
                    </p>
                  ) : null}
                </div>
              </details>

              <aside className="session-slot-right">
                <details className="session-slot-section session-slot-section-enroll" open>
                  <summary>{selectedSessionAllowsStudentBookings ? t("admin.planning.enroll_student") : t("admin.planning.student_enrollments")}</summary>
                  <div className="session-slot-section-body">
                    {!selectedSessionAllowsStudentBookings ? (
                      <p className="muted">
                        {t("admin.planning.no_enrollment_possible")}
                      </p>
                    ) : (
                      <form action={adminAddClientToSessionAction} className="session-enroll-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="return_to" value={modalHref} />

                        <SearchMultiSelect
                          className="session-enroll-search"
                          label={t("client.child")}
                          name="client_id"
                          options={bookingClientOptions}
                          selectedIds={[]}
                          placeholder={t("admin.planning.enroll_search_student")}
                          emptySelectionLabel={t("admin.planning.enroll_no_student_selected")}
                          maxSelections={1}
                          requiredSelection
                        />

                        <div className="session-enroll-submit">
                          {selectedSession.recurrence_group_id ? (
                            <details className="session-slot-add-confirm">
                              <summary>{t("admin.planning.add_student")}</summary>
                              <div className="session-slot-inline-confirm-panel session-slot-scope-panel">
                                <p className="muted">{t("admin.planning.enroll_scope_help")}</p>
                                <label className="checkline">
                                  <input type="radio" name="scope" value="OCCURRENCE" defaultChecked />
                                  {t("admin.planning.this_session_only")}
                                </label>
                                <label className="checkline">
                                  <input type="radio" name="scope" value="SERIES_FUTURE" />
                                  {t("admin.planning.whole_future_series")}
                                </label>
                                <button type="submit">{t("admin.planning.confirm")}</button>
                              </div>
                            </details>
                          ) : (
                            <>
                              <input type="hidden" name="scope" value="OCCURRENCE" />
                              <button type="submit">{t("admin.planning.add_student")}</button>
                            </>
                          )}
                        </div>
                      </form>
                    )}
                  </div>
                </details>

                <details className="session-slot-section session-slot-section-details" open>
                  <summary>{t("common.details")}</summary>
                  <div className="session-slot-section-body session-slot-details-list">
                    <p className="muted">
                      <strong>{t("admin.planning.activity")}:</strong> {selectedCourseTypeName}
                    </p>
                    <p className="muted">
                      <strong>{t("admin.planning.recurrence_label")}:</strong> {recurrenceSummaryLabel(selectedSession, language)}
                    </p>
                    <p className="muted">
                      <strong>{t("admin.planning.regular_teacher")}:</strong> {selectedHabitualProfessorLabel}
                    </p>
                    <p className="muted">
                      <strong>{t("admin.planning.substitute_teacher")}:</strong> {selectedSubstituteProfessorLabel}
                    </p>
                    <p className="muted">
                      <strong>{t("admin.planning.effective_teacher")}:</strong> {selectedEffectiveProfessorLabel || t("admin.planning.no_teacher_required")}
                    </p>
                    <p className="muted">
                      <strong>{t("common.location")}:</strong> {selectedLocationName}
                    </p>
                    {selectedSessionZoomLink ? (
                      <p>
                        <a href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                          {t("admin.planning.zoom_link")}
                        </a>
                      </p>
                    ) : null}
                    {selectedSession.public_description ? (
                      <p className="muted">
                        <strong>{t("admin.planning.public_description_label")}:</strong> {selectedSession.public_description}
                      </p>
                    ) : null}
                    {selectedSession.private_description ? (
                      <p className="muted">
                        <strong>{t("admin.planning.private_description_label")}:</strong> {selectedSession.private_description}
                      </p>
                    ) : null}
                    {selectedSession.professor_reminder_note ? (
                      <p className="muted">
                        <strong>{t("admin.planning.professor_note_summary")}:</strong> {stripHtml(selectedSession.professor_reminder_note)}
                      </p>
                    ) : null}
                  </div>
                </details>
              </aside>
            </div>
          </article>
        </ModalA11yFrame>
      ) : null}

      {selectedSession && editSessionOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel session-edit-modal-shell">
            <header className="session-edit-shell-header">
              <div>
                <h2 className="modal-title">{t("admin.planning.edit_slot")}</h2>
                <p className="muted">
                  {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {selectedLocationName} · {t("admin.planning.recorded_schedule", { value: sessionTimeRangeLabel(selectedSession, language) })}
                </p>
              </div>
              <div className="session-edit-shell-header-actions">
                <details className="session-slot-overflow-menu">
                  <summary aria-label={t("admin.planning.secondary_actions")}>⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <a className="mode-link" href={duplicateModalHref}>
                      {t("admin.planning.duplicate_slot")}
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      {t("admin.planning.delete_slot")}
                    </a>
                    {selectedSessionZoomLink ? (
                      <a className="mode-link" href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                        {t("admin.planning.copy_zoom_link")}
                      </a>
                    ) : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={modalHref} aria-label={t("common.close")}>
                  ×
                </a>
              </div>
            </header>

            {okMessage ? <section className="flash-ok modal-flash">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err modal-flash">{errorMessage}</section> : null}

            <SessionEditModalBridge initialActiveTab={editTab} tabReturnHrefs={editTabHrefs}>
              <form action={updateAdminSessionAction} className="session-edit-shell-form" noValidate>
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={activeEditTabHref} data-session-edit-return-to />
                <input type="hidden" name="has_recurrence_group" value={selectedSession.recurrence_group_id ? "1" : "0"} />

                <nav className="session-edit-tabs" aria-label={t("admin.planning.sections_label")}>
                  <a
                    className={`session-edit-tab ${editTab === "general" ? "active" : ""}`}
                    href={editTabHref("general")}
                    data-session-edit-tab="general"
                  >
                    <span>{t("admin.planning.section_general")}</span>
                    <small>{selectedEffectiveProfessorLabel || t("admin.planning.no_teacher_required")} · {t("admin.planning.places_count", { count: selectedSession.capacity_max })}</small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "schedule" ? "active" : ""}`}
                    href={editTabHref("schedule")}
                    data-session-edit-tab="schedule"
                  >
                    <span>{t("admin.planning.section_schedule")}</span>
                    <small>{t("admin.planning.recorded_short", { value: sessionTimeRangeLabel(selectedSession, language) })}</small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "visibility" ? "active" : ""}`}
                    href={editTabHref("visibility")}
                    data-session-edit-tab="visibility"
                  >
                    <span>{t("admin.planning.section_visibility")}</span>
                    <small>
                      {sessionAudienceScopesLabel(selectedVisibilityScopes, language)} ·{" "}
                      {selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : t("admin.planning.closed")}
                    </small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "notes" ? "active" : ""}`}
                    href={editTabHref("notes")}
                    data-session-edit-tab="notes"
                  >
                    <span>{t("admin.planning.section_notes")}</span>
                    <small>{selectedSession.professor_reminder_note ? t("admin.planning.filled") : t("admin.planning.empty")}</small>
                  </a>
                </nav>

                <div className="session-edit-shell-body">
                  <section
                    className={`session-edit-panel ${editTab === "general" ? "active" : ""}`}
                    data-session-edit-panel="general"
                    hidden={editTab !== "general"}
                  >
                  <div className="grid cols-2">
                    <label>
                      {t("admin.planning.title_label")}
                      <input type="text" name="title" defaultValue={selectedSession.title} required />
                    </label>

                    <label>
                      {t("admin.planning.course_type")}
                      <select name="course_type_id" defaultValue={selectedSession.course_type_id} required>
                        {courseTypes.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("common.location")}
                      <select name="location_id" defaultValue={selectedSession.location_id} required>
                        {locations.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("admin.planning.coach")}
                      <select name="professor_id" defaultValue={selectedSession.professor_id ?? ""}>
                        <option value="">{t("admin.planning.no_teacher")}</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                      {!selectedSessionRequiresProfessor ? (
                        <small className="muted">{t("admin.planning.optional_teacher_help")}</small>
                      ) : null}
                    </label>

                    <label>
                      {t("admin.planning.substitute_teacher_occurrence")}
                      <select name="substitute_teacher_id" defaultValue={selectedSession.substitute_teacher_id ?? ""}>
                        <option value="">{t("admin.planning.no_substitute")}</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {t("admin.planning.capacity_max")}
                      <input type="number" name="capacity_max" min={0} defaultValue={selectedSession.capacity_max} />
                      {!selectedSessionAllowsStudentBookings ? (
                        <small className="muted">{t("admin.planning.zero_capacity_help")}</small>
                      ) : null}
                    </label>

                    <label>
                      {t("common.status")}
                      <select name="status" defaultValue={selectedSession.status}>
                        <option value="SCHEDULED">{t("admin.planning.status.scheduled")}</option>
                        <option value="COMPLETED">{t("admin.planning.status.completed")}</option>
                        <option value="CANCELLED">{t("admin.planning.status.cancelled")}</option>
                      </select>
                    </label>

                    <label className="session-edit-span">
                      {t("admin.planning.zoom_link")}
                      <input type="url" name="zoom_link" defaultValue={selectedSession.zoom_link ?? ""} />
                    </label>

                    <label className="session-edit-span">
                      {t("admin.planning.substitute_note")}
                      <textarea name="substitute_note" rows={2} defaultValue={selectedSession.substitute_note ?? ""} />
                    </label>
                  </div>
                  </section>

                  <section
                    className={`session-edit-panel ${editTab === "schedule" ? "active" : ""}`}
                    data-session-edit-panel="schedule"
                    hidden={editTab !== "schedule"}
                  >
                  <div className="grid cols-2">
                    <label>
                      {t("admin.planning.start_day")}
                      <input
                        type="date"
                        name="start_date"
                        defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                        required
                      />
                    </label>

                    <label>
                      {t("admin.planning.apply_scope")}
                      <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                        <option value="ONE">{t("admin.planning.scope.one")}</option>
                        {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{t("admin.planning.scope.future")}</option> : null}
                        {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{t("admin.planning.scope.all")}</option> : null}
                      </select>
                    </label>

                    <label className="checkline session-edit-span">
                      <input type="checkbox" name="is_all_day" defaultChecked={selectedSession.is_all_day} />
                      {t("admin.planning.all_day_slot")}
                    </label>

                    <details className="session-edit-collapsible session-edit-span">
                      <summary>{t("admin.planning.advanced_options")}</summary>
                      <label>
                        {t("admin.planning.filter.session_timezone")}
                        <select name="session_timezone" defaultValue={selectedSession.timezone} required>
                          {sessionTimezoneOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </details>

                    <SessionTimeFields
                      startLabel={t("admin.planning.start_time")}
                      endLabel={t("admin.planning.end_time")}
                      durationLabel={t("admin.planning.duration_minutes")}
                      labelClassName="session-time-field"
                      defaultStartTime={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone, language)}
                      defaultEndTime={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone, language)}
                      defaultDurationMinutes={sessionDurationMinutes(selectedSession)}
                      requiredStart
                    />
                    <p className="muted session-edit-span">
                      {t("admin.planning.edit_schedule_help")}
                    </p>
                  </div>

                  <fieldset className="session-edit-span recurrence-panel">
                    <legend>{t("admin.planning.recurrence")}</legend>
                    <div className="recurrence-mode-row">
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="NONE" defaultChecked={editDefaultRecurrenceMode === "NONE"} />
                        {t("admin.planning.recurrence.no_change")}
                      </label>
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="RECURRING" defaultChecked={editDefaultRecurrenceMode === "RECURRING"} />
                        {t("admin.planning.recurrence.edit")}
                      </label>
                    </div>
                    <div className="recurrence-settings">
                      <div className="grid cols-3 recurrence-grid">
                        <label>
                          {t("admin.planning.recurrence.frequency")}
                          <select name="recurrence_frequency" defaultValue={editRecurrenceDefaults.frequency}>
                            <option value="DAILY">{t("admin.planning.recurrence.daily")}</option>
                            <option value="WEEKLY">{t("admin.planning.recurrence.weekly")}</option>
                            <option value="MONTHLY">{t("admin.planning.recurrence.monthly")}</option>
                          </select>
                        </label>
                        <label>
                          {t("admin.planning.recurrence.every")}
                          <input type="number" name="recurrence_interval" min={1} defaultValue={editRecurrenceDefaults.interval} />
                          <small className="muted">{t("admin.planning.recurrence.every_help")}</small>
                        </label>
                        <label>
                          {t("admin.planning.recurrence.until")}
                          <input type="date" name="recurrence_until_date" defaultValue={editRecurrenceUntilDate} />
                        </label>
                      </div>
                      <label className="checkline">
                        <input
                          type="checkbox"
                          name="recurrence_keep_local_time"
                          value="1"
                          defaultChecked={editRecurrenceDefaults.timeBasis === "LOCAL"}
                        />
                        {t("admin.planning.recurrence.keep_local_time")}
                      </label>
                      <p className="muted">
                        {t("admin.planning.recurrence.edit_local_time_help")}
                      </p>
                      {selectedSession.recurrence_group_id ? (
                        <p className="muted">
                          {t("admin.planning.recurrence.existing_series_help")}
                        </p>
                      ) : (
                        <p className="muted">{t("admin.planning.recurrence.convert_help")}</p>
                      )}
                    </div>
                  </fieldset>
                  </section>

                  <section
                    className={`session-edit-panel ${editTab === "visibility" ? "active" : ""}`}
                    data-session-edit-panel="visibility"
                    hidden={editTab !== "visibility"}
                  >
                  <div className="grid cols-2">
                    <SessionVisibilityFields
                      language={language}
                      initialVisibilityScopes={selectedVisibilityScopes}
                      initialBookingScopes={selectedBookingScopes}
                      allowsStudentBookings={selectedSessionAllowsStudentBookings}
                      initialShowExternalRemainingSeats={selectedShowExternalRemainingSeats}
                    />

                    <label>
                      {t("admin.planning.external_price")}
                      <input
                        type="text"
                        name="external_booking_price_ttc"
                        inputMode="decimal"
                        defaultValue={selectedSession.external_booking_price_ttc ?? ""}
                        placeholder={t("admin.planning.external_price_placeholder")}
                      />
                      <small className="muted">{t("admin.planning.external_price_remove_help")}</small>
                    </label>
                  </div>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.public_description)}>
                    <summary>{t("admin.planning.public_description_optional")}</summary>
                    <label>
                      {t("admin.planning.public_description")}
                      <textarea name="public_description" rows={4} defaultValue={selectedSession.public_description ?? ""} />
                    </label>
                  </details>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.private_description)}>
                    <summary>{t("admin.planning.private_description_optional")}</summary>
                    <label>
                      {t("admin.planning.private_description")}
                      <textarea name="private_description" rows={4} defaultValue={selectedSession.private_description ?? ""} />
                    </label>
                  </details>
                  </section>

                  <section
                    className={`session-edit-panel ${editTab === "notes" ? "active" : ""}`}
                    data-session-edit-panel="notes"
                    hidden={editTab !== "notes"}
                  >
                  <div className="row spread">
                    <p className="muted">{t("admin.planning.professor_note_help")}</p>
                    {notesAdvancedMode ? (
                      <a className="mode-link" href={notesSimpleHref}>
                        {t("admin.planning.simple_mode")}
                      </a>
                    ) : (
                      <a className="mode-link" href={notesAdvancedHref}>
                        {t("admin.planning.advanced_mode")}
                      </a>
                    )}
                  </div>
                  {notesAdvancedMode ? (
                    <RichMessageEditor
                      name="professor_reminder_note"
                      formatName="professor_reminder_note_format"
                      rows={6}
                      maxLength={12000}
                      defaultFormat="HTML"
                      defaultValue={selectedSession.professor_reminder_note ?? ""}
                      placeholder={t("admin.planning.professor_note_placeholder")}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {t("common.message")}
                      <textarea
                        name="professor_reminder_note"
                        rows={6}
                        defaultValue={selectedSession.professor_reminder_note ?? ""}
                        placeholder={t("admin.planning.professor_note_placeholder")}
                      />
                    </label>
                  )}
                  </section>
                </div>

                <footer className="session-edit-shell-footer">
                  <a className="reset-link" href={modalHref}>
                    {t("common.cancel")}
                  </a>
                  <button type="submit">{t("common.save")}</button>
                </footer>
              </form>

              <form
                action={shiftAdminSessionAction}
                className="row quick-shift-row"
                data-session-edit-schedule-only
                hidden={editTab !== "schedule"}
              >
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={activeEditTabHref} data-session-edit-return-to />
                <input type="hidden" name="current_start_at_utc" value={toDateTimeLocalUtcValue(selectedSession.start_at_utc)} />
                <input type="hidden" name="current_end_at_utc" value={toDateTimeLocalUtcValue(selectedSession.end_at_utc)} />

                <label className="scope-inline compact">
                  {t("admin.planning.quick_adjust")}
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">{t("admin.planning.scope.one")}</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{t("admin.planning.scope.future")}</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{t("admin.planning.scope.all")}</option> : null}
                  </select>
                </label>
                <button type="submit" name="minutes_delta" value="-15" className="ghost small-btn">
                  -15m
                </button>
                <button type="submit" name="minutes_delta" value="15" className="ghost small-btn">
                  +15m
                </button>
                <button type="submit" name="minutes_delta" value="60" className="ghost small-btn">
                  +1h
                </button>
                <button type="submit" name="minutes_delta" value="1440" className="ghost small-btn">
                  +1j
                </button>
              </form>
            </SessionEditModalBridge>
          </article>
        </section>
      ) : null}

      {selectedSession && attendanceModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel session-attendance-modal-v2">
            <header className="note-modal-header">
              <div className="note-modal-header-main">
                <h2 className="modal-title">{t("admin.planning.attendance_title")}</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {sessionTimeRangeLabel(selectedSession, language)} · {selectedLocationName}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <span className="status-badge status-waitlist">
                  {t("admin.planning.student_progress", {
                    current: focusedAttendanceBooking ? focusedAttendanceIndex + 1 : 0,
                    total: attendanceBookings.length || (focusedAttendanceBooking ? 1 : 0),
                  })}
                </span>
                <span className="status-badge status-scheduled">{t("admin.planning.remaining_count", { count: attendanceMissingCount })}</span>
                <a className="modal-close-x" href={modalHref} aria-label={t("admin.planning.close")}>
                  ×
                </a>
              </div>
            </header>

            {!selectedSessionHasBookings || !focusedAttendanceBooking ? (
              <section className="note-modal-empty">
                <p className="muted">{t("admin.planning.no_student_on_slot")}</p>
              </section>
            ) : (
              <>
                <div className="attendance-v2-body">
                  <aside className="attendance-v2-list">
                    <div className="attendance-v2-list-filters">
                      <a className={`mode-link ${attendanceFilter === "all" ? "mode-active" : ""}`} href={attendanceFilteredHref("all")}>
                        {t("admin.planning.filter_all")}
                      </a>
                      <a className={`mode-link ${attendanceFilter === "missing" ? "mode-active" : ""}`} href={attendanceFilteredHref("missing")}>
                        {t("admin.planning.filter_missing")}
                      </a>
                    </div>
                    <div className="attendance-v2-students">
                      {attendanceBookings.map((booking, index) => (
                        <a
                          key={booking.id}
                          href={attendanceBookingHref(booking.id)}
                          className={`attendance-v2-student-row ${booking.id === focusedAttendanceBooking.id ? "active" : ""}`}
                        >
                          <div className="attendance-v2-student-main">
                            <strong>{booking.client_display_name || t("admin.planning.participant_number", { number: index + 1 })}</strong>
                            <small className="muted">{bookingEnrollmentLabel(booking.status, language)}</small>
                          </div>
                          <span className={`status-badge ${attendanceBadgeToneClass(booking.status)}`}>
                            {attendanceChoiceLabel(booking.status, language)}
                          </span>
                        </a>
                      ))}
                    </div>
                  </aside>

                  <section className="attendance-v2-main">
                    <div className="attendance-v2-main-head">
                      <div>
                        <h3>{focusedAttendanceBooking.client_display_name || t("admin.planning.selection")}</h3>
                        <p className="muted">{t("admin.planning.completed_count", { count: attendanceCompletedCount, total: selectedSessionBookings.length })}</p>
                      </div>
                      <div className="attendance-v2-nav-links">
                        {previousAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(previousAttendanceBooking.id)}>
                            ← {t("admin.planning.previous")}
                          </a>
                        ) : null}
                        {nextAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(nextAttendanceBooking.id)}>
                            {t("admin.planning.next")} →
                          </a>
                        ) : null}
                      </div>
                    </div>

                    {canEditAttendance(focusedAttendanceBooking.status) ? (
                      <form action={adminUpdateSessionAttendanceAction} className="attendance-v2-status-form" id="attendance-status-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                        <input
                          type="hidden"
                          name="return_to"
                          value={nextAttendanceBooking ? attendanceBookingHref(nextAttendanceBooking.id) : attendanceBookingHref(focusedAttendanceBooking.id)}
                        />
                        <PresenceButtonsGroup
                          language={language}
                          formId="attendance-status-form"
                          initialValue={
                            focusedAttendanceBooking.status === "ATTENDED" ||
                            focusedAttendanceBooking.status === "NO_SHOW" ||
                            focusedAttendanceBooking.status === "EXCUSED_ABSENCE"
                              ? focusedAttendanceBooking.status
                              : "BOOKED"
                          }
                          previousHref={previousAttendanceBooking ? attendanceBookingHref(previousAttendanceBooking.id) : null}
                          nextHref={nextAttendanceBooking ? attendanceBookingHref(nextAttendanceBooking.id) : null}
                        />
                      </form>
                    ) : (
                      <p className="muted">{t("admin.planning.presence_not_editable")}</p>
                    )}

                    <details className="attendance-v2-notes">
                      <summary>{t("admin.planning.notes_optional")}</summary>
                      <form action={adminUpdateSessionBookingNoteAction} className="attendance-v2-note-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                        <input type="hidden" name="student_id" value={focusedAttendanceBooking.client_id} />
                        <input type="hidden" name="student_display_name" value={focusedAttendanceBooking.client_display_name || t("admin.planning.student_label")} />
                        <input type="hidden" name="session_title" value={selectedSession.title} />
                        <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                        <label className="session-edit-span">
                          {t("admin.planning.message")}
                          <input type="hidden" name="student_note_format" value="TEXT" />
                          <textarea
                            name="student_note"
                            rows={5}
                            placeholder={t("admin.planning.internal_note_placeholder")}
                            defaultValue={stripHtml(focusedAttendanceBooking.student_note ?? "")}
                          />
                        </label>
                        <div className="row">
                          <button type="submit" name="note_action" value="SAVE_INTERNAL" className="ghost">
                            {t("admin.planning.save_note")}
                          </button>
                          <button type="submit" name="note_action" value="SEND_PARENTS" className="ghost">
                            {t("admin.planning.send_to_parents")}
                          </button>
                        </div>
                      </form>
                    </details>
                  </section>
                </div>
                <footer className="note-modal-footer">
                  <a className="reset-link" href={modalHref}>
                    {t("admin.planning.cancel")}
                  </a>
                  <div className="row">
                    {canEditAttendance(focusedAttendanceBooking.status) ? (
                      <button type="submit" form="attendance-status-form">
                        {t("admin.planning.save_and_next")}
                      </button>
                    ) : null}
                  </div>
                </footer>
              </>
            )}
          </article>
        </section>
      ) : null}

      {selectedSession && groupNotesModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel note-modal-shell">
            <header className="note-modal-header">
              <div className="note-modal-header-main">
                <h2 className="modal-title">{t("admin.planning.group_note_title")}</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {sessionTimeRangeLabel(selectedSession, language)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label={t("admin.planning.close")}>
                  ×
                </a>
              </div>
            </header>

            <form action={adminUpdateSessionGroupNoteAction} className="note-modal-form">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="session_title" value={selectedSession.title} />
              <input type="hidden" name="return_to" value={groupNoteTabHref(groupNoteTab)} />

              <nav className="note-modal-tabs">
                <a className={`note-modal-tab ${groupNoteTab === "content" ? "active" : ""}`} href={groupNoteTabHref("content")}>
                  {t("admin.planning.tab_content")}
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "recipients" ? "active" : ""}`} href={groupNoteTabHref("recipients")}>
                  {t("admin.planning.tab_recipients")}
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "send" ? "active" : ""}`} href={groupNoteTabHref("send")}>
                  {t("admin.planning.tab_send")}
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${groupNoteTab === "content" ? "active" : ""}`}>
                  {groupNoteTemplates.length > 0 ? (
                    <label className="session-edit-span">
                      {t("admin.planning.template_label")}
                      <div className="note-template-row">
                        <select name="group_note_template_id" defaultValue={selectedGroupNoteTemplate?.id ?? ""}>
                          <option value="">{t("admin.planning.no_template")}</option>
                          {groupNoteTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                        {selectedGroupNoteTemplate ? (
                          <a className="mode-link" href={groupNotesModalClearTemplateHref}>
                            {t("admin.planning.remove")}
                          </a>
                        ) : null}
                      </div>
                    </label>
                  ) : (
                    <div className="session-edit-alert">
                      {t("admin.planning.no_template_configured")}
                    </div>
                  )}
                  <div className="row spread">
                    <p className="muted">{t("admin.planning.group_note_content_label")}</p>
                    {groupNoteAdvancedMode ? (
                      <a className="mode-link" href={groupNoteSimpleHref}>
                        {t("admin.planning.simple_mode")}
                      </a>
                    ) : (
                      <a className="mode-link" href={groupNoteAdvancedHref}>
                        {t("admin.planning.advanced_mode")}
                      </a>
                    )}
                  </div>
                  {groupNoteAdvancedMode ? (
                    <RichMessageEditor
                      name="group_note"
                      formatName="group_note_format"
                      rows={10}
                      maxLength={12000}
                      placeholder={t("admin.planning.group_note_placeholder")}
                      defaultValue={groupNotePrefill}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {t("admin.planning.message")}
                      <input type="hidden" name="group_note_format" value="TEXT" />
                      <textarea name="group_note" rows={8} defaultValue={stripHtml(groupNotePrefill)} />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "recipients" ? "active" : ""}`}>
                  <fieldset className="note-destination-radios">
                    <legend>{t("admin.planning.destination_label")}</legend>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PRIVATE" defaultChecked={groupNoteDestination === "PRIVATE"} />
                      {noteDestinationLabel("PRIVATE", language)}
                    </label>
                    <label className="checkline">
                      <input
                        type="radio"
                        name="note_destination"
                        value="STUDENTS_AND_PARENTS"
                        defaultChecked={groupNoteDestination === "STUDENTS_AND_PARENTS"}
                      />
                      {noteDestinationLabel("STUDENTS_AND_PARENTS", language)}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PARENTS" defaultChecked={groupNoteDestination === "PARENTS"} />
                      {noteDestinationLabel("PARENTS", language)}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="STUDENTS" defaultChecked={groupNoteDestination === "STUDENTS"} />
                      {noteDestinationLabel("STUDENTS", language)}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PROFESSOR" defaultChecked={groupNoteDestination === "PROFESSOR"} />
                      {noteDestinationLabel("PROFESSOR", language)}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="ADMINS" defaultChecked={groupNoteDestination === "ADMINS"} />
                      {noteDestinationLabel("ADMINS", language)}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="SELF" defaultChecked={groupNoteDestination === "SELF"} />
                      {noteDestinationLabel("SELF", language)}
                    </label>
                  </fieldset>

                  <div className="note-recipient-summary">
                    <strong>{t("admin.planning.selected_students_count", { count: sessionRecipientStudentIds.length })}</strong>
                    <span className="muted">{sessionRecipientSummary || t("admin.planning.no_student_summary")}</span>
                  </div>
                  <details className="note-recipient-picker" open={isGroupNoteStudentAudience}>
                    <summary>{t("admin.planning.edit_selection")}</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label={t("admin.planning.included_students")}
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder={t("admin.planning.search_student")}
                      emptySelectionLabel={selectedSessionHasBookings ? t("admin.planning.no_student_selected") : t("admin.planning.no_student_on_slot")}
                    />
                  </details>
                  {!selectedSessionHasBookings && isGroupNoteStudentAudience ? (
                    <p className="flash-err">{t("admin.planning.no_student_for_student_audience")}</p>
                  ) : null}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "send" ? "active" : ""}`}>
                  {groupNoteDestination === "PRIVATE" ? (
                    <p className="muted">{t("admin.planning.internal_destination_help")}</p>
                  ) : (
                    <>
                      <label className="checkline">
                        <input type="checkbox" name="send_to_self" />
                        {t("admin.planning.send_copy_self")}
                      </label>
                      <label>
                        {t("admin.planning.email_subject_optional")}
                        <input type="text" name="subject" defaultValue={t("admin.planning.group_note_subject_default", { title: selectedSession.title })} maxLength={255} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="confirm_send" />
                        {t("admin.planning.confirm_send_count", { count: sessionRecipientStudentIds.length })}
                      </label>
                    </>
                  )}
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  {t("admin.planning.close")}
                </a>
                <div className="row">
                  <button type="submit" name="note_action" value="SAVE_ONLY" className="ghost">
                    {t("admin.planning.save")}
                  </button>
                  {groupNoteDestination !== "PRIVATE" ? (
                    <button type="submit" name="note_action" value="SEND_EMAIL">
                      {t("admin.planning.send")}
                    </button>
                  ) : null}
                </div>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionEmailModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel note-modal-shell">
            <header className="note-modal-header">
              <div className="note-modal-header-main">
                <h2 className="modal-title">{t("admin.planning.email_title")}</h2>
                <p className="muted">
                  {t("admin.planning.slot_prefix")} {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {formatTime(selectedSession.start_at_utc, selectedSession.timezone, language)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label={t("admin.planning.close")}>
                  ×
                </a>
              </div>
            </header>
            <form action={adminSendSessionBroadcastAction} className="note-modal-form">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="channel" value="EMAIL" />
              <input type="hidden" name="return_to" value={sessionEmailTabHref(emailTab)} />

              <nav className="note-modal-tabs">
                <a className={`note-modal-tab ${emailTab === "recipients" ? "active" : ""}`} href={sessionEmailTabHref("recipients")}>
                  {t("admin.planning.tab_recipients")}
                </a>
                <a className={`note-modal-tab ${emailTab === "content" ? "active" : ""}`} href={sessionEmailTabHref("content")}>
                  {t("admin.planning.tab_content")}
                </a>
                <a className={`note-modal-tab ${emailTab === "send" ? "active" : ""}`} href={sessionEmailTabHref("send")}>
                  {t("admin.planning.tab_options")}
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${emailTab === "recipients" ? "active" : ""}`}>
                  <label>
                    {t("admin.planning.recipients_label")}
                    <select name="audience" defaultValue={emailAudience}>
                      <option value="STUDENTS">{messageAudienceLabel("STUDENTS", language)}</option>
                      <option value="PARENTS">{messageAudienceLabel("PARENTS", language)}</option>
                      <option value="STUDENTS_AND_PARENTS">{messageAudienceLabel("STUDENTS_AND_PARENTS", language)}</option>
                      <option value="PROFESSOR">{messageAudienceLabel("PROFESSOR", language)}</option>
                      <option value="ADMINS">{messageAudienceLabel("ADMINS", language)}</option>
                      <option value="SELF">{messageAudienceLabel("SELF", language)}</option>
                    </select>
                  </label>
                  <div className="note-recipient-summary">
                    <strong>{t("admin.planning.selected_recipients_count", { count: sessionRecipientStudentIds.length })}</strong>
                    <span className="muted">{sessionRecipientSummary || t("admin.planning.no_student_recipient")}</span>
                  </div>
                  <details className="note-recipient-picker" open={emailAudience === "STUDENTS" || emailAudience === "PARENTS" || emailAudience === "STUDENTS_AND_PARENTS"}>
                    <summary>{t("admin.planning.edit")}</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label={t("admin.planning.included_students_optional_remove")}
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder={t("admin.planning.search_student")}
                      emptySelectionLabel={t("admin.planning.no_student_selected")}
                    />
                  </details>
                  {!selectedSessionHasBookings ? <p className="muted">{t("admin.planning.no_student_recipient_help")}</p> : null}
                </section>

                <section className={`note-modal-panel ${emailTab === "content" ? "active" : ""}`}>
                  <label>
                    {t("admin.planning.subject")}
                    <input type="text" name="subject" defaultValue={t("admin.planning.slot_message_subject_default", { title: selectedSession.title })} maxLength={255} required />
                  </label>
                  <div className="row spread">
                    <p className="muted">{t("admin.planning.message")}</p>
                    {emailAdvancedMode ? (
                      <a className="mode-link" href={sessionEmailSimpleHref}>
                        {t("admin.planning.simple_mode")}
                      </a>
                    ) : (
                      <a className="mode-link" href={sessionEmailAdvancedHref}>
                        {t("admin.planning.advanced_mode")}
                      </a>
                    )}
                  </div>
                  {emailAdvancedMode ? (
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={10}
                      maxLength={12000}
                      defaultValue={t("admin.planning.email_default_body", {
                        title: selectedSession.title,
                        date: formatDate(selectedSession.start_at_utc, selectedSession.timezone, language),
                      })}
                      placeholder={t("admin.planning.enter_message")}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {t("admin.planning.message")}
                      <input type="hidden" name="body_format" value="TEXT" />
                      <textarea
                        name="body"
                        rows={8}
                        defaultValue={t("admin.planning.email_default_body", {
                          title: selectedSession.title,
                          date: formatDate(selectedSession.start_at_utc, selectedSession.timezone, language),
                        })}
                        placeholder={t("admin.planning.enter_message")}
                      />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${emailTab === "send" ? "active" : ""}`}>
                  <label className="checkline">
                    <input type="checkbox" name="send_to_self" />
                    {t("admin.planning.send_copy_self")}
                  </label>
                  <label className="session-edit-span">
                    {t("admin.planning.copy_emails_optional")}
                    <textarea name="cc_emails" rows={2} placeholder="copie@example.com; autre@example.com" />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="confirm_send" />
                    {t("admin.planning.confirm_send_to_count", { count: sessionRecipientStudentIds.length })}
                  </label>
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  {t("admin.planning.close")}
                </a>
                <div className="row">
                  <button type="submit">{t("admin.planning.send")}</button>
                </div>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionSmsModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact session-group-notes-modal">
            <a className="modal-close-x" href={modalHref} aria-label={t("admin.planning.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.planning.sms_title")}</h2>
            <p className="muted">{t("admin.planning.sms_help")}</p>
            <form action={adminSendSessionBroadcastAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="channel" value="SMS" />
              <input type="hidden" name="return_to" value={sessionSmsModalHref} />

              <label>
                {t("admin.planning.recipients_label")}
                <select name="audience" defaultValue="STUDENTS">
                  <option value="STUDENTS">{messageAudienceLabel("STUDENTS", language)}</option>
                  <option value="PARENTS">{messageAudienceLabel("PARENTS", language)}</option>
                  <option value="STUDENTS_AND_PARENTS">{messageAudienceLabel("STUDENTS_AND_PARENTS", language)}</option>
                  <option value="PROFESSOR">{messageAudienceLabel("PROFESSOR", language)}</option>
                  <option value="ADMINS">{messageAudienceLabel("ADMINS", language)}</option>
                  <option value="SELF">{messageAudienceLabel("SELF", language)}</option>
                </select>
              </label>

              <SearchMultiSelect
                className="session-edit-span"
                label={t("admin.planning.included_students_optional_remove")}
                name="included_student_ids"
                options={sessionRecipientStudents}
                selectedIds={sessionRecipientStudentIds}
                placeholder={t("admin.planning.search_student")}
                emptySelectionLabel={t("admin.planning.no_student_selected")}
              />
              {!selectedSessionHasBookings ? <p className="muted">{t("admin.planning.no_student_recipient_help")}</p> : null}

              <label className="checkline">
                <input type="checkbox" name="send_to_self" />
                {t("admin.planning.send_copy_self")}
              </label>

              <label>
                {t("admin.planning.subject_optional")}
                <input type="text" name="subject" defaultValue={t("admin.planning.sms_subject_default", { title: selectedSession.title })} maxLength={255} />
              </label>

              <label className="session-edit-span">
                {t("admin.planning.copy_phones_optional")}
                <textarea name="cc_phone_numbers" rows={2} placeholder="+33600000000; 0600000000" />
              </label>

              <label className="session-edit-span">
                {t("admin.planning.sms_message_label")}
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  defaultFormat="TEXT"
                  rows={8}
                  maxLength={12000}
                  defaultValue={t("admin.planning.sms_default_body", {
                    title: selectedSession.title,
                    date: formatDate(selectedSession.start_at_utc, selectedSession.timezone, language),
                  })}
                  placeholder={t("admin.planning.enter_sms_message")}
                />
              </label>

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  {t("admin.planning.cancel")}
                </a>
                <button type="submit">{t("admin.planning.send_sms")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && duplicateModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={modalHref} aria-label={t("admin.planning.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.planning.duplicate_title")}</h2>
            <p className="muted">
              {t("admin.planning.duplicate_help")}
            </p>

            <form action={duplicateAdminSessionAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={duplicateModalHref} />
              <input type="hidden" name="session_timezone" value={selectedSession.timezone} />

              <div className="grid cols-2">
                <label>
                  {t("admin.planning.target_date")}
                  <input
                    type="date"
                    name="target_date"
                    defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                    required
                  />
                </label>
                <label>
                  {t("admin.planning.target_start_time")}
                  <input
                    type="time"
                    name="target_time"
                    defaultValue={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone, language)}
                    required
                  />
                </label>
              </div>

              {selectedSession.recurrence_group_id ? (
                <fieldset className="grid">
                  <legend>{t("admin.planning.duplicate_scope")}</legend>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="ONE" defaultChecked />
                    {t("admin.planning.duplicate_one")}
                  </label>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="SERIES_FUTURE" />
                    {t("admin.planning.duplicate_future")}
                  </label>
                </fieldset>
              ) : (
                <>
                  <input type="hidden" name="apply_scope" value="ONE" />
                  <p className="muted">{t("admin.planning.one_off_duplicate_help")}</p>
                </>
              )}

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  {t("admin.planning.cancel")}
                </a>
                <button type="submit">{t("admin.planning.duplicate_slot")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && confirmAction ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-confirm-operation">
            <a className="modal-close-x" href={confirmCloseHref} aria-label={t("admin.planning.close")}>
              ×
            </a>
            <h2 className="modal-title">{confirmAction === "delete" ? t("admin.planning.confirm_delete_title") : t("admin.planning.confirm_cancel_title")}</h2>
            <p className="muted">
              {confirmAction === "delete"
                ? t("admin.planning.confirm_delete_help")
                : t("admin.planning.confirm_cancel_help")}
            </p>

            <form action={confirmAction === "delete" ? deleteAdminSessionAction : cancelAdminSessionAction} className="grid">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={modalHref} />
              {confirmAction === "delete" && selectedSession.recurrence_group_id ? (
                <label className="session-edit-span">
                  {t("admin.planning.delete_following_label")}
                  <select name="delete_following" defaultValue="no">
                    <option value="no">{t("admin.planning.delete_following_one")}</option>
                    <option value="yes">{t("admin.planning.delete_following_future")}</option>
                  </select>
                </label>
              ) : (
                <label>
                  {t("admin.planning.scope_label")}
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">{t("admin.planning.this_session_only")}</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{t("admin.planning.scope.future")}</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{t("admin.planning.scope.all")}</option> : null}
                  </select>
                </label>
              )}

              <p className="muted span-3">
                {t("admin.planning.target_professor")}: <strong>{selectedEffectiveProfessorLabel || t("admin.planning.no_teacher_required")}</strong>
              </p>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_students" />
                {t("admin.planning.notify_students")}
              </label>

              <label>
                {t("admin.planning.students_subject")}
                <input
                  type="text"
                  name="students_subject"
                  defaultValue={
                    confirmAction === "delete"
                      ? t("admin.planning.students_subject_delete_default", { title: selectedSession.title })
                      : t("admin.planning.students_subject_cancel_default", { title: selectedSession.title })
                  }
                  maxLength={255}
                />
              </label>

              <label className="session-edit-span">
                {t("admin.planning.students_message")}
                <RichMessageEditor
                  name="students_message"
                  formatName="students_format"
                  rows={8}
                  maxLength={12000}
                  defaultValue={
                    confirmAction === "delete"
                      ? t("admin.planning.students_message_delete_default", {
                          title: selectedSession.title,
                          date: formatDate(selectedSession.start_at_utc, selectedSession.timezone, language),
                        })
                      : t("admin.planning.students_message_cancel_default", {
                          title: selectedSession.title,
                          date: formatDate(selectedSession.start_at_utc, selectedSession.timezone, language),
                        })
                  }
                  placeholder={t("admin.planning.students_message")}
                />
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_professor" />
                {t("admin.planning.notify_professor")}
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="professor_same_as_students" defaultChecked />
                {t("admin.planning.same_as_students")}
              </label>

              <label>
                {t("admin.planning.professor_subject_distinct")}
                <input type="text" name="professor_subject" maxLength={255} />
              </label>

              <label className="session-edit-span">
                {t("admin.planning.professor_message_distinct")}
                <RichMessageEditor
                  name="professor_message"
                  formatName="professor_format"
                  rows={8}
                  maxLength={12000}
                  placeholder={t("admin.planning.professor_message_distinct")}
                />
              </label>

              <div className="row quick-actions-row">
                <button className="danger" type="submit">
                  {confirmAction === "delete" ? t("admin.planning.confirm_delete_title") : t("admin.planning.confirm_cancel_title")}
                </button>
                <a className="reset-link" href={confirmCloseHref}>
                  {t("admin.planning.return")}
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
