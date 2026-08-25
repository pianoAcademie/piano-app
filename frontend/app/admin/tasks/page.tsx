import Link from "next/link";
import { redirect } from "next/navigation";

import { hasTaskManagerAccess } from "../../../lib/admin-access";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type {
  AdminTaskContactOut,
  AdminTaskEffectiveStatus,
  AdminTaskOptionsOut,
  AdminTaskOut,
  AdminTaskSourcePrefillOut,
  AdminTaskType,
  UserOut,
} from "../../../lib/types";
import { createAdminTaskAction } from "./actions";
import styles from "./tasks.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

const TYPE_LABELS: Record<AdminTaskType, string> = {
  CLIENT_CALL: "Appel client",
  PROVIDER_CALL: "Appel prestataire",
  SLOT_CHOICE: "Choix de créneau",
  PROFESSOR_CONTACT: "Contact professeur",
  SHEET_MUSIC_DELIVERY: "Remise de partition",
  PLANNING: "Planning",
};

const STATUS_LABELS: Record<AdminTaskEffectiveStatus, string> = {
  CREATED: "Créée",
  ASSIGNED: "Affectée",
  IN_PROGRESS: "En cours",
  CONTACTED_NO_RESPONSE: "Contacté sans réponse",
  WAITING_CLIENT: "En attente de réponse client",
  OVERDUE: "En retard",
  COMPLETED: "Terminée",
  ARCHIVED: "Archivée",
};

function param(params: SearchParams, key: string): string {
  const raw = params[key];
  return Array.isArray(raw) ? raw[0] ?? "" : raw ?? "";
}

function taskStatusClass(status: AdminTaskEffectiveStatus): string {
  if (status === "COMPLETED") return "status-ok";
  if (status === "OVERDUE") return "status-off";
  if (status === "ARCHIVED") return "status-off";
  return "status-warn";
}

function formatDate(value: string | null, includeTime = true): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" as const } : {}),
    timeZone: "Europe/Paris",
  }).format(new Date(value));
}

function listHref(searchParams: SearchParams, changes: Record<string, string | null>): string {
  const next = new URLSearchParams();
  for (const [key, raw] of Object.entries(searchParams)) {
    const item = Array.isArray(raw) ? raw[0] : raw;
    if (item) next.set(key, item);
  }
  for (const [key, item] of Object.entries(changes)) {
    if (item) next.set(key, item);
    else next.delete(key);
  }
  const query = next.toString();
  return `/admin/tasks${query ? `?${query}` : ""}`;
}

export default async function AdminTasksPage({ searchParams = {} }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const view = param(searchParams, "view") === "all" ? "all" : "mine";
  const status = param(searchParams, "status").toUpperCase();
  const assignee = param(searchParams, "assignee");
  const includeArchived = param(searchParams, "archived") === "1";
  const query = new URLSearchParams();
  if (view === "mine") query.set("mine", "true");
  else if (assignee) query.set("assignee_user_id", assignee);
  if (status) query.set("status", status);
  if (includeArchived) query.set("include_archived", "true");

  const [meResult, optionsResult, tasksResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<AdminTaskOptionsOut>("/api/v1/admin/tasks/options", {}, token),
    backendRequest<AdminTaskOut[]>(`/api/v1/admin/tasks?${query.toString()}`, {}, token),
  ]);
  if (!meResult.ok || !hasTaskManagerAccess(meResult.data)) redirect("/admin?error=Accès%20non%20autorisé");
  if (!optionsResult.ok) redirect(`/admin?error=${encodeURIComponent(optionsResult.message)}`);
  const tasks = tasksResult.ok ? tasksResult.data : [];
  const options = optionsResult.data;
  const createOpen = param(searchParams, "create") === "1";
  const intakeId = param(searchParams, "intake_id");
  const quoteId = param(searchParams, "quote_id");
  let sourcePrefill: AdminTaskSourcePrefillOut | null = null;
  if (createOpen && (intakeId || quoteId)) {
    const sourceQuery = new URLSearchParams();
    if (intakeId) sourceQuery.set("intake_id", intakeId);
    if (quoteId) sourceQuery.set("quote_id", quoteId);
    const result = await backendRequest<AdminTaskSourcePrefillOut>(
      `/api/v1/admin/tasks/source-prefill?${sourceQuery.toString()}`,
      {},
      token,
    );
    sourcePrefill = result.ok ? result.data : null;
  }
  const contactQuery = param(searchParams, "contact_q").trim();
  let contacts: AdminTaskContactOut[] = [];
  if (contactQuery.length >= 2) {
    const result = await backendRequest<AdminTaskContactOut[]>(
      `/api/v1/admin/tasks/contacts?q=${encodeURIComponent(contactQuery)}`,
      {},
      token,
    );
    contacts = result.ok ? result.data : [];
  }
  const sourceContactKey = sourcePrefill?.contact
    ? `${sourcePrefill.contact.kind}-${sourcePrefill.contact.id}`
    : "";
  const contactOptions = sourcePrefill?.contact
    ? [sourcePrefill.contact, ...contacts.filter((contact) => `${contact.kind}-${contact.id}` !== sourceContactKey)]
    : contacts;
  const error = param(searchParams, "error") || (!tasksResult.ok ? tasksResult.message : "");
  const ok = param(searchParams, "ok");
  const createReturnTo = listHref(searchParams, {});

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <h1>Tâches administratives</h1>
          <p className="muted">Appels, choix de créneaux, contacts professeurs et remises de partitions.</p>
        </div>
        <Link className="reset-link" href={listHref(searchParams, { create: "1" })}>Créer une tâche</Link>
      </section>

      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      {createOpen ? (
        <section className={styles.panel}>
          <div className="row spread wrap gap-sm">
            <div>
              <h2>Nouvelle tâche</h2>
              <p className="muted">
                {intakeId ? "Cette tâche sera rattachée au questionnaire ouvert. " : ""}
                {quoteId ? "Cette tâche sera rattachée au devis ouvert. " : ""}
                Un email est envoyé dès qu’un responsable est choisi.
              </p>
            </div>
            <Link className="ghost" href={listHref(searchParams, { create: null, contact_q: null, intake_id: null, quote_id: null })}>Fermer</Link>
          </div>

          <form className={`${styles.contactSearch} top-gap-sm`} method="get">
            <input type="hidden" name="create" value="1" />
            <input type="hidden" name="view" value={view} />
            {intakeId ? <input type="hidden" name="intake_id" value={intakeId} /> : null}
            {quoteId ? <input type="hidden" name="quote_id" value={quoteId} /> : null}
            <label className={styles.field}>
              <span>Rechercher un client ou un prospect</span>
              <input name="contact_q" defaultValue={contactQuery} placeholder="Nom, email ou téléphone" minLength={2} />
            </label>
            <button type="submit">Rechercher</button>
          </form>

          <form action={createAdminTaskAction} className={`${styles.formGrid} top-gap-sm`}>
            <input type="hidden" name="return_to" value={createReturnTo} />
            {intakeId ? <input type="hidden" name="intake_id" value={intakeId} /> : null}
            {quoteId ? <input type="hidden" name="quote_id" value={quoteId} /> : null}
            <label className={styles.field}>
              <span>Type *</span>
              <select name="task_type" defaultValue="CLIENT_CALL" required>
                {Object.entries(TYPE_LABELS).map(([item, label]) => <option key={item} value={item}>{label}</option>)}
              </select>
            </label>
            <label className={styles.field}>
              <span>Responsable</span>
              <select name="assignee_user_id" defaultValue={options.current_user_id}>
                <option value="">Non affectée</option>
                {options.managers.map((manager) => <option key={manager.id} value={manager.id}>{manager.name}</option>)}
              </select>
            </label>
            <label className={styles.field}>
              <span>Échéance</span>
              <input name="due_at" type="datetime-local" />
            </label>
            <div className={styles.field}>
              <span>Client ou prospect</span>
              {contactOptions.length ? (
                <div className={styles.contactResults}>
                  {contactOptions.map((contact) => (
                    <label className={styles.contactOption} key={`${contact.kind}-${contact.id}`}>
                      <input
                        type="radio"
                        name="contact_ref"
                        value={`${contact.kind}:${contact.id}`}
                        defaultChecked={`${contact.kind}-${contact.id}` === sourceContactKey}
                      />
                      <span>
                        <strong>{contact.name}</strong><br />
                        <small>
                          {contact.kind === "CLIENT" ? "Client" : "Prospect"} · {contact.phone || contact.email || "Coordonnées non renseignées"}
                          {`${contact.kind}-${contact.id}` === sourceContactKey ? " · Responsable repris automatiquement" : ""}
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              ) : <span className="muted">{contactQuery ? "Aucun résultat." : "Utilisez la recherche ci-dessus si cette tâche concerne une personne."}</span>}
            </div>
            <label className={`${styles.field} ${styles.span2}`}>
              <span>Descriptif *</span>
              <textarea name="description" required rows={4} maxLength={10000} defaultValue={sourcePrefill?.description || ""} />
            </label>
            <label className={`${styles.field} ${styles.span2}`}>
              <span>Commentaire</span>
              <textarea name="comment" rows={3} maxLength={10000} />
            </label>
            <div className={`${styles.actions} ${styles.span2}`}><button type="submit">Créer et affecter la tâche</button></div>
          </form>
        </section>
      ) : null}

      <section className={styles.panel}>
        <div className={styles.tabs}>
          <Link className={`${styles.tab} ${view === "mine" ? styles.tabActive : ""}`} href={listHref(searchParams, { view: "mine", assignee: null })}>Mes tâches</Link>
          <Link className={`${styles.tab} ${view === "all" ? styles.tabActive : ""}`} href={listHref(searchParams, { view: "all" })}>Toutes les tâches</Link>
        </div>
        <form className={`${styles.filters} top-gap-sm`}>
          <input type="hidden" name="view" value={view} />
          <label className={styles.field}>
            <span>Statut</span>
            <select name="status" defaultValue={status}>
              <option value="">Tous les statuts</option>
              {Object.entries(STATUS_LABELS).map(([item, label]) => <option key={item} value={item}>{label}</option>)}
            </select>
          </label>
          {view === "all" ? (
            <label className={styles.field}>
              <span>Responsable</span>
              <select name="assignee" defaultValue={assignee}>
                <option value="">Toutes les personnes</option>
                {options.managers.map((manager) => <option key={manager.id} value={manager.id}>{manager.name}</option>)}
              </select>
            </label>
          ) : <div />}
          <label className="row gap-sm"><input type="checkbox" name="archived" value="1" defaultChecked={includeArchived} /> Archives</label>
          <button type="submit">Filtrer</button>
        </form>
      </section>

      <section className={styles.panel}>
        <div className="row spread wrap gap-sm"><h2>{view === "mine" ? "Mes tâches" : "Toutes les tâches"}</h2><span className="badge">{tasks.length}</span></div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Statut</th><th>Tâche</th><th>Personne liée</th><th>Responsable</th><th>Échéance</th><th /></tr></thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td><span className={`status-pill ${taskStatusClass(task.effective_status)}`}>{STATUS_LABELS[task.effective_status]}</span></td>
                  <td><strong>{TYPE_LABELS[task.task_type]}</strong><div className={styles.description} title={task.description}>{task.description}</div><div className={styles.meta}><span>Créée le {formatDate(task.created_at)}</span></div></td>
                  <td>{task.contact ? <><strong>{task.contact.name}</strong><br /><span>{task.contact.phone || task.contact.email || "—"}</span></> : "—"}</td>
                  <td>{task.assignee?.name || "Non affectée"}</td>
                  <td>{formatDate(task.due_at)}</td>
                  <td><Link className="ghost" href={`/admin/tasks/${task.id}`}>Ouvrir</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!tasks.length ? <div className={styles.empty}>Aucune tâche ne correspond aux filtres.</div> : null}
      </section>
    </main>
  );
}
