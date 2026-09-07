import Link from "next/link";
import { redirect } from "next/navigation";

import { hasAdminPermission } from "../../../lib/admin-access";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { createAnnualSeriesTransferAction, updateAnnualSeriesTransferStatusAction } from "../../../lib/actions";

type SearchParams = Record<string, string | string[] | undefined>;
type SeriesOption = {
  recurrence_group_id: string;
  session_id: string;
  booking_id: string | null;
  label: string;
  occurrence_count: number;
  minimum_remaining_places: number;
};
type TransferRequest = {
  id: string;
  student_user_id: string;
  student_display_name: string;
  source_booking_id: string;
  source_label: string;
  target_session_id: string;
  target_label: string;
  status: string;
  priority_position: number;
  place_available: boolean;
  internal_note: string | null;
  requested_at: string;
};
type TransfersOut = { requests: TransferRequest[]; source_series: SeriesOption[]; target_series: SeriesOption[] };

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function statusLabel(status: string): string {
  if (status === "COMPLETED") return "Changement effectué";
  if (status === "PARENT_CONTACTED") return "Parent contacté";
  if (status === "CANCELLED") return "Annulée";
  if (status === "DECLINED") return "Refusée";
  return "En attente";
}

export default async function AdminSeriesTransfersPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const me = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!me.ok || !hasAdminPermission(me.data, "can_edit_planning")) redirect("/login?error_code=admin_access_required");

  const params = searchParams ?? {};
  const studentId = param(params, "student_id").trim();
  const endpoint = studentId
    ? `/api/v1/admin/annual-series-transfers?student_user_id=${encodeURIComponent(studentId)}`
    : "/api/v1/admin/annual-series-transfers";
  const result = await backendRequest<TransfersOut>(endpoint, {}, token);
  const data = result.ok ? result.data : { requests: [], source_series: [], target_series: [] };
  const returnTo = studentId ? `/admin/series-transfers?student_id=${encodeURIComponent(studentId)}` : "/admin/series-transfers";
  const open = data.requests.filter((request) => request.status === "WAITING" || request.status === "PARENT_CONTACTED");
  const history = data.requests.filter((request) => !open.includes(request));

  return (
    <main className="admin-page">
      <section className="card">
        <p className="eyebrow">Planning annuel</p>
        <h1>Demandes de changement de série</h1>
        <p>Conservez le créneau actuel de l’élève et tracez sa priorité sur la série souhaitée. Une absence ponctuelle ne déclenche jamais le changement.</p>
      </section>
      {param(params, "ok") ? <p className="form-feedback success">{param(params, "ok")}</p> : null}
      {param(params, "error") || !result.ok ? <p className="form-feedback error">{param(params, "error") || (!result.ok ? result.message : "")}</p> : null}

      {studentId ? (
        <form className="card stack-md" action={createAnnualSeriesTransferAction}>
          <h2>Nouvelle demande</h2>
          <input type="hidden" name="student_user_id" value={studentId} />
          <input type="hidden" name="return_to" value={returnTo} />
          <label>Série actuelle
            <select name="source_booking_id" required defaultValue="">
              <option value="" disabled>Choisir le créneau conservé actuellement</option>
              {data.source_series.map((series) => <option key={series.recurrence_group_id} value={series.booking_id ?? ""}>{series.label}</option>)}
            </select>
          </label>
          <label>Série souhaitée pour toute l’année
            <select name="target_session_id" required defaultValue="">
              <option value="" disabled>Choisir le nouveau créneau</option>
              {data.target_series.map((series) => (
                <option key={series.recurrence_group_id} value={series.session_id}>{series.label} · {series.minimum_remaining_places} place(s) min.</option>
              ))}
            </select>
          </label>
          <label>Note interne
            <textarea name="internal_note" rows={3} placeholder="Contexte, contraintes de la famille, date de la demande…" />
          </label>
          <div><button type="submit">Enregistrer la demande prioritaire</button></div>
        </form>
      ) : (
        <section className="card"><p>Pour créer une demande, ouvrez la fiche de l’élève, onglet Réservations, puis cliquez sur <strong>Demande annuelle</strong>.</p></section>
      )}

      <section className="card stack-md">
        <h2>Demandes actives ({open.length})</h2>
        {open.length === 0 ? <p className="muted">Aucune demande active.</p> : open.map((request) => (
          <article className="card" key={request.id}>
            <div className="row gap-sm">
              <strong>{request.student_display_name}</strong>
              <span className={`status-pill ${request.place_available ? "success" : "warning"}`}>{request.place_available ? "Place disponible" : "En attente d’une place"}</span>
              <span className="status-pill neutral">Priorité n° {request.priority_position}</span>
            </div>
            <p><strong>Actuel :</strong> {request.source_label}<br /><strong>Souhaité :</strong> {request.target_label}</p>
            {request.internal_note ? <p className="muted">{request.internal_note}</p> : null}
            <div className="row gap-sm">
              <Link className="button secondary" href={`/admin/planning-reorganization?booking_id=${encodeURIComponent(request.source_booking_id)}&scope=series_future`}>Préparer le déplacement</Link>
              <form action={updateAnnualSeriesTransferStatusAction}>
                <input type="hidden" name="request_id" value={request.id} /><input type="hidden" name="return_to" value={returnTo} /><input type="hidden" name="status" value="COMPLETED" />
                <button type="submit">Marquer le changement effectué</button>
              </form>
              <form action={updateAnnualSeriesTransferStatusAction}>
                <input type="hidden" name="request_id" value={request.id} /><input type="hidden" name="return_to" value={returnTo} />
                <input type="hidden" name="status" value={request.status === "WAITING" ? "PARENT_CONTACTED" : "WAITING"} />
                <button className="secondary" type="submit">{request.status === "WAITING" ? "Parent contacté" : "Remettre en attente"}</button>
              </form>
              <form action={updateAnnualSeriesTransferStatusAction}>
                <input type="hidden" name="request_id" value={request.id} /><input type="hidden" name="return_to" value={returnTo} /><input type="hidden" name="status" value="CANCELLED" />
                <button className="secondary" type="submit">Annuler la demande</button>
              </form>
            </div>
          </article>
        ))}
      </section>

      {history.length ? <details className="card"><summary><strong>Historique ({history.length})</strong></summary>{history.map((request) => <p key={request.id}><strong>{request.student_display_name}</strong> · {statusLabel(request.status)} · {request.target_label}</p>)}</details> : null}
    </main>
  );
}
