import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../../lib/backend";
import type { NotificationJobRunDetailOut, NotificationJobRunPageOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatDateTime(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "medium" });
}

function statusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "running") {
    return uiText(language, "admin.jobs.status_running");
  }
  if (normalized === "success") {
    return uiText(language, "admin.jobs.status_success");
  }
  if (normalized === "warning") {
    return uiText(language, "admin.jobs.status_warning");
  }
  if (normalized === "failed") {
    return uiText(language, "admin.jobs.status_failed");
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
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

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
        <h2>{t("admin.jobs.title")}</h2>
        <p className="muted">{t("admin.jobs.subtitle")}</p>
      </section>

      <section className="card">
        {!jobsResult.ok ? <p className="flash-err">{t("admin.jobs.backend_error")}: {jobsResult.message}</p> : null}
        {detailResult && !detailResult.ok ? <p className="flash-err">{t("admin.jobs.detail_error")}: {detailResult.message}</p> : null}
        <form className="grid cols-4 sticky-filters" method="get">
          <label>
            {t("admin.jobs.date_from")}
            <input type="datetime-local" name="started_from" defaultValue={startedFrom} />
          </label>
          <label>
            {t("admin.jobs.date_to")}
            <input type="datetime-local" name="started_to" defaultValue={startedTo} />
          </label>
          <label>
            {t("admin.jobs.job_type")}
            <input type="text" name="job_name" defaultValue={jobName} placeholder="reminder_generation_job" />
          </label>
          <label>
            {t("admin.jobs.status_filter")}
            <select name="status" defaultValue={status}>
              <option value="">{uiText(language, "common.all")}</option>
              <option value="running">{statusLabel("running", language)}</option>
              <option value="success">{statusLabel("success", language)}</option>
              <option value="warning">{statusLabel("warning", language)}</option>
              <option value="failed">{statusLabel("failed", language)}</option>
            </select>
          </label>
          <label className="cols-span-2">
            {t("admin.jobs.search_text")}
            <input type="text" name="q" defaultValue={q} placeholder={t("admin.jobs.search_placeholder")} />
          </label>
          <div className="row end cols-span-2 top-gap-sm">
            <button type="submit">{uiText(language, "common.apply")}</button>
            <a className="ghost top-gap-sm-inline" href={resetHref}>
              {t("admin.jobs.reset_filters")}
            </a>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("admin.jobs.column_start")}</th>
                <th>{t("admin.jobs.column_end")}</th>
                <th>{t("admin.jobs.column_job")}</th>
                <th>{uiText(language, "common.status")}</th>
                <th>{t("admin.jobs.column_duration")}</th>
                <th>{t("admin.jobs.column_scanned")}</th>
                <th>{t("admin.jobs.column_processed")}</th>
                <th>{t("admin.jobs.column_sent")}</th>
                <th>{t("admin.jobs.column_skipped")}</th>
                <th>{t("admin.jobs.column_errors")}</th>
                <th>{t("admin.jobs.column_triggered_by")}</th>
                <th>{uiText(language, "client.action")}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={12}>
                    <p className="muted">{t("admin.jobs.no_jobs")}</p>
                  </td>
                </tr>
              ) : (
                jobs.map((row) => {
                  const detailParams = new URLSearchParams(baseParams);
                  detailParams.set("job_run_id", row.id);
                  const detailHref = `/admin/notifications/jobs?${detailParams.toString()}`;
                  return (
                    <tr key={row.id}>
                      <td>{formatDateTime(row.started_at, language)}</td>
                      <td>{formatDateTime(row.finished_at, language)}</td>
                      <td>{row.job_name}</td>
                      <td>
                        <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status, language)}</span>
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
                          {t("admin.jobs.view_detail")}
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
            <a className="modal-close-x" href={baseHref} aria-label={uiText(language, "common.close")}>
              ×
            </a>
            <header className="activity-modal-header">
              <h2 className="modal-title">{t("admin.jobs.detail_title")}</h2>
              <p className="muted">{detailResult.data.run.job_name}</p>
            </header>

            <section className="card modal-card">
              <h3>{t("admin.jobs.summary")}</h3>
              <div className="list">
                <article className="item row spread"><span>{uiText(language, "common.status")}</span><strong>{statusLabel(detailResult.data.run.status, language)}</strong></article>
                <article className="item row spread"><span>{t("admin.jobs.started")}</span><strong>{formatDateTime(detailResult.data.run.started_at, language)}</strong></article>
                <article className="item row spread"><span>{t("admin.jobs.finished")}</span><strong>{formatDateTime(detailResult.data.run.finished_at, language)}</strong></article>
                <article className="item row spread"><span>{t("admin.jobs.triggered_by")}</span><strong>{detailResult.data.run.triggered_by}</strong></article>
                <article className="item row spread"><span>{t("admin.jobs.summary_label")}</span><strong>{detailResult.data.run.summary_text ?? "-"}</strong></article>
                <article className="item row spread"><span>{t("admin.jobs.error_label")}</span><strong>{detailResult.data.run.error_text ?? "-"}</strong></article>
              </div>
            </section>

            <section className="card modal-card">
              <h3>{t("admin.jobs.counters")}</h3>
              <div className="grid cols-5">
                <article className="item"><strong>{t("admin.jobs.column_scanned")}</strong><p>{detailResult.data.run.items_scanned}</p></article>
                <article className="item"><strong>{t("admin.jobs.column_processed")}</strong><p>{detailResult.data.run.items_processed}</p></article>
                <article className="item"><strong>{t("admin.jobs.column_sent")}</strong><p>{detailResult.data.run.items_sent}</p></article>
                <article className="item"><strong>{t("admin.jobs.column_skipped")}</strong><p>{detailResult.data.run.items_skipped}</p></article>
                <article className="item"><strong>{t("admin.jobs.column_errors")}</strong><p>{detailResult.data.run.items_failed}</p></article>
              </div>
            </section>

            <section className="card modal-card">
              <h3>{t("admin.jobs.parameters_context")}</h3>
              <pre className="code-block">{JSON.stringify(detailResult.data.metadata_json, null, 2)}</pre>
            </section>

            <section className="card modal-card">
              <h3>{t("admin.jobs.logs")}</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{uiText(language, "common.date")}</th>
                      <th>{t("admin.jobs.log_level")}</th>
                      <th>{t("admin.jobs.log_message")}</th>
                      <th>{t("admin.jobs.log_context")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailResult.data.logs.length === 0 ? (
                      <tr>
                        <td colSpan={4}>{t("admin.jobs.no_logs")}</td>
                      </tr>
                    ) : (
                      detailResult.data.logs.map((row) => (
                        <tr key={row.id}>
                          <td>{formatDateTime(row.created_at, language)}</td>
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
              <h3>{t("admin.jobs.processed_entities")}</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("admin.jobs.entity_id")}</th>
                      <th>{uiText(language, "common.type")}</th>
                      <th>{uiText(language, "admin.incidents.channel")}</th>
                      <th>{uiText(language, "common.status")}</th>
                      <th>{t("admin.jobs.scheduled_for")}</th>
                      <th>{t("admin.jobs.error_label")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailResult.data.notifications.length === 0 ? (
                      <tr>
                        <td colSpan={6}>{t("admin.jobs.no_related_notifications")}</td>
                      </tr>
                    ) : (
                      detailResult.data.notifications.map((row) => (
                        <tr key={row.id}>
                          <td>{row.id}</td>
                          <td>{row.notification_type}</td>
                          <td>{row.channel}</td>
                          <td>{row.status}</td>
                          <td>{formatDateTime(row.scheduled_for, language)}</td>
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
