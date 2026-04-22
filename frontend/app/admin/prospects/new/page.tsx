import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProspectForm from "../../../../components/admin-prospect-form";
import { createAdminProspectAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { UserOut } from "../../../../lib/types";
import { normalizeUiLanguage, uiText } from "../../../../lib/ui-i18n";

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
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error=Acces%20admin%20requis");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

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
            <h2>{t("admin.prospects.new_title")}</h2>
            <p className="muted">{t("admin.prospects.new_subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={returnTo}>{t("admin.prospects.back")}</Link>
            <Link className="ghost" href="/admin/prospects">{t("admin.prospects.back_list")}</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}
      {!parentsResult.ok ? <section className="flash-err">{t("admin.prospects.parents_search_error")}: {parentsResult.message}</section> : null}

      <section className="card">
        <AdminProspectForm
          mode="create"
          language={language}
          returnTo={returnTo}
          submitAction={createAdminProspectAction}
          parentCandidates={parentCandidates}
        />
      </section>
    </section>
  );
}
