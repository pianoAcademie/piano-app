import { redirect } from "next/navigation";

import { createClientNewsAction, deleteClientNewsAction, updateClientNewsAction } from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminClientNewsOut, ClientNewsAudienceCode, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";
import styles from "./client-news.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

const AUDIENCES: Array<{ code: ClientNewsAudienceCode; fr: string; en: string }> = [
  { code: "ALL_CLIENTS", fr: "Tous les clients", en: "All clients" },
  { code: "PARENTS_CHILD_5_12", fr: "Parents d’enfants de 5 à 12 ans", en: "Parents of children aged 5–12" },
  { code: "PARENTS_TEEN", fr: "Parents d’adolescents", en: "Parents of teenagers" },
  { code: "PARENTS_EARLY_MUSIC", fr: "Parents – éveil musical", en: "Parents – early music" },
  { code: "PARENTS_INITIATION", fr: "Parents – initiation", en: "Parents – initiation" },
  { code: "ADULT_STUDENTS", fr: "Élèves adultes", en: "Adult students" },
  { code: "CHILD_ONLINE_ONLY", fr: "Parents – enfants uniquement en ligne", en: "Parents – online-only children" },
  { code: "ADULT_ONLINE_ONLY", fr: "Adultes uniquement en ligne", en: "Online-only adults" },
  { code: "PROFESSORS", fr: "Professeurs uniquement", en: "Professors only" },
];

const NEWS_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    status_draft: "Brouillon",
    status_scheduled: "Planifiée",
    status_expired: "Expirée",
    status_published: "Publiée",
    title: "Actualités clients",
    subtitle: "Publiez les informations importantes directement dans l’espace client.",
    published_count: "publiée(s)",
    create_title: "Créer une actualité",
    create_submit: "Créer l’actualité",
    title_field: "Titre *",
    summary: "Résumé court",
    content: "Actualité *",
    status: "Statut",
    publish: "Publier",
    publication_paris: "Publication (heure de Paris)",
    optional_expiration: "Expiration facultative",
    pin_first: "Épingler en premier",
    optional_link: "Lien facultatif",
    link_label: "Libellé du lien",
    learn_more: "En savoir plus",
    optional_english: "Version anglaise facultative",
    english_title: "Titre anglais",
    english_summary: "Résumé anglais",
    english_content: "Actualité en anglais",
    english_link_label: "Libellé anglais du lien",
    pinned: "Épinglée",
    publication: "Publication",
    not_published: "non publiée",
    expiration: "Expiration",
    edit: "Modifier",
    save: "Enregistrer",
    delete: "Supprimer",
    empty: "Aucune actualité pour le moment.",
    access_denied: "Accès non autorisé",
    audience: "Public concerné *",
    audience_help: "Plusieurs catégories clients peuvent être sélectionnées. Une actualité n’est affichée qu’une fois par compte.",
  },
  en: {
    status_draft: "Draft",
    status_scheduled: "Scheduled",
    status_expired: "Expired",
    status_published: "Published",
    title: "Client news",
    subtitle: "Publish important updates directly in the client portal.",
    published_count: "published",
    create_title: "Create a news item",
    create_submit: "Create news item",
    title_field: "French title *",
    summary: "French short summary",
    content: "News content in French *",
    status: "Status",
    publish: "Publish",
    publication_paris: "Publication (Paris time)",
    optional_expiration: "Optional expiration",
    pin_first: "Pin to the top",
    optional_link: "Optional link",
    link_label: "Link label",
    learn_more: "Learn more",
    optional_english: "Optional English version",
    english_title: "English title",
    english_summary: "English summary",
    english_content: "News content in English",
    english_link_label: "English link label",
    pinned: "Pinned",
    publication: "Publication",
    not_published: "not published",
    expiration: "Expiration",
    edit: "Edit",
    save: "Save",
    delete: "Delete",
    empty: "No news items yet.",
    access_denied: "Access denied",
    audience: "Audience *",
    audience_help: "Several client categories may be selected. A news item is shown only once per account.",
  },
};

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

function statusLabel(article: AdminClientNewsOut, language: UiLanguage): string {
  const text = NEWS_TEXT[language];
  if (article.status === "DRAFT") return text.status_draft;
  if (article.published_at && new Date(article.published_at).getTime() > Date.now()) return text.status_scheduled;
  if (article.expires_at && new Date(article.expires_at).getTime() <= Date.now()) return text.status_expired;
  return text.status_published;
}

function NewsFields({ article, language }: { article?: AdminClientNewsOut; language: UiLanguage }): JSX.Element {
  const text = NEWS_TEXT[language];
  return (
    <div className={styles.formGrid}>
      <input type="hidden" name="ui_language" value={language} />
      <label className={styles.wide}><span>{text.title_field}</span><input name="title_fr" required maxLength={220} defaultValue={article?.title_fr ?? ""} /></label>
      <label className={styles.wide}><span>{text.summary}</span><textarea name="summary_fr" maxLength={500} rows={2} defaultValue={article?.summary_fr ?? ""} /></label>
      <label className={styles.wide}><span>{text.content}</span><textarea name="body_fr" required maxLength={20000} rows={7} defaultValue={article?.body_fr ?? ""} /></label>
      <label><span>{text.status}</span><select name="status" defaultValue={article?.status ?? "DRAFT"}><option value="DRAFT">{text.status_draft}</option><option value="PUBLISHED">{text.publish}</option></select></label>
      <label><span>{text.publication_paris}</span><input type="datetime-local" name="published_at_local" defaultValue={localDateTimeValue(article?.published_at ?? null)} /></label>
      <label><span>{text.optional_expiration}</span><input type="datetime-local" name="expires_at_local" defaultValue={localDateTimeValue(article?.expires_at ?? null)} /></label>
      <label className={styles.check}><input type="checkbox" name="is_pinned" defaultChecked={article?.is_pinned ?? false} /> {text.pin_first}</label>
      <fieldset className={`${styles.audiences} ${styles.wide}`}>
        <legend>{text.audience}</legend>
        <p>{text.audience_help}</p>
        <div className={styles.audienceGrid}>
          {AUDIENCES.map((audience) => (
            <label className={styles.check} key={audience.code}>
              <input
                type="checkbox"
                name="audience_codes"
                value={audience.code}
                defaultChecked={(article?.audience_codes ?? ["ALL_CLIENTS"]).includes(audience.code)}
              />
              {language === "en" ? audience.en : audience.fr}
            </label>
          ))}
        </div>
      </fieldset>
      <label className={styles.wide}><span>{text.optional_link}</span><input type="url" name="link_url" placeholder="https://..." defaultValue={article?.link_url ?? ""} /></label>
      <label><span>{text.link_label}</span><input name="link_label_fr" maxLength={120} placeholder={text.learn_more} defaultValue={article?.link_label_fr ?? ""} /></label>
      <details className={`${styles.translation} ${styles.wide}`}>
        <summary>{text.optional_english}</summary>
        <div className={styles.formGrid}>
          <label className={styles.wide}><span>{text.english_title}</span><input name="title_en" maxLength={220} defaultValue={article?.title_en ?? ""} /></label>
          <label className={styles.wide}><span>{text.english_summary}</span><textarea name="summary_en" maxLength={500} rows={2} defaultValue={article?.summary_en ?? ""} /></label>
          <label className={styles.wide}><span>{text.english_content}</span><textarea name="body_en" maxLength={20000} rows={6} defaultValue={article?.body_en ?? ""} /></label>
          <label><span>{text.english_link_label}</span><input name="link_label_en" maxLength={120} defaultValue={article?.link_label_en ?? ""} /></label>
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
  const language = normalizeUiLanguage(param(searchParams, "lang") || meResult.data.preferred_language);
  const text = NEWS_TEXT[language];
  const locale = localeForUiLanguage(language);
  if (!newsResult.ok && newsResult.status === 403) {
    redirect(`/admin?lang=${language}&error=${encodeURIComponent(text.access_denied)}`);
  }
  const articles = newsResult.ok ? newsResult.data : [];
  const error = param(searchParams, "error") || (!newsResult.ok ? newsResult.message : "");
  const ok = param(searchParams, "ok");

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div><h1>{text.title}</h1><p>{text.subtitle}</p></div>
        <span className={styles.metric}>{articles.filter((article) => statusLabel(article, language) === text.status_published).length} {text.published_count}</span>
      </section>
      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}
      <details className={styles.panel} open={articles.length === 0}>
        <summary><strong>{text.create_title}</strong></summary>
        <form action={createClientNewsAction} className={styles.form}>
          <NewsFields language={language} />
          <button type="submit">{text.create_submit}</button>
        </form>
      </details>
      <section className={styles.list}>
        {articles.map((article) => (
          <article className={styles.article} key={article.id}>
            <header><div><h2>{language === "en" ? article.title_en || article.title_fr : article.title_fr}</h2><p>{language === "en" ? article.summary_en || article.body_en?.slice(0, 180) || article.summary_fr || article.body_fr.slice(0, 180) : article.summary_fr || article.body_fr.slice(0, 180)}</p></div><span className={styles.badge}>{article.is_pinned ? `${text.pinned} · ` : ""}{statusLabel(article, language)}</span></header>
            <p className={styles.meta}>{text.publication} : {article.published_at ? new Date(article.published_at).toLocaleString(locale, { timeZone: "Europe/Paris" }) : text.not_published}{article.expires_at ? ` · ${text.expiration} : ${new Date(article.expires_at).toLocaleString(locale, { timeZone: "Europe/Paris" })}` : ""}</p>
            <p className={styles.meta}>{text.audience} : {(article.audience_codes ?? ["ALL_CLIENTS"]).map((code) => AUDIENCES.find((item) => item.code === code)?.[language] ?? code).join(" · ")}</p>
            <details>
              <summary>{text.edit}</summary>
              <form action={updateClientNewsAction} className={styles.form}>
                <input type="hidden" name="article_id" value={article.id} />
                <NewsFields article={article} language={language} />
                <button type="submit">{text.save}</button>
              </form>
              <form action={deleteClientNewsAction} className={styles.deleteForm}>
                <input type="hidden" name="article_id" value={article.id} />
                <input type="hidden" name="ui_language" value={language} />
                <button type="submit">{text.delete}</button>
              </form>
            </details>
          </article>
        ))}
        {articles.length === 0 ? <p className={styles.panel}>{text.empty}</p> : null}
      </section>
    </main>
  );
}
