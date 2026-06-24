import Link from "next/link";
import { redirect } from "next/navigation";

import {
  adminAddClientToSessionAction,
  adminRemoveClientFromSessionAction,
  adminSendSessionBroadcastAction,
  adminUpdateSessionAttendanceAction,
  adminUpdateSessionBookingNoteAction,
  adminUpdateSessionBookingStudentTimeAction,
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
import { hasAdminPermission } from "../../lib/admin-access";
import AutoSubmitSelect from "../../components/auto-submit-select";
import RichMessageEditor from "../../components/rich-message-editor";
import SearchMultiSelect from "../../components/search-multi-select";
import SessionTimeFields from "../../components/session-time-fields";
import SessionVisibilityFields from "../../components/session-visibility-fields";
import ModalA11yFrame from "../../components/modal-a11y-frame";
import PresenceButtonsGroup from "../../components/presence-buttons-group";
import DayEventsDrawer from "../../components/planning/day-events-drawer";
import SessionEditModalBridge from "../../components/planning/session-edit-modal-bridge";
import MonthDayCard from "../../components/planning/month-day-card";
import SessionCreateMainFields from "../../components/planning/session-create-main-fields";
import SessionCreateSubmitButton from "../../components/planning/session-create-submit-button";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../lib/ui-i18n";
import { resolveUiFlashMessage, withUiLanguage } from "../../lib/ui-messages";
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
  language: UiLanguage;
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

const PLANNING_TIMEZONES: Array<{ value: string; labelKey: string }> = [
  { value: "Europe/Paris", labelKey: "admin.planning.timezone.europe_paris" },
  { value: "Europe/Brussels", labelKey: "admin.planning.timezone.europe_brussels" },
  { value: "Europe/Zurich", labelKey: "admin.planning.timezone.europe_zurich" },
  { value: "Europe/London", labelKey: "admin.planning.timezone.europe_london" },
  { value: "Europe/Madrid", labelKey: "admin.planning.timezone.europe_madrid" },
  { value: "America/New_York", labelKey: "admin.planning.timezone.america_new_york" },
  { value: "America/Los_Angeles", labelKey: "admin.planning.timezone.america_los_angeles" },
];

const SESSION_AUDIENCE_SCOPE_LABELS: Record<SessionAudienceScope, string> = {
  EXTERNAL: "Externe",
  SUBSCRIPTION: "Abonne / carnet",
  FORFAIT: "Forfait",
  PRIVATE: "Prive",
};

function pickText(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

function localeForLanguage(language: UiLanguage): string {
  return language === "en" ? "en-GB" : "fr-FR";
}

function planningTimezoneLabel(value: string, language: UiLanguage): string {
  const known = PLANNING_TIMEZONES.find((option) => option.value === value);
  if (known) {
    return uiText(language, known.labelKey);
  }
  return uiText(language, "admin.planning.timezone.custom", { value });
}

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
    return new Intl.DateTimeFormat(localeForLanguage(language), {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  return new Intl.DateTimeFormat(localeForLanguage(language), {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function agendaDayLongLabel(dayKey: string, language: UiLanguage = "fr"): string {
  const date = keyToUtcDate(dayKey);
  return new Intl.DateTimeFormat(localeForLanguage(language), {
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
      title: new Intl.DateTimeFormat(localeForLanguage(language), {
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
      title: `${new Intl.DateTimeFormat(localeForLanguage(language), {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(from)} - ${new Intl.DateTimeFormat(localeForLanguage(language), {
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
    title: new Intl.DateTimeFormat(localeForLanguage(language), {
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
    return pickText(language, "Navigation: mois par mois.", "Navigation: month by month.");
  }
  if (view === "week") {
    return pickText(language, "Navigation: semaine par semaine.", "Navigation: week by week.");
  }
  return pickText(language, "Navigation: jour par jour.", "Navigation: day by day.");
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

function toTimeInputInTimezone(value: string, timezone: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "";
  }
  return parsed.toLocaleTimeString("fr-FR", {
    timeZone: resolveTimezone(timezone),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatDateKeyFr(value: string, language: UiLanguage = "fr"): string {
  if (!isDateKey(value)) {
    return "-";
  }
  return new Intl.DateTimeFormat(localeForLanguage(language), {
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
    const timeKey = toTimeInputInTimezone(value, resolvedTimezone);
    if (dateKey && timeKey) {
      return `${formatDateKeyFr(dateKey, language)}, ${timeKey}`;
    }
  }
  return parsed.toLocaleString(localeForLanguage(language), {
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
    const timeKey = toTimeInputInTimezone(value, resolvedTimezone);
    if (timeKey) {
      return timeKey;
    }
  }
  return parsed.toLocaleTimeString(localeForLanguage(language), {
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
    return pickText(language, "Toute la journee", "All day");
  }
  return `${formatTime(session.start_at_utc, session.timezone, language)} - ${formatTime(session.end_at_utc, session.timezone, language)}`;
}

function bookingStudentTimeRangeLabel(
  booking: AdminSessionBookingOut,
  session: AdminSessionOut,
  language: UiLanguage = "fr",
): string | null {
  if (!booking.student_start_at_utc || !booking.student_end_at_utc) {
    return null;
  }
  return `${formatTime(booking.student_start_at_utc, session.timezone, language)} - ${formatTime(booking.student_end_at_utc, session.timezone, language)}`;
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

type StudentTimePreset = {
  start: string;
  end: string;
  label: string;
};

function timeInputToMinutes(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
    return null;
  }
  return hours * 60 + minutes;
}

function minutesToTimeInput(value: number): string {
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function studentTimePresetOptions(session: AdminSessionOut): StudentTimePreset[] {
  const duration = sessionDurationMinutes(session);
  if (!duration || duration <= 60) {
    return [];
  }
  const start = timeInputToMinutes(toTimeInputInTimezone(session.start_at_utc, session.timezone));
  const end = timeInputToMinutes(toTimeInputInTimezone(session.end_at_utc, session.timezone));
  if (start === null || end === null || end <= start) {
    return [];
  }

  const studentDuration = Math.min(60, end - start);
  const options: StudentTimePreset[] = [];
  for (let optionStart = start; optionStart + studentDuration <= end; optionStart += 15) {
    const optionEnd = optionStart + studentDuration;
    const startLabel = minutesToTimeInput(optionStart);
    const endLabel = minutesToTimeInput(optionEnd);
    options.push({
      start: startLabel,
      end: endLabel,
      label: `${startLabel} - ${endLabel}`,
    });
  }
  return options;
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
    return pickText(language, "Liste attente", "Waitlist");
  }
  if (status === "BOOKED") {
    return pickText(language, "Inscrit", "Booked");
  }
  if (status === "CANCELLED") {
    return pickText(language, "Annule", "Cancelled");
  }
  return pickText(language, "Inscrit", "Booked");
}

function bookingPresenceLabel(status: string, language: UiLanguage = "fr"): string | null {
  if (status === "ATTENDED") {
    return pickText(language, "Present", "Present");
  }
  if (status === "NO_SHOW") {
    return pickText(language, "Absent", "Absent");
  }
  if (status === "EXCUSED_ABSENCE") {
    return pickText(language, "Abs. excusee", "Excused");
  }
  return null;
}

function attendanceChoiceLabel(status: string, language: UiLanguage = "fr"): string {
  if (status === "ATTENDED") {
    return pickText(language, "Present", "Present");
  }
  if (status === "NO_SHOW") {
    return pickText(language, "Absent non excuse", "Unexcused absence");
  }
  if (status === "EXCUSED_ABSENCE") {
    return pickText(language, "Absent excuse", "Excused absence");
  }
  return pickText(language, "A saisir", "To fill in");
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
    return "Online";
  }
  if (lowerLocation.includes("domicile")) {
    return pickText(language, "Domicile", "Home visit");
  }
  if (session.is_private) {
    return pickText(language, "Prive", "Private");
  }
  return pickText(language, "Collectif", "Group");
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
  if (language === "en") {
    if (scope === "EXTERNAL") {
      return "External";
    }
    if (scope === "SUBSCRIPTION") {
      return "Subscription / pass";
    }
    if (scope === "FORFAIT") {
      return "Package";
    }
    if (scope === "PRIVATE") {
      return "Private";
    }
  }
  return SESSION_AUDIENCE_SCOPE_LABELS[scope] ?? scope;
}

function sessionAudienceScopesLabel(scopes: SessionAudienceScope[], language: UiLanguage = "fr"): string {
  if (scopes.length === 1 && scopes[0] === "PRIVATE") {
    return pickText(language, "Prive", "Private");
  }
  return scopes.map((scope) => sessionAudienceScopeLabel(scope, language)).join(" + ");
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
  if (query.language === "en") {
    sp.set("lang", "en");
  }
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
    return pickText(language, "Ponctuel", "One-time");
  }
  const { frequency, interval, timeBasis } = parseRecurrenceRuleDefaults(session.recurrence_rule);

  let label = pickText(language, "Hebdo", "Weekly");
  if (frequency === "DAILY") {
    label = interval > 1 ? pickText(language, `Tous les ${interval} jours`, `Every ${interval} days`) : pickText(language, "Quotidien", "Daily");
  } else if (frequency === "WEEKLY") {
    label = interval > 1 ? pickText(language, `Toutes les ${interval} semaines`, `Every ${interval} weeks`) : pickText(language, "Hebdo", "Weekly");
  } else if (frequency === "MONTHLY") {
    label = interval > 1 ? pickText(language, `Tous les ${interval} mois`, `Every ${interval} months`) : pickText(language, "Mensuel", "Monthly");
  }
  if (timeBasis === "LOCAL") {
    return `${label} · ${pickText(language, "heure locale fixe", "fixed local time")}`;
  }
  return `${label} · ${pickText(language, "UTC fixe", "fixed UTC")}`;
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

function parseRecurrenceRuleDefaults(
  rawRule: string | null | undefined,
): { frequency: "DAILY" | "WEEKLY" | "MONTHLY"; interval: number; timeBasis: "LOCAL" | "UTC" } {
  const raw = String(rawRule || "").trim().toUpperCase();
  if (!raw) {
    return { frequency: "WEEKLY", interval: 1, timeBasis: "LOCAL" };
  }
  const [rulePart, basisPart] = raw.includes("@") ? raw.split("@", 2) : [raw, "LOCAL"];
  const [frequencyRaw, intervalRaw] = rulePart.includes(":") ? rulePart.split(":", 2) : [rulePart, "1"];
  const frequency = frequencyRaw === "DAILY" || frequencyRaw === "MONTHLY" ? frequencyRaw : "WEEKLY";
  const intervalParsed = Number.parseInt(intervalRaw || "1", 10);
  const interval = Number.isFinite(intervalParsed) && intervalParsed > 0 ? intervalParsed : 1;
  const timeBasis = basisPart === "UTC" ? "UTC" : "LOCAL";
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
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_planning")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const selectedCourseType = readParam(searchParams, "course_type_id");
  const selectedActivityIds = readMultiParam(searchParams, "activity_ids");
  const rawLocation = readParam(searchParams, "location_id");
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

  const sessionsQuery = new URLSearchParams();
  const locationFilterIdsForApi = selectedLocationIdsFromQuery.length ? selectedLocationIdsFromQuery : rawLocation ? [rawLocation] : [];
  for (const locationId of locationFilterIdsForApi) {
    sessionsQuery.append("location_ids", locationId);
  }
  if (selectedCourseType) {
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

  const focusedLocationId = rawLocation || selectedLocationIdsFromQuery[0] || "";
  const selectedLocationIds = selectedLocationIdsFromQuery.length ? selectedLocationIdsFromQuery : rawLocation ? [rawLocation] : [];
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
  const isEnglish = language === "en";

  const queryForLinks: PlanningQuery = {
    language,
    agendaView,
    agendaDate,
    timezone,
    locationId: focusedLocationId,
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
    activityIds: [],
    courseTypeId: "",
    locationId: "",
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

  const agendaRange = buildAgendaRange(agendaView, agendaDate, language);
  const fromMs = agendaRange.from.getTime();
  const toMs = agendaRange.to.getTime();

  const courseTypeById = new Map(courseTypes.map((row) => [row.id, row]));
  const locationById = new Map(locations.map((row) => [row.id, row]));
  const professorById = new Map(professors.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));
  const selectedLocationSet = new Set(selectedLocationIds);
  const selectedActivitySet = new Set(selectedActivityIds);
  const selectedProfessorSet = new Set(selectedProfessorIds);
  const selectedActivityLabels = selectedActivityIds
    .map((activityId) => courseTypeById.get(activityId)?.name ?? "")
    .filter((name) => name.length > 0);
  const selectedLocationLabels = selectedLocationIdsFromQuery
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
    Boolean(selectedCourseType) ||
    selectedLocationIdsFromQuery.length > 0 ||
    selectedProfessorIds.length > 0 ||
    selectedClientIds.length > 0 ||
    selectedStatus !== "ALL" ||
    selectedClientStatus !== "ALL";
  const planningLocationLabel =
    selectedLocationLabels.length > 1
      ? pickText(language, `Multi lieux (${selectedLocationLabels.length})`, `Multiple locations (${selectedLocationLabels.length})`)
      : selectedLocationLabels[0]
        ? selectedLocationLabels[0]
        : focusedLocation?.name
          ? focusedLocation.name
          : pickText(language, "Tous les lieux", "All locations");
  const planningViewLabel = agendaView === "month"
    ? pickText(language, "Mois", "Month")
    : agendaView === "week"
      ? pickText(language, "Semaine", "Week")
      : pickText(language, "Jour", "Day");
  const planningSubtitle = `${planningViewLabel} · ${planningLocationLabel} · ${timezone}`;

  const filteredSessions = sessions
    .filter((session) => {
      if (selectedLocationSet.size > 0 && !selectedLocationSet.has(session.location_id)) {
        return false;
      }
      if (selectedActivitySet.size > 0 && !selectedActivitySet.has(session.course_type_id)) {
        return false;
      }
      if (selectedCourseType && session.course_type_id !== selectedCourseType) {
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
    .sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  const planningStats = filteredSessions.reduce(
    (acc, session) => {
      acc.sessions += 1;
      acc.booked += Number(session.booked_count || 0);
      if (session.allows_student_bookings !== false && Number(session.capacity_max || 0) > 0) {
        const remaining = Math.max(0, Number(session.capacity_max || 0) - Number(session.booked_count || 0));
        acc.openSeats += remaining;
        if (remaining === 0) {
          acc.full += 1;
        }
      }
      if (session.requires_professor !== false && !session.effective_teacher_id) {
        acc.missingTeacher += 1;
      }
      return acc;
    },
    { sessions: 0, booked: 0, openSeats: 0, full: 0, missingTeacher: 0 },
  );

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
  const agendaDayCards = agendaDays.map((day) => ({
    key: day.key,
    label: day.label,
    events: day.sessions.map((session) => session),
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
    .sort((a, b) => clientDisplayName(a).localeCompare(clientDisplayName(b), "fr"));
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

  const okMessage =
    resolveUiFlashMessage(searchParams, language, "ok") ??
    resolveAuthOkMessage(readParam(searchParams, "ok"), readParam(searchParams, "ok_code"), language);
  const errorMessage =
    resolveUiFlashMessage(searchParams, language, "error") ??
    readParam(searchParams, "error");
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
  const editTabReturnHrefs: Record<SlotEditTab, string> = {
    general: editTabHref("general"),
    schedule: editTabHref("schedule"),
    visibility: editTabHref("visibility"),
    notes: notesAdvancedMode ? notesAdvancedHref : notesSimpleHref,
  };
  const activeEditTabHref = editTabReturnHrefs[editTab];
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
  const selectedCourseTypeName = selectedSession ? courseTypeById.get(selectedSession.course_type_id)?.name ?? pickText(language, "Type non defini", "Undefined type") : "";
  const selectedLocationName = selectedSession ? locationById.get(selectedSession.location_id)?.name ?? pickText(language, "Lieu non defini", "Undefined location") : "";
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
  const selectedSessionSupportsStudentTimeOverrides = selectedSession ? selectedSession.supports_student_time_overrides === true : false;
  const selectedHabitualProfessorName = selectedSession
    ? (selectedSession.habitual_teacher_display_name || "").trim() ||
      (selectedHabitualProfessorDetail ? `${selectedHabitualProfessorDetail.first_name} ${selectedHabitualProfessorDetail.last_name}`.trim() : "") ||
      pickText(language, "Professeur non defini", "Undefined teacher")
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
      ? selectedHabitualProfessorName === pickText(language, "Professeur non defini", "Undefined teacher")
        ? pickText(language, "Non requis", "Not required")
        : `${selectedHabitualProfessorName}${pickText(language, " (optionnel)", " (optional)")}`
      : selectedHabitualProfessorName;
  const selectedSubstituteProfessorLabel = !selectedSession
    ? ""
    : !selectedSessionRequiresProfessor
      ? selectedSubstituteProfessorName
        ? `${selectedSubstituteProfessorName}${pickText(language, " (optionnel)", " (optional)")}`
        : pickText(language, "Aucun", "None")
      : selectedSubstituteProfessorName || pickText(language, "Aucun", "None");
  const selectedSessionIsSubstituted = Boolean(selectedSession?.substitute_teacher_id);
  const selectedEffectiveProfessorLabel = !selectedSession
    ? ""
    : !selectedSessionRequiresProfessor
      ? selectedEffectiveProfessorName && selectedEffectiveProfessorName !== pickText(language, "Professeur non defini", "Undefined teacher")
        ? `${selectedEffectiveProfessorName}${selectedSessionIsSubstituted ? pickText(language, " (remplacant optionnel)", " (optional substitute)") : pickText(language, " (optionnel)", " (optional)")}`
        : pickText(language, "Non requis", "Not required")
      : `${selectedEffectiveProfessorName}${selectedSessionIsSubstituted ? pickText(language, " (remplacant)", " (substitute)") : ""}`;
  const selectedEffectiveProfessorZoomLink = (selectedEffectiveProfessorDetail?.zoom_link ?? "").trim();
  const selectedSessionZoomLink =
    selectedSession && ((selectedSession.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      ? ((selectedSession?.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      : null;
  const selectedSessionTypeName = selectedSession ? sessionTypeLabel(selectedSession, selectedLocationName, language) : "";
  const selectedSessionHeaderTitle = selectedSession ? `${selectedCourseTypeName} - ${selectedLocationName}` : "";
  const selectedSessionSubtitle = selectedSession
    ? `${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · ${sessionTimeRangeLabel(selectedSession, language)} · ${selectedSession.timezone} · ${pickText(language, "Prof:", "Teacher:")} ${selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")}`
    : "";
  const selectedSessionDurationValue = selectedSession ? sessionDurationMinutes(selectedSession) : null;
  const selectedSessionDurationLabel = !selectedSession
    ? ""
    : selectedSessionDurationValue === null
      ? pickText(language, "Toute la journee", "All day")
      : `${selectedSessionDurationValue} min`;
  const selectedSessionStudentTimePresets =
    selectedSession && selectedSessionSupportsStudentTimeOverrides ? studentTimePresetOptions(selectedSession) : [];
  const selectedSessionRecurrenceLabel = selectedSession ? recurrenceLabel(selectedSession, language) : "";
  const selectedSessionRecurrenceEndLabel =
    selectedSession?.recurrence_end_date && selectedSession.recurrence_group_id
      ? formatDateKeyFr(selectedSession.recurrence_end_date, language)
      : "";
  const selectedSessionCapacityLabel = !selectedSession
    ? ""
    : !selectedSessionAllowsStudentBookings
      ? pickText(language, "Sans eleve", "No student")
      : `${selectedSession.booked_count}/${selectedSession.capacity_max}`;
  const selectedSessionEnrollmentSummary = !selectedSession
    ? ""
    : !selectedSessionAllowsStudentBookings
      ? pickText(language, "Aucune inscription possible", "Bookings disabled")
      : selectedSessionBookings.length === 0
        ? pickText(language, "Aucun eleve inscrit", "No student booked")
        : pickText(
            language,
            `${selectedSessionBookings.length} eleve${selectedSessionBookings.length > 1 ? "s" : ""} inscrit${selectedSessionBookings.length > 1 ? "s" : ""}`,
            `${selectedSessionBookings.length} attendee${selectedSessionBookings.length > 1 ? "s" : ""}`,
          );
  const sessionTimezoneValues = new Set<string>([
    ...PLANNING_TIMEZONES.map((option) => option.value),
    ...locations.map((row) => row.timezone),
    selectedSession?.timezone ?? timezone,
  ]);
  const sessionTimezoneOptions = Array.from(sessionTimezoneValues)
    .filter((value) => value && value.trim().length > 0)
    .sort((a, b) => a.localeCompare(b, localeForUiLanguage(language)))
    .map((value) => ({ value, label: planningTimezoneLabel(value, language) }));
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
  const selectedSessionBookingLabel = selectedSessionAllowsStudentBookings
    ? sessionAudienceScopesLabel(selectedBookingScopes, language)
    : pickText(language, "Fermee", "Closed");
  const selectedSessionPublicationSummary = !selectedSession
    ? ""
    : `${pickText(language, "Reservation", "Booking")}: ${selectedSessionBookingLabel}${selectedSession.external_booking_price_ttc ? ` · ${pickText(language, "Tarif ext.", "External price")}: ${selectedSession.external_booking_price_ttc} EUR TTC` : ""}`;
  const selectedSessionHasNotesSection = Boolean(
    selectedSession?.group_note ||
      selectedSession?.public_description ||
      selectedSession?.private_description ||
      selectedSession?.professor_reminder_note,
  );
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
  const editRecurrenceUntilDate = selectedSession
    ? selectedSession.recurrence_end_date || toDateInputInTimezone(addUtcDays(new Date(selectedSession.start_at_utc), 84).toISOString(), selectedSession.timezone)
    : agendaDate;
  const planningText = isEnglish
    ? {
        backendError: "Backend error:",
        schedule: "Schedule",
        view: "View",
        edit: "Edit",
        addSlot: "Add slot",
        settings: "Settings",
        location: "Location",
        calendarView: "Calendar view",
        timezone: "Timezone",
        reset: "Reset",
        advancedFilters: "Advanced filters",
        activities: "Activities",
        type: "Type",
        locations: "Locations",
        teachers: "Teachers",
        students: "Students",
        sessionStatus: "Session status",
        clientStatus: "Client status",
        noAdvancedFilters: "No advanced filters active.",
        filtersTitle: "Schedule filters",
        filtersHelp: "You can filter by multiple activities, rooms, teachers and students.",
        courseType: "Course type",
        byActivities: "By activities",
        byRooms: "By rooms",
        byTeachers: "By teachers",
        byStudents: "By students",
        searchActivity: "Search an activity...",
        searchRoom: "Search a room...",
        searchTeacher: "Search a teacher...",
        searchStudent: "Search a student...",
        noActivitySelected: "No activity selected.",
        noRoomSelected: "No room selected.",
        noTeacherSelected: "No teacher selected.",
        noStudentSelected: "No student selected.",
        close: "Close",
        addSlotTitle: "Add a slot",
        addSlotHelp: "A slot happens on a single local day. Capacity 0 is allowed for slots without students.",
        createFailed: "Could not create slot",
        createDone: "Slot created",
        fixForm: "Fix the form",
        mainInformation: "Main information",
        required: "Required",
        metricsSlots: "Visible slots",
        metricsStudents: "Students",
        metricsSeats: "Open seats",
        metricsFull: "Full",
        metricsMissingTeacher: "Missing teacher",
      }
    : {
        backendError: "Erreur backend :",
        schedule: "Planning",
        view: "Vue",
        edit: "Edition",
        addSlot: "Ajouter un creneau",
        settings: "Parametres",
        location: "Lieu",
        calendarView: "Vue agenda",
        timezone: "Fuseau horaire",
        reset: "Reinitialiser",
        advancedFilters: "Filtres avances",
        activities: "Activites",
        type: "Type",
        locations: "Lieux",
        teachers: "Professeurs",
        students: "Eleves",
        sessionStatus: "Statut cours",
        clientStatus: "Statut adherent",
        noAdvancedFilters: "Aucun filtre avance actif.",
        filtersTitle: "Filtres planning",
        filtersHelp: "Vous pouvez filtrer sur plusieurs activites, salles, professeurs et eleves.",
        courseType: "Type de cours",
        byActivities: "Par activites",
        byRooms: "Par salles",
        byTeachers: "Par professeurs",
        byStudents: "Par eleves",
        searchActivity: "Rechercher une activite...",
        searchRoom: "Rechercher une salle...",
        searchTeacher: "Rechercher un professeur...",
        searchStudent: "Rechercher un eleve...",
        noActivitySelected: "Aucune activite selectionnee.",
        noRoomSelected: "Aucune salle selectionnee.",
        noTeacherSelected: "Aucun professeur selectionne.",
        noStudentSelected: "Aucun eleve selectionne.",
        close: "Fermer",
        addSlotTitle: "Ajouter un creneau",
        addSlotHelp: "Un creneau est sur un seul jour local. Capacite 0 autorisee pour les creneaux sans eleve.",
        createFailed: "Creation impossible",
        createDone: "Creation terminee",
        fixForm: "Corriger la saisie",
        mainInformation: "Informations principales",
        required: "Obligatoire",
        metricsSlots: "Creneaux visibles",
        metricsStudents: "Eleves",
        metricsSeats: "Places restantes",
        metricsFull: "Complets",
        metricsMissingTeacher: "Professeur manquant",
      };

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">{planningText.backendError} {errors.join(" | ")}</section> : null}

      <section className="card planning-header-card">
        <div className="row spread planning-header-row">
          <div className="stack-xs">
            <h2>{planningText.schedule}</h2>
            <p className="muted planning-subtitle">{planningSubtitle}</p>
          </div>
          <div className="row planning-header-actions">
            <a className={`mode-link ${!createOpen ? "mode-active" : ""}`} href={lectureHref}>
              {planningText.view}
            </a>
            <a className={`mode-link ${createOpen ? "mode-active" : ""}`} href={createHref}>
              {planningText.edit}
            </a>
            <a className="icon-add-button" href={createHref}>
              <span className="icon-add-button-plus" aria-hidden="true">
                +
              </span>
              {planningText.addSlot}
            </a>
            {focusedLocationId ? (
              <Link className="mode-link" href={withUiLanguage(`/admin/plannings/${focusedLocationId}/settings`, language)}>
                {planningText.settings}
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card planning-filters-card">
        <form method="get" className="planning-quick-form">
          {language === "en" ? <input type="hidden" name="lang" value="en" /> : null}
          <input type="hidden" name="status" value={selectedStatus} />
          <input type="hidden" name="client_status" value={selectedClientStatus} />
          <input type="hidden" name="agenda_date" value={agendaDate} />
          {selectedActivityIds.map((activityId) => (
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
          <input type="hidden" name="timezone" value={timezone} />
          {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

          <label>
            {planningText.location}
            <AutoSubmitSelect
              name="location_id"
              defaultValue={focusedLocationId}
              options={[{ value: "", label: isEnglish ? "-- All locations --" : "-- Tous les lieux --" }, ...locations.map((row) => ({ value: row.id, label: row.name }))]}
            />
          </label>

          <label>
            {planningText.calendarView}
            <AutoSubmitSelect
              name="agenda_view"
              defaultValue={agendaView}
              options={[
                { value: "month", label: isEnglish ? "Month" : "Mois" },
                { value: "week", label: isEnglish ? "Week" : "Semaine" },
                { value: "day", label: isEnglish ? "Day" : "Jour" },
              ]}
            />
          </label>

          <label>
            {isEnglish ? "Course type" : "Type de cours"}
            <AutoSubmitSelect
              name="course_type_id"
              defaultValue={selectedCourseType}
              options={[{ value: "", label: isEnglish ? "-- All types --" : "-- Tous les types --" }, ...courseTypes.map((row) => ({ value: row.id, label: row.name }))]}
            />
          </label>

          <div className="row">
            <a className="planning-reset-link" href={filtersResetHref}>
              {planningText.reset}
            </a>
            <a className="mode-link planning-advanced-link" href={filtersHref}>
              {planningText.advancedFilters}
            </a>
          </div>
        </form>
        <div className="row planning-active-filters">
          {selectedActivityLabels.length > 0 ? (
            <span className="badge">{planningText.activities}: {compactList(selectedActivityLabels)}</span>
          ) : null}
          {selectedCourseType ? (
            <span className="badge">{planningText.type}: {courseTypeById.get(selectedCourseType)?.name ?? pickText(language, "Selection", "Selection")}</span>
          ) : null}
          {selectedLocationLabels.length > 0 ? (
            <span className="badge">{planningText.locations}: {compactList(selectedLocationLabels)}</span>
          ) : null}
          {selectedProfessorLabels.length > 0 ? (
            <span className="badge">{planningText.teachers}: {compactList(selectedProfessorLabels)}</span>
          ) : null}
          {selectedClientLabels.length > 0 ? (
            <span className="badge">{planningText.students}: {compactList(selectedClientLabels)}</span>
          ) : null}
          {selectedStatus !== "ALL" ? <span className="badge">{planningText.sessionStatus}: {selectedStatus}</span> : null}
          {selectedClientStatus !== "ALL" ? <span className="badge">{planningText.clientStatus}: {selectedClientStatus}</span> : null}
          {!hasAdvancedFilters ? (
            <span className="muted">{planningText.noAdvancedFilters}</span>
          ) : null}
        </div>
      </section>

      {filtersOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact planning-filters-modal">
            <a className="modal-close-x" href={filtersCloseHref} aria-label={planningText.close}>
              ×
            </a>
            <h2 className="modal-title">{planningText.filtersTitle}</h2>
            <p className="muted">{planningText.filtersHelp}</p>
            <form method="get" className="grid cols-2">
              {language === "en" ? <input type="hidden" name="lang" value="en" /> : null}
              <input type="hidden" name="location_id" value={focusedLocationId} />
              <input type="hidden" name="agenda_view" value={agendaView} />
              <input type="hidden" name="agenda_date" value={agendaDate} />
              <input type="hidden" name="timezone" value={timezone} />
              {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

              <label className="span-2">
                {planningText.courseType}
                <select name="course_type_id" defaultValue={selectedCourseType}>
                  <option value="">{isEnglish ? "All" : "Tous"}</option>
                  {courseTypes.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>

              <SearchMultiSelect
                className="span-2"
                label={planningText.byActivities}
                name="activity_ids"
                options={courseTypes.map((row) => ({ id: row.id, label: row.name }))}
                selectedIds={selectedActivityIds}
                placeholder={planningText.searchActivity}
                emptySelectionLabel={planningText.noActivitySelected}
              />

              <SearchMultiSelect
                label={planningText.byRooms}
                name="location_ids"
                options={locationFilterOptions}
                selectedIds={selectedLocationIdsFromQuery}
                placeholder={planningText.searchRoom}
                emptySelectionLabel={planningText.noRoomSelected}
              />

              <SearchMultiSelect
                label={planningText.byTeachers}
                name="professor_ids"
                options={professorFilterOptions}
                selectedIds={selectedProfessorIds}
                placeholder={planningText.searchTeacher}
                emptySelectionLabel={planningText.noTeacherSelected}
              />

              <SearchMultiSelect
                className="span-2"
                label={planningText.byStudents}
                name="client_ids"
                options={clientFilterOptions}
                selectedIds={selectedClientIds}
                placeholder={planningText.searchStudent}
                emptySelectionLabel={planningText.noStudentSelected}
              />

              <label>
                {planningText.sessionStatus}
                <select name="status" defaultValue={selectedStatus}>
                  <option value="ALL">{t("common.all")}</option>
                  <option value="SCHEDULED">{t("admin.planning.status.scheduled")}</option>
                  <option value="CANCELLED">{t("admin.planning.status.cancelled")}</option>
                  <option value="COMPLETED">{t("admin.planning.status.completed")}</option>
                </select>
              </label>

              <label>
                {planningText.clientStatus}
                <select name="client_status" defaultValue={selectedClientStatus}>
                  <option value="ALL">{t("common.all")}</option>
                  <option value="ACTIVE">{t("admin.clients.status_active")}</option>
                  <option value="RESPONSABLE">{t("admin.clients.status_responsable")}</option>
                  <option value="TRIAL">{t("admin.clients.status_trial")}</option>
                  <option value="PENDING">{t("admin.clients.status_pending")}</option>
                  <option value="INACTIVE">{t("admin.clients.status_inactive")}</option>
                  <option value="ARCHIVED">{t("admin.clients.status_archived")}</option>
                </select>
              </label>

              <div className="row span-2">
                <button type="submit">{t("common.apply")}</button>
                <a className="reset-link" href={filtersResetHref}>
                  {planningText.reset}
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{planningText.metricsSlots}</span>
            <strong>{planningStats.sessions}</strong>
          </article>
          <article>
            <span>{planningText.metricsStudents}</span>
            <strong>{planningStats.booked}</strong>
          </article>
          <article>
            <span>{planningText.metricsSeats}</span>
            <strong>{planningStats.openSeats}</strong>
          </article>
          <article className={planningStats.full > 0 ? "is-warning" : ""}>
            <span>{planningText.metricsFull}</span>
            <strong>{planningStats.full}</strong>
          </article>
          <article className={planningStats.missingTeacher > 0 ? "is-warning" : ""}>
            <span>{planningText.metricsMissingTeacher}</span>
            <strong>{planningStats.missingTeacher}</strong>
          </article>
        </div>
      </section>

      {createOpen && !filtersOpen && !selectedDayDetails && !selectedSession ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-create-session">
            <a className="modal-close-x" href={createCloseHref} aria-label={planningText.close}>
              ×
            </a>
            <h2 className="modal-title">{planningText.addSlotTitle}</h2>
            <p className="muted">{planningText.addSlotHelp}</p>
            {(okMessage || errorMessage) ? (
              <section className="modal-overlay modal-overlay-front">
                <article className="modal-panel modal-compact">
                  <a
                    className="modal-close-x"
                    href={errorMessage ? createFeedbackDismissHref : createCloseHref}
                    aria-label={planningText.close}
                  >
                    ×
                  </a>
                  <h3 className="modal-title">
                    {errorMessage ? planningText.createFailed : planningText.createDone}
                  </h3>
                  {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
                  {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
                  <div className="row modal-actions-end">
                    {errorMessage ? (
                      <a className="ghost" href={createFeedbackDismissHref}>
                        {planningText.fixForm}
                      </a>
                    ) : null}
                    <a className="mode-link" href={createCloseHref}>
                      {planningText.close}
                    </a>
                  </div>
                </article>
              </section>
            ) : null}
            <form action={createAdminSessionAction} className="create-session-form" noValidate>
              <input type="hidden" name="return_to" value={createHref} />
              <section className="create-session-section">
                <div className="row spread">
                  <h3 className="create-session-section-title">{planningText.mainInformation}</h3>
                  <span className="badge">{planningText.required}</span>
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
                  recurrenceDefaults={{
                    mode: createRecurrenceMode,
                    frequency: createRecurrenceFrequency,
                    interval: createRecurrenceInterval,
                    untilDate: createDraft?.recurrence_until_date || "",
                    keepLocalTime: createRecurrenceTimeBasis === "LOCAL",
                  }}
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

              <section className="create-session-section">
                <h3 className="create-session-section-title">{language === "en" ? "Visibility and descriptions" : "Visibilite et descriptions"}</h3>
                <div className="grid cols-2 create-session-visibility-grid">
                  <SessionVisibilityFields
                    language={language}
                    initialVisibilityScopes={createInitialVisibilityScopes}
                    initialBookingScopes={createInitialBookingScopes}
                    allowsStudentBookings={createAllowsStudentBookings}
                  />

                  <label>
                    {language === "en" ? "External booking price incl. VAT" : "Tarif reservation externe TTC"}
                    <input
                      type="text"
                      name="external_booking_price_ttc"
                      inputMode="decimal"
                      defaultValue={createDraft?.external_booking_price_ttc || ""}
                      placeholder="ex. 35,00"
                    />
                    <small className="muted">
                      {language === "en"
                        ? "Leave empty to keep this slot hidden from the external integration."
                        : "Laissez vide pour ne pas exposer ce creneau a l integration externe."}
                    </small>
                  </label>

                  <label>
                    {language === "en" ? "Public description (client view)" : "Description publique (vue client)"}
                    <textarea name="public_description" rows={4} defaultValue={createDraft?.public_description || ""} />
                  </label>

                  <label>
                    {language === "en" ? "Private description (internal)" : "Description privee (interne)"}
                    <textarea name="private_description" rows={4} defaultValue={createDraft?.private_description || ""} />
                  </label>

                  <label className="span-2">
                    {language === "en" ? "Note for the teacher (sent 24h before)" : "Note pour le professeur (envoyee 24h avant)"}
                    <RichMessageEditor
                      name="professor_reminder_note"
                      formatName="professor_reminder_note_format"
                      rows={6}
                      maxLength={12000}
                      defaultFormat="HTML"
                      defaultValue={createDraft?.professor_reminder_note || ""}
                      placeholder={
                        language === "en"
                          ? "Enter the note to include in the teacher reminder..."
                          : "Saisir la note a joindre au rappel professeur..."
                      }
                    />
                  </label>
                </div>
              </section>

              <div className="row spread create-session-actions">
                <p className="muted">
                  {language === "en" ? "Required fields are marked at the top of the form." : "Les champs obligatoires sont marques en haut du formulaire."}
                </p>
                <div className="row">
                  <a className="reset-link" href={createCloseHref}>
                    {language === "en" ? "Cancel" : "Annuler"}
                  </a>
                  <SessionCreateSubmitButton language={language} />
                </div>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread">
          <h2>{isEnglish ? "Calendar" : "Agenda"}</h2>
          <div className="row planning-agenda-nav">
            <a className="mode-link" href={previousHref}>
              ←
            </a>
            <details className="planning-jump-menu">
              <summary className="badge planning-jump-trigger">{agendaRange.title}</summary>
              <form method="get" className="planning-jump-form">
                <input type="hidden" name="agenda_view" value={agendaView} />
                <input type="hidden" name="timezone" value={timezone} />
                {focusedLocationId ? <input type="hidden" name="location_id" value={focusedLocationId} /> : null}
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
                {selectedCourseType ? <input type="hidden" name="course_type_id" value={selectedCourseType} /> : null}
                {selectedStatus !== "ALL" ? <input type="hidden" name="status" value={selectedStatus} /> : null}
                {selectedClientStatus !== "ALL" ? <input type="hidden" name="client_status" value={selectedClientStatus} /> : null}
                {filtersOpen ? <input type="hidden" name="filters" value="1" /> : null}
                <label className="planning-jump-field">
                  <span>{isEnglish ? "Display date" : "Date d affichage"}</span>
                  <input type="date" name="agenda_date" defaultValue={agendaDate} />
                </label>
                <div className="row planning-jump-actions">
                  <button type="submit" className="mode-link planning-advanced-link">
                    {isEnglish ? "Go" : "Aller"}
                  </button>
                </div>
              </form>
            </details>
            <a className="mode-link" href={nextHref}>
              →
            </a>
            <a className="mode-link" href={todayHref}>
              {isEnglish ? "Today" : "Aujourd'hui"}
            </a>
          </div>
        </div>
        <p className="muted">{agendaNavigationHint(agendaView, language)}</p>

        <div className={`agenda-grid agenda-grid-${agendaView}`}>
          {agendaDayCards.map((day) => (
            <MonthDayCard
              key={day.key}
              dayLabel={day.label}
              events={day.events}
              isToday={day.key === todayAgendaKey}
              language={language}
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
        dayLabel={selectedDayDetails ? agendaDayLongLabel(selectedDayDetails.key, language) : ""}
        events={selectedDayDetails ? selectedDayDetails.events : []}
        language={language}
        closeHref={dayDetailsCloseHref}
        openSessionHref={(sessionId) => withSessionInHref(sessionModalBaseHref, sessionId)}
      />

      {selectedSession && !editSessionOpen ? (
        <ModalA11yFrame className="modal-overlay session-slot-overlay" closeHref={baseHref} label={isEnglish ? "Slot details" : "Detail du creneau"}>
          <article className="modal-panel session-slot-modal">
            <header className="session-slot-header">
              <div className="session-slot-header-main">
                <h2 className="modal-title session-slot-title">{selectedSessionHeaderTitle}</h2>
                <p className="muted session-slot-subtitle">{selectedSessionSubtitle}</p>
              </div>
              <div className="session-slot-header-actions">
                <span className={`status-badge ${statusClass(selectedSession.status)}`}>{selectedSession.status_label}</span>
                <details className="session-slot-overflow-menu">
                  <summary aria-label={isEnglish ? "More options" : "Plus d options"}>⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <p className="muted">{isEnglish ? "Actions" : "Actions"}</p>
                    <a className="mode-link" href={attendanceModalHref}>
                      {isEnglish ? "Take attendance" : "Prendre les presences"}
                    </a>
                    <a className="mode-link" href={groupNotesModalHref}>
                      {isEnglish ? "Group note" : "Note de groupe"}
                    </a>
                    <a className="mode-link" href={sessionEmailModalHref}>
                      {isEnglish ? "Send email" : "Envoyer email"}
                    </a>
                    <a className="mode-link" href={sessionSmsModalHref}>
                      {isEnglish ? "Send SMS" : "Envoyer SMS"}
                    </a>
                    <a className="mode-link" href={duplicateModalHref}>
                      {isEnglish ? "Duplicate" : "Dupliquer"}
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      {isEnglish ? "Delete slot" : "Supprimer le creneau"}
                    </a>
                    <hr />
                    <p className="muted">{isEnglish ? "Details" : "Infos"}</p>
                    <span className="badge">{isEnglish ? "Teacher" : "Professeur"}: {selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")}</span>
                    {selectedSessionIsSubstituted ? <span className="badge">{isEnglish ? "Substitute" : "Remplacant"}</span> : null}
                    <span className="badge">{isEnglish ? "Visibility" : "Affichage"}: {sessionAudienceScopesLabel(selectedVisibilityScopes, language)}</span>
                    <span className="badge">
                      {isEnglish ? "Booking" : "Reservation"}: {selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : pickText(language, "Fermee", "Closed")}
                    </span>
                    {!selectedSessionAllowsStudentBookings ? <span className="badge">{isEnglish ? "No students" : "Sans eleve"}</span> : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={baseHref} aria-label={isEnglish ? "Close" : "Fermer"}>
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
              <span className="badge">{recurrenceLabel(selectedSession)}</span>
              <span className="badge">{isEnglish ? "Visibility" : "Affichage"} {sessionAudienceScopesLabel(selectedVisibilityScopes, language)}</span>
              <span className="badge">
                {isEnglish ? "Booking" : "Reservation"} {selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : pickText(language, "Fermee", "Closed")}
              </span>
              {!selectedSessionAllowsStudentBookings ? <span className="badge">{isEnglish ? "No students" : "Sans eleve"}</span> : null}
            </div>

            <div className="session-slot-toolbar">
              <a className="mode-link" href={editSessionHref}>
                {isEnglish ? "Edit" : "Modifier"}
              </a>
              {selectedSession.status !== "CANCELLED" ? (
                <a className="danger-link" href={cancelConfirmHref}>
                  {isEnglish ? "Cancel" : "Annuler"}
                </a>
              ) : null}
              <details className="session-slot-overflow-menu session-slot-toolbar-menu">
                <summary aria-label={isEnglish ? "More actions" : "Plus d actions"}>⋯</summary>
                <div className="session-slot-overflow-panel">
                  <a className="mode-link" href={attendanceModalHref}>
                    {isEnglish ? "Take attendance" : "Prendre les presences"}
                  </a>
                  <a className="mode-link" href={groupNotesModalHref}>
                    {isEnglish ? "Group note" : "Note de groupe"}
                  </a>
                  <a className="mode-link" href={sessionEmailModalHref}>
                    {isEnglish ? "Send email" : "Envoyer email"}
                  </a>
                  <a className="mode-link" href={sessionSmsModalHref}>
                    {isEnglish ? "Send SMS" : "Envoyer SMS"}
                  </a>
                  <a className="mode-link" href={duplicateModalHref}>
                    {isEnglish ? "Duplicate" : "Dupliquer"}
                  </a>
                  <a className="danger-link" href={deleteConfirmHref}>
                    {isEnglish ? "Delete" : "Supprimer"}
                  </a>
                </div>
              </details>
            </div>

            <div className="session-slot-overview-grid">
              <section className="session-slot-overview-card session-slot-overview-card-highlight">
                <span className="session-slot-overview-label">{isEnglish ? "Schedule" : "Horaire"}</span>
                <strong>{sessionTimeRangeLabel(selectedSession, language)}</strong>
                <small>
                  {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {selectedSession.timezone} · {selectedSessionDurationLabel}
                </small>
              </section>

              <section className="session-slot-overview-card">
                <span className="session-slot-overview-label">{isEnglish ? "Teacher" : "Professeur"}</span>
                <strong>{selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")}</strong>
                <small>
                  {isEnglish ? "Usual" : "Habituel"}: {selectedHabitualProfessorLabel}
                  {selectedSessionIsSubstituted ? ` · ${isEnglish ? "Substitute" : "Remplacant"}: ${selectedSubstituteProfessorLabel}` : ""}
                </small>
              </section>

              <section className="session-slot-overview-card">
                <span className="session-slot-overview-label">{isEnglish ? "Recurrence" : "Recurrence"}</span>
                <strong>{selectedSessionRecurrenceLabel}</strong>
                <small>
                  {selectedSession.recurrence_group_id
                    ? selectedSessionRecurrenceEndLabel
                      ? pickText(language, `Serie active jusqu au ${selectedSessionRecurrenceEndLabel}`, `Recurring series until ${selectedSessionRecurrenceEndLabel}`)
                      : pickText(language, "Serie active", "Recurring series")
                    : pickText(language, "Creneau ponctuel", "Single slot")}
                </small>
              </section>

              <section className="session-slot-overview-card">
                <span className="session-slot-overview-label">{isEnglish ? "Publication" : "Publication"}</span>
                <strong>{sessionAudienceScopesLabel(selectedVisibilityScopes, language)}</strong>
                <small>{selectedSessionPublicationSummary}</small>
              </section>

              <section className="session-slot-overview-card">
                <span className="session-slot-overview-label">{isEnglish ? "Attendees" : "Inscrits"}</span>
                <strong>{selectedSessionCapacityLabel}</strong>
                <small>{selectedSessionEnrollmentSummary}</small>
              </section>
            </div>

            <div className="session-slot-body">
              <details className="session-slot-section session-slot-section-attendees" open>
                <summary>{isEnglish ? "Attendees" : "Inscrits"} ({selectedSessionBookings.length})</summary>
                <div className="session-slot-section-body">
                  {selectedSessionBookings.length === 0 ? (
                    <p className="muted session-slot-empty-state">{isEnglish ? "No student booked." : "Aucun eleve inscrit."}</p>
                  ) : (
                    <div className="session-bookings-summary-list session-slot-attendees-list">
                      {selectedSessionBookings.map((booking, index) => {
                        const presence = bookingPresenceLabel(booking.status, language);
                        const enrollment = bookingEnrollmentLabel(booking.status, language);
                        const studentTime = bookingStudentTimeRangeLabel(booking, selectedSession, language);
                        return (
                          <article key={booking.id} className="session-slot-attendee-row">
                            <div className="session-slot-attendee-identity">
                              {booking.client_id ? (
                                <Link
                                  className="client-name-link"
                                  href={`/admin/clients/${booking.client_id}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={isEnglish ? "Open client record in a new tab" : "Ouvrir la fiche client dans un nouvel onglet"}
                                >
                                  {booking.client_display_name || `Participant ${index + 1}`}
                                </Link>
                              ) : (
                                <strong>{booking.client_display_name || `Participant ${index + 1}`}</strong>
                              )}
                              <small className="muted">{booking.client_email}</small>
                              {studentTime ? (
                                <small className="muted">{isEnglish ? "Student time" : "Horaire eleve"}: {studentTime}</small>
                              ) : null}
                            </div>
                            <div className="session-slot-attendee-badges">
                              <span className={`status-pill ${statusClass(booking.status)}`}>
                                {enrollment}
                                {booking.waitlist_position ? ` #${booking.waitlist_position}` : ""}
                              </span>
                              <span className={`status-pill ${presence ? "status-ok" : "status-off"}`}>{presence ?? pickText(language, "Presence: -", "Attendance: -")}</span>
                            </div>
                            <div className="session-slot-attendee-actions">
                              <a className="mode-link" href={attendanceBookingHref(booking.id)}>
                                {isEnglish ? "Attendance & note" : "Presence & note"}
                              </a>
                              {isBookingRemovable(selectedSession, booking) ? (
                                <details className="session-slot-inline-confirm">
                                  <summary className="session-slot-delete-icon" aria-label={isEnglish ? "Remove this attendee" : "Retirer cet inscrit"} title={isEnglish ? "Remove this attendee" : "Retirer cet inscrit"}>
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
                                          {isEnglish ? "This session" : "Cette seance"}
                                        </label>
                                        <label className="checkline">
                                          <input type="radio" name="scope" value="SERIES_FUTURE" />
                                          {isEnglish ? "Future series" : "Serie future"}
                                        </label>
                                      </fieldset>
                                    ) : (
                                      <input type="hidden" name="scope" value="OCCURRENCE" />
                                    )}
                                    <button className="danger" type="submit">
                                      {isEnglish ? "Confirm" : "Confirmer"}
                                    </button>
                                  </form>
                                </details>
                              ) : (
                                <span className="muted">{isEnglish ? "Locked" : "Verrouille"}</span>
                              )}
                            </div>
                            {selectedSessionSupportsStudentTimeOverrides ? (
                              <div className="session-slot-staggered-time-panel">
                                <div className="session-slot-staggered-time-head">
                                  <strong>{isEnglish ? "Student schedule" : "Horaire individuel"}</strong>
                                  <span className="muted">
                                    {studentTime
                                      ? studentTime
                                      : pickText(language, "Creneau professeur complet", "Full teacher slot")}
                                  </span>
                                </div>
                                {selectedSessionStudentTimePresets.length > 0 ? (
                                  <div className="session-slot-staggered-presets" aria-label={isEnglish ? "Suggested schedules" : "Horaires proposes"}>
                                    {selectedSessionStudentTimePresets.map((preset) => (
                                      <form key={`${booking.id}-${preset.start}-${preset.end}`} action={adminUpdateSessionBookingStudentTimeAction}>
                                        <input type="hidden" name="session_id" value={selectedSession.id} />
                                        <input type="hidden" name="booking_id" value={booking.id} />
                                        <input type="hidden" name="return_to" value={modalHref} />
                                        <input type="hidden" name="student_start_time_local" value={preset.start} />
                                        <input type="hidden" name="student_end_time_local" value={preset.end} />
                                        <button
                                          type="submit"
                                          className={studentTime === preset.label ? "ghost active" : "ghost"}
                                          aria-pressed={studentTime === preset.label}
                                        >
                                          {preset.label}
                                        </button>
                                      </form>
                                    ))}
                                    <form action={adminUpdateSessionBookingStudentTimeAction}>
                                      <input type="hidden" name="session_id" value={selectedSession.id} />
                                      <input type="hidden" name="booking_id" value={booking.id} />
                                      <input type="hidden" name="return_to" value={modalHref} />
                                      <input type="hidden" name="student_start_time_local" value="" />
                                      <input type="hidden" name="student_end_time_local" value="" />
                                      <button type="submit" className={!studentTime ? "ghost active" : "ghost"} aria-pressed={!studentTime}>
                                        {isEnglish ? "Full slot" : "Creneau complet"}
                                      </button>
                                    </form>
                                  </div>
                                ) : null}
                                <form action={adminUpdateSessionBookingStudentTimeAction} className="session-slot-staggered-manual-form">
                                  <input type="hidden" name="session_id" value={selectedSession.id} />
                                  <input type="hidden" name="booking_id" value={booking.id} />
                                  <input type="hidden" name="return_to" value={modalHref} />
                                  <label>
                                    {isEnglish ? "Start" : "Debut"}
                                    <input
                                      type="time"
                                      name="student_start_time_local"
                                      defaultValue={
                                        booking.student_start_at_utc ? toTimeInputInTimezone(booking.student_start_at_utc, selectedSession.timezone) : ""
                                      }
                                      min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                      max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                                    />
                                  </label>
                                  <label>
                                    {isEnglish ? "End" : "Fin"}
                                    <input
                                      type="time"
                                      name="student_end_time_local"
                                      defaultValue={
                                        booking.student_end_at_utc ? toTimeInputInTimezone(booking.student_end_at_utc, selectedSession.timezone) : ""
                                      }
                                      min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                      max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                                    />
                                  </label>
                                  <button type="submit" className="ghost">
                                    {isEnglish ? "Save" : "Enregistrer"}
                                  </button>
                                </form>
                              </div>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  )}
                </div>
              </details>

              <aside className="session-slot-right">
                <details className="session-slot-section session-slot-section-details" open>
                  <summary>{isEnglish ? "Details" : "Details"}</summary>
                  <div className="session-slot-section-body session-slot-details-list">
                    <div className="session-slot-fact-list">
                      <div className="session-slot-fact-row">
                        <span className="session-slot-fact-label">{isEnglish ? "Activity" : "Activite"}</span>
                        <span className="session-slot-fact-value">{selectedCourseTypeName}</span>
                      </div>
                      <div className="session-slot-fact-row">
                        <span className="session-slot-fact-label">{isEnglish ? "Location" : "Lieu"}</span>
                        <span className="session-slot-fact-value">{selectedLocationName}</span>
                      </div>
                      <div className="session-slot-fact-row">
                        <span className="session-slot-fact-label">{isEnglish ? "Usual teacher" : "Professeur habituel"}</span>
                        <span className="session-slot-fact-value">{selectedHabitualProfessorLabel}</span>
                      </div>
                      <div className="session-slot-fact-row">
                        <span className="session-slot-fact-label">{isEnglish ? "Substitute" : "Remplacant"}</span>
                        <span className="session-slot-fact-value">{selectedSubstituteProfessorLabel}</span>
                      </div>
                      <div className="session-slot-fact-row">
                        <span className="session-slot-fact-label">{isEnglish ? "Effective teacher" : "Professeur effectif"}</span>
                        <span className="session-slot-fact-value">{selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")}</span>
                      </div>
                      {selectedSession.recurrence_group_id && selectedSessionRecurrenceEndLabel ? (
                        <div className="session-slot-fact-row">
                          <span className="session-slot-fact-label">{isEnglish ? "Series end" : "Fin de serie"}</span>
                          <span className="session-slot-fact-value">{selectedSessionRecurrenceEndLabel}</span>
                        </div>
                      ) : null}
                      {selectedSessionZoomLink ? (
                        <div className="session-slot-fact-row">
                          <span className="session-slot-fact-label">Zoom</span>
                          <span className="session-slot-fact-value">
                            <a href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                              {isEnglish ? "Open link" : "Ouvrir le lien"}
                            </a>
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </details>

                {selectedSessionHasNotesSection ? (
                  <details className="session-slot-section session-slot-section-notes">
                    <summary>{isEnglish ? "Notes & messages" : "Notes & messages"}</summary>
                    <div className="session-slot-section-body session-slot-details-list">
                      {selectedSession.group_note ? (
                        <section className="session-slot-note-block">
                          <span className="session-slot-fact-label">{isEnglish ? "Group note" : "Note de groupe"}</span>
                          <p>{stripHtml(selectedSession.group_note)}</p>
                        </section>
                      ) : null}
                      {selectedSession.public_description ? (
                        <section className="session-slot-note-block">
                          <span className="session-slot-fact-label">{isEnglish ? "Public description" : "Description publique"}</span>
                          <p>{selectedSession.public_description}</p>
                        </section>
                      ) : null}
                      {selectedSession.private_description ? (
                        <section className="session-slot-note-block">
                          <span className="session-slot-fact-label">{isEnglish ? "Private description" : "Description privee"}</span>
                          <p>{selectedSession.private_description}</p>
                        </section>
                      ) : null}
                      {selectedSession.professor_reminder_note ? (
                        <section className="session-slot-note-block">
                          <span className="session-slot-fact-label">{isEnglish ? "Teacher note (24h reminder)" : "Note professeur (rappel 24h)"}</span>
                          <p>{stripHtml(selectedSession.professor_reminder_note)}</p>
                        </section>
                      ) : null}
                    </div>
                  </details>
                ) : null}

                <details className="session-slot-section session-slot-section-enroll">
                  <summary>{selectedSessionAllowsStudentBookings ? (isEnglish ? "Add a student" : "Inscrire un eleve") : (isEnglish ? "Student bookings" : "Inscriptions eleves")}</summary>
                  <div className="session-slot-section-body">
                    {!selectedSessionAllowsStudentBookings ? (
                      <p className="muted">
                        {isEnglish
                          ? "This slot is marked as no-student. No booking is possible from the schedule or from the client portal."
                          : "Ce creneau est marque sans eleve. Aucune inscription n est possible depuis le planning ni depuis l espace client."}
                      </p>
                    ) : (
                      <form action={adminAddClientToSessionAction} className="session-enroll-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="return_to" value={modalHref} />

                        <SearchMultiSelect
                          className="session-enroll-search"
                          label={isEnglish ? "Student" : "Eleve"}
                          name="client_id"
                          options={bookingClientOptions}
                          selectedIds={[]}
                          placeholder={isEnglish ? "Search a student..." : "Rechercher un eleve..."}
                          emptySelectionLabel={isEnglish ? "No student selected." : "Aucun eleve selectionne."}
                          maxSelections={1}
                          requiredSelection
                        />

                        {selectedSessionSupportsStudentTimeOverrides ? (
                          <div className="grid cols-2 config-form-grid">
                            <label>
                              {isEnglish ? "Student start" : "Debut eleve"}
                              <input
                                type="time"
                                name="student_start_time_local"
                                min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                              />
                            </label>
                            <label>
                              {isEnglish ? "Student end" : "Fin eleve"}
                              <input
                                type="time"
                                name="student_end_time_local"
                                min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                              />
                            </label>
                            <small className="muted span-2">
                              {isEnglish
                                ? "Optional. Keep empty to use the full teacher slot."
                                : "Optionnel. Laisser vide pour utiliser tout le creneau professeur."}
                            </small>
                          </div>
                        ) : null}

                        <div className="session-enroll-submit">
                          {selectedSession.recurrence_group_id ? (
                            <details className="session-slot-add-confirm">
                              <summary>{isEnglish ? "Add" : "Ajouter"}</summary>
                              <div className="session-slot-inline-confirm-panel session-slot-scope-panel">
                                <p className="muted">{isEnglish ? "Book the student on this session or on the future series?" : "Inscrire l eleve sur cette seance ou sur la serie future ?"}</p>
                                <label className="checkline">
                                  <input type="radio" name="scope" value="OCCURRENCE" defaultChecked />
                                  {isEnglish ? "This session only" : "Cette seance uniquement"}
                                </label>
                                <label className="checkline">
                                  <input type="radio" name="scope" value="SERIES_FUTURE" />
                                  {isEnglish ? "Whole series (future sessions)" : "Toute la serie (futures)"}
                                </label>
                                <button type="submit">{isEnglish ? "Confirm" : "Confirmer"}</button>
                              </div>
                            </details>
                          ) : (
                            <>
                              <input type="hidden" name="scope" value="OCCURRENCE" />
                              <button type="submit">{isEnglish ? "Add" : "Ajouter"}</button>
                            </>
                          )}
                        </div>
                      </form>
                    )}
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
                <h2 className="modal-title">{isEnglish ? "Edit slot" : "Modifier le creneau"}</h2>
                <p className="muted">
                  {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {selectedLocationName} · {isEnglish ? "Saved time" : "Horaire enregistre"}: {sessionTimeRangeLabel(selectedSession, language)}
                </p>
              </div>
              <div className="session-edit-shell-header-actions">
                <details className="session-slot-overflow-menu">
                  <summary aria-label={isEnglish ? "Secondary actions" : "Actions secondaires"}>⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <a className="mode-link" href={duplicateModalHref}>
                      {isEnglish ? "Duplicate slot" : "Dupliquer le creneau"}
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      {isEnglish ? "Delete slot" : "Supprimer le creneau"}
                    </a>
                    {selectedSessionZoomLink ? (
                      <a className="mode-link" href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                        {isEnglish ? "Copy Zoom link" : "Copier lien Zoom"}
                      </a>
                    ) : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
                  ×
                </a>
              </div>
            </header>

            {okMessage ? <section className="flash-ok modal-flash">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err modal-flash">{errorMessage}</section> : null}

            <SessionEditModalBridge initialActiveTab={editTab} tabReturnHrefs={editTabReturnHrefs}>
              <form action={updateAdminSessionAction} className="session-edit-shell-form" noValidate>
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={activeEditTabHref} data-session-edit-return-to />
                <input type="hidden" name="has_recurrence_group" value={selectedSession.recurrence_group_id ? "1" : "0"} />

                <nav className="session-edit-tabs" aria-label={isEnglish ? "Edit slot sections" : "Sections modification creneau"}>
                  <a
                    className={`session-edit-tab ${editTab === "general" ? "active" : ""}`}
                    href={editTabReturnHrefs.general}
                    data-session-edit-tab="general"
                    aria-current={editTab === "general" ? "page" : undefined}
                  >
                    <span>{isEnglish ? "General" : "General"}</span>
                    <small>{selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")} · {selectedSession.capacity_max} {isEnglish ? "seats" : "places"}</small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "schedule" ? "active" : ""}`}
                    href={editTabReturnHrefs.schedule}
                    data-session-edit-tab="schedule"
                    aria-current={editTab === "schedule" ? "page" : undefined}
                  >
                    <span>{isEnglish ? "Schedule & recurrence" : "Horaire & recurrence"}</span>
                    <small>{isEnglish ? "Saved" : "Enregistre"}: {sessionTimeRangeLabel(selectedSession, language)}</small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "visibility" ? "active" : ""}`}
                    href={editTabReturnHrefs.visibility}
                    data-session-edit-tab="visibility"
                    aria-current={editTab === "visibility" ? "page" : undefined}
                  >
                    <span>{isEnglish ? "Visibility" : "Visibilite"}</span>
                    <small>
                      {sessionAudienceScopesLabel(selectedVisibilityScopes, language)} ·{" "}
                      {selectedSessionAllowsStudentBookings ? sessionAudienceScopesLabel(selectedBookingScopes, language) : pickText(language, "Fermee", "Closed")}
                    </small>
                  </a>
                  <a
                    className={`session-edit-tab ${editTab === "notes" ? "active" : ""}`}
                    href={editTabReturnHrefs.notes}
                    data-session-edit-tab="notes"
                    aria-current={editTab === "notes" ? "page" : undefined}
                  >
                    <span>{isEnglish ? "Notes & messages" : "Notes & messages"}</span>
                    <small>{selectedSession.professor_reminder_note ? pickText(language, "Renseignee", "Filled in") : pickText(language, "Vide", "Empty")}</small>
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
                      {isEnglish ? "Title" : "Titre"}
                      <input type="text" name="title" defaultValue={selectedSession.title} required />
                    </label>

                    <label>
                      {isEnglish ? "Course type" : "Type de cours"}
                      <select name="course_type_id" defaultValue={selectedSession.course_type_id} required>
                        {courseTypes.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {isEnglish ? "Location" : "Lieu"}
                      <select name="location_id" defaultValue={selectedSession.location_id} required>
                        {locations.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {isEnglish ? "Teacher" : "Coach"}
                      <select name="professor_id" defaultValue={selectedSession.professor_id ?? ""}>
                        <option value="">{isEnglish ? "No teacher" : "Sans professeur"}</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                      {!selectedSessionRequiresProfessor ? (
                        <small className="muted">{isEnglish ? "Teacher is optional for this slot type." : "Le professeur est optionnel pour ce type de creneau."}</small>
                      ) : null}
                    </label>

                    <label>
                      {isEnglish ? "Substitute teacher (occurrence)" : "Professeur remplacant (occurrence)"}
                      <select name="substitute_teacher_id" defaultValue={selectedSession.substitute_teacher_id ?? ""}>
                        <option value="">{isEnglish ? "No substitute" : "Aucun remplacant"}</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      {isEnglish ? "Max capacity" : "Capacite max"}
                      <input type="number" name="capacity_max" min={0} defaultValue={selectedSession.capacity_max} />
                      {!selectedSessionAllowsStudentBookings ? (
                        <small className="muted">{isEnglish ? "Leave 0 for a no-student slot." : "Laissez 0 pour un creneau sans eleve."}</small>
                      ) : null}
                    </label>

                    <label>
                      {isEnglish ? "Status" : "Statut"}
                      <select name="status" defaultValue={selectedSession.status}>
                        <option value="SCHEDULED">{isEnglish ? "Scheduled" : "Planifie"}</option>
                        <option value="COMPLETED">{isEnglish ? "Completed" : "Termine"}</option>
                        <option value="CANCELLED">{isEnglish ? "Cancelled" : "Annule"}</option>
                      </select>
                    </label>

                    <label className="session-edit-span">
                      {isEnglish ? "Zoom link" : "Lien Zoom"}
                      <input type="url" name="zoom_link" defaultValue={selectedSession.zoom_link ?? ""} />
                    </label>

                    <label className="session-edit-span">
                      {isEnglish ? "Substitute note (optional)" : "Note remplaçant (optionnel)"}
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
                      {isEnglish ? "Start date" : "Jour debut"}
                      <input
                        type="date"
                        name="start_date"
                        defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                        required
                      />
                    </label>

                    <label>
                      {isEnglish ? "Edit scope" : "Portee modification"}
                      <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                        <option value="ONE">{isEnglish ? "This occurrence" : "Cette occurrence"}</option>
                        {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{isEnglish ? "Future series" : "Serie future"}</option> : null}
                        {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{isEnglish ? "Whole series" : "Toute la serie"}</option> : null}
                      </select>
                    </label>

                    <label className="checkline session-edit-span">
                      <input type="checkbox" name="is_all_day" defaultChecked={selectedSession.is_all_day} />
                      {isEnglish ? "All-day slot" : "Creneau sur toute la journee"}
                    </label>

                    <details className="session-edit-collapsible session-edit-span">
                      <summary>{isEnglish ? "Advanced options" : "Options avancees"}</summary>
                      <label>
                        {isEnglish ? "Session timezone" : "Fuseau horaire du creneau"}
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
                      language={language}
                      labelClassName="session-time-field"
                      defaultStartTime={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                      defaultEndTime={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                      defaultDurationMinutes={sessionDurationMinutes(selectedSession)}
                      requiredStart
                    />
                    <p className="muted session-edit-span">
                      {isEnglish
                        ? "The header shows the saved time. The fields above show your in-progress changes before saving."
                        : "L'entete affiche l'horaire enregistre. Les champs ci-dessus montrent vos modifications en cours avant enregistrement."}
                    </p>
                  </div>

                  <fieldset className="session-edit-span recurrence-panel">
                    <legend>{isEnglish ? "Recurrence" : "Recurrence"}</legend>
                    <div className="recurrence-mode-row">
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="NONE" defaultChecked />
                        {isEnglish ? "Do not change recurrence" : "Ne pas modifier la recurrence"}
                      </label>
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="RECURRING" />
                        {isEnglish ? "Edit recurrence" : "Modifier la recurrence"}
                      </label>
                    </div>
                    <div className="recurrence-settings">
                      <div className="grid cols-3 recurrence-grid">
                        <label>
                          {isEnglish ? "Frequency" : "Frequence"}
                          <select name="recurrence_frequency" defaultValue={editRecurrenceDefaults.frequency}>
                            <option value="DAILY">{isEnglish ? "Daily" : "Journaliere"}</option>
                            <option value="WEEKLY">{isEnglish ? "Weekly" : "Hebdomadaire"}</option>
                            <option value="MONTHLY">{isEnglish ? "Monthly" : "Mensuelle"}</option>
                          </select>
                        </label>
                        <label>
                          {isEnglish ? "Repeats every" : "Se repete chaque"}
                          <input type="number" name="recurrence_interval" min={1} defaultValue={editRecurrenceDefaults.interval} />
                          <small className="muted">{isEnglish ? "Example: 2 for every 2 weeks." : "Ex: 2 pour toutes les 2 semaines."}</small>
                        </label>
                        <label>
                          {isEnglish ? "Repeat until" : "Repeter jusqu au"}
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
                        {isEnglish ? "Keep local time" : "Heure locale fixe"}
                      </label>
                      <p className="muted">
                        {isEnglish
                          ? "When this option is enabled, a 6 PM lesson stays at 6 PM in local time even after daylight saving changes."
                          : "Quand cette option est activee, un cours a 18h reste a 18h en heure locale meme apres un changement d'heure."}
                      </p>
                      {selectedSession.recurrence_group_id ? (
                        <p className="muted">
                          {isEnglish
                            ? <>Existing series: to change recurrence, choose scope <strong>Future series</strong> or <strong>Whole series</strong>.</>
                            : <>Serie existante: pour changer la recurrence, choisir la portee <strong>Serie future</strong> ou <strong>Toute la serie</strong>.</>}
                        </p>
                      ) : (
                        <p className="muted">{isEnglish ? "Enable recurrence editing to convert this one-time slot." : "Activez la modification recurrence pour convertir ce creneau ponctuel."}</p>
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
                    />

                    <label>
                      {language === "en" ? "External booking price incl. VAT" : "Tarif reservation externe TTC"}
                      <input
                        type="text"
                        name="external_booking_price_ttc"
                        inputMode="decimal"
                        defaultValue={selectedSession.external_booking_price_ttc ?? ""}
                        placeholder="ex. 35,00"
                      />
                      <small className="muted">
                        {language === "en"
                          ? "Leave empty to remove this slot from the external iframe."
                          : "Laissez vide pour retirer ce creneau de l iframe externe."}
                      </small>
                    </label>
                  </div>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.public_description)}>
                    <summary>{language === "en" ? "Public description (optional)" : "Description publique (optionnel)"}</summary>
                    <label>
                      {language === "en" ? "Public description (client view)" : "Description publique (vue client)"}
                      <textarea name="public_description" rows={4} defaultValue={selectedSession.public_description ?? ""} />
                    </label>
                  </details>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.private_description)}>
                    <summary>{language === "en" ? "Private description (optional)" : "Description privee (optionnel)"}</summary>
                    <label>
                      {language === "en" ? "Private description (internal)" : "Description privee (interne)"}
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
                    <p className="muted">{isEnglish ? "Note for the teacher (sent 24h before)." : "Note pour le professeur (envoyee 24h avant)."}</p>
                    {notesAdvancedMode ? (
                      <a className="mode-link" href={notesSimpleHref}>
                        {isEnglish ? "Simple mode" : "Mode simple"}
                      </a>
                    ) : (
                      <a className="mode-link" href={notesAdvancedHref}>
                        {isEnglish ? "Advanced mode" : "Mode avance"}
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
                      placeholder={isEnglish ? "Enter the note to include in the teacher reminder..." : "Saisir la note a joindre au rappel professeur..."}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {isEnglish ? "Message" : "Message"}
                      <textarea
                        name="professor_reminder_note"
                        rows={6}
                        defaultValue={selectedSession.professor_reminder_note ?? ""}
                        placeholder={isEnglish ? "Enter the note to include in the teacher reminder..." : "Saisir la note a joindre au rappel professeur..."}
                      />
                    </label>
                  )}
                  </section>
                </div>

                <footer className="session-edit-shell-footer">
                  <a className="reset-link" href={modalHref}>
                    {isEnglish ? "Cancel" : "Annuler"}
                  </a>
                  <button type="submit">{isEnglish ? "Save" : "Enregistrer"}</button>
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
                  {isEnglish ? "Quick shift" : "Ajustement rapide"}
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">{isEnglish ? "This occurrence" : "Cette occurrence"}</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{isEnglish ? "Future series" : "Serie future"}</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{isEnglish ? "Whole series" : "Toute la serie"}</option> : null}
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
                <h2 className="modal-title">{isEnglish ? "Attendance" : "Presences"}</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {sessionTimeRangeLabel(selectedSession, language)} · {selectedLocationName}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <span className="status-badge status-waitlist">
                  {focusedAttendanceBooking
                    ? `${isEnglish ? "Student" : "Eleve"} ${focusedAttendanceIndex + 1}/${attendanceBookings.length || 1}`
                    : `${isEnglish ? "Student" : "Eleve"} 0/${attendanceBookings.length || 0}`}
                </span>
                <span className="status-badge status-scheduled">{isEnglish ? "Remaining" : "Restant"} {attendanceMissingCount}</span>
                <a className="modal-close-x" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
                  ×
                </a>
              </div>
            </header>

            {!selectedSessionHasBookings || !focusedAttendanceBooking ? (
              <section className="note-modal-empty">
                <p className="muted">{isEnglish ? "No student booked on this slot." : "Aucun eleve inscrit sur ce creneau."}</p>
              </section>
            ) : (
              <>
                <div className="attendance-v2-body">
                  <aside className="attendance-v2-list">
                    <div className="attendance-v2-list-filters">
                      <a className={`mode-link ${attendanceFilter === "all" ? "mode-active" : ""}`} href={attendanceFilteredHref("all")}>
                        {isEnglish ? "All" : "Tous"}
                      </a>
                      <a className={`mode-link ${attendanceFilter === "missing" ? "mode-active" : ""}`} href={attendanceFilteredHref("missing")}>
                        {isEnglish ? "Missing" : "Manquants"}
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
                            <strong>{booking.client_display_name || `${pickText(language, "Participant", "Student")} ${index + 1}`}</strong>
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
                        <h3>{focusedAttendanceBooking.client_display_name || pickText(language, "Participant", "Student")}</h3>
                        <p className="muted">{isEnglish ? "Completed" : "Completes"}: {attendanceCompletedCount} / {selectedSessionBookings.length}</p>
                      </div>
                      <div className="attendance-v2-nav-links">
                        {previousAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(previousAttendanceBooking.id)}>
                            {isEnglish ? "← Previous" : "← Precedent"}
                          </a>
                        ) : null}
                        {nextAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(nextAttendanceBooking.id)}>
                            {isEnglish ? "Next →" : "Suivant →"}
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
                          value={nextAttendanceBooking ? attendanceBookingHref(nextAttendanceBooking.id) : modalHref}
                        />
                        <PresenceButtonsGroup
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
                      <p className="muted">{isEnglish ? "Attendance cannot be edited for this status." : "Presence non editable pour ce statut."}</p>
                    )}

                    {selectedSessionSupportsStudentTimeOverrides ? (
                      <details className="attendance-v2-notes" open={Boolean(focusedAttendanceBooking.student_start_at_utc)}>
                        <summary>{isEnglish ? "Student reminder time" : "Horaire de rappel eleve"}</summary>
                        <form action={adminUpdateSessionBookingStudentTimeAction} className="attendance-v2-note-form">
                          <input type="hidden" name="session_id" value={selectedSession.id} />
                          <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                          <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                          <div className="grid cols-2 config-form-grid">
                            <label>
                              {isEnglish ? "Start" : "Debut"}
                              <input
                                type="time"
                                name="student_start_time_local"
                                defaultValue={
                                  focusedAttendanceBooking.student_start_at_utc
                                    ? toTimeInputInTimezone(focusedAttendanceBooking.student_start_at_utc, selectedSession.timezone)
                                    : ""
                                }
                                min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                              />
                            </label>
                            <label>
                              {isEnglish ? "End" : "Fin"}
                              <input
                                type="time"
                                name="student_end_time_local"
                                defaultValue={
                                  focusedAttendanceBooking.student_end_at_utc
                                    ? toTimeInputInTimezone(focusedAttendanceBooking.student_end_at_utc, selectedSession.timezone)
                                    : ""
                                }
                                min={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                                max={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                              />
                            </label>
                          </div>
                          <div className="row">
                            <button type="submit" className="ghost">
                              {isEnglish ? "Save time" : "Enregistrer l horaire"}
                            </button>
                          </div>
                        </form>
                      </details>
                    ) : null}

                    <details className="attendance-v2-notes">
                      <summary>{isEnglish ? "Notes (optional)" : "Notes (optionnel)"}</summary>
                      <form action={adminUpdateSessionBookingNoteAction} className="attendance-v2-note-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                        <input type="hidden" name="student_id" value={focusedAttendanceBooking.client_id} />
                        <input type="hidden" name="student_display_name" value={focusedAttendanceBooking.client_display_name || pickText(language, "Eleve", "Student")} />
                        <input type="hidden" name="session_title" value={selectedSession.title} />
                        <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                        <label className="session-edit-span">
                          {isEnglish ? "Message" : "Message"}
                          <input type="hidden" name="student_note_format" value="TEXT" />
                          <textarea
                            name="student_note"
                            rows={5}
                            placeholder={isEnglish ? "Internal note..." : "Note interne..."}
                            defaultValue={stripHtml(focusedAttendanceBooking.student_note ?? "")}
                          />
                        </label>
                        <div className="row">
                          <button type="submit" name="note_action" value="SAVE_INTERNAL" className="ghost">
                            {isEnglish ? "Save note" : "Enregistrer la note"}
                          </button>
                          <button type="submit" name="note_action" value="SEND_PARENTS" className="ghost">
                            {isEnglish ? "Send to parents" : "Envoyer aux parents"}
                          </button>
                        </div>
                      </form>
                    </details>
                  </section>
                </div>
                <footer className="note-modal-footer">
                  <a className="reset-link" href={modalHref}>
                    {isEnglish ? "Cancel" : "Annuler"}
                  </a>
                  <div className="row">
                    {canEditAttendance(focusedAttendanceBooking.status) ? (
                      <button type="submit" form="attendance-status-form">
                        {nextAttendanceBooking
                          ? (isEnglish ? "Save & next" : "Enregistrer & suivant")
                          : (isEnglish ? "Save & close" : "Enregistrer & fermer")}
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
                <h2 className="modal-title">{isEnglish ? "Group note" : "Note de groupe"}</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {sessionTimeRangeLabel(selectedSession, language)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
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
                  {isEnglish ? "Content" : "Contenu"}
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "recipients" ? "active" : ""}`} href={groupNoteTabHref("recipients")}>
                  {isEnglish ? "Recipients" : "Destinataires"}
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "send" ? "active" : ""}`} href={groupNoteTabHref("send")}>
                  {isEnglish ? "Send" : "Envoi"}
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${groupNoteTab === "content" ? "active" : ""}`}>
                  {groupNoteTemplates.length > 0 ? (
                    <label className="session-edit-span">
                      {isEnglish ? "Template" : "Modele"}
                      <div className="note-template-row">
                        <select name="group_note_template_id" defaultValue={selectedGroupNoteTemplate?.id ?? ""}>
                          <option value="">{isEnglish ? "No template" : "Aucun modele"}</option>
                          {groupNoteTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                        {selectedGroupNoteTemplate ? (
                          <a className="mode-link" href={groupNotesModalClearTemplateHref}>
                            {isEnglish ? "Remove" : "Retirer"}
                          </a>
                        ) : null}
                      </div>
                    </label>
                  ) : (
                    <div className="session-edit-alert">
                      {isEnglish ? "No template configured. Add one in Settings > Messaging." : "Aucun modele configure. Ajoutez-en un dans Configuration > Messagerie."}
                    </div>
                  )}
                  <div className="row spread">
                    <p className="muted">{isEnglish ? "Note content" : "Contenu de la note"}</p>
                    {groupNoteAdvancedMode ? (
                      <a className="mode-link" href={groupNoteSimpleHref}>
                        {isEnglish ? "Simple mode" : "Mode simple"}
                      </a>
                    ) : (
                      <a className="mode-link" href={groupNoteAdvancedHref}>
                        {isEnglish ? "Advanced mode" : "Mode avance"}
                      </a>
                    )}
                  </div>
                  {groupNoteAdvancedMode ? (
                    <RichMessageEditor
                      name="group_note"
                      formatName="group_note_format"
                      rows={10}
                      maxLength={12000}
                      placeholder={isEnglish ? "Enter a group note..." : "Saisir une note de groupe..."}
                      defaultValue={groupNotePrefill}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {isEnglish ? "Message" : "Message"}
                      <input type="hidden" name="group_note_format" value="TEXT" />
                      <textarea name="group_note" rows={8} defaultValue={stripHtml(groupNotePrefill)} />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "recipients" ? "active" : ""}`}>
                  <fieldset className="note-destination-radios">
                    <legend>{isEnglish ? "Destination" : "Destination"}</legend>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PRIVATE" defaultChecked={groupNoteDestination === "PRIVATE"} />
                      {isEnglish ? "Internal" : "Interne"}
                    </label>
                    <label className="checkline">
                      <input
                        type="radio"
                        name="note_destination"
                        value="STUDENTS_AND_PARENTS"
                        defaultChecked={groupNoteDestination === "STUDENTS_AND_PARENTS"}
                      />
                      {isEnglish ? "Parents / students" : "Parents / eleves"}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PARENTS" defaultChecked={groupNoteDestination === "PARENTS"} />
                      {isEnglish ? "Parents only" : "Parents uniquement"}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="STUDENTS" defaultChecked={groupNoteDestination === "STUDENTS"} />
                      {isEnglish ? "Students only" : "Eleves uniquement"}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PROFESSOR" defaultChecked={groupNoteDestination === "PROFESSOR"} />
                      {isEnglish ? "Teacher" : "Professeur"}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="ADMINS" defaultChecked={groupNoteDestination === "ADMINS"} />
                      {isEnglish ? "Administration" : "Administration"}
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="SELF" defaultChecked={groupNoteDestination === "SELF"} />
                      {isEnglish ? "Myself" : "Moi-meme"}
                    </label>
                  </fieldset>

                  <div className="note-recipient-summary">
                    <strong>{sessionRecipientStudentIds.length} {isEnglish ? "student(s) selected" : "eleve(s) selectionne(s)"}</strong>
                    <span className="muted">{sessionRecipientSummary || pickText(language, "Aucun eleve", "No student")}</span>
                  </div>
                  <details className="note-recipient-picker" open={isGroupNoteStudentAudience}>
                    <summary>{isEnglish ? "Edit selection" : "Modifier la selection"}</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label={isEnglish ? "Included students" : "Eleves inclus"}
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder={isEnglish ? "Search a student..." : "Rechercher un eleve..."}
                      emptySelectionLabel={selectedSessionHasBookings ? pickText(language, "Aucun eleve selectionne.", "No student selected.") : pickText(language, "Aucun eleve inscrit sur ce creneau.", "No student booked on this slot.")}
                    />
                  </details>
                  {!selectedSessionHasBookings && isGroupNoteStudentAudience ? (
                    <p className="flash-err">{isEnglish ? "No student is booked on this slot for a Students/Parents send." : "Aucun eleve inscrit sur ce creneau pour un envoi Eleves/Parents."}</p>
                  ) : null}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "send" ? "active" : ""}`}>
                  {groupNoteDestination === "PRIVATE" ? (
                    <p className="muted">{isEnglish ? "Internal destination: no external send will be performed." : "Destination interne: aucun envoi externe n est effectue."}</p>
                  ) : (
                    <>
                      <label className="checkline">
                        <input type="checkbox" name="send_to_self" />
                        {isEnglish ? "Send myself a copy too" : "M envoyer aussi une copie"}
                      </label>
                      <label>
                        {isEnglish ? "Email subject (optional)" : "Sujet email (optionnel)"}
                        <input type="text" name="subject" defaultValue={`${isEnglish ? "Group note" : "Note de groupe"} - ${selectedSession.title}`} maxLength={255} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="confirm_send" />
                        {isEnglish ? `Confirm send (${sessionRecipientStudentIds.length} potential recipient(s))` : `Confirmer l envoi (${sessionRecipientStudentIds.length} destinataire(s) potentiels)`}
                      </label>
                    </>
                  )}
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  {isEnglish ? "Close" : "Fermer"}
                </a>
                <div className="row">
                  <button type="submit" name="note_action" value="SAVE_ONLY" className="ghost">
                    {isEnglish ? "Save" : "Enregistrer"}
                  </button>
                  {groupNoteDestination !== "PRIVATE" ? (
                    <button type="submit" name="note_action" value="SEND_EMAIL">
                      {isEnglish ? "Send" : "Envoyer"}
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
                <h2 className="modal-title">{isEnglish ? "Send an email" : "Envoyer un email"}</h2>
                <p className="muted">
                  {isEnglish ? "Slot" : "Creneau"}: {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} · {formatTime(selectedSession.start_at_utc, selectedSession.timezone, language)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
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
                  {isEnglish ? "Recipients" : "Destinataires"}
                </a>
                <a className={`note-modal-tab ${emailTab === "content" ? "active" : ""}`} href={sessionEmailTabHref("content")}>
                  {isEnglish ? "Content" : "Contenu"}
                </a>
                <a className={`note-modal-tab ${emailTab === "send" ? "active" : ""}`} href={sessionEmailTabHref("send")}>
                  {isEnglish ? "Options" : "Options"}
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${emailTab === "recipients" ? "active" : ""}`}>
                  <label>
                    {isEnglish ? "Recipients" : "Destinataires"}
                    <select name="audience" defaultValue={emailAudience}>
                      <option value="STUDENTS">{isEnglish ? "Booked students" : "Eleves inscrits"}</option>
                      <option value="PARENTS">{isEnglish ? "Parents of students" : "Parents des eleves"}</option>
                      <option value="STUDENTS_AND_PARENTS">{isEnglish ? "Students + parents" : "Eleves + parents"}</option>
                      <option value="PROFESSOR">{isEnglish ? "Teacher" : "Professeur"}</option>
                      <option value="ADMINS">{isEnglish ? "Administration" : "Administration"}</option>
                      <option value="SELF">{isEnglish ? "Myself" : "Moi-meme"}</option>
                    </select>
                  </label>
                  <div className="note-recipient-summary">
                    <strong>{sessionRecipientStudentIds.length} {isEnglish ? "recipient(s) selected" : "destinataire(s) selectionnes"}</strong>
                    <span className="muted">{sessionRecipientSummary || pickText(language, "Aucun destinataire eleve", "No student recipient")}</span>
                  </div>
                  <details className="note-recipient-picker" open={emailAudience === "STUDENTS" || emailAudience === "PARENTS" || emailAudience === "STUDENTS_AND_PARENTS"}>
                    <summary>{isEnglish ? "Edit" : "Modifier"}</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label={isEnglish ? "Included students (you can remove some)" : "Eleves inclus (vous pouvez en retirer)"}
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder={isEnglish ? "Search a student..." : "Rechercher un eleve..."}
                      emptySelectionLabel={isEnglish ? "No student selected." : "Aucun eleve selectionne."}
                    />
                  </details>
                  {!selectedSessionHasBookings ? <p className="muted">{isEnglish ? "No student booked: use Teacher, Administration or Myself." : "Aucun eleve inscrit: utilisez Professeur, Administration ou Moi-meme."}</p> : null}
                </section>

                <section className={`note-modal-panel ${emailTab === "content" ? "active" : ""}`}>
                  <label>
                    {isEnglish ? "Subject" : "Sujet"}
                    <input type="text" name="subject" defaultValue={`${isEnglish ? "Slot message" : "Message creneau"}: ${selectedSession.title}`} maxLength={255} required />
                  </label>
                  <div className="row spread">
                    <p className="muted">{isEnglish ? "Message" : "Message"}</p>
                    {emailAdvancedMode ? (
                      <a className="mode-link" href={sessionEmailSimpleHref}>
                        {isEnglish ? "Simple mode" : "Mode simple"}
                      </a>
                    ) : (
                      <a className="mode-link" href={sessionEmailAdvancedHref}>
                        {isEnglish ? "Advanced mode" : "Mode avance"}
                      </a>
                    )}
                  </div>
                  {emailAdvancedMode ? (
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={10}
                      maxLength={12000}
                      defaultValue={
                        isEnglish
                          ? `Hello,\n\nMessage about the slot "${selectedSession.title}" on ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.\n`
                          : `Bonjour,\n\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.\n`
                      }
                      placeholder={isEnglish ? "Enter your message..." : "Saisir votre message..."}
                    />
                  ) : (
                    <label className="session-edit-span">
                      {isEnglish ? "Message" : "Message"}
                      <input type="hidden" name="body_format" value="TEXT" />
                      <textarea
                        name="body"
                        rows={8}
                        defaultValue={
                          isEnglish
                            ? `Hello,\n\nMessage about the slot "${selectedSession.title}" on ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.\n`
                            : `Bonjour,\n\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.\n`
                        }
                        placeholder={isEnglish ? "Enter your message..." : "Saisir votre message..."}
                      />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${emailTab === "send" ? "active" : ""}`}>
                  <label className="checkline">
                    <input type="checkbox" name="send_to_self" />
                    {isEnglish ? "Send myself a copy too" : "M envoyer aussi une copie"}
                  </label>
                  <label className="session-edit-span">
                    {isEnglish ? "Copy (emails, optional)" : "Copie (emails, optionnel)"}
                    <textarea name="cc_emails" rows={2} placeholder="copie@example.com; autre@example.com" />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="confirm_send" />
                    {isEnglish ? `Confirm send to ${sessionRecipientStudentIds.length} recipient(s)` : `Confirmer l envoi a ${sessionRecipientStudentIds.length} destinataire(s)`}
                  </label>
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  {isEnglish ? "Close" : "Fermer"}
                </a>
                <div className="row">
                  <button type="submit">{isEnglish ? "Send" : "Envoyer"}</button>
                </div>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionSmsModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel note-modal-shell">
            <header className="note-modal-header">
              <div className="note-modal-header-main">
                <h2 className="modal-title">{isEnglish ? "Send an SMS" : "Envoyer un SMS"}</h2>
                <p className="muted">{isEnglish ? "Group send for students or parents linked to this slot." : "Envoi groupe pour les eleves ou parents rattaches a ce creneau."}</p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
                  ×
                </a>
              </div>
            </header>

            <form action={adminSendSessionBroadcastAction} className="note-modal-form">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="channel" value="SMS" />
              <input type="hidden" name="return_to" value={sessionSmsModalHref} />

              <div className="note-modal-body">
                <section className="note-modal-panel active">
                  <label>
                    {isEnglish ? "Recipients" : "Destinataires"}
                    <select name="audience" defaultValue="STUDENTS">
                      <option value="STUDENTS">{isEnglish ? "Booked students" : "Eleves inscrits"}</option>
                      <option value="PARENTS">{isEnglish ? "Parents of students" : "Parents des eleves"}</option>
                      <option value="STUDENTS_AND_PARENTS">{isEnglish ? "Students + parents" : "Eleves + parents"}</option>
                      <option value="PROFESSOR">{isEnglish ? "Teacher" : "Professeur"}</option>
                      <option value="ADMINS">{isEnglish ? "Administration" : "Administration"}</option>
                      <option value="SELF">{isEnglish ? "Myself" : "Moi-meme"}</option>
                    </select>
                  </label>

                  <SearchMultiSelect
                    className="session-edit-span"
                    label={isEnglish ? "Included students (you can remove some)" : "Eleves inclus (vous pouvez en retirer)"}
                    name="included_student_ids"
                    options={sessionRecipientStudents}
                    selectedIds={sessionRecipientStudentIds}
                    placeholder={isEnglish ? "Search a student..." : "Rechercher un eleve..."}
                    emptySelectionLabel={isEnglish ? "No student selected." : "Aucun eleve selectionne."}
                  />
                  {!selectedSessionHasBookings ? <p className="muted">{isEnglish ? "No student booked: use Teacher, Administration or Myself." : "Aucun eleve inscrit: utilisez Professeur, Administration ou Moi-meme."}</p> : null}

                  <label className="checkline">
                    <input type="checkbox" name="send_to_self" />
                    {isEnglish ? "Send myself a copy too" : "M envoyer aussi une copie"}
                  </label>

                  <label>
                    {isEnglish ? "Subject (optional)" : "Sujet (optionnel)"}
                    <input type="text" name="subject" defaultValue={`${isEnglish ? "Slot info" : "Information creneau"}: ${selectedSession.title}`} maxLength={255} />
                  </label>

                  <label className="session-edit-span">
                    {isEnglish ? "Copy (phone numbers, separated by commas, semicolons or new lines)" : "Copie (telephones separes par virgule, point-virgule ou retour ligne)"}
                    <textarea name="cc_phone_numbers" rows={2} placeholder="+33600000000; 0600000000" />
                  </label>

                  <label className="session-edit-span">
                    {isEnglish ? "SMS message" : "Message SMS"}
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      defaultFormat="TEXT"
                      rows={8}
                      maxLength={12000}
                      defaultValue={
                        isEnglish
                          ? `Hello,\nMessage about the slot "${selectedSession.title}" on ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.`
                          : `Bonjour,\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)}.`
                      }
                      placeholder={isEnglish ? "Enter your SMS message..." : "Saisir votre message SMS..."}
                    />
                  </label>
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  {isEnglish ? "Cancel" : "Annuler"}
                </a>
                <div className="row">
                  <button type="submit">{isEnglish ? "Send SMS" : "Envoyer le SMS"}</button>
                </div>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && duplicateModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={modalHref} aria-label={isEnglish ? "Close" : "Fermer"}>
              ×
            </a>
            <h2 className="modal-title">{isEnglish ? "Duplicate slot" : "Dupliquer le creneau"}</h2>
            <p className="muted">
              {isEnglish
                ? "Set the target date and start time. Students linked to the slot will be duplicated automatically."
                : "Definir la date cible et l heure de debut. Les eleves rattaches au creneau seront dupliques automatiquement."}
            </p>

            <form action={duplicateAdminSessionAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={duplicateModalHref} />
              <input type="hidden" name="session_timezone" value={selectedSession.timezone} />

              <div className="grid cols-2">
                <label>
                  {isEnglish ? "Target date" : "Date cible"}
                  <input
                    type="date"
                    name="target_date"
                    defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                    required
                  />
                </label>
                <label>
                  {isEnglish ? "Start time" : "Heure de debut"}
                  <input
                    type="time"
                    name="target_time"
                    defaultValue={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                    required
                  />
                </label>
              </div>

              {selectedSession.recurrence_group_id ? (
                <fieldset className="grid">
                  <legend>{isEnglish ? "Duplication scope" : "Portee de duplication"}</legend>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="ONE" defaultChecked />
                    {isEnglish ? "Duplicate this slot only" : "Dupliquer ce creneau uniquement"}
                  </label>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="SERIES_FUTURE" />
                    {isEnglish ? "Duplicate this slot and following recurring occurrences" : "Dupliquer ce creneau et les occurrences recurrentes suivantes"}
                  </label>
                </fieldset>
              ) : (
                <>
                  <input type="hidden" name="apply_scope" value="ONE" />
                  <p className="muted">{isEnglish ? "One-time slot: duplicate only one slot." : "Creneau ponctuel: duplication d un seul creneau."}</p>
                </>
              )}

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  {isEnglish ? "Cancel" : "Annuler"}
                </a>
                <button type="submit">{isEnglish ? "Duplicate slot" : "Dupliquer le creneau"}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && confirmAction ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-confirm-operation">
            <a className="modal-close-x" href={confirmCloseHref} aria-label={isEnglish ? "Close" : "Fermer"}>
              ×
            </a>
            <h2 className="modal-title">{confirmAction === "delete" ? (isEnglish ? "Confirm deletion" : "Confirmer la suppression") : (isEnglish ? "Confirm cancellation" : "Confirmer l'annulation")}</h2>
            <p className="muted">
              {confirmAction === "delete"
                ? (isEnglish ? "The slot will be removed from the calendar. You can notify booked students and the teacher." : "Le creneau sera supprime du calendrier. Vous pouvez notifier les eleves inscrits et le professeur.")
                : (isEnglish ? "The slot will remain visible in the calendar with status CANCELLED. You can notify booked students and the teacher." : "Le creneau restera visible au calendrier avec le statut CANCELLED. Vous pouvez notifier les eleves inscrits et le professeur.")}
            </p>

            <form action={confirmAction === "delete" ? deleteAdminSessionAction : cancelAdminSessionAction} className="grid">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={modalHref} />
              {confirmAction === "delete" && selectedSession.recurrence_group_id ? (
                <label className="session-edit-span">
                  {isEnglish ? "Delete all occurrences starting from this slot?" : "Supprimer toutes les occurrences a partir de ce creneau ?"}
                  <select name="delete_following" defaultValue="no">
                    <option value="no">{isEnglish ? "No, delete this slot only" : "Non, supprimer uniquement ce creneau"}</option>
                    <option value="yes">{isEnglish ? "Yes, delete this slot and all following occurrences" : "Oui, supprimer ce creneau et toutes les occurrences suivantes"}</option>
                  </select>
                </label>
              ) : (
                <label>
                  {isEnglish ? "Scope" : "Portee"}
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">{isEnglish ? "This slot" : "Ce creneau"}</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">{isEnglish ? "Future series" : "Serie future"}</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">{isEnglish ? "Whole series" : "Toute la serie"}</option> : null}
                  </select>
                </label>
              )}

              <p className="muted span-3">
                {isEnglish ? "Target teacher" : "Professeur cible"}: <strong>{selectedEffectiveProfessorLabel || pickText(language, "Non requis", "Not required")}</strong>
              </p>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_students" />
                {isEnglish ? "Send a message to all booked students" : "Envoyer un message a tous les eleves inscrits"}
              </label>

              <label>
                {isEnglish ? "Student subject" : "Sujet eleves"}
                <input
                  type="text"
                  name="students_subject"
                  defaultValue={`${confirmAction === "delete"
                    ? (isEnglish ? "Deletion" : "Suppression")
                    : (isEnglish ? "Cancellation" : "Annulation")} ${isEnglish ? "of slot" : "du creneau"}: ${selectedSession.title}`}
                  maxLength={255}
                />
              </label>

              <label className="session-edit-span">
                {isEnglish ? "Student message" : "Message eleves"}
                <RichMessageEditor
                  name="students_message"
                  formatName="students_format"
                  rows={8}
                  maxLength={12000}
                  defaultValue={
                    confirmAction === "delete"
                      ? (isEnglish
                        ? `Hello,\n\nThe slot "${selectedSession.title}" on ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} has been deleted.\n\nPiano Academie`
                        : `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} a ete supprime.\n\nPiano Academie`)
                      : (isEnglish
                        ? `Hello,\n\nThe slot "${selectedSession.title}" on ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} has been cancelled.\n\nPiano Academie`
                        : `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone, language)} a ete annule.\n\nPiano Academie`)
                  }
                  placeholder={isEnglish ? "Student message" : "Message eleves"}
                />
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_professor" />
                {isEnglish ? "Send a message to the selected teacher" : "Envoyer un message au professeur selectionne"}
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="professor_same_as_students" defaultChecked />
                {isEnglish ? "Use the same subject/message as for students" : "Utiliser le meme sujet/message que pour les eleves"}
              </label>

              <label>
                {isEnglish ? "Teacher subject (if different)" : "Sujet professeur (si message distinct)"}
                <input type="text" name="professor_subject" maxLength={255} />
              </label>

              <label className="session-edit-span">
                {isEnglish ? "Teacher message (if different)" : "Message professeur (si message distinct)"}
                <RichMessageEditor
                  name="professor_message"
                  formatName="professor_format"
                  rows={8}
                  maxLength={12000}
                  placeholder={isEnglish ? "Teacher message" : "Message professeur"}
                />
              </label>

              <div className="row quick-actions-row">
                <button className="danger" type="submit">
                  {confirmAction === "delete" ? (isEnglish ? "Confirm deletion" : "Confirmer la suppression") : (isEnglish ? "Confirm cancellation" : "Confirmer l'annulation")}
                </button>
                <a className="reset-link" href={confirmCloseHref}>
                  {isEnglish ? "Back" : "Retour"}
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
