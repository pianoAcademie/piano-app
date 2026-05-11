import Link from "next/link";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../../components/copy-link-button";
import { disableAdminFormulaAction, duplicateAdminFormulaAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminFormulaOut, UserOut } from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;
type FormulaStatusFilter = "all" | "active" | "inactive";
type FormulaVisibilityFilter = "all" | "public" | "private";
type FormulaDiffusionFilter = "all" | "enabled" | "disabled";

const PURCHASE_LINK_OPTION_ENABLED = new Set(["achat_par_lien", "purchase_link_enabled", "buy_link_enabled"]);
const PURCHASE_LINK_OPTION_DISABLED = new Set(["achat_par_lien_desactive", "purchase_link_disabled", "buy_link_disabled"]);

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function parseStatusFilter(raw: string): FormulaStatusFilter {
  const value = raw.trim().toLowerCase();
  if (value === "active") {
    return "active";
  }
  if (value === "inactive") {
    return "inactive";
  }
  return "all";
}

function parseVisibilityFilter(raw: string): FormulaVisibilityFilter {
  const value = raw.trim().toLowerCase();
  if (value === "public") {
    return "public";
  }
  if (value === "private") {
    return "private";
  }
  return "all";
}

function parseDiffusionFilter(raw: string): FormulaDiffusionFilter {
  const value = raw.trim().toLowerCase();
  if (value === "enabled") {
    return "enabled";
  }
  if (value === "disabled") {
    return "disabled";
  }
  return "all";
}

function buildFormulasHref(params: SearchParams, updates: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(params)) {
    const value = Array.isArray(rawValue) ? rawValue[0] : rawValue;
    if (!value) {
      continue;
    }
    sp.set(key, value);
  }
  for (const [key, value] of Object.entries(updates)) {
    if (!value) {
      sp.delete(key);
      continue;
    }
    sp.set(key, value);
  }
  const query = sp.toString();
  return query ? `/admin/config/formulas?${query}` : "/admin/config/formulas";
}

function formulaKindLabel(kind: AdminFormulaOut["kind"], language: UiLanguage): string {
  if (kind === "PACK") {
    return uiText(language, "admin.formulas.kind_pack");
  }
  if (kind === "FORFAIT") {
    return uiText(language, "admin.formulas.kind_forfait");
  }
  return uiText(language, "admin.formulas.kind_subscription");
}

function formulaFrequencyLabel(kind: AdminFormulaOut["kind"], language: UiLanguage): string {
  if (kind === "SUBSCRIPTION") {
    return uiText(language, "admin.formulas.frequency_monthly");
  }
  return uiText(language, "admin.formulas.frequency_one_time");
}

function normalizeFormulaOptions(options: string[]): Set<string> {
  return new Set(options.map((value) => value.trim().toLowerCase()).filter(Boolean));
}

function formulaPurchaseLinkEnabled(formula: AdminFormulaOut): boolean {
  const options = normalizeFormulaOptions(formula.options);
  if ([...options].some((key) => PURCHASE_LINK_OPTION_DISABLED.has(key))) {
    return false;
  }
  if ([...options].some((key) => PURCHASE_LINK_OPTION_ENABLED.has(key))) {
    return true;
  }
  return true;
}

function formulaDiffusionStatus(formula: AdminFormulaOut, language: UiLanguage): { label: string; enabled: boolean } {
  if (!formula.active) {
    return { label: uiText(language, "admin.formulas.link_inactive_formula"), enabled: false };
  }
  if (!formulaPurchaseLinkEnabled(formula)) {
    return { label: uiText(language, "admin.formulas.link_disabled"), enabled: false };
  }
  return { label: uiText(language, "admin.formulas.link_active"), enabled: true };
}

function formatMoney(amountRaw: string | null, currency: string | null, language: UiLanguage): string {
  if (!amountRaw) {
    return "-";
  }
  const amount = Number(amountRaw);
  const normalizedCurrency = currency || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${normalizedCurrency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency: normalizedCurrency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${normalizedCurrency}`;
  }
}

function buildPublicBaseUrl(): string {
  const h = headers();
  const forwardedHost = h.get("x-forwarded-host");
  const host = forwardedHost || h.get("host") || "localhost:3000";
  const forwardedProto = h.get("x-forwarded-proto");
  const proto = forwardedProto || (host.includes("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

export default async function AdminFormulasPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
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

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const query = readParam(params, "q").trim().toLowerCase();
  const statusFilter = parseStatusFilter(readParam(params, "status"));
  const visibilityFilter = parseVisibilityFilter(readParam(params, "visibility"));
  const diffusionFilter = parseDiffusionFilter(readParam(params, "diffusion"));

  const formulasResult = await backendRequest<AdminFormulaOut[]>("/api/v1/admin/formulas?include_inactive=true", {}, token);
  if (!formulasResult.ok && formulasResult.status === 401) {
    redirect("/login?error_code=session_expired");
  }

  const formulas = formulasResult.ok ? formulasResult.data : [];
  const loadError = formulasResult.ok ? "" : formulasResult.message;
  const baseUrl = buildPublicBaseUrl();

  const filtered = formulas
    .filter((formula) => {
      if (statusFilter === "active" && !formula.active) {
        return false;
      }
      if (statusFilter === "inactive" && formula.active) {
        return false;
      }
      if (visibilityFilter === "public" && formula.is_private) {
        return false;
      }
      if (visibilityFilter === "private" && !formula.is_private) {
        return false;
      }
      const diffusion = formulaDiffusionStatus(formula, language);
      if (diffusionFilter === "enabled" && !diffusion.enabled) {
        return false;
      }
      if (diffusionFilter === "disabled" && diffusion.enabled) {
        return false;
      }
      if (!query) {
        return true;
      }
      const haystack = `${formula.name} ${formula.code} ${formula.description ?? ""}`.toLowerCase();
      return haystack.includes(query);
    })
    .sort((left, right) => left.name.localeCompare(right.name, localeForUiLanguage(language)));

  const currentHref = buildFormulasHref(params, {});
  const formulaStats = {
    total: formulas.length,
    active: formulas.filter((formula) => formula.active).length,
    public: formulas.filter((formula) => !formula.is_private).length,
    diffusionEnabled: formulas.filter((formula) => formulaDiffusionStatus(formula, language).enabled).length,
  };

  return (
    <main className="stack admin-formulas-page">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>{t("admin.formulas.title")}</h1>
            <p className="muted">{t("admin.formulas.subtitle")}</p>
          </div>
          <div className="row">
            <Link className="ghost" href="/admin/config?section=params-account">
              {t("admin.formulas.back_config")}
            </Link>
            <Link className="mode-link" href={`/admin/config/formulas/new?back=${encodeURIComponent(currentHref)}`}>
              {t("admin.formulas.add_formula")}
            </Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadError ? <section className="flash-err">{t("admin.formulas.load_error", { message: loadError })}</section> : null}

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{t("admin.config.metrics.total")}</span>
            <strong>{formulaStats.total}</strong>
          </article>
          <article>
            <span>{t("common.active")}</span>
            <strong>{formulaStats.active}</strong>
          </article>
          <article>
            <span>{t("admin.formulas.visibility_public")}</span>
            <strong>{formulaStats.public}</strong>
          </article>
          <article>
            <span>{t("admin.formulas.diffusion")}</span>
            <strong>{formulaStats.diffusionEnabled}</strong>
          </article>
        </div>
      </section>

      <section className="card">
        <form method="get" className="row formulas-admin-filters">
          <label>
            {uiText(language, "common.search")}
            <input type="search" name="q" defaultValue={readParam(params, "q")} placeholder={t("admin.formulas.search_placeholder")} />
          </label>
          <label>
            {uiText(language, "common.status")}
            <select name="status" defaultValue={statusFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="active">{uiText(language, "common.active")}</option>
              <option value="inactive">{uiText(language, "common.inactive")}</option>
            </select>
          </label>
          <label>
            {uiText(language, "common.visibility")}
            <select name="visibility" defaultValue={visibilityFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="public">{uiText(language, "common.public")}</option>
              <option value="private">{uiText(language, "common.private")}</option>
            </select>
          </label>
          <label>
            {t("admin.formulas.diffusion")}
            <select name="diffusion" defaultValue={diffusionFilter}>
              <option value="all">{uiText(language, "common.all")}</option>
              <option value="enabled">{t("admin.formulas.link_active")}</option>
              <option value="disabled">{t("admin.formulas.link_disabled")}</option>
            </select>
          </label>
          <button className="ghost small-btn" type="submit">
            {uiText(language, "common.apply")}
          </button>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>{t("admin.formulas.formulas_count", { count: filtered.length })}</h3>
          <small className="muted">{t("admin.formulas.direct_action_hint")}</small>
        </div>
        {filtered.length === 0 ? (
          <p className="muted">{t("admin.formulas.no_formulas")}</p>
        ) : (
          <div className="table-wrap formulas-admin-table-wrap">
            <table className="data-table formulas-admin-table">
              <thead>
                <tr>
                  <th>{t("admin.formulas.table_formula")}</th>
                  <th>{uiText(language, "common.type")}</th>
                  <th>{uiText(language, "common.status")}</th>
                  <th>{uiText(language, "common.visibility")}</th>
                  <th>{t("admin.formulas.access_restrictions")}</th>
                  <th>{t("admin.formulas.price_payment")}</th>
                  <th>{t("admin.formulas.diffusion")}</th>
                  <th>{uiText(language, "common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((formula) => {
                  const linkStatus = formulaDiffusionStatus(formula, language);
                  const purchasePath = `/buy/formula/${formula.id}`;
                  const purchaseUrl = `${baseUrl}${purchasePath}`;
                  const editHref = `/admin/config/formulas/${formula.id}?back=${encodeURIComponent(currentHref)}`;
                  return (
                    <tr key={formula.id}>
                      <td>
                        <strong>{formula.name}</strong>
                        <div className="formula-meta-code">{formula.code}</div>
                        {formula.description ? <p className="muted">{formula.description}</p> : null}
                      </td>
                      <td>
                        <div className="formula-info-col">
                          <span>{formulaKindLabel(formula.kind, language)}</span>
                          <small className="muted">{formulaFrequencyLabel(formula.kind, language)}</small>
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill ${formula.active ? "status-ok" : "status-off"}`}>
                          {formula.active ? uiText(language, "common.active") : uiText(language, "common.inactive")}
                        </span>
                      </td>
                      <td>
                        <span className={`status-pill ${formula.is_private ? "status-warn" : "status-info"}`}>
                          {formula.is_private ? uiText(language, "common.private") : uiText(language, "common.public")}
                        </span>
                      </td>
                      <td>
                        <div className="formula-info-col">
                          <small className="muted">
                            {t("admin.formulas.activities_label")}: {formula.entitlement_course_type_names.length > 0 ? formula.entitlement_course_type_names.join(", ") : t("admin.formulas.no_activity")}
                          </small>
                          <small className="muted">{t("admin.formulas.restrictions_label")}: {formula.restrictions.length}</small>
                        </div>
                      </td>
                      <td>
                        <div className="formula-info-col">
                          <small>
                            {t("admin.formulas.price_label")}:{" "}
                            {formatMoney(
                              formula.monthly_price_value ?? formula.monthly_price_excl_vat,
                              formula.currency_code ?? "EUR",
                              language,
                            )}
                          </small>
                          <small>
                            {t("admin.formulas.signup_fee_label")}:{" "}
                            {formatMoney(
                              formula.signup_fee_value ?? formula.signup_fee_excl_vat,
                              formula.currency_code ?? "EUR",
                              language,
                            )}
                          </small>
                          <small className="muted">{formula.payment_methods.length > 0 ? formula.payment_methods.join(", ") : "-"}</small>
                        </div>
                      </td>
                      <td>
                        <div className="formula-diffusion-block">
                          <small>
                            {t("admin.formulas.link_status")}:{" "}
                            <strong className={linkStatus.enabled ? "text-ok" : "text-danger"}>{linkStatus.label}</strong>
                          </small>
                          <small>{t("admin.formulas.purchase_link")}: {purchasePath}</small>
                          <small>{t("admin.formulas.purchase_link_allowed")}: {linkStatus.enabled ? uiText(language, "common.yes") : uiText(language, "common.no")}</small>
                          <div className="row formula-diffusion-actions">
                            <CopyLinkButton
                              value={purchaseUrl}
                              label={uiText(language, "common.copy_link")}
                              copiedLabel={uiText(language, "common.link_copied")}
                            />
                            <Link className="ghost small-btn" href={purchasePath} target="_blank" rel="noreferrer">
                              {t("admin.formulas.view_purchase_page")}
                            </Link>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="formula-actions-cell">
                          <Link className="mode-link" href={editHref}>
                            {uiText(language, "common.edit")}
                          </Link>
                          <form action={duplicateAdminFormulaAction}>
                            <input type="hidden" name="formula_id" value={formula.id} />
                            <input type="hidden" name="return_to" value={currentHref} />
                            <button type="submit" className="ghost small-btn">
                              {uiText(language, "common.duplicate")}
                            </button>
                          </form>
                          <form action={disableAdminFormulaAction}>
                            <input type="hidden" name="formula_id" value={formula.id} />
                            <input type="hidden" name="return_to" value={currentHref} />
                            <button type="submit" className="danger small-btn" disabled={!formula.active}>
                              {t("admin.formulas.disable")}
                            </button>
                          </form>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
