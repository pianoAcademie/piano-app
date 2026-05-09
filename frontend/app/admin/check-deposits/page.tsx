import Link from "next/link";
import { redirect } from "next/navigation";

import { bulkUpdateAdminCheckDepositStatusAction } from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminCheckDepositPaymentOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams | undefined, key: string): string {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatRowsTotal(rows: AdminCheckDepositPaymentOut[], language: UiLanguage): string {
  const currency = rows[0]?.currency || "EUR";
  const total = rows.reduce((sum, row) => {
    const amount = Number(row.amount_incl_vat);
    return sum + (Number.isFinite(amount) ? amount : 0);
  }, 0);
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency,
  }).format(total);
}

function statusLabel(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "CHECK_DEPOSITED") {
    return "Deposes";
  }
  if (normalized === "PAID") {
    return "Encaisses";
  }
  if (normalized === "CHECK_REFUSED") {
    return "Refuses";
  }
  return "Recus";
}

function statusClass(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PAID") {
    return "status-ok";
  }
  if (normalized === "CHECK_DEPOSITED") {
    return "status-info";
  }
  if (normalized === "CHECK_REFUSED") {
    return "status-off";
  }
  return "status-warn";
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function todayDateValue(): string {
  return new Date().toISOString().slice(0, 10);
}

function checkMatchesQuery(row: AdminCheckDepositPaymentOut, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystack = normalizeSearch([
    row.client_name,
    row.label,
    row.reference ?? "",
    row.invoice_number ?? "",
    row.amount_incl_vat,
    row.status,
    row.tracking_note ?? "",
  ].join(" "));
  return haystack.includes(query);
}

function CheckRowsTable({
  rows,
  language,
  selectable = true,
}: {
  rows: AdminCheckDepositPaymentOut[];
  language: UiLanguage;
  selectable?: boolean;
}): JSX.Element {
  if (rows.length === 0) {
    return <p className="muted">Aucun cheque dans ce statut.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {selectable ? <th>Depot</th> : null}
            <th>Famille</th>
            <th>Date</th>
            <th>Reference</th>
            <th>Facture</th>
            <th>Montant</th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.transaction_id}>
              {selectable ? (
                <td>
                  <input type="checkbox" name="transaction_ids" value={row.transaction_id} />
                </td>
              ) : null}
              <td>
                <Link className="mode-link" href={`/admin/clients/${row.client_id}?tab=paiements`}>
                  {row.client_name}
                </Link>
                <small className="muted">{row.label}</small>
              </td>
              <td>{new Date(row.occurred_at).toLocaleDateString(localeForUiLanguage(language))}</td>
              <td>{row.reference || "-"}</td>
              <td>{row.invoice_number || "-"}</td>
              <td>{formatMoney(row.amount_incl_vat, row.currency, language)}</td>
              <td>
                <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
                {row.tracking_note ? <small className="muted">{row.tracking_note}</small> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function AdminCheckDepositsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const checksResult = await backendRequest<AdminCheckDepositPaymentOut[]>(
    "/api/v1/admin/clients/check-deposits/pending?statuses=CHECK_RECEIVED,CHECK_DEPOSITED,CHECK_REFUSED",
    {},
    token,
  );
  const searchQuery = normalizeSearch(readParam(searchParams, "q").trim());
  const returnTo = searchQuery ? `/admin/check-deposits?q=${encodeURIComponent(readParam(searchParams, "q").trim())}` : "/admin/check-deposits";
  const allChecks = checksResult.ok ? checksResult.data : [];
  const checks = allChecks.filter((row) => checkMatchesQuery(row, searchQuery));
  const received = checks.filter((row) => row.status.trim().toUpperCase() === "CHECK_RECEIVED");
  const deposited = checks.filter((row) => row.status.trim().toUpperCase() === "CHECK_DEPOSITED");
  const refused = checks.filter((row) => row.status.trim().toUpperCase() === "CHECK_REFUSED");
  const okMessage = readParam(searchParams, "ok");
  const errorMessage = readParam(searchParams, "error") || (!checksResult.ok ? checksResult.message : "");

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Depots de cheques</h2>
            <p className="muted">Traitez les cheques par lot apres scan, controle Excel ou depot banque.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/check-deposits/template">Modele import</Link>
            <Link className="ghost" href="/admin/check-deposits/export">Exporter les cheques attendus</Link>
            <Link className="ghost" href="/admin/clients?tab=paiements">Paiements clients</Link>
          </div>
        </div>
        <form className="row wrap gap-sm top-gap-sm" action="/admin/check-deposits">
          <input
            aria-label="Recherche"
            name="q"
            placeholder="Rechercher nom, montant, facture, reference..."
            defaultValue={readParam(searchParams, "q")}
          />
          <button type="submit">Rechercher</button>
          {searchQuery ? <Link className="ghost" href="/admin/check-deposits">Effacer</Link> : null}
        </form>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="card span-2">
        <h3>Import CSV ou XLSX issu d'Excel</h3>
        <p className="muted">
          Colonnes reconnues: transaction_id ou id, reference/ref/numero_cheque, montant/montant_ttc/amount,
          nom/payeur/tireur/emetteur/titulaire/nom_sur_cheque.
          Les fichiers CSV et XLSX sont acceptes. L'export ci-dessus contient le transaction_id: c'est la colonne la plus fiable pour un depot massif.
        </p>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="grid cols-2 config-form-grid top-gap-sm" encType="multipart/form-data">
          <input type="hidden" name="return_to" value={returnTo} />
          <label>
            Fichier CSV ou XLSX
            <input type="file" name="deposit_file" accept=".csv,.txt,.tsv,.xlsx" required />
          </label>
          <label>
            Action
            <select name="target_status" defaultValue="CHECK_DEPOSITED">
              <option value="CHECK_DEPOSITED">Passer en deposes</option>
              <option value="PAID">Passer en encaisses</option>
              <option value="CHECK_REFUSED">Passer en refuses</option>
            </select>
          </label>
          <label>
            Reference de lot
            <input name="batch_reference" placeholder="Depot banque, bordereau, remise..." />
          </label>
          <label>
            Date operation
            <input type="date" name="effective_date" defaultValue={todayDateValue()} />
          </label>
          <div className="row span-2">
            <button type="submit">Importer et mettre a jour</button>
          </div>
        </form>
      </section>

      <section className="card span-2">
        <div className="row spread wrap gap-sm">
          <div>
            <h3>Cheques recus a deposer</h3>
            <p className="muted">{received.length} cheque(s) en attente de depot. Total: {formatRowsTotal(received, language)}.</p>
          </div>
        </div>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="top-gap-sm">
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="target_status" value="CHECK_DEPOSITED" />
          <div className="grid cols-2 config-form-grid">
            <label>
              Reference depot
              <input name="batch_reference" placeholder="Depot banque, bordereau..." />
            </label>
            <label>
              Date depot
              <input type="date" name="effective_date" defaultValue={todayDateValue()} />
            </label>
          </div>
          <CheckRowsTable rows={received} language={language} />
          {received.length > 0 ? (
            <div className="row top-gap-sm">
              <button type="submit">Marquer la selection comme deposee</button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="card span-2">
        <h3>Cheques deposes a encaisser</h3>
        <p className="muted">{deposited.length} cheque(s) deposes mais pas encore encaisses. Total: {formatRowsTotal(deposited, language)}.</p>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="top-gap-sm">
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="target_status" value="PAID" />
          <div className="grid cols-2 config-form-grid">
            <label>
              Reference encaissement
              <input name="batch_reference" placeholder="Operation bancaire, releve..." />
            </label>
            <label>
              Date encaissement
              <input type="date" name="effective_date" defaultValue={todayDateValue()} />
            </label>
          </div>
          <CheckRowsTable rows={deposited} language={language} />
          {deposited.length > 0 ? (
            <div className="row top-gap-sm">
              <button type="submit">Marquer la selection comme encaissee</button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="card span-2">
        <h3>Cheques refuses</h3>
        <p className="muted">
          {refused.length} cheque(s) refuse(s) par la banque. Ces montants ne comptent plus comme encaisses et doivent etre traites depuis la fiche client.
        </p>
        <CheckRowsTable rows={refused} language={language} selectable={false} />
      </section>
    </section>
  );
}
