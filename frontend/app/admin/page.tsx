import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  adminAddClientToSessionAction,
  adminRemoveClientFromSessionAction,
  cancelAdminSessionAction,
  createAdminSessionAction,
  deleteAdminSessionAction,
  shiftAdminSessionAction,
  updateAdminSessionAction,
} from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
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
  courseTypeId: string;
  professorId: string;
  status: string;
  clientStatus: string;
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

  const dayStep = view === "week" ? 14 : 2;
  return utcDateToKey(addUtcDays(focusDate, direction * dayStep));
}

function toDateTimeLocalUtcValue(value: string): string {
  return safeDate(value)?.toISOString().slice(0, 16) ?? "";
}

function toDateInputUtcValue(value: string): string {
  return safeDate(value)?.toISOString().slice(0, 10) ?? "";
}

function toTimeInputUtcValue(value: string): string {
  return safeDate(value)?.toISOString().slice(11, 16) ?? "";
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

function sessionTimeRangeLabel(session: AdminSessionOut): string {
  if (session.is_all_day) {
    return "Toute la journee";
  }
  return `${formatTime(session.start_at_utc)} - ${formatTime(session.end_at_utc)}`;
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
  if (status === "COMPLETED") {
    return "status-completed";
  }
  if (status === "WAITLISTED") {
    return "status-waitlist";
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
  if (query.professorId) {
    sp.set("professor_id", query.professorId);
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

export default async function AdminPlanningPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const selectedCourseType = readParam(searchParams, "course_type_id");
  const rawLocation = readParam(searchParams, "location_id");
  const selectedProfessor = readParam(searchParams, "professor_id");
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
  const confirmActionRaw = readParam(searchParams, "confirm_action").toLowerCase();
  const confirmAction: "" | "cancel" | "delete" = confirmActionRaw === "cancel" || confirmActionRaw === "delete" ? confirmActionRaw : "";

  const sessionsQuery = new URLSearchParams();
  if (rawLocation) {
    sessionsQuery.set("location_id", rawLocation);
  }
  if (selectedCourseType) {
    sessionsQuery.set("course_type_id", selectedCourseType);
  }
  if (selectedProfessor) {
    sessionsQuery.set("professor_id", selectedProfessor);
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

  const focusedLocationId = rawLocation || (locations[0]?.id ?? "");
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
    courseTypeId: selectedCourseType,
    professorId: selectedProfessor,
    status: selectedStatus,
    clientStatus: selectedClientStatus,
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
    professorId: "",
    status: "ALL",
    clientStatus: "ALL",
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

  const filteredSessions = sessions
    .filter((session) => {
      if (!focusedLocationId || session.location_id !== focusedLocationId) {
        return false;
      }
      if (selectedCourseType && session.course_type_id !== selectedCourseType) {
        return false;
      }
      if (selectedProfessor && session.professor_id !== selectedProfessor) {
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

  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const modalHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const confirmCloseHref = selectedSession ? withSessionInHref(baseHref, selectedSession.id) : baseHref;
  const cancelConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "cancel") : baseHref;
  const deleteConfirmHref = selectedSession ? withQueryParam(withSessionInHref(baseHref, selectedSession.id), "confirm_action", "delete") : baseHref;
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

  return (
    <section className="admin-page-grid">
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {errors.length > 0 ? <section className="flash-err">Erreur backend: {errors.join(" | ")}</section> : null}

      <section className="card">
        <div className="row spread">
          <h2>Planning - {focusedLocation?.name ?? "Aucun lieu"}</h2>
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
          <input type="hidden" name="professor_id" value={selectedProfessor} />
          <input type="hidden" name="status" value={selectedStatus} />
          <input type="hidden" name="client_status" value={selectedClientStatus} />
          <input type="hidden" name="agenda_date" value={agendaDate} />
          {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

          <label>
            Lieu
            <select name="location_id" defaultValue={focusedLocationId} required>
              {locations.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Vue agenda
            <select name="agenda_view" defaultValue={agendaView}>
              <option value="month">Mois</option>
              <option value="week">Semaine</option>
              <option value="day">Jour</option>
            </select>
          </label>

          <label>
            Fuseau horaire
            <select name="timezone" defaultValue={timezone}>
              {timezoneOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="row">
            <button type="submit">Mettre a jour</button>
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
          {selectedProfessor ? (
            <span className="badge">
              Prof: {professorById.get(selectedProfessor)?.first_name} {professorById.get(selectedProfessor)?.last_name}
            </span>
          ) : null}
          {selectedStatus !== "ALL" ? <span className="badge">Statut cours: {selectedStatus}</span> : null}
          {selectedClientStatus !== "ALL" ? <span className="badge">Statut adherent: {selectedClientStatus}</span> : null}
          {!selectedCourseType && !selectedProfessor && selectedStatus === "ALL" && selectedClientStatus === "ALL" ? (
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
            <p className="muted">Le lieu, la vue et le fuseau horaire se reglent directement dans la barre principale.</p>
            <form method="get" className="grid">
              <input type="hidden" name="location_id" value={focusedLocationId} />
              <input type="hidden" name="agenda_view" value={agendaView} />
              <input type="hidden" name="agenda_date" value={agendaDate} />
              <input type="hidden" name="timezone" value={timezone} />
              {dayDetails ? <input type="hidden" name="day_details" value={dayDetails} /> : null}

              <label>
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

              <label>
                Professeur
                <select name="professor_id" defaultValue={selectedProfessor}>
                  <option value="">Tous</option>
                  {professors.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.first_name} {row.last_name}
                    </option>
                  ))}
                </select>
              </label>

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

              <div className="row">
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
            <p className="muted">
              Saisie separee jour/heure (UTC). Capacite requise (defaut: 1). Un creneau est sur un seul jour.
            </p>
            <form action={createAdminSessionAction} className="grid cols-4 create-session-form">
              <input type="hidden" name="return_to" value={createHref} />

              <label>
                Titre
                <input type="text" name="title" required maxLength={255} />
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
                Lieu
                <select name="location_id" defaultValue={focusedLocationId} required>
                  {locations.map((row) => (
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
                Jour debut (UTC)
                <input type="date" name="start_date" defaultValue={agendaDate} required />
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_all_day" />
                Creneau sur toute la journee
              </label>

              <label>
                Heure debut (UTC)
                <input type="time" name="start_time" defaultValue="12:00" />
              </label>

              <label>
                Heure fin (UTC)
                <input type="time" name="end_time" defaultValue="13:00" />
              </label>

              <label>
                Capacite max
                <input type="number" name="capacity_max" min={0} defaultValue={1} required />
              </label>

              <label>
                Lien Zoom (optionnel)
                <input type="url" name="zoom_link" placeholder="https://..." />
              </label>

              <fieldset className="session-edit-span recurrence-panel">
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

                <div className="grid cols-4 recurrence-grid">
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

                  <label className="checkline recurrence-forever">
                    <input type="checkbox" name="recurrence_forever" />
                    Repeter indefiniment
                  </label>

                  <label>
                    Repeter jusqu a (UTC)
                    <input type="date" name="recurrence_until_date" />
                  </label>
                </div>
                <p className="muted">
                  Optionnel: renseignez un nombre d occurrences au lieu d une date de fin.
                </p>
                <label className="recurrence-occurrences-label">
                  Nombre d occurrences
                  <input type="number" name="recurrence_occurrences" min={2} max={365} />
                </label>
              </fieldset>

              <label className="checkline">
                <input type="checkbox" name="is_private" />
                Creneau prive
              </label>

              <label className="span-2">
                Description publique (vue client)
                <textarea name="public_description" rows={3} />
              </label>

              <label className="span-2">
                Description privee (interne)
                <textarea name="private_description" rows={3} />
              </label>

              <div className="row">
                <button type="submit">Creer le creneau</button>
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
        <p className="muted">Navigation: mois par mois, 2 semaines en vue semaine, 2 jours en vue jour.</p>

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
                    const activityColor = courseType?.color_hex ?? "#d8ccb9";
                    const eventStateClass =
                      session.status === "COMPLETED"
                        ? "agenda-event-completed"
                        : session.status === "CANCELLED"
                          ? "agenda-event-cancelled"
                          : "";

                    return (
                      <a key={session.id} className="agenda-event-link" href={openSessionHref}>
                        <article className={`agenda-event ${eventStateClass}`} style={{ borderLeft: `4px solid ${activityColor}` }}>
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
                        </article>
                      </a>
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
                🔁
              </span>
              {recurrenceLabel(selectedSession)}
            </p>

            <div className="row quick-actions-row">
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
                <div className="list session-bookings-list">
                  {selectedSessionBookings.map((booking) => (
                    <article key={booking.id} className="item row spread session-booking-row">
                      <div>
                        <strong>{booking.client_display_name}</strong>
                        <br />
                        <small className="muted">{booking.client_email}</small>
                      </div>
                      <div className="row">
                        <span className={`status-badge ${statusClass(booking.status)}`}>
                          {booking.status}
                          {booking.waitlist_position ? ` #${booking.waitlist_position}` : ""}
                        </span>
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
            </section>

            <section className="card modal-card">
              <h3>Inscrire un adherent</h3>
              <form action={adminAddClientToSessionAction} className="grid cols-3">
                <input type="hidden" name="session_id" value={selectedSession.id} />
                <input type="hidden" name="return_to" value={modalHref} />

                <label className="span-2">
                  Eleve
                  <select name="client_id" required>
                    <option value="">Selectionner un eleve</option>
                    {clientsSorted.map((client) => (
                      <option key={client.id} value={client.id}>
                        {clientDisplayName(client)} - {client.email}
                      </option>
                    ))}
                  </select>
                </label>

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
                  <details className="modal-details">
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
                        Jour debut (UTC)
                        <input type="date" name="start_date" defaultValue={toDateInputUtcValue(selectedSession.start_at_utc)} required />
                      </label>

                      <label className="checkline">
                        <input type="checkbox" name="is_all_day" defaultChecked={selectedSession.is_all_day} />
                        Creneau sur toute la journee
                      </label>

                      <label>
                        Heure debut (UTC)
                        <input type="time" name="start_time" defaultValue={toTimeInputUtcValue(selectedSession.start_at_utc)} />
                      </label>

                      <label>
                        Heure fin (UTC)
                        <input type="time" name="end_time" defaultValue={toTimeInputUtcValue(selectedSession.end_at_utc)} />
                      </label>

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

                      <label className="checkline">
                        <input type="checkbox" name="is_private" defaultChecked={selectedSession.is_private} />
                        Creneau prive
                      </label>

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

              <label>
                Format eleves
                <select name="students_format" defaultValue="TEXT">
                  <option value="TEXT">Texte</option>
                  <option value="HTML">HTML</option>
                </select>
              </label>

              <label className="session-edit-span">
                Message eleves
                <textarea
                  name="students_message"
                  rows={4}
                  defaultValue={
                    confirmAction === "delete"
                      ? `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc)} a ete supprime.\n\nPiano Academie`
                      : `Bonjour,\n\nLe creneau \"${selectedSession.title}\" du ${formatDate(selectedSession.start_at_utc)} a ete annule.\n\nPiano Academie`
                  }
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

              <label>
                Format professeur
                <select name="professor_format" defaultValue="TEXT">
                  <option value="TEXT">Texte</option>
                  <option value="HTML">HTML</option>
                </select>
              </label>

              <label className="session-edit-span">
                Message professeur (si message distinct)
                <textarea name="professor_message" rows={4} />
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
