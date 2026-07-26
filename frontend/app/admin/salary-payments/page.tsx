import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createAdminCollaboratorSalaryPaymentAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { AdminProfessorDetailOut, AdminProfessorSalaryPaymentOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function todayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function firstDayOfCurrentMonthIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  return `${year}-${month}-01`;
}

function money(value: string, currency: string, language: UiLanguage): string {
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) {
    return `0,00 ${currency}`;
  }
  return `${amount.toLocaleString(localeForUiLanguage(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function paymentMethodLabel(method: string, language: UiLanguage): string {
  if (method === "BANK_TRANSFER") return uiText(language, "admin.salary.bank_transfer");
  if (method === "CHEQUE") return uiText(language, "admin.salary.cheque");
  return uiText(language, "admin.salary.cash");
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), { dateStyle: "short" });
}

function buildPageHref(params: {
  search?: string;
  referenceDate: string;
  payProfessorId?: string;
}): string {
  const query = new URLSearchParams();
  if (params.search) {
    query.set("search", params.search);
  }
  query.set("reference_date", params.referenceDate);
  if (params.payProfessorId) {
    query.set("pay_professor_id", params.payProfessorId);
  }
  return `/admin/salary-payments?${query.toString()}`;
}

export default async function AdminSalaryPaymentsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
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

  const search = readParam(searchParams, "search").trim();
  const referenceDate = readParam(searchParams, "reference_date").trim() || firstDayOfCurrentMonthIsoDate();
  const payProfessorId = readParam(searchParams, "pay_professor_id").trim();
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error");

  const collaboratorsQuery = new URLSearchParams();
  collaboratorsQuery.set("active_only", "true");
  collaboratorsQuery.set("payout_as_of", referenceDate);
  collaboratorsQuery.set("limit", "500");
  if (search) {
    collaboratorsQuery.set("search", search);
  }

  const [collaboratorsResult, paymentsResult] = await Promise.all([
    backendRequest<AdminProfessorDetailOut[]>(`/api/v1/admin/collaborators?${collaboratorsQuery.toString()}`, {}, token),
    backendRequest<AdminProfessorSalaryPaymentOut[]>(
      `/api/v1/admin/collaborators/salary/payments?reference_date=${encodeURIComponent(referenceDate)}&limit=300`,
      {},
      token,
    ),
  ]);

  const collaborators = collaboratorsResult.ok ? collaboratorsResult.data : [];
  const selectedProfessor = payProfessorId ? collaborators.find((row) => row.id === payProfessorId) ?? null : null;
  const selectedCurrency = selectedProfessor?.payout_balance_currency || selectedProfessor?.payout_currency || "EUR";
  const selectedDue = selectedProfessor?.payout_balance_amount || "0.00";

  const closeModalHref = buildPageHref({ search, referenceDate });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.salary.title")}</h2>
        <p className="muted">{t("admin.salary.subtitle")}</p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!collaboratorsResult.ok ? <section className="flash-err">{t("admin.salary.collaborators_error")}: {collaboratorsResult.message}</section> : null}
      {!paymentsResult.ok ? <section className="flash-err">{t("admin.salary.payments_error")}: {paymentsResult.message}</section> : null}

      <section className="card">
        <form method="get" className="admin-list-filter-primary">
          <label>
            {t("admin.salary.search_collaborator")}
            <input type="search" name="search" defaultValue={search} placeholder={t("admin.salary.search_placeholder")} enterKeyHint="search" />
          </label>
          <label>
            {t("admin.salary.reference_date")}
            <input type="date" name="reference_date" defaultValue={referenceDate} />
          </label>
          <div className="admin-list-filter-actions">
            <button type="submit">{t("admin.salary.update")}</button>
            <a className="reset-link" href="/admin/salary-payments">
              {uiText(language, "common.reset")}
            </a>
          </div>
        </form>
      </section>

      <section className="card table-wrap admin-table-card-wrap">
        <h3>{t("admin.salary.amounts_due_title")}</h3>
        <table className="data-table admin-responsive-table">
          <thead>
            <tr>
              <th>{uiText(language, "admin.nav.professors")}</th>
              <th>{uiText(language, "common.email")}</th>
              <th>{t("admin.salary.amount_due")}</th>
              <th>{t("admin.salary.reference_date")}</th>
              <th>{uiText(language, "client.action")}</th>
            </tr>
          </thead>
          <tbody>
            {collaborators.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <p className="muted">{t("admin.salary.no_collaborator")}</p>
                </td>
              </tr>
            ) : (
              collaborators.map((professor) => {
                const currency = professor.payout_balance_currency || professor.payout_currency || "EUR";
                const due = professor.payout_balance_amount || "0.00";
                const openHref = buildPageHref({
                  search,
                  referenceDate,
                  payProfessorId: professor.id,
                });
                return (
                  <tr key={professor.id}>
                    <td data-mobile-label="" className="mobile-row-primary">
                      <Link href={`/admin/professors/${professor.id}`} className="mode-link">
                        <strong>
                          {professor.first_name} {professor.last_name}
                        </strong>
                      </Link>
                    </td>
                    <td data-mobile-label={uiText(language, "common.email")}>{professor.email}</td>
                    <td data-mobile-label={t("admin.salary.amount_due")}>{money(due, currency, language)}</td>
                    <td data-mobile-hidden="true">{referenceDate}</td>
                    <td data-mobile-label={uiText(language, "client.action")}>
                      <a className="mode-link" href={openHref}>
                        {t("admin.salary.action_pay")}
                      </a>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      <section className="card table-wrap admin-table-card-wrap">
        <h3>{t("admin.salary.history_title")}</h3>
        <table className="data-table admin-responsive-table">
          <thead>
            <tr>
              <th>{t("admin.salary.payment_date")}</th>
              <th>{uiText(language, "admin.nav.professors")}</th>
              <th>{uiText(language, "common.invoices")}</th>
              <th>{t("admin.salary.payment_method")}</th>
              <th>{uiText(language, "common.ht")}</th>
              <th>{uiText(language, "common.ttc")}</th>
              <th>{t("admin.salary.settled_lines")}</th>
            </tr>
          </thead>
          <tbody>
            {!paymentsResult.ok || paymentsResult.data.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">{t("admin.salary.no_payment")}</p>
                </td>
              </tr>
            ) : (
              paymentsResult.data.map((row) => (
                <tr key={row.id}>
                  <td data-mobile-label={t("admin.salary.payment_date")}>{formatDate(row.payment_date, language)}</td>
                  <td data-mobile-label="" className="mobile-row-primary">
                    {row.professor_first_name} {row.professor_last_name}
                  </td>
                  <td data-mobile-label={uiText(language, "common.invoices")}>{row.invoice_number}</td>
                  <td data-mobile-label={t("admin.salary.payment_method")}>{paymentMethodLabel(row.payment_method, language)}</td>
                  <td data-mobile-hidden="true">{money(row.amount_excl_vat, row.currency_code, language)}</td>
                  <td data-mobile-label={uiText(language, "common.ttc")}>{money(row.amount_incl_vat, row.currency_code, language)}</td>
                  <td data-mobile-label={t("admin.salary.settled_lines")}>{row.settled_payout_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selectedProfessor ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={closeModalHref} aria-label={uiText(language, "common.close")}>
              ×
            </a>
            <h2 className="modal-title">{t("admin.salary.modal_title")}</h2>
            <p className="muted">
              {t("admin.salary.collaborator_label", {
                name: `${selectedProfessor.first_name} ${selectedProfessor.last_name}`.trim(),
                email: selectedProfessor.email,
              })}
            </p>
            <p className="muted">
              {t("admin.salary.amount_due_as_of", {
                date: formatDate(referenceDate, language),
                amount: money(selectedDue, selectedCurrency, language),
              })}
            </p>
            <form action={createAdminCollaboratorSalaryPaymentAction} className="grid cols-2">
              <input type="hidden" name="professor_id" value={selectedProfessor.id} />
              <input type="hidden" name="reference_date" value={referenceDate} />
              <input type="hidden" name="return_to" value={closeModalHref} />

              <label className="span-2">
                {t("admin.salary.invoice_number_professor")}
                <input type="text" name="invoice_number" required maxLength={120} placeholder={t("admin.salary.invoice_placeholder")} />
              </label>

              <label>
                {t("admin.salary.amount_excl_tax")}
                <input type="number" name="amount_excl_vat" required min="0" step="0.01" defaultValue={selectedDue} />
              </label>

              <label>
                {t("admin.salary.amount_incl_tax")}
                <input type="number" name="amount_incl_vat" required min="0" step="0.01" defaultValue={selectedDue} />
              </label>

              <label>
                {t("admin.salary.payment_date")}
                <input type="date" name="payment_date" required defaultValue={todayIsoDate()} />
              </label>

              <label>
                {t("admin.salary.payment_method")}
                <select name="payment_method" defaultValue="BANK_TRANSFER">
                  <option value="BANK_TRANSFER">{t("admin.salary.bank_transfer")}</option>
                  <option value="CHEQUE">{t("admin.salary.cheque")}</option>
                  <option value="CASH">{t("admin.salary.cash")}</option>
                </select>
              </label>

              <div className="row span-2 end">
                <a className="mode-link" href={closeModalHref}>
                  {uiText(language, "common.cancel")}
                </a>
                <button type="submit">{t("admin.salary.record_payment")}</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
