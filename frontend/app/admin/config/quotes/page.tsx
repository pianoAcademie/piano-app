import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminQuoteTemplateConfigAction,
  createAdminCgvVersionConfigAction,
  createAdminPricingCatalogConfigAction,
  createAdminQuoteTypeConfigAction,
  deleteAdminQuoteTemplateConfigAction,
  deleteAdminCgvVersionConfigAction,
  deleteAdminPricingCatalogConfigAction,
  deleteAdminQuoteTypeConfigAction,
  deleteAdminSolfegeLevelRuleConfigAction,
  updateAdminQuoteTemplateConfigAction,
  updateAdminCgvVersionConfigAction,
  updateAdminPricingCatalogConfigAction,
  updateAdminQuoteTypeConfigAction,
  upsertAdminSolfegeLevelRuleConfigAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import QuoteTemplateEditor from "../../../../components/quote-template-editor";
import type { LocationOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type QuotesConfigTab = "types" | "catalogs" | "cgv" | "templates" | "variables" | "solfege";

type QuoteTypeOut = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  default_expiry_days: number;
  is_active: boolean;
  updated_at: string;
};

type PricingCatalogOut = {
  id: string;
  name: string;
  school_year_label: string | null;
  effective_from: string;
  effective_to: string | null;
  is_default: boolean;
  is_active: boolean;
  updated_at: string;
};

type CgvVersionOut = {
  id: string;
  version_label: string;
  content: string;
  is_active: boolean;
  updated_at: string;
};

type QuoteTemplateOut = {
  id: string;
  code: string;
  name: string;
  language: string;
  subject_template: string;
  body_template: string;
  is_active: boolean;
  is_default: boolean;
  updated_at: string;
};

type QuoteTemplateVariableOut = {
  key: string;
  label: string;
  description: string;
  example: string;
};

type SolfegeLevelRuleOut = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
  is_active: boolean;
  updated_at: string;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function parseTab(raw: string): QuotesConfigTab {
  const value = raw.trim().toLowerCase();
  if (value === "catalogs" || value === "cgv" || value === "templates" || value === "variables" || value === "solfege") {
    return value;
  }
  return "types";
}

function buildQuotesConfigHref(tab: QuotesConfigTab, params: Record<string, string> = {}): string {
  const sp = new URLSearchParams();
  sp.set("tab", tab);
  for (const [key, value] of Object.entries(params)) {
    if (!value) {
      continue;
    }
    sp.set(key, value);
  }
  return `/admin/config/quotes?${sp.toString()}`;
}

function dateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  return value.slice(0, 10);
}

function dateTimeLabel(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function weekdaysLabel(days: number[]): string {
  if (!days.length) {
    return "Tous";
  }
  return days.join(", ");
}

function modalityLabel(value: string | null): string {
  const normalized = (value || "").trim().toUpperCase();
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  if (normalized === "ANY") {
    return "Tous";
  }
  return "-";
}

function solfegeSlotsCsv(slots: Array<Record<string, unknown>>): string {
  if (!slots.length) {
    return "";
  }
  return slots
    .map((slot) => {
      const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
      const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
      if (!start || !end) {
        return "";
      }
      return `${start}-${end}`;
    })
    .filter(Boolean)
    .join(", ");
}

export default async function AdminQuoteConfigurationPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const tab = parseTab(readParam(params, "tab"));
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  const [quoteTypesResult, catalogsResult, cgvVersionsResult, quoteTemplatesResult, templateVariablesResult, solfegeRulesResult, locationsResult] = await Promise.all([
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<CgvVersionOut[]>("/api/v1/cgv-versions", {}, token),
    backendRequest<QuoteTemplateOut[]>("/api/v1/quote-templates", {}, token),
    backendRequest<QuoteTemplateVariableOut[]>("/api/v1/quote-template-variables", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
  ]);

  const loadErrors: string[] = [];
  const quoteTypes = quoteTypesResult.ok
    ? quoteTypesResult.data
    : (() => {
        loadErrors.push(`Types de devis: ${quoteTypesResult.message}`);
        return [] as QuoteTypeOut[];
      })();
  const catalogs = catalogsResult.ok
    ? catalogsResult.data
    : (() => {
        loadErrors.push(`Catalogues de prix: ${catalogsResult.message}`);
        return [] as PricingCatalogOut[];
      })();
  const cgvVersions = cgvVersionsResult.ok
    ? cgvVersionsResult.data
    : (() => {
        loadErrors.push(`CGV: ${cgvVersionsResult.message}`);
        return [] as CgvVersionOut[];
      })();
  const quoteTemplates = quoteTemplatesResult.ok
    ? quoteTemplatesResult.data
    : (() => {
        loadErrors.push(`Templates de devis: ${quoteTemplatesResult.message}`);
        return [] as QuoteTemplateOut[];
      })();
  const templateVariables = templateVariablesResult.ok
    ? templateVariablesResult.data
    : (() => {
        loadErrors.push(`Variables de template: ${templateVariablesResult.message}`);
        return [] as QuoteTemplateVariableOut[];
      })();
  const solfegeRules = solfegeRulesResult.ok
    ? solfegeRulesResult.data
    : (() => {
        loadErrors.push(`Regles solfege: ${solfegeRulesResult.message}`);
        return [] as SolfegeLevelRuleOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`Lieux: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const returnPath = buildQuotesConfigHref(tab);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Configuration Devis</h2>
            <p className="muted">Administrez les referentiels de devis: types, catalogues, CGV, templates et creneaux solfege.</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/config">Retour Configuration</Link>
            <Link className="ghost" href="/admin/quotes">Voir Devis</Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>Erreurs de chargement</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card">
        <nav className="config-sub-nav">
          <Link className={`config-sub-link ${tab === "types" ? "active" : ""}`} href={buildQuotesConfigHref("types")}>Types de devis</Link>
          <Link className={`config-sub-link ${tab === "catalogs" ? "active" : ""}`} href={buildQuotesConfigHref("catalogs")}>Catalogues de prix</Link>
          <Link className={`config-sub-link ${tab === "cgv" ? "active" : ""}`} href={buildQuotesConfigHref("cgv")}>CGV</Link>
          <Link className={`config-sub-link ${tab === "templates" ? "active" : ""}`} href={buildQuotesConfigHref("templates")}>Templates</Link>
          <Link className={`config-sub-link ${tab === "variables" ? "active" : ""}`} href={buildQuotesConfigHref("variables")}>Variables</Link>
          <Link className={`config-sub-link ${tab === "solfege" ? "active" : ""}`} href={buildQuotesConfigHref("solfege")}>Creneaux solfege</Link>
        </nav>
      </section>

      {tab === "types" ? (
        <section className="card">
          <h3>Types de devis</h3>
          <form action={createAdminQuoteTypeConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
            <label>
              Code
              <input type="text" name="code" required maxLength={60} placeholder="FORFAIT_STANDARD" />
            </label>
            <label className="span-2">
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Forfait standard" />
            </label>
            <label>
              Delai expiration (jours)
              <input type="number" name="default_expiry_days" min={1} max={120} defaultValue={10} required />
            </label>
            <label className="span-3">
              Description
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter le type</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {quoteTypes.length === 0 ? <p className="muted">Aucun type de devis.</p> : null}
            {quoteTypes.map((row) => (
              <article key={row.id} className="item">
                <div className="row spread wrap gap-sm">
                  <div>
                    <strong>{row.name}</strong>
                    <p className="muted">{row.code} · Expiration {row.default_expiry_days} jours</p>
                    <small className="muted">{row.description || "Sans description"}</small>
                  </div>
                  <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span>
                </div>
                <details>
                  <summary className="mode-link">Modifier</summary>
                  <form action={updateAdminQuoteTypeConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
                    <input type="hidden" name="quote_type_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
                    <label>
                      Code
                      <input type="text" name="code" defaultValue={row.code} required maxLength={60} />
                    </label>
                    <label className="span-2">
                      Nom
                      <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                    </label>
                    <label>
                      Delai expiration (jours)
                      <input type="number" name="default_expiry_days" min={1} max={120} defaultValue={row.default_expiry_days} required />
                    </label>
                    <label className="span-3">
                      Description
                      <input type="text" name="description" defaultValue={row.description || ""} maxLength={2000} />
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                      Actif
                    </label>
                    <div className="row span-4">
                      <button type="submit">Enregistrer</button>
                    </div>
                  </form>
                  <form action={deleteAdminQuoteTypeConfigAction} className="row top-gap-sm">
                    <input type="hidden" name="quote_type_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
                    <button type="submit" className="danger">Supprimer</button>
                  </form>
                </details>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {tab === "catalogs" ? (
        <section className="card">
          <h3>Catalogues de prix</h3>
          <form action={createAdminPricingCatalogConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
            <label className="span-2">
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Catalogue 2026-2027" />
            </label>
            <label>
              Annee scolaire
              <input type="text" name="school_year_label" maxLength={40} placeholder="2026-2027" />
            </label>
            <label>
              Date debut
              <input type="date" name="effective_from" required />
            </label>
            <label>
              Date fin
              <input type="date" name="effective_to" />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_default" />
              Catalogue par defaut
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter le catalogue</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Annee</th>
                  <th>Periode</th>
                  <th>Statut</th>
                  <th>Maj</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {catalogs.length === 0 ? (
                  <tr><td colSpan={6}><p className="muted">Aucun catalogue configure.</p></td></tr>
                ) : (
                  catalogs.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.name}</strong></td>
                      <td>{row.school_year_label || "-"}</td>
                      <td>{dateInputValue(row.effective_from)} → {dateInputValue(row.effective_to)}</td>
                      <td>
                        <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span>
                        {row.is_default ? <span className="badge">Defaut</span> : null}
                      </td>
                      <td>{dateTimeLabel(row.updated_at)}</td>
                      <td>
                        <details>
                          <summary className="mode-link">Modifier</summary>
                          <form action={updateAdminPricingCatalogConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="catalog_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
                            <label>
                              Nom
                              <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                            </label>
                            <label>
                              Annee scolaire
                              <input type="text" name="school_year_label" defaultValue={row.school_year_label || ""} maxLength={40} />
                            </label>
                            <label>
                              Date debut
                              <input type="date" name="effective_from" defaultValue={dateInputValue(row.effective_from)} required />
                            </label>
                            <label>
                              Date fin
                              <input type="date" name="effective_to" defaultValue={dateInputValue(row.effective_to)} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_default" defaultChecked={row.is_default} />
                              Defaut
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              Actif
                            </label>
                            <div className="row">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminPricingCatalogConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="catalog_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
                            <button type="submit" className="danger">Supprimer</button>
                          </form>
                        </details>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === "cgv" ? (
        <section className="card">
          <h3>CGV applicables aux devis</h3>
          <form action={createAdminCgvVersionConfigAction} className="grid cols-2 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("cgv")} />
            <label>
              Version
              <input type="text" name="version_label" required maxLength={80} placeholder="CGV 2026.1" />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Active
            </label>
            <label className="span-2">
              Contenu
              <textarea name="content" rows={8} required />
            </label>
            <div className="row span-2">
              <button type="submit">Ajouter la version</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {cgvVersions.length === 0 ? <p className="muted">Aucune version CGV.</p> : null}
            {cgvVersions.map((row) => (
              <article key={row.id} className="item">
                <div className="row spread wrap gap-sm">
                  <div>
                    <strong>{row.version_label}</strong>
                    <p className="muted">Maj: {dateTimeLabel(row.updated_at)}</p>
                  </div>
                  <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Active" : "Inactive"}</span>
                </div>
                <p className="muted top-gap-sm">{row.content.slice(0, 220)}{row.content.length > 220 ? "..." : ""}</p>
                <details>
                  <summary className="mode-link">Modifier</summary>
                  <form action={updateAdminCgvVersionConfigAction} className="grid config-form-grid top-gap-sm">
                    <input type="hidden" name="cgv_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("cgv")} />
                    <label>
                      Version
                      <input type="text" name="version_label" defaultValue={row.version_label} required maxLength={80} />
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                      Active
                    </label>
                    <label>
                      Contenu
                      <textarea name="content" rows={8} defaultValue={row.content} required />
                    </label>
                    <div className="row">
                      <button type="submit">Enregistrer</button>
                    </div>
                  </form>
                  <form action={deleteAdminCgvVersionConfigAction} className="row top-gap-sm">
                    <input type="hidden" name="cgv_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("cgv")} />
                    <button type="submit" className="danger">Supprimer</button>
                  </form>
                </details>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {tab === "templates" ? (
        <section className="card">
          <h3>Templates de devis</h3>
          <p className="muted">
            Variables disponibles: {templateVariables.length} · <Link className="mode-link" href={buildQuotesConfigHref("variables")}>Voir les variables</Link>
          </p>
          <form action={createAdminQuoteTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("templates")} />
            <label>
              Code
              <input type="text" name="code" required maxLength={80} placeholder="QUOTE_DEFAULT_FR" />
            </label>
            <label>
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Template devis FR" />
            </label>
            <label>
              Langue
              <input type="text" name="language" defaultValue="fr" required maxLength={8} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_default" />
              Template par defaut
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <div className="span-2">
              <QuoteTemplateEditor
                subjectName="subject_template"
                bodyName="body_template"
                defaultSubject="Votre devis {quote_number} Piano Academie"
                defaultBody={"Bonjour {recipient_name},\n\nVotre devis {quote_number} est pret.\nTotal: {total_ttc} {currency}.\nExpiration: {expires_at}."}
                variables={templateVariables}
              />
            </div>
            <div className="row span-2">
              <button type="submit">Ajouter le template</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {quoteTemplates.length === 0 ? <p className="muted">Aucun template de devis.</p> : null}
            {quoteTemplates.map((row) => (
              <article key={row.id} className="item">
                <div className="row spread wrap gap-sm">
                  <div>
                    <strong>{row.name}</strong>
                    <p className="muted">{row.code} · langue {row.language.toUpperCase()} · Maj: {dateTimeLabel(row.updated_at)}</p>
                  </div>
                  <div className="row wrap gap-sm">
                    {row.is_default ? <span className="badge">Defaut</span> : null}
                    <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span>
                  </div>
                </div>
                <details>
                  <summary className="mode-link">Modifier</summary>
                  <form action={updateAdminQuoteTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                    <input type="hidden" name="template_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("templates")} />
                    <label>
                      Code
                      <input type="text" name="code" defaultValue={row.code} required maxLength={80} />
                    </label>
                    <label>
                      Nom
                      <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                    </label>
                    <label>
                      Langue
                      <input type="text" name="language" defaultValue={row.language} required maxLength={8} />
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="is_default" defaultChecked={row.is_default} />
                      Template par defaut
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                      Actif
                    </label>
                    <div className="span-2">
                      <QuoteTemplateEditor
                        subjectName="subject_template"
                        bodyName="body_template"
                        defaultSubject={row.subject_template}
                        defaultBody={row.body_template}
                        variables={templateVariables}
                      />
                    </div>
                    <div className="row span-2">
                      <button type="submit">Enregistrer</button>
                    </div>
                  </form>
                  <form action={deleteAdminQuoteTemplateConfigAction} className="row top-gap-sm">
                    <input type="hidden" name="template_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("templates")} />
                    <button type="submit" className="danger">Supprimer</button>
                  </form>
                </details>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {tab === "solfege" ? (
        <section className="card">
          <h3>Creneaux solfege par niveau</h3>
          <p className="muted">Formats attendus: jours = 0,1,2 (0 dimanche) ; creneaux = 09:00-09:30, 14:00-14:45.</p>
          <form action={upsertAdminSolfegeLevelRuleConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
            <label>
              Niveau
              <select name="level_code" defaultValue="1">
                <option value="1">Niveau 1</option>
                <option value="2">Niveau 2</option>
                <option value="3">Niveau 3</option>
                <option value="4">Niveau 4</option>
                <option value="5">Niveau 5</option>
              </select>
            </label>
            <label>
              Duree (min)
              <input type="number" name="duration_minutes" min={10} max={180} defaultValue={30} required />
            </label>
            <label>
              Local (optionnel)
              <select name="location_id" defaultValue="">
                <option value="">Tous</option>
                {locations.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>
              Modalite
              <select name="modality" defaultValue="ANY">
                <option value="ANY">Tous</option>
                <option value="ONLINE">En ligne</option>
                <option value="ONSITE">Presentiel</option>
              </select>
            </label>
            <label className="span-2">
              Jours autorises (0..6)
              <input type="text" name="allowed_weekdays_csv" placeholder="1,3,5" />
            </label>
            <label className="span-2">
              Creneaux autorises (HH:MM-HH:MM)
              <input type="text" name="allowed_time_slots_csv" placeholder="09:00-09:30, 14:00-14:45" />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Active
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter / mettre a jour</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Niveau</th>
                  <th>Duree</th>
                  <th>Jours</th>
                  <th>Creneaux</th>
                  <th>Local</th>
                  <th>Mode</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {solfegeRules.length === 0 ? (
                  <tr><td colSpan={8}><p className="muted">Aucune regle solfege.</p></td></tr>
                ) : (
                  solfegeRules.map((row) => (
                    <tr key={row.id}>
                      <td>Niveau {row.level_code}</td>
                      <td>{row.duration_minutes} min</td>
                      <td>{weekdaysLabel(row.allowed_weekdays)}</td>
                      <td>{solfegeSlotsCsv(row.allowed_time_slots) || "-"}</td>
                      <td>{row.location_id ? (locationById.get(row.location_id) || row.location_id) : "Tous"}</td>
                      <td>{modalityLabel(row.modality)}</td>
                      <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Active" : "Inactive"}</span></td>
                      <td>
                        <details>
                          <summary className="mode-link">Modifier</summary>
                          <form action={upsertAdminSolfegeLevelRuleConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
                            <label>
                              Niveau
                              <input type="text" name="level_code" defaultValue={row.level_code} maxLength={10} required />
                            </label>
                            <label>
                              Duree (min)
                              <input type="number" name="duration_minutes" min={10} max={180} defaultValue={row.duration_minutes} required />
                            </label>
                            <label>
                              Local
                              <select name="location_id" defaultValue={row.location_id || ""}>
                                <option value="">Tous</option>
                                {locations.map((location) => (
                                  <option key={location.id} value={location.id}>{location.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Modalite
                              <select name="modality" defaultValue={(row.modality || "ANY").toUpperCase()}>
                                <option value="ANY">Tous</option>
                                <option value="ONLINE">En ligne</option>
                                <option value="ONSITE">Presentiel</option>
                              </select>
                            </label>
                            <label>
                              Jours autorises (0..6)
                              <input type="text" name="allowed_weekdays_csv" defaultValue={row.allowed_weekdays.join(",")} />
                            </label>
                            <label>
                              Creneaux autorises
                              <input type="text" name="allowed_time_slots_csv" defaultValue={solfegeSlotsCsv(row.allowed_time_slots)} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              Active
                            </label>
                            <div className="row">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminSolfegeLevelRuleConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="rule_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
                            <button type="submit" className="danger">Supprimer</button>
                          </form>
                        </details>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === "variables" ? (
        <section className="card">
          <h3>Variables de devis disponibles</h3>
          <p className="muted">Variables supportees dans les templates de devis.</p>
          <div className="list">
            {templateVariables.map((item) => (
              <article key={item.key} className="item">
                <p><code>{`{${item.key}}`}</code></p>
                <p className="muted">{item.label} - {item.description}</p>
                <p className="muted">Exemple: {item.example}</p>
              </article>
            ))}
          </div>
          <div className="row top-gap-sm">
            <Link className="ghost" href={returnPath}>Actualiser</Link>
          </div>
        </section>
      ) : null}
    </section>
  );
}
