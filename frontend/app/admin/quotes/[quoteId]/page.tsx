import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ConfirmSubmitButton from "../../../../components/confirm-submit-button";
import CopyLinkButton from "../../../../components/copy-link-button";
import QuoteClientMatchCard from "../../../../components/quotes/quote-client-match-card";
import QuoteIntegrationProjectionCard from "../../../../components/quotes/quote-integration-projection-card";
import QuoteIntegrationResultCard from "../../../../components/quotes/quote-integration-result-card";
import QuoteOverviewSection from "../../../../components/quotes/quote-overview-section";
import QuoteRightSummaryRail from "../../../../components/quotes/quote-right-summary-rail";
import type { QuoteIntegrationUiState } from "../../../../components/quotes/quote-row-integration-state";
import type { QuoteValidationUiState } from "../../../../components/quotes/quote-row-validation-state";
import QuoteValidationIntegrationSection from "../../../../components/quotes/quote-validation-integration-section";
import QuoteWorkspaceHeader from "../../../../components/quotes/quote-workspace-header";
import QuoteWorkspaceShell from "../../../../components/quotes/quote-workspace-shell";
import QuoteWorkspaceSidebar from "../../../../components/quotes/quote-workspace-sidebar";
import QuoteFollowupSlotForm from "../../../../components/quote-followup-slot-form";
import QuoteLinesEditor from "../../../../components/quote-lines-editor";
import QuotePlanningEditor from "../../../../components/quote-planning-editor";
import {
  changeQuoteFollowupPaymentMethodAction,
  duplicateQuoteAction,
  finalizeQuoteFollowupAction,
  regenerateQuoteDocumentAction,
  selectQuoteFollowupSlotAction,
  sendQuoteAction,
  updateQuoteLinesAction,
  updateQuotePlanningAction,
  updateQuoteSettingsAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type {
  AdminActivityOut,
  AdminCatalogKitOut,
  AdminCatalogProductOut,
  AdminClientOut,
  AdminLegalEntityOut,
  LocationOut,
} from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type QuoteWorkspaceSection = "overview" | "cadre" | "planning" | "pricing" | "document" | "integration";

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
};

type QuoteDetailOut = {
  quote: QuoteOut;
  lines: QuoteLineOut[];
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
    || normalized === "integration"
  ) {
    return normalized;
  }
  return "overview";
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

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
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
  if (status === "change_requested") return "incomplet";
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
  if (state === "valide") return "Valide";
  if (state === "refuse") return "Refuse";
  return "Expire";
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
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");

  const [detailResult, followupsResult, paymentPlansResult, quoteTypesResult, legalEntitiesResult, catalogsResult, termsTemplatesResult, quoteTemplatesResult, activitiesResult, productsResult, kitsResult, locationsResult, solfegeRulesResult, prospectsResult, clientsResult, documentPreviewResult] = await Promise.all([
    backendRequest<QuoteDetailOut>(`/api/v1/quotes/${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<QuoteFollowupOut[]>(`/api/v1/quote-followups?quote_id=${encodeURIComponent(quoteId)}`, {}, token),
    backendRequest<PaymentPlanOut[]>("/api/v1/payment-plans", {}, token),
    backendRequest<QuoteTypeOut[]>("/api/v1/quote-types", {}, token),
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
  const activityPrices = activityPricesResult?.ok ? activityPricesResult.data : [];
  const productPrices = productPricesResult?.ok ? productPricesResult.data : [];
  const kitPrices = kitPricesResult?.ok ? kitPricesResult.data : [];

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
  const owner = detail.quote.context_type === "acquisition"
    ? prospectById.get(detail.quote.prospect_id || "")
    : clientById.get(detail.quote.client_id || "");

  const ownerName = owner
    ? displayName(owner.first_name, owner.last_name, owner.email)
    : "-";
  const quoteLanguage = readStringMeta(detail.quote.meta || {}, "language", "fr").toLowerCase();
  const quoteTemplateId = detail.quote.quote_template_id || readStringMeta(detail.quote.meta || {}, "quote_template_uuid");
  const quoteTermsTemplateId = detail.quote.terms_template_id || readStringMeta(detail.quote.meta || {}, "terms_template_id");
  const calendarSessions = getCalendarSessions(detail.quote.calendar_snapshot || {});
  const planningBlocks = getPlanningBlocks(detail.quote.calendar_snapshot || {});
  const planningSummary = planningVisualSummary(calendarSessions);
  const followupPayload = readObject(activeFollowup?.payload);
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
  const publicPdfHref = detail.quote.pdf_token
    ? `/q/${detail.quote.id}/pdf?t=${encodeURIComponent(detail.quote.pdf_token)}${pdfVersionTag ? `&v=${encodeURIComponent(pdfVersionTag)}` : ""}`
    : null;
  const regenerateFormId = `quote-regenerate-form-${detail.quote.id}`;

  const quoteBasePath = `/admin/quotes/${encodeURIComponent(detail.quote.id)}`;
  const sectionHref = (section: QuoteWorkspaceSection): string =>
    `${quoteBasePath}?back=${encodeURIComponent(backPath)}&section=${section}`;
  const selfPath = sectionHref(activeSection);
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
    integrationAlerts.push("Erreur d'integration detectee.");
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
  const sidebarItems = [
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
    { id: "document", label: "Document et envoi", href: sectionHref("document"), active: activeSection === "document" },
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
              { label: "Validation client", value: detail.quote.approved_at ? "Valide" : "En attente" },
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
              { label: "Validation client", value: detail.quote.approved_at ? formatDate(detail.quote.approved_at) : "En attente" },
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
          <QuoteOverviewSection
            cards={[
              { label: "Statut devis", value: commercialStateLabel(commercialState) },
              { label: "Statut document", value: detail.quote.document_status || "stale" },
              { label: "Validation client", value: detail.quote.approved_at ? formatDate(detail.quote.approved_at) : "En attente" },
              { label: "Integration centrale", value: integrationStateLabel(integrationState) },
              { label: "Total TTC", value: formatAmount(detail.quote.total_ttc, detail.quote.currency) },
              { label: "Expiration", value: formatDate(detail.quote.expires_at) },
            ]}
            alerts={integrationAlerts.map((message) => ({ level: message.toLowerCase().includes("erreur") ? "error" : "warn", message }))}
            quickActions={(
              <>
                <Link className="ghost" href={sectionHref("document")}>Document et envoi</Link>
                <Link className="ghost" href={sectionHref("planning")}>Activites planifiees</Link>
                <Link className="ghost" href={sectionHref("pricing")}>Lignes facturees</Link>
                <Link className="ghost" href={sectionHref("integration")}>Validation et integration</Link>
              </>
            )}
          />
        ) : null}

        {activeSection === "document" ? (
          <>
            <section className="card" id="quote-document">
              <h3>Actions</h3>
              <div className="row wrap gap-sm top-gap-sm">
                {detail.quote.status === "created" ? (
                  <form action={sendQuoteAction} className="row wrap gap-sm">
                    <input type="hidden" name="quote_id" value={detail.quote.id} />
                    <input type="hidden" name="return_to" value={selfPath} />
                    <input type="email" name="recipient_email" placeholder="Email destinataire (optionnel)" />
                    <button type="submit">Envoyer le devis</button>
                  </form>
                ) : null}

                <form action={duplicateQuoteAction}>
                  <input type="hidden" name="quote_id" value={detail.quote.id} />
                  <input type="hidden" name="return_to" value={selfPath} />
                  <button type="submit" className="ghost">Dupliquer en nouvelle version</button>
                </form>

                {detail.quote.public_token ? (
                  <>
                    <Link
                      className="ghost"
                      href={`/q/${detail.quote.id}?t=${encodeURIComponent(detail.quote.public_token)}`}
                      target="_blank"
                    >
                      Ouvrir page publique
                    </Link>
                    <CopyLinkButton
                      value={`${process.env.NEXT_PUBLIC_FRONTEND_URL ?? "http://localhost:3000"}/q/${detail.quote.id}?t=${detail.quote.public_token}`}
                      label="Copier lien public"
                    />
                  </>
                ) : (
                  <small className="muted">Le lien public sera disponible apres envoi.</small>
                )}

                {detail.quote.pdf_token ? (
                  <Link
                    className="ghost"
                    href={publicPdfHref || "#"}
                    target="_blank"
                  >
                    PDF public
                  </Link>
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
            Entite legale
            <select
              name="legal_entity_id"
              defaultValue={detail.quote.legal_entity_id || legalEntities[0]?.id || ""}
              disabled={detail.quote.status !== "created"}
            >
              <option value="">Aucune</option>
              {legalEntities.map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </select>
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
          defaultVatRate={defaultVatRate}
          saveAction={updateQuoteLinesAction}
        />
          </section>
        ) : null}

        {activeSection === "integration" ? (
          <>
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
                note="Placeholder UI active: l'integration reelle vers l'application centrale sera branchee dans une etape ulterieure."
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
                      label="Finaliser le parcours post-approbation"
                      title="Confirmer la finalisation du parcours post-approbation ?"
                      description="Le follow-up passera en statut complete. Le paiement et le creneau seront valides selon leur etat actuel."
                      confirmLabel="Finaliser"
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
