import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { teacherApproveStatementsAction, teacherDisputeStatementsAction } from "../../../../../lib/actions";
import { backendRequest } from "../../../../../lib/backend";
import type { TeacherStatementOut } from "../../../../../lib/types";

export default async function TeacherStatementMonthDetailPage({
  params,
  searchParams,
}: {
  params: { year: string; month: string };
  searchParams: Record<string, string | string[] | undefined>;
}): Promise<JSX.Element> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const year = Number.parseInt(params.year, 10);
  const month = Number.parseInt(params.month, 10);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    redirect("/prof/statements?error=Periode%20invalide");
  }

  const ok = Array.isArray(searchParams.ok) ? searchParams.ok[0] : (searchParams.ok ?? "");
  const error = Array.isArray(searchParams.error) ? searchParams.error[0] : (searchParams.error ?? "");
  const statementsResult = await backendRequest<TeacherStatementOut[]>(
    `/api/v1/teacher/statements/${year}/${month}`,
    {},
    token,
  );
  if (!statementsResult.ok) {
    return <section className="flash-err">Erreur releve detail: {statementsResult.message}</section>;
  }

  return (
    <section className="admin-page-grid">
      <article className="card">
        <div className="row spread">
          <h2>Detail releves {month.toString().padStart(2, "0")}/{year}</h2>
          <Link className="reset-link" href={`/prof/statements?year=${year}&month=${month}`}>
            Retour
          </Link>
        </div>
      </article>
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <article className="card">
        <div className="row">
          <form action={teacherApproveStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements/${year}/${month}`} />
            <button type="submit">Approuver et generer les factures</button>
          </form>
          <form action={teacherDisputeStatementsAction}>
            <input type="hidden" name="year" value={year} />
            <input type="hidden" name="month" value={month} />
            <input type="hidden" name="return_to" value={`/prof/statements/${year}/${month}`} />
            <input type="text" name="message" placeholder="Motif du litige" required />
            <button type="submit" className="ghost">
              Litige
            </button>
          </form>
        </div>
      </article>

      {statementsResult.data.map((statement) => (
        <article key={statement.payor_legal_entity_id} className="card">
          <div className="row spread">
            <strong>{statement.payor_legal_entity_name}</strong>
            <span className={`status-pill ${statement.attendance_complete ? "status-ok" : "status-warn"}`}>{statement.status}</span>
          </div>
          <p className="muted">
            HT {statement.totals_ht} | TVA {statement.totals_vat} | TTC {statement.totals_ttc} {statement.currency}
          </p>
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
                {statement.lines.map((line) => (
                  <tr key={`${statement.payor_legal_entity_id}-${line.course_type_id ?? line.course_type_label}`}>
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
          {!statement.attendance_complete ? (
            <div className="list top-gap-sm">
              {statement.missing_sessions.map((row) => (
                <article key={row.session_id} className="item">
                  {new Date(row.start_at_utc).toLocaleString("fr-FR")} | {row.title} | manquantes: {row.pending_students_count}/
                  {row.total_students_count}
                </article>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </section>
  );
}
