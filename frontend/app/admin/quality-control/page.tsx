import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { repairSafeQuotePlanningMismatchesAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { AdminQuotePlanningAuditOut, UserOut } from "../../../lib/types";


type SearchParams = Record<string, string | string[] | undefined>;


function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}


function dateLabel(value: string | null): string {
  if (!value) return "-";
  const parts = value.split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : value;
}


function issueLabel(code: string): string {
  const labels: Record<string, string> = {
    PLANNING_DATE_MISMATCH: "Dates du planning différentes du devis",
    BOOKING_COUNT_MISMATCH: "Nombre d’inscriptions différent du devis",
    MISSING_INVOICE_LINE: "Ligne de facture manquante",
    INVOICE_DATE_MISMATCH: "Date de facture différente du planning",
    INVOICE_AMOUNT_MISMATCH: "Montant de facture différent de l’inscription",
  };
  return labels[code] ?? code;
}


export default async function AdminQualityControlPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) redirect("/login?error_code=session_expired");
  const me = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!me.ok || (me.data.role !== "admin" && !me.data.admin_permissions?.can_view_quotes)) {
    redirect("/login?error_code=admin_access_required");
  }

  const schoolYear = param(searchParams, "school_year") || "2026-2027";
  const result = await backendRequest<AdminQuotePlanningAuditOut>(
    `/api/v1/admin/quality-control/quote-planning?school_year=${encodeURIComponent(schoolYear)}`,
    {},
    token,
    120000,
  );
  const audit = result.ok ? result.data : null;
  const okMessage = param(searchParams, "ok");
  const errorMessage = param(searchParams, "error");

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Contrôle devis, planning et factures</h2>
        <p className="muted">
          Ce contrôle compare les dates acceptées dans chaque devis avec les inscriptions réellement créées, puis vérifie les dates et montants figés dans les factures.
        </p>
      </section>

      {okMessage ? <p className="flash-ok">{okMessage}</p> : null}
      {errorMessage ? <p className="flash-err">{errorMessage}</p> : null}
      {!result.ok ? <p className="flash-err">Contrôle indisponible : {result.message}</p> : null}

      <section className="card">
        <form method="get" className="admin-list-filter-form">
          <div className="admin-list-filter-primary">
            <label>
              Année scolaire
              <input name="school_year" defaultValue={schoolYear} />
            </label>
            <div className="admin-list-filter-actions"><button type="submit">Contrôler</button></div>
          </div>
        </form>
      </section>

      {audit ? (
        <>
          <section className="grid cols-4">
            <article className="card"><span className="muted">Devis contrôlés</span><h2>{audit.checked_quotes}</h2></article>
            <article className="card"><span className="muted">Séries concernées</span><h2>{audit.affected_series}</h2></article>
            <article className="card"><span className="muted">Écarts</span><h2>{audit.issue_count}</h2></article>
            <article className="card"><span className="muted">Corrections vérifiées</span><h2>{audit.approved_repair_count}</h2></article>
          </section>

          {audit.approved_repair_count > 0 && me.data.role === "admin" ? (
            <section className="card">
              <h3>Corrections automatiques vérifiées</h3>
              <p className="muted">
                Seules les neuf séries auditées le 28 août sont concernées. Pour chaque enfant, le nombre d’inscriptions correspond exactement au devis. Les identifiants d’inscription, les tarifs et les montants facturés sont conservés. Aucun e-mail n’est envoyé.
              </p>
              <form action={repairSafeQuotePlanningMismatchesAction}>
                <input type="hidden" name="school_year" value={schoolYear} />
                <button type="submit">Corriger les séries auditées</button>
              </form>
            </section>
          ) : null}

          <section className="card">
            <h3>Résultats</h3>
            {audit.items.length === 0 ? (
              <p className="flash-ok">Aucun écart détecté pour {schoolYear}.</p>
            ) : (
              <div className="table-wrap admin-table-card-wrap">
                <table className="data-table admin-responsive-table">
                  <thead>
                    <tr>
                      <th>Élève / devis</th>
                      <th>Créneau</th>
                      <th>Contrôle</th>
                      <th>Dates</th>
                      <th>Facture</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.items.map((item) => (
                      <tr key={`${item.quote_id}:${item.series_id}`}>
                        <td data-mobile-label="Élève" className="mobile-row-primary">
                          <strong>{item.student_name}</strong><br />
                          <Link href={`/admin/quotes/${item.quote_id}`}>{item.quote_number}</Link>
                        </td>
                        <td data-mobile-label="Créneau">
                          {item.activity_name}<br />{item.location_name}<br />{item.slot_label}
                        </td>
                        <td data-mobile-label="Contrôle">
                          {item.issue_codes.map((code) => <span key={code} className="status-pill status-warn">{issueLabel(code)}</span>)}
                        </td>
                        <td data-mobile-label="Dates">
                          Devis : {item.expected_sessions} ({dateLabel(item.expected_start)} → {dateLabel(item.expected_end)})<br />
                          Planning : {item.booked_sessions} ({dateLabel(item.booked_start)} → {dateLabel(item.booked_end)})
                          {item.unexpected_dates.length ? <><br /><strong>À retirer :</strong> {item.unexpected_dates.map(dateLabel).join(", ")}</> : null}
                          {item.missing_dates.length ? <><br /><strong>À ajouter :</strong> {item.missing_dates.map(dateLabel).join(", ")}</> : null}
                        </td>
                        <td data-mobile-label="Facture">
                          {item.invoiced_sessions}/{item.booked_sessions} ligne(s)<br />
                          {item.issue_codes.includes("INVOICE_AMOUNT_MISMATCH") ? "Montant à vérifier" : "Montants cohérents"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
