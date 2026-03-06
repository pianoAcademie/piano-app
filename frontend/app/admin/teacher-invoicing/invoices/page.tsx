import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { backendRequest } from "../../../../lib/backend";
import type { AdminProfessorSalaryPaymentOut } from "../../../../lib/types";

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

function paymentMethodLabel(method: AdminProfessorSalaryPaymentOut["payment_method"]): string {
  if (method === "BANK_TRANSFER") {
    return "Virement";
  }
  if (method === "CHEQUE") {
    return "Cheque";
  }
  return "Especes";
}

function formatMoney(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  return `${amount.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

export default async function AdminTeacherInvoicingInvoicesPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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
      <AdminTeacherInvoicingNav activeTab="invoices" />

      {!paymentsResult.ok ? <section className="flash-err">Erreur backend: {paymentsResult.message}</section> : null}

      <section className="card">
        <div className="row spread">
          <h3>Factures</h3>
          <form method="get" className="row catalog-admin-filters">
            <label>
              Date de reference
              <input type="date" name="reference_date" defaultValue={referenceDate} />
            </label>
            <label>
              Recherche
              <input type="search" name="q" defaultValue={readParam(searchParams, "q")} placeholder="Professeur, email, facture..." />
            </label>
            <button type="submit">Filtrer</button>
            <Link className="ghost" href="/admin/teacher-invoicing/invoices">
              Reinitialiser
            </Link>
          </form>
        </div>
        <p className="muted">Suivi des factures professeurs, statuts de paiement et historique.</p>
      </section>

      <section className="grid cols-3">
        <article className="card">
          <h3>Lignes</h3>
          <p className="muted">{rows.length}</p>
        </article>
        <article className="card">
          <h3>Total TTC</h3>
          <p className="muted">{formatMoney(totalTtc.toFixed(2), currency)}</p>
        </article>
        <article className="card">
          <h3>Action rapide</h3>
          <Link className="mode-link" href="/admin/salary-payments">
            Ouvrir Paiement des salaires
          </Link>
        </article>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date paiement</th>
              <th>Professeur</th>
              <th>Email</th>
              <th>Facture</th>
              <th>Mode</th>
              <th>HT</th>
              <th>TTC</th>
              <th>Lignes reglees</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <p className="muted">Aucune facture professeur pour ces filtres.</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.payment_date}</td>
                  <td>{row.professor_first_name} {row.professor_last_name}</td>
                  <td>{row.professor_email}</td>
                  <td>{row.invoice_number}</td>
                  <td>{paymentMethodLabel(row.payment_method)}</td>
                  <td>{formatMoney(row.amount_excl_vat, row.currency_code)}</td>
                  <td>{formatMoney(row.amount_incl_vat, row.currency_code)}</td>
                  <td>{row.settled_payout_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </section>
  );
}
