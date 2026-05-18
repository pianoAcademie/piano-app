import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type {
  AttendanceReportRow,
  IntakeFamilyChildSummary,
  IntakeFamilySummaryRow,
  ProfessorStatementRow,
  ReservationReportRow,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

function formatDate(value: string, language: UiLanguage): string {
  return new Date(value).toLocaleString(localeForUiLanguage(language), {
    dateStyle: "short",
    timeStyle: "short",
  });
}

const FAMILY_SUMMARY_ROWS: Array<{ key: keyof Pick<IntakeFamilyChildSummary, "course_1" | "course_2" | "solfege" | "masterclass" | "pass_recup">; labelKey: string }> = [
  { key: "course_1", labelKey: "admin.reporting.family_course_1" },
  { key: "course_2", labelKey: "admin.reporting.family_course_2" },
  { key: "solfege", labelKey: "admin.reporting.family_solfege" },
  { key: "masterclass", labelKey: "admin.reporting.family_masterclass" },
  { key: "pass_recup", labelKey: "admin.reporting.family_pass_recup" },
];

export default async function AdminReportingPage(): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const [reservationsResult, attendanceResult, statementsResult, intakeFamiliesResult] = await Promise.all([
    backendRequest<ReservationReportRow[]>("/api/v1/admin/reports/reservations", {}, token),
    backendRequest<AttendanceReportRow[]>("/api/v1/admin/reports/attendance", {}, token),
    backendRequest<ProfessorStatementRow[]>("/api/v1/admin/reports/professor-statements", {}, token),
    backendRequest<IntakeFamilySummaryRow[]>("/api/v1/admin/reports/intake-families", {}, token),
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

        <article className="card">
          <h3>{t("admin.reporting.intake_families")}</h3>
          <p className="muted">{intakeFamiliesResult.ok ? t("admin.reporting.rows_count", { count: intakeFamiliesResult.data.length }) : t("admin.reporting.error_prefix", { message: intakeFamiliesResult.message })}</p>
        </article>
      </section>

      <section className="card">
        <h3>{t("admin.reporting.intake_families_title")}</h3>
        <p className="muted">{t("admin.reporting.intake_families_help")}</p>
        {intakeFamiliesResult.ok ? (
          intakeFamiliesResult.data.length > 0 ? (
            <div className="list top-gap-sm">
              {intakeFamiliesResult.data.map((family) => (
                <article key={family.family_key} className="item">
                  <strong>{family.family_label}</strong>
                  <p className="muted">
                    {t("admin.reporting.intake_family_meta", {
                      count: family.intake_count,
                      contact: family.parent_email || family.parent_phone || "-",
                    })}
                  </p>
                  <div className="table-wrap top-gap-sm">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{t("admin.reporting.family_row")}</th>
                          {family.children.map((child) => (
                            <th key={child.intake_id}>
                              {child.child_name}
                              <br />
                              <span className="muted">{child.source_form_label || child.source_form_id}</span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {FAMILY_SUMMARY_ROWS.map((summaryRow) => (
                          <tr key={summaryRow.key}>
                            <th>{t(summaryRow.labelKey)}</th>
                            {family.children.map((child) => (
                              <td key={`${child.intake_id}-${summaryRow.key}`}>{child[summaryRow.key] || "-"}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted">{t("admin.reporting.no_intake_family")}</p>
          )
        ) : (
          <p className="muted">{t("admin.reporting.unable_to_load")}</p>
        )}
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
