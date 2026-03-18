import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ConfirmSubmitButton from "../../../../components/confirm-submit-button";
import CopyLinkButton from "../../../../components/copy-link-button";
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
import {
  cancelQuoteAction,
  changeQuoteFollowupPaymentMethodAction,
  duplicateQuoteAction,
  finalizeQuoteFollowupAction,
  quickTransformQuoteAction,
  regenerateQuoteDocumentAction,
  resendQuoteAction,
  rollbackQuoteTransformationAction,
  restoreQuotePublicResponseAction,
  selectQuoteFollowupSlotAction,
  sendQuoteAction,
  updateQuoteLinesAction,
  updateQuotePlanningAction,
  updateQuoteSettingsAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import {
  analyzeQuoteQuickTransformStatus,
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
} from "../../../../lib/types";

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

type TermsTemplateOut = {
  id: string;
  name: string;
  language: string;
};

type QuoteTemplateV2Out = {
  id: string;
  name: string;
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

function messagingTemplateRef(template: AdminMessagingTemplateOut): string {
  if (template.kind === "PREDEFINED") {
    return `predefined:${template.code || ""}`;
  }
  return `custom:${template.id}`;
}

function messagingTemplateOptionLabel(template: AdminMessagingTemplateOut): string {
  const suffix = template.kind === "PREDEFINED" ? "Systeme" : "Personnalise";
  return `${template.name} · ${suffix}`;
}

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
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

function buildQuoteTransformationFailureUi(
  technicalMessage: string,
  transformBasePath: string,
): QuoteTransformationFailureUi {
  const normalized = String(technicalMessage || "").trim().toLowerCase();
  if (normalized.includes("correspondance live")) {
    return {
      title: "Blocage sur les creneaux live",
      summary: "C'est un blocage reel, pas un simple warning.",
      guidance:
        "Le devis pointe encore vers au moins un creneau du snapshot qui n'a plus de correspondance exacte dans le planning live. Il faut reouvrir l'etape Planning / creneaux, reassigner le creneau, puis relancer la transformation.",
      actionLabel: "Revoir les creneaux dans le wizard",
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
      title: "Blocage sur la reservation du creneau",
      summary: "La transformation ne peut pas continuer tant que le creneau n'est pas de nouveau reservable.",
      guidance:
        "Reouvrez l'etape Planning / creneaux pour verifier la disponibilite live, choisir un autre creneau si besoin, puis relancer la transformation.",
      actionLabel: "Verifier le planning live",
      actionHref: `${transformBasePath}&step=3`,
      technicalMessage,
    };
  }
  return {
    title: "Blocage de transformation",
    summary: "La transformation a echoue et rien n'a ete cree.",
    guidance:
      "Corrigez le point bloquant indique ci-dessous, puis relancez la transformation. Si besoin, repassez par le wizard complet pour reverifier les etapes.",
    actionLabel: "Reouvrir le wizard complet",
    actionHref: transformBasePath,
    technicalMessage,
  };
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return `${value} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: currency || "EUR" }).format(amount);
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

function paymentMethodLabel(methodCode: string): string {
  const normalized = String(methodCode || "").trim().toUpperCase();
  if (normalized === "CARD") return "Carte bancaire";
  if (normalized === "CARD_MONTHLY") return "Carte bancaire mensuelle";
  if (normalized === "CHECK") return "Cheque";
  if (normalized === "BANK_TRANSFER") return "Virement bancaire";
  if (normalized === "CASH") return "Especes";
  if (normalized === "CARD_4X_FEES") return "4 fois avec frais";
  if (!normalized) return "-";
  return normalized;
}

function labelForContext(contextType: string): string {
  return contextType === "active_client" ? "Client actif" : "Acquisition";
}

function labelForProspectType(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "child") return "Enfant";
  if (normalized === "adult") return "Adulte";
  return "-";
}

function labelForClientKind(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toUpperCase();
  if (normalized === "CHILD") return "Enfant";
  if (normalized === "ADULT") return "Adulte";
  return "-";
}

function labelForQuoteStatus(value: string | null | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "created") return "Brouillon";
  if (normalized === "sent") return "Envoye";
  if (normalized === "approved") return "Approuve";
  if (normalized === "rejected") return "Refuse";
  if (normalized === "change_requested") return "Modification demandee";
  if (normalized === "cancelled") return "Annule";
  if (normalized === "expired") return "Expire";
  return normalized || "-";
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
}

function locationNameById(locations: LocationOut[], locationId: string | null): string {
  if (!locationId) {
    return "Lieu non defini";
  }
  return locations.find((row) => row.id === locationId)?.name || "Lieu non defini";
}

function getScheduleItems(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const raw = snapshot.schedule;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

function formatScheduleDueLabel(item: Record<string, unknown>): string {
  const dueType = String(item.due_type ?? "").trim().toLowerCase();
  const dueLabel = String(item.due_label ?? "").trim();
  const normalized = dueLabel.toLowerCase();
  if (dueType === "on_registration") {
    return "à réception de votre facture";
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
    return "à réception de votre facture";
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

const MONTH_LABELS_FR = [
  "Janvier",
  "Fevrier",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Aout",
  "Septembre",
  "Octobre",
  "Novembre",
  "Decembre",
];

type PlanningSummaryBlock = {
  key: string;
  title: string;
  count: number;
  semester1: Array<{ monthLabel: string; days: string }>;
  semester2: Array<{ monthLabel: string; days: string }>;
};

function planningVisualSummary(sessions: Array<Record<string, unknown>>): PlanningSummaryBlock[] {
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
    const activityLabel = String(session.activity_label ?? "").trim() || "Activite";
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
    const months = Array.from(monthMap.keys()).sort((a, b) => a - b);
    return months
      .filter((month) => (semester === 1 ? month >= 9 || month <= 1 : month >= 2 && month <= 8))
      .map((month) => {
        const days = Array.from(new Set(monthMap.get(month) || [])).sort((a, b) => a - b);
        return {
          monthLabel: MONTH_LABELS_FR[month - 1] || String(month),
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

function adjustmentTypeLabel(type: QuoteFinancialAdjustment["type"]): string {
  if (type === "credit") {
    return "Avoir";
  }
  if (type === "debt") {
    return "Dette";
  }
  return "Aucun";
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

function commercialStateLabel(state: QuoteValidationUiState): string {
  if (state === "brouillon") return "Brouillon";
  if (state === "incomplet") return "Incomplet";
  if (state === "pret_a_envoyer") return "Pret a envoyer";
  if (state === "envoye") return "Envoye";
  if (state === "consulte") return "Consulte";
  if (state === "modification_demandee") return "Modification demandee";
  if (state === "valide") return "Valide";
  if (state === "refuse") return "Refuse";
  return "Expire";
}

function validationClientLabelFromQuote(quote: QuoteOut): string {
  const status = String(quote.status || "").trim().toLowerCase();
  if (status === "approved") {
    return "Valide";
  }
  if (status === "change_requested") {
    return "Modification demandee";
  }
  if (status === "rejected") {
    return "Refuse";
  }
  return "En attente";
}

function validationClientDateLabelFromQuote(quote: QuoteOut): string {
  const status = String(quote.status || "").trim().toLowerCase();
  const meta = quote.meta || {};
  const lastPublicResponseAt = readStringMeta(meta, "public_response_last_at", "");
  if (status === "approved") {
    return formatDate(quote.approved_at);
  }
  if (status === "change_requested") {
    return lastPublicResponseAt ? `Recue le ${formatDate(lastPublicResponseAt)}` : "Recue";
  }
  if (status === "rejected") {
    return lastPublicResponseAt ? `Refuse le ${formatDate(lastPublicResponseAt)}` : "Refuse";
  }
  return "En attente";
}

const QUOTE_INTERACTION_EVENT_TYPES = new Set([
  "quote_created",
  "quote_document_regenerated",
  "quote_email_sent",
  "quote_sms_sent",
  "quote_sent",
  "quote_resent",
  "quote_approved",
  "quote_rejected",
  "quote_change_requested",
  "quote_public_confirmation_email_failed",
  "quote_public_confirmation_email_skipped",
  "quote_public_response_restored",
  "quote_cancelled",
  "quote_reminder_sent",
  "quote_expired",
  "quote_transformation_executed",
  "quote_transformation_rolled_back",
]);

function quoteEventTitle(event: QuoteEventOut): string {
  const type = String(event.event_type || "").trim().toLowerCase();
  if (type === "quote_created") return "Devis cree";
  if (type === "quote_document_regenerated") return "Document regenere";
  if (type === "quote_email_sent") return "Email envoye";
  if (type === "quote_sms_sent") return "SMS envoye";
  if (type === "quote_sent") return "Devis envoye";
  if (type === "quote_resent") return "Devis renvoye";
  if (type === "quote_approved") return "Devis approuve";
  if (type === "quote_rejected") return "Devis rejete";
  if (type === "quote_change_requested") return "Demande de modification";
  if (type === "quote_public_confirmation_email_failed") return "Confirmation client non envoyee";
  if (type === "quote_public_confirmation_email_skipped") return "Confirmation client ignoree";
  if (type === "quote_public_response_restored") return "Reponse client restauree";
  if (type === "quote_cancelled") return "Devis annule";
  if (type === "quote_reminder_sent") return "Relance envoyee";
  if (type === "quote_expired") return "Devis expire";
  if (type === "quote_transformation_executed") return "Transformation executee";
  if (type === "quote_transformation_rolled_back") return "Transformation annulee";
  return type || "Evenement";
}

function quoteEventTone(event: QuoteEventOut): "client" | "admin" | "system" {
  const type = String(event.event_type || "").trim().toLowerCase();
  if (["quote_approved", "quote_rejected", "quote_change_requested"].includes(type)) {
    return "client";
  }
  if (
    [
      "quote_public_response_restored",
      "quote_cancelled",
      "quote_transformation_rolled_back",
      "quote_document_regenerated",
      "quote_email_sent",
      "quote_sms_sent",
      "quote_sent",
      "quote_resent",
    ].includes(type)
  ) {
    return "admin";
  }
  return "system";
}

function quoteEventDescription(event: QuoteEventOut): string {
  const type = String(event.event_type || "").trim().toLowerCase();
  const payload = event.payload || {};
  const actorLabel = event.actor_label || (event.actor_type === "admin" ? "Admin" : event.actor_type === "prospect" ? "Client / prospect" : "Systeme");
  const message = typeof payload.message === "string" ? payload.message.trim() : "";
  const recipientEmail = typeof payload.recipient_email === "string" ? payload.recipient_email.trim() : "";
  const recipientPhone = typeof payload.recipient_phone === "string" ? payload.recipient_phone.trim() : "";
  const fromStatus = typeof payload.from_status === "string" ? payload.from_status.trim() : "";
  const toStatus = typeof payload.to_status === "string" ? payload.to_status.trim() : "";
  const error = typeof payload.error === "string" ? payload.error.trim() : "";
  if (type === "quote_change_requested") {
    return message || "Le client a demande une correction sans laisser de message detaille.";
  }
  if (type === "quote_public_response_restored") {
    return `Action admin par ${actorLabel}${fromStatus || toStatus ? ` · ${labelForQuoteStatus(fromStatus)} -> ${labelForQuoteStatus(toStatus)}` : ""}`;
  }
  if (type === "quote_document_regenerated") {
    return `Le document gele du devis a ete regenere par ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_email_sent") {
    return recipientEmail ? `Email operationnel envoye a ${recipientEmail}.` : `Email operationnel envoye par ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_sms_sent") {
    return recipientPhone ? `SMS envoye au ${recipientPhone}.` : `SMS envoye par ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_sent" || type === "quote_resent") {
    const channels = [recipientEmail ? `email ${recipientEmail}` : "", recipientPhone ? `SMS ${recipientPhone}` : ""].filter(Boolean).join(" · ");
    return channels ? `Envoi au destinataire via ${channels}.` : `Action ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_public_confirmation_email_failed") {
    return error || "La confirmation automatique apres reponse client n a pas pu etre envoyee.";
  }
  if (type === "quote_public_confirmation_email_skipped") {
    return "Aucune confirmation client n a ete envoyee pour cette action.";
  }
  if (type === "quote_cancelled") {
    return `Action ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_transformation_executed" || type === "quote_transformation_rolled_back") {
    return `Action ${actorLabel.toLowerCase()}.`;
  }
  if (type === "quote_approved" || type === "quote_rejected") {
    return `Reponse recue depuis la page publique.`;
  }
  if (type === "quote_reminder_sent") {
    return "Relance automatique avant expiration.";
  }
  if (type === "quote_expired") {
    return "Le devis a atteint sa date d'expiration.";
  }
  return `Action ${actorLabel.toLowerCase()}.`;
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

function integrationStateLabel(state: QuoteIntegrationUiState): string {
  if (state === "non_concerne") return "Non concerne";
  if (state === "en_attente_validation_client") return "En attente validation client";
  if (state === "a_preparer") return "A preparer";
  if (state === "a_verifier") return "A verifier";
  if (state === "pret_a_integrer") return "Pret a integrer";
  if (state === "integre") return "Integre";
  return "Erreur integration";
}

export default async function AdminQuoteDetailPage({ params, searchParams }: RouteParams): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    redirect("/admin/quotes?error=Devis%20introuvable");
  }

  const backPath = safeBackPath(readParam(searchParams, "back"));
  const activeSection = parseWorkspaceSection(readParam(searchParams, "section"));
  const quickScenario = parseQuickScenario(readParam(searchParams, "quick_scenario"));
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [
    detailResult,
    followupsResult,
    paymentPlansResult,
    quoteTypesResult,
    plansResult,
    legalEntitiesResult,
    catalogsResult,
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
    backendRequest<TermsTemplateOut[]>("/api/v1/terms-templates?active_only=true", {}, token),
    backendRequest<QuoteTemplateV2Out[]>("/api/v1/quote-templates-v2?active_only=true", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<AdminCatalogProductOut[]>("/api/v1/admin/config/catalog/products?include_inactive=true", {}, token),
    backendRequest<AdminCatalogKitOut[]>("/api/v1/admin/config/catalog/kits?include_inactive=true", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
    backendRequest<SolfegeLevelRuleOut[]>("/api/v1/solfege-level-rules", {}, token),
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=800&include_archived=false", {}, token),
    backendRequest<QuoteDocumentPreviewOut>(
      `/api/v1/quotes/${encodeURIComponent(quoteId)}/document-preview?audience=admin_preview`,
      {},
      token,
    ),
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
          <h2>Detail devis</h2>
          <p className="flash-err">{detailResult.message}</p>
          <div className="row top-gap-sm">
            <Link className="ghost" href={backPath}>Retour liste devis</Link>
          </div>
        </section>
      </section>
    );
  }

  const detail = detailResult.data;
  const pricingCatalogId = detail.quote.pricing_catalog_id || "";
  const [activityPricesResult, productPricesResult, kitPricesResult] = pricingCatalogId
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
  const termsTemplates = termsTemplatesResult.ok ? termsTemplatesResult.data : [];
  const quoteTemplates = quoteTemplatesResult.ok ? quoteTemplatesResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const products = productsResult.ok ? productsResult.data : [];
  const kits = kitsResult.ok ? kitsResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const solfegeRules = solfegeRulesResult.ok ? solfegeRulesResult.data : [];
  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const clients = clientsResult.ok ? clientsResult.data : [];
  const documentPreview = documentPreviewResult.ok ? documentPreviewResult.data : null;
  const messagingSettings = messagingSettingsResult.ok ? messagingSettingsResult.data : null;
  const quoteSendTemplates = quoteSendTemplatesResult.ok ? quoteSendTemplatesResult.data : [];
  const quoteSendSmsTemplates = quoteSendSmsTemplatesResult.ok ? quoteSendSmsTemplatesResult.data : [];
  const quoteCancelTemplates = quoteCancelTemplatesResult.ok ? quoteCancelTemplatesResult.data : [];
  const quoteCancelSmsTemplates = quoteCancelSmsTemplatesResult.ok ? quoteCancelSmsTemplatesResult.data : [];
  const activityPrices = activityPricesResult?.ok ? activityPricesResult.data : [];
  const productPrices = productPricesResult?.ok ? productPricesResult.data : [];
  const kitPrices = kitPricesResult?.ok ? kitPricesResult.data : [];

  const activityIds = Array.from(new Set(
    detail.lines
      .map((line) => line.activity_id)
      .filter((activityId): activityId is string => Boolean(activityId)),
  ));

  const sessionsPerActivity = await Promise.all(
    activityIds.map(async (activityId) => {
      const query = new URLSearchParams();
      query.set("course_type_id", activityId);
      if (detail.quote.location_id) {
        query.set("location_id", detail.quote.location_id);
      }
      const result = await backendRequest<AdminSessionOut[]>(
        `/api/v1/admin/sessions?${query.toString()}`,
        {},
        token,
      );
      return { activityId, sessions: result.ok ? result.data : [] };
    }),
  );

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
    ? displayName(owner.first_name, owner.last_name, owner.email)
    : "-";
  const ownerPhone = selectedProspect?.phone
    || selectedClient?.mobile_phone_1
    || selectedClient?.phone
    || selectedClient?.home_phone
    || "-";
  const prospectMeta = readObject(selectedProspect?.meta) || {};
  const prospectType = String(prospectMeta.prospect_type ?? "").trim().toLowerCase();
  const prospectTypeLabel = labelForProspectType(prospectType);
  const clientKindLabel = labelForClientKind(selectedClient?.client_kind);
  const sourceTypeLabel = prospectTypeLabel !== "-" ? prospectTypeLabel : clientKindLabel;
  const sourceTypeOrigin = prospectTypeLabel !== "-" ? "prospect" : clientKindLabel !== "-" ? "client" : "inconnu";
  const parentReferent = readObject(prospectMeta.parent_referent);
  const parentReferentName = parentReferent
    ? displayName(
      typeof parentReferent.first_name === "string" ? parentReferent.first_name : null,
      typeof parentReferent.last_name === "string" ? parentReferent.last_name : null,
      typeof parentReferent.email === "string" ? parentReferent.email : "Parent referent",
    )
    : "-";
  const parentReferentEmail = parentReferent && typeof parentReferent.email === "string" ? parentReferent.email : "-";
  const parentReferentPhone = parentReferent && typeof parentReferent.phone === "string" ? parentReferent.phone : "-";

  const familyLinks = clientFamily
    ? [
      ...clientFamily.links_as_adult.map((link) => ({
        key: `adult-${link.id}`,
        role: "Enfant rattache",
        personName: displayName(link.child.first_name, link.child.last_name, link.child.email),
        personEmail: link.child.email,
        billing: link.is_billing_recipient,
      })),
      ...clientFamily.links_as_child.map((link) => ({
        key: `child-${link.id}`,
        role: "Adulte rattache",
        personName: displayName(link.adult.first_name, link.adult.last_name, link.adult.email),
        personEmail: link.adult.email,
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
  const hasPublicChangeRequest = quoteStatus === "change_requested" || publicResponseLastAction === "change_requested";
  const publicChangeRequestReceivedLabel = publicResponseLastAt ? formatDate(publicResponseLastAt) : "Date non disponible";
  const publicChangeRequestMessage = publicResponseLastMessage || "Le client a demande une modification sans laisser de message detaille.";
  const canSendQuote = quoteStatus === "created";
  const canResendQuote = ["sent", "approved", "rejected", "expired", "change_requested"].includes(quoteStatus);
  const canCancelQuote = !["cancelled", "approved"].includes(quoteStatus);
  const canRestorePublicResponse = ["approved", "rejected", "change_requested"].includes(quoteStatus);
  const restoreTargetStatusRaw = readStringMeta(detail.quote.meta || {}, "public_response_previous_status", "").trim().toLowerCase();
  const restoreTargetStatus =
    restoreTargetStatusRaw === "sent" || restoreTargetStatusRaw === "change_requested"
      ? restoreTargetStatusRaw
      : "sent";
  const restoreTargetStatusLabel = labelForQuoteStatus(restoreTargetStatus);
  const primaryRecipientLabel = detail.quote.context_type === "acquisition" ? "prospect" : "client";
  const ownerEmail = String(owner?.email || "").trim().toLowerCase();
  const lastRecipientEmail = readStringMeta(detail.quote.meta || {}, "recipient_email", "").trim().toLowerCase();
  const lastRecipientPhone = readStringMeta(detail.quote.meta || {}, "recipient_phone", "").trim();
  const defaultThirdPartyEmail = lastRecipientEmail && lastRecipientEmail !== ownerEmail ? lastRecipientEmail : "";
  const defaultPrimaryPhone = [lastRecipientPhone, resolvedParentReferentPhone, ownerPhone]
    .map((value) => String(value || "").trim())
    .find((value) => value && value !== "-") || "";
  const defaultSendTemplateRef =
    messagingSettings?.quote_send_template_ref ||
    (quoteSendTemplates[0] ? messagingTemplateRef(quoteSendTemplates[0]) : "");
  const defaultSendSmsTemplateRef =
    messagingSettings?.quote_send_sms_template_ref ||
    (quoteSendSmsTemplates[0] ? messagingTemplateRef(quoteSendSmsTemplates[0]) : "");
  const defaultCancelTemplateRef =
    messagingSettings?.quote_cancel_template_ref ||
    (quoteCancelTemplates[0] ? messagingTemplateRef(quoteCancelTemplates[0]) : "");
  const defaultCancelSmsTemplateRef =
    messagingSettings?.quote_cancel_sms_template_ref ||
    (quoteCancelSmsTemplates[0] ? messagingTemplateRef(quoteCancelSmsTemplates[0]) : "");
  const validationClientStatusLabel = validationClientLabelFromQuote(detail.quote);
  const validationClientStatusDetail = validationClientDateLabelFromQuote(detail.quote);
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
            <h3>Historique des interactions</h3>
            <p className="muted">Trace des actions client, BO et automatisations sur ce devis.</p>
          </div>
        </div>
        <ol className="quote-interactions-timeline top-gap-sm">
          {interactionEvents.map((event) => (
            <li key={event.id} className={`quote-interaction-item is-${quoteEventTone(event)}`}>
              <div className="quote-interaction-dot" aria-hidden="true" />
              <div className="quote-interaction-body">
                <div className="row spread wrap gap-sm">
                  <div>
                    <strong>{quoteEventTitle(event)}</strong>
                    <div className="muted">
                      {formatDate(event.created_at)}
                      {event.actor_label ? ` · ${event.actor_label}` : ""}
                    </div>
                  </div>
                </div>
                <p className="top-gap-xs">{quoteEventDescription(event)}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    ) : null;
  const quoteTermsTemplateId = detail.quote.terms_template_id || readStringMeta(detail.quote.meta || {}, "terms_template_id");
  const calendarSessions = getCalendarSessions(detail.quote.calendar_snapshot || {});
  const planningBlocks = getPlanningBlocks(detail.quote.calendar_snapshot || {});
  const planningByActivityId: Record<string, { plannedQuantity: number; pendingSelection: boolean }> = {};
  for (const session of calendarSessions) {
    const activityId = String(session.activity_id ?? "").trim();
    if (!activityId) {
      continue;
    }
    if (!(activityId in planningByActivityId)) {
      planningByActivityId[activityId] = { plannedQuantity: 0, pendingSelection: false };
    }
    planningByActivityId[activityId].plannedQuantity += 1;
  }
  for (const block of planningBlocks) {
    const activityId = String(block.activity_id ?? "").trim();
    if (!activityId) {
      continue;
    }
    if (!(activityId in planningByActivityId)) {
      planningByActivityId[activityId] = { plannedQuantity: 0, pendingSelection: false };
    }
    const rawPending = block.selection_pending;
    const isPending = rawPending === true || String(rawPending ?? "").trim().toLowerCase() === "true";
    if (isPending) {
      planningByActivityId[activityId].pendingSelection = true;
    }
  }
  const planningSummary = planningVisualSummary(calendarSessions);
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
      label: paymentMethodLabel(code),
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
  const defaultVatRate = resolveDefaultVatRate(detail);
  const signedAdjustment = adjustmentSignedAmount(quoteAdjustment);
  const totalTtcNumber = Number(detail.quote.total_ttc);
  const totalBeforeAdjustment = Number.isFinite(totalTtcNumber) ? totalTtcNumber - signedAdjustment : null;
  const languageQuoteTemplates = quoteTemplates.filter((row) => normalizeLang(row.language) === normalizeLang(quoteLanguage));
  const selectedTemplate = quoteTemplates.find((row) => row.id === quoteTemplateId);
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
  const adminPdfHref = `/admin/quotes/${detail.quote.id}/pdf${pdfVersionTag ? `?v=${encodeURIComponent(pdfVersionTag)}` : ""}`;
  const publicPdfHref = detail.quote.public_pdf_url
    ? `${detail.quote.public_pdf_url}${pdfVersionTag ? `&v=${encodeURIComponent(pdfVersionTag)}` : ""}`
    : detail.quote.pdf_token
    ? `/q/${detail.quote.id}/pdf?t=${encodeURIComponent(detail.quote.pdf_token)}${pdfVersionTag ? `&v=${encodeURIComponent(pdfVersionTag)}` : ""}`
    : null;
  const regenerateFormId = `quote-regenerate-form-${detail.quote.id}`;
  const restorePublicResponseFormId = `quote-restore-public-response-form-${detail.quote.id}`;
  const sendPrimaryFormId = `quote-send-primary-form-${detail.quote.id}`;
  const sendThirdPartyFormId = `quote-send-third-party-form-${detail.quote.id}`;

  const quoteBasePath = `/admin/quotes/${encodeURIComponent(detail.quote.id)}`;
  const sectionHref = (section: QuoteWorkspaceSection): string =>
    `${quoteBasePath}?back=${encodeURIComponent(backPath)}&section=${section}`;
  const selfPath = appendQuickScenario(sectionHref(activeSection), quickScenario);
  const transformBasePath = `${quoteBasePath}/transform?back=${encodeURIComponent(selfPath)}${quickScenario === "live" ? "" : `&scenario=${quickScenario}`}`;
  const followupTransformationFailureUi =
    followupTransformationExecutionStatus === "failed" && followupTransformationFailedMessage
      ? buildQuoteTransformationFailureUi(followupTransformationFailedMessage, transformBasePath)
      : null;
  const quickScenarioLinks = [
    {
      key: "live" as const,
      label: "Live",
      href: sectionHref("integration"),
      active: quickScenario === "live",
    },
    {
      key: "A" as const,
      label: "Scenario 1 (auto-validable)",
      href: appendQuickScenario(sectionHref("integration"), "A"),
      active: quickScenario === "A",
    },
    {
      key: "B" as const,
      label: "Scenario 2 (a verifier)",
      href: appendQuickScenario(sectionHref("integration"), "B"),
      active: quickScenario === "B",
    },
    {
      key: "C" as const,
      label: "Scenario 3 (bloque)",
      href: appendQuickScenario(sectionHref("integration"), "C"),
      active: quickScenario === "C",
    },
  ];
  const commercialState = commercialStateFromQuote(detail.quote);
  const integrationState = integrationStateFromQuote(detail.quote, commercialState, activeFollowup);
  const validationChannel = readStringMeta(detail.quote.meta || {}, "validation_channel", detail.quote.approved_at ? "Portail public" : "-");
  const integrationTargetMode = readStringMeta(detail.quote.meta || {}, "integration_target_mode", "Creation / mise a jour a verifier");
  const clientMatchRaw = readStringMeta(detail.quote.meta || {}, "client_match_status", detail.quote.client_id ? "deja_lie" : "aucun").toLowerCase();
  const clientMatchStatus = clientMatchRaw === "probable" || clientMatchRaw === "multiple" || clientMatchRaw === "deja_lie" ? clientMatchRaw : "aucun";
  const integrationAlerts: string[] = [];
  if (detail.quote.status === "approved" && integrationState === "a_preparer") {
    integrationAlerts.push("Devis valide a preparer pour integration.");
  }
  if (integrationState === "a_verifier") {
    integrationAlerts.push("Correspondance client a verifier.");
  }
  if (integrationState === "erreur_integration") {
    integrationAlerts.push(
      followupTransformationFailureUi?.summary
        || "Erreur d'integration detectee.",
    );
  }
  if (detail.quote.document_status === "stale") {
    integrationAlerts.push("Document modifie apres validation.");
  }
  const validationRows = [
    { label: "Date validation", value: formatDate(detail.quote.approved_at) },
    { label: "Canal validation", value: validationChannel },
    { label: "Version validee (hash)", value: detail.quote.document_hash || "-" },
    {
      label: "Version utilisee pour integration",
      value: readStringMeta(detail.quote.meta || {}, "integration_document_hash", detail.quote.document_hash || "-"),
    },
    { label: "Derniere modification admin", value: formatDate(detail.quote.created_at) },
  ];
  const projectionRows = [
    { label: "Mode cible", value: integrationTargetMode },
    { label: "Contact payeur", value: ownerName },
    { label: "Eleve(s)", value: readStringMeta(detail.quote.meta || {}, "integration_students_label", ownerName) },
    { label: "Activites acceptees", value: String(getPlanningBlocks(detail.quote.calendar_snapshot || {}).length || 0) },
    { label: "Creneaux a creer / maj", value: String(calendarSessions.length) },
    { label: "Annee scolaire", value: detail.quote.school_year_label || "-" },
    {
      label: "Plan de paiement",
      value: paymentPlans.find((plan) => plan.id === detail.quote.payment_plan_id)?.name || "Aucun",
    },
    { label: "Options a reprendre", value: readStringMeta(detail.quote.meta || {}, "integration_options_label", "Selon devis valide") },
  ];
  const integrationResultRows = [
    { label: "Statut integration", value: integrationStateLabel(integrationState) },
    { label: "Client central", value: readStringMeta(detail.quote.meta || {}, "integration_client_result", "-") },
    { label: "Creneaux", value: readStringMeta(detail.quote.meta || {}, "integration_slots_result", "-") },
    { label: "Date integration", value: readStringMeta(detail.quote.meta || {}, "integration_completed_at", "-") },
    { label: "Utilisateur", value: readStringMeta(detail.quote.meta || {}, "integration_by", "-") },
    { label: "Lien fiche centrale", value: readStringMeta(detail.quote.meta || {}, "integration_client_link", "A venir") },
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
    legalEntityName: legalEntities.find((entity) => entity.id === detail.quote.legal_entity_id)?.name || "A definir",
    paymentPlanName: paymentPlans.find((plan) => plan.id === detail.quote.payment_plan_id)?.name || "-",
    quoteType: detail.quote.quote_type,
    quoteTypeFormulaName: selectedQuoteType?.formula_name || null,
    locationId: detail.quote.location_id,
    locationName: locationNameById(locations, detail.quote.location_id),
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
    meta: {},
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
    calendarSnapshot: detail.quote.calendar_snapshot || {},
    followupId: activeFollowup?.id || null,
    followupStatus: activeFollowup?.status || null,
    scenario: quickScenario,
  });

  const sidebarItems: SidebarItem[] = [
    { id: "overview", label: "Vue d'ensemble", href: sectionHref("overview"), active: activeSection === "overview" },
    { id: "cadre", label: "Cadre du devis", href: sectionHref("cadre"), active: activeSection === "cadre" },
    {
      id: "planning",
      label: "Activites planifiees",
      href: sectionHref("planning"),
      badge: `${calendarSessions.length}`,
      active: activeSection === "planning",
    },
    {
      id: "pricing",
      label: "Lignes facturees",
      href: sectionHref("pricing"),
      badge: `${detail.lines.length}`,
      active: activeSection === "pricing",
    },
    {
      id: "interactions",
      label: "Interactions client",
      href: sectionHref("interactions"),
      badge: hasPublicChangeRequest ? "!" : interactionEvents.length > 0 ? `${interactionEvents.length}` : undefined,
      badgeTone: hasPublicChangeRequest ? "alert" : "default",
      active: activeSection === "interactions",
    },
    { id: "document", label: "Envoi", href: sectionHref("document"), active: activeSection === "document" },
    {
      id: "integration",
      label: "Validation et integration",
      href: sectionHref("integration"),
      active: activeSection === "integration",
    },
  ];

  return (
    <section className="admin-page-grid">
      <QuoteWorkspaceShell
        header={(
          <QuoteWorkspaceHeader
            title={`Devis ${detail.quote.quote_number}`}
            subtitle={`${labelForContext(detail.quote.context_type)} · ${formatAmount(detail.quote.total_ttc, detail.quote.currency)} · Destinataire ${ownerName}`}
            backLink={(
              <>
                <Link className="ghost" href={backPath}>Retour liste devis</Link>
                <Link className="ghost" href="/admin/quotes/new">Nouveau devis</Link>
              </>
            )}
            statuses={[
              { label: "Commercial", value: commercialStateLabel(commercialState) },
              { label: "Document", value: detail.quote.document_status || "stale" },
              {
                label: "Validation client",
                value: validationClientStatusLabel,
                className: commercialState === "modification_demandee" ? "quote-header-status-info" : "",
              },
              { label: "Integration", value: integrationStateLabel(integrationState) },
            ]}
          />
        )}
        sidebar={<QuoteWorkspaceSidebar items={sidebarItems} />}
        rightRail={(
          <QuoteRightSummaryRail
            top={[
              { label: "Total TTC", value: formatAmount(detail.quote.total_ttc, detail.quote.currency) },
              { label: "Expiration", value: formatDate(detail.quote.expires_at) },
            ]}
            statuses={[
              { label: "Validation client", value: validationClientStatusDetail },
              { label: "Integration centrale", value: integrationStateLabel(integrationState) },
              { label: "Mode cible", value: integrationTargetMode },
              { label: "Creneaux prevus", value: String(calendarSessions.length) },
            ]}
            alerts={integrationAlerts}
          />
        )}
      >
        {ok ? <section className="flash-ok">{ok}</section> : null}
        {error ? <section className="flash-err">{error}</section> : null}

        {activeSection === "overview" ? (
          <>
            <QuoteOverviewSection
              cards={[
                { label: "Statut devis", value: commercialStateLabel(commercialState) },
                { label: "Statut document", value: detail.quote.document_status || "stale" },
                { label: "Validation client", value: validationClientStatusDetail },
                { label: "Integration centrale", value: integrationStateLabel(integrationState) },
                { label: "Total TTC", value: formatAmount(detail.quote.total_ttc, detail.quote.currency) },
                { label: "Expiration", value: formatDate(detail.quote.expires_at) },
              ]}
              alerts={integrationAlerts.map((message) => ({ level: message.toLowerCase().includes("erreur") ? "error" : "warn", message }))}
              quickActions={(
                <>
                  <Link className="ghost" href={sectionHref("document")}>Envoi</Link>
                  <Link className="ghost" href={sectionHref("interactions")}>Interactions client</Link>
                  <Link className="ghost" href={sectionHref("planning")}>Activites planifiees</Link>
                  <Link className="ghost" href={sectionHref("pricing")}>Lignes facturees</Link>
                  <Link className="ghost" href={sectionHref("integration")}>Validation et integration</Link>
                </>
              )}
            />

            <section className="card" id="quote-contact-family">
              <div className="row spread wrap gap-sm">
                <div>
                  <h3>Prospect et famille</h3>
                  <p className="muted">Informations source du devis et liens famille disponibles.</p>
                </div>
                <div className="row wrap gap-sm">
                  {selectedProspect ? (
                    <Link
                      className="ghost"
                      href={`/admin/prospects/${encodeURIComponent(selectedProspect.id)}?return_to=${encodeURIComponent(selfPath)}`}
                    >
                      Modifier prospect
                    </Link>
                  ) : null}
                  {selectedClient ? (
                    <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}?tab=infos&edit_infos=1`}>
                      Modifier infos client
                    </Link>
                  ) : null}
                  {selectedClient ? (
                    <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}?tab=famille`}>
                      Gerer famille
                    </Link>
                  ) : null}
                </div>
              </div>
              <div className="grid cols-2 top-gap-sm">
                <article className="item">
                  <h4>Contact source</h4>
                  <p><strong>Contexte:</strong> {detail.quote.context_type === "acquisition" ? "Prospect acquisition" : "Client actif"}</p>
                  <p><strong>Nom:</strong> {ownerName}</p>
                  <p><strong>Email:</strong> {owner?.email || "-"}</p>
                  <p><strong>Telephone:</strong> {ownerPhone}</p>
                  <div className="row wrap gap-sm top-gap-sm">
                    {selectedProspect ? (
                      <Link className="ghost" href={`/admin/prospects/${encodeURIComponent(selectedProspect.id)}`}>
                        Ouvrir fiche prospect
                      </Link>
                    ) : null}
                    {selectedClient ? (
                      <Link className="ghost" href={`/admin/clients/${encodeURIComponent(selectedClient.id)}`}>
                        Ouvrir fiche client
                      </Link>
                    ) : null}
                  </div>
                </article>

                <article className="item">
                  <h4>Contexte famille</h4>
                  <p><strong>Type source:</strong> {sourceTypeLabel} {sourceTypeOrigin !== "inconnu" ? <small className="muted">(base {sourceTypeOrigin})</small> : null}</p>
                  <p><strong>Parent referent:</strong> {resolvedParentReferentName}</p>
                  <p><strong>Email parent:</strong> {resolvedParentReferentEmail}</p>
                  <p><strong>Telephone parent:</strong> {resolvedParentReferentPhone}</p>
                  {selectedClient ? (
                    <p className="top-gap-sm">
                      <strong>Liens famille client:</strong> {familyLinks.length}
                    </p>
                  ) : (
                    <p className="muted top-gap-sm">Aucun client lie au devis pour lire la famille en base.</p>
                  )}
                  {familyLinks.length > 0 ? (
                    <ul className="top-gap-sm">
                      {familyLinks.slice(0, 6).map((row) => (
                        <li key={row.key}>
                          {row.role}: <strong>{row.personName}</strong> ({row.personEmail}){row.billing ? " · destinataire facture" : ""}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </article>
              </div>
            </section>
          </>
        ) : null}

        {activeSection === "interactions" ? (
          <>
            {hasPublicChangeRequest ? (
              <section className="card quote-public-feedback-card">
                <div className="row spread wrap gap-sm">
                  <div>
                    <h3>Demande de modification du client</h3>
                    <p className="muted">Recue le {publicChangeRequestReceivedLabel}. Corrigez le devis puis renvoyez-le au client.</p>
                  </div>
                  <div className="row wrap gap-sm">
                    <Link className="ghost" href={sectionHref("document")}>Traiter dans Envoi</Link>
                    <Link className="ghost" href={sectionHref("pricing")}>Verifier les lignes facturees</Link>
                  </div>
                </div>
                <div className="quote-public-feedback-message top-gap-sm">
                  <strong>Message du client</strong>
                  <p>{publicChangeRequestMessage}</p>
                </div>
              </section>
            ) : null}

            {interactionHistorySection}

            {!hasPublicChangeRequest && !interactionHistorySection ? (
              <section className="card">
                <h3>Interactions client</h3>
                <p className="muted top-gap-sm">Aucune interaction client ou automatisation notable n'a encore ete enregistree pour ce devis.</p>
              </section>
            ) : null}
          </>
        ) : null}

        {activeSection === "document" ? (
          <>

            <section className="card" id="quote-document">
              <h3>Actions</h3>
              <div className="row wrap gap-sm top-gap-sm">
                {canSendQuote || canResendQuote ? (
                  <>
                    <div className="card" style={{ minWidth: 320, flex: "1 1 320px" }}>
                      <h4>{canSendQuote ? `Envoyer au ${primaryRecipientLabel}` : `Renvoyer au ${primaryRecipientLabel}`}</h4>
                      <p className="muted top-gap-sm">
                        {ownerEmail
                          ? `Cette action utilise l'email du ${primaryRecipientLabel} rattache au devis: ${ownerEmail}.`
                          : `Aucun email de ${primaryRecipientLabel} n'est disponible pour ce devis.`}
                      </p>
                      <form
                        id={sendPrimaryFormId}
                        action={canSendQuote ? sendQuoteAction : resendQuoteAction}
                        className="top-gap-sm"
                      >
                        <input type="hidden" name="quote_id" value={detail.quote.id} />
                        <input type="hidden" name="return_to" value={selfPath} />
                        <input type="hidden" name="recipient_email" value={ownerEmail} />
                        <label>
                          Template email
                          <select name="template_ref" defaultValue={defaultSendTemplateRef} disabled={!ownerEmail || quoteSendTemplates.length === 0}>
                            {quoteSendTemplates.map((template) => (
                              <option key={`primary-send-${template.id}`} value={messagingTemplateRef(template)}>
                                {messagingTemplateOptionLabel(template)}
                              </option>
                            ))}
                          </select>
                        </label>
                        {defaultPrimaryPhone ? (
                          <div className="quote-action-sms-group">
                            <label className="checkline quote-action-checkline">
                              <input type="checkbox" name="send_sms" />
                              Envoyer aussi un SMS
                            </label>
                            <label>
                              N° de SMS
                              <input type="text" name="recipient_phone" defaultValue={defaultPrimaryPhone} maxLength={30} />
                            </label>
                            <label>
                              Template SMS
                              <select
                                name="sms_template_ref"
                                defaultValue={defaultSendSmsTemplateRef}
                                disabled={quoteSendSmsTemplates.length === 0}
                              >
                                {quoteSendSmsTemplates.map((template) => (
                                  <option key={`primary-send-sms-${template.id}`} value={messagingTemplateRef(template)}>
                                    {messagingTemplateOptionLabel(template)}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        ) : (
                          <small className="muted top-gap-sm">Aucun numero mobile resolu pour proposer l envoi par SMS.</small>
                        )}
                        <div className="top-gap-sm">
                          <ConfirmSubmitButton
                            formId={sendPrimaryFormId}
                            label={canSendQuote ? `Envoyer au ${primaryRecipientLabel}` : `Renvoyer au ${primaryRecipientLabel}`}
                            title={canSendQuote ? "Confirmer l'envoi du devis ?" : "Confirmer le renvoi du devis ?"}
                            description="Le devis sera envoye par email. Si l'option SMS est cochee, un SMS sera aussi envoye."
                            confirmLabel={canSendQuote ? "Envoyer" : "Renvoyer"}
                            disabled={!ownerEmail}
                          />
                        </div>
                      </form>
                      <small className="muted top-gap-sm">
                        Le contenu est choisi parmi les modeles BO "Envoi / renvoi du devis".
                      </small>
                    </div>

                    <div className="card" style={{ minWidth: 320, flex: "1 1 320px" }}>
                      <h4>{canSendQuote ? "Envoyer a un tiers" : "Renvoyer a un tiers"}</h4>
                      <p className="muted top-gap-sm">
                        Saisissez une autre adresse email pour envoyer ce devis a un tiers.
                      </p>
                      <form
                        id={sendThirdPartyFormId}
                        action={canSendQuote ? sendQuoteAction : resendQuoteAction}
                        className="top-gap-sm"
                      >
                        <input type="hidden" name="quote_id" value={detail.quote.id} />
                        <input type="hidden" name="return_to" value={selfPath} />
                        <label>
                          Destinataire tiers
                          <input
                            type="email"
                            name="recipient_email"
                            placeholder="Email du tiers"
                            defaultValue={defaultThirdPartyEmail}
                            required
                          />
                        </label>
                        <label>
                          Template email
                          <select name="template_ref" defaultValue={defaultSendTemplateRef} disabled={quoteSendTemplates.length === 0}>
                            {quoteSendTemplates.map((template) => (
                              <option key={`third-send-${template.id}`} value={messagingTemplateRef(template)}>
                                {messagingTemplateOptionLabel(template)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <div className="row wrap gap-sm top-gap-sm">
                          <ConfirmSubmitButton
                            formId={sendThirdPartyFormId}
                            label={canSendQuote ? "Envoyer" : "Renvoyer"}
                            title={canSendQuote ? "Confirmer l'envoi au tiers ?" : "Confirmer le renvoi au tiers ?"}
                            description="Le devis sera envoye a l'adresse email tiers renseignee ci-dessus."
                            confirmLabel={canSendQuote ? "Envoyer" : "Renvoyer"}
                          />
                        </div>
                      </form>
                      {lastRecipientEmail ? (
                        <small className="muted top-gap-sm">Dernier destinataire enregistre: {lastRecipientEmail}</small>
                      ) : null}
                      {lastRecipientPhone ? (
                        <small className="muted top-gap-sm">Dernier numero utilise: {lastRecipientPhone}</small>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <small className="muted">
                    Le devis ne peut pas etre envoye ou renvoye dans son statut actuel.
                  </small>
                )}

                {canCancelQuote ? (
                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
                    <h4>Annuler le devis</h4>
                    <p className="muted top-gap-sm">
                      Cette action passe le devis en statut annule. Vous pouvez aussi notifier le destinataire avec un template dedie.
                    </p>
                    <form action={cancelQuoteAction} className="top-gap-sm">
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
                      <label className="checkline">
                        <input type="checkbox" name="notify_recipient" defaultChecked={Boolean(ownerEmail)} />
                        Notifier le destinataire par email
                      </label>
                      <label>
                        Destinataire
                        <input
                          type="email"
                          name="recipient_email"
                          defaultValue={ownerEmail || defaultThirdPartyEmail}
                          placeholder="Email a notifier"
                        />
                      </label>
                      <label>
                        Template d annulation
                        <select name="template_ref" defaultValue={defaultCancelTemplateRef} disabled={quoteCancelTemplates.length === 0}>
                          {quoteCancelTemplates.map((template) => (
                            <option key={`cancel-${template.id}`} value={messagingTemplateRef(template)}>
                              {messagingTemplateOptionLabel(template)}
                            </option>
                          ))}
                        </select>
                      </label>
                      {defaultPrimaryPhone ? (
                        <div className="quote-action-sms-group">
                          <label className="checkline quote-action-checkline">
                            <input type="checkbox" name="notify_recipient_sms" defaultChecked />
                            Notifier aussi par SMS
                          </label>
                          <label>
                            N° de SMS
                            <input type="text" name="recipient_phone" defaultValue={defaultPrimaryPhone} maxLength={30} />
                          </label>
                          <label>
                            Template SMS d annulation
                            <select
                              name="sms_template_ref"
                              defaultValue={defaultCancelSmsTemplateRef}
                              disabled={quoteCancelSmsTemplates.length === 0}
                            >
                              {quoteCancelSmsTemplates.map((template) => (
                                <option key={`cancel-sms-${template.id}`} value={messagingTemplateRef(template)}>
                                  {messagingTemplateOptionLabel(template)}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                      ) : null}
                      <div className="row wrap gap-sm top-gap-sm">
                        <button type="submit" className="danger">
                          Annuler le devis
                        </button>
                      </div>
                    </form>
                  </div>
                ) : null}

                {canRestorePublicResponse ? (
                  <div className="card" style={{ minWidth: 360, flex: "1 1 360px" }}>
                    <h4>Restaurer l etat precedent</h4>
                    <p className="muted top-gap-sm">
                      Utilisez cette action si la reponse publique a ete enregistree par erreur.
                      Aucun email ne sera envoye au prospect.
                    </p>
                    <p className="top-gap-sm">
                      <strong>Statut actuel :</strong> {labelForQuoteStatus(quoteStatus)}<br />
                      <strong>Statut restaure :</strong> {restoreTargetStatusLabel}
                    </p>
                    <form id={restorePublicResponseFormId} action={restoreQuotePublicResponseAction} className="top-gap-sm">
                      <input type="hidden" name="quote_id" value={detail.quote.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
                      <ConfirmSubmitButton
                        formId={restorePublicResponseFormId}
                        label="Restaurer l etat precedent"
                        title="Confirmer la restauration du statut public ?"
                        description={`Le devis repassera de ${labelForQuoteStatus(quoteStatus)} a ${restoreTargetStatusLabel}, sans notification envoyee au prospect.`}
                        confirmLabel="Restaurer"
                        className="ghost"
                      />
                    </form>
                  </div>
                ) : null}

                <form action={duplicateQuoteAction}>
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <button type="submit" className="ghost">Dupliquer en nouvelle version</button>
                </form>

                {detail.quote.public_token ? (
                  <>
                    <a
                      className="ghost"
                      href={detail.quote.public_url ?? `/q/${detail.quote.id}?t=${encodeURIComponent(detail.quote.public_token)}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ouvrir page publique
                    </a>
                    <CopyLinkButton
                      value={detail.quote.public_url ?? `/q/${detail.quote.id}?t=${detail.quote.public_token}`}
                      label="Copier lien public"
                    />
                  </>
                ) : (
                  <small className="muted">Le lien public sera disponible apres envoi.</small>
                )}

                {detail.quote.pdf_token ? (
                  <a
                    className="ghost"
                    href={publicPdfHref || "#"}
                    target="_blank"
                    rel="noreferrer"
                  >
                    PDF public
                  </a>
                ) : null}
                <Link className="ghost" href={adminPdfHref} target="_blank">
                  PDF admin
                </Link>
                <form id={regenerateFormId} action={regenerateQuoteDocumentAction}>
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <ConfirmSubmitButton
                    formId={regenerateFormId}
                    label="Regenerer document"
                    title="Confirmer la regeneration du devis ?"
                    description="Le document devis sera regenere avec les parametres et templates actuellement selectionnes."
                    confirmLabel="Regenerer"
                    className="ghost"
                    disabled={detail.quote.status !== "created"}
                  />
                </form>
                {detail.quote.status !== "created" ? (
                  <small className="muted">Regeneration reservee au brouillon.</small>
                ) : null}
              </div>
            </section>

            <section className="card">
              <details className="modal-details quote-preview-details">
                <summary className="quote-preview-summary">
                  <span>Apercu documentaire (admin)</span>
                  <small className="muted">Audience: admin_preview</small>
                </summary>
                {documentPreview ? (
                  <div className="top-gap-sm">
                    <p className="muted">
                      Hash rendu: <strong>{documentPreview.document_hash}</strong>
                    </p>
                    <div className="grid cols-2 top-gap-sm">
                      <article className="item">
                        <strong>Blocs visibles</strong>
                        {documentPreview.visible_blocks.length === 0 ? (
                          <p className="muted top-gap-sm">Aucun bloc visible.</p>
                        ) : (
                          <ul className="top-gap-sm">
                            {documentPreview.visible_blocks.map((name) => (
                              <li key={`visible-${name}`}>{name}</li>
                            ))}
                          </ul>
                        )}
                      </article>
                      <article className="item">
                        <strong>Blocs masques</strong>
                        {documentPreview.hidden_blocks.length === 0 ? (
                          <p className="muted top-gap-sm">Aucun bloc masque.</p>
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
                      <h4>Apercu devis</h4>
                      <div
                        className="top-gap-sm"
                        dangerouslySetInnerHTML={{ __html: documentPreview.quote_body_html || documentPreview.combined_html }}
                      />
                    </article>
                    <details className="modal-details top-gap-sm">
                      <summary>Conditions generales (CGV)</summary>
                      <article className="item">
                        {documentPreview.terms_html ? (
                          <div dangerouslySetInnerHTML={{ __html: documentPreview.terms_html }} />
                        ) : (
                          <p className="muted">Aucune CGV disponible pour ce devis.</p>
                        )}
                      </article>
                    </details>
                  </div>
                ) : (
                  <p className="muted top-gap-sm">Apercu documentaire indisponible.</p>
                )}
              </details>
            </section>
          </>
        ) : null}

        {activeSection === "cadre" ? (
          <>
            <section className="card" id="quote-cadre">
              <h3>Parametres du devis</h3>
              <p className="muted">Devise, langue, templates, CGV et referentiels metier du devis.</p>
              <form action={updateQuoteSettingsAction} className="grid cols-3 config-form-grid top-gap-sm">
          <input type="hidden" name="quote_id" value={detail.quote.id} />
          <input type="hidden" name="return_to" value={selfPath} />
          <input type="hidden" name="current_meta_json" value={JSON.stringify(detail.quote.meta || {})} />
          <label>
            Type devis
            <select name="quote_type_id" defaultValue={detail.quote.quote_type_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {quoteTypes.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
            {selectedQuoteType ? (
              <small className="muted">
                Defaut type: expiration {selectedQuoteType.default_expiry_days} jours
                {selectedQuoteType.school_year_label ? ` · annee scolaire ${selectedQuoteType.school_year_label}` : ""}
                {selectedQuoteType.formula_name ? ` · formule ${selectedQuoteType.formula_name}` : ""}
              </small>
            ) : null}
          </label>
          <label>
            Catalogue prix
            <select name="pricing_catalog_id" defaultValue={detail.quote.pricing_catalog_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {catalogs.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Plan paiement
            <select name="payment_plan_id" defaultValue={detail.quote.payment_plan_id || ""} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {paymentPlans.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Formule liee (depuis le type de devis)
            <input type="text" value={selectedQuoteType?.formula_name || "-"} readOnly disabled />
            <small className="muted">
              Valeur calculee depuis les parametres deja enregistres. Apres changement du type devis, cliquer sur "Enregistrer parametres".
            </small>
          </label>
          <label>
            Entite legale
            <select
              name="legal_entity_id"
              defaultValue={detail.quote.legal_entity_id || ""}
              disabled={detail.quote.status !== "created"}
            >
              <option value="">Aucune</option>
              {legalEntities.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
            <small className="muted">
              Valeur enregistree sur le devis. Si vous changez, cliquez sur "Enregistrer parametres".
            </small>
          </label>
          <label>
            Modele de devis
            <select name="quote_template_uuid" defaultValue={quoteTemplateId} disabled={detail.quote.status !== "created"}>
              <option value="">Aucun</option>
              {templateOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Modele de CGV
            <select name="terms_template_id" defaultValue={quoteTermsTemplateId} disabled={detail.quote.status !== "created"}>
              <option value="">Conserver snapshot actuel</option>
              {termsOptions.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Langue
            <select name="language" defaultValue={quoteLanguage} disabled={detail.quote.status !== "created"}>
              <option value="fr">Francais</option>
              <option value="en">English</option>
            </select>
          </label>
          <label>
            Devise
            <select name="currency" defaultValue={detail.quote.currency || "EUR"} disabled={detail.quote.status !== "created"}>
              <option value="EUR">EUR</option>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
            </select>
          </label>
          <label>
            Delai expiration (jours)
            <input type="number" name="expiry_days" min={1} max={120} defaultValue={detail.quote.expiry_days} disabled={detail.quote.status !== "created"} />
          </label>
          <label>
            Annee scolaire
            <input type="text" name="school_year_label" defaultValue={detail.quote.school_year_label ?? ""} disabled={detail.quote.status !== "created"} />
          </label>
          <label>
            Ajustement financier
            <select name="financial_adjustment_type" defaultValue={quoteAdjustment.type} disabled={detail.quote.status !== "created"}>
              <option value="none">Aucun</option>
              <option value="credit">Avoir</option>
              <option value="debt">Dette</option>
            </select>
          </label>
          <label>
            Option Pass Recup
            <select name="pass_recup_mode" defaultValue={passRecupMode} disabled={detail.quote.status !== "created"}>
              <option value="auto">Automatique (selon lignes devis)</option>
              <option value="enabled">Souscrite</option>
              <option value="disabled">Non souscrite</option>
            </select>
          </label>
          <label>
            Acompte preinscription
            <select
              name="pre_registration_deposit_enabled"
              defaultValue={quoteDeposit.enabled ? "yes" : "no"}
              disabled={detail.quote.status !== "created"}
            >
              <option value="no">Non</option>
              <option value="yes">Oui</option>
            </select>
          </label>
          <label>
            Montant ajustement TTC
            <input
              type="number"
              name="financial_adjustment_amount_ttc"
              min={0}
              step="0.01"
              defaultValue={quoteAdjustment.type === "none" ? "" : quoteAdjustment.amountTtc.toFixed(2)}
              placeholder="100.00"
              disabled={detail.quote.status !== "created"}
            />
          </label>
          <label>
            Montant acompte TTC
            <input
              type="number"
              name="pre_registration_deposit_amount_ttc"
              min={0}
              step="0.01"
              defaultValue={quoteDeposit.amountTtc.toFixed(2)}
              placeholder="200.00"
              disabled={detail.quote.status !== "created"}
            />
            <small className="muted">Par defaut: 200,00 EUR.</small>
          </label>
          <label>
            Date ajustement
            <input
              type="date"
              name="financial_adjustment_effective_date"
              defaultValue={quoteAdjustment.effectiveDate}
              disabled={detail.quote.status !== "created"}
            />
          </label>
          <label className="span-3">
            Libelle ajustement (optionnel)
            <input
              type="text"
              name="financial_adjustment_label"
              defaultValue={quoteAdjustment.label}
              placeholder="Ex: Avoir fidelite septembre"
              disabled={detail.quote.status !== "created"}
            />
          </label>
                <div className="row span-3 top-gap-sm">
                  <button type="submit" disabled={detail.quote.status !== "created"}>Enregistrer parametres</button>
                  {detail.quote.status !== "created" ? <small className="muted">Le devis est immuable apres envoi.</small> : null}
                </div>
              </form>
              <p className="muted top-gap-sm">
                Ajustement courant: <strong>{adjustmentTypeLabel(quoteAdjustment.type)}</strong>
                {quoteAdjustment.type !== "none" ? (
                  <>
                    {" · "}
                    <strong>{formatAmount(String(quoteAdjustment.amountTtc), detail.quote.currency)}</strong>
                    {quoteAdjustment.effectiveDate ? <> · Date: <strong>{quoteAdjustment.effectiveDate}</strong></> : null}
                    {quoteAdjustment.label ? <> · Libelle: <strong>{quoteAdjustment.label}</strong></> : null}
                  </>
                ) : null}
              </p>
              <p className="muted">
                Acompte preinscription: <strong>{quoteDeposit.enabled ? "Oui" : "Non"}</strong>
                {quoteDeposit.enabled ? (
                  <>
                    {" · "}
                    <strong>{formatAmount(String(quoteDeposit.amountTtc), detail.quote.currency)}</strong>
                  </>
                ) : null}
              </p>
              {totalBeforeAdjustment !== null ? (
                <p className="muted">
                  Total lignes avant ajustement: <strong>{formatAmount(String(totalBeforeAdjustment), detail.quote.currency)}</strong>
                  {" · "}
                  Total facture apres ajustement: <strong>{formatAmount(detail.quote.total_ttc, detail.quote.currency)}</strong>
                </p>
              ) : null}
              <p className="muted top-gap-sm">
                CGV snapshot active: <strong>{String(detail.quote.cgv_snapshot?.version_label || "-")}</strong>
              </p>
              <p className="muted">
                Templates affiches pour la langue: <strong>{quoteLanguage.toUpperCase()}</strong>
              </p>
              <p className="muted">
                Statut document: <strong>{detail.quote.document_status || "stale"}</strong>
                {" · "}
                Genere le: <strong>{formatDate(detail.quote.document_generated_at)}</strong>
              </p>
              <p className="muted">
                Hash document: <strong>{detail.quote.document_hash || "-"}</strong>
              </p>
            </section>

            <section className="card">
              <h3>Infos devis</h3>
              <div className="grid cols-3 top-gap-sm">
                <p><strong>Type:</strong> {detail.quote.quote_type}</p>
                <p><strong>Annee scolaire:</strong> {detail.quote.school_year_label ?? "-"}</p>
                <p><strong>Creation:</strong> {formatDate(detail.quote.created_at)}</p>
                <p><strong>Envoi:</strong> {formatDate(detail.quote.sent_at)}</p>
                <p><strong>Expiration:</strong> {formatDate(detail.quote.expires_at)}</p>
                <p><strong>Options pedagogiques:</strong> Gerees via les activites du planning</p>
                {selectedQuoteType?.formula_name ? <p><strong>Formule type devis:</strong> {selectedQuoteType.formula_name}</p> : null}
              </div>
            </section>
          </>
        ) : null}

        {activeSection === "planning" ? (
          <section className="card quote-workstream-card quote-workstream-card-planning" id="quote-planning">
        <div className="quote-workstream-head">
          <span className="quote-workstream-badge quote-workstream-badge-planning">Bloc 1 · Construction pedagogique</span>
          <h3>Planning des cours</h3>
          <p className="muted">Quoi, ou, quand. {planningBlocks.length} activite(s) configuree(s) et {calendarSessions.length} seance(s) calculee(s).</p>
        </div>
        <div className="top-gap-sm">
          <QuotePlanningEditor
            quoteId={detail.quote.id}
            returnTo={selfPath}
            editable={detail.quote.status === "created"}
            schoolYearLabel={detail.quote.school_year_label}
            activities={activities.map((row) => ({
              id: row.id,
              name: row.name,
              code: row.code,
              service_code: row.service_code,
              duration_minutes: row.duration_minutes,
              exclude_holidays_in_recurrence: row.exclude_holidays_in_recurrence,
              exclude_school_vacations_in_recurrence: row.exclude_school_vacations_in_recurrence,
            }))}
            locations={locations.map((row) => ({
              id: row.id,
              name: row.name,
            }))}
            solfegeRules={solfegeRules.map((row) => ({
              id: row.id,
              level_code: row.level_code,
              duration_minutes: row.duration_minutes,
              allowed_weekdays: row.allowed_weekdays,
              allowed_time_slots: row.allowed_time_slots,
              location_id: row.location_id,
              modality: row.modality,
            }))}
            initialSnapshot={detail.quote.calendar_snapshot}
            initialMeta={detail.quote.meta || {}}
            saveAction={updateQuotePlanningAction}
          />
        </div>
          </section>
        ) : null}

        {activeSection === "pricing" ? (
          <section className="card quote-workstream-card quote-workstream-card-pricing" id="quote-pricing">
        <div className="quote-workstream-head">
          <span className="quote-workstream-badge quote-workstream-badge-pricing">Bloc 2 · Construction commerciale</span>
          <h3>Lignes facturees</h3>
          <p className="muted">Ce qui sera facture. {detail.lines.length} ligne(s) actuellement enregistree(s).</p>
        </div>
        <QuoteLinesEditor
          quoteId={detail.quote.id}
          returnTo={selfPath}
          editable={detail.quote.status === "created"}
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
          activityCatalogPriceByActivityId={activityCatalogPriceByActivityId}
          productCatalogPriceByProductId={productCatalogPriceByProductId}
          kitCatalogPriceByKitId={kitCatalogPriceByKitId}
          planningByActivityId={planningByActivityId}
          defaultVatRate={defaultVatRate}
          saveAction={updateQuoteLinesAction}
        />
          </section>
        ) : null}

        {activeSection === "integration" ? (
          <>
            {followupTransformationExecutionStatus ? (
              <section className="card">
                <h3>Execution de la transformation</h3>
                <p className="muted">
                  Statut technique:{" "}
                  <strong>
                    {followupTransformationExecutionStatus === "executed"
                      ? "integree"
                      : followupTransformationExecutionStatus === "rolled_back"
                      ? "rollback effectue"
                      : followupTransformationExecutionStatus === "failed"
                      ? "echec bloquant"
                      : followupTransformationExecutionStatus}
                  </strong>
                  {followupTransformationExecution?.executed_at
                    ? ` · Executee le ${formatDate(String(followupTransformationExecution.executed_at))}`
                    : null}
                  {followupTransformationExecution?.rolled_back_at
                    ? ` · Rollback le ${formatDate(String(followupTransformationExecution.rolled_back_at))}`
                    : null}
                </p>
                <div className="quote-quick-transform-summary top-gap-sm">
                  <p><strong>Bookings crees:</strong> {transformationExecutionSummary.bookings}</p>
                  <p><strong>Charges crees:</strong> {transformationExecutionSummary.transactions}</p>
                  <p><strong>Abonnements crees:</strong> {transformationExecutionSummary.subscriptions}</p>
                  <p><strong>Clients crees:</strong> {transformationExecutionSummary.users}</p>
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
                      <strong>Detail technique :</strong> {followupTransformationFailureUi.technicalMessage}
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
                      label="Rollback de la transformation"
                      title="Confirmer le rollback de l'integration ?"
                      description="Les bookings, abonnements et charges crees par cette transformation seront supprimes et le devis reviendra a son etat precedent. Aucun email ne sera envoye au prospect."
                      confirmLabel="Restaurer l'etat precedent"
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
            />

            <section className="card">
              <h3>Transformation vers inscription (wizard complet)</h3>
              <p className="muted">Parcours detaille en 5 etapes avec controles et arbitrages manuels.</p>
              <div className="row wrap gap-sm top-gap-sm">
                <Link className="ghost" href={transformBasePath}>Transformer en inscription</Link>
                <Link className="ghost" href={`${transformBasePath}&scenario=A`}>Scenario A (simple)</Link>
                <Link className="ghost" href={`${transformBasePath}&scenario=B`}>Scenario B (ambigu)</Link>
                <Link className="ghost" href={`${transformBasePath}&scenario=C`}>Scenario C (bloquant)</Link>
              </div>
            </section>

            <section id="quote-validation-integration">
              <QuoteValidationIntegrationSection
                validationRows={validationRows}
                projectionCard={<QuoteIntegrationProjectionCard rows={projectionRows} />}
                clientMatchCard={(
                  <QuoteClientMatchCard
                    status={clientMatchStatus}
                    detail={
                      clientMatchStatus === "deja_lie"
                        ? "Le devis est deja relie a un client."
                        : clientMatchStatus === "multiple"
                        ? "Plusieurs correspondances detectees, verification manuelle necessaire."
                        : clientMatchStatus === "probable"
                        ? "Une correspondance probable a ete detectee."
                        : "Aucune correspondance client detectee pour le moment."
                    }
                  />
                )}
                integrationResultCard={<QuoteIntegrationResultCard rows={integrationResultRows} />}
                note="Le wizard de transformation est actif via le bouton ci-dessus. Ce panneau conserve la synthese des controles d'integration."
              />
            </section>

            <section className="card">
              <h3>Parcours post-approbation</h3>
              {activeFollowup ? (
                <>
                  <p className="muted">
                    Statut follow-up: <strong>{activeFollowup.status}</strong> · Paiement: <strong>{activeFollowup.payment_method_status}</strong> · Solfege: <strong>{activeFollowup.solfege_slot_status}</strong>
                  </p>

                  <div className="grid cols-2 top-gap-sm">
                    <QuoteFollowupSlotForm
                      followupId={activeFollowup.id}
                      returnTo={selfPath}
                      solfegeRules={solfegeRules}
                      initialLevelCode={followupLevelCode}
                      initialSelectedSlot={followupSelectedSlot}
                      submitAction={selectQuoteFollowupSlotAction}
                    />

                    <form id={`followup-payment-form-${activeFollowup.id}`} action={changeQuoteFollowupPaymentMethodAction} className="card quote-followup-form">
                      <h4>Changer le mode de paiement</h4>
                      <input type="hidden" name="followup_id" value={activeFollowup.id} />
                      <input type="hidden" name="return_to" value={selfPath} />
                      <label>
                        Methode
                        <select name="payment_method_code" defaultValue={followupMethodDefaultCode} required>
                          <option value="">Selectionner</option>
                          {Array.from(paymentMethodOptionsByCode.values()).map((item) => (
                            <option key={item.code} value={item.code}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                        <small className="muted">Liste issue des plans de paiement configures.</small>
                      </label>
                      <label>
                        Plan de paiement (optionnel)
                        <select name="payment_plan_id" defaultValue={followupPaymentPlanId}>
                          <option value="">Aucun</option>
                          {paymentPlans.map((row) => (
                            <option key={row.id} value={row.id}>{row.name} ({paymentMethodLabel(row.payment_method)})</option>
                          ))}
                        </select>
                      </label>
                      <ConfirmSubmitButton
                        formId={`followup-payment-form-${activeFollowup.id}`}
                        label="Mettre a jour paiement"
                        title="Confirmer la mise a jour du paiement ?"
                        description="Le mode de paiement et le plan selectionne seront appliques au devis."
                        confirmLabel="Mettre a jour"
                      />
                    </form>
                  </div>

                  <form id={`followup-finalize-form-${activeFollowup.id}`} action={finalizeQuoteFollowupAction} className="row top-gap-sm">
                    <input type="hidden" name="followup_id" value={activeFollowup.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
                    <ConfirmSubmitButton
                      formId={`followup-finalize-form-${activeFollowup.id}`}
                      label={followupTransformationPayload ? "Executer la transformation maintenant" : "Finaliser le parcours post-approbation"}
                      title={followupTransformationPayload ? "Confirmer l'execution reelle de la transformation ?" : "Confirmer la finalisation du parcours post-approbation ?"}
                      description={followupTransformationPayload
                        ? "Le systeme reverifiera la capacite des creneaux, creera les bookings et les charges hors planning, puis mettra a jour le client. Un rollback admin restera possible ensuite."
                        : "Le follow-up passera en statut complete. Le paiement et le creneau seront valides selon leur etat actuel."}
                      confirmLabel={followupTransformationPayload ? "Executer la transformation" : "Finaliser"}
                    />
                  </form>
                </>
              ) : (
                <p className="muted">Aucun follow-up actif pour ce devis. Il sera cree automatiquement apres approbation du devis.</p>
              )}
            </section>

            <section className="card">
              <h3>Echeancier snapshot</h3>
              <div className="quote-public-lines top-gap-sm">
                {getScheduleItems(detail.quote.payment_terms_snapshot).length === 0 ? (
                  <p className="muted">Aucun echeancier.</p>
                ) : (
                  getScheduleItems(detail.quote.payment_terms_snapshot).map((item, index) => (
                    <article key={`schedule-${index}`} className="quote-public-line-item">
                      <strong>{String(item.label ?? `Echeance ${index + 1}`)}</strong>
                      <span>{formatScheduleDueLabel(item)}</span>
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
