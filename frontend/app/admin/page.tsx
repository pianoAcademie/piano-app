import Link from "next/link";
import { cookies } from "next/headers";
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
import { backendRequest } from "../../lib/backend";
import AutoSubmitSelect from "../../components/auto-submit-select";
import RichMessageEditor from "../../components/rich-message-editor";
import SearchMultiSelect from "../../components/search-multi-select";
import SessionTimeFields from "../../components/session-time-fields";
import SessionVisibilityFields from "../../components/session-visibility-fields";
import type {
  AdminClientOut,
  AdminProfessorOut,
  AdminSessionBookingOut,
  AdminSessionOut,
  CourseTypeOut,
  LocationOut,
} from "../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type AgendaView = "month" | "week" | "day";
type ApplyScope = "ONE" | "SERIES_FUTURE" | "SERIES_ALL";

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

function formatDate(value: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string): string {
  const parsed = safeDate(value);
  if (!parsed) {
    return "--:--";
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
  return `${formatTime(session.start_at_utc)} - ${formatTime(session.end_at_utc)}`;
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

function recurrenceLabel(session: AdminSessionOut): string {
  if (!session.recurrence_rule) {
    return "Ponctuel";
  }
  if (session.recurrence_rule === "DAILY") {
    return "Quotidien";
  }
  if (session.recurrence_rule === "WEEKLY") {
    return "Hebdo";
  }
  if (session.recurrence_rule === "MONTHLY") {
    return "Mensuel";
  }
  return session.recurrence_rule;
}

function defaultApplyScope(session: AdminSessionOut): ApplyScope {
  if (session.recurrence_group_id) {
    return "SERIES_FUTURE";
  }
  return "ONE";
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
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const selectedCourseType = readParam(searchParams, "course_type_id");
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
  const filtersOpen = readParam(searchParams, "filters") === "1";
  const createOpen = readParam(searchParams, "create") === "1";
  const dayDetailsRaw = readParam(searchParams, "day_details");
  const dayDetails = isDateKey(dayDetailsRaw) ? dayDetailsRaw : "";
  const selectedSessionId = readParam(searchParams, "session_id");
  const attendanceModalOpen = readParam(searchParams, "attendance") === "1";
  const notesModal = readParam(searchParams, "notes").toLowerCase();
  const groupNotesModalOpen = notesModal === "group";
  const duplicateModalOpen = readParam(searchParams, "duplicate") === "1";
  const messageModalRaw = readParam(searchParams, "message").trim().toLowerCase();
  const sessionEmailModalOpen = messageModalRaw === "email";
  const sessionSmsModalOpen = messageModalRaw === "sms";
  const bookingFocusId = readParam(searchParams, "booking_focus");
  const editSessionOpen = readParam(searchParams, "edit") === "1";
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

  const [locationsResult, professorsResult, sessionsResult, clientsResult] = await Promise.all([
    backendRequest<LocationOut[]>("/api/v1/locations", {}, token),
    backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors", {}, token),
    backendRequest<AdminSessionOut[]>(sessionsEndpoint, {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?active_only=true&limit=500", {}, token),
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
  const createHref = buildPlanningHref({ ...queryForLinks, createOpen: true, showFilters: false, dayDetails: "" });
  const createCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const baseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const sessionModalBaseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const dayDetailsCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const filtersHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: true, dayDetails: "" });
  const filtersCloseHref = buildPlanningHref({ ...queryForLinks, createOpen: false, showFilters: false, dayDetails: "" });
  const filtersResetHref = buildPlanningHref({
    ...queryForLinks,
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

  const previousHref = buildPlanningHref({ ...queryForLinks, agendaDate: previousAgendaDate, createOpen: false, dayDetails: "" });
  const nextHref = buildPlanningHref({ ...queryForLinks, agendaDate: nextAgendaDate, createOpen: false, dayDetails: "" });
  const todayHref = buildPlanningHref({ ...queryForLinks, agendaDate: todayKeyInTimezone(timezone), createOpen: false, dayDetails: "" });

  const agendaRange = buildAgendaRange(agendaView, agendaDate);
  const fromMs = agendaRange.from.getTime();
  const toMs = agendaRange.to.getTime();

  const courseTypeById = new Map(courseTypes.map((row) => [row.id, row]));
  const locationById = new Map(locations.map((row) => [row.id, row]));
  const professorById = new Map(professors.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));
  const selectedLocationSet = new Set(selectedLocationIds);
  const selectedProfessorSet = new Set(selectedProfessorIds);
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
    Boolean(selectedCourseType) ||
    selectedLocationIdsFromQuery.length > 0 ||
    selectedProfessorIds.length > 0 ||
    selectedClientIds.length > 0 ||
    selectedStatus !== "ALL" ||
    selectedClientStatus !== "ALL";
  const planningTitle =
    selectedLocationLabels.length > 1
      ? `Planning - Multi lieux (${selectedLocationLabels.length})`
      : selectedLocationLabels[0]
        ? `Planning - ${selectedLocationLabels[0]}`
        : focusedLocation?.name
          ? `Planning - ${focusedLocation.name}`
          : "Planning - Tous les lieux";

  const filteredSessions = sessions
    .filter((session) => {
      if (selectedLocationSet.size > 0 && !selectedLocationSet.has(session.location_id)) {
        return false;
      }
      if (selectedCourseType && session.course_type_id !== selectedCourseType) {
        return false;
      }
      if (selectedProfessorSet.size > 0 && !selectedProfessorSet.has(session.professor_id)) {
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
  const selectedDayDetails = dayDetails ? agendaDays.find((day) => day.key === dayDetails) ?? null : null;
  const maxVisibleSessionsByDay = agendaView === "month" ? 4 : agendaView === "week" ? 6 : 24;

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

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const modalHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const attendanceModalHref = selectedSession ? withQueryParam(modalHref, "attendance", "1") : modalHref;
  const groupNotesModalHref = selectedSession ? withQueryParam(modalHref, "notes", "group") : modalHref;
  const duplicateModalHref = selectedSession ? withQueryParam(modalHref, "duplicate", "1") : modalHref;
  const sessionEmailModalHref = selectedSession ? withQueryParam(modalHref, "message", "email") : modalHref;
  const sessionSmsModalHref = selectedSession ? withQueryParam(modalHref, "message", "sms") : modalHref;
  const editSessionHref = selectedSession ? withQueryParam(modalHref, "edit", "1") : modalHref;
  const attendanceBookingHref = (bookingId: string): string => withQueryParam(attendanceModalHref, "booking_focus", bookingId);
  const confirmCloseHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const cancelConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "cancel") : baseHref;
  const deleteConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "delete") : baseHref;
  const focusedAttendanceBooking =
    selectedSessionBookings.find((booking) => booking.id === bookingFocusId) ?? selectedSessionBookings[0] ?? null;
  const selectedSessionHasBookings = selectedSessionBookings.length > 0;
  const focusedAttendanceIndex = focusedAttendanceBooking
    ? selectedSessionBookings.findIndex((booking) => booking.id === focusedAttendanceBooking.id)
    : -1;
  const previousAttendanceBooking =
    focusedAttendanceIndex > 0 ? selectedSessionBookings[focusedAttendanceIndex - 1] : null;
  const nextAttendanceBooking =
    focusedAttendanceIndex >= 0 && focusedAttendanceIndex < selectedSessionBookings.length - 1
      ? selectedSessionBookings[focusedAttendanceIndex + 1]
      : null;
  const selectedCourseTypeName = selectedSession ? courseTypeById.get(selectedSession.course_type_id)?.name ?? "Type non defini" : "";
  const selectedLocationName = selectedSession ? locationById.get(selectedSession.location_id)?.name ?? "Lieu non defini" : "";
  const selectedProfessorDetail = selectedSession ? professorById.get(selectedSession.professor_id) : null;
  const selectedProfessorName = selectedSession
    ? selectedProfessorDetail
      ? `${selectedProfessorDetail.first_name} ${selectedProfessorDetail.last_name}`.trim()
      : "Professeur non defini"
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

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">Erreur backend: {errors.join(" | ")}</section> : null}

      <section className="card">
        <div className="row spread">
          <h2>{planningTitle}</h2>
          <div className="row">
            <a className={`mode-link ${!createOpen ? "mode-active" : ""}`} href={lectureHref}>
              Lecture
            </a>
            <a className={`mode-link ${createOpen ? "mode-active" : ""}`} href={createHref}>
              Ajouter creneau
            </a>
            {focusedLocationId ? (
              <Link className="mode-link" href={`/admin/plannings/${focusedLocationId}/settings`}>
                Parametres
              </Link>
            ) : null}
          </div>
        </div>
        <p className="muted">Cliquez un creneau pour ouvrir la popup de consultation/modification.</p>
      </section>

      <section className="card">
        <div className="row spread planning-toolbar-top">
          <h2>Pilotage planning</h2>
          <a className="mode-link" href={filtersHref}>
            Filtres
          </a>
        </div>
        <form method="get" className="grid cols-4 planning-quick-form">
          <input type="hidden" name="course_type_id" value={selectedCourseType} />
          <input type="hidden" name="status" value={selectedStatus} />
          <input type="hidden" name="client_status" value={selectedClientStatus} />
          <input type="hidden" name="agenda_date" value={agendaDate} />
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
            <a className="reset-link" href={filtersResetHref}>
              Reset filtres
            </a>
          </div>
        </form>
        <p className="muted">Les regles du planning sont visibles uniquement via le bouton Parametres.</p>
        <div className="row planning-active-filters">
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
            <form action={createAdminSessionAction} className="create-session-form">
              <input type="hidden" name="return_to" value={createHref} />
              <section className="create-session-section">
                <div className="row spread">
                  <h3 className="create-session-section-title">Informations principales</h3>
                  <span className="badge">Obligatoire</span>
                </div>
                <div className="grid cols-4 create-session-grid">
                  <label className="span-2">
                    Titre
                    <input type="text" name="title" required maxLength={255} autoFocus />
                  </label>

                  <label>
                    Type de cours
                    <select name="course_type_id" required>
                      <option value="">Selectionner</option>
                      {courseTypes.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Coach
                    <select name="professor_id" required>
                      <option value="">Selectionner</option>
                      {professors.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.first_name} {row.last_name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Lieu
                    <select name="location_id" defaultValue={focusedLocationId || (locations[0]?.id ?? "")} required>
                      {locations.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Fuseau horaire du creneau
                    <select name="session_timezone" defaultValue={timezone} required>
                      {sessionTimezoneOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Jour debut
                    <input type="date" name="start_date" defaultValue={agendaDate} required />
                  </label>

                  <label className="checkline create-session-toggle">
                    <input type="checkbox" name="is_all_day" />
                    Creneau sur toute la journee
                  </label>

                  <SessionTimeFields
                    labelClassName="create-time-field session-time-field"
                    defaultStartTime="12:00"
                    defaultEndTime="13:00"
                    defaultDurationMinutes={60}
                    requiredStart
                  />

                  <label>
                    Capacite max
                    <input type="number" name="capacity_max" min={0} defaultValue={1} required />
                  </label>

                  <label className="span-2">
                    Lien Zoom (optionnel)
                    <input type="url" name="zoom_link" placeholder="https://..." />
                  </label>
                </div>
              </section>

              <fieldset className="create-session-section recurrence-panel">
                <legend>Recurrence</legend>
                <div className="recurrence-mode-row">
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="NONE" defaultChecked />
                    Evenement unique
                  </label>
                  <label className="checkline">
                    <input type="radio" name="recurrence_mode" value="RECURRING" />
                    Evenement recurrent
                  </label>
                </div>

                <div className="recurrence-settings">
                  <div className="grid cols-3 recurrence-grid">
                    <label>
                      Frequence
                      <select name="recurrence_frequency" defaultValue="WEEKLY">
                        <option value="DAILY">Journaliere</option>
                        <option value="WEEKLY">Hebdomadaire</option>
                        <option value="MONTHLY">Mensuelle</option>
                      </select>
                    </label>

                    <label>
                      Se repete chaque
                      <input type="number" name="recurrence_interval" min={1} defaultValue={1} />
                    </label>

                    <label>
                      Repeter jusqu au
                      <input type="date" name="recurrence_until_date" />
                    </label>
                  </div>
                  <p className="muted">La recurrence est creee jusqu a la date de fin incluse.</p>
                </div>
              </fieldset>

              <section className="create-session-section">
                <h3 className="create-session-section-title">Visibilite et descriptions</h3>
                <div className="grid cols-2 create-session-visibility-grid">
                  <SessionVisibilityFields initialIsPrivate={false} initialAllowOnlineBooking />

                  <label>
                    Description publique (vue client)
                    <textarea name="public_description" rows={4} />
                  </label>

                  <label>
                    Description privee (interne)
                    <textarea name="private_description" rows={4} />
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
          {agendaDays.map((day) => (
            <article key={day.key} className="agenda-day">
              <div className="row spread agenda-day-header">
                <h3>{day.label}</h3>
                <span className="badge">{day.sessions.length}</span>
              </div>

              {day.sessions.length === 0 ? (
                <p className="muted agenda-empty">Aucun cours</p>
              ) : (
                <div className="agenda-events">
                  {day.sessions.slice(0, maxVisibleSessionsByDay).map((session) => {
                    const courseType = courseTypeById.get(session.course_type_id);
                    const location = locationById.get(session.location_id);
                    const occupancyText = `${session.booked_count}/${session.capacity_max}`;
                    const openSessionHref = withSessionInHref(sessionModalBaseHref, session.id);
                    const attendanceSessionHref = withQueryParam(openSessionHref, "attendance", "1");
                    const groupNotesSessionHref = withQueryParam(openSessionHref, "notes", "group");
                    const duplicateSessionHref = withQueryParam(openSessionHref, "duplicate", "1");
                    const editSessionCardHref = withQueryParam(openSessionHref, "edit", "1");
                    const sessionEmailHref = withQueryParam(openSessionHref, "message", "email");
                    const sessionSmsHref = withQueryParam(openSessionHref, "message", "sms");
                    const deleteSessionHref = withQueryParam(openSessionHref, "confirm_action", "delete");
                    const hasBookedStudents = session.booked_count > 0;
                    const activityColor = courseType?.color_hex ?? "#d8ccb9";
                    const eventStateClass =
                      session.status === "COMPLETED"
                        ? "agenda-event-completed"
                        : session.status === "CANCELLED"
                          ? "agenda-event-cancelled"
                          : "";

                    return (
                      <article key={session.id} className="agenda-event-shell">
                        <a className="agenda-event-link" href={openSessionHref}>
                          <section className={`agenda-event ${eventStateClass}`} style={{ borderLeft: `4px solid ${activityColor}` }}>
                            <div className="row spread">
                              <p className="muted">
                                {sessionTimeRangeLabel(session)}
                              </p>
                              <div className="row">
                                <span className={`occ-badge ${occupancyClass(session.booked_count, session.capacity_max)}`}>{occupancyText}</span>
                                <span className={`status-badge ${statusClass(session.status)}`}>{session.status}</span>
                                {session.is_private ? <span className="status-badge status-private">PRIVE</span> : null}
                              </div>
                            </div>

                            <h3 className="event-title">{session.title}</h3>
                            <small className="muted event-meta">
                              <span className="meta-icon" aria-hidden="true">
                                🎵
                              </span>
                              {courseType?.name ?? "Type non defini"}
                            </small>
                            <small className="muted event-meta">
                              <span className="meta-icon" aria-hidden="true">
                                📍
                              </span>
                              {location?.name ?? "Lieu non defini"}
                            </small>
                          </section>
                        </a>

                        <div className="agenda-event-hover-actions" aria-label="Actions creneau">
                          {hasBookedStudents ? (
                            <a
                              className="agenda-event-action icon"
                              href={attendanceSessionHref}
                              aria-label="Prendre les presences"
                              title="Prendre les presences"
                            >
                              ✅
                            </a>
                          ) : null}
                          {hasBookedStudents ? (
                            <a
                              className="agenda-event-action icon"
                              href={groupNotesSessionHref}
                              aria-label="Ajouter une note de groupe"
                              title="Ajouter une note de groupe"
                            >
                              📝
                            </a>
                          ) : null}
                          {hasBookedStudents ? (
                            <a
                              className="agenda-event-action icon"
                              href={sessionEmailHref}
                              aria-label="Envoyer un email"
                              title="Envoyer un email"
                            >
                              ✉️
                            </a>
                          ) : null}
                          {hasBookedStudents ? (
                            <a
                              className="agenda-event-action icon"
                              href={sessionSmsHref}
                              aria-label="Envoyer un SMS"
                              title="Envoyer un SMS"
                            >
                              💬
                            </a>
                          ) : null}
                          <a className="agenda-event-action icon" href={duplicateSessionHref} aria-label="Dupliquer" title="Dupliquer">
                            📄
                          </a>
                          <a className="agenda-event-action icon" href={editSessionCardHref} aria-label="Modifier" title="Modifier">
                            ✏️
                          </a>
                          <a className="agenda-event-action danger icon" href={deleteSessionHref} aria-label="Supprimer" title="Supprimer">
                            🗑
                          </a>
                        </div>
                      </article>
                    );
                  })}
                  {day.sessions.length > maxVisibleSessionsByDay ? (
                    <a
                      className="agenda-more-link"
                      href={buildPlanningHref({ ...queryForLinks, showFilters: false, dayDetails: day.key })}
                    >
                      {day.sessions.length - maxVisibleSessionsByDay} more
                    </a>
                  ) : null}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      {selectedDayDetails && !selectedSession ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-day-details">
            <a className="modal-close-x" href={dayDetailsCloseHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Cours du {agendaDayLongLabel(selectedDayDetails.key)}</h2>
            <p className="muted">{selectedDayDetails.sessions.length} cours sur cette journee.</p>

            {selectedDayDetails.sessions.length === 0 ? (
              <p className="muted">Aucun cours.</p>
            ) : (
              <div className="list day-details-list">
                {selectedDayDetails.sessions.map((session) => {
                  const courseType = courseTypeById.get(session.course_type_id);
                  const location = locationById.get(session.location_id);
                  const professor = professorById.get(session.professor_id);
                  const occupancyText = `${session.booked_count}/${session.capacity_max}`;
                  const openSessionHref = withSessionInHref(sessionModalBaseHref, session.id);

                  return (
                    <a key={session.id} className="item day-details-item" href={openSessionHref}>
                      <div className="row spread">
                        <strong>
                          {sessionTimeRangeLabel(session)}
                        </strong>
                        <div className="row">
                          <span className={`occ-badge ${occupancyClass(session.booked_count, session.capacity_max)}`}>
                            {occupancyText}
                          </span>
                          <span className={`status-badge ${statusClass(session.status)}`}>{session.status}</span>
                        </div>
                      </div>
                      <h3 className="event-title">{session.title}</h3>
                      <small className="muted">
                        {courseType?.name ?? "Type non defini"} |{" "}
                        {professor ? `${professor.first_name} ${professor.last_name}`.trim() : "Professeur non defini"}
                      </small>
                      <small className="muted">{location?.name ?? "Lieu non defini"}</small>
                    </a>
                  );
                })}
              </div>
            )}
          </article>
        </section>
      ) : null}

      {selectedSession ? (
        <section className="modal-overlay">
          <article className="modal-panel">
            <a className="modal-close-x" href={baseHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">{selectedSession.title}</h2>

            {okMessage ? <section className="flash-ok modal-flash">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err modal-flash">{errorMessage}</section> : null}

            <p className="muted">
              {formatDate(selectedSession.start_at_utc)} | {sessionTimeRangeLabel(selectedSession)} | Statut: {selectedSession.status}
            </p>
            <div className="row">
              <span className={`occ-badge ${occupancyClass(selectedSession.booked_count, selectedSession.capacity_max)}`}>
                {selectedSession.booked_count}/{selectedSession.capacity_max}
              </span>
              <span className={`status-badge ${statusClass(selectedSession.status)}`}>{selectedSession.status}</span>
              {selectedSession.recurrence_group_id ? <span className="badge">Serie recurrente</span> : null}
              {selectedSession.is_private ? <span className="status-badge status-private">PRIVE</span> : null}
              {!selectedSession.is_private ? (
                <span className="badge">{selectedSession.allow_online_booking ? "Reservation en ligne: oui" : "Reservation en ligne: non"}</span>
              ) : null}
            </div>
            <p className="muted session-summary-line">
              <span className="meta-icon" aria-hidden="true">
                🎵
              </span>
              {selectedCourseTypeName}
              {"  "}
              <span className="meta-icon" aria-hidden="true">
                👤
              </span>
              {selectedProfessorName}
              {"  "}
              <span className="meta-icon" aria-hidden="true">
                📍
              </span>
              {selectedLocationName}
              {"  "}
              <span className="meta-icon" aria-hidden="true">
                🕒
              </span>
              {selectedSession.timezone}
              {"  "}
              <span className="meta-icon" aria-hidden="true">
                🔁
              </span>
              {recurrenceLabel(selectedSession)}
            </p>

            <div className="row quick-actions-row">
              {selectedSessionHasBookings ? (
                <a className="mode-link" href={attendanceModalHref}>
                  Prendre les presences
                </a>
              ) : null}
              {selectedSessionHasBookings ? (
                <a className="mode-link" href={groupNotesModalHref}>
                  Note de groupe
                </a>
              ) : null}
              {selectedSessionHasBookings ? (
                <a className="mode-link" href={sessionEmailModalHref}>
                  Envoyer email
                </a>
              ) : null}
              {selectedSessionHasBookings ? (
                <a className="mode-link" href={sessionSmsModalHref}>
                  Envoyer SMS
                </a>
              ) : null}
              <a className="mode-link" href={duplicateModalHref}>
                Dupliquer
              </a>
              <a className="mode-link" href={editSessionHref}>
                Modifier
              </a>
              {selectedSession.status !== "CANCELLED" ? (
                <a className="danger-link" href={cancelConfirmHref}>
                  Annuler le creneau...
                </a>
              ) : null}
              <a className="danger-link" href={deleteConfirmHref}>
                Supprimer le creneau...
              </a>
            </div>

            {selectedSession.zoom_link ? (
              <p>
                <a href={selectedSession.zoom_link} target="_blank" rel="noreferrer">
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

            <section className="card modal-card">
              <div className="row spread">
                <h3>Inscrits sur ce creneau</h3>
                <span className="badge">{selectedSessionBookings.length}</span>
              </div>

              {selectedSessionBookings.length === 0 ? (
                <p className="muted">Aucun eleve inscrit.</p>
              ) : (
                <div className="list session-bookings-summary-list">
                  {selectedSessionBookings.map((booking, index) => (
                    <article key={booking.id} className="item row spread session-booking-summary-row">
                      <div>
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
                        <br />
                        <small className="muted">{booking.client_email}</small>
                      </div>
                      <div className="row">
                        <span className={`status-badge ${statusClass(booking.status)}`}>
                          {booking.status}
                          {booking.waitlist_position ? ` #${booking.waitlist_position}` : ""}
                        </span>
                        <a className="mode-link" href={attendanceBookingHref(booking.id)}>
                          Presence & note
                        </a>
                        {isBookingRemovable(selectedSession, booking) ? (
                          <form action={adminRemoveClientFromSessionAction} className="row">
                            <input type="hidden" name="session_id" value={selectedSession.id} />
                            <input type="hidden" name="booking_id" value={booking.id} />
                            <input type="hidden" name="return_to" value={modalHref} />
                            <button className="icon-btn danger" type="submit" title="Retirer l adherent">
                              🗑
                            </button>
                          </form>
                        ) : (
                          <span className="muted">Verrouille</span>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
              {selectedSessionHasBookings ? (
                <div className="row session-primary-actions">
                  <a className="mode-link" href={attendanceModalHref}>
                    Prendre les presences
                  </a>
                  <a className="mode-link" href={groupNotesModalHref}>
                    Ajouter des notes de groupe
                  </a>
                </div>
              ) : null}
              {selectedSession.group_note ? (
                <p className="muted top-gap-sm">
                  <strong>Note de groupe:</strong> {stripHtml(selectedSession.group_note)}
                </p>
              ) : null}
            </section>

            <section className="card modal-card">
              <h3>Inscrire un adherent</h3>
              <form action={adminAddClientToSessionAction} className="grid cols-3">
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={modalHref} />

                <SearchMultiSelect
                  className="span-2"
                  label="Eleve"
                  name="client_id"
                  options={bookingClientOptions}
                  selectedIds={[]}
                  placeholder="Rechercher un eleve..."
                  emptySelectionLabel="Aucun eleve selectionne."
                  maxSelections={1}
                />

                <label className="checkline span-2">
                  <input type="checkbox" name="apply_recurrence" />
                  Inscription recurrente (meme jour/heure/type/lieu/coach)
                </label>
                <label>
                  Date fin recurrence (UTC)
                  <input type="date" name="recurrence_end_date" />
                </label>
                <p className="muted span-3">Sans activation, inscription sur ce creneau uniquement.</p>

                <div className="row">
                  <button type="submit">Valider la reservation</button>
                </div>
              </form>
            </section>

            <section className="card modal-card">
                  <details className="modal-details" open={editSessionOpen}>
                    <summary>Modifier ce creneau</summary>

                    <form action={updateAdminSessionAction} className="grid session-edit-form" noValidate>
                      <input type="hidden" name="session_id" value={selectedSession.id} />
                      <input type="hidden" name="return_to" value={modalHref} />

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
                        <select name="professor_id" defaultValue={selectedSession.professor_id} required>
                          {professors.map((row) => (
                            <option key={row.id} value={row.id}>
                              {row.first_name} {row.last_name}
                            </option>
                          ))}
                        </select>
                      </label>

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

                      <label>
                        Jour debut
                        <input
                          type="date"
                          name="start_date"
                          defaultValue={toDateInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                          required
                        />
                      </label>

                      <label className="checkline">
                        <input type="checkbox" name="is_all_day" defaultChecked={selectedSession.is_all_day} />
                        Creneau sur toute la journee
                      </label>

                      <SessionTimeFields
                        labelClassName="session-time-field"
                        defaultStartTime={toTimeInputInTimezone(selectedSession.start_at_utc, selectedSession.timezone)}
                        defaultEndTime={toTimeInputInTimezone(selectedSession.end_at_utc, selectedSession.timezone)}
                        defaultDurationMinutes={sessionDurationMinutes(selectedSession)}
                        requiredStart
                      />

                      <label>
                        Capacite max
                        <input type="number" name="capacity_max" min={0} defaultValue={selectedSession.capacity_max} />
                      </label>

                      <label>
                        Statut
                        <select name="status" defaultValue={selectedSession.status}>
                          <option value="SCHEDULED">SCHEDULED</option>
                          <option value="COMPLETED">COMPLETED</option>
                          <option value="CANCELLED">CANCELLED</option>
                        </select>
                      </label>

                      <label>
                        Lien Zoom
                        <input type="url" name="zoom_link" defaultValue={selectedSession.zoom_link ?? ""} />
                      </label>

                      <label>
                        Portee modification
                        <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                          <option value="ONE">Ce creneau</option>
                          {selectedSession.recurrence_group_id ? <option value="SERIES_FUTURE">Serie future</option> : null}
                          {selectedSession.recurrence_group_id ? <option value="SERIES_ALL">Toute la serie</option> : null}
                        </select>
                      </label>

                      {!selectedSession.recurrence_group_id ? (
                        <fieldset className="session-edit-span recurrence-panel">
                          <legend>Recurrence</legend>
                          <div className="recurrence-mode-row">
                            <label className="checkline">
                              <input type="radio" name="recurrence_mode" value="NONE" defaultChecked />
                              Garder ponctuel
                            </label>
                            <label className="checkline">
                              <input type="radio" name="recurrence_mode" value="RECURRING" />
                              Transformer en recurrent
                            </label>
                          </div>

                          <div className="recurrence-settings">
                            <div className="grid cols-3 recurrence-grid">
                              <label>
                                Frequence
                                <select name="recurrence_frequency" defaultValue="WEEKLY">
                                  <option value="DAILY">Journaliere</option>
                                  <option value="WEEKLY">Hebdomadaire</option>
                                  <option value="MONTHLY">Mensuelle</option>
                                </select>
                              </label>

                              <label>
                                Se repete chaque
                                <input type="number" name="recurrence_interval" min={1} defaultValue={1} />
                              </label>

                              <label>
                                Repeter jusqu au
                                <input type="date" name="recurrence_until_date" />
                              </label>
                            </div>
                            <p className="muted">
                              Le creneau actuel devient l ancre de la serie, puis les occurrences futures sont creees.
                            </p>
                          </div>
                        </fieldset>
                      ) : (
                        <p className="session-edit-span muted">
                          Ce creneau appartient deja a une serie recurrente. Utilisez la portee de modification pour ajuster la serie.
                        </p>
                      )}

                      <SessionVisibilityFields
                        initialIsPrivate={selectedSession.is_private}
                        initialAllowOnlineBooking={selectedSession.allow_online_booking}
                      />

                      <label className="session-edit-span">
                        Description publique (vue client)
                        <textarea name="public_description" rows={3} defaultValue={selectedSession.public_description ?? ""} />
                      </label>

                      <label className="session-edit-span">
                        Description privee (interne)
                        <textarea name="private_description" rows={3} defaultValue={selectedSession.private_description ?? ""} />
                      </label>

                      <div className="row">
                        <button type="submit">Enregistrer</button>
                      </div>
                    </form>

                    <form action={shiftAdminSessionAction} className="row quick-shift-row">
                      <input type="hidden" name="session_id" value={selectedSession.id} />
                      <input type="hidden" name="return_to" value={modalHref} />
                      <input type="hidden" name="current_start_at_utc" value={toDateTimeLocalUtcValue(selectedSession.start_at_utc)} />
                      <input type="hidden" name="current_end_at_utc" value={toDateTimeLocalUtcValue(selectedSession.end_at_utc)} />

                      <label className="scope-inline">
                        Deplacer
                        <select name="apply_scope" defaultValue={defaultApplyScope(selectedSession)}>
                          <option value="ONE">Ce creneau</option>
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

                  </details>
                </section>
          </article>
        </section>
      ) : null}

      {selectedSession && attendanceModalOpen && selectedSessionHasBookings ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel session-attendance-modal">
            <a className="modal-close-x" href={modalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Prendre les presences</h2>
            <p className="muted">Saisie eleve par eleve dans une popup dediee.</p>

            {selectedSessionBookings.length === 0 || !focusedAttendanceBooking ? (
              <p className="muted">Aucun eleve inscrit sur ce creneau.</p>
            ) : (
              <div className="attendance-modal-layout">
                <aside className="attendance-students-list">
                  {selectedSessionBookings.map((booking, index) => (
                    <a
                      key={booking.id}
                      href={attendanceBookingHref(booking.id)}
                      className={`attendance-student-link ${booking.id === focusedAttendanceBooking.id ? "active" : ""}`}
                    >
                      <strong>{booking.client_display_name || `Participant ${index + 1}`}</strong>
                      <small className="muted">{booking.client_email}</small>
                      <span className={`status-badge ${statusClass(booking.status)}`}>{booking.status}</span>
                    </a>
                  ))}
                </aside>

                <section className="attendance-focus-card">
                  <div className="row spread">
                    <div>
                      <h3>{focusedAttendanceBooking.client_display_name || "Participant"}</h3>
                      <small className="muted">{focusedAttendanceBooking.client_email}</small>
                    </div>
                    <span className={`status-badge ${statusClass(focusedAttendanceBooking.status)}`}>
                      {focusedAttendanceBooking.status}
                    </span>
                  </div>

                  {["BOOKED", "ATTENDED", "NO_SHOW", "EXCUSED_ABSENCE"].includes(focusedAttendanceBooking.status) ? (
                    <form action={adminUpdateSessionAttendanceAction} className="grid top-gap-sm">
                      <input type="hidden" name="session_id" value={selectedSession.id} />
                      <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                      <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                      <label>
                        Presence
                        <select name="attendance_status" defaultValue={focusedAttendanceBooking.status} required>
                          <option value="BOOKED">Non renseigne</option>
                          <option value="ATTENDED">Present</option>
                          <option value="NO_SHOW">Absent</option>
                          <option value="EXCUSED_ABSENCE">Absent excuse</option>
                        </select>
                      </label>
                      <div className="row">
                        <button type="submit">Sauvegarder presence</button>
                      </div>
                    </form>
                  ) : (
                    <p className="muted top-gap-sm">Presence non editable pour ce statut.</p>
                  )}

                  <form action={adminUpdateSessionBookingNoteAction} className="grid top-gap-sm">
                    <input type="hidden" name="session_id" value={selectedSession.id} />
                    <input type="hidden" name="booking_id" value={focusedAttendanceBooking.id} />
                    <input type="hidden" name="return_to" value={attendanceBookingHref(focusedAttendanceBooking.id)} />
                    <label className="session-edit-span">
                      Note eleve
                      <RichMessageEditor
                        name="student_note"
                        formatName="student_note_format"
                        rows={8}
                        maxLength={12000}
                        placeholder="Saisir une note pour cet eleve..."
                        defaultValue={focusedAttendanceBooking.student_note ?? ""}
                      />
                    </label>
                    <div className="row">
                      <button type="submit" className="ghost">
                        Sauvegarder note eleve
                      </button>
                    </div>
                  </form>

                  <div className="row spread attendance-focus-nav">
                    {previousAttendanceBooking ? (
                      <a className="mode-link" href={attendanceBookingHref(previousAttendanceBooking.id)}>
                        ← Eleve precedent
                      </a>
                    ) : (
                      <span />
                    )}
                    {nextAttendanceBooking ? (
                      <a className="mode-link" href={attendanceBookingHref(nextAttendanceBooking.id)}>
                        Eleve suivant →
                      </a>
                    ) : null}
                  </div>
                </section>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {selectedSession && groupNotesModalOpen && selectedSessionHasBookings ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact session-group-notes-modal">
            <a className="modal-close-x" href={modalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Notes de groupe</h2>
            <p className="muted">Notes partagees pour le groupe de ce creneau.</p>
            <form action={adminUpdateSessionGroupNoteAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="return_to" value={groupNotesModalHref} />
              <label className="session-edit-span">
                Note du creneau (groupe)
                <RichMessageEditor
                  name="group_note"
                  formatName="group_note_format"
                  rows={10}
                  maxLength={12000}
                  placeholder="Saisir une note de groupe..."
                  defaultValue={selectedSession.group_note ?? ""}
                />
              </label>
              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  Fermer
                </a>
                <button type="submit">Sauvegarder note de groupe</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionEmailModalOpen && selectedSessionHasBookings ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact session-group-notes-modal">
            <a className="modal-close-x" href={modalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Envoyer un email</h2>
            <p className="muted">Envoi groupe pour les eleves ou parents rattaches a ce creneau.</p>
            <form action={adminSendSessionBroadcastAction} className="grid top-gap-sm">
              <input type="hidden" name="session_id" value={selectedSession.id} />
              <input type="hidden" name="channel" value="EMAIL" />
              <input type="hidden" name="return_to" value={sessionEmailModalHref} />

              <label>
                Destinataires
                <select name="audience" defaultValue="STUDENTS">
                  <option value="STUDENTS">Eleves inscrits</option>
                  <option value="PARENTS">Parents des eleves</option>
                  <option value="STUDENTS_AND_PARENTS">Eleves + parents</option>
                </select>
              </label>

              <label>
                Sujet
                <input type="text" name="subject" defaultValue={`Message creneau: ${selectedSession.title}`} maxLength={255} required />
              </label>

              <label className="session-edit-span">
                Copie (emails, separes par virgule/point-virgule/retour ligne)
                <textarea name="cc_emails" rows={2} placeholder="copie@example.com; autre@example.com" />
              </label>

              <label className="session-edit-span">
                Message
                <RichMessageEditor
                  name="body"
                  formatName="body_format"
                  rows={10}
                  maxLength={12000}
                  defaultValue={`Bonjour,\n\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc)}.\n`}
                  placeholder="Saisir votre message..."
                />
              </label>

              <div className="row spread">
                <a className="reset-link" href={modalHref}>
                  Annuler
                </a>
                <button type="submit">Envoyer l email</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}

      {selectedSession && sessionSmsModalOpen && selectedSessionHasBookings ? (
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
                </select>
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
                  defaultValue={`Bonjour,\nMessage concernant le creneau "${selectedSession.title}" du ${formatDate(selectedSession.start_at_utc)}.`}
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
                Professeur cible: <strong>{selectedProfessorName}</strong>
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
                      ? `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc)} a ete supprime.\n\nPiano Academie`
                      : `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc)} a ete annule.\n\nPiano Academie`
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
