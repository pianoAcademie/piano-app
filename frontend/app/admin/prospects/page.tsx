import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type { UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import { resolveUiFlashMessage, withUiLanguage } from "../../../lib/ui-messages";

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

function formatDate(value: string, language: UiLanguage): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function prospectTypeLabel(type: "adult" | "child", language: UiLanguage): string {
  return type === "child" ? uiText(language, "admin.prospects.type_child") : uiText(language, "admin.prospects.type_adult");
}

function prospectStatusLabel(status: string, language: UiLanguage): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === "active") return uiText(language, "admin.prospects.status_active");
  if (normalized === "new") return uiText(language, "admin.prospects.status_new");
  if (normalized === "lost") return uiText(language, "admin.prospects.status_lost");
  if (normalized === "converted") return uiText(language, "admin.prospects.status_converted");
  if (normalized === "archived") return uiText(language, "admin.prospects.status_archived");
  return status || "-";
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
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

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
  const okMessage = resolveUiFlashMessage(searchParams, language, "ok") || ok;
  const errorMessage = resolveUiFlashMessage(searchParams, language, "error") || error;

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

  const currentListHref = withUiLanguage(buildProspectsListHref({
    q,
    status,
    prospectType: typeFilter,
    hasParent: parentFilter,
    hasQuote: hasQuoteFilter,
    source: sourceFilter,
    createdFrom: createdFromRaw,
    createdTo: createdToRaw,
  }), language);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.prospects.title")}</h2>
            <p className="muted">{t("admin.prospects.subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={withUiLanguage("/admin/quotes", language)}>{t("admin.prospects.view_quotes")}</Link>
            <Link className="mode-link" href={withUiLanguage("/admin/prospects/new", language)}>{t("admin.prospects.new_prospect")}</Link>
          </div>
        </div>
      </section>

      {!prospectsResult.ok ? <section className="flash-err">{t("admin.prospects.prospects_error")}: {prospectsResult.message}</section> : null}
      {!quotesResult.ok ? <section className="flash-err">{t("admin.prospects.quotes_error")}: {quotesResult.message}</section> : null}
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="card">
        <h3>{t("admin.prospects.list_title")}</h3>
        <form method="get" className="grid cols-4 sticky-filters top-gap-sm">
          <label className="cols-span-2">
            {uiText(language, "common.search")}
            <input type="search" name="q" defaultValue={q} placeholder={t("admin.prospects.search_placeholder")} />
          </label>
          <label>
            {uiText(language, "common.status")}
            <select name="status" defaultValue={status}>
              <option value="">{uiText(language, "common.all")}</option>
              <option value="active">{t("admin.prospects.status_active")}</option>
              <option value="new">{t("admin.prospects.status_new")}</option>
              <option value="lost">{t("admin.prospects.status_lost")}</option>
              <option value="converted">{t("admin.prospects.status_converted")}</option>
              <option value="archived">{t("admin.prospects.status_archived")}</option>
            </select>
          </label>
          <label>
            {uiText(language, "common.type")}
            <select name="prospect_type" defaultValue={typeFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="adult">{t("admin.prospects.type_adult")}</option>
              <option value="child">{t("admin.prospects.type_child")}</option>
            </select>
          </label>
          <label>
            {t("admin.prospects.parent_referent")}
            <select name="has_parent" defaultValue={parentFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="yes">{t("admin.prospects.with_parent")}</option>
              <option value="no">{t("admin.prospects.without_parent")}</option>
            </select>
          </label>
          <label>
            {t("admin.prospects.has_quote")}
            <select name="has_quote" defaultValue={hasQuoteFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="yes">{uiText(language, "common.yes")}</option>
              <option value="no">{uiText(language, "common.no")}</option>
            </select>
          </label>
          <label>
            {uiText(language, "common.source")}
            <input type="text" name="source" defaultValue={sourceFilter} placeholder={t("admin.prospects.source_placeholder")} />
          </label>
          <label>
            {t("admin.prospects.created_from")}
            <input type="date" name="created_from" defaultValue={createdFromRaw} />
          </label>
          <label>
            {t("admin.prospects.created_to")}
            <input type="date" name="created_to" defaultValue={createdToRaw} />
          </label>
          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">{uiText(language, "common.apply")}</button>
            <a className="ghost" href={withUiLanguage("/admin/prospects", language)}>{uiText(language, "common.reset")}</a>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("admin.prospects.column_prospect_type")}</th>
                <th>{t("admin.prospects.column_primary_name")}</th>
                <th>{t("admin.prospects.column_primary_email")}</th>
                <th>{t("admin.prospects.column_primary_phone")}</th>
                <th>{t("admin.prospects.parent_referent")}</th>
                <th>{t("admin.prospects.column_quote_count")}</th>
                <th>{t("admin.prospects.column_last_quote")}</th>
                <th>{uiText(language, "common.status")}</th>
                <th>{t("admin.prospects.column_created_at")}</th>
                <th>{uiText(language, "common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredProspects.length === 0 ? (
                <tr>
                  <td colSpan={10}><p className="muted">{t("admin.prospects.no_results")}</p></td>
                </tr>
              ) : (
                filteredProspects.map((row) => {
                  const type = prospectType(row.meta || {});
                  const detailHref = withUiLanguage(`/admin/prospects/${row.id}?return_to=${encodeURIComponent(currentListHref)}`, language);
                  const newQuoteHref = withUiLanguage(`/admin/quotes/new?prospect_id=${encodeURIComponent(row.id)}`, language);
                  const quoteMeta = quoteMetaByProspect.get(row.id) ?? { count: 0, lastQuote: null };
                  const lastQuote = quoteMeta.lastQuote;
                  const lastQuoteHref = lastQuote
                    ? withUiLanguage(`/admin/quotes/${lastQuote.id}?back=${encodeURIComponent(withUiLanguage("/admin/quotes", language))}`, language)
                    : "";
                  return (
                    <tr key={row.id}>
                      <td>{prospectTypeLabel(type, language)}</td>
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
                            <small className="muted">{quoteStatusLabel(lastQuote.status, language)} · {formatDate(lastQuote.created_at, language)}</small>
                          </>
                        ) : (
                          <span className="muted">{t("admin.prospects.none")}</span>
                        )}
                      </td>
                      <td><span className="status-pill status-off">{prospectStatusLabel(row.status, language)}</span></td>
                      <td>{formatDate(row.created_at, language)}</td>
                      <td>
                        <div className="row wrap gap-xs">
                          <Link className="ghost" href={detailHref}>{t("admin.prospects.view_edit")}</Link>
                          <Link className="ghost" href={newQuoteHref}>{t("admin.prospects.create_quote")}</Link>
                          {lastQuoteHref ? <Link className="ghost" href={lastQuoteHref}>{t("admin.prospects.last_quote")}</Link> : null}
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
