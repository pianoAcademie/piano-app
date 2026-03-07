import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminQuoteTemplateConfigAction,
  createAdminQuoteTemplateV2ConfigAction,
  createAdminCgvVersionConfigAction,
  createAdminTermsTemplateConfigAction,
  createAdminQuoteDocumentBindingConfigAction,
  createAdminPaymentPlanConfigAction,
  createAdminPricingCatalogConfigAction,
  createAdminQuoteTypeConfigAction,
  deleteAdminQuoteTemplateConfigAction,
  deleteAdminQuoteTemplateV2ConfigAction,
  deleteAdminCgvVersionConfigAction,
  deleteAdminTermsTemplateConfigAction,
  deleteAdminQuoteDocumentBindingConfigAction,
  deleteAdminPaymentPlanConfigAction,
  deleteAdminPricingCatalogConfigAction,
  deleteAdminQuoteTypeConfigAction,
  deleteAdminSolfegeLevelRuleConfigAction,
  updateAdminQuoteTemplateConfigAction,
  updateAdminQuoteTemplateV2ConfigAction,
  updateAdminCgvVersionConfigAction,
  updateAdminTermsTemplateConfigAction,
  updateAdminQuoteDocumentBindingConfigAction,
  updateAdminPaymentPlanConfigAction,
  updateAdminPricingCatalogConfigAction,
  updateAdminQuoteTypeConfigAction,
  upsertAdminSolfegeLevelRuleConfigAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import QuoteTemplateEditor from "../../../../components/quote-template-editor";
import WysiwygField from "../../../../components/wysiwyg-field";
import type { LocationOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type QuotesConfigTab =
  | "types"
  | "catalogs"
  | "payment_plans"
  | "cgv"
  | "templates"
  | "variables"
  | "solfege"
  | "doc_templates"
  | "doc_terms"
  | "doc_bindings";

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

type PaymentPlanOut = {
  id: string;
  code: string;
  name: string;
  payment_method: string;
  schedule_type: string;
  schedule_rules: Record<string, unknown>;
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

type QuoteTemplateV2Out = {
  id: string;
  code: string;
  name: string;
  template_type: string;
  target: string | null;
  language: string;
  description: string | null;
  is_active: boolean;
  is_default: boolean;
  status: string;
  current_version_id: string | null;
  current_version_number: number | null;
  updated_at: string;
};

type TermsTemplateOut = {
  id: string;
  code: string;
  name: string;
  terms_type: string;
  target: string | null;
  language: string;
  description: string | null;
  is_active: boolean;
  status: string;
  current_version_id: string | null;
  current_version_number: number | null;
  updated_at: string;
};

type QuoteDocumentBindingOut = {
  id: string;
  prospect_type: string | null;
  context_type: string | null;
  activity_family: string | null;
  activity_id: string | null;
  quote_type_id: string | null;
  language: string | null;
  currency: string | null;
  quote_template_id: string | null;
  quote_template_version_id: string | null;
  terms_template_id: string | null;
  terms_template_version_id: string | null;
  priority: number;
  is_active: boolean;
  notes: string | null;
  updated_at: string;
};

type QuoteTemplateVersionOut = {
  id: string;
  version_number: number;
  content_snapshot: Record<string, unknown>;
  is_active_version: boolean;
};

type TermsTemplateVersionOut = {
  id: string;
  version_number: number;
  content_snapshot: Record<string, unknown>;
  is_active_version: boolean;
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
  if (
    value === "catalogs" ||
    value === "payment_plans" ||
    value === "cgv" ||
    value === "templates" ||
    value === "variables" ||
    value === "solfege" ||
    value === "doc_templates" ||
    value === "doc_terms" ||
    value === "doc_bindings"
  ) {
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

const WEEKDAY_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: "Lundi" },
  { value: 1, label: "Mardi" },
  { value: 2, label: "Mercredi" },
  { value: 3, label: "Jeudi" },
  { value: 4, label: "Vendredi" },
  { value: 5, label: "Samedi" },
  { value: 6, label: "Dimanche" },
];

function weekdaysLabel(days: number[]): string {
  if (!days.length) {
    return "Tous";
  }
  return days
    .map((day) => WEEKDAY_OPTIONS.find((option) => option.value === day)?.label ?? String(day))
    .join(", ");
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

  const [
    quoteTypesResult,
    catalogsResult,
    paymentPlansResult,
    cgvVersionsResult,
    quoteTemplatesResult,
    templateVariablesResult,
    solfegeRulesResult,
    locationsResult,
    quoteTemplatesV2Result,
    termsTemplatesResult,
    quoteDocumentBindingsResult,
  ] = await Promise.all([
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<CgvVersionOut[]>("/api/v1/cgv-versions", {}, token),
    backendRequest<QuoteTemplateOut[]>("/api/v1/quote-templates", {}, token),
    backendRequest<QuoteTemplateVariableOut[]>("/api/v1/quote-template-variables", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<QuoteTemplateV2Out[]>("/api/v1/quote-templates-v2", {}, token),
    backendRequest<TermsTemplateOut[]>("/api/v1/terms-templates", {}, token),
    backendRequest<QuoteDocumentBindingOut[]>("/api/v1/quote-document-bindings", {}, token),
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
  const paymentPlans = paymentPlansResult.ok
    ? paymentPlansResult.data
    : (() => {
        loadErrors.push(`Plans de paiement: ${paymentPlansResult.message}`);
        return [] as PaymentPlanOut[];
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
  const quoteTemplatesV2 = quoteTemplatesV2Result.ok
    ? quoteTemplatesV2Result.data
    : (() => {
        loadErrors.push(`Templates documentaires: ${quoteTemplatesV2Result.message}`);
        return [] as QuoteTemplateV2Out[];
      })();
  const termsTemplates = termsTemplatesResult.ok
    ? termsTemplatesResult.data
    : (() => {
        loadErrors.push(`Templates CGV: ${termsTemplatesResult.message}`);
        return [] as TermsTemplateOut[];
      })();
  const quoteDocumentBindings = quoteDocumentBindingsResult.ok
    ? quoteDocumentBindingsResult.data
    : (() => {
        loadErrors.push(`Regles de selection documentaire: ${quoteDocumentBindingsResult.message}`);
        return [] as QuoteDocumentBindingOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const quoteTemplateVersionPrefill = new Map<string, { subject: string; body: string; versionNumber: number | null }>();
  const termsTemplateVersionPrefill = new Map<string, { versionLabel: string; content: string; versionNumber: number | null }>();
  await Promise.all(
    quoteTemplatesV2.map(async (row) => {
      const result = await backendRequest<QuoteTemplateVersionOut[]>(
        `/api/v1/quote-templates-v2/${encodeURIComponent(row.id)}/versions`,
        {},
        token,
      );
      if (!result.ok || result.data.length === 0) {
        return;
      }
      const active = result.data.find((item) => item.is_active_version) ?? result.data[0];
      quoteTemplateVersionPrefill.set(row.id, {
        subject: String(active.content_snapshot?.subject_template || ""),
        body: String(active.content_snapshot?.body_template || ""),
        versionNumber: active.version_number ?? null,
      });
    }),
  );
  await Promise.all(
    termsTemplates.map(async (row) => {
      const result = await backendRequest<TermsTemplateVersionOut[]>(
        `/api/v1/terms-templates/${encodeURIComponent(row.id)}/versions`,
        {},
        token,
      );
      if (!result.ok || result.data.length === 0) {
        return;
      }
      const active = result.data.find((item) => item.is_active_version) ?? result.data[0];
      termsTemplateVersionPrefill.set(row.id, {
        versionLabel: String(active.content_snapshot?.version_label || ""),
        content: String(active.content_snapshot?.content || ""),
        versionNumber: active.version_number ?? null,
      });
    }),
  );
  const returnPath = buildQuotesConfigHref(tab);

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Configuration Devis</h2>
            <p className="muted">Administrez les referentiels metier et documentaires des devis: types, catalogues, modeles, CGV et creneaux solfege.</p>
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
          <Link className={`config-sub-link ${tab === "payment_plans" ? "active" : ""}`} href={buildQuotesConfigHref("payment_plans")}>Plans de paiement</Link>
          <Link className={`config-sub-link ${tab === "cgv" ? "active" : ""}`} href={buildQuotesConfigHref("cgv")}>CGV</Link>
          <Link className={`config-sub-link ${tab === "templates" ? "active" : ""}`} href={buildQuotesConfigHref("templates")}>Templates email (legacy)</Link>
          <Link className={`config-sub-link ${tab === "doc_templates" ? "active" : ""}`} href={buildQuotesConfigHref("doc_templates")}>Modeles de devis</Link>
          <Link className={`config-sub-link ${tab === "doc_terms" ? "active" : ""}`} href={buildQuotesConfigHref("doc_terms")}>Modeles de CGV</Link>
          <Link className={`config-sub-link ${tab === "doc_bindings" ? "active" : ""}`} href={buildQuotesConfigHref("doc_bindings")}>Regles d association documentaire</Link>
          <Link className={`config-sub-link ${tab === "variables" ? "active" : ""}`} href={buildQuotesConfigHref("variables")}>Variables documentaires</Link>
          <Link className={`config-sub-link ${tab === "solfege" ? "active" : ""}`} href={buildQuotesConfigHref("solfege")}>Creneaux de solfege</Link>
        </nav>
      </section>

      {tab === "types" ? (
        <section className="card">
          <h3>Types de devis</h3>
          <p className="muted">Le code technique est genere automatiquement a partir du nom.</p>
          <form action={createAdminQuoteTypeConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
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

      {tab === "payment_plans" ? (
        <section className="card">
          <h3>Plans de paiement</h3>
          <p className="muted">Ce referentiel alimente le champ Plan de paiement dans la creation et l edition des devis.</p>
          <form action={createAdminPaymentPlanConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
            <label>
              Code
              <input type="text" name="code" required maxLength={60} placeholder="CHEQUE_2" />
            </label>
            <label>
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Cheque en 2 fois" />
            </label>
            <label>
              Methode de paiement
              <input type="text" name="payment_method" required maxLength={40} placeholder="CHEQUE_2" />
            </label>
            <label>
              Type d echeancier
              <input type="text" name="schedule_type" required maxLength={40} placeholder="fixed_months" />
            </label>
            <label className="span-4">
              Regles JSON
              <textarea name="schedule_rules_json" rows={4} defaultValue={"{}"} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter le plan</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Nom</th>
                  <th>Methode</th>
                  <th>Type</th>
                  <th>Regles</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paymentPlans.length === 0 ? (
                  <tr><td colSpan={7}><p className="muted">Aucun plan de paiement.</p></td></tr>
                ) : (
                  paymentPlans.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.code}</strong></td>
                      <td>{row.name}</td>
                      <td>{row.payment_method}</td>
                      <td>{row.schedule_type}</td>
                      <td><code>{JSON.stringify(row.schedule_rules || {})}</code></td>
                      <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span></td>
                      <td>
                        <details>
                          <summary className="mode-link">Modifier</summary>
                          <form action={updateAdminPaymentPlanConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="plan_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
                            <label>
                              Code
                              <input type="text" name="code" defaultValue={row.code} required maxLength={60} />
                            </label>
                            <label>
                              Nom
                              <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                            </label>
                            <label>
                              Methode de paiement
                              <input type="text" name="payment_method" defaultValue={row.payment_method} required maxLength={40} />
                            </label>
                            <label>
                              Type d echeancier
                              <input type="text" name="schedule_type" defaultValue={row.schedule_type} required maxLength={40} />
                            </label>
                            <label className="span-4">
                              Regles JSON
                              <textarea name="schedule_rules_json" rows={4} defaultValue={JSON.stringify(row.schedule_rules || {}, null, 2)} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              Actif
                            </label>
                            <div className="row">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminPaymentPlanConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="plan_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
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
            <div className="span-2">
              <WysiwygField
                name="content"
                label="Contenu"
                defaultValue="<p>Conditions generales de vente...</p>"
                helpText="Vous pouvez utiliser du HTML dans les CGV."
              />
            </div>
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
                    <WysiwygField
                      name="content"
                      label="Contenu"
                      defaultValue={row.content}
                      helpText="Version CGV editable en mode WYSIWYG ou HTML."
                    />
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
          <h3>Templates email devis (legacy)</h3>
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
                defaultBody={
                  "<h1>Devis {quote_number}</h1><p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p><p><strong>Type:</strong> {prospect_type_label}</p><p><strong>Parent:</strong> {parent_full_name}</p><p><strong>Eleve:</strong> {child_full_name}</p><h2>Activites</h2>{services_table_html}<h2>Produits</h2>{products_table_html}<h2>Kits</h2>{kits_table_html}<h2>Echeancier de paiement</h2>{payment_schedule_table_html}<h2>Calendrier des cours</h2>{calendar_table_html}<p><strong>Total HT:</strong> {total_ht} {currency}</p><p><strong>TVA ({vat_rate}%):</strong> {vat_amount} {currency}</p><p><strong>Total TTC:</strong> {total_ttc} {currency}</p><p><strong>Expiration:</strong> {expires_at}</p>"
                }
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

      {tab === "doc_templates" ? (
        <section className="card">
          <h3>Modeles de devis (document principal)</h3>
          <p className="muted">Chaque mise a jour publie une nouvelle version figee du template de devis.</p>
          <form action={createAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
            <label>
              Code
              <input type="text" name="code" required maxLength={80} placeholder="QUOTE_CHILD_COLLECTIVE" />
            </label>
            <label>
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Template enfant collectif" />
            </label>
            <label>
              Type
              <input type="text" name="template_type" defaultValue="quote_body" maxLength={40} />
            </label>
            <label>
              Cible
              <input type="text" name="target" maxLength={40} placeholder="adult | child_collective | eveil" />
            </label>
            <label>
              Langue
              <input type="text" name="language" defaultValue="fr" required maxLength={8} />
            </label>
            <label>
              Statut
              <select name="status" defaultValue="draft">
                <option value="draft">Brouillon</option>
                <option value="published">Publie</option>
                <option value="archived">Archive</option>
              </select>
            </label>
            <label className="span-2">
              Description interne
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_default" />
              Defaut (langue)
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <label className="checkline">
              <input type="checkbox" name="publish_now" defaultChecked />
              Publier maintenant
            </label>
            <label className="span-2">
              Changelog
              <input type="text" name="changelog" maxLength={2000} placeholder="v1 initiale" />
            </label>
            <div className="span-2">
              <QuoteTemplateEditor
                subjectName="subject_template"
                bodyName="body_template"
                defaultSubject="Votre devis {quote_number} Piano Academie"
                defaultBody={
                  "<h1>Devis {quote_number}</h1><p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p><p><strong>Type:</strong> {prospect_type_label}</p><p><strong>Parent:</strong> {parent_full_name}</p><p><strong>Eleve:</strong> {child_full_name}</p><h2>Activites</h2>{services_table_html}<h2>Produits</h2>{products_table_html}<h2>Kits</h2>{kits_table_html}<h2>Echeancier de paiement</h2>{payment_schedule_table_html}<h2>Calendrier des cours</h2>{calendar_table_html}<p><strong>Total HT:</strong> {total_ht} {currency}</p><p><strong>TVA ({vat_rate}%):</strong> {vat_amount} {currency}</p><p><strong>Total TTC:</strong> {total_ttc} {currency}</p><p><strong>Expiration:</strong> {expires_at}</p>"
                }
                variables={templateVariables}
              />
            </div>
            <div className="row span-2">
              <button type="submit">Creer le template documentaire</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {quoteTemplatesV2.length === 0 ? <p className="muted">Aucun template documentaire.</p> : null}
            {quoteTemplatesV2.map((row) => {
              const prefill = quoteTemplateVersionPrefill.get(row.id);
              return (
                <article key={row.id} className="item">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <strong>{row.name}</strong>
                      <p className="muted">
                        {row.code} · cible {row.target || "-"} · langue {row.language.toUpperCase()} · v{row.current_version_number ?? "-"} · Maj: {dateTimeLabel(row.updated_at)}
                      </p>
                    </div>
                    <div className="row wrap gap-sm">
                      {row.is_default ? <span className="badge">Defaut</span> : null}
                      <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.status}</span>
                    </div>
                  </div>
                  <details>
                    <summary className="mode-link">Modifier / publier nouvelle version</summary>
                    <form action={updateAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
                      <label>
                        Code
                        <input type="text" name="code" defaultValue={row.code} required maxLength={80} />
                      </label>
                      <label>
                        Nom
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        Type
                        <input type="text" name="template_type" defaultValue={row.template_type} maxLength={40} />
                      </label>
                      <label>
                        Cible
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        Langue
                        <input type="text" name="language" defaultValue={row.language} required maxLength={8} />
                      </label>
                      <label>
                        Statut
                        <select name="status" defaultValue={row.status || "draft"}>
                          <option value="draft">Brouillon</option>
                          <option value="published">Publie</option>
                          <option value="archived">Archive</option>
                        </select>
                      </label>
                      <label className="span-2">
                        Description interne
                        <input type="text" name="description" defaultValue={row.description ?? ""} maxLength={2000} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_default" defaultChecked={row.is_default} />
                        Defaut (langue)
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                        Actif
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="publish_now" defaultChecked />
                        Publier maintenant
                      </label>
                      <label className="span-2">
                        Changelog
                        <input type="text" name="changelog" maxLength={2000} placeholder="Nouvelle version" />
                      </label>
                      <div className="span-2">
                        <QuoteTemplateEditor
                          subjectName="subject_template"
                          bodyName="body_template"
                          defaultSubject={prefill?.subject || `Devis {quote_number}`}
                          defaultBody={
                            prefill?.body ||
                            "<h1>Devis {quote_number}</h1><h2>Activites</h2>{services_table_html}<h2>Produits</h2>{products_table_html}<h2>Kits</h2>{kits_table_html}<h2>Echeancier</h2>{payment_schedule_table_html}<h2>Calendrier</h2>{calendar_table_html}<p>Total TTC: {total_ttc} {currency}</p>"
                          }
                          variables={templateVariables}
                        />
                      </div>
                      <div className="row span-2">
                        <button type="submit">Enregistrer</button>
                      </div>
                    </form>
                    <form action={deleteAdminQuoteTemplateV2ConfigAction} className="row top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
                      <button type="submit" className="danger">Archiver</button>
                    </form>
                  </details>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {tab === "doc_terms" ? (
        <section className="card">
          <h3>Modeles de CGV (annexe juridique)</h3>
          <p className="muted">Les CGV sont versionnees et snapshottees dans chaque devis envoye.</p>
          <form action={createAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
            <label>
              Code
              <input type="text" name="code" required maxLength={80} placeholder="CGV_CHILD_COLLECTIVE" />
            </label>
            <label>
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="CGV enfants collectifs" />
            </label>
            <label>
              Type
              <input type="text" name="terms_type" defaultValue="cgv" maxLength={40} />
            </label>
            <label>
              Cible
              <input type="text" name="target" maxLength={40} placeholder="adult | child_collective | eveil" />
            </label>
            <label>
              Langue
              <input type="text" name="language" defaultValue="fr" required maxLength={8} />
            </label>
            <label>
              Statut
              <select name="status" defaultValue="draft">
                <option value="draft">Brouillon</option>
                <option value="published">Publie</option>
                <option value="archived">Archive</option>
              </select>
            </label>
            <label>
              Label version
              <input type="text" name="version_label" required maxLength={80} placeholder="CGV 2026.1" />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Actif
            </label>
            <label className="checkline">
              <input type="checkbox" name="publish_now" defaultChecked />
              Publier maintenant
            </label>
            <label className="span-2">
              Description interne
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="span-2">
              Changelog
              <input type="text" name="changelog" maxLength={2000} />
            </label>
            <div className="span-2">
              <WysiwygField
                name="content"
                label="Contenu CGV"
                defaultValue="<h2>Conditions generales de vente</h2><p>...</p>"
                helpText="Editez les CGV en mode WYSIWYG ou HTML."
              />
            </div>
            <div className="row span-2">
              <button type="submit">Creer le template CGV</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {termsTemplates.length === 0 ? <p className="muted">Aucun template CGV.</p> : null}
            {termsTemplates.map((row) => {
              const prefill = termsTemplateVersionPrefill.get(row.id);
              return (
                <article key={row.id} className="item">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <strong>{row.name}</strong>
                      <p className="muted">
                        {row.code} · {row.terms_type} · cible {row.target || "-"} · langue {row.language.toUpperCase()} · v{row.current_version_number ?? "-"} · Maj: {dateTimeLabel(row.updated_at)}
                      </p>
                    </div>
                    <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.status}</span>
                  </div>
                  <details>
                    <summary className="mode-link">Modifier / publier nouvelle version</summary>
                    <form action={updateAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <label>
                        Code
                        <input type="text" name="code" defaultValue={row.code} required maxLength={80} />
                      </label>
                      <label>
                        Nom
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        Type
                        <input type="text" name="terms_type" defaultValue={row.terms_type} maxLength={40} />
                      </label>
                      <label>
                        Cible
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        Langue
                        <input type="text" name="language" defaultValue={row.language} required maxLength={8} />
                      </label>
                      <label>
                        Statut
                        <select name="status" defaultValue={row.status || "draft"}>
                          <option value="draft">Brouillon</option>
                          <option value="published">Publie</option>
                          <option value="archived">Archive</option>
                        </select>
                      </label>
                      <label>
                        Label version
                        <input type="text" name="version_label" defaultValue={prefill?.versionLabel || "CGV"} required maxLength={80} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                        Actif
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="publish_now" defaultChecked />
                        Publier maintenant
                      </label>
                      <label className="span-2">
                        Description interne
                        <input type="text" name="description" defaultValue={row.description ?? ""} maxLength={2000} />
                      </label>
                      <label className="span-2">
                        Changelog
                        <input type="text" name="changelog" maxLength={2000} />
                      </label>
                      <div className="span-2">
                        <WysiwygField
                          name="content"
                          label="Contenu CGV"
                          defaultValue={prefill?.content || ""}
                          helpText="Toute modification publie une nouvelle version CGV."
                        />
                      </div>
                      <div className="row span-2">
                        <button type="submit">Enregistrer</button>
                      </div>
                    </form>
                    <form action={deleteAdminTermsTemplateConfigAction} className="row top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <button type="submit" className="danger">Archiver</button>
                    </form>
                  </details>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {tab === "doc_bindings" ? (
        <section className="card">
          <h3>Regles d association documentaire</h3>
          <p className="muted">Associez un contexte metier a un couple Modele de devis + Modele de CGV.</p>
          <form action={createAdminQuoteDocumentBindingConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
            <label>
              Type prospect
              <select name="prospect_type" defaultValue="">
                <option value="">Tous</option>
                <option value="adult">Adulte</option>
                <option value="child">Enfant</option>
              </select>
            </label>
            <label>
              Contexte
              <select name="context_type" defaultValue="">
                <option value="">Tous</option>
                <option value="acquisition">Acquisition</option>
                <option value="active_client">Client actif</option>
              </select>
            </label>
            <label>
              Famille activite
              <input type="text" name="activity_family" maxLength={80} placeholder="piano_collectif" />
            </label>
            <label>
              Langue
              <input type="text" name="language" maxLength={8} placeholder="fr" />
            </label>
            <label>
              Devise
              <input type="text" name="currency" maxLength={3} placeholder="EUR" />
            </label>
            <label>
              Type de devis
              <select name="quote_type_id" defaultValue="">
                <option value="">Tous</option>
                {quoteTypes.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="span-2">
              Template devis
              <select name="quote_template_id" defaultValue="">
                <option value="">Aucun</option>
                {quoteTemplatesV2.map((row) => (
                  <option key={row.id} value={row.id}>{row.name} ({row.language.toUpperCase()})</option>
                ))}
              </select>
            </label>
            <label className="span-2">
              Template CGV
              <select name="terms_template_id" defaultValue="">
                <option value="">Aucun</option>
                {termsTemplates.map((row) => (
                  <option key={row.id} value={row.id}>{row.name} ({row.language.toUpperCase()})</option>
                ))}
              </select>
            </label>
            <label>
              Priorite
              <input type="number" name="priority" min={0} max={9999} defaultValue={100} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Active
            </label>
            <label className="span-4">
              Notes
              <input type="text" name="notes" maxLength={2000} />
            </label>
            <div className="row span-4">
              <button type="submit">Ajouter la regle</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Scope</th>
                  <th>Template devis</th>
                  <th>Template CGV</th>
                  <th>Priorite</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {quoteDocumentBindings.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="muted">Aucune regle.</td>
                  </tr>
                ) : (
                  quoteDocumentBindings.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.prospect_type || "Tous"}</strong>
                        <div className="muted">{row.context_type || "Tous contextes"} · {row.language || "toutes langues"} · {row.currency || "toutes devises"}</div>
                        <div className="muted">Activite: {row.activity_family || "toutes"} · Type devis: {row.quote_type_id ? quoteTypes.find((item) => item.id === row.quote_type_id)?.name || row.quote_type_id : "tous"}</div>
                      </td>
                      <td>{quoteTemplatesV2.find((item) => item.id === row.quote_template_id)?.name || "-"}</td>
                      <td>{termsTemplates.find((item) => item.id === row.terms_template_id)?.name || "-"}</td>
                      <td>{row.priority}</td>
                      <td>
                        <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Active" : "Inactive"}</span>
                      </td>
                      <td>
                        <details>
                          <summary className="mode-link">Modifier</summary>
                          <form action={updateAdminQuoteDocumentBindingConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="binding_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
                            <label>
                              Type prospect
                              <select name="prospect_type" defaultValue={row.prospect_type || ""}>
                                <option value="">Tous</option>
                                <option value="adult">Adulte</option>
                                <option value="child">Enfant</option>
                              </select>
                            </label>
                            <label>
                              Contexte
                              <select name="context_type" defaultValue={row.context_type || ""}>
                                <option value="">Tous</option>
                                <option value="acquisition">Acquisition</option>
                                <option value="active_client">Client actif</option>
                              </select>
                            </label>
                            <label>
                              Famille activite
                              <input type="text" name="activity_family" defaultValue={row.activity_family || ""} maxLength={80} />
                            </label>
                            <label>
                              Langue
                              <input type="text" name="language" defaultValue={row.language || ""} maxLength={8} />
                            </label>
                            <label>
                              Devise
                              <input type="text" name="currency" defaultValue={row.currency || ""} maxLength={3} />
                            </label>
                            <label>
                              Type de devis
                              <select name="quote_type_id" defaultValue={row.quote_type_id || ""}>
                                <option value="">Tous</option>
                                {quoteTypes.map((qt) => (
                                  <option key={qt.id} value={qt.id}>{qt.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Template devis
                              <select name="quote_template_id" defaultValue={row.quote_template_id || ""}>
                                <option value="">Aucun</option>
                                {quoteTemplatesV2.map((tpl) => (
                                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Template CGV
                              <select name="terms_template_id" defaultValue={row.terms_template_id || ""}>
                                <option value="">Aucun</option>
                                {termsTemplates.map((tpl) => (
                                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Priorite
                              <input type="number" name="priority" min={0} max={9999} defaultValue={row.priority} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              Active
                            </label>
                            <label>
                              Notes
                              <input type="text" name="notes" defaultValue={row.notes || ""} maxLength={2000} />
                            </label>
                            <div className="row">
                              <button type="submit">Enregistrer</button>
                            </div>
                          </form>
                          <form action={deleteAdminQuoteDocumentBindingConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="binding_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
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

      {tab === "solfege" ? (
        <section className="card">
          <h3>Creneaux de solfege par niveau</h3>
          <p className="muted">Configurez les jours et creneaux en langage metier (ex: mardi 17:05-17:35).</p>
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
            <fieldset className="span-2">
              <legend>Jours autorises</legend>
              <div className="row wrap gap-sm">
                {WEEKDAY_OPTIONS.map((day) => (
                  <label key={`create-day-${day.value}`} className="checkline">
                    <input type="checkbox" name="allowed_weekday" value={day.value} />
                    {day.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="span-2">
              Creneaux autorises (HH:MM-HH:MM)
              <input type="text" name="allowed_time_slots_csv" placeholder="17:05-17:35, 18:05-18:35" />
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
                            <fieldset>
                              <legend>Jours autorises</legend>
                              <div className="row wrap gap-sm">
                                {WEEKDAY_OPTIONS.map((day) => (
                                  <label key={`${row.id}-day-${day.value}`} className="checkline">
                                    <input
                                      type="checkbox"
                                      name="allowed_weekday"
                                      value={day.value}
                                      defaultChecked={row.allowed_weekdays.includes(day.value)}
                                    />
                                    {day.label}
                                  </label>
                                ))}
                              </div>
                            </fieldset>
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
