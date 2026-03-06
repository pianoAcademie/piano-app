import Link from "next/link";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../../components/copy-link-button";
import { disableAdminFormulaAction, duplicateAdminFormulaAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { AdminFormulaOut } from "../../../../lib/types";

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

function formulaKindLabel(kind: AdminFormulaOut["kind"]): string {
  if (kind === "PACK") {
    return "Carnet";
  }
  if (kind === "FORFAIT") {
    return "Forfait";
  }
  return "Abonnement";
}

function formulaFrequencyLabel(kind: AdminFormulaOut["kind"]): string {
  if (kind === "SUBSCRIPTION") {
    return "Mensuel";
  }
  return "Paiement unique";
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

function formulaDiffusionStatus(formula: AdminFormulaOut): { label: string; enabled: boolean } {
  if (!formula.active) {
    return { label: "Lien inactif (formule desactivee)", enabled: false };
  }
  if (!formulaPurchaseLinkEnabled(formula)) {
    return { label: "Achat par lien desactive", enabled: false };
  }
  return { label: "Lien actif", enabled: true };
}

function formatMoney(amountRaw: string | null, currency: string | null): string {
  if (!amountRaw) {
    return "-";
  }
  const amount = Number(amountRaw);
  const normalizedCurrency = currency || "EUR";
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${normalizedCurrency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", {
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
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const query = readParam(params, "q").trim().toLowerCase();
  const statusFilter = parseStatusFilter(readParam(params, "status"));
  const visibilityFilter = parseVisibilityFilter(readParam(params, "visibility"));
  const diffusionFilter = parseDiffusionFilter(readParam(params, "diffusion"));

  const formulasResult = await backendRequest<AdminFormulaOut[]>("/api/v1/admin/formulas?include_inactive=true", {}, token);
  if (!formulasResult.ok && formulasResult.status === 401) {
    redirect("/login?error=Session%20expiree");
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
      const diffusion = formulaDiffusionStatus(formula);
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
    .sort((left, right) => left.name.localeCompare(right.name, "fr-FR"));

  const currentHref = buildFormulasHref(params, {});

  return (
    <main className="stack admin-formulas-page">
      <section className="card">
        <div className="row spread">
          <div>
            <h1>Configuration des formules</h1>
            <p className="muted">
              Gere la diffusion des formules, copie le lien d achat et pilote le parcours client jusqu au paiement.
            </p>
          </div>
          <div className="row">
            <Link className="ghost" href="/admin/config?section=params-account">
              Retour configuration
            </Link>
            <Link className="mode-link" href={`/admin/config/formulas/new?back=${encodeURIComponent(currentHref)}`}>
              Ajouter une formule
            </Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadError ? <section className="flash-err">Impossible de charger les formules: {loadError}</section> : null}

      <section className="card">
        <form method="get" className="row formulas-admin-filters">
          <label>
            Recherche
            <input type="search" name="q" defaultValue={readParam(params, "q")} placeholder="Nom, code ou description..." />
          </label>
          <label>
            Statut
            <select name="status" defaultValue={statusFilter}>
              <option value="all">Tous</option>
              <option value="active">Actives</option>
              <option value="inactive">Desactivees</option>
            </select>
          </label>
          <label>
            Visibilite
            <select name="visibility" defaultValue={visibilityFilter}>
              <option value="all">Toutes</option>
              <option value="public">Publiques</option>
              <option value="private">Privees</option>
            </select>
          </label>
          <label>
            Diffusion
            <select name="diffusion" defaultValue={diffusionFilter}>
              <option value="all">Tous</option>
              <option value="enabled">Lien actif</option>
              <option value="disabled">Lien inactif</option>
            </select>
          </label>
          <button className="ghost small-btn" type="submit">
            Filtrer
          </button>
        </form>
      </section>

      <section className="card">
        <div className="row spread">
          <h3>Formules ({filtered.length})</h3>
          <small className="muted">Action directe: copier le lien sans ouvrir la fiche</small>
        </div>
        {filtered.length === 0 ? (
          <p className="muted">Aucune formule ne correspond aux filtres.</p>
        ) : (
          <div className="table-wrap formulas-admin-table-wrap">
            <table className="data-table formulas-admin-table">
              <thead>
                <tr>
                  <th>Formule</th>
                  <th>Type</th>
                  <th>Statut</th>
                  <th>Visibilite</th>
                  <th>Acces / restrictions</th>
                  <th>Prix / paiement</th>
                  <th>Diffusion</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((formula) => {
                  const linkStatus = formulaDiffusionStatus(formula);
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
                          <span>{formulaKindLabel(formula.kind)}</span>
                          <small className="muted">{formulaFrequencyLabel(formula.kind)}</small>
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill ${formula.active ? "status-ok" : "status-off"}`}>
                          {formula.active ? "Active" : "Desactivee"}
                        </span>
                      </td>
                      <td>
                        <span className={`status-pill ${formula.is_private ? "status-warn" : "status-info"}`}>
                          {formula.is_private ? "Privee" : "Publique"}
                        </span>
                      </td>
                      <td>
                        <div className="formula-info-col">
                          <small className="muted">
                            Activites: {formula.entitlement_course_type_names.length > 0 ? formula.entitlement_course_type_names.join(", ") : "Aucune"}
                          </small>
                          <small className="muted">Restrictions: {formula.restrictions.length}</small>
                        </div>
                      </td>
                      <td>
                        <div className="formula-info-col">
                          <small>
                            Tarif:{" "}
                            {formatMoney(
                              formula.monthly_price_value ?? formula.monthly_price_excl_vat,
                              formula.currency_code ?? "EUR",
                            )}
                          </small>
                          <small>
                            Frais dossier:{" "}
                            {formatMoney(
                              formula.signup_fee_value ?? formula.signup_fee_excl_vat,
                              formula.currency_code ?? "EUR",
                            )}
                          </small>
                          <small className="muted">{formula.payment_methods.length > 0 ? formula.payment_methods.join(", ") : "-"}</small>
                        </div>
                      </td>
                      <td>
                        <div className="formula-diffusion-block">
                          <small>
                            Statut du lien:{" "}
                            <strong className={linkStatus.enabled ? "text-ok" : "text-danger"}>{linkStatus.label}</strong>
                          </small>
                          <small>Lien d achat: {purchasePath}</small>
                          <small>Achat par lien autorise: {linkStatus.enabled ? "Oui" : "Non"}</small>
                          <div className="row formula-diffusion-actions">
                            <CopyLinkButton value={purchaseUrl} />
                            <Link className="ghost small-btn" href={purchasePath} target="_blank" rel="noreferrer">
                              Voir la page d achat
                            </Link>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="formula-actions-cell">
                          <Link className="mode-link" href={editHref}>
                            Modifier
                          </Link>
                          <form action={duplicateAdminFormulaAction}>
                            <input type="hidden" name="formula_id" value={formula.id} />
                            <input type="hidden" name="return_to" value={currentHref} />
                            <button type="submit" className="ghost small-btn">
                              Dupliquer
                            </button>
                          </form>
                          <form action={disableAdminFormulaAction}>
                            <input type="hidden" name="formula_id" value={formula.id} />
                            <input type="hidden" name="return_to" value={currentHref} />
                            <button type="submit" className="danger small-btn" disabled={!formula.active}>
                              Desactiver
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
