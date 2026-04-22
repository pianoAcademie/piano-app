import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { AttendanceReportRow, ProfessorStatementRow, ReservationReportRow, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

function formatDate(value: string, language: UiLanguage): string {
  return new Date(value).toLocaleString(localeForUiLanguage(language), {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default async function AdminReportingPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const [reservationsResult, attendanceResult, statementsResult] = await Promise.all([
    backendRequest<ReservationReportRow[]>("/api/v1/admin/reports/reservations", {}, token),
    backendRequest<AttendanceReportRow[]>("/api/v1/admin/reports/attendance", {}, token),
    backendRequest<ProfessorStatementRow[]>("/api/v1/admin/reports/professor-statements", {}, token),
  ]);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.reporting.title")}</h2>
        <p className="muted">{t("admin.reporting.subtitle")}</p>
      </section>

      <section className="grid cols-3">
        <article className="card">
          <h3>{t("admin.reporting.reservations")}</h3>
          <p className="muted">{reservationsResult.ok ? t("admin.reporting.rows_count", { count: reservationsResult.data.length }) : t("admin.reporting.error_prefix", { message: reservationsResult.message })}</p>
        </article>

        <article className="card">
          <h3>{t("admin.reporting.attendance")}</h3>
          <p className="muted">{attendanceResult.ok ? t("admin.reporting.rows_count", { count: attendanceResult.data.length }) : t("admin.reporting.error_prefix", { message: attendanceResult.message })}</p>
        </article>

        <article className="card">
          <h3>{t("admin.reporting.professor_statements")}</h3>
          <p className="muted">{statementsResult.ok ? t("admin.reporting.rows_count", { count: statementsResult.data.length }) : t("admin.reporting.error_prefix", { message: statementsResult.message })}</p>
        </article>
      </section>

      <section className="grid cols-2">
        <article className="card">
          <h3>{t("admin.reporting.latest_reservations")}</h3>
          {reservationsResult.ok ? (
            <div className="list">
              {reservationsResult.data.slice(0, 8).map((row) => (
                <article key={row.booking_id} className="item">
                  <strong>{row.course_type_name}</strong>
                  <p className="muted">
                    {formatDate(row.start_at_utc, language)} | {row.location_name} | {row.client_email}
                  </p>
                </article>
              ))}
              {reservationsResult.data.length === 0 ? <p className="muted">{t("admin.reporting.no_reservation")}</p> : null}
            </div>
          ) : (
            <p className="muted">{t("admin.reporting.unable_to_load")}</p>
          )}
        </article>

        <article className="card">
          <h3>{t("admin.reporting.latest_professor_statements")}</h3>
          {statementsResult.ok ? (
            <div className="list">
              {statementsResult.data.slice(0, 8).map((row) => (
                <article key={row.session_id} className="item">
                  <strong>{row.professor_name}</strong>
                  <p className="muted">
                    {formatDate(row.start_at_utc, language)} | {row.course_type_name} | {t("admin.reporting.session_status", { status: row.session_status })}
                  </p>
                </article>
              ))}
              {statementsResult.data.length === 0 ? <p className="muted">{t("admin.reporting.no_statement")}</p> : null}
            </div>
          ) : (
            <p className="muted">{t("admin.reporting.unable_to_load")}</p>
          )}
        </article>
      </section>
    </section>
  );
}
