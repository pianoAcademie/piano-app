import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import AdminProspectForm from "../../../../components/admin-prospect-form";
import { updateAdminProspectAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

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

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function formatDate(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string, language: UiLanguage): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: currency || "EUR" }).format(amount);
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

function quoteStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "created") return uiText(language, "admin.prospects.quote_created");
  if (normalized === "sent") return uiText(language, "admin.prospects.quote_sent");
  if (normalized === "approved") return uiText(language, "admin.prospects.quote_approved");
  if (normalized === "rejected") return uiText(language, "admin.prospects.quote_rejected");
  if (normalized === "change_requested") return uiText(language, "admin.prospects.quote_change_requested");
  if (normalized === "cancelled") return uiText(language, "admin.prospects.quote_cancelled");
  if (normalized === "expired") return uiText(language, "admin.prospects.quote_expired");
  return status || "-";
}

export default async function AdminProspectDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const prospectId = String(params.prospectId || "").trim();
  if (!prospectId) {
    redirect(`/admin/prospects?error=${encodeURIComponent(t("admin.prospects.not_found"))}`);
  }

  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const returnTo = safeReturnPath(readParam(searchParams, "return_to") || "/admin/prospects");

  const [prospectResult, quotesResult, parentsResult] = await Promise.all([
    backendRequest<ProspectOut>(`/api/v1/prospects/${encodeURIComponent(prospectId)}`, {}, token),
    backendRequest<QuoteOut[]>("/api/v1/quotes?limit=1000", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000&prospect_type=adult", {}, token),
  ]);

  if (!prospectResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>{t("admin.prospects.not_found")}</h2>
          <p className="flash-err">{prospectResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href="/admin/prospects">{t("admin.prospects.back_list")}</Link>
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
            <h2>{t("admin.prospects.detail_title", { name: displayName(prospect.first_name, prospect.last_name, prospect.email) })}</h2>
            <p className="muted">{t("admin.prospects.detail_subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={returnTo}>{t("admin.prospects.back")}</Link>
            <Link className="ghost" href={`/admin/quotes/new?prospect_id=${encodeURIComponent(prospect.id)}`}>{t("admin.prospects.create_quote")}</Link>
          </div>
        </div>
      </section>

      {ok ? <section className="flash-ok">{ok}</section> : null}
      {error ? <section className="flash-err">{error}</section> : null}
      {!quotesResult.ok ? <section className="flash-err">{t("admin.prospects.quotes_error")}: {quotesResult.message}</section> : null}
      {!parentsResult.ok ? <section className="flash-err">{t("admin.prospects.parents_search_error")}: {parentsResult.message}</section> : null}

      <section className="card">
        <AdminProspectForm
          mode="edit"
          language={language}
          returnTo={returnTo}
          submitAction={updateAdminProspectAction}
          initial={prospect}
          parentCandidates={parentCandidates}
        />
      </section>

      <section className="card">
        <div className="row spread wrap gap-sm">
          <h3>{t("admin.prospects.linked_quotes")}</h3>
          <Link className="ghost" href={`/admin/quotes/new?prospect_id=${encodeURIComponent(prospect.id)}`}>{t("admin.prospects.create_a_quote")}</Link>
        </div>
        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("admin.prospects.quote_number")}</th>
                <th>{uiText(language, "common.status")}</th>
                <th>{t("admin.prospects.total_ttc")}</th>
                <th>{t("admin.prospects.created_on")}</th>
                <th>{t("admin.prospects.expires_on")}</th>
                <th>{uiText(language, "client.action")}</th>
              </tr>
            </thead>
            <tbody>
              {linkedQuotes.length === 0 ? (
                <tr>
                  <td colSpan={6}><p className="muted">{t("admin.prospects.no_linked_quotes")}</p></td>
                </tr>
              ) : (
                linkedQuotes.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.quote_number}</strong></td>
                    <td><span className={`status-pill ${quoteStatusClass(row.status)}`}>{quoteStatusLabel(row.status, language)}</span></td>
                    <td>{formatAmount(row.total_ttc, row.currency, language)}</td>
                    <td>{formatDate(row.created_at, language)}</td>
                    <td>{formatDate(row.expires_at, language)}</td>
                    <td>
                      <Link className="ghost" href={`/admin/quotes/${row.id}?back=${encodeURIComponent(returnTo)}`}>{uiText(language, "common.open")}</Link>
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
