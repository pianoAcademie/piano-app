import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../../lib/backend";
import type { NotificationJobRunDetailOut, NotificationJobRunPageOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" });
}

function statusLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "running") {
    return "En cours";
  }
  if (normalized === "success") {
    return "Succes";
  }
  if (normalized === "warning") {
    return "Alerte";
  }
  if (normalized === "failed") {
    return "Echec";
  }
  return status;
}

function statusClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "success") {
    return "status-ok";
  }
  if (normalized === "failed") {
    return "status-cancelled";
  }
  if (normalized === "warning") {
    return "status-warn";
  }
  return "status-off";
}

export default async function AdminNotificationJobsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const startedFrom = readParam(searchParams, "started_from");
  const startedTo = readParam(searchParams, "started_to");
  const jobName = readParam(searchParams, "job_name");
  const status = readParam(searchParams, "status");
  const q = readParam(searchParams, "q");
  const selectedRunId = readParam(searchParams, "job_run_id");

  const listParams = new URLSearchParams();
  if (startedFrom) {
    listParams.set("started_from", startedFrom);
  }
  if (startedTo) {
    listParams.set("started_to", startedTo);
  }
  if (jobName) {
    listParams.set("job_name", jobName);
  }
  if (status) {
    listParams.set("status", status);
  }
  if (q) {
    listParams.set("q", q);
  }
  listParams.set("limit", "500");

  const jobsResult = await backendRequest<NotificationJobRunPageOut>(
    `/api/v1/admin/notifications/job-runs?${listParams.toString()}`,
    {},
    token,
  );
  const jobs = jobsResult.ok ? jobsResult.data.items : [];

  let detailResult: Awaited<ReturnType<typeof backendRequest<NotificationJobRunDetailOut>>> | null = null;
  if (selectedRunId) {
    detailResult = await backendRequest<NotificationJobRunDetailOut>(
      `/api/v1/admin/notifications/job-runs/${selectedRunId}`,
      {},
      token,
    );
  }

  const baseParams = new URLSearchParams();
  if (startedFrom) baseParams.set("started_from", startedFrom);
  if (startedTo) baseParams.set("started_to", startedTo);
  if (jobName) baseParams.set("job_name", jobName);
  if (status) baseParams.set("status", status);
  if (q) baseParams.set("q", q);
  const baseQuery = baseParams.toString();
  const baseHref = baseQuery ? `/admin/notifications/jobs?${baseQuery}` : "/admin/notifications/jobs";
  const resetHref = "/admin/notifications/jobs";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>Monitoring des jobs</h2>
        <p className="muted">Supervision des executions, erreurs et notifications traitees.</p>
      </section>

      <section className="card">
        {!jobsResult.ok ? <p className="flash-err">Erreur backend: {jobsResult.message}</p> : null}
        {detailResult && !detailResult.ok ? <p className="flash-err">Erreur detail: {detailResult.message}</p> : null}
        <form className="grid cols-4 sticky-filters" method="get">
          <label>
            Date du
            <input type="datetime-local" name="started_from" defaultValue={startedFrom} />
          </label>
          <label>
            Date au
            <input type="datetime-local" name="started_to" defaultValue={startedTo} />
          </label>
          <label>
            Type de job
            <input type="text" name="job_name" defaultValue={jobName} placeholder="reminder_generation_job" />
          </label>
          <label>
            Statut
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="running">running</option>
              <option value="success">success</option>
              <option value="warning">warning</option>
              <option value="failed">failed</option>
            </select>
          </label>
          <label className="cols-span-2">
            Recherche texte
            <input type="text" name="q" defaultValue={q} placeholder="summary/error/job name" />
          </label>
          <div className="row end cols-span-2 top-gap-sm">
            <button type="submit">Appliquer</button>
            <a className="ghost top-gap-sm-inline" href={resetHref}>
              Reset filtres
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Debut</th>
                <th>Fin</th>
                <th>Job</th>
                <th>Statut</th>
                <th>Duree</th>
                <th>Scannes</th>
                <th>Traites</th>
                <th>Envoyes</th>
                <th>Ignores</th>
                <th>Erreurs</th>
                <th>Declenchement</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={12}>
                    <p className="muted">Aucun job trouve pour les filtres selectionnes.</p>
                  </td>
                </tr>
              ) : (
                jobs.map((row) => {
                  const detailParams = new URLSearchParams(baseParams);
                  detailParams.set("job_run_id", row.id);
                  const detailHref = `/admin/notifications/jobs?${detailParams.toString()}`;
                  return (
                    <tr key={row.id}>
                      <td>{formatDateTime(row.started_at)}</td>
                      <td>{formatDateTime(row.finished_at)}</td>
                      <td>{row.job_name}</td>
                      <td>
                        <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
                      </td>
                      <td>{row.duration_seconds ?? "-"}</td>
                      <td>{row.items_scanned}</td>
                      <td>{row.items_processed}</td>
                      <td>{row.items_sent}</td>
                      <td>{row.items_skipped}</td>
                      <td>{row.items_failed}</td>
                      <td>{row.triggered_by}</td>
                      <td>
                        <a className="ghost" href={detailHref}>
                          Voir le detail
                        </a>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {detailResult?.ok ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-panel-wide">
            <a className="modal-close-x" href={baseHref} aria-label="Fermer">
              ×
            </a>
            <header className="activity-modal-header">
              <h2 className="modal-title">Detail job</h2>
              <p className="muted">{detailResult.data.run.job_name}</p>
            </header>

            <section className="card modal-card">
              <h3>Resume</h3>
              <div className="list">
                <article className="item row spread"><span>Statut</span><strong>{statusLabel(detailResult.data.run.status)}</strong></article>
                <article className="item row spread"><span>Started</span><strong>{formatDateTime(detailResult.data.run.started_at)}</strong></article>
                <article className="item row spread"><span>Finished</span><strong>{formatDateTime(detailResult.data.run.finished_at)}</strong></article>
                <article className="item row spread"><span>Triggered by</span><strong>{detailResult.data.run.triggered_by}</strong></article>
                <article className="item row spread"><span>Summary</span><strong>{detailResult.data.run.summary_text ?? "-"}</strong></article>
                <article className="item row spread"><span>Error</span><strong>{detailResult.data.run.error_text ?? "-"}</strong></article>
              </div>
            </section>

            <section className="card modal-card">
              <h3>Compteurs</h3>
              <div className="grid cols-5">
                <article className="item"><strong>Scannes</strong><p>{detailResult.data.run.items_scanned}</p></article>
                <article className="item"><strong>Traites</strong><p>{detailResult.data.run.items_processed}</p></article>
                <article className="item"><strong>Envoyes</strong><p>{detailResult.data.run.items_sent}</p></article>
                <article className="item"><strong>Ignores</strong><p>{detailResult.data.run.items_skipped}</p></article>
                <article className="item"><strong>Erreurs</strong><p>{detailResult.data.run.items_failed}</p></article>
              </div>
            </section>

            <section className="card modal-card">
              <h3>Parametres / contexte</h3>
              <pre className="code-block">{JSON.stringify(detailResult.data.metadata_json, null, 2)}</pre>
            </section>

            <section className="card modal-card">
              <h3>Logs</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Level</th>
                      <th>Message</th>
                      <th>Contexte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailResult.data.logs.length === 0 ? (
                      <tr>
                        <td colSpan={4}>Aucun log</td>
                      </tr>
                    ) : (
                      detailResult.data.logs.map((row) => (
                        <tr key={row.id}>
                          <td>{formatDateTime(row.created_at)}</td>
                          <td>{row.level}</td>
                          <td>{row.message}</td>
                          <td><code>{JSON.stringify(row.context_json)}</code></td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card modal-card">
              <h3>Entites traitees</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Type</th>
                      <th>Canal</th>
                      <th>Statut</th>
                      <th>Planifie le</th>
                      <th>Erreur</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailResult.data.notifications.length === 0 ? (
                      <tr>
                        <td colSpan={6}>Aucune notification rattachee.</td>
                      </tr>
                    ) : (
                      detailResult.data.notifications.map((row) => (
                        <tr key={row.id}>
                          <td>{row.id}</td>
                          <td>{row.notification_type}</td>
                          <td>{row.channel}</td>
                          <td>{row.status}</td>
                          <td>{formatDateTime(row.scheduled_for)}</td>
                          <td>{row.failure_reason ?? "-"}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </article>
        </section>
      ) : null}
    </section>
  );
}
