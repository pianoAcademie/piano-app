import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  teacherApproveStatementsAction,
  teacherCancelInvoiceAction,
  teacherDisputeStatementsAction,
  teacherSendInvoiceToAccountingAction,
  teacherUncancelInvoiceAction,
} from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { TeacherInvoiceOut, TeacherStatementOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

const MONTH_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "Janvier" },
  { value: 2, label: "Février" },
  { value: 3, label: "Mars" },
  { value: 4, label: "Avril" },
  { value: 5, label: "Mai" },
  { value: 6, label: "Juin" },
  { value: 7, label: "Juillet" },
  { value: 8, label: "Août" },
  { value: 9, label: "Septembre" },
  { value: 10, label: "Octobre" },
  { value: 11, label: "Novembre" },
  { value: 12, label: "Décembre" },
];

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

export default async function TeacherStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const now = new Date();
  const year = Number.parseInt(readParam(searchParams, "year"), 10) || now.getUTCFullYear();
  const parsedMonth = Number.parseInt(readParam(searchParams, "month"), 10);
  const month = Number.isFinite(parsedMonth) && parsedMonth >= 1 && parsedMonth <= 12 ? parsedMonth : now.getUTCMonth() + 1;
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [statementsResult, invoicesResult] = await Promise.all([
    backendRequest<TeacherStatementOut[]>(`/api/v1/teacher/statements?year=${year}&month=${month}`, {}, token),
    backendRequest<TeacherInvoiceOut[]>(`/api/v1/teacher/invoices?year=${year}&month=${month}`, {}, token),
  ]);
  if (!statementsResult.ok) {
    return <section className="flash-err">Erreur releves: {statementsResult.message}</section>;
  }
  if (!invoicesResult.ok) {
    return <section className="flash-err">Erreur factures prof: {invoicesResult.message}</section>;
  }

  const statements = statementsResult.data;
  const invoices = invoicesResult.data;
  const invoicesByPayor = new Map<string, TeacherInvoiceOut[]>();
  for (const invoice of invoices) {
    const bucket = invoicesByPayor.get(invoice.payor_legal_entity_id) ?? [];
    bucket.push(invoice);
    invoicesByPayor.set(invoice.payor_legal_entity_id, bucket);
  }

  return (
    <section className="admin-page-grid">
      <article className="card">
        <div className="row spread">
          <h2>Releves mensuels professeur</h2>
          <Link className="mode-link" href="/prof">
            Retour à l'accueil
          </Link>
        </div>
        <form method="get" className="row">
          <label>
            Annee
            <input type="number" name="year" min={2000} max={2100} defaultValue={year} />
          </label>
          <label>
            Mois
            <select name="month" defaultValue={month}>
              {MONTH_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Afficher</button>
        </form>
      </article>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <article className="card">
        <div className="row">
          <form action={teacherApproveStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements?year=${year}&month=${month}`} />
            <button type="submit">Approuver et generer les factures</button>
          </form>
          <form action={teacherDisputeStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements?year=${year}&month=${month}`} />
            <input type="text" name="message" placeholder="Motif de litige" required />
            <button type="submit" className="ghost">
              Signaler un litige
            </button>
          </form>
        </div>
      </article>

      {statements.length === 0 ? (
        <article className="card">
          <p className="muted">Aucun releve trouve pour cette periode.</p>
        </article>
      ) : (
        <div className="grid">
          {statements.map((statement) => (
            <article key={`${statement.payor_legal_entity_id}-${statement.year}-${statement.month}`} className="card">
              <div className="row spread">
                <strong>{statement.payor_legal_entity_name}</strong>
                {statement.attendance_complete ? <span className="status-pill status-ok">{statement.status}</span> : null}
              </div>
              <p className="muted">
                Total HT: {statement.totals_ht} {statement.currency} | TVA: {statement.totals_vat} {statement.currency} | TTC:{" "}
                {statement.totals_ttc} {statement.currency}
              </p>
              {!statement.attendance_complete ? (
                <div className="list">
                  <section className="flash-err">Présences à renseigner</section>
                  {statement.missing_sessions.map((missing) => (
                    <article key={missing.session_id} className="item">
                      {new Date(missing.start_at_utc).toLocaleString("fr-FR")} | {missing.title} | presences manquantes:{" "}
                      {missing.pending_students_count}/{missing.total_students_count}
                    </article>
                  ))}
                </div>
              ) : null}
              <div className="row">
                <Link className="mode-link" href={`/prof/statements/${year}/${month}`}>
                  Voir detail
                </Link>
              </div>

              {invoicesByPayor.get(statement.payor_legal_entity_id)?.map((invoice) => (
                <article key={invoice.id} className="item">
                  <div className="row spread">
                    <strong>{invoice.invoice_number}</strong>
                    <span className={`status-pill ${invoice.status === "cancelled" ? "status-off" : "status-ok"}`}>{invoice.status}</span>
                  </div>
                  <p className="muted">
                    {invoice.totals_ttc} EUR | echeance: {invoice.due_date}
                  </p>
                  <div className="row">
                    <Link className="reset-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
                      PDF
                    </Link>
                    <Link className="reset-link" href={`/prof/invoices/${invoice.id}`}>
                      Ouvrir
                    </Link>
                    <form action={teacherSendInvoiceToAccountingAction}>
                      <input type="hidden" name="invoice_id" value={invoice.id} />
                      <input type="hidden" name="return_to" value={`/prof/statements?year=${year}&month=${month}`} />
                      <button type="submit" className="ghost">
                        Envoyer compta
                      </button>
                    </form>
                    {invoice.status === "cancelled" ? (
                      <form action={teacherUncancelInvoiceAction}>
                        <input type="hidden" name="invoice_id" value={invoice.id} />
                        <input type="hidden" name="return_to" value={`/prof/statements?year=${year}&month=${month}`} />
                        <button type="submit">Reactiver</button>
                      </form>
                    ) : (
                      <form action={teacherCancelInvoiceAction}>
                        <input type="hidden" name="invoice_id" value={invoice.id} />
                        <input type="hidden" name="return_to" value={`/prof/statements?year=${year}&month=${month}`} />
                        <button type="submit" className="danger">
                          Annuler
                        </button>
                      </form>
                    )}
                  </div>
                </article>
              ))}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
