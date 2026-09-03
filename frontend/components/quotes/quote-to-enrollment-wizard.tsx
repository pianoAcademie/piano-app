"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import ConfirmSubmitButton from "../confirm-submit-button";
import {
  buildActivityPricingRows,
  buildBillingExtraRows,
  buildClientMatchCandidates,
  buildIdempotencyKey,
  buildSessionMatches,
  coerceQuoteToEnrollmentDraft,
  deriveActivityLocationIdById,
  deriveActivityLocationNameById,
  deriveScheduleSessionCounts,
  deriveScheduleHints,
  displayName,
  evaluateFinancialStatus,
  quoteTransformConfidenceLabel,
  quoteTransformStatusLabel,
  sumBillingRows,
  summarizeStatus,
  translateQuoteTransformMessage,
  type BillingExtraRow,
  type QuoteTransformClientResolutionMode,
  type QuoteToEnrollmentDraft,
  type QuoteToEnrollmentSeriesAssignment,
  type QuoteTransformActivityCatalog,
  type QuoteTransformClient,
  type QuoteTransformLegalEntity,
  type QuoteTransformLine,
  type QuoteTransformPlan,
  type QuoteTransformProspect,
  type QuoteTransformQuote,
  type QuoteTransformScenario,
  type QuoteTransformSession,
  type QuoteTransformStatus,
  type SessionMatchOption,
  type StepIssue,
} from "../../lib/quote-transformation";
import { localeForUiLanguage, type UiLanguage, uiText } from "../../lib/ui-i18n";

type ScenarioLink = {
  scenario: QuoteTransformScenario;
  label: string;
  href: string;
  active: boolean;
};

type QuoteToEnrollmentWizardProps = {
  quote: QuoteTransformQuote;
  prospect: QuoteTransformProspect | null;
  lines: QuoteTransformLine[];
  calendarSnapshot: Record<string, unknown>;
  clients: QuoteTransformClient[];
  activities: QuoteTransformActivityCatalog[];
  sessionsByActivityId: Record<string, QuoteTransformSession[]>;
  plans: QuoteTransformPlan[];
  legalEntities: QuoteTransformLegalEntity[];
  scenario: QuoteTransformScenario;
  scenarioLinks: ScenarioLink[];
  preferredStep?: 1 | 2 | 3 | 4 | 5 | null;
  followupId: string | null;
  followupStatus: string | null;
  initialDraft: QuoteToEnrollmentDraft | null;
  backPath: string;
  returnTo: string;
  saveDraftAction: (formData: FormData) => Promise<void>;
  finalizeAction: (formData: FormData) => Promise<void>;
  language?: UiLanguage;
};

type QuotePlanningContext = {
  activity: string;
  quantity: string;
  slot: string;
  location: string;
};

function statusLabel(status: QuoteTransformStatus, language: UiLanguage): string {
  return quoteTransformStatusLabel(status, language);
}

function statusClassName(status: QuoteTransformStatus): string {
  if (status === "ok") {
    return "status-ok";
  }
  if (status === "warning") {
    return "status-warn";
  }
  return "quote-transform-status-blocked";
}

function currency(value: number, code: string, language: UiLanguage): string {
  if (!Number.isFinite(value)) {
    return `${value} ${code}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), { style: "currency", currency: code || "EUR" }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(code || "EUR").toUpperCase()}`;
  }
}

function isSupportedStep(step: number): step is 1 | 2 | 3 | 4 | 5 {
  return step === 1 || step === 2 || step === 3 || step === 4 || step === 5;
}

function billingStatus(row: BillingExtraRow): QuoteTransformStatus {
  if (row.type === "discount") {
    if (row.amountTtc >= 0 || row.vatRate < 0) {
      return "blocked";
    }
    return "ok";
  }
  if (row.amountTtc < 0 || row.vatRate < 0) {
    return "blocked";
  }
  if (row.vatRate === 0) {
    return "warning";
  }
  return "ok";
}

function normalizeClientSearch(value: string | null | undefined): string {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function hasSamePersonName(
  left: { firstName: string | null; lastName: string | null },
  right: { firstName: string | null; lastName: string | null },
): boolean {
  const leftFirst = normalizeClientSearch(left.firstName);
  const leftLast = normalizeClientSearch(left.lastName);
  const rightFirst = normalizeClientSearch(right.firstName);
  const rightLast = normalizeClientSearch(right.lastName);
  return Boolean(leftFirst && leftLast && leftFirst === rightFirst && leftLast === rightLast);
}

function isPlaceholderClientEmail(email: string | null | undefined): boolean {
  return String(email || "").toLowerCase().endsWith("@no-email.local");
}

function clientOptionLabel(client: QuoteTransformClient): string {
  const name = displayName(client.firstName, client.lastName, client.email);
  const contacts = [
    isPlaceholderClientEmail(client.email) ? "" : client.email,
    client.mobilePhone1 || client.phone || client.homePhone || "",
    client.familyName || "",
  ].filter(Boolean);
  return contacts.length > 0 ? `${name} · ${contacts.join(" · ")}` : name;
}

function clientSearchHaystack(client: QuoteTransformClient): string {
  return normalizeClientSearch([
    client.firstName,
    client.lastName,
    client.email,
    client.mobilePhone1,
    client.mobilePhone2,
    client.phone,
    client.homePhone,
    client.familyName,
    client.clientKind,
    client.clientStatus,
  ].filter(Boolean).join(" "));
}

function sortClientsByName(clients: QuoteTransformClient[]): QuoteTransformClient[] {
  return clients.slice().sort((left, right) => {
    const leftKey = normalizeClientSearch(`${left.lastName || ""} ${left.firstName || ""} ${left.email || ""}`);
    const rightKey = normalizeClientSearch(`${right.lastName || ""} ${right.firstName || ""} ${right.email || ""}`);
    return leftKey.localeCompare(rightKey, "fr");
  });
}

function primaryClientPhone(client: QuoteTransformClient | null): string {
  if (!client) {
    return "";
  }
  return client.mobilePhone1 || client.phone || client.homePhone || client.mobilePhone2 || "";
}

function canProceedFromStep(step: number, status: QuoteTransformStatus): boolean {
  if (step === 5) {
    return true;
  }
  return status !== "blocked";
}

function selectedSessionLabel(options: SessionMatchOption[], selectedSessionId: string | null, language: UiLanguage): string {
  if (!selectedSessionId) {
    return uiText(language, "admin.quote_transform.none");
  }
  const selected = options.find((option) => option.sessionId === selectedSessionId);
  if (!selected) {
    return uiText(language, "admin.quote_transform.none");
  }
  return `${selected.label} (${selected.dateLabel} · ${selected.locationName})`;
}

function defaultSessionAssignment(
  row: { activityId: string },
  options: SessionMatchOption[],
  scenario: QuoteTransformScenario,
): string | null {
  const approvedSelection = options.find(
    (option) => option.status.toUpperCase() === "SCHEDULED" && option.approvedQuoteSelection === true,
  );
  if (approvedSelection) {
    return approvedSelection.sessionId;
  }
  const firstUsable = options.find((option) => option.status.toUpperCase() === "SCHEDULED" && option.seatsRemaining > 0);
  const shouldAutoAssign = scenario === "A" || options.length === 1;
  return shouldAutoAssign && firstUsable ? firstUsable.sessionId : null;
}

function formatQuantity(value: number, unit: string, language: UiLanguage): string {
  const safeValue = Number.isFinite(value) ? value : 0;
  const formatted = new Intl.NumberFormat(localeForUiLanguage(language), { maximumFractionDigits: 2 }).format(safeValue);
  return unit ? `${formatted} ${unit}` : formatted;
}

function formatScheduleHint(
  hint: { startDate: string | null; weekday: number | null; startTime: string | null; endTime: string | null } | null,
  language: UiLanguage,
): string {
  if (!hint) {
    return uiText(language, "admin.quote_transform.none");
  }
  const weekdayLabels = language === "en"
    ? ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    : ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
  const dateLabel = hint.startDate
    ? new Intl.DateTimeFormat(localeForUiLanguage(language), { day: "2-digit", month: "2-digit" }).format(new Date(`${hint.startDate}T00:00:00Z`))
    : "";
  const weekdayLabel = hint.weekday !== null && hint.weekday >= 0 && hint.weekday <= 6 ? weekdayLabels[hint.weekday] : "";
  const timeLabel = [hint.startTime, hint.endTime].filter(Boolean).join("-");
  const parts = [weekdayLabel || dateLabel, timeLabel].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : uiText(language, "admin.quote_transform.none");
}

function normalizeComparable(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export default function QuoteToEnrollmentWizard({
  quote,
  prospect,
  lines,
  calendarSnapshot,
  clients,
  activities,
  sessionsByActivityId,
  plans,
  legalEntities,
  scenario,
  scenarioLinks,
  preferredStep = null,
  followupId,
  followupStatus,
  initialDraft,
  backPath,
  returnTo,
  saveDraftAction,
  finalizeAction,
  language = "fr",
}: QuoteToEnrollmentWizardProps): JSX.Element {
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const restoredDraft = useMemo(() => (initialDraft ? coerceQuoteToEnrollmentDraft(initialDraft) : null), [initialDraft]);
  const activitiesById = useMemo(() => new Map(activities.map((activity) => [activity.id, activity])), [activities]);
  const clientsById = useMemo(() => new Map(clients.map((client) => [client.id, client])), [clients]);
  const clientCandidates = useMemo(
    () => buildClientMatchCandidates(prospect, clients, scenario),
    [prospect, clients, scenario],
  );
  const bestClientCandidate = clientCandidates[0] || null;
  const bestCandidateClient = bestClientCandidate ? clientsById.get(bestClientCandidate.clientId) || null : null;
  const linkedQuoteClient = quote.clientId ? clientsById.get(quote.clientId) || null : null;
  const linkedQuoteClientKind = String(linkedQuoteClient?.clientKind || "").toUpperCase();
  const quoteOwnerType = prospect?.prospectType
    ?? (linkedQuoteClientKind === "CHILD" ? "child" : linkedQuoteClientKind === "ADULT" ? "adult" : null);
  const hasStrongClientCandidate = (bestClientCandidate?.confidence || 0) >= 80;
  const bestAdultCandidate = clientCandidates
    .map((candidate) => ({ candidate, client: clientsById.get(candidate.clientId) || null }))
    .find((entry) => (
      entry.client
      && String(entry.client.clientKind || "").toUpperCase() === "ADULT"
      && entry.candidate.confidence >= 70
      && !(quoteOwnerType === "child" && prospect && hasSamePersonName(entry.client, prospect))
    )) || null;
  const sortedClients = useMemo(() => sortClientsByName(clients), [clients]);

  const initialClientMode: QuoteTransformClientResolutionMode =
    restoredDraft?.clientResolution.mode
    ?? (
      linkedQuoteClient
        ? "existing"
        : quoteOwnerType === "child"
        ? bestAdultCandidate
          ? "new_child_existing_parent"
          : "new_parent_child"
        : scenario === "A"
          ? "new_adult"
          : scenario === "C"
            ? "new_parent_child"
            : hasStrongClientCandidate
              ? "existing"
              : "existing"
    );

  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4 | 5>(() => {
    const stepCandidate = Number(preferredStep ?? restoredDraft?.currentStep ?? 1);
    return isSupportedStep(stepCandidate) ? stepCandidate : 1;
  });
  const [clientMode, setClientMode] = useState<QuoteTransformClientResolutionMode>(initialClientMode);
  const [selectedClientId, setSelectedClientId] = useState<string>(
    restoredDraft?.clientResolution.selectedClientId
    || (initialClientMode === "existing" ? quote.clientId || bestClientCandidate?.clientId || "" : ""),
  );
  const [selectedParentClientId, setSelectedParentClientId] = useState<string>(
    restoredDraft?.clientResolution.selectedParentClientId
    || (initialClientMode === "new_child_existing_parent" ? bestAdultCandidate?.candidate.clientId || "" : "")
    || (
      initialClientMode === "new_parent_child" && String(bestCandidateClient?.clientKind || "").toUpperCase() === "ADULT"
        ? bestClientCandidate?.clientId || ""
        : ""
    ),
  );
  const [clientNotes, setClientNotes] = useState<string>(restoredDraft?.clientResolution.notes || "");
  const [clientSearch, setClientSearch] = useState<string>("");
  const [parentClientSearch, setParentClientSearch] = useState<string>("");

  const existingClientOptions = useMemo(() => {
    const output = new Map<string, { id: string; label: string }>();
    const query = normalizeClientSearch(clientSearch);
    const addClient = (client: QuoteTransformClient, label?: string): void => {
      output.set(client.id, {
        id: client.id,
        label: label || clientOptionLabel(client),
      });
    };

    for (const candidate of clientCandidates) {
      const client = clientsById.get(candidate.clientId) || null;
      const candidateLabel = `${candidate.displayName} · ${candidate.email} · ${t("admin.quote_transform.match_short", { confidence: candidate.confidence })}`;
      if (!query || normalizeClientSearch(candidateLabel).includes(query) || (client && clientSearchHaystack(client).includes(query))) {
        output.set(candidate.clientId, {
          id: candidate.clientId,
          label: candidateLabel,
        });
      }
    }

    for (const client of sortedClients) {
      if (output.size >= 120) {
        break;
      }
      if (output.has(client.id)) {
        continue;
      }
      if (query && !clientSearchHaystack(client).includes(query)) {
        continue;
      }
      addClient(client);
    }

    for (const id of [quote.clientId || "", selectedClientId]) {
      const client = id ? clientsById.get(id) || null : null;
      if (client && !output.has(client.id)) {
        addClient(client);
      }
    }

    return Array.from(output.values());
  }, [clientCandidates, clientsById, sortedClients, clientSearch, selectedClientId, quote.clientId, language]);

  const parentClientOptions = useMemo(() => {
    const output = new Map<string, { id: string; label: string }>();
    const query = normalizeClientSearch(parentClientSearch);
    const adults = sortedClients.filter((client) => (
      String(client.clientKind || "").toUpperCase() === "ADULT"
      && !(quoteOwnerType === "child" && prospect && hasSamePersonName(client, prospect))
    ));

    for (const client of adults) {
      if (output.size >= 120) {
        break;
      }
      if (query && !clientSearchHaystack(client).includes(query)) {
        continue;
      }
      output.set(client.id, {
        id: client.id,
        label: clientOptionLabel(client),
      });
    }

    const selectedParent = selectedParentClientId ? clientsById.get(selectedParentClientId) || null : null;
    if (selectedParent && !output.has(selectedParent.id)) {
      output.set(selectedParent.id, {
        id: selectedParent.id,
        label: clientOptionLabel(selectedParent),
      });
    }

    return Array.from(output.values());
  }, [clientsById, parentClientSearch, selectedParentClientId, sortedClients, prospect, quoteOwnerType]);

  const quoteOwnerName = prospect
    ? displayName(prospect.firstName, prospect.lastName, prospect.email)
    : linkedQuoteClient
      ? displayName(linkedQuoteClient.firstName, linkedQuoteClient.lastName, linkedQuoteClient.email)
      : "-";
  const quoteOwnerEmail = prospect?.email
    || (linkedQuoteClient && !isPlaceholderClientEmail(linkedQuoteClient.email) ? linkedQuoteClient.email : "")
    || "-";
  const quoteOwnerPhone = prospect?.phone || primaryClientPhone(linkedQuoteClient) || "-";
  const selectedExistingClient = selectedClientId ? clientsById.get(selectedClientId) || null : null;
  const existingChildNeedsResponsibleSelection =
    clientMode === "existing"
    && quoteOwnerType === "child"
    && String(selectedExistingClient?.clientKind || "").toUpperCase() === "CHILD";

  const [selectedPlanId, setSelectedPlanId] = useState<string>(() => {
    if (restoredDraft?.activityResolution.planId) {
      return restoredDraft.activityResolution.planId;
    }
    const planByFormula = plans.find((plan) => plan.name.toLowerCase() === String(quote.quoteTypeFormulaName || "").trim().toLowerCase());
    return planByFormula?.id || plans[0]?.id || "";
  });

  const [alignedActivityIds, setAlignedActivityIds] = useState<Set<string>>(
    () => new Set(restoredDraft?.activityResolution.alignedActivityIds || []),
  );
  const [offPlanningActivityIds, setOffPlanningActivityIds] = useState<Set<string>>(
    () => new Set(restoredDraft?.activityResolution.offPlanningActivityIds || []),
  );
  const activityLocationNameById = useMemo(
    () => deriveActivityLocationNameById(calendarSnapshot),
    [calendarSnapshot],
  );
  const activityLocationIdById = useMemo(
    () => deriveActivityLocationIdById(calendarSnapshot),
    [calendarSnapshot],
  );

  const baseActivityRows = useMemo(
    () => buildActivityPricingRows(lines, activitiesById, activityLocationNameById, quote.locationName, scenario, calendarSnapshot),
    [lines, activitiesById, activityLocationNameById, quote.locationName, scenario, calendarSnapshot],
  );

  const activityRows = useMemo(
    () => baseActivityRows.map((row) => {
      const acceptedQuoteIsAuthoritative = String(quote.status || "").trim().toLowerCase() === "approved";
      if (!acceptedQuoteIsAuthoritative && !alignedActivityIds.has(row.scheduleKey)) {
        return row;
      }
      return {
        ...row,
        currentSystemTtc: row.expectedTtc,
        deltaTtc: 0,
        status: "ok" as const,
        reason: acceptedQuoteIsAuthoritative
          ? (language === "en" ? "accepted quote contract price" : "tarif contractuel du devis validé")
          : (language === "en" ? "manually aligned with quote" : "alignement manuel sur devis"),
      };
    }),
    [baseActivityRows, alignedActivityIds, quote.status, language],
  );

  const scheduleHints = useMemo(() => deriveScheduleHints(calendarSnapshot), [calendarSnapshot]);
  const scheduleSessionCounts = useMemo(() => deriveScheduleSessionCounts(calendarSnapshot), [calendarSnapshot]);

  const quotePlanningContextByScheduleKey = useMemo(() => {
    const output = new Map<string, QuotePlanningContext>();
    for (const row of activityRows) {
      const hint = scheduleHints.get(row.scheduleKey) ?? scheduleHints.get(row.activityId) ?? null;
      output.set(row.scheduleKey, {
        activity: row.activityName,
        quantity: formatQuantity(row.quantity, row.pricingUnit, language),
        slot: formatScheduleHint(hint, language),
        location: row.locationName || uiText(language, "admin.quote_transform.location_not_defined"),
      });
    }
    return output;
  }, [activityRows, scheduleHints, language]);

  const sessionOptionsByActivityId = useMemo(() => {
    const output = new Map<string, SessionMatchOption[]>();
    for (const row of activityRows) {
      const sessions = row.matchingActivityIds.flatMap((activityId) => sessionsByActivityId[activityId] || []);
      const expectedLocationId = activityLocationIdById.get(row.scheduleKey) || activityLocationIdById.get(row.activityId) || quote.locationId;
      const options = buildSessionMatches(
        row,
        sessions,
        expectedLocationId,
        scheduleHints,
        scenario,
        localeForUiLanguage(language),
        language,
      );
      output.set(row.scheduleKey, options);
    }
    return output;
  }, [activityRows, sessionsByActivityId, activityLocationIdById, quote.locationId, scheduleHints, scenario, language]);

  const [assignedSessionByActivityId, setAssignedSessionByActivityId] = useState<Record<string, string>>(() => {
    const restored = restoredDraft?.scheduleResolution.assignedSessionByActivityId || {};
    if (Object.keys(restored).length > 0) {
      return { ...restored };
    }

    const defaults: Record<string, string> = {};
    for (const row of baseActivityRows) {
      const options = sessionOptionsByActivityId.get(row.scheduleKey) || [];
      const defaultSessionId = defaultSessionAssignment(row, options, scenario);
      if (defaultSessionId) {
        defaults[row.scheduleKey] = defaultSessionId;
      }
    }
    return defaults;
  });

  useEffect(() => {
    setAssignedSessionByActivityId((current) => {
      const next: Record<string, string> = {};
      let changed = false;
      const scheduleKeys = new Set(activityRows.map((row) => row.scheduleKey));

      for (const row of activityRows) {
        const options = sessionOptionsByActivityId.get(row.scheduleKey) || [];
        const currentSessionId = current[row.scheduleKey] || "";
        const stillAvailable = Boolean(currentSessionId && options.some((option) => option.sessionId === currentSessionId));
        if (stillAvailable) {
          next[row.scheduleKey] = currentSessionId;
          continue;
        }

        if (currentSessionId) {
          changed = true;
        }
        const defaultSessionId = defaultSessionAssignment(row, options, scenario);
        if (defaultSessionId) {
          next[row.scheduleKey] = defaultSessionId;
          if (defaultSessionId !== currentSessionId) {
            changed = true;
          }
        }
      }

      for (const scheduleKey of Object.keys(current)) {
        if (!scheduleKeys.has(scheduleKey)) {
          changed = true;
          break;
        }
      }

      return changed ? next : current;
    });
  }, [activityRows, sessionOptionsByActivityId, scenario]);

  const suggestedBillingRows = useMemo(
    () => buildBillingExtraRows(lines, activityRows, offPlanningActivityIds, quote),
    [lines, activityRows, offPlanningActivityIds, quote],
  );

  const [billingRows, setBillingRows] = useState<BillingExtraRow[]>(() => {
    const suggestedById = new Map(suggestedBillingRows.map((row) => [row.rowId, row]));
    if (restoredDraft?.billingResolution.rows && restoredDraft.billingResolution.rows.length > 0) {
      return restoredDraft.billingResolution.rows.map((row) => {
        const suggested = suggestedById.get(row.rowId);
        const amountVat = Number((row.amountTtc - row.amountHt).toFixed(2));
        const mapped: BillingExtraRow = {
          rowId: row.rowId,
          sourceLineId: suggested?.sourceLineId || null,
          type: suggested?.type || row.type,
          label: row.label,
          amountHt: row.amountHt,
          vatRate: row.vatRate,
          amountVat,
          amountTtc: row.amountTtc,
          status: "ok",
          editable: true,
          effectiveDate: row.effectiveDate || suggested?.effectiveDate || null,
        };
        return { ...mapped, status: billingStatus(mapped) };
      }).filter((row) => {
        if (suggestedById.has(row.rowId)) {
          return true;
        }
        return !row.rowId.startsWith("off-planning-") && billingStatus(row) !== "blocked";
      });
    }
    return suggestedBillingRows.map((row) => ({ ...row, status: billingStatus(row) }));
  });

  useEffect(() => {
    setBillingRows((previous) => {
      const previousById = new Map(previous.map((row) => [row.rowId, row]));
      const merged = suggestedBillingRows.map((row) => {
        const stored = previousById.get(row.rowId);
        if (!stored) {
          return { ...row, status: billingStatus(row) };
        }
        const next: BillingExtraRow = {
          ...row,
          amountHt: stored.amountHt,
          vatRate: stored.vatRate,
          amountVat: Number((stored.amountTtc - stored.amountHt).toFixed(2)),
          amountTtc: stored.amountTtc,
          label: stored.label,
          editable: stored.editable,
          effectiveDate: stored.effectiveDate || row.effectiveDate || null,
          status: stored.status,
        };
        return { ...next, status: billingStatus(next) };
      });

      const preservedCustom = previous.filter((row) => {
        if (suggestedBillingRows.some((suggested) => suggested.rowId === row.rowId)) {
          return false;
        }
        if (row.rowId.startsWith("off-planning-")) {
          return false;
        }
        return billingStatus(row) !== "blocked";
      });
      return [...merged, ...preservedCustom];
    });
  }, [suggestedBillingRows]);

  const [acceptedBlockingIssueIds, setAcceptedBlockingIssueIds] = useState<Set<string>>(
    () => new Set(restoredDraft?.acceptedBlockingIssueIds || []),
  );

  const step1Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    if (!prospect && !linkedQuoteClient) {
      issues.push({
        issueId: "step1-prospect-missing",
        step: 1,
        level: "blocked",
        message: t("admin.quote_transform.issue_prospect_missing"),
        canOverride: false,
      });
    }

    if (clientMode === "existing") {
      if (!selectedClientId) {
        issues.push({
          issueId: "step1-client-selection-required",
          step: 1,
          level: "blocked",
          message: t("admin.quote_transform.issue_select_existing_or_create"),
          canOverride: false,
        });
      } else if (!clientsById.has(selectedClientId)) {
        issues.push({
          issueId: "step1-client-selection-invalid",
          step: 1,
          level: "blocked",
          message: t("admin.quote_transform.issue_selected_client_invalid"),
          canOverride: false,
        });
      } else if (
        quoteOwnerType === "child"
        && String(clientsById.get(selectedClientId)?.clientKind || "").toUpperCase() !== "CHILD"
      ) {
        issues.push({
          issueId: "step1-child-must-target-child-client",
          step: 1,
          level: "blocked",
          message: "Pour un prospect enfant, la fiche selectionnee doit etre une fiche enfant. Utilisez creation parent + enfant ou selectionnez un enfant existant.",
          canOverride: false,
        });
      }
    }

    if (scenario === "B" && clientCandidates.length > 1) {
      issues.push({
        issueId: "step1-ambiguous-matches",
        step: 1,
        level: "warning",
        message: t("admin.quote_transform.issue_multiple_probable_matches"),
        canOverride: false,
      });
    }

    if (clientMode === "new_child_existing_parent" && !selectedParentClientId) {
      issues.push({
        issueId: "step1-existing-parent-required",
        step: 1,
        level: "blocked",
        message: t("admin.quote_transform.issue_existing_parent_required"),
        canOverride: false,
      });
    }

    if (clientMode === "new_parent_child" && !selectedParentClientId) {
      issues.push({
        issueId: "step1-parent-to-create",
        step: 1,
        level: "warning",
        message: t("admin.quote_transform.issue_parent_not_selected"),
        canOverride: false,
      });
    }

    return issues;
  }, [prospect, linkedQuoteClient, quoteOwnerType, clientMode, selectedClientId, selectedParentClientId, scenario, clientCandidates.length, clientsById, language]);

  const step1Status = useMemo(
    () => summarizeStatus(step1Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step1Issues],
  );

  const step2Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    if (!selectedPlanId) {
      issues.push({
        issueId: "step2-plan-required",
        step: 2,
        level: "blocked",
        message: t("admin.quote_transform.issue_select_plan"),
        canOverride: false,
      });
    }

    for (const row of activityRows) {
      if (row.status === "ok") {
        continue;
      }
      issues.push({
        issueId: `step2-pricing-${row.scheduleKey}`,
        step: 2,
        level: row.status === "blocked" ? "blocked" : "warning",
        message: t("admin.quote_transform.issue_pricing_gap", {
          activity: row.activityName,
          reason: translateQuoteTransformMessage(row.reason, language),
          delta: currency(row.deltaTtc, quote.currency, language),
        }),
        canOverride: row.status === "warning",
      });
    }
    return issues;
  }, [selectedPlanId, activityRows, quote.currency, language]);

  const step2Status = useMemo(
    () => summarizeStatus(step2Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step2Issues],
  );

  const step3Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    for (const row of activityRows) {
      if (offPlanningActivityIds.has(row.scheduleKey)) {
        issues.push({
          issueId: `step3-off-planning-${row.scheduleKey}`,
          step: 3,
          level: "warning",
          message: t("admin.quote_transform.issue_off_planning_switch", { activity: row.activityName }),
          canOverride: false,
        });
        continue;
      }

      const options = sessionOptionsByActivityId.get(row.scheduleKey) || [];
      if (options.length === 0) {
        issues.push({
          issueId: `step3-no-session-${row.scheduleKey}`,
          step: 3,
          level: "blocked",
          message: t("admin.quote_transform.issue_no_compatible_slot", { activity: row.activityName }),
          canOverride: false,
        });
        continue;
      }

      const selectedSessionId = assignedSessionByActivityId[row.scheduleKey] || "";
      if (!selectedSessionId) {
        issues.push({
          issueId: `step3-session-choice-required-${row.scheduleKey}`,
          step: 3,
          level: "blocked",
          message: t("admin.quote_transform.issue_session_required", { activity: row.activityName }),
          canOverride: false,
        });
        continue;
      }

      const selectedOption = options.find((option) => option.sessionId === selectedSessionId);
      if (!selectedOption) {
        issues.push({
          issueId: `step3-session-choice-invalid-${row.scheduleKey}`,
          step: 3,
          level: "blocked",
          message: t("admin.quote_transform.issue_session_invalid", { activity: row.activityName }),
          canOverride: false,
        });
        continue;
      }

      if (selectedOption.status.toUpperCase() !== "SCHEDULED") {
        issues.push({
          issueId: `step3-session-not-scheduled-${row.scheduleKey}`,
          step: 3,
          level: "blocked",
          message: `${row.activityName} : le créneau sélectionné n'est plus planifié. Sélectionnez une série active.`,
          canOverride: false,
        });
        continue;
      }

      const approvedSessionCount = scheduleSessionCounts.get(row.scheduleKey) ?? scheduleSessionCounts.get(row.activityId);
      const billedSessionCount = Number.isFinite(row.quantity) ? Math.round(row.quantity) : 0;
      if (billedSessionCount > 1 && approvedSessionCount !== undefined && approvedSessionCount !== billedSessionCount) {
        issues.push({
          issueId: `step3-session-count-mismatch-${row.scheduleKey}`,
          step: 3,
          level: "warning",
          message: language === "en"
            ? `${row.activityName}: the accepted quote bills ${billedSessionCount} session(s). This contractual quantity will be applied despite the ${approvedSessionCount} occurrence(s) currently materialized.`
            : `${row.activityName} : le devis validé facture ${billedSessionCount} séance(s). Cette quantité contractuelle sera appliquée malgré les ${approvedSessionCount} occurrence(s) actuellement matérialisée(s).`,
          canOverride: false,
        });
      }

      if (selectedOption.seatsRemaining <= 0) {
        const approvedSelection = selectedOption.approvedQuoteSelection === true;
        issues.push({
          issueId: `step3-session-full-${row.scheduleKey}`,
          step: 3,
          level: approvedSelection ? "warning" : "blocked",
          message: approvedSelection
            ? language === "en"
              ? `${row.activityName}: the exact slot accepted in the quote is now full. The enrollment will still be honored and the capacity exception will be audited.`
              : `${row.activityName} : le créneau exact du devis validé est désormais complet. L'inscription sera néanmoins honorée et le dépassement sera tracé.`
            : t("admin.quote_transform.issue_session_full", { activity: row.activityName }),
          canOverride: false,
        });
      } else if (options.length > 1) {
        issues.push({
          issueId: `step3-session-multiple-${row.scheduleKey}`,
          step: 3,
          level: "warning",
          message: t("admin.quote_transform.issue_multiple_slots", { activity: row.activityName }),
          canOverride: false,
        });
      }
    }
    return issues;
  }, [activityRows, offPlanningActivityIds, sessionOptionsByActivityId, assignedSessionByActivityId, scheduleSessionCounts, language]);

  const step3Status = useMemo(
    () => summarizeStatus(step3Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step3Issues],
  );

  const step4Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    for (const row of billingRows) {
      if (row.status === "ok") {
        continue;
      }
      issues.push({
        issueId: `step4-billing-${row.rowId}`,
        step: 4,
        level: row.status === "blocked" ? "blocked" : "warning",
        message: t("admin.quote_transform.issue_billing_row_fix", {
          label: row.label,
          status: statusLabel(row.status, language),
        }),
        canOverride: row.status === "warning",
      });
    }
    return issues;
  }, [billingRows, language]);

  const step4Status = useMemo(
    () => summarizeStatus(step4Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step4Issues],
  );

  const scheduledActivitiesTotal = useMemo(
    () => activityRows
      .filter((row) => !offPlanningActivityIds.has(row.scheduleKey))
      .reduce((sum, row) => Number((sum + row.currentSystemTtc).toFixed(2)), 0),
    [activityRows, offPlanningActivityIds],
  );

  const billingTotals = useMemo(() => sumBillingRows(billingRows), [billingRows]);

  const systemTotalTtc = useMemo(
    () => Number((scheduledActivitiesTotal + billingTotals.totalTtc).toFixed(2)),
    [scheduledActivitiesTotal, billingTotals.totalTtc],
  );

  const financialControl = useMemo(
    () => evaluateFinancialStatus(quote.totalTtc, systemTotalTtc),
    [quote.totalTtc, systemTotalTtc],
  );

  const step5Issues = useMemo(() => {
    const issues: StepIssue[] = [];

    if (financialControl.status === "warning" || financialControl.status === "blocked") {
      const absDelta = Math.abs(financialControl.deltaTtc);
      issues.push({
        issueId: "step5-financial-delta",
        step: 5,
        level: financialControl.status === "blocked" ? "blocked" : "warning",
        message: t("admin.quote_transform.issue_financial_delta", {
          delta: currency(financialControl.deltaTtc, quote.currency, language),
        }),
        canOverride: financialControl.status === "blocked" && absDelta <= 30,
      });
    }

    if (!followupId) {
      issues.push({
        issueId: "step5-followup-missing",
        step: 5,
        level: "warning",
        message: t("admin.quote_transform.issue_followup_missing"),
        canOverride: false,
      });
    }

    return issues;
  }, [financialControl, quote.currency, followupId, language]);

  const step5Status = useMemo(
    () => summarizeStatus(step5Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step5Issues],
  );

  const allIssues = useMemo(
    () => [...step1Issues, ...step2Issues, ...step3Issues, ...step4Issues, ...step5Issues],
    [step1Issues, step2Issues, step3Issues, step4Issues, step5Issues],
  );

  const unresolvedBlockingIssues = useMemo(
    () => allIssues.filter((issue) => issue.level === "blocked" && !(issue.canOverride && acceptedBlockingIssueIds.has(issue.issueId))),
    [allIssues, acceptedBlockingIssueIds],
  );

  const stepStatuses = [step1Status, step2Status, step3Status, step4Status, step5Status] as const;
  const okStepsCount = stepStatuses.filter((status) => status === "ok").length;

  const selectedClientName = useMemo(() => {
    if (clientMode !== "existing") {
      if (clientMode === "new_child_existing_parent") {
        const parent = clientsById.get(selectedParentClientId);
        return parent
          ? t("admin.quote_transform.selected_client_create_child_existing_parent_named", {
            parent: displayName(parent.firstName, parent.lastName, parent.email),
          })
          : t("admin.quote_transform.selected_client_create_child_existing_parent");
      }
      return clientMode === "new_parent_child"
        ? t("admin.quote_transform.selected_client_create_parent_child")
        : t("admin.quote_transform.selected_client_create_new_client");
    }
    const candidate = clientCandidates.find((item) => item.clientId === selectedClientId);
    if (candidate) {
      return candidate.displayName;
    }
    const selectedClient = clientsById.get(selectedClientId);
    if (!selectedClient) {
      return t("admin.quote_transform.selected_client_none");
    }
    return displayName(selectedClient.firstName, selectedClient.lastName, selectedClient.email);
  }, [clientMode, clientCandidates, selectedClientId, selectedParentClientId, clientsById, language]);
  const selectedClientHref = clientMode === "existing" && selectedClientId
    ? `/admin/clients/${encodeURIComponent(selectedClientId)}`
    : null;

  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId) || null;
  const selectedLegalEntity = legalEntities.find((entity) => entity.id === quote.legalEntityId) || null;

  const saveDisabled = !followupId;
  const finalizeDisabled = !followupId || unresolvedBlockingIssues.length > 0;
  const finalizeDisabledReason = !followupId
    ? t("admin.quote_transform.no_followup_persistence")
    : unresolvedBlockingIssues.length > 0
      ? t("admin.quote_transform.critical_blocks_remaining", { count: unresolvedBlockingIssues.length })
      : "";

  const draftPayload = useMemo<QuoteToEnrollmentDraft>(() => {
    const draftRows = billingRows.map((row) => ({
      rowId: row.rowId,
      type: row.type,
      label: row.label,
      amountHt: Number(row.amountHt.toFixed(2)),
      vatRate: Number(row.vatRate.toFixed(2)),
      amountTtc: Number(row.amountTtc.toFixed(2)),
      effectiveDate: row.effectiveDate || null,
    }));

    const logs = [
      {
        at: new Date().toISOString(),
        action: "quote_to_enrollment_snapshot",
        detail: `step=${currentStep} client_mode=${clientMode} plan=${selectedPlanId || "none"} blocked=${unresolvedBlockingIssues.length}`,
      },
      {
        at: new Date().toISOString(),
        action: "schedule_resolution",
        detail: `assigned=${Object.keys(assignedSessionByActivityId).length} off_planning=${offPlanningActivityIds.size}`,
      },
      {
        at: new Date().toISOString(),
        action: "financial_check",
        detail: `expected=${quote.totalTtc.toFixed(2)} system=${systemTotalTtc.toFixed(2)} delta=${financialControl.deltaTtc.toFixed(2)}`,
      },
    ];

    const seriesAssignmentsByActivityId: Record<string, QuoteToEnrollmentSeriesAssignment> = {};
    for (const row of activityRows) {
      const selectedSessionId = assignedSessionByActivityId[row.scheduleKey] || "";
      const option = (sessionOptionsByActivityId.get(row.scheduleKey) || []).find(
        (candidate) => candidate.sessionId === selectedSessionId,
      );
      if (!option) {
        continue;
      }
      seriesAssignmentsByActivityId[row.scheduleKey] = {
        sessionId: option.sessionId,
        recurrenceGroupId: option.recurrenceGroupId,
        courseTypeId: option.courseTypeId,
        locationId: option.locationId,
        timezone: option.timezone,
        localWeekday: option.localWeekday,
        localStartTime: option.localStartTime,
        localEndTime: option.localEndTime,
        expectedQuantity: row.quantity,
      };
    }

    return {
      version: 1,
      scenario,
      currentStep,
      clientResolution: {
        mode: clientMode,
        selectedClientId: selectedClientId || null,
        selectedParentClientId: selectedParentClientId || null,
        notes: clientNotes,
      },
      activityResolution: {
        planId: selectedPlanId || null,
        alignedActivityIds: Array.from(alignedActivityIds),
        offPlanningActivityIds: Array.from(offPlanningActivityIds),
      },
      scheduleResolution: {
        assignedSessionByActivityId,
        seriesAssignmentsByActivityId,
      },
      billingResolution: {
        rows: draftRows,
      },
      acceptedBlockingIssueIds: Array.from(acceptedBlockingIssueIds),
      financialControl: {
        expectedTtc: quote.totalTtc,
        systemTtc: systemTotalTtc,
        deltaTtc: financialControl.deltaTtc,
      },
      idempotencyKey: buildIdempotencyKey({
        quoteId: quote.id,
        scenario,
        clientMode,
        selectedClientId: selectedClientId || null,
        selectedPlanId: selectedPlanId || null,
        assignedSessionByActivityId,
        billingRows: draftRows.map((row) => ({ rowId: row.rowId, amountTtc: row.amountTtc })),
      }),
      logs,
      finalizedAt: restoredDraft?.finalizedAt || null,
    };
  }, [
    billingRows,
    currentStep,
    clientMode,
    selectedClientId,
    selectedParentClientId,
    clientNotes,
    selectedPlanId,
    alignedActivityIds,
    offPlanningActivityIds,
    assignedSessionByActivityId,
    activityRows,
    sessionOptionsByActivityId,
    acceptedBlockingIssueIds,
    scenario,
    quote.id,
    quote.totalTtc,
    systemTotalTtc,
    financialControl.deltaTtc,
    restoredDraft?.finalizedAt,
    unresolvedBlockingIssues.length,
  ]);

  const stepper = [
    { step: 1 as const, label: t("admin.quote_transform.step1_label"), status: step1Status },
    { step: 2 as const, label: t("admin.quote_transform.step2_label"), status: step2Status },
    { step: 3 as const, label: t("admin.quote_transform.step3_label"), status: step3Status },
    { step: 4 as const, label: t("admin.quote_transform.step4_label"), status: step4Status },
    { step: 5 as const, label: t("admin.quote_transform.step5_label"), status: step5Status },
  ];

  function nextStep(): void {
    const currentStatus = stepStatuses[currentStep - 1];
    if (!canProceedFromStep(currentStep, currentStatus)) {
      return;
    }
    setCurrentStep((step) => (step >= 5 ? 5 : ((step + 1) as 1 | 2 | 3 | 4 | 5)));
  }

  function previousStep(): void {
    setCurrentStep((step) => (step <= 1 ? 1 : ((step - 1) as 1 | 2 | 3 | 4 | 5)));
  }

  function toggleAlignedActivity(activityId: string): void {
    setAlignedActivityIds((previous) => {
      const next = new Set(previous);
      if (next.has(activityId)) {
        next.delete(activityId);
      } else {
        next.add(activityId);
      }
      return next;
    });
  }

  function toggleOffPlanningActivity(activityId: string): void {
    setOffPlanningActivityIds((previous) => {
      const next = new Set(previous);
      if (next.has(activityId)) {
        next.delete(activityId);
      } else {
        next.add(activityId);
      }
      return next;
    });
  }

  function assignSession(activityId: string, sessionId: string): void {
    setAssignedSessionByActivityId((previous) => ({ ...previous, [activityId]: sessionId }));
    setOffPlanningActivityIds((previous) => {
      if (!previous.has(activityId)) {
        return previous;
      }
      const next = new Set(previous);
      next.delete(activityId);
      return next;
    });
  }

  function updateBillingRow(rowId: string, patch: Partial<BillingExtraRow>): void {
    setBillingRows((previous) => previous.map((row) => {
      if (row.rowId !== rowId) {
        return row;
      }
      const nextVatRate = patch.vatRate ?? row.vatRate;
      const nextTtc = patch.amountTtc ?? row.amountTtc;
      const nextHt = patch.amountHt ?? Number((nextTtc / (1 + (nextVatRate / 100))).toFixed(2));
      const next: BillingExtraRow = {
        ...row,
        ...patch,
        amountHt: Number(nextHt.toFixed(2)),
        vatRate: Number(nextVatRate.toFixed(2)),
        amountTtc: Number(nextTtc.toFixed(2)),
        amountVat: Number((nextTtc - nextHt).toFixed(2)),
      };
      return { ...next, status: billingStatus(next) };
    }));
  }

  function toggleBlockingAcceptance(issueId: string): void {
    setAcceptedBlockingIssueIds((previous) => {
      const next = new Set(previous);
      if (next.has(issueId)) {
        next.delete(issueId);
      } else {
        next.add(issueId);
      }
      return next;
    });
  }

  return (
    <section className="quote-transform-shell">
      <header className="card quote-transform-header">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>{t("admin.quote_transform.title")}</h2>
            <p className="muted">
              {t("admin.quote_transform.subtitle", {
                number: quote.quoteNumber,
                quote_type: quote.quoteType,
                total: currency(quote.totalTtc, quote.currency, language),
              })}
            </p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backPath}>{t("admin.quote_transform.back_to_quote")}</Link>
          </div>
        </div>
        <div className="quote-transform-header-kpis top-gap-sm">
          <span className="badge">{t("admin.quote_transform.badge_owner")}: {quoteOwnerName}</span>
          <span className="badge">{t("admin.quote_transform.badge_school_year")}: {quote.schoolYearLabel || "-"}</span>
          <span className="badge">{t("admin.quote_transform.badge_legal_entity")}: {selectedLegalEntity?.name || quote.legalEntityName}</span>
          <span className="badge">{t("admin.quote_transform.badge_followup_status")}: {followupStatus || t("admin.quote_transform.followup_absent")}</span>
        </div>
      </header>

      <div className="quote-transform-layout">
        <aside className="card quote-transform-sidebar">
          <h3>{t("admin.quote_transform.summary_title")}</h3>
          <div className="quote-transform-sidebar-grid top-gap-sm">
            <p>
              <strong>{t("admin.quote_transform.summary_target_client")}:</strong>{" "}
              {selectedClientHref ? (
                <Link className="mode-link" href={selectedClientHref}>
                  {selectedClientName}
                </Link>
              ) : (
                selectedClientName
              )}
            </p>
            <p><strong>{t("admin.quote_transform.summary_plan")}:</strong> {selectedPlan?.name || t("admin.quote_transform.none")}</p>
            <p><strong>{t("admin.quote_transform.summary_activities")}:</strong> {activityRows.length}</p>
            <p><strong>{t("admin.quote_transform.summary_off_planning")}:</strong> {offPlanningActivityIds.size}</p>
            <p><strong>{t("admin.quote_transform.summary_quote_total")}:</strong> {currency(quote.totalTtc, quote.currency, language)}</p>
            <p><strong>{t("admin.quote_transform.summary_system_total")}:</strong> {currency(systemTotalTtc, quote.currency, language)}</p>
          </div>

          <section className="top-gap-sm">
            <h4>{t("admin.quote_transform.scenarios_title")}</h4>
            <div className="quote-transform-scenario-list top-gap-sm">
              {scenarioLinks.map((item) => (
                <Link key={item.scenario} href={item.href} className={`quote-transform-scenario-link ${item.active ? "active" : ""}`.trim()}>
                  {item.label}
                </Link>
              ))}
            </div>
            <p className="muted top-gap-sm">{t("admin.quote_transform.scenarios_help")}</p>
          </section>

          <section className="top-gap-sm">
            <h4>{t("admin.quote_transform.steps_title")}</h4>
            <div className="quote-transform-step-list top-gap-sm">
              {stepper.map((item) => (
                <button
                  key={`sidebar-step-${item.step}`}
                  type="button"
                  className={`quote-transform-step-link ${currentStep === item.step ? "active" : ""}`.trim()}
                  onClick={() => setCurrentStep(item.step)}
                >
                  <span>{item.step}. {item.label}</span>
                  <span className={`status-pill ${statusClassName(item.status)}`}>{statusLabel(item.status, language)}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="top-gap-sm">
            <h4>{t("admin.quote_transform.issues_title")}</h4>
            <div className="quote-transform-issue-kpis top-gap-sm">
              <span className="status-pill status-ok">{t("admin.quote_transform.issues_ok", { count: okStepsCount })}</span>
              <span className="status-pill status-warn">{t("admin.quote_transform.issues_warnings", { count: allIssues.filter((issue) => issue.level === "warning").length })}</span>
              <span className="status-pill quote-transform-status-blocked">{t("admin.quote_transform.issues_blocked", { count: unresolvedBlockingIssues.length })}</span>
            </div>
          </section>
        </aside>

        <main className="quote-transform-main">
          <section className="card quote-transform-stepper-card">
            <ol className="quote-transform-stepper" aria-label={t("admin.quote_transform.stepper_aria")}>
              {stepper.map((item) => (
                <li key={`stepper-${item.step}`} className={currentStep === item.step ? "active" : ""}>
                  <button type="button" onClick={() => setCurrentStep(item.step)}>
                    <strong>{item.step}</strong>
                    <span>{item.label}</span>
                    <small className={`status-pill ${statusClassName(item.status)}`}>{statusLabel(item.status, language)}</small>
                  </button>
                </li>
              ))}
            </ol>
          </section>

          {currentStep === 1 ? (
            <section className="card quote-transform-step-card">
              <h3>{t("admin.quote_transform.step1_title")}</h3>
              <p className="muted">{t("admin.quote_transform.step1_subtitle")}</p>

              <div className="grid cols-2 top-gap-sm">
                <article className="item">
                  <h4>{t("admin.quote_transform.quote_prospect")}</h4>
                  <p><strong>{t("admin.quote_transform.name")}:</strong> {quoteOwnerName}</p>
                  <p><strong>{t("admin.quote_transform.email")}:</strong> {quoteOwnerEmail}</p>
                  <p><strong>{t("admin.quote_transform.phone")}:</strong> {quoteOwnerPhone}</p>
                  <p><strong>{t("admin.quote_transform.type")}:</strong> {quoteOwnerType === "child" ? t("admin.quote_transform.type_child") : quoteOwnerType === "adult" ? t("admin.quote_transform.type_adult") : "-"}</p>
                </article>
                <article className="item">
                  <h4>{t("admin.quote_transform.resolution_mode_title")}</h4>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="existing"
                      checked={clientMode === "existing"}
                      onChange={() => setClientMode("existing")}
                    />
                    {t("admin.quote_transform.use_existing_record")}
                  </label>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="new_adult"
                      checked={clientMode === "new_adult"}
                      onChange={() => setClientMode("new_adult")}
                    />
                    {t("admin.quote_transform.create_new_client")}
                  </label>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="new_parent_child"
                      checked={clientMode === "new_parent_child"}
                      onChange={() => setClientMode("new_parent_child")}
                    />
                    {t("admin.quote_transform.create_parent_child")}
                  </label>
                  {quoteOwnerType === "child" ? (
                    <label className="quote-transform-radio">
                      <input
                        type="radio"
                        name="client_mode"
                        value="new_child_existing_parent"
                        checked={clientMode === "new_child_existing_parent"}
                        onChange={() => {
                          setClientMode("new_child_existing_parent");
                          setSelectedClientId("");
                          setSelectedParentClientId((current) => current || bestAdultCandidate?.candidate.clientId || "");
                        }}
                      />
                      {t("admin.quote_transform.create_child_existing_parent")}
                    </label>
                  ) : null}
                </article>
              </div>

              <section className="top-gap-sm">
                <h4>{t("admin.quote_transform.matches_title")}</h4>
                {clientCandidates.length === 0 ? (
                  <p className="flash-warn top-gap-sm">{t("admin.quote_transform.no_auto_match")}</p>
                ) : (
                  <div className="table-wrap top-gap-sm">
                    <table className="data-table quote-transform-compact-table">
                      <thead>
                        <tr>
                          <th>{t("admin.quote_transform.col_client")}</th>
                          <th>{t("admin.quote_transform.col_email")}</th>
                          <th>{t("admin.quote_transform.col_phone")}</th>
                          <th>{t("admin.quote_transform.col_confidence")}</th>
                          <th>{t("admin.quote_transform.col_actions")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {clientCandidates.map((candidate) => {
                          const candidateClient = clientsById.get(candidate.clientId) || null;
                          const candidateClientKind = String(candidateClient?.clientKind || "").toUpperCase();
                          const candidateHasChildIdentity = Boolean(quoteOwnerType === "child" && prospect && candidateClient && hasSamePersonName(candidateClient, prospect));
                          const candidateIsAdultForChildProspect = quoteOwnerType === "child" && candidateClientKind === "ADULT" && !candidateHasChildIdentity;
                          return (
                          <tr key={candidate.clientId}>
                            <td>
                              <strong>{candidate.displayName}</strong>
                              <small className="muted block">{candidate.reasons.map((reason) => translateQuoteTransformMessage(reason, language)).join(" · ")}</small>
                            </td>
                            <td>{candidate.email}</td>
                            <td>{candidate.phone || "-"}</td>
                            <td>
                              <span className={`status-pill ${candidate.confidence >= 80 ? "status-ok" : candidate.confidence >= 55 ? "status-warn" : "quote-transform-status-blocked"}`}>
                                {quoteTransformConfidenceLabel(candidate.confidenceLabel, language)} ({candidate.confidence})
                              </span>
                            </td>
                            <td>
                              <div className="row wrap gap-sm">
                                {!candidateIsAdultForChildProspect ? (
                                  <button
                                    type="button"
                                    className="ghost"
                                    onClick={() => {
                                      setClientMode("existing");
                                      setSelectedClientId(candidate.clientId);
                                    }}
                                  >
                                    {t("admin.quote_transform.use_record")}
                                  </button>
                                ) : null}
                                {candidateIsAdultForChildProspect ? (
                                  <button
                                    type="button"
                                    className="ghost"
                                    onClick={() => {
                                      setClientMode("new_child_existing_parent");
                                      setSelectedParentClientId(candidate.clientId);
                                      setSelectedClientId("");
                                    }}
                                  >
                                    {t("admin.quote_transform.create_child_here")}
                                  </button>
                                ) : null}
                                {clientsById.has(candidate.clientId) ? (
                                  <Link className="ghost" href={`/admin/clients/${encodeURIComponent(candidate.clientId)}`} target="_blank">
                                    {t("admin.quote_transform.view_detail")}
                                  </Link>
                                ) : (
                                  <span className="muted">{t("admin.quote_transform.local_simulation")}</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {clientMode === "existing" ? (
                <section className="top-gap-sm">
                  <label>
                    {t("admin.quote_transform.client_search")}
                    <input
                      type="search"
                      value={clientSearch}
                      onChange={(event) => setClientSearch(event.target.value)}
                      placeholder={t("admin.quote_transform.client_search_placeholder")}
                    />
                  </label>
                  <label className="top-gap-sm">
                    {t("admin.quote_transform.selected_client_record")}
                    <select value={selectedClientId} onChange={(event) => setSelectedClientId(event.target.value)}>
                      <option value="">{t("admin.quote_transform.select")}</option>
                      {existingClientOptions.map((option) => (
                        <option key={`client-option-${option.id}`} value={option.id}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="muted">{t("admin.quote_transform.client_search_count", { count: existingClientOptions.length })}</p>
                </section>
              ) : null}

              {clientMode === "new_parent_child" || clientMode === "new_child_existing_parent" || existingChildNeedsResponsibleSelection ? (
                <section className="top-gap-sm">
                  <label>
                    {t("admin.quote_transform.parent_search")}
                    <input
                      type="search"
                      value={parentClientSearch}
                      onChange={(event) => setParentClientSearch(event.target.value)}
                      placeholder={t("admin.quote_transform.parent_search_placeholder")}
                    />
                  </label>
                  <label className="top-gap-sm">
                    {clientMode === "new_child_existing_parent"
                      ? t("admin.quote_transform.existing_parent_required")
                      : existingChildNeedsResponsibleSelection
                        ? t("admin.quote_transform.existing_child_parent_optional")
                      : t("admin.quote_transform.existing_parent_optional")}
                    <select value={selectedParentClientId} onChange={(event) => setSelectedParentClientId(event.target.value)}>
                      <option value="">
                        {clientMode === "new_child_existing_parent"
                          ? t("admin.quote_transform.select_existing_parent")
                          : existingChildNeedsResponsibleSelection
                            ? t("admin.quote_transform.keep_existing_parent_link")
                          : t("admin.quote_transform.create_new_parent")}
                      </option>
                      {parentClientOptions.map((option) => (
                        <option key={`parent-option-${option.id}`} value={option.id}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="muted">{t("admin.quote_transform.client_search_count", { count: parentClientOptions.length })}</p>
                </section>
              ) : null}

              <label className="top-gap-sm">
                {t("admin.quote_transform.notes")}
                <textarea
                  rows={3}
                  value={clientNotes}
                  onChange={(event) => setClientNotes(event.target.value)}
                  placeholder={t("admin.quote_transform.notes_placeholder")}
                />
              </label>
            </section>
          ) : null}

          {currentStep === 2 ? (
            <section className="card quote-transform-step-card">
              <h3>{t("admin.quote_transform.step2_title")}</h3>
              <p className="muted">{t("admin.quote_transform.step2_subtitle")}</p>

              <div className="grid cols-3 top-gap-sm">
                <label>
                  {t("admin.quote_transform.plan_formula")}
                  <select value={selectedPlanId} onChange={(event) => setSelectedPlanId(event.target.value)}>
                    <option value="">{t("admin.quote_transform.select")}</option>
                    {plans.map((plan) => (
                      <option key={plan.id} value={plan.id}>{plan.name} · {plan.kind}</option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("admin.quote_transform.legal_entity")}
                  <input type="text" value={selectedLegalEntity?.name || quote.legalEntityName} readOnly />
                </label>
                <label>
                  {t("admin.quote_transform.payment_plan")}
                  <input type="text" value={quote.paymentPlanName || "-"} readOnly />
                </label>
              </div>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>{t("admin.quote_transform.col_activity")}</th>
                      <th>{t("admin.quote_transform.col_location")}</th>
                      <th>{t("admin.quote_transform.col_unit")}</th>
                      <th>{t("admin.quote_transform.col_quantity_duration")}</th>
                      <th>{t("admin.quote_transform.col_quote_price")}</th>
                      <th>{t("admin.quote_transform.col_system_price")}</th>
                      <th>{t("admin.quote_transform.col_delta")}</th>
                      <th>{t("admin.quote_transform.col_status")}</th>
                      <th>{t("admin.quote_transform.col_actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activityRows.map((row) => (
                      <tr key={row.rowId}>
                        <td>{row.activityName}</td>
                        <td>{row.locationName}</td>
                        <td>{row.pricingUnit}</td>
                        <td>{row.quantity} · {row.durationMinutes || "-"} min</td>
                        <td>{currency(row.expectedTtc, quote.currency, language)}</td>
                        <td>{currency(row.currentSystemTtc, quote.currency, language)}</td>
                        <td>{currency(row.deltaTtc, quote.currency, language)}</td>
                        <td><span className={`status-pill ${statusClassName(row.status)}`}>{statusLabel(row.status, language)}</span></td>
                        <td>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => toggleAlignedActivity(row.scheduleKey)}
                          >
                            {alignedActivityIds.has(row.scheduleKey) ? t("admin.quote_transform.remove_alignment") : t("admin.quote_transform.align_to_quote")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {currentStep === 3 ? (
            <section className="card quote-transform-step-card">
              <h3>{t("admin.quote_transform.step3_title")}</h3>
              <p className="muted">{t("admin.quote_transform.step3_subtitle")}</p>

              <div className="quote-transform-schedule-stack top-gap-sm">
                {activityRows.map((row) => {
                  const options = sessionOptionsByActivityId.get(row.scheduleKey) || [];
                  const selectedSessionId = assignedSessionByActivityId[row.scheduleKey] || "";
                  const quoteContext = quotePlanningContextByScheduleKey.get(row.scheduleKey) || null;
                  return (
                    <article key={`schedule-${row.rowId}`} className="quote-transform-schedule-card">
                      <div className="row spread wrap gap-sm">
                        <div>
                          <h4>{row.activityName}</h4>
                          <p className="muted">{t("admin.quote_transform.current_selection")}: {selectedSessionLabel(options, selectedSessionId || null, language)}</p>
                        </div>
                        <div className="row wrap gap-sm">
                          <span className={`status-pill ${offPlanningActivityIds.has(row.scheduleKey) ? "status-warn" : options.length === 0 ? "quote-transform-status-blocked" : "status-ok"}`}>
                            {offPlanningActivityIds.has(row.scheduleKey)
                              ? t("admin.quote_transform.off_planning_badge")
                              : options.length === 0
                              ? t("admin.quote_transform.no_match_badge")
                              : t("admin.quote_transform.options_badge", { count: options.length })}
                          </span>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => toggleOffPlanningActivity(row.scheduleKey)}
                          >
                            {offPlanningActivityIds.has(row.scheduleKey) ? t("admin.quote_transform.move_back_to_schedule") : t("admin.quote_transform.move_off_planning")}
                          </button>
                        </div>
                      </div>

                      {quoteContext ? (
                        <div className="quote-transform-quote-context">
                          <strong>{t("admin.quote_transform.quote_context_title")}</strong>
                          <dl>
                            <div>
                              <dt>{t("admin.quote_transform.quote_context_activity")}</dt>
                              <dd>{quoteContext.activity}</dd>
                            </div>
                            <div>
                              <dt>{t("admin.quote_transform.quote_context_quantity")}</dt>
                              <dd>{quoteContext.quantity}</dd>
                            </div>
                            <div>
                              <dt>{t("admin.quote_transform.quote_context_slot")}</dt>
                              <dd>{quoteContext.slot}</dd>
                            </div>
                            <div>
                              <dt>{t("admin.quote_transform.quote_context_location")}</dt>
                              <dd>{quoteContext.location}</dd>
                            </div>
                          </dl>
                        </div>
                      ) : null}

                      {offPlanningActivityIds.has(row.scheduleKey) ? (
                        <p className="flash-warn top-gap-sm">{t("admin.quote_transform.off_planning_message")}</p>
                      ) : null}

                      {!offPlanningActivityIds.has(row.scheduleKey) ? (
                        <div className="quote-transform-session-grid top-gap-sm">
                          {options.length === 0 ? (
                            <p className="flash-err">{t("admin.quote_transform.no_compatible_slot")}</p>
                          ) : (
                            options.map((option) => (
                              <label key={option.sessionId} className={`quote-transform-session-option ${selectedSessionId === option.sessionId ? "active" : ""}`.trim()}>
                                <input
                                  type="radio"
                                  name={`session-${row.scheduleKey}`}
                                  value={option.sessionId}
                                  checked={selectedSessionId === option.sessionId}
                                  onChange={() => assignSession(row.scheduleKey, option.sessionId)}
                                />
                                <div>
                                  <div className="row wrap gap-sm">
                                    <strong>{option.label}</strong>
                                    {quoteContext && option.score >= 100 ? (
                                      <span className="status-pill status-ok">{t("admin.quote_transform.quote_option_matches")}</span>
                                    ) : quoteContext && normalizeComparable(option.locationName) !== normalizeComparable(quoteContext.location) ? (
                                      <span className="status-pill status-warn">{t("admin.quote_transform.quote_option_location_differs")}</span>
                                    ) : null}
                                    {option.recommended && options.length > 1 ? (
                                      <span className="status-pill status-ok">{t("admin.quote_transform.recommended_slot")}</span>
                                    ) : null}
                                  </div>
                                  <p className="muted">{option.dateLabel} · {option.locationName} · {option.teacher}</p>
                                  <p className="muted">
                                    {t(option.usesSeriesAvailability ? "admin.quote_transform.series_min_seats_remaining" : "admin.quote_transform.seats_remaining", { count: option.seatsRemaining })}
                                    {" · "}
                                    {t("admin.quote_transform.score", { score: option.score })}
                                  </p>
                                  {option.hasFullSeriesSession ? (
                                    <p className="muted">{t("admin.quote_transform.series_has_full_session")}</p>
                                  ) : null}
                                  <p className="muted">{option.reasons.map((reason) => translateQuoteTransformMessage(reason, language)).join(" · ")}</p>
                                </div>
                              </label>
                            ))
                          )}
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            </section>
          ) : null}

          {currentStep === 4 ? (
            <section className="card quote-transform-step-card">
              <h3>{t("admin.quote_transform.step4_title")}</h3>
              <p className="muted">{t("admin.quote_transform.step4_subtitle")}</p>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>{t("admin.quote_transform.col_type")}</th>
                      <th>{t("admin.quote_transform.col_label")}</th>
                      <th>{t("admin.quote_transform.col_ht")}</th>
                      <th>{t("admin.quote_transform.col_vat")}</th>
                      <th>{t("admin.quote_transform.col_ttc")}</th>
                      <th>{t("admin.quote_transform.col_status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {billingRows.map((row) => (
                      <tr key={row.rowId}>
                        <td>{row.type}</td>
                        <td>
                          <input
                            type="text"
                            value={row.label}
                            onChange={(event) => updateBillingRow(row.rowId, { label: event.target.value })}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min={row.type === "discount" ? undefined : "0"}
                            value={row.amountHt}
                            onChange={(event) => {
                              const nextHt = Number(event.target.value || "0");
                              const ratio = 1 + (row.vatRate / 100);
                              const nextTtc = Number((nextHt * ratio).toFixed(2));
                              updateBillingRow(row.rowId, { amountHt: nextHt, amountTtc: nextTtc });
                            }}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={row.vatRate}
                            onChange={(event) => {
                              const nextVat = Number(event.target.value || "0");
                              const ratio = 1 + (nextVat / 100);
                              const nextTtc = Number((row.amountHt * ratio).toFixed(2));
                              updateBillingRow(row.rowId, { vatRate: nextVat, amountTtc: nextTtc });
                            }}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            step="0.01"
                            min={row.type === "discount" ? undefined : "0"}
                            value={row.amountTtc}
                            onChange={(event) => updateBillingRow(row.rowId, { amountTtc: Number(event.target.value || "0") })}
                          />
                        </td>
                        <td><span className={`status-pill ${statusClassName(row.status)}`}>{statusLabel(row.status, language)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="muted top-gap-sm">
                {t("admin.quote_transform.off_planning_total_ht")}: <strong>{currency(billingTotals.totalHt, quote.currency, language)}</strong>
                {" · "}
                {t("admin.quote_transform.off_planning_total_ttc")}: <strong>{currency(billingTotals.totalTtc, quote.currency, language)}</strong>
              </p>
            </section>
          ) : null}

          {currentStep === 5 ? (
            <section className="card quote-transform-step-card">
              <h3>{t("admin.quote_transform.step5_title")}</h3>
              <p className="muted">{t("admin.quote_transform.step5_subtitle")}</p>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>{t("admin.quote_transform.col_section")}</th>
                      <th>{t("admin.quote_transform.col_quote_value")}</th>
                      <th>{t("admin.quote_transform.col_system_value")}</th>
                      <th>{t("admin.quote_transform.col_status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>{t("admin.quote_transform.section_client")}</td>
                      <td>{prospect ? displayName(prospect.firstName, prospect.lastName, prospect.email) : "-"}</td>
                      <td>{selectedClientName}</td>
                      <td><span className={`status-pill ${statusClassName(step1Status)}`}>{statusLabel(step1Status, language)}</span></td>
                    </tr>
                    <tr>
                      <td>{t("admin.quote_transform.section_formula_activities")}</td>
                      <td>{t("admin.quote_transform.comparison_formula_quote", {
                        formula: quote.quoteTypeFormulaName || t("admin.quote_transform.formula_fallback"),
                        count: activityRows.length,
                      })}</td>
                      <td>{t("admin.quote_transform.comparison_formula_system", {
                        plan: selectedPlan?.name || t("admin.quote_transform.none_feminine"),
                        count: activityRows.length,
                      })}</td>
                      <td><span className={`status-pill ${statusClassName(step2Status)}`}>{statusLabel(step2Status, language)}</span></td>
                    </tr>
                    <tr>
                      <td>{t("admin.quote_transform.section_schedule")}</td>
                      <td>{t("admin.quote_transform.quote_sessions", { count: activityRows.length })}</td>
                      <td>{t("admin.quote_transform.assignments", { count: Object.keys(assignedSessionByActivityId).length })}</td>
                      <td><span className={`status-pill ${statusClassName(step3Status)}`}>{statusLabel(step3Status, language)}</span></td>
                    </tr>
                    <tr>
                      <td>{t("admin.quote_transform.section_off_planning")}</td>
                      <td>{t("admin.quote_transform.lines_count", { count: billingRows.length })}</td>
                      <td>{currency(billingTotals.totalTtc, quote.currency, language)}</td>
                      <td><span className={`status-pill ${statusClassName(step4Status)}`}>{statusLabel(step4Status, language)}</span></td>
                    </tr>
                    <tr>
                      <td>{t("admin.quote_transform.section_totals_ttc")}</td>
                      <td>{currency(quote.totalTtc, quote.currency, language)}</td>
                      <td>{currency(systemTotalTtc, quote.currency, language)}</td>
                      <td><span className={`status-pill ${statusClassName(financialControl.status)}`}>{statusLabel(financialControl.status, language)}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {allIssues.length > 0 ? (
                <section className="top-gap-sm">
                  <h4>{t("admin.quote_transform.issues_decisions")}</h4>
                  <div className="quote-transform-issue-stack top-gap-sm">
                    {allIssues.map((issue) => (
                      <article key={issue.issueId} className={`quote-transform-issue-card ${issue.level === "blocked" ? "blocked" : "warning"}`}>
                        <div className="row spread wrap gap-sm">
                          <strong>{issue.level === "blocked" ? t("admin.quote_transform.issue_blocked") : t("admin.quote_transform.issue_warning")}</strong>
                          {issue.canOverride ? (
                            <label className="quote-transform-inline-checkbox">
                              <input
                                type="checkbox"
                                checked={acceptedBlockingIssueIds.has(issue.issueId)}
                                onChange={() => toggleBlockingAcceptance(issue.issueId)}
                              />
                              {t("admin.quote_transform.accept_difference")}
                            </label>
                          ) : null}
                        </div>
                        <p className="top-gap-sm">{issue.message}</p>
                      </article>
                    ))}
                  </div>
                </section>
              ) : (
                <p className="flash-ok top-gap-sm">{t("admin.quote_transform.no_difference")}</p>
              )}
            </section>
          ) : null}

          <section className="card quote-transform-actions">
            <div className="row spread wrap gap-sm">
              <div className="row wrap gap-sm">
                <button type="button" className="ghost" onClick={previousStep} disabled={currentStep === 1}>{t("admin.quote_transform.previous")}</button>
                <button
                  type="button"
                  onClick={nextStep}
                  disabled={currentStep === 5 || !canProceedFromStep(currentStep, stepStatuses[currentStep - 1])}
                >
                  {t("admin.quote_transform.next")}
                </button>
              </div>
              <div className="row wrap gap-sm">
                <form action={saveDraftAction}>
                  <input type="hidden" name="quote_id" value={quote.id} />
                  <input type="hidden" name="followup_id" value={followupId || ""} />
                  <input type="hidden" name="return_to" value={`${returnTo}${returnTo.includes("?") ? "&" : "?"}scenario=${encodeURIComponent(scenario)}`} />
                  <input type="hidden" name="transformation_json" value={JSON.stringify(draftPayload)} />
                  <button type="submit" className="ghost" disabled={saveDisabled}>{t("admin.quote_transform.save_draft")}</button>
                </form>

                <form id={`quote-transform-finalize-${quote.id}`} action={finalizeAction}>
                  <input type="hidden" name="quote_id" value={quote.id} />
                  <input type="hidden" name="followup_id" value={followupId || ""} />
                  <input type="hidden" name="allow_force_finalize" value={unresolvedBlockingIssues.length > 0 ? "0" : "1"} />
                  <input type="hidden" name="return_to" value={`${returnTo}${returnTo.includes("?") ? "&" : "?"}scenario=${encodeURIComponent(scenario)}`} />
                  <input type="hidden" name="transformation_json" value={JSON.stringify(draftPayload)} />
                  <ConfirmSubmitButton
                    formId={`quote-transform-finalize-${quote.id}`}
                    label={t("admin.quote_transform.finalize")}
                    title={t("admin.quote_transform.confirm_title")}
                    description={t("admin.quote_transform.confirm_description")}
                    confirmLabel={t("admin.quote_transform.confirm_execute")}
                    disabled={finalizeDisabled}
                    disabledReason={finalizeDisabledReason}
                  />
                </form>
              </div>
            </div>

            {followupId ? null : (
              <p className="flash-warn top-gap-sm">
                {t("admin.quote_transform.no_followup_persistence")}
              </p>
            )}
            {unresolvedBlockingIssues.length > 0 ? (
              <p className="flash-err top-gap-sm">
                {t("admin.quote_transform.critical_blocks_remaining", { count: unresolvedBlockingIssues.length })}
              </p>
            ) : null}
          </section>
        </main>
      </div>
    </section>
  );
}
