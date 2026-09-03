import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

function loadCommonJsTypeScript(url, requireImpl = () => {
  throw new Error("Unexpected dependency");
}) {
  const resolvedUrl = new URL(url, import.meta.url);
  const filename = resolvedUrl.pathname;
  const source = readFileSync(resolvedUrl, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  const module = { exports: {} };
  const factory = vm.runInThisContext(`(function (require, module, exports) { ${compiled}\n})`, { filename });
  factory(requireImpl, module, module.exports);
  return module.exports;
}

const ui = loadCommonJsTypeScript("../lib/ui-i18n.ts");
const quoteTransformation = loadCommonJsTypeScript(
  "../lib/quote-transformation.ts",
  (specifier) => {
    if (specifier === "./ui-i18n") {
      return ui;
    }
    throw new Error(`Unexpected dependency: ${specifier}`);
  },
);
const {
  buildSessionMatches,
  coerceQuoteToEnrollmentDraft,
  deriveScheduleSessionCounts,
} = quoteTransformation;

const activityId = "11111111-1111-4111-8111-111111111111";
const locationId = "22222222-2222-4222-8222-222222222222";

function session(id, status, startAtUtc) {
  return {
    id,
    courseTypeId: activityId,
    locationId,
    recurrenceGroupId: "33333333-3333-4333-8333-333333333333",
    locationName: "Online",
    title: "Solfège en ligne",
    startAtUtc,
    endAtUtc: new Date(new Date(startAtUtc).getTime() + 30 * 60_000).toISOString(),
    timezone: "Europe/Paris",
    teacherDisplayName: "Professeur",
    status,
    statusLabel: status,
    capacityMax: 10,
    bookedCount: 1,
    seatsRemaining: 9,
  };
}

test("completed recurring occurrences count toward the series without becoming the actionable slot", () => {
  const row = {
    rowId: "row",
    lineId: "line",
    scheduleKey: `${activityId}:online_solfege`,
    activityId,
    matchingActivityIds: [activityId],
    activityName: "Solfège en ligne",
    locationName: "Online",
    pricingUnit: "session",
    quantity: 2,
    durationMinutes: 30,
    expectedTtc: 0,
    baseRateTtc: 0,
    currentSystemTtc: 0,
    discountTtc: 0,
    supplementTtc: 0,
    deltaTtc: 0,
    status: "ok",
    reason: "alignement devis/systeme",
  };
  const options = buildSessionMatches(
    row,
    [
      session("completed", "COMPLETED", "2026-09-02T16:05:00Z"),
      session("cancelled", "CANCELLED", "2026-09-09T16:05:00Z"),
      session("scheduled", "SCHEDULED", "2026-09-16T16:05:00Z"),
    ],
    locationId,
    new Map(),
    "live",
  );

  assert.deepEqual(options.map((option) => option.sessionId), ["scheduled"]);
  assert.equal(options[0].seriesSize, 2);
  assert.equal(options[0].status, "SCHEDULED");
  assert.equal(options[0].localStartTime, "18:05");
  assert.equal(options[0].timezone, "Europe/Paris");
});

test("localized status labels never turn scheduled options into false blockers", () => {
  const scheduled = session("scheduled-localized", "SCHEDULED", "2026-09-30T16:35:00Z");
  scheduled.statusLabel = "Planifie";
  const row = {
    rowId: "row-localized",
    lineId: "line-localized",
    scheduleKey: `${activityId}:online_solfege`,
    activityId,
    matchingActivityIds: [activityId],
    activityName: "Solfège niveau 2",
    locationName: "Online",
    pricingUnit: "session",
    quantity: 26,
    durationMinutes: 45,
    expectedTtc: 0,
    baseRateTtc: 0,
    currentSystemTtc: 0,
    discountTtc: 0,
    supplementTtc: 0,
    deltaTtc: 0,
    status: "ok",
    reason: "alignement devis/systeme",
  };

  const options = buildSessionMatches(row, [scheduled], locationId, new Map(), "live");

  assert.equal(options.length, 1);
  assert.equal(options[0].status, "SCHEDULED");
});

test("a session without a valid local timezone is never proposed", () => {
  const invalid = session("missing-timezone", "SCHEDULED", "2026-09-16T16:05:00Z");
  invalid.timezone = "";
  const options = buildSessionMatches(
    {
      rowId: "row",
      lineId: "line",
      scheduleKey: activityId,
      activityId,
      matchingActivityIds: [activityId],
      activityName: "Cours en ligne",
      locationName: "Online",
      pricingUnit: "session",
      quantity: 1,
      durationMinutes: 30,
      expectedTtc: 0,
      baseRateTtc: 0,
      currentSystemTtc: 0,
      discountTtc: 0,
      supplementTtc: 0,
      deltaTtc: 0,
      status: "ok",
      reason: "alignement devis/systeme",
    },
    [invalid],
    locationId,
    new Map(),
    "live",
  );

  assert.deepEqual(options, []);
});

test("a unique suffixed solfege block exposes its approved count through the bare activity key", () => {
  const counts = deriveScheduleSessionCounts({
    blocks: [
      {
        activity_id: activityId,
        recommendation_key: `${activityId}:online_solfege`,
        sessions_count: 13,
      },
    ],
  });

  assert.equal(counts.get(`${activityId}:online_solfege`), 13);
  assert.equal(counts.get(activityId), 13);
});

test("stable series metadata survives draft reload", () => {
  const raw = {
    version: 1,
    scenario: "live",
    currentStep: 3,
    clientResolution: { mode: "existing", selectedClientId: null, selectedParentClientId: null, notes: "" },
    activityResolution: { planId: null, alignedActivityIds: [], offPlanningActivityIds: [] },
    scheduleResolution: {
      assignedSessionByActivityId: { [activityId]: "scheduled" },
      seriesAssignmentsByActivityId: {
        [activityId]: {
          sessionId: "scheduled",
          recurrenceGroupId: "33333333-3333-4333-8333-333333333333",
          courseTypeId: activityId,
          locationId,
          timezone: "Europe/Paris",
          localWeekday: 2,
          localStartTime: "18:05",
          localEndTime: "18:35",
          expectedQuantity: 26,
        },
      },
    },
    billingResolution: { rows: [] },
    acceptedBlockingIssueIds: [],
    financialControl: { expectedTtc: 0, systemTtc: 0, deltaTtc: 0 },
    idempotencyKey: "stable-key",
    logs: [],
    finalizedAt: null,
  };

  const draft = coerceQuoteToEnrollmentDraft(raw);
  assert.ok(draft);
  assert.equal(draft.scheduleResolution.seriesAssignmentsByActivityId[activityId].localStartTime, "18:05");
  assert.equal(draft.scheduleResolution.seriesAssignmentsByActivityId[activityId].expectedQuantity, 26);
});

test("the exact series accepted in the quote remains recommended even when it became full", () => {
  const approvedSeriesId = "44444444-4444-4444-8444-444444444444";
  const alternativeSeriesId = "55555555-5555-4555-8555-555555555555";
  const pompeId = "66666666-6666-4666-8666-666666666666";
  const schefferId = "77777777-7777-4777-8777-777777777777";
  const row = {
    rowId: "row-approved-full",
    lineId: "line-approved-full",
    scheduleKey: activityId,
    activityId,
    matchingActivityIds: [activityId],
    activityName: "Cours collectif enfants",
    locationName: "Rue de la Pompe",
    pricingUnit: "session",
    quantity: 2,
    durationMinutes: 60,
    expectedTtc: 76,
    baseRateTtc: 38,
    currentSystemTtc: 76,
    discountTtc: 0,
    supplementTtc: 0,
    deltaTtc: 0,
    status: "ok",
    reason: "tarif contractuel",
  };
  const makeSession = (id, seriesId, locationIdValue, locationName, seatsRemaining) => ({
    ...session(id, "SCHEDULED", "2026-09-09T12:00:00Z"),
    recurrenceGroupId: seriesId,
    locationId: locationIdValue,
    locationName,
    capacityMax: 6,
    bookedCount: 6 - seatsRemaining,
    seatsRemaining,
  });
  const hints = new Map([[activityId, {
    activityId,
    seriesKey: approvedSeriesId,
    locationId: pompeId,
    selectedSessionId: null,
    startDate: "2026-09-09",
    weekday: 2,
    startTime: "14:00",
    endTime: "15:00",
  }]]);

  const options = buildSessionMatches(
    row,
    [
      makeSession("approved-1", approvedSeriesId, pompeId, "Rue de la Pompe", 0),
      makeSession("approved-2", approvedSeriesId, pompeId, "Rue de la Pompe", 0),
      makeSession("alternative-1", alternativeSeriesId, schefferId, "Rue Scheffer", 3),
      makeSession("alternative-2", alternativeSeriesId, schefferId, "Rue Scheffer", 3),
    ],
    pompeId,
    hints,
    "live",
  );

  assert.equal(options[0].recurrenceGroupId, approvedSeriesId);
  assert.equal(options[0].approvedQuoteSelection, true);
  assert.equal(options[0].recommended, true);
  assert.equal(options[0].seatsRemaining, 0);
  assert.notEqual(options[1].approvedQuoteSelection, true);
});
