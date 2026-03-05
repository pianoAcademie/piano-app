import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  logoutAction,
  professorCreateCatalogRequestAction,
  professorDeliverCatalogRequestAction,
  professorMarkSessionAbsentAction,
  professorSendSessionMessageAction,
  professorUpdateAttendanceAction,
} from "../../lib/actions";
import { backendRequest } from "../../lib/backend";
import AutoSubmitSelect from "../../components/auto-submit-select";
import DayEventsDrawer from "../../components/planning/day-events-drawer";
import MonthDayCard from "../../components/planning/month-day-card";
import RichMessageEditor from "../../components/rich-message-editor";
import ActionCard from "../../components/teacher-ui/action-card";
import AlertCard from "../../components/teacher-ui/alert-card";
import BottomTabs from "../../components/teacher-ui/bottom-tabs";
import ListRow from "../../components/teacher-ui/list-row";
import PageHeaderMobile from "../../components/teacher-ui/page-header-mobile";
import SectionAccordion from "../../components/teacher-ui/section-accordion";
import StatCard from "../../components/teacher-ui/stat-card";
import StatChip from "../../components/teacher-ui/stat-chip";
import StickyActionBar from "../../components/teacher-ui/sticky-action-bar";
import type { PlanningEventChipData } from "../../components/planning/month-event-chip";
import type {
  ProfessorAttendancePendingOut,
  ProfessorBalanceOut,
  ProfessorContractGridOut,
  AdminCatalogProductOut,
  AdminCatalogRequestOut,
  LocationOut,
  ProfessorMeOut,
  ProfessorCatalogStudentOut,
  ProfessorPayoutOut,
  ProfessorSessionMessageOut,
  ProfessorSessionOut,
  UserOut,
} from "../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type Tab = "overview" | "planning" | "finance" | "messages" | "catalog" | "profile";
type AgendaView = "week" | "day" | "agenda";

type AgendaRange = {
  from: Date;
  to: Date;
  dayKeys: string[];
  title: string;
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseTab(value: string): Tab {
  if (value === "planning" || value === "finance" || value === "messages" || value === "catalog" || value === "profile") {
    return value;
  }
  return "overview";
}

function parseAgendaView(value: string): AgendaView {
  if (value === "day" || value === "agenda" || value === "week") {
    return value;
  }
  return "agenda";
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

function startOfWeekUtc(date: Date): Date {
  const day = date.getUTCDay();
  const offsetFromMonday = (day + 6) % 7;
  return addUtcDays(date, -offsetFromMonday);
}

function todayKeyUtc(): string {
  return utcDateToKey(new Date());
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

  if (view === "agenda") {
    const from = focusDate;
    const dayKeys: string[] = [];
    for (let i = 0; i < 14; i += 1) {
      dayKeys.push(utcDateToKey(addUtcDays(from, i)));
    }
    const lastDay = addUtcDays(from, 13);
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

function formatDayLabel(dayKey: string, view: AgendaView): string {
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

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusBadgeClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ATTENDANCE_PENDING") {
    return "status-waitlist";
  }
  if (normalized === "COMPLETED") {
    return "status-completed";
  }
  if (normalized === "CANCELLED") {
    return "status-cancelled";
  }
  return "status-scheduled";
}

function statusLabel(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "ATTENDANCE_PENDING") {
    return "Presences a renseigner";
  }
  if (normalized === "SCHEDULED") {
    return "Planifie";
  }
  if (normalized === "COMPLETED") {
    return "Termine";
  }
  if (normalized === "CANCELLED") {
    return "Annule";
  }
  return normalized;
}

function professorTypeLabel(session: ProfessorSessionOut): string {
  const locationCode = (session.location.code || "").toUpperCase();
  const locationName = (session.location.name || "").toLowerCase();
  const courseName = (session.course_type.name || "").toLowerCase();
  if (session.location.is_online || locationCode === "ONLINE") {
    return "Online";
  }
  if (locationCode.includes("DOMICILE") || locationName.includes("domicile")) {
    return "Domicile";
  }
  if (courseName.includes("prive") || courseName.includes("particulier")) {
    return "Prive";
  }
  return "Collectif";
}

function shortLocationLabel(value: string): string {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    return "Lieu";
  }
  for (const separator of [" - ", ",", "|"]) {
    if (trimmed.includes(separator)) {
      return trimmed.split(separator, 1)[0].trim() || "Lieu";
    }
  }
  return trimmed;
}

function attendanceLabel(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "BOOKED") {
    return "A saisir";
  }
  if (normalized === "ATTENDED") {
    return "Present";
  }
  if (normalized === "NO_SHOW") {
    return "Absent non excuse";
  }
  if (normalized === "EXCUSED_ABSENCE") {
    return "Absent excuse";
  }
  if (normalized === "WAITLISTED") {
    return "Liste attente";
  }
  return normalized;
}

function buildProfHref(params: {
  tab: Tab;
  agendaView: AgendaView;
  agendaDate: string;
  sessionId?: string | null;
  messageId?: string | null;
  dayDetails?: string | null;
}): string {
  const query = new URLSearchParams();
  query.set("tab", params.tab);
  query.set("agenda_view", params.agendaView);
  query.set("agenda_date", params.agendaDate);
  if (params.sessionId) {
    query.set("session_id", params.sessionId);
  }
  if (params.messageId) {
    query.set("message_id", params.messageId);
  }
  if (params.dayDetails) {
    query.set("day_details", params.dayDetails);
  }
  return `/prof?${query.toString()}`;
}

function shiftAgendaDate(view: AgendaView, agendaDate: string, direction: -1 | 1): string {
  const focusDate = keyToUtcDate(agendaDate);
  if (view === "week") {
    return utcDateToKey(addUtcDays(focusDate, direction * 7));
  }
  if (view === "day") {
    return utcDateToKey(addUtcDays(focusDate, direction));
  }
  return utcDateToKey(addUtcDays(focusDate, direction * 14));
}

function parseMessageSubject(subject: string): { cleanedSubject: string; targetLabel: string | null } {
  const studentMatch = subject.match(/\s*\(eleve:\s*(.+)\)\s*$/i);
  if (studentMatch) {
    const cleanedSubject = subject.replace(/\s*\(eleve:\s*(.+)\)\s*$/i, "").trim();
    return {
      cleanedSubject: cleanedSubject || subject,
      targetLabel: studentMatch[1]?.trim() || null,
    };
  }
  const adminMatch = subject.match(/\s*\(administration\)\s*$/i);
  if (adminMatch) {
    const cleanedSubject = subject.replace(/\s*\(administration\)\s*$/i, "").trim();
    return {
      cleanedSubject: cleanedSubject || subject,
      targetLabel: "Administration",
    };
  }
  return { cleanedSubject: subject, targetLabel: null };
}

function pendingAttendanceCount(session: ProfessorSessionOut): number {
  return session.students.filter((student) => student.attendance_status === "BOOKED").length;
}

function presentAttendanceCount(session: ProfessorSessionOut): number {
  return session.students.filter((student) => student.attendance_status === "ATTENDED").length;
}

function reservedStudentsCountFromRoster(session: ProfessorSessionOut): number {
  return session.students.filter((student) => {
    return (
      student.attendance_status === "BOOKED" ||
      student.attendance_status === "ATTENDED" ||
      student.attendance_status === "NO_SHOW" ||
      student.attendance_status === "EXCUSED_ABSENCE"
    );
  }).length;
}

function sessionDisplayStatus(session: ProfessorSessionOut): string {
  const normalized = session.status.toUpperCase();
  if (normalized !== "SCHEDULED") {
    return normalized;
  }
  const sessionEnded = new Date(session.end_at_utc).getTime() <= Date.now();
  if (!sessionEnded) {
    return normalized;
  }
  return pendingAttendanceCount(session) > 0 ? "ATTENDANCE_PENDING" : "COMPLETED";
}

function productRequestStatusLabel(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "PROCESSING") {
    return "En cours de traitement";
  }
  if (normalized === "INVOICE_TO_SEND") {
    return "Facture a envoyer";
  }
  if (normalized === "TO_DELIVER") {
    return "A remettre";
  }
  if (normalized === "DELIVERED") {
    return "Remis";
  }
  if (normalized === "REJECTED") {
    return "Refuse";
  }
  return normalized;
}

function productRequestSourceLabel(source: string): string {
  const normalized = source.toUpperCase();
  if (normalized === "PROFESSOR") {
    return "Professeur";
  }
  if (normalized === "ADMIN") {
    return "Administration";
  }
  return normalized;
}

export default async function ProfessorPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok) {
    redirect("/login?error=Session%20expiree");
  }

  if (meResult.data.role === "admin") {
    redirect("/admin");
  }
  if (meResult.data.role !== "prof") {
    redirect("/client?tab=home");
  }

  const currentTab = parseTab(readParam(searchParams, "tab"));
  const agendaView = parseAgendaView(readParam(searchParams, "agenda_view"));
  const agendaDateRaw = readParam(searchParams, "agenda_date");
  const agendaDate = isDateKey(agendaDateRaw) ? agendaDateRaw : todayKeyUtc();
  const agendaRange = buildAgendaRange(agendaView, agendaDate);

  const sessionsQuery = new URLSearchParams();
  sessionsQuery.set("from", agendaRange.from.toISOString());
  sessionsQuery.set("to", agendaRange.to.toISOString());
  sessionsQuery.set("include_students", "true");

  const [
    profileResult,
    pendingResult,
    sessionsResult,
    balanceResult,
    payoutsResult,
    messagesResult,
    contractGridsResult,
    catalogStudentsResult,
    catalogProductsResult,
    catalogLocationsResult,
    catalogRequestsResult,
  ] = await Promise.all([
    backendRequest<ProfessorMeOut>("/api/v1/professors/me", {}, token),
    backendRequest<ProfessorAttendancePendingOut[]>("/api/v1/professors/me/attendance/pending?limit=200", {}, token),
    backendRequest<ProfessorSessionOut[]>(`/api/v1/professors/me/sessions?${sessionsQuery.toString()}`, {}, token),
    backendRequest<ProfessorBalanceOut>("/api/v1/professors/me/balance", {}, token),
    backendRequest<ProfessorPayoutOut[]>("/api/v1/professors/me/payouts?limit=200", {}, token),
    backendRequest<ProfessorSessionMessageOut[]>("/api/v1/professors/me/messages?limit=100", {}, token),
    backendRequest<ProfessorContractGridOut[]>("/api/v1/professors/me/contract-grids", {}, token),
    backendRequest<ProfessorCatalogStudentOut[]>("/api/v1/professors/me/catalog/students", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/professors/me/catalog/products", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token),
    backendRequest<AdminCatalogRequestOut[]>("/api/v1/professors/me/catalog/requests", {}, token),
  ]);

  if (!profileResult.ok) {
    redirect(`/login?error=${encodeURIComponent(profileResult.message)}`);
  }

  const profile = profileResult.data;
  const fullName = `${profile.first_name} ${profile.last_name}`.trim();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const sessions = sessionsResult.ok ? sessionsResult.data : [];
  const sessionsByDay = new Map<string, ProfessorSessionOut[]>();
  for (const session of sessions) {
    const dayKey = session.start_at_utc.slice(0, 10);
    const bucket = sessionsByDay.get(dayKey) ?? [];
    bucket.push(session);
    sessionsByDay.set(dayKey, bucket);
  }
  for (const rows of sessionsByDay.values()) {
    rows.sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  }
  const agendaDays = agendaRange.dayKeys.map((dayKey) => ({
    key: dayKey,
    label: formatDayLabel(dayKey, agendaView),
    sessions: sessionsByDay.get(dayKey) ?? [],
  }));
  const dayDetailsRaw = readParam(searchParams, "day_details");
  const dayDetails = isDateKey(dayDetailsRaw) ? dayDetailsRaw : "";
  const agendaCardDays = agendaDays.map((day) => ({
    key: day.key,
    label: day.label,
    events: day.sessions.map((session) => {
      const displayStatus = sessionDisplayStatus(session);
      return {
        id: session.id,
        title: session.title,
        start_at_utc: session.start_at_utc,
        end_at_utc: session.end_at_utc,
        capacity_max: session.capacity_max,
        booked_count: Math.max(session.booked_count, reservedStudentsCountFromRoster(session)),
        teacher_display_name: fullName || profile.email,
        location_label: shortLocationLabel(session.location.name),
        type_label: professorTypeLabel(session),
        status_label: statusLabel(displayStatus),
        status: displayStatus,
      } satisfies PlanningEventChipData;
    }),
  }));
  const selectedDayDetails = dayDetails ? agendaCardDays.find((day) => day.key === dayDetails) ?? null : null;

  const selectedSessionId = readParam(searchParams, "session_id");
  const selectedSession = selectedSessionId ? sessions.find((session) => session.id === selectedSessionId) ?? null : null;
  const selectedSessionDisplayStatus = selectedSession ? sessionDisplayStatus(selectedSession) : null;
  const selectedSessionReservedCount = selectedSession
    ? Math.max(selectedSession.booked_count, reservedStudentsCountFromRoster(selectedSession))
    : 0;
  const selectedSessionPresentCount = selectedSession ? presentAttendanceCount(selectedSession) : 0;
  const selectedSessionPendingCount = selectedSession ? pendingAttendanceCount(selectedSession) : 0;
  const selectedMessageId = readParam(searchParams, "message_id");

  const pendingRows = pendingResult.ok ? pendingResult.data : [];
  const pendingCount = pendingRows.reduce((sum, row) => sum + row.pending_students_count, 0);
  const catalogStudents = catalogStudentsResult.ok ? catalogStudentsResult.data : [];
  const catalogProducts = catalogProductsResult.ok ? catalogProductsResult.data.filter((row) => row.active) : [];
  const catalogLocations = catalogLocationsResult.ok ? catalogLocationsResult.data.filter((row) => row.active) : [];
  const catalogRequests = catalogRequestsResult.ok ? catalogRequestsResult.data : [];
  const catalogToDeliver = catalogRequests.filter(
    (row) => row.status === "TO_DELIVER" || row.status === "INVOICE_TO_SEND",
  );

  const todaySessions = sessionsByDay.get(todayKeyUtc()) ?? [];
  const canEditPlanning = profile.permissions.can_edit_planning;
  const canMessageStudents = profile.permissions.can_message_clients;
  const maxVisibleSessionsByDay = agendaView === "day" ? 24 : agendaView === "week" ? 8 : 5;
  const previousAgendaDate = shiftAgendaDate(agendaView, agendaDate, -1);
  const nextAgendaDate = shiftAgendaDate(agendaView, agendaDate, 1);
  const previousAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: previousAgendaDate, dayDetails: "" });
  const nextAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: nextAgendaDate, dayDetails: "" });
  const todayAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: todayKeyUtc(), dayDetails: "" });
  const archivedMessages = messagesResult.ok ? messagesResult.data : [];
  const selectedMessage = selectedMessageId ? archivedMessages.find((message) => message.id === selectedMessageId) ?? null : null;

  const navTabs: Array<{ id: Tab; label: string; icon: string }> = [
    { id: "overview", label: "A traiter", icon: "🗂" },
    { id: "planning", label: "Planning", icon: "📅" },
    { id: "catalog", label: "Produits", icon: "📦" },
    { id: "finance", label: "Solde", icon: "💶" },
    { id: "messages", label: "Messages", icon: "✉️" },
    { id: "profile", label: "Profil", icon: "👤" },
  ];

  return (
    <main className="page prof-page teacher-shell">
      <PageHeaderMobile
        title={fullName || "Professeur"}
        subtitle={profile.email}
        statusLabel={profile.active ? "Actif" : "Inactif"}
        trailing={
          <Link className="mode-link teacher-header-link" href="/prof/statements">
            Releves
          </Link>
        }
        menu={
          <div className="teacher-header-menu-items">
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "catalog", agendaView, agendaDate })}>
              Produits
            </Link>
            <Link className="teacher-header-menu-link" href={buildProfHref({ tab: "finance", agendaView, agendaDate })}>
              Solde
            </Link>
            <form action={logoutAction}>
              <button className="ghost teacher-header-menu-btn" type="submit">
                Se deconnecter
              </button>
            </form>
          </div>
        }
      />

      <section className="card prof-nav teacher-desktop-nav">
        {navTabs.map((tab) => (
          <Link
            key={tab.id}
            className={`prof-nav-link ${currentTab === tab.id ? "active" : ""}`}
            href={buildProfHref({ tab: tab.id, agendaView, agendaDate })}
          >
            <span aria-hidden>{tab.icon}</span>
            {tab.label}
          </Link>
        ))}
        <Link className="prof-nav-link" href="/prof/statements">
          <span aria-hidden>🧾</span>
          Releves
        </Link>
      </section>

      <BottomTabs
        activeId={currentTab}
        items={[
          { id: "overview", label: "A traiter", icon: "📌", href: buildProfHref({ tab: "overview", agendaView, agendaDate }) },
          { id: "planning", label: "Planning", icon: "📅", href: buildProfHref({ tab: "planning", agendaView, agendaDate }) },
          { id: "statements", label: "Releves", icon: "🧾", href: "/prof/statements" },
          { id: "messages", label: "Messages", icon: "✉️", href: buildProfHref({ tab: "messages", agendaView, agendaDate }) },
          { id: "profile", label: "Profil", icon: "👤", href: buildProfHref({ tab: "profile", agendaView, agendaDate }) },
        ]}
      />

      {okMessage ? <AlertCard tone="ok">{okMessage}</AlertCard> : null}
      {errorMessage ? <AlertCard tone="error">{errorMessage}</AlertCard> : null}
      {!sessionsResult.ok ? <AlertCard tone="error">Erreur planning: {sessionsResult.message}</AlertCard> : null}
      {!pendingResult.ok ? <AlertCard tone="error">Erreur presences: {pendingResult.message}</AlertCard> : null}
      {!balanceResult.ok ? <AlertCard tone="error">Erreur solde: {balanceResult.message}</AlertCard> : null}
      {!messagesResult.ok ? <AlertCard tone="error">Erreur messages: {messagesResult.message}</AlertCard> : null}
      {!contractGridsResult.ok ? <AlertCard tone="error">Erreur grille contractuelle: {contractGridsResult.message}</AlertCard> : null}
      {!catalogStudentsResult.ok ? <AlertCard tone="error">Erreur eleves catalogue: {catalogStudentsResult.message}</AlertCard> : null}
      {!catalogProductsResult.ok ? <AlertCard tone="error">Erreur produits catalogue: {catalogProductsResult.message}</AlertCard> : null}
      {!catalogRequestsResult.ok ? <AlertCard tone="error">Erreur demandes produits: {catalogRequestsResult.message}</AlertCard> : null}

      {currentTab === "overview" ? (
        <section className="teacher-section-stack">
          <ActionCard
            title="Aujourd hui"
            subtitle="Suivi de vos seances et presences a renseigner."
            chips={
              <>
                <StatChip label="Presences" value={pendingCount} tone={pendingCount > 0 ? "warn" : "ok"} />
                <StatChip label="Cours du jour" value={todaySessions.length} />
                <StatChip label="Droits" value={canEditPlanning ? "Edition" : "Lecture"} />
              </>
            }
            action={
              <Link className="mode-link teacher-cta-full" href={buildProfHref({ tab: "planning", agendaView: "day", agendaDate: todayKeyUtc() })}>
                Ouvrir le planning
              </Link>
            }
          >
            {pendingRows.length === 0 ? (
              <p className="muted">Aucune saisie en attente.</p>
            ) : (
              <div className="list teacher-list-compact">
                {pendingRows.map((row) => {
                  const dayKey = row.start_at_utc.slice(0, 10);
                  const href = buildProfHref({
                    tab: "planning",
                    agendaView: "day",
                    agendaDate: dayKey,
                    sessionId: row.session_id,
                  });
                  return (
                    <ListRow
                      key={row.session_id}
                      href={href}
                      left={row.title}
                      subtitle={`${formatDateTime(row.start_at_utc)} - ${formatTime(row.end_at_utc)} | ${row.course_type_name} | ${row.location_name}`}
                      right={<span className="status-pill status-warn">A saisir {row.pending_students_count}/{row.total_students_count}</span>}
                    />
                  );
                })}
              </div>
            )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "planning" ? (
        <section className="card teacher-planning-card">
          <div className="row spread teacher-planning-head">
            <h2>Mes prochains cours</h2>
            <span className="badge">{agendaRange.title}</span>
          </div>

          <form method="get" className="grid cols-4 teacher-planning-controls">
            <input type="hidden" name="tab" value="planning" />
            <label>
              Vue
              <AutoSubmitSelect
                name="agenda_view"
                defaultValue={agendaView}
                options={[
                  { value: "agenda", label: "Prochains cours (14 jours)" },
                  { value: "week", label: "Semaine" },
                  { value: "day", label: "Jour" },
                ]}
              />
            </label>
            <label>
              Date de reference (UTC)
              <input type="date" name="agenda_date" defaultValue={agendaDate} />
            </label>
            <div className="row teacher-planning-controls-actions">
              <button type="submit" className="ghost">Aller</button>
              <Link className="reset-link" href={todayAgendaHref}>
                Aujourd hui
              </Link>
            </div>
            <div className="row teacher-planning-controls-arrows">
              <Link className="mode-link" href={previousAgendaHref}>
                ←
              </Link>
              <Link className="mode-link" href={nextAgendaHref}>
                →
              </Link>
            </div>
          </form>
          <p className="muted">La vue change immediatement a la selection. Navigation semaine par semaine disponible via les fleches.</p>

          <div className={`agenda-grid coach-agenda-grid agenda-grid-${agendaView === "agenda" ? "month" : agendaView}`}>
            {agendaCardDays.map((day) => (
              <MonthDayCard
                key={day.key}
                dayLabel={day.label}
                events={day.events}
                isToday={day.key === todayKeyUtc()}
                maxVisibleEvents={maxVisibleSessionsByDay}
                expanded={agendaView !== "agenda"}
                dayDetailsHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: day.key })}
                openSessionHref={(sessionId) =>
                  buildProfHref({
                    tab: "planning",
                    agendaView,
                    agendaDate,
                    sessionId,
                    dayDetails: "",
                  })
                }
              />
            ))}
          </div>

          <DayEventsDrawer
            isOpen={Boolean(selectedDayDetails && !selectedSession)}
            dayLabel={selectedDayDetails ? selectedDayDetails.label : ""}
            events={selectedDayDetails ? selectedDayDetails.events : []}
            closeHref={buildProfHref({ tab: "planning", agendaView, agendaDate, dayDetails: "" })}
            openSessionHref={(sessionId) =>
              buildProfHref({
                tab: "planning",
                agendaView,
                agendaDate,
                sessionId,
                dayDetails: "",
              })
            }
          />
        </section>
      ) : null}

      {currentTab === "catalog" ? (
        <section className="grid cols-2 teacher-catalog-layout">
          <ActionCard
            title="Signaler un besoin produit"
            subtitle="Demande pour un eleve. Validation par l administration."
            action={
              <StickyActionBar>
                <button type="submit" form="teacher-catalog-request-form">
                  Envoyer la demande
                </button>
              </StickyActionBar>
            }
          >
            <form id="teacher-catalog-request-form" action={professorCreateCatalogRequestAction} className="grid teacher-form-stack">
              <input type="hidden" name="return_to" value={buildProfHref({ tab: "catalog", agendaView, agendaDate })} />
              <label>
                Eleve
                <select name="student_user_id" required defaultValue="">
                  <option value="">Selectionner un eleve</option>
                  {catalogStudents.map((row) => (
                    <option key={row.user_id} value={row.user_id}>
                      {row.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Produit
                <select name="product_id" required defaultValue="">
                  <option value="">Selectionner un produit</option>
                  {catalogProducts.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Lieu de remise
                <select name="location_id" required defaultValue="">
                  <option value="">Selectionner un lieu</option>
                  {catalogLocations.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Quantite
                <input type="number" name="quantity" min={1} step={1} defaultValue={1} required />
              </label>
              <label>
                Note (optionnel)
                <textarea name="note" rows={3} maxLength={2000} />
              </label>
            </form>
          </ActionCard>

          <ActionCard title="Produits a remettre" subtitle="Marquez les demandes remises a l eleve.">
            {catalogToDeliver.length === 0 ? (
              <p className="muted">Aucun produit en attente de remise.</p>
            ) : (
              <>
                <div className="table-wrap teacher-desktop-table">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Eleve</th>
                        <th>Produit</th>
                        <th>Lieu</th>
                        <th>Qt</th>
                        <th>Stock</th>
                        <th>Statut</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catalogToDeliver.map((row) => {
                        const lowOrNegative = (row.stock_estimated_quantity ?? 0) < 0;
                        return (
                          <tr key={row.id} className={lowOrNegative ? "catalog-stock-negative" : ""}>
                            <td>{formatDateTime(row.requested_at)}</td>
                            <td>{row.student_name}</td>
                            <td>{row.product_title}</td>
                            <td>{row.location_name}</td>
                            <td>{row.quantity}</td>
                            <td>
                              {row.stock_estimated_quantity ?? "-"}
                              {lowOrNegative ? <div className="catalog-stock-alert">Stock negatif</div> : null}
                            </td>
                            <td>{productRequestStatusLabel(row.status)}</td>
                            <td>
                              <form action={professorDeliverCatalogRequestAction} className="grid">
                                <input type="hidden" name="request_id" value={row.id} />
                                <input
                                  type="hidden"
                                  name="return_to"
                                  value={buildProfHref({ tab: "catalog", agendaView, agendaDate })}
                                />
                                <input type="text" name="note" maxLength={2000} placeholder="Note remise (optionnel)" />
                                <button type="submit">Marquer remis</button>
                              </form>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="teacher-mobile-card-list">
                  {catalogToDeliver.map((row) => {
                    const lowOrNegative = (row.stock_estimated_quantity ?? 0) < 0;
                    return (
                      <article key={`${row.id}-mobile`} className="item">
                        <p className="muted">{formatDateTime(row.requested_at)}</p>
                        <strong>{row.product_title}</strong>
                        <p className="muted">
                          {row.student_name} | {row.location_name} | Qt {row.quantity}
                        </p>
                        <p className="muted">
                          Statut: {productRequestStatusLabel(row.status)} | Stock: {row.stock_estimated_quantity ?? "-"}
                        </p>
                        {lowOrNegative ? <p className="catalog-stock-alert">Stock negatif</p> : null}
                        <form action={professorDeliverCatalogRequestAction} className="grid top-gap-sm">
                          <input type="hidden" name="request_id" value={row.id} />
                          <input type="hidden" name="return_to" value={buildProfHref({ tab: "catalog", agendaView, agendaDate })} />
                          <input type="text" name="note" maxLength={2000} placeholder="Note remise (optionnel)" />
                          <button type="submit">Marquer remis</button>
                        </form>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
          </ActionCard>

          <div className="span-2">
            <ActionCard title="Historique des demandes produits" subtitle="Suivi chronologique des demandes.">
              {catalogRequests.length === 0 ? (
                <p className="muted">Aucune demande.</p>
              ) : (
                <>
                  <div className="table-wrap teacher-desktop-table">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Source</th>
                          <th>Eleve</th>
                          <th>Produit</th>
                          <th>Lieu</th>
                          <th>Qt</th>
                          <th>Statut</th>
                          <th>Facturation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {catalogRequests.map((row) => (
                          <tr key={`${row.id}-history`}>
                            <td>{formatDateTime(row.requested_at)}</td>
                            <td>{productRequestSourceLabel(row.request_source)}</td>
                            <td>{row.student_name}</td>
                            <td>{row.product_title}</td>
                            <td>{row.location_name}</td>
                            <td>{row.quantity}</td>
                            <td>{productRequestStatusLabel(row.status)}</td>
                            <td>{row.should_bill === null ? "-" : row.should_bill ? "Oui" : "Non"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="list teacher-mobile-card-list">
                    {catalogRequests.map((row) => (
                      <ListRow
                        key={`${row.id}-list`}
                        left={row.product_title}
                        subtitle={`${formatDateTime(row.requested_at)} | ${row.student_name} | ${row.location_name}`}
                        right={
                          <span className="status-pill status-warn">
                            {productRequestStatusLabel(row.status)}
                          </span>
                        }
                      />
                    ))}
                  </div>
                </>
              )}
            </ActionCard>
          </div>
        </section>
      ) : null}

      {currentTab === "finance" ? (
        <section className="grid teacher-finance-layout">
          <ActionCard title="Mon solde" subtitle="Synthese actuelle de votre remuneration.">
            {balanceResult.ok ? (
              <>
                <div className="teacher-stat-grid">
                  <StatCard
                    label="En attente"
                    value={`${balanceResult.data.pending_amount} ${balanceResult.data.currency}`}
                    hint={`${balanceResult.data.pending_sessions} cours`}
                  />
                  <StatCard
                    label="Valide"
                    value={`${balanceResult.data.approved_amount} ${balanceResult.data.currency}`}
                    hint={`${balanceResult.data.approved_sessions} cours`}
                  />
                  <StatCard
                    label="Paye"
                    value={`${balanceResult.data.paid_amount} ${balanceResult.data.currency}`}
                    hint={`${balanceResult.data.paid_sessions} cours`}
                  />
                  <StatCard label="Total" value={`${balanceResult.data.total_amount} ${balanceResult.data.currency}`} hint={`Devise ${balanceResult.data.currency}`} />
                </div>
              </>
            ) : (
              <p className="muted">Solde indisponible.</p>
            )}
          </ActionCard>

          <ActionCard title="Suivi des paiements" subtitle="Derniers paiements et statuts.">
            {payoutsResult.ok && payoutsResult.data.length > 0 ? (
              <div className="list teacher-list-compact">
                {payoutsResult.data.map((row) => (
                  <ListRow
                    key={row.payout_id}
                    left={`${row.amount_snapshot} ${row.currency_snapshot}`}
                    subtitle={`${row.course_type_name} - ${row.location_name} | ${formatDateTime(row.session_start_at_utc)}`}
                    right={
                      <span className={`status-pill ${row.payout_status.toUpperCase() === "PAID" ? "status-ok" : "status-warn"}`}>
                        {row.payout_status}
                      </span>
                    }
                  />
                ))}
              </div>
            ) : (
              <p className="muted">Aucun paiement enregistre.</p>
            )}
          </ActionCard>

          <ActionCard title="Ma grille contractuelle" subtitle="Regles de remuneration par activite et effectif.">
            {contractGridsResult.ok && contractGridsResult.data.length > 0 ? (
              <div className="list">
                {contractGridsResult.data.map((grid) => (
                  <SectionAccordion
                    key={grid.grid_id}
                    title={grid.location_label}
                    subtitle={`${grid.valid_from} - ${grid.valid_to ?? "non definie"}`}
                    defaultOpen={false}
                  >
                    <div className="table-wrap top-gap-sm">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Activite</th>
                            <th>Mode</th>
                            <th>Duree ref</th>
                            <th>Taux default</th>
                            <th>Regles effectif</th>
                          </tr>
                        </thead>
                        <tbody>
                          {grid.lines.map((line) => (
                            <tr key={`${grid.grid_id}-${line.course_type_id ?? line.service_type}-${line.mode}`}>
                              <td>{line.course_type_name || line.service_type}</td>
                              <td>{line.mode}</td>
                              <td>{line.reference_duration_minutes ?? "-"}</td>
                              <td>{line.default_hourly_rate ?? "-"}</td>
                              <td>
                                {line.rules.length > 0
                                  ? line.rules
                                      .map((rule) => {
                                        const range = rule.max_students === null ? `${rule.min_students}+` : `${rule.min_students}-${rule.max_students}`;
                                        return `${range}:${rule.hourly_rate}`;
                                      })
                                      .join("; ")
                                  : "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </SectionAccordion>
                ))}
              </div>
            ) : (
              <p className="muted">Aucune grille contractuelle active a cette date.</p>
            )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "messages" ? (
        <section className="teacher-section-stack">
          <ActionCard title="Messages" subtitle="Historique des envois groupes et individuels.">
          {messagesResult.ok && archivedMessages.length > 0 ? (
            <div className="list teacher-list-compact">
              {archivedMessages.map((message) => {
                const parsedSubject = parseMessageSubject(message.subject);
                return (
                  <ListRow
                    key={message.id}
                    href={buildProfHref({ tab: "messages", agendaView, agendaDate, messageId: message.id })}
                    left={parsedSubject.cleanedSubject}
                    subtitle={`Envoye le ${formatDateTime(message.sent_at)} | Format ${message.body_format}`}
                    right={
                      <div className="row">
                        <span className="badge">
                          {parsedSubject.targetLabel ? `Eleve: ${parsedSubject.targetLabel}` : "Groupe"}
                        </span>
                        <span className="badge">{message.recipient_count} destinataire(s)</span>
                      </div>
                    }
                  />
                );
              })}
            </div>
          ) : (
            <p className="muted">Aucun message archive.</p>
          )}
          </ActionCard>
        </section>
      ) : null}

      {currentTab === "profile" ? (
        <section className="teacher-section-stack">
          <SectionAccordion title="Mon profil" subtitle="Informations principales" defaultOpen={true}>
            <div className="list teacher-list-compact">
              <ListRow left="Nom" right={fullName || "-"} />
              <ListRow left="Email" right={profile.email} />
              <ListRow left="Telephone" right={profile.phone ?? "Non renseigne"} />
              <ListRow left="Lien Zoom" right={profile.zoom_link ?? "Non renseigne"} />
              <ListRow left="Langues" right={profile.spoken_languages.length > 0 ? profile.spoken_languages.join(", ") : "Non renseigne"} />
              <ListRow left="Devise contrat" right={profile.payout_currency} />
            </div>
          </SectionAccordion>

          <SectionAccordion title="Email quotidien planning" subtitle="Reglage administration" defaultOpen={false}>
            <div className="list teacher-list-compact">
              <ListRow left="Activation" right={profile.daily_schedule_email_enabled ? "Activee" : "Desactivee"} />
              <ListRow left="Heure UTC" right={profile.daily_schedule_email_time} />
              <ListRow left="Ignorer les jours sans cours" right={profile.daily_schedule_skip_if_no_course ? "Oui" : "Non"} />
            </div>
            <p className="muted top-gap-sm">
              Reglage configure par l administration. Le digest recapitule vos cours du jour et la liste des eleves.
            </p>
          </SectionAccordion>
        </section>
      ) : null}

      {currentTab === "planning" && selectedSession ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-day-details">
            <Link
              className="modal-close-x"
              href={buildProfHref({ tab: "planning", agendaView, agendaDate })}
              aria-label="Fermer"
            >
              ×
            </Link>
            <h3 className="modal-title">{selectedSession.title}</h3>
            <p className="muted">
              {formatDateTime(selectedSession.start_at_utc)} - {formatTime(selectedSession.end_at_utc)} | Statut:{" "}
              {statusLabel(selectedSessionDisplayStatus ?? selectedSession.status)}
            </p>
            <div className="row">
              <span className={`occ-badge ${selectedSessionReservedCount >= selectedSession.capacity_max ? "occ-high" : "occ-low"}`}>
                {selectedSessionReservedCount}/{selectedSession.capacity_max}
              </span>
              <span className={`status-badge ${statusBadgeClass(selectedSessionDisplayStatus ?? selectedSession.status)}`}>
                {statusLabel(selectedSessionDisplayStatus ?? selectedSession.status)}
              </span>
              <span className={`status-badge ${selectedSessionPresentCount > 0 ? "status-completed" : "status-scheduled"}`}>
                Présents: {selectedSessionPresentCount}
              </span>
              {selectedSessionPendingCount > 0 ? (
                <span className="status-badge status-waitlist">A saisir: {selectedSessionPendingCount}</span>
              ) : null}
            </div>
            <p className="muted">
              {selectedSession.course_type.name} | {selectedSession.location.name}
              {selectedSession.zoom_link ? ` | Zoom: ${selectedSession.zoom_link}` : ""}
            </p>

            <section className="modal-card">
              <h4>Eleves du creneau</h4>
              {selectedSession.students.length === 0 ? (
                <p className="muted">Aucun eleve inscrit.</p>
              ) : (
                <div className="list session-bookings-list">
                  {selectedSession.students.map((student) => (
                    <article key={student.booking_id} className="item prof-student-item">
                      <div className="row spread">
                        <div>
                          <strong>{student.display_name}</strong>
                          <div className="row">
                            <span className="status-badge status-scheduled">{attendanceLabel(student.attendance_status)}</span>
                            {student.is_trial_course ? <span className="status-pill status-warn">Essai</span> : null}
                            {student.is_first_course ? <span className="status-pill status-ok">Premier cours</span> : null}
                          </div>
                        </div>
                        {student.attendance_status !== "WAITLISTED" && canEditPlanning ? (
                          <div className="prof-attendance-actions">
                            <form action={professorUpdateAttendanceAction}>
                              <input type="hidden" name="booking_id" value={student.booking_id} />
                              <input type="hidden" name="attendance_status" value="ATTENDED" />
                              <input
                                type="hidden"
                                name="return_to"
                                value={buildProfHref({
                                  tab: "planning",
                                  agendaView,
                                  agendaDate,
                                  sessionId: selectedSession.id,
                                })}
                              />
                              <button type="submit" className="ghost small-btn">Present</button>
                            </form>
                            <form action={professorUpdateAttendanceAction}>
                              <input type="hidden" name="booking_id" value={student.booking_id} />
                              <input type="hidden" name="attendance_status" value="EXCUSED_ABSENCE" />
                              <input
                                type="hidden"
                                name="return_to"
                                value={buildProfHref({
                                  tab: "planning",
                                  agendaView,
                                  agendaDate,
                                  sessionId: selectedSession.id,
                                })}
                              />
                              <button type="submit" className="ghost small-btn">Abs. excuse</button>
                            </form>
                            <form action={professorUpdateAttendanceAction}>
                              <input type="hidden" name="booking_id" value={student.booking_id} />
                              <input type="hidden" name="attendance_status" value="NO_SHOW" />
                              <input
                                type="hidden"
                                name="return_to"
                                value={buildProfHref({
                                  tab: "planning",
                                  agendaView,
                                  agendaDate,
                                  sessionId: selectedSession.id,
                                })}
                              />
                              <button type="submit" className="small-btn">Abs. non excuse</button>
                            </form>
                          </div>
                        ) : (
                          <span className="muted">{student.attendance_status === "WAITLISTED" ? "Liste attente" : "Lecture seule"}</span>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {canMessageStudents ? (
              <section className="modal-card">
                <h4>Envoyer un message (groupe ou eleve)</h4>
                <form action={professorSendSessionMessageAction} className="grid">
                  <input type="hidden" name="session_id" value={selectedSession.id} />
                  <input
                    type="hidden"
                    name="return_to"
                    value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id })}
                  />
                  <label>
                    Objet
                    <input type="text" name="subject" required maxLength={255} />
                  </label>
                  <label>
                    Destinataire
                    <select name="recipient_target" defaultValue="GROUP">
                      <option value="GROUP">Tous les eleves du creneau</option>
                      {selectedSession.students.map((student) => (
                        <option key={`msg-${student.user_id}`} value={`STUDENT:${student.user_id}`}>
                          {student.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Message
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={8}
                      maxLength={12000}
                      defaultFormat="HTML"
                      placeholder="Rédiger votre message..."
                    />
                  </label>
                  <div className="row">
                    <button type="submit">Envoyer</button>
                  </div>
                </form>
              </section>
            ) : null}

            {canMessageStudents ? (
              <section className="modal-card">
                <h4>Note a l administration</h4>
                <form action={professorSendSessionMessageAction} className="grid">
                  <input type="hidden" name="session_id" value={selectedSession.id} />
                  <input
                    type="hidden"
                    name="return_to"
                    value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id })}
                  />
                  <input type="hidden" name="recipient_target" value="ADMIN" />
                  <label>
                    Objet
                    <input type="text" name="subject" required maxLength={255} defaultValue={`Note cours - ${selectedSession.title}`} />
                  </label>
                  <label>
                    Message (administration uniquement)
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={8}
                      maxLength={12000}
                      defaultFormat="HTML"
                      placeholder="Saisir une note pour l administration..."
                    />
                  </label>
                  <div className="row">
                    <button type="submit">Envoyer a l administration</button>
                  </div>
                </form>
              </section>
            ) : null}

            {canEditPlanning && selectedSession.status !== "CANCELLED" ? (
              <section className="modal-card">
                <h4>Absence professeur</h4>
                <form action={professorMarkSessionAbsentAction} className="grid">
                  <input type="hidden" name="session_id" value={selectedSession.id} />
                  <input
                    type="hidden"
                    name="return_to"
                    value={buildProfHref({ tab: "planning", agendaView, agendaDate, sessionId: selectedSession.id })}
                  />
                  <label className="checkline">
                    <input type="checkbox" name="notify_students" />
                    Notifier les eleves par email
                  </label>
                  <label>
                    Sujet (optionnel)
                    <input type="text" name="students_subject" maxLength={255} />
                  </label>
                  <label className="span-2">
                    Message (optionnel)
                    <RichMessageEditor
                      name="students_message"
                      formatName="students_format"
                      rows={6}
                      maxLength={12000}
                      defaultFormat="HTML"
                      placeholder="Message aux eleves"
                    />
                  </label>
                  <div className="row">
                    <button type="submit" className="danger">Declarer absence professeur</button>
                  </div>
                </form>
                <p className="muted">Le creneau sera annule et les credits restores si applicable.</p>
              </section>
            ) : null}
          </article>
        </section>
      ) : null}

      {currentTab === "messages" && selectedMessage ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <Link
              className="modal-close-x"
              href={buildProfHref({ tab: "messages", agendaView, agendaDate })}
              aria-label="Fermer"
            >
              ×
            </Link>
            {(() => {
              const parsedSubject = parseMessageSubject(selectedMessage.subject);
              return (
                <>
                  <h3 className="modal-title">{parsedSubject.cleanedSubject}</h3>
                  <p className="muted">
                    Envoye le {formatDateTime(selectedMessage.sent_at)} |{" "}
                    {parsedSubject.targetLabel === "Administration"
                      ? "Administration"
                      : parsedSubject.targetLabel
                        ? `Eleve: ${parsedSubject.targetLabel}`
                        : "Message groupe"}
                  </p>
                </>
              );
            })()}
            {selectedMessage.body_format === "HTML" ? (
              <article className="item" dangerouslySetInnerHTML={{ __html: selectedMessage.body }} />
            ) : (
              <article className="item">
                <p style={{ whiteSpace: "pre-wrap" }}>{selectedMessage.body}</p>
              </article>
            )}
          </article>
        </section>
      ) : null}
    </main>
  );
}
