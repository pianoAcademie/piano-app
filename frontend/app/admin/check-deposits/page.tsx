import Link from "next/link";
import { redirect } from "next/navigation";

import { bulkUpdateAdminCheckDepositStatusAction } from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminCheckDepositPaymentOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

const CHECK_DEPOSIT_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    empty_status: "Aucun cheque dans ce statut.",
    deposit: "Depot",
    family: "Famille",
    date: "Date",
    reference: "Reference",
    invoice: "Facture",
    amount: "Montant",
    status: "Statut",
    status_received: "Recus",
    status_deposited: "Deposes",
    status_cashed: "Encaisses",
    status_refused: "Refuses",
    title: "Depots de cheques",
    subtitle: "Traitez les cheques par lot apres scan, controle Excel ou depot banque.",
    template: "Modele import",
    export_expected: "Exporter les cheques attendus",
    client_payments: "Paiements clients",
    search: "Recherche",
    search_placeholder: "Rechercher nom, montant, facture, reference...",
    search_button: "Rechercher",
    clear: "Effacer",
    import_title: "Import CSV ou XLSX issu d'Excel",
    import_help:
      "Colonnes reconnues: transaction_id ou id, reference/ref/numero_cheque, montant/montant_ttc/amount, nom/payeur/tireur/emetteur/titulaire/nom_sur_cheque. Les fichiers CSV et XLSX sont acceptes. L'export ci-dessus contient le transaction_id: c'est la colonne la plus fiable pour un depot massif.",
    file: "Fichier CSV ou XLSX",
    action: "Action",
    action_deposit: "Passer en deposes",
    action_cash: "Passer en encaisses",
    action_refuse: "Passer en refuses",
    batch_reference: "Reference de lot",
    batch_reference_placeholder: "Depot banque, bordereau, remise...",
    operation_date: "Date operation",
    import_submit: "Importer et mettre a jour",
    received_title: "Cheques recus a deposer",
    received_summary: "{count} cheque(s) en attente de depot. Total: {total}.",
    deposit_reference: "Reference depot",
    deposit_reference_placeholder: "Depot banque, bordereau...",
    deposit_date: "Date depot",
    mark_deposited: "Marquer la selection comme deposee",
    deposited_title: "Cheques deposes a encaisser",
    deposited_summary: "{count} cheque(s) deposes mais pas encore encaisses. Total: {total}.",
    cash_reference: "Reference encaissement",
    cash_reference_placeholder: "Operation bancaire, releve...",
    cash_date: "Date encaissement",
    mark_cashed: "Marquer la selection comme encaissee",
    refused_title: "Cheques refuses",
    refused_summary:
      "{count} cheque(s) refuse(s) par la banque. Ces montants ne comptent plus comme encaisses et doivent etre traites depuis la fiche client.",
  },
  en: {
    empty_status: "No checks in this status.",
    deposit: "Deposit",
    family: "Family",
    date: "Date",
    reference: "Reference",
    invoice: "Invoice",
    amount: "Amount",
    status: "Status",
    status_received: "Received",
    status_deposited: "Deposited",
    status_cashed: "Cashed",
    status_refused: "Refused",
    title: "Check deposits",
    subtitle: "Process checks in batches after scanning, Excel review, or bank deposit.",
    template: "Import template",
    export_expected: "Export expected checks",
    client_payments: "Client payments",
    search: "Search",
    search_placeholder: "Search name, amount, invoice, reference...",
    search_button: "Search",
    clear: "Clear",
    import_title: "CSV or XLSX import from Excel",
    import_help:
      "Recognized columns: transaction_id or id, reference/ref/numero_cheque, montant/montant_ttc/amount, nom/payeur/tireur/emetteur/titulaire/nom_sur_cheque. CSV and XLSX files are accepted. The export above includes transaction_id, which is the most reliable column for large deposits.",
    file: "CSV or XLSX file",
    action: "Action",
    action_deposit: "Mark as deposited",
    action_cash: "Mark as cashed",
    action_refuse: "Mark as refused",
    batch_reference: "Batch reference",
    batch_reference_placeholder: "Bank deposit, slip, remittance...",
    operation_date: "Operation date",
    import_submit: "Import and update",
    received_title: "Received checks to deposit",
    received_summary: "{count} check(s) awaiting deposit. Total: {total}.",
    deposit_reference: "Deposit reference",
    deposit_reference_placeholder: "Bank deposit, slip...",
    deposit_date: "Deposit date",
    mark_deposited: "Mark selection as deposited",
    deposited_title: "Deposited checks to cash",
    deposited_summary: "{count} check(s) deposited but not yet cashed. Total: {total}.",
    cash_reference: "Cashing reference",
    cash_reference_placeholder: "Bank operation, statement...",
    cash_date: "Cashing date",
    mark_cashed: "Mark selection as cashed",
    refused_title: "Refused checks",
    refused_summary:
      "{count} check(s) refused by the bank. These amounts no longer count as cashed and must be handled from the client record.",
  },
};

function tt(language: UiLanguage, key: string, values?: Record<string, string | number>): string {
  const template = CHECK_DEPOSIT_TEXT[language][key] || CHECK_DEPOSIT_TEXT.fr[key] || key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, token) => String(values[token] ?? ""));
}

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

function statusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "CHECK_DEPOSITED") {
    return tt(language, "status_deposited");
  }
  if (normalized === "PAID") {
    return tt(language, "status_cashed");
  }
  if (normalized === "CHECK_REFUSED") {
    return tt(language, "status_refused");
  }
  return tt(language, "status_received");
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
    return <p className="muted">{tt(language, "empty_status")}</p>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {selectable ? <th>{tt(language, "deposit")}</th> : null}
            <th>{tt(language, "family")}</th>
            <th>{tt(language, "date")}</th>
            <th>{tt(language, "reference")}</th>
            <th>{tt(language, "invoice")}</th>
            <th>{tt(language, "amount")}</th>
            <th>{tt(language, "status")}</th>
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
                <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status, language)}</span>
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
  const languageQuery = `?lang=${language}`;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{tt(language, "title")}</h2>
            <p className="muted">{tt(language, "subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={`/admin/check-deposits/template${languageQuery}`}>{tt(language, "template")}</Link>
            <Link className="ghost" href={`/admin/check-deposits/export${languageQuery}`}>{tt(language, "export_expected")}</Link>
            <Link className="ghost" href="/admin/clients?tab=paiements">{tt(language, "client_payments")}</Link>
          </div>
        </div>
        <form className="row wrap gap-sm top-gap-sm" action="/admin/check-deposits">
          <input
            aria-label={tt(language, "search")}
            name="q"
            placeholder={tt(language, "search_placeholder")}
            defaultValue={readParam(searchParams, "q")}
          />
          <button type="submit">{tt(language, "search_button")}</button>
          {searchQuery ? <Link className="ghost" href="/admin/check-deposits">{tt(language, "clear")}</Link> : null}
        </form>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="card span-2">
        <h3>{tt(language, "import_title")}</h3>
        <p className="muted">{tt(language, "import_help")}</p>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="grid cols-2 config-form-grid top-gap-sm" encType="multipart/form-data">
          <input type="hidden" name="return_to" value={returnTo} />
          <label>
            {tt(language, "file")}
            <input type="file" name="deposit_file" accept=".csv,.txt,.tsv,.xlsx" required />
          </label>
          <label>
            {tt(language, "action")}
            <select name="target_status" defaultValue="CHECK_DEPOSITED">
              <option value="CHECK_DEPOSITED">{tt(language, "action_deposit")}</option>
              <option value="PAID">{tt(language, "action_cash")}</option>
              <option value="CHECK_REFUSED">{tt(language, "action_refuse")}</option>
            </select>
          </label>
          <label>
            {tt(language, "batch_reference")}
            <input name="batch_reference" placeholder={tt(language, "batch_reference_placeholder")} />
          </label>
          <label>
            {tt(language, "operation_date")}
            <input type="date" name="effective_date" defaultValue={todayDateValue()} />
          </label>
          <div className="row span-2">
            <button type="submit">{tt(language, "import_submit")}</button>
          </div>
        </form>
      </section>

      <section className="card span-2">
        <div className="row spread wrap gap-sm">
          <div>
            <h3>{tt(language, "received_title")}</h3>
            <p className="muted">{tt(language, "received_summary", { count: received.length, total: formatRowsTotal(received, language) })}</p>
          </div>
        </div>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="top-gap-sm">
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="target_status" value="CHECK_DEPOSITED" />
          <div className="grid cols-2 config-form-grid">
            <label>
              {tt(language, "deposit_reference")}
              <input name="batch_reference" placeholder={tt(language, "deposit_reference_placeholder")} />
            </label>
            <label>
              {tt(language, "deposit_date")}
              <input type="date" name="effective_date" defaultValue={todayDateValue()} />
            </label>
          </div>
          <CheckRowsTable rows={received} language={language} />
          {received.length > 0 ? (
            <div className="row top-gap-sm">
              <button type="submit">{tt(language, "mark_deposited")}</button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="card span-2">
        <h3>{tt(language, "deposited_title")}</h3>
        <p className="muted">{tt(language, "deposited_summary", { count: deposited.length, total: formatRowsTotal(deposited, language) })}</p>
        <form action={bulkUpdateAdminCheckDepositStatusAction} className="top-gap-sm">
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="target_status" value="PAID" />
          <div className="grid cols-2 config-form-grid">
            <label>
              {tt(language, "cash_reference")}
              <input name="batch_reference" placeholder={tt(language, "cash_reference_placeholder")} />
            </label>
            <label>
              {tt(language, "cash_date")}
              <input type="date" name="effective_date" defaultValue={todayDateValue()} />
            </label>
          </div>
          <CheckRowsTable rows={deposited} language={language} />
          {deposited.length > 0 ? (
            <div className="row top-gap-sm">
              <button type="submit">{tt(language, "mark_cashed")}</button>
            </div>
          ) : null}
        </form>
      </section>

      <section className="card span-2">
        <h3>{tt(language, "refused_title")}</h3>
        <p className="muted">{tt(language, "refused_summary", { count: refused.length })}</p>
        <CheckRowsTable rows={refused} language={language} selectable={false} />
      </section>
    </section>
  );
}
