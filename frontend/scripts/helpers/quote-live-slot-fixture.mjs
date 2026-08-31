import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { sourceFunctions } from "./source-functions.mjs";
import { uiText } from "../../lib/ui-i18n.ts";

const fixture = JSON.parse(readFileSync(new URL("../fixtures/quote-wednesday-series.json", import.meta.url)));
const pageUrl = new URL("../../app/admin/quotes/[quoteId]/page.tsx", import.meta.url);
const editorUrl = new URL("../../components/quote-planning-editor.tsx", import.meta.url);
const actionsUrl = new URL("../../lib/actions.ts", import.meta.url);
const liveUrl = new URL("../../lib/quote-planning-live.ts", import.meta.url);
const weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map(x => "common.weekday_" + x);
const editor = sourceFunctions(editorUrl, ["applyLiveSeriesToBlock", "parseInitialBlocks", "parseSnapshotSessions", "estimateSessionDates", "selectedLivePlanningOptionKey", "editablePlanningBlockChanged", "displayedPlanningSessionDates"], { WEEKDAY_UNSET: -1 });

function pageFor(sessions = fixture.sessions) {
  return sourceFunctions(pageUrl, ["loadLivePlanningSeriesOptions", "quoteLinePlanningLimit"], {
    uiText, QUOTE_PLANNING_WEEKDAY_KEYS: weekdays,
    backendRequest: async (url) => {
      const query = new URL(url, "http://fixture.local").searchParams;
      assert.equal(query.get("status"), "SCHEDULED");
      return { ok: true, data: sessions.filter(s => s.status === "SCHEDULED") };
    },
  });
}

async function slots(overrides = {}, sessions = fixture.sessions) {
  return pageFor(sessions).loadLivePlanningSeriesOptions({
    token: "fixture-only", schoolYearLabel: "2026-2027",
    activities: [fixture.activity], calendarPresets: [fixture.calendar], language: "fr",
    // Intentional adversarial extra arguments: no quote context may limit the catalogue.
    lines: [fixture.line], planningSnapshot: { blocks: [] }, ...overrides,
  });
}

function saveHarness(sessions = fixture.sessions) {
  let actions;
  const backendRequest = async (url, init = {}) => {
    if (url.startsWith("/api/v1/admin/sessions?")) return { ok: true, data: sessions.filter(s => s.status === "SCHEDULED") };
    if (url.startsWith("/api/v1/quote-school-calendars/active/by-location/")) return {
      ok: true, data: { calendar: { id: "calendar", name: "2026-2027", school_year_label: "2026-2027" }, ...fixture.calendar },
    };
    if (url === "/api/v1/quotes/calendar/preview") {
      const input = JSON.parse(init.body);
      return { ok: true, data: { sessions: actions.buildLocalPlanningRowsForBlock({
        block: { ...input, weekday: input.weekdays[0] }, endDate: input.end_date,
        holidayDates: input.holiday_dates, closureDates: input.closure_dates, sessionLimit: input.session_limit || 0,
      }) } };
    }
    throw new Error("Unexpected IO: " + url);
  };
  const live = sourceFunctions(liveUrl, ["loadLivePlanningMatchForBlock"], { backendRequest });
  actions = sourceFunctions(actionsUrl, ["parsePlanningBlocksJson", "buildCalendarSnapshotFromBlocks", "buildLocalPlanningRowsForBlock"], {
    backendRequest, ...live,
    redirect: (url) => { throw new Error("Unexpected redirect: " + url); },
  });
  return { ...actions, ...live };
}


export { fixture, pageFor, slots, saveHarness, editor };
