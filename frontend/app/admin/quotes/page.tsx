import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../components/copy-link-button";
import { duplicateQuoteAction, sendQuoteAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import type { AdminActivityOut, AdminClientOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  meta: Record<string, unknown>;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  public_token: string | null;
  pdf_token: string | null;
  context_type: string;
  currency: string;
  total_ttc: string;
  created_at: string;
  expires_at: string | null;
  quote_type: string;
  prospect_id: string | null;
  client_id: string | null;
  school_year_label: string | null;
  estimated_solfege_level: string | null;
  calendar_snapshot: Record<string, unknown>;
  cgv_snapshot: Record<string, unknown>;
  meta: Record<string, unknown>;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: currency || "EUR" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function quoteStatusClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "approved") return "status-ok";
  if (normalized === "sent" || normalized === "change_requested") return "status-warn";
  if (normalized === "rejected" || normalized === "expired" || normalized === "cancelled") return "status-cancelled";
  return "status-off";
}

function labelForContext(contextType: string): string {
  return contextType === "active_client" ? "Client actif" : "Acquisition";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function getCalendarSessionsCount(snapshot: Record<string, unknown>): number {
  const raw = snapshot.sessions;
  if (!Array.isArray(raw)) {
    return 0;
  }
  return raw.length;
}

function parseIsoDateOnly(raw: string): Date | null {
  const value = raw.trim();
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function parseDecimal(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function languageLabel(meta: Record<string, unknown>): string {
  const language = typeof meta.language === "string" ? meta.language.trim().toLowerCase() : "";
  return language || "fr";
}

function templateLabel(meta: Record<string, unknown>): string {
  const options = [meta.template_name, meta.template_code, meta.template_id];
  for (const candidate of options) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return "-";
}

function cgvLabel(snapshot: Record<string, unknown>): string {
  const label = snapshot.version_label;
  if (typeof label === "string" && label.trim()) {
    return label.trim();
  }
  return "-";
}

function prospectTypeLabelFromMeta(meta: Record<string, unknown>): "adult" | "child" | "-" {
  const value = typeof meta.prospect_type === "string" ? meta.prospect_type.trim().toLowerCase() : "";
  if (value === "adult" || value === "child") {
    return value;
  }
  return "-";
}

function prospectTypeLabelFromClient(client: AdminClientOut | undefined): "adult" | "child" | "-" {
  if (!client) {
    return "-";
  }
  const value = String(client.client_kind || "").trim().toUpperCase();
  if (value === "ADULT") {
    return "adult";
  }
  if (value === "CHILD") {
    return "child";
  }
  return "-";
}

function buildQuotesListHref(params: {
  status: string;
  contextType: string;
  activityId: string;
  q: string;
  prospectType: string;
  currency: string;
  quoteType: string;
  schoolYear: string;
  language: string;
  template: string;
  cgv: string;
  hasSolfege: string;
  minTotal: string;
  maxTotal: string;
  createdFrom: string;
  createdTo: string;
  expiresFrom: string;
  expiresTo: string;
}): string {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.contextType) sp.set("context_type", params.contextType);
  if (params.activityId) sp.set("activity_id", params.activityId);
  if (params.q) sp.set("q", params.q);
  if (params.prospectType) sp.set("prospect_type", params.prospectType);
  if (params.currency) sp.set("currency", params.currency);
  if (params.quoteType) sp.set("quote_type", params.quoteType);
  if (params.schoolYear) sp.set("school_year", params.schoolYear);
  if (params.language) sp.set("language", params.language);
  if (params.template) sp.set("template", params.template);
  if (params.cgv) sp.set("cgv", params.cgv);
  if (params.hasSolfege) sp.set("has_solfege", params.hasSolfege);
  if (params.minTotal) sp.set("min_total", params.minTotal);
  if (params.maxTotal) sp.set("max_total", params.maxTotal);
  if (params.createdFrom) sp.set("created_from", params.createdFrom);
  if (params.createdTo) sp.set("created_to", params.createdTo);
  if (params.expiresFrom) sp.set("expires_from", params.expiresFrom);
  if (params.expiresTo) sp.set("expires_to", params.expiresTo);
  const value = sp.toString();
  return value ? `/admin/quotes?${value}` : "/admin/quotes";
}

export default async function AdminQuotesPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const statusFilter = readParam(searchParams, "status");
  const contextFilter = readParam(searchParams, "context_type");
  const activityFilter = readParam(searchParams, "activity_id");
  const query = readParam(searchParams, "q");
  const prospectTypeFilter = readParam(searchParams, "prospect_type").trim().toLowerCase();
  const currencyFilter = readParam(searchParams, "currency").trim().toUpperCase();
  const quoteTypeFilter = readParam(searchParams, "quote_type").trim().toLowerCase();
  const schoolYearFilter = readParam(searchParams, "school_year").trim().toLowerCase();
  const languageFilter = readParam(searchParams, "language").trim().toLowerCase();
  const templateFilter = readParam(searchParams, "template").trim().toLowerCase();
  const cgvFilter = readParam(searchParams, "cgv").trim().toLowerCase();
  const hasSolfegeFilter = readParam(searchParams, "has_solfege").trim().toLowerCase();
  const minTotalFilterRaw = readParam(searchParams, "min_total");
  const maxTotalFilterRaw = readParam(searchParams, "max_total");
  const createdFromFilterRaw = readParam(searchParams, "created_from");
  const createdToFilterRaw = readParam(searchParams, "created_to");
  const expiresFromFilterRaw = readParam(searchParams, "expires_from");
  const expiresToFilterRaw = readParam(searchParams, "expires_to");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const minTotalFilter = parseDecimal(minTotalFilterRaw);
  const maxTotalFilter = parseDecimal(maxTotalFilterRaw);
  const createdFromFilter = parseIsoDateOnly(createdFromFilterRaw);
  const createdToFilter = parseIsoDateOnly(createdToFilterRaw);
  const expiresFromFilter = parseIsoDateOnly(expiresFromFilterRaw);
  const expiresToFilter = parseIsoDateOnly(expiresToFilterRaw);

  const listQuery = new URLSearchParams();
  if (statusFilter) listQuery.set("status", statusFilter);
  if (contextFilter) listQuery.set("context_type", contextFilter);
  if (activityFilter) listQuery.set("activity_id", activityFilter);
  listQuery.set("limit", "1000");

  const [prospectsResult, clientsResult, activitiesResult, quotesResult] = await Promise.all([
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<QuoteOut[]>(`/api/v1/quotes?${listQuery.toString()}`, {}, token),
  ]);

  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const quotes = quotesResult.ok ? quotesResult.data : [];

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));

  const filteredQuotes = quotes.filter((row) => {
    const owner = row.context_type === "acquisition"
      ? prospectById.get(row.prospect_id || "")
      : clientById.get(row.client_id || "");

    const ownerName = owner ? displayName(owner.first_name, owner.last_name, owner.email) : "";
    const ownerPhone = owner
      ? [
          String(owner.phone || ""),
          "mobile_phone_1" in owner ? String(owner.mobile_phone_1 || "") : "",
          "mobile_phone_2" in owner ? String(owner.mobile_phone_2 || "") : "",
        ]
          .join(" ")
          .trim()
      : "";

    const textHaystack = [row.quote_number, ownerName, owner?.email || "", ownerPhone]
      .join(" ")
      .toLowerCase();
    if (query && !textHaystack.includes(query.trim().toLowerCase())) {
      return false;
    }

    const rowProspectType = row.context_type === "acquisition"
      ? prospectTypeLabelFromMeta((owner as ProspectOut | undefined)?.meta || {})
      : prospectTypeLabelFromClient(owner as AdminClientOut | undefined);
    if (prospectTypeFilter && rowProspectType !== prospectTypeFilter) {
      return false;
    }

    if (currencyFilter && (row.currency || "").toUpperCase() !== currencyFilter) {
      return false;
    }

    if (quoteTypeFilter && (row.quote_type || "").trim().toLowerCase() !== quoteTypeFilter) {
      return false;
    }

    if (schoolYearFilter && !(row.school_year_label || "").trim().toLowerCase().includes(schoolYearFilter)) {
      return false;
    }

    const rowLanguage = languageLabel(row.meta || {});
    if (languageFilter && rowLanguage !== languageFilter) {
      return false;
    }

    const rowTemplate = templateLabel(row.meta || {}).toLowerCase();
    if (templateFilter && !rowTemplate.includes(templateFilter)) {
      return false;
    }

    const rowCgv = cgvLabel(row.cgv_snapshot || {}).toLowerCase();
    if (cgvFilter && !rowCgv.includes(cgvFilter)) {
      return false;
    }

    const rowHasSolfege = Boolean((row.estimated_solfege_level || "").trim());
    if (hasSolfegeFilter === "yes" && !rowHasSolfege) {
      return false;
    }
    if (hasSolfegeFilter === "no" && rowHasSolfege) {
      return false;
    }

    const total = Number(row.total_ttc);
    if (minTotalFilter !== null && Number.isFinite(total) && total < minTotalFilter) {
      return false;
    }
    if (maxTotalFilter !== null && Number.isFinite(total) && total > maxTotalFilter) {
      return false;
    }

    const createdAt = new Date(row.created_at);
    if (createdFromFilter && (!Number.isFinite(createdAt.getTime()) || createdAt < createdFromFilter)) {
      return false;
    }
    if (createdToFilter) {
      const createdToLimit = new Date(createdToFilter.getTime() + 24 * 60 * 60 * 1000);
      if (!Number.isFinite(createdAt.getTime()) || createdAt >= createdToLimit) {
        return false;
      }
    }

    if (expiresFromFilter || expiresToFilter) {
      if (!row.expires_at) {
        return false;
      }
      const expiresAt = new Date(row.expires_at);
      if (expiresFromFilter && (!Number.isFinite(expiresAt.getTime()) || expiresAt < expiresFromFilter)) {
        return false;
      }
      if (expiresToFilter) {
        const expiresToLimit = new Date(expiresToFilter.getTime() + 24 * 60 * 60 * 1000);
        if (!Number.isFinite(expiresAt.getTime()) || expiresAt >= expiresToLimit) {
          return false;
        }
      }
    }

    return true;
  });

  const currentListHref = buildQuotesListHref({
    status: statusFilter,
    contextType: contextFilter,
    activityId: activityFilter,
    q: query,
    prospectType: prospectTypeFilter,
    currency: currencyFilter,
    quoteType: quoteTypeFilter,
    schoolYear: schoolYearFilter,
    language: languageFilter,
    template: templateFilter,
    cgv: cgvFilter,
    hasSolfege: hasSolfegeFilter,
    minTotal: minTotalFilterRaw,
    maxTotal: maxTotalFilterRaw,
    createdFrom: createdFromFilterRaw,
    createdTo: createdToFilterRaw,
    expiresFrom: expiresFromFilterRaw,
    expiresTo: expiresToFilterRaw,
  });

  const currencyValues = Array.from(new Set(quotes.map((row) => (row.currency || "").toUpperCase()).filter(Boolean))).sort();
  const quoteTypeValues = Array.from(new Set(quotes.map((row) => (row.quote_type || "").trim()).filter(Boolean))).sort();
  const frontendBase = process.env.NEXT_PUBLIC_FRONTEND_URL ?? "http://localhost:3000";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Devis</h2>
            <p className="muted">Retrouvez, filtrez et ouvrez les devis sans melanger la creation ni les prospects.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/prospects">
              Voir prospects
            </Link>
            <Link className="ghost" href="/admin/config/quotes">
              Configurer devis
            </Link>
            <Link className="mode-link" href="/admin/quotes/new">
              Nouveau devis
            </Link>
          </div>
        </div>
      </section>

      {!quotesResult.ok ? <section className="flash-err">Erreur devis: {quotesResult.message}</section> : null}
      {!activitiesResult.ok ? <section className="flash-err">Erreur activites: {activitiesResult.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <h3>Liste des devis</h3>
        <form method="get" className="grid cols-4 sticky-filters top-gap-sm">
          <label>
            Statut
            <select name="status" defaultValue={statusFilter}>
              <option value="">Tous</option>
              <option value="created">Brouillon</option>
              <option value="sent">Envoye</option>
              <option value="change_requested">Demande modif</option>
              <option value="approved">Accepte</option>
              <option value="rejected">Refuse</option>
              <option value="expired">Expire</option>
              <option value="cancelled">Annule</option>
            </select>
          </label>
          <label>
            Contexte
            <select name="context_type" defaultValue={contextFilter}>
              <option value="">Tous</option>
              <option value="acquisition">Acquisition</option>
              <option value="active_client">Client actif</option>
            </select>
          </label>
          <label>
            Activite specifique
            <select name="activity_id" defaultValue={activityFilter}>
              <option value="">Toutes</option>
              {activities.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Type prospect
            <select name="prospect_type" defaultValue={prospectTypeFilter}>
              <option value="">Tous</option>
              <option value="adult">Adulte</option>
              <option value="child">Enfant</option>
            </select>
          </label>
          <label>
            Avec solfege
            <select name="has_solfege" defaultValue={hasSolfegeFilter}>
              <option value="">Tous</option>
              <option value="yes">Oui</option>
              <option value="no">Non</option>
            </select>
          </label>

          <label className="cols-span-2">
            Recherche (numero, prospect, email, telephone)
            <input type="text" name="q" defaultValue={query} placeholder="DV-..., nom, email..." />
          </label>
          <label>
            Devise
            <select name="currency" defaultValue={currencyFilter}>
              <option value="">Toutes</option>
              {currencyValues.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Type devis
            <select name="quote_type" defaultValue={quoteTypeFilter}>
              <option value="">Tous</option>
              {quoteTypeValues.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>

          <label>
            Annee scolaire
            <input type="text" name="school_year" defaultValue={schoolYearFilter} placeholder="2026-2027" />
          </label>
          <label>
            Langue
            <input type="text" name="language" defaultValue={languageFilter} placeholder="fr" />
          </label>
          <label>
            Template
            <input type="text" name="template" defaultValue={templateFilter} placeholder="template code" />
          </label>
          <label>
            CGV
            <input type="text" name="cgv" defaultValue={cgvFilter} placeholder="CGV 2026" />
          </label>

          <label>
            Total min TTC
            <input type="number" name="min_total" min={0} step="0.01" defaultValue={minTotalFilterRaw} />
          </label>
          <label>
            Total max TTC
            <input type="number" name="max_total" min={0} step="0.01" defaultValue={maxTotalFilterRaw} />
          </label>
          <label>
            Cree du
            <input type="date" name="created_from" defaultValue={createdFromFilterRaw} />
          </label>
          <label>
            Cree au
            <input type="date" name="created_to" defaultValue={createdToFilterRaw} />
          </label>
          <label>
            Expire du
            <input type="date" name="expires_from" defaultValue={expiresFromFilterRaw} />
          </label>
          <label>
            Expire au
            <input type="date" name="expires_to" defaultValue={expiresToFilterRaw} />
          </label>

          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">Filtrer</button>
            <a className="ghost" href="/admin/quotes">Reset</a>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Numero</th>
                <th>Prospect / client</th>
                <th>Type prospect</th>
                <th>Contexte</th>
                <th>Total TTC</th>
                <th>Langue</th>
                <th>Template</th>
                <th>CGV</th>
                <th>Statut</th>
                <th>Creation</th>
                <th>Expiration</th>
                <th>Activites</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredQuotes.length === 0 ? (
                <tr>
                  <td colSpan={13}><p className="muted">Aucun devis sur ces filtres.</p></td>
                </tr>
              ) : (
                filteredQuotes.map((row) => {
                  const owner = row.context_type === "acquisition"
                    ? prospectById.get(row.prospect_id || "")
                    : clientById.get(row.client_id || "");
                  const ownerName = owner
                    ? displayName(owner.first_name, owner.last_name, owner.email)
                    : "-";
                  const ownerEmail = owner?.email ?? "";

                  const rowProspectType = row.context_type === "acquisition"
                    ? prospectTypeLabelFromMeta((owner as ProspectOut | undefined)?.meta || {})
                    : prospectTypeLabelFromClient(owner as AdminClientOut | undefined);
                  const detailHref = `/admin/quotes/${row.id}?back=${encodeURIComponent(currentListHref)}`;
                  const publicHref = row.public_token ? `/q/${row.id}?t=${encodeURIComponent(row.public_token)}` : "";
                  const publicAbsoluteHref = row.public_token ? `${frontendBase}/q/${row.id}?t=${row.public_token}` : "";

                  return (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.quote_number}</strong>
                        <br />
                        <small className="muted">{row.quote_type}</small>
                      </td>
                      <td>
                        <strong>{ownerName}</strong>
                        <br />
                        <small className="muted">{owner?.email ?? "-"}</small>
                      </td>
                      <td>{rowProspectType === "-" ? "-" : rowProspectType === "adult" ? "Adulte" : "Enfant"}</td>
                      <td>{labelForContext(row.context_type)}</td>
                      <td>{formatAmount(row.total_ttc, row.currency)}</td>
                      <td>{languageLabel(row.meta || {}).toUpperCase()}</td>
                      <td>{templateLabel(row.meta || {})}</td>
                      <td>{cgvLabel(row.cgv_snapshot || {})}</td>
                      <td><span className={`status-pill ${quoteStatusClass(row.status)}`}>{row.status}</span></td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>{formatDate(row.expires_at)}</td>
                      <td>{getCalendarSessionsCount(row.calendar_snapshot)}</td>
                      <td>
                        <div className="row wrap gap-xs">
                          <Link className="ghost" href={detailHref}>{row.status === "created" ? "Modifier" : "Ouvrir"}</Link>
                          {row.status === "created" ? (
                            <form action={sendQuoteAction}>
                              <input type="hidden" name="quote_id" value={row.id} />
                              <input type="hidden" name="return_to" value={currentListHref} />
                              <input type="hidden" name="recipient_email" value={ownerEmail} />
                              <button type="submit" className="ghost">Envoyer</button>
                            </form>
                          ) : null}
                          <form action={duplicateQuoteAction}>
                            <input type="hidden" name="quote_id" value={row.id} />
                            <input type="hidden" name="return_to" value={currentListHref} />
                            <button type="submit" className="ghost">Dupliquer</button>
                          </form>
                          {publicHref ? (
                            <Link className="ghost" href={publicHref} target="_blank">Page publique</Link>
                          ) : null}
                          {publicAbsoluteHref ? (
                            <CopyLinkButton value={publicAbsoluteHref} label="Copier lien" />
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
