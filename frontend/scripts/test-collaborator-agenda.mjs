import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  buildAgendaRange, formatAgendaDayLabel, formatAgendaTime, isAgendaDateKey, parisDateKey,
} from "../lib/collaborator-agenda.ts";

test("Rosana's 31 August class is 19:00–20:00 in Paris, regardless of host TZ", () => {
  assert.equal(formatAgendaTime("2026-08-31T17:00:00Z", "fr-FR"), "19:00");
  assert.equal(formatAgendaTime("2026-08-31T18:00:00Z", "fr-FR"), "20:00");
  assert.equal(formatAgendaTime("2026-08-31T17:00:00Z", "en-GB"), "19:00");
  assert.equal(formatAgendaTime("2026-12-07T17:00:00Z", "fr-FR"), "18:00");
  assert.equal(formatAgendaTime("invalid", "fr-FR"), "-");
});

test("today and session grouping use the Paris calendar date, including midnight", () => {
  assert.equal(parisDateKey("2026-08-30T22:30:00Z"), "2026-08-31");
  assert.equal(parisDateKey("2026-08-31T22:30:00Z"), "2026-09-01");
  assert.equal(parisDateKey(new Date("2026-12-31T23:00:00Z")), "2027-01-01");
  assert.equal(formatAgendaTime("2026-08-30T22:00:00Z", "fr-FR"), "00:00");
});

test("day queries include exactly a local day, not a UTC day", () => {
  const range = buildAgendaRange("day", "2026-08-31", "fr-FR");
  assert.equal(range.from.toISOString(), "2026-08-30T22:00:00.000Z");
  assert.equal(range.to.toISOString(), "2026-08-31T21:59:59.999Z");
  assert.deepEqual(range.dayKeys, ["2026-08-31"]);
  assert.match(range.title, /lundi 31 août 2026/);
  assert.match(formatAgendaDayLabel("2026-08-31", "month", "fr-FR"), /lun\. 31 août/);
  const rows = ["2026-08-30T21:59:59.999Z", "2026-08-30T22:00:00Z", "2026-08-31T17:00:00Z", "2026-08-31T22:00:00Z"];
  assert.deepEqual(rows.filter((x) => new Date(x) >= range.from && new Date(x) <= range.to),
    ["2026-08-30T22:00:00Z", "2026-08-31T17:00:00Z"]);
});

test("week queries span Monday–Sunday in local time across month/year boundaries", () => {
  const week = buildAgendaRange("week", "2026-09-06", "fr-FR");
  assert.equal(week.from.toISOString(), "2026-08-30T22:00:00.000Z");
  assert.equal(week.to.toISOString(), "2026-09-06T21:59:59.999Z");
  assert.equal(week.dayKeys.length, 7);
  assert.equal(week.dayKeys[0], "2026-08-31");
  assert.equal(week.dayKeys[6], "2026-09-06");
  const winter = buildAgendaRange("week", "2027-01-01", "en-GB");
  assert.equal(winter.dayKeys[0], "2026-12-28");
  assert.equal(winter.dayKeys[6], "2027-01-03");
  assert.equal(winter.from.toISOString(), "2026-12-27T23:00:00.000Z");
});

test("month queries use Paris midnights and handle leap years", () => {
  const month = buildAgendaRange("month", "2026-08-31", "fr-FR");
  assert.equal(month.from.toISOString(), "2026-07-31T22:00:00.000Z");
  assert.equal(month.to.toISOString(), "2026-08-31T21:59:59.999Z");
  assert.equal(month.dayKeys.length, 31);
  assert.equal(month.title, "août 2026");
  assert.equal(buildAgendaRange("month", "2028-02-29", "fr-FR").dayKeys.length, 29);
});

test("spring and autumn DST boundaries create 23h/25h local days", () => {
  const spring = buildAgendaRange("day", "2026-03-29", "fr-FR");
  const autumn = buildAgendaRange("day", "2026-10-25", "fr-FR");
  assert.equal(spring.from.toISOString(), "2026-03-28T23:00:00.000Z");
  assert.equal(spring.to.toISOString(), "2026-03-29T21:59:59.999Z");
  assert.equal(autumn.from.toISOString(), "2026-10-24T22:00:00.000Z");
  assert.equal(autumn.to.toISOString(), "2026-10-25T22:59:59.999Z");
  assert.equal((spring.to - spring.from + 1) / 3600000, 23);
  assert.equal((autumn.to - autumn.from + 1) / 3600000, 25);
  assert.equal(formatAgendaTime("2026-03-29T00:30:00Z", "fr-FR"), "01:30");
  assert.equal(formatAgendaTime("2026-03-29T01:30:00Z", "fr-FR"), "03:30");
  assert.equal(formatAgendaTime("2026-10-25T00:30:00Z", "fr-FR"), "02:30");
  assert.equal(formatAgendaTime("2026-10-25T01:30:00Z", "fr-FR"), "02:30");
  for (const [date, hours] of [["2026-03-29", 167], ["2026-10-25", 169]]) {
    const week = buildAgendaRange("week", date, "fr-FR");
    assert.equal((week.to - week.from + 1) / 3600000, hours);
    assert.equal(week.dayKeys.length, 7);
  }
  for (const [date, hours] of [["2026-03-29", 743], ["2026-10-25", 745]]) {
    const month = buildAgendaRange("month", date, "fr-FR");
    assert.equal((month.to - month.from + 1) / 3600000, hours);
    assert.equal(month.dayKeys.length, 31);
  }
});

test("invalid date parameters are rejected before building a range", () => {
  for (const key of ["", "2026-02-29", "2026-08-32", "2026-13-01", "2026-8-31", "garbage"]) {
    assert.equal(isAgendaDateKey(key), false);
    assert.throws(() => buildAgendaRange("day", key, "fr-FR"), RangeError);
  }
  assert.equal(isAgendaDateKey("2028-02-29"), true);
});

test("collaborator page uses the local helpers for range, grouping and time", () => {
  const page = readFileSync(new URL("../app/admin/professors/[id]/page.tsx", import.meta.url), "utf8");
  assert.match(page, /isAgendaDateKey\(agendaDateInput\).*parisDateKey\(new Date\(\)\)/);
  assert.match(page, /buildAgendaRange\(agendaView, agendaDate, sortLocale\)/);
  assert.match(page, /parisDateKey\(session.start_at_utc\)/);
  assert.match(page, /formatAgendaTime\(session.start_at_utc, sortLocale\)/);
  assert.match(page, /formatAgendaTime\(session.end_at_utc, sortLocale\)/);
  assert.doesNotMatch(page, /session.start_at_utc.slice\(0, 10\)/);
  const translations = readFileSync(new URL("../lib/ui-i18n.ts", import.meta.url), "utf8");
  assert.match(translations, /schedule_reference_date": "Date de référence \(heure de Paris\)"/);
  assert.match(translations, /schedule_reference_date": "Reference date \(Paris time\)"/);
});
