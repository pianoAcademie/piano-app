import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { hasAdminPermission } from "../../../../lib/admin-access";
import { backendRequest } from "../../../../lib/backend";
import type { AdminProfessorOut, TeacherStatementOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type AttendanceRow = {
  student_name: string;
  status: string;
};

type StatementSessionRow = {
  id: string;
  title: string;
  startAt: string;
  endAt: string;
  location: string;
  durationMinutes: number;
  hourlyRateHt: number;
  amountHt: number;
  attendance: AttendanceRow[];
};

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function safeNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: number, currency: string, language: UiLanguage): string {
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
    minimumFractionDigits: 2,
  }).format(value);
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleDateString(localeForUiLanguage(language), {
    timeZone: "Europe/Paris",
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatTime(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleTimeString(localeForUiLanguage(language), {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function attendanceLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ATTENDED") return uiText(language, "admin.teacher_invoicing.attendance_present");
  if (normalized === "NO_SHOW") return uiText(language, "admin.teacher_invoicing.attendance_no_show");
  if (normalized === "EXCUSED_ABSENCE") return uiText(language, "admin.teacher_invoicing.attendance_excused");
  if (normalized === "BOOKED") return uiText(language, "admin.teacher_invoicing.attendance_pending");
  return status || "-";
}

function attendanceTone(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "ATTENDED") return "status-ok";
  if (normalized === "BOOKED") return "status-warn";
  if (normalized === "NO_SHOW") return "status-error";
  return "status-off";
}

function flattenSessions(statements: TeacherStatementOut[]): StatementSessionRow[] {
  const rows: StatementSessionRow[] = [];
  for (const statement of statements) {
    for (const line of statement.lines) {
      const rawItems = (line.meta as Record<string, unknown> | null)?.session_items;
      if (!Array.isArray(rawItems)) continue;
      rawItems.forEach((rawItem, index) => {
        const item = (rawItem ?? {}) as Record<string, unknown>;
        const rawAttendance = Array.isArray(item.attendance) ? item.attendance : [];
        rows.push({
          id: String(item.session_id ?? `${line.course_type_id ?? line.course_type_label}-${index}`),
          title: String(item.title ?? line.course_type_label),
          startAt: String(item.start_at_utc ?? ""),
          endAt: String(item.end_at_utc ?? ""),
          location: String(item.location_name ?? "-"),
          durationMinutes: Math.max(0, safeNumber(item.duration_minutes)),
          hourlyRateHt: safeNumber(item.unit_rate_ht ?? line.unit_rate_ht),
          amountHt: safeNumber(item.amount_ht ?? line.amount_ht),
          attendance: rawAttendance
            .map((rawRow) => {
              const row = (rawRow ?? {}) as Record<string, unknown>;
              return {
                student_name: String(row.student_name ?? "-").trim() || "-",
                status: String(row.status ?? "").trim(),
              };
            })
            .sort((a, b) => a.student_name.localeCompare(b.student_name)),
        });
      });
    }
  }
  return rows.sort((a, b) => new Date(a.startAt).getTime() - new Date(b.startAt).getTime());
}

function currentPeriod(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value ?? "2026";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  return `${year}-${month}`;
}

export default async function AdminTeacherInvoicingStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_invoices_and_accounts")) redirect("/login?error_code=admin_access_required");

  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const professorId = readParam(searchParams, "professor_id").trim();
  const requestedPeriod = readParam(searchParams, "period").trim() || currentPeriod();
  const periodMatch = /^(20\d{2})-(0[1-9]|1[0-2])$/.exec(requestedPeriod);
  const period = periodMatch ? requestedPeriod : currentPeriod();
  const year = Number(period.slice(0, 4));
  const month = Number(period.slice(5, 7));

  const professorsResult = await backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors?active_only=true&limit=1000", {}, token);
  const professors = professorsResult.ok
    ? [...professorsResult.data].sort((a, b) => `${a.last_name} ${a.first_name}`.localeCompare(`${b.last_name} ${b.first_name}`))
    : [];
  const selectedProfessor = professors.find((row) => row.id === professorId) ?? null;
  const statementsResult = professorId
    ? await backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/admin/statements/${professorId}/${year}/${month}`, {}, token)
    : null;
  const statements = statementsResult?.ok ? statementsResult.data : [];
  const sessions = flattenSessions(statements);
  const currency = statements[0]?.currency || "EUR";
  const totalHours = statements.reduce(
    (statementSum, statement) => statementSum + statement.lines.reduce((lineSum, line) => lineSum + safeNumber(line.hours), 0),
    0,
  );
  const totalHt = statements.reduce((sum, statement) => sum + safeNumber(statement.totals_ht), 0);
  const attendanceComplete = statements.length > 0 && statements.every((statement) => statement.attendance_complete);
  const exportHref = professorId
    ? `/admin/teacher-invoicing/statements/export?professor_id=${encodeURIComponent(professorId)}&year=${year}&month=${month}`
    : "";
  const exportPdfHref = professorId
    ? `/admin/teacher-invoicing/statements/export-pdf?professor_id=${encodeURIComponent(professorId)}&year=${year}&month=${month}`
    : "";

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="statements" language={language} isFullAdmin={meResult.data.role === "admin"} />

      {!professorsResult.ok ? <section className="flash-err">{t("admin.teacher_invoicing.backend_error")}: {professorsResult.message}</section> : null}
      {statementsResult && !statementsResult.ok ? <section className="flash-err">{t("admin.teacher_invoicing.backend_error")}: {statementsResult.message}</section> : null}

      <section className="card">
        <h3>{t("admin.teacher_invoicing.monthly_statement_title")}</h3>
        <p className="muted">{t("admin.teacher_invoicing.monthly_statement_help")}</p>
        <form method="get" className="row catalog-admin-filters">
          <label>
            {t("admin.teacher_invoicing.teacher")}
            <select name="professor_id" defaultValue={professorId} required>
              <option value="">{t("admin.teacher_invoicing.choose_teacher")}</option>
              {professors.map((professor) => (
                <option key={professor.id} value={professor.id}>{professor.first_name} {professor.last_name}</option>
              ))}
            </select>
          </label>
          <label>
            {t("admin.teacher_invoicing.period")}
            <input type="month" name="period" defaultValue={period} required />
          </label>
          <button type="submit">{t("admin.teacher_invoicing.show_statement")}</button>
          <Link className="ghost" href="/admin/teacher-invoicing/statements">{uiText(language, "common.reset")}</Link>
        </form>
      </section>

      {!professorId ? (
        <section className="card"><p className="muted">{t("admin.teacher_invoicing.select_teacher_hint")}</p></section>
      ) : null}

      {professorId && statementsResult?.ok ? (
        <>
          <section className="card statement-period-hero">
            <div className="row spread">
              <div>
                <p className="statement-title">{selectedProfessor ? `${selectedProfessor.first_name} ${selectedProfessor.last_name}` : t("admin.teacher_invoicing.teacher")}</p>
                <p className="muted">{t("admin.teacher_invoicing.period_value", { period })}</p>
              </div>
              {sessions.length > 0 ? (
                <div className="row statement-export-actions">
                  <a className="mode-link" href={exportPdfHref}>{t("admin.teacher_invoicing.export_pdf")}</a>
                  <a className="ghost" href={exportHref}>{t("admin.teacher_invoicing.export_csv")}</a>
                </div>
              ) : null}
            </div>
          </section>

          <section className="card statement-summary-card">
            <h3>{t("admin.teacher_invoicing.summary")}</h3>
            <div className="statement-summary-grid">
              <div><small className="muted">{t("admin.teacher_invoicing.courses_count")}</small><strong>{sessions.length}</strong></div>
              <div><small className="muted">{t("admin.teacher_invoicing.total_hours")}</small><strong>{totalHours.toFixed(2)} h</strong></div>
              <div><small className="muted">{t("admin.teacher_invoicing.total_ht")}</small><strong>{formatMoney(totalHt, currency, language)}</strong></div>
              <div>
                <small className="muted">{t("admin.teacher_invoicing.attendance")}</small>
                <strong className={`status-pill ${attendanceComplete ? "status-ok" : "status-warn"}`}>
                  {attendanceComplete ? t("admin.teacher_invoicing.attendance_complete") : t("admin.teacher_invoicing.attendance_incomplete")}
                </strong>
              </div>
            </div>
          </section>

          <section className="card">
            <h3>{t("admin.teacher_invoicing.courses_detail")}</h3>
            {sessions.length === 0 ? <p className="muted">{t("admin.teacher_invoicing.no_courses_period")}</p> : (
              <div className="statement-service-list">
                {sessions.map((session) => (
                  <article key={session.id} className="statement-service-card">
                    <div className="statement-service-head">
                      <div>
                        <strong>{session.title}</strong>
                        <small>{formatDate(session.startAt, language)} · {formatTime(session.startAt, language)}–{formatTime(session.endAt, language)}</small>
                      </div>
                      <span className="badge">{session.location}</span>
                    </div>
                    <div className="statement-service-grid">
                      <small>{t("admin.teacher_invoicing.duration")}: <strong>{session.durationMinutes} min</strong></small>
                      <small>{t("admin.teacher_invoicing.hourly_rate_ht")}: <strong>{formatMoney(session.hourlyRateHt, currency, language)}</strong></small>
                      <small>{t("admin.teacher_invoicing.amount_ht")}: <strong>{formatMoney(session.amountHt, currency, language)}</strong></small>
                    </div>
                    <div className="top-gap-sm">
                      <small className="muted">{t("admin.teacher_invoicing.student_attendance")}</small>
                      {session.attendance.length === 0 ? <p className="muted">{t("admin.teacher_invoicing.no_students")}</p> : (
                        <div className="row statement-attendance-list">
                          {session.attendance.map((row, index) => (
                            <span key={`${session.id}-${row.student_name}-${index}`} className={`status-pill ${attendanceTone(row.status)}`}>
                              {row.student_name} · {attendanceLabel(row.status, language)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
