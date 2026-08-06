import { redirect } from "next/navigation";

import { createClientNewsAction, deleteClientNewsAction, updateClientNewsAction } from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminClientNewsOut, UserOut } from "../../../lib/types";
import styles from "./client-news.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function localDateTimeValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes): string => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function statusLabel(article: AdminClientNewsOut): string {
  if (article.status === "DRAFT") return "Brouillon";
  if (article.published_at && new Date(article.published_at).getTime() > Date.now()) return "Planifiée";
  if (article.expires_at && new Date(article.expires_at).getTime() <= Date.now()) return "Expirée";
  return "Publiée";
}

function NewsFields({ article }: { article?: AdminClientNewsOut }): JSX.Element {
  return (
    <div className={styles.formGrid}>
      <label className={styles.wide}><span>Titre *</span><input name="title_fr" required maxLength={220} defaultValue={article?.title_fr ?? ""} /></label>
      <label className={styles.wide}><span>Résumé court</span><textarea name="summary_fr" maxLength={500} rows={2} defaultValue={article?.summary_fr ?? ""} /></label>
      <label className={styles.wide}><span>Actualité *</span><textarea name="body_fr" required maxLength={20000} rows={7} defaultValue={article?.body_fr ?? ""} /></label>
      <label><span>Statut</span><select name="status" defaultValue={article?.status ?? "DRAFT"}><option value="DRAFT">Brouillon</option><option value="PUBLISHED">Publier</option></select></label>
      <label><span>Publication (heure de Paris)</span><input type="datetime-local" name="published_at_local" defaultValue={localDateTimeValue(article?.published_at ?? null)} /></label>
      <label><span>Expiration facultative</span><input type="datetime-local" name="expires_at_local" defaultValue={localDateTimeValue(article?.expires_at ?? null)} /></label>
      <label className={styles.check}><input type="checkbox" name="is_pinned" defaultChecked={article?.is_pinned ?? false} /> Épingler en premier</label>
      <label className={styles.wide}><span>Lien facultatif</span><input type="url" name="link_url" placeholder="https://..." defaultValue={article?.link_url ?? ""} /></label>
      <label><span>Libellé du lien</span><input name="link_label_fr" maxLength={120} placeholder="En savoir plus" defaultValue={article?.link_label_fr ?? ""} /></label>
      <details className={`${styles.translation} ${styles.wide}`}>
        <summary>Version anglaise facultative</summary>
        <div className={styles.formGrid}>
          <label className={styles.wide}><span>Titre anglais</span><input name="title_en" maxLength={220} defaultValue={article?.title_en ?? ""} /></label>
          <label className={styles.wide}><span>Résumé anglais</span><textarea name="summary_en" maxLength={500} rows={2} defaultValue={article?.summary_en ?? ""} /></label>
          <label className={styles.wide}><span>Actualité en anglais</span><textarea name="body_en" maxLength={20000} rows={6} defaultValue={article?.body_en ?? ""} /></label>
          <label><span>Libellé anglais du lien</span><input name="link_label_en" maxLength={120} defaultValue={article?.link_label_en ?? ""} /></label>
        </div>
      </details>
    </div>
  );
}

export default async function AdminClientNewsPage({ searchParams = {} }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const [meResult, newsResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<AdminClientNewsOut[]>("/api/v1/admin/client-news", {}, token),
  ]);
  if (!meResult.ok) redirect("/login?error_code=session_expired");
  if (!newsResult.ok && newsResult.status === 403) redirect("/admin?error=Accès%20non%20autorisé");
  const articles = newsResult.ok ? newsResult.data : [];
  const error = param(searchParams, "error") || (!newsResult.ok ? newsResult.message : "");
  const ok = param(searchParams, "ok");

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div><h1>Actualités clients</h1><p>Publiez les informations importantes directement dans l’espace client.</p></div>
        <span className={styles.metric}>{articles.filter((article) => statusLabel(article) === "Publiée").length} publiée(s)</span>
      </section>
      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}
      <details className={styles.panel} open={articles.length === 0}>
        <summary><strong>Créer une actualité</strong></summary>
        <form action={createClientNewsAction} className={styles.form}>
          <NewsFields />
          <button type="submit">Créer l’actualité</button>
        </form>
      </details>
      <section className={styles.list}>
        {articles.map((article) => (
          <article className={styles.article} key={article.id}>
            <header><div><h2>{article.title_fr}</h2><p>{article.summary_fr || article.body_fr.slice(0, 180)}</p></div><span className={styles.badge}>{article.is_pinned ? "Épinglée · " : ""}{statusLabel(article)}</span></header>
            <p className={styles.meta}>Publication : {article.published_at ? new Date(article.published_at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" }) : "non publiée"}{article.expires_at ? ` · Expiration : ${new Date(article.expires_at).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}` : ""}</p>
            <details>
              <summary>Modifier</summary>
              <form action={updateClientNewsAction} className={styles.form}>
                <input type="hidden" name="article_id" value={article.id} />
                <NewsFields article={article} />
                <button type="submit">Enregistrer</button>
              </form>
              <form action={deleteClientNewsAction} className={styles.deleteForm}>
                <input type="hidden" name="article_id" value={article.id} />
                <button type="submit">Supprimer</button>
              </form>
            </details>
          </article>
        ))}
        {articles.length === 0 ? <p className={styles.panel}>Aucune actualité pour le moment.</p> : null}
      </section>
    </main>
  );
}
