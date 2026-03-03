import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createAdminCollaboratorSalaryPaymentAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { AdminProfessorDetailOut, AdminProfessorSalaryPaymentOut } from "../../../lib/types";

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

function money(value: string, currency: string): string {
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) {
    return `0,00 ${currency}`;
  }
  return `${amount.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
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
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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
      `/api/v1/admin/collaborators/salary-payments?reference_date=${encodeURIComponent(referenceDate)}&limit=300`,
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
        <h2>Paiement des salaires</h2>
        <p className="muted">
          Saisie comptable des factures collaborateurs (numero de facture, HT, TTC, date, mode de paiement).
          La date de reference est par defaut le 1er jour du mois en cours.
        </p>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {!collaboratorsResult.ok ? <section className="flash-err">Erreur collaborateurs: {collaboratorsResult.message}</section> : null}
      {!paymentsResult.ok ? <section className="flash-err">Erreur paiements salaires: {paymentsResult.message}</section> : null}

      <section className="card">
        <form method="get" className="grid cols-3">
          <label>
            Recherche collaborateur
            <input type="text" name="search" defaultValue={search} placeholder="Nom, prenom, email..." />
          </label>
          <label>
            Date de reference
            <input type="date" name="reference_date" defaultValue={referenceDate} />
          </label>
          <div className="row">
            <button type="submit">Mettre a jour</button>
            <a className="reset-link" href="/admin/salary-payments">
              Reinitialiser
            </a>
          </div>
        </form>
      </section>

      <section className="card table-wrap">
        <h3>Montants dus par collaborateur</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Collaborateur</th>
              <th>Email</th>
              <th>Somme due</th>
              <th>Date de reference</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {collaborators.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <p className="muted">Aucun collaborateur pour ces filtres.</p>
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
                    <td>
                      <strong>
                        {professor.first_name} {professor.last_name}
                      </strong>
                    </td>
                    <td>{professor.email}</td>
                    <td>{money(due, currency)}</td>
                    <td>{referenceDate}</td>
                    <td>
                      <a className="mode-link" href={openHref}>
                        Paiement
                      </a>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      <section className="card table-wrap">
        <h3>Historique des paiements collaborateurs</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Date paiement</th>
              <th>Collaborateur</th>
              <th>Facture</th>
              <th>Mode</th>
              <th>HT</th>
              <th>TTC</th>
              <th>Lignes reglees</th>
            </tr>
          </thead>
          <tbody>
            {!paymentsResult.ok || paymentsResult.data.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">Aucun paiement saisi pour cette date de reference.</p>
                </td>
              </tr>
            ) : (
              paymentsResult.data.map((row) => (
                <tr key={row.id}>
                  <td>{row.payment_date}</td>
                  <td>
                    {row.professor_first_name} {row.professor_last_name}
                  </td>
                  <td>{row.invoice_number}</td>
                  <td>
                    {row.payment_method === "BANK_TRANSFER"
                      ? "Virement bancaire"
                      : row.payment_method === "CHEQUE"
                        ? "Cheque"
                        : "Especes"}
                  </td>
                  <td>{money(row.amount_excl_vat, row.currency_code)}</td>
                  <td>{money(row.amount_incl_vat, row.currency_code)}</td>
                  <td>{row.settled_payout_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {selectedProfessor ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={closeModalHref} aria-label="Fermer">
              ×
            </a>
            <h2 className="modal-title">Saisir un paiement collaborateur</h2>
            <p className="muted">
              Collaborateur: {selectedProfessor.first_name} {selectedProfessor.last_name} ({selectedProfessor.email})
            </p>
            <p className="muted">Somme due au {referenceDate}: {money(selectedDue, selectedCurrency)}</p>
            <form action={createAdminCollaboratorSalaryPaymentAction} className="grid cols-2">
              <input type="hidden" name="professor_id" value={selectedProfessor.id} />
              <input type="hidden" name="reference_date" value={referenceDate} />
              <input type="hidden" name="return_to" value={closeModalHref} />

              <label className="span-2">
                Numero de facture (professeur)
                <input type="text" name="invoice_number" required maxLength={120} placeholder="Ex: F-2026-03-001" />
              </label>

              <label>
                Montant HT
                <input type="number" name="amount_excl_vat" required min="0" step="0.01" defaultValue={selectedDue} />
              </label>

              <label>
                Montant TTC
                <input type="number" name="amount_incl_vat" required min="0" step="0.01" defaultValue={selectedDue} />
              </label>

              <label>
                Date de paiement
                <input type="date" name="payment_date" required defaultValue={todayIsoDate()} />
              </label>

              <label>
                Mode de paiement
                <select name="payment_method" defaultValue="BANK_TRANSFER">
                  <option value="BANK_TRANSFER">Virement bancaire</option>
                  <option value="CHEQUE">Cheque</option>
                  <option value="CASH">Especes</option>
                </select>
              </label>

              <div className="row span-2 end">
                <a className="mode-link" href={closeModalHref}>
                  Annuler
                </a>
                <button type="submit">Enregistrer le paiement</button>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
