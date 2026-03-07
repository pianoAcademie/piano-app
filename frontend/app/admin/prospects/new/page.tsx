import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProspectForm from "../../../../components/admin-prospect-form";
import { createAdminProspectAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";

type SearchParams = Record<string, string | string[] | undefined>;
type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
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

export default async function AdminProspectNewPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const returnTo = safeReturnPath(readParam(searchParams, "return_to"));
  const parentsResult = await backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000&prospect_type=adult", {}, token);
  const parentCandidates = (parentsResult.ok ? parentsResult.data : [])
    .filter((row) => String(row.meta?.prospect_type || "adult").toLowerCase() !== "child")
    .map((row) => ({
      id: row.id,
      first_name: row.first_name,
      last_name: row.last_name,
      email: row.email,
      phone: row.phone,
      address: typeof row.meta?.adult_address === "string" ? row.meta.adult_address : null,
    }));

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Nouveau prospect</h2>
            <p className="muted">Creez un prospect adulte ou enfant avec parent referent.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={returnTo}>Retour</Link>
            <Link className="ghost" href="/admin/prospects">Liste prospects</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}
      {!parentsResult.ok ? <section className="flash-err">Erreur recherche parents: {parentsResult.message}</section> : null}

      <section className="card">
        <AdminProspectForm
          mode="create"
          returnTo={returnTo}
          submitAction={createAdminProspectAction}
          parentCandidates={parentCandidates}
        />
      </section>
    </section>
  );
}
