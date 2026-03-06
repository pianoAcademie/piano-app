import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminTeacherInvoicingNav from "../../../../components/admin-teacher-invoicing-nav";
import { backendRequest } from "../../../../lib/backend";
import type { ProfessorStatementRow } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function payoutStatusLabel(value: ProfessorStatementRow["payout_status"]): string {
  if (value === "PAID") {
    return "Paye";
  }
  if (value === "APPROVED") {
    return "Valide";
  }
  if (value === "PENDING") {
    return "A verifier";
  }
  return "-";
}

function statementAmountLabel(row: ProfessorStatementRow): string {
  if (!row.amount_snapshot) {
    return "-";
  }
  const amount = Number(row.amount_snapshot);
  if (!Number.isFinite(amount)) {
    return `${row.amount_snapshot} ${row.currency_snapshot ?? ""}`.trim();
  }
  return `${amount.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${row.currency_snapshot ?? "EUR"}`;
}

export default async function AdminTeacherInvoicingStatementsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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
      <AdminTeacherInvoicingNav activeTab="statements" />

      {!statementsResult.ok ? <section className="flash-err">Erreur backend: {statementsResult.message}</section> : null}

      <section className="card">
        <div className="row spread">
          <h3>Releves</h3>
          <form method="get" className="row catalog-admin-filters">
            <label>
              Recherche
              <input type="search" name="q" defaultValue={query} placeholder="Professeur, activite, lieu..." />
            </label>
            <label>
              Statut
              <select name="status" defaultValue={statusFilter}>
                <option value="">Tous</option>
                <option value="PENDING">A verifier</option>
                <option value="APPROVED">Valides</option>
                <option value="PAID">Payes</option>
              </select>
            </label>
            <button type="submit">Filtrer</button>
            <Link className="ghost" href="/admin/teacher-invoicing/statements">
              Reinitialiser
            </Link>
          </form>
        </div>
        <p className="muted">Controle des releves, validation et suivi des litiges avant generation de facture.</p>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Professeur</th>
              <th>Date / Horaire</th>
              <th>Activite</th>
              <th>Lieu</th>
              <th>Statut releve</th>
              <th>Montant</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">Aucune ligne de releve pour ces filtres.</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.session_id}>
                  <td>{row.professor_name}</td>
                  <td>{formatDate(row.start_at_utc)}</td>
                  <td>{row.course_type_name}</td>
                  <td>{row.location_name}</td>
                  <td>{payoutStatusLabel(row.payout_status)}</td>
                  <td>{statementAmountLabel(row)}</td>
                  <td>
                    <Link className="mode-link" href={`/admin/professors/${row.professor_id}?tab=solde`}>
                      Ouvrir
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
