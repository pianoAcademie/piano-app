import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";

type SearchParams = Record<string, string | string[] | undefined>;
type ProspectStatusFilter = "" | "active" | "archived" | "converted" | "lost" | "new";
type ProspectTypeFilter = "all" | "adult" | "child";
type ParentFilter = "all" | "yes" | "no";
type HasQuoteFilter = "all" | "yes" | "no";

type ProspectOut = {
  id: string;
  status: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  source: string | null;
  notes: string | null;
  meta: Record<string, unknown>;
  created_at: string;
};

type QuoteOut = {
  id: string;
  prospect_id: string | null;
  quote_number: string;
  status: string;
  created_at: string;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function parseTypeFilter(value: string): ProspectTypeFilter {
  const normalized = value.trim().toLowerCase();
  if (normalized === "adult" || normalized === "child") {
    return normalized;
  }
  return "all";
}

function parseParentFilter(value: string): ParentFilter {
  const normalized = value.trim().toLowerCase();
  if (normalized === "yes" || normalized === "no") {
    return normalized;
  }
  return "all";
}

function parseHasQuoteFilter(value: string): HasQuoteFilter {
  const normalized = value.trim().toLowerCase();
  if (normalized === "yes" || normalized === "no") {
    return normalized;
  }
  return "all";
}

function safeStatusFilter(value: string): ProspectStatusFilter {
  const normalized = value.trim().toLowerCase();
  if (normalized === "active" || normalized === "archived" || normalized === "converted" || normalized === "lost" || normalized === "new") {
    return normalized;
  }
  return "";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function prospectType(meta: Record<string, unknown>): "adult" | "child" {
  return String(meta.prospect_type || "").trim().toLowerCase() === "child" ? "child" : "adult";
}

function parentLabel(meta: Record<string, unknown>): string {
  const parent = meta.parent_referent;
  if (!parent || typeof parent !== "object") {
    return "-";
  }
  const record = parent as Record<string, unknown>;
  const firstName = typeof record.first_name === "string" ? record.first_name : "";
  const lastName = typeof record.last_name === "string" ? record.last_name : "";
  const email = typeof record.email === "string" ? record.email : "";
  const label = [firstName, lastName].filter(Boolean).join(" ").trim();
  return label || email || "-";
}

function hasParent(meta: Record<string, unknown>): boolean {
  return parentLabel(meta) !== "-";
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function parseIsoDateOnly(raw: string): Date | null {
  const value = raw.trim();
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function buildProspectsListHref(params: {
  q: string;
  status: string;
  prospectType: string;
  hasParent: string;
  hasQuote: string;
  source: string;
  createdFrom: string;
  createdTo: string;
}): string {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.status) sp.set("status", params.status);
  if (params.prospectType) sp.set("prospect_type", params.prospectType);
  if (params.hasParent) sp.set("has_parent", params.hasParent);
  if (params.hasQuote) sp.set("has_quote", params.hasQuote);
  if (params.source) sp.set("source", params.source);
  if (params.createdFrom) sp.set("created_from", params.createdFrom);
  if (params.createdTo) sp.set("created_to", params.createdTo);
  const value = sp.toString();
  return value ? `/admin/prospects?${value}` : "/admin/prospects";
}

export default async function AdminProspectsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const q = readParam(searchParams, "q");
  const status = safeStatusFilter(readParam(searchParams, "status"));
  const typeFilter = parseTypeFilter(readParam(searchParams, "prospect_type"));
  const parentFilter = parseParentFilter(readParam(searchParams, "has_parent"));
  const hasQuoteFilter = parseHasQuoteFilter(readParam(searchParams, "has_quote"));
  const sourceFilter = readParam(searchParams, "source").trim().toLowerCase();
  const createdFromRaw = readParam(searchParams, "created_from");
  const createdToRaw = readParam(searchParams, "created_to");
  const createdFrom = parseIsoDateOnly(createdFromRaw);
  const createdTo = parseIsoDateOnly(createdToRaw);
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  query.set("limit", "1000");

  const [prospectsResult, quotesResult] = await Promise.all([
    backendRequest<ProspectOut[]>(`/api/v1/prospects?${query.toString()}`, {}, token),
    backendRequest<QuoteOut[]>("/api/v1/quotes?limit=1000", {}, token),
  ]);
  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const quotes = quotesResult.ok ? quotesResult.data : [];
  const quoteMetaByProspect = new Map<string, { count: number; lastQuote: QuoteOut | null }>();
  for (const row of quotes) {
    if (!row.prospect_id) {
      continue;
    }
    const current = quoteMetaByProspect.get(row.prospect_id) ?? { count: 0, lastQuote: null };
    current.count += 1;
    if (!current.lastQuote) {
      current.lastQuote = row;
    } else {
      const currentDate = new Date(current.lastQuote.created_at);
      const nextDate = new Date(row.created_at);
      if (Number.isFinite(nextDate.getTime()) && (!Number.isFinite(currentDate.getTime()) || nextDate > currentDate)) {
        current.lastQuote = row;
      }
    }
    quoteMetaByProspect.set(row.prospect_id, current);
  }

  const filteredProspects = prospects.filter((row) => {
    const rowType = prospectType(row.meta || {});
    const rowHasParent = hasParent(row.meta || {});
    const quoteMeta = quoteMetaByProspect.get(row.id) ?? { count: 0, lastQuote: null };
    const rowCreatedAt = new Date(row.created_at);
    if (typeFilter !== "all" && rowType !== typeFilter) {
      return false;
    }
    if (parentFilter === "yes" && !rowHasParent) {
      return false;
    }
    if (parentFilter === "no" && rowHasParent) {
      return false;
    }
    if (hasQuoteFilter === "yes" && quoteMeta.count === 0) {
      return false;
    }
    if (hasQuoteFilter === "no" && quoteMeta.count > 0) {
      return false;
    }
    if (sourceFilter && !(row.source || "").toLowerCase().includes(sourceFilter)) {
      return false;
    }
    if (createdFrom && (!Number.isFinite(rowCreatedAt.getTime()) || rowCreatedAt < createdFrom)) {
      return false;
    }
    if (createdTo) {
      const createdToLimit = new Date(createdTo.getTime() + 24 * 60 * 60 * 1000);
      if (!Number.isFinite(rowCreatedAt.getTime()) || rowCreatedAt >= createdToLimit) {
        return false;
      }
    }
    return true;
  });

  const currentListHref = buildProspectsListHref({
    q,
    status,
    prospectType: typeFilter,
    hasParent: parentFilter,
    hasQuote: hasQuoteFilter,
    source: sourceFilter,
    createdFrom: createdFromRaw,
    createdTo: createdToRaw,
  });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Prospects</h2>
            <p className="muted">Gestion separee des prospects avant ou en dehors de la creation d un devis.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/quotes">Voir devis</Link>
            <Link className="mode-link" href="/admin/prospects/new">Nouveau prospect</Link>
          </div>
        </div>
      </section>

      {!prospectsResult.ok ? <section className="flash-err">Erreur prospects: {prospectsResult.message}</section> : null}
      {!quotesResult.ok ? <section className="flash-err">Erreur devis: {quotesResult.message}</section> : null}
      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}

      <section className="card">
        <h3>Liste des prospects</h3>
        <form method="get" className="grid cols-4 sticky-filters top-gap-sm">
          <label className="cols-span-2">
            Recherche
            <input type="search" name="q" defaultValue={q} placeholder="Nom, prenom, email, telephone..." />
          </label>
          <label>
            Statut
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="active">Actif</option>
              <option value="new">Nouveau</option>
              <option value="lost">Perdu</option>
              <option value="converted">Converti</option>
              <option value="archived">Archive</option>
            </select>
          </label>
          <label>
            Type
            <select name="prospect_type" defaultValue={typeFilter}>
              <option value="all">Tous</option>
              <option value="adult">Adulte</option>
              <option value="child">Enfant</option>
            </select>
          </label>
          <label>
            Parent referent
            <select name="has_parent" defaultValue={parentFilter}>
              <option value="all">Tous</option>
              <option value="yes">Avec parent</option>
              <option value="no">Sans parent</option>
            </select>
          </label>
          <label>
            A deja un devis
            <select name="has_quote" defaultValue={hasQuoteFilter}>
              <option value="all">Tous</option>
              <option value="yes">Oui</option>
              <option value="no">Non</option>
            </select>
          </label>
          <label>
            Source
            <input type="text" name="source" defaultValue={sourceFilter} placeholder="site_web, telephone..." />
          </label>
          <label>
            Cree du
            <input type="date" name="created_from" defaultValue={createdFromRaw} />
          </label>
          <label>
            Cree au
            <input type="date" name="created_to" defaultValue={createdToRaw} />
          </label>
          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">Filtrer</button>
            <a className="ghost" href="/admin/prospects">Reset</a>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type prospect</th>
                <th>Nom principal</th>
                <th>Email principal</th>
                <th>Telephone principal</th>
                <th>Parent referent</th>
                <th>Nb devis</th>
                <th>Dernier devis</th>
                <th>Statut</th>
                <th>Date creation</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProspects.length === 0 ? (
                <tr>
                  <td colSpan={10}><p className="muted">Aucun prospect sur ces filtres.</p></td>
                </tr>
              ) : (
                filteredProspects.map((row) => {
                  const type = prospectType(row.meta || {});
                  const detailHref = `/admin/prospects/${row.id}?return_to=${encodeURIComponent(currentListHref)}`;
                  const newQuoteHref = `/admin/quotes/new?prospect_id=${encodeURIComponent(row.id)}`;
                  const quoteMeta = quoteMetaByProspect.get(row.id) ?? { count: 0, lastQuote: null };
                  const lastQuote = quoteMeta.lastQuote;
                  const lastQuoteHref = lastQuote
                    ? `/admin/quotes/${lastQuote.id}?back=${encodeURIComponent("/admin/quotes")}`
                    : "";
                  return (
                    <tr key={row.id}>
                      <td>{type === "child" ? "Enfant" : "Adulte"}</td>
                      <td><strong>{displayName(row.first_name, row.last_name, row.email)}</strong></td>
                      <td>{row.email}</td>
                      <td>{row.phone || "-"}</td>
                      <td>{parentLabel(row.meta || {})}</td>
                      <td>{quoteMeta.count}</td>
                      <td>
                        {lastQuote ? (
                          <>
                            <strong>{lastQuote.quote_number}</strong>
                            <br />
                            <small className="muted">{lastQuote.status} · {formatDate(lastQuote.created_at)}</small>
                          </>
                        ) : (
                          <span className="muted">Aucun</span>
                        )}
                      </td>
                      <td><span className="status-pill status-off">{row.status}</span></td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>
                        <div className="row wrap gap-xs">
                          <Link className="ghost" href={detailHref}>Voir / Editer</Link>
                          <Link className="ghost" href={newQuoteHref}>Creer devis</Link>
                          {lastQuoteHref ? <Link className="ghost" href={lastQuoteHref}>Dernier devis</Link> : null}
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
