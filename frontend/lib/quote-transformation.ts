import { type UiLanguage, uiText } from "./ui-i18n";

export type QuoteTransformScenario = "live" | "A" | "B" | "C";

export type QuoteTransformStatus = "ok" | "warning" | "blocked";

export type QuoteTransformStep = 1 | 2 | 3 | 4 | 5;

export type QuoteTransformClientResolutionMode = "existing" | "new_adult" | "new_parent_child" | "new_child_existing_parent";

export type QuoteTransformProspect = {
  id: string;
  firstName: string | null;
  lastName: string | null;
  email: string;
  phone: string | null;
  parentProspectId: string | null;
  prospectType: "adult" | "child";
  meta: Record<string, unknown>;
};

export type QuoteTransformClient = {
  id: string;
  firstName: string | null;
  lastName: string | null;
  email: string;
  phone: string | null;
  mobilePhone1: string | null;
  mobilePhone2: string | null;
  homePhone: string | null;
  familyName: string | null;
  clientKind: string;
  clientStatus: string;
};

export type QuoteTransformPlan = {
  id: string;
  name: string;
  kind: string;
  active: boolean;
};

export type QuoteTransformLegalEntity = {
  id: string;
  name: string;
};

export type QuoteTransformActivityCatalog = {
  id: string;
  name: string;
  serviceCode: string;
  durationMinutes: number;
  defaultCourseRateTtc: number | null;
  mode: string;
  active: boolean;
};

export type QuoteTransformLine = {
  id: string;
  lineType: string;
  lineCategory: string;
  masterItemType: string | null;
  activityId: string | null;
  title: string;
  quantity: number;
  durationMinutes: number | null;
  pricingUnit: string | null;
  amountHt: number;
  amountTtc: number;
  vatRate: number;
  meta: Record<string, unknown>;
};

export type QuoteTransformFinancialAdjustment = {
  type: "none" | "credit" | "debt";
  amountTtc: number;
  label: string | null;
  vatRate: number;
};

export type QuoteTransformQuote = {
  id: string;
  quoteNumber: string;
  status: string;
  clientId?: string | null;
  currency: string;
  totalTtc: number;
  totalHt: number;
  schoolYearLabel: string | null;
  legalEntityId: string | null;
  legalEntityName: string;
  paymentPlanName: string;
  quoteType: string;
  quoteTypeFormulaName: string | null;
  locationId: string | null;
  locationName: string;
  financialAdjustment?: QuoteTransformFinancialAdjustment | null;
};

export function quoteTransformFinancialAdjustmentFromMeta(
  meta: Record<string, unknown> | null | undefined,
  defaultVatRate = 20,
): QuoteTransformFinancialAdjustment | null {
  const row = readObject(meta?.financial_adjustment);
  const rawType = String(row?.type ?? "").trim().toLowerCase();
  const type = rawType === "credit" || rawType === "debt" ? rawType : "none";
  const amountTtc = readNumber(row?.amount_ttc ?? row?.amountTtc, 0);
  if (type === "none" || !Number.isFinite(amountTtc) || amountTtc <= 0) {
    return null;
  }
  const rawVatRate = readNumber(row?.vat_rate ?? row?.vatRate, defaultVatRate);
  const vatRate = Number.isFinite(rawVatRate) && rawVatRate >= 0 ? rawVatRate : defaultVatRate;
  const label = readString(row?.label) || null;
  return {
    type,
    amountTtc,
    label,
    vatRate,
  };
}

export type QuoteScheduleHint = {
  activityId: string | null;
  startDate: string | null;
  weekday: number | null;
  startTime: string | null;
  endTime: string | null;
};

export type QuoteTransformSession = {
  id: string;
  courseTypeId: string;
  locationId: string;
  title: string;
  startAtUtc: string;
  endAtUtc: string;
  timezone: string;
  teacherDisplayName: string;
  status: string;
  statusLabel: string;
  capacityMax: number;
  bookedCount: number;
  seatsRemaining: number;
};

export type ClientMatchCandidate = {
  clientId: string;
  displayName: string;
  email: string;
  phone: string | null;
  familyName: string | null;
  confidence: number;
  confidenceLabel: "fort" | "moyen" | "faible";
  reasons: string[];
};

export type ActivityPricingRow = {
  rowId: string;
  lineId: string;
  activityId: string;
  activityName: string;
  locationName: string;
  pricingUnit: string;
  quantity: number;
  durationMinutes: number | null;
  expectedTtc: number;
  baseRateTtc: number | null;
  currentSystemTtc: number;
  discountTtc: number;
  supplementTtc: number;
  deltaTtc: number;
  status: QuoteTransformStatus;
  reason: string;
};

export type SessionMatchOption = {
  sessionId: string;
  label: string;
  dateLabel: string;
  teacher: string;
  seatsRemaining: number;
  status: string;
  score: number;
  reasons: string[];
};

export type BillingExtraRow = {
  rowId: string;
  sourceLineId: string | null;
  type: string;
  label: string;
  amountHt: number;
  vatRate: number;
  amountVat: number;
  amountTtc: number;
  status: QuoteTransformStatus;
  editable: boolean;
};

export type StepIssue = {
  issueId: string;
  step: QuoteTransformStep;
  level: "warning" | "blocked";
  message: string;
  canOverride: boolean;
};

export type QuoteToEnrollmentLogEntry = {
  at: string;
  action: string;
  detail: string;
};

export type QuoteToEnrollmentBillingDraftRow = {
  rowId: string;
  type: string;
  label: string;
  amountHt: number;
  vatRate: number;
  amountTtc: number;
};

export type QuoteToEnrollmentDraft = {
  version: 1;
  scenario: QuoteTransformScenario;
  currentStep: QuoteTransformStep;
  clientResolution: {
    mode: QuoteTransformClientResolutionMode;
    selectedClientId: string | null;
    selectedParentClientId: string | null;
    notes: string;
  };
  activityResolution: {
    planId: string | null;
    alignedActivityIds: string[];
    offPlanningActivityIds: string[];
  };
  scheduleResolution: {
    assignedSessionByActivityId: Record<string, string>;
  };
  billingResolution: {
    rows: QuoteToEnrollmentBillingDraftRow[];
  };
  acceptedBlockingIssueIds: string[];
  financialControl: {
    expectedTtc: number;
    systemTtc: number;
    deltaTtc: number;
  };
  idempotencyKey: string;
  logs: QuoteToEnrollmentLogEntry[];
  finalizedAt: string | null;
};

export type QuoteQuickTransformStatus = "auto_validable" | "review_required" | "blocked";

export type QuoteQuickTransformProposedClient = {
  clientId: string;
  displayName: string;
  confidence: number;
  confidenceLabel: "fort" | "moyen" | "faible";
  source: "quote_client_link" | "matching";
};

export type QuoteQuickTransformProposedScheduleAssignment = {
  activityId: string;
  activityName: string;
  status: "auto_assigned" | "choice_required" | "missing" | "full";
  sessionId: string | null;
  sessionLabel: string;
  seatsRemaining: number | null;
  warning: string | null;
};

export type QuoteQuickTransformPriceMatchSummary = {
  activitiesCount: number;
  okCount: number;
  warningCount: number;
  blockedCount: number;
  expectedTotalTtc: number;
  systemTotalTtc: number;
  deltaTtc: number;
};

export type QuoteQuickTransformFinancialSummary = {
  expectedTtc: number;
  systemTtc: number;
  deltaTtc: number;
  status: QuoteTransformStatus;
};

export type QuoteQuickTransformSummary = {
  activitiesCount: number;
  slotsFoundCount: number;
  autoAssignableCount: number;
  offPlanningCount: number;
  totalQuoteTtc: number;
  totalSystemTtc: number;
};

export type QuoteQuickTransformAnalysis = {
  status: QuoteQuickTransformStatus;
  reasonsOk: string[];
  warnings: string[];
  blockingIssues: string[];
  proposedClient: QuoteQuickTransformProposedClient | null;
  proposedScheduleAssignments: QuoteQuickTransformProposedScheduleAssignment[];
  priceMatchSummary: QuoteQuickTransformPriceMatchSummary;
  financialMatchSummary: QuoteQuickTransformFinancialSummary;
  summary: QuoteQuickTransformSummary;
  canQuickTransform: boolean;
  firstNonConformStep: QuoteTransformStep | null;
  suggestedDraft: QuoteToEnrollmentDraft | null;
};

export type QuoteQuickTransformAnalysisInput = {
  quote: QuoteTransformQuote;
  prospect: QuoteTransformProspect | null;
  lines: QuoteTransformLine[];
  clients: QuoteTransformClient[];
  activities: QuoteTransformActivityCatalog[];
  sessionsByActivityId: Record<string, QuoteTransformSession[]>;
  plans: QuoteTransformPlan[];
  calendarSnapshot: Record<string, unknown>;
  followupId: string | null;
  followupStatus: string | null;
  scenario?: QuoteTransformScenario;
};

function normalizeText(value: string | null | undefined): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readNumber(value: unknown, fallback = 0): number {
  const parsed = Number(String(value ?? "").replace(",", "."));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return parsed;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function isHhmm(value: string): boolean {
  return /^([01]\d|2[0-3]):([0-5]\d)$/.test(value);
}

function weekdayFromDateKey(value: string): number | null {
  if (!isIsoDate(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const day = parsed.getUTCDay();
  return day === 0 ? 6 : day - 1;
}

function dayNumberFromDateKey(value: string): number | null {
  if (!isIsoDate(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return Math.floor(parsed.getTime() / 86_400_000);
}

export function normalizePhone(value: string | null | undefined): string {
  return String(value || "").replace(/[^\d+]/g, "");
}

export function displayName(firstName: string | null | undefined, lastName: string | null | undefined, fallback: string): string {
  const value = `${firstName || ""} ${lastName || ""}`.trim();
  return value || fallback;
}

export function quoteTransformStatusLabel(status: QuoteTransformStatus, language: UiLanguage = "fr"): string {
  const key =
    status === "ok"
      ? "admin.quote_transform.status_ok"
      : status === "warning"
      ? "admin.quote_transform.status_warning"
      : "admin.quote_transform.status_blocked";
  return uiText(language, key);
}

export function quoteTransformConfidenceLabel(
  label: ClientMatchCandidate["confidenceLabel"] | QuoteQuickTransformProposedClient["confidenceLabel"],
  language: UiLanguage = "fr",
): string {
  if (label === "fort") {
    return uiText(language, "admin.quote_transform.confidence_strong");
  }
  if (label === "moyen") {
    return uiText(language, "admin.quote_transform.confidence_medium");
  }
  return uiText(language, "admin.quote_transform.confidence_low");
}

export function translateQuoteTransformMessage(message: string, language: UiLanguage = "fr"): string {
  const raw = String(message || "").trim();
  if (!raw) {
    return raw;
  }

  const exact: Record<string, string> = {
    "email identique": "admin.quote_transform.reason_same_email",
    "telephone identique": "admin.quote_transform.reason_same_phone",
    "prenom proche": "admin.quote_transform.reason_first_name_close",
    "nom proche": "admin.quote_transform.reason_last_name_close",
    "famille probable": "admin.quote_transform.reason_family_probable",
    "correspondance partielle": "admin.quote_transform.reason_partial_match",
    "arbitrage manuel requis (scenario B)": "admin.quote_transform.reason_manual_arbitration_scenario_b",
    "correspondance a verifier (scenario B)": "admin.quote_transform.reason_match_review_scenario_b",
    "alignement devis/systeme": "admin.quote_transform.reason_quote_system_aligned",
    "ecart mineur a verifier": "admin.quote_transform.reason_minor_gap_review",
    "ecart critique": "admin.quote_transform.reason_critical_gap",
    "ecart simule (scenario B)": "admin.quote_transform.reason_simulated_gap_scenario_b",
    "ecart simule (scenario C)": "admin.quote_transform.reason_simulated_gap_scenario_c",
    "lieu compatible": "admin.quote_transform.reason_location_compatible",
    "creneau planifie": "admin.quote_transform.reason_slot_scheduled",
    "statut non ideal": "admin.quote_transform.reason_status_not_ideal",
    "place disponible": "admin.quote_transform.reason_seat_available",
    "complet": "admin.quote_transform.reason_full",
    "date demarrage coherente": "admin.quote_transform.reason_start_date_consistent",
    "jour coherent": "admin.quote_transform.reason_weekday_consistent",
    "horaire demarrage coherent": "admin.quote_transform.reason_start_time_consistent",
    "proposition de demonstration": "admin.quote_transform.reason_demo_proposal",
    "date la plus proche": "admin.quote_transform.reason_nearest_date",
    "date la plus proche (horaire approche)": "admin.quote_transform.reason_nearest_date_time",
    "Client cible deja lie au devis.": "admin.quote_transform.analysis_client_already_linked",
    "Aucun client fiable identifie.": "admin.quote_transform.analysis_no_reliable_client",
    "Plusieurs correspondances client probables necessitent un arbitrage.": "admin.quote_transform.analysis_multiple_client_matches",
    "Correspondance client detectee mais confiance moyenne.": "admin.quote_transform.analysis_medium_confidence_match",
    "Client cible identifie sans ambiguite.": "admin.quote_transform.analysis_client_identified",
    "Aucune activite planifiable detectee sur le devis.": "admin.quote_transform.analysis_no_plannable_activity",
    "Aucune ligne hors planning a reprendre.": "admin.quote_transform.analysis_no_off_planning",
    "Totaux HT/TTC conformes.": "admin.quote_transform.analysis_totals_ok",
    "Follow-up absent: verification manuelle recommandee.": "admin.quote_transform.analysis_followup_missing",
    "Follow-up disponible pour journalisation.": "admin.quote_transform.analysis_followup_available",
    "Validation client du devis requise avant transformation.": "admin.quote_transform.analysis_quote_approval_required",
    "Scenario A: parcours simple auto-validable (demo localhost).": "admin.quote_transform.analysis_demo_simple",
    "Scenario B: verification manuelle recommandee (demo localhost).": "admin.quote_transform.analysis_demo_review",
    "Scenario C: blocage critique simule (demo localhost).": "admin.quote_transform.analysis_demo_blocked",
    "Choix manuel requis": "admin.quote_transform.analysis_manual_choice_required",
    "Aucun creneau": "admin.quote_transform.analysis_no_slot",
  };
  if (raw in exact) {
    return uiText(language, exact[raw]!);
  }

  let match = raw.match(/^Formule detectee: (.+)\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_formula_detected", { plan: match[1] });
  }
  match = raw.match(/^(.+): activite non mappee dans le referentiel\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_activity_not_mapped", { activity: match[1] });
  }
  match = raw.match(/^(.+): ecart tarifaire critique \(([-0-9.,]+)\)\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_price_gap_critical", { activity: match[1], delta: match[2] });
  }
  match = raw.match(/^(.+): ecart tarifaire mineur \(([-0-9.,]+)\)\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_price_gap_minor", { activity: match[1], delta: match[2] });
  }
  match = raw.match(/^(.+): aucun creneau coherent trouve\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_no_coherent_slot", { activity: match[1] });
  }
  match = raw.match(/^(.+): creneau complet sans alternative\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_full_slot_no_alternative", { activity: match[1] });
  }
  match = raw.match(/^(.+): creneau unique auto-assignable\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_unique_slot", { activity: match[1] });
  }
  match = raw.match(/^(.+): plusieurs creneaux possibles, recommandation disponible\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_multiple_slots", { activity: match[1] });
  }
  match = raw.match(/^(.+): ligne hors planning invalide\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_off_planning_invalid", { label: match[1] });
  }
  match = raw.match(/^(.+): ligne hors planning a confirmer\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_off_planning_confirm", { label: match[1] });
  }
  match = raw.match(/^(.+): ligne hors planning coherente\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_off_planning_ok", { label: match[1] });
  }
  match = raw.match(/^Total devis\/systeme incoherent \(([-0-9.,]+)\)\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_totals_incoherent", { delta: match[1] });
  }
  match = raw.match(/^Ecart financier mineur a confirmer \(([-0-9.,]+)\)\.$/);
  if (match) {
    return uiText(language, "admin.quote_transform.analysis_financial_minor", { delta: match[1] });
  }

  return raw;
}

function confidenceLabel(value: number): "fort" | "moyen" | "faible" {
  if (value >= 80) {
    return "fort";
  }
  if (value >= 55) {
    return "moyen";
  }
  return "faible";
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function buildClientMatchCandidates(
  prospect: QuoteTransformProspect | null,
  clients: QuoteTransformClient[],
  scenario: QuoteTransformScenario,
): ClientMatchCandidate[] {
  if (!prospect) {
    return [];
  }

  const prospectEmail = normalizeText(prospect.email);
  const prospectPhone = normalizePhone(prospect.phone);
  const prospectFirst = normalizeText(prospect.firstName);
  const prospectLast = normalizeText(prospect.lastName);

  const matches = clients
    .map((client) => {
      let score = 0;
      const reasons: string[] = [];

      if (prospectEmail && normalizeText(client.email) === prospectEmail) {
        score += 60;
        reasons.push("email identique");
      }

      const phoneCandidates = [client.phone, client.mobilePhone1, client.mobilePhone2, client.homePhone]
        .map((item) => normalizePhone(item))
        .filter(Boolean);
      if (prospectPhone && phoneCandidates.includes(prospectPhone)) {
        score += 25;
        reasons.push("telephone identique");
      }

      const clientFirst = normalizeText(client.firstName);
      const clientLast = normalizeText(client.lastName);
      if (prospectFirst && clientFirst && prospectFirst === clientFirst) {
        score += 8;
        reasons.push("prenom proche");
      }
      if (prospectLast && clientLast && prospectLast === clientLast) {
        score += 12;
        reasons.push("nom proche");
      }
      if (prospectLast && normalizeText(client.familyName) === prospectLast) {
        score += 8;
        reasons.push("famille probable");
      }

      if (scenario === "B" && reasons.length > 0) {
        score += 8;
      }
      if (scenario === "C" && client.clientKind.toUpperCase() === "ADULT") {
        score += 4;
      }

      return {
        client,
        score: clamp(score, 0, 100),
        reasons,
      };
    })
    .filter((row) => row.score >= 35)
    .sort((a, b) => b.score - a.score)
    .slice(0, scenario === "B" ? 4 : 3)
    .map((row) => ({
      clientId: row.client.id,
      displayName: displayName(row.client.firstName, row.client.lastName, row.client.email),
      email: row.client.email,
      phone: row.client.mobilePhone1 || row.client.phone || row.client.homePhone,
      familyName: row.client.familyName,
      confidence: row.score,
      confidenceLabel: confidenceLabel(row.score),
      reasons: row.reasons.length > 0 ? row.reasons : ["correspondance partielle"],
    }));

  if (scenario === "B" && matches.length === 0 && clients.length >= 2) {
    return clients.slice(0, 2).map((client, index) => ({
      clientId: client.id,
      displayName: displayName(client.firstName, client.lastName, client.email),
      email: client.email,
      phone: client.mobilePhone1 || client.phone || client.homePhone,
      familyName: client.familyName,
      confidence: index === 0 ? 71 : 63,
      confidenceLabel: "moyen" as const,
      reasons: ["arbitrage manuel requis (scenario B)"],
    }));
  }

  if (scenario === "B" && matches.length === 1) {
    const used = new Set(matches.map((item) => item.clientId));
    const alternate = clients.find((client) => !used.has(client.id));
    if (alternate) {
      return [
        matches[0],
        {
          clientId: alternate.id,
          displayName: displayName(alternate.firstName, alternate.lastName, alternate.email),
          email: alternate.email,
          phone: alternate.mobilePhone1 || alternate.phone || alternate.homePhone,
          familyName: alternate.familyName,
          confidence: 63,
          confidenceLabel: "moyen",
          reasons: ["correspondance a verifier (scenario B)"],
        },
      ];
    }
  }

  return matches;
}

function statusFromAmountDelta(deltaTtc: number): QuoteTransformStatus {
  const absolute = Math.abs(deltaTtc);
  if (absolute <= 0.5) {
    return "ok";
  }
  if (absolute <= 8) {
    return "warning";
  }
  return "blocked";
}

function amountReason(deltaTtc: number): string {
  const absolute = Math.abs(deltaTtc);
  if (absolute <= 0.5) {
    return "alignement devis/systeme";
  }
  if (absolute <= 8) {
    return "ecart mineur a verifier";
  }
  return "ecart critique";
}

export function buildActivityPricingRows(
  lines: QuoteTransformLine[],
  activitiesById: Map<string, QuoteTransformActivityCatalog>,
  activityLocationNameById: Map<string, string>,
  fallbackLocationName: string,
  scenario: QuoteTransformScenario,
): ActivityPricingRow[] {
  const rows = lines
    .filter((line) => line.activityId)
    .map((line, index) => {
      const activityId = line.activityId || "";
      const activity = activitiesById.get(activityId);
      const quantity = line.quantity > 0 ? line.quantity : 1;
      const expectedTtc = Number(line.amountTtc.toFixed(2));
      const baseRate = activity?.defaultCourseRateTtc ?? null;
      let currentSystemTtc = baseRate !== null ? Number((baseRate * quantity).toFixed(2)) : expectedTtc;
      let forcedScenarioReason: string | null = null;

      if (scenario === "B" && index === 0) {
        currentSystemTtc = Number((expectedTtc + 3.2).toFixed(2));
        forcedScenarioReason = "ecart simule (scenario B)";
      }
      if (scenario === "C" && index === 0) {
        currentSystemTtc = Number((expectedTtc + 12.5).toFixed(2));
        forcedScenarioReason = "ecart simule (scenario C)";
      }

      const deltaTtc = Number((currentSystemTtc - expectedTtc).toFixed(2));
      const locationName = activityLocationNameById.get(activityId) || fallbackLocationName;
      return {
        rowId: `${line.id}-${activityId}`,
        lineId: line.id,
        activityId,
        activityName: activity?.name || line.title,
        locationName,
        pricingUnit: line.pricingUnit || "forfait",
        quantity,
        durationMinutes: line.durationMinutes,
        expectedTtc,
        baseRateTtc: baseRate,
        currentSystemTtc,
        discountTtc: 0,
        supplementTtc: 0,
        deltaTtc,
        status: statusFromAmountDelta(deltaTtc),
        reason: forcedScenarioReason || amountReason(deltaTtc),
      } satisfies ActivityPricingRow;
    });

  if (rows.length === 0 && scenario !== "live") {
    return [
      {
        rowId: "demo-activity-1",
        lineId: "demo-line-1",
        activityId: "demo-activity",
        activityName: "Cours individuel piano",
        locationName: fallbackLocationName,
        pricingUnit: "session",
        quantity: 1,
        durationMinutes: 60,
        expectedTtc: 120,
        baseRateTtc: 120,
        currentSystemTtc: scenario === "C" ? 134 : 120,
        discountTtc: 0,
        supplementTtc: 0,
        deltaTtc: scenario === "C" ? 14 : 0,
        status: scenario === "C" ? "blocked" : "ok",
        reason: scenario === "C" ? "ecart simule (scenario C)" : "alignement devis/systeme",
      },
    ];
  }

  return rows;
}

function isoPartsInTimezone(
  iso: string,
  timezone: string | null | undefined,
): { dateKey: string | null; timeKey: string | null; weekday: number | null } {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return { dateKey: null, timeKey: null, weekday: null };
  }
  const safeTimezone = (timezone || "").trim() || "UTC";
  try {
    const dateParts = new Intl.DateTimeFormat("en-CA", {
      timeZone: safeTimezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(parsed);
    const year = dateParts.find((part) => part.type === "year")?.value || "";
    const month = dateParts.find((part) => part.type === "month")?.value || "";
    const day = dateParts.find((part) => part.type === "day")?.value || "";
    const dateKey = year && month && day ? `${year}-${month}-${day}` : null;
    const timeKey = parsed.toLocaleTimeString("fr-FR", {
      timeZone: safeTimezone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return {
      dateKey,
      timeKey: isHhmm(timeKey) ? timeKey : null,
      weekday: dateKey ? weekdayFromDateKey(dateKey) : null,
    };
  } catch {
    const year = String(parsed.getUTCFullYear());
    const month = String(parsed.getUTCMonth() + 1).padStart(2, "0");
    const day = String(parsed.getUTCDate()).padStart(2, "0");
    const dateKey = `${year}-${month}-${day}`;
    const hours = String(parsed.getUTCHours()).padStart(2, "0");
    const minutes = String(parsed.getUTCMinutes()).padStart(2, "0");
    return {
      dateKey,
      timeKey: `${hours}:${minutes}`,
      weekday: weekdayFromDateKey(dateKey),
    };
  }
}

function toLocalDateLabel(iso: string, timezone: string, locale = "fr-FR"): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return locale.startsWith("en") ? "date unavailable" : "date inconnue";
  }
  try {
    return parsed.toLocaleString(locale, {
      timeZone: (timezone || "").trim() || "UTC",
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return parsed.toLocaleString(locale, {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
}

function matchScore(
  session: QuoteTransformSession,
  hint: QuoteScheduleHint | null,
  expectedLocationId: string | null,
): { score: number; reasons: string[] } {
  let score = 0;
  const reasons: string[] = [];

  if (expectedLocationId && session.locationId === expectedLocationId) {
    score += 18;
    reasons.push("lieu compatible");
  }

  if (session.status.toUpperCase() === "SCHEDULED") {
    score += 14;
    reasons.push("creneau planifie");
  } else {
    score -= 30;
    reasons.push("statut non ideal");
  }

  if (session.seatsRemaining > 0) {
    score += 20;
    reasons.push("place disponible");
  } else {
    score -= 35;
    reasons.push("complet");
  }

  if (hint) {
    const sessionParts = isoPartsInTimezone(session.startAtUtc, session.timezone);
    if (hint.startDate && sessionParts.dateKey && hint.startDate === sessionParts.dateKey) {
      score += 24;
      reasons.push("date demarrage coherente");
    }
    if (hint.weekday !== null && sessionParts.weekday !== null && hint.weekday === sessionParts.weekday) {
      score += 12;
      reasons.push("jour coherent");
    }
    if (hint.startTime && sessionParts.timeKey && hint.startTime === sessionParts.timeKey) {
      score += 18;
      reasons.push("horaire demarrage coherent");
    }
  }

  return { score, reasons };
}

function mockSessionOption(
  activityName: string,
  activityId: string,
  variant: "single" | "multi" | "full" | "none",
  language: UiLanguage = "fr",
): SessionMatchOption[] {
  if (variant === "none") {
    return [];
  }
  const base = {
    sessionId: `mock-${activityId}-1`,
    label: `${activityName} · Studio Opera`,
    dateLabel: language === "en" ? "Mon 18:00" : "lun. 18:00",
    teacher: language === "en" ? "Demo teacher" : "Prof. Demo",
    status: "SCHEDULED",
    reasons: ["proposition de demonstration"],
  };
  if (variant === "full") {
    return [
      {
        ...base,
        seatsRemaining: 0,
        score: 42,
      },
    ];
  }
  if (variant === "multi") {
    return [
      {
        ...base,
        sessionId: `mock-${activityId}-1`,
        seatsRemaining: 3,
        score: 79,
      },
      {
        ...base,
        sessionId: `mock-${activityId}-2`,
        dateLabel: language === "en" ? "Wed 17:30" : "mer. 17:30",
        teacher: language === "en" ? "Workshop teacher" : "Prof. Atelier",
        seatsRemaining: 2,
        score: 72,
      },
    ];
  }
  return [
    {
      ...base,
      seatsRemaining: 4,
      score: 84,
    },
  ];
}

export function buildSessionMatches(
  activityRow: ActivityPricingRow,
  sessions: QuoteTransformSession[],
  expectedLocationId: string | null,
  hintsByActivityId: Map<string, QuoteScheduleHint>,
  scenario: QuoteTransformScenario,
  locale = "fr-FR",
  language: UiLanguage = "fr",
): SessionMatchOption[] {
  const hint = hintsByActivityId.get(activityRow.activityId) ?? null;
  const selectionModeRef: { value: "exact_date_time" | "exact_date" | "nearest_date_time" | "nearest_date" | "all" } = { value: "all" };
  const scopedSessions = (() => {
    if (!hint || !hint.startDate) {
      return sessions;
    }

    const sessionsWithParts = sessions.map((session) => ({
      session,
      local: isoPartsInTimezone(session.startAtUtc, session.timezone),
    }));
    const onStartDate = sessionsWithParts.filter((item) => item.local.dateKey === hint.startDate);

    const filterByTime = (
      items: Array<{ session: QuoteTransformSession; local: { dateKey: string | null; timeKey: string | null; weekday: number | null } }>,
    ): Array<{ session: QuoteTransformSession; local: { dateKey: string | null; timeKey: string | null; weekday: number | null } }> => {
      if (!hint.startTime) {
        return items;
      }
      return items.filter((item) => item.local.timeKey === hint.startTime);
    };

    const nearestByDate = (
      items: Array<{ session: QuoteTransformSession; local: { dateKey: string | null; timeKey: string | null; weekday: number | null } }>,
    ): Array<{ session: QuoteTransformSession; local: { dateKey: string | null; timeKey: string | null; weekday: number | null } }> => {
      const targetDay = dayNumberFromDateKey(hint.startDate || "");
      if (targetDay === null || items.length === 0) {
        return items;
      }
      const withDistance = items
        .map((item) => {
          const dayNumber = dayNumberFromDateKey(item.local.dateKey || "");
          if (dayNumber === null) {
            return null;
          }
          const delta = dayNumber - targetDay;
          return { item, delta };
        })
        .filter((row): row is { item: { session: QuoteTransformSession; local: { dateKey: string | null; timeKey: string | null; weekday: number | null } }; delta: number } => row !== null);

      if (withDistance.length === 0) {
        return [];
      }

      const onOrAfter = withDistance.filter((row) => row.delta >= 0);
      if (onOrAfter.length > 0) {
        const minForwardDelta = onOrAfter.reduce((acc, row) => (row.delta < acc ? row.delta : acc), Number.POSITIVE_INFINITY);
        return onOrAfter.filter((row) => row.delta === minForwardDelta).map((row) => row.item);
      }

      const maxPastDelta = withDistance.reduce((acc, row) => (row.delta > acc ? row.delta : acc), Number.NEGATIVE_INFINITY);
      return withDistance.filter((row) => row.delta === maxPastDelta).map((row) => row.item);
    };

    const onStartDateSameTime = filterByTime(onStartDate);
    if (onStartDateSameTime.length > 0) {
      selectionModeRef.value = "exact_date_time";
      return onStartDateSameTime.map((item) => item.session);
    }

    if (onStartDate.length > 0) {
      selectionModeRef.value = "exact_date";
      return onStartDate.map((item) => item.session);
    }

    const allSameTime = filterByTime(sessionsWithParts);
    if (allSameTime.length > 0) {
      const nearestSameTime = nearestByDate(allSameTime);
      if (nearestSameTime.length > 0) {
        selectionModeRef.value = "nearest_date_time";
        return nearestSameTime.map((item) => item.session);
      }
    }

    const nearestAnyTime = nearestByDate(sessionsWithParts);
    if (nearestAnyTime.length > 0) {
      selectionModeRef.value = "nearest_date";
      return nearestAnyTime.map((item) => item.session);
    }

    return sessions;
  })();

  const options = scopedSessions
    .map((session) => {
      const scoreData = matchScore(session, hint, expectedLocationId);
      const dateLabel = toLocalDateLabel(session.startAtUtc, session.timezone, locale);
      return {
        sessionId: session.id,
        label: session.title,
        dateLabel,
        teacher: session.teacherDisplayName || uiText(language, "admin.quote_transform.to_define"),
        seatsRemaining: session.seatsRemaining,
        status: session.statusLabel,
        score: scoreData.score,
        reasons: [
          ...scoreData.reasons,
          ...(selectionModeRef.value === "nearest_date_time" ? ["date la plus proche"] : []),
          ...(selectionModeRef.value === "nearest_date" ? ["date la plus proche (horaire approche)"] : []),
        ],
      } satisfies SessionMatchOption;
    })
    .sort((a, b) => b.score - a.score);

  if (scenario === "live") {
    return options;
  }

  if (scenario === "A") {
    if (options.length > 0) {
      return [options[0]];
    }
    return mockSessionOption(activityRow.activityName, activityRow.activityId, "single", language);
  }

  if (scenario === "B") {
    if (options.length >= 2) {
      return options.slice(0, 2);
    }
    if (options.length === 1) {
      return [options[0], ...mockSessionOption(activityRow.activityName, activityRow.activityId, "single", language)];
    }
    return mockSessionOption(activityRow.activityName, activityRow.activityId, "multi", language);
  }

  if (scenario === "C") {
    const normalizedName = normalizeText(activityRow.activityName);
    if (normalizedName.includes("solfege") || normalizedName.includes("collectif")) {
      return mockSessionOption(activityRow.activityName, activityRow.activityId, "none", language);
    }
    if (options.length > 0) {
      const first = { ...options[0], seatsRemaining: 0, score: options[0].score - 25 };
      return [first, ...options.slice(1, 2)];
    }
    return mockSessionOption(activityRow.activityName, activityRow.activityId, "full", language);
  }

  return options;
}

function billingRowTypeFromLine(line: QuoteTransformLine): string {
  const lineType = normalizeText(line.lineType);
  const masterItemType = normalizeText(line.masterItemType);
  if (lineType === "discount" || masterItemType === "discount_rule") {
    return "discount";
  }
  if (lineType === "surcharge" || masterItemType === "surcharge_rule") {
    return "surcharge";
  }
  if (masterItemType === "kit") {
    return "kit";
  }
  if (masterItemType === "option") {
    return "option";
  }
  if (masterItemType === "product") {
    return "product";
  }
  if (masterItemType === "activity") {
    return "service";
  }
  return line.lineCategory || line.lineType || "extra";
}

function rowStatusFromBilling(row: BillingExtraRow): QuoteTransformStatus {
  if (row.type === "discount") {
    if (row.amountTtc >= 0) {
      return "blocked";
    }
    if (row.vatRate < 0) {
      return "blocked";
    }
    return "ok";
  }
  if (row.amountTtc <= 0) {
    return "blocked";
  }
  if (row.vatRate < 0) {
    return "blocked";
  }
  if (row.vatRate === 0 && row.type !== "discount") {
    return "warning";
  }
  return "ok";
}

export function buildBillingExtraRows(
  lines: QuoteTransformLine[],
  activityRows: ActivityPricingRow[],
  offPlanningActivityIds: Set<string>,
  quote?: QuoteTransformQuote,
): BillingExtraRow[] {
  const explicitExtras = lines
    .filter((line) => !line.activityId)
    .map((line) => {
      const amountHt = Number(line.amountHt.toFixed(2));
      const amountTtc = Number(line.amountTtc.toFixed(2));
      const vatRate = Number(line.vatRate.toFixed(2));
      const amountVat = Number((amountTtc - amountHt).toFixed(2));
      const type = billingRowTypeFromLine(line);
      const row: BillingExtraRow = {
        rowId: `extra-${line.id}`,
        sourceLineId: line.id,
        type,
        label: line.title,
        amountHt,
        vatRate,
        amountVat,
        amountTtc,
        status: "ok",
        editable: true,
      };
      row.status = rowStatusFromBilling(row);
      return row;
    });

  const offPlanningRows = activityRows
    .filter((row) => offPlanningActivityIds.has(row.activityId))
    .map((row) => {
      const amountTtc = Number(row.expectedTtc.toFixed(2));
      const amountHt = Number((amountTtc / 1.2).toFixed(2));
      const extra: BillingExtraRow = {
        rowId: `off-planning-${row.activityId}`,
        sourceLineId: row.lineId,
        type: "off_planning_activity",
        label: `${row.activityName} (hors planning)`,
        amountHt,
        vatRate: 20,
        amountVat: Number((amountTtc - amountHt).toFixed(2)),
        amountTtc,
        status: "warning",
        editable: true,
      };
      extra.status = rowStatusFromBilling(extra);
      return extra;
    });

  const adjustment = quote?.financialAdjustment;
  const adjustmentAmount = Number(adjustment?.amountTtc ?? 0);
  const adjustmentRows: BillingExtraRow[] = [];
  if (adjustment && adjustment.type !== "none" && Number.isFinite(adjustmentAmount) && adjustmentAmount > 0) {
    const signedAmountTtc = adjustment.type === "credit" ? -adjustmentAmount : adjustmentAmount;
    const vatRate = Number.isFinite(adjustment.vatRate) && adjustment.vatRate >= 0 ? adjustment.vatRate : 0;
    const amountHt = vatRate > 0
      ? Number((signedAmountTtc / (1 + vatRate / 100)).toFixed(2))
      : Number(signedAmountTtc.toFixed(2));
    const row: BillingExtraRow = {
      rowId: "quote-financial-adjustment",
      sourceLineId: null,
      type: adjustment.type === "credit" ? "discount" : "surcharge",
      label: adjustment.label || "Ajustement financier du devis",
      amountHt,
      vatRate,
      amountVat: Number((signedAmountTtc - amountHt).toFixed(2)),
      amountTtc: Number(signedAmountTtc.toFixed(2)),
      status: "ok",
      editable: true,
    };
    row.status = rowStatusFromBilling(row);
    adjustmentRows.push(row);
  }

  return [...explicitExtras, ...offPlanningRows, ...adjustmentRows];
}

export function deriveScheduleHints(calendarSnapshot: Record<string, unknown>): Map<string, QuoteScheduleHint> {
  const hints = new Map<string, QuoteScheduleHint>();
  const blocksRaw = Array.isArray(calendarSnapshot.blocks) ? calendarSnapshot.blocks : [];
  for (const raw of blocksRaw) {
    const block = readObject(raw);
    if (!block) {
      continue;
    }
    const activityId = readString(block.activity_id);
    if (!activityId) {
      continue;
    }
    const startDateRaw = readString(block.start_date);
    const startTimeRaw = readString(block.start_time);
    const endTimeRaw = readString(block.end_time);
    const weekdayRaw = Number.parseInt(String(block.weekday ?? ""), 10);
    const startDate = isIsoDate(startDateRaw) ? startDateRaw : null;
    const weekdayFromBlock = Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6 ? weekdayRaw : null;
    const computedWeekday = startDate ? weekdayFromDateKey(startDate) : null;
    const candidate: QuoteScheduleHint = {
      activityId,
      startDate,
      weekday: weekdayFromBlock ?? computedWeekday,
      startTime: isHhmm(startTimeRaw) ? startTimeRaw : null,
      endTime: isHhmm(endTimeRaw) ? endTimeRaw : null,
    };
    const existing = hints.get(activityId);
    if (!existing) {
      hints.set(activityId, candidate);
      continue;
    }
    if (candidate.startDate && (!existing.startDate || candidate.startDate < existing.startDate)) {
      hints.set(activityId, candidate);
      continue;
    }
    if (
      candidate.startDate
      && existing.startDate
      && candidate.startDate === existing.startDate
      && !existing.startTime
      && candidate.startTime
    ) {
      hints.set(activityId, { ...existing, startTime: candidate.startTime, endTime: candidate.endTime });
    }
  }

  const sessionsRaw = Array.isArray(calendarSnapshot.sessions) ? calendarSnapshot.sessions : [];
  for (const raw of sessionsRaw) {
    const session = readObject(raw);
    if (!session) {
      continue;
    }
    const activityId = readString(session.activity_id);
    if (!activityId) {
      continue;
    }
    const isoDate = readString(session.date);
    const startTime = readString(session.start_time);
    const endTime = readString(session.end_time);

    let weekday: number | null = null;
    if (isoDate) {
      const parsed = new Date(`${isoDate}T00:00:00Z`);
      if (!Number.isNaN(parsed.getTime())) {
        const day = parsed.getUTCDay();
        weekday = day === 0 ? 6 : day - 1;
      }
    }

    const existing = hints.get(activityId);
    if (!existing) {
      hints.set(activityId, {
        activityId,
        startDate: isIsoDate(isoDate) ? isoDate : null,
        weekday,
        startTime: isHhmm(startTime) ? startTime : null,
        endTime: isHhmm(endTime) ? endTime : null,
      });
      continue;
    }

    if (!existing.startDate && isIsoDate(isoDate)) {
      existing.startDate = isoDate;
    }
    if (existing.weekday === null && weekday !== null) {
      existing.weekday = weekday;
    }
    if (!existing.startTime && isHhmm(startTime)) {
      existing.startTime = startTime;
    }
    if (!existing.endTime && isHhmm(endTime)) {
      existing.endTime = endTime;
    }
    hints.set(activityId, existing);
  }
  return hints;
}

export function deriveActivityLocationNameById(calendarSnapshot: Record<string, unknown>): Map<string, string> {
  const output = new Map<string, string>();

  const feed = (items: unknown[]): void => {
    for (const raw of items) {
      const row = readObject(raw);
      if (!row) {
        continue;
      }
      const activityId = readString(row.activity_id);
      if (!activityId || output.has(activityId)) {
        continue;
      }
      const locationLabel = readString(row.location_label);
      if (locationLabel) {
        output.set(activityId, locationLabel);
        continue;
      }
      const locationId = readString(row.location_id);
      if (locationId) {
        output.set(activityId, locationId);
      }
    }
  };

  const blocksRaw = Array.isArray(calendarSnapshot.blocks) ? calendarSnapshot.blocks : [];
  const sessionsRaw = Array.isArray(calendarSnapshot.sessions) ? calendarSnapshot.sessions : [];
  feed(blocksRaw);
  feed(sessionsRaw);

  return output;
}

export function deriveActivityLocationIdById(calendarSnapshot: Record<string, unknown>): Map<string, string> {
  const output = new Map<string, string>();

  const feed = (items: unknown[]): void => {
    for (const raw of items) {
      const row = readObject(raw);
      if (!row) {
        continue;
      }
      const activityId = readString(row.activity_id);
      const locationId = readString(row.location_id);
      if (!activityId || !locationId || output.has(activityId)) {
        continue;
      }
      output.set(activityId, locationId);
    }
  };

  const blocksRaw = Array.isArray(calendarSnapshot.blocks) ? calendarSnapshot.blocks : [];
  const sessionsRaw = Array.isArray(calendarSnapshot.sessions) ? calendarSnapshot.sessions : [];
  feed(blocksRaw);
  feed(sessionsRaw);

  return output;
}

export function sumBillingRows(rows: BillingExtraRow[]): { totalHt: number; totalTtc: number } {
  return rows.reduce(
    (acc, row) => ({
      totalHt: Number((acc.totalHt + row.amountHt).toFixed(2)),
      totalTtc: Number((acc.totalTtc + row.amountTtc).toFixed(2)),
    }),
    { totalHt: 0, totalTtc: 0 },
  );
}

export function evaluateFinancialStatus(expectedTtc: number, systemTtc: number): { deltaTtc: number; status: QuoteTransformStatus } {
  const deltaTtc = Number((systemTtc - expectedTtc).toFixed(2));
  const absDelta = Math.abs(deltaTtc);
  if (absDelta <= 1) {
    return { deltaTtc, status: "ok" };
  }
  if (absDelta <= 15) {
    return { deltaTtc, status: "warning" };
  }
  return { deltaTtc, status: "blocked" };
}

export function summarizeStatus(statuses: QuoteTransformStatus[]): QuoteTransformStatus {
  if (statuses.includes("blocked")) {
    return "blocked";
  }
  if (statuses.includes("warning")) {
    return "warning";
  }
  return "ok";
}

type QuickStepBucket = {
  ok: string[];
  warnings: string[];
  blocked: string[];
};

function createQuickStepBuckets(): Record<QuoteTransformStep, QuickStepBucket> {
  return {
    1: { ok: [], warnings: [], blocked: [] },
    2: { ok: [], warnings: [], blocked: [] },
    3: { ok: [], warnings: [], blocked: [] },
    4: { ok: [], warnings: [], blocked: [] },
    5: { ok: [], warnings: [], blocked: [] },
  };
}

function findBestPlanFromQuoteType(plans: QuoteTransformPlan[], quoteTypeFormulaName: string | null): QuoteTransformPlan | null {
  const normalizedFormula = normalizeText(quoteTypeFormulaName);
  if (!normalizedFormula) {
    return null;
  }
  return plans.find((plan) => normalizeText(plan.name) === normalizedFormula) || null;
}

export function analyzeQuoteQuickTransformStatus(input: QuoteQuickTransformAnalysisInput): QuoteQuickTransformAnalysis {
  const scenario = input.scenario || "live";
  const steps = createQuickStepBuckets();

  const pushOk = (step: QuoteTransformStep, message: string): void => {
    steps[step].ok.push(message);
  };
  const pushWarning = (step: QuoteTransformStep, message: string): void => {
    steps[step].warnings.push(message);
  };
  const pushBlocked = (step: QuoteTransformStep, message: string): void => {
    steps[step].blocked.push(message);
  };

  const clientsById = new Map(input.clients.map((client) => [client.id, client]));
  const activitiesById = new Map(input.activities.map((activity) => [activity.id, activity]));

  const linkedClient = input.quote.clientId ? clientsById.get(input.quote.clientId) || null : null;
  const clientCandidates = buildClientMatchCandidates(input.prospect, input.clients, scenario);

  let proposedClient: QuoteQuickTransformProposedClient | null = null;
  if (linkedClient) {
    proposedClient = {
      clientId: linkedClient.id,
      displayName: displayName(linkedClient.firstName, linkedClient.lastName, linkedClient.email),
      confidence: 100,
      confidenceLabel: "fort",
      source: "quote_client_link",
    };
    pushOk(1, "Client cible deja lie au devis.");
  } else {
    const best = clientCandidates[0] || null;
    const second = clientCandidates[1] || null;
    if (!best || best.confidence < 55) {
      pushBlocked(1, "Aucun client fiable identifie.");
    } else {
      const isAmbiguous = Boolean(second && second.confidence >= 70 && Math.abs(best.confidence - second.confidence) <= 10);
      proposedClient = {
        clientId: best.clientId,
        displayName: best.displayName,
        confidence: best.confidence,
        confidenceLabel: best.confidenceLabel,
        source: "matching",
      };
      if (isAmbiguous) {
        pushWarning(1, "Plusieurs correspondances client probables necessitent un arbitrage.");
      } else if (best.confidence < 80) {
        pushWarning(1, "Correspondance client detectee mais confiance moyenne.");
      } else {
        pushOk(1, "Client cible identifie sans ambiguite.");
      }
    }
  }

  const plan = findBestPlanFromQuoteType(input.plans, input.quote.quoteTypeFormulaName);
  if (!plan) {
    pushBlocked(2, "Formule / plan non mappe depuis le type de devis.");
  } else {
    pushOk(2, `Formule detectee: ${plan.name}.`);
  }

  const activityLocationNameById = deriveActivityLocationNameById(input.calendarSnapshot);
  const activityLocationIdById = deriveActivityLocationIdById(input.calendarSnapshot);
  const activityRows = buildActivityPricingRows(
    input.lines,
    activitiesById,
    activityLocationNameById,
    input.quote.locationName,
    scenario,
  );

  if (activityRows.length === 0) {
    pushWarning(2, "Aucune activite planifiable detectee sur le devis.");
  }

  let priceOkCount = 0;
  let priceWarningCount = 0;
  let priceBlockedCount = 0;
  for (const row of activityRows) {
    if (!activitiesById.has(row.activityId)) {
      priceBlockedCount += 1;
      pushBlocked(2, `${row.activityName}: activite non mappee dans le referentiel.`);
      continue;
    }
    if (row.status === "blocked") {
      priceBlockedCount += 1;
      pushBlocked(2, `${row.activityName}: ecart tarifaire critique (${row.deltaTtc.toFixed(2)}).`);
      continue;
    }
    if (row.status === "warning") {
      priceWarningCount += 1;
      pushWarning(2, `${row.activityName}: ecart tarifaire mineur (${row.deltaTtc.toFixed(2)}).`);
      continue;
    }
    priceOkCount += 1;
  }

  const scheduleHints = deriveScheduleHints(input.calendarSnapshot);
  const proposedScheduleAssignments: QuoteQuickTransformProposedScheduleAssignment[] = [];
  let slotsFoundCount = 0;
  let autoAssignableCount = 0;

  for (const row of activityRows) {
    const sessions = input.sessionsByActivityId[row.activityId] || [];
    const expectedLocationId = activityLocationIdById.get(row.activityId) || input.quote.locationId;
    const options = buildSessionMatches(row, sessions, expectedLocationId, scheduleHints, scenario);
    if (options.length > 0) {
      slotsFoundCount += 1;
    }
    if (options.length === 0) {
      pushBlocked(3, `${row.activityName}: aucun creneau coherent trouve.`);
      proposedScheduleAssignments.push({
        activityId: row.activityId,
        activityName: row.activityName,
        status: "missing",
        sessionId: null,
        sessionLabel: "-",
        seatsRemaining: null,
        warning: "Aucun creneau",
      });
      continue;
    }

    const available = options.filter((option) => option.seatsRemaining > 0);
    if (available.length === 0) {
      const first = options[0];
      pushBlocked(3, `${row.activityName}: creneau complet sans alternative.`);
      proposedScheduleAssignments.push({
        activityId: row.activityId,
        activityName: row.activityName,
        status: "full",
        sessionId: first?.sessionId || null,
        sessionLabel: first?.label || "-",
        seatsRemaining: 0,
        warning: "Complet",
      });
      continue;
    }

    const recommended = available[0];
    if (available.length === 1) {
      autoAssignableCount += 1;
      pushOk(3, `${row.activityName}: creneau unique auto-assignable.`);
      proposedScheduleAssignments.push({
        activityId: row.activityId,
        activityName: row.activityName,
        status: "auto_assigned",
        sessionId: recommended.sessionId,
        sessionLabel: `${recommended.label} · ${recommended.dateLabel}`,
        seatsRemaining: recommended.seatsRemaining,
        warning: null,
      });
    } else {
      pushWarning(3, `${row.activityName}: plusieurs creneaux possibles, recommandation disponible.`);
      proposedScheduleAssignments.push({
        activityId: row.activityId,
        activityName: row.activityName,
        status: "choice_required",
        sessionId: recommended.sessionId,
        sessionLabel: `${recommended.label} · ${recommended.dateLabel}`,
        seatsRemaining: recommended.seatsRemaining,
        warning: "Choix manuel requis",
      });
    }
  }

  const offPlanningActivityIds = new Set<string>();
  const billingRows = buildBillingExtraRows(input.lines, activityRows, offPlanningActivityIds, input.quote);
  if (billingRows.length === 0) {
    pushOk(4, "Aucune ligne hors planning a reprendre.");
  }
  for (const row of billingRows) {
    if (row.status === "blocked") {
      pushBlocked(4, `${row.label}: ligne hors planning invalide.`);
    } else if (row.status === "warning") {
      pushWarning(4, `${row.label}: ligne hors planning a confirmer.`);
    } else {
      pushOk(4, `${row.label}: ligne hors planning coherente.`);
    }
  }

  const scheduledActivitiesTotal = activityRows.reduce((sum, row) => Number((sum + row.currentSystemTtc).toFixed(2)), 0);
  const billingTotals = sumBillingRows(billingRows);
  const systemTotalTtc = Number((scheduledActivitiesTotal + billingTotals.totalTtc).toFixed(2));
  const financial = evaluateFinancialStatus(input.quote.totalTtc, systemTotalTtc);

  if (financial.status === "blocked") {
    pushBlocked(5, `Total devis/systeme incoherent (${financial.deltaTtc.toFixed(2)}).`);
  } else if (financial.status === "warning") {
    pushWarning(5, `Ecart financier mineur a confirmer (${financial.deltaTtc.toFixed(2)}).`);
  } else {
    pushOk(5, "Totaux HT/TTC conformes.");
  }

  if (!input.followupId) {
    pushWarning(5, "Follow-up absent: verification manuelle recommandee.");
  } else {
    pushOk(5, "Follow-up disponible pour journalisation.");
  }

  if (String(input.quote.status || "").trim().toLowerCase() !== "approved") {
    pushBlocked(5, "Validation client du devis requise avant transformation.");
  }

  const reasonsOk: string[] = [];
  const warnings: string[] = [];
  const blockingIssues: string[] = [];
  for (const step of [1, 2, 3, 4, 5] as const) {
    reasonsOk.push(...steps[step].ok);
    warnings.push(...steps[step].warnings);
    blockingIssues.push(...steps[step].blocked);
  }

  const firstNonConformStep =
    ([1, 2, 3, 4, 5] as const).find((step) => steps[step].blocked.length > 0 || steps[step].warnings.length > 0) || null;

  const baseStatus: QuoteQuickTransformStatus =
    blockingIssues.length > 0 ? "blocked" : warnings.length > 0 ? "review_required" : "auto_validable";

  const priceExpectedTotal = Number(activityRows.reduce((sum, row) => sum + row.expectedTtc, 0).toFixed(2));
  const priceSystemTotal = Number(activityRows.reduce((sum, row) => sum + row.currentSystemTtc, 0).toFixed(2));
  const priceDelta = Number((priceSystemTotal - priceExpectedTotal).toFixed(2));

  const createSuggestedDraft = (
    candidateClient: QuoteQuickTransformProposedClient | null,
    candidatePlan: QuoteTransformPlan | null,
    scheduleAssignments: QuoteQuickTransformProposedScheduleAssignment[],
  ): QuoteToEnrollmentDraft | null => {
    if (!candidateClient || !candidatePlan) {
      return null;
    }
    const assignedSessionByActivityId: Record<string, string> = {};
    for (const assignment of scheduleAssignments) {
      if (assignment.status === "auto_assigned" && assignment.sessionId) {
        assignedSessionByActivityId[assignment.activityId] = assignment.sessionId;
      }
    }
    const draftRows = billingRows.map((row) => ({
      rowId: row.rowId,
      type: row.type,
      label: row.label,
      amountHt: Number(row.amountHt.toFixed(2)),
      vatRate: Number(row.vatRate.toFixed(2)),
      amountTtc: Number(row.amountTtc.toFixed(2)),
    }));
    const idempotencyKey = buildIdempotencyKey({
      quoteId: input.quote.id,
      scenario,
      clientMode: "existing",
      selectedClientId: candidateClient.clientId,
      selectedPlanId: candidatePlan.id,
      assignedSessionByActivityId,
      billingRows: draftRows.map((row) => ({ rowId: row.rowId, amountTtc: row.amountTtc })),
    });

    return {
      version: 1,
      scenario,
      currentStep: 5,
      clientResolution: {
        mode: "existing",
        selectedClientId: candidateClient.clientId,
        selectedParentClientId: null,
        notes: "Validation rapide auto (analyse serveur).",
      },
      activityResolution: {
        planId: candidatePlan.id,
        alignedActivityIds: [],
        offPlanningActivityIds: [],
      },
      scheduleResolution: {
        assignedSessionByActivityId,
      },
      billingResolution: {
        rows: draftRows,
      },
      acceptedBlockingIssueIds: [],
      financialControl: {
        expectedTtc: input.quote.totalTtc,
        systemTtc: systemTotalTtc,
        deltaTtc: financial.deltaTtc,
      },
      idempotencyKey,
      logs: [
        {
          at: new Date().toISOString(),
          action: "quote_quick_transform_analysis",
          detail: `status=${baseStatus} activities=${activityRows.length} auto_slots=${autoAssignableCount}`,
        },
      ],
      finalizedAt: null,
    };
  };

  let finalStatus = baseStatus;
  let finalReasonsOk = reasonsOk.slice();
  let finalWarnings = warnings.slice();
  let finalBlockingIssues = blockingIssues.slice();
  let finalProposedClient = proposedClient;
  let finalProposedScheduleAssignments = proposedScheduleAssignments.slice();
  let finalFirstNonConformStep = firstNonConformStep;
  let finalSuggestedDraft = createSuggestedDraft(finalProposedClient, plan, finalProposedScheduleAssignments);
  let finalCanQuickTransform = finalStatus === "auto_validable" && Boolean(finalSuggestedDraft);

  if (scenario === "A") {
    if (!finalProposedClient) {
      const fallbackCandidate = clientCandidates[0];
      if (fallbackCandidate) {
        finalProposedClient = {
          clientId: fallbackCandidate.clientId,
          displayName: fallbackCandidate.displayName,
          confidence: fallbackCandidate.confidence,
          confidenceLabel: fallbackCandidate.confidenceLabel,
          source: "matching",
        };
      } else if (input.clients[0]) {
        const client = input.clients[0];
        finalProposedClient = {
          clientId: client.id,
          displayName: displayName(client.firstName, client.lastName, client.email),
          confidence: 90,
          confidenceLabel: "fort",
          source: "matching",
        };
      }
    }

    if (finalProposedScheduleAssignments.length === 0 && activityRows.length > 0) {
      finalProposedScheduleAssignments = activityRows.map((row) => ({
        activityId: row.activityId,
        activityName: row.activityName,
        status: "auto_assigned",
        sessionId: `demo-${row.activityId}`,
        sessionLabel: `${row.activityName} · Creneau recommande`,
        seatsRemaining: 3,
        warning: null,
      }));
    } else {
      finalProposedScheduleAssignments = finalProposedScheduleAssignments.map((assignment) => ({
        ...assignment,
        status: "auto_assigned",
        sessionId: assignment.sessionId || `demo-${assignment.activityId}`,
        sessionLabel: assignment.sessionLabel === "-" ? `${assignment.activityName} · Creneau recommande` : assignment.sessionLabel,
        seatsRemaining: assignment.seatsRemaining && assignment.seatsRemaining > 0 ? assignment.seatsRemaining : 3,
        warning: null,
      }));
    }

    finalWarnings = [];
    finalBlockingIssues = [];
    finalStatus = "auto_validable";
    finalFirstNonConformStep = null;
    finalReasonsOk = [...finalReasonsOk, "Scenario A: parcours simple auto-validable (demo localhost)."];

    const planForScenarioA = plan || input.plans.find((candidate) => candidate.active) || input.plans[0] || null;
    finalSuggestedDraft = createSuggestedDraft(finalProposedClient, planForScenarioA, finalProposedScheduleAssignments);
    finalCanQuickTransform = Boolean(finalSuggestedDraft);
  }

  if (scenario === "B") {
    finalStatus = "review_required";
    finalBlockingIssues = [];
    finalSuggestedDraft = null;
    finalCanQuickTransform = false;
    finalFirstNonConformStep = finalFirstNonConformStep || 1;
    if (finalWarnings.length === 0) {
      finalWarnings = ["Scenario B: verification manuelle recommandee (demo localhost)."];
    }
    if (finalProposedScheduleAssignments.length > 0 && !finalProposedScheduleAssignments.some((item) => item.status === "choice_required")) {
      const [first, ...rest] = finalProposedScheduleAssignments;
      finalProposedScheduleAssignments = [
        {
          ...first,
          status: "choice_required",
          warning: "Choix manuel requis",
          seatsRemaining: first.seatsRemaining && first.seatsRemaining > 0 ? first.seatsRemaining : 2,
        },
        ...rest,
      ];
    }
  }

  if (scenario === "C") {
    finalStatus = "blocked";
    finalCanQuickTransform = false;
    finalSuggestedDraft = null;
    finalFirstNonConformStep = finalFirstNonConformStep || 3;
    if (finalBlockingIssues.length === 0) {
      finalBlockingIssues = ["Scenario C: blocage critique simule (demo localhost)."];
    }
    if (finalProposedScheduleAssignments.length > 0 && !finalProposedScheduleAssignments.some((item) => item.status === "missing" || item.status === "full")) {
      const [first, ...rest] = finalProposedScheduleAssignments;
      finalProposedScheduleAssignments = [
        {
          ...first,
          status: "missing",
          sessionId: null,
          sessionLabel: "-",
          seatsRemaining: null,
          warning: "Aucun creneau",
        },
        ...rest,
      ];
    }
  }

  return {
    status: finalStatus,
    reasonsOk: finalReasonsOk,
    warnings: finalWarnings,
    blockingIssues: finalBlockingIssues,
    proposedClient: finalProposedClient,
    proposedScheduleAssignments: finalProposedScheduleAssignments,
    priceMatchSummary: {
      activitiesCount: activityRows.length,
      okCount: priceOkCount,
      warningCount: priceWarningCount,
      blockedCount: priceBlockedCount,
      expectedTotalTtc: priceExpectedTotal,
      systemTotalTtc: priceSystemTotal,
      deltaTtc: priceDelta,
    },
    financialMatchSummary: {
      expectedTtc: input.quote.totalTtc,
      systemTtc: systemTotalTtc,
      deltaTtc: financial.deltaTtc,
      status: financial.status,
    },
    summary: {
      activitiesCount: activityRows.length,
      slotsFoundCount,
      autoAssignableCount,
      offPlanningCount: offPlanningActivityIds.size,
      totalQuoteTtc: input.quote.totalTtc,
      totalSystemTtc: systemTotalTtc,
    },
    canQuickTransform: finalCanQuickTransform,
    firstNonConformStep: finalFirstNonConformStep,
    suggestedDraft: finalSuggestedDraft,
  };
}

export function buildIdempotencyKey(input: {
  quoteId: string;
  scenario: QuoteTransformScenario;
  clientMode: string;
  selectedClientId: string | null;
  selectedPlanId: string | null;
  assignedSessionByActivityId: Record<string, string>;
  billingRows: Array<{ rowId: string; amountTtc: number }>;
}): string {
  const assignments = Object.entries(input.assignedSessionByActivityId)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([activityId, sessionId]) => `${activityId}:${sessionId}`)
    .join(",");
  const billing = input.billingRows
    .slice()
    .sort((a, b) => a.rowId.localeCompare(b.rowId))
    .map((row) => `${row.rowId}:${row.amountTtc.toFixed(2)}`)
    .join(",");

  return [
    input.quoteId,
    input.scenario,
    input.clientMode,
    input.selectedClientId || "new",
    input.selectedPlanId || "no-plan",
    assignments || "no-sessions",
    billing || "no-billing",
  ].join("|");
}

export function coerceQuoteToEnrollmentDraft(raw: unknown): QuoteToEnrollmentDraft | null {
  const root = readObject(raw);
  if (!root) {
    return null;
  }

  const scenarioRaw = readString(root.scenario).toUpperCase();
  const scenario: QuoteTransformScenario =
    scenarioRaw === "A" || scenarioRaw === "B" || scenarioRaw === "C" ? scenarioRaw : "live";

  const currentStepRaw = readNumber(root.currentStep, 1);
  const currentStep = ([1, 2, 3, 4, 5] as const).includes(currentStepRaw as QuoteTransformStep)
    ? (currentStepRaw as QuoteTransformStep)
    : 1;

  const clientResolutionRaw = readObject(root.clientResolution) || {};
  const modeRaw = readString(clientResolutionRaw.mode);
  const mode =
    modeRaw === "existing" || modeRaw === "new_parent_child" || modeRaw === "new_child_existing_parent"
      ? modeRaw
      : "new_adult";

  const activityResolutionRaw = readObject(root.activityResolution) || {};
  const scheduleResolutionRaw = readObject(root.scheduleResolution) || {};
  const billingResolutionRaw = readObject(root.billingResolution) || {};
  const financialControlRaw = readObject(root.financialControl) || {};

  const acceptedRaw = Array.isArray(root.acceptedBlockingIssueIds) ? root.acceptedBlockingIssueIds : [];
  const acceptedBlockingIssueIds = acceptedRaw
    .map((value) => readString(value))
    .filter(Boolean);

  const alignedRaw = Array.isArray(activityResolutionRaw.alignedActivityIds) ? activityResolutionRaw.alignedActivityIds : [];
  const offPlanningRaw = Array.isArray(activityResolutionRaw.offPlanningActivityIds) ? activityResolutionRaw.offPlanningActivityIds : [];

  const rowsRaw = Array.isArray(billingResolutionRaw.rows) ? billingResolutionRaw.rows : [];
  const rows: QuoteToEnrollmentBillingDraftRow[] = rowsRaw
    .map((item, index) => ({ item: readObject(item), index }))
    .filter((entry): entry is { item: Record<string, unknown>; index: number } => Boolean(entry.item))
    .map((entry) => ({
      rowId: readString(entry.item.rowId) || `row-${entry.index + 1}`,
      type: readString(entry.item.type) || "extra",
      label: readString(entry.item.label) || "Ligne",
      amountHt: readNumber(entry.item.amountHt, 0),
      vatRate: readNumber(entry.item.vatRate, 20),
      amountTtc: readNumber(entry.item.amountTtc, 0),
    }));

  const assignedRaw = readObject(scheduleResolutionRaw.assignedSessionByActivityId) || {};
  const assignedSessionByActivityId: Record<string, string> = {};
  for (const [key, value] of Object.entries(assignedRaw)) {
    const normalizedKey = readString(key);
    const normalizedValue = readString(value);
    if (!normalizedKey || !normalizedValue) {
      continue;
    }
    assignedSessionByActivityId[normalizedKey] = normalizedValue;
  }

  const logsRaw = Array.isArray(root.logs) ? root.logs : [];
  const logs: QuoteToEnrollmentLogEntry[] = logsRaw
    .map((item) => readObject(item))
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .map((item) => ({
      at: readString(item.at) || new Date().toISOString(),
      action: readString(item.action) || "draft",
      detail: readString(item.detail) || "",
    }));

  return {
    version: 1,
    scenario,
    currentStep,
    clientResolution: {
      mode,
      selectedClientId: readString(clientResolutionRaw.selectedClientId) || null,
      selectedParentClientId: readString(clientResolutionRaw.selectedParentClientId) || null,
      notes: readString(clientResolutionRaw.notes),
    },
    activityResolution: {
      planId: readString(activityResolutionRaw.planId) || null,
      alignedActivityIds: alignedRaw.map((value) => readString(value)).filter(Boolean),
      offPlanningActivityIds: offPlanningRaw.map((value) => readString(value)).filter(Boolean),
    },
    scheduleResolution: {
      assignedSessionByActivityId,
    },
    billingResolution: {
      rows,
    },
    acceptedBlockingIssueIds,
    financialControl: {
      expectedTtc: readNumber(financialControlRaw.expectedTtc, 0),
      systemTtc: readNumber(financialControlRaw.systemTtc, 0),
      deltaTtc: readNumber(financialControlRaw.deltaTtc, 0),
    },
    idempotencyKey: readString(root.idempotencyKey),
    logs,
    finalizedAt: readString(root.finalizedAt) || null,
  };
}
