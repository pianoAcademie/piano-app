"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  buildActivityPricingRows,
  buildBillingExtraRows,
  buildClientMatchCandidates,
  buildIdempotencyKey,
  buildSessionMatches,
  coerceQuoteToEnrollmentDraft,
  deriveActivityLocationNameById,
  deriveScheduleHints,
  displayName,
  evaluateFinancialStatus,
  sumBillingRows,
  summarizeStatus,
  type BillingExtraRow,
  type QuoteToEnrollmentDraft,
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
};

function statusLabel(status: QuoteTransformStatus): string {
  if (status === "ok") {
    return "ok";
  }
  if (status === "warning") {
    return "warning";
  }
  return "blocked";
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

function currency(value: number, code: string): string {
  if (!Number.isFinite(value)) {
    return `${value} ${code}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency: code || "EUR" }).format(value);
  } catch {
    return `${value.toFixed(2)} ${(code || "EUR").toUpperCase()}`;
  }
}

function isSupportedStep(step: number): step is 1 | 2 | 3 | 4 | 5 {
  return step === 1 || step === 2 || step === 3 || step === 4 || step === 5;
}

function billingStatus(row: BillingExtraRow): QuoteTransformStatus {
  if (row.amountTtc <= 0 || row.vatRate < 0) {
    return "blocked";
  }
  if (row.vatRate === 0 && row.type !== "discount") {
    return "warning";
  }
  return "ok";
}

function canProceedFromStep(step: number, status: QuoteTransformStatus): boolean {
  if (step === 5) {
    return true;
  }
  return status !== "blocked";
}

function selectedSessionLabel(options: SessionMatchOption[], selectedSessionId: string | null): string {
  if (!selectedSessionId) {
    return "Aucun";
  }
  const selected = options.find((option) => option.sessionId === selectedSessionId);
  if (!selected) {
    return "Aucun";
  }
  return `${selected.label} (${selected.dateLabel})`;
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
}: QuoteToEnrollmentWizardProps): JSX.Element {
  const restoredDraft = useMemo(() => (initialDraft ? coerceQuoteToEnrollmentDraft(initialDraft) : null), [initialDraft]);
  const activitiesById = useMemo(() => new Map(activities.map((activity) => [activity.id, activity])), [activities]);
  const clientsById = useMemo(() => new Map(clients.map((client) => [client.id, client])), [clients]);
  const clientCandidates = useMemo(
    () => buildClientMatchCandidates(prospect, clients, scenario),
    [prospect, clients, scenario],
  );
  const bestClientCandidate = clientCandidates[0] || null;
  const bestCandidateClient = bestClientCandidate ? clientsById.get(bestClientCandidate.clientId) || null : null;
  const hasStrongClientCandidate = (bestClientCandidate?.confidence || 0) >= 80;
  const existingClientOptions = useMemo(() => {
    const output = new Map<string, { id: string; label: string }>();
    for (const candidate of clientCandidates) {
      output.set(candidate.clientId, {
        id: candidate.clientId,
        label: `${candidate.displayName} · ${candidate.email} · match ${candidate.confidence}`,
      });
    }
    for (const client of clients.slice(0, 300)) {
      if (output.has(client.id)) {
        continue;
      }
      output.set(client.id, {
        id: client.id,
        label: `${displayName(client.firstName, client.lastName, client.email)} · ${client.email}`,
      });
    }
    return Array.from(output.values());
  }, [clientCandidates, clients]);

  const initialClientMode =
    restoredDraft?.clientResolution.mode
    ?? (scenario === "A"
      ? "new_adult"
      : scenario === "C"
      ? "new_parent_child"
      : hasStrongClientCandidate
      ? "existing"
      : prospect?.prospectType === "child"
      ? "new_parent_child"
      : "existing");

  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4 | 5>(() => {
    const stepCandidate = Number(preferredStep ?? restoredDraft?.currentStep ?? 1);
    return isSupportedStep(stepCandidate) ? stepCandidate : 1;
  });
  const [clientMode, setClientMode] = useState<"existing" | "new_adult" | "new_parent_child">(
    initialClientMode === "existing" || initialClientMode === "new_parent_child" ? initialClientMode : "new_adult",
  );
  const [selectedClientId, setSelectedClientId] = useState<string>(
    restoredDraft?.clientResolution.selectedClientId
    || (initialClientMode === "existing" ? bestClientCandidate?.clientId || "" : ""),
  );
  const [selectedParentClientId, setSelectedParentClientId] = useState<string>(
    restoredDraft?.clientResolution.selectedParentClientId
    || (
      initialClientMode === "new_parent_child"
      && String(bestCandidateClient?.clientKind || "").toUpperCase() === "ADULT"
      ? bestClientCandidate?.clientId || ""
      : ""
    ),
  );
  const [clientNotes, setClientNotes] = useState<string>(restoredDraft?.clientResolution.notes || "");

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

  const baseActivityRows = useMemo(
    () => buildActivityPricingRows(lines, activitiesById, activityLocationNameById, quote.locationName, scenario),
    [lines, activitiesById, activityLocationNameById, quote.locationName, scenario],
  );

  const activityRows = useMemo(
    () => baseActivityRows.map((row) => {
      if (!alignedActivityIds.has(row.activityId)) {
        return row;
      }
      return {
        ...row,
        currentSystemTtc: row.expectedTtc,
        deltaTtc: 0,
        status: "ok" as const,
        reason: "alignement manuel sur devis",
      };
    }),
    [baseActivityRows, alignedActivityIds],
  );

  const scheduleHints = useMemo(() => deriveScheduleHints(calendarSnapshot), [calendarSnapshot]);

  const sessionOptionsByActivityId = useMemo(() => {
    const output = new Map<string, SessionMatchOption[]>();
    for (const row of activityRows) {
      const sessions = sessionsByActivityId[row.activityId] || [];
      const options = buildSessionMatches(row, sessions, quote.locationId, scheduleHints, scenario);
      output.set(row.activityId, options);
    }
    return output;
  }, [activityRows, sessionsByActivityId, quote.locationId, scheduleHints, scenario]);

  const [assignedSessionByActivityId, setAssignedSessionByActivityId] = useState<Record<string, string>>(() => {
    const restored = restoredDraft?.scheduleResolution.assignedSessionByActivityId || {};
    if (Object.keys(restored).length > 0) {
      return { ...restored };
    }

    const defaults: Record<string, string> = {};
    if (scenario === "A") {
      for (const row of baseActivityRows) {
        const options = sessionOptionsByActivityId.get(row.activityId) || [];
        const firstUsable = options.find((option) => option.seatsRemaining > 0) || options[0];
        if (firstUsable) {
          defaults[row.activityId] = firstUsable.sessionId;
        }
      }
    }
    return defaults;
  });

  const suggestedBillingRows = useMemo(
    () => buildBillingExtraRows(lines, activityRows, offPlanningActivityIds),
    [lines, activityRows, offPlanningActivityIds],
  );

  const [billingRows, setBillingRows] = useState<BillingExtraRow[]>(() => {
    if (restoredDraft?.billingResolution.rows && restoredDraft.billingResolution.rows.length > 0) {
      return restoredDraft.billingResolution.rows.map((row) => {
        const amountVat = Number((row.amountTtc - row.amountHt).toFixed(2));
        const mapped: BillingExtraRow = {
          rowId: row.rowId,
          sourceLineId: null,
          type: row.type,
          label: row.label,
          amountHt: row.amountHt,
          vatRate: row.vatRate,
          amountVat,
          amountTtc: row.amountTtc,
          status: "ok",
          editable: true,
        };
        return { ...mapped, status: billingStatus(mapped) };
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
          status: stored.status,
        };
        return { ...next, status: billingStatus(next) };
      });

      const preservedCustom = previous.filter((row) => !suggestedBillingRows.some((suggested) => suggested.rowId === row.rowId));
      return [...merged, ...preservedCustom];
    });
  }, [suggestedBillingRows]);

  const [acceptedBlockingIssueIds, setAcceptedBlockingIssueIds] = useState<Set<string>>(
    () => new Set(restoredDraft?.acceptedBlockingIssueIds || []),
  );

  const step1Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    if (!prospect) {
      issues.push({
        issueId: "step1-prospect-missing",
        step: 1,
        level: "blocked",
        message: "Prospect introuvable pour ce devis.",
        canOverride: false,
      });
    }

    if (clientMode === "existing") {
      if (!selectedClientId) {
        issues.push({
          issueId: "step1-client-selection-required",
          step: 1,
          level: "blocked",
          message: "Selectionnez une fiche client existante ou passez en creation.",
          canOverride: false,
        });
      } else if (!clientsById.has(selectedClientId)) {
        issues.push({
          issueId: "step1-client-selection-invalid",
          step: 1,
          level: "blocked",
          message: "La fiche client selectionnee est invalide. Selectionnez une fiche existante.",
          canOverride: false,
        });
      }
    }

    if (scenario === "B" && clientCandidates.length > 1) {
      issues.push({
        issueId: "step1-ambiguous-matches",
        step: 1,
        level: "warning",
        message: "Plusieurs correspondances client probables detectees.",
        canOverride: false,
      });
    }

    if (clientMode === "new_parent_child" && !selectedParentClientId) {
      issues.push({
        issueId: "step1-parent-to-create",
        step: 1,
        level: "warning",
        message: "Parent responsable non selectionne: creation parent + enfant prevue.",
        canOverride: false,
      });
    }

    return issues;
  }, [prospect, clientMode, selectedClientId, selectedParentClientId, scenario, clientCandidates.length, clientsById]);

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
        message: "Selectionnez une formule/plan pour l'inscription.",
        canOverride: false,
      });
    }

    for (const row of activityRows) {
      if (row.status === "ok") {
        continue;
      }
      issues.push({
        issueId: `step2-pricing-${row.activityId}`,
        step: 2,
        level: row.status === "blocked" ? "blocked" : "warning",
        message: `${row.activityName}: ${row.reason} (ecart ${currency(row.deltaTtc, quote.currency)}).`,
        canOverride: row.status === "warning",
      });
    }
    return issues;
  }, [selectedPlanId, activityRows, quote.currency]);

  const step2Status = useMemo(
    () => summarizeStatus(step2Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step2Issues],
  );

  const step3Issues = useMemo(() => {
    const issues: StepIssue[] = [];
    for (const row of activityRows) {
      if (offPlanningActivityIds.has(row.activityId)) {
        issues.push({
          issueId: `step3-off-planning-${row.activityId}`,
          step: 3,
          level: "warning",
          message: `${row.activityName}: bascule hors planning (facturation dediee).`,
          canOverride: false,
        });
        continue;
      }

      const options = sessionOptionsByActivityId.get(row.activityId) || [];
      if (options.length === 0) {
        issues.push({
          issueId: `step3-no-session-${row.activityId}`,
          step: 3,
          level: "blocked",
          message: `${row.activityName}: aucun creneau compatible trouve.`,
          canOverride: false,
        });
        continue;
      }

      const selectedSessionId = assignedSessionByActivityId[row.activityId] || "";
      if (!selectedSessionId) {
        issues.push({
          issueId: `step3-session-choice-required-${row.activityId}`,
          step: 3,
          level: "blocked",
          message: `${row.activityName}: selection de creneau obligatoire.`,
          canOverride: false,
        });
        continue;
      }

      const selectedOption = options.find((option) => option.sessionId === selectedSessionId);
      if (!selectedOption) {
        issues.push({
          issueId: `step3-session-choice-invalid-${row.activityId}`,
          step: 3,
          level: "blocked",
          message: `${row.activityName}: creneau selectionne invalide.`,
          canOverride: false,
        });
        continue;
      }

      if (selectedOption.seatsRemaining <= 0) {
        issues.push({
          issueId: `step3-session-full-${row.activityId}`,
          step: 3,
          level: "blocked",
          message: `${row.activityName}: creneau complet, choisir une autre option.`,
          canOverride: false,
        });
      } else if (options.length > 1) {
        issues.push({
          issueId: `step3-session-multiple-${row.activityId}`,
          step: 3,
          level: "warning",
          message: `${row.activityName}: plusieurs creneaux compatibles disponibles.`,
          canOverride: false,
        });
      }
    }
    return issues;
  }, [activityRows, offPlanningActivityIds, sessionOptionsByActivityId, assignedSessionByActivityId]);

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
        message: `${row.label}: ligne hors planning a corriger (${statusLabel(row.status)}).`,
        canOverride: row.status === "warning",
      });
    }
    return issues;
  }, [billingRows]);

  const step4Status = useMemo(
    () => summarizeStatus(step4Issues.map((issue) => (issue.level === "blocked" ? "blocked" : "warning"))),
    [step4Issues],
  );

  const scheduledActivitiesTotal = useMemo(
    () => activityRows
      .filter((row) => !offPlanningActivityIds.has(row.activityId))
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
        message: `Controle financier: ecart total ${currency(financialControl.deltaTtc, quote.currency)} entre devis et systeme.`,
        canOverride: financialControl.status === "blocked" && absDelta <= 30,
      });
    }

    if (!followupId) {
      issues.push({
        issueId: "step5-followup-missing",
        step: 5,
        level: "warning",
        message: "Aucun follow-up existant: sauvegarde brouillon indisponible tant que le devis n'est pas valide.",
        canOverride: false,
      });
    }

    return issues;
  }, [financialControl, quote.currency, followupId]);

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
      return clientMode === "new_parent_child" ? "Creation parent + enfant" : "Creation nouveau client";
    }
    const candidate = clientCandidates.find((item) => item.clientId === selectedClientId);
    if (candidate) {
      return candidate.displayName;
    }
    const selectedClient = clientsById.get(selectedClientId);
    if (!selectedClient) {
      return "Aucun client choisi";
    }
    return displayName(selectedClient.firstName, selectedClient.lastName, selectedClient.email);
  }, [clientMode, clientCandidates, selectedClientId, clientsById]);

  const selectedPlan = plans.find((plan) => plan.id === selectedPlanId) || null;
  const selectedLegalEntity = legalEntities.find((entity) => entity.id === quote.legalEntityId) || null;

  const saveDisabled = !followupId;
  const finalizeDisabled = !followupId || unresolvedBlockingIssues.length > 0;

  const draftPayload = useMemo<QuoteToEnrollmentDraft>(() => {
    const draftRows = billingRows.map((row) => ({
      rowId: row.rowId,
      type: row.type,
      label: row.label,
      amountHt: Number(row.amountHt.toFixed(2)),
      vatRate: Number(row.vatRate.toFixed(2)),
      amountTtc: Number(row.amountTtc.toFixed(2)),
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
    { step: 1 as const, label: "Client", status: step1Status },
    { step: 2 as const, label: "Formule et activites", status: step2Status },
    { step: 3 as const, label: "Planning / creneaux", status: step3Status },
    { step: 4 as const, label: "Facturation hors planning", status: step4Status },
    { step: 5 as const, label: "Controle final", status: step5Status },
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
            <h2>Transformation devis vers inscription</h2>
            <p className="muted">
              Devis <strong>{quote.quoteNumber}</strong> · {quote.quoteType} · {currency(quote.totalTtc, quote.currency)}
            </p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href={backPath}>Retour devis</Link>
          </div>
        </div>
        <div className="quote-transform-header-kpis top-gap-sm">
          <span className="badge">Prospect / client: {prospect ? displayName(prospect.firstName, prospect.lastName, prospect.email) : "-"}</span>
          <span className="badge">Annee scolaire: {quote.schoolYearLabel || "-"}</span>
          <span className="badge">Entite legale: {selectedLegalEntity?.name || quote.legalEntityName}</span>
          <span className="badge">Statut follow-up: {followupStatus || "absent"}</span>
        </div>
      </header>

      <div className="quote-transform-layout">
        <aside className="card quote-transform-sidebar">
          <h3>Resume transformation</h3>
          <div className="quote-transform-sidebar-grid top-gap-sm">
            <p><strong>Client cible:</strong> {selectedClientName}</p>
            <p><strong>Plan:</strong> {selectedPlan?.name || "Aucun"}</p>
            <p><strong>Activites:</strong> {activityRows.length}</p>
            <p><strong>Hors planning:</strong> {offPlanningActivityIds.size}</p>
            <p><strong>Total devis:</strong> {currency(quote.totalTtc, quote.currency)}</p>
            <p><strong>Total systeme:</strong> {currency(systemTotalTtc, quote.currency)}</p>
          </div>

          <section className="top-gap-sm">
            <h4>Scenarios localhost</h4>
            <div className="quote-transform-scenario-list top-gap-sm">
              {scenarioLinks.map((item) => (
                <Link key={item.scenario} href={item.href} className={`quote-transform-scenario-link ${item.active ? "active" : ""}`.trim()}>
                  {item.label}
                </Link>
              ))}
            </div>
            <p className="muted top-gap-sm">A, B et C injectent des cas de test. Live utilise uniquement les donnees reelles.</p>
          </section>

          <section className="top-gap-sm">
            <h4>Etapes</h4>
            <div className="quote-transform-step-list top-gap-sm">
              {stepper.map((item) => (
                <button
                  key={`sidebar-step-${item.step}`}
                  type="button"
                  className={`quote-transform-step-link ${currentStep === item.step ? "active" : ""}`.trim()}
                  onClick={() => setCurrentStep(item.step)}
                >
                  <span>{item.step}. {item.label}</span>
                  <span className={`status-pill ${statusClassName(item.status)}`}>{statusLabel(item.status)}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="top-gap-sm">
            <h4>Issues</h4>
            <div className="quote-transform-issue-kpis top-gap-sm">
              <span className="status-pill status-ok">OK {okStepsCount}</span>
              <span className="status-pill status-warn">Warnings {allIssues.filter((issue) => issue.level === "warning").length}</span>
              <span className="status-pill quote-transform-status-blocked">Blocked {unresolvedBlockingIssues.length}</span>
            </div>
          </section>
        </aside>

        <main className="quote-transform-main">
          <section className="card quote-transform-stepper-card">
            <ol className="quote-transform-stepper" aria-label="Etapes transformation">
              {stepper.map((item) => (
                <li key={`stepper-${item.step}`} className={currentStep === item.step ? "active" : ""}>
                  <button type="button" onClick={() => setCurrentStep(item.step)}>
                    <strong>{item.step}</strong>
                    <span>{item.label}</span>
                    <small className={`status-pill ${statusClassName(item.status)}`}>{statusLabel(item.status)}</small>
                  </button>
                </li>
              ))}
            </ol>
          </section>

          {currentStep === 1 ? (
            <section className="card quote-transform-step-card">
              <h3>Etape 1 · Client</h3>
              <p className="muted">Identifier la fiche client existante ou preparer la creation sans doublon.</p>

              <div className="grid cols-2 top-gap-sm">
                <article className="item">
                  <h4>Prospect devis</h4>
                  <p><strong>Nom:</strong> {prospect ? displayName(prospect.firstName, prospect.lastName, prospect.email) : "-"}</p>
                  <p><strong>Email:</strong> {prospect?.email || "-"}</p>
                  <p><strong>Telephone:</strong> {prospect?.phone || "-"}</p>
                  <p><strong>Type:</strong> {prospect?.prospectType === "child" ? "Enfant" : "Adulte"}</p>
                </article>
                <article className="item">
                  <h4>Mode de resolution</h4>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="existing"
                      checked={clientMode === "existing"}
                      onChange={() => setClientMode("existing")}
                    />
                    Utiliser une fiche existante
                  </label>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="new_adult"
                      checked={clientMode === "new_adult"}
                      onChange={() => setClientMode("new_adult")}
                    />
                    Creer un nouveau client
                  </label>
                  <label className="quote-transform-radio">
                    <input
                      type="radio"
                      name="client_mode"
                      value="new_parent_child"
                      checked={clientMode === "new_parent_child"}
                      onChange={() => setClientMode("new_parent_child")}
                    />
                    Creer parent + enfant
                  </label>
                </article>
              </div>

              <section className="top-gap-sm">
                <h4>Correspondances detectees</h4>
                {clientCandidates.length === 0 ? (
                  <p className="flash-warn top-gap-sm">Aucune correspondance automatique au-dessus du seuil.</p>
                ) : (
                  <div className="table-wrap top-gap-sm">
                    <table className="data-table quote-transform-compact-table">
                      <thead>
                        <tr>
                          <th>Client</th>
                          <th>Email</th>
                          <th>Telephone</th>
                          <th>Confiance</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {clientCandidates.map((candidate) => (
                          <tr key={candidate.clientId}>
                            <td>
                              <strong>{candidate.displayName}</strong>
                              <small className="muted block">{candidate.reasons.join(" · ")}</small>
                            </td>
                            <td>{candidate.email}</td>
                            <td>{candidate.phone || "-"}</td>
                            <td>
                              <span className={`status-pill ${candidate.confidence >= 80 ? "status-ok" : candidate.confidence >= 55 ? "status-warn" : "quote-transform-status-blocked"}`}>
                                {candidate.confidenceLabel} ({candidate.confidence})
                              </span>
                            </td>
                            <td>
                              <div className="row wrap gap-sm">
                                <button
                                  type="button"
                                  className="ghost"
                                  onClick={() => {
                                    setClientMode("existing");
                                    setSelectedClientId(candidate.clientId);
                                  }}
                                >
                                  Utiliser cette fiche
                                </button>
                                {clientsById.has(candidate.clientId) ? (
                                  <Link className="ghost" href={`/admin/clients/${encodeURIComponent(candidate.clientId)}`} target="_blank">
                                    Voir detail
                                  </Link>
                                ) : (
                                  <span className="muted">Simulation locale</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {clientMode === "existing" ? (
                <label className="top-gap-sm">
                  Fiche client retenue
                  <select value={selectedClientId} onChange={(event) => setSelectedClientId(event.target.value)}>
                    <option value="">Selectionner</option>
                    {existingClientOptions.map((option) => (
                      <option key={`client-option-${option.id}`} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              {clientMode === "new_parent_child" ? (
                <label className="top-gap-sm">
                  Parent existant a rattacher (optionnel)
                  <select value={selectedParentClientId} onChange={(event) => setSelectedParentClientId(event.target.value)}>
                    <option value="">Creer un nouveau parent</option>
                    {clients
                      .filter((client) => String(client.clientKind || "").toUpperCase() === "ADULT")
                      .slice(0, 60)
                      .map((client) => (
                        <option key={`parent-option-${client.id}`} value={client.id}>
                          {displayName(client.firstName, client.lastName, client.email)}
                        </option>
                      ))}
                  </select>
                </label>
              ) : null}

              <label className="top-gap-sm">
                Notes de transformation
                <textarea
                  rows={3}
                  value={clientNotes}
                  onChange={(event) => setClientNotes(event.target.value)}
                  placeholder="Arbitrage, decisions, contraintes famille..."
                />
              </label>
            </section>
          ) : null}

          {currentStep === 2 ? (
            <section className="card quote-transform-step-card">
              <h3>Etape 2 · Formule et activites</h3>
              <p className="muted">Reprise automatique des objets metier et visualisation immediate des ecarts devis/systeme.</p>

              <div className="grid cols-3 top-gap-sm">
                <label>
                  Formule / plan
                  <select value={selectedPlanId} onChange={(event) => setSelectedPlanId(event.target.value)}>
                    <option value="">Selectionner</option>
                    {plans.map((plan) => (
                      <option key={plan.id} value={plan.id}>{plan.name} · {plan.kind}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Entite legale
                  <input type="text" value={selectedLegalEntity?.name || quote.legalEntityName} readOnly />
                </label>
                <label>
                  Plan paiement
                  <input type="text" value={quote.paymentPlanName || "-"} readOnly />
                </label>
              </div>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>Activite</th>
                      <th>Lieu</th>
                      <th>Unite</th>
                      <th>Quantite / duree</th>
                      <th>Prix devis</th>
                      <th>Prix systeme</th>
                      <th>Ecart</th>
                      <th>Statut</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activityRows.map((row) => (
                      <tr key={row.rowId}>
                        <td>{row.activityName}</td>
                        <td>{row.locationName}</td>
                        <td>{row.pricingUnit}</td>
                        <td>{row.quantity} · {row.durationMinutes || "-"} min</td>
                        <td>{currency(row.expectedTtc, quote.currency)}</td>
                        <td>{currency(row.currentSystemTtc, quote.currency)}</td>
                        <td>{currency(row.deltaTtc, quote.currency)}</td>
                        <td><span className={`status-pill ${statusClassName(row.status)}`}>{statusLabel(row.status)}</span></td>
                        <td>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => toggleAlignedActivity(row.activityId)}
                          >
                            {alignedActivityIds.has(row.activityId) ? "Retirer alignement" : "Aligner sur devis"}
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
              <h3>Etape 3 · Planning / creneaux</h3>
              <p className="muted">Matching cible sur la date de demarrage de l'activite du devis, puis meme horaire et capacite disponible.</p>

              <div className="quote-transform-schedule-stack top-gap-sm">
                {activityRows.map((row) => {
                  const options = sessionOptionsByActivityId.get(row.activityId) || [];
                  const selectedSessionId = assignedSessionByActivityId[row.activityId] || "";
                  return (
                    <article key={`schedule-${row.rowId}`} className="quote-transform-schedule-card">
                      <div className="row spread wrap gap-sm">
                        <div>
                          <h4>{row.activityName}</h4>
                          <p className="muted">Selection actuelle: {selectedSessionLabel(options, selectedSessionId || null)}</p>
                        </div>
                        <div className="row wrap gap-sm">
                          <span className={`status-pill ${offPlanningActivityIds.has(row.activityId) ? "status-warn" : options.length === 0 ? "quote-transform-status-blocked" : "status-ok"}`}>
                            {offPlanningActivityIds.has(row.activityId) ? "hors planning" : options.length === 0 ? "no match" : `${options.length} options`}
                          </span>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => toggleOffPlanningActivity(row.activityId)}
                          >
                            {offPlanningActivityIds.has(row.activityId) ? "Repasser en planning" : "Bascule hors planning"}
                          </button>
                        </div>
                      </div>

                      {offPlanningActivityIds.has(row.activityId) ? (
                        <p className="flash-warn top-gap-sm">Activite traitee en facturation hors planning a l'etape 4.</p>
                      ) : null}

                      {!offPlanningActivityIds.has(row.activityId) ? (
                        <div className="quote-transform-session-grid top-gap-sm">
                          {options.length === 0 ? (
                            <p className="flash-err">Aucun creneau compatible detecte.</p>
                          ) : (
                            options.map((option) => (
                              <label key={option.sessionId} className={`quote-transform-session-option ${selectedSessionId === option.sessionId ? "active" : ""}`.trim()}>
                                <input
                                  type="radio"
                                  name={`session-${row.activityId}`}
                                  value={option.sessionId}
                                  checked={selectedSessionId === option.sessionId}
                                  onChange={() => assignSession(row.activityId, option.sessionId)}
                                />
                                <div>
                                  <strong>{option.label}</strong>
                                  <p className="muted">{option.dateLabel} · {option.teacher}</p>
                                  <p className="muted">Places restantes: {option.seatsRemaining} · Score {option.score}</p>
                                  <p className="muted">{option.reasons.join(" · ")}</p>
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
              <h3>Etape 4 · Facturation hors planning</h3>
              <p className="muted">Lignes financieres hors booking: kits, options, pass recup, acompte, annexes.</p>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Libelle</th>
                      <th>HT</th>
                      <th>TVA</th>
                      <th>TTC</th>
                      <th>Statut</th>
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
                            min="0"
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
                            min="0"
                            value={row.amountTtc}
                            onChange={(event) => updateBillingRow(row.rowId, { amountTtc: Number(event.target.value || "0") })}
                          />
                        </td>
                        <td><span className={`status-pill ${statusClassName(row.status)}`}>{statusLabel(row.status)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="muted top-gap-sm">
                Total hors planning HT: <strong>{currency(billingTotals.totalHt, quote.currency)}</strong>
                {" · "}
                TTC: <strong>{currency(billingTotals.totalTtc, quote.currency)}</strong>
              </p>
            </section>
          ) : null}

          {currentStep === 5 ? (
            <section className="card quote-transform-step-card">
              <h3>Etape 5 · Controle final</h3>
              <p className="muted">Validation finale avec comparaison devis/systeme et blocage tant que les points critiques ne sont pas resolus.</p>

              <div className="table-wrap top-gap-sm">
                <table className="data-table quote-transform-compact-table">
                  <thead>
                    <tr>
                      <th>Section</th>
                      <th>Valeur devis</th>
                      <th>Valeur systeme</th>
                      <th>Statut</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Client</td>
                      <td>{prospect ? displayName(prospect.firstName, prospect.lastName, prospect.email) : "-"}</td>
                      <td>{selectedClientName}</td>
                      <td><span className={`status-pill ${statusClassName(step1Status)}`}>{statusLabel(step1Status)}</span></td>
                    </tr>
                    <tr>
                      <td>Formule / activites</td>
                      <td>{quote.quoteTypeFormulaName || "Formule devis"} · {activityRows.length} activites</td>
                      <td>{selectedPlan?.name || "Aucune"} · {activityRows.length} activites</td>
                      <td><span className={`status-pill ${statusClassName(step2Status)}`}>{statusLabel(step2Status)}</span></td>
                    </tr>
                    <tr>
                      <td>Planning</td>
                      <td>Sessions devis: {activityRows.length}</td>
                      <td>Affectations: {Object.keys(assignedSessionByActivityId).length}</td>
                      <td><span className={`status-pill ${statusClassName(step3Status)}`}>{statusLabel(step3Status)}</span></td>
                    </tr>
                    <tr>
                      <td>Hors planning</td>
                      <td>{billingRows.length} lignes</td>
                      <td>{currency(billingTotals.totalTtc, quote.currency)}</td>
                      <td><span className={`status-pill ${statusClassName(step4Status)}`}>{statusLabel(step4Status)}</span></td>
                    </tr>
                    <tr>
                      <td>Totaux TTC</td>
                      <td>{currency(quote.totalTtc, quote.currency)}</td>
                      <td>{currency(systemTotalTtc, quote.currency)}</td>
                      <td><span className={`status-pill ${statusClassName(financialControl.status)}`}>{statusLabel(financialControl.status)}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {allIssues.length > 0 ? (
                <section className="top-gap-sm">
                  <h4>Ecarts et decisions</h4>
                  <div className="quote-transform-issue-stack top-gap-sm">
                    {allIssues.map((issue) => (
                      <article key={issue.issueId} className={`quote-transform-issue-card ${issue.level === "blocked" ? "blocked" : "warning"}`}>
                        <div className="row spread wrap gap-sm">
                          <strong>{issue.level === "blocked" ? "Blocage" : "Warning"}</strong>
                          {issue.canOverride ? (
                            <label className="quote-transform-inline-checkbox">
                              <input
                                type="checkbox"
                                checked={acceptedBlockingIssueIds.has(issue.issueId)}
                                onChange={() => toggleBlockingAcceptance(issue.issueId)}
                              />
                              Accepter cet ecart
                            </label>
                          ) : null}
                        </div>
                        <p className="top-gap-sm">{issue.message}</p>
                      </article>
                    ))}
                  </div>
                </section>
              ) : (
                <p className="flash-ok top-gap-sm">Aucun ecart detecte.</p>
              )}
            </section>
          ) : null}

          <section className="card quote-transform-actions">
            <div className="row spread wrap gap-sm">
              <div className="row wrap gap-sm">
                <button type="button" className="ghost" onClick={previousStep} disabled={currentStep === 1}>Precedent</button>
                <button
                  type="button"
                  onClick={nextStep}
                  disabled={currentStep === 5 || !canProceedFromStep(currentStep, stepStatuses[currentStep - 1])}
                >
                  Suivant
                </button>
              </div>
              <div className="row wrap gap-sm">
                <form action={saveDraftAction}>
                  <input type="hidden" name="quote_id" value={quote.id} />
                  <input type="hidden" name="followup_id" value={followupId || ""} />
                  <input type="hidden" name="return_to" value={`${returnTo}${returnTo.includes("?") ? "&" : "?"}scenario=${encodeURIComponent(scenario)}`} />
                  <input type="hidden" name="transformation_json" value={JSON.stringify(draftPayload)} />
                  <button type="submit" className="ghost" disabled={saveDisabled}>Sauvegarder brouillon</button>
                </form>

                <form action={finalizeAction}>
                  <input type="hidden" name="quote_id" value={quote.id} />
                  <input type="hidden" name="followup_id" value={followupId || ""} />
                  <input type="hidden" name="allow_force_finalize" value={unresolvedBlockingIssues.length > 0 ? "0" : "1"} />
                  <input type="hidden" name="return_to" value={`${returnTo}${returnTo.includes("?") ? "&" : "?"}scenario=${encodeURIComponent(scenario)}`} />
                  <input type="hidden" name="transformation_json" value={JSON.stringify(draftPayload)} />
                  <button type="submit" disabled={finalizeDisabled}>Valider la transformation</button>
                </form>
              </div>
            </div>

            {followupId ? null : (
              <p className="flash-warn top-gap-sm">
                Aucun follow-up disponible pour ce devis. Validation client requise avant persistance workflow.
              </p>
            )}
            {unresolvedBlockingIssues.length > 0 ? (
              <p className="flash-err top-gap-sm">
                {unresolvedBlockingIssues.length} blocage(s) critique(s) restent a resoudre avant validation.
              </p>
            ) : null}
          </section>
        </main>
      </div>
    </section>
  );
}
