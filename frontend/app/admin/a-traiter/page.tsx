import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest, backendUrl } from "../../../lib/backend";
import type { AdminToProcessMessageOut, AdminToProcessStatus, AdminToProcessStatusUpdateOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function safeAdminPath(value: string, fallback: string): string {
  const raw = value.trim();
  if (raw.startsWith("/admin")) {
    return raw;
  }
  return fallback;
}

function appendQueryMessage(path: string, key: string, value: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${key}=${encodeURIComponent(value)}`;
}

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function statusLabel(status: AdminToProcessStatus, language: UiLanguage): string {
  if (status === "a_traiter") return uiText(language, "admin.todo.status_todo");
  if (status === "en_cours") return uiText(language, "admin.todo.status_in_progress");
  return uiText(language, "admin.todo.status_done");
}

function statusClass(status: AdminToProcessStatus): string {
  if (status === "a_traiter") return "status-warn";
  if (status === "en_cours") return "status-off";
  return "status-ok";
}

function sourceLabel(value: string, language: UiLanguage): string {
  if (value === "releves_professeur") return uiText(language, "admin.todo.source_teacher_statements");
  if (value === "facturation_professeur") return uiText(language, "admin.todo.source_teacher_invoicing");
  if (value === "message_portail_professeur") return uiText(language, "admin.todo.source_teacher_portal");
  return value.replaceAll("_", " ");
}

function typeLabel(value: string, language: UiLanguage): string {
  if (value === "erreur_releve") return uiText(language, "admin.todo.type_statement_error");
  if (value === "erreur_lignes_releve") return uiText(language, "admin.todo.type_statement_lines_error");
  if (value === "prestation_manquante") return uiText(language, "admin.todo.type_missing_service");
  return value.replaceAll("_", " ");
}

function preview(value: string): string {
  const cleaned = value.replaceAll("\n", " ").trim();
  if (cleaned.length <= 120) {
    return cleaned;
  }
  return `${cleaned.slice(0, 117)}...`;
}

type ParsedMessageBody = {
  heading: string | null;
  details: Array<{ label: string; value: string }>;
  teacherComment: string | null;
  trailingText: string[];
};

function parseMessageBody(value: string): ParsedMessageBody {
  const lines = value.replaceAll("\r\n", "\n").split("\n").map((line) => line.trimEnd());
  let cursor = 0;
  while (cursor < lines.length && !lines[cursor]?.trim()) {
    cursor += 1;
  }

  let heading: string | null = null;
  if (cursor < lines.length && !lines[cursor]?.includes(":")) {
    heading = lines[cursor]?.trim() || null;
    cursor += 1;
  }

  const details: Array<{ label: string; value: string }> = [];
  const trailingText: string[] = [];
  let teacherComment: string | null = null;

  let currentLabel: string | null = null;
  let currentValue = "";

  const flushCurrent = (): void => {
    if (!currentLabel) {
      return;
    }
    const normalizedValue = currentValue.trim() || "-";
    const normalizedLabel = currentLabel.toLowerCase();
    if (normalizedLabel.includes("commentaire") || normalizedLabel.includes("comment")) {
      teacherComment = normalizedValue;
    } else {
      details.push({ label: currentLabel, value: normalizedValue });
    }
    currentLabel = null;
    currentValue = "";
  };

  for (; cursor < lines.length; cursor += 1) {
    const rawLine = lines[cursor] ?? "";
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    const kvMatch = line.match(/^([^:]{2,80}):\s*(.*)$/);
    if (kvMatch) {
      flushCurrent();
      currentLabel = kvMatch[1]?.trim() || null;
      currentValue = kvMatch[2]?.trim() || "";
      continue;
    }
    if (currentLabel) {
      currentValue = currentValue ? `${currentValue}\n${line}` : line;
      continue;
    }
    trailingText.push(line);
  }

  flushCurrent();
  return {
    heading,
    details,
    teacherComment,
    trailingText,
  };
}

function readLanguageFromFormData(formData: FormData): UiLanguage {
  return normalizeUiLanguage(String(formData.get("ui_language") ?? ""));
}

async function updateMessageStatusAction(formData: FormData): Promise<void> {
  "use server";

  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  const language = readLanguageFromFormData(formData);
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const messageId = String(formData.get("message_id") ?? "").trim();
  const targetStatus = String(formData.get("status") ?? "").trim() as AdminToProcessStatus;
  const returnTo = safeAdminPath(String(formData.get("return_to") ?? ""), "/admin/a-traiter");

  if (!messageId || !["a_traiter", "en_cours", "termine"].includes(targetStatus)) {
    redirect(appendQueryMessage(returnTo, "error", uiText(language, "admin.todo.invalid_status_update")));
  }

  const response = await fetch(`${backendUrl()}/api/v1/admin/to-process/messages/${encodeURIComponent(messageId)}/status`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status: targetStatus }),
    cache: "no-store",
  });

  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  revalidatePath("/admin/a-traiter");

  if (!response.ok) {
    const detail = (payload?.detail || uiText(language, "admin.todo.backend_error")).toString();
    redirect(appendQueryMessage(returnTo, "error", detail));
  }

  const _result = payload as AdminToProcessStatusUpdateOut | null;
  redirect(appendQueryMessage(returnTo, "ok", uiText(language, "admin.todo.status_updated")));
}

export default async function AdminToProcessPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const q = readParam(searchParams, "q").trim();
  const status = readParam(searchParams, "status").trim() as AdminToProcessStatus | "";
  const selectedSource = readParam(searchParams, "source").trim();
  const selectedType = readParam(searchParams, "type").trim();
  const selectedMessageId = readParam(searchParams, "message_id").trim();
  const ok = readParam(searchParams, "ok").trim();
  const error = readParam(searchParams, "error").trim();

  const baseParams = new URLSearchParams();
  if (q) baseParams.set("q", q);
  if (status) baseParams.set("status", status);
  if (selectedSource) baseParams.set("source", selectedSource);
  if (selectedType) baseParams.set("type", selectedType);
  const baseHref = baseParams.toString() ? `/admin/a-traiter?${baseParams.toString()}` : "/admin/a-traiter";

  const apiParams = new URLSearchParams();
  if (q) apiParams.set("q", q);
  if (status) apiParams.set("status", status);
  if (selectedSource) apiParams.set("source", selectedSource);
  if (selectedType) apiParams.set("message_type", selectedType);
  apiParams.set("limit", "5000");

  const listResult = await backendRequest<AdminToProcessMessageOut[]>(
    `/api/v1/admin/to-process/messages?${apiParams.toString()}`,
    {},
    token,
  );

  const rows = listResult.ok ? listResult.data : [];
  const sourceOptions = Array.from(new Set(rows.map((row) => row.source))).sort((a, b) => a.localeCompare(b));
  const typeOptions = Array.from(new Set(rows.map((row) => row.message_type))).sort((a, b) => a.localeCompare(b));

  const detailResult = selectedMessageId
    ? await backendRequest<AdminToProcessMessageOut>(
        `/api/v1/admin/to-process/messages/${encodeURIComponent(selectedMessageId)}`,
        {},
        token,
      )
    : null;
  const selected = detailResult && detailResult.ok ? detailResult.data : null;
  const parsedMessage = selected ? parseMessageBody(selected.message_body || "") : null;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>{t("admin.todo.title")}</h2>
        <p className="muted">{t("admin.todo.subtitle")}</p>
      </section>

      {!listResult.ok ? <section className="flash-err">{t("admin.todo.backend_error")}: {listResult.message}</section> : null}
      {detailResult && !detailResult.ok ? <section className="flash-err">{t("admin.todo.detail_error")}: {detailResult.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <form method="get" className="grid cols-4 sticky-filters">
          <label className="cols-span-2">
            {uiText(language, "common.search")}
            <input type="search" name="q" defaultValue={q} placeholder={t("admin.todo.search_placeholder")} />
          </label>
          <label>
            {uiText(language, "common.status")}
            <select name="status" defaultValue={status}>
              <option value="">{uiText(language, "common.all")}</option>
              <option value="a_traiter">{statusLabel("a_traiter", language)}</option>
              <option value="en_cours">{statusLabel("en_cours", language)}</option>
              <option value="termine">{statusLabel("termine", language)}</option>
            </select>
          </label>
          <label>
            {uiText(language, "common.source")}
            <select name="source" defaultValue={selectedSource}>
              <option value="">{uiText(language, "common.all")}</option>
              {sourceOptions.map((value) => (
                <option key={value} value={value}>
                  {sourceLabel(value, language)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("admin.todo.message_type")}
            <select name="type" defaultValue={selectedType}>
              <option value="">{uiText(language, "common.all")}</option>
              {typeOptions.map((value) => (
                <option key={value} value={value}>
                  {typeLabel(value, language)}
                </option>
              ))}
            </select>
          </label>
          <div className="row end cols-span-3 top-gap-sm">
            <button type="submit">{uiText(language, "common.apply")}</button>
            <a className="ghost" href="/admin/a-traiter">
              {uiText(language, "common.reset")}
            </a>
          </div>
        </form>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("admin.todo.column_created_at")}</th>
              <th>{uiText(language, "common.source")}</th>
              <th>{t("admin.todo.message_type")}</th>
              <th>{uiText(language, "common.status")}</th>
              <th>{t("admin.todo.column_teacher")}</th>
              <th>{t("admin.todo.column_excerpt")}</th>
              <th>{uiText(language, "client.action")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">{t("admin.todo.no_results")}</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const detailParams = new URLSearchParams(baseParams);
                detailParams.set("message_id", row.id);
                const detailHref = `/admin/a-traiter?${detailParams.toString()}`;
                return (
                  <tr key={row.id}>
                    <td>{formatDate(row.created_at, language)}</td>
                    <td>{sourceLabel(row.source, language)}</td>
                    <td>{typeLabel(row.message_type, language)}</td>
                    <td>
                      <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status, language)}</span>
                    </td>
                    <td>{row.teacher_name || "-"}</td>
                    <td>{preview(row.message_body)}</td>
                    <td>
                      <a className="mode-link" href={detailHref}>
                        {uiText(language, "common.view")}
                      </a>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      {selected ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact message-detail-modal">
            <a className="modal-close-x" href={baseHref} aria-label={uiText(language, "common.close")}>
              ×
            </a>
            <div className="message-detail-shell">
              <header className="message-detail-header">
                <div className="row spread message-detail-header-row">
                  <h3 className="modal-title message-detail-title">{t("admin.todo.detail_title")}</h3>
                  <span className={`status-pill ${statusClass(selected.status)}`}>{statusLabel(selected.status, language)}</span>
                </div>
                <p className="muted message-detail-date">{formatDate(selected.created_at, language)}</p>
              </header>

              <section className="message-detail-meta-grid">
                <article className="message-detail-meta-item">
                  <span className="message-detail-meta-label">{uiText(language, "common.source")}</span>
                  <strong>{sourceLabel(selected.source, language)}</strong>
                </article>
                <article className="message-detail-meta-item">
                  <span className="message-detail-meta-label">{uiText(language, "common.type")}</span>
                  <strong>{typeLabel(selected.message_type, language)}</strong>
                </article>
                <article className="message-detail-meta-item">
                  <span className="message-detail-meta-label">{t("admin.todo.column_teacher")}</span>
                  <strong>{selected.teacher_name || "-"}</strong>
                </article>
                <article className="message-detail-meta-item">
                  <span className="message-detail-meta-label">{t("admin.todo.message_id")}</span>
                  <strong className="message-detail-meta-mono">{selected.id}</strong>
                </article>
              </section>

              {selected.related_entity_type || selected.related_entity_id ? (
                <section className="message-detail-context">
                  <p className="message-detail-context-title">{t("admin.todo.context")}</p>
                  <p className="message-detail-context-value">
                    {selected.related_entity_type || "-"}
                    {selected.related_entity_id ? ` · ${selected.related_entity_id}` : ""}
                  </p>
                </section>
              ) : null}

              <section className="message-detail-content">
                <h4 className="message-detail-content-title">{parsedMessage?.heading || t("admin.todo.message_heading")}</h4>
                {parsedMessage && parsedMessage.details.length > 0 ? (
                  <dl className="message-detail-kv">
                    {parsedMessage.details.map((detail, detailIndex) => (
                      <div key={`${detailIndex}-${detail.label}`} className="message-detail-kv-row">
                        <dt>{detail.label}</dt>
                        <dd>{detail.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {parsedMessage?.teacherComment ? (
                  <article className="message-detail-comment">
                    <p className="message-detail-comment-title">{t("admin.todo.teacher_comment")}</p>
                    <p>{parsedMessage.teacherComment}</p>
                  </article>
                ) : null}
                {parsedMessage && parsedMessage.trailingText.length > 0 ? (
                  <pre className="message-full-text message-detail-raw">{parsedMessage.trailingText.join("\n")}</pre>
                ) : null}
                {parsedMessage && parsedMessage.details.length === 0 && !parsedMessage.teacherComment && parsedMessage.trailingText.length === 0 ? (
                  <pre className="message-full-text message-detail-raw">{selected.message_body || "-"}</pre>
                ) : null}
              </section>
            </div>

            <form action={updateMessageStatusAction} className="message-detail-status-form">
              <input type="hidden" name="message_id" value={selected.id} />
              <input type="hidden" name="return_to" value={baseHref} />
              <input type="hidden" name="ui_language" value={language} />
              <label className="message-detail-status-label">
                {t("admin.todo.change_status")}
                <select name="status" defaultValue={selected.status}>
                  <option value="a_traiter">{statusLabel("a_traiter", language)}</option>
                  <option value="en_cours">{statusLabel("en_cours", language)}</option>
                  <option value="termine">{statusLabel("termine", language)}</option>
                </select>
              </label>
              <div className="row modal-actions-end">
                <button type="submit">{t("admin.todo.update_status")}</button>
                <a className="reset-link" href={baseHref}>
                  {uiText(language, "common.close")}
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
