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
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  source: string | null;
  notes: string | null;
  meta: Record<string, unknown>;
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

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
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

  const prospectResult = await backendRequest<ProspectOut>(`/api/v1/prospects/${encodeURIComponent(prospectId)}`, {}, token);

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

      <section className="card">
        <AdminProspectForm mode="edit" returnTo={returnTo} submitAction={updateAdminProspectAction} initial={prospect} />
      </section>
    </section>
  );
}
