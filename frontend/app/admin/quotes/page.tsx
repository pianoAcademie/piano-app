import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import CopyLinkButton from "../../../components/copy-link-button";
import QuoteListPageRefine from "../../../components/quotes/quote-list-page-refine";
import QuoteRowIntegrationState, { type QuoteIntegrationUiState } from "../../../components/quotes/quote-row-integration-state";
import QuoteRowNextAction, { type QuoteNextAction } from "../../../components/quotes/quote-row-next-action";
import QuoteRowValidationState, { type QuoteValidationUiState } from "../../../components/quotes/quote-row-validation-state";
import { duplicateQuoteAction, sendQuoteAction } from "../../../lib/actions";
import { backendRequest } from "../../../lib/backend";
import { hasAdminPermission } from "../../../lib/admin-access";
import type { AdminActivityOut, AdminClientOut, UserOut } from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import { resolveUiFlashMessage, withUiLanguage } from "../../../lib/ui-messages";

type SearchParams = Record<string, string | string[] | undefined>;

type ProspectOut = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  meta: Record<string, unknown>;
};

type QuoteOut = {
  id: string;
  quote_number: string;
  status: string;
  public_token: string | null;
  pdf_token: string | null;
  public_url: string | null;
  public_pdf_url: string | null;
  context_type: string;
  currency: string;
  total_ttc: string;
  created_at: string;
  expires_at: string | null;
  quote_type: string;
  prospect_id: string | null;
  client_id: string | null;
  school_year_label: string | null;
  estimated_solfege_level: string | null;
  calendar_snapshot: Record<string, unknown>;
  cgv_snapshot: Record<string, unknown>;
  meta: Record<string, unknown>;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function formatDate(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString(localeForUiLanguage(language), { dateStyle: "short", timeStyle: "short" });
}

function formatAmount(value: string, currency: string, language: UiLanguage): string {
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

function labelForContext(contextType: string, language: UiLanguage): string {
  return contextType === "active_client"
    ? uiText(language, "admin.quotes.context_active_client")
    : uiText(language, "admin.quotes.context_acquisition");
}

function displayName(firstName: string | null, lastName: string | null, fallback: string): string {
  const value = [firstName, lastName].filter(Boolean).join(" ").trim();
  return value || fallback;
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

function getCalendarSessionsCount(snapshot: Record<string, unknown>): number {
  const raw = snapshot.sessions;
  if (!Array.isArray(raw)) {
    return 0;
  }
  return raw.length;
}

function normalizeLocationSignal(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function snapshotRows(snapshot: Record<string, unknown>): Array<Record<string, unknown>> {
  const blocks = Array.isArray(snapshot.blocks) ? snapshot.blocks : [];
  const sessions = Array.isArray(snapshot.sessions) ? snapshot.sessions : [];
  return [...blocks, ...sessions].filter(
    (row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row),
  );
}

function quotePotentialLocation(row: QuoteOut): "paris" | "bar_le_duc" {
  const rows = snapshotRows(row.calendar_snapshot || {});
  const hasBarLeDucPhysicalBlock = rows.some((item) => {
    const haystack = normalizeLocationSignal([
      item.location_label,
      item.location_name,
      item.location,
      item.location_code,
      item.location_id,
      item.modality,
      item.mode,
      item.activity_label,
      item.activity_name,
      item.title,
    ].join(" "));
    const isOnline = haystack.includes("online") || haystack.includes("en ligne") || haystack.includes("ligne");
    const isBarLeDuc = haystack.includes("bar-le-duc") || haystack.includes("bar le duc") || haystack.includes("bar_le_duc");
    return isBarLeDuc && !isOnline;
  });
  return hasBarLeDucPhysicalBlock ? "bar_le_duc" : "paris";
}

function isPotentialEnrollmentState(state: QuoteValidationUiState): boolean {
  return (
    state === "incomplet"
    || state === "brouillon"
    || state === "pret_a_envoyer"
    || state === "envoye"
    || state === "consulte"
    || state === "modification_demandee"
    || state === "valide"
  );
}

function parseIsoDateOnly(raw: string): Date | null {
  const value = raw.trim();
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function parseDecimal(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function languageLabel(meta: Record<string, unknown>): string {
  const language = typeof meta.language === "string" ? meta.language.trim().toLowerCase() : "";
  return language || "fr";
}

function templateLabel(meta: Record<string, unknown>): string {
  const options = [meta.template_name, meta.template_code, meta.template_id];
  for (const candidate of options) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return "-";
}

function cgvLabel(snapshot: Record<string, unknown>): string {
  const label = snapshot.version_label;
  if (typeof label === "string" && label.trim()) {
    return label.trim();
  }
  return "-";
}

function readStringMeta(meta: Record<string, unknown>, key: string, fallback = ""): string {
  const value = meta[key];
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function prospectTypeLabelFromMeta(meta: Record<string, unknown>): "adult" | "child" | "-" {
  const value = typeof meta.prospect_type === "string" ? meta.prospect_type.trim().toLowerCase() : "";
  if (value === "adult" || value === "child") {
    return value;
  }
  return "-";
}

function prospectTypeLabelFromClient(client: AdminClientOut | undefined): "adult" | "child" | "-" {
  if (!client) {
    return "-";
  }
  const value = String(client.client_kind || "").trim().toUpperCase();
  if (value === "ADULT") {
    return "adult";
  }
  if (value === "CHILD") {
    return "child";
  }
  return "-";
}

function quoteValidationState(row: QuoteOut): QuoteValidationUiState {
  const status = String(row.status || "").trim().toLowerCase();
  const meta = row.meta || {};
  const publicResponseLastAction = readStringMeta(meta, "public_response_last_action", "").toLowerCase();
  if (status === "approved") {
    return "valide";
  }
  if (status === "rejected" || status === "cancelled") {
    return "refuse";
  }
  if (status === "expired") {
    return "expire";
  }
  if (status === "sent") {
    const viewed = ["public_viewed_at", "viewed_at", "consulted_at", "last_viewed_at"].some((key) => {
      const value = meta[key];
      return typeof value === "string" && value.trim().length > 0;
    });
    return viewed ? "consulte" : "envoye";
  }
  if (status === "change_requested" || publicResponseLastAction === "change_requested") {
    return "modification_demandee";
  }
  if (status === "created") {
    const hasOwner = Boolean(row.prospect_id || row.client_id);
    const hasTemplate = templateLabel(meta) !== "-";
    const total = Number(row.total_ttc);
    const hasAmount = Number.isFinite(total) ? Math.abs(total) > 0 : String(row.total_ttc || "").trim().length > 0;
    if (hasOwner && hasTemplate && hasAmount) {
      return "pret_a_envoyer";
    }
    if (!hasOwner || !hasTemplate) {
      return "incomplet";
    }
    return "brouillon";
  }
  return "incomplet";
}

function quoteIntegrationState(row: QuoteOut, commercialState: QuoteValidationUiState): QuoteIntegrationUiState {
  const meta = row.meta || {};
  if (readStringMeta(meta, "change_request_revision_quote_id", "")) {
    return "non_concerne";
  }
  if (commercialState === "refuse" || commercialState === "expire") {
    return "non_concerne";
  }
  if (commercialState !== "valide") {
    return "en_attente_validation_client";
  }
  const raw = String(meta.integration_status ?? meta.central_integration_status ?? "").trim().toLowerCase();
  if (raw === "a_preparer" || raw === "to_prepare") return "a_preparer";
  if (raw === "a_verifier" || raw === "to_check") return "a_verifier";
  if (raw === "pret_a_integrer" || raw === "ready_to_integrate") return "pret_a_integrer";
  if (raw === "integre" || raw === "integrated") return "integre";
  if (raw === "erreur_integration" || raw === "integration_error") return "erreur_integration";
  const hasError = Boolean(meta.integration_error) || String(meta.integration_error_message ?? "").trim().length > 0;
  if (hasError) {
    return "erreur_integration";
  }
  const integratedAt = String(meta.integration_completed_at ?? "").trim();
  if (integratedAt) {
    return "integre";
  }
  const matchStatus = String(meta.client_match_status ?? "").trim().toLowerCase();
  if (matchStatus === "multiple" || matchStatus === "ambiguous") {
    return "a_verifier";
  }
  const ready = Boolean(meta.integration_ready) || String(meta.integration_ready ?? "").trim().toLowerCase() === "true";
  if (ready) {
    return "pret_a_integrer";
  }
  return "a_preparer";
}

function quoteNextAction(
  commercialState: QuoteValidationUiState,
  integrationState: QuoteIntegrationUiState,
): QuoteNextAction {
  if (commercialState === "brouillon" || commercialState === "incomplet") {
    return "completer_le_devis";
  }
  if (commercialState === "pret_a_envoyer") {
    return "envoyer";
  }
  if (commercialState === "modification_demandee") {
    return "traiter_demande_client";
  }
  if (commercialState === "envoye" || commercialState === "consulte") {
    return "relancer";
  }
  if (commercialState === "valide") {
    if (integrationState === "a_preparer") return "preparer_integration";
    if (integrationState === "a_verifier" || integrationState === "erreur_integration") return "verifier_correspondance_client";
    if (integrationState === "pret_a_integrer") return "integrer_dans_centrale";
  }
  return "aucune_action";
}

function matchesCommercialStatusFilter(row: QuoteOut, filter: string): boolean {
  const normalized = filter.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const commercialState = quoteValidationState(row);
  if (normalized === commercialState) {
    return true;
  }
  if (normalized === "created") {
    return commercialState === "incomplet" || commercialState === "brouillon" || commercialState === "pret_a_envoyer";
  }
  if (normalized === "sent") {
    return commercialState === "envoye" || commercialState === "consulte";
  }
  if (normalized === "change_requested") {
    return commercialState === "modification_demandee";
  }
  if (normalized === "approved") {
    return commercialState === "valide";
  }
  if (normalized === "rejected" || normalized === "cancelled") {
    return commercialState === "refuse";
  }
  if (normalized === "expired") {
    return commercialState === "expire";
  }
  return false;
}

function quoteChangeRequestSummary(row: QuoteOut): { message: string; at: string } | null {
  const meta = row.meta || {};
  const publicResponseLastAction = readStringMeta(meta, "public_response_last_action", "").toLowerCase();
  const status = String(row.status || "").trim().toLowerCase();
  if (status !== "change_requested" && publicResponseLastAction !== "change_requested") {
    return null;
  }
  return {
    message: readStringMeta(meta, "public_response_last_message", ""),
    at: readStringMeta(meta, "public_response_last_at", ""),
  };
}

function quoteChangeRequestRevision(row: QuoteOut): { id: string; number: string } | null {
  const meta = row.meta || {};
  const id = readStringMeta(meta, "change_request_revision_quote_id", "");
  if (!id) {
    return null;
  }
  return {
    id,
    number: readStringMeta(meta, "change_request_revision_quote_number", ""),
  };
}

function buildQuotesListHref(params: {
  status: string;
  contextType: string;
  activityId: string;
  q: string;
  prospectType: string;
  currency: string;
  quoteType: string;
  schoolYear: string;
  language: string;
  template: string;
  cgv: string;
  hasSolfege: string;
  workflowFilter: string;
  minTotal: string;
  maxTotal: string;
  createdFrom: string;
  createdTo: string;
  expiresFrom: string;
  expiresTo: string;
}): string {
  const sp = new URLSearchParams();
  if (params.status) sp.set("status", params.status);
  if (params.contextType) sp.set("context_type", params.contextType);
  if (params.activityId) sp.set("activity_id", params.activityId);
  if (params.q) sp.set("q", params.q);
  if (params.prospectType) sp.set("prospect_type", params.prospectType);
  if (params.currency) sp.set("currency", params.currency);
  if (params.quoteType) sp.set("quote_type", params.quoteType);
  if (params.schoolYear) sp.set("school_year", params.schoolYear);
  if (params.language) sp.set("language", params.language);
  if (params.template) sp.set("template", params.template);
  if (params.cgv) sp.set("cgv", params.cgv);
  if (params.hasSolfege) sp.set("has_solfege", params.hasSolfege);
  if (params.workflowFilter) sp.set("workflow_filter", params.workflowFilter);
  if (params.minTotal) sp.set("min_total", params.minTotal);
  if (params.maxTotal) sp.set("max_total", params.maxTotal);
  if (params.createdFrom) sp.set("created_from", params.createdFrom);
  if (params.createdTo) sp.set("created_to", params.createdTo);
  if (params.expiresFrom) sp.set("expires_from", params.expiresFrom);
  if (params.expiresTo) sp.set("expires_to", params.expiresTo);
  const value = sp.toString();
  return value ? `/admin/quotes?${value}` : "/admin/quotes";
}

export default async function AdminQuotesPage({ searchParams }: { searchParams: SearchParams }): Promise<JSX.Element> {
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

  const statusFilter = readParam(searchParams, "status");
  const contextFilter = readParam(searchParams, "context_type");
  const activityFilter = readParam(searchParams, "activity_id");
  const query = readParam(searchParams, "q");
  const prospectTypeFilter = readParam(searchParams, "prospect_type").trim().toLowerCase();
  const currencyFilter = readParam(searchParams, "currency").trim().toUpperCase();
  const quoteTypeFilter = readParam(searchParams, "quote_type").trim().toLowerCase();
  const schoolYearFilter = readParam(searchParams, "school_year").trim().toLowerCase();
  const languageFilter = readParam(searchParams, "language").trim().toLowerCase();
  const templateFilter = readParam(searchParams, "template").trim().toLowerCase();
  const cgvFilter = readParam(searchParams, "cgv").trim().toLowerCase();
  const hasSolfegeFilter = readParam(searchParams, "has_solfege").trim().toLowerCase();
  const workflowFilter = readParam(searchParams, "workflow_filter").trim().toLowerCase();
  const minTotalFilterRaw = readParam(searchParams, "min_total");
  const maxTotalFilterRaw = readParam(searchParams, "max_total");
  const createdFromFilterRaw = readParam(searchParams, "created_from");
  const createdToFilterRaw = readParam(searchParams, "created_to");
  const expiresFromFilterRaw = readParam(searchParams, "expires_from");
  const expiresToFilterRaw = readParam(searchParams, "expires_to");
  const ok = readParam(searchParams, "ok");
  const error = readParam(searchParams, "error");
  const okMessage = resolveUiFlashMessage(searchParams, language, "ok") || ok;
  const errorMessage = resolveUiFlashMessage(searchParams, language, "error") || error;

  const minTotalFilter = parseDecimal(minTotalFilterRaw);
  const maxTotalFilter = parseDecimal(maxTotalFilterRaw);
  const createdFromFilter = parseIsoDateOnly(createdFromFilterRaw);
  const createdToFilter = parseIsoDateOnly(createdToFilterRaw);
  const expiresFromFilter = parseIsoDateOnly(expiresFromFilterRaw);
  const expiresToFilter = parseIsoDateOnly(expiresToFilterRaw);

  const listQuery = new URLSearchParams();
  if (contextFilter) listQuery.set("context_type", contextFilter);
  if (activityFilter) listQuery.set("activity_id", activityFilter);
  listQuery.set("limit", "1000");

  const [prospectsResult, clientsResult, activitiesResult, quotesResult] = await Promise.all([
    backendRequest<ProspectOut[]>("/api/v1/prospects?limit=1000", {}, token),
    backendRequest<AdminClientOut[]>("/api/v1/admin/clients?limit=1000&include_archived=false", {}, token),
    backendRequest<AdminActivityOut[]>("/api/v1/admin/activities?include_inactive=true", {}, token),
    backendRequest<QuoteOut[]>(`/api/v1/quotes?${listQuery.toString()}`, {}, token),
  ]);

  const prospects = prospectsResult.ok ? prospectsResult.data : [];
  const baseClients = clientsResult.ok ? clientsResult.data : [];
  const activities = activitiesResult.ok ? activitiesResult.data : [];
  const quotes = quotesResult.ok ? quotesResult.data : [];

  const baseClientById = new Map(baseClients.map((row) => [row.id, row]));
  const missingQuoteClientIds = Array.from(new Set(
    quotes
      .map((row) => row.client_id || "")
      .filter((clientId) => clientId && !baseClientById.has(clientId)),
  ));
  const missingClientResults = missingQuoteClientIds.length > 0
    ? await Promise.all(missingQuoteClientIds.slice(0, 100).map((clientId) => (
      backendRequest<AdminClientOut>(`/api/v1/admin/clients/${encodeURIComponent(clientId)}`, {}, token)
    )))
    : [];
  const clients = [
    ...baseClients,
    ...missingClientResults.flatMap((result) => (result.ok ? [result.data] : [])),
  ];

  const prospectById = new Map(prospects.map((row) => [row.id, row]));
  const clientById = new Map(clients.map((row) => [row.id, row]));

  const filteredQuotes = quotes.filter((row) => {
    const owner = row.context_type === "acquisition"
      ? prospectById.get(row.prospect_id || "")
      : clientById.get(row.client_id || "");

    const ownerName = owner ? displayName(owner.first_name, owner.last_name, owner.email) : "";
    const ownerPhone = owner
      ? [
          String(owner.phone || ""),
          "mobile_phone_1" in owner ? String(owner.mobile_phone_1 || "") : "",
          "mobile_phone_2" in owner ? String(owner.mobile_phone_2 || "") : "",
        ]
          .join(" ")
          .trim()
      : "";

    const textHaystack = [row.quote_number, ownerName, owner?.email || "", ownerPhone]
      .join(" ")
      .toLowerCase();
    if (query && !textHaystack.includes(query.trim().toLowerCase())) {
      return false;
    }

    if (!matchesCommercialStatusFilter(row, statusFilter)) {
      return false;
    }

    const rowProspectType = row.context_type === "acquisition"
      ? prospectTypeLabelFromMeta((owner as ProspectOut | undefined)?.meta || {})
      : prospectTypeLabelFromClient(owner as AdminClientOut | undefined);
    if (prospectTypeFilter && rowProspectType !== prospectTypeFilter) {
      return false;
    }

    if (currencyFilter && (row.currency || "").toUpperCase() !== currencyFilter) {
      return false;
    }

    if (quoteTypeFilter && (row.quote_type || "").trim().toLowerCase() !== quoteTypeFilter) {
      return false;
    }

    if (schoolYearFilter && !(row.school_year_label || "").trim().toLowerCase().includes(schoolYearFilter)) {
      return false;
    }

    const rowLanguage = languageLabel(row.meta || {});
    if (languageFilter && rowLanguage !== languageFilter) {
      return false;
    }

    const rowTemplate = templateLabel(row.meta || {}).toLowerCase();
    if (templateFilter && !rowTemplate.includes(templateFilter)) {
      return false;
    }

    const rowCgv = cgvLabel(row.cgv_snapshot || {}).toLowerCase();
    if (cgvFilter && !rowCgv.includes(cgvFilter)) {
      return false;
    }

    const rowHasSolfege = Boolean((row.estimated_solfege_level || "").trim());
    if (hasSolfegeFilter === "yes" && !rowHasSolfege) {
      return false;
    }
    if (hasSolfegeFilter === "no" && rowHasSolfege) {
      return false;
    }

    if (workflowFilter) {
      const commercialState = quoteValidationState(row);
      const integrationState = quoteIntegrationState(row, commercialState);
      const nextAction = quoteNextAction(commercialState, integrationState);
      if (workflowFilter === "preparer_integration" && !(commercialState === "valide" && integrationState === "a_preparer")) {
        return false;
      }
      if (workflowFilter === "integrer_dans_centrale" && nextAction !== "integrer_dans_centrale") {
        return false;
      }
      if (workflowFilter === "erreur_integration" && integrationState !== "erreur_integration") {
        return false;
      }
    }

    const total = Number(row.total_ttc);
    if (minTotalFilter !== null && Number.isFinite(total) && total < minTotalFilter) {
      return false;
    }
    if (maxTotalFilter !== null && Number.isFinite(total) && total > maxTotalFilter) {
      return false;
    }

    const createdAt = new Date(row.created_at);
    if (createdFromFilter && (!Number.isFinite(createdAt.getTime()) || createdAt < createdFromFilter)) {
      return false;
    }
    if (createdToFilter) {
      const createdToLimit = new Date(createdToFilter.getTime() + 24 * 60 * 60 * 1000);
      if (!Number.isFinite(createdAt.getTime()) || createdAt >= createdToLimit) {
        return false;
      }
    }

    if (expiresFromFilter || expiresToFilter) {
      if (!row.expires_at) {
        return false;
      }
      const expiresAt = new Date(row.expires_at);
      if (expiresFromFilter && (!Number.isFinite(expiresAt.getTime()) || expiresAt < expiresFromFilter)) {
        return false;
      }
      if (expiresToFilter) {
        const expiresToLimit = new Date(expiresToFilter.getTime() + 24 * 60 * 60 * 1000);
        if (!Number.isFinite(expiresAt.getTime()) || expiresAt >= expiresToLimit) {
          return false;
        }
      }
    }

    return true;
  });

  const currentListHref = withUiLanguage(buildQuotesListHref({
    status: statusFilter,
    contextType: contextFilter,
    activityId: activityFilter,
    q: query,
    prospectType: prospectTypeFilter,
    currency: currencyFilter,
    quoteType: quoteTypeFilter,
    schoolYear: schoolYearFilter,
    language: languageFilter,
    template: templateFilter,
    cgv: cgvFilter,
    hasSolfege: hasSolfegeFilter,
    workflowFilter,
    minTotal: minTotalFilterRaw,
    maxTotal: maxTotalFilterRaw,
    createdFrom: createdFromFilterRaw,
    createdTo: createdToFilterRaw,
    expiresFrom: expiresFromFilterRaw,
    expiresTo: expiresToFilterRaw,
  }), language);

  const currencyValues = Array.from(new Set(quotes.map((row) => (row.currency || "").toUpperCase()).filter(Boolean))).sort();
  const quoteTypeValues = Array.from(new Set(quotes.map((row) => (row.quote_type || "").trim()).filter(Boolean))).sort();
  const quoteStatusOptions = [
    { value: "incomplet", label: t("admin.quotes.validation.incomplet") },
    { value: "brouillon", label: t("admin.quotes.validation.brouillon") },
    { value: "pret_a_envoyer", label: t("admin.quotes.validation.pret_a_envoyer") },
    { value: "envoye", label: t("admin.quotes.validation.envoye") },
    { value: "consulte", label: t("admin.quotes.validation.consulte") },
    { value: "modification_demandee", label: t("admin.quotes.validation.modification_demandee") },
    { value: "valide", label: t("admin.quotes.validation.valide") },
    { value: "refuse", label: t("admin.quotes.validation.refuse") },
    { value: "expire", label: t("admin.quotes.validation.expire") },
  ];
  const quoteStats = filteredQuotes.reduce(
    (acc, row) => {
      const commercialState = quoteValidationState(row);
      const integrationState = quoteIntegrationState(row, commercialState);
      if (isPotentialEnrollmentState(commercialState)) {
        acc.potentialEnrollments += 1;
        if (quotePotentialLocation(row) === "bar_le_duc") {
          acc.potentialBarLeDuc += 1;
        } else {
          acc.potentialParis += 1;
        }
      }
      if (commercialState === "incomplet") {
        acc.incomplete += 1;
      }
      if (commercialState === "pret_a_envoyer") {
        acc.readyToSend += 1;
      }
      if (commercialState === "brouillon") {
        acc.draft += 1;
      }
      if (commercialState === "envoye" || commercialState === "consulte") {
        acc.sent += 1;
      }
      if (commercialState === "modification_demandee") {
        acc.changeRequests += 1;
      }
      if (commercialState === "valide") {
        acc.approved += 1;
        if (integrationState !== "integre") {
          acc.integrationTodo += 1;
        }
      }
      if (integrationState === "erreur_integration") {
        acc.integrationErrors += 1;
      }
      return acc;
    },
    {
      total: filteredQuotes.length,
      potentialEnrollments: 0,
      potentialParis: 0,
      potentialBarLeDuc: 0,
      incomplete: 0,
      draft: 0,
      readyToSend: 0,
      sent: 0,
      changeRequests: 0,
      approved: 0,
      integrationTodo: 0,
      integrationErrors: 0,
    },
  );
  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.quotes.title")}</h2>
            <p className="muted">{t("admin.quotes.subtitle")}</p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={withUiLanguage("/admin/prospects", language)}>
              {t("admin.quotes.view_prospects")}
            </Link>
            <Link className="ghost" href={withUiLanguage("/admin/config/quotes", language)}>
              {t("admin.quotes.configure_quotes")}
            </Link>
            <Link className="mode-link" href={withUiLanguage("/admin/quotes/new", language)}>
              {t("admin.quotes.new_quote")}
            </Link>
          </div>
        </div>
      </section>

      {!quotesResult.ok ? <section className="flash-err">{t("admin.quotes.error_quotes")}: {quotesResult.message}</section> : null}
      {!activitiesResult.ok ? <section className="flash-err">{t("admin.quotes.error_activities")}: {activitiesResult.message}</section> : null}
      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <section className="card">
        <div className="config-metric-grid">
          <article>
            <span>{t("admin.quotes.metrics_potential_enrollments")}</span>
            <strong>{quoteStats.potentialEnrollments}</strong>
          </article>
          <article>
            <span>{t("admin.quotes.metrics_potential_paris")}</span>
            <strong>{quoteStats.potentialParis}</strong>
          </article>
          <article>
            <span>{t("admin.quotes.metrics_potential_bar_le_duc")}</span>
            <strong>{quoteStats.potentialBarLeDuc}</strong>
          </article>
          <article className={quoteStats.incomplete > 0 ? "is-warning" : ""}>
            <span>{t("admin.quotes.metrics_incomplete")}</span>
            <strong>{quoteStats.incomplete}</strong>
          </article>
          <article>
            <span>{t("admin.quotes.metrics_ready_to_send")}</span>
            <strong>{quoteStats.readyToSend}</strong>
          </article>
          <article className={quoteStats.changeRequests > 0 ? "is-warning" : ""}>
            <span>{t("admin.quotes.metrics_change_requests")}</span>
            <strong>{quoteStats.changeRequests}</strong>
          </article>
          <article>
            <span>{t("admin.quotes.metrics_approved")}</span>
            <strong>{quoteStats.approved}</strong>
          </article>
          <article className={quoteStats.integrationTodo > 0 ? "is-warning" : ""}>
            <span>{t("admin.quotes.metrics_integration_todo")}</span>
            <strong>{quoteStats.integrationTodo}</strong>
          </article>
          <article className={quoteStats.integrationErrors > 0 ? "is-warning" : ""}>
            <span>{t("admin.quotes.metrics_integration_errors")}</span>
            <strong>{quoteStats.integrationErrors}</strong>
          </article>
        </div>
      </section>

      <QuoteListPageRefine
        language={language}
        actions={(
          <>
            <QuoteRowValidationState state="valide" language={language} />
            <QuoteRowIntegrationState state="a_preparer" language={language} />
            <QuoteRowIntegrationState state="integre" language={language} />
          </>
        )}
      >
        <form method="get" className="quote-list-filters">
          <div className="grid cols-4 sticky-filters">
            <label className="cols-span-2">
              {t("admin.quotes.search_label")}
              <input type="text" name="q" defaultValue={query} placeholder={t("admin.quotes.search_placeholder")} />
            </label>
            <label>
              {t("admin.quotes.commercial_status")}
              <select name="status" defaultValue={statusFilter}>
                <option value="">{t("common.all")}</option>
                {quoteStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quotes.context")}
              <select name="context_type" defaultValue={contextFilter}>
                <option value="">{t("common.all")}</option>
                <option value="acquisition">{t("admin.quotes.context_acquisition")}</option>
                <option value="active_client">{t("admin.quotes.context_active_client")}</option>
              </select>
            </label>
            <label>
              {t("admin.quotes.prospect_type")}
              <select name="prospect_type" defaultValue={prospectTypeFilter}>
                <option value="">{t("common.all")}</option>
                <option value="adult">{t("client.adult")}</option>
                <option value="child">{t("client.child")}</option>
              </select>
            </label>
            <label>
              {t("admin.quotes.with_solfege")}
              <select name="has_solfege" defaultValue={hasSolfegeFilter}>
                <option value="">{t("common.all")}</option>
                <option value="yes">{t("common.yes")}</option>
                <option value="no">{t("common.no")}</option>
              </select>
            </label>
            <label>
              {t("admin.quotes.specific_activity")}
              <select name="activity_id" defaultValue={activityFilter}>
                <option value="">{t("admin.quotes.all_activities")}</option>
                {activities.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label>
              {t("admin.quotes.next_action_filter")}
              <select name="workflow_filter" defaultValue={workflowFilter}>
                <option value="">{t("admin.quotes.all_next_actions")}</option>
                <option value="preparer_integration">{t("admin.quotes.workflow_prepare_integration")}</option>
                <option value="integrer_dans_centrale">{t("admin.quotes.workflow_ready_to_integrate")}</option>
                <option value="erreur_integration">{t("admin.quotes.workflow_integration_errors")}</option>
              </select>
            </label>
          </div>

          <details className="quote-advanced-filters top-gap-sm">
            <summary>{t("admin.quotes.advanced_filters")}</summary>
            <div className="grid cols-4 top-gap-sm">
              <label>
                {t("admin.quotes.currency")}
                <select name="currency" defaultValue={currencyFilter}>
                  <option value="">{t("admin.quotes.all_currencies")}</option>
                  {currencyValues.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("admin.quotes.quote_type")}
                <select name="quote_type" defaultValue={quoteTypeFilter}>
                  <option value="">{t("common.all")}</option>
                  {quoteTypeValues.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                {t("admin.quotes.school_year")}
                <input type="text" name="school_year" defaultValue={schoolYearFilter} placeholder={t("admin.quotes.placeholder_school_year")} />
              </label>
              <label>
                {t("common.language")}
                <input type="text" name="language" defaultValue={languageFilter} placeholder={t("admin.quotes.placeholder_language")} />
              </label>
              <label>
                {t("admin.quotes.template")}
                <input type="text" name="template" defaultValue={templateFilter} placeholder={t("admin.quotes.placeholder_template")} />
              </label>
              <label>
                {t("admin.quotes.terms")}
                <input type="text" name="cgv" defaultValue={cgvFilter} placeholder={t("admin.quotes.placeholder_terms")} />
              </label>
              <label>
                {t("admin.quotes.min_total_ttc")}
                <input type="number" name="min_total" min={0} step="0.01" defaultValue={minTotalFilterRaw} />
              </label>
              <label>
                {t("admin.quotes.max_total_ttc")}
                <input type="number" name="max_total" min={0} step="0.01" defaultValue={maxTotalFilterRaw} />
              </label>
              <label>
                {t("admin.quotes.created_from")}
                <input type="date" name="created_from" defaultValue={createdFromFilterRaw} />
              </label>
              <label>
                {t("admin.quotes.created_to")}
                <input type="date" name="created_to" defaultValue={createdToFilterRaw} />
              </label>
              <label>
                {t("admin.quotes.expires_from")}
                <input type="date" name="expires_from" defaultValue={expiresFromFilterRaw} />
              </label>
              <label>
                {t("admin.quotes.expires_to")}
                <input type="date" name="expires_to" defaultValue={expiresToFilterRaw} />
              </label>
            </div>
          </details>

          <div className="row end cols-span-4 top-gap-sm">
            <button type="submit">{t("admin.quotes.filter")}</button>
            <a className="ghost" href={withUiLanguage("/admin/quotes", language)}>{t("common.reset")}</a>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table quote-list-table">
            <thead>
              <tr>
                <th>{t("admin.quotes.number")}</th>
                <th>{t("admin.quotes.owner")}</th>
                <th>{t("admin.quotes.context")}</th>
                <th>{t("admin.quotes.total_ttc")}</th>
                <th>{t("admin.quotes.client_validation")}</th>
                <th>{t("admin.quotes.central_integration")}</th>
                <th>{t("admin.quotes.next_action")}</th>
                <th>{t("admin.quotes.creation")}</th>
                <th>{t("admin.quotes.expiration")}</th>
                <th>{t("admin.quotes.activities")}</th>
                <th>{t("admin.quotes.action")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredQuotes.length === 0 ? (
                <tr>
                  <td colSpan={11}><p className="muted">{t("admin.quotes.no_quotes")}</p></td>
                </tr>
              ) : (
                filteredQuotes.map((row) => {
                  const owner = row.context_type === "acquisition"
                    ? prospectById.get(row.prospect_id || "")
                    : clientById.get(row.client_id || "");
                  const ownerName = owner
                    ? displayName(owner.first_name, owner.last_name, owner.email)
                    : "-";
                  const ownerEmail = visibleEmail(owner?.email);

                  const rowProspectType = row.context_type === "acquisition"
                    ? prospectTypeLabelFromMeta((owner as ProspectOut | undefined)?.meta || {})
                    : prospectTypeLabelFromClient(owner as AdminClientOut | undefined);
                  const detailHref = withUiLanguage(`/admin/quotes/${row.id}?back=${encodeURIComponent(currentListHref)}`, language);
                  const publicHref = row.public_url ?? (row.public_token ? `/q/${row.id}?t=${encodeURIComponent(row.public_token)}` : "");
                  const publicAbsoluteHref = row.public_url ?? "";
                  const commercialState = quoteValidationState(row);
                  const integrationState = quoteIntegrationState(row, commercialState);
                  const nextAction = quoteNextAction(commercialState, integrationState);
                  const changeRequest = quoteChangeRequestSummary(row);
                  const changeRequestRevision = quoteChangeRequestRevision(row);

                  return (
                    <tr key={row.id} className="quote-list-row">
                      <td>
                        <Link className="quote-list-row-link" href={detailHref}>
                          <strong>{row.quote_number}</strong>
                        </Link>
                        <br />
                        <small className="muted">{row.quote_type}</small>
                      </td>
                      <td>
                        <strong>{ownerName}</strong>
                        <br />
                        <small className="muted">{owner?.email ?? "-"}</small>
                        <br />
                        <small className="muted">{rowProspectType === "-" ? "-" : rowProspectType === "adult" ? t("client.adult") : t("client.child")}</small>
                      </td>
                      <td>{labelForContext(row.context_type, language)}</td>
                      <td>{formatAmount(row.total_ttc, row.currency, language)}</td>
                      <td>
                        <div className="quote-list-status-cell">
                          <QuoteRowValidationState state={commercialState} language={language} />
                          {changeRequest ? (
                            <div className="quote-list-change-request-note">
                              <strong>{t("admin.quotes.change_request")}</strong>
                              {changeRequest.at ? (
                                <span>{t("admin.quotes.received_on", { date: formatDate(changeRequest.at, language) })}</span>
                              ) : null}
                              {changeRequest.message ? (
                                <span className="quote-list-change-request-message">"{changeRequest.message}"</span>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td><QuoteRowIntegrationState state={integrationState} language={language} /></td>
                      <td>
                        <div className="quote-list-status-cell">
                          <QuoteRowNextAction action={nextAction} language={language} />
                          {changeRequest ? (
                            <span className="quote-list-inline-hint">{t("admin.quotes.open_to_handle_request")}</span>
                          ) : null}
                          {changeRequestRevision ? (
                            <Link className="quote-list-inline-hint" href={withUiLanguage(`/admin/quotes/${changeRequestRevision.id}`, language)}>
                              Version brouillon {changeRequestRevision.number || ""}
                            </Link>
                          ) : null}
                        </div>
                      </td>
                      <td>{formatDate(row.created_at, language)}</td>
                      <td>{formatDate(row.expires_at, language)}</td>
                      <td>{getCalendarSessionsCount(row.calendar_snapshot)}</td>
                      <td>
                        <div className="row wrap gap-xs">
                          <Link className="ghost" href={detailHref}>{row.status === "created" ? t("common.edit") : t("common.open")}</Link>
                          {row.status === "created" ? (
                            <form action={sendQuoteAction}>
                              <input type="hidden" name="quote_id" value={row.id} />
                              <input type="hidden" name="return_to" value={currentListHref} />
                              <input type="hidden" name="recipient_email" value={ownerEmail} />
                              <button type="submit" className="ghost">{t("admin.quotes.send")}</button>
                            </form>
                          ) : null}
                          <form action={duplicateQuoteAction}>
                            <input type="hidden" name="quote_id" value={row.id} />
                            <input type="hidden" name="return_to" value={currentListHref} />
                            <button type="submit" className="ghost">{t("common.duplicate")}</button>
                          </form>
                          {publicHref ? (
                            <a className="ghost" href={publicHref} target="_blank" rel="noreferrer">{t("admin.quotes.public_page")}</a>
                          ) : null}
                          {publicAbsoluteHref ? (
                            <CopyLinkButton
                              value={publicAbsoluteHref}
                              label={t("common.copy_link")}
                              copiedLabel={t("common.link_copied")}
                            />
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </QuoteListPageRefine>
    </section>
  );
}
