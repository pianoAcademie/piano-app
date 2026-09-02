import assert from "node:assert/strict";
import { regularScheduleSummaries } from "../lib/client-schedule-summary.ts";

const row = (overrides = {}) => ({
  id: crypto.randomUUID(),
  session_id: crypto.randomUUID(),
  session_title: "Cours",
  session_status: "SCHEDULED",
  session_start_at_utc: "2026-09-09T12:00:00Z",
  session_end_at_utc: "2026-09-09T13:00:00Z",
  course_type_name: "Piano collectif",
  location_name: "Richelieu",
  recurrence_group_id: "series-piano",
  professor_name: "Mi-Young Lee",
  status: "BOOKED",
  ...overrides,
});

const rows = [
  row({ session_start_at_utc: "2026-09-16T12:00:00Z", session_end_at_utc: "2026-09-16T13:00:00Z" }),
  row(),
  row({
    recurrence_group_id: "series-solfege",
    course_type_name: "Solfège niveau 3",
    location_name: "En ligne",
    professor_name: null,
    session_start_at_utc: "2026-09-09T17:30:00Z",
    session_end_at_utc: "2026-09-09T18:15:00Z",
  }),
  row({ recurrence_group_id: "cancelled", status: "CANCELLED" }),
  row({
    recurrence_group_id: "past",
    session_start_at_utc: "2026-01-01T12:00:00Z",
    session_end_at_utc: "2026-01-01T13:00:00Z",
  }),
  row({
    recurrence_group_id: null,
    course_type_name: "Cours d’essai",
    session_start_at_utc: "2026-09-10T12:00:00Z",
    session_end_at_utc: "2026-09-10T13:00:00Z",
  }),
];

const result = regularScheduleSummaries(rows, Date.parse("2026-09-01T00:00:00Z"));
assert.equal(result.length, 2);
const piano = result.find((item) => item.key.startsWith("series-piano|"));
assert.equal(piano?.occurrenceCount, 2);
assert.equal(piano?.firstDate, "2026-09-09T12:00:00Z");
assert.equal(piano?.lastDate, "2026-09-16T12:00:00Z");
assert.equal(result.find((item) => item.key.startsWith("series-solfege|"))?.professorName, null);
assert.equal(result.some((item) => item.courseTypeName === "Cours d’essai"), false);
console.log("Client schedule summary: 6 assertions passed");
