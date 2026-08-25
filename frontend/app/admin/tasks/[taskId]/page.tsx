import Link from "next/link";
import { redirect } from "next/navigation";

import { hasTaskManagerAccess } from "../../../../lib/admin-access";
import { getAdminToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type { AdminTaskContactOut, AdminTaskOptionsOut, AdminTaskOut, AdminTaskType, UserOut } from "../../../../lib/types";
import { addAdminTaskCommentAction, updateAdminTaskAction, updateAdminTaskContactAction } from "../actions";
import styles from "../tasks.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

const TYPE_LABELS: Record<AdminTaskType, string> = {
  CLIENT_CALL: "Appel client", PROVIDER_CALL: "Appel prestataire", SLOT_CHOICE: "Choix de créneau",
  PROFESSOR_CONTACT: "Contact professeur", SHEET_MUSIC_DELIVERY: "Remise de partition",
};

function param(params: SearchParams, key: string): string {
  const raw = params[key];
  return Array.isArray(raw) ? raw[0] ?? "" : raw ?? "";
}

function localInput(value: string | null): string {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "Europe/Paris",
  }).formatToParts(new Date(value));
  const item = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${item("year")}-${item("month")}-${item("day")}T${item("hour")}:${item("minute")}`;
}

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Paris" }).format(new Date(value)) : "Non renseignée";
}

export default async function AdminTaskDetailPage({ params, searchParams = {} }: { params: { taskId: string }; searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const [meResult, optionsResult, taskResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<AdminTaskOptionsOut>("/api/v1/admin/tasks/options", {}, token),
    backendRequest<AdminTaskOut>(`/api/v1/admin/tasks/${encodeURIComponent(params.taskId)}`, {}, token),
  ]);
  if (!meResult.ok || !hasTaskManagerAccess(meResult.data)) redirect("/admin?error=Accès%20non%20autorisé");
  if (!taskResult.ok) redirect(`/admin/tasks?error=${encodeURIComponent(taskResult.message)}`);
  if (!optionsResult.ok) redirect(`/admin/tasks?error=${encodeURIComponent(optionsResult.message)}`);
  const task = taskResult.data;
  const ok = param(searchParams, "ok");
  const error = param(searchParams, "error");
  const contactQuery = param(searchParams, "contact_q").trim();
  let contacts: AdminTaskContactOut[] = [];
  let contactSearchError = "";
  if (contactQuery.length >= 2) {
    const result = await backendRequest<AdminTaskContactOut[]>(
      `/api/v1/admin/tasks/contacts?q=${encodeURIComponent(contactQuery)}`,
      {},
      token,
    );
    if (result.ok) contacts = result.data;
    else contactSearchError = result.message;
  }
  const contactHref = task.contact?.kind === "CLIENT"
    ? `/admin/clients/${task.contact.id}`
    : task.contact?.linked_client_id ? `/admin/clients/${task.contact.linked_client_id}` : task.contact ? `/admin/prospects/${task.contact.id}` : null;

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div><p className="muted">Tâche administrative</p><h1>{TYPE_LABELS[task.task_type]}</h1><p className="muted">Créée le {formatDate(task.created_at)} par {task.created_by?.name || "un gestionnaire"}</p></div>
        <Link className="reset-link" href="/admin/tasks">Retour aux tâches</Link>
      </section>
      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}
      <section className={styles.detailGrid}>
        <div className={styles.panel}>
          <h2>Suivi de la tâche</h2>
          <form action={updateAdminTaskAction} className={styles.formGrid}>
            <input type="hidden" name="task_id" value={task.id} />
            <input type="hidden" name="return_to" value={`/admin/tasks/${task.id}`} />
            <label className={styles.field}><span>Type</span><select name="task_type" defaultValue={task.task_type}>{Object.entries(TYPE_LABELS).map(([item, label]) => <option key={item} value={item}>{label}</option>)}</select></label>
            <label className={styles.field}><span>Statut</span><select name="status" defaultValue={task.status}><option value="CREATED">Créée</option><option value="ASSIGNED">Affectée</option><option value="IN_PROGRESS">En cours</option><option value="WAITING_CLIENT">En attente de réponse client</option><option value="COMPLETED">Terminée</option><option value="ARCHIVED">Archivée</option></select></label>
            <label className={styles.field}><span>Responsable</span><select name="assignee_user_id" defaultValue={task.assignee?.id || ""}><option value="">Non affectée</option>{optionsResult.data.managers.map((manager) => <option key={manager.id} value={manager.id}>{manager.name}</option>)}</select><small>Un email sera envoyé en cas de nouvelle affectation.</small></label>
            <label className={styles.field}><span>Échéance</span><input name="due_at" type="datetime-local" defaultValue={localInput(task.due_at)} /></label>
            <label className={`${styles.field} ${styles.span2}`}><span>Descriptif</span><textarea name="description" rows={6} required defaultValue={task.description} /></label>
            <div className={`${styles.actions} ${styles.span2}`}><button type="submit">Enregistrer les modifications</button></div>
          </form>
          <section className={styles.followUpSection}>
            <h3>Commentaires de suivi</h3>
            <form action={addAdminTaskCommentAction} className={styles.commentComposer}>
              <input type="hidden" name="task_id" value={task.id} />
              <input type="hidden" name="return_to" value={`/admin/tasks/${task.id}`} />
              <label className={styles.field}>
                <span>Ajouter un nouveau commentaire</span>
                <textarea name="body" rows={8} maxLength={10000} required placeholder="Saisissez ici la nouvelle information de suivi…" />
              </label>
              <div className={styles.actions}><button type="submit">Ajouter le commentaire</button></div>
            </form>
            {task.comments.length ? (
              <div className={styles.commentHistory}>
                {task.comments.map((comment) => (
                  <article className={styles.commentCard} key={comment.id}>
                    <p className={styles.commentMeta}>
                      <strong>{comment.author?.name || "Auteur non renseigné (commentaire antérieur)"}</strong>
                      <span>{formatDate(comment.created_at)}</span>
                    </p>
                    <p className={styles.commentBody}>{comment.body}</p>
                  </article>
                ))}
              </div>
            ) : <p className="muted">Aucun commentaire de suivi pour le moment.</p>}
          </section>
        </div>
        <aside className={styles.page}>
          <section className={styles.panel}>
            <h3>Personne liée</h3>
            {task.contact ? <div className={styles.contactCard}><strong>{task.contact.name}</strong><span>{task.contact.kind === "CLIENT" ? "Client" : "Prospect"}</span>{task.contact.phone ? <a href={`tel:${task.contact.phone}`}>{task.contact.phone}</a> : <span>Téléphone non renseigné</span>}{task.contact.email ? <a href={`mailto:${task.contact.email}`}>{task.contact.email}</a> : null}{contactHref ? <Link className="ghost" href={contactHref}>Ouvrir la fiche</Link> : null}</div> : <p className="muted">Aucun client ou prospect lié.</p>}
            <form className={`${styles.contactSearch} top-gap-sm`} method="get">
              <label className={styles.field}>
                <span>{task.contact ? "Lier une autre personne" : "Lier une personne"}</span>
                <input name="contact_q" defaultValue={contactQuery} placeholder="Nom, email ou téléphone" minLength={2} required />
              </label>
              <button type="submit">Rechercher</button>
            </form>
            {contactSearchError ? <p className="notice error top-gap-sm">{contactSearchError}</p> : null}
            {contactQuery.length >= 2 && !contactSearchError ? (
              contacts.length ? (
                <div className={`${styles.contactResults} top-gap-sm`}>
                  {contacts.map((contact) => {
                    const isCurrent = task.contact?.kind === contact.kind && task.contact.id === contact.id;
                    return (
                      <div className={styles.contactResultRow} key={`${contact.kind}-${contact.id}`}>
                        <span>
                          <strong>{contact.name}</strong><br />
                          <small>{contact.kind === "CLIENT" ? "Client" : "Prospect"} · {contact.phone || contact.email || "Coordonnées non renseignées"}</small>
                        </span>
                        {isCurrent ? <span className={styles.currentContact}>Déjà liée</span> : (
                          <form action={updateAdminTaskContactAction}>
                            <input type="hidden" name="task_id" value={task.id} />
                            <input type="hidden" name="return_to" value={`/admin/tasks/${task.id}`} />
                            <input type="hidden" name="contact_ref" value={`${contact.kind}:${contact.id}`} />
                            <button type="submit">{task.contact ? "Remplacer" : "Lier"}</button>
                          </form>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : <p className="muted top-gap-sm">Aucun client ou prospect trouvé.</p>
            ) : null}
            {task.contact ? (
              <form action={updateAdminTaskContactAction} className={`${styles.actions} top-gap-sm`}>
                <input type="hidden" name="task_id" value={task.id} />
                <input type="hidden" name="return_to" value={`/admin/tasks/${task.id}`} />
                <input type="hidden" name="contact_ref" value="CLEAR" />
                <button className="ghost" type="submit">Retirer la liaison</button>
              </form>
            ) : null}
          </section>
          <section className={styles.panel}>
            <h3>Contexte</h3>
            <p><strong>Échéance :</strong><br />{formatDate(task.due_at)}</p>
            {task.source.intake_id ? <p><Link href={`/admin/intakes/${task.source.intake_id}`}>{task.source.intake_label || "Ouvrir le questionnaire"}</Link></p> : null}
            {task.source.quote_id ? <p><Link href={`/admin/quotes/${task.source.quote_id}`}>{task.source.quote_label || "Ouvrir le devis"}</Link></p> : null}
            {!task.source.intake_id && !task.source.quote_id ? <p className="muted">Tâche créée depuis le menu.</p> : null}
          </section>
        </aside>
      </section>
    </main>
  );
}
