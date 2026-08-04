import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

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
  client_status: string;
  has_intake: boolean;
  intake_status: string | null;
  intake_received_at: string | null;
  quote_status: string | null;
  is_registered: boolean;
  trial_detection_source: string;
};

function firstParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function defaultDates(): { from: string; to: string } {
  const today = new Date();
  const from = new Date(today);
  const to = new Date(today);
  from.setDate(from.getDate() - 90);
  to.setDate(to.getDate() + 30);
  return { from: isoDate(from), to: isoDate(to) };
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

const LABELS = {
  fr: {
    title: "Suivi des cours d'essai",
    subtitle: "Tous les essais, quel que soit le type de cours, avec présence et avancement commercial.",
    back: "Retour au reporting",
    from: "Du",
    to: "Au",
    professor: "Professeur",
    location: "Lieu",
    all: "Tous",
    apply: "Appliquer",
    reset: "Réinitialiser",
    export: "Exporter en Excel",
    total: "Cours d'essai",
    attended: "Présents",
    intakes: "Intakes remplis",
    registered: "Inscriptions finales",
    rate: "Taux de conversion",
    dateTime: "Date et heure",
    course: "Cours",
    student: "Élève",
    note: "Note interne professeur",
    attendance: "Présence",
    status: "Statut de suivi",
    noRows: "Aucun cours d'essai ne correspond à ces filtres.",
  },
  en: {
    title: "Trial lesson tracking",
    subtitle: "All trial lessons, across every course type, with attendance and commercial progress.",
    back: "Back to reporting",
    from: "From",
    to: "To",
    professor: "Teacher",
    location: "Location",
    all: "All",
    apply: "Apply",
    reset: "Reset",
    export: "Export to Excel",
    total: "Trial lessons",
    attended: "Attended",
    intakes: "Completed intakes",
    registered: "Final registrations",
    rate: "Conversion rate",
    dateTime: "Date and time",
    course: "Course",
    student: "Student",
    note: "Internal teacher note",
    attendance: "Attendance",
    status: "Follow-up status",
    noRows: "No trial lesson matches these filters.",
  },
};

export default async function TrialCoursesReportPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const labels = LABELS[language];
  const defaults = defaultDates();
  const dateFrom = firstParam(searchParams, "date_from") || defaults.from;
  const dateTo = firstParam(searchParams, "date_to") || defaults.to;
  const professorId = firstParam(searchParams, "professor_id");
  const locationId = firstParam(searchParams, "location_id");
  const query = reportQuery({ date_from: dateFrom, date_to: dateTo, professor_id: professorId, location_id: locationId });

  const [rowsResult, professorsResult, locationsResult] = await Promise.all([
    backendRequest<TrialCourseReportRow[]>(`/api/v1/admin/reports/trial-courses?${query}`, {}, token),
    backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors?active_only=false&limit=1000", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
  ]);
  const rows = rowsResult.ok ? rowsResult.data : [];
  const professors = professorsResult.ok ? professorsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const attended = rows.filter((row) => row.attendance_status === "ATTENDED").length;
  const intakes = rows.filter((row) => row.has_intake).length;
  const registered = rows.filter((row) => row.is_registered).length;
  const conversionRate = rows.length > 0 ? registered / rows.length : 0;

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
              <option value="">{labels.all}</option>
              {professors.map((professor) => (
                <option key={professor.id} value={professor.id}>{professor.first_name} {professor.last_name}</option>
              ))}
            </select>
          </label>
          <label>
            {labels.location}
            <select name="location_id" defaultValue={locationId}>
              <option value="">{labels.all}</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>{location.name}</option>
              ))}
            </select>
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
          [labels.attended, String(attended)],
          [labels.intakes, String(intakes)],
          [labels.registered, `${registered} · ${new Intl.NumberFormat(localeForUiLanguage(language), { style: "percent", maximumFractionDigits: 1 }).format(conversionRate)}`],
        ].map(([label, value]) => (
          <article className="card" key={label}>
            <p className="muted">{label}</p>
            <h3>{value}</h3>
          </article>
        ))}
      </section>

      <section className="card">
        {rows.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{labels.dateTime}</th>
                  <th>{labels.course}</th>
                  <th>{labels.professor}</th>
                  <th>{labels.student}</th>
                  <th>{labels.note}</th>
                  <th>{labels.attendance}</th>
                  <th>{labels.status}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const when = localDateTime(row.session_start_at, row.session_timezone, language);
                  return (
                    <tr key={row.booking_id}>
                      <td><strong>{when.date}</strong><br /><span className="muted">{when.time}</span></td>
                      <td><strong>{row.course_type_name}</strong><br /><span className="muted">{row.course_format === "PARTICULIER" ? "Particulier" : "Collectif"} · {row.location_name}</span></td>
                      <td>{row.professor_name}</td>
                      <td>
                        <Link href={`/admin/clients/${encodeURIComponent(row.student_id)}`}><strong>{row.student_first_name || ""} {row.student_last_name || ""}</strong></Link>
                        <br /><span className="muted">{row.parent_email || row.student_email}</span>
                      </td>
                      <td style={{ whiteSpace: "pre-wrap", minWidth: 240 }}>{row.internal_note || "-"}</td>
                      <td><span className="status-pill">{row.attendance_label}</span></td>
                      <td>
                        <strong>{row.conversion_status}</strong>
                        <br /><span className="muted">Intake: {row.has_intake ? "oui" : "non"}{row.quote_status ? ` · Devis: ${row.quote_status}` : ""}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">{labels.noRows}</p>}
      </section>
    </section>
  );
}
