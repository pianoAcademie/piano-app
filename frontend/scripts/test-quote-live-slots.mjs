import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { fixture, pageFor, slots, saveHarness, editor } from "./helpers/quote-live-slot-fixture.mjs";

test("adding 32 Wednesdays preserves the existing 31 Saturdays through save and reload", async () => {
  const saturday = JSON.parse(readFileSync(new URL("./fixtures/quote-saturday-series.json", import.meta.url)));
  const sessions = [...fixture.sessions, ...saturday];
  const options = await slots({}, sessions);
  const wed = options.find(o => o.weekday === 2);
  const sat = options.find(o => o.weekday === 5);
  assert.equal(wed.sessions_count, 32);
  assert.equal(sat.sessions_count, 31);
  assert.equal(sat.end_date, "2027-06-19");
  const blocks = [sat, wed].map(option => editor.applyLiveSeriesToBlock({ modality: "ONSITE" }, option));
  const server = saveHarness(sessions);
  const snapshot = await server.buildCalendarSnapshotFromBlocks({
    blocks: server.parsePlanningBlocksJson(JSON.stringify(blocks)), quoteLines: [fixture.line],
    token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.equal(snapshot.sessions.length, 63);
  assert.deepEqual(snapshot.blocks.map(b => b.sessions_count), [31, 32]);
  const reloaded = editor.parseInitialBlocks(snapshot);
  assert.deepEqual(reloaded.map(b => [b.weekday, b.end_date, b.sessions_count]), [
    [5, "2027-06-19", 31], [2, "2027-06-16", 32],
  ]);
});

test("reproduction: a 31-Saturday quote offers all 32 Wednesdays through June 16", async () => {
  const [option] = await slots();
  assert.equal(option.sessions_count, 32);
  assert.equal(option.start_date, "2026-09-09");
  assert.equal(option.end_date, "2027-06-16");
  assert.equal(option.start_time, "17:00"); // Paris, including winter/summer DST
  assert.equal(option.end_time, "18:00");
  assert.equal(option.planning_session_limit, null);
  assert.match(option.label, /16\/06\/2027/);
  assert.match(option.label, /32/);
});

test("catalogue does not depend on billed quantity, other packs, or an existing block's start", async () => {
  const baseline = await slots({ lines: [] });
  for (const quantity of ["10", "31", "32", "64"]) {
    for (const meta of [{}, { planning_session_limit: 10 }, { typeform_template: { planning_session_limit: 26 } }]) {
      assert.deepEqual(await slots({
        lines: [{ ...fixture.line, quantity, meta }],
        planningSnapshot: { blocks: [{ ...baseline[0], start_date: "2027-01-06" }] },
      }), baseline);
    }
  }
});

test("small billed session packs constrain planning while annual quantities do not", () => {
  const { quoteLinePlanningLimit } = pageFor();
  assert.equal(quoteLinePlanningLimit(fixture.line), 0);
  assert.equal(quoteLinePlanningLimit({ ...fixture.line, quantity: "10.00" }), 10);
  assert.equal(quoteLinePlanningLimit({ ...fixture.line, meta: { planning_session_limit: 10 } }), 10);
  assert.equal(quoteLinePlanningLimit({ ...fixture.line, meta: { typeform_template: { planning_session_limit: 26 } } }), 26);
});

test("selecting a complete live series clears a stale inherited cap and custom period", async () => {
  const [option] = await slots({ lines: [] });
  const old = { planning_session_limit: 31, custom_period: true, forced_planning: true, recommendation_key: "keep-me" };
  const selected = editor.applyLiveSeriesToBlock(old, option);
  assert.equal(selected.planning_session_limit, null);
  assert.equal(selected.custom_period, false);
  assert.equal(selected.forced_planning, false);
  assert.equal(selected.sessions_count, 32);
  assert.equal(selected.recommendation_key, "keep-me");
  assert.equal(old.planning_session_limit, 31); // No mutation of saved state.
});

test("saved truncated/custom periods are not silently presented as the complete slot", async () => {
  const [option] = await slots();
  const complete = editor.applyLiveSeriesToBlock({}, option);
  const old = { ...complete, end_date: "2027-06-09", planning_session_limit: 31, sessions_count: 31 };
  assert.equal(editor.selectedLivePlanningOptionKey(old, [option]), "");
  assert.equal(old.end_date, "2027-06-09");
  assert.equal(editor.selectedLivePlanningOptionKey({ ...complete, custom_period: true }, [option]), "");
  const repaired = editor.applyLiveSeriesToBlock(old, option);
  assert.equal(editor.selectedLivePlanningOptionKey(repaired, [option]), option.key);
  assert.equal(editor.editablePlanningBlockChanged(old, repaired), true);
  assert.equal(editor.editablePlanningBlockChanged(complete, { ...complete }), false);
  assert.equal(editor.editablePlanningBlockChanged({ ...complete, planning_session_limit: 31 }, complete), true);
  assert.equal(editor.editablePlanningBlockChanged({ ...complete, sessions_count: 31 }, complete), true);
});

test("a saved live block with a stale 31-date cap is healed from the authoritative series", async () => {
  const [option] = await slots();
  const server = saveHarness();
  const selected = editor.applyLiveSeriesToBlock({ ...fixture.calendar }, option);
  const legacy = await server.buildCalendarSnapshotFromBlocks({
    blocks: server.parsePlanningBlocksJson(JSON.stringify([{ ...selected, end_date: "2027-06-09", planning_session_limit: 31 }])),
    quoteLines: [fixture.line], token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  const [saved] = editor.parseInitialBlocks(legacy);
  const snapshotRows = editor.parseSnapshotSessions(legacy);
  assert.equal(legacy.sessions.length, 32);
  assert.equal(legacy.blocks[0].sessions_count, 32);
  assert.equal(legacy.blocks[0].planning_session_limit, null);
  assert.equal(editor.displayedPlanningSessionDates(saved, snapshotRows, [option]).length, 32);
  const repaired = { ...editor.applyLiveSeriesToBlock(saved, option), dirty: true };
  const displayed = editor.displayedPlanningSessionDates(repaired, snapshotRows, [option]);
  assert.equal(displayed.length, 32);
  assert.equal(displayed.at(-1), "2027-06-16");
  assert.equal(legacy.sessions.length, 32);
});

test("a weekly block with a stale weekday and an end date one lesson early is repaired from production", async () => {
  const [option] = await slots();
  const server = saveHarness();
  const stale = {
    ...option,
    source: null,
    series_key: null,
    recurrence_frequency: "weekly",
    weekday: 1,
    weekday_label: "Mardi",
    end_date: "2027-06-09",
    planning_session_limit: 32,
  };
  const snapshot = await server.buildCalendarSnapshotFromBlocks({
    blocks: server.parsePlanningBlocksJson(JSON.stringify([stale])),
    quoteLines: [{ ...fixture.line, meta: { planning_session_limit: 32 } }],
    token: "fixture-only",
    returnTo: "/fixture",
    schoolYearLabel: "2026-2027",
  });
  assert.equal(snapshot.blocks[0].weekday, 2);
  assert.equal(snapshot.blocks[0].source, "live_planning");
  assert.equal(snapshot.blocks[0].sessions_count, 32);
  assert.equal(snapshot.blocks[0].end_date, "2027-06-16");
});

test("a new live draft displays actual dates, not a theoretical lesson cancelled in the middle of the year", async () => {
  const sessions = fixture.sessions.map((s, i) => i === 3 ? { ...s, status: "CANCELLED" } : s);
  const [option] = await slots({}, sessions);
  const draft = editor.applyLiveSeriesToBlock({ ...fixture.calendar, saved: false }, option);
  const displayed = editor.displayedPlanningSessionDates(draft, [], [option]);
  assert.equal(displayed.length, 31);
  assert.equal(displayed.includes(fixture.sessions[3].start_at_utc.slice(0, 10)), false);
  assert.equal(displayed.at(-1), "2027-06-16");
});

test("cancelled or missing lessons are never synthesized to match a billed quantity", async () => {
  const cancelled = fixture.sessions.map((s, i) => i === 3 ? { ...s, status: "CANCELLED" } : s);
  const [option] = await slots({ lines: [{ ...fixture.line, quantity: "32" }] }, cancelled);
  assert.equal(option.sessions_count, 31);
  assert.equal(option.end_date, "2027-06-16");
  const [missingTail] = await slots({ lines: [{ ...fixture.line, quantity: "32" }] }, fixture.sessions.slice(0, -1));
  assert.equal(missingTail.sessions_count, 31);
  assert.equal(missingTail.end_date, "2027-06-09");
});

test("duplicate occurrences and fragmented recurrence IDs do not inflate the series", async () => {
  const rows = [...fixture.sessions, { ...fixture.sessions[0], id: "duplicate", recurrence_group_id: "other-series" }].reverse();
  const [option] = await slots({}, rows);
  assert.equal(option.sessions_count, 32);
  assert.equal(option.end_date, "2027-06-16");
  assert.equal(option.series_key, fixture.sessions[0].recurrence_group_id);
  const fragmented = fixture.sessions.map((s, i) => ({ ...s, recurrence_group_id: i % 2 ? "one" : "two" }));
  assert.equal((await slots({}, fragmented))[0].series_key, "");
});

test("overlapping obsolete and partial recurrence groups never get stitched into one slot", async () => {
  const obsolete = fixture.sessions.slice(0, 26).map((row) => ({ ...row, id: `obsolete-${row.id}`, recurrence_group_id: "obsolete" }));
  const partialTail = fixture.sessions.slice(-4).map((row) => ({ ...row, id: `tail-${row.id}`, recurrence_group_id: "partial-tail" }));

  const [option] = await slots({}, [...obsolete, ...partialTail, ...fixture.sessions]);

  assert.equal(option.sessions_count, 32);
  assert.equal(option.series_key, fixture.sessions[0].recurrence_group_id);
  assert.deepEqual(option.session_dates, fixture.sessions.map((row) => row.start_at_utc.slice(0, 10)));
});

test("school closures and actual location-specific teaching ends are respected", async () => {
  const extra = { ...fixture.sessions.at(-1), start_at_utc: "2027-06-23T15:00:00Z", end_at_utc: "2027-06-23T16:00:00Z" };
  assert.equal((await slots({}, [...fixture.sessions, extra]))[0].sessions_count, 32);
  const bld = [...fixture.sessions, extra].map(s => ({ ...s, location_label: "Bar-le-Duc" }));
  assert.equal((await slots({}, bld))[0].sessions_count, 33);
  const closed = { ...fixture.calendar, closure_dates: [...fixture.calendar.closure_dates, "2027-06-16"] };
  assert.equal((await slots({ calendarPresets: [closed] }))[0].sessions_count, 31);
  const closureAllowed = { ...fixture.activity, exclude_school_vacations_in_recurrence: false };
  assert.equal((await slots({ activities: [closureAllowed], calendarPresets: [closed] }))[0].sessions_count, 32);
});


test("select → serialize → server snapshot → reload preserves all 32 dates, without double counting", async () => {
  const [option] = await slots();
  const selected = editor.applyLiveSeriesToBlock({ modality: "ONSITE", ...fixture.calendar }, option);
  const server = saveHarness();
  const blocks = server.parsePlanningBlocksJson(JSON.stringify([selected]));
  assert.ok(blocks);
  const snapshot = await server.buildCalendarSnapshotFromBlocks({
    blocks, quoteLines: [fixture.line], token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.equal(snapshot.sessions.length, 32);
  assert.equal(snapshot.blocks[0].sessions_count, 32);
  assert.equal(snapshot.blocks[0].end_date, "2027-06-16");
  assert.equal(new Set(snapshot.sessions.map(s => s.date)).size, 32);
  const [reloaded] = editor.parseInitialBlocks(snapshot);
  assert.equal(reloaded.planning_session_limit, null);
  assert.equal(reloaded.end_date, "2027-06-16");
  assert.equal(reloaded.sessions_count, 32);
  const second = await server.buildCalendarSnapshotFromBlocks({
    blocks: server.parsePlanningBlocksJson(JSON.stringify(snapshot.blocks)), quoteLines: [fixture.line],
    token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.deepEqual(second.sessions, snapshot.sessions);
});

test("an intentionally limited pack and a custom period remain limited on save", async () => {
  const [option] = await slots({ lines: [] });
  const server = saveHarness();
  const block = { ...option, location_label: "Rue Scheffer", ...fixture.calendar, recurrence_frequency: "weekly" };
  const pack = await server.buildCalendarSnapshotFromBlocks({
    blocks: [block], quoteLines: [{ ...fixture.line, meta: { planning_session_limit: 10 } }],
    token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.equal(pack.sessions.length, 10);
  assert.equal(pack.blocks[0].sessions_count, 10);
  const manualPack = await server.buildCalendarSnapshotFromBlocks({
    blocks: [block], quoteLines: [{ ...fixture.line, quantity: "10.00", meta: {} }],
    token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.equal(manualPack.sessions.length, 10);
  assert.equal(manualPack.blocks[0].planning_session_limit, 10);
  const custom = await server.buildCalendarSnapshotFromBlocks({
    blocks: [{ ...block, custom_period: true, start_date: "2027-06-02", end_date: "2027-06-09" }],
    quoteLines: [fixture.line], token: "fixture-only", returnTo: "/fixture", schoolYearLabel: "2026-2027",
  });
  assert.equal(custom.sessions.length, 2);
  assert.equal(custom.blocks[0].end_date, "2027-06-09");
  assert.equal(custom.blocks[0].custom_period, true);
});
