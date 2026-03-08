import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminQuoteTemplateV2ConfigAction,
  createAdminTermsTemplateConfigAction,
  createAdminQuoteDocumentBindingConfigAction,
  createAdminPaymentPlanConfigAction,
  createAdminPricingCatalogConfigAction,
  createAdminQuoteTypeConfigAction,
  deleteAdminQuoteTemplateV2ConfigAction,
  deleteAdminTermsTemplateConfigAction,
  deleteAdminQuoteDocumentBindingConfigAction,
  deleteAdminPaymentPlanConfigAction,
  deleteAdminPricingCatalogConfigAction,
  deleteAdminQuoteTypeConfigAction,
  deleteAdminSolfegeLevelRuleConfigAction,
  updateAdminQuoteTemplateV2ConfigAction,
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
import type { AdminActivityOut, LocationOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type QuotesConfigTab =
  | "types"
  | "catalogs"
  | "payment_plans"
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

const PAYMENT_PLAN_PRESET_OPTIONS: Array<{ value: string; label: string; payment_method: string; schedule_type: string }> = [
  { value: "Carte bancaire", label: "Carte bancaire", payment_method: "CARD", schedule_type: "single" },
  { value: "Carte bancaire mensuelle", label: "Carte bancaire mensuelle", payment_method: "CARD_MONTHLY", schedule_type: "monthly" },
  { value: "Cheque en 1 fois", label: "Cheque en 1 fois", payment_method: "CHECK", schedule_type: "single" },
  { value: "Cheque en 2 fois", label: "Cheque en 2 fois", payment_method: "CHECK", schedule_type: "split_2" },
  { value: "Cheque en 4 fois", label: "Cheque en 4 fois", payment_method: "CHECK", schedule_type: "split_4" },
  { value: "Virement bancaire", label: "Virement bancaire", payment_method: "BANK_TRANSFER", schedule_type: "single" },
  { value: "Especes", label: "Especes", payment_method: "CASH", schedule_type: "single" },
  { value: "4 fois avec frais", label: "4 fois avec frais", payment_method: "CARD_4X_FEES", schedule_type: "split_4" },
];

const PAYMENT_SCHEDULE_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "single", label: "Paiement unitaire" },
  { value: "split_2", label: "Paiement en 2 fois" },
  { value: "split_3", label: "Paiement en 3 fois" },
  { value: "split_4", label: "Paiement en 4 fois" },
  { value: "monthly", label: "Paiement mensuel" },
];

function weekdaysLabel(days: number[]): string {
  if (!days.length) {
    return "Tous";
  }
  return days
    .map((day) => WEEKDAY_OPTIONS.find((option) => option.value === day)?.label ?? String(day))
    .join(", ");
}

function paymentScheduleTypeLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  const fromCatalog = PAYMENT_SCHEDULE_TYPE_OPTIONS.find((item) => item.value === normalized)?.label;
  return (fromCatalog ?? value) || "-";
}

function paymentMethodLabel(value: string): string {
  const normalized = value.trim().toUpperCase();
  if (!normalized) return "-";
  if (normalized === "CARD") return "Carte bancaire";
  if (normalized === "CARD_MONTHLY") return "Carte bancaire mensuelle";
  if (normalized === "CHECK") return "Cheque";
  if (normalized === "BANK_TRANSFER") return "Virement bancaire";
  if (normalized === "CASH") return "Especes";
  if (normalized === "CARD_4X_FEES") return "4 fois avec frais";
  return value;
}

function paymentInstallmentCount(rules: Record<string, unknown>): string {
  const raw = Number.parseInt(String(rules.installment_count ?? ""), 10);
  if (!Number.isFinite(raw) || raw <= 0) {
    return "-";
  }
  return String(raw);
}

function paymentFeePercent(rules: Record<string, unknown>): string {
  const raw = Number.parseFloat(String(rules.fee_percent ?? ""));
  if (!Number.isFinite(raw) || raw <= 0) {
    return "0 %";
  }
  return `${raw.toFixed(2).replace(".", ",")} %`;
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
      const weekdayRaw = Number.parseInt(String(slot.weekday ?? ""), 10);
      const weekdayText = Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6
        ? `${WEEKDAY_OPTIONS.find((item) => item.value === weekdayRaw)?.label ?? weekdayRaw}`
        : "";
      const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
      const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
      if (!start || !end) {
        return "";
      }
      return `${weekdayText ? `${weekdayText} ` : ""}${start}-${end}`;
    })
    .filter(Boolean)
    .join(", ");
}

function solfegeSlotRows(
  slots: Array<Record<string, unknown>>,
  weekdays: number[],
): Array<{ weekday: number; start: string; end: string }> {
  const out: Array<{ weekday: number; start: string; end: string }> = [];
  for (const slot of slots) {
    const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
    const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
    if (!start || !end) {
      continue;
    }
    const weekdayRaw = Number.parseInt(String(slot.weekday ?? ""), 10);
    if (Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6) {
      out.push({ weekday: weekdayRaw, start, end });
      continue;
    }
    const fallbackWeekday = weekdays.find((day) => Number.isFinite(day) && day >= 0 && day <= 6);
    if (fallbackWeekday !== undefined) {
      out.push({ weekday: fallbackWeekday, start, end });
    }
  }
  return out;
}

export default async function AdminQuoteConfigurationPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const rawTab = readParam(params, "tab").trim().toLowerCase();
  if (rawTab === "cgv" || rawTab === "templates") {
    const mapped = rawTab === "cgv" ? "doc_terms" : "doc_templates";
    redirect(buildQuotesConfigHref(mapped));
  }
  if (rawTab === "calendars") {
    const redirectParams = new URLSearchParams();
    const ok = readParam(params, "ok").trim();
    const error = readParam(params, "error").trim();
    if (ok) {
      redirectParams.set("ok", ok);
    }
    if (error) {
      redirectParams.set("error", error);
    }
    const suffix = redirectParams.toString();
    redirect(suffix ? `/admin/config/calendars?${suffix}` : "/admin/config/calendars");
  }
  const tab = parseTab(rawTab);
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  const [
    quoteTypesResult,
    catalogsResult,
    paymentPlansResult,
    templateVariablesResult,
    solfegeRulesResult,
    locationsResult,
    activitiesResult,
    quoteTemplatesV2Result,
    termsTemplatesResult,
    quoteDocumentBindingsResult,
  ] = await Promise.all([
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<QuoteTemplateVariableOut[]>("/api/v1/quote-template-variables", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
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
  const paymentPlans = paymentPlansResult.ok
    ? paymentPlansResult.data
    : (() => {
        loadErrors.push(`Plans de paiement: ${paymentPlansResult.message}`);
        return [] as PaymentPlanOut[];
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
  const activities = activitiesResult.ok
    ? activitiesResult.data
    : (() => {
        loadErrors.push(`Activites: ${activitiesResult.message}`);
        return [] as AdminActivityOut[];
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
        loadErrors.push(`Regles d association documentaire: ${quoteDocumentBindingsResult.message}`);
        return [] as QuoteDocumentBindingOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const activityFamilies = Array.from(
    new Set(
      activities
        .map((row) => String(row.service_code || "").trim())
        .filter((value) => value.length > 0),
    ),
  ).sort((a, b) => a.localeCompare(b, "fr-FR"));
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

      {okMessage || errorMessage ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={returnPath} aria-label="Fermer">
              ×
            </a>
            <h3 className="modal-title">{errorMessage ? "Erreur" : "Confirmation"}</h3>
            {okMessage ? <section className="flash-ok top-gap-sm">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err top-gap-sm">{errorMessage}</section> : null}
            <div className="row modal-actions-end top-gap-sm">
              <a className="ghost" href={returnPath}>Fermer</a>
            </div>
          </article>
        </section>
      ) : null}
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
          <Link className={`config-sub-link ${tab === "doc_templates" ? "active" : ""}`} href={buildQuotesConfigHref("doc_templates")}>Modeles de devis</Link>
          <Link className={`config-sub-link ${tab === "doc_terms" ? "active" : ""}`} href={buildQuotesConfigHref("doc_terms")}>Modeles de CGV</Link>
          <Link className={`config-sub-link ${tab === "doc_bindings" ? "active" : ""}`} href={buildQuotesConfigHref("doc_bindings")}>Regles d association documentaire</Link>
          <Link className={`config-sub-link ${tab === "variables" ? "active" : ""}`} href={buildQuotesConfigHref("variables")}>Variables documentaires</Link>
          <Link className={`config-sub-link ${tab === "solfege" ? "active" : ""}`} href={buildQuotesConfigHref("solfege")}>Creneaux de solfege</Link>
          <Link className="config-sub-link" href="/admin/config/calendars">Calendriers scolaires</Link>
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
          <p className="muted">Configuration metier guidee: libelle commercial, methode, type d echeancier et frais. Le code et les regles techniques sont generes automatiquement.</p>
          <form action={createAdminPaymentPlanConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
            <label className="span-2">
              Plan de paiement / libelle commercial
              <select name="plan_label_preset" defaultValue="Carte bancaire" required>
                <option value="">Selectionner</option>
                {PAYMENT_PLAN_PRESET_OPTIONS.map((option) => (
                  <option key={`preset-create-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              Methode de paiement
              <select name="payment_method" defaultValue="CARD" required>
                <option value="CARD">Carte bancaire</option>
                <option value="CARD_MONTHLY">Carte bancaire mensuelle</option>
                <option value="CHECK">Cheque</option>
                <option value="BANK_TRANSFER">Virement bancaire</option>
                <option value="CASH">Especes</option>
                <option value="CARD_4X_FEES">4 fois avec frais</option>
              </select>
            </label>
            <label>
              Type d echeancier
              <select name="schedule_type" defaultValue="single" required>
                {PAYMENT_SCHEDULE_TYPE_OPTIONS.map((option) => (
                  <option key={`schedule-create-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              Frais (%)
              <input type="number" name="fee_percent" min={0} max={100} step="0.01" defaultValue="0" />
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
                  <th>Libelle</th>
                  <th>Methode</th>
                  <th>Echeancier</th>
                  <th>Echeances</th>
                  <th>Frais</th>
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
                      <td>
                        <strong>{row.name}</strong>
                        <div className="muted"><code>{row.code}</code></div>
                      </td>
                      <td>{paymentMethodLabel(row.payment_method)}</td>
                      <td>{paymentScheduleTypeLabel(row.schedule_type)}</td>
                      <td>{paymentInstallmentCount(row.schedule_rules || {})}</td>
                      <td>{paymentFeePercent(row.schedule_rules || {})}</td>
                      <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span></td>
                      <td>
                        <details>
                          <summary className="mode-link">Modifier</summary>
                          <form action={updateAdminPaymentPlanConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="plan_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
                            <input type="hidden" name="name_current" value={row.name} />
                            <label className="span-2">
                              Plan de paiement / libelle commercial
                              <select name="plan_label_preset" defaultValue={PAYMENT_PLAN_PRESET_OPTIONS.some((item) => item.value === row.name) ? row.name : ""}>
                                <option value="">Conserver actuel</option>
                                {PAYMENT_PLAN_PRESET_OPTIONS.map((option) => (
                                  <option key={`preset-edit-${row.id}-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label className="span-2">
                              Libelle personnalise (optionnel)
                              <input type="text" name="name_custom" maxLength={180} placeholder={row.name} />
                            </label>
                            <label>
                              Methode de paiement
                              <select name="payment_method" defaultValue={row.payment_method} required>
                                {!["CARD", "CARD_MONTHLY", "CHECK", "BANK_TRANSFER", "CASH", "CARD_4X_FEES"].includes(row.payment_method) ? (
                                  <option value={row.payment_method}>{row.payment_method}</option>
                                ) : null}
                                <option value="CARD">Carte bancaire</option>
                                <option value="CARD_MONTHLY">Carte bancaire mensuelle</option>
                                <option value="CHECK">Cheque</option>
                                <option value="BANK_TRANSFER">Virement bancaire</option>
                                <option value="CASH">Especes</option>
                                <option value="CARD_4X_FEES">4 fois avec frais</option>
                              </select>
                            </label>
                            <label>
                              Type d echeancier
                              <select name="schedule_type" defaultValue={row.schedule_type} required>
                                {!PAYMENT_SCHEDULE_TYPE_OPTIONS.some((option) => option.value === row.schedule_type) ? (
                                  <option value={row.schedule_type}>{row.schedule_type}</option>
                                ) : null}
                                {PAYMENT_SCHEDULE_TYPE_OPTIONS.map((option) => (
                                  <option key={`schedule-edit-${row.id}-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Frais (%)
                              <input
                                type="number"
                                name="fee_percent"
                                min={0}
                                max={100}
                                step="0.01"
                                defaultValue={String(row.schedule_rules?.fee_percent ?? 0)}
                              />
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

      {tab === "doc_templates" ? (
        <section className="card">
          <h3>Modeles de devis (document principal)</h3>
          <p className="muted">
            Ce bloc gere le document devis (rendu admin, page publique et PDF). Les codes techniques sont geres automatiquement.
          </p>
          <form action={createAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
            <div className="span-2">
              <h4>Etape 1 · Fiche du modele</h4>
            </div>
            <label>
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="Template enfant collectif" />
            </label>
            <label>
              Cible
              <input type="text" name="target" maxLength={40} placeholder="adult | child_collective | eveil" />
            </label>
            <label>
              Langue
              <select name="language" defaultValue="fr" required>
                <option value="fr">Français</option>
              </select>
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
              <h4>Etape 2 · Contenu documentaire</h4>
            </div>
            <div className="span-2">
              <QuoteTemplateEditor
                subjectName="subject_template"
                bodyName="body_template"
                defaultSubject="Votre devis {quote_number} Piano Academie"
                defaultBody={
                  "<h1>Devis {quote_number}</h1><p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p><p><strong>Annee scolaire:</strong> {school_year_label}</p>{prospect_identity_block_html}<h2>Activites</h2>{services_table_html}<h2>Produits</h2>{products_table_html}<h2>Kits</h2>{kits_table_html}<h2>Paiement</h2>{payment_method_block_html}{payment_schedule_table_html}{solfege_block_html}{masterclass_block_html}{pass_recup_block_html}<h2>Calendrier des cours</h2><p>{calendar_summary}</p>{calendar_activity_semesters_html}<p><strong>Total HT:</strong> {total_ht} {currency}</p><p><strong>TVA ({vat_rate}%):</strong> {vat_amount} {currency}</p><p><strong>Total TTC:</strong> {total_ttc} {currency}</p><p><strong>Expiration:</strong> {expires_at}</p>"
                }
                variables={templateVariables}
              />
            </div>
            <div className="row span-2">
              <button type="submit">Enregistrer le modele de devis</button>
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
                        cible {row.target || "-"} · langue {row.language.toUpperCase()} · v{row.current_version_number ?? "-"} · Maj: {dateTimeLabel(row.updated_at)}
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
                      <input type="hidden" name="code" value={row.code} />
                      <input type="hidden" name="template_type" value={row.template_type || "quote_body"} />
                      <div className="span-2">
                        <h4>Etape 1 · Fiche du modele</h4>
                      </div>
                      <label>
                        Nom
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        Cible
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        Langue
                        <select name="language" defaultValue={row.language || "fr"} required>
                          <option value="fr">Français</option>
                        </select>
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
                        <h4>Etape 2 · Contenu documentaire</h4>
                      </div>
                      <div className="span-2">
                        <QuoteTemplateEditor
                          subjectName="subject_template"
                          bodyName="body_template"
                          defaultSubject={prefill?.subject || `Devis {quote_number}`}
                          defaultBody={
                            prefill?.body ||
                            "<h1>Devis {quote_number}</h1><p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p>{prospect_identity_block_html}<h2>Activites</h2>{services_table_html}<h2>Produits</h2>{products_table_html}<h2>Kits</h2>{kits_table_html}<h2>Paiement</h2>{payment_method_block_html}{payment_schedule_table_html}<h2>Calendrier des cours</h2>{calendar_activity_semesters_html}<p>Total TTC: {total_ttc} {currency}</p>"
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
              Nom
              <input type="text" name="name" required maxLength={180} placeholder="CGV enfants collectifs" />
            </label>
            <label>
              Cible
              <input type="text" name="target" maxLength={40} placeholder="adult | child_collective | eveil" />
            </label>
            <label>
              Langue
              <select name="language" defaultValue="fr" required>
                <option value="fr">Français</option>
              </select>
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
              <button type="submit">Enregistrer le modele de CGV</button>
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
                        cible {row.target || "-"} · langue {row.language.toUpperCase()} · v{row.current_version_number ?? "-"} · Maj: {dateTimeLabel(row.updated_at)}
                      </p>
                    </div>
                    <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.status}</span>
                  </div>
                  <details>
                    <summary className="mode-link">Modifier / publier nouvelle version</summary>
                    <form action={updateAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <input type="hidden" name="current_code" value={row.code} />
                      <label>
                        Nom
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        Cible
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        Langue
                        <select name="language" defaultValue={row.language || "fr"} required>
                          <option value="fr">Français</option>
                        </select>
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
              <select name="activity_family" defaultValue="">
                <option value="">Toutes</option>
                {activityFamilies.map((family) => (
                  <option key={`binding-family-create-${family}`} value={family}>{family}</option>
                ))}
              </select>
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
                              <select name="activity_family" defaultValue={row.activity_family || ""}>
                                <option value="">Toutes</option>
                                {activityFamilies.map((family) => (
                                  <option key={`binding-family-edit-${row.id}-${family}`} value={family}>{family}</option>
                                ))}
                              </select>
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
            <div className="span-4">
              <p className="muted">Lignes de creneaux (jour + heure de debut). L heure de fin est calculee automatiquement avec la duree.</p>
              <div className="grid cols-4 top-gap-sm">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={`create-solfege-slot-${index}`} className="grid cols-2">
                    <label>
                      Jour
                      <select name="slot_weekday" defaultValue="">
                        <option value="">-</option>
                        {WEEKDAY_OPTIONS.map((day) => (
                          <option key={`create-solfege-slot-day-${index}-${day.value}`} value={day.value}>{day.label}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Heure debut
                      <input type="time" name="slot_start_time" defaultValue="" />
                    </label>
                  </div>
                ))}
              </div>
            </div>
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
                            <div className="span-4">
                              <p className="muted">Lignes de creneaux (jour + heure de debut). Duree heritee du niveau.</p>
                              <div className="grid cols-4 top-gap-sm">
                                {Array.from({ length: Math.max(5, solfegeSlotRows(row.allowed_time_slots, row.allowed_weekdays).length) }).map((_, index) => {
                                  const slot = solfegeSlotRows(row.allowed_time_slots, row.allowed_weekdays)[index];
                                  return (
                                    <div key={`${row.id}-slot-edit-${index}`} className="grid cols-2">
                                      <label>
                                        Jour
                                        <select name="slot_weekday" defaultValue={slot ? String(slot.weekday) : ""}>
                                          <option value="">-</option>
                                          {WEEKDAY_OPTIONS.map((day) => (
                                            <option key={`${row.id}-slot-day-${index}-${day.value}`} value={day.value}>{day.label}</option>
                                          ))}
                                        </select>
                                      </label>
                                      <label>
                                        Heure debut
                                        <input type="time" name="slot_start_time" defaultValue={slot?.start || ""} />
                                      </label>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
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
