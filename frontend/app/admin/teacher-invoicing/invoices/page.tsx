import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { hasAdminPermission } from "../../../../lib/admin-access";
import { backendRequest } from "../../../../lib/backend";
import type { AdminProfessorSalaryPaymentOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function firstDayOfCurrentMonthIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  return `${year}-${month}-01`;
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value || "-";
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), { dateStyle: "short" });
}

function paymentMethodUiLabel(method: AdminProfessorSalaryPaymentOut["payment_method"], language: UiLanguage): string {
  if (method === "BANK_TRANSFER") {
    return uiText(language, "admin.salary.bank_transfer");
  }
  if (method === "CHEQUE") {
    return uiText(language, "admin.salary.cheque");
  }
  return uiText(language, "admin.salary.cash");
}

function formatMoney(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  return `${amount.toLocaleString(localeForUiLanguage(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

export default async function AdminTeacherInvoicingInvoicesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_invoices_and_accounts")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const referenceDate = readParam(searchParams, "reference_date").trim() || firstDayOfCurrentMonthIsoDate();
  const query = readParam(searchParams, "q").trim().toLowerCase();

  const paymentsResult = await backendRequest<AdminProfessorSalaryPaymentOut[]>(
    `/api/v1/admin/collaborators/salary/payments?reference_date=${encodeURIComponent(referenceDate)}&limit=500`,
    {},
    token,
  );

  const rows = paymentsResult.ok
    ? paymentsResult.data.filter((row) => {
        if (!query) {
          return true;
        }
        const haystack = [
          row.professor_first_name,
          row.professor_last_name,
          row.professor_email,
          row.invoice_number,
          row.payment_method,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
    : [];

  const totalTtc = rows.reduce((sum, row) => sum + (Number(row.amount_incl_vat) || 0), 0);
  const currency = rows[0]?.currency_code ?? "EUR";

  return (
    <section className="admin-page-grid">
      <AdminTeacherInvoicingNav activeTab="invoices" language={language} isFullAdmin={meResult.data.role === "admin"} />

      {!paymentsResult.ok ? <section className="flash-err">{t("admin.teacher_invoicing.backend_error")}: {paymentsResult.message}</section> : null}

      <section className="card">
        <div className="row spread">
          <h3>{uiText(language, "common.invoices")}</h3>
          <form method="get" className="row catalog-admin-filters">
            <label>
              {uiText(language, "admin.salary.reference_date")}
              <input type="date" name="reference_date" defaultValue={referenceDate} />
            </label>
            <label>
              {uiText(language, "common.search")}
              <input type="search" name="q" defaultValue={readParam(searchParams, "q")} placeholder={t("admin.teacher_invoicing.invoices_search_placeholder")} />
            </label>
            <button type="submit">{uiText(language, "common.apply")}</button>
            <Link className="ghost" href="/admin/teacher-invoicing/invoices">
              {uiText(language, "common.reset")}
            </Link>
          </form>
        </div>
        <p className="muted">{t("admin.teacher_invoicing.invoices_subtitle")}</p>
      </section>

      <section className="grid cols-3">
        <article className="card">
          <h3>{t("admin.teacher_invoicing.rows")}</h3>
          <p className="muted">{rows.length}</p>
        </article>
        <article className="card">
          <h3>{t("admin.teacher_invoicing.total_ttc")}</h3>
          <p className="muted">{formatMoney(totalTtc.toFixed(2), currency, language)}</p>
        </article>
        <article className="card">
          <h3>{t("admin.teacher_invoicing.quick_action")}</h3>
          <Link className="mode-link" href="/admin/salary-payments">
            {t("admin.teacher_invoicing.open_salary_payments")}
          </Link>
        </article>
      </section>

      <section className="card table-wrap admin-table-card-wrap">
        <table className="data-table admin-responsive-table">
          <thead>
            <tr>
              <th>{uiText(language, "admin.salary.payment_date")}</th>
              <th>{t("admin.teacher_invoicing.teacher")}</th>
              <th>{uiText(language, "common.email")}</th>
              <th>{uiText(language, "common.invoices")}</th>
              <th>{uiText(language, "admin.salary.payment_method")}</th>
              <th>{uiText(language, "common.ht")}</th>
              <th>{uiText(language, "common.ttc")}</th>
              <th>{uiText(language, "admin.salary.settled_lines")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <p className="muted">{t("admin.teacher_invoicing.no_invoices")}</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td data-mobile-label={uiText(language, "admin.salary.payment_date")}>{formatDate(row.payment_date, language)}</td>
                  <td data-mobile-label="" className="mobile-row-primary">{row.professor_first_name} {row.professor_last_name}</td>
                  <td data-mobile-label={uiText(language, "common.email")}>{row.professor_email}</td>
                  <td data-mobile-label={uiText(language, "common.invoices")}>{row.invoice_number}</td>
                  <td data-mobile-label={uiText(language, "admin.salary.payment_method")}>{paymentMethodUiLabel(row.payment_method, language)}</td>
                  <td data-mobile-hidden="true">{formatMoney(row.amount_excl_vat, row.currency_code, language)}</td>
                  <td data-mobile-label={uiText(language, "common.ttc")}>{formatMoney(row.amount_incl_vat, row.currency_code, language)}</td>
                  <td data-mobile-label={uiText(language, "admin.salary.settled_lines")}>{row.settled_payout_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </section>
  );
}
