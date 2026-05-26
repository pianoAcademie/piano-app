import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ConfirmSubmitButton from "../../../../components/confirm-submit-button";
import CopyLinkButton from "../../../../components/copy-link-button";
import QuoteEmailPreviewSubmitButton from "../../../../components/quote-email-preview-submit-button";
import QuoteClientMatchCard from "../../../../components/quotes/quote-client-match-card";
import QuoteIntegrationProjectionCard from "../../../../components/quotes/quote-integration-projection-card";
import QuoteIntegrationResultCard from "../../../../components/quotes/quote-integration-result-card";
import QuoteOverviewSection from "../../../../components/quotes/quote-overview-section";
import QuoteQuickTransformPanel from "../../../../components/quotes/quote-quick-transform-panel";
import QuoteRightSummaryRail from "../../../../components/quotes/quote-right-summary-rail";
import type { QuoteIntegrationUiState } from "../../../../components/quotes/quote-row-integration-state";
import type { QuoteValidationUiState } from "../../../../components/quotes/quote-row-validation-state";
import QuoteValidationIntegrationSection from "../../../../components/quotes/quote-validation-integration-section";
import QuoteWorkspaceHeader from "../../../../components/quotes/quote-workspace-header";
import QuoteWorkspaceShell from "../../../../components/quotes/quote-workspace-shell";
import QuoteWorkspaceSidebar, { type SidebarItem } from "../../../../components/quotes/quote-workspace-sidebar";
import QuoteFollowupSlotForm from "../../../../components/quote-followup-slot-form";
import QuoteLinesEditor from "../../../../components/quote-lines-editor";
import QuotePlanningEditor from "../../../../components/quote-planning-editor";
import RichMessageEditor from "../../../../components/rich-message-editor";
import {
  cancelQuoteAction,
  changeQuoteFollowupPaymentMethodAction,
  duplicateQuoteAction,
  duplicateQuoteForChildAction,
  finalizeQuoteFollowupAction,
  logQuoteManualReplyAction,
  quickTransformQuoteAction,
  regenerateQuoteDocumentAction,
  resendQuoteAction,
  resendQuotePublicConfirmationAction,
  rollbackQuoteTransformationAction,
  restoreQuotePublicResponseAction,
  selectQuoteFollowupSlotAction,
  sendQuoteManualEmailAction,
  sendQuoteAction,
  updateQuoteLinesAction,
  updateQuotePlanningAction,
  updateQuoteSettingsAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { hasAdminPermission } from "../../../../lib/admin-access";
import { loadLivePlanningMatchForBlock, type LivePlanningBlockInput } from "../../../../lib/quote-planning-live";
import {
  analyzeQuoteQuickTransformStatus,
  deriveCalendarSnapshotActivityIds,
  type QuoteQuickTransformAnalysis,
  type QuoteTransformActivityCatalog,
  type QuoteTransformClient,
  type QuoteTransformLine,
  type QuoteTransformPlan,
  type QuoteTransformProspect,
  type QuoteTransformQuote,
  type QuoteTransformSession,
} from "../../../../lib/quote-transformation";
import type {
  AdminActivityOut,
  AdminCatalogKitOut,
  AdminCatalogProductOut,
  AdminClientOut,
  AdminClientFamilyOut,
  AdminLegalEntityOut,
  AdminMessagingSettingsOut,
  AdminMessagingTemplateOut,
  AdminSessionOut,
  LocationOut,
  PlanOut,
  UserOut,
} from "../../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
import { resolveUiFlashMessage, withUiLanguage, withUiMessageCode } from "../../../../lib/ui-messages";

type SearchParams = Record<string, string | string[] | undefined>;
type QuoteWorkspaceSection =
  | "overview"
  | "cadre"
  | "planning"
  | "pricing"
  | "document"
  | "interactions"
  | "integration";

type RouteParams = {
  params: {
    quoteId: string;
  };
  searchParams: SearchParams;
};

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone?: string | null;
  parent_prospect_id?: string | null;
  meta?: Record<string, unknown>;
};

type QuoteLineOut = {
  id: string;
  line_type: string;
  line_category: string;
  master_item_type: string | null;
  activity_id: string | null;
  product_id: string | null;
  kit_id: string | null;
  title: string;
  quantity: string;
  vat_rate: string;
  unit_price_ht: string;
  unit_vat_amount: string;
  unit_price_ttc: string;
  amount_ht: string;
  amount_vat: string;
  amount_ttc: string;
  meta: Record<string, unknown>;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  context_type: string;
  legal_entity_id: string | null;
  quote_type_id: string | null;
  pricing_catalog_id: string | null;
  payment_plan_id: string | null;
  quote_template_id: string | null;
  quote_template_version_id: string | null;
  terms_template_id: string | null;
  terms_template_version_id: string | null;
  currency: string;
  language: string | null;
  total_ttc: string;
  vat_rate: string | null;
  expiry_days: number;
  created_at: string;
  expires_at: string | null;
  sent_at: string | null;
  approved_at: string | null;
  prospect_id: string | null;
  client_id: string | null;
  location_id: string | null;
  quote_type: string;
  school_year_label: string | null;
  estimated_solfege_level: string | null;
  selected_solfege_slot: Record<string, unknown>;
  calendar_snapshot: Record<string, unknown>;
  payment_terms_snapshot: Record<string, unknown>;
  cgv_snapshot: Record<string, unknown>;
  meta: Record<string, unknown>;
  document_status: string;
  document_snapshot_id: string | null;
  document_hash: string | null;
  document_generated_at: string | null;
  public_token: string | null;
  pdf_token: string | null;
  public_url: string | null;
  public_pdf_url: string | null;
};

type QuoteDetailOut = {
  quote: QuoteOut;
  lines: QuoteLineOut[];
  events: QuoteEventOut[];
  intake_summary?: QuoteIntakeSummaryOut | null;
};

type QuoteIntakeSummaryOut = {
  parent_name: string | null;
  student_name: string | null;
  birth_date: string | null;
  is_reenrollment: boolean | null;
  requested_pass_recup: boolean | null;
  quote_pass_recup: boolean | null;
  pass_recup_status: string | null;
  warnings: string[];
};

type QuoteEventOut = {
  id: string;
  event_type: string;
  actor_type: string | null;
  actor_id: string | null;
  actor_label: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

type QuoteFollowupOut = {
  id: string;
  quote_id: string;
  target_client_id: string | null;
  status: string;
  payment_method_status: string;
  solfege_slot_status: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type PaymentPlanOut = {
  id: string;
  name: string;
  payment_method: string;
};

type QuoteTypeOut = {
  id: string;
  name: string;
  default_expiry_days: number;
  formula_id: string | null;
  formula_name: string | null;
  school_year_label: string | null;
};

type PricingCatalogOut = {
  id: string;
  name: string;
};

type PricingActivityPriceOut = {
  id: string;
  catalog_id: string;
  activity_id: string;
  location_id: string | null;
  unit_price_ttc: string;
  is_active: boolean;
};

type PricingProductPriceOut = {
  id: string;
  catalog_id: string;
  product_id: string;
  unit_price_ttc: string;
  is_active: boolean;
};

type PricingKitPriceOut = {
  id: string;
  catalog_id: string;
  kit_id: string;
  unit_price_ttc: string;
  is_active: boolean;
};

type QuoteDiscountRuleOut = {
  id: string;
  code: string;
  label: string;
  unit_price_ttc: string;
  vat_rate: string;
  currency: string;
  is_active: boolean;
  sort_order: number;
};

type TermsTemplateOut = {
  id: string;
  name: string;
  language: string;
};

type QuoteTemplateV2Out = {
  id: string;
  code: string;
  name: string;
  template_type: string;
  target?: string | null;
  language: string;
  is_default: boolean;
};

type QuoteTransformationFailureUi = {
  title: string;
  summary: string;
  guidance: string;
  actionLabel: string | null;
  actionHref: string | null;
  technicalMessage: string;
};

type SolfegeLevelRuleOut = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
};

type QuoteDocumentPreviewOut = {
  quote_id: string;
  audience: string;
  document_hash: string;
  document_status: string;
  quote_body_html: string;
  terms_html: string;
  combined_html: string;
  display_flags: Record<string, boolean>;
  visible_blocks: string[];
  hidden_blocks: string[];
  payment_schedule_compact_notice: string;
};

type QuoteSchoolCalendarResolveOut = {
  calendar: Record<string, unknown> | null;
  holiday_dates: string[];
  closure_dates: string[];
};

type PlanningCalendarPreset = {
  location_id: string;
  modality: string;
  calendar_name: string;
  holiday_dates: string[];
  closure_dates: string[];
};

function messagingTemplateRef(template: AdminMessagingTemplateOut): string {
  if (template.kind === "PREDEFINED") {
    return `predefined:${template.code || ""}`;
  }
  return `custom:${template.id}`;
}

function messagingTemplateOptionLabel(template: AdminMessagingTemplateOut, language: UiLanguage = "fr"): string {
  const suffix = template.kind === "PREDEFINED"
    ? uiText(language, "admin.quote_detail.template_system")
    : uiText(language, "admin.quote_detail.template_custom");
  return `${template.name} · ${suffix}`;
}

function normalizeTemplateAudienceText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function templateAudienceScore(template: AdminMessagingTemplateOut, audience: "child" | "adult"): number {
  const haystack = normalizeTemplateAudienceText(`${template.name || ""} ${template.code || ""}`);
  if (!haystack.trim()) {
    return 0;
  }
  const childTokens = ["enfant", "child", "eleve", "famille", "parent"];
  const adultTokens = ["adulte", "adult"];
  const wantedTokens = audience === "child" ? childTokens : adultTokens;
  const unwantedTokens = audience === "child" ? adultTokens : childTokens;
  let score = 0;
  for (const token of wantedTokens) {
    if (haystack.includes(token)) {
      score += 2;
    }
  }
  for (const token of unwantedTokens) {
    if (haystack.includes(token)) {
      score -= 3;
    }
  }
  return score;
}

function resolveAudienceAwareTemplateRef(
  templates: AdminMessagingTemplateOut[],
  {
    audience,
    fallbackRef,
  }: {
    audience: "child" | "adult";
    fallbackRef: string;
  },
): string {
  let bestTemplate: AdminMessagingTemplateOut | null = null;
  let bestScore = 0;
  for (const template of templates) {
    const score = templateAudienceScore(template, audience);
    if (score > bestScore) {
      bestScore = score;
      bestTemplate = template;
    }
  }
  if (bestTemplate) {
    return messagingTemplateRef(bestTemplate);
  }
  return fallbackRef;
}

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function immediateBackendResult<T>(data: T): Promise<{ ok: true; status: number; data: T }> {
  return Promise.resolve({ ok: true, status: 200, data });
}

function parseWorkspaceSection(value: string): QuoteWorkspaceSection {
  const normalized = String(value || "").trim().toLowerCase();
  if (
    normalized === "overview"
    || normalized === "cadre"
    || normalized === "planning"
    || normalized === "pricing"
    || normalized === "document"
    || normalized === "interactions"
    || normalized === "integration"
  ) {
    return normalized;
  }
  return "overview";
}

function parseQuickScenario(raw: string): "live" | "A" | "B" | "C" {
  const normalized = String(raw || "").trim().toUpperCase();
  if (normalized === "A" || normalized === "B" || normalized === "C") {
    return normalized;
  }
  return "live";
}

function appendQuickScenario(path: string, quickScenario: "live" | "A" | "B" | "C"): string {
  if (quickScenario === "live") {
    return path;
  }
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}quick_scenario=${encodeURIComponent(quickScenario)}`;
}

function appendQueryParam(path: string, key: string, value: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
}

function buildQuoteTransformationFailureUi(
  technicalMessage: string,
  transformBasePath: string,
  language: UiLanguage = "fr",
): QuoteTransformationFailureUi {
  const normalized = String(technicalMessage || "").trim().toLowerCase();
  if (normalized.includes("correspondance live")) {
    return {
      title: uiText(language, "admin.quote_detail.transform_failure.live_title"),
      summary: uiText(language, "admin.quote_detail.transform_failure.live_summary"),
      guidance:
        uiText(language, "admin.quote_detail.transform_failure.live_guidance"),
      actionLabel: uiText(language, "admin.quote_detail.transform_failure.live_action"),
      actionHref: `${transformBasePath}&step=3`,
      technicalMessage,
    };
  }
  if (
    normalized.includes("n'est plus reservable")
    || normalized.includes("selectionne introuvable")
    || normalized.includes("aucun creneau")
    || normalized.includes("capacity")
    || normalized.includes("plein")
  ) {
    return {
      title: uiText(language, "admin.quote_detail.transform_failure.slot_title"),
      summary: uiText(language, "admin.quote_detail.transform_failure.slot_summary"),
      guidance:
        uiText(language, "admin.quote_detail.transform_failure.slot_guidance"),
      actionLabel: uiText(language, "admin.quote_detail.transform_failure.slot_action"),
      actionHref: `${transformBasePath}&step=3`,
      technicalMessage,
    };
  }
  return {
    title: uiText(language, "admin.quote_detail.transform_failure.generic_title"),
    summary: uiText(language, "admin.quote_detail.transform_failure.generic_summary"),
    guidance:
      uiText(language, "admin.quote_detail.transform_failure.generic_guidance"),
    actionLabel: uiText(language, "admin.quote_detail.transform_failure.generic_action"),
    actionHref: transformBasePath,
    technicalMessage,
  };
}

function formatDate(value: string | null, language: UiLanguage = "fr"): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function formatDateOnly(value: string | null, language: UiLanguage = "fr"): string {
  if (!value) {
    return "-";
  }
  const parts = value.split("-").map(Number);
  if (parts.length >= 3 && parts[0] && parts[1] && parts[2]) {
    return new Intl.DateTimeFormat(localeForUiLanguage(language), {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(new Date(parts[0], parts[1] - 1, parts[2]));
  }
  return formatDate(value, language);
}

function formatAmount(value: string, currency: string, language: UiLanguage = "fr"): string {
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

function toNumber(value: string | number | null | undefined, fallback = 0): number {
  const parsed = Number(String(value ?? "").replace(",", "."));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return parsed;
}

function isSolfegeActivityName(value: string | null | undefined): boolean {
  return String(value || "")
    .trim()
    .toLowerCase()
    .includes("solfege");
}

function paymentMethodLabel(methodCode: string, language: UiLanguage = "fr"): string {
  const normalized = String(methodCode || "").trim().toUpperCase();
  if (normalized === "CARD") return uiText(language, "admin.quote_detail.payment_method_card");
  if (normalized === "CARD_MONTHLY") return uiText(language, "admin.quote_detail.payment_method_card_monthly");
  if (normalized === "CHECK") return uiText(language, "admin.quote_detail.payment_method_check");
  if (normalized === "BANK_TRANSFER") return uiText(language, "admin.quote_detail.payment_method_bank_transfer");
  if (normalized === "CASH") return uiText(language, "admin.quote_detail.payment_method_cash");
  if (normalized === "CARD_4X_FEES") return uiText(language, "admin.quote_detail.payment_method_card_4x_fees");
  if (!normalized) return "-";
  return normalized;
}

function labelForContext(contextType: string, language: UiLanguage = "fr"): string {
  return contextType === "active_client"
    ? uiText(language, "admin.quotes.context_active_client")
    : uiText(language, "admin.quotes.context_acquisition");
}

function labelForProspectType(value: string, language: UiLanguage = "fr"): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "child") return uiText(language, "admin.quote_detail.prospect_type_child");
  if (normalized === "adult") return uiText(language, "admin.quote_detail.prospect_type_adult");
  return "-";
}

function labelForClientKind(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const normalized = String(value || "").trim().toUpperCase();
  if (normalized === "CHILD") return uiText(language, "admin.quote_detail.prospect_type_child");
  if (normalized === "ADULT") return uiText(language, "admin.quote_detail.prospect_type_adult");
  return "-";
}

function labelForQuoteStatus(value: string | null | undefined, language: UiLanguage = "fr"): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "created") return uiText(language, "admin.quotes.status_created");
  if (normalized === "sent") return uiText(language, "admin.quotes.status_sent");
  if (normalized === "approved") return uiText(language, "admin.quotes.status_approved");
  if (normalized === "rejected") return uiText(language, "admin.quotes.status_rejected");
  if (normalized === "change_requested") return uiText(language, "admin.quotes.validation.modification_demandee");
  if (normalized === "cancelled") return uiText(language, "admin.quotes.status_cancelled");
  if (normalized === "expired") return uiText(language, "admin.quotes.status_expired");
  return normalized || "-";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string | null, language: UiLanguage = "fr"): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback || uiText(language, "admin.quote_detail.default_client");
}

function visibleEmail(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  if (normalized.endsWith("@piano-academie.invalid") || normalized.endsWith("@no-email.local")) {
    return "";
  }
  return normalized;
}

function locationNameById(locations: LocationOut[], locationId: string | null, language: UiLanguage = "fr"): string {
  if (!locationId) {
    return uiText(language, "admin.quote_detail.location_not_defined");
  }
  return locations.find((row) => row.id === locationId)?.name || uiText(language, "admin.quote_detail.location_not_defined");
}

function getScheduleItems(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.schedule;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function formatScheduleDueLabel(item: Record<string, unknown>, language: UiLanguage = "fr"): string {
  const dueType = String(item.due_type ?? "").trim().toLowerCase();
  const dueLabel = String(item.due_label ?? "").trim();
  const normalized = dueLabel.toLowerCase();
  if (dueType === "on_registration") {
    return uiText(language, "admin.quote_detail.schedule_due_on_registration");
  }
  if (
    normalized === "a reception"
    || normalized === "a reception du dossier"
    || normalized === "a reception de votre facture"
    || normalized === "à reception"
    || normalized === "à reception du dossier"
    || normalized === "à reception de votre facture"
    || normalized === "à réception"
    || normalized === "à réception du dossier"
    || normalized === "à réception de votre facture"
  ) {
    return uiText(language, "admin.quote_detail.schedule_due_on_registration");
  }
  if (dueLabel) {
    return dueLabel;
  }
  return dueType || "-";
}

function getCalendarSessions(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.sessions;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function planningKeyFromActivityAndSource(activityId: string, source: string): string {
  return source ? `${activityId}:${source}` : activityId;
}

function planningKeyFromSnapshotItem(item: Record<string, unknown>): string {
  const recommendationKey = String(item.recommendation_key ?? "").trim();
  if (recommendationKey) {
    return recommendationKey;
  }
  return String(item.activity_id ?? "").trim();
}

function planningKeyFromQuoteLine(line: QuoteLineOut): string {
  const activityId = String(line.activity_id ?? "").trim();
  if (!activityId) {
    return "";
  }
  const source = readStringMeta(line.meta || {}, "typeform_automatic_line");
  return planningKeyFromActivityAndSource(activityId, source);
}

function monthLabel(month: number, language: UiLanguage): string {
  try {
    const label = new Intl.DateTimeFormat(localeForUiLanguage(language), { month: "long" }).format(new Date(2026, month - 1, 1));
    return label.charAt(0).toUpperCase() + label.slice(1);
  } catch {
    return String(month);
  }
}

type PlanningSummaryBlock = {
  key: string;
  title: string;
  count: number;
  semester1: Array<{ monthLabel: string; days: string }>;
  semester2: Array<{ monthLabel: string; days: string }>;
};

type LivePlanningSeriesOption = {
  key: string;
  activity_id: string;
  activity_label: string | null;
  location_id: string;
  location_label: string | null;
  series_key: string;
  weekday: number;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  sessions_count: number;
  planning_session_limit: number | null;
  modality: string | null;
  label: string;
};

const QUOTE_PLANNING_WEEKDAY_KEYS: Record<number, string> = {
  0: "common.weekday_monday",
  1: "common.weekday_tuesday",
  2: "common.weekday_wednesday",
  3: "common.weekday_thursday",
  4: "common.weekday_friday",
  5: "common.weekday_saturday",
  6: "common.weekday_sunday",
};

function planningVisualSummary(sessions: Array<Record<string, unknown>>, language: UiLanguage = "fr"): PlanningSummaryBlock[] {
  const grouped = new Map<string, Map<number, number[]>>();
  for (const session of sessions) {
    const dateRaw = String(session.date ?? "").trim();
    const parsed = dateRaw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!parsed) {
      continue;
    }
    const month = Number.parseInt(parsed[2], 10);
    const day = Number.parseInt(parsed[3], 10);
    if (!Number.isFinite(month) || !Number.isFinite(day) || month < 1 || month > 12 || day < 1 || day > 31) {
      continue;
    }
    const activityLabel = String(session.activity_label ?? "").trim() || uiText(language, "admin.quote_lines.untitled_activity");
    const locationLabel = String(session.location_label ?? "").trim();
    const title = locationLabel ? `${activityLabel} · ${locationLabel}` : activityLabel;
    const key = title;
    if (!grouped.has(key)) {
      grouped.set(key, new Map<number, number[]>());
    }
    const monthMap = grouped.get(key)!;
    if (!monthMap.has(month)) {
      monthMap.set(month, []);
    }
    monthMap.get(month)!.push(day);
  }

  const toEntries = (monthMap: Map<number, number[]>, semester: 1 | 2): Array<{ monthLabel: string; days: string }> => {
    const schoolYearMonthOrder = (month: number): number => (month >= 9 ? month : month + 12);
    const months = Array.from(monthMap.keys()).sort((a, b) => schoolYearMonthOrder(a) - schoolYearMonthOrder(b));
    return months
      .filter((month) => (semester === 1 ? month >= 9 || month <= 1 : month >= 2 && month <= 8))
      .map((month) => {
        const days = Array.from(new Set(monthMap.get(month) || [])).sort((a, b) => a - b);
        return {
          monthLabel: monthLabel(month, language),
          days: days.join(", "),
        };
      });
  };

  return Array.from(grouped.entries()).map(([key, monthMap]) => {
    const count = Array.from(monthMap.values()).reduce((sum, days) => sum + days.length, 0);
    return {
      key,
      title: key,
      count,
      semester1: toEntries(monthMap, 1),
      semester2: toEntries(monthMap, 2),
    };
  });
}

function safeBackPath(raw: string): string {
  const value = raw.trim();
  if (value.startsWith("/admin/quotes")) {
    return value;
  }
  return "/admin/quotes";
}

function readStringMeta(meta: Record<string, unknown>, key: string, fallback = ""): string {
  const raw = meta[key];
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim();
  }
  return fallback;
}

function parseVatRateValue(value: unknown): number | null {
  const normalized = String(value ?? "").trim().replace(",", ".");
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function formatVatRateValue(value: number): string {
  return value.toFixed(2);
}

function resolveDefaultVatRate(detail: QuoteDetailOut): string {
  const meta = detail.quote.meta || {};
  const directCandidates: unknown[] = [
    detail.quote.vat_rate,
    readStringMeta(meta, "tva_rate", ""),
    readStringMeta(meta, "default_vat_rate", ""),
  ];
  for (const candidate of directCandidates) {
    const parsed = parseVatRateValue(candidate);
    if (parsed !== null) {
      return formatVatRateValue(parsed);
    }
  }
  for (const line of detail.lines) {
    const parsed = parseVatRateValue(line.vat_rate);
    if (parsed !== null) {
      return formatVatRateValue(parsed);
    }
  }
  return "20.00";
}

function normalizeLang(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || "fr";
}

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function getPlanningBlocks(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.blocks;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function snapshotSessionMatchesPlanningBlock(
  session: Record<string, unknown>,
  block: Record<string, unknown>,
): boolean {
  const activityId = String(block.activity_id ?? "").trim();
  if (activityId && String(session.activity_id ?? "").trim() !== activityId) {
    return false;
  }
  const startTime = String(block.start_time ?? "").trim();
  if (startTime && String(session.start_time ?? "").trim() !== startTime) {
    return false;
  }
  const blockWeekday = Number.parseInt(String(block.weekday ?? ""), 10);
  if (Number.isFinite(blockWeekday) && blockWeekday >= 0 && blockWeekday <= 6) {
    const sessionWeekday = Number.parseInt(String(session.weekday ?? ""), 10);
    if (Number.isFinite(sessionWeekday) && sessionWeekday >= 0 && sessionWeekday <= 6 && sessionWeekday !== blockWeekday) {
      return false;
    }
  }
  const blockLocationId = String(block.location_id ?? "").trim();
  const blockModality = normalizePlanningBlockModality(block.modality);
  if (blockLocationId && blockModality !== "ONLINE" && String(session.location_id ?? "").trim() !== blockLocationId) {
    return false;
  }
  return true;
}

function countSnapshotSessionsForPlanningBlock(
  snapshot: Record<string, unknown>,
  block: Record<string, unknown>,
): number {
  return getCalendarSessions(snapshot).filter((session) => snapshotSessionMatchesPlanningBlock(session, block)).length;
}

function normalizeCalendarDateList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return Array.from(
    new Set(
      value
        .map((item) => String(item).trim())
        .filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item)),
    ),
  ).sort((left, right) => left.localeCompare(right));
}

function deriveSchoolYearLabelFromDate(value: unknown): string | null {
  const trimmed = String(value ?? "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }
  const year = Number.parseInt(trimmed.slice(0, 4), 10);
  const month = Number.parseInt(trimmed.slice(5, 7), 10);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) {
    return null;
  }
  const startYear = month >= 9 ? year : year - 1;
  return `${startYear}-${startYear + 1}`;
}

function schoolYearDateRangeFromLabel(label: string | null | undefined): { from: string; to: string } | null {
  const match = String(label ?? "").match(/(20\d{2})\s*[-/]\s*(20\d{2})/);
  if (!match) {
    return null;
  }
  const startYear = Number.parseInt(match[1], 10);
  const endYear = Number.parseInt(match[2], 10);
  if (!Number.isFinite(startYear) || !Number.isFinite(endYear) || endYear !== startYear + 1) {
    return null;
  }
  return {
    from: `${startYear}-09-01T00:00:00.000Z`,
    to: `${endYear}-08-31T23:59:59.999Z`,
  };
}

function derivePlanningSnapshotSchoolYearLabel(
  snapshot: Record<string, unknown>,
  fallback: string | null | undefined,
): string | null {
  const labels = Array.from(
    new Set(
      getPlanningBlocks(snapshot)
        .map((block) => deriveSchoolYearLabelFromDate(block.start_date))
        .filter((label): label is string => Boolean(label)),
    ),
  );
  if (labels.length === 1) {
    return labels[0];
  }
  return fallback || null;
}

function normalizePlanningBlockModality(value: unknown): "ONLINE" | "ONSITE" | null {
  const normalized = String(value ?? "").trim().toUpperCase();
  if (normalized === "ONLINE" || normalized === "ONSITE") {
    return normalized;
  }
  return null;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function adminSessionLocalParts(session: AdminSessionOut): { date: string; start_time: string; end_time: string; weekday: number } | null {
  const timezone = session.timezone || "Europe/Paris";
  const partsFor = (iso: string): { date: string; time: string; weekday: number } | null => {
    const instant = new Date(iso);
    if (Number.isNaN(instant.getTime())) {
      return null;
    }
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(instant);
    const pick = (type: Intl.DateTimeFormatPartTypes): number => {
      const value = parts.find((part) => part.type === type)?.value ?? "0";
      return Number.parseInt(value, 10);
    };
    const year = pick("year");
    const month = pick("month");
    const day = pick("day");
    const hour = pick("hour");
    const minute = pick("minute");
    if (![year, month, day, hour, minute].every(Number.isFinite)) {
      return null;
    }
    const date = `${year}-${pad2(month)}-${pad2(day)}`;
    const utcDay = new Date(`${date}T00:00:00Z`).getUTCDay();
    return {
      date,
      time: `${pad2(hour)}:${pad2(minute)}`,
      weekday: utcDay === 0 ? 6 : utcDay - 1,
    };
  };
  const start = partsFor(session.start_at_utc);
  const end = partsFor(session.end_at_utc);
  if (!start || !end) {
    return null;
  }
  return {
    date: start.date,
    start_time: start.time,
    end_time: end.time,
    weekday: start.weekday,
  };
}

function formatDateForLivePlanningLabel(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return value;
  }
  return `${match[3]}/${match[2]}/${match[1]}`;
}

function positiveInt(value: unknown): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function quoteLinePlanningLimit(line: QuoteLineOut): number {
  const meta = readObject(line.meta || {}) || {};
  const template = readObject(meta.typeform_template) || {};
  return positiveInt(meta.planning_session_limit)
    || positiveInt(template.planning_session_limit)
    || positiveInt(line.quantity);
}

function inferUniqueActivityPlanningLimit(activityId: string, lines: QuoteLineOut[]): number {
  const candidates = lines
    .filter((line) => String(line.line_category || "").toLowerCase() === "service")
    .filter((line) => String(line.line_type || "").toLowerCase() === "item")
    .filter((line) => String(line.activity_id || "") === activityId)
    .map(quoteLinePlanningLimit)
    .filter((limit) => limit > 0);
  const unique = Array.from(new Set(candidates));
  return unique.length === 1 ? unique[0] : 0;
}

function dateOnly(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function isoDateOnly(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function expectedWeeklyDates({
  startDate,
  endDate,
  weekday,
  excludedDates,
  limit,
}: {
  startDate: string;
  endDate: string;
  weekday: number;
  excludedDates: Set<string>;
  limit: number;
}): string[] {
  const start = dateOnly(startDate);
  const end = dateOnly(endDate);
  if (!start || !end || end < start || weekday < 0 || weekday > 6) {
    return [];
  }
  const out: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    const iso = isoDateOnly(cursor);
    if (cursor.getUTCDay() === (weekday + 1) % 7 && !excludedDates.has(iso)) {
      out.push(iso);
      if (limit > 0 && out.length >= limit) {
        break;
      }
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

function calendarPresetForLiveSeries(
  presets: PlanningCalendarPreset[],
  locationId: string,
  modality: string | null,
): PlanningCalendarPreset | null {
  const normalizedModality = normalizePlanningBlockModality(modality) || "";
  return presets.find((preset) => preset.location_id === locationId && normalizePlanningBlockModality(preset.modality) === normalizedModality)
    ?? presets.find((preset) => preset.location_id === locationId && !normalizePlanningBlockModality(preset.modality))
    ?? null;
}

async function loadLivePlanningSeriesOptions({
  token,
  schoolYearLabel,
  activities,
  lines,
  calendarPresets,
  language,
}: {
  token: string;
  schoolYearLabel: string | null;
  activities: AdminActivityOut[];
  lines: QuoteLineOut[];
  calendarPresets: PlanningCalendarPreset[];
  language: UiLanguage;
}): Promise<LivePlanningSeriesOption[]> {
  const range = schoolYearDateRangeFromLabel(schoolYearLabel);
  if (!range) {
    return [];
  }
  const activityById = new Map(activities.map((activity) => [activity.id, activity]));
  const query = new URLSearchParams();
  query.set("status", "SCHEDULED");
  query.set("from", range.from);
  query.set("to", range.to);
  const result = await backendRequest<AdminSessionOut[]>(`/api/v1/admin/sessions?${query.toString()}`, {}, token);
  if (!result.ok) {
    return [];
  }

  const groups = new Map<string, Array<{ session: AdminSessionOut; local: { date: string; start_time: string; end_time: string; weekday: number } }>>();
  for (const session of result.data) {
    const local = adminSessionLocalParts(session);
    if (!local) {
      continue;
    }
    const recurrenceKey = String(session.recurrence_group_id || "").trim();
    const fallbackKey = [
      session.course_type_id,
      session.location_id,
      local.weekday,
      local.start_time,
      local.end_time,
    ].join("|");
    const key = recurrenceKey ? `${session.course_type_id}|${session.location_id}|${recurrenceKey}` : fallbackKey;
    const rows = groups.get(key) ?? [];
    rows.push({ session, local });
    groups.set(key, rows);
  }

  const options: LivePlanningSeriesOption[] = [];
  for (const rows of groups.values()) {
    rows.sort((left, right) => {
      const byDate = left.local.date.localeCompare(right.local.date);
      if (byDate !== 0) {
        return byDate;
      }
      return left.local.start_time.localeCompare(right.local.start_time);
    });
    const first = rows[0];
    const last = rows[rows.length - 1];
    if (!first || !last) {
      continue;
    }
    const session = first.session;
    const activity = activityById.get(session.course_type_id);
    const modality = normalizePlanningBlockModality(activity?.mode);
    const preset = calendarPresetForLiveSeries(calendarPresets, session.location_id, modality);
    const excludedDates = new Set([
      ...(activity?.exclude_holidays_in_recurrence === false ? [] : (preset?.holiday_dates ?? [])),
      ...(activity?.exclude_school_vacations_in_recurrence === false ? [] : (preset?.closure_dates ?? [])),
    ]);
    const filteredRows = rows.filter((row) => !excludedDates.has(row.local.date));
    const firstFiltered = filteredRows[0];
    const lastFiltered = filteredRows[filteredRows.length - 1];
    if (!firstFiltered || !lastFiltered) {
      continue;
    }
    const activityLabel = activity?.name || session.type_label || null;
    const planningSessionLimit = inferUniqueActivityPlanningLimit(session.course_type_id, lines);
    const expectedDates = planningSessionLimit > 0
      ? expectedWeeklyDates({
        startDate: firstFiltered.local.date,
        endDate: range.to.slice(0, 10),
        weekday: firstFiltered.local.weekday,
        excludedDates,
        limit: planningSessionLimit,
      })
      : filteredRows.map((row) => row.local.date);
    const startDate = expectedDates[0] ?? firstFiltered.local.date;
    const endDate = expectedDates[expectedDates.length - 1] ?? lastFiltered.local.date;
    const sessionsCount = expectedDates.length || filteredRows.length;
    const weekdayText = uiText(language, QUOTE_PLANNING_WEEKDAY_KEYS[firstFiltered.local.weekday] || "admin.quote_planning.weekday_unset");
    const period = `${formatDateForLivePlanningLabel(startDate)} -> ${formatDateForLivePlanningLabel(endDate)}`;
    const sessionsText = uiText(language, "admin.quote_planning.live_slot_sessions", { count: sessionsCount });
    const seriesKey = String(session.recurrence_group_id || "").trim();
    const optionKey = seriesKey || [
      session.course_type_id,
      session.location_id,
      firstFiltered.local.weekday,
      firstFiltered.local.start_time,
      firstFiltered.local.end_time,
      firstFiltered.local.date,
    ].join("|");
    options.push({
      key: optionKey,
      activity_id: session.course_type_id,
      activity_label: activityLabel,
      location_id: session.location_id,
      location_label: session.location_label || null,
      series_key: seriesKey,
      weekday: firstFiltered.local.weekday,
      start_date: startDate,
      end_date: endDate,
      start_time: firstFiltered.local.start_time,
      end_time: firstFiltered.local.end_time,
      sessions_count: sessionsCount,
      planning_session_limit: planningSessionLimit > 0 ? planningSessionLimit : null,
      modality,
      label: `${weekdayText} ${firstFiltered.local.start_time}-${firstFiltered.local.end_time} · ${period} · ${sessionsText}`,
    });
  }

  return options.sort((left, right) => {
    const byActivity = String(left.activity_label || "").localeCompare(String(right.activity_label || ""));
    if (byActivity !== 0) {
      return byActivity;
    }
    const byLocation = String(left.location_label || "").localeCompare(String(right.location_label || ""));
    if (byLocation !== 0) {
      return byLocation;
    }
    if (left.weekday !== right.weekday) {
      return left.weekday - right.weekday;
    }
    return left.start_time.localeCompare(right.start_time);
  });
}

async function hydratePlanningSnapshotForEditor({
  snapshot,
  token,
  schoolYearLabel,
  activities,
}: {
  snapshot: Record<string, unknown>;
  token: string;
  schoolYearLabel: string | null;
  activities: AdminActivityOut[];
}): Promise<Record<string, unknown>> {
  const blocks = getPlanningBlocks(snapshot);
  if (blocks.length === 0) {
    return snapshot;
  }

  const activityById = new Map(activities.map((activity) => [activity.id, activity]));
  const calendarCache = new Map<string, QuoteSchoolCalendarResolveOut>();
  let didMutate = false;

  const nextBlocks = await Promise.all(
    blocks.map(async (block) => {
      const activityId = String(block.activity_id ?? "").trim();
      const locationId = String(block.location_id ?? "").trim();
      const activity = activityById.get(activityId);
      const shouldExcludeHolidays = activity?.exclude_holidays_in_recurrence !== false;
      const shouldExcludeVacations = activity?.exclude_school_vacations_in_recurrence !== false;
      const hasHolidayDates = Array.isArray(block.holiday_dates);
      const hasClosureDates = Array.isArray(block.closure_dates);
      const currentHolidayDates = shouldExcludeHolidays ? normalizeCalendarDateList(block.holiday_dates) : [];
      const currentClosureDates = shouldExcludeVacations ? normalizeCalendarDateList(block.closure_dates) : [];
      const hasResolvedHolidayDates = !shouldExcludeHolidays || currentHolidayDates.length > 0;
      const hasResolvedClosureDates = !shouldExcludeVacations || currentClosureDates.length > 0;

      if (hasResolvedHolidayDates && hasResolvedClosureDates) {
        if (!shouldExcludeHolidays && hasHolidayDates) {
          didMutate = true;
          return { ...block, holiday_dates: [] };
        }
        if (!shouldExcludeVacations && hasClosureDates) {
          didMutate = true;
          return { ...block, closure_dates: [] };
        }
        return block;
      }

      if (!locationId) {
        didMutate = true;
        return {
          ...block,
          holiday_dates: shouldExcludeHolidays ? currentHolidayDates : [],
          closure_dates: shouldExcludeVacations ? currentClosureDates : [],
        };
      }

      const resolvedModality = normalizePlanningBlockModality(block.modality) ?? normalizePlanningBlockModality(activity?.mode);
      const cacheKey = `${locationId}|${schoolYearLabel || ""}|${resolvedModality || ""}`;
      let resolvedCalendar = calendarCache.get(cacheKey);
      if (!resolvedCalendar) {
        const query = new URLSearchParams();
        if (schoolYearLabel) {
          query.set("school_year_label", schoolYearLabel);
        }
        if (resolvedModality) {
          query.set("modality", resolvedModality);
        }
        const suffix = query.toString() ? `?${query.toString()}` : "";
        const result = await backendRequest<QuoteSchoolCalendarResolveOut>(
          `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(locationId)}${suffix}`,
          {},
          token,
        );
        if (!result.ok) {
          resolvedCalendar = { calendar: null, holiday_dates: currentHolidayDates, closure_dates: currentClosureDates };
        } else if (result.data.calendar || !schoolYearLabel) {
          resolvedCalendar = result.data;
        } else {
          const fallbackQuery = new URLSearchParams();
          if (resolvedModality) {
            fallbackQuery.set("modality", resolvedModality);
          }
          const fallbackSuffix = fallbackQuery.toString() ? `?${fallbackQuery.toString()}` : "";
          const fallbackResult = await backendRequest<QuoteSchoolCalendarResolveOut>(
            `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(locationId)}${fallbackSuffix}`,
            {},
            token,
          );
          resolvedCalendar = fallbackResult.ok
            ? fallbackResult.data
            : { calendar: null, holiday_dates: currentHolidayDates, closure_dates: currentClosureDates };
        }
        calendarCache.set(cacheKey, resolvedCalendar);
      }

      const nextHolidayDates = shouldExcludeHolidays
        ? normalizeCalendarDateList(resolvedCalendar.holiday_dates)
        : [];
      const nextClosureDates = shouldExcludeVacations
        ? normalizeCalendarDateList(resolvedCalendar.closure_dates)
        : [];
      const nextCalendarName = String(block.calendar_name ?? "").trim() || String(resolvedCalendar.calendar?.name ?? "").trim();

      if (
        JSON.stringify(nextHolidayDates) === JSON.stringify(currentHolidayDates) &&
        JSON.stringify(nextClosureDates) === JSON.stringify(currentClosureDates) &&
        nextCalendarName === String(block.calendar_name ?? "")
      ) {
        return block;
      }

      didMutate = true;
      return {
        ...block,
        calendar_name: nextCalendarName,
        holiday_dates: nextHolidayDates,
        closure_dates: nextClosureDates,
      };
    }),
  );

  if (!didMutate) {
    const liveHydrated = await hydratePlanningSnapshotWithLiveSessions({
      snapshot,
      blocks,
      token,
    });
    return liveHydrated || snapshot;
  }

  const calendarHydrated = {
    ...snapshot,
    blocks: nextBlocks,
  };
  const liveHydrated = await hydratePlanningSnapshotWithLiveSessions({
    snapshot: calendarHydrated,
    blocks: nextBlocks,
    token,
  });
  return liveHydrated || calendarHydrated;
}

async function hydratePlanningSnapshotWithLiveSessions({
  snapshot,
  blocks,
  token,
}: {
  snapshot: Record<string, unknown>;
  blocks: Array<Record<string, unknown>>;
  token: string;
}): Promise<Record<string, unknown> | null> {
  const nextBlocks: Array<Record<string, unknown>> = [];
  const liveSessions: Array<Record<string, unknown>> = [];
  let didUseLivePlanning = false;

  for (const block of blocks) {
    const liveMatch = await loadLivePlanningMatchForBlock({
      block: block as LivePlanningBlockInput,
      token,
    });
    if (!liveMatch) {
      nextBlocks.push(block);
      continue;
    }
    const existingCount = countSnapshotSessionsForPlanningBlock(snapshot, block);
    if (existingCount > liveMatch.sessions.length) {
      nextBlocks.push(block);
      continue;
    }
    didUseLivePlanning = true;
    nextBlocks.push(liveMatch.block);
    liveSessions.push(...liveMatch.sessions);
  }

  if (!didUseLivePlanning) {
    return null;
  }

  const liveActivityIds = new Set(liveSessions.map((session) => String(session.activity_id || "")).filter(Boolean));
  const existingSessions = getCalendarSessions(snapshot).filter((session) => {
    const activityId = String(session.activity_id || "");
    return !liveActivityIds.has(activityId);
  });

  return {
    ...snapshot,
    blocks: nextBlocks,
    sessions: [...existingSessions, ...liveSessions].sort((left, right) => {
      const leftDate = String(left.date || "");
      const rightDate = String(right.date || "");
      if (leftDate !== rightDate) {
        return leftDate.localeCompare(rightDate);
      }
      return String(left.start_time || "").localeCompare(String(right.start_time || ""));
    }),
    sessions_count: existingSessions.length + liveSessions.length,
    live_planning_hydrated_at: new Date().toISOString(),
  };
}

async function loadPlanningCalendarPresets({
  token,
  schoolYearLabel,
  locations,
}: {
  token: string;
  schoolYearLabel: string | null;
  locations: LocationOut[];
}): Promise<PlanningCalendarPreset[]> {
  if (locations.length === 0) {
    return [];
  }
  const modalities = ["", "ONSITE", "ONLINE"] as const;
  const rows = await Promise.all(
    locations.flatMap((location) =>
      modalities.map(async (modality) => {
        const query = new URLSearchParams();
        if (schoolYearLabel) {
          query.set("school_year_label", schoolYearLabel);
        }
        if (modality) {
          query.set("modality", modality);
        }
        const suffix = query.toString() ? `?${query.toString()}` : "";
        const result = await backendRequest<QuoteSchoolCalendarResolveOut>(
          `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(location.id)}${suffix}`,
          {},
          token,
        );
        let resolvedCalendar = result.ok ? result.data : null;
        if (resolvedCalendar && !resolvedCalendar.calendar && schoolYearLabel) {
          const fallbackQuery = new URLSearchParams();
          if (modality) {
            fallbackQuery.set("modality", modality);
          }
          const fallbackSuffix = fallbackQuery.toString() ? `?${fallbackQuery.toString()}` : "";
          const fallbackResult = await backendRequest<QuoteSchoolCalendarResolveOut>(
            `/api/v1/quote-school-calendars/active/by-location/${encodeURIComponent(location.id)}${fallbackSuffix}`,
            {},
            token,
          );
          if (fallbackResult.ok) {
            resolvedCalendar = fallbackResult.data;
          }
        }
        return {
          location_id: location.id,
          modality,
          calendar_name: resolvedCalendar ? String(resolvedCalendar.calendar?.name ?? "").trim() : "",
          holiday_dates: resolvedCalendar ? normalizeCalendarDateList(resolvedCalendar.holiday_dates) : [],
          closure_dates: resolvedCalendar ? normalizeCalendarDateList(resolvedCalendar.closure_dates) : [],
        };
      }),
    ),
  );
  return rows;
}

type QuoteFinancialAdjustment = {
  type: "none" | "credit" | "debt";
  amountTtc: number;
  effectiveDate: string;
  label: string;
};

type QuotePreRegistrationDeposit = {
  enabled: boolean;
  amountTtc: number;
};

function parseQuoteFinancialAdjustment(meta: Record<string, unknown>): QuoteFinancialAdjustment {
  const row = readObject(meta.financial_adjustment);
  const rawType = String(row?.type ?? "").trim().toLowerCase();
  const type = rawType === "credit" || rawType === "debt" ? rawType : "none";
  const amount = Number(String(row?.amount_ttc ?? "0"));
  const normalizedAmount = Number.isFinite(amount) && amount > 0 ? amount : 0;
  const effectiveDate = String(row?.effective_date ?? "").trim();
  const label = String(row?.label ?? "").trim();
  if (type === "none" || normalizedAmount <= 0) {
    return { type: "none", amountTtc: 0, effectiveDate: "", label: "" };
  }
  return {
    type,
    amountTtc: normalizedAmount,
    effectiveDate: /^\d{4}-\d{2}-\d{2}$/.test(effectiveDate) ? effectiveDate : "",
    label,
  };
}

function adjustmentSignedAmount(adjustment: QuoteFinancialAdjustment): number {
  if (adjustment.type === "credit") {
    return -adjustment.amountTtc;
  }
  if (adjustment.type === "debt") {
    return adjustment.amountTtc;
  }
  return 0;
}

function adjustmentTypeLabel(type: QuoteFinancialAdjustment["type"], language: UiLanguage = "fr"): string {
  if (type === "credit") {
    return uiText(language, "admin.quote_detail.adjustment_credit");
  }
  if (type === "debt") {
    return uiText(language, "admin.quote_detail.adjustment_debt");
  }
  return uiText(language, "admin.quote_detail.none");
}

function parseQuotePreRegistrationDeposit(meta: Record<string, unknown>): QuotePreRegistrationDeposit {
  const row = readObject(meta.pre_registration_deposit);
  const enabledRaw = row?.enabled;
  const enabled =
    enabledRaw === true ||
    String(enabledRaw ?? "")
      .trim()
      .toLowerCase() === "true" ||
    String(enabledRaw ?? "")
      .trim()
      .toLowerCase() === "yes";
  const amount = Number(String(row?.amount_ttc ?? "200"));
  const normalizedAmount = Number.isFinite(amount) && amount > 0 ? amount : 200;
  if (!enabled) {
    return { enabled: false, amountTtc: normalizedAmount };
  }
  return { enabled: true, amountTtc: normalizedAmount };
}

function commercialStateFromQuote(quote: QuoteOut): QuoteValidationUiState {
  const status = String(quote.status || "").trim().toLowerCase();
  if (status === "approved") return "valide";
  if (status === "rejected" || status === "cancelled") return "refuse";
  if (status === "expired") return "expire";
  if (status === "sent") {
    const meta = quote.meta || {};
    const viewed = ["public_viewed_at", "viewed_at", "consulted_at", "last_viewed_at"].some((key) => {
      const value = meta[key];
      return typeof value === "string" && value.trim().length > 0;
    });
    return viewed ? "consulte" : "envoye";
  }
  if (status === "change_requested") return "modification_demandee";
  if (status === "created") {
    const hasTemplate = Boolean(quote.quote_template_id);
    const hasRecipient = Boolean(quote.prospect_id || quote.client_id);
    const total = Number(quote.total_ttc);
    const hasTotal = Number.isFinite(total) ? Math.abs(total) > 0 : String(quote.total_ttc || "").trim().length > 0;
    if (hasTemplate && hasRecipient && hasTotal) return "pret_a_envoyer";
    if (!hasTemplate || !hasRecipient) return "incomplet";
    return "brouillon";
  }
  return "incomplet";
}

function commercialStateLabel(state: QuoteValidationUiState, language: UiLanguage = "fr"): string {
  const key = {
    brouillon: "admin.quotes.validation.brouillon",
    incomplet: "admin.quotes.validation.incomplet",
    pret_a_envoyer: "admin.quotes.validation.pret_a_envoyer",
    envoye: "admin.quotes.validation.envoye",
    consulte: "admin.quotes.validation.consulte",
    modification_demandee: "admin.quotes.validation.modification_demandee",
    valide: "admin.quotes.validation.valide",
    refuse: "admin.quotes.validation.refuse",
    expire: "admin.quotes.validation.expire",
  }[state];
  return uiText(language, key);
}

function validationClientLabelFromQuote(quote: QuoteOut, language: UiLanguage = "fr"): string {
  const status = String(quote.status || "").trim().toLowerCase();
  if (status === "approved") {
    return uiText(language, "admin.quotes.validation.valide");
  }
  if (status === "change_requested") {
    return uiText(language, "admin.quotes.validation.modification_demandee");
  }
  if (status === "rejected") {
    return uiText(language, "admin.quotes.validation.refuse");
  }
  return uiText(language, "admin.quote_detail.pending");
}

function validationClientDateLabelFromQuote(quote: QuoteOut, language: UiLanguage = "fr"): string {
  const status = String(quote.status || "").trim().toLowerCase();
  const meta = quote.meta || {};
  const lastPublicResponseAt = readStringMeta(meta, "public_response_last_at", "");
  if (status === "approved") {
    return formatDate(quote.approved_at, language);
  }
  if (status === "change_requested") {
    return lastPublicResponseAt
      ? uiText(language, "admin.quotes.received_on", { date: formatDate(lastPublicResponseAt, language) })
      : uiText(language, "admin.quote_detail.received");
  }
  if (status === "rejected") {
    return lastPublicResponseAt
      ? uiText(language, "admin.quote_detail.rejected_on", { date: formatDate(lastPublicResponseAt, language) })
      : uiText(language, "admin.quotes.validation.refuse");
  }
  return uiText(language, "admin.quote_detail.pending");
}

const QUOTE_INTERACTION_EVENT_TYPES = new Set([
  "quote_created",
  "quote_document_regenerated",
  "quote_email_sent",
  "quote_manual_email_sent",
  "quote_manual_email_received",
  "quote_sms_sent",
  "quote_sent",
  "quote_resent",
  "quote_approved",
  "quote_rejected",
  "quote_change_requested",
  "quote_created_from_change_request",
  "quote_public_confirmation_email_failed",
  "quote_public_confirmation_email_skipped",
  "quote_public_response_restored",
  "quote_cancelled",
  "quote_reminder_sent",
  "quote_expired_notification_sent",
  "quote_expired",
  "quote_transformation_executed",
  "quote_transformation_rolled_back",
]);

function quoteConfirmationKindLabel(kind: string, language: UiLanguage = "fr"): string {
  const normalizedKind = kind.trim().toLowerCase();
  if (normalizedKind === "quote_public_approved_confirmation") {
    return uiText(language, "admin.quote_events.kind.approved_confirmation");
  }
  if (normalizedKind === "quote_public_rejected_confirmation") {
    return uiText(language, "admin.quote_events.kind.rejected_confirmation");
  }
  if (normalizedKind === "quote_public_change_requested_confirmation") {
    return uiText(language, "admin.quote_events.kind.change_requested_confirmation");
  }
  return uiText(language, "admin.quote_events.kind.client_confirmation");
}

function quoteConfirmationSkipReasonLabel(reason: string, language: UiLanguage = "fr"): string {
  const normalizedReason = reason.trim().toLowerCase();
  if (normalizedReason === "missing_recipient_email") {
    return uiText(language, "admin.quote_events.reason.missing_recipient_email");
  }
  if (normalizedReason === "delivery_disabled") {
    return uiText(language, "admin.quote_events.reason.delivery_disabled");
  }
  return uiText(language, "admin.quote_events.reason.unknown");
}

function quoteEventTitle(event: QuoteEventOut, language: UiLanguage = "fr"): string {
  const type = String(event.event_type || "").trim().toLowerCase();
  const payload = event.payload || {};
  const kind = typeof payload.kind === "string" ? payload.kind.trim().toLowerCase() : "";
  if (
    type === "quote_email_sent"
    && kind.startsWith("quote_public_")
    && kind.endsWith("_confirmation")
  ) {
    return uiText(language, "admin.quote_events.title.client_confirmation_sent");
  }
  const keyByType: Record<string, string> = {
    quote_created: "admin.quote_events.title.created",
    quote_document_regenerated: "admin.quote_events.title.document_regenerated",
    quote_email_sent: "admin.quote_events.title.email_sent",
    quote_manual_email_sent: "admin.quote_events.title.manual_email_sent",
    quote_manual_email_received: "admin.quote_events.title.manual_email_received",
    quote_sms_sent: "admin.quote_events.title.sms_sent",
    quote_sent: "admin.quote_events.title.sent",
    quote_resent: "admin.quote_events.title.resent",
    quote_approved: "admin.quote_events.title.approved",
    quote_rejected: "admin.quote_events.title.rejected",
    quote_change_requested: "admin.quote_events.title.change_requested",
    quote_created_from_change_request: "admin.quote_events.title.created_from_change_request",
    quote_public_confirmation_email_failed: "admin.quote_events.title.confirmation_failed",
    quote_public_confirmation_email_skipped: "admin.quote_events.title.confirmation_skipped",
    quote_public_response_restored: "admin.quote_events.title.public_response_restored",
    quote_cancelled: "admin.quote_events.title.cancelled",
    quote_reminder_sent: "admin.quote_events.title.reminder_sent",
    quote_expired_notification_sent: "admin.quote_events.title.expired_notification_sent",
    quote_expired: "admin.quote_events.title.expired",
    quote_transformation_executed: "admin.quote_events.title.transformation_executed",
    quote_transformation_rolled_back: "admin.quote_events.title.transformation_rolled_back",
  };
  return keyByType[type] ? uiText(language, keyByType[type]) : type || uiText(language, "admin.quote_events.title.event");
}

function quoteEventTone(event: QuoteEventOut): "client" | "admin" | "system" {
  const type = String(event.event_type || "").trim().toLowerCase();
  if (["quote_approved", "quote_rejected", "quote_change_requested", "quote_manual_email_received"].includes(type)) {
    return "client";
  }
  if (
    ["quote_public_confirmation_email_failed", "quote_public_confirmation_email_skipped"].includes(type)
    && event.actor_type === "admin"
  ) {
    return "admin";
  }
  if (
    [
      "quote_public_response_restored",
      "quote_cancelled",
      "quote_transformation_rolled_back",
      "quote_document_regenerated",
      "quote_email_sent",
      "quote_manual_email_sent",
      "quote_sms_sent",
      "quote_sent",
      "quote_resent",
    ].includes(type)
  ) {
    return "admin";
  }
  return "system";
}

function quoteEventDescription(event: QuoteEventOut, language: UiLanguage = "fr"): string {
  const type = String(event.event_type || "").trim().toLowerCase();
  const payload = event.payload || {};
  const actorLabel = event.actor_label || (
    event.actor_type === "admin"
      ? uiText(language, "admin.quote_events.actor_admin")
      : event.actor_type === "prospect"
      ? uiText(language, "admin.quote_events.actor_client")
      : uiText(language, "admin.quote_events.actor_system")
  );
  const message = typeof payload.message === "string" ? payload.message.trim() : "";
  const recipientEmail = typeof payload.recipient_email === "string" ? payload.recipient_email.trim() : "";
  const senderEmail = typeof payload.sender_email === "string" ? payload.sender_email.trim() : "";
  const subject = typeof payload.subject === "string" ? payload.subject.trim() : "";
  const recipientPhone = typeof payload.recipient_phone === "string" ? payload.recipient_phone.trim() : "";
  const fromStatus = typeof payload.from_status === "string" ? payload.from_status.trim() : "";
  const toStatus = typeof payload.to_status === "string" ? payload.to_status.trim() : "";
  const error = typeof payload.error === "string" ? payload.error.trim() : "";
  const kind = typeof payload.kind === "string" ? payload.kind.trim() : "";
  const reason = typeof payload.reason === "string" ? payload.reason.trim() : "";
  const detail = typeof payload.detail === "string" ? payload.detail.trim() : "";
  if (type === "quote_change_requested") {
    return message || uiText(language, "admin.quote_events.description.change_requested_fallback");
  }
  if (type === "quote_created_from_change_request") {
    const sourceQuoteNumber = typeof payload.source_quote_number === "string" ? payload.source_quote_number.trim() : "";
    const sourceLabel = sourceQuoteNumber || "-";
    return message
      ? uiText(language, "admin.quote_events.description.created_from_change_request_with_message", {
        quote: sourceLabel,
        message,
      })
      : uiText(language, "admin.quote_events.description.created_from_change_request", { quote: sourceLabel });
  }
  if (type === "quote_public_response_restored") {
    return fromStatus || toStatus
      ? uiText(language, "admin.quote_events.description.admin_action_status", {
        actor: actorLabel,
        from: labelForQuoteStatus(fromStatus, language),
        to: labelForQuoteStatus(toStatus, language),
      })
      : uiText(language, "admin.quote_events.description.admin_action", { actor: actorLabel });
  }
  if (type === "quote_document_regenerated") {
    return uiText(language, "admin.quote_events.description.document_regenerated", { actor: actorLabel });
  }
  if (type === "quote_email_sent") {
    if (kind.trim().toLowerCase().startsWith("quote_public_") && kind.trim().toLowerCase().endsWith("_confirmation")) {
      const localizedKind = quoteConfirmationKindLabel(kind, language);
      return recipientEmail
        ? uiText(language, "admin.quote_events.description.client_confirmation_sent_to", {
          email: recipientEmail,
          kind: localizedKind,
        })
        : uiText(language, "admin.quote_events.description.client_confirmation_sent", {
          kind: localizedKind,
        });
    }
    return recipientEmail
      ? uiText(language, "admin.quote_events.description.email_sent_to", { email: recipientEmail })
      : uiText(language, "admin.quote_events.description.email_sent_by", { actor: actorLabel });
  }
  if (type === "quote_manual_email_sent") {
    return recipientEmail
      ? uiText(language, "admin.quote_events.description.manual_email_sent_to", { email: recipientEmail, subject: subject || "-" })
      : uiText(language, "admin.quote_events.description.email_sent_by", { actor: actorLabel });
  }
  if (type === "quote_manual_email_received") {
    return senderEmail
      ? uiText(language, "admin.quote_events.description.manual_email_received_from", { email: senderEmail, subject: subject || "-" })
      : uiText(language, "admin.quote_events.description.manual_email_received");
  }
  if (type === "quote_sms_sent") {
    return recipientPhone
      ? uiText(language, "admin.quote_events.description.sms_sent_to", { phone: recipientPhone })
      : uiText(language, "admin.quote_events.description.sms_sent_by", { actor: actorLabel });
  }
  if (type === "quote_sent" || type === "quote_resent") {
    const channels = [recipientEmail ? `email ${recipientEmail}` : "", recipientPhone ? `SMS ${recipientPhone}` : ""].filter(Boolean).join(" · ");
    return channels
      ? uiText(language, "admin.quote_events.description.sent_via", { channels })
      : uiText(language, "admin.quote_events.description.action_by", { actor: actorLabel });
  }
  if (type === "quote_public_confirmation_email_failed") {
    const localizedKind = quoteConfirmationKindLabel(kind, language);
    const failureReason = error || uiText(language, "admin.quote_events.description.confirmation_failed");
    return recipientEmail
      ? uiText(language, "admin.quote_events.description.client_confirmation_failed_to", {
        email: recipientEmail,
        error: failureReason,
        kind: localizedKind,
      })
      : uiText(language, "admin.quote_events.description.client_confirmation_failed", {
        error: failureReason,
        kind: localizedKind,
      });
  }
  if (type === "quote_public_confirmation_email_skipped") {
    const localizedKind = quoteConfirmationKindLabel(kind, language);
    const localizedReason = detail
      ? `${quoteConfirmationSkipReasonLabel(reason, language)} · ${detail}`
      : quoteConfirmationSkipReasonLabel(reason, language);
    return recipientEmail
      ? uiText(language, "admin.quote_events.description.client_confirmation_skipped_to", {
        email: recipientEmail,
        kind: localizedKind,
        reason: localizedReason,
      })
      : uiText(language, "admin.quote_events.description.client_confirmation_skipped", {
        kind: localizedKind,
        reason: localizedReason,
      });
  }
  if (type === "quote_cancelled") {
    return uiText(language, "admin.quote_events.description.action_by", { actor: actorLabel });
  }
  if (type === "quote_transformation_executed" || type === "quote_transformation_rolled_back") {
    return uiText(language, "admin.quote_events.description.action_by", { actor: actorLabel });
  }
  if (type === "quote_approved" || type === "quote_rejected") {
    return uiText(language, "admin.quote_events.description.public_response");
  }
  if (type === "quote_reminder_sent") {
    return uiText(language, "admin.quote_events.description.reminder_sent");
  }
  if (type === "quote_expired_notification_sent") {
    return uiText(language, "admin.quote_events.description.expired_notification_sent");
  }
  if (type === "quote_expired") {
    return uiText(language, "admin.quote_events.description.expired");
  }
  return uiText(language, "admin.quote_events.description.action_by", { actor: actorLabel });
}

function quoteEventMessageBody(event: QuoteEventOut): string {
  return typeof event.payload?.body === "string" ? event.payload.body.trim() : "";
}

function quoteEventMessageBodyFormat(event: QuoteEventOut): "TEXT" | "HTML" {
  return String(event.payload?.body_format || "").trim().toUpperCase() === "HTML" ? "HTML" : "TEXT";
}

function integrationStateFromQuote(
  quote: QuoteOut,
  commercialState: QuoteValidationUiState,
  followup: QuoteFollowupOut | null,
): QuoteIntegrationUiState {
  if (commercialState === "refuse" || commercialState === "expire") return "non_concerne";
  if (commercialState !== "valide") return "en_attente_validation_client";
  const meta = quote.meta || {};
  const raw = String(meta.integration_status ?? meta.central_integration_status ?? "").trim().toLowerCase();
  if (raw === "a_preparer" || raw === "to_prepare") return "a_preparer";
  if (raw === "a_verifier" || raw === "to_check") return "a_verifier";
  if (raw === "pret_a_integrer" || raw === "ready_to_integrate") return "pret_a_integrer";
  if (raw === "integre" || raw === "integrated") return "integre";
  if (raw === "erreur_integration" || raw === "integration_error") return "erreur_integration";

  const hasError = Boolean(meta.integration_error) || String(meta.integration_error_message ?? "").trim().length > 0;
  if (hasError) return "erreur_integration";
  const integratedAt = String(meta.integration_completed_at ?? "").trim();
  if (integratedAt) return "integre";

  const clientMatchStatus = String(meta.client_match_status ?? "").trim().toLowerCase();
  if (clientMatchStatus === "multiple" || clientMatchStatus === "ambiguous") return "a_verifier";

  const followupPayload = readObject(followup?.payload);
  const execution = readObject(followupPayload?.quote_to_enrollment_execution);
  const executionStatus = String(execution?.status ?? "").trim().toLowerCase();
  if (executionStatus === "executed") return "integre";
  if (executionStatus === "failed") return "erreur_integration";
  if (executionStatus === "rolled_back") return "a_preparer";
  if (followup?.status === "completed") return "pret_a_integrer";
  return "a_preparer";
}

function integrationStateLabel(state: QuoteIntegrationUiState, language: UiLanguage = "fr"): string {
  const key = {
    non_concerne: "admin.quotes.integration.non_concerne",
    en_attente_validation_client: "admin.quotes.integration.en_attente_validation_client",
    a_preparer: "admin.quotes.integration.a_preparer",
    a_verifier: "admin.quotes.integration.a_verifier",
    pret_a_integrer: "admin.quotes.integration.pret_a_integrer",
    integre: "admin.quotes.integration.integre",
    erreur_integration: "admin.quotes.integration.erreur_integration",
  }[state];
  return uiText(language, key);
}

export default async function AdminQuoteDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }
  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_quotes")) {
    redirect("/login?error_code=admin_access_required");
  }
  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    redirect(withUiMessageCode("/admin/quotes", "error", "quote_not_found", { lang: language }));
  }

  const backPath = withUiLanguage(safeBackPath(readParam(searchParams, "back")), language);
  const activeSection = parseWorkspaceSection(readParam(searchParams, "section"));
  const quickScenario = parseQuickScenario(readParam(searchParams, "quick_scenario"));
  const ok = resolveUiFlashMessage(searchParams, language, "ok") || readParam(searchParams, "ok");
  const error = resolveUiFlashMessage(searchParams, language, "error") || readParam(searchParams, "error");
  const needsDocumentPreview = activeSection === "document";
  const needsPlanningEditorData = activeSection === "planning";
  const needsIntegrationAnalysis = activeSection === "integration";
  const needsPricingCatalogPrices = activeSection === "pricing";

  const [
    detailResult,
    followupsResult,
    paymentPlansResult,
    quoteTypesResult,
    plansResult,
    legalEntitiesResult,
    catalogsResult,
    discountRulesResult,
    termsTemplatesResult,
    quoteTemplatesResult,
    activitiesResult,
    productsResult,
    kitsResult,
    locationsResult,
    solfegeRulesResult,
    prospectsResult,
    clientsResult,
    documentPreviewResult,
    messagingSettingsResult,
    quoteSendTemplatesResult,
    quoteSendSmsTemplatesResult,
    quoteCancelTemplatesResult,
    quoteCancelSmsTemplatesResult,
  ] = await Promise.all([
    backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
    backendRequest<PlanOut[]>("/api/v1/plans?active=true", {}, token),
    backendRequest<AdminLegalEntityOut[]>("/api/v1/admin/legal-entities?include_inactive=false", {}, token),
    backendRequest<PricingCatalogOut[]>("/api/v1/pricing-catalogs", {}, token),
    backendRequest<QuoteDiscountRuleOut[]>("/api/v1/quote-discount-rules?active_only=true", {}, token),
    backendRequest<TermsTemplateOut[]>("/api/v1/terms-templates?active_only=true", {}, token),
    backendRequest<QuoteTemplateV2Out[]>("/api/v1/quote-templates-v2?active_only=true", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=800&include_archived=false", {}, token),
    needsDocumentPreview
      ? backendRequest<QuoteDocumentPreviewOut>(
        `/api/v1/quotes/${encodeURIComponent(quoteId)}/document-preview?audience=admin_preview`,
        {},
        token,
      )
      : immediateBackendResult<QuoteDocumentPreviewOut | null>(null),
    backendRequest<AdminMessagingSettingsOut>("/api/v1/admin/config/messaging-settings", {}, token),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=EMAIL&usage_context=QUOTE_SEND&active_only=true",
      {},
      token,
    ),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=SMS&usage_context=QUOTE_SEND&active_only=true",
      {},
      token,
    ),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=EMAIL&usage_context=QUOTE_CANCEL&active_only=true",
      {},
      token,
    ),
    backendRequest<AdminMessagingTemplateOut[]>(
      "/api/v1/admin/config/messaging-templates?channel=SMS&usage_context=QUOTE_CANCEL&active_only=true",
      {},
      token,
    ),
  ]);

  if (!detailResult.ok) {
    return (
      <section className="admin-page-grid">
        <section className="card">
          <h2>{t("admin.quote_detail.page_title")}</h2>
          <p className="flash-err">{detailResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href={backPath}>{t("admin.quote_detail.back_to_quotes")}</Link>
          </div>
        </section>
      </section>
    );
  }

  const detail = detailResult.data;
  const pricingCatalogId = detail.quote.pricing_catalog_id || "";
  const [activityPricesResult, productPricesResult, kitPricesResult] = pricingCatalogId && needsPricingCatalogPrices
    ? await Promise.all([
      backendRequest<PricingActivityPriceOut[]>(
        `/api/v1/pricing-activity-prices?catalog_id=${encodeURIComponent(pricingCatalogId)}`,
        {},
        token,
      ),
      backendRequest<PricingProductPriceOut[]>(
        `/api/v1/pricing-product-prices?catalog_id=${encodeURIComponent(pricingCatalogId)}`,
        {},
        token,
      ),
      backendRequest<PricingKitPriceOut[]>(
        `/api/v1/pricing-kit-prices?catalog_id=${encodeURIComponent(pricingCatalogId)}`,
        {},
        token,
      ),
    ])
    : [null, null, null];
  const followups = followupsResult.ok ? followupsResult.data : [];
  const activeFollowup = followups[0] ?? null;
  const paymentPlans = paymentPlansResult.ok ? paymentPlansResult.data : [];
  const quoteTypes = quoteTypesResult.ok ? quoteTypesResult.data : [];
  const plans = plansResult.ok ? plansResult.data : [];
  const legalEntities = legalEntitiesResult.ok ? legalEntitiesResult.data : [];
  const selectedQuoteType = quoteTypes.find((row) => row.id === detail.quote.quote_type_id) ?? null;
  const catalogs = catalogsResult.ok ? catalogsResult.data : [];
  const discountRules = discountRulesResult.ok ? discountRulesResult.data : [];
  const termsTemplates = termsTemplatesResult.ok ? termsTemplatesResult.data : [];
  const quoteTemplates = quoteTemplatesResult.ok ? quoteTemplatesResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const solfegeRules = solfegeRulesResult.ok ? solfegeRulesResult.data : [];
  const planningEditorSchoolYearLabel = derivePlanningSnapshotSchoolYearLabel(
    detail.quote.calendar_snapshot || {},
    detail.quote.school_year_label,
  );
  const planningCalendarPresets = needsPlanningEditorData
    ? await loadPlanningCalendarPresets({
      token,
      schoolYearLabel: planningEditorSchoolYearLabel,
      locations,
    })
    : [];
  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  let clients = clientsResult.ok ? clientsResult.data : [];
  if (detail.quote.client_id && !clients.some((client) => client.id === detail.quote.client_id)) {
    const selectedClientResult = await backendRequest<AdminClientOut>(
      `/api/v1/admin/clients/${encodeURIComponent(detail.quote.client_id)}`,
      {},
      token,
    );
    if (selectedClientResult.ok) {
      clients = [...clients, selectedClientResult.data];
    }
  }
  const documentPreview = documentPreviewResult.ok ? documentPreviewResult.data : null;
  const messagingSettings = messagingSettingsResult.ok ? messagingSettingsResult.data : null;
  const quoteSendTemplates = quoteSendTemplatesResult.ok ? quoteSendTemplatesResult.data : [];
  const quoteSendSmsTemplates = quoteSendSmsTemplatesResult.ok ? quoteSendSmsTemplatesResult.data : [];
  const quoteCancelTemplates = quoteCancelTemplatesResult.ok ? quoteCancelTemplatesResult.data : [];
  const quoteCancelSmsTemplates = quoteCancelSmsTemplatesResult.ok ? quoteCancelSmsTemplatesResult.data : [];
  const activityPrices = activityPricesResult?.ok ? activityPricesResult.data : [];
  const productPrices = productPricesResult?.ok ? productPricesResult.data : [];
  const kitPrices = kitPricesResult?.ok ? kitPricesResult.data : [];
  const planningSnapshotForEditor = needsPlanningEditorData || needsIntegrationAnalysis
    ? await hydratePlanningSnapshotForEditor({
      snapshot: detail.quote.calendar_snapshot || {},
      token,
      schoolYearLabel: planningEditorSchoolYearLabel,
      activities,
    })
    : detail.quote.calendar_snapshot || {};
  const livePlanningSeries = needsPlanningEditorData
    ? await loadLivePlanningSeriesOptions({
      token,
      schoolYearLabel: planningEditorSchoolYearLabel,
      activities,
      lines: detail.lines,
      calendarPresets: planningCalendarPresets,
      language,
    })
    : [];

  const activityIds = Array.from(new Set(
    [
      ...detail.lines
        .map((line) => line.activity_id)
        .filter((activityId): activityId is string => Boolean(activityId)),
      ...deriveCalendarSnapshotActivityIds(detail.quote.calendar_snapshot || {}),
    ],
  ));

  const sessionsPerActivity = needsIntegrationAnalysis
    ? await Promise.all(
      activityIds.map(async (activityId) => {
        const query = new URLSearchParams();
        query.set("course_type_id", activityId);
        const result = await backendRequest<AdminSessionOut[]>(
          `/api/v1/admin/sessions?${query.toString()}`,
          {},
          token,
        );
        return { activityId, sessions: result.ok ? result.data : [] };
      }),
    )
    : [];

  const activityCatalogPriceByActivityId: Record<string, string> = {};
  const activityCatalogPriceSpecificity: Record<string, number> = {};
  for (const row of activityPrices) {
    if (!row.is_active) {
      continue;
    }
    const specificity = row.location_id ? 1 : 2;
    if (!(row.activity_id in activityCatalogPriceByActivityId) || specificity > (activityCatalogPriceSpecificity[row.activity_id] || 0)) {
      activityCatalogPriceByActivityId[row.activity_id] = String(row.unit_price_ttc ?? "0");
      activityCatalogPriceSpecificity[row.activity_id] = specificity;
    }
  }
  const productCatalogPriceByProductId: Record<string, string> = {};
  for (const row of productPrices) {
    if (!row.is_active || row.product_id in productCatalogPriceByProductId) {
      continue;
    }
    productCatalogPriceByProductId[row.product_id] = String(row.unit_price_ttc ?? "0");
  }
  const kitCatalogPriceByKitId: Record<string, string> = {};
  for (const row of kitPrices) {
    if (!row.is_active || row.kit_id in kitCatalogPriceByKitId) {
      continue;
    }
    kitCatalogPriceByKitId[row.kit_id] = String(row.unit_price_ttc ?? "0");
  }

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));
  const selectedProspectFromList = detail.quote.prospect_id
    ? prospectById.get(detail.quote.prospect_id || "")
    : null;
  const selectedClient = detail.quote.client_id
    ? clientById.get(detail.quote.client_id || "")
    : null;

  const [prospectDetailResult, clientFamilyResult] = await Promise.all([
    detail.quote.prospect_id
      ? backendRequest<ProspectOut>(`/api/v1/prospects/${encodeURIComponent(detail.quote.prospect_id)}`, {}, token)
      : Promise.resolve(null),
    detail.quote.client_id
      ? backendRequest<AdminClientFamilyOut>(`/api/v1/admin/clients/${encodeURIComponent(detail.quote.client_id)}/family`, {}, token)
      : Promise.resolve(null),
  ]);

  const selectedProspect = prospectDetailResult && prospectDetailResult.ok
    ? prospectDetailResult.data
    : selectedProspectFromList || null;
  const clientFamily = clientFamilyResult && clientFamilyResult.ok ? clientFamilyResult.data : null;

  const owner = detail.quote.context_type === "acquisition"
    ? selectedProspect
    : selectedClient;

  const ownerName = owner
    ? displayName(owner.first_name, owner.last_name, owner.email, language)
    : "-";
  const ownerPhone = selectedProspect?.phone
    || selectedClient?.mobile_phone_1
    || selectedClient?.phone
    || selectedClient?.home_phone
    || "-";
  const prospectMeta = readObject(selectedProspect?.meta) || {};
  const prospectType = String(prospectMeta.prospect_type ?? "").trim().toLowerCase();
  const prospectTypeLabel = labelForProspectType(prospectType, language);
  const clientKindLabel = labelForClientKind(selectedClient?.client_kind, language);
  const sourceTypeLabel = prospectTypeLabel !== "-" ? prospectTypeLabel : clientKindLabel;
  const sourceTypeOrigin = prospectTypeLabel !== "-" ? "prospect" : clientKindLabel !== "-" ? "client" : "inconnu";
  const isChildSource = prospectType === "child" || selectedClient?.client_kind === "CHILD";
  const parentReferent = readObject(prospectMeta.parent_referent);
  const parentReferentName = parentReferent
    ? displayName(
      typeof parentReferent.first_name === "string" ? parentReferent.first_name : null,
      typeof parentReferent.last_name === "string" ? parentReferent.last_name : null,
      typeof parentReferent.email === "string" ? parentReferent.email : t("admin.quote_detail.parent_referent"),
      language,
    )
    : "-";
  const parentReferentEmail = parentReferent && typeof parentReferent.email === "string" ? parentReferent.email : "-";
  const parentReferentPhone = parentReferent && typeof parentReferent.phone === "string" ? parentReferent.phone : "-";

  const familyLinks = clientFamily
    ? [
      ...clientFamily.links_as_adult.map((link) => ({
        key: `adult-${link.id}`,
        role: t("admin.quote_detail.linked_child"),
        personName: displayName(link.child.first_name, link.child.last_name, link.child.email, language),
        personEmail: visibleEmail(link.child.email) || "-",
        billing: link.is_billing_recipient,
      })),
      ...clientFamily.links_as_child.map((link) => ({
        key: `child-${link.id}`,
        role: t("admin.quote_detail.linked_adult"),
        personName: displayName(link.adult.first_name, link.adult.last_name, link.adult.email, language),
        personEmail: visibleEmail(link.adult.email) || "-",
        billing: link.is_billing_recipient,
      })),
    ]
    : [];
  const inferredParentFromFamily = clientFamily
    ? (clientFamily.links_as_child.find((link) => link.is_billing_recipient) ?? clientFamily.links_as_child[0] ?? null)
    : null;
  const resolvedParentReferentName = parentReferentName !== "-"
    ? parentReferentName
    : inferredParentFromFamily
      ? displayName(
        inferredParentFromFamily.adult.first_name,
        inferredParentFromFamily.adult.last_name,
        inferredParentFromFamily.adult.email,
        language,
      )
      : "-";
  const resolvedParentReferentEmail = parentReferentEmail !== "-"
    ? parentReferentEmail
    : inferredParentFromFamily?.adult.email ?? "-";
  const resolvedParentReferentPhone = parentReferentPhone !== "-"
    ? parentReferentPhone
    : inferredParentFromFamily?.adult.mobile_phone_1
      || inferredParentFromFamily?.adult.phone
      || inferredParentFromFamily?.adult.home_phone
      || "-";
  const quoteStatus = String(detail.quote.status || "").trim().toLowerCase();
  const publicResponseLastAction = readStringMeta(detail.quote.meta || {}, "public_response_last_action", "")
    .trim()
    .toLowerCase();
  const publicResponseLastMessage = readStringMeta(detail.quote.meta || {}, "public_response_last_message", "");
  const publicResponseLastAt = readStringMeta(detail.quote.meta || {}, "public_response_last_at", "");
  const changeRequestRevisionQuoteId = readStringMeta(detail.quote.meta || {}, "change_request_revision_quote_id", "");
  const changeRequestRevisionQuoteNumber = readStringMeta(detail.quote.meta || {}, "change_request_revision_quote_number", "");
  const revisionSourceQuoteId = readStringMeta(detail.quote.meta || {}, "revision_source_quote_id", "");
  const revisionSourceQuoteNumber = readStringMeta(detail.quote.meta || {}, "revision_source_quote_number", "");
  const revisionChangeRequestMessage = readStringMeta(detail.quote.meta || {}, "revision_change_request_message", "");
  const revisionChangeRequestAt = readStringMeta(detail.quote.meta || {}, "revision_change_request_at", "");
  const hasRevisionChangeRequest = Boolean(revisionSourceQuoteId && revisionChangeRequestMessage);
  const hasPublicChangeRequest = quoteStatus === "change_requested" || publicResponseLastAction === "change_requested" || hasRevisionChangeRequest;
  const hasChangeRequestRevision = Boolean(changeRequestRevisionQuoteId);
  const publicChangeRequestReceivedLabel = publicResponseLastAt
    ? formatDate(publicResponseLastAt, language)
    : revisionChangeRequestAt
    ? formatDate(revisionChangeRequestAt, language)
    : t("admin.quote_detail.date_not_available");
  const publicChangeRequestMessage = publicResponseLastMessage || revisionChangeRequestMessage || t("admin.quote_detail.public_change_request_fallback");
  const canEditQuote = ["created", "change_requested"].includes(quoteStatus) && !hasChangeRequestRevision;
  const canSendQuote = quoteStatus === "created";
  const canResendQuote = ["sent", "approved", "rejected", "expired", "change_requested"].includes(quoteStatus) && !hasChangeRequestRevision;
  const quoteHasKitLine = detail.lines.some((line) => Boolean(line.kit_id));
  const showMissingKitWarning = !quoteHasKitLine;
  const canCancelQuote = !["cancelled", "approved"].includes(quoteStatus);
  const canReopenCancelledQuote = quoteStatus === "cancelled";
  const canRestorePublicResponse = ["approved", "rejected", "change_requested"].includes(quoteStatus);
  const canResendPublicConfirmation = ["approved", "rejected", "change_requested"].includes(quoteStatus);
  const restoreTargetStatusRaw = readStringMeta(detail.quote.meta || {}, "public_response_previous_status", "").trim().toLowerCase();
  const restoreTargetStatus =
    restoreTargetStatusRaw === "sent" || restoreTargetStatusRaw === "change_requested"
      ? restoreTargetStatusRaw
      : "sent";
  const restoreTargetStatusLabel = labelForQuoteStatus(restoreTargetStatus, language);
  const primaryRecipientLabel = detail.quote.context_type === "acquisition"
    ? t("admin.quote_detail.primary_recipient_prospect")
    : t("admin.quote_detail.primary_recipient_client");
  const ownerEmail = visibleEmail(owner?.email);
  const lastRecipientEmail = readStringMeta(detail.quote.meta || {}, "recipient_email", "").trim().toLowerCase();
  const lastRecipientPhone = readStringMeta(detail.quote.meta || {}, "recipient_phone", "").trim();
  const defaultThirdPartyEmail = lastRecipientEmail && lastRecipientEmail !== ownerEmail ? lastRecipientEmail : "";
  const parentRecipientEmail = visibleEmail(resolvedParentReferentEmail);
  const primaryRecipientEmail = isChildSource ? (parentRecipientEmail || ownerEmail) : ownerEmail;
  const defaultPublicConfirmationRecipient = [
    isChildSource ? parentRecipientEmail : "",
    ownerEmail,
    lastRecipientEmail,
  ]
    .map((value) => String(value || "").trim().toLowerCase())
    .find((value) => value && value !== "-") || "";
  const publicConfirmationStatusLabel = quoteStatus === "approved"
    ? t("admin.quote_events.kind.approved_confirmation")
    : quoteStatus === "rejected"
      ? t("admin.quote_events.kind.rejected_confirmation")
      : t("admin.quote_events.kind.change_requested_confirmation");
  const defaultPrimaryPhone = [lastRecipientPhone, resolvedParentReferentPhone, ownerPhone]
    .map((value) => String(value || "").trim())
    .find((value) => value && value !== "-") || "";
  const manualEmailRecipients = Array.from(
    new Set(
      [
        primaryRecipientEmail,
        parentRecipientEmail,
        ownerEmail,
        lastRecipientEmail,
      ]
        .map((value) => String(value || "").trim().toLowerCase())
        .filter((value) => value && value !== "-"),
    ),
  );
  const defaultManualEmail = manualEmailRecipients[0] || "";
  const defaultManualEmailSubject = t("admin.quote_detail.manual_email_default_subject", { quote: detail.quote.quote_number });
  const defaultSendTemplateRef =
    messagingSettings?.quote_send_template_ref ||
    (quoteSendTemplates[0] ? messagingTemplateRef(quoteSendTemplates[0]) : "");
  const defaultSendTemplateRefForQuote = resolveAudienceAwareTemplateRef(quoteSendTemplates, {
    audience: isChildSource ? "child" : "adult",
    fallbackRef: defaultSendTemplateRef,
  });
  const defaultSendSmsTemplateRef =
    messagingSettings?.quote_send_sms_template_ref ||
    (quoteSendSmsTemplates[0] ? messagingTemplateRef(quoteSendSmsTemplates[0]) : "");
  const defaultCancelTemplateRef =
    messagingSettings?.quote_cancel_template_ref ||
    (quoteCancelTemplates[0] ? messagingTemplateRef(quoteCancelTemplates[0]) : "");
  const defaultCancelSmsTemplateRef =
    messagingSettings?.quote_cancel_sms_template_ref ||
    (quoteCancelSmsTemplates[0] ? messagingTemplateRef(quoteCancelSmsTemplates[0]) : "");
  const validationClientStatusLabel = validationClientLabelFromQuote(detail.quote, language);
  const validationClientStatusDetail = validationClientDateLabelFromQuote(detail.quote, language);
  const quoteLanguage = readStringMeta(detail.quote.meta || {}, "language", "fr").toLowerCase();
  const quoteTemplateId = detail.quote.quote_template_id || readStringMeta(detail.quote.meta || {}, "quote_template_uuid");
  const interactionEvents = Array.isArray(detail.events)
    ? detail.events.filter((event) => QUOTE_INTERACTION_EVENT_TYPES.has(String(event.event_type || "").trim().toLowerCase()))
    : [];
  const interactionHistorySection =
    interactionEvents.length > 0 ? (
      <section className="card quote-interactions-card">
        <div className="row spread wrap gap-sm">
          <div>
            <h3>{t("admin.quote_detail.interaction_history_title")}</h3>
            <p className="muted">{t("admin.quote_detail.interaction_history_subtitle")}</p>
          </div>
        </div>
        <ol className="quote-interactions-timeline top-gap-sm">
          {interactionEvents.map((event) => {
            const messageBody = quoteEventMessageBody(event);
            const messageBodyFormat = quoteEventMessageBodyFormat(event);
            return (
              <li key={event.id} className={`quote-interaction-item is-${quoteEventTone(event)}`}>
                <div className="quote-interaction-dot" aria-hidden="true" />
                <div className="quote-interaction-body">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <strong>{quoteEventTitle(event, language)}</strong>
                      <div className="muted">
                        {formatDate(event.created_at)}
                        {event.actor_label ? ` · ${event.actor_label}` : ""}
                      </div>
                    </div>
                  </div>
                  <p className="top-gap-xs">{quoteEventDescription(event, language)}</p>
                  {messageBody ? (
                    <details className="quote-interaction-message top-gap-xs">
                      <summary>{t("admin.quote_detail.interaction_message_toggle")}</summary>
                      {messageBodyFormat === "HTML" ? (
                        <div
                          className="quote-interaction-message-html"
                          dangerouslySetInnerHTML={{ __html: messageBody }}
                        />
                      ) : (
                        <pre>{messageBody}</pre>
                      )}
                    </details>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    ) : null;
  const quoteTermsTemplateId = detail.quote.terms_template_id || readStringMeta(detail.quote.meta || {}, "terms_template_id");
  const calendarSessions = getCalendarSessions(planningSnapshotForEditor);
  const planningBlocks = getPlanningBlocks(planningSnapshotForEditor);
  const planningByActivityId: Record<string, { plannedQuantity: number; pendingSelection: boolean }> = {};
  for (const session of calendarSessions) {
    const planningKey = planningKeyFromSnapshotItem(session);
    if (!planningKey) {
      continue;
    }
    if (!(planningKey in planningByActivityId)) {
      planningByActivityId[planningKey] = { plannedQuantity: 0, pendingSelection: false };
    }
    planningByActivityId[planningKey].plannedQuantity += 1;
  }
  for (const block of planningBlocks) {
    const planningKey = planningKeyFromSnapshotItem(block);
    if (!planningKey) {
      continue;
    }
    if (!(planningKey in planningByActivityId)) {
      planningByActivityId[planningKey] = { plannedQuantity: 0, pendingSelection: false };
    }
    const rawPending = block.selection_pending;
    const isPending = rawPending === true || String(rawPending ?? "").trim().toLowerCase() === "true";
    if (isPending) {
      planningByActivityId[planningKey].pendingSelection = true;
    }
  }
  const activityById = new Map(activities.map((activity) => [activity.id, activity]));
  const sendQuantityMismatchWarnings = detail.lines
    .filter((line) => Boolean(line.activity_id))
    .filter((line) => {
      const activity = activityById.get(String(line.activity_id || "").trim());
      const haystack = [activity?.name, activity?.code, activity?.service_code, line.title]
        .filter(Boolean)
        .join(" ");
      return !isSolfegeActivityName(haystack);
    })
    .map((line) => {
      const planningKey = planningKeyFromQuoteLine(line);
      const planningSummaryForActivity = planningKey ? planningByActivityId[planningKey] : undefined;
      const plannedQuantity = planningSummaryForActivity?.plannedQuantity ?? 0;
      const billedQuantity = toNumber(line.quantity, 0);
      return {
        title: String(line.title || t("admin.quote_lines.untitled_activity")).trim() || t("admin.quote_lines.untitled_activity"),
        billedQuantity,
        plannedQuantity,
        mismatch: Math.round(billedQuantity) !== plannedQuantity,
      };
    })
    .filter((entry) => entry.mismatch);
  const primarySendDescriptionLines = [
    t("admin.quote_detail.send_primary_description"),
  ];
  if (sendQuantityMismatchWarnings.length > 0) {
    primarySendDescriptionLines.push(
      "",
      t("admin.quote_detail.send_quantity_warning_intro"),
      ...sendQuantityMismatchWarnings.map(
        (entry) =>
          t("admin.quote_detail.send_quantity_warning_line", {
            title: entry.title,
            billed: entry.billedQuantity,
            planned: entry.plannedQuantity,
          }),
      ),
      "",
      t("admin.quote_detail.send_quantity_warning_solfege"),
      t("admin.quote_detail.send_quantity_warning_confirm"),
    );
  }
  const primarySendDescription = primarySendDescriptionLines.join("\n");
  const primarySendTitle =
    sendQuantityMismatchWarnings.length > 0
      ? canSendQuote
        ? t("admin.quote_detail.send_confirm_with_mismatch")
        : t("admin.quote_detail.resend_confirm_with_mismatch")
      : canSendQuote
        ? t("admin.quote_detail.send_confirm")
        : t("admin.quote_detail.resend_confirm");
  const planningSummary = planningVisualSummary(calendarSessions, language);
  const followupPayload = readObject(activeFollowup?.payload);
  const followupTransformationPayload = readObject(followupPayload?.quote_to_enrollment);
  const followupTransformationExecution = readObject(followupPayload?.quote_to_enrollment_execution);
  const followupTransformationExecutionStatus = String(followupTransformationExecution?.status ?? "").trim().toLowerCase();
  const followupTransformationFailedMessage = String(followupTransformationExecution?.error_message ?? "").trim();
  const canRollbackTransformation = followupTransformationExecutionStatus === "executed";
  const transformationExecutionSummary = {
    bookings: Array.isArray(followupTransformationExecution?.created_booking_ids)
      ? followupTransformationExecution.created_booking_ids.length
      : 0,
    transactions: Array.isArray(followupTransformationExecution?.created_transaction_ids)
      ? followupTransformationExecution.created_transaction_ids.length
      : 0,
    subscriptions: Array.isArray(followupTransformationExecution?.created_subscription_ids)
      ? followupTransformationExecution.created_subscription_ids.length
      : 0,
    users: Array.isArray(followupTransformationExecution?.created_user_ids)
      ? followupTransformationExecution.created_user_ids.length
      : 0,
  };
  const followupSelectedSlot = readObject(followupPayload?.selected_solfege_slot)
    ?? readObject(detail.quote.selected_solfege_slot);
  const followupPaymentPlanId = String(followupPayload?.payment_plan_id ?? detail.quote.payment_plan_id ?? "").trim();
  const followupPaymentMethodCode = String(followupPayload?.payment_method_code ?? "").trim().toUpperCase();
  const followupLevelCode = String(
    followupSelectedSlot?.level_code
    ?? detail.quote.estimated_solfege_level
    ?? "",
  ).trim();
  const paymentMethodOptionsByCode = new Map<string, { code: string; label: string; sourcePlans: string[] }>();
  for (const row of paymentPlans) {
    const code = String(row.payment_method || "").trim().toUpperCase();
    if (!code) {
      continue;
    }
    const existing = paymentMethodOptionsByCode.get(code);
    if (existing) {
      existing.sourcePlans.push(row.name);
      continue;
    }
    paymentMethodOptionsByCode.set(code, {
      code,
      label: paymentMethodLabel(code, language),
      sourcePlans: [row.name],
    });
  }
  const followupMethodDefaultCode = followupPaymentMethodCode
    || (followupPaymentPlanId
      ? String(
        paymentPlans.find((row) => row.id === followupPaymentPlanId)?.payment_method ?? "",
      ).trim().toUpperCase()
      : "");
  const quoteAdjustment = parseQuoteFinancialAdjustment(detail.quote.meta || {});
  const quoteDeposit = parseQuotePreRegistrationDeposit(detail.quote.meta || {});
  const passRecupModeRaw = String((detail.quote.meta || {}).pass_recup_mode || "").trim().toLowerCase();
  const passRecupMode = passRecupModeRaw === "enabled" || passRecupModeRaw === "disabled" ? passRecupModeRaw : "auto";
  const intakeSummary = detail.intake_summary || null;
  const typeformMeta = readObject((detail.quote.meta || {}).typeform_intake) || {};
  const typeformIntakeId = String(typeformMeta.intake_id || (detail.quote.meta || {}).typeform_intake_id || "").trim();
  const typeformSource = String(typeformMeta.source_code || typeformMeta.source_form_id || "").trim();
  const typeformResponse = String(typeformMeta.source_response_id || "").trim();
  const typeformSegment = String(typeformMeta.audience_segment || "").trim();
  const typeformLocation = String(typeformMeta.location_code || typeformMeta.form_location_code || "").trim();
  const typeformSchoolYear = String(typeformMeta.school_year_label || detail.quote.school_year_label || "").trim();
  const formatNullableBoolean = (value: boolean | null | undefined) => {
    if (value === true) return t("common.yes");
    if (value === false) return t("common.no");
    return t("admin.quote_detail.intake_summary_unknown");
  };
  const defaultVatRate = resolveDefaultVatRate(detail);
  const signedAdjustment = adjustmentSignedAmount(quoteAdjustment);
  const totalTtcNumber = Number(detail.quote.total_ttc);
  const totalBeforeAdjustment = Number.isFinite(totalTtcNumber) ? totalTtcNumber - signedAdjustment : null;
  const languageQuoteTemplates = quoteTemplates.filter((row) => normalizeLang(row.language) === normalizeLang(quoteLanguage));
  const selectedTemplate = quoteTemplates.find((row) => row.id === quoteTemplateId);
  const hidePassRecupForTemplate = (() => {
    if (!selectedTemplate) {
      return false;
    }
    const target = String(selectedTemplate.target || "").trim().toLowerCase();
    if (target === "eveil" || target === "initiation") {
      return true;
    }
    const haystack = `${selectedTemplate.name || ""} ${selectedTemplate.code || ""}`.trim().toLowerCase();
    return haystack.includes("eveil") || haystack.includes("initiation");
  })();
  const templateOptions = (() => {
    if (!selectedTemplate) {
      return languageQuoteTemplates;
    }
    if (languageQuoteTemplates.some((row) => row.id === selectedTemplate.id)) {
      return languageQuoteTemplates;
    }
    return [selectedTemplate, ...languageQuoteTemplates];
  })();
  const languageTermsTemplates = termsTemplates.filter((row) => normalizeLang(row.language) === normalizeLang(quoteLanguage));
  const selectedTermsTemplate = termsTemplates.find((row) => row.id === quoteTermsTemplateId);
  const termsOptions = (() => {
    if (!selectedTermsTemplate) {
      return languageTermsTemplates;
    }
    if (languageTermsTemplates.some((row) => row.id === selectedTermsTemplate.id)) {
      return languageTermsTemplates;
    }
    return [selectedTermsTemplate, ...languageTermsTemplates];
  })();
  const pdfVersionTag = String(detail.quote.document_hash || detail.quote.document_generated_at || "").trim();
  const adminPdfHref = withUiLanguage(
    `/admin/quotes/${detail.quote.id}/pdf${pdfVersionTag ? `?v=${encodeURIComponent(pdfVersionTag)}` : ""}`,
    language,
  );
  const publicPdfHref = detail.quote.public_pdf_url
    ? `${detail.quote.public_pdf_url}${pdfVersionTag ? `&v=${encodeURIComponent(pdfVersionTag)}` : ""}`
    : detail.quote.pdf_token
    ? `/q/${detail.quote.id}/pdf?t=${encodeURIComponent(detail.quote.pdf_token)}${pdfVersionTag ? `&v=${encodeURIComponent(pdfVersionTag)}` : ""}`
    : null;
  const regenerateFormId = `quote-regenerate-form-${detail.quote.id}`;
  const restorePublicResponseFormId = `quote-restore-public-response-form-${detail.quote.id}`;
  const resendPublicConfirmationFormId = `quote-resend-public-confirmation-form-${detail.quote.id}`;
  const sendPrimaryFormId = `quote-send-primary-form-${detail.quote.id}`;
  const sendThirdPartyFormId = `quote-send-third-party-form-${detail.quote.id}`;
  const sendEmailPreviewPath = withUiLanguage(`/admin/quotes/${encodeURIComponent(detail.quote.id)}/email-preview`, language);

  const quoteBasePath = `/admin/quotes/${encodeURIComponent(detail.quote.id)}`;
  const sectionHref = (section: QuoteWorkspaceSection): string =>
    withUiLanguage(`${quoteBasePath}?back=${encodeURIComponent(backPath)}&section=${section}`, language);
  const selfPath = appendQuickScenario(sectionHref(activeSection), quickScenario);
  const intakePanelOpen = readParam(searchParams, "intake") === "1";
  const intakePanelHref = appendQueryParam(selfPath, "intake", "1");
  const intakeDetailHref = typeformIntakeId ? withUiLanguage(`/admin/intakes/${encodeURIComponent(typeformIntakeId)}`, language) : "";
  const transformBasePath = `${quoteBasePath}/transform?back=${encodeURIComponent(selfPath)}${quickScenario === "live" ? "" : `&scenario=${quickScenario}`}`;
  const followupTransformationFailureUi =
    followupTransformationExecutionStatus === "failed" && followupTransformationFailedMessage
      ? buildQuoteTransformationFailureUi(followupTransformationFailedMessage, transformBasePath, language)
      : null;
  const quickScenarioLinks = [
    {
      key: "live" as const,
      label: t("admin.quote_detail.quick_transform.scenario_live"),
      href: sectionHref("integration"),
      active: quickScenario === "live",
    },
    {
      key: "A" as const,
      label: t("admin.quote_detail.quick_transform.scenario_auto_validable"),
      href: appendQuickScenario(sectionHref("integration"), "A"),
      active: quickScenario === "A",
    },
    {
      key: "B" as const,
      label: t("admin.quote_detail.quick_transform.scenario_review_required"),
      href: appendQuickScenario(sectionHref("integration"), "B"),
      active: quickScenario === "B",
    },
    {
      key: "C" as const,
      label: t("admin.quote_detail.quick_transform.scenario_blocked"),
      href: appendQuickScenario(sectionHref("integration"), "C"),
      active: quickScenario === "C",
    },
  ];
  const commercialState = commercialStateFromQuote(detail.quote);
  const integrationState = integrationStateFromQuote(detail.quote, commercialState, activeFollowup);
  const validationChannel = readStringMeta(
    detail.quote.meta || {},
    "validation_channel",
    detail.quote.approved_at ? t("admin.quote_detail.validation_channel_public_portal") : "-",
  );
  const integrationTargetMode = readStringMeta(
    detail.quote.meta || {},
    "integration_target_mode",
    t("admin.quote_detail.integration_target_mode_review"),
  );
  const clientMatchRaw = readStringMeta(detail.quote.meta || {}, "client_match_status", detail.quote.client_id ? "deja_lie" : "aucun").toLowerCase();
  const clientMatchStatus = clientMatchRaw === "probable" || clientMatchRaw === "multiple" || clientMatchRaw === "deja_lie" ? clientMatchRaw : "aucun";
  const integrationAlerts: string[] = [];
  if (detail.quote.status === "approved" && integrationState === "a_preparer") {
    integrationAlerts.push(t("admin.quote_detail.integration_alert_prepare"));
  }
  if (integrationState === "a_verifier") {
    integrationAlerts.push(t("admin.quote_detail.integration_alert_match_review"));
  }
  if (integrationState === "erreur_integration") {
    integrationAlerts.push(
      followupTransformationFailureUi?.summary
        || t("admin.quote_detail.integration_alert_error"),
    );
  }
  if (detail.quote.document_status === "stale") {
    integrationAlerts.push(t("admin.quote_detail.integration_alert_document_stale"));
  }
  const validationRows = [
    { label: t("admin.quote_detail.validation_date"), value: formatDate(detail.quote.approved_at, language) },
    { label: t("admin.quote_detail.validation_channel"), value: validationChannel },
    { label: t("admin.quote_detail.approved_version_hash"), value: detail.quote.document_hash || "-" },
    {
      label: t("admin.quote_detail.integration_version_hash"),
      value: readStringMeta(detail.quote.meta || {}, "integration_document_hash", detail.quote.document_hash || "-"),
    },
    { label: t("admin.quote_detail.last_admin_change"), value: formatDate(detail.quote.created_at, language) },
  ];
  const projectionRows = [
    { label: t("admin.quote_detail.target_mode"), value: integrationTargetMode },
    { label: t("admin.quote_detail.billing_contact"), value: ownerName },
    { label: t("admin.quote_detail.students"), value: readStringMeta(detail.quote.meta || {}, "integration_students_label", ownerName) },
    { label: t("admin.quote_detail.accepted_activities"), value: String(getPlanningBlocks(planningSnapshotForEditor).length || 0) },
    { label: t("admin.quote_detail.slots_to_create"), value: String(calendarSessions.length) },
    { label: t("admin.quotes.school_year"), value: detail.quote.school_year_label || "-" },
    {
      label: t("admin.quote_detail.payment_plan"),
      value: paymentPlans.find((plan) => plan.id === detail.quote.payment_plan_id)?.name || t("admin.quote_detail.none"),
    },
    {
      label: t("admin.quote_detail.options_to_reuse"),
      value: readStringMeta(detail.quote.meta || {}, "integration_options_label", t("admin.quote_detail.according_to_approved_quote")),
    },
  ];
  const integrationResultRows = [
    { label: t("admin.quote_detail.integration_status"), value: integrationStateLabel(integrationState, language) },
    { label: t("admin.quote_detail.central_client"), value: readStringMeta(detail.quote.meta || {}, "integration_client_result", "-") },
    { label: t("admin.quote_detail.slots"), value: readStringMeta(detail.quote.meta || {}, "integration_slots_result", "-") },
    { label: t("admin.quote_detail.integration_date"), value: readStringMeta(detail.quote.meta || {}, "integration_completed_at", "-") },
    { label: t("admin.quote_detail.user"), value: readStringMeta(detail.quote.meta || {}, "integration_by", "-") },
    {
      label: t("admin.quote_detail.central_profile_link"),
      value: readStringMeta(detail.quote.meta || {}, "integration_client_link", t("admin.quote_detail.coming_soon")),
    },
  ];

  const quickProspectTypeRaw = String((selectedProspect?.meta || {}).prospect_type || "").trim().toLowerCase();
  const quickProspect: QuoteTransformProspect | null = selectedProspect
    ? {
      id: selectedProspect.id,
      firstName: selectedProspect.first_name,
      lastName: selectedProspect.last_name,
      email: selectedProspect.email,
      phone: selectedProspect.phone || null,
      parentProspectId: selectedProspect.parent_prospect_id || null,
      prospectType: quickProspectTypeRaw === "child" ? "child" : "adult",
      meta: selectedProspect.meta || {},
    }
    : selectedClient
      ? {
        id: `client:${selectedClient.id}`,
        firstName: selectedClient.first_name,
        lastName: selectedClient.last_name,
        email: selectedClient.email,
        phone: selectedClient.mobile_phone_1 || selectedClient.phone || selectedClient.home_phone || null,
        parentProspectId: null,
        prospectType: String(selectedClient.client_kind || "").trim().toUpperCase() === "CHILD" ? "child" : "adult",
        meta: {
          source: "linked_client_fallback",
          linked_client_id: selectedClient.id,
        },
      }
      : null;

  const quickQuote: QuoteTransformQuote = {
    id: detail.quote.id,
    quoteNumber: detail.quote.quote_number,
    status: detail.quote.status,
    clientId: detail.quote.client_id,
    currency: detail.quote.currency || "EUR",
    totalTtc: toNumber(detail.quote.total_ttc),
    totalHt: Number(detail.lines.reduce((sum, line) => sum + toNumber(line.amount_ht), 0).toFixed(2)),
    schoolYearLabel: detail.quote.school_year_label,
    legalEntityId: detail.quote.legal_entity_id,
    legalEntityName: legalEntities.find((entity) => entity.id === detail.quote.legal_entity_id)?.name || t("admin.quote_transform.to_define"),
    paymentPlanName: paymentPlans.find((plan) => plan.id === detail.quote.payment_plan_id)?.name || "-",
    quoteType: detail.quote.quote_type,
    quoteTypeFormulaName: selectedQuoteType?.formula_name || null,
    locationId: detail.quote.location_id,
    locationName: locationNameById(locations, detail.quote.location_id, language),
    financialAdjustment: {
      type: quoteAdjustment.type,
      amountTtc: quoteAdjustment.amountTtc,
      label: quoteAdjustment.label || null,
      vatRate: toNumber(defaultVatRate, 20),
      effectiveDate: quoteAdjustment.effectiveDate || null,
    },
  };

  const quickLines: QuoteTransformLine[] = detail.lines.map((line) => ({
    id: line.id,
    lineType: line.line_type,
    lineCategory: line.line_category,
    masterItemType: line.master_item_type,
    activityId: line.activity_id,
    title: line.title,
    quantity: toNumber(line.quantity, 1),
    durationMinutes: null,
    pricingUnit: line.line_category === "service" ? "session" : "item",
    amountHt: toNumber(line.amount_ht),
    amountTtc: toNumber(line.amount_ttc),
    vatRate: toNumber(line.vat_rate),
    meta: readObject(line.meta) || {},
  }));

  const quickClients: QuoteTransformClient[] = clients.map((client) => ({
    id: client.id,
    firstName: client.first_name,
    lastName: client.last_name,
    email: client.email,
    phone: client.phone,
    mobilePhone1: client.mobile_phone_1,
    mobilePhone2: client.mobile_phone_2,
    homePhone: client.home_phone,
    familyName: client.family_name,
    clientKind: client.client_kind,
    clientStatus: client.client_status,
  }));

  const quickActivities: QuoteTransformActivityCatalog[] = activities.map((activity) => ({
    id: activity.id,
    name: activity.name,
    serviceCode: activity.service_code,
    durationMinutes: activity.duration_minutes,
    defaultCourseRateTtc: activity.default_course_rate_ttc ? toNumber(activity.default_course_rate_ttc) : null,
    mode: activity.mode,
    active: activity.active,
  }));

  const quickPlans: QuoteTransformPlan[] = plans.map((plan) => ({
    id: plan.id,
    name: plan.name,
    kind: plan.kind,
    active: plan.active,
  }));

  const quickSessionsByActivityId: Record<string, QuoteTransformSession[]> = {};
  for (const item of sessionsPerActivity) {
    quickSessionsByActivityId[item.activityId] = item.sessions.map((session) => {
      const seatsRemaining = Math.max(0, Number(session.capacity_max || 0) - Number(session.booked_count || 0));
      return {
        id: session.id,
        courseTypeId: session.course_type_id,
        locationId: session.location_id,
        locationName: session.location_label,
        title: session.title,
        startAtUtc: session.start_at_utc,
        endAtUtc: session.end_at_utc,
        timezone: session.timezone,
        teacherDisplayName: session.effective_teacher_display_name,
        status: session.status,
        statusLabel: session.status_label,
        capacityMax: session.capacity_max,
        bookedCount: session.booked_count,
        seatsRemaining,
      };
    });
  }

  const quickTransformAnalysis: QuoteQuickTransformAnalysis = analyzeQuoteQuickTransformStatus({
    quote: quickQuote,
    prospect: quickProspect,
    lines: quickLines,
    clients: quickClients,
    activities: quickActivities,
    sessionsByActivityId: quickSessionsByActivityId,
    plans: quickPlans,
    calendarSnapshot: planningSnapshotForEditor,
    followupId: activeFollowup?.id || null,
    followupStatus: activeFollowup?.status || null,
    scenario: quickScenario,
  });

  const sidebarItems: SidebarItem[] = [
    { id: "overview", label: t("admin.quote_detail.sidebar_overview"), href: sectionHref("overview"), active: activeSection === "overview" },
    { id: "cadre", label: t("admin.quote_detail.sidebar_cadre"), href: sectionHref("cadre"), active: activeSection === "cadre" },
    {
      id: "planning",
      label: t("admin.quote_detail.sidebar_planning"),
      href: sectionHref("planning"),
      badge: `${calendarSessions.length}`,
      active: activeSection === "planning",
    },
    {
      id: "pricing",
      label: t("admin.quote_detail.sidebar_pricing"),
      href: sectionHref("pricing"),
      badge: `${detail.lines.length}`,
      active: activeSection === "pricing",
    },
    {
      id: "interactions",
      label: t("admin.quote_detail.sidebar_interactions"),
      href: sectionHref("interactions"),
      badge: hasPublicChangeRequest ? "!" : interactionEvents.length > 0 ? `${interactionEvents.length}` : undefined,
      badgeTone: hasPublicChangeRequest ? "alert" : "default",
      active: activeSection === "interactions",
    },
    { id: "document", label: t("admin.quote_detail.sidebar_document"), href: sectionHref("document"), active: activeSection === "document" },
    {
      id: "integration",
      label: t("admin.quote_detail.sidebar_integration"),
      href: sectionHref("integration"),
      active: activeSection === "integration",
    },
  ];

  return (
    <section className="admin-page-grid">
      <QuoteWorkspaceShell
        header={(
          <QuoteWorkspaceHeader
            title={t("admin.quote_detail.quote_title", { number: detail.quote.quote_number })}
            subtitle={t("admin.quote_detail.header_subtitle", {
              context: labelForContext(detail.quote.context_type, language),
              total: formatAmount(detail.quote.total_ttc, detail.quote.currency, language),
              owner: ownerName,
            })}
            backLink={(
              <>
                <Link className="ghost" href={intakePanelHref}>{t("admin.quote_detail.intake_info_button")}</Link>
                <Link className="ghost" href={backPath}>{t("admin.quote_detail.back_to_quotes")}</Link>
                <Link className="ghost" href="/admin/quotes/new">{t("admin.quotes.new_quote")}</Link>
              </>
            )}
            statuses={[
              { label: t("admin.quote_detail.status_commercial"), value: commercialStateLabel(commercialState, language) },
              { label: t("admin.quote_detail.status_document"), value: detail.quote.document_status || "stale" },
              {
                label: t("admin.quotes.client_validation"),
                value: validationClientStatusLabel,
                className: commercialState === "modification_demandee" ? "quote-header-status-info" : "",
              },
              { label: t("admin.quote_detail.status_integration"), value: integrationStateLabel(integrationState, language) },
            ]}
          />
        )}
        sidebar={<QuoteWorkspaceSidebar items={sidebarItems} language={language} />}
        rightRail={(
          <QuoteRightSummaryRail
            top={[
              { label: t("admin.quotes.total_ttc"), value: formatAmount(detail.quote.total_ttc, detail.quote.currency, language) },
              { label: t("admin.quotes.expiration"), value: formatDate(detail.quote.expires_at, language) },
            ]}
            statuses={[
              { label: t("admin.quotes.client_validation"), value: validationClientStatusDetail },
              { label: t("admin.quotes.central_integration"), value: integrationStateLabel(integrationState, language) },
              { label: t("admin.quote_detail.target_mode"), value: integrationTargetMode },
              { label: t("admin.quote_detail.planned_slots"), value: String(calendarSessions.length) },
            ]}
            alerts={integrationAlerts}
            language={language}
          />
        )}
      >
        {intakePanelOpen ? (
          <section className="modal-overlay quote-intake-drawer-overlay" role="dialog" aria-modal="true" aria-label={t("admin.quote_detail.intake_panel_title")}>
            <article className="modal-panel quote-intake-drawer">
              <header className="quote-intake-drawer-header">
                <div>
                  <h3 className="modal-title">{t("admin.quote_detail.intake_panel_title")}</h3>
                  <p className="muted">{t("admin.quote_detail.intake_summary_subtitle")}</p>
                </div>
                <Link className="modal-close-x" href={selfPath} aria-label={t("common.close")}>
                  ×
                </Link>
              </header>
              {intakeSummary ? (
                <div className="quote-intake-drawer-body">
                  <section className="quote-intake-info-grid">
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_student")}</span>
                      <strong>{intakeSummary.student_name || "-"}</strong>
                    </p>
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_parent")}</span>
                      <strong>{intakeSummary.parent_name || "-"}</strong>
                    </p>
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_birth_date")}</span>
                      <strong>{formatDateOnly(intakeSummary.birth_date || null, language)}</strong>
                    </p>
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_reenrollment")}</span>
                      <strong>{formatNullableBoolean(intakeSummary.is_reenrollment)}</strong>
                    </p>
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_pass_recup_requested")}</span>
                      <strong>{formatNullableBoolean(intakeSummary.requested_pass_recup)}</strong>
                    </p>
                    <p>
                      <span className="muted">{t("admin.quote_detail.intake_pass_recup_quote")}</span>
                      <strong>{formatNullableBoolean(intakeSummary.quote_pass_recup)}</strong>
                    </p>
                  </section>
                  <section className="quote-intake-meta-list">
                    <p><span className="muted">{t("admin.quote_detail.intake_source")}</span><strong>{typeformSource || "-"}</strong></p>
                    <p><span className="muted">{t("admin.quote_detail.intake_response")}</span><strong>{typeformResponse || "-"}</strong></p>
                    <p><span className="muted">{t("admin.quote_detail.intake_segment")}</span><strong>{typeformSegment || "-"}</strong></p>
                    <p><span className="muted">{t("admin.quote_detail.intake_location")}</span><strong>{typeformLocation || "-"}</strong></p>
                    <p><span className="muted">{t("admin.quote_detail.intake_school_year")}</span><strong>{typeformSchoolYear || "-"}</strong></p>
                  </section>
                  {intakeSummary.warnings?.includes("requested_pass_recup_missing") ? (
                    <p className="form-error top-gap-sm">{t("admin.quote_detail.intake_summary_pass_recup_warning")}</p>
                  ) : null}
                  {intakeDetailHref ? (
                    <div className="row modal-actions-end">
                      <Link className="ghost" href={intakeDetailHref}>{t("admin.quote_detail.open_full_intake")}</Link>
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="muted">{t("admin.quote_detail.intake_summary_empty")}</p>
              )}
            </article>
          </section>
        ) : null}
        {ok ? <section className="flash-ok">{ok}</section> : null}
        {error ? <section className="flash-err">{error}</section> : null}

        {activeSection === "overview" ? (
          <>
            <QuoteOverviewSection
              cards={[
                { label: t("admin.quote_detail.quote_status"), value: commercialStateLabel(commercialState, language) },
                { label: t("admin.quote_detail.document_status"), value: detail.quote.document_status || "stale" },
                { label: t("admin.quotes.client_validation"), value: validationClientStatusDetail },
                { label: t("admin.quotes.central_integration"), value: integrationStateLabel(integrationState, language) },
                { label: t("admin.quotes.total_ttc"), value: formatAmount(detail.quote.total_ttc, detail.quote.currency, language) },
                { label: t("admin.quotes.expiration"), value: formatDate(detail.quote.expires_at, language) },
              ]}
              alerts={integrationAlerts.map((message) => ({ level: message.toLowerCase().includes("erreur") ? "error" : "warn", message }))}
              quickActions={(
                <>
                  <Link className="ghost" href={sectionHref("document")}>{t("admin.quote_detail.sidebar_document")}</Link>
                  <Link className="ghost" href={sectionHref("interactions")}>{t("admin.quote_detail.sidebar_interactions")}</Link>
                  <Link className="ghost" href={sectionHref("planning")}>{t("admin.quote_detail.sidebar_planning")}</Link>
                  <Link className="ghost" href={sectionHref("pricing")}>{t("admin.quote_detail.sidebar_pricing")}</Link>
                  <Link className="ghost" href={sectionHref("integration")}>{t("admin.quote_detail.sidebar_integration")}</Link>
                </>
              )}
              language={language}
            />

	            <section className="card" id="quote-contact-family">
	              <div className="row spread wrap gap-sm">
	                <div>
	                  <h3>{t("admin.quote_detail.contact_family_title")}</h3>
	                  <p className="muted">{t("admin.quote_detail.contact_family_subtitle")}</p>
	                </div>
	                <div className="row wrap gap-sm">
	                  {selectedProspect ? (
                    <Link
                      className="ghost"
	                      href={withUiLanguage(`/admin/prospects/${encodeURIComponent(selectedProspect.id)}?return_to=${encodeURIComponent(selfPath)}`, language)}
	                    >
	                      {t("admin.quote_detail.edit_prospect")}
	                    </Link>
	                  ) : null}
	                  {selectedClient ? (
	                    <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}?tab=infos&edit_infos=1`}>
	                      {t("admin.quote_detail.edit_client_info")}
	                    </Link>
	                  ) : null}
	                  {selectedClient ? (
	                    <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}?tab=famille`}>
	                      {t("admin.quote_detail.manage_family")}
	                    </Link>
	                  ) : null}
	                </div>
              </div>
	              <div className="grid cols-2 top-gap-sm">
	                <article className="item">
	                  <h4>{t("admin.quote_detail.source_contact_title")}</h4>
	                  <p><strong>{t("admin.quote_detail.context_label")}:</strong> {labelForContext(detail.quote.context_type, language)}</p>
	                  <p><strong>{t("admin.quote_detail.name_label")}:</strong> {ownerName}</p>
	                  <p><strong>{t("common.email")}:</strong> {ownerEmail || "-"}</p>
	                  <p><strong>{t("admin.quote_detail.phone_label")}:</strong> {ownerPhone}</p>
	                  <div className="row wrap gap-sm top-gap-sm">
	                    {selectedProspect ? (
	                      <Link className="ghost" href={`/admin/prospects/${encodeURIComponent(selectedProspect.id)}`}>
	                        {t("admin.quote_detail.open_prospect_record")}
	                      </Link>
	                    ) : null}
	                    {selectedClient ? (
	                      <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}`}>
	                        {t("admin.quote_detail.open_client_record")}
	                      </Link>
	                    ) : null}
	                  </div>
		                </article>
		                <article className="item">
	                  <h4>{t("admin.quote_detail.family_context_title")}</h4>
	                  <p><strong>{t("admin.quote_detail.source_type_label")}:</strong> {sourceTypeLabel} {sourceTypeOrigin !== "inconnu" ? <small className="muted">{t("admin.quote_detail.source_base", { origin: sourceTypeOrigin === "prospect" ? t("admin.quote_detail.source_origin_prospect") : t("admin.quote_detail.source_origin_client") })}</small> : null}</p>
	                  <p><strong>{t("admin.quote_detail.parent_referent")}:</strong> {resolvedParentReferentName}</p>
	                  <p><strong>{t("admin.quote_detail.parent_email")}:</strong> {resolvedParentReferentEmail}</p>
	                  <p><strong>{t("admin.quote_detail.parent_phone")}:</strong> {resolvedParentReferentPhone}</p>
	                  {selectedClient ? (
	                    <p className="top-gap-sm">
	                      <strong>{t("admin.quote_detail.client_family_links")}:</strong> {familyLinks.length}
	                    </p>
	                  ) : (
	                    <p className="muted top-gap-sm">{t("admin.quote_detail.no_linked_client_family")}</p>
	                  )}
	                  {familyLinks.length > 0 ? (
	                    <ul className="top-gap-sm">
	                      {familyLinks.slice(0, 6).map((row) => (
	                        <li key={row.key}>
	                          {row.role}: <strong>{row.personName}</strong> ({row.personEmail}){row.billing ? ` · ${t("admin.quote_detail.invoice_recipient")}` : ""}
	                        </li>
	                      ))}
	                    </ul>
                  ) : null}
                </article>
              </div>
              {selectedProspect && isChildSource ? (
                <article className="item top-gap-sm">
                  <div className="row spread wrap gap-sm">
                    <div>
                      <h4>{t("admin.quote_detail.sibling_quote_title")}</h4>
                      <p className="muted">{t("admin.quote_detail.sibling_quote_help")}</p>
                    </div>
                  </div>
                  <form action={duplicateQuoteForChildAction} className="grid cols-4 top-gap-sm">
                    <input type="hidden" name="quote_id" value={detail.quote.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
                    <label>
                      {t("admin.quote_detail.sibling_first_name")}
                      <input type="text" name="child_first_name" placeholder="Archibald" required />
                    </label>
                    <label>
                      {t("admin.quote_detail.sibling_last_name")}
                      <input type="text" name="child_last_name" defaultValue={selectedProspect.last_name || ""} required />
                    </label>
                    <label>
                      {t("admin.quote_detail.sibling_birth_date")}
                      <input type="date" name="child_birth_date" />
                    </label>
                    <label>
                      {t("admin.quote_detail.sibling_notes")}
                      <input type="text" name="notes" defaultValue={t("admin.quote_detail.sibling_default_note", { quote: detail.quote.quote_number })} />
                    </label>
                    <div className="row wrap gap-sm">
                      <button type="submit">{t("admin.quote_detail.sibling_create_quote")}</button>
                    </div>
                  </form>
                </article>
              ) : null}
            </section>
          </>
        ) : null}

        {activeSection === "interactions" ? (
          <>
            <section className="card quote-mailbox-card">
              <div className="row spread wrap gap-sm">
                <div>
                  <h3>{t("admin.quote_detail.manual_email_title")}</h3>
                  <p className="muted">{t("admin.quote_detail.manual_email_subtitle")}</p>
                </div>
              </div>
              <div className="quote-mailbox-grid top-gap-sm">
                <form action={sendQuoteManualEmailAction} className="quote-mailbox-panel">
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <h4>{t("admin.quote_detail.manual_email_send_title")}</h4>
                  <label>
                    {t("admin.quote_detail.manual_email_recipient")}
                    <input
                      type="email"
                      name="recipient_email"
                      defaultValue={defaultManualEmail}
                      list={`quote-email-recipients-${detail.quote.id}`}
                      required
                    />
                  </label>
                  <label>
                    {t("admin.quote_detail.manual_email_subject")}
                    <input type="text" name="subject" defaultValue={defaultManualEmailSubject} maxLength={255} required />
                  </label>
                  <label>
                    {t("admin.quote_detail.manual_email_body")}
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={8}
                      maxLength={20000}
                      placeholder={t("admin.quote_detail.manual_email_body_placeholder")}
                      language={language}
                    />
                  </label>
                  <button type="submit">{t("admin.quote_detail.manual_email_send_button")}</button>
                </form>

                <form action={logQuoteManualReplyAction} className="quote-mailbox-panel">
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <h4>{t("admin.quote_detail.manual_reply_title")}</h4>
                  <label>
                    {t("admin.quote_detail.manual_reply_sender")}
                    <input
                      type="email"
                      name="sender_email"
                      defaultValue={defaultManualEmail}
                      list={`quote-email-recipients-${detail.quote.id}`}
                      required
                    />
                  </label>
                  <label>
                    {t("admin.quote_detail.manual_email_subject")}
                    <input type="text" name="subject" defaultValue={`Re: ${defaultManualEmailSubject}`} maxLength={255} />
                  </label>
                  <label>
                    {t("admin.quote_detail.manual_reply_body")}
                    <RichMessageEditor
                      name="body"
                      formatName="body_format"
                      rows={8}
                      maxLength={20000}
                      placeholder={t("admin.quote_detail.manual_reply_body_placeholder")}
                      language={language}
                    />
                  </label>
                  <button type="submit" className="ghost">{t("admin.quote_detail.manual_reply_save_button")}</button>
                </form>
              </div>
              <datalist id={`quote-email-recipients-${detail.quote.id}`}>
                {manualEmailRecipients.map((email) => (
                  <option value={email} key={email} />
                ))}
              </datalist>
              <p className="muted top-gap-sm">{t("admin.quote_detail.manual_email_inbound_note")}</p>
            </section>

	            {hasPublicChangeRequest ? (
	              <section className="card quote-public-feedback-card">
	                <div className="row spread wrap gap-sm">
	                  <div>
	                    <h3>{t("admin.quote_detail.public_change_request_title")}</h3>
	                    <p className="muted">{t("admin.quote_detail.public_change_request_subtitle", { date: publicChangeRequestReceivedLabel })}</p>
	                  </div>
	                  <div className="row wrap gap-sm">
	                    <Link className="ghost" href={sectionHref("document")}>{t("admin.quote_detail.handle_in_send")}</Link>
	                    <Link className="ghost" href={sectionHref("pricing")}>{t("admin.quote_detail.check_billed_lines")}</Link>
	                  </div>
	                </div>
                <div className="quote-public-feedback-message top-gap-sm">
                  <strong>{t("admin.quote_detail.client_message")}</strong>
                  <p>{publicChangeRequestMessage}</p>
                </div>
                {hasChangeRequestRevision ? (
                  <p className="muted top-gap-sm">
                    Nouvelle version brouillon creee automatiquement :{" "}
                    <Link className="quote-list-row-link" href={`/admin/quotes/${encodeURIComponent(changeRequestRevisionQuoteId)}`}>
                      {changeRequestRevisionQuoteNumber || "ouvrir la version"}
                    </Link>
                    . Cette version envoyee reste conservee comme archive figee.
                  </p>
                ) : null}
                {hasRevisionChangeRequest ? (
                  <p className="muted top-gap-sm">
                    Demande issue du devis{" "}
                    <Link className="quote-list-row-link" href={`/admin/quotes/${encodeURIComponent(revisionSourceQuoteId)}`}>
                      {revisionSourceQuoteNumber || "source"}
                    </Link>
                    .
                  </p>
                ) : null}
              </section>
            ) : null}

            {interactionHistorySection}

            {!hasPublicChangeRequest && !interactionHistorySection ? (
              <section className="card">
                <h3>{t("admin.quote_detail.sidebar_interactions")}</h3>
                <p className="muted top-gap-sm">{t("admin.quote_detail.no_interactions")}</p>
              </section>
            ) : null}
          </>
        ) : null}

        {activeSection === "document" ? (
          <>

	            <section className="card" id="quote-document">
	              <h3>{t("admin.quote_detail.actions_title")}</h3>
	              <div className="row wrap gap-sm top-gap-sm">
                {canSendQuote || canResendQuote ? (
                  <>
                    <div className="card" style={{ minWidth: 320, flex: "1 1 320px" }}>
                      <h4>
                        {canSendQuote
                          ? t("admin.quote_detail.send_to_recipient", { recipient: primaryRecipientLabel })
                          : t("admin.quote_detail.resend_to_recipient", { recipient: primaryRecipientLabel })}
	                      </h4>
	                      <p className="muted top-gap-sm">
	                        {primaryRecipientEmail
	                          ? t("admin.quote_detail.primary_email_hint", { recipient: primaryRecipientLabel, email: primaryRecipientEmail })
	                          : t("admin.quote_detail.primary_email_missing", { recipient: primaryRecipientLabel })}
	                      </p>
                      <form
                        id={sendPrimaryFormId}
                        action={canSendQuote ? sendQuoteAction : resendQuoteAction}
                        className="top-gap-sm"
                      >
                        <input type="hidden" name="quote_id" value={detail.quote.id} />
                        <input type="hidden" name="return_to" value={selfPath} />
                        <input type="hidden" name="confirm_missing_kit" value="false" />
	                        <input type="hidden" name="recipient_email" value={primaryRecipientEmail} />
	                        <label>
	                          {t("admin.quote_detail.email_template")}
	                          <select name="template_ref" defaultValue={defaultSendTemplateRefForQuote} disabled={!primaryRecipientEmail || quoteSendTemplates.length === 0}>
                            {quoteSendTemplates.map((template) => (
                              <option key={`primary-send-${template.id}`} value={messagingTemplateRef(template)}>
                                {messagingTemplateOptionLabel(template, language)}
                              </option>
                            ))}
                          </select>
                        </label>
                        {defaultPrimaryPhone ? (
                          <div className="quote-action-sms-group">
                            <label className="checkline quote-action-checkline">
                              <input type="checkbox" name="send_sms" />
                              {t("admin.quote_detail.send_sms_too")}
	                            </label>
	                            <label>
	                              {t("admin.quote_detail.sms_number")}
	                              <input type="text" name="recipient_phone" defaultValue={defaultPrimaryPhone} maxLength={30} />
	                            </label>
	                            <label>
	                              {t("admin.quote_detail.sms_template")}
	                              <select
                                name="sms_template_ref"
                                defaultValue={defaultSendSmsTemplateRef}
                                disabled={quoteSendSmsTemplates.length === 0}
                              >
                                {quoteSendSmsTemplates.map((template) => (
                                  <option key={`primary-send-sms-${template.id}`} value={messagingTemplateRef(template)}>
                                    {messagingTemplateOptionLabel(template, language)}
                                  </option>
                                ))}
                              </select>
                            </label>
	                          </div>
	                        ) : (
	                          <small className="muted top-gap-sm">{t("admin.quote_detail.no_mobile_for_sms")}</small>
	                        )}
                        <div className="top-gap-sm">
                          <QuoteEmailPreviewSubmitButton
                            formId={sendPrimaryFormId}
                            previewUrl={sendEmailPreviewPath}
                            label={
                              canSendQuote
                                ? t("admin.quote_detail.send_to_recipient", { recipient: primaryRecipientLabel })
                                : t("admin.quote_detail.resend_to_recipient", { recipient: primaryRecipientLabel })
                            }
                            title={primarySendTitle}
                            description={primarySendDescription}
                            confirmLabel={canSendQuote ? t("admin.quote_detail.send_quote") : t("admin.quote_detail.resend_quote")}
                            language={language}
                            disabled={!primaryRecipientEmail}
                            missingKitWarning={showMissingKitWarning}
                          />
                        </div>
                      </form>
                      <small className="muted top-gap-sm">
                        {t("admin.quote_detail.send_template_hint")}
                      </small>
                    </div>

                    <div className="card" style={{ minWidth: 320, flex: "1 1 320px" }}>
                      <h4>{canSendQuote ? t("admin.quote_detail.send_third_party") : t("admin.quote_detail.resend_third_party")}</h4>
                      <p className="muted top-gap-sm">
                        {t("admin.quote_detail.third_party_help")}
                      </p>
                      <form
                        id={sendThirdPartyFormId}
                        action={canSendQuote ? sendQuoteAction : resendQuoteAction}
                        className="top-gap-sm"
                      >
                        <input type="hidden" name="quote_id" value={detail.quote.id} />
                        <input type="hidden" name="return_to" value={selfPath} />
                        <input type="hidden" name="confirm_missing_kit" value="false" />
                        <label>
                          {t("admin.quote_detail.third_party_recipient")}
                          <input
                            type="email"
                            name="recipient_email"
                            placeholder={t("admin.quote_detail.third_party_email_placeholder")}
                            defaultValue={defaultThirdPartyEmail}
                            required
                          />
                        </label>
	                        <label>
	                          {t("admin.quote_detail.email_template")}
	                          <select name="template_ref" defaultValue={defaultSendTemplateRefForQuote} disabled={quoteSendTemplates.length === 0}>
                            {quoteSendTemplates.map((template) => (
                              <option key={`third-send-${template.id}`} value={messagingTemplateRef(template)}>
                                {messagingTemplateOptionLabel(template, language)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="row wrap gap-sm top-gap-sm">
                          <QuoteEmailPreviewSubmitButton
                            formId={sendThirdPartyFormId}
                            previewUrl={sendEmailPreviewPath}
                            label={canSendQuote ? t("common.send") : t("admin.quote_detail.resend")}
                            title={canSendQuote ? t("admin.quote_detail.third_party_send_preview_title") : t("admin.quote_detail.third_party_resend_preview_title")}
                            description={t("admin.quote_detail.third_party_preview_description")}
                            confirmLabel={canSendQuote ? t("admin.quote_detail.send_quote") : t("admin.quote_detail.resend_quote")}
                            language={language}
                            missingKitWarning={showMissingKitWarning}
                          />
                        </div>
                      </form>
                      {lastRecipientEmail ? (
                        <small className="muted top-gap-sm">{t("admin.quote_detail.last_recipient_email", { email: lastRecipientEmail })}</small>
                      ) : null}
                      {lastRecipientPhone ? (
                        <small className="muted top-gap-sm">{t("admin.quote_detail.last_recipient_phone", { phone: lastRecipientPhone })}</small>
                      ) : null}
                    </div>
                  </>
                ) : canReopenCancelledQuote ? (
                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
                    <h4>{t("admin.quote_detail.reopen_cancelled_quote_title")}</h4>
                    <p className="muted top-gap-sm">
                      {t("admin.quote_detail.reopen_cancelled_quote_help")}
                    </p>
                    <form action={duplicateQuoteAction} className="top-gap-sm">
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
                      <button type="submit" className="ghost">
                        {t("admin.quote_detail.reopen_new_version")}
                      </button>
                    </form>
                  </div>
                ) : (
                  <small className="muted">
                    {t("admin.quote_detail.send_unavailable_status")}
                  </small>
                )}

	                {canCancelQuote ? (
	                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
	                    <h4>{t("admin.quote_detail.cancel_quote")}</h4>
	                    <p className="muted top-gap-sm">
	                      {t("admin.quote_detail.cancel_quote_help")}
	                    </p>
                    <form action={cancelQuoteAction} className="top-gap-sm">
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
	                      <label className="checkline">
	                        <input type="checkbox" name="notify_recipient" defaultChecked={Boolean(primaryRecipientEmail)} />
	                        {t("admin.quote_detail.notify_recipient_email")}
	                      </label>
	                      <label>
	                        {t("admin.quote_detail.recipient")}
	                        <input
                          type="email"
                          name="recipient_email"
                          defaultValue={primaryRecipientEmail || defaultThirdPartyEmail}
	                          placeholder={t("admin.quote_detail.notify_email_placeholder")}
	                        />
	                      </label>
	                      <label>
	                        {t("admin.quote_detail.cancel_template")}
	                        <select name="template_ref" defaultValue={defaultCancelTemplateRef} disabled={quoteCancelTemplates.length === 0}>
                          {quoteCancelTemplates.map((template) => (
                            <option key={`cancel-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(template, language)}
                            </option>
                          ))}
                        </select>
                      </label>
                      {defaultPrimaryPhone ? (
                        <div className="quote-action-sms-group">
	                          <label className="checkline quote-action-checkline">
	                            <input type="checkbox" name="notify_recipient_sms" defaultChecked />
	                            {t("admin.quote_detail.notify_sms_too")}
	                          </label>
	                          <label>
	                            {t("admin.quote_detail.sms_number")}
	                            <input type="text" name="recipient_phone" defaultValue={defaultPrimaryPhone} maxLength={30} />
	                          </label>
	                          <label>
	                            {t("admin.quote_detail.cancel_sms_template")}
	                            <select
                              name="sms_template_ref"
                              defaultValue={defaultCancelSmsTemplateRef}
                              disabled={quoteCancelSmsTemplates.length === 0}
                            >
                              {quoteCancelSmsTemplates.map((template) => (
                                <option key={`cancel-sms-${template.id}`} value={messagingTemplateRef(template)}>
                                  {messagingTemplateOptionLabel(template, language)}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                      ) : null}
	                      <div className="row wrap gap-sm top-gap-sm">
	                        <button type="submit" className="danger">
	                          {t("admin.quote_detail.cancel_quote")}
	                        </button>
	                      </div>
                    </form>
                  </div>
                ) : null}

	                {canRestorePublicResponse ? (
	                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
	                    <h4>{t("admin.quote_detail.restore_previous_state")}</h4>
	                    <p className="muted top-gap-sm">
	                      {t("admin.quote_detail.restore_previous_state_help")}
	                    </p>
	                    <p className="top-gap-sm">
	                      <strong>{t("admin.quote_detail.current_status")}:</strong> {labelForQuoteStatus(quoteStatus, language)}<br />
	                      <strong>{t("admin.quote_detail.restored_status")}:</strong> {restoreTargetStatusLabel}
	                    </p>
                    <form id={restorePublicResponseFormId} action={restoreQuotePublicResponseAction} className="top-gap-sm">
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
	                      <ConfirmSubmitButton
	                        formId={restorePublicResponseFormId}
	                        label={t("admin.quote_detail.restore_previous_state")}
	                        title={t("admin.quote_detail.restore_confirm_title")}
	                        description={t("admin.quote_detail.restore_confirm_description", { from: labelForQuoteStatus(quoteStatus, language), to: restoreTargetStatusLabel })}
	                        confirmLabel={t("admin.quote_detail.restore")}
	                        language={language}
	                        className="ghost"
	                      />
                    </form>
                  </div>
                ) : null}

                {canResendPublicConfirmation ? (
                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
                    <h4>{t("admin.quote_detail.public_confirmation_title")}</h4>
                    <p className="muted top-gap-sm">
                      {t("admin.quote_detail.public_confirmation_help", { status: publicConfirmationStatusLabel })}
                    </p>
                    <form
                      id={resendPublicConfirmationFormId}
                      action={resendQuotePublicConfirmationAction}
                      className="top-gap-sm"
                    >
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
                      <label>
                        {t("admin.quote_detail.public_confirmation_recipient")}
                        <input
                          type="email"
                          name="recipient_email"
                          defaultValue={defaultPublicConfirmationRecipient}
                          placeholder={t("admin.quote_detail.notify_email_placeholder")}
                        />
                      </label>
                      <div className="row wrap gap-sm top-gap-sm">
                        <ConfirmSubmitButton
                          formId={resendPublicConfirmationFormId}
                          label={t("admin.quote_detail.public_confirmation_resend")}
                          title={t("admin.quote_detail.public_confirmation_confirm_title")}
                          description={t("admin.quote_detail.public_confirmation_confirm_description", { status: publicConfirmationStatusLabel })}
                          confirmLabel={t("admin.quote_detail.public_confirmation_resend")}
                          language={language}
                          className="ghost"
                        />
                      </div>
                    </form>
                    {defaultPublicConfirmationRecipient ? (
                      <small className="muted top-gap-sm">
                        {t("admin.quote_detail.public_confirmation_default_recipient_hint", { email: defaultPublicConfirmationRecipient })}
                      </small>
                    ) : (
                      <small className="muted top-gap-sm">
                        {t("admin.quote_detail.public_confirmation_recipient_missing")}
                      </small>
                    )}
                  </div>
                ) : null}

                {!canReopenCancelledQuote ? (
                  <form action={duplicateQuoteAction}>
                    <input type="hidden" name="quote_id" value={detail.quote.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
	                    <button type="submit" className="ghost">{t("admin.quote_detail.duplicate_new_version")}</button>
	                  </form>
                ) : null}

                {detail.quote.public_token ? (
                  <>
                    <a
                      className="ghost"
                      href={detail.quote.public_url ?? `/q/${detail.quote.id}?t=${encodeURIComponent(detail.quote.public_token)}`}
                      target="_blank"
                      rel="noreferrer"
	                    >
	                      {t("admin.quote_detail.open_public_page")}
	                    </a>
	                    <CopyLinkButton
	                      value={detail.quote.public_url ?? `/q/${detail.quote.id}?t=${detail.quote.public_token}`}
	                      label={t("admin.quote_detail.copy_public_link")}
	                    />
                  </>
	                ) : (
	                  <small className="muted">{t("admin.quote_detail.public_link_after_send")}</small>
	                )}

                {detail.quote.pdf_token ? (
                  <a
                    className="ghost"
                    href={publicPdfHref || "#"}
                    target="_blank"
                    rel="noreferrer"
	                  >
	                    {t("admin.quote_detail.public_pdf")}
	                  </a>
	                ) : null}
	                <Link className="ghost" href={adminPdfHref} target="_blank">
	                  {t("admin.quote_detail.admin_pdf")}
	                </Link>
                <form id={regenerateFormId} action={regenerateQuoteDocumentAction}>
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
	                  <ConfirmSubmitButton
	                    formId={regenerateFormId}
	                    label={t("admin.quote_detail.regenerate_document")}
	                    title={t("admin.quote_detail.regenerate_confirm_title")}
	                    description={t("admin.quote_detail.regenerate_confirm_description")}
	                    confirmLabel={t("admin.quote_detail.regenerate")}
	                    language={language}
	                    className="ghost"
	                    disabled={!canEditQuote}
	                  />
	                </form>
	                {!canEditQuote ? (
	                  <small className="muted">{t("admin.quote_detail.regeneration_draft_only")}</small>
	                ) : null}
              </div>
		            </section>
		            <section className="card">
	              <details className="modal-details quote-preview-details">
	                <summary className="quote-preview-summary">
	                  <span>{t("admin.quote_detail.document_preview_admin")}</span>
	                  <small className="muted">{t("admin.quote_detail.preview_audience", { audience: "admin_preview" })}</small>
	                </summary>
	                {documentPreview ? (
	                  <div className="top-gap-sm">
	                    <p className="muted">
	                      {t("admin.quote_detail.render_hash")}: <strong>{documentPreview.document_hash}</strong>
	                    </p>
	                    <div className="grid cols-2 top-gap-sm">
	                      <article className="item">
	                        <strong>{t("admin.quote_detail.visible_blocks")}</strong>
	                        {documentPreview.visible_blocks.length === 0 ? (
	                          <p className="muted top-gap-sm">{t("admin.quote_detail.no_visible_block")}</p>
	                        ) : (
                          <ul className="top-gap-sm">
                            {documentPreview.visible_blocks.map((name) => (
                              <li key={`visible-${name}`}>{name}</li>
                            ))}
                          </ul>
                        )}
	                      </article>
	                      <article className="item">
	                        <strong>{t("admin.quote_detail.hidden_blocks")}</strong>
	                        {documentPreview.hidden_blocks.length === 0 ? (
	                          <p className="muted top-gap-sm">{t("admin.quote_detail.no_hidden_block")}</p>
	                        ) : (
                          <ul className="top-gap-sm">
                            {documentPreview.hidden_blocks.map((name) => (
                              <li key={`hidden-${name}`}>{name}</li>
                            ))}
                          </ul>
                        )}
                      </article>
	                    </div>
	                    <article className="item top-gap-sm">
	                      <h4>{t("admin.quote_detail.quote_preview")}</h4>
	                      <div
                        className="top-gap-sm"
                        dangerouslySetInnerHTML={{ __html: documentPreview.quote_body_html || documentPreview.combined_html }}
                      />
	                    </article>
	                    <details className="modal-details top-gap-sm">
	                      <summary>{t("admin.quote_detail.terms_conditions")}</summary>
	                      <article className="item">
	                        {documentPreview.terms_html ? (
	                          <div dangerouslySetInnerHTML={{ __html: documentPreview.terms_html }} />
	                        ) : (
	                          <p className="muted">{t("admin.quote_detail.no_terms_available")}</p>
	                        )}
                      </article>
                    </details>
	                  </div>
	                ) : (
	                  <p className="muted top-gap-sm">{t("admin.quote_detail.document_preview_unavailable")}</p>
	                )}
              </details>
            </section>
          </>
        ) : null}

	        {activeSection === "cadre" ? (
	          <>
	            <section className="card" id="quote-cadre">
	              <h3>{t("admin.quote_detail.settings_title")}</h3>
	              <p className="muted">{t("admin.quote_detail.settings_subtitle")}</p>
	              {intakeSummary ? (
	                <article className="item top-gap-sm">
	                  <strong>{t("admin.quote_detail.intake_summary_title")}</strong>
	                  <p className="muted top-gap-sm">{t("admin.quote_detail.intake_summary_subtitle")}</p>
	                  <div className="grid cols-3 top-gap-sm">
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_student")}</span>
	                      <br />
	                      <strong>{intakeSummary.student_name || "-"}</strong>
	                    </p>
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_parent")}</span>
	                      <br />
	                      <strong>{intakeSummary.parent_name || "-"}</strong>
	                    </p>
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_birth_date")}</span>
	                      <br />
	                      <strong>{formatDateOnly(intakeSummary.birth_date || null, language)}</strong>
	                    </p>
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_reenrollment")}</span>
	                      <br />
	                      <strong>{formatNullableBoolean(intakeSummary.is_reenrollment)}</strong>
	                    </p>
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_pass_recup_requested")}</span>
	                      <br />
	                      <strong>{formatNullableBoolean(intakeSummary.requested_pass_recup)}</strong>
	                    </p>
	                    <p>
	                      <span className="muted">{t("admin.quote_detail.intake_pass_recup_quote")}</span>
	                      <br />
	                      <strong>{formatNullableBoolean(intakeSummary.quote_pass_recup)}</strong>
	                    </p>
	                  </div>
	                  {intakeSummary.warnings?.includes("requested_pass_recup_missing") ? (
	                    <p className="form-error top-gap-sm">{t("admin.quote_detail.intake_summary_pass_recup_warning")}</p>
	                  ) : null}
	                </article>
	              ) : null}
	              <form action={updateQuoteSettingsAction} className="grid cols-3 config-form-grid top-gap-sm">
          <input type="hidden" name="quote_id" value={detail.quote.id} />
          <input type="hidden" name="return_to" value={selfPath} />
	          <input type="hidden" name="current_meta_json" value={JSON.stringify(detail.quote.meta || {})} />
	          <label>
	            {t("admin.quote_detail.quote_type")}
	            <select name="quote_type_id" defaultValue={detail.quote.quote_type_id || ""} disabled={!canEditQuote}>
	              <option value="">{t("admin.quote_detail.none")}</option>
	              {quoteTypes.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
	            {selectedQuoteType ? (
	              <small className="muted">
	                {t("admin.quote_detail.quote_type_default", { days: selectedQuoteType.default_expiry_days })}
	                {selectedQuoteType.school_year_label ? ` · ${t("admin.quote_detail.school_year_value", { value: selectedQuoteType.school_year_label })}` : ""}
	                {selectedQuoteType.formula_name ? ` · ${t("admin.quote_detail.formula_value", { value: selectedQuoteType.formula_name })}` : ""}
	              </small>
	            ) : null}
	          </label>
	          <label>
	            {t("admin.quote_detail.pricing_catalog")}
	            <select name="pricing_catalog_id" defaultValue={detail.quote.pricing_catalog_id || ""} disabled={!canEditQuote}>
	              <option value="">{t("admin.quote_detail.none")}</option>
              {catalogs.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.payment_plan")}
	            <select name="payment_plan_id" defaultValue={detail.quote.payment_plan_id || ""} disabled={!canEditQuote}>
	              <option value="">{t("admin.quote_detail.none")}</option>
              {paymentPlans.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.linked_formula")}
	            <input type="text" value={selectedQuoteType?.formula_name || "-"} readOnly disabled />
	            <small className="muted">
	              {t("admin.quote_detail.linked_formula_hint")}
	            </small>
	          </label>
	          <label>
	            {t("admin.quote_detail.legal_entity")}
            <select
              name="legal_entity_id"
              defaultValue={detail.quote.legal_entity_id || ""}
              disabled={!canEditQuote}
	            >
	              <option value="">{t("admin.quote_detail.none_feminine")}</option>
              {legalEntities.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
	            </select>
	            <small className="muted">
	              {t("admin.quote_detail.saved_value_hint")}
	            </small>
	          </label>
	          <label>
	            {t("admin.quote_detail.quote_template")}
	            <select name="quote_template_uuid" defaultValue={quoteTemplateId} disabled={!canEditQuote}>
	              <option value="">{t("admin.quote_detail.none")}</option>
              {templateOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.terms_template")}
	            <select name="terms_template_id" defaultValue={quoteTermsTemplateId} disabled={!canEditQuote}>
	              <option value="">{t("admin.quote_detail.keep_current_snapshot")}</option>
              {termsOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
	          </label>
	          <label>
	            {t("common.language")}
	            <select name="language" defaultValue={quoteLanguage} disabled={!canEditQuote}>
	              <option value="fr">{t("common.french")}</option>
	              <option value="en">{t("common.english")}</option>
	            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.currency")}
            <select name="currency" defaultValue={detail.quote.currency || "EUR"} disabled={!canEditQuote}>
              <option value="EUR">EUR</option>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.expiry_delay_days")}
	            <input type="number" name="expiry_days" min={1} max={120} defaultValue={detail.quote.expiry_days} disabled={!canEditQuote} />
	          </label>
	          <label>
	            {t("admin.quote_detail.school_year")}
	            <input type="text" name="school_year_label" defaultValue={detail.quote.school_year_label ?? ""} disabled={!canEditQuote} />
	          </label>
	          <label>
	            {t("admin.quote_detail.financial_adjustment")}
	            <select name="financial_adjustment_type" defaultValue={quoteAdjustment.type} disabled={!canEditQuote}>
	              <option value="none">{t("admin.quote_detail.none")}</option>
	              <option value="credit">{t("admin.quote_detail.adjustment_credit")}</option>
	              <option value="debt">{t("admin.quote_detail.adjustment_debt")}</option>
	            </select>
	          </label>
	          {!hidePassRecupForTemplate ? (
	            <label>
	              {t("admin.quote_detail.pass_recup_option")}
	              <select name="pass_recup_mode" defaultValue={passRecupMode} disabled={!canEditQuote}>
	                <option value="auto">{t("admin.quote_detail.pass_recup_auto")}</option>
	                <option value="enabled">{t("admin.quote_detail.pass_recup_enabled")}</option>
	                <option value="disabled">{t("admin.quote_detail.pass_recup_disabled")}</option>
	              </select>
	            </label>
	          ) : null}
	          <label>
	            {t("admin.quote_detail.pre_registration_deposit")}
            <select
              name="pre_registration_deposit_enabled"
              defaultValue={quoteDeposit.enabled ? "yes" : "no"}
              disabled={!canEditQuote}
	            >
	              <option value="no">{t("common.no")}</option>
	              <option value="yes">{t("common.yes")}</option>
	            </select>
	          </label>
	          <label>
	            {t("admin.quote_detail.adjustment_amount_ttc")}
            <input
              type="number"
              name="financial_adjustment_amount_ttc"
              min={0}
              step="0.01"
              defaultValue={quoteAdjustment.type === "none" ? "" : quoteAdjustment.amountTtc.toFixed(2)}
              placeholder="100.00"
              disabled={!canEditQuote}
            />
	          </label>
	          <label>
	            {t("admin.quote_detail.deposit_amount_ttc")}
            <input
              type="number"
              name="pre_registration_deposit_amount_ttc"
              min={0}
              step="0.01"
              defaultValue={quoteDeposit.amountTtc.toFixed(2)}
              placeholder="200.00"
              disabled={!canEditQuote}
            />
	            <small className="muted">{t("admin.quote_detail.deposit_default")}</small>
	          </label>
	          <label>
	            {t("admin.quote_detail.adjustment_date")}
            <input
              type="date"
              name="financial_adjustment_effective_date"
              defaultValue={quoteAdjustment.effectiveDate}
              disabled={!canEditQuote}
            />
	          </label>
	          <label className="span-3">
	            {t("admin.quote_detail.adjustment_label_optional")}
            <input
              type="text"
              name="financial_adjustment_label"
              defaultValue={quoteAdjustment.label}
	              placeholder={t("admin.quote_detail.adjustment_label_placeholder")}
	              disabled={!canEditQuote}
	            />
	          </label>
	                <div className="row span-3 top-gap-sm">
	                  <button type="submit" disabled={!canEditQuote}>{t("admin.quote_detail.save_settings")}</button>
	                  {!canEditQuote ? <small className="muted">{t("admin.quote_lines.immutable_after_send")}</small> : null}
	                </div>
	              </form>
	              <p className="muted top-gap-sm">
	                {t("admin.quote_detail.current_adjustment")}: <strong>{adjustmentTypeLabel(quoteAdjustment.type, language)}</strong>
	                {quoteAdjustment.type !== "none" ? (
	                  <>
	                    {" · "}
	                    <strong>{formatAmount(String(quoteAdjustment.amountTtc), detail.quote.currency, language)}</strong>
	                    {quoteAdjustment.effectiveDate ? <> · {t("admin.quote_detail.date_label")}: <strong>{quoteAdjustment.effectiveDate}</strong></> : null}
	                    {quoteAdjustment.label ? <> · {t("admin.quote_detail.label_label")}: <strong>{quoteAdjustment.label}</strong></> : null}
	                  </>
	                ) : null}
	              </p>
	              <p className="muted">
	                {t("admin.quote_detail.pre_registration_deposit")}: <strong>{quoteDeposit.enabled ? t("common.yes") : t("common.no")}</strong>
	                {quoteDeposit.enabled ? (
	                  <>
	                    {" · "}
	                    <strong>{formatAmount(String(quoteDeposit.amountTtc), detail.quote.currency, language)}</strong>
	                  </>
	                ) : null}
	              </p>
	              {totalBeforeAdjustment !== null ? (
	                <p className="muted">
	                  {t("admin.quote_detail.lines_total_before_adjustment")}: <strong>{formatAmount(String(totalBeforeAdjustment), detail.quote.currency, language)}</strong>
	                  {" · "}
	                  {t("admin.quote_detail.invoice_total_after_adjustment")}: <strong>{formatAmount(detail.quote.total_ttc, detail.quote.currency, language)}</strong>
	                </p>
	              ) : null}
	              <p className="muted top-gap-sm">
	                {t("admin.quote_detail.active_terms_snapshot")}: <strong>{String(detail.quote.cgv_snapshot?.version_label || "-")}</strong>
	              </p>
	              <p className="muted">
	                {t("admin.quote_detail.templates_language")}: <strong>{quoteLanguage.toUpperCase()}</strong>
	              </p>
	              <p className="muted">
	                {t("admin.quote_detail.document_status")}: <strong>{detail.quote.document_status || "stale"}</strong>
	                {" · "}
	                {t("admin.quote_detail.generated_on")}: <strong>{formatDate(detail.quote.document_generated_at, language)}</strong>
	              </p>
	              <p className="muted">
	                {t("admin.quote_detail.document_hash")}: <strong>{detail.quote.document_hash || "-"}</strong>
	              </p>
            </section>

	            <section className="card">
	              <h3>{t("admin.quote_detail.quote_info_title")}</h3>
	              <div className="grid cols-3 top-gap-sm">
	                <p><strong>{t("admin.quote_detail.type_label")}:</strong> {detail.quote.quote_type}</p>
	                <p><strong>{t("admin.quote_detail.school_year")}:</strong> {detail.quote.school_year_label ?? "-"}</p>
	                <p><strong>{t("admin.quote_detail.created_on")}:</strong> {formatDate(detail.quote.created_at, language)}</p>
	                <p><strong>{t("admin.quote_detail.sent_on")}:</strong> {formatDate(detail.quote.sent_at, language)}</p>
	                <p><strong>{t("admin.quotes.expiration")}:</strong> {formatDate(detail.quote.expires_at, language)}</p>
	                <p><strong>{t("admin.quote_detail.pedagogical_options")}:</strong> {t("admin.quote_detail.pedagogical_options_planning")}</p>
	                {selectedQuoteType?.formula_name ? <p><strong>{t("admin.quote_detail.quote_type_formula")}:</strong> {selectedQuoteType.formula_name}</p> : null}
	              </div>
	            </section>
          </>
        ) : null}

	        {activeSection === "planning" ? (
	          <section className="card quote-workstream-card quote-workstream-card-planning" id="quote-planning">
	        <div className="quote-workstream-head">
	          <span className="quote-workstream-badge quote-workstream-badge-planning">{t("admin.quote_detail.planning_badge")}</span>
	          <h3>{t("admin.quote_detail.course_planning_title")}</h3>
	          <p className="muted">{t("admin.quote_detail.course_planning_subtitle", { activities: planningBlocks.length, sessions: calendarSessions.length })}</p>
	        </div>
        <div className="top-gap-sm">
          <QuotePlanningEditor
            quoteId={detail.quote.id}
            returnTo={selfPath}
            editable={canEditQuote}
            schoolYearLabel={planningEditorSchoolYearLabel}
            activities={activities.map((row) => ({
              id: row.id,
              name: row.name,
              code: row.code,
              service_code: row.service_code,
              mode: row.mode,
              duration_minutes: row.duration_minutes,
              exclude_holidays_in_recurrence: row.exclude_holidays_in_recurrence,
              exclude_school_vacations_in_recurrence: row.exclude_school_vacations_in_recurrence,
            }))}
            locations={locations.map((row) => ({
              id: row.id,
              name: row.name,
            }))}
            calendarPresets={planningCalendarPresets}
            solfegeRules={solfegeRules.map((row) => ({
              id: row.id,
              level_code: row.level_code,
              duration_minutes: row.duration_minutes,
              allowed_weekdays: row.allowed_weekdays,
              allowed_time_slots: row.allowed_time_slots,
              location_id: row.location_id,
              modality: row.modality,
            }))}
            livePlanningSeries={livePlanningSeries}
            initialSnapshot={planningSnapshotForEditor}
            initialMeta={detail.quote.meta || {}}
            language={language}
            saveAction={updateQuotePlanningAction}
          />
        </div>
          </section>
        ) : null}

	        {activeSection === "pricing" ? (
	          <section className="card quote-workstream-card quote-workstream-card-pricing" id="quote-pricing">
	        <div className="quote-workstream-head">
	          <span className="quote-workstream-badge quote-workstream-badge-pricing">{t("admin.quote_detail.pricing_badge")}</span>
	          <h3>{t("admin.quote_detail.billed_lines_title")}</h3>
	          <p className="muted">{t("admin.quote_detail.billed_lines_subtitle", { count: detail.lines.length })}</p>
	        </div>
        <QuoteLinesEditor
          quoteId={detail.quote.id}
          returnTo={selfPath}
          editable={canEditQuote}
          currency={detail.quote.currency}
          initialLines={detail.lines}
          activities={activities.map((row) => ({
            id: row.id,
            name: row.name,
            duration_minutes: row.duration_minutes,
            default_hourly_rate: row.default_hourly_rate,
            default_course_rate_ttc: row.default_course_rate_ttc,
          }))}
          products={products.map((row) => ({
            id: row.id,
            title: row.title,
            price_incl_vat: row.price_incl_vat,
            vat_rate: row.vat_rate,
          }))}
          kits={kits.map((row) => ({
            id: row.id,
            title: row.title,
            effective_price_ttc: row.price_effective_incl_vat,
            vat_rate: row.vat_rate,
          }))}
          discountRules={discountRules.map((row) => ({
            id: row.id,
            code: row.code,
            label: row.label,
            unit_price_ttc: row.unit_price_ttc,
            vat_rate: row.vat_rate,
            currency: row.currency,
          }))}
          activityCatalogPriceByActivityId={activityCatalogPriceByActivityId}
          productCatalogPriceByProductId={productCatalogPriceByProductId}
          kitCatalogPriceByKitId={kitCatalogPriceByKitId}
          planningByActivityId={planningByActivityId}
          defaultVatRate={defaultVatRate}
          language={language}
          saveAction={updateQuoteLinesAction}
        />
          </section>
        ) : null}

        {activeSection === "integration" ? (
          <>
	            {followupTransformationExecutionStatus ? (
	              <section className="card">
	                <h3>{t("admin.quote_detail.transformation_execution_title")}</h3>
	                <p className="muted">
	                  {t("admin.quote_detail.technical_status")}:{" "}
	                  <strong>
	                    {followupTransformationExecutionStatus === "executed"
	                      ? t("admin.quote_detail.execution_status_integrated")
	                      : followupTransformationExecutionStatus === "rolled_back"
	                      ? t("admin.quote_detail.execution_status_rolled_back")
	                      : followupTransformationExecutionStatus === "failed"
	                      ? t("admin.quote_detail.execution_status_failed")
	                      : followupTransformationExecutionStatus}
	                  </strong>
	                  {followupTransformationExecution?.executed_at
	                    ? ` · ${t("admin.quote_detail.executed_on", { date: formatDate(String(followupTransformationExecution.executed_at), language) })}`
	                    : null}
	                  {followupTransformationExecution?.rolled_back_at
	                    ? ` · ${t("admin.quote_detail.rollback_on", { date: formatDate(String(followupTransformationExecution.rolled_back_at), language) })}`
	                    : null}
	                </p>
	                <div className="quote-quick-transform-summary top-gap-sm">
	                  <p><strong>{t("admin.quote_detail.bookings_created")}:</strong> {transformationExecutionSummary.bookings}</p>
	                  <p><strong>{t("admin.quote_detail.charges_created")}:</strong> {transformationExecutionSummary.transactions}</p>
	                  <p><strong>{t("admin.quote_detail.subscriptions_created")}:</strong> {transformationExecutionSummary.subscriptions}</p>
	                  <p><strong>{t("admin.quote_detail.clients_created")}:</strong> {transformationExecutionSummary.users}</p>
	                </div>
                {followupTransformationFailureUi ? (
                  <div className="quote-transform-issue-card blocked quote-transform-execution-alert top-gap-sm">
                    <p className="quote-transform-execution-alert-title">
                      <strong>{followupTransformationFailureUi.title}</strong>
                    </p>
                    <p>{followupTransformationFailureUi.summary}</p>
                    <p>{followupTransformationFailureUi.guidance}</p>
                    {followupTransformationFailureUi.actionHref && followupTransformationFailureUi.actionLabel ? (
                      <div className="row wrap gap-sm">
                        <Link className="ghost" href={followupTransformationFailureUi.actionHref}>
                          {followupTransformationFailureUi.actionLabel}
                        </Link>
                      </div>
                    ) : null}
	                    <p className="muted">
	                      <strong>{t("admin.quote_detail.technical_detail")}:</strong> {followupTransformationFailureUi.technicalMessage}
	                    </p>
                  </div>
                ) : null}
                {canRollbackTransformation && activeFollowup ? (
                  <form id={`followup-rollback-form-${activeFollowup.id}`} action={rollbackQuoteTransformationAction} className="top-gap-sm">
                    <input type="hidden" name="quote_id" value={detail.quote.id} />
                    <input type="hidden" name="followup_id" value={activeFollowup.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
	                    <ConfirmSubmitButton
	                      formId={`followup-rollback-form-${activeFollowup.id}`}
	                      label={t("admin.quote_detail.rollback_transformation")}
	                      title={t("admin.quote_detail.rollback_confirm_title")}
	                      description={t("admin.quote_detail.rollback_confirm_description")}
	                      confirmLabel={t("admin.quote_detail.restore_previous_state")}
	                      language={language}
	                    />
                  </form>
                ) : null}
              </section>
            ) : null}

            <QuoteQuickTransformPanel
              quoteId={detail.quote.id}
              currency={detail.quote.currency}
              analysis={quickTransformAnalysis}
              transformBasePath={transformBasePath}
              returnTo={selfPath}
              scenarioLinks={quickScenarioLinks}
              quickTransformAction={quickTransformQuoteAction}
              language={language}
            />

	            <section className="card">
	              <h3>{t("admin.quote_detail.full_wizard_title")}</h3>
	              <p className="muted">{t("admin.quote_detail.full_wizard_subtitle")}</p>
	              <div className="row wrap gap-sm top-gap-sm">
	                <Link className="ghost" href={transformBasePath}>{t("admin.quote_detail.transform_to_enrollment")}</Link>
	                <Link className="ghost" href={`${transformBasePath}&scenario=A`}>{t("admin.quote_detail.scenario_a_simple")}</Link>
	                <Link className="ghost" href={`${transformBasePath}&scenario=B`}>{t("admin.quote_detail.scenario_b_ambiguous")}</Link>
	                <Link className="ghost" href={`${transformBasePath}&scenario=C`}>{t("admin.quote_detail.scenario_c_blocking")}</Link>
	              </div>
	            </section>

            <section id="quote-validation-integration">
              <QuoteValidationIntegrationSection
                validationRows={validationRows}
                projectionCard={<QuoteIntegrationProjectionCard rows={projectionRows} language={language} />}
                clientMatchCard={(
                  <QuoteClientMatchCard
                    status={clientMatchStatus}
                    detail={
                      clientMatchStatus === "deja_lie"
                        ? t("admin.quote_detail.client_match_detail_linked")
                        : clientMatchStatus === "multiple"
                        ? t("admin.quote_detail.client_match_detail_multiple")
                        : clientMatchStatus === "probable"
                        ? t("admin.quote_detail.client_match_detail_probable")
                        : t("admin.quote_detail.client_match_detail_none")
                    }
                    language={language}
                  />
                )}
                integrationResultCard={<QuoteIntegrationResultCard rows={integrationResultRows} language={language} />}
                note={t("admin.quote_detail.integration_note")}
                language={language}
              />
            </section>

	            <section className="card">
	              <h3>{t("admin.quote_detail.post_approval_title")}</h3>
	              {activeFollowup ? (
	                <>
	                  <p className="muted">
	                    {t("admin.quote_detail.followup_status")}: <strong>{activeFollowup.status}</strong> · {t("admin.quote_detail.payment")} : <strong>{activeFollowup.payment_method_status}</strong> · {t("admin.quote_detail.solfege")}: <strong>{activeFollowup.solfege_slot_status}</strong>
	                  </p>

                  <div className="grid cols-2 top-gap-sm">
                    <QuoteFollowupSlotForm
                      followupId={activeFollowup.id}
                      returnTo={selfPath}
                      solfegeRules={solfegeRules}
                      initialLevelCode={followupLevelCode}
                      initialSelectedSlot={followupSelectedSlot}
                      language={language}
                      submitAction={selectQuoteFollowupSlotAction}
                    />

	                    <form id={`followup-payment-form-${activeFollowup.id}`} action={changeQuoteFollowupPaymentMethodAction} className="card quote-followup-form">
	                      <h4>{t("admin.quote_detail.change_payment_method")}</h4>
                      <input type="hidden" name="followup_id" value={activeFollowup.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
	                      <label>
	                        {t("admin.quote_detail.method")}
	                        <select name="payment_method_code" defaultValue={followupMethodDefaultCode} required>
	                          <option value="">{t("common.select")}</option>
                          {Array.from(paymentMethodOptionsByCode.values()).map((item) => (
                            <option key={item.code} value={item.code}>
                              {item.label}
                            </option>
                          ))}
	                        </select>
	                        <small className="muted">{t("admin.quote_detail.payment_methods_from_plans")}</small>
	                      </label>
	                      <label>
	                        {t("admin.quote_detail.payment_plan_optional")}
	                        <select name="payment_plan_id" defaultValue={followupPaymentPlanId}>
	                          <option value="">{t("admin.quote_detail.none")}</option>
                          {paymentPlans.map((row) => (
                            <option key={row.id} value={row.id}>{row.name} ({paymentMethodLabel(row.payment_method, language)})</option>
                          ))}
                        </select>
                      </label>
	                      <ConfirmSubmitButton
	                        formId={`followup-payment-form-${activeFollowup.id}`}
	                        label={t("admin.quote_detail.update_payment")}
	                        title={t("admin.quote_detail.update_payment_confirm_title")}
	                        description={t("admin.quote_detail.update_payment_confirm_description")}
	                        confirmLabel={t("admin.quote_detail.update")}
	                        language={language}
	                      />
                    </form>
                  </div>

                  <form id={`followup-finalize-form-${activeFollowup.id}`} action={finalizeQuoteFollowupAction} className="row top-gap-sm">
                    <input type="hidden" name="followup_id" value={activeFollowup.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
	                    <ConfirmSubmitButton
	                      formId={`followup-finalize-form-${activeFollowup.id}`}
	                      label={followupTransformationPayload ? t("admin.quote_detail.execute_transformation_now") : t("admin.quote_detail.finalize_post_approval")}
	                      title={followupTransformationPayload ? t("admin.quote_detail.execute_transformation_confirm_title") : t("admin.quote_detail.finalize_post_approval_confirm_title")}
	                      description={followupTransformationPayload
	                        ? t("admin.quote_detail.execute_transformation_confirm_description")
	                        : t("admin.quote_detail.finalize_post_approval_confirm_description")}
	                      confirmLabel={followupTransformationPayload ? t("admin.quote_detail.execute_transformation") : t("admin.quote_detail.finalize")}
	                      language={language}
	                    />
                  </form>
                </>
	              ) : (
	                <p className="muted">{t("admin.quote_detail.no_active_followup")}</p>
	              )}
	            </section>
	            <section className="card">
	              <h3>{t("admin.quote_detail.snapshot_schedule")}</h3>
	              <div className="quote-public-lines top-gap-sm">
	                {getScheduleItems(detail.quote.payment_terms_snapshot).length === 0 ? (
	                  <p className="muted">{t("admin.quote_detail.no_schedule")}</p>
	                ) : (
	                  getScheduleItems(detail.quote.payment_terms_snapshot).map((item, index) => (
	                    <article key={`schedule-${index}`} className="quote-public-line-item">
	                      <strong>{String(item.label ?? t("admin.quote_detail.schedule_item_fallback", { index: index + 1 }))}</strong>
	                      <span>{formatScheduleDueLabel(item, language)}</span>
                      <small>{String(item.amount_ttc ?? "0")} {detail.quote.currency}</small>
                    </article>
                  ))
                )}
              </div>
            </section>
          </>
        ) : null}
      </QuoteWorkspaceShell>
    </section>
  );
}
