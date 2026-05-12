import Link from "next/link";
import { redirect } from "next/navigation";

import {
  recomputeAdminReferralRewardAction,
  recomputeAllAdminReferralRewardsAction,
  validateAdminReferralRewardAction,
} from "../../../lib/actions";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { AdminReferralRewardOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

const STATUS_OPTIONS = ["", "NEEDS_REVIEW", "AWAITING_PAYMENT", "CREDIT_GRANTED", "CANCELLED"] as const;

const REFERRAL_TEXT: Record<UiLanguage, Record<string, string>> = {
  fr: {
    all: "Tous",
    status_needs_review: "A verifier",
    status_awaiting_payment: "En attente paiement",
    status_credit_granted: "Avoir genere",
    status_cancelled: "Annule",
    status_cancelled_plural: "Annules",
    status_declared: "Declare",
    category_online: "En ligne",
    category_home: "Domicile",
    candidate: "Candidat",
    title: "Parrainages",
    subtitle: "Suivi des recommandations Typeform, validations manuelles et avoirs generes.",
    recompute_all: "Tout recalculer",
    export_csv: "Exporter CSV",
    configure: "Configurer",
    status: "Statut",
    search: "Recherche",
    search_placeholder: "Nom, email, filleul, categorie...",
    filter: "Filtrer",
    clear: "Effacer",
    referrals: "Parrainage(s)",
    needs_review: "A verifier",
    awaiting: "En attente",
    credits_granted: "Avoirs generes",
    referrer: "Parrain",
    referred: "Filleul",
    category: "Categorie",
    cashing: "Encaissement",
    credit: "Avoir",
    email: "Email",
    links: "Liens",
    validate: "Valider",
    referred_family: "Famille filleule",
    not_linked: "Non rattache",
    on_amount: "sur {amount}",
    threshold: "Seuil: {amount} ({ratio})",
    progress: "Avancement: {ratio}",
    no_invoice: "Pas encore facture",
    announcement: "Annonce: {date}",
    credit_email: "Avoir: {date}",
    intake: "Intake",
    quote: "Devis",
    credit_created: "Avoir cree",
    recompute: "Recalculer",
    empty: "Aucun parrainage dans ce filtre.",
  },
  en: {
    all: "All",
    status_needs_review: "To review",
    status_awaiting_payment: "Awaiting payment",
    status_credit_granted: "Credit granted",
    status_cancelled: "Cancelled",
    status_cancelled_plural: "Cancelled",
    status_declared: "Declared",
    category_online: "Online",
    category_home: "Home",
    candidate: "Candidate",
    title: "Referrals",
    subtitle: "Track Typeform recommendations, manual validation, and generated credits.",
    recompute_all: "Recompute all",
    export_csv: "Export CSV",
    configure: "Configure",
    status: "Status",
    search: "Search",
    search_placeholder: "Name, email, referred family, category...",
    filter: "Filter",
    clear: "Clear",
    referrals: "Referral(s)",
    needs_review: "To review",
    awaiting: "Awaiting",
    credits_granted: "Credits granted",
    referrer: "Referrer",
    referred: "Referred",
    category: "Category",
    cashing: "Cashing",
    credit: "Credit",
    email: "Email",
    links: "Links",
    validate: "Validate",
    referred_family: "Referred family",
    not_linked: "Not linked",
    on_amount: "of {amount}",
    threshold: "Threshold: {amount} ({ratio})",
    progress: "Progress: {ratio}",
    no_invoice: "Not invoiced yet",
    announcement: "Recorded: {date}",
    credit_email: "Credit: {date}",
    intake: "Intake",
    quote: "Quote",
    credit_created: "Credit created",
    recompute: "Recompute",
    empty: "No referrals for this filter.",
  },
};

function rt(language: UiLanguage, key: string, values?: Record<string, string | number>): string {
  const template = REFERRAL_TEXT[language][key] || REFERRAL_TEXT.fr[key] || key;
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, token) => String(values[token] ?? ""));
}

function readParam(params: SearchParams | undefined, key: string): string {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "currency",
    currency: currency || "EUR",
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatDate(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language));
}

function formatPercent(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const ratio = Number(value);
  if (!Number.isFinite(ratio)) {
    return "-";
  }
  return new Intl.NumberFormat(localeForUiLanguage(language), {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(ratio);
}

function statusLabel(value: string, language: UiLanguage): string {
  if (value === "NEEDS_REVIEW") return rt(language, "status_needs_review");
  if (value === "AWAITING_PAYMENT") return rt(language, "status_awaiting_payment");
  if (value === "CREDIT_GRANTED") return rt(language, "status_credit_granted");
  if (value === "CANCELLED") return rt(language, "status_cancelled");
  if (value === "DECLARED") return rt(language, "status_declared");
  return value;
}

function statusClass(value: string): string {
  if (value === "CREDIT_GRANTED") return "status-ok";
  if (value === "AWAITING_PAYMENT") return "status-info";
  if (value === "NEEDS_REVIEW" || value === "DECLARED") return "status-warn";
  return "status-off";
}

function categoryLabel(value: string | null, language: UiLanguage): string {
  if (value === "PARIS") return "Paris";
  if (value === "BAR_LE_DUC") return "Bar-le-Duc";
  if (value === "ONLINE") return rt(language, "category_online");
  if (value === "DOMICILE") return rt(language, "category_home");
  return value || "-";
}

function referralCounters(rows: AdminReferralRewardOut[]): Record<string, number> {
  return rows.reduce<Record<string, number>>((acc, row) => {
    acc[row.status] = (acc[row.status] || 0) + 1;
    return acc;
  }, {});
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function candidateLabel(candidate: Record<string, unknown>, language: UiLanguage = "fr"): string {
  const name = String(candidate.display_name ?? "").trim();
  const email = String(candidate.email ?? "").trim();
  const confidence = Number(candidate.confidence ?? 0);
  const suffix = Number.isFinite(confidence) && confidence > 0 ? ` (${confidence}%)` : "";
  return `${name || email || rt(language, "candidate")}${suffix}`;
}

function candidateUserId(candidate: Record<string, unknown>): string {
  return String(candidate.user_id ?? "").trim();
}

function rowMatchesQuery(row: AdminReferralRewardOut, query: string): boolean {
  if (!query) {
    return true;
  }
  const candidateText = row.match_candidates.map((candidate) => candidateLabel(candidate)).join(" ");
  const haystack = normalizeSearch([
    row.declared_referrer_text,
    row.referrer_name ?? "",
    row.referrer_email ?? "",
    row.referred_client_name ?? "",
    row.referred_student_name ?? "",
    row.category ?? "",
    row.status,
    row.match_status,
    row.reward_amount,
    row.invoice_total ?? "",
    row.paid_total ?? "",
    row.threshold_amount ?? "",
    candidateText,
  ].join(" "));
  return haystack.includes(query);
}

export default async function AdminReferralsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const status = readParam(searchParams, "status").trim().toUpperCase();
  const searchText = readParam(searchParams, "q").trim();
  const searchQuery = normalizeSearch(searchText);
  const referralsResult = await backendRequest<AdminReferralRewardOut[]>(
    "/api/v1/admin/clients/referrals/rewards",
    {},
    token,
  );
  const allReferrals = referralsResult.ok ? referralsResult.data : [];
  const operationalReferrals = status === "CANCELLED" ? allReferrals : allReferrals.filter((row) => row.status !== "CANCELLED");
  const referrals = operationalReferrals.filter((row) => (!status || row.status === status) && rowMatchesQuery(row, searchQuery));
  const counters = referralCounters(operationalReferrals);
  const totalAmount = operationalReferrals
    .filter((row) => row.status === "CREDIT_GRANTED")
    .reduce((sum, row) => sum + (Number(row.reward_amount) || 0), 0);
  const errorMessage = referralsResult.ok ? "" : referralsResult.message;
  const exportParams = new URLSearchParams();
  exportParams.set("lang", language);
  if (status) {
    exportParams.set("status", status);
  }
  if (searchText) {
    exportParams.set("q", searchText);
  }
  const returnHref = `/admin/referrals${exportParams.toString() ? `?${exportParams.toString()}` : ""}`;
  const exportHref = `/admin/referrals/export${exportParams.toString() ? `?${exportParams.toString()}` : ""}`;

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{rt(language, "title")}</h2>
            <p className="muted">{rt(language, "subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <form action={recomputeAllAdminReferralRewardsAction}>
              <input type="hidden" name="return_to" value={returnHref} />
              <button className="ghost" type="submit">{rt(language, "recompute_all")}</button>
            </form>
            <Link className="ghost" href={exportHref}>{rt(language, "export_csv")}</Link>
            <Link className="ghost" href="/admin/config?section=params-referrals">{rt(language, "configure")}</Link>
          </div>
        </div>
        <form className="row wrap gap-sm top-gap-sm" action="/admin/referrals">
          <label>
            {rt(language, "status")}
            <select name="status" defaultValue={status}>
              {STATUS_OPTIONS.map((item) => (
                <option key={item || "ALL"} value={item}>
                  {item === "" ? rt(language, "all") : item === "CANCELLED" ? rt(language, "status_cancelled_plural") : statusLabel(item, language)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {rt(language, "search")}
            <input name="q" placeholder={rt(language, "search_placeholder")} defaultValue={searchText} />
          </label>
          <button type="submit">{rt(language, "filter")}</button>
          {status || searchText ? <Link className="ghost" href="/admin/referrals">{rt(language, "clear")}</Link> : null}
        </form>
      </section>

      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="grid cols-4 span-2">
        <article className="card">
          <strong>{operationalReferrals.length}</strong>
          <span className="muted">{rt(language, "referrals")}</span>
        </article>
        <article className="card">
          <strong>{counters.NEEDS_REVIEW || 0}</strong>
          <span className="muted">{rt(language, "needs_review")}</span>
        </article>
        <article className="card">
          <strong>{counters.AWAITING_PAYMENT || 0}</strong>
          <span className="muted">{rt(language, "awaiting")}</span>
        </article>
        <article className="card">
          <strong>{formatMoney(String(totalAmount), "EUR", language)}</strong>
          <span className="muted">{rt(language, "credits_granted")}</span>
        </article>
      </section>

      <section className="card span-2">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{rt(language, "status")}</th>
                <th>{rt(language, "referrer")}</th>
                <th>{rt(language, "referred")}</th>
                <th>{rt(language, "category")}</th>
                <th>{rt(language, "cashing")}</th>
                <th>{rt(language, "credit")}</th>
                <th>{rt(language, "email")}</th>
                <th>{rt(language, "links")}</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status, language)}</span>
                    <small className="muted">{row.match_status} {row.match_confidence ? `(${row.match_confidence}%)` : ""}</small>
                  </td>
                  <td>
                    {row.referrer_user_id ? (
                      <Link className="mode-link" href={`/admin/clients/${row.referrer_user_id}?tab=paiements`}>
                        {row.referrer_name || row.declared_referrer_text}
                      </Link>
                    ) : (
                      <span>{row.declared_referrer_text}</span>
                    )}
                    {row.referrer_email ? <small className="muted">{row.referrer_email}</small> : null}
                    {!row.referrer_user_id && row.match_candidates.length > 0 ? (
                      <form action={validateAdminReferralRewardAction} className="row wrap gap-sm top-gap-sm">
                        <input type="hidden" name="reward_id" value={row.id} />
                        <input type="hidden" name="return_to" value={returnHref} />
                        <select name="referrer_user_id" defaultValue={candidateUserId(row.match_candidates[0])}>
                          {row.match_candidates
                            .filter((candidate) => candidateUserId(candidate))
                            .slice(0, 5)
                            .map((candidate) => (
                              <option key={candidateUserId(candidate)} value={candidateUserId(candidate)}>
                                {candidateLabel(candidate, language)}
                              </option>
                            ))}
                        </select>
                        <button type="submit">{rt(language, "validate")}</button>
                      </form>
                    ) : null}
                  </td>
                  <td>
                    {row.referred_client_id ? (
                      <Link className="mode-link" href={`/admin/clients/${row.referred_client_id}`}>
                        {row.referred_client_name || rt(language, "referred_family")}
                      </Link>
                    ) : row.referred_prospect_name ? (
                      <span>{row.referred_prospect_name}</span>
                    ) : (
                      <span className="muted">{rt(language, "not_linked")}</span>
                    )}
                    {row.referred_student_name ? <small className="muted">{row.referred_student_name}</small> : null}
                  </td>
                  <td>{categoryLabel(row.category, language)}</td>
                  <td>
                    {row.invoice_total ? (
                      <>
                        <strong>{formatMoney(row.paid_total ?? "0", row.currency, language)}</strong>
                        <small className="muted">{rt(language, "on_amount", { amount: formatMoney(row.invoice_total, row.currency, language) })}</small>
                        <small className="muted">{rt(language, "threshold", { amount: formatMoney(row.threshold_amount ?? "0", row.currency, language), ratio: formatPercent(row.trigger_ratio, language) })}</small>
                        <small className="muted">{rt(language, "progress", { ratio: formatPercent(row.payment_progress_ratio, language) })}</small>
                      </>
                    ) : (
                      <span className="muted">{rt(language, "no_invoice")}</span>
                    )}
                  </td>
                  <td>{formatMoney(row.reward_amount, row.currency, language)}</td>
                  <td>
                    <small className="muted">{rt(language, "announcement", { date: formatDate(row.announcement_email_sent_at, language) })}</small>
                    <small className="muted">{rt(language, "credit_email", { date: formatDate(row.credit_email_sent_at, language) })}</small>
                  </td>
                  <td>
                    <div className="row wrap gap-sm">
                      {row.typeform_intake_id ? <Link className="mode-link" href={`/admin/intakes/${row.typeform_intake_id}`}>{rt(language, "intake")}</Link> : null}
                      {row.quote_id ? <Link className="mode-link" href={`/admin/quotes/${row.quote_id}`}>{rt(language, "quote")}</Link> : null}
                      {row.credit_transaction_id ? <span className="status-pill status-ok">{rt(language, "credit_created")}</span> : null}
                      {row.status !== "CREDIT_GRANTED" ? (
                        <form action={recomputeAdminReferralRewardAction}>
                          <input type="hidden" name="reward_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnHref} />
                          <button className="ghost" type="submit">{rt(language, "recompute")}</button>
                        </form>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {referrals.length === 0 ? (
                <tr>
                  <td colSpan={8}><p className="muted">{rt(language, "empty")}</p></td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
