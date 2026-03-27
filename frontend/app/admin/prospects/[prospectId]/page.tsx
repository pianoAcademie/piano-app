import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProspectForm from "../../../../components/admin-prospect-form";
import { updateAdminProspectAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";

type SearchParams = Record<string, string | string[] | undefined>;

type RouteParams = {
  params: {
    prospectId: string;
  };
  searchParams: SearchParams;
};

type ProspectOut = {
  id: string;
  status: string;
  parent_prospect_id: string | null;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  source: string | null;
  notes: string | null;
  meta: Record<string, unknown>;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  currency: string;
  total_ttc: string;
  prospect_id: string | null;
  created_at: string;
  expires_at: string | null;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function safeReturnPath(raw: string): string {
  const value = raw.trim();
  if (value.startsWith("/admin/prospects") || value.startsWith("/admin/quotes")) {
    return value;
  }
  return "/admin/prospects";
}

function readEditTarget(raw: string): "child" | "parent" | null {
  const value = raw.trim().toLowerCase();
  if (value === "child" || value === "parent") {
    return value;
  }
  return null;
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
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

export default async function AdminProspectDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const prospectId = String(params.prospectId || "").trim();
  if (!prospectId) {
    redirect("/admin/prospects?error=Prospect%20introuvable");
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const returnTo = safeReturnPath(readParam(searchParams, "return_to") || "/admin/prospects");
  const editTarget = readEditTarget(readParam(searchParams, "edit_target"));

  const [prospectResult, quotesResult, parentsResult] = await Promise.all([
    backendRequest<ProspectOut>(`/api/v1/prospects/${encodeURIComponent(prospectId)}`, {}, token),
    backendRequest<QuoteOut[]>("/api/v1/quotes?limit=1000", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000&prospect_type=adult", {}, token),
  ]);

  if (!prospectResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>Prospect introuvable</h2>
          <p className="flash-err">{prospectResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href="/admin/prospects">Retour liste prospects</Link>
          </div>
        </section>
      </section>
    );
  }

  const prospect = prospectResult.data;
  const parentCandidates = (parentsResult.ok ? parentsResult.data : [])
    .filter((row) => row.id !== prospect.id)
    .filter((row) => String(row.meta?.prospect_type || "adult").toLowerCase() !== "child")
    .map((row) => ({
      id: row.id,
      first_name: row.first_name,
      last_name: row.last_name,
      email: row.email,
      phone: row.phone,
      address: typeof row.meta?.adult_address === "string" ? row.meta.adult_address : null,
    }));
  const linkedQuotes = (quotesResult.ok ? quotesResult.data : [])
    .filter((row) => row.prospect_id === prospect.id)
    .sort((a, b) => {
      const left = new Date(a.created_at).getTime();
      const right = new Date(b.created_at).getTime();
      return (Number.isFinite(right) ? right : 0) - (Number.isFinite(left) ? left : 0);
    });

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Prospect: {displayName(prospect.first_name, prospect.last_name, prospect.email)}</h2>
            <p className="muted">Edition du profil prospect et preparation des devis.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={returnTo}>Retour</Link>
            <Link className="ghost" href={`/admin/quotes/new?prospect_id=${encodeURIComponent(prospect.id)}`}>Creer devis</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}
      {!quotesResult.ok ? <section className="flash-err">Erreur devis: {quotesResult.message}</section> : null}
      {!parentsResult.ok ? <section className="flash-err">Erreur recherche parents: {parentsResult.message}</section> : null}

      <section className="card">
        <AdminProspectForm
          mode="edit"
          returnTo={returnTo}
          submitAction={updateAdminProspectAction}
          initial={prospect}
          parentCandidates={parentCandidates}
          focusTarget={editTarget}
        />
      </section>

      <section className="card">
        <div className="row spread wrap gap-sm">
          <h3>Devis lies a ce prospect</h3>
          <Link className="ghost" href={`/admin/quotes/new?prospect_id=${encodeURIComponent(prospect.id)}`}>Creer un devis</Link>
        </div>
        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Numero</th>
                <th>Statut</th>
                <th>Total TTC</th>
                <th>Cree le</th>
                <th>Expire le</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {linkedQuotes.length === 0 ? (
                <tr>
                  <td colSpan={6}><p className="muted">Aucun devis lie.</p></td>
                </tr>
              ) : (
                linkedQuotes.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.quote_number}</strong></td>
                    <td><span className={`status-pill ${quoteStatusClass(row.status)}`}>{row.status}</span></td>
                    <td>{formatAmount(row.total_ttc, row.currency)}</td>
                    <td>{formatDate(row.created_at)}</td>
                    <td>{formatDate(row.expires_at)}</td>
                    <td>
                      <Link className="ghost" href={`/admin/quotes/${row.id}?back=${encodeURIComponent(returnTo)}`}>Ouvrir</Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
