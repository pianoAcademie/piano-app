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

const STATUS_OPTIONS = [
  { value: "", label: "Tous" },
  { value: "NEEDS_REVIEW", label: "A verifier" },
  { value: "AWAITING_PAYMENT", label: "En attente paiement" },
  { value: "CREDIT_GRANTED", label: "Avoir genere" },
  { value: "CANCELLED", label: "Annules" },
] as const;

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

function statusLabel(value: string): string {
  if (value === "NEEDS_REVIEW") return "A verifier";
  if (value === "AWAITING_PAYMENT") return "En attente paiement";
  if (value === "CREDIT_GRANTED") return "Avoir genere";
  if (value === "CANCELLED") return "Annule";
  if (value === "DECLARED") return "Declare";
  return value;
}

function statusClass(value: string): string {
  if (value === "CREDIT_GRANTED") return "status-ok";
  if (value === "AWAITING_PAYMENT") return "status-info";
  if (value === "NEEDS_REVIEW" || value === "DECLARED") return "status-warn";
  return "status-off";
}

function categoryLabel(value: string | null): string {
  if (value === "PARIS") return "Paris";
  if (value === "BAR_LE_DUC") return "Bar-le-Duc";
  if (value === "ONLINE") return "En ligne";
  if (value === "DOMICILE") return "Domicile";
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

function candidateLabel(candidate: Record<string, unknown>): string {
  const name = String(candidate.display_name ?? "").trim();
  const email = String(candidate.email ?? "").trim();
  const confidence = Number(candidate.confidence ?? 0);
  const suffix = Number.isFinite(confidence) && confidence > 0 ? ` (${confidence}%)` : "";
  return `${name || email || "Candidat"}${suffix}`;
}

function candidateUserId(candidate: Record<string, unknown>): string {
  return String(candidate.user_id ?? "").trim();
}

function rowMatchesQuery(row: AdminReferralRewardOut, query: string): boolean {
  if (!query) {
    return true;
  }
  const candidateText = row.match_candidates.map(candidateLabel).join(" ");
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
  const referrals = allReferrals.filter((row) => (!status || row.status === status) && rowMatchesQuery(row, searchQuery));
  const counters = referralCounters(allReferrals);
  const totalAmount = allReferrals
    .filter((row) => row.status === "CREDIT_GRANTED")
    .reduce((sum, row) => sum + (Number(row.reward_amount) || 0), 0);
  const errorMessage = referralsResult.ok ? "" : referralsResult.message;
  const exportParams = new URLSearchParams();
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
            <h2>Parrainages</h2>
            <p className="muted">Suivi des recommandations Typeform, validations manuelles et avoirs generes.</p>
          </div>
          <div className="row wrap gap-sm">
            <form action={recomputeAllAdminReferralRewardsAction}>
              <input type="hidden" name="return_to" value={returnHref} />
              <button className="ghost" type="submit">Tout recalculer</button>
            </form>
            <Link className="ghost" href={exportHref}>Exporter CSV</Link>
            <Link className="ghost" href="/admin/config?section=params-referrals">Configurer</Link>
          </div>
        </div>
        <form className="row wrap gap-sm top-gap-sm" action="/admin/referrals">
          <label>
            Statut
            <select name="status" defaultValue={status}>
              {STATUS_OPTIONS.map((item) => (
                <option key={item.value || "ALL"} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label>
            Recherche
            <input name="q" placeholder="Nom, email, filleul, categorie..." defaultValue={searchText} />
          </label>
          <button type="submit">Filtrer</button>
          {status || searchText ? <Link className="ghost" href="/admin/referrals">Effacer</Link> : null}
        </form>
      </section>

      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="grid cols-4 span-2">
        <article className="card">
          <strong>{allReferrals.length}</strong>
          <span className="muted">Parrainage(s)</span>
        </article>
        <article className="card">
          <strong>{counters.NEEDS_REVIEW || 0}</strong>
          <span className="muted">A verifier</span>
        </article>
        <article className="card">
          <strong>{counters.AWAITING_PAYMENT || 0}</strong>
          <span className="muted">En attente</span>
        </article>
        <article className="card">
          <strong>{formatMoney(String(totalAmount), "EUR", language)}</strong>
          <span className="muted">Avoirs generes</span>
        </article>
      </section>

      <section className="card span-2">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Statut</th>
                <th>Parrain</th>
                <th>Filleul</th>
                <th>Categorie</th>
                <th>Encaissement</th>
                <th>Avoir</th>
                <th>Email</th>
                <th>Liens</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span className={`status-pill ${statusClass(row.status)}`}>{statusLabel(row.status)}</span>
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
                                {candidateLabel(candidate)}
                              </option>
                            ))}
                        </select>
                        <button type="submit">Valider</button>
                      </form>
                    ) : null}
                  </td>
                  <td>
                    {row.referred_client_id ? (
                      <Link className="mode-link" href={`/admin/clients/${row.referred_client_id}`}>
                        {row.referred_client_name || "Famille filleule"}
                      </Link>
                    ) : (
                      <span className="muted">Non rattache</span>
                    )}
                    {row.referred_student_name ? <small className="muted">{row.referred_student_name}</small> : null}
                  </td>
                  <td>{categoryLabel(row.category)}</td>
                  <td>
                    {row.invoice_total ? (
                      <>
                        <strong>{formatMoney(row.paid_total ?? "0", row.currency, language)}</strong>
                        <small className="muted">sur {formatMoney(row.invoice_total, row.currency, language)}</small>
                        <small className="muted">Seuil: {formatMoney(row.threshold_amount ?? "0", row.currency, language)} ({formatPercent(row.trigger_ratio, language)})</small>
                        <small className="muted">Avancement: {formatPercent(row.payment_progress_ratio, language)}</small>
                      </>
                    ) : (
                      <span className="muted">Pas encore facture</span>
                    )}
                  </td>
                  <td>{formatMoney(row.reward_amount, row.currency, language)}</td>
                  <td>
                    <small className="muted">Annonce: {formatDate(row.announcement_email_sent_at, language)}</small>
                    <small className="muted">Avoir: {formatDate(row.credit_email_sent_at, language)}</small>
                  </td>
                  <td>
                    <div className="row wrap gap-sm">
                      {row.typeform_intake_id ? <Link className="mode-link" href={`/admin/intakes/${row.typeform_intake_id}`}>Intake</Link> : null}
                      {row.quote_id ? <Link className="mode-link" href={`/admin/quotes/${row.quote_id}`}>Devis</Link> : null}
                      {row.credit_transaction_id ? <span className="status-pill status-ok">Avoir cree</span> : null}
                      {row.status !== "CREDIT_GRANTED" ? (
                        <form action={recomputeAdminReferralRewardAction}>
                          <input type="hidden" name="reward_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnHref} />
                          <button className="ghost" type="submit">Recalculer</button>
                        </form>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {referrals.length === 0 ? (
                <tr>
                  <td colSpan={8}><p className="muted">Aucun parrainage dans ce filtre.</p></td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
