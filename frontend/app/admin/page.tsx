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
import SessionCreateMainFields from "../../components/planning/session-create-main-fields";
import type {
  AdminClientOut,
  AdminMessagingTemplateOut,
  AdminProfessorOut,
  AdminSessionBookingOut,
  AdminSessionOut,
  CourseTypeOut,
  LocationOut,
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
  session_visibility: "PRIVATE" | "PUBLIC";
  allow_online_booking: "1" | "0";
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

function agendaDayLongLabel(dayKey: string): string {
  const date = keyToUtcDate(dayKey);
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
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

  const from = startOfMonthUtc(focusDate);
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
    }).format(from),
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

function agendaNavigationHint(view: AgendaView): string {
  if (view === "month") {
    return "Navigation: mois par mois.";
  }
  if (view === "week") {
    return "Navigation: semaine par semaine.";
  }
  return "Navigation: jour par jour.";
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

function formatDateKeyFr(value: string): string {
  if (!isDateKey(value)) {
    return "-";
  }
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(keyToUtcDate(value));
}

function formatDate(value: string, timezone?: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  const resolvedTimezone = timezone ? resolveTimezone(timezone) : "";
  if (resolvedTimezone) {
    const dateKey = toDateInputInTimezone(value, resolvedTimezone);
    const timeKey = toTimeInputInTimezone(value, resolvedTimezone);
    if (dateKey && timeKey) {
      return `${formatDateKeyFr(dateKey)}, ${timeKey}`;
    }
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string, timezone?: string): string {
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
  return parsed.toLocaleTimeString("fr-FR", {
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

function sessionTimeRangeLabel(session: AdminSessionOut): string {
  if (session.is_all_day) {
    return "Toute la journee";
  }
  return `${formatTime(session.start_at_utc, session.timezone)} - ${formatTime(session.end_at_utc, session.timezone)}`;
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

function bookingEnrollmentLabel(status: string): string {
  if (status === "WAITLISTED") {
    return "Liste attente";
  }
  if (status === "BOOKED") {
    return "Inscrit";
  }
  if (status === "CANCELLED") {
    return "Annule";
  }
  return "Inscrit";
}

function bookingPresenceLabel(status: string): string | null {
  if (status === "ATTENDED") {
    return "Present";
  }
  if (status === "NO_SHOW") {
    return "Absent";
  }
  if (status === "EXCUSED_ABSENCE") {
    return "Abs. excusee";
  }
  return null;
}

function attendanceChoiceLabel(status: string): string {
  if (status === "ATTENDED") {
    return "Present";
  }
  if (status === "NO_SHOW") {
    return "Absent non excuse";
  }
  if (status === "EXCUSED_ABSENCE") {
    return "Absent excuse";
  }
  return "A saisir";
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

function sessionTypeLabel(session: AdminSessionOut, locationLabel: string): string {
  const lowerLocation = locationLabel.toLowerCase();
  if (lowerLocation.includes("online") || lowerLocation.includes("ligne")) {
    return "Online";
  }
  if (lowerLocation.includes("domicile")) {
    return "Domicile";
  }
  if (session.is_private) {
    return "Prive";
  }
  return "Collectif";
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

function recurrenceLabel(session: AdminSessionOut): string {
  if (!session.recurrence_rule) {
    return "Ponctuel";
  }
  const raw = String(session.recurrence_rule || "").trim().toUpperCase();
  const [frequencyRaw, intervalRaw] = raw.includes(":") ? raw.split(":", 2) : [raw, "1"];
  const interval = Number.parseInt(intervalRaw || "1", 10);
  const safeInterval = Number.isFinite(interval) && interval > 0 ? interval : 1;

  if (frequencyRaw === "DAILY") {
    return safeInterval > 1 ? `Tous les ${safeInterval} jours` : "Quotidien";
  }
  if (frequencyRaw === "WEEKLY") {
    return safeInterval > 1 ? `Toutes les ${safeInterval} semaines` : "Hebdo";
  }
  if (frequencyRaw === "MONTHLY") {
    return safeInterval > 1 ? `Tous les ${safeInterval} mois` : "Mensuel";
  }
  return raw;
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
    const visibilityRaw = String(parsed.session_visibility ?? "").trim().toUpperCase();
    const visibility = visibilityRaw === "PUBLIC" ? "PUBLIC" : "PRIVATE";
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
      session_visibility: visibility,
      allow_online_booking: String(parsed.allow_online_booking ?? "") === "1" ? "1" : "0",
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

function parseRecurrenceRuleDefaults(rawRule: string | null | undefined): { frequency: "DAILY" | "WEEKLY" | "MONTHLY"; interval: number } {
  const raw = String(rawRule || "").trim().toUpperCase();
  if (!raw) {
    return { frequency: "WEEKLY", interval: 1 };
  }
  const [frequencyRaw, intervalRaw] = raw.includes(":") ? raw.split(":", 2) : [raw, "1"];
  const frequency = frequencyRaw === "DAILY" || frequencyRaw === "MONTHLY" ? frequencyRaw : "WEEKLY";
  const intervalParsed = Number.parseInt(intervalRaw || "1", 10);
  const interval = Number.isFinite(intervalParsed) && intervalParsed > 0 ? intervalParsed : 1;
  return { frequency, interval };
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

  const queryForLinks: PlanningQuery = {
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

  const agendaRange = buildAgendaRange(agendaView, agendaDate);
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
      ? `Multi lieux (${selectedLocationLabels.length})`
      : selectedLocationLabels[0]
        ? selectedLocationLabels[0]
        : focusedLocation?.name
          ? focusedLocation.name
          : "Tous les lieux";
  const planningViewLabel = agendaView === "month" ? "Mois" : agendaView === "week" ? "Semaine" : "Jour";
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

  const sessionsByDay = new Map<string, AdminSessionOut[]>();
  for (const session of filteredSessions) {
    const key = dateKeyInTimezone(session.start_at_utc, timezone);
    const existing = sessionsByDay.get(key) ?? [];
    existing.push(session);
    sessionsByDay.set(key, existing);
  }

  const agendaDays = agendaRange.dayKeys.map((dayKey) => ({
    key: dayKey,
    label: agendaDayLabel(dayKey, agendaView),
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
    ? selectedSessionBookings.filter((booking) => bookingPresenceLabel(booking.status) === null)
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
  const attendanceMissingCount = selectedSessionBookings.filter((booking) => bookingPresenceLabel(booking.status) === null).length;
  const attendanceCompletedCount = selectedSessionBookings.length - attendanceMissingCount;
  const selectedCourseTypeName = selectedSession ? courseTypeById.get(selectedSession.course_type_id)?.name ?? "Type non defini" : "";
  const selectedLocationName = selectedSession ? locationById.get(selectedSession.location_id)?.name ?? "Lieu non defini" : "";
  const selectedHabitualProfessorDetail =
    selectedSession && selectedSession.habitual_teacher_id ? professorById.get(selectedSession.habitual_teacher_id) : null;
  const selectedSubstituteProfessorDetail =
    selectedSession && selectedSession.substitute_teacher_id ? professorById.get(selectedSession.substitute_teacher_id) : null;
  const selectedEffectiveProfessorDetail =
    selectedSession && selectedSession.effective_teacher_id ? professorById.get(selectedSession.effective_teacher_id) : null;
  const selectedSessionIsOnline = selectedSession
    ? (locationById.get(selectedSession.location_id)?.is_online ?? false) || selectedSession.type_label.toLowerCase().includes("online")
    : false;
  const selectedHabitualProfessorName = selectedSession
    ? (selectedSession.habitual_teacher_display_name || "").trim() ||
      (selectedHabitualProfessorDetail ? `${selectedHabitualProfessorDetail.first_name} ${selectedHabitualProfessorDetail.last_name}`.trim() : "") ||
      "Professeur non defini"
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
  const selectedSessionIsSubstituted = Boolean(selectedSession?.substitute_teacher_id);
  const selectedEffectiveProfessorZoomLink = (selectedEffectiveProfessorDetail?.zoom_link ?? "").trim();
  const selectedSessionZoomLink =
    selectedSession && ((selectedSession.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      ? ((selectedSession?.zoom_link ?? "").trim() || (selectedSessionIsOnline ? selectedEffectiveProfessorZoomLink : ""))
      : null;
  const selectedSessionTypeName = selectedSession ? sessionTypeLabel(selectedSession, selectedLocationName) : "";
  const selectedSessionHeaderTitle = selectedSession ? `${selectedCourseTypeName} - ${selectedLocationName}` : "";
  const selectedSessionSubtitle = selectedSession
    ? `${formatDate(selectedSession.start_at_utc, selectedSession.timezone)} · ${sessionTimeRangeLabel(selectedSession)} · ${selectedSession.timezone} · Prof: ${selectedEffectiveProfessorName}${selectedSessionIsSubstituted ? " (remplacant)" : ""}`
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
    .sort((a, b) => a.localeCompare(b, "fr"))
    .map((value) => {
      const known = PLANNING_TIMEZONES.find((option) => option.value === value);
      return { value, label: known?.label ?? value };
    });
  const createInitialIsPrivate = createDraft ? createDraft.session_visibility !== "PUBLIC" : true;
  const createInitialAllowOnlineBooking = createDraft
    ? createDraft.allow_online_booking === "1"
    : false;
  const createDraftDuration = createDraft ? draftPositiveInteger(createDraft.duration_minutes) : null;
  const createDraftCapacity = createDraft ? draftPositiveInteger(createDraft.capacity_max) : null;
  const createRecurrenceMode = createDraft?.recurrence_mode?.trim().toUpperCase() === "RECURRING" ? "RECURRING" : "NONE";
  const createRecurrenceFrequencyRaw = createDraft?.recurrence_frequency?.trim().toUpperCase() ?? "WEEKLY";
  const createRecurrenceFrequency =
    createRecurrenceFrequencyRaw === "DAILY" || createRecurrenceFrequencyRaw === "MONTHLY"
      ? createRecurrenceFrequencyRaw
      : "WEEKLY";
  const createRecurrenceInterval = createDraft ? draftPositiveInteger(createDraft.recurrence_interval) ?? 1 : 1;
  const editRecurrenceDefaults = parseRecurrenceRuleDefaults(selectedSession?.recurrence_rule);
  const editRecurrenceUntilDate = selectedSession
    ? toDateInputInTimezone(addUtcDays(new Date(selectedSession.start_at_utc), 84).toISOString(), selectedSession.timezone)
    : agendaDate;

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">Erreur backend: {errors.join(" | ")}</section> : null}

      <section className="card planning-header-card">
        <div className="row spread planning-header-row">
          <div className="stack-xs">
            <h2>Planning</h2>
            <p className="muted planning-subtitle">{planningSubtitle}</p>
          </div>
          <div className="row planning-header-actions">
            <a className={`mode-link ${!createOpen ? "mode-active" : ""}`} href={lectureHref}>
              Lecture
            </a>
            <a className={`mode-link ${createOpen ? "mode-active" : ""}`} href={createHref}>
              Edition
            </a>
            <a className="icon-add-button" href={createHref}>
              <span className="icon-add-button-plus" aria-hidden="true">
                +
              </span>
              Ajouter un creneau
            </a>
            {focusedLocationId ? (
              <Link className="mode-link" href={`/admin/plannings/${focusedLocationId}/settings`}>
                Parametres
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card planning-filters-card">
        <form method="get" className="planning-quick-form">
          <input type="hidden" name="course_type_id" value={selectedCourseType} />
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
          {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

          <label>
            Lieu
            <AutoSubmitSelect
              name="location_id"
              defaultValue={focusedLocationId}
              options={[{ value: "", label: "-- Tous les lieux --" }, ...locations.map((row) => ({ value: row.id, label: row.name }))]}
            />
          </label>

          <label>
            Vue agenda
            <AutoSubmitSelect
              name="agenda_view"
              defaultValue={agendaView}
              options={[
                { value: "month", label: "Mois" },
                { value: "week", label: "Semaine" },
                { value: "day", label: "Jour" },
              ]}
            />
          </label>

          <label>
            Fuseau horaire
            <AutoSubmitSelect
              name="timezone"
              defaultValue={timezone}
              options={timezoneOptions.map((option) => ({ value: option.value, label: option.label }))}
            />
          </label>

          <div className="row">
            <a className="planning-reset-link" href={filtersResetHref}>
              Reinitialiser
            </a>
            <a className="mode-link planning-advanced-link" href={filtersHref}>
              Filtres avances
            </a>
          </div>
        </form>
        <div className="row planning-active-filters">
          {selectedActivityLabels.length > 0 ? (
            <span className="badge">Activites: {compactList(selectedActivityLabels)}</span>
          ) : null}
          {selectedCourseType ? (
            <span className="badge">Type: {courseTypeById.get(selectedCourseType)?.name ?? "Selection"}</span>
          ) : null}
          {selectedLocationLabels.length > 0 ? (
            <span className="badge">Lieux: {compactList(selectedLocationLabels)}</span>
          ) : null}
          {selectedProfessorLabels.length > 0 ? (
            <span className="badge">Professeurs: {compactList(selectedProfessorLabels)}</span>
          ) : null}
          {selectedClientLabels.length > 0 ? (
            <span className="badge">Etudiants: {compactList(selectedClientLabels)}</span>
          ) : null}
          {selectedStatus !== "ALL" ? <span className="badge">Statut cours: {selectedStatus}</span> : null}
          {selectedClientStatus !== "ALL" ? <span className="badge">Statut adherent: {selectedClientStatus}</span> : null}
          {!hasAdvancedFilters ? (
            <span className="muted">Aucun filtre avance actif.</span>
          ) : null}
        </div>
      </section>

      {filtersOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact planning-filters-modal">
            <a className="modal-close-x" href={filtersCloseHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Filtres planning</h2>
            <p className="muted">Vous pouvez filtrer sur plusieurs lieux, professeurs et etudiants.</p>
            <form method="get" className="grid cols-2">
              <input type="hidden" name="location_id" value={focusedLocationId} />
              <input type="hidden" name="agenda_view" value={agendaView} />
              <input type="hidden" name="agenda_date" value={agendaDate} />
              <input type="hidden" name="timezone" value={timezone} />
              {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

              <label className="span-2">
                Type de cours
                <select name="course_type_id" defaultValue={selectedCourseType}>
                  <option value="">Tous</option>
                  {courseTypes.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>

              <SearchMultiSelect
                className="span-2"
                label="Par activites"
                name="activity_ids"
                options={courseTypes.map((row) => ({ id: row.id, label: row.name }))}
                selectedIds={selectedActivityIds}
                placeholder="Rechercher une activite..."
                emptySelectionLabel="Aucune activite selectionnee."
              />

              <SearchMultiSelect
                label="Par salles"
                name="location_ids"
                options={locationFilterOptions}
                selectedIds={selectedLocationIdsFromQuery}
                placeholder="Rechercher une salle..."
                emptySelectionLabel="Aucune salle selectionnee."
              />

              <SearchMultiSelect
                label="Par enseignants"
                name="professor_ids"
                options={professorFilterOptions}
                selectedIds={selectedProfessorIds}
                placeholder="Rechercher un enseignant..."
                emptySelectionLabel="Aucun enseignant selectionne."
              />

              <SearchMultiSelect
                className="span-2"
                label="Par etudiants"
                name="client_ids"
                options={clientFilterOptions}
                selectedIds={selectedClientIds}
                placeholder="Rechercher un etudiant..."
                emptySelectionLabel="Aucun etudiant selectionne."
              />

              <label>
                Statut cours
                <select name="status" defaultValue={selectedStatus}>
                  <option value="ALL">Tous</option>
                  <option value="SCHEDULED">SCHEDULED</option>
                  <option value="CANCELLED">CANCELLED</option>
                  <option value="COMPLETED">COMPLETED</option>
                </select>
              </label>

              <label>
                Statut adherent
                <select name="client_status" defaultValue={selectedClientStatus}>
                  <option value="ALL">Tous</option>
                  <option value="ACTIVE">ACTIF</option>
                  <option value="TRIAL">ESSAI</option>
                  <option value="PENDING">EN ATTENTE</option>
                  <option value="INACTIVE">INACTIF</option>
                  <option value="ARCHIVED">ARCHIVE</option>
                </select>
              </label>

              <div className="row span-2">
                <button type="submit">Appliquer</button>
                <a className="reset-link" href={filtersResetHref}>
                  Reinitialiser
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {createOpen && !filtersOpen && !selectedDayDetails && !selectedSession ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-create-session">
            <a className="modal-close-x" href={createCloseHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Ajouter un creneau</h2>
            <p className="muted">Un creneau est sur un seul jour local. Capacite requise (defaut: 1).</p>
            {(okMessage || errorMessage) ? (
              <section className="modal-overlay modal-overlay-front">
                <article className="modal-panel modal-compact">
                  <a className="modal-close-x" href={errorMessage ? createFeedbackDismissHref : createCloseHref} aria-label="Fermer">
                    ×
                  </a>
                  <h3 className="modal-title">{errorMessage ? "Creation impossible" : "Creation terminee"}</h3>
                  {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
                  {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
                  <div className="row modal-actions-end">
                    {errorMessage ? (
                      <a className="ghost" href={createFeedbackDismissHref}>
                        Corriger la saisie
                      </a>
                    ) : null}
                    <a className="mode-link" href={createCloseHref}>
                      Fermer
                    </a>
                  </div>
                </article>
              </section>
            ) : null}
            <form action={createAdminSessionAction} className="create-session-form">
              <input type="hidden" name="return_to" value={createHref} />
              <section className="create-session-section">
                <div className="row spread">
                  <h3 className="create-session-section-title">Informations principales</h3>
                  <span className="badge">Obligatoire</span>
                </div>
                <SessionCreateMainFields
                  courseTypes={courseTypes.map((row) => ({
                    id: row.id,
                    name: row.name,
                    durationMinutes: row.duration_minutes,
                    defaultCapacity: row.default_capacity,
                    requiresProfessor: row.requires_professor,
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
                <legend>Recurrence</legend>
                <div className="recurrence-mode-row">
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="NONE" defaultChecked={createRecurrenceMode === "NONE"} />
                    Evenement unique
                  </label>
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="RECURRING" defaultChecked={createRecurrenceMode === "RECURRING"} />
                    Evenement recurrent
                  </label>
                </div>

                <div className="recurrence-settings">
                  <div className="grid cols-3 recurrence-grid">
                    <label>
                      Frequence
                      <select name="recurrence_frequency" defaultValue={createRecurrenceFrequency}>
                        <option value="DAILY">Journaliere</option>
                        <option value="WEEKLY">Hebdomadaire</option>
                        <option value="MONTHLY">Mensuelle</option>
                      </select>
                    </label>

                    <label>
                      Se repete chaque
                      <input type="number" name="recurrence_interval" min={1} defaultValue={createRecurrenceInterval} />
                      <small className="muted">Ex: 2 pour toutes les 2 semaines.</small>
                    </label>

                    <label>
                      Repeter jusqu au
                      <input type="date" name="recurrence_until_date" defaultValue={createDraft?.recurrence_until_date || ""} />
                    </label>
                  </div>
                  <p className="muted">La recurrence est creee jusqu a la date de fin incluse.</p>
                </div>
              </fieldset>

              <section className="create-session-section">
                <h3 className="create-session-section-title">Visibilite et descriptions</h3>
                <div className="grid cols-2 create-session-visibility-grid">
                  <SessionVisibilityFields
                    initialIsPrivate={createInitialIsPrivate}
                    initialAllowOnlineBooking={createInitialAllowOnlineBooking}
                  />

                  <label>
                    Description publique (vue client)
                    <textarea name="public_description" rows={4} defaultValue={createDraft?.public_description || ""} />
                  </label>

                  <label>
                    Description privee (interne)
                    <textarea name="private_description" rows={4} defaultValue={createDraft?.private_description || ""} />
                  </label>

                  <label className="span-2">
                    Note pour le professeur (envoyee 24h avant)
                    <RichMessageEditor
                      name="professor_reminder_note"
                      formatName="professor_reminder_note_format"
                      rows={6}
                      maxLength={12000}
                      defaultFormat="HTML"
                      defaultValue={createDraft?.professor_reminder_note || ""}
                      placeholder="Saisir la note a joindre au rappel professeur..."
                    />
                  </label>
                </div>
              </section>

              <div className="row spread create-session-actions">
                <p className="muted">Les champs obligatoires sont marques en haut du formulaire.</p>
                <div className="row">
                  <a className="reset-link" href={createCloseHref}>
                    Annuler
                  </a>
                  <button type="submit">Creer le creneau</button>
                </div>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      <section className="card">
        <div className="row spread">
          <h2>Agenda</h2>
          <div className="row">
            <a className="mode-link" href={previousHref}>
              ←
            </a>
            <span className="badge">{agendaRange.title}</span>
            <a className="mode-link" href={nextHref}>
              →
            </a>
            <a className="mode-link" href={todayHref}>
              Aujourd&apos;hui
            </a>
          </div>
        </div>
        <p className="muted">{agendaNavigationHint(agendaView)}</p>

        <div className={`agenda-grid agenda-grid-${agendaView}`}>
          {agendaDayCards.map((day) => (
            <MonthDayCard
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
        dayLabel={selectedDayDetails ? agendaDayLongLabel(selectedDayDetails.key) : ""}
        events={selectedDayDetails ? selectedDayDetails.events : []}
        closeHref={dayDetailsCloseHref}
        openSessionHref={(sessionId) => withSessionInHref(sessionModalBaseHref, sessionId)}
      />

      {selectedSession && !editSessionOpen ? (
        <ModalA11yFrame className="modal-overlay session-slot-overlay" closeHref={baseHref} label="Detail du creneau">
          <article className="modal-panel session-slot-modal">
            <header className="session-slot-header">
              <div className="session-slot-header-main">
                <h2 className="modal-title session-slot-title">{selectedSessionHeaderTitle}</h2>
                <p className="muted session-slot-subtitle">{selectedSessionSubtitle}</p>
              </div>
              <div className="session-slot-header-actions">
                <span className={`status-badge ${statusClass(selectedSession.status)}`}>{selectedSession.status_label}</span>
                <details className="session-slot-overflow-menu">
                  <summary aria-label="Plus d options">⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <p className="muted">Actions</p>
                    <a className="mode-link" href={attendanceModalHref}>
                      Prendre les presences
                    </a>
                    <a className="mode-link" href={groupNotesModalHref}>
                      Note de groupe
                    </a>
                    <a className="mode-link" href={sessionEmailModalHref}>
                      Envoyer email
                    </a>
                    <a className="mode-link" href={sessionSmsModalHref}>
                      Envoyer SMS
                    </a>
                    <a className="mode-link" href={duplicateModalHref}>
                      Dupliquer
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      Supprimer le creneau
                    </a>
                    <hr />
                    <p className="muted">Infos</p>
                    <span className="badge">Professeur: {selectedEffectiveProfessorName}</span>
                    {selectedSessionIsSubstituted ? <span className="badge">Remplacant</span> : null}
                    <span className="badge">{selectedSession.allow_online_booking ? "Reservation en ligne: oui" : "Reservation en ligne: non"}</span>
                    {selectedSession.is_private ? <span className="badge">Prive</span> : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={baseHref} aria-label="Fermer">
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
            </div>

            <div className="session-slot-toolbar">
              <a className="mode-link" href={editSessionHref}>
                Modifier
              </a>
              {selectedSession.status !== "CANCELLED" ? (
                <a className="danger-link" href={cancelConfirmHref}>
                  Annuler
                </a>
              ) : null}
              <details className="session-slot-overflow-menu session-slot-toolbar-menu">
                <summary aria-label="Plus d actions">⋯</summary>
                <div className="session-slot-overflow-panel">
                  <a className="mode-link" href={attendanceModalHref}>
                    Prendre les presences
                  </a>
                  <a className="mode-link" href={groupNotesModalHref}>
                    Note de groupe
                  </a>
                  <a className="mode-link" href={sessionEmailModalHref}>
                    Envoyer email
                  </a>
                  <a className="mode-link" href={sessionSmsModalHref}>
                    Envoyer SMS
                  </a>
                  <a className="mode-link" href={duplicateModalHref}>
                    Dupliquer
                  </a>
                  <a className="danger-link" href={deleteConfirmHref}>
                    Supprimer
                  </a>
                </div>
              </details>
            </div>

            <div className="session-slot-body">
              <details className="session-slot-section session-slot-section-attendees" open>
                <summary>Inscrits ({selectedSessionBookings.length})</summary>
                <div className="session-slot-section-body">
                  {selectedSessionBookings.length === 0 ? (
                    <p className="muted">Aucun eleve inscrit.</p>
                  ) : (
                    <div className="session-bookings-summary-list session-slot-attendees-list">
                      {selectedSessionBookings.map((booking, index) => {
                        const presence = bookingPresenceLabel(booking.status);
                        const enrollment = bookingEnrollmentLabel(booking.status);
                        return (
                          <article key={booking.id} className="session-slot-attendee-row">
                            <div className="session-slot-attendee-identity">
                              {booking.client_id ? (
                                <Link
                                  className="client-name-link"
                                  href={`/admin/clients/${booking.client_id}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  title="Ouvrir la fiche client dans un nouvel onglet"
                                >
                                  {booking.client_display_name || `Participant ${index + 1}`}
                                </Link>
                              ) : (
                                <strong>{booking.client_display_name || `Participant ${index + 1}`}</strong>
                              )}
                              <small className="muted">{booking.client_email}</small>
                            </div>
                            <div className="session-slot-attendee-badges">
                              <span className={`status-pill ${statusClass(booking.status)}`}>
                                {enrollment}
                                {booking.waitlist_position ? ` #${booking.waitlist_position}` : ""}
                              </span>
                              <span className={`status-pill ${presence ? "status-ok" : "status-off"}`}>{presence ?? "Presence: -"}</span>
                            </div>
                            <div className="session-slot-attendee-actions">
                              <a className="mode-link" href={attendanceBookingHref(booking.id)}>
                                Presence & note
                              </a>
                              {isBookingRemovable(selectedSession, booking) ? (
                                <details className="session-slot-inline-confirm">
                                  <summary className="session-slot-delete-icon" aria-label="Retirer cet inscrit" title="Retirer cet inscrit">
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
                                          Cette seance
                                        </label>
                                        <label className="checkline">
                                          <input type="radio" name="scope" value="SERIES_FUTURE" />
                                          Serie future
                                        </label>
                                      </fieldset>
                                    ) : (
                                      <input type="hidden" name="scope" value="OCCURRENCE" />
                                    )}
                                    <button className="danger" type="submit">
                                      Confirmer
                                    </button>
                                  </form>
                                </details>
                              ) : (
                                <span className="muted">Verrouille</span>
                              )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                  {selectedSession.group_note ? (
                    <p className="muted top-gap-sm">
                      <strong>Note de groupe:</strong> {stripHtml(selectedSession.group_note)}
                    </p>
                  ) : null}
                </div>
              </details>

              <aside className="session-slot-right">
                <details className="session-slot-section session-slot-section-enroll" open>
                  <summary>Inscrire un eleve</summary>
                  <div className="session-slot-section-body">
                    <form action={adminAddClientToSessionAction} className="session-enroll-form">
                      <input type="hidden" name="session_id" value={selectedSession.id} />
                      <input type="hidden" name="return_to" value={modalHref} />

                      <SearchMultiSelect
                        className="session-enroll-search"
                        label="Eleve"
                        name="client_id"
                        options={bookingClientOptions}
                        selectedIds={[]}
                        placeholder="Rechercher un eleve..."
                        emptySelectionLabel="Aucun eleve selectionne."
                        maxSelections={1}
                        requiredSelection
                      />

                      <div className="session-enroll-submit">
                        {selectedSession.recurrence_group_id ? (
                          <details className="session-slot-add-confirm">
                            <summary>Ajouter</summary>
                            <div className="session-slot-inline-confirm-panel session-slot-scope-panel">
                              <p className="muted">Inscrire l eleve sur cette seance ou sur la serie future ?</p>
                              <label className="checkline">
                                <input type="radio" name="scope" value="OCCURRENCE" defaultChecked />
                                Cette seance uniquement
                              </label>
                              <label className="checkline">
                                <input type="radio" name="scope" value="SERIES_FUTURE" />
                                Toute la serie (futures)
                              </label>
                              <button type="submit">Confirmer</button>
                            </div>
                          </details>
                        ) : (
                          <>
                            <input type="hidden" name="scope" value="OCCURRENCE" />
                            <button type="submit">Ajouter</button>
                          </>
                        )}
                      </div>
                    </form>
                  </div>
                </details>

                <details className="session-slot-section session-slot-section-details" open>
                  <summary>Details</summary>
                  <div className="session-slot-section-body session-slot-details-list">
                    <p className="muted">
                      <strong>Activite:</strong> {selectedCourseTypeName}
                    </p>
                    <p className="muted">
                      <strong>Professeur habituel:</strong> {selectedHabitualProfessorName}
                    </p>
                    <p className="muted">
                      <strong>Professeur remplacant:</strong> {selectedSubstituteProfessorName || "Aucun"}
                    </p>
                    <p className="muted">
                      <strong>Professeur effectif:</strong> {selectedEffectiveProfessorName}
                    </p>
                    <p className="muted">
                      <strong>Lieu:</strong> {selectedLocationName}
                    </p>
                    {selectedSessionZoomLink ? (
                      <p>
                        <a href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                          Lien Zoom
                        </a>
                      </p>
                    ) : null}
                    {selectedSession.public_description ? (
                      <p className="muted">
                        <strong>Description publique:</strong> {selectedSession.public_description}
                      </p>
                    ) : null}
                    {selectedSession.private_description ? (
                      <p className="muted">
                        <strong>Description privee:</strong> {selectedSession.private_description}
                      </p>
                    ) : null}
                    {selectedSession.professor_reminder_note ? (
                      <p className="muted">
                        <strong>Note professeur (rappel 24h):</strong> {stripHtml(selectedSession.professor_reminder_note)}
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
                <h2 className="modal-title">Modifier le creneau</h2>
                <p className="muted">
                  {formatDate(selectedSession.start_at_utc, selectedSession.timezone)} · {selectedLocationName} · Horaire enregistre: {sessionTimeRangeLabel(selectedSession)}
                </p>
              </div>
              <div className="session-edit-shell-header-actions">
                <details className="session-slot-overflow-menu">
                  <summary aria-label="Actions secondaires">⋯</summary>
                  <div className="session-slot-overflow-panel">
                    <a className="mode-link" href={duplicateModalHref}>
                      Dupliquer le creneau
                    </a>
                    <a className="danger-link" href={deleteConfirmHref}>
                      Supprimer le creneau
                    </a>
                    {selectedSessionZoomLink ? (
                      <a className="mode-link" href={selectedSessionZoomLink} target="_blank" rel="noreferrer">
                        Copier lien Zoom
                      </a>
                    ) : null}
                  </div>
                </details>
                <a className="modal-close-x session-slot-close" href={modalHref} aria-label="Fermer">
                  ×
                </a>
              </div>
            </header>

            {okMessage ? <section className="flash-ok modal-flash">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err modal-flash">{errorMessage}</section> : null}

            <form action={updateAdminSessionAction} className="session-edit-shell-form" noValidate>
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={activeEditTabHref} />
              <input type="hidden" name="has_recurrence_group" value={selectedSession.recurrence_group_id ? "1" : "0"} />

              <nav className="session-edit-tabs" aria-label="Sections modification creneau">
                <a className={`session-edit-tab ${editTab === "general" ? "active" : ""}`} href={editTabHref("general")}>
                  <span>General</span>
                  <small>{selectedEffectiveProfessorName} · {selectedSession.capacity_max} places</small>
                </a>
                <a className={`session-edit-tab ${editTab === "schedule" ? "active" : ""}`} href={editTabHref("schedule")}>
                  <span>Horaire & recurrence</span>
                  <small>Enregistre: {sessionTimeRangeLabel(selectedSession)}</small>
                </a>
                <a className={`session-edit-tab ${editTab === "visibility" ? "active" : ""}`} href={editTabHref("visibility")}>
                  <span>Visibilite</span>
                  <small>{selectedSession.is_private ? "Prive" : "Public"}</small>
                </a>
                <a className={`session-edit-tab ${editTab === "notes" ? "active" : ""}`} href={editTabHref("notes")}>
                  <span>Notes & messages</span>
                  <small>{selectedSession.professor_reminder_note ? "Renseignee" : "Vide"}</small>
                </a>
              </nav>

              <div className="session-edit-shell-body">
                <section className={`session-edit-panel ${editTab === "general" ? "active" : ""}`}>
                  <div className="grid cols-2">
                    <label>
                      Titre
                      <input type="text" name="title" defaultValue={selectedSession.title} required />
                    </label>

                    <label>
                      Type de cours
                      <select name="course_type_id" defaultValue={selectedSession.course_type_id} required>
                        {courseTypes.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Lieu
                      <select name="location_id" defaultValue={selectedSession.location_id} required>
                        {locations.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Coach
                      <select name="professor_id" defaultValue={selectedSession.professor_id ?? ""}>
                        <option value="">Sans professeur</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Professeur remplacant (occurrence)
                      <select name="substitute_teacher_id" defaultValue={selectedSession.substitute_teacher_id ?? ""}>
                        <option value="">Aucun remplacant</option>
                        {professors.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.first_name} {row.last_name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Capacite max
                      <input type="number" name="capacity_max" min={0} defaultValue={selectedSession.capacity_max} />
                    </label>

                    <label>
                      Statut
                      <select name="status" defaultValue={selectedSession.status}>
                        <option value="SCHEDULED">Planifie</option>
                        <option value="COMPLETED">Termine</option>
                        <option value="CANCELLED">Annule</option>
                      </select>
                    </label>

                    <label className="session-edit-span">
                      Lien Zoom
                      <input type="url" name="zoom_link" defaultValue={selectedSession.zoom_link ?? ""} />
                    </label>

                    <label className="session-edit-span">
                      Note remplaçant (optionnel)
                      <textarea name="substitute_note" rows={2} defaultValue={selectedSession.substitute_note ?? ""} />
                    </label>
                  </div>
                </section>

                <section className={`session-edit-panel ${editTab === "schedule" ? "active" : ""}`}>
                  <div className="grid cols-2">
                    <label>
                      Jour debut
                      <input
                        type="date"
                        name="start_date"
                        defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                        required
                      />
                    </label>

                    <label>
                      Portee modification
                      <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                        <option value="ONE">Cette occurrence</option>
                        {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">Serie future</option> : null}
                        {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">Toute la serie</option> : null}
                      </select>
                    </label>

                    <label className="checkline session-edit-span">
                      <input type="checkbox" name="is_all_day" defaultChecked={selectedSession.is_all_day} />
                      Creneau sur toute la journee
                    </label>

                    <details className="session-edit-collapsible session-edit-span">
                      <summary>Options avancees</summary>
                      <label>
                        Fuseau horaire du creneau
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
                      labelClassName="session-time-field"
                      defaultStartTime={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                      defaultEndTime={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                      defaultDurationMinutes={sessionDurationMinutes(selectedSession)}
                      requiredStart
                    />
                    <p className="muted session-edit-span">
                      L'entete affiche l'horaire enregistre. Les champs ci-dessus montrent vos modifications en cours avant enregistrement.
                    </p>
                  </div>

                  <fieldset className="session-edit-span recurrence-panel">
                    <legend>Recurrence</legend>
                    <div className="recurrence-mode-row">
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="NONE" defaultChecked />
                        Ne pas modifier la recurrence
                      </label>
                      <label className="checkline">
                        <input type="radio" name="recurrence_mode" value="RECURRING" />
                        Modifier la recurrence
                      </label>
                    </div>
                    <div className="recurrence-settings">
                      <div className="grid cols-3 recurrence-grid">
                        <label>
                          Frequence
                          <select name="recurrence_frequency" defaultValue={editRecurrenceDefaults.frequency}>
                            <option value="DAILY">Journaliere</option>
                            <option value="WEEKLY">Hebdomadaire</option>
                            <option value="MONTHLY">Mensuelle</option>
                          </select>
                        </label>
                        <label>
                          Se repete chaque
                          <input type="number" name="recurrence_interval" min={1} defaultValue={editRecurrenceDefaults.interval} />
                          <small className="muted">Ex: 2 pour toutes les 2 semaines.</small>
                        </label>
                        <label>
                          Repeter jusqu au
                          <input type="date" name="recurrence_until_date" defaultValue={editRecurrenceUntilDate} />
                        </label>
                      </div>
                      {selectedSession.recurrence_group_id ? (
                        <p className="muted">
                          Serie existante: pour changer la recurrence, choisir la portee <strong>Serie future</strong> ou <strong>Toute la serie</strong>.
                        </p>
                      ) : (
                        <p className="muted">Activez la modification recurrence pour convertir ce creneau ponctuel.</p>
                      )}
                    </div>
                  </fieldset>
                </section>

                <section className={`session-edit-panel ${editTab === "visibility" ? "active" : ""}`}>
                  <div className="grid cols-2">
                    <SessionVisibilityFields
                      initialIsPrivate={selectedSession.is_private}
                      initialAllowOnlineBooking={selectedSession.allow_online_booking}
                    />
                  </div>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.public_description)}>
                    <summary>Description publique (optionnel)</summary>
                    <label>
                      Description publique (vue client)
                      <textarea name="public_description" rows={4} defaultValue={selectedSession.public_description ?? ""} />
                    </label>
                  </details>

                  <details className="session-edit-collapsible" open={Boolean(selectedSession.private_description)}>
                    <summary>Description privee (optionnel)</summary>
                    <label>
                      Description privee (interne)
                      <textarea name="private_description" rows={4} defaultValue={selectedSession.private_description ?? ""} />
                    </label>
                  </details>
                </section>

                <section className={`session-edit-panel ${editTab === "notes" ? "active" : ""}`}>
                  <div className="row spread">
                    <p className="muted">Note pour le professeur (envoyee 24h avant).</p>
                    {notesAdvancedMode ? (
                      <a className="mode-link" href={notesSimpleHref}>
                        Mode simple
                      </a>
                    ) : (
                      <a className="mode-link" href={notesAdvancedHref}>
                        Mode avance
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
                      placeholder="Saisir la note a joindre au rappel professeur..."
                    />
                  ) : (
                    <label className="session-edit-span">
                      Message
                      <textarea
                        name="professor_reminder_note"
                        rows={6}
                        defaultValue={selectedSession.professor_reminder_note ?? ""}
                        placeholder="Saisir la note a joindre au rappel professeur..."
                      />
                    </label>
                  )}
                </section>
              </div>

              <footer className="session-edit-shell-footer">
                <a className="reset-link" href={modalHref}>
                  Annuler
                </a>
                <button type="submit">Enregistrer</button>
              </footer>
            </form>

            {editTab === "schedule" ? (
              <form action={shiftAdminSessionAction} className="row quick-shift-row">
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={activeEditTabHref} />
                <input type="hidden" name="current_start_at_utc" value={toDateTimeLocalUtcValue(selectedSession.start_at_utc)} />
                <input type="hidden" name="current_end_at_utc" value={toDateTimeLocalUtcValue(selectedSession.end_at_utc)} />

                <label className="scope-inline compact">
                  Ajustement rapide
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">Cette occurrence</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">Serie future</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">Toute la serie</option> : null}
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
            ) : null}
          </article>
        </section>
      ) : null}

      {selectedSession && attendanceModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel session-attendance-modal-v2">
            <header className="note-modal-header">
              <div className="note-modal-header-main">
                <h2 className="modal-title">Presences</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone)} · {sessionTimeRangeLabel(selectedSession)} · {selectedLocationName}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <span className="status-badge status-waitlist">
                  {focusedAttendanceBooking ? `Eleve ${focusedAttendanceIndex + 1}/${attendanceBookings.length || 1}` : `Eleve 0/${attendanceBookings.length || 0}`}
                </span>
                <span className="status-badge status-scheduled">Restant {attendanceMissingCount}</span>
                <a className="modal-close-x" href={modalHref} aria-label="Fermer">
                  ×
                </a>
              </div>
            </header>

            {!selectedSessionHasBookings || !focusedAttendanceBooking ? (
              <section className="note-modal-empty">
                <p className="muted">Aucun eleve inscrit sur ce creneau.</p>
              </section>
            ) : (
              <>
                <div className="attendance-v2-body">
                  <aside className="attendance-v2-list">
                    <div className="attendance-v2-list-filters">
                      <a className={`mode-link ${attendanceFilter === "all" ? "mode-active" : ""}`} href={attendanceFilteredHref("all")}>
                        Tous
                      </a>
                      <a className={`mode-link ${attendanceFilter === "missing" ? "mode-active" : ""}`} href={attendanceFilteredHref("missing")}>
                        Manquants
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
                            <strong>{booking.client_display_name || `Participant ${index + 1}`}</strong>
                            <small className="muted">{bookingEnrollmentLabel(booking.status)}</small>
                          </div>
                          <span className={`status-badge ${attendanceBadgeToneClass(booking.status)}`}>
                            {attendanceChoiceLabel(booking.status)}
                          </span>
                        </a>
                      ))}
                    </div>
                  </aside>

                  <section className="attendance-v2-main">
                    <div className="attendance-v2-main-head">
                      <div>
                        <h3>{focusedAttendanceBooking.client_display_name || "Participant"}</h3>
                        <p className="muted">Completes: {attendanceCompletedCount} / {selectedSessionBookings.length}</p>
                      </div>
                      <div className="attendance-v2-nav-links">
                        {previousAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(previousAttendanceBooking.id)}>
                            ← Precedent
                          </a>
                        ) : null}
                        {nextAttendanceBooking ? (
                          <a className="mode-link" href={attendanceBookingHref(nextAttendanceBooking.id)}>
                            Suivant →
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
                      <p className="muted">Presence non editable pour ce statut.</p>
                    )}

                    <details className="attendance-v2-notes">
                      <summary>Notes (optionnel)</summary>
                      <form action={adminUpdateSessionBookingNoteAction} className="attendance-v2-note-form">
                        <input type="hidden" name="session_id" value={selectedSession.id} />
                        <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                        <input type="hidden" name="student_id" value={focusedAttendanceBooking.client_id} />
                        <input type="hidden" name="student_display_name" value={focusedAttendanceBooking.client_display_name || "Eleve"} />
                        <input type="hidden" name="session_title" value={selectedSession.title} />
                        <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                        <label className="session-edit-span">
                          Message
                          <input type="hidden" name="student_note_format" value="TEXT" />
                          <textarea
                            name="student_note"
                            rows={5}
                            placeholder="Note interne..."
                            defaultValue={stripHtml(focusedAttendanceBooking.student_note ?? "")}
                          />
                        </label>
                        <div className="row">
                          <button type="submit" name="note_action" value="SAVE_INTERNAL" className="ghost">
                            Enregistrer note
                          </button>
                          <button type="submit" name="note_action" value="SEND_PARENTS" className="ghost">
                            Envoyer aux parents
                          </button>
                        </div>
                      </form>
                    </details>
                  </section>
                </div>
                <footer className="note-modal-footer">
                  <a className="reset-link" href={modalHref}>
                    Annuler
                  </a>
                  <div className="row">
                    {canEditAttendance(focusedAttendanceBooking.status) ? (
                      <button type="submit" form="attendance-status-form">
                        Enregistrer & suivant
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
                <h2 className="modal-title">Note de groupe</h2>
                <p className="muted">
                  {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone)} · {sessionTimeRangeLabel(selectedSession)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label="Fermer">
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
                  Contenu
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "recipients" ? "active" : ""}`} href={groupNoteTabHref("recipients")}>
                  Destinataires
                </a>
                <a className={`note-modal-tab ${groupNoteTab === "send" ? "active" : ""}`} href={groupNoteTabHref("send")}>
                  Envoi
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${groupNoteTab === "content" ? "active" : ""}`}>
                  {groupNoteTemplates.length > 0 ? (
                    <label className="session-edit-span">
                      Modele
                      <div className="note-template-row">
                        <select name="group_note_template_id" defaultValue={selectedGroupNoteTemplate?.id ?? ""}>
                          <option value="">Aucun modele</option>
                          {groupNoteTemplates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                        {selectedGroupNoteTemplate ? (
                          <a className="mode-link" href={groupNotesModalClearTemplateHref}>
                            Retirer
                          </a>
                        ) : null}
                      </div>
                    </label>
                  ) : (
                    <div className="session-edit-alert">
                      Aucun modele configure. Ajoutez un modele dans Configuration › Messagerie.
                    </div>
                  )}
                  <div className="row spread">
                    <p className="muted">Contenu de la note</p>
                    {groupNoteAdvancedMode ? (
                      <a className="mode-link" href={groupNoteSimpleHref}>
                        Mode simple
                      </a>
                    ) : (
                      <a className="mode-link" href={groupNoteAdvancedHref}>
                        Mode avance
                      </a>
                    )}
                  </div>
                  {groupNoteAdvancedMode ? (
                    <RichMessageEditor
                      name="group_note"
                      formatName="group_note_format"
                      rows={10}
                      maxLength={12000}
                      placeholder="Saisir une note de groupe..."
                      defaultValue={groupNotePrefill}
                    />
                  ) : (
                    <label className="session-edit-span">
                      Message
                      <input type="hidden" name="group_note_format" value="TEXT" />
                      <textarea name="group_note" rows={8} defaultValue={stripHtml(groupNotePrefill)} />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "recipients" ? "active" : ""}`}>
                  <fieldset className="note-destination-radios">
                    <legend>Destination</legend>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PRIVATE" defaultChecked={groupNoteDestination === "PRIVATE"} />
                      Interne
                    </label>
                    <label className="checkline">
                      <input
                        type="radio"
                        name="note_destination"
                        value="STUDENTS_AND_PARENTS"
                        defaultChecked={groupNoteDestination === "STUDENTS_AND_PARENTS"}
                      />
                      Parents / eleves
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PARENTS" defaultChecked={groupNoteDestination === "PARENTS"} />
                      Parents uniquement
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="STUDENTS" defaultChecked={groupNoteDestination === "STUDENTS"} />
                      Eleves uniquement
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="PROFESSOR" defaultChecked={groupNoteDestination === "PROFESSOR"} />
                      Professeur
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="ADMINS" defaultChecked={groupNoteDestination === "ADMINS"} />
                      Administration
                    </label>
                    <label className="checkline">
                      <input type="radio" name="note_destination" value="SELF" defaultChecked={groupNoteDestination === "SELF"} />
                      Moi-meme
                    </label>
                  </fieldset>

                  <div className="note-recipient-summary">
                    <strong>{sessionRecipientStudentIds.length} eleve(s) selectionne(s)</strong>
                    <span className="muted">{sessionRecipientSummary || "Aucun eleve"}</span>
                  </div>
                  <details className="note-recipient-picker" open={isGroupNoteStudentAudience}>
                    <summary>Modifier la selection</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label="Eleves inclus"
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder="Rechercher un eleve..."
                      emptySelectionLabel={selectedSessionHasBookings ? "Aucun eleve selectionne." : "Aucun eleve inscrit sur ce creneau."}
                    />
                  </details>
                  {!selectedSessionHasBookings && isGroupNoteStudentAudience ? (
                    <p className="flash-err">Aucun eleve inscrit sur ce creneau pour une diffusion Etudiants/Parents.</p>
                  ) : null}
                </section>

                <section className={`note-modal-panel ${groupNoteTab === "send" ? "active" : ""}`}>
                  {groupNoteDestination === "PRIVATE" ? (
                    <p className="muted">Destination interne: aucun envoi externe n est effectue.</p>
                  ) : (
                    <>
                      <label className="checkline">
                        <input type="checkbox" name="send_to_self" />
                        M envoyer aussi une copie
                      </label>
                      <label>
                        Sujet email (optionnel)
                        <input type="text" name="subject" defaultValue={`Note de groupe - ${selectedSession.title}`} maxLength={255} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="confirm_send" />
                        Confirmer l envoi ({sessionRecipientStudentIds.length} destinataire(s) potentiels)
                      </label>
                    </>
                  )}
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  Fermer
                </a>
                <div className="row">
                  <button type="submit" name="note_action" value="SAVE_ONLY" className="ghost">
                    Enregistrer
                  </button>
                  {groupNoteDestination !== "PRIVATE" ? (
                    <button type="submit" name="note_action" value="SEND_EMAIL">
                      Envoyer
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
                <h2 className="modal-title">Envoyer un email</h2>
                <p className="muted">
                  Creneau: {selectedCourseTypeName} · {formatDate(selectedSession.start_at_utc, selectedSession.timezone)} · {formatTime(selectedSession.start_at_utc, selectedSession.timezone)}
                </p>
              </div>
              <div className="note-modal-header-meta">
                <a className="modal-close-x" href={modalHref} aria-label="Fermer">
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
                  Destinataires
                </a>
                <a className={`note-modal-tab ${emailTab === "content" ? "active" : ""}`} href={sessionEmailTabHref("content")}>
                  Contenu
                </a>
                <a className={`note-modal-tab ${emailTab === "send" ? "active" : ""}`} href={sessionEmailTabHref("send")}>
                  Options
                </a>
              </nav>

              <div className="note-modal-body">
                <section className={`note-modal-panel ${emailTab === "recipients" ? "active" : ""}`}>
                  <label>
                    Destinataires
                    <select name="audience" defaultValue={emailAudience}>
                      <option value="STUDENTS">Eleves inscrits</option>
                      <option value="PARENTS">Parents des eleves</option>
                      <option value="STUDENTS_AND_PARENTS">Eleves + parents</option>
                      <option value="PROFESSOR">Professeur</option>
                      <option value="ADMINS">Administration</option>
                      <option value="SELF">Moi-meme</option>
                    </select>
                  </label>
                  <div className="note-recipient-summary">
                    <strong>{sessionRecipientStudentIds.length} destinataire(s) selectionnes</strong>
                    <span className="muted">{sessionRecipientSummary || "Aucun destinataire eleve"}</span>
                  </div>
                  <details className="note-recipient-picker" open={emailAudience === "STUDENTS" || emailAudience === "PARENTS" || emailAudience === "STUDENTS_AND_PARENTS"}>
                    <summary>Modifier</summary>
                    <SearchMultiSelect
                      className="session-edit-span"
                      label="Eleves inclus (vous pouvez en retirer)"
                      name="included_student_ids"
                      options={sessionRecipientStudents}
                      selectedIds={sessionRecipientStudentIds}
                      placeholder="Rechercher un eleve..."
                      emptySelectionLabel="Aucun eleve selectionne."
                    />
                  </details>
                  {!selectedSessionHasBookings ? <p className="muted">Aucun eleve inscrit: utilisez Professeur, Administration ou Moi-meme.</p> : null}
                </section>

                <section className={`note-modal-panel ${emailTab === "content" ? "active" : ""}`}>
                  <label>
                    Sujet
                    <input type="text" name="subject" defaultValue={`Message creneau: ${selectedSession.title}`} maxLength={255} required />
                  </label>
                  <div className="row spread">
                    <p className="muted">Message</p>
                    {emailAdvancedMode ? (
                      <a className="mode-link" href={sessionEmailSimpleHref}>
                        Mode simple
                      </a>
                    ) : (
                      <a className="mode-link" href={sessionEmailAdvancedHref}>
                        Mode avance
                      </a>
                    )}
                  </div>
                  {emailAdvancedMode ? (
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={10}
                      maxLength={12000}
                      defaultValue={`Bonjour,\n\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone)}.\n`}
                      placeholder="Saisir votre message..."
                    />
                  ) : (
                    <label className="session-edit-span">
                      Message
                      <input type="hidden" name="body_format" value="TEXT" />
                      <textarea
                        name="body"
                        rows={8}
                        defaultValue={`Bonjour,\n\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone)}.\n`}
                        placeholder="Saisir votre message..."
                      />
                    </label>
                  )}
                </section>

                <section className={`note-modal-panel ${emailTab === "send" ? "active" : ""}`}>
                  <label className="checkline">
                    <input type="checkbox" name="send_to_self" />
                    M envoyer aussi une copie
                  </label>
                  <label className="session-edit-span">
                    Copie (emails, optionnel)
                    <textarea name="cc_emails" rows={2} placeholder="copie@example.com; autre@example.com" />
                  </label>
                  <label className="checkline">
                    <input type="checkbox" name="confirm_send" />
                    Confirmer l envoi a {sessionRecipientStudentIds.length} destinataire(s)
                  </label>
                </section>
              </div>

              <footer className="note-modal-footer">
                <a className="reset-link" href={modalHref}>
                  Fermer
                </a>
                <div className="row">
                  <button type="submit">Envoyer</button>
                </div>
              </footer>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionSmsModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact session-group-notes-modal">
            <a className="modal-close-x" href={modalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Envoyer un SMS</h2>
            <p className="muted">Envoi groupe pour les eleves ou parents rattaches a ce creneau.</p>
            <form action={adminSendSessionBroadcastAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="channel" value="SMS" />
              <input type="hidden" name="return_to" value={sessionSmsModalHref} />

              <label>
                Destinataires
                <select name="audience" defaultValue="STUDENTS">
                  <option value="STUDENTS">Eleves inscrits</option>
                  <option value="PARENTS">Parents des eleves</option>
                  <option value="STUDENTS_AND_PARENTS">Eleves + parents</option>
                  <option value="PROFESSOR">Professeur</option>
                  <option value="ADMINS">Administration</option>
                  <option value="SELF">Moi-meme</option>
                </select>
              </label>

              <SearchMultiSelect
                className="session-edit-span"
                label="Eleves inclus (vous pouvez en retirer)"
                name="included_student_ids"
                options={sessionRecipientStudents}
                selectedIds={sessionRecipientStudentIds}
                placeholder="Rechercher un eleve..."
                emptySelectionLabel="Aucun eleve selectionne."
              />
              {!selectedSessionHasBookings ? <p className="muted">Aucun eleve inscrit: utilisez Professeur, Administration ou Moi-meme.</p> : null}

              <label className="checkline">
                <input type="checkbox" name="send_to_self" />
                M envoyer aussi une copie
              </label>

              <label>
                Sujet (optionnel)
                <input type="text" name="subject" defaultValue={`Information creneau: ${selectedSession.title}`} maxLength={255} />
              </label>

              <label className="session-edit-span">
                Copie (telephones, separes par virgule/point-virgule/retour ligne)
                <textarea name="cc_phone_numbers" rows={2} placeholder="+33600000000; 0600000000" />
              </label>

              <label className="session-edit-span">
                Message SMS
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  defaultFormat="TEXT"
                  rows={8}
                  maxLength={12000}
                  defaultValue={`Bonjour,\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone)}.`}
                  placeholder="Saisir votre message SMS..."
                />
              </label>

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  Annuler
                </a>
                <button type="submit">Envoyer le SMS</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && duplicateModalOpen ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={modalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Dupliquer le creneau</h2>
            <p className="muted">
              Definir la date cible et l heure de debut. Les eleves rattaches au creneau seront dupliques automatiquement.
            </p>

            <form action={duplicateAdminSessionAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={duplicateModalHref} />
              <input type="hidden" name="session_timezone" value={selectedSession.timezone} />

              <div className="grid cols-2">
                <label>
                  Date cible
                  <input
                    type="date"
                    name="target_date"
                    defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                    required
                  />
                </label>
                <label>
                  Heure de debut
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
                  <legend>Portee de duplication</legend>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="ONE" defaultChecked />
                    Dupliquer ce creneau uniquement
                  </label>
                  <label className="checkline">
                    <input type="radio" name="apply_scope" value="SERIES_FUTURE" />
                    Dupliquer ce creneau et les occurrences recurrentes suivantes
                  </label>
                </fieldset>
              ) : (
                <>
                  <input type="hidden" name="apply_scope" value="ONE" />
                  <p className="muted">Creneau ponctuel: duplication d un seul creneau.</p>
                </>
              )}

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  Annuler
                </a>
                <button type="submit">Dupliquer le creneau</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && confirmAction ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-confirm-operation">
            <a className="modal-close-x" href={confirmCloseHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">{confirmAction === "delete" ? "Confirmer la suppression" : "Confirmer l'annulation"}</h2>
            <p className="muted">
              {confirmAction === "delete"
                ? "Le creneau sera supprime du calendrier. Vous pouvez notifier les eleves inscrits et le professeur."
                : "Le creneau restera visible au calendrier avec le statut CANCELLED. Vous pouvez notifier les eleves inscrits et le professeur."}
            </p>

            <form action={confirmAction === "delete" ? deleteAdminSessionAction : cancelAdminSessionAction} className="grid">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={modalHref} />
              {confirmAction === "delete" && selectedSession.recurrence_group_id ? (
                <label className="session-edit-span">
                  Supprimer toutes les occurrences a partir de ce creneau ?
                  <select name="delete_following" defaultValue="no">
                    <option value="no">Non, supprimer uniquement ce creneau</option>
                    <option value="yes">Oui, supprimer ce creneau et toutes les occurrences suivantes</option>
                  </select>
                </label>
              ) : (
                <label>
                  Portee
                  <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                    <option value="ONE">Ce creneau</option>
                    {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">Serie future</option> : null}
                    {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">Toute la serie</option> : null}
                  </select>
                </label>
              )}

              <p className="muted span-3">
                Professeur cible: <strong>{selectedEffectiveProfessorName}</strong>
              </p>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_students" />
                Envoyer un message a tous les eleves inscrits
              </label>

              <label>
                Sujet eleves
                <input
                  type="text"
                  name="students_subject"
                  defaultValue={`${confirmAction === "delete" ? "Suppression" : "Annulation"} du creneau: ${selectedSession.title}`}
                  maxLength={255}
                />
              </label>

              <label className="session-edit-span">
                Message eleves
                <RichMessageEditor
                  name="students_message"
                  formatName="students_format"
                  rows={8}
                  maxLength={12000}
                  defaultValue={
                    confirmAction === "delete"
                      ? `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone)} a ete supprime.\n\nPiano Academie`
                      : `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc, selectedSession.timezone)} a ete annule.\n\nPiano Academie`
                  }
                  placeholder="Message eleves"
                />
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="notify_professor" />
                Envoyer un message au professeur selectionne
              </label>

              <label className="checkline span-3">
                <input type="checkbox" name="professor_same_as_students" defaultChecked />
                Utiliser le meme sujet/message que pour les eleves
              </label>

              <label>
                Sujet professeur (si message distinct)
                <input type="text" name="professor_subject" maxLength={255} />
              </label>

              <label className="session-edit-span">
                Message professeur (si message distinct)
                <RichMessageEditor
                  name="professor_message"
                  formatName="professor_format"
                  rows={8}
                  maxLength={12000}
                  placeholder="Message professeur"
                />
              </label>

              <div className="row quick-actions-row">
                <button className="danger" type="submit">
                  {confirmAction === "delete" ? "Confirmer la suppression" : "Confirmer l'annulation"}
                </button>
                <a className="reset-link" href={confirmCloseHref}>
                  Retour
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
