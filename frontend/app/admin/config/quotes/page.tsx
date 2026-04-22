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
  hardDeleteAdminQuoteTemplateV2ConfigAction,
  deleteAdminTermsTemplateConfigAction,
  hardDeleteAdminTermsTemplateConfigAction,
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
import { normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
import type { AdminActivityOut, AdminFormulaOut, LocationOut, UserOut } from "../../../../lib/types";

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
  formula_id: string | null;
  formula_name: string | null;
  school_year_label: string | null;
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

type TypeformFormConfigOut = {
  id: string;
  typeform_form_id: string;
  source_code: string;
  location_code: string;
  school_year_label: string;
  audience_segment: string;
  default_pricing_catalog_id: string | null;
  configuration_json: Record<string, unknown>;
  is_active: boolean;
  updated_at: string;
};

type PricingActivityPriceOut = {
  id: string;
  catalog_id: string;
  activity_id: string;
  location_id: string | null;
  student_category: string | null;
  pricing_unit: string;
  unit_price_ttc: string;
  currency: string;
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

type TypeformTemplatePricingRow = {
  key: string;
  formId: string;
  formSourceCode: string;
  formLabel: string;
  locationCode: string;
  itemLabel: string;
  itemCode: string | null;
  mode: "override" | "fallback";
  amountTtc: number;
  conditionsLabel: string;
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

function dateTimeLabel(value: string | null, language: UiLanguage = "fr"): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(language === "en" ? "en-US" : "fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function templateStatusLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "published") {
    return uiText(language, "admin.quote_config.status_published");
  }
  if (normalized === "archived") {
    return uiText(language, "admin.quote_config.status_archived");
  }
  return uiText(language, "admin.quote_config.status_draft");
}

function uiLanguageLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "en") {
    return uiText(language, "common.english");
  }
  if (normalized === "fr") {
    return uiText(language, "common.french");
  }
  return normalized ? normalized.toUpperCase() : "-";
}

function moneyLabel(value: string | number | null | undefined, currency = "EUR"): string {
  const numeric = typeof value === "number" ? value : Number(String(value ?? "").trim().replace(",", "."));
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency: (currency || "EUR").toUpperCase(),
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  } catch {
    return `${numeric.toFixed(2)} ${(currency || "EUR").toUpperCase()}`;
  }
}

function pricingUnitLabel(value: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "per_session") {
    return "Par cours";
  }
  if (normalized === "hourly") {
    return "Horaire";
  }
  if (normalized === "fixed") {
    return "Forfait";
  }
  return value || "-";
}

function computedActivityFallbackPrice(activity: AdminActivityOut): { label: string; amountTtc: number | null; tone: "ok" | "warn" | "off" } {
  const direct = Number(String(activity.default_course_rate_ttc ?? "").trim());
  if (Number.isFinite(direct) && direct > 0) {
    return {
      label: "Tarif par cours par defaut activite",
      amountTtc: direct,
      tone: "warn",
    };
  }
  const hourly = Number(String(activity.default_hourly_rate ?? "").trim());
  const duration = Number(activity.duration_minutes || 0);
  if (Number.isFinite(hourly) && hourly > 0 && Number.isFinite(duration) && duration > 0) {
    return {
      label: "Tarif horaire par defaut activite",
      amountTtc: hourly * (duration / 60),
      tone: "warn",
    };
  }
  return {
    label: "Aucune source tarifaire de secours",
    amountTtc: null,
    tone: "off",
  };
}

function boolish(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on" || normalized === "oui";
}

function moneyNumber(value: unknown): number | null {
  const normalized = String(value ?? "").trim().replace(",", ".");
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function typeformTemplatePriceMode(template: Record<string, unknown>): "override" | "fallback" | null {
  const amount = moneyNumber(template.unit_price_ttc);
  if (amount === null || amount <= 0) {
    return null;
  }
  const rawMode = String(template.price_mode ?? "").trim().toLowerCase();
  if (boolish(template.allow_price_override) || rawMode === "override" || rawMode === "forced") {
    return "override";
  }
  return "fallback";
}

function typeformConditionsLabel(rawWhen: unknown): string {
  if (!rawWhen || typeof rawWhen !== "object" || Array.isArray(rawWhen)) {
    return "Toujours";
  }
  const entries = Object.entries(rawWhen as Record<string, unknown>)
    .map(([key, rawValue]) => {
      const values = Array.isArray(rawValue) ? rawValue : [rawValue];
      const labels = values.map((value) => String(value ?? "").trim()).filter(Boolean);
      if (labels.length === 0) {
        return key;
      }
      return `${key}: ${labels.join(" / ")}`;
    })
    .filter(Boolean);
  return entries.length > 0 ? entries.join(" · ") : "Toujours";
}

function collectTypeformTemplatePricingRows(
  configs: TypeformFormConfigOut[],
  options: {
    catalogId: string;
    activityByCode: ReadonlyMap<string, AdminActivityOut>;
  },
): TypeformTemplatePricingRow[] {
  const { catalogId, activityByCode } = options;
  const rows: TypeformTemplatePricingRow[] = [];
  for (const config of configs) {
    if (config.default_pricing_catalog_id !== catalogId) {
      continue;
    }
    const configJson = config.configuration_json ?? {};
    const templates = Array.isArray(configJson.line_templates) ? configJson.line_templates : [];
    const formLabel = String(configJson.label ?? config.source_code).trim() || config.source_code;
    templates.forEach((rawTemplate, index) => {
      if (!rawTemplate || typeof rawTemplate !== "object" || Array.isArray(rawTemplate)) {
        return;
      }
      const template = rawTemplate as Record<string, unknown>;
      const mode = typeformTemplatePriceMode(template);
      const amountTtc = moneyNumber(template.unit_price_ttc);
      if (!mode || amountTtc === null || amountTtc <= 0) {
        return;
      }
      const activityCode = String(template.activity_code ?? "").trim();
      const productCode = String(template.product_code ?? "").trim();
      const kitCode = String(template.kit_code ?? "").trim();
      const itemCode = activityCode || productCode || kitCode || null;
      const activity = activityCode ? activityByCode.get(activityCode) : undefined;
      const itemLabel = activity?.name || String(template.title ?? "").trim() || itemCode || `Ligne ${index + 1}`;
      rows.push({
        key: `${config.id}-${index}-${itemCode ?? "line"}`,
        formId: config.typeform_form_id,
        formSourceCode: config.source_code,
        formLabel,
        locationCode: config.location_code,
        itemLabel,
        itemCode,
        mode,
        amountTtc,
        conditionsLabel: typeformConditionsLabel(template.when),
      });
    });
  }
  return rows;
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

const MONTH_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 1, label: "Janvier" },
  { value: 2, label: "Fevrier" },
  { value: 3, label: "Mars" },
  { value: 4, label: "Avril" },
  { value: 5, label: "Mai" },
  { value: 6, label: "Juin" },
  { value: 7, label: "Juillet" },
  { value: 8, label: "Aout" },
  { value: 9, label: "Septembre" },
  { value: 10, label: "Octobre" },
  { value: 11, label: "Novembre" },
  { value: 12, label: "Decembre" },
];

function weekdayLabel(day: number): string {
  return WEEKDAY_OPTIONS.find((option) => option.value === day)?.label ?? String(day);
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

function paymentDeferredMonthValue(rules: Record<string, unknown>, index: number): string {
  const monthsRaw = Array.isArray(rules.deferred_due_months) ? rules.deferred_due_months : [];
  const value = Number.parseInt(String(monthsRaw[index] ?? ""), 10);
  if (!Number.isFinite(value) || value < 1 || value > 12) {
    return "";
  }
  return String(value);
}

function paymentScheduleVisibilityFlag(rules: Record<string, unknown>, key: "public_page" | "client_pdf"): boolean {
  const raw = rules.schedule_visibility;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return true;
  }
  return Boolean((raw as Record<string, unknown>)[key]);
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
        ? `${weekdayLabel(weekdayRaw)}`
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
    }
  }
  return out;
}

export default async function AdminQuoteConfigurationPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
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
  const sortLocale = language === "en" ? "en-US" : "fr-FR";

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
    formulasResult,
    catalogsResult,
    typeformFormConfigsResult,
    pricingActivityPricesResult,
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
    backendRequest<AdminFormulaOut[]>("/api/v1/admin/formulas?include_inactive=true", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<TypeformFormConfigOut[]>("/api/v1/typeform/form-configs", {}, token),
    backendRequest<PricingActivityPriceOut[]>("/api/v1/pricing-activity-prices", {}, token),
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
        loadErrors.push(`${t("admin.quote_config.load_quote_types")}: ${quoteTypesResult.message}`);
        return [] as QuoteTypeOut[];
      })();
  const formulas = formulasResult.ok
    ? formulasResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_formulas")}: ${formulasResult.message}`);
        return [] as AdminFormulaOut[];
      })();
  const catalogs = catalogsResult.ok
    ? catalogsResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_catalogs")}: ${catalogsResult.message}`);
        return [] as PricingCatalogOut[];
      })();
  const typeformFormConfigs = typeformFormConfigsResult.ok
    ? typeformFormConfigsResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_typeform_configs")}: ${typeformFormConfigsResult.message}`);
        return [] as TypeformFormConfigOut[];
      })();
  const paymentPlans = paymentPlansResult.ok
    ? paymentPlansResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_payment_plans")}: ${paymentPlansResult.message}`);
        return [] as PaymentPlanOut[];
      })();
  const pricingActivityPrices = pricingActivityPricesResult.ok
    ? pricingActivityPricesResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_activity_prices")}: ${pricingActivityPricesResult.message}`);
        return [] as PricingActivityPriceOut[];
      })();
  const templateVariables = templateVariablesResult.ok
    ? templateVariablesResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_template_variables")}: ${templateVariablesResult.message}`);
        return [] as QuoteTemplateVariableOut[];
      })();
  const solfegeRules = solfegeRulesResult.ok
    ? solfegeRulesResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_solfege_rules")}: ${solfegeRulesResult.message}`);
        return [] as SolfegeLevelRuleOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_locations")}: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();
  const activities = activitiesResult.ok
    ? activitiesResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_activities")}: ${activitiesResult.message}`);
        return [] as AdminActivityOut[];
      })();
  const quoteTemplatesV2 = quoteTemplatesV2Result.ok
    ? quoteTemplatesV2Result.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_doc_templates")}: ${quoteTemplatesV2Result.message}`);
        return [] as QuoteTemplateV2Out[];
      })();
  const termsTemplates = termsTemplatesResult.ok
    ? termsTemplatesResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_terms_templates")}: ${termsTemplatesResult.message}`);
        return [] as TermsTemplateOut[];
      })();
  const quoteDocumentBindings = quoteDocumentBindingsResult.ok
    ? quoteDocumentBindingsResult.data
    : (() => {
        loadErrors.push(`${t("admin.quote_config.load_document_bindings")}: ${quoteDocumentBindingsResult.message}`);
        return [] as QuoteDocumentBindingOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const formulaById = new Map(formulas.map((row) => [row.id, row.name]));
  const activityByCode = new Map(activities.map((row) => [row.code, row]));
  const activeActivities = activities
    .filter((row) => row.active)
    .sort((a, b) => a.name.localeCompare(b.name, sortLocale));
  const activityFamilies = Array.from(
    new Set(
      activities
        .map((row) => String(row.service_code || "").trim())
        .filter((value) => value.length > 0),
    ),
  ).sort((a, b) => a.localeCompare(b, sortLocale));
  const defaultQuoteTemplateSubject = language === "en"
    ? "Your Piano Academie quote {quote_number}"
    : "Votre devis {quote_number} Piano Academie";
  const defaultQuoteTemplateBody = language === "en"
    ? "{document_style_html}{cover_page_standard_html}{header_standard_html}<h1>Quote {quote_number}</h1>{page_break_html}<h2>Student and parent details</h2><div class='quote-block'>{prospect_identity_block_html}</div>{activities_planning_section_html}{services_section_html}{adjustments_section_html}{products_section_html}{kits_section_html}{financial_recap_block_html}<h2>Payment and schedule</h2>{payment_method_block_html}<p>{payment_schedule_summary}</p>{payment_schedule_table_html}{options_section_html}<h2>Planned lesson schedule</h2><p><strong>Calendar overview:</strong> {calendar_summary}</p>{calendar_activity_semesters_html}<p><strong>Expiry:</strong> {expires_at}</p>{footer_standard_html}"
    : "{document_style_html}{cover_page_standard_html}{header_standard_html}<h1>Devis {quote_number}</h1>{page_break_html}<h2>Informations de l’élève et du responsable</h2><div class='quote-block'>{prospect_identity_block_html}</div>{activities_planning_section_html}{services_section_html}{adjustments_section_html}{products_section_html}{kits_section_html}{financial_recap_block_html}<h2>Règlement et échéancier</h2>{payment_method_block_html}<p>{payment_schedule_summary}</p>{payment_schedule_table_html}{options_section_html}<h2>Calendrier prévisionnel des cours</h2><p><strong>Vue d’ensemble du calendrier :</strong> {calendar_summary}</p>{calendar_activity_semesters_html}<p><strong>Expiration:</strong> {expires_at}</p>{footer_standard_html}";
  const defaultQuoteTemplateFallbackBody = language === "en"
    ? "{document_style_html}{header_standard_html}<h1>Quote {quote_number}</h1>{page_break_html}<h2>Student and parent details</h2><div class='quote-block'>{prospect_identity_block_html}</div>{activities_planning_section_html}{services_section_html}{adjustments_section_html}{products_section_html}{kits_section_html}{financial_recap_block_html}<h2>Payment and schedule</h2>{payment_method_block_html}<p>{payment_schedule_summary}</p>{payment_schedule_table_html}{options_section_html}<h2>Planned lesson schedule</h2><p><strong>Calendar overview:</strong> {calendar_summary}</p>{calendar_activity_semesters_html}{footer_standard_html}"
    : "{document_style_html}{header_standard_html}<h1>Devis {quote_number}</h1>{page_break_html}<h2>Informations de l’élève et du responsable</h2><div class='quote-block'>{prospect_identity_block_html}</div>{activities_planning_section_html}{services_section_html}{adjustments_section_html}{products_section_html}{kits_section_html}{financial_recap_block_html}<h2>Règlement et échéancier</h2>{payment_method_block_html}<p>{payment_schedule_summary}</p>{payment_schedule_table_html}{options_section_html}<h2>Calendrier prévisionnel des cours</h2><p><strong>Vue d’ensemble du calendrier :</strong> {calendar_summary}</p>{calendar_activity_semesters_html}{footer_standard_html}";
  const defaultTermsVersionLabel = language === "en" ? "Terms 2026.1" : "CGV 2026.1";
  const defaultTermsContent = language === "en"
    ? "<h2>Terms and conditions</h2><p>...</p>"
    : "<h2>Conditions generales de vente</h2><p>...</p>";
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
            <h2>{t("admin.quote_config.page_title")}</h2>
            <p className="muted">{t("admin.quote_config.page_subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/config">{t("admin.quote_config.back_config")}</Link>
            <Link className="ghost" href="/admin/quotes">{t("admin.quote_config.view_quotes")}</Link>
          </div>
        </div>
      </section>

      {okMessage || errorMessage ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact">
            <a className="modal-close-x" href={returnPath} aria-label={t("common.close")}>
              ×
            </a>
            <h3 className="modal-title">{errorMessage ? t("admin.quote_config.feedback_error_title") : t("admin.quote_config.feedback_success_title")}</h3>
            {okMessage ? <section className="flash-ok top-gap-sm">{okMessage}</section> : null}
            {errorMessage ? <section className="flash-err top-gap-sm">{errorMessage}</section> : null}
            <div className="row modal-actions-end top-gap-sm">
              <a className="ghost" href={returnPath}>{t("common.close")}</a>
            </div>
          </article>
        </section>
      ) : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>{t("admin.quote_config.loading_errors")}</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card">
        <nav className="config-sub-nav">
          <Link className={`config-sub-link ${tab === "types" ? "active" : ""}`} href={buildQuotesConfigHref("types")}>{t("admin.quote_config.nav_types")}</Link>
          <Link className={`config-sub-link ${tab === "catalogs" ? "active" : ""}`} href={buildQuotesConfigHref("catalogs")}>{t("admin.quote_config.nav_catalogs")}</Link>
          <Link className={`config-sub-link ${tab === "payment_plans" ? "active" : ""}`} href={buildQuotesConfigHref("payment_plans")}>{t("admin.quote_config.nav_payment_plans")}</Link>
          <Link className={`config-sub-link ${tab === "doc_templates" ? "active" : ""}`} href={buildQuotesConfigHref("doc_templates")}>{t("admin.quote_config.nav_doc_templates")}</Link>
          <Link className={`config-sub-link ${tab === "doc_terms" ? "active" : ""}`} href={buildQuotesConfigHref("doc_terms")}>{t("admin.quote_config.nav_doc_terms")}</Link>
          <Link className={`config-sub-link ${tab === "doc_bindings" ? "active" : ""}`} href={buildQuotesConfigHref("doc_bindings")}>{t("admin.quote_config.nav_doc_bindings")}</Link>
          <Link className={`config-sub-link ${tab === "variables" ? "active" : ""}`} href={buildQuotesConfigHref("variables")}>{t("admin.quote_config.nav_variables")}</Link>
          <Link className={`config-sub-link ${tab === "solfege" ? "active" : ""}`} href={buildQuotesConfigHref("solfege")}>{t("admin.quote_config.nav_solfege")}</Link>
          <Link className="config-sub-link" href="/admin/config/calendars">{t("admin.quote_config.nav_calendars")}</Link>
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
            <label>
              Annee scolaire par defaut
              <input type="text" name="school_year_label" maxLength={40} placeholder="2026-2027" />
            </label>
            <label className="span-2">
              Formule rattachee
              <select name="formula_id" defaultValue="">
                <option value="">Aucune</option>
                {formulas.map((formula) => (
                  <option key={formula.id} value={formula.id}>
                    {formula.name}
                  </option>
                ))}
              </select>
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
                    <p className="muted">
                      Formule: {row.formula_name || "-"} · Annee scolaire: {row.school_year_label || "-"}
                    </p>
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
                    <label>
                      Annee scolaire par defaut
                      <input type="text" name="school_year_label" defaultValue={row.school_year_label || ""} maxLength={40} />
                    </label>
                    <label className="span-2">
                      Formule rattachee
                      <select name="formula_id" defaultValue={row.formula_id || ""}>
                        <option value="">Aucune</option>
                        {formulas.map((formula) => (
                          <option key={formula.id} value={formula.id}>
                            {formula.name}
                          </option>
                        ))}
                      </select>
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
                  <th>Sources tarifaires</th>
                  <th>Statut</th>
                  <th>Maj</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {catalogs.length === 0 ? (
                  <tr><td colSpan={7}><p className="muted">Aucun catalogue configure.</p></td></tr>
                ) : (
                  catalogs.map((row) => {
                    const explicitActivityPrices = pricingActivityPrices
                      .filter((price) => price.catalog_id === row.id && price.is_active)
                      .sort((left, right) => {
                        const leftActivity = activities.find((item) => item.id === left.activity_id)?.name ?? "";
                        const rightActivity = activities.find((item) => item.id === right.activity_id)?.name ?? "";
                        const byActivity = leftActivity.localeCompare(rightActivity, "fr-FR");
                        if (byActivity !== 0) {
                          return byActivity;
                        }
                        const leftLocation = left.location_id ? (locationById.get(left.location_id) ?? "") : "";
                        const rightLocation = right.location_id ? (locationById.get(right.location_id) ?? "") : "";
                        return leftLocation.localeCompare(rightLocation, "fr-FR");
                      });
                    const explicitActivityIds = new Set(explicitActivityPrices.map((price) => price.activity_id));
                    const fallbackActivities = activeActivities
                      .filter((activity) => !explicitActivityIds.has(activity.id))
                      .map((activity) => ({
                        activity,
                        fallback: computedActivityFallbackPrice(activity),
                      }));
                    const typeformTemplatePricingRows = collectTypeformTemplatePricingRows(typeformFormConfigs, {
                      catalogId: row.id,
                      activityByCode,
                    });
                    const fallbackAvailableCount = fallbackActivities.filter((item) => item.fallback.amountTtc !== null).length;
                    const fallbackMissingCount = fallbackActivities.length - fallbackAvailableCount;
                    const typeformOverrideCount = typeformTemplatePricingRows.filter((item) => item.mode === "override").length;
                    const typeformFallbackCount = typeformTemplatePricingRows.length - typeformOverrideCount;

                    return (
                      <tr key={row.id}>
                        <td><strong>{row.name}</strong></td>
                        <td>{row.school_year_label || "-"}</td>
                        <td>{dateInputValue(row.effective_from)} → {dateInputValue(row.effective_to)}</td>
                        <td>
                          <div><strong>{explicitActivityPrices.length}</strong> tarif(s) explicite(s)</div>
                          <div className="muted">
                            {fallbackAvailableCount} fallback(s) activite · {typeformOverrideCount} surcharge(s) Typeform · {typeformFallbackCount} secours Typeform · {fallbackMissingCount} sans source
                          </div>
                        </td>
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

                            <div className="top-gap-sm">
                              <h4>Sources tarifaires activites</h4>
                              <p className="muted">
                                Ce diagnostic montre les tarifs explicites du catalogue, puis le fallback activite reellement applique par le moteur de devis.
                                Les tarifs portes par Typeform sont affiches a part: par defaut ils ne servent plus qu en secours, et seules les surcharges explicitement marquees restent prioritaires sur le fallback activite.
                              </p>

                              <div className="table-wrap top-gap-sm">
                                <table className="data-table">
                                  <thead>
                                    <tr>
                                      <th>Tarif Typeform configure</th>
                                      <th>Formulaire</th>
                                      <th>Mode</th>
                                      <th>Montant TTC</th>
                                      <th>Condition</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {typeformTemplatePricingRows.length === 0 ? (
                                      <tr>
                                        <td colSpan={5}>
                                          <p className="muted">Aucun tarif Typeform explicite rattache a ce catalogue.</p>
                                        </td>
                                      </tr>
                                    ) : (
                                      typeformTemplatePricingRows.map((item) => (
                                        <tr key={item.key}>
                                          <td>
                                            <strong>{item.itemLabel}</strong>
                                            <div className="muted"><code>{item.itemCode || "-"}</code></div>
                                          </td>
                                          <td>
                                            <strong>{item.formLabel}</strong>
                                            <div className="muted"><code>{item.formId}</code> · {item.locationCode}</div>
                                          </td>
                                          <td>
                                            <span className={`status-pill ${item.mode === "override" ? "status-warn" : "status-off"}`}>
                                              {item.mode === "override" ? "Surcharge explicite" : "Secours Typeform"}
                                            </span>
                                          </td>
                                          <td>{moneyLabel(item.amountTtc)}</td>
                                          <td>{item.conditionsLabel}</td>
                                        </tr>
                                      ))
                                    )}
                                  </tbody>
                                </table>
                              </div>

                              <div className="table-wrap top-gap-sm">
                                <table className="data-table">
                                  <thead>
                                    <tr>
                                      <th>Activite</th>
                                      <th>Lieu</th>
                                      <th>Unite</th>
                                      <th>Source</th>
                                      <th>Montant TTC</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {explicitActivityPrices.length === 0 ? (
                                      <tr>
                                        <td colSpan={5}>
                                          <p className="muted">Aucun tarif explicite enregistre dans ce catalogue.</p>
                                        </td>
                                      </tr>
                                    ) : (
                                      explicitActivityPrices.map((price) => {
                                        const activity = activities.find((item) => item.id === price.activity_id);
                                        const locationName = price.location_id ? (locationById.get(price.location_id) ?? price.location_id) : "Tous sites";
                                        const sourceLabel = price.location_id ? "Catalogue · site specifique" : "Catalogue · general";
                                        return (
                                          <tr key={price.id}>
                                            <td>
                                              <strong>{activity?.name || price.activity_id}</strong>
                                              <div className="muted"><code>{activity?.code || price.activity_id}</code></div>
                                            </td>
                                            <td>{locationName}</td>
                                            <td>{pricingUnitLabel(price.pricing_unit)}</td>
                                            <td>{sourceLabel}</td>
                                            <td>{moneyLabel(price.unit_price_ttc, price.currency)}</td>
                                          </tr>
                                        );
                                      })
                                    )}
                                  </tbody>
                                </table>
                              </div>

                              <div className="table-wrap top-gap-sm">
                                <table className="data-table">
                                  <thead>
                                    <tr>
                                      <th>Activite sans tarif catalogue explicite</th>
                                      <th>Mode</th>
                                      <th>Fallback</th>
                                      <th>Montant de secours</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {fallbackActivities.length === 0 ? (
                                      <tr>
                                        <td colSpan={4}>
                                          <p className="muted">Toutes les activites actives ont un tarif explicite dans ce catalogue.</p>
                                        </td>
                                      </tr>
                                    ) : (
                                      fallbackActivities.map(({ activity, fallback }) => (
                                        <tr key={`${row.id}-${activity.id}`}>
                                          <td>
                                            <strong>{activity.name}</strong>
                                            <div className="muted"><code>{activity.code}</code></div>
                                          </td>
                                          <td>{modalityLabel(activity.mode)}</td>
                                          <td>
                                            <span className={`status-pill ${fallback.tone === "off" ? "status-off" : fallback.tone === "warn" ? "status-warn" : "status-ok"}`}>
                                              {fallback.label}
                                            </span>
                                          </td>
                                          <td>{fallback.amountTtc === null ? "-" : moneyLabel(fallback.amountTtc)}</td>
                                        </tr>
                                      ))
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </div>

                            <form action={deleteAdminPricingCatalogConfigAction} className="row top-gap-sm">
                              <input type="hidden" name="catalog_id" value={row.id} />
                              <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
                              <button type="submit" className="danger">Supprimer</button>
                            </form>
                          </details>
                        </td>
                      </tr>
                    );
                  })
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
            <label>
              Encaissement 2e echeance (mois)
              <select name="due_month_2" defaultValue="2">
                <option value="">Auto</option>
                {MONTH_OPTIONS.map((option) => (
                  <option key={`create-month2-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              Encaissement 3e echeance (mois)
              <select name="due_month_3" defaultValue="2">
                <option value="">Auto</option>
                {MONTH_OPTIONS.map((option) => (
                  <option key={`create-month3-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              Encaissement 4e echeance (mois)
              <select name="due_month_4" defaultValue="4">
                <option value="">Auto</option>
                {MONTH_OPTIONS.map((option) => (
                  <option key={`create-month4-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="checkline">
              <input type="checkbox" name="collect_all_checks_upfront" defaultChecked />
              Tous les cheques envoyes en meme temps
            </label>
            <label className="checkline">
              <input type="checkbox" name="show_schedule_public" defaultChecked />
              Afficher l echeancier detaille (page publique)
            </label>
            <label className="checkline">
              <input type="checkbox" name="show_schedule_pdf" defaultChecked />
              Afficher l echeancier detaille (PDF client)
            </label>
            <label className="span-2">
              Adresse de reception des cheques (optionnel)
              <textarea name="check_submission_address" rows={2} placeholder="Piano Academie, [adresse postale]" />
            </label>
            <label className="span-2">
              Consigne affichee dans le devis (optionnel)
              <textarea
                name="check_submission_instruction"
                rows={2}
                placeholder="Le 1er cheque est encaisse a reception. Le 2e cheque est encaisse debut fevrier."
              />
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
                  <th>Consignes</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paymentPlans.length === 0 ? (
                  <tr><td colSpan={8}><p className="muted">Aucun plan de paiement.</p></td></tr>
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
                      <td>
                        {String((row.schedule_rules?.check_submission_instruction ?? "") || "").trim() || "-"}
                      </td>
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
                            <label>
                              Encaissement 2e echeance (mois)
                              <select name="due_month_2" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 0)}>
                                <option value="">Auto</option>
                                {MONTH_OPTIONS.map((option) => (
                                  <option key={`edit-${row.id}-month2-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Encaissement 3e echeance (mois)
                              <select name="due_month_3" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 1)}>
                                <option value="">Auto</option>
                                {MONTH_OPTIONS.map((option) => (
                                  <option key={`edit-${row.id}-month3-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Encaissement 4e echeance (mois)
                              <select name="due_month_4" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 2)}>
                                <option value="">Auto</option>
                                {MONTH_OPTIONS.map((option) => (
                                  <option key={`edit-${row.id}-month4-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label className="checkline">
                              <input
                                type="checkbox"
                                name="collect_all_checks_upfront"
                                defaultChecked={Boolean(row.schedule_rules?.collect_all_checks_upfront ?? true)}
                              />
                              Tous les cheques envoyes en meme temps
                            </label>
                            <label className="checkline">
                              <input
                                type="checkbox"
                                name="show_schedule_public"
                                defaultChecked={paymentScheduleVisibilityFlag(row.schedule_rules || {}, "public_page")}
                              />
                              Afficher l echeancier detaille (page publique)
                            </label>
                            <label className="checkline">
                              <input
                                type="checkbox"
                                name="show_schedule_pdf"
                                defaultChecked={paymentScheduleVisibilityFlag(row.schedule_rules || {}, "client_pdf")}
                              />
                              Afficher l echeancier detaille (PDF client)
                            </label>
                            <label className="span-2">
                              Adresse de reception des cheques (optionnel)
                              <textarea
                                name="check_submission_address"
                                rows={2}
                                defaultValue={String((row.schedule_rules?.check_submission_address ?? "") || "")}
                              />
                            </label>
                            <label className="span-2">
                              Consigne affichee dans le devis (optionnel)
                              <textarea
                                name="check_submission_instruction"
                                rows={2}
                                defaultValue={String((row.schedule_rules?.check_submission_instruction ?? "") || "")}
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
          <h3>{t("admin.quote_config.doc_templates_title")}</h3>
          <p className="muted">{t("admin.quote_config.doc_templates_subtitle")}</p>
          <form action={createAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
            <div className="span-2">
              <h4>{t("admin.quote_config.step_template_record")}</h4>
            </div>
            <label>
              {t("common.name")}
              <input type="text" name="name" required maxLength={180} placeholder={t("admin.quote_config.doc_template_name_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.target")}
              <input type="text" name="target" maxLength={40} placeholder={t("admin.quote_config.target_placeholder")} />
            </label>
            <label>
              {t("common.language")}
              <select name="language" defaultValue="fr" required>
                <option value="fr">{t("common.french")}</option>
                <option value="en">{t("common.english")}</option>
              </select>
            </label>
            <label>
              {t("common.status")}
              <select name="status" defaultValue="draft">
                <option value="draft">{t("admin.quote_config.status_draft")}</option>
                <option value="published">{t("admin.quote_config.status_published")}</option>
                <option value="archived">{t("admin.quote_config.status_archived")}</option>
              </select>
            </label>
            <label className="span-2">
              {t("admin.quote_config.internal_description")}
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_default" />
              {t("admin.quote_config.default_for_language")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="publish_now" defaultChecked />
              {t("admin.quote_config.publish_now")}
            </label>
            <label className="span-2">
              {t("admin.quote_config.changelog")}
              <input type="text" name="changelog" maxLength={2000} placeholder={t("admin.quote_config.changelog_initial_placeholder")} />
            </label>
            <div className="span-2">
              <h4>{t("admin.quote_config.step_document_content")}</h4>
            </div>
            <div className="span-2">
              <QuoteTemplateEditor
                language={language}
                subjectName="subject_template"
                bodyName="body_template"
                defaultSubject={defaultQuoteTemplateSubject}
                defaultBody={defaultQuoteTemplateBody}
                variables={templateVariables}
              />
            </div>
            <div className="row span-2">
              <button type="submit">{t("admin.quote_config.save_quote_template")}</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {quoteTemplatesV2.length === 0 ? <p className="muted">{t("admin.quote_config.no_quote_templates")}</p> : null}
            {quoteTemplatesV2.map((row) => {
              const prefill = quoteTemplateVersionPrefill.get(row.id);
              return (
                <article key={row.id} className="item">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <strong>{row.name}</strong>
                      <p className="muted">
                        {t("admin.quote_config.template_meta", {
                          target: row.target || "-",
                          language: uiLanguageLabel(row.language, language),
                          version: row.current_version_number ?? "-",
                          updated_at: dateTimeLabel(row.updated_at, language),
                        })}
                      </p>
                    </div>
                    <div className="row wrap gap-sm">
                      {row.is_default ? <span className="badge">{t("admin.quote_config.default_badge")}</span> : null}
                      <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{templateStatusLabel(row.status, language)}</span>
                    </div>
                  </div>
                  <details>
                    <summary className="mode-link">{t("admin.quote_config.edit_publish_new_version")}</summary>
                    <form action={updateAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
                      <input type="hidden" name="code" value={row.code} />
                      <input type="hidden" name="template_type" value={row.template_type || "quote_body"} />
                      <div className="span-2">
                        <h4>{t("admin.quote_config.step_template_record")}</h4>
                      </div>
                      <label>
                        {t("common.name")}
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        {t("admin.quote_config.target")}
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        {t("common.language")}
                        <select name="language" defaultValue={row.language || "fr"} required>
                          <option value="fr">{t("common.french")}</option>
                          <option value="en">{t("common.english")}</option>
                        </select>
                      </label>
                      <label>
                        {t("common.status")}
                        <select name="status" defaultValue={row.status || "draft"}>
                          <option value="draft">{t("admin.quote_config.status_draft")}</option>
                          <option value="published">{t("admin.quote_config.status_published")}</option>
                          <option value="archived">{t("admin.quote_config.status_archived")}</option>
                        </select>
                      </label>
                      <label className="span-2">
                        {t("admin.quote_config.internal_description")}
                        <input type="text" name="description" defaultValue={row.description ?? ""} maxLength={2000} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_default" defaultChecked={row.is_default} />
                        {t("admin.quote_config.default_for_language")}
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                        {t("common.active")}
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="publish_now" defaultChecked />
                        {t("admin.quote_config.publish_now")}
                      </label>
                      <label className="span-2">
                        {t("admin.quote_config.changelog")}
                        <input type="text" name="changelog" maxLength={2000} placeholder={t("admin.quote_config.changelog_new_version_placeholder")} />
                      </label>
                      <div className="span-2">
                        <h4>{t("admin.quote_config.step_document_content")}</h4>
                      </div>
                      <div className="span-2">
                        <QuoteTemplateEditor
                          language={language}
                          subjectName="subject_template"
                          bodyName="body_template"
                          defaultSubject={prefill?.subject || defaultQuoteTemplateSubject}
                          defaultBody={prefill?.body || defaultQuoteTemplateFallbackBody}
                          variables={templateVariables}
                        />
                      </div>
                      <div className="row span-2">
                        <button type="submit">{t("common.save")}</button>
                      </div>
                    </form>
                    <form action={deleteAdminQuoteTemplateV2ConfigAction} className="row top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
                      <button type="submit" className="danger">{t("common.archive")}</button>
                    </form>
                    <form action={hardDeleteAdminQuoteTemplateV2ConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_templates")} />
                      <label className="span-2">
                        {t("admin.quote_config.hard_delete_confirmation")}
                        <input
                          type="text"
                          name="confirm_delete"
                          required
                          placeholder={t("admin.quote_config.hard_delete_placeholder")}
                          autoComplete="off"
                        />
                      </label>
                      <div className="row span-2">
                        <button type="submit" className="danger">{t("admin.quote_config.hard_delete_button")}</button>
                      </div>
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
          <h3>{t("admin.quote_config.doc_terms_title")}</h3>
          <p className="muted">{t("admin.quote_config.doc_terms_subtitle")}</p>
          <form action={createAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
            <label>
              {t("common.name")}
              <input type="text" name="name" required maxLength={180} placeholder={t("admin.quote_config.doc_terms_name_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.target")}
              <input type="text" name="target" maxLength={40} placeholder={t("admin.quote_config.target_placeholder")} />
            </label>
            <label>
              {t("common.language")}
              <select name="language" defaultValue="fr" required>
                <option value="fr">{t("common.french")}</option>
                <option value="en">{t("common.english")}</option>
              </select>
            </label>
            <label>
              {t("common.status")}
              <select name="status" defaultValue="draft">
                <option value="draft">{t("admin.quote_config.status_draft")}</option>
                <option value="published">{t("admin.quote_config.status_published")}</option>
                <option value="archived">{t("admin.quote_config.status_archived")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_config.version_label")}
              <input type="text" name="version_label" required maxLength={80} placeholder={defaultTermsVersionLabel} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="publish_now" defaultChecked />
              {t("admin.quote_config.publish_now")}
            </label>
            <label className="span-2">
              {t("admin.quote_config.internal_description")}
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="span-2">
              {t("admin.quote_config.changelog")}
              <input type="text" name="changelog" maxLength={2000} />
            </label>
            <div className="span-2">
              <WysiwygField
                language={language}
                name="content"
                label={t("admin.quote_config.terms_content")}
                defaultValue={defaultTermsContent}
                helpText={t("admin.quote_config.terms_content_help")}
              />
            </div>
            <div className="row span-2">
              <button type="submit">{t("admin.quote_config.save_terms_template")}</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {termsTemplates.length === 0 ? <p className="muted">{t("admin.quote_config.no_terms_templates")}</p> : null}
            {termsTemplates.map((row) => {
              const prefill = termsTemplateVersionPrefill.get(row.id);
              return (
                <article key={row.id} className="item">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <strong>{row.name}</strong>
                      <p className="muted">
                        {t("admin.quote_config.template_meta", {
                          target: row.target || "-",
                          language: uiLanguageLabel(row.language, language),
                          version: row.current_version_number ?? "-",
                          updated_at: dateTimeLabel(row.updated_at, language),
                        })}
                      </p>
                    </div>
                    <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{templateStatusLabel(row.status, language)}</span>
                  </div>
                  <details>
                    <summary className="mode-link">{t("admin.quote_config.edit_publish_new_version")}</summary>
                    <form action={updateAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <input type="hidden" name="current_code" value={row.code} />
                      <label>
                        {t("common.name")}
                        <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                      </label>
                      <label>
                        {t("admin.quote_config.target")}
                        <input type="text" name="target" defaultValue={row.target ?? ""} maxLength={40} />
                      </label>
                      <label>
                        {t("common.language")}
                        <select name="language" defaultValue={row.language || "fr"} required>
                          <option value="fr">{t("common.french")}</option>
                          <option value="en">{t("common.english")}</option>
                        </select>
                      </label>
                      <label>
                        {t("common.status")}
                        <select name="status" defaultValue={row.status || "draft"}>
                          <option value="draft">{t("admin.quote_config.status_draft")}</option>
                          <option value="published">{t("admin.quote_config.status_published")}</option>
                          <option value="archived">{t("admin.quote_config.status_archived")}</option>
                        </select>
                      </label>
                      <label>
                        {t("admin.quote_config.version_label")}
                        <input type="text" name="version_label" defaultValue={prefill?.versionLabel || defaultTermsVersionLabel} required maxLength={80} />
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                        {t("common.active")}
                      </label>
                      <label className="checkline">
                        <input type="checkbox" name="publish_now" defaultChecked />
                        {t("admin.quote_config.publish_now")}
                      </label>
                      <label className="span-2">
                        {t("admin.quote_config.internal_description")}
                        <input type="text" name="description" defaultValue={row.description ?? ""} maxLength={2000} />
                      </label>
                      <label className="span-2">
                        {t("admin.quote_config.changelog")}
                        <input type="text" name="changelog" maxLength={2000} />
                      </label>
                      <div className="span-2">
                        <WysiwygField
                          language={language}
                          name="content"
                          label={t("admin.quote_config.terms_content")}
                          defaultValue={prefill?.content || ""}
                          helpText={t("admin.quote_config.terms_content_publish_help")}
                        />
                      </div>
                      <div className="row span-2">
                        <button type="submit">{t("common.save")}</button>
                      </div>
                    </form>
                    <form action={deleteAdminTermsTemplateConfigAction} className="row top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <button type="submit" className="danger">{t("common.archive")}</button>
                    </form>
                    <form action={hardDeleteAdminTermsTemplateConfigAction} className="grid cols-2 config-form-grid top-gap-sm">
                      <input type="hidden" name="template_id" value={row.id} />
                      <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_terms")} />
                      <label className="span-2">
                        {t("admin.quote_config.hard_delete_confirmation")}
                        <input
                          type="text"
                          name="confirm_delete"
                          required
                          placeholder={t("admin.quote_config.hard_delete_placeholder")}
                          autoComplete="off"
                        />
                      </label>
                      <div className="row span-2">
                        <button type="submit" className="danger">{t("admin.quote_config.hard_delete_button")}</button>
                      </div>
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
          <p className="muted">Un creneau = un jour + une heure de debut + une duree de niveau. L heure de fin est calculee automatiquement.</p>
          <form action={upsertAdminSolfegeLevelRuleConfigAction} className="solfege-config-form">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
            <div className="grid cols-4 config-form-grid">
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
            </div>
            <div className="solfege-slot-editor">
              <h4>Lignes de creneaux</h4>
              <p className="muted">Desktop first: renseignez simplement les paires jour + heure de debut. Laissez vide les lignes inutiles.</p>
              <div className="solfege-slot-grid top-gap-sm">
                {Array.from({ length: 6 }).map((_, index) => (
                  <article key={`create-solfege-slot-${index}`} className="solfege-slot-row">
                    <p className="solfege-slot-row-index">Creneau {index + 1}</p>
                    <label>
                      Jour
                      <select name="slot_weekday" defaultValue="">
                        <option value="">Selection a faire</option>
                        {WEEKDAY_OPTIONS.map((day) => (
                          <option key={`create-solfege-slot-day-${index}-${day.value}`} value={day.value}>{day.label}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Heure debut
                      <input type="time" name="slot_start_time" defaultValue="" />
                    </label>
                    <p className="muted solfege-slot-row-end">Heure fin: calculee automatiquement</p>
                  </article>
                ))}
              </div>
            </div>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              Active
            </label>
            <div className="row">
              <button type="submit">Ajouter / mettre a jour</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Niveau</th>
                  <th>Duree</th>
                  <th>Creneaux</th>
                  <th>Local</th>
                  <th>Mode</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {solfegeRules.length === 0 ? (
                  <tr><td colSpan={7}><p className="muted">Aucune regle solfege.</p></td></tr>
                ) : (
                  solfegeRules.map((row) => {
                    const editSlots = solfegeSlotRows(row.allowed_time_slots);
                    const levelKnown = ["1", "2", "3", "4", "5"].includes(row.level_code);
                    return (
                      <tr key={row.id}>
                        <td>Niveau {row.level_code}</td>
                        <td>{row.duration_minutes} min</td>
                        <td>{solfegeSlotsCsv(row.allowed_time_slots) || "-"}</td>
                        <td>{row.location_id ? (locationById.get(row.location_id) || row.location_id) : "Tous"}</td>
                        <td>{modalityLabel(row.modality)}</td>
                        <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Active" : "Inactive"}</span></td>
                        <td>
                          <details>
                            <summary className="mode-link">Modifier</summary>
                            <form action={upsertAdminSolfegeLevelRuleConfigAction} className="solfege-config-form top-gap-sm">
                              <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
                              <div className="grid cols-4 config-form-grid">
                                <label>
                                  Niveau
                                  <select name="level_code" defaultValue={row.level_code}>
                                    {!levelKnown ? <option value={row.level_code}>Niveau {row.level_code}</option> : null}
                                    <option value="1">Niveau 1</option>
                                    <option value="2">Niveau 2</option>
                                    <option value="3">Niveau 3</option>
                                    <option value="4">Niveau 4</option>
                                    <option value="5">Niveau 5</option>
                                  </select>
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
                              </div>
                              <div className="solfege-slot-editor">
                                <h4>Lignes de creneaux</h4>
                                <p className="muted">Meme logique: un creneau = jour + heure de debut. L heure de fin est recalculee selon la duree.</p>
                                <div className="solfege-slot-grid top-gap-sm">
                                  {Array.from({ length: Math.max(6, editSlots.length) }).map((_, index) => {
                                    const slot = editSlots[index];
                                    return (
                                      <article key={`${row.id}-slot-edit-${index}`} className="solfege-slot-row">
                                        <p className="solfege-slot-row-index">Creneau {index + 1}</p>
                                        <label>
                                          Jour
                                          <select name="slot_weekday" defaultValue={slot ? String(slot.weekday) : ""}>
                                            <option value="">Selection a faire</option>
                                            {WEEKDAY_OPTIONS.map((day) => (
                                              <option key={`${row.id}-slot-day-${index}-${day.value}`} value={day.value}>{day.label}</option>
                                            ))}
                                          </select>
                                        </label>
                                        <label>
                                          Heure debut
                                          <input type="time" name="slot_start_time" defaultValue={slot?.start || ""} />
                                        </label>
                                        <p className="muted solfege-slot-row-end">Heure fin: {slot?.end || "Calculee automatiquement"}</p>
                                      </article>
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
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === "variables" ? (
        <section className="card">
          <h3>{t("admin.quote_config.variables_title")}</h3>
          <p className="muted">{t("admin.quote_config.variables_subtitle")}</p>
          <div className="list">
            {templateVariables.map((item) => (
              <article key={item.key} className="item">
                <p><code>{`{${item.key}}`}</code></p>
                <p className="muted">{item.label} - {item.description}</p>
                <p className="muted">{t("admin.quote_config.example_prefix", { example: item.example })}</p>
              </article>
            ))}
          </div>
          <div className="row top-gap-sm">
            <Link className="ghost" href={returnPath}>{t("admin.quote_config.refresh_variables")}</Link>
          </div>
        </section>
      ) : null}
    </section>
  );
}
