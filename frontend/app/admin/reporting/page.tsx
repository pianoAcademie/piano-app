import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { AttendanceReportRow, ProfessorStatementRow, ReservationReportRow } from "../../../lib/types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default async function AdminReportingPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const [reservationsResult, attendanceResult, statementsResult] = await Promise.all([
    backendRequest<ReservationReportRow[]>("/api/v1/admin/reports/reservations", {}, token),
    backendRequest<AttendanceReportRow[]>("/api/v1/admin/reports/attendance", {}, token),
    backendRequest<ProfessorStatementRow[]>("/api/v1/admin/reports/professor-statements", {}, token),
  ]);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Reporting</h2>
        <p className="muted">Suivi reservations, presence eleves et releves professeurs.</p>
      </section>

      <section className="grid cols-3">
        <article className="card">
          <h3>Reservations</h3>
          <p className="muted">{reservationsResult.ok ? `${reservationsResult.data.length} lignes` : `Erreur: ${reservationsResult.message}`}</p>
        </article>

        <article className="card">
          <h3>Presence</h3>
          <p className="muted">{attendanceResult.ok ? `${attendanceResult.data.length} lignes` : `Erreur: ${attendanceResult.message}`}</p>
        </article>

        <article className="card">
          <h3>Releves professeurs</h3>
          <p className="muted">{statementsResult.ok ? `${statementsResult.data.length} lignes` : `Erreur: ${statementsResult.message}`}</p>
        </article>
      </section>

      <section className="grid cols-2">
        <article className="card">
          <h3>Dernieres reservations</h3>
          {reservationsResult.ok ? (
            <div className="list">
              {reservationsResult.data.slice(0, 8).map((row) => (
                <article key={row.booking_id} className="item">
                  <strong>{row.course_type_name}</strong>
                  <p className="muted">
                    {formatDate(row.start_at_utc)} | {row.location_name} | {row.client_email}
                  </p>
                </article>
              ))}
              {reservationsResult.data.length === 0 ? <p className="muted">Aucune reservation.</p> : null}
            </div>
          ) : (
            <p className="muted">Impossible de charger.</p>
          )}
        </article>

        <article className="card">
          <h3>Derniers releves professeurs</h3>
          {statementsResult.ok ? (
            <div className="list">
              {statementsResult.data.slice(0, 8).map((row) => (
                <article key={row.session_id} className="item">
                  <strong>{row.professor_name}</strong>
                  <p className="muted">
                    {formatDate(row.start_at_utc)} | {row.course_type_name} | Statut session: {row.session_status}
                  </p>
                </article>
              ))}
              {statementsResult.data.length === 0 ? <p className="muted">Aucun releve.</p> : null}
            </div>
          ) : (
            <p className="muted">Impossible de charger.</p>
          )}
        </article>
      </section>
    </section>
  );
}
