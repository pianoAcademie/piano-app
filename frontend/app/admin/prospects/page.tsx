import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";

type SearchParams = Record<string, string | string[] | undefined>;
type ProspectStatusFilter = "" | "active" | "archived" | "converted" | "lost" | "new";
type ProspectTypeFilter = "all" | "adult" | "child";
type ParentFilter = "all" | "yes" | "no";

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

export default async function AdminProspectsPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const q = readParam(searchParams, "q");
  const status = safeStatusFilter(readParam(searchParams, "status"));
  const typeFilter = parseTypeFilter(readParam(searchParams, "prospect_type"));
  const parentFilter = parseParentFilter(readParam(searchParams, "has_parent"));
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  query.set("limit", "1000");

  const prospectsResult = await backendRequest<ProspectOut[]>(`/api/v1/prospects?${query.toString()}`, {}, token);
  const prospects = prospectsResult.ok ? prospectsResult.data : [];

  const filteredProspects = prospects.filter((row) => {
    const rowType = prospectType(row.meta || {});
    const rowHasParent = hasParent(row.meta || {});
    if (typeFilter !== "all" && rowType !== typeFilter) {
      return false;
    }
    if (parentFilter === "yes" && !rowHasParent) {
      return false;
    }
    if (parentFilter === "no" && rowHasParent) {
      return false;
    }
    return true;
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
                <th>Statut</th>
                <th>Date creation</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProspects.length === 0 ? (
                <tr>
                  <td colSpan={8}><p className="muted">Aucun prospect sur ces filtres.</p></td>
                </tr>
              ) : (
                filteredProspects.map((row) => {
                  const type = prospectType(row.meta || {});
                  const detailHref = `/admin/prospects/${row.id}`;
                  const newQuoteHref = `/admin/quotes/new?prospect_id=${encodeURIComponent(row.id)}`;
                  return (
                    <tr key={row.id}>
                      <td>{type === "child" ? "Enfant" : "Adulte"}</td>
                      <td><strong>{displayName(row.first_name, row.last_name, row.email)}</strong></td>
                      <td>{row.email}</td>
                      <td>{row.phone || "-"}</td>
                      <td>{parentLabel(row.meta || {})}</td>
                      <td><span className="status-pill status-off">{row.status}</span></td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>
                        <div className="row wrap gap-xs">
                          <Link className="ghost" href={detailHref}>Voir / Editer</Link>
                          <Link className="ghost" href={newQuoteHref}>Creer devis</Link>
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
