import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { backendRequest } from "../../../../lib/backend";
import type { ProfessorStatementRow, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function payoutStatusLabel(value: ProfessorStatementRow["payout_status"], language: UiLanguage): string {
  if (value === "PAID") {
    return uiText(language, "admin.teacher_invoicing.payout_paid");
  }
  if (value === "APPROVED") {
    return uiText(language, "admin.teacher_invoicing.payout_approved");
  }
  if (value === "PENDING") {
    return uiText(language, "admin.teacher_invoicing.payout_pending");
  }
  return "-";
}

function statementAmountLabel(row: ProfessorStatementRow, language: UiLanguage): string {
  if (!row.amount_snapshot) {
    return "-";
  }
  const amount = Number(row.amount_snapshot);
  if (!Number.isFinite(amount)) {
    return `${row.amount_snapshot} ${row.currency_snapshot ?? ""}`.trim();
  }
  return `${amount.toLocaleString(localeForUiLanguage(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${row.currency_snapshot ?? "EUR"}`;
}

export default async function AdminTeacherInvoicingStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
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

  const query = readParam(searchParams, "q").trim();
  const statusFilter = readParam(searchParams, "status").trim().toUpperCase();

  const statementsResult = await backendRequest<ProfessorStatementRow[]>("/api/v1/admin/reports/professor-statements", {}, token);
  const rows = statementsResult.ok
    ? [...statementsResult.data]
        .sort((a, b) => new Date(b.start_at_utc).getTime() - new Date(a.start_at_utc).getTime())
        .filter((row) => {
          if (statusFilter && (row.payout_status ?? "NONE") !== statusFilter) {
            return false;
          }
          if (!query) {
            return true;
          }
          const haystack = [
            row.professor_name,
            row.course_type_name,
            row.location_name,
            row.session_status,
            row.payout_status ?? "",
          ]
            .join(" ")
            .toLowerCase();
          return haystack.includes(query.toLowerCase());
        })
    : [];

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="statements" language={language} />

      {!statementsResult.ok ? <section className="flash-err">{t("admin.teacher_invoicing.backend_error")}: {statementsResult.message}</section> : null}

      <section className="card">
        <div className="row spread">
          <h3>{t("admin.teacher_invoicing.statements")}</h3>
          <form method="get" className="row catalog-admin-filters">
            <label>
              {uiText(language, "common.search")}
              <input type="search" name="q" defaultValue={query} placeholder={t("admin.teacher_invoicing.statements_search_placeholder")} />
            </label>
            <label>
              {uiText(language, "common.status")}
              <select name="status" defaultValue={statusFilter}>
                <option value="">{uiText(language, "common.all")}</option>
                <option value="PENDING">{t("admin.teacher_invoicing.payout_pending")}</option>
                <option value="APPROVED">{t("admin.teacher_invoicing.payout_approved_plural")}</option>
                <option value="PAID">{t("admin.teacher_invoicing.payout_paid_plural")}</option>
              </select>
            </label>
            <button type="submit">{uiText(language, "common.apply")}</button>
            <Link className="ghost" href="/admin/teacher-invoicing/statements">
              {uiText(language, "common.reset")}
            </Link>
          </form>
        </div>
        <p className="muted">{t("admin.teacher_invoicing.statements_subtitle")}</p>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("admin.teacher_invoicing.teacher")}</th>
              <th>{t("admin.teacher_invoicing.date_time")}</th>
              <th>{t("admin.teacher_invoicing.activity")}</th>
              <th>{uiText(language, "common.location")}</th>
              <th>{t("admin.teacher_invoicing.statement_status")}</th>
              <th>{uiText(language, "common.amount")}</th>
              <th>{uiText(language, "client.action")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">{t("admin.teacher_invoicing.no_statements")}</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.session_id}>
                  <td>{row.professor_name}</td>
                  <td>{formatDate(row.start_at_utc, language)}</td>
                  <td>{row.course_type_name}</td>
                  <td>{row.location_name}</td>
                  <td>{payoutStatusLabel(row.payout_status, language)}</td>
                  <td>{statementAmountLabel(row, language)}</td>
                  <td>
                    <Link className="mode-link" href={`/admin/professors/${row.professor_id}?tab=solde`}>
                      {uiText(language, "common.open")}
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </section>
  );
}
