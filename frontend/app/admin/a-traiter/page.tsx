import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest, backendUrl } from "../../../lib/backend";
import type { AdminToProcessMessageOut, AdminToProcessStatus, AdminToProcessStatusUpdateOut } from "../../../lib/types";

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

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function statusLabel(status: AdminToProcessStatus): string {
  if (status === "a_traiter") return "A traiter";
  if (status === "en_cours") return "En cours";
  return "Termine";
}

function statusClass(status: AdminToProcessStatus): string {
  if (status === "a_traiter") return "status-warn";
  if (status === "en_cours") return "status-off";
  return "status-ok";
}

function sourceLabel(value: string): string {
  if (value === "releves_professeur") return "Releves professeur";
  if (value === "facturation_professeur") return "Facturation professeur";
  if (value === "message_portail_professeur") return "Portail professeur";
  return value.replaceAll("_", " ");
}

function typeLabel(value: string): string {
  if (value === "erreur_releve") return "Erreur releve";
  if (value === "erreur_lignes_releve") return "Erreur lignes releve";
  if (value === "prestation_manquante") return "Prestation manquante";
  return value.replaceAll("_", " ");
}

function preview(value: string): string {
  const cleaned = value.replaceAll("\n", " ").trim();
  if (cleaned.length <= 120) {
    return cleaned;
  }
  return `${cleaned.slice(0, 117)}...`;
}

async function updateMessageStatusAction(formData: FormData): Promise<void> {
  "use server";

  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const messageId = String(formData.get("message_id") ?? "").trim();
  const targetStatus = String(formData.get("status") ?? "").trim() as AdminToProcessStatus;
  const returnTo = safeAdminPath(String(formData.get("return_to") ?? ""), "/admin/a-traiter");

  if (!messageId || !["a_traiter", "en_cours", "termine"].includes(targetStatus)) {
    redirect(appendQueryMessage(returnTo, "error", "Mise a jour invalide"));
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
    const detail = (payload?.detail || "Erreur backend").toString();
    redirect(appendQueryMessage(returnTo, "error", detail));
  }

  const _result = payload as AdminToProcessStatusUpdateOut | null;
  redirect(appendQueryMessage(returnTo, "ok", "Statut mis a jour"));
}

export default async function AdminToProcessPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

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

  return (
    <section className="admin-page-grid">
      <section className="card">
        <h2>A traiter</h2>
        <p className="muted">Boite centralisee des messages professeur vers administration.</p>
      </section>

      {!listResult.ok ? <section className="flash-err">Erreur backend: {listResult.message}</section> : null}
      {detailResult && !detailResult.ok ? <section className="flash-err">Erreur detail: {detailResult.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <form method="get" className="grid cols-4 sticky-filters">
          <label className="cols-span-2">
            Recherche
            <input type="search" name="q" defaultValue={q} placeholder="Message, professeur, source..." />
          </label>
          <label>
            Statut
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="a_traiter">A traiter</option>
              <option value="en_cours">En cours</option>
              <option value="termine">Termine</option>
            </select>
          </label>
          <label>
            Source
            <select name="source" defaultValue={selectedSource}>
              <option value="">Toutes</option>
              {sourceOptions.map((value) => (
                <option key={value} value={value}>
                  {sourceLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type de message
            <select name="type" defaultValue={selectedType}>
              <option value="">Tous</option>
              {typeOptions.map((value) => (
                <option key={value} value={value}>
                  {typeLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <div className="row end cols-span-3 top-gap-sm">
            <button type="submit">Filtrer</button>
            <a className="ghost" href="/admin/a-traiter">
              Reset
            </a>
          </div>
        </form>
      </section>

      <section className="card table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date creation</th>
              <th>Source</th>
              <th>Type message</th>
              <th>Statut</th>
              <th>Professeur</th>
              <th>Extrait</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <p className="muted">Aucun message a traiter.</p>
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const detailParams = new URLSearchParams(baseParams);
                detailParams.set("message_id", row.id);
                const detailHref = `/admin/a-traiter?${detailParams.toString()}`;
                return (
                  <tr key={row.id}>
                    <td>{formatDate(row.created_at)}</td>
                    <td>{sourceLabel(row.source)}</td>
                    <td>{typeLabel(row.message_type)}</td>
                    <td>
                      <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
                    </td>
                    <td>{row.teacher_name || "-"}</td>
                    <td>{preview(row.message_body)}</td>
                    <td>
                      <a className="mode-link" href={detailHref}>
                        Voir
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
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={baseHref} aria-label="Fermer">
              ×
            </a>
            <h3 className="modal-title">Detail message</h3>
            <p className="muted">{formatDate(selected.created_at)}</p>
            <div className="stack-sm top-gap-sm">
              <p>
                <strong>Source :</strong> {sourceLabel(selected.source)}
              </p>
              <p>
                <strong>Type :</strong> {typeLabel(selected.message_type)}
              </p>
              <p>
                <strong>Statut :</strong>{" "}
                <span className={`status-pill ${statusClass(selected.status)}`}>{statusLabel(selected.status)}</span>
              </p>
              <p>
                <strong>Professeur :</strong> {selected.teacher_name || "-"}
              </p>
              {selected.related_entity_type || selected.related_entity_id ? (
                <p>
                  <strong>Contexte :</strong> {selected.related_entity_type || "-"} {selected.related_entity_id ? `(${selected.related_entity_id})` : ""}
                </p>
              ) : null}
              <div className="item">
                <strong>Message</strong>
                <pre className="message-full-text">{selected.message_body || "-"}</pre>
              </div>
            </div>

            <form action={updateMessageStatusAction} className="grid top-gap-sm">
              <input type="hidden" name="message_id" value={selected.id} />
              <input type="hidden" name="return_to" value={baseHref} />
              <label>
                Changer le statut
                <select name="status" defaultValue={selected.status}>
                  <option value="a_traiter">A traiter</option>
                  <option value="en_cours">En cours</option>
                  <option value="termine">Termine</option>
                </select>
              </label>
              <div className="row modal-actions-end">
                <button type="submit">Enregistrer</button>
                <a className="reset-link" href={baseHref}>
                  Fermer
                </a>
              </div>
            </form>
          </article>
        </section>
      ) : null}
    </section>
  );
}
