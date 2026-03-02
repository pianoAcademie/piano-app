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
import RichMessageEditor from "../../components/rich-message-editor";
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
  if (normalized === "SCHEDULED") {
    return "PREVU";
  }
  if (normalized === "COMPLETED") {
    return "TERMINE";
  }
  if (normalized === "CANCELLED") {
    return "ANNULE";
  }
  return normalized;
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
  return `/prof?${query.toString()}`;
}

function stripHtml(raw: string): string {
  return raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
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
  const match = subject.match(/\s*\(eleve:\s*(.+)\)\s*$/i);
  if (!match) {
    return { cleanedSubject: subject, targetLabel: null };
  }
  const cleanedSubject = subject.replace(/\s*\(eleve:\s*(.+)\)\s*$/i, "").trim();
  return {
    cleanedSubject: cleanedSubject || subject,
    targetLabel: match[1]?.trim() || null,
  };
}

function pendingAttendanceCount(session: ProfessorSessionOut): number {
  return session.students.filter((student) => student.attendance_status === "BOOKED").length;
}

function occupancyClass(booked: number, capacity: number): string {
  if (capacity <= 0) {
    return "occ-low";
  }
  if (booked >= capacity) {
    return "occ-high";
  }
  if (booked >= Math.max(1, Math.ceil(capacity * 0.7))) {
    return "occ-medium";
  }
  return "occ-low";
}

function agendaEventStateClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "COMPLETED") {
    return "agenda-event-completed";
  }
  if (normalized === "CANCELLED") {
    return "agenda-event-cancelled";
  }
  return "";
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
    redirect("/dashboard");
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

  const selectedSessionId = readParam(searchParams, "session_id");
  const selectedSession = selectedSessionId ? sessions.find((session) => session.id === selectedSessionId) ?? null : null;
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
  const maxVisibleSessionsByDay = 4;
  const previousAgendaDate = shiftAgendaDate(agendaView, agendaDate, -1);
  const nextAgendaDate = shiftAgendaDate(agendaView, agendaDate, 1);
  const previousAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: previousAgendaDate });
  const nextAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: nextAgendaDate });
  const todayAgendaHref = buildProfHref({ tab: "planning", agendaView, agendaDate: todayKeyUtc() });
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
    <main className="page prof-page">
      <section className="card row header-row">
        <div>
          <h1>Espace professeur</h1>
          <p className="muted">
            {fullName || profile.email} | {profile.email}
          </p>
        </div>
        <div className="row">
          <span className={`status-pill ${profile.active ? "status-ok" : "status-off"}`}>{profile.active ? "Actif" : "Inactif"}</span>
          <form action={logoutAction}>
            <button className="ghost" type="submit">
              Se deconnecter
            </button>
          </form>
        </div>
      </section>

      <section className="card prof-nav">
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
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!sessionsResult.ok ? <section className="flash-err">Erreur planning: {sessionsResult.message}</section> : null}
      {!pendingResult.ok ? <section className="flash-err">Erreur presences: {pendingResult.message}</section> : null}
      {!balanceResult.ok ? <section className="flash-err">Erreur solde: {balanceResult.message}</section> : null}
      {!messagesResult.ok ? <section className="flash-err">Erreur messages: {messagesResult.message}</section> : null}
      {!contractGridsResult.ok ? <section className="flash-err">Erreur grille contractuelle: {contractGridsResult.message}</section> : null}
      {!catalogStudentsResult.ok ? <section className="flash-err">Erreur eleves catalogue: {catalogStudentsResult.message}</section> : null}
      {!catalogProductsResult.ok ? <section className="flash-err">Erreur produits catalogue: {catalogProductsResult.message}</section> : null}
      {!catalogRequestsResult.ok ? <section className="flash-err">Erreur demandes produits: {catalogRequestsResult.message}</section> : null}

      <section className="grid cols-3 prof-kpi-grid">
        <article className="card">
          <h3>Presences en attente</h3>
          <p className="prof-kpi-value">{pendingCount}</p>
          <small className="muted">{pendingRows.length} cours a completer</small>
        </article>
        <article className="card">
          <h3>Cours du jour</h3>
          <p className="prof-kpi-value">{todaySessions.length}</p>
          <small className="muted">Planning de la journee</small>
        </article>
        <article className="card">
          <h3>Mes droits</h3>
          <p className="prof-kpi-value">{canEditPlanning ? "Edition" : "Lecture"}</p>
          <small className="muted">{canMessageStudents ? "Messages eleves autorises" : "Messages eleves non autorises"}</small>
        </article>
      </section>

      {currentTab === "overview" ? (
        <section className="card">
          <div className="row spread">
            <h2>Cours passes sans presence saisie</h2>
            <Link className="mode-link" href={buildProfHref({ tab: "planning", agendaView: "day", agendaDate: todayKeyUtc() })}>
              Voir planning
            </Link>
          </div>
          {pendingRows.length === 0 ? (
            <p className="muted">Aucune saisie en attente.</p>
          ) : (
            <div className="list">
              {pendingRows.map((row) => {
                const dayKey = row.start_at_utc.slice(0, 10);
                const href = buildProfHref({
                  tab: "planning",
                  agendaView: "day",
                  agendaDate: dayKey,
                  sessionId: row.session_id,
                });
                return (
                  <article key={row.session_id} className="item row spread">
                    <div>
                      <strong>{row.title}</strong>
                      <p className="muted">
                        {formatDateTime(row.start_at_utc)} - {formatTime(row.end_at_utc)} | {row.course_type_name} | {row.location_name}
                      </p>
                      <p className="muted">
                        Eleves a saisir: {row.pending_students_count}/{row.total_students_count}
                      </p>
                    </div>
                    <Link className="mode-link" href={href}>
                      Saisir presences
                    </Link>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ) : null}

      {currentTab === "planning" ? (
        <section className="card">
          <div className="row spread">
            <h2>Mes prochains cours</h2>
            <span className="badge">{agendaRange.title}</span>
          </div>

          <form method="get" className="grid cols-4">
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
            <div className="row">
              <button type="submit" className="ghost">Aller</button>
              <Link className="reset-link" href={todayAgendaHref}>
                Aujourd hui
              </Link>
            </div>
            <div className="row">
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
            {agendaDays.map((day) => (
              <article key={day.key} className="agenda-day coach-agenda-day">
                <div className="row spread agenda-day-header">
                  <h3>{day.label}</h3>
                  <span className="badge">{day.sessions.length}</span>
                </div>
                {day.sessions.length === 0 ? (
                  <p className="muted agenda-empty">Aucun cours.</p>
                ) : (
                  <div className="agenda-events coach-agenda-events">
                    {day.sessions.slice(0, maxVisibleSessionsByDay).map((session) => {
                      const pending = pendingAttendanceCount(session);
                      const openHref = buildProfHref({
                        tab: "planning",
                        agendaView,
                        agendaDate,
                        sessionId: session.id,
                      });
                      const trialCount = session.students.filter((student) => student.is_trial_course).length;
                      const firstCount = session.students.filter((student) => student.is_first_course).length;
                      return (
                        <Link key={session.id} className="agenda-event-link" href={openHref}>
                          <article className={`agenda-event coach-agenda-event ${agendaEventStateClass(session.status)}`}>
                            <div className="row spread">
                              <p className="muted">
                                {formatTime(session.start_at_utc)} - {formatTime(session.end_at_utc)}
                              </p>
                              <span className={`status-badge ${statusBadgeClass(session.status)}`}>{statusLabel(session.status)}</span>
                            </div>
                            <h3 className="event-title">{session.title}</h3>
                            <small className="muted event-meta">
                              <span className="meta-icon" aria-hidden="true">
                                🎵
                              </span>
                              {session.course_type.name}
                            </small>
                            <small className="muted event-meta">
                              <span className="meta-icon" aria-hidden="true">
                                📍
                              </span>
                              {session.location.name}
                            </small>
                            <small className="muted event-meta">
                              <span className="meta-icon" aria-hidden="true">
                                👥
                              </span>
                              Places {session.booked_count}/{session.capacity_max}
                            </small>
                            <div className="row">
                              <span className={`occ-badge ${occupancyClass(session.booked_count, session.capacity_max)}`}>
                                {session.booked_count}/{session.capacity_max}
                              </span>
                              <span className={`status-badge ${pending > 0 ? "status-waitlist" : "status-scheduled"}`}>
                                Presences: {pending}
                              </span>
                            </div>
                            {(trialCount > 0 || firstCount > 0) && (
                              <p className="muted event-meta">
                                {trialCount > 0 ? `Essai: ${trialCount}` : ""}
                                {trialCount > 0 && firstCount > 0 ? " | " : ""}
                                {firstCount > 0 ? `Premier cours: ${firstCount}` : ""}
                              </p>
                            )}
                          </article>
                        </Link>
                      );
                    })}
                    {day.sessions.length > maxVisibleSessionsByDay ? (
                      <details className="agenda-more-block coach-agenda-more">
                        <summary>{day.sessions.length - maxVisibleSessionsByDay} more</summary>
                        <div className="agenda-events">
                          {day.sessions.slice(maxVisibleSessionsByDay).map((session) => {
                            const openHref = buildProfHref({
                              tab: "planning",
                              agendaView,
                              agendaDate,
                              sessionId: session.id,
                            });
                            return (
                              <Link key={`${day.key}-${session.id}`} className="agenda-event-link" href={openHref}>
                                <article className={`agenda-event coach-agenda-event ${agendaEventStateClass(session.status)}`}>
                                  <p className="muted">
                                    {formatTime(session.start_at_utc)} - {formatTime(session.end_at_utc)}
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
                )}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {currentTab === "catalog" ? (
        <section className="grid cols-2">
          <article className="card">
            <h2>Signaler un besoin produit</h2>
            <p className="muted">
              Créez une demande pour un eleve. Le statut initial sera “En cours de traitement” puis validé/refusé par l administration.
            </p>
            <form action={professorCreateCatalogRequestAction} className="grid">
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
              <div className="row">
                <button type="submit">Envoyer la demande</button>
              </div>
            </form>
          </article>

          <article className="card">
            <h2>Produits a remettre</h2>
            <p className="muted">Quand le produit est donne a l eleve, utilisez le bouton "Marquer remis".</p>
            {catalogToDeliver.length === 0 ? (
              <p className="muted">Aucun produit en attente de remise.</p>
            ) : (
              <div className="table-wrap">
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
                            {lowOrNegative ? <div className="catalog-stock-alert">⚠ Stock negatif</div> : null}
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
            )}
          </article>

          <article className="card span-2">
            <h2>Historique des demandes produits</h2>
            {catalogRequests.length === 0 ? (
              <p className="muted">Aucune demande.</p>
            ) : (
              <div className="table-wrap">
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
            )}
          </article>
        </section>
      ) : null}

      {currentTab === "finance" ? (
        <section className="grid cols-2">
          <article className="card">
            <h2>Mon solde</h2>
            {balanceResult.ok ? (
              <div className="list">
                <article className="item row spread">
                  <span className="muted">Devise contrat</span>
                  <strong>{balanceResult.data.currency}</strong>
                </article>
                <article className="item row spread">
                  <span className="muted">En attente</span>
                  <strong>
                    {balanceResult.data.pending_amount} {balanceResult.data.currency} ({balanceResult.data.pending_sessions} cours)
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Valide</span>
                  <strong>
                    {balanceResult.data.approved_amount} {balanceResult.data.currency} ({balanceResult.data.approved_sessions} cours)
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Paye</span>
                  <strong>
                    {balanceResult.data.paid_amount} {balanceResult.data.currency} ({balanceResult.data.paid_sessions} cours)
                  </strong>
                </article>
                <article className="item row spread">
                  <span className="muted">Total</span>
                  <strong>
                    {balanceResult.data.total_amount} {balanceResult.data.currency}
                  </strong>
                </article>
              </div>
            ) : (
              <p className="muted">Solde indisponible.</p>
            )}
          </article>
          <article className="card">
            <h2>Suivi des paiements</h2>
            {payoutsResult.ok && payoutsResult.data.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Cours</th>
                      <th>Montant</th>
                      <th>Statut</th>
                      <th>Paye le</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payoutsResult.data.map((row) => (
                      <tr key={row.payout_id}>
                        <td>
                          {row.course_type_name} - {row.location_name}
                          <br />
                          <small className="muted">{formatDateTime(row.session_start_at_utc)}</small>
                        </td>
                        <td>
                          {row.amount_snapshot} {row.currency_snapshot}
                        </td>
                        <td>{row.payout_status}</td>
                        <td>{row.paid_at ? formatDateTime(row.paid_at) : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">Aucun paiement enregistre.</p>
            )}
          </article>

          <article className="card span-2">
            <h2>Ma grille contractuelle</h2>
            {contractGridsResult.ok && contractGridsResult.data.length > 0 ? (
              <div className="list">
                {contractGridsResult.data.map((grid) => (
                  <article key={grid.grid_id} className="item">
                    <div className="row spread">
                      <strong>{grid.location_label}</strong>
                      <span className="badge">
                        {grid.valid_from} - {grid.valid_to ?? "non definie"}
                      </span>
                    </div>
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
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">Aucune grille contractuelle active a cette date.</p>
            )}
          </article>
        </section>
      ) : null}

      {currentTab === "messages" ? (
        <section className="card">
          <h2>Messages envoyes (groupe + eleve)</h2>
          {messagesResult.ok && archivedMessages.length > 0 ? (
            <div className="list">
              {archivedMessages.map((message) => {
                const parsedSubject = parseMessageSubject(message.subject);
                return (
                  <a
                    key={message.id}
                    href={buildProfHref({ tab: "messages", agendaView, agendaDate, messageId: message.id })}
                    className="item mode-link"
                  >
                    <div className="row spread">
                      <strong>{parsedSubject.cleanedSubject}</strong>
                      <div className="row">
                        <span className="badge">
                          {parsedSubject.targetLabel ? `Eleve: ${parsedSubject.targetLabel}` : "Groupe"}
                        </span>
                        <span className="badge">{message.recipient_count} destinataire(s)</span>
                      </div>
                    </div>
                    <p className="muted">
                      Envoye le {formatDateTime(message.sent_at)} | Format: {message.body_format}
                    </p>
                    <p>{message.body_format === "HTML" ? stripHtml(message.body) : message.body}</p>
                  </a>
                );
              })}
            </div>
          ) : (
            <p className="muted">Aucun message archive.</p>
          )}
        </section>
      ) : null}

      {currentTab === "profile" ? (
        <section className="grid cols-2">
          <article className="card">
            <h2>Mon profil</h2>
            <div className="list">
              <article className="item row spread">
                <span className="muted">Nom</span>
                <strong>{fullName || "-"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Email</span>
                <strong>{profile.email}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Telephone</span>
                <strong>{profile.phone ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Lien Zoom</span>
                <strong>{profile.zoom_link ?? "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Langues</span>
                <strong>{profile.spoken_languages.length > 0 ? profile.spoken_languages.join(", ") : "Non renseigne"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Devise contrat</span>
                <strong>{profile.payout_currency}</strong>
              </article>
            </div>
          </article>
          <article className="card">
            <h2>Email quotidien planning</h2>
            <div className="list">
              <article className="item row spread">
                <span className="muted">Activation</span>
                <strong>{profile.daily_schedule_email_enabled ? "Activee" : "Desactivee"}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Heure UTC</span>
                <strong>{profile.daily_schedule_email_time}</strong>
              </article>
              <article className="item row spread">
                <span className="muted">Ignorer les jours sans cours</span>
                <strong>{profile.daily_schedule_skip_if_no_course ? "Oui" : "Non"}</strong>
              </article>
            </div>
            <p className="muted top-gap-sm">
              Reglage configure par l administration. Le digest recapitule vos cours du jour et la liste des eleves.
            </p>
          </article>
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
              {statusLabel(selectedSession.status)}
            </p>
            <div className="row">
              <span className={`occ-badge ${selectedSession.booked_count >= selectedSession.capacity_max ? "occ-high" : "occ-low"}`}>
                {selectedSession.booked_count}/{selectedSession.capacity_max}
              </span>
              <span className={`status-badge ${statusBadgeClass(selectedSession.status)}`}>{statusLabel(selectedSession.status)}</span>
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
                    {parsedSubject.targetLabel ? `Eleve: ${parsedSubject.targetLabel}` : "Message groupe"}
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
