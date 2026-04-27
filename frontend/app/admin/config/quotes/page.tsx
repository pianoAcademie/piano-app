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

function pricingUnitLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "per_session") {
    return uiText(language, "admin.quote_config.pricing_unit_per_session");
  }
  if (normalized === "hourly") {
    return uiText(language, "admin.quote_config.pricing_unit_hourly");
  }
  if (normalized === "fixed") {
    return uiText(language, "admin.quote_config.pricing_unit_fixed");
  }
  return value || "-";
}

function computedActivityFallbackPrice(
  activity: AdminActivityOut,
  language: UiLanguage,
): { label: string; amountTtc: number | null; tone: "ok" | "warn" | "off" } {
  const direct = Number(String(activity.default_course_rate_ttc ?? "").trim());
  if (Number.isFinite(direct) && direct > 0) {
    return {
      label: uiText(language, "admin.quote_config.fallback_course_rate"),
      amountTtc: direct,
      tone: "warn",
    };
  }
  const hourly = Number(String(activity.default_hourly_rate ?? "").trim());
  const duration = Number(activity.duration_minutes || 0);
  if (Number.isFinite(hourly) && hourly > 0 && Number.isFinite(duration) && duration > 0) {
    return {
      label: uiText(language, "admin.quote_config.fallback_hourly_rate"),
      amountTtc: hourly * (duration / 60),
      tone: "warn",
    };
  }
  return {
    label: uiText(language, "admin.quote_config.fallback_none"),
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

function typeformConditionsLabel(rawWhen: unknown, language: UiLanguage): string {
  if (!rawWhen || typeof rawWhen !== "object" || Array.isArray(rawWhen)) {
    return uiText(language, "admin.quote_config.always");
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
  return entries.length > 0 ? entries.join(" · ") : uiText(language, "admin.quote_config.always");
}

function collectTypeformTemplatePricingRows(
  configs: TypeformFormConfigOut[],
  options: {
    catalogId: string;
    activityByCode: ReadonlyMap<string, AdminActivityOut>;
    language: UiLanguage;
  },
): TypeformTemplatePricingRow[] {
  const { catalogId, activityByCode, language } = options;
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
      const itemLabel = activity?.name || String(template.title ?? "").trim() || itemCode || uiText(language, "admin.quote_config.line_index", { index: index + 1 });
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
        conditionsLabel: typeformConditionsLabel(template.when, language),
      });
    });
  }
  return rows;
}

const WEEKDAY_VALUES = [0, 1, 2, 3, 4, 5, 6] as const;

const PAYMENT_PLAN_PRESET_OPTIONS: Array<{ value: string; payment_method: string; schedule_type: string }> = [
  { value: "Carte bancaire", payment_method: "CARD", schedule_type: "single" },
  { value: "Carte bancaire mensuelle", payment_method: "CARD_MONTHLY", schedule_type: "monthly" },
  { value: "Cheque en 1 fois", payment_method: "CHECK", schedule_type: "single" },
  { value: "Cheque en 2 fois", payment_method: "CHECK", schedule_type: "split_2" },
  { value: "Cheque en 4 fois", payment_method: "CHECK", schedule_type: "split_4" },
  { value: "Virement bancaire", payment_method: "BANK_TRANSFER", schedule_type: "single" },
  { value: "Especes", payment_method: "CASH", schedule_type: "single" },
  { value: "4 fois avec frais", payment_method: "CARD_4X_FEES", schedule_type: "split_4" },
];

const PAYMENT_SCHEDULE_TYPE_OPTIONS: Array<{ value: string }> = [
  { value: "single" },
  { value: "split_2" },
  { value: "split_3" },
  { value: "split_4" },
  { value: "monthly" },
];

const PAYMENT_METHOD_OPTIONS = ["CARD", "CARD_MONTHLY", "CHECK", "BANK_TRANSFER", "CASH", "CARD_4X_FEES"] as const;
const MONTH_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;

function weekdayLabel(day: number, language: UiLanguage): string {
  if (day < 0 || day > 6) {
    return String(day);
  }
  const locale = language === "en" ? "en-US" : "fr-FR";
  const label = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(2026, 0, 5 + day)),
  );
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function solfegeLevelLabel(level: string, language: UiLanguage): string {
  return uiText(language, "admin.quote_config.solfege_level_option", { level });
}

function paymentPlanPresetLabel(value: string, language: UiLanguage): string {
  const normalized = value.trim();
  if (normalized === "Carte bancaire") return uiText(language, "admin.quote_config.payment_preset_card");
  if (normalized === "Carte bancaire mensuelle") return uiText(language, "admin.quote_config.payment_preset_card_monthly");
  if (normalized === "Cheque en 1 fois") return uiText(language, "admin.quote_config.payment_preset_check_single");
  if (normalized === "Cheque en 2 fois") return uiText(language, "admin.quote_config.payment_preset_check_split_2");
  if (normalized === "Cheque en 4 fois") return uiText(language, "admin.quote_config.payment_preset_check_split_4");
  if (normalized === "Virement bancaire") return uiText(language, "admin.quote_detail.payment_method_bank_transfer");
  if (normalized === "Especes") return uiText(language, "admin.quote_detail.payment_method_cash");
  if (normalized === "4 fois avec frais") return uiText(language, "admin.quote_detail.payment_method_card_4x_fees");
  return value || "-";
}

function paymentScheduleTypeLabel(value: string, language: UiLanguage): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "single") return uiText(language, "admin.quote_config.payment_schedule_single");
  if (normalized === "split_2") return uiText(language, "admin.quote_config.payment_schedule_split_2");
  if (normalized === "split_3") return uiText(language, "admin.quote_config.payment_schedule_split_3");
  if (normalized === "split_4") return uiText(language, "admin.quote_config.payment_schedule_split_4");
  if (normalized === "monthly") return uiText(language, "admin.quote_config.payment_schedule_monthly");
  return value || "-";
}

function paymentMethodLabel(value: string, language: UiLanguage): string {
  const normalized = value.trim().toUpperCase();
  if (!normalized) return "-";
  if (normalized === "CARD") return uiText(language, "admin.quote_detail.payment_method_card");
  if (normalized === "CARD_MONTHLY") return uiText(language, "admin.quote_detail.payment_method_card_monthly");
  if (normalized === "CHECK") return uiText(language, "admin.quote_detail.payment_method_check");
  if (normalized === "BANK_TRANSFER") return uiText(language, "admin.quote_detail.payment_method_bank_transfer");
  if (normalized === "CASH") return uiText(language, "admin.quote_detail.payment_method_cash");
  if (normalized === "CARD_4X_FEES") return uiText(language, "admin.quote_detail.payment_method_card_4x_fees");
  return value;
}

function paymentInstallmentCount(rules: Record<string, unknown>): string {
  const raw = Number.parseInt(String(rules.installment_count ?? ""), 10);
  if (!Number.isFinite(raw) || raw <= 0) {
    return "-";
  }
  return String(raw);
}

function paymentFeePercent(rules: Record<string, unknown>, language: UiLanguage): string {
  const raw = Number.parseFloat(String(rules.fee_percent ?? ""));
  const locale = language === "en" ? "en-US" : "fr-FR";
  if (!Number.isFinite(raw) || raw <= 0) {
    return `0 ${uiText(language, "admin.quote_config.percent_symbol")}`;
  }
  return `${new Intl.NumberFormat(locale, {
    minimumFractionDigits: raw % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(raw)} ${uiText(language, "admin.quote_config.percent_symbol")}`;
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

function monthLabel(month: number, language: UiLanguage): string {
  const locale = language === "en" ? "en-US" : "fr-FR";
  const label = new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(2026, month - 1, 1)),
  );
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function modalityLabel(value: string | null, language: UiLanguage): string {
  const normalized = (value || "").trim().toUpperCase();
  if (normalized === "ONLINE") {
    return uiText(language, "admin.quote_config.modality_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.quote_config.modality_onsite");
  }
  if (normalized === "ANY") {
    return uiText(language, "common.all");
  }
  return "-";
}

function quoteBindingProspectTypeLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return uiText(language, "common.all");
  }
  if (normalized === "adult") {
    return uiText(language, "admin.quote_config.prospect_type_adult");
  }
  if (normalized === "child") {
    return uiText(language, "admin.quote_config.prospect_type_child");
  }
  return value || uiText(language, "common.all");
}

function quoteBindingContextLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return uiText(language, "admin.quote_config.all_contexts");
  }
  if (normalized === "acquisition") {
    return uiText(language, "admin.quote_config.context_acquisition");
  }
  if (normalized === "active_client") {
    return uiText(language, "admin.quote_config.context_active_client");
  }
  return value || uiText(language, "admin.quote_config.all_contexts");
}

function solfegeSlotsCsv(slots: Array<Record<string, unknown>>, language: UiLanguage): string {
  if (!slots.length) {
    return "";
  }
  return slots
    .map((slot) => {
      const weekdayRaw = Number.parseInt(String(slot.weekday ?? ""), 10);
      const weekdayText = Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6
        ? `${weekdayLabel(weekdayRaw, language)}`
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
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
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
  const paymentPlanPresetOptions = PAYMENT_PLAN_PRESET_OPTIONS.map((option) => ({
    ...option,
    label: paymentPlanPresetLabel(option.value, language),
  }));
  const paymentMethodOptions = PAYMENT_METHOD_OPTIONS.map((value) => ({
    value,
    label: paymentMethodLabel(value, language),
  }));
  const paymentScheduleTypeOptions = PAYMENT_SCHEDULE_TYPE_OPTIONS.map((option) => ({
    ...option,
    label: paymentScheduleTypeLabel(option.value, language),
  }));
  const paymentMonthOptions = MONTH_VALUES.map((value) => ({
    value,
    label: monthLabel(value, language),
  }));
  const defaultQuoteTemplateSubject = t("admin.quote_config.default_quote_template_subject");
  const defaultQuoteTemplateBody = t("admin.quote_config.default_quote_template_body");
  const defaultQuoteTemplateFallbackBody = t("admin.quote_config.default_quote_template_fallback_body");
  const defaultTermsVersionLabel = t("admin.quote_config.default_terms_version_label");
  const defaultTermsContent = t("admin.quote_config.default_terms_content");
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
          <h3>{t("admin.quote_config.types_title")}</h3>
          <p className="muted">{t("admin.quote_config.types_subtitle")}</p>
          <form action={createAdminQuoteTypeConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
            <label className="span-2">
              {t("common.name")}
              <input type="text" name="name" required maxLength={180} placeholder={t("admin.quote_config.quote_type_name_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.expiry_days")}
              <input type="number" name="default_expiry_days" min={1} max={120} defaultValue={10} required />
            </label>
            <label>
              {t("admin.quote_config.default_school_year")}
              <input type="text" name="school_year_label" maxLength={40} placeholder={t("admin.quote_config.school_year_placeholder")} />
            </label>
            <label className="span-2">
              {t("admin.quote_config.linked_formula")}
              <select name="formula_id" defaultValue="">
                <option value="">{t("admin.quote_config.none_option")}</option>
                {formulas.map((formula) => (
                  <option key={formula.id} value={formula.id}>
                    {formula.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="span-3">
              {t("common.description")}
              <input type="text" name="description" maxLength={2000} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <div className="row span-4">
              <button type="submit">{t("admin.quote_config.add_quote_type")}</button>
            </div>
          </form>

          <div className="list top-gap-sm">
            {quoteTypes.length === 0 ? <p className="muted">{t("admin.quote_config.no_quote_types")}</p> : null}
            {quoteTypes.map((row) => (
              <article key={row.id} className="item">
                <div className="row spread wrap gap-sm">
                  <div>
                    <strong>{row.name}</strong>
                    <p className="muted">{t("admin.quote_config.quote_type_meta", { code: row.code, days: row.default_expiry_days })}</p>
                    <p className="muted">
                      {t("admin.quote_config.quote_type_formula_school_year", {
                        formula: row.formula_name || "-",
                        school_year: row.school_year_label || "-",
                      })}
                    </p>
                    <small className="muted">{row.description || t("admin.quote_config.no_description")}</small>
                  </div>
                  <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? t("common.active") : t("common.inactive")}</span>
                </div>
                <details>
                  <summary className="mode-link">{t("common.edit")}</summary>
                  <form action={updateAdminQuoteTypeConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
                    <input type="hidden" name="quote_type_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
                    <label className="span-2">
                      {t("common.name")}
                      <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                    </label>
                    <label>
                      {t("admin.quote_config.expiry_days")}
                      <input type="number" name="default_expiry_days" min={1} max={120} defaultValue={row.default_expiry_days} required />
                    </label>
                    <label>
                      {t("admin.quote_config.default_school_year")}
                      <input type="text" name="school_year_label" defaultValue={row.school_year_label || ""} maxLength={40} />
                    </label>
                    <label className="span-2">
                      {t("admin.quote_config.linked_formula")}
                      <select name="formula_id" defaultValue={row.formula_id || ""}>
                        <option value="">{t("admin.quote_config.none_option")}</option>
                        {formulas.map((formula) => (
                          <option key={formula.id} value={formula.id}>
                            {formula.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="span-3">
                      {t("common.description")}
                      <input type="text" name="description" defaultValue={row.description || ""} maxLength={2000} />
                    </label>
                    <label className="checkline">
                      <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                      {t("common.active")}
                    </label>
                    <div className="row span-4">
                      <button type="submit">{t("common.save")}</button>
                    </div>
                  </form>
                  <form action={deleteAdminQuoteTypeConfigAction} className="row top-gap-sm">
                    <input type="hidden" name="quote_type_id" value={row.id} />
                    <input type="hidden" name="return_to" value={buildQuotesConfigHref("types")} />
                    <button type="submit" className="danger">{t("common.delete")}</button>
                  </form>
                </details>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {tab === "catalogs" ? (
        <section className="card">
          <h3>{t("admin.quote_config.catalogs_title")}</h3>
          <form action={createAdminPricingCatalogConfigAction} className="grid cols-4 config-form-grid">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
            <label className="span-2">
              {t("common.name")}
              <input type="text" name="name" required maxLength={180} placeholder={t("admin.quote_config.catalog_name_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.school_year")}
              <input type="text" name="school_year_label" maxLength={40} placeholder={t("admin.quote_config.school_year_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.start_date")}
              <input type="date" name="effective_from" required />
            </label>
            <label>
              {t("admin.quote_config.end_date")}
              <input type="date" name="effective_to" />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_default" />
              {t("admin.quote_config.default_catalog")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <div className="row span-4">
              <button type="submit">{t("admin.quote_config.add_catalog")}</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("common.name")}</th>
                  <th>{t("admin.quote_config.year_short")}</th>
                  <th>{t("common.period")}</th>
                  <th>{t("admin.quote_config.pricing_sources")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("admin.quote_config.updated_short")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {catalogs.length === 0 ? (
                  <tr><td colSpan={7}><p className="muted">{t("admin.quote_config.no_catalogs")}</p></td></tr>
                ) : (
                  catalogs.map((row) => {
                    const explicitActivityPrices = pricingActivityPrices
                      .filter((price) => price.catalog_id === row.id && price.is_active)
                      .sort((left, right) => {
                        const leftActivity = activities.find((item) => item.id === left.activity_id)?.name ?? "";
                        const rightActivity = activities.find((item) => item.id === right.activity_id)?.name ?? "";
                        const byActivity = leftActivity.localeCompare(rightActivity, sortLocale);
                        if (byActivity !== 0) {
                          return byActivity;
                        }
                        const leftLocation = left.location_id ? (locationById.get(left.location_id) ?? "") : "";
                        const rightLocation = right.location_id ? (locationById.get(right.location_id) ?? "") : "";
                        return leftLocation.localeCompare(rightLocation, sortLocale);
                      });
                    const explicitActivityIds = new Set(explicitActivityPrices.map((price) => price.activity_id));
                    const fallbackActivities = activeActivities
                      .filter((activity) => !explicitActivityIds.has(activity.id))
                      .map((activity) => ({
                        activity,
                        fallback: computedActivityFallbackPrice(activity, language),
                      }));
                    const typeformTemplatePricingRows = collectTypeformTemplatePricingRows(typeformFormConfigs, {
                      catalogId: row.id,
                      activityByCode,
                      language,
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
                          <div><strong>{explicitActivityPrices.length}</strong> {t("admin.quote_config.explicit_price_count", { count: explicitActivityPrices.length })}</div>
                          <div className="muted">
                            {t("admin.quote_config.catalog_source_summary", {
                              fallback_available: fallbackAvailableCount,
                              typeform_override: typeformOverrideCount,
                              typeform_fallback: typeformFallbackCount,
                              missing: fallbackMissingCount,
                            })}
                          </div>
                        </td>
                        <td>
                          <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? t("common.active") : t("common.inactive")}</span>
                          {row.is_default ? <span className="badge">{t("admin.quote_config.default_badge")}</span> : null}
                        </td>
                        <td>{dateTimeLabel(row.updated_at, language)}</td>
                        <td>
                          <details>
                            <summary className="mode-link">{t("common.edit")}</summary>
                            <form action={updateAdminPricingCatalogConfigAction} className="grid config-form-grid top-gap-sm">
                              <input type="hidden" name="catalog_id" value={row.id} />
                              <input type="hidden" name="return_to" value={buildQuotesConfigHref("catalogs")} />
                              <label>
                                {t("common.name")}
                                <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                              </label>
                              <label>
                                {t("admin.quote_config.school_year")}
                                <input type="text" name="school_year_label" defaultValue={row.school_year_label || ""} maxLength={40} />
                              </label>
                              <label>
                                {t("admin.quote_config.start_date")}
                                <input type="date" name="effective_from" defaultValue={dateInputValue(row.effective_from)} required />
                              </label>
                              <label>
                                {t("admin.quote_config.end_date")}
                                <input type="date" name="effective_to" defaultValue={dateInputValue(row.effective_to)} />
                              </label>
                              <label className="checkline">
                                <input type="checkbox" name="is_default" defaultChecked={row.is_default} />
                                {t("admin.quote_config.default_badge")}
                              </label>
                              <label className="checkline">
                                <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                                {t("common.active")}
                              </label>
                              <div className="row">
                                <button type="submit">{t("common.save")}</button>
                              </div>
                            </form>

                            <div className="top-gap-sm">
                              <h4>{t("admin.quote_config.pricing_sources_diagnostics_title")}</h4>
                              <p className="muted">{t("admin.quote_config.pricing_sources_diagnostics_help")}</p>

                              <div className="table-wrap top-gap-sm">
                                <table className="data-table">
                                  <thead>
                                    <tr>
                                      <th>{t("admin.quote_config.typeform_price_title")}</th>
                                      <th>{t("admin.quote_config.form_label")}</th>
                                      <th>{t("admin.quote_config.mode")}</th>
                                      <th>{t("admin.quote_config.amount_ttc")}</th>
                                      <th>{t("admin.quote_config.condition")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {typeformTemplatePricingRows.length === 0 ? (
                                      <tr>
                                        <td colSpan={5}>
                                          <p className="muted">{t("admin.quote_config.no_typeform_prices")}</p>
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
                                              {item.mode === "override" ? t("admin.quote_config.typeform_mode_override") : t("admin.quote_config.typeform_mode_fallback")}
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
                                      <th>{t("admin.quote_config.activity")}</th>
                                      <th>{t("common.location")}</th>
                                      <th>{t("admin.quote_config.unit")}</th>
                                      <th>{t("common.source")}</th>
                                      <th>{t("admin.quote_config.amount_ttc")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {explicitActivityPrices.length === 0 ? (
                                      <tr>
                                        <td colSpan={5}>
                                          <p className="muted">{t("admin.quote_config.no_explicit_prices")}</p>
                                        </td>
                                      </tr>
                                    ) : (
                                      explicitActivityPrices.map((price) => {
                                        const activity = activities.find((item) => item.id === price.activity_id);
                                        const locationName = price.location_id ? (locationById.get(price.location_id) ?? price.location_id) : t("admin.quote_config.all_sites");
                                        const sourceLabel = price.location_id ? t("admin.quote_config.source_catalog_specific") : t("admin.quote_config.source_catalog_general");
                                        return (
                                          <tr key={price.id}>
                                            <td>
                                              <strong>{activity?.name || price.activity_id}</strong>
                                              <div className="muted"><code>{activity?.code || price.activity_id}</code></div>
                                            </td>
                                            <td>{locationName}</td>
                                            <td>{pricingUnitLabel(price.pricing_unit, language)}</td>
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
                                      <th>{t("admin.quote_config.activity_without_explicit_price")}</th>
                                      <th>{t("admin.quote_config.mode")}</th>
                                      <th>{t("admin.quote_config.fallback")}</th>
                                      <th>{t("admin.quote_config.fallback_amount")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {fallbackActivities.length === 0 ? (
                                      <tr>
                                        <td colSpan={4}>
                                          <p className="muted">{t("admin.quote_config.all_activities_priced")}</p>
                                        </td>
                                      </tr>
                                    ) : (
                                      fallbackActivities.map(({ activity, fallback }) => (
                                        <tr key={`${row.id}-${activity.id}`}>
                                          <td>
                                            <strong>{activity.name}</strong>
                                            <div className="muted"><code>{activity.code}</code></div>
                                          </td>
                                          <td>{modalityLabel(activity.mode, language)}</td>
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
                              <button type="submit" className="danger">{t("common.delete")}</button>
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
          <h3>{t("admin.quote_config.payment_plans_title")}</h3>
          <p className="muted">{t("admin.quote_config.payment_plans_subtitle")}</p>
          <form action={createAdminPaymentPlanConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
            <label className="span-2">
              {t("admin.quote_config.payment_plan_preset_label")}
              <select name="plan_label_preset" defaultValue="Carte bancaire" required>
                <option value="">{t("admin.quote_config.select_option")}</option>
                {paymentPlanPresetOptions.map((option) => (
                  <option key={`preset-create-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.payment_method")}
              <select name="payment_method" defaultValue="CARD" required>
                {paymentMethodOptions.map((option) => (
                  <option key={`payment-method-create-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.payment_schedule_type")}
              <select name="schedule_type" defaultValue="single" required>
                {paymentScheduleTypeOptions.map((option) => (
                  <option key={`schedule-create-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.fees_percent")}
              <input type="number" name="fee_percent" min={0} max={100} step="0.01" defaultValue="0" />
            </label>
            <label>
              {t("admin.quote_config.due_month_2")}
              <select name="due_month_2" defaultValue="2">
                <option value="">{t("admin.quote_config.auto_option")}</option>
                {paymentMonthOptions.map((option) => (
                  <option key={`create-month2-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.due_month_3")}
              <select name="due_month_3" defaultValue="2">
                <option value="">{t("admin.quote_config.auto_option")}</option>
                {paymentMonthOptions.map((option) => (
                  <option key={`create-month3-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.due_month_4")}
              <select name="due_month_4" defaultValue="4">
                <option value="">{t("admin.quote_config.auto_option")}</option>
                {paymentMonthOptions.map((option) => (
                  <option key={`create-month4-${option.value}`} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="checkline">
              <input type="checkbox" name="collect_all_checks_upfront" defaultChecked />
              {t("admin.quote_config.collect_all_checks_upfront")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="show_schedule_public" defaultChecked />
              {t("admin.quote_config.show_schedule_public")}
            </label>
            <label className="checkline">
              <input type="checkbox" name="show_schedule_pdf" defaultChecked />
              {t("admin.quote_config.show_schedule_pdf")}
            </label>
            <label className="span-2">
              {t("admin.quote_config.check_submission_address_optional")}
              <textarea name="check_submission_address" rows={2} placeholder={t("admin.quote_config.check_submission_address_placeholder")} />
            </label>
            <label className="span-2">
              {t("admin.quote_config.check_submission_instruction_optional")}
              <textarea
                name="check_submission_instruction"
                rows={2}
                placeholder={t("admin.quote_config.check_submission_instruction_placeholder")}
              />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <div className="row span-4">
              <button type="submit">{t("admin.quote_config.add_payment_plan")}</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("admin.quote_config.label")}</th>
                  <th>{t("admin.quote_config.payment_method")}</th>
                  <th>{t("admin.quote_config.payment_schedule_type")}</th>
                  <th>{t("admin.quote_config.installments")}</th>
                  <th>{t("admin.quote_config.fees_percent")}</th>
                  <th>{t("admin.quote_config.instructions")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {paymentPlans.length === 0 ? (
                  <tr><td colSpan={8}><p className="muted">{t("admin.quote_config.no_payment_plans")}</p></td></tr>
                ) : (
                  paymentPlans.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{paymentPlanPresetLabel(row.name, language)}</strong>
                        <div className="muted"><code>{row.code}</code></div>
                      </td>
                      <td>{paymentMethodLabel(row.payment_method, language)}</td>
                      <td>{paymentScheduleTypeLabel(row.schedule_type, language)}</td>
                      <td>{paymentInstallmentCount(row.schedule_rules || {})}</td>
                      <td>{paymentFeePercent(row.schedule_rules || {}, language)}</td>
                      <td>
                        {String((row.schedule_rules?.check_submission_instruction ?? "") || "").trim() || "-"}
                      </td>
                      <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? t("common.active") : t("common.inactive")}</span></td>
                      <td>
                        <details>
                          <summary className="mode-link">{t("common.edit")}</summary>
                          <form action={updateAdminPaymentPlanConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="plan_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
                            <input type="hidden" name="name_current" value={row.name} />
                            <label className="span-2">
                              {t("admin.quote_config.payment_plan_preset_label")}
                              <select name="plan_label_preset" defaultValue={PAYMENT_PLAN_PRESET_OPTIONS.some((item) => item.value === row.name) ? row.name : ""}>
                                <option value="">{t("admin.quote_config.keep_current_option")}</option>
                                {paymentPlanPresetOptions.map((option) => (
                                  <option key={`preset-edit-${row.id}-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label className="span-2">
                              {t("admin.quote_config.custom_label_optional")}
                              <input type="text" name="name_custom" maxLength={180} placeholder={paymentPlanPresetLabel(row.name, language)} />
                            </label>
                            <label>
                              {t("admin.quote_config.payment_method")}
                              <select name="payment_method" defaultValue={row.payment_method} required>
                                {!["CARD", "CARD_MONTHLY", "CHECK", "BANK_TRANSFER", "CASH", "CARD_4X_FEES"].includes(row.payment_method) ? (
                                  <option value={row.payment_method}>{row.payment_method}</option>
                                ) : null}
                                {paymentMethodOptions.map((option) => (
                                  <option key={`payment-method-edit-${row.id}-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.payment_schedule_type")}
                              <select name="schedule_type" defaultValue={row.schedule_type} required>
                                {!PAYMENT_SCHEDULE_TYPE_OPTIONS.some((option) => option.value === row.schedule_type) ? (
                                  <option value={row.schedule_type}>{row.schedule_type}</option>
                                ) : null}
                                {paymentScheduleTypeOptions.map((option) => (
                                  <option key={`schedule-edit-${row.id}-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.fees_percent")}
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
                              {t("admin.quote_config.due_month_2")}
                              <select name="due_month_2" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 0)}>
                                <option value="">{t("admin.quote_config.auto_option")}</option>
                                {paymentMonthOptions.map((option) => (
                                  <option key={`edit-${row.id}-month2-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.due_month_3")}
                              <select name="due_month_3" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 1)}>
                                <option value="">{t("admin.quote_config.auto_option")}</option>
                                {paymentMonthOptions.map((option) => (
                                  <option key={`edit-${row.id}-month3-${option.value}`} value={option.value}>{option.label}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.due_month_4")}
                              <select name="due_month_4" defaultValue={paymentDeferredMonthValue(row.schedule_rules || {}, 2)}>
                                <option value="">{t("admin.quote_config.auto_option")}</option>
                                {paymentMonthOptions.map((option) => (
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
                              {t("admin.quote_config.collect_all_checks_upfront")}
                            </label>
                            <label className="checkline">
                              <input
                                type="checkbox"
                                name="show_schedule_public"
                                defaultChecked={paymentScheduleVisibilityFlag(row.schedule_rules || {}, "public_page")}
                              />
                              {t("admin.quote_config.show_schedule_public")}
                            </label>
                            <label className="checkline">
                              <input
                                type="checkbox"
                                name="show_schedule_pdf"
                                defaultChecked={paymentScheduleVisibilityFlag(row.schedule_rules || {}, "client_pdf")}
                              />
                              {t("admin.quote_config.show_schedule_pdf")}
                            </label>
                            <label className="span-2">
                              {t("admin.quote_config.check_submission_address_optional")}
                              <textarea
                                name="check_submission_address"
                                rows={2}
                                defaultValue={String((row.schedule_rules?.check_submission_address ?? "") || "")}
                              />
                            </label>
                            <label className="span-2">
                              {t("admin.quote_config.check_submission_instruction_optional")}
                              <textarea
                                name="check_submission_instruction"
                                rows={2}
                                defaultValue={String((row.schedule_rules?.check_submission_instruction ?? "") || "")}
                              />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              {t("common.active")}
                            </label>
                            <div className="row">
                              <button type="submit">{t("common.save")}</button>
                            </div>
                          </form>
                          <form action={deleteAdminPaymentPlanConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="plan_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("payment_plans")} />
                            <button type="submit" className="danger">{t("common.delete")}</button>
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
          <h3>{t("admin.quote_config.doc_bindings_title")}</h3>
          <p className="muted">{t("admin.quote_config.doc_bindings_subtitle")}</p>
          <form action={createAdminQuoteDocumentBindingConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
            <label>
              {t("admin.quote_config.prospect_type")}
              <select name="prospect_type" defaultValue="">
                <option value="">{t("common.all")}</option>
                <option value="adult">{t("admin.quote_config.prospect_type_adult")}</option>
                <option value="child">{t("admin.quote_config.prospect_type_child")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_config.context")}
              <select name="context_type" defaultValue="">
                <option value="">{t("common.all")}</option>
                <option value="acquisition">{t("admin.quote_config.context_acquisition")}</option>
                <option value="active_client">{t("admin.quote_config.context_active_client")}</option>
              </select>
            </label>
            <label>
              {t("admin.quote_config.activity_family")}
              <select name="activity_family" defaultValue="">
                <option value="">{t("common.all")}</option>
                {activityFamilies.map((family) => (
                  <option key={`binding-family-create-${family}`} value={family}>{family}</option>
                ))}
              </select>
            </label>
            <label>
              {t("common.language")}
              <input type="text" name="language" maxLength={8} placeholder={t("admin.quote_config.language_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.currency")}
              <input type="text" name="currency" maxLength={3} placeholder={t("admin.quote_config.currency_placeholder")} />
            </label>
            <label>
              {t("admin.quote_config.quote_type")}
              <select name="quote_type_id" defaultValue="">
                <option value="">{t("common.all")}</option>
                {quoteTypes.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="span-2">
              {t("admin.quote_config.quote_template")}
              <select name="quote_template_id" defaultValue="">
                <option value="">{t("admin.quote_config.none_option")}</option>
                {quoteTemplatesV2.map((row) => (
                  <option key={row.id} value={row.id}>{row.name} ({uiLanguageLabel(row.language, language)})</option>
                ))}
              </select>
            </label>
            <label className="span-2">
              {t("admin.quote_config.terms_template")}
              <select name="terms_template_id" defaultValue="">
                <option value="">{t("admin.quote_config.none_option")}</option>
                {termsTemplates.map((row) => (
                  <option key={row.id} value={row.id}>{row.name} ({uiLanguageLabel(row.language, language)})</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quote_config.priority")}
              <input type="number" name="priority" min={0} max={9999} defaultValue={100} />
            </label>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <label className="span-4">
              {t("common.notes")}
              <input type="text" name="notes" maxLength={2000} />
            </label>
            <div className="row span-4">
              <button type="submit">{t("admin.quote_config.add_binding")}</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="table compact">
              <thead>
                <tr>
                  <th>{t("admin.quote_config.scope")}</th>
                  <th>{t("admin.quote_config.quote_template")}</th>
                  <th>{t("admin.quote_config.terms_template")}</th>
                  <th>{t("admin.quote_config.priority")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {quoteDocumentBindings.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="muted">{t("admin.quote_config.no_bindings")}</td>
                  </tr>
                ) : (
                  quoteDocumentBindings.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{quoteBindingProspectTypeLabel(row.prospect_type, language)}</strong>
                        <div className="muted">
                          {quoteBindingContextLabel(row.context_type, language)} · {row.language || t("admin.quote_config.all_languages")} · {row.currency || t("admin.quote_config.all_currencies")}
                        </div>
                        <div className="muted">
                          {t("admin.quote_config.binding_scope_activity_quote_type", {
                            activity: row.activity_family || t("common.all"),
                            quote_type: row.quote_type_id ? quoteTypes.find((item) => item.id === row.quote_type_id)?.name || row.quote_type_id : t("common.all"),
                          })}
                        </div>
                      </td>
                      <td>{quoteTemplatesV2.find((item) => item.id === row.quote_template_id)?.name || "-"}</td>
                      <td>{termsTemplates.find((item) => item.id === row.terms_template_id)?.name || "-"}</td>
                      <td>{row.priority}</td>
                      <td>
                        <span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? t("common.active") : t("common.inactive")}</span>
                      </td>
                      <td>
                        <details>
                          <summary className="mode-link">{t("common.edit")}</summary>
                          <form action={updateAdminQuoteDocumentBindingConfigAction} className="grid config-form-grid top-gap-sm">
                            <input type="hidden" name="binding_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
                            <label>
                              {t("admin.quote_config.prospect_type")}
                              <select name="prospect_type" defaultValue={row.prospect_type || ""}>
                                <option value="">{t("common.all")}</option>
                                <option value="adult">{t("admin.quote_config.prospect_type_adult")}</option>
                                <option value="child">{t("admin.quote_config.prospect_type_child")}</option>
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.context")}
                              <select name="context_type" defaultValue={row.context_type || ""}>
                                <option value="">{t("common.all")}</option>
                                <option value="acquisition">{t("admin.quote_config.context_acquisition")}</option>
                                <option value="active_client">{t("admin.quote_config.context_active_client")}</option>
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.activity_family")}
                              <select name="activity_family" defaultValue={row.activity_family || ""}>
                                <option value="">{t("common.all")}</option>
                                {activityFamilies.map((family) => (
                                  <option key={`binding-family-edit-${row.id}-${family}`} value={family}>{family}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("common.language")}
                              <input type="text" name="language" defaultValue={row.language || ""} maxLength={8} />
                            </label>
                            <label>
                              {t("admin.quote_config.currency")}
                              <input type="text" name="currency" defaultValue={row.currency || ""} maxLength={3} />
                            </label>
                            <label>
                              {t("admin.quote_config.quote_type")}
                              <select name="quote_type_id" defaultValue={row.quote_type_id || ""}>
                                <option value="">{t("common.all")}</option>
                                {quoteTypes.map((qt) => (
                                  <option key={qt.id} value={qt.id}>{qt.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.quote_template")}
                              <select name="quote_template_id" defaultValue={row.quote_template_id || ""}>
                                <option value="">{t("admin.quote_config.none_option")}</option>
                                {quoteTemplatesV2.map((tpl) => (
                                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.terms_template")}
                              <select name="terms_template_id" defaultValue={row.terms_template_id || ""}>
                                <option value="">{t("admin.quote_config.none_option")}</option>
                                {termsTemplates.map((tpl) => (
                                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                                ))}
                              </select>
                            </label>
                            <label>
                              {t("admin.quote_config.priority")}
                              <input type="number" name="priority" min={0} max={9999} defaultValue={row.priority} />
                            </label>
                            <label className="checkline">
                              <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                              {t("common.active")}
                            </label>
                            <label>
                              {t("common.notes")}
                              <input type="text" name="notes" defaultValue={row.notes || ""} maxLength={2000} />
                            </label>
                            <div className="row">
                              <button type="submit">{t("common.save")}</button>
                            </div>
                          </form>
                          <form action={deleteAdminQuoteDocumentBindingConfigAction} className="row top-gap-sm">
                            <input type="hidden" name="binding_id" value={row.id} />
                            <input type="hidden" name="return_to" value={buildQuotesConfigHref("doc_bindings")} />
                            <button type="submit" className="danger">{t("common.delete")}</button>
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
          <h3>{t("admin.quote_config.solfege_title")}</h3>
          <p className="muted">{t("admin.quote_config.solfege_subtitle")}</p>
          <form action={upsertAdminSolfegeLevelRuleConfigAction} className="solfege-config-form">
            <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
            <div className="grid cols-4 config-form-grid">
              <label>
                {t("admin.quote_config.solfege_level")}
                <select name="level_code" defaultValue="1">
                  <option value="1">{solfegeLevelLabel("1", language)}</option>
                  <option value="2">{solfegeLevelLabel("2", language)}</option>
                  <option value="3">{solfegeLevelLabel("3", language)}</option>
                  <option value="4">{solfegeLevelLabel("4", language)}</option>
                  <option value="5">{solfegeLevelLabel("5", language)}</option>
                </select>
              </label>
              <label>
                {t("admin.quote_config.solfege_duration_minutes")}
                <input type="number" name="duration_minutes" min={10} max={180} defaultValue={30} required />
              </label>
              <label>
                {t("admin.quote_config.solfege_location_optional")}
                <select name="location_id" defaultValue="">
                  <option value="">{t("common.all")}</option>
                  {locations.map((row) => (
                    <option key={row.id} value={row.id}>{row.name}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("admin.quote_config.solfege_modality")}
                <select name="modality" defaultValue="ANY">
                  <option value="ANY">{t("common.all")}</option>
                  <option value="ONLINE">{modalityLabel("ONLINE", language)}</option>
                  <option value="ONSITE">{modalityLabel("ONSITE", language)}</option>
                </select>
              </label>
            </div>
            <div className="solfege-slot-editor">
              <h4>{t("admin.quote_config.solfege_slot_lines")}</h4>
              <p className="muted">{t("admin.quote_config.solfege_slot_lines_help_create")}</p>
              <div className="solfege-slot-grid top-gap-sm">
                {Array.from({ length: 6 }).map((_, index) => (
                  <article key={`create-solfege-slot-${index}`} className="solfege-slot-row">
                    <p className="solfege-slot-row-index">{t("admin.quote_config.solfege_slot_index", { index: index + 1 })}</p>
                    <label>
                      {t("admin.quote_config.solfege_day")}
                      <select name="slot_weekday" defaultValue="">
                        <option value="">{t("admin.quote_config.select_option")}</option>
                        {WEEKDAY_VALUES.map((day) => (
                          <option key={`create-solfege-slot-day-${index}-${day}`} value={day}>{weekdayLabel(day, language)}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.quote_config.solfege_start_time")}
                      <input type="time" name="slot_start_time" defaultValue="" />
                    </label>
                    <p className="muted solfege-slot-row-end">{t("admin.quote_config.solfege_end_time_auto")}</p>
                  </article>
                ))}
              </div>
            </div>
            <label className="checkline">
              <input type="checkbox" name="is_active" defaultChecked />
              {t("common.active")}
            </label>
            <div className="row">
              <button type="submit">{t("admin.quote_config.solfege_add_or_update")}</button>
            </div>
          </form>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("admin.quote_config.solfege_level")}</th>
                  <th>{t("admin.quote_config.solfege_duration")}</th>
                  <th>{t("admin.quote_config.solfege_slots")}</th>
                  <th>{t("admin.quote_config.solfege_location")}</th>
                  <th>{t("admin.quote_config.solfege_mode")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {solfegeRules.length === 0 ? (
                  <tr><td colSpan={7}><p className="muted">{t("admin.quote_config.solfege_no_rules")}</p></td></tr>
                ) : (
                  solfegeRules.map((row) => {
                    const editSlots = solfegeSlotRows(row.allowed_time_slots);
                    const levelKnown = ["1", "2", "3", "4", "5"].includes(row.level_code);
                    return (
                      <tr key={row.id}>
                        <td>{solfegeLevelLabel(row.level_code, language)}</td>
                        <td>{t("admin.quote_config.solfege_duration_short", { minutes: row.duration_minutes })}</td>
                        <td>{solfegeSlotsCsv(row.allowed_time_slots, language) || "-"}</td>
                        <td>{row.location_id ? (locationById.get(row.location_id) || row.location_id) : t("common.all")}</td>
                        <td>{modalityLabel(row.modality, language)}</td>
                        <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? t("common.active") : t("common.inactive")}</span></td>
                        <td>
                          <details>
                            <summary className="mode-link">{t("common.edit")}</summary>
                            <form action={upsertAdminSolfegeLevelRuleConfigAction} className="solfege-config-form top-gap-sm">
                              <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
                              <div className="grid cols-4 config-form-grid">
                                <label>
                                  {t("admin.quote_config.solfege_level")}
                                  <select name="level_code" defaultValue={row.level_code}>
                                    {!levelKnown ? <option value={row.level_code}>{solfegeLevelLabel(row.level_code, language)}</option> : null}
                                    <option value="1">{solfegeLevelLabel("1", language)}</option>
                                    <option value="2">{solfegeLevelLabel("2", language)}</option>
                                    <option value="3">{solfegeLevelLabel("3", language)}</option>
                                    <option value="4">{solfegeLevelLabel("4", language)}</option>
                                    <option value="5">{solfegeLevelLabel("5", language)}</option>
                                  </select>
                                </label>
                                <label>
                                  {t("admin.quote_config.solfege_duration_minutes")}
                                  <input type="number" name="duration_minutes" min={10} max={180} defaultValue={row.duration_minutes} required />
                                </label>
                                <label>
                                  {t("admin.quote_config.solfege_location")}
                                  <select name="location_id" defaultValue={row.location_id || ""}>
                                    <option value="">{t("common.all")}</option>
                                    {locations.map((location) => (
                                      <option key={location.id} value={location.id}>{location.name}</option>
                                    ))}
                                  </select>
                                </label>
                                <label>
                                  {t("admin.quote_config.solfege_modality")}
                                  <select name="modality" defaultValue={(row.modality || "ANY").toUpperCase()}>
                                    <option value="ANY">{t("common.all")}</option>
                                    <option value="ONLINE">{modalityLabel("ONLINE", language)}</option>
                                    <option value="ONSITE">{modalityLabel("ONSITE", language)}</option>
                                  </select>
                                </label>
                              </div>
                              <div className="solfege-slot-editor">
                                <h4>{t("admin.quote_config.solfege_slot_lines")}</h4>
                                <p className="muted">{t("admin.quote_config.solfege_slot_lines_help_edit")}</p>
                                <div className="solfege-slot-grid top-gap-sm">
                                  {Array.from({ length: Math.max(6, editSlots.length) }).map((_, index) => {
                                    const slot = editSlots[index];
                                    return (
                                      <article key={`${row.id}-slot-edit-${index}`} className="solfege-slot-row">
                                        <p className="solfege-slot-row-index">{t("admin.quote_config.solfege_slot_index", { index: index + 1 })}</p>
                                        <label>
                                          {t("admin.quote_config.solfege_day")}
                                          <select name="slot_weekday" defaultValue={slot ? String(slot.weekday) : ""}>
                                            <option value="">{t("admin.quote_config.select_option")}</option>
                                            {WEEKDAY_VALUES.map((day) => (
                                              <option key={`${row.id}-slot-day-${index}-${day}`} value={day}>{weekdayLabel(day, language)}</option>
                                            ))}
                                          </select>
                                        </label>
                                        <label>
                                          {t("admin.quote_config.solfege_start_time")}
                                          <input type="time" name="slot_start_time" defaultValue={slot?.start || ""} />
                                        </label>
                                        <p className="muted solfege-slot-row-end">
                                          {slot?.end
                                            ? t("admin.quote_config.solfege_end_time_value", { time: slot.end })
                                            : t("admin.quote_config.solfege_end_time_auto")}
                                        </p>
                                      </article>
                                    );
                                  })}
                                </div>
                              </div>
                              <label className="checkline">
                                <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                                {t("common.active")}
                              </label>
                              <div className="row">
                                <button type="submit">{t("common.save")}</button>
                              </div>
                            </form>
                            <form action={deleteAdminSolfegeLevelRuleConfigAction} className="row top-gap-sm">
                              <input type="hidden" name="rule_id" value={row.id} />
                              <input type="hidden" name="return_to" value={buildQuotesConfigHref("solfege")} />
                              <button type="submit" className="danger">{t("common.delete")}</button>
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
