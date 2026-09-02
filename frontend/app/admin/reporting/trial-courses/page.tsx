import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { hasAdminPermission } from "../../../../lib/admin-access";
import { backendRequest } from "../../../../lib/backend";
import type { AdminProfessorOut, LocationOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type TrialCourseReportRow = {
  booking_id: string;
  session_id: string;
  session_start_at: string;
  session_end_at: string;
  session_timezone: string;
  course_type_name: string;
  course_format: "COLLECTIF" | "PARTICULIER";
  location_id: string;
  location_name: string;
  professor_id: string | null;
  professor_name: string;
  student_id: string;
  student_first_name: string | null;
  student_last_name: string | null;
  student_email: string;
  parent_email: string | null;
  attendance_status: string;
  attendance_label: string;
  internal_note: string | null;
  conversion_status: string;
  account_status_label: string;
  client_kind: string;
  client_status: string;
  has_intake: boolean;
  intake_status_label: string;
  intake_status: string | null;
  intake_received_at: string | null;
  quote_status: string | null;
  quote_status_label: string;
  is_registered: boolean;
  enrollment_status_label: string;
  enrollment_evidence: string | null;
  email_history: Array<{
    communication_id: string;
    trigger_code: string;
    trigger_label: string;
    subject: string;
    delivery_status: string;
    sent_at: string;
    delivered_at: string | null;
  }>;
  trial_detection_source: string;
};

function firstParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function isoDate(value: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function defaultDates(): { from: string; to: string } {
  const today = new Date();
  const to = new Date(today);
  to.setDate(to.getDate() + 30);
  return { from: isoDate(today), to: isoDate(to) };
}

function reportQuery(values: Record<string, string>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value.trim()) {
      params.set(key, value.trim());
    }
  }
  return params.toString();
}

function localDateTime(value: string, timezone: string, language: UiLanguage): { date: string; time: string } {
  const parsed = new Date(value);
  const options = { timeZone: timezone || "Europe/Paris" };
  try {
    return {
      date: new Intl.DateTimeFormat(localeForUiLanguage(language), { ...options, dateStyle: "short" }).format(parsed),
      time: new Intl.DateTimeFormat(localeForUiLanguage(language), { ...options, hour: "2-digit", minute: "2-digit" }).format(parsed),
    };
  } catch {
    return localDateTime(value, "Europe/Paris", language);
  }
}

function localDay(value: string, timezone: string, language: UiLanguage): { key: string; label: string } {
  const parsed = new Date(value);
  const safeTimezone = timezone || "Europe/Paris";
  try {
    const keyParts = new Intl.DateTimeFormat("en-CA", {
      timeZone: safeTimezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(parsed);
    const keyValues = Object.fromEntries(keyParts.map((part) => [part.type, part.value]));
    return {
      key: `${keyValues.year}-${keyValues.month}-${keyValues.day}`,
      label: new Intl.DateTimeFormat(localeForUiLanguage(language), {
        timeZone: safeTimezone,
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(parsed),
    };
  } catch {
    return localDay(value, "Europe/Paris", language);
  }
}

function groupRowsByDay(rows: TrialCourseReportRow[], language: UiLanguage): Array<{
  key: string;
  label: string;
  rows: TrialCourseReportRow[];
}> {
  const groups = new Map<string, { key: string; label: string; rows: TrialCourseReportRow[] }>();
  for (const row of [...rows].sort((left, right) => (
    new Date(left.session_start_at).getTime() - new Date(right.session_start_at).getTime()
  ))) {
    const day = localDay(row.session_start_at, row.session_timezone, language);
    const group = groups.get(day.key) ?? { ...day, rows: [] };
    group.rows.push(row);
    groups.set(day.key, group);
  }
  return [...groups.values()];
}

function attendanceClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ATTENDED") {
    return "status-ok";
  }
  if (["CANCELLED", "NO_SHOW", "WAITLISTED"].includes(normalized)) {
    return "status-off";
  }
  return "status-warn";
}

function deliveryStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  const labels = language === "fr"
    ? { DELIVERED: "Délivré", SENT: "Envoyé", QUEUED: "En attente", FAILED: "Échec", UNKNOWN: "Statut inconnu" }
    : { DELIVERED: "Delivered", SENT: "Sent", QUEUED: "Queued", FAILED: "Failed", UNKNOWN: "Unknown status" };
  return labels[normalized as keyof typeof labels] ?? normalized;
}

const LABELS = {
  fr: {
    title: "Essais à venir",
    subtitle: "Tous les cours d'essai planifiés, regroupés par jour, quel que soit le type de cours.",
    back: "Retour au reporting",
    from: "Du",
    to: "Au",
    professor: "Professeur",
    location: "Lieu",
    allProfessors: "Tous les professeurs",
    allLocations: "Tous les lieux",
    includeInactive: "Afficher aussi les réservations annulées et les listes d'attente",
    apply: "Appliquer",
    reset: "Réinitialiser",
    export: "Exporter en Excel",
    total: "Essais à venir",
    days: "Jours concernés",
    locationsCount: "Lieux concernés",
    professorsCount: "Professeurs concernés",
    trial: "essai",
    trials: "essais",
    slot: "Créneau",
    openSlot: "Ouvrir le créneau",
    course: "Cours",
    student: "Élève",
    note: "Note interne professeur",
    attendance: "Présence",
    status: "Statut de suivi",
    emails: "E-mails automatiques",
    noEmail: "Aucun trigger e-mail retrouvé",
    noRows: "Aucun cours d'essai ne correspond à ces filtres.",
  },
  en: {
    title: "Upcoming trial lessons",
    subtitle: "All scheduled trial lessons, grouped by day, across every course type.",
    back: "Back to reporting",
    from: "From",
    to: "To",
    professor: "Teacher",
    location: "Location",
    allProfessors: "All teachers",
    allLocations: "All locations",
    includeInactive: "Also show cancelled bookings and waiting lists",
    apply: "Apply",
    reset: "Reset",
    export: "Export to Excel",
    total: "Upcoming trials",
    days: "Scheduled days",
    locationsCount: "Locations",
    professorsCount: "Teachers",
    trial: "trial",
    trials: "trials",
    slot: "Time slot",
    openSlot: "Open time slot",
    course: "Course",
    student: "Student",
    note: "Internal teacher note",
    attendance: "Attendance",
    status: "Follow-up status",
    emails: "Automated emails",
    noEmail: "No email trigger found",
    noRows: "No trial lesson matches these filters.",
  },
};

export default async function TrialCoursesReportPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_upcoming_trials")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const labels = LABELS[language];
  const defaults = defaultDates();
  const dateFrom = firstParam(searchParams, "date_from") || defaults.from;
  const dateTo = firstParam(searchParams, "date_to") || defaults.to;
  const professorId = firstParam(searchParams, "professor_id");
  const locationId = firstParam(searchParams, "location_id");
  const includeInactive = ["1", "true", "on"].includes(firstParam(searchParams, "include_inactive").toLowerCase());
  const query = reportQuery({
    date_from: dateFrom,
    date_to: dateTo,
    professor_id: professorId,
    location_id: locationId,
    include_inactive: includeInactive ? "true" : "false",
  });

  const [rowsResult, professorsResult, locationsResult] = await Promise.all([
    backendRequest<TrialCourseReportRow[]>(`/api/v1/admin/reports/trial-courses?${query}`, {}, token),
    backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors?active_only=false&limit=1000", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
  ]);
  const rows = rowsResult.ok ? rowsResult.data : [];
  const professors = professorsResult.ok
    ? professorsResult.data.map((professor) => ({
      id: professor.id,
      name: `${professor.first_name} ${professor.last_name}`.trim(),
    }))
    : Array.from(
      new Map(
        rows
          .filter((row) => row.professor_id)
          .map((row) => [row.professor_id as string, { id: row.professor_id as string, name: row.professor_name }]),
      ).values(),
    ).sort((left, right) => left.name.localeCompare(right.name, localeForUiLanguage(language)));
  const locations = locationsResult.ok ? locationsResult.data : [];
  const dayGroups = groupRowsByDay(rows, language);
  const locationCount = new Set(rows.map((row) => row.location_id)).size;
  const professorCount = new Set(rows.map((row) => row.professor_id).filter(Boolean)).size;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="section-title-row">
          <div>
            <h2>{labels.title}</h2>
            <p className="muted">{labels.subtitle}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="button-link" href="/admin/reporting">{labels.back}</Link>
            <a className="button-link" href={`/admin/reporting/trial-courses/export?${query}`}>{labels.export}</a>
          </div>
        </div>
      </section>

      <section className="card">
        <form className="grid cols-4 config-form-grid" method="get">
          <label>
            {labels.from}
            <input type="date" name="date_from" defaultValue={dateFrom} />
          </label>
          <label>
            {labels.to}
            <input type="date" name="date_to" defaultValue={dateTo} />
          </label>
          <label>
            {labels.professor}
            <select name="professor_id" defaultValue={professorId}>
              <option value="">{labels.allProfessors}</option>
              {professors.map((professor) => (
                <option key={professor.id} value={professor.id}>{professor.name}</option>
              ))}
            </select>
          </label>
          <label>
            {labels.location}
            <select name="location_id" defaultValue={locationId}>
              <option value="">{labels.allLocations}</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
          </label>
          <label className="checkbox span-4 trial-report-inactive-filter">
            <input type="checkbox" name="include_inactive" value="true" defaultChecked={includeInactive} />
            <span>{labels.includeInactive}</span>
          </label>
          <div className="form-actions span-4">
            <Link className="button-link" href="/admin/reporting/trial-courses">{labels.reset}</Link>
            <button type="submit">{labels.apply}</button>
          </div>
        </form>
        {!rowsResult.ok ? <p className="error-text top-gap-sm">{rowsResult.message}</p> : null}
      </section>

      <section className="grid cols-4">
        {[
          [labels.total, String(rows.length)],
          [labels.days, String(dayGroups.length)],
          [labels.locationsCount, String(locationCount)],
          [labels.professorsCount, String(professorCount)],
        ].map(([label, value]) => (
          <article className="card" key={label}>
            <p className="muted">{label}</p>
            <h3>{value}</h3>
          </article>
        ))}
      </section>

      {dayGroups.length > 0 ? (
        <section className="trial-report-day-list">
          {dayGroups.map((group) => (
            <section className="card trial-report-day-card" key={group.key}>
              <div className="trial-report-day-header">
                <h3>{group.label}</h3>
                <span className="status-pill status-warn">
                  {group.rows.length} {group.rows.length > 1 ? labels.trials : labels.trial}
                </span>
              </div>
              <div className="table-wrap">
                <table className="data-table trial-report-table">
                  <thead>
                    <tr>
                      <th>{labels.slot}</th>
                      <th>{labels.student}</th>
                      <th>{labels.course}</th>
                      <th>{labels.professor}</th>
                      <th>{labels.location}</th>
                      <th>{labels.attendance}</th>
                      <th>{labels.status}</th>
                      <th>{labels.emails}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((row) => {
                      const startsAt = localDateTime(row.session_start_at, row.session_timezone, language);
                      const endsAt = localDateTime(row.session_end_at, row.session_timezone, language);
                      return (
                        <tr key={row.booking_id}>
                          <td>
                            <Link className="trial-report-slot-link" href={`/admin?session_id=${encodeURIComponent(row.session_id)}`}>
                              <strong>{startsAt.time} – {endsAt.time}</strong>
                              <small className="muted">{labels.openSlot}</small>
                            </Link>
                          </td>
                          <td>
                            <Link href={`/admin/clients/${encodeURIComponent(row.student_id)}`}>
                              <strong>{row.student_first_name || ""} {row.student_last_name || ""}</strong>
                            </Link>
                            <br /><small className="muted">{row.parent_email || row.student_email}</small>
                          </td>
                          <td>
                            <strong>{row.course_type_name}</strong>
                            <br /><small className="muted">{row.course_format === "PARTICULIER" ? "Particulier" : "Collectif"}</small>
                            {row.internal_note ? <small className="trial-report-course-note">{row.internal_note}</small> : null}
                          </td>
                          <td>{row.professor_name}</td>
                          <td><strong>{row.location_name}</strong></td>
                          <td><span className={`status-pill ${attendanceClass(row.attendance_status)}`}>{row.attendance_label}</span></td>
                          <td>
                            <strong>{row.conversion_status}</strong>
                            <small className="trial-report-followup-evidence">
                              Compte : {row.account_status_label}<br />
                              Intake : {row.intake_status_label}<br />
                              Devis : {row.quote_status_label}<br />
                              Inscription : {row.enrollment_status_label}
                            </small>
                          </td>
                          <td>
                            {row.email_history.length > 0 ? (
                              <ul className="trial-report-email-history">
                                {row.email_history.map((event) => {
                                  const sentAt = localDateTime(event.sent_at, row.session_timezone, language);
                                  return (
                                    <li key={event.communication_id} title={event.subject}>
                                      <strong>{event.trigger_label}</strong>
                                      <small>{sentAt.date} à {sentAt.time} · {deliveryStatusLabel(event.delivery_status, language)}</small>
                                      <small className="muted">{event.trigger_code}</small>
                                    </li>
                                  );
                                })}
                              </ul>
                            ) : <small className="muted">{labels.noEmail}</small>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </section>
      ) : (
        <section className="card"><p className="muted">{labels.noRows}</p></section>
      )}
    </section>
  );
}
