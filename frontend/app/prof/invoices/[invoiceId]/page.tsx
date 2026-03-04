import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  teacherCancelInvoiceAction,
  teacherSendInvoiceToAccountingAction,
  teacherUncancelInvoiceAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { TeacherInvoiceOut } from "../../../../lib/types";

export default async function TeacherInvoiceDetailPage({
  params,
  searchParams,
}: {
  params: { invoiceId: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const invoiceId = params.invoiceId;
  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");

  const result = await backendRequest<TeacherInvoiceOut>(`/api/v1/teacher/invoices/${invoiceId}`, {}, token);
  if (!result.ok) {
    return <section className="flash-err">Erreur facture professeur: {result.message}</section>;
  }
  const invoice = result.data;

  return (
    <section className="admin-page-grid">
      <article className="card">
        <div className="row spread">
          <h2>Facture {invoice.invoice_number}</h2>
          <Link className="reset-link" href={`/prof/statements?year=${invoice.invoice_date.slice(0, 4)}&month=${invoice.invoice_date.slice(5, 7)}`}>
            Retour releves
          </Link>
        </div>
        <p className="muted">
          {invoice.payor_legal_entity_name} | Date: {invoice.invoice_date} | Echeance: {invoice.due_date}
        </p>
      </article>
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <article className="card">
        <div className="row">
          <a className="mode-link" href={`/api/v1/teacher/invoices/${invoice.id}/pdf`}>
            Telecharger PDF
          </a>
          <form action={teacherSendInvoiceToAccountingAction}>
            <input type="hidden" name="invoice_id" value={invoice.id} />
            <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
            <button type="submit">Envoyer a la comptabilite</button>
          </form>
          {invoice.status === "cancelled" ? (
            <form action={teacherUncancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit">Reactiver</button>
            </form>
          ) : (
            <form action={teacherCancelInvoiceAction}>
              <input type="hidden" name="invoice_id" value={invoice.id} />
              <input type="hidden" name="return_to" value={`/prof/invoices/${invoice.id}`} />
              <button type="submit" className="danger">
                Annuler
              </button>
            </form>
          )}
        </div>
      </article>

      <article className="card">
        <div className="list">
          <article className="item row spread">
            <span className="muted">Statut</span>
            <strong>{invoice.status}</strong>
          </article>
          <article className="item row spread">
            <span className="muted">SIRET prof</span>
            <strong>{invoice.teacher_siret_display}</strong>
          </article>
          <article className="item row spread">
            <span className="muted">IBAN</span>
            <strong>{invoice.teacher_iban}</strong>
          </article>
          <article className="item row spread">
            <span className="muted">Total HT</span>
            <strong>{invoice.totals_ht}</strong>
          </article>
          <article className="item row spread">
            <span className="muted">Total TVA</span>
            <strong>{invoice.totals_vat}</strong>
          </article>
          <article className="item row spread">
            <span className="muted">Total TTC</span>
            <strong>{invoice.totals_ttc}</strong>
          </article>
        </div>
      </article>

      <article className="card">
        <h3>Lignes facture</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Prestation</th>
                <th>Heures</th>
                <th>Taux HT</th>
                <th>Montant HT</th>
                <th>Montant TTC</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.course_type_label}</td>
                  <td>{line.hours}</td>
                  <td>{line.unit_rate_ht}</td>
                  <td>{line.amount_ht}</td>
                  <td>{line.amount_ttc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
