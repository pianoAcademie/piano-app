"use client";

import { useEffect, useMemo, useState } from "react";

import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type ActivityOption = {
  id: string;
  name: string;
  code?: string;
  service_code?: string;
  mode?: string;
  duration_minutes: number;
  exclude_holidays_in_recurrence?: boolean;
  exclude_school_vacations_in_recurrence?: boolean;
};

type LocationOption = {
  id: string;
  name: string;
};

type PlanningBlock = {
  uid: string;
  activity_id: string;
  location_id: string;
  series_key: string;
  recommendation_key: string;
  source: string;
  duration_minutes: number | null;
  sessions_count: number | null;
  planning_session_limit: number | null;
  weekday: number;
  recurrence_frequency: "weekly" | "biweekly" | "monthly";
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality: string;
  calendar_name: string;
  holiday_dates: string[];
  closure_dates: string[];
  saved: boolean;
  dirty: boolean;
};

type SolfegeRule = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
};

type SolfegeSlotOption = {
  key: string;
  weekday: number;
  weekday_label: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  location_id: string | null;
  location_label: string | null;
  modality: string | null;
  label: string;
};

type PlanningCalendarPreset = {
  location_id: string;
  modality: string;
  calendar_name: string;
  holiday_dates: string[];
  closure_dates: string[];
};

type LivePlanningSeriesOption = {
  key: string;
  activity_id: string;
  activity_label: string | null;
  location_id: string;
  location_label: string | null;
  series_key: string;
  weekday: number;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  sessions_count: number;
  planning_session_limit: number | null;
  modality: string | null;
  label: string;
};

type QuotePlanningEditorProps = {
  quoteId: string;
  returnTo: string;
  editable: boolean;
  schoolYearLabel?: string | null;
  activities: ActivityOption[];
  locations: LocationOption[];
  calendarPresets?: PlanningCalendarPreset[];
  solfegeRules?: SolfegeRule[];
  livePlanningSeries?: LivePlanningSeriesOption[];
  initialSnapshot: Record<string, unknown>;
  initialMeta: Record<string, unknown>;
  language?: UiLanguage | string;
  saveAction: (formData: FormData) => Promise<void>;
};

type PlanningEditorState = {
  originalUid: string | null;
  block: PlanningBlock;
};

function PencilIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 16.25V20h3.75L18.8 8.94l-3.75-3.75L4 16.25Zm2.92 2.33H6v-.92l9.8-9.79.92.92-9.8 9.79ZM20.7 7.04a1 1 0 0 0 0-1.42l-2.32-2.33a1.03 1.03 0 0 0-1.42 0l-1.31 1.3 3.75 3.75 1.3-1.3Z"
        fill="currentColor"
      />
    </svg>
  );
}

function TrashIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v8h-2V9Zm4 0h2v8h-2V9ZM7 9h2v8H7V9Zm-1 11a2 2 0 0 1-2-2V8h16v10a2 2 0 0 1-2 2H6Z"
        fill="currentColor"
      />
    </svg>
  );
}

function PlusIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />
    </svg>
  );
}

function CalendarIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M7 2h2v2h6V2h2v2h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2V2Zm12 8H5v8h14v-8ZM5 8h14V6H5v2Zm2 3h3v3H7v-3Zm5 0h3v3h-3v-3Z"
        fill="currentColor"
      />
    </svg>
  );
}

const WEEKDAY_UNSET = -1;
const WEEKDAY_OPTIONS: Array<{ value: number; key: string }> = [
  { value: WEEKDAY_UNSET, key: "admin.quote_planning.weekday_unset" },
  { value: 0, key: "common.weekday_monday" },
  { value: 1, key: "common.weekday_tuesday" },
  { value: 2, key: "common.weekday_wednesday" },
  { value: 3, key: "common.weekday_thursday" },
  { value: 4, key: "common.weekday_friday" },
  { value: 5, key: "common.weekday_saturday" },
  { value: 6, key: "common.weekday_sunday" },
];
const RECURRENCE_OPTIONS: Array<{ value: PlanningBlock["recurrence_frequency"]; key: string }> = [
  { value: "weekly", key: "admin.quote_planning.recurrence_weekly" },
  { value: "biweekly", key: "admin.quote_planning.recurrence_biweekly" },
  { value: "monthly", key: "admin.quote_planning.recurrence_monthly" },
];

function normalizePlanningModality(value: string | null | undefined): string {
  const normalized = String(value ?? "").trim().toUpperCase();
  return normalized === "ONLINE" || normalized === "ONSITE" ? normalized : "";
}

function lockedPlanningModality(activity: ActivityOption | undefined): string {
  const normalized = String(activity?.mode ?? "").trim().toUpperCase();
  return normalized === "ONLINE" || normalized === "ONSITE" ? normalized : "";
}

function resolvePlanningModality(activity: ActivityOption | undefined, currentValue: string | null | undefined): string {
  return lockedPlanningModality(activity) || normalizePlanningModality(currentValue);
}

function monthLabel(month: number, language: UiLanguage): string {
  try {
    const label = new Intl.DateTimeFormat(localeForUiLanguage(language), { month: "long" }).format(new Date(2026, month - 1, 1));
    return label.charAt(0).toUpperCase() + label.slice(1);
  } catch {
    return String(month);
  }
}

function planningModalityLabel(value: string | null | undefined, language: UiLanguage): string {
  const normalized = String(value ?? "").trim().toUpperCase();
  if (normalized === "ONLINE") {
    return uiText(language, "admin.quote_planning.modality_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.quote_planning.modality_onsite");
  }
  if (!normalized || normalized === "AUTO") {
    return uiText(language, "admin.quote_planning.modality_auto");
  }
  return normalized;
}

function addMinutesToTime(startTime: string, deltaMinutes: number): string {
  const match = startTime.trim().match(/^(\d{2}):(\d{2})$/);
  if (!match) {
    return startTime;
  }
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return startTime;
  }
  const total = (hours * 60 + minutes + Math.max(0, deltaMinutes)) % (24 * 60);
  const outHours = Math.floor(total / 60).toString().padStart(2, "0");
  const outMinutes = (total % 60).toString().padStart(2, "0");
  return `${outHours}:${outMinutes}`;
}

function planningDurationMinutes(activity: ActivityOption | undefined | null): number {
  const duration = Number(activity?.duration_minutes ?? 0);
  return Number.isFinite(duration) && duration > 0 ? duration : 60;
}

function parseDateOnly(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed || !/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }
  const parsed = new Date(`${trimmed}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function uniqueSortedDateList(values: string[]): string[] {
  return Array.from(new Set(values.filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item)))).sort((a, b) =>
    a.localeCompare(b),
  );
}

function planningCalendarPresetKey(locationId: string, modality: string | null | undefined): string {
  return `${locationId}|${normalizePlanningModality(modality)}`;
}

function resolvePlanningCalendarPreset(
  locationId: string,
  activity: ActivityOption | undefined,
  modality: string | null | undefined,
  calendarPresetMap: Map<string, PlanningCalendarPreset>,
): PlanningCalendarPreset | null {
  if (!locationId) {
    return null;
  }
  const resolvedModality = resolvePlanningModality(activity, modality);
  const exact = calendarPresetMap.get(planningCalendarPresetKey(locationId, resolvedModality));
  if (exact) {
    return exact;
  }
  return calendarPresetMap.get(planningCalendarPresetKey(locationId, "")) ?? null;
}

function timeToMinutes(value: string): number | null {
  const match = value.trim().match(/^(\d{2}):(\d{2})$/);
  if (!match) {
    return null;
  }
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  return hours * 60 + minutes;
}

function schoolYearEndDateFromStart(start: Date): Date {
  const startYear = start.getUTCMonth() + 1 >= 9 ? start.getUTCFullYear() : start.getUTCFullYear() - 1;
  return new Date(Date.UTC(startYear + 1, 7, 31));
}

function planningSessionLimit(block: PlanningBlock): number {
  const parsed = Number.parseInt(String(block.planning_session_limit ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function estimateSessionDates(block: PlanningBlock): string[] {
  const start = parseDateOnly(block.start_date);
  const end = parseDateOnly(block.end_date);
  if (!start || !end || end < start) {
    return [];
  }
  const limit = planningSessionLimit(block);
  const effectiveEnd = limit > 0 && schoolYearEndDateFromStart(start) > end ? schoolYearEndDateFromStart(start) : end;
  const excluded = new Set(uniqueSortedDateList([...block.holiday_dates, ...block.closure_dates]));
  const matchedDates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= effectiveEnd) {
    const normalizedWeekday = (cursor.getUTCDay() + 6) % 7;
    const dayIso = cursor.toISOString().slice(0, 10);
    if (normalizedWeekday === block.weekday && !excluded.has(dayIso)) {
      matchedDates.push(dayIso);
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  if (block.recurrence_frequency === "weekly") {
    return limit > 0 ? matchedDates.slice(0, limit) : matchedDates;
  }
  if (block.recurrence_frequency === "biweekly") {
    if (matchedDates.length <= 1) {
      return matchedDates;
    }
    const firstDate = parseDateOnly(matchedDates[0]);
    if (!firstDate) {
      return matchedDates;
    }
    const biweekly = matchedDates.filter((item) => {
      const parsed = parseDateOnly(item);
      if (!parsed) {
        return false;
      }
      const deltaDays = Math.floor((parsed.getTime() - firstDate.getTime()) / 86_400_000);
      return deltaDays % 14 === 0;
    });
    return limit > 0 ? biweekly.slice(0, limit) : biweekly;
  }
  const monthSet = new Set<string>();
  const monthly: string[] = [];
  for (const row of matchedDates) {
    const parsed = parseDateOnly(row);
    if (!parsed) {
      continue;
    }
    const key = `${parsed.getUTCFullYear()}-${parsed.getUTCMonth() + 1}`;
    if (monthSet.has(key)) {
      continue;
    }
    monthSet.add(key);
    monthly.push(row);
  }
  return limit > 0 ? monthly.slice(0, limit) : monthly;
}

type SnapshotSession = {
  date: string;
  activity_id: string;
  location_id: string;
  series_key: string;
  start_time: string;
  end_time: string;
  weekday: number | null;
};

function parseSnapshotSessions(snapshot: Record<string, unknown>): SnapshotSession[] {
  if (!Array.isArray(snapshot.sessions)) {
    return [];
  }
  return snapshot.sessions
    .map((raw): SnapshotSession | null => {
      if (!raw || typeof raw !== "object") {
        return null;
      }
      const row = raw as Record<string, unknown>;
      const date = String(row.date ?? "").trim();
      const activityId = String(row.activity_id ?? "").trim();
      const locationId = String(row.location_id ?? "").trim();
      const seriesKey = String(row.series_key ?? "").trim();
      const startTime = String(row.start_time ?? "").trim();
      const endTime = String(row.end_time ?? "").trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !activityId || !startTime || !endTime) {
        return null;
      }
      const weekdayRaw = Number.parseInt(String(row.weekday ?? ""), 10);
      return {
        date,
        activity_id: activityId,
        location_id: locationId,
        series_key: seriesKey,
        start_time: startTime,
        end_time: endTime,
        weekday: Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6 ? weekdayRaw : null,
      };
    })
    .filter((item): item is SnapshotSession => item !== null);
}

function isLikelyDstShiftSeries(block: PlanningBlock, sessions: SnapshotSession[]): boolean {
  if (sessions.length <= 1 || !block.start_time || !block.end_time) {
    return false;
  }
  const exactRows = sessions.filter((row) => row.start_time === block.start_time && row.end_time === block.end_time);
  const shiftedRows = sessions.filter((row) => row.start_time !== block.start_time || row.end_time !== block.end_time);
  if (exactRows.length === 0 || shiftedRows.length === 0) {
    return false;
  }
  const shiftedPairs = Array.from(new Set(shiftedRows.map((row) => `${row.start_time}|${row.end_time}`)));
  if (shiftedPairs.length !== 1) {
    return false;
  }
  const [shiftedStart, shiftedEnd] = shiftedPairs[0].split("|");
  const blockStartMinutes = timeToMinutes(block.start_time);
  const blockEndMinutes = timeToMinutes(block.end_time);
  const shiftedStartMinutes = timeToMinutes(shiftedStart);
  const shiftedEndMinutes = timeToMinutes(shiftedEnd);
  if (
    blockStartMinutes === null ||
    blockEndMinutes === null ||
    shiftedStartMinutes === null ||
    shiftedEndMinutes === null
  ) {
    return false;
  }
  if (shiftedStartMinutes - blockStartMinutes !== 60 || shiftedEndMinutes - blockEndMinutes !== 60) {
    return false;
  }
  const sorted = [...sessions].sort((left, right) => {
    const byDate = left.date.localeCompare(right.date);
    if (byDate !== 0) {
      return byDate;
    }
    return left.start_time.localeCompare(right.start_time);
  });
  let sawShifted = false;
  for (const row of sorted) {
    const matchesBlockTime = row.start_time === block.start_time && row.end_time === block.end_time;
    if (matchesBlockTime && sawShifted) {
      return false;
    }
    if (!matchesBlockTime) {
      sawShifted = true;
    }
  }
  return true;
}

function datesFromSnapshotSessions(block: PlanningBlock, sessions: SnapshotSession[]): string[] {
  if (sessions.length === 0 || !block.activity_id || !block.start_time || !block.end_time) {
    return [];
  }
  const start = parseDateOnly(block.start_date);
  const end = parseDateOnly(block.end_date);
  if (!start || !end || end < start) {
    return [];
  }
  const startIso = start.toISOString().slice(0, 10);
  const endIso = end.toISOString().slice(0, 10);
  const isOnlineBlock = normalizePlanningModality(block.modality) === "ONLINE";
  const excludedDates = new Set(uniqueSortedDateList([...block.holiday_dates, ...block.closure_dates]));
  const relaxedMatches = sessions
    .filter((row) => {
      if (row.activity_id !== block.activity_id) {
        return false;
      }
      if (block.location_id && !isOnlineBlock && (row.location_id || "") !== block.location_id) {
        return false;
      }
      if (row.date < startIso || row.date > endIso) {
        return false;
      }
      if (excludedDates.has(row.date)) {
        return false;
      }
      if (row.weekday !== null && row.weekday !== block.weekday) {
        return false;
      }
      return true;
    })
  if (block.series_key) {
    const bySeries = relaxedMatches
      .filter((row) => row.series_key && row.series_key === block.series_key)
      .map((row) => row.date);
    if (bySeries.length > 0) {
      return uniqueSortedDateList(bySeries);
    }
  }
  const exactMatches = relaxedMatches
    .filter((row) => row.start_time === block.start_time && row.end_time === block.end_time)
    .map((row) => row.date);
  if (exactMatches.length > 0 && isLikelyDstShiftSeries(block, relaxedMatches)) {
    return uniqueSortedDateList(relaxedMatches.map((row) => row.date));
  }
  return uniqueSortedDateList(exactMatches);
}

function summarizeBySemester(dates: string[], semester: 1 | 2, language: UiLanguage): Array<{ monthLabel: string; days: string }> {
  const grouped = new Map<number, number[]>();
  for (const raw of dates) {
    const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) {
      continue;
    }
    const month = Number.parseInt(match[2], 10);
    const day = Number.parseInt(match[3], 10);
    if (!Number.isFinite(month) || !Number.isFinite(day)) {
      continue;
    }
    if (semester === 1 && !(month >= 9 || month <= 1)) {
      continue;
    }
    if (semester === 2 && !(month >= 2 && month <= 8)) {
      continue;
    }
    if (!grouped.has(month)) {
      grouped.set(month, []);
    }
    grouped.get(month)?.push(day);
  }

  const schoolYearMonthOrder = (month: number): number => (month >= 9 ? month : month + 12);

  return Array.from(grouped.entries())
    .sort((a, b) => schoolYearMonthOrder(a[0]) - schoolYearMonthOrder(b[0]))
    .map(([month, days]) => ({
      monthLabel: monthLabel(month, language),
      days: Array.from(new Set(days)).sort((a, b) => a - b).join(", "),
    }));
}

function weekdayLabel(weekday: number, language: UiLanguage): string {
  if (weekday === WEEKDAY_UNSET) {
    return uiText(language, "admin.quote_planning.weekday_unset");
  }
  const option = WEEKDAY_OPTIONS.find((entry) => entry.value === weekday);
  return option ? uiText(language, option.key) : String(weekday);
}

function timeSlotParts(slot: Record<string, unknown>): { start: string; end: string } | null {
  const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
  const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
  if (!start || !end) {
    return null;
  }
  return { start, end };
}

function normalizeModality(value: string | null | undefined): "ONLINE" | "ONSITE" | null {
  const normalized = String(value ?? "").trim().toUpperCase();
  if (normalized === "ONLINE" || normalized === "ONSITE") {
    return normalized;
  }
  return null;
}

function solfegeLevelFromActivity(activity: ActivityOption | undefined): string | null {
  if (!activity) {
    return null;
  }
  const candidates = [activity.name, activity.code, activity.service_code].filter(Boolean).map((value) => String(value));
  for (const candidate of candidates) {
    const match = candidate.match(/niveau\s*([1-5])/i) || candidate.match(/SOLFEGE[_\-\s]*NIVEAU[_\-\s]*([1-5])/i);
    if (match?.[1]) {
      return match[1];
    }
  }
  return null;
}

function isSolfegeActivity(activity: ActivityOption | undefined): boolean {
  if (!activity) {
    return false;
  }
  const haystack = [activity.name, activity.code, activity.service_code].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes("solfege");
}

function slotOptionsFromRule(rule: SolfegeRule | null | undefined, locationLabel: string | null, language: UiLanguage): SolfegeSlotOption[] {
  if (!rule) {
    return [];
  }
  const options: SolfegeSlotOption[] = [];
  const hasStructuredWeekdays = rule.allowed_time_slots.some((slot) => {
    const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
    return Number.isFinite(weekday) && weekday >= 0 && weekday <= 6;
  });

  const pushOption = (weekday: number, start: string, end: string): void => {
    const weekdayText = weekdayLabel(weekday, language);
    const locationSuffix = locationLabel ? ` · ${locationLabel}` : "";
    const modalitySuffix = rule.modality && rule.modality.toUpperCase() !== "ANY" ? ` · ${planningModalityLabel(rule.modality, language)}` : "";
    options.push({
      key: `${weekday}|${start}|${end}|${rule.id}|${locationLabel || "-"}`,
      weekday,
      weekday_label: weekdayText,
      start_time: start,
      end_time: end,
      duration_minutes: rule.duration_minutes,
      location_id: rule.location_id,
      location_label: locationLabel,
      modality: rule.modality,
      label: `${weekdayText} ${start}-${end}${modalitySuffix}${locationSuffix}`,
    });
  };

  if (hasStructuredWeekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = timeSlotParts(slot);
      if (!parts) {
        continue;
      }
      const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
      if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) {
        continue;
      }
      pushOption(weekday, parts.start, parts.end);
    }
    return options;
  }

  const weekdays = rule.allowed_weekdays.length > 0
    ? rule.allowed_weekdays.filter((day) => Number.isFinite(day) && day >= 0 && day <= 6)
    : [0, 1, 2, 3, 4, 5, 6];
  for (const weekday of weekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = timeSlotParts(slot);
      if (!parts) {
        continue;
      }
      pushOption(weekday, parts.start, parts.end);
    }
  }
  return options;
}

function parseInitialBlocks(snapshot: Record<string, unknown>): PlanningBlock[] {
  const fromBlocks = snapshot.blocks;
  if (Array.isArray(fromBlocks)) {
    const parsed = fromBlocks
      .map((raw, index): PlanningBlock | null => {
        if (!raw || typeof raw !== "object") {
          return null;
        }
        const row = raw as Record<string, unknown>;
        const weekday = Number.parseInt(String(row.weekday ?? "0"), 10);
        const selectionPending = Boolean(row.selection_pending);
        const activityId = typeof row.activity_id === "string" ? row.activity_id : "";
        const recurrenceRaw = String(row.recurrence_frequency ?? "").trim().toLowerCase();
        const recurrenceFrequency: PlanningBlock["recurrence_frequency"] =
          recurrenceRaw === "biweekly" || recurrenceRaw === "monthly" ? recurrenceRaw : "weekly";
        const startDate = typeof row.start_date === "string" ? row.start_date : "";
        const endDate = typeof row.end_date === "string" ? row.end_date : "";
        const startTime = typeof row.start_time === "string" ? row.start_time : "";
        const endTime = typeof row.end_time === "string" ? row.end_time : "";
        const locationId = typeof row.location_id === "string" ? row.location_id : "";
        const seriesKey = typeof row.series_key === "string" ? row.series_key : "";
        const recommendationKey = typeof row.recommendation_key === "string" ? row.recommendation_key : "";
        const source = typeof row.source === "string" ? row.source : "";
        const durationMinutesRaw = Number.parseInt(String(row.duration_minutes ?? ""), 10);
        const sessionsCountRaw = Number.parseInt(String(row.sessions_count ?? ""), 10);
        const planningSessionLimitRaw = Number.parseInt(String(row.planning_session_limit ?? ""), 10);
        const modality = typeof row.modality === "string" ? row.modality : "";
        const holidayDates = Array.isArray(row.holiday_dates)
          ? row.holiday_dates.map((item) => String(item)).filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item))
          : [];
        const closureDates = Array.isArray(row.closure_dates)
          ? row.closure_dates.map((item) => String(item)).filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item))
          : [];
        const calendarName = typeof row.calendar_name === "string" ? row.calendar_name : "";

        return {
          uid: `block-${index + 1}`,
          activity_id: activityId,
          location_id: locationId,
          series_key: seriesKey,
          recommendation_key: recommendationKey,
          source,
          duration_minutes: Number.isFinite(durationMinutesRaw) && durationMinutesRaw > 0 ? durationMinutesRaw : null,
          sessions_count: Number.isFinite(sessionsCountRaw) && sessionsCountRaw >= 0 ? sessionsCountRaw : null,
          planning_session_limit:
            Number.isFinite(planningSessionLimitRaw) && planningSessionLimitRaw > 0 ? planningSessionLimitRaw : null,
          weekday: selectionPending
            ? WEEKDAY_UNSET
            : Number.isFinite(weekday) && weekday >= 0 && weekday <= 6
            ? weekday
            : WEEKDAY_UNSET,
          recurrence_frequency: recurrenceFrequency,
          start_date: startDate,
          end_date: endDate,
          start_time: selectionPending ? "" : startTime,
          end_time: selectionPending ? "" : endTime,
          modality,
          calendar_name: calendarName,
          holiday_dates: holidayDates,
          closure_dates: closureDates,
          saved: true,
          dirty: false,
        };
      })
      .filter((item): item is PlanningBlock => item !== null);
    if (parsed.length > 0) {
      return parsed;
    }
  }

  const startDate = typeof snapshot.start_date === "string" ? snapshot.start_date : "";
  const endDate = typeof snapshot.end_date === "string" ? snapshot.end_date : "";
  const startTime = typeof snapshot.start_time === "string" ? snapshot.start_time : "";
  const endTime = typeof snapshot.end_time === "string" ? snapshot.end_time : "";
  const weekdays = Array.isArray(snapshot.weekdays) ? snapshot.weekdays : [];
  const weekdayRaw = weekdays[0];
  const weekday = Number.isFinite(Number(weekdayRaw)) ? Number(weekdayRaw) : 0;
  const activityId = typeof snapshot.activity_id === "string" ? snapshot.activity_id : "";
  const locationId = typeof snapshot.location_id === "string" ? snapshot.location_id : "";
  const modality = typeof snapshot.modality === "string" ? snapshot.modality : "";
  if (startDate || endDate || activityId) {
    return [
      {
        uid: "block-1",
        activity_id: activityId,
        location_id: locationId,
        series_key: "",
        recommendation_key: "",
        source: "",
        duration_minutes: null,
        sessions_count: null,
        planning_session_limit: null,
        weekday: weekday >= 0 && weekday <= 6 ? weekday : WEEKDAY_UNSET,
        recurrence_frequency: "weekly",
        start_date: startDate,
        end_date: endDate,
        start_time: startTime,
        end_time: endTime,
        modality,
        calendar_name: "",
        holiday_dates: [],
        closure_dates: [],
        saved: true,
        dirty: false,
      },
    ];
  }
  return [];
}

function newPlanningBlock(activities: ActivityOption[], locations: LocationOption[]): PlanningBlock {
  const defaultActivity = activities[0];
  const defaultActivityId = activities[0]?.id ?? "";
  const defaultDuration = planningDurationMinutes(defaultActivity);
  const startTime = "17:00";
  return {
    uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    activity_id: defaultActivityId,
    location_id: locations[0]?.id ?? "",
    series_key: "",
    recommendation_key: "",
    source: "",
    duration_minutes: null,
    sessions_count: null,
    planning_session_limit: null,
    weekday: 0,
    recurrence_frequency: "weekly",
    start_date: "",
    end_date: "",
    start_time: startTime,
    end_time: addMinutesToTime(startTime, defaultDuration),
    modality: resolvePlanningModality(defaultActivity, defaultActivity?.mode),
    calendar_name: "",
    holiday_dates: [],
    closure_dates: [],
    saved: false,
    dirty: true,
  };
}

function normalizePlanningBlockWithActivity(
  block: PlanningBlock,
  activities: ActivityOption[],
  calendarPresetMap: Map<string, PlanningCalendarPreset>,
): PlanningBlock {
  const activity = activities.find((item) => item.id === block.activity_id);
  const resolvedModality = resolvePlanningModality(activity, block.modality);
  const preset = resolvePlanningCalendarPreset(block.location_id, activity, resolvedModality, calendarPresetMap);
  const hasLocation = String(block.location_id || "").trim().length > 0;
  const shouldExcludeHolidays = activity?.exclude_holidays_in_recurrence !== false;
  const shouldExcludeVacations = activity?.exclude_school_vacations_in_recurrence !== false;
  const nextHolidayDates = shouldExcludeHolidays
    ? uniqueSortedDateList(hasLocation ? (preset?.holiday_dates ?? block.holiday_dates) : [])
    : [];
  const nextClosureDates = shouldExcludeVacations
    ? uniqueSortedDateList(hasLocation ? (preset?.closure_dates ?? block.closure_dates) : [])
    : [];
  return {
    ...block,
    end_time: block.start_time ? addMinutesToTime(block.start_time, planningDurationMinutes(activity)) : block.end_time,
    modality: resolvedModality,
    calendar_name: hasLocation ? (preset?.calendar_name || block.calendar_name) : "",
    holiday_dates: nextHolidayDates,
    closure_dates: nextClosureDates,
  };
}

function editablePlanningBlockChanged(current: PlanningBlock, next: PlanningBlock): boolean {
  return current.activity_id !== next.activity_id
    || current.location_id !== next.location_id
    || current.weekday !== next.weekday
    || current.recurrence_frequency !== next.recurrence_frequency
    || current.start_date !== next.start_date
    || current.end_date !== next.end_date
    || current.start_time !== next.start_time
    || current.end_time !== next.end_time
    || current.modality !== next.modality;
}

export default function QuotePlanningEditor({
  quoteId,
  returnTo,
  editable,
  schoolYearLabel,
  activities,
  locations,
  calendarPresets = [],
  solfegeRules = [],
  livePlanningSeries = [],
  initialSnapshot,
  initialMeta,
  language: languageProp = "fr",
  saveAction,
}: QuotePlanningEditorProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const calendarPresetMap = useMemo(() => {
    const map = new Map<string, PlanningCalendarPreset>();
    for (const preset of calendarPresets) {
      const locationId = String(preset.location_id || "").trim();
      if (!locationId) {
        continue;
      }
      map.set(planningCalendarPresetKey(locationId, preset.modality), {
        ...preset,
        location_id: locationId,
        modality: normalizePlanningModality(preset.modality),
        holiday_dates: uniqueSortedDateList(preset.holiday_dates),
        closure_dates: uniqueSortedDateList(preset.closure_dates),
      });
    }
    return map;
  }, [calendarPresets]);

  const initialBlocks = useMemo(
    () =>
      parseInitialBlocks(initialSnapshot).map((block) =>
        normalizePlanningBlockWithActivity(block, activities, calendarPresetMap),
      ),
    [initialSnapshot, activities, calendarPresetMap],
  );
  const snapshotSyncKey = useMemo(() => {
    const blocksRaw = Array.isArray(initialSnapshot.blocks) ? initialSnapshot.blocks : [];
    const sessionsRaw = Array.isArray(initialSnapshot.sessions) ? initialSnapshot.sessions : [];
    const generatedAt = typeof initialSnapshot.generated_at === "string" ? initialSnapshot.generated_at : "";
    return JSON.stringify({
      blocks: blocksRaw,
      sessions_count: sessionsRaw.length,
      generated_at: generatedAt,
    });
  }, [initialSnapshot]);

  const [blocks, setBlocks] = useState<PlanningBlock[]>(initialBlocks);
  const [editorState, setEditorState] = useState<PlanningEditorState | null>(null);
  const [expandedUid, setExpandedUid] = useState<string | null>(null);
  const snapshotSessions = useMemo(() => parseSnapshotSessions(initialSnapshot), [initialSnapshot]);
  const liveSeriesBySelector = useMemo(() => {
    const map = new Map<string, LivePlanningSeriesOption[]>();
    for (const option of livePlanningSeries) {
      const key = `${option.activity_id}|${option.location_id}|${option.weekday}`;
      const list = map.get(key) ?? [];
      list.push(option);
      map.set(key, list);
    }
    for (const list of map.values()) {
      list.sort((left, right) => {
        const byTime = left.start_time.localeCompare(right.start_time);
        if (byTime !== 0) {
          return byTime;
        }
        return left.start_date.localeCompare(right.start_date);
      });
    }
    return map;
  }, [livePlanningSeries]);

  // Keep client-side editor state aligned with server snapshot after save/redirect.
  useEffect(() => {
    setBlocks(initialBlocks);
    setEditorState(null);
    setExpandedUid(null);
  }, [snapshotSyncKey, initialBlocks]);

  const blocksJson = useMemo(
    () =>
      JSON.stringify(
        blocks.map((row) => {
          const activity = activities.find((item) => item.id === row.activity_id);
          const locationLabel = locations.find((item) => item.id === row.location_id)?.name || null;
          const selectionPending = row.weekday === WEEKDAY_UNSET;
          const pendingLevel =
            selectionPending && isSolfegeActivity(activity) ? solfegeLevelFromActivity(activity) : null;
          const pendingRule = pendingLevel
            ? solfegeRules.find((rule) => String(rule.level_code) === String(pendingLevel)) || null
            : null;
          const pendingSlotOptions =
            selectionPending && pendingLevel
              ? slotOptionsFromRule(pendingRule, locationLabel, language).map((slot) => ({
                  weekday: slot.weekday,
                  weekday_label: slot.weekday_label,
                  start_time: slot.start_time,
                  end_time: slot.end_time,
                  duration_minutes: slot.duration_minutes,
                  location_id: slot.location_id,
                  location_label: slot.location_label,
                  modality: slot.modality,
                  label: slot.label,
                }))
              : [];
          return {
            activity_id: row.activity_id || null,
            activity_label: activity?.name || null,
            location_id: row.location_id || null,
            location_label: locationLabel,
            series_key: row.series_key || null,
            recommendation_key: row.recommendation_key || null,
            source: row.source || null,
            duration_minutes: row.duration_minutes,
            sessions_count: row.sessions_count,
            planning_session_limit: row.planning_session_limit,
            calendar_name: row.calendar_name || null,
            weekday: row.weekday,
            weekday_label: row.weekday === WEEKDAY_UNSET ? null : weekdayLabel(row.weekday, language),
            recurrence_frequency: row.recurrence_frequency,
            start_date: selectionPending ? "" : row.start_date,
            end_date: selectionPending ? "" : row.end_date,
            start_time: selectionPending ? "" : row.start_time,
            end_time: selectionPending ? "" : row.end_time,
            modality: row.modality || null,
            selection_pending: selectionPending,
            pending_solfege_level: pendingLevel,
            pending_slot_options: pendingSlotOptions,
            exclude_holidays_in_recurrence:
              activity?.exclude_holidays_in_recurrence !== false,
            exclude_school_vacations_in_recurrence:
              activity?.exclude_school_vacations_in_recurrence !== false,
          };
        }),
      ),
    [blocks, activities, locations, solfegeRules, language],
  );
  const removedActivityIdsJson = useMemo(() => {
    const remainingActivityIds = new Set(
      blocks
        .map((row) => String(row.activity_id || "").trim())
        .filter((value) => value.length > 0),
    );
    const removedActivityIds = Array.from(
      new Set(
        initialBlocks
          .filter((row) => row.saved)
          .map((row) => String(row.activity_id || "").trim())
          .filter((activityId) => activityId.length > 0 && !remainingActivityIds.has(activityId)),
      ),
    );
    return JSON.stringify(removedActivityIds);
  }, [blocks, initialBlocks]);

  function openCreateModal(): void {
    setEditorState({
      originalUid: null,
      block: normalizePlanningBlockWithActivity(newPlanningBlock(activities, locations), activities, calendarPresetMap),
    });
  }

  function removeBlock(uid: string): void {
    setBlocks((prev) => prev.filter((row) => row.uid !== uid));
    setEditorState((prev) => (prev?.originalUid === uid ? null : prev));
    setExpandedUid((prev) => (prev === uid ? null : prev));
  }

  function openEditModal(uid: string): void {
    const current = blocks.find((row) => row.uid === uid);
    if (!current) {
      return;
    }
    setEditorState({
      originalUid: uid,
      block: normalizePlanningBlockWithActivity(current, activities, calendarPresetMap),
    });
  }

  function closeEditor(): void {
    setEditorState(null);
  }

  function matchingLiveSeriesOptions(block: PlanningBlock): LivePlanningSeriesOption[] {
    if (!block.activity_id || !block.location_id || block.weekday === WEEKDAY_UNSET) {
      return [];
    }
    return liveSeriesBySelector.get(`${block.activity_id}|${block.location_id}|${block.weekday}`) ?? [];
  }

  function applyLiveSeriesToBlock(block: PlanningBlock, option: LivePlanningSeriesOption): PlanningBlock {
    return {
      ...block,
      activity_id: option.activity_id,
      location_id: option.location_id,
      series_key: option.series_key,
      source: "live_planning",
      sessions_count: option.sessions_count,
      planning_session_limit: option.planning_session_limit ?? block.planning_session_limit,
      weekday: option.weekday,
      recurrence_frequency: "weekly",
      start_date: option.start_date,
      end_date: option.end_date,
      start_time: option.start_time,
      end_time: option.end_time,
      modality: option.modality || block.modality,
    };
  }

  function updateEditor(
    patch: Partial<PlanningBlock>,
    options: { autoApplyLiveSeries?: boolean; preserveLiveIdentity?: boolean } = {},
  ): void {
    setEditorState((prev) => {
      if (!prev) {
        return prev;
      }
      const liveIdentityKeys: Array<keyof PlanningBlock> = [
        "activity_id",
        "location_id",
        "weekday",
        "recurrence_frequency",
        "start_date",
        "end_date",
        "start_time",
        "end_time",
        "modality",
      ];
      const resetLiveIdentity = !options.preserveLiveIdentity && liveIdentityKeys.some((key) =>
        Object.prototype.hasOwnProperty.call(patch, key) && patch[key] !== prev.block[key],
      );
      const nextInput = {
        ...prev.block,
        ...patch,
        ...(resetLiveIdentity
          ? {
              series_key: "",
              recommendation_key: "",
              source: "",
              sessions_count: null,
              planning_session_limit: null,
            }
          : {}),
      };
      let nextBlock = normalizePlanningBlockWithActivity(
        nextInput,
        activities,
        calendarPresetMap,
      );
      if (options.autoApplyLiveSeries) {
        const matches = matchingLiveSeriesOptions(nextBlock);
        if (matches.length > 0) {
          const preferred = matches.find((option) => option.start_time === nextBlock.start_time) ?? matches[0];
          nextBlock = normalizePlanningBlockWithActivity(
            applyLiveSeriesToBlock(nextBlock, preferred),
            activities,
            calendarPresetMap,
          );
        }
      }
      return {
        ...prev,
        block: nextBlock,
      };
    });
  }

  function syncEndTimeWithActivity(activityId: string): void {
    const activity = activities.find((item) => item.id === activityId);
    updateEditor({
      activity_id: activityId,
      modality: resolvePlanningModality(activity, activity?.mode),
    }, { autoApplyLiveSeries: true });
  }

  function commitEditor(): void {
    if (!editorState) {
      return;
    }
    const draft = editorState.block;
    if (editorState.originalUid === null) {
      setBlocks((prev) => [...prev, draft]);
      setEditorState(null);
      return;
    }
    setBlocks((prev) =>
      prev.map((row) => {
        if (row.uid !== editorState.originalUid) {
          return row;
        }
        if (!editablePlanningBlockChanged(row, draft)) {
          return row;
        }
        return {
          ...draft,
          uid: row.uid,
          saved: row.saved,
          dirty: row.saved ? true : draft.dirty,
        };
      }),
    );
    setEditorState(null);
  }

  const editorBlock = editorState?.block ?? null;
  const savedCount = blocks.filter((row) => row.saved && !row.dirty).length;
  const modifiedCount = blocks.filter((row) => row.saved && row.dirty).length;
  const newCount = blocks.filter((row) => !row.saved).length;
  const currentSavedUids = new Set(blocks.filter((row) => row.saved).map((row) => row.uid));
  const removedSavedCount = initialBlocks.filter((row) => row.saved && !currentSavedUids.has(row.uid)).length;
  const draftCount = modifiedCount + newCount + removedSavedCount;
  const pendingSaveCount = draftCount;

  function blockStatusLabel(block: PlanningBlock): string {
    if (!block.saved) {
      return t("admin.quote_lines.status_new");
    }
    if (block.dirty) {
      return t("admin.quote_lines.status_dirty");
    }
    return t("admin.quote_lines.status_saved");
  }

  function blockStatusClass(block: PlanningBlock): string {
    if (!block.saved) return "quote-status-chip-new";
    if (block.dirty) return "quote-status-chip-editing";
    return "quote-status-chip-saved";
  }

  return (
    <form action={saveAction}>
      <input type="hidden" name="quote_id" value={quoteId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="school_year_label" value={schoolYearLabel || ""} />
      <input type="hidden" name="planning_blocks_json" value={blocksJson} />
      <input type="hidden" name="removed_activity_ids_json" value={removedActivityIdsJson} />
      <input type="hidden" name="current_meta_json" value={JSON.stringify(initialMeta || {})} />

      <div className="quote-editor-toolbar row spread wrap gap-sm">
        <div className="quote-editor-toolbar-main">
          <strong>{t("admin.quote_planning.title_main")}</strong>
          <span className="quote-editor-count">
            {t("admin.quote_lines.counts", { saved: savedCount, draft: draftCount })}
          </span>
        </div>
        <div className="row wrap gap-sm">
          <button type="button" className="ghost quote-add-button" onClick={openCreateModal} disabled={!editable}>
            <PlusIcon />
            <span>{t("admin.quote_planning.add_activity")}</span>
          </button>
          <span className={`quote-status-chip ${pendingSaveCount > 0 ? "quote-status-chip-pending" : "quote-status-chip-saved"}`}>
            {pendingSaveCount > 0 ? t("admin.quote_lines.pending_save") : t("admin.quote_lines.status_saved")}
          </span>
        </div>
      </div>
      {removedSavedCount > 0 ? (
        <p className="quote-editor-empty quote-editor-warning">
          {t("admin.quote_planning.removed_notice", { count: removedSavedCount })}
        </p>
      ) : null}

      <section className="quote-editor-pane quote-editor-pane-saved top-gap-sm">
        {blocks.length === 0 ? (
          <p className="quote-editor-empty">{t("admin.quote_planning.empty")}</p>
        ) : (
          <div className="quote-saved-list">
            {blocks.map((block, index) => {
              const activity = activities.find((item) => item.id === block.activity_id);
              const locationLabel = locations.find((item) => item.id === block.location_id)?.name || t("admin.quote_detail.location_not_defined");
              const selectionPending = block.weekday === WEEKDAY_UNSET;
              const calculatedDates = datesFromSnapshotSessions(block, snapshotSessions);
              const targetSessionLimit = planningSessionLimit(block);
              const theoreticalDates = estimateSessionDates(block);
              const estimatedDates =
                calculatedDates.length > 0 && (targetSessionLimit <= 0 || calculatedDates.length >= targetSessionLimit)
                  ? calculatedDates
                  : theoreticalDates;
              const displayStartDate = estimatedDates[0] || block.start_date || "-";
              const displayEndDate = estimatedDates[estimatedDates.length - 1] || block.end_date || "-";
              const semester1 = summarizeBySemester(estimatedDates, 1, language);
              const semester2 = summarizeBySemester(estimatedDates, 2, language);
              const isExpanded = expandedUid === block.uid;
              return (
                <article key={block.uid} className="quote-saved-card">
                  <div className="quote-saved-card-top">
                    <div className="quote-saved-card-head">
                      <div className="quote-saved-card-badges">
                        <span className="quote-line-kind-pill">{t("admin.quote_planning.kind_planning")}</span>
                        <span className={`quote-status-chip ${blockStatusClass(block)}`}>{blockStatusLabel(block)}</span>
                      </div>
                      <button
                        type="button"
                        className="quote-saved-card-title-button"
                        onClick={() => openEditModal(block.uid)}
                      >
                        <span className="quote-line-title-text" title={activity?.name || t("admin.quote_planning.activity_fallback", { index: index + 1 })}>
                          {activity?.name || t("admin.quote_planning.activity_fallback", { index: index + 1 })}
                        </span>
                      </button>
                    </div>
                    <div className="quote-saved-card-actions">
                      <button
                        type="button"
                        className="quote-icon-button"
                        onClick={() => openEditModal(block.uid)}
                        disabled={!editable}
                        aria-label={t("admin.quote_planning.edit_aria", { title: activity?.name || t("admin.quote_planning.activity_fallback_short") })}
                        title={t("common.edit")}
                      >
                        <PencilIcon />
                      </button>
                      <button
                        type="button"
                        className="quote-icon-button"
                        onClick={() => setExpandedUid((prev) => (prev === block.uid ? null : block.uid))}
                        aria-label={isExpanded ? t("admin.quote_planning.hide_sessions") : t("admin.quote_planning.show_sessions")}
                        aria-pressed={isExpanded}
                        title={isExpanded ? t("admin.quote_planning.hide_sessions") : t("admin.quote_planning.show_sessions")}
                      >
                        <CalendarIcon />
                      </button>
                      <button
                        type="button"
                        className="quote-icon-button quote-icon-button-danger"
                        onClick={() => removeBlock(block.uid)}
                        disabled={!editable}
                        aria-label={t("admin.quote_planning.delete_aria", { title: activity?.name || t("admin.quote_planning.activity_fallback_short") })}
                        title={t("common.delete")}
                      >
                        <TrashIcon />
                      </button>
                    </div>
                  </div>
                  <div className="quote-saved-card-metrics">
                    <div>
                      <span>{t("admin.quote_planning.schedule")}</span>
                      <strong>
                        {selectionPending
                          ? t("admin.quote_planning.weekday_unset")
                          : `${weekdayLabel(block.weekday, language)} · ${block.start_time || "--:--"} - ${block.end_time || "--:--"}`}
                      </strong>
                    </div>
                    <div>
                      <span>{t("common.period")}</span>
                      <strong>{displayStartDate} → {displayEndDate}</strong>
                    </div>
                    <div>
                      <span>{t("admin.quote_planning.frequency")}</span>
                      <strong>{t(RECURRENCE_OPTIONS.find((item) => item.value === block.recurrence_frequency)?.key || "admin.quote_planning.recurrence_weekly")}</strong>
                    </div>
                    <div>
                      <span>{t("admin.quote_planning.sessions")}</span>
                      <strong>{estimatedDates.length}</strong>
                    </div>
                  </div>
                  <div className="quote-saved-card-footer">
                    <span>{t("admin.quote_planning.location_value", { location: locationLabel })}</span>
                    {selectionPending ? <span>{t("admin.quote_planning.slot_to_confirm")}</span> : null}
                  </div>
                  {isExpanded ? (
                    <div className="quote-saved-card-detail top-gap-sm">
                      <div className="grid cols-2">
                        <div>
                          <strong>{t("admin.quote_planning.semester_1")}</strong>
                          {semester1.length === 0 ? <p className="muted">{t("admin.quote_planning.no_session")}</p> : null}
                          {semester1.map((item) => (
                            <p key={`${block.uid}-left-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                          ))}
                        </div>
                        <div>
                          <strong>{t("admin.quote_planning.semester_2")}</strong>
                          {semester2.length === 0 ? <p className="muted">{t("admin.quote_planning.no_session")}</p> : null}
                          {semester2.map((item) => (
                            <p key={`${block.uid}-right-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editorBlock ? (
        <section
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t("admin.quote_planning.modal_aria")}
          onClick={closeEditor}
        >
          <article className="modal-panel quote-planning-editor-modal" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close-x" onClick={closeEditor} aria-label={t("common.close")}>
              ×
            </button>
            <div className="quote-line-editor-modal-head">
              <div>
                <p className="quote-line-editor-kicker">
                  {editorState?.originalUid ? t("admin.quote_planning.editing_kicker") : t("admin.quote_planning.new_kicker")}
                </p>
                <h3 className="modal-title">
                  {editorState?.originalUid ? t("admin.quote_planning.edit_activity") : t("admin.quote_planning.add_planned_activity")}
                </h3>
              </div>
              <span className={`quote-status-chip ${editorBlock.saved ? "quote-status-chip-editing" : "quote-status-chip-new"}`}>
                {editorBlock.saved ? t("admin.quote_lines.draft_modified") : t("admin.quote_lines.draft_added")}
              </span>
            </div>

            {(() => {
              const activity = activities.find((item) => item.id === editorBlock.activity_id);
              const lockedModality = lockedPlanningModality(activity);
              const selectionPending = editorBlock.weekday === WEEKDAY_UNSET;
              const blockSolfegeLevel = isSolfegeActivity(activity) ? solfegeLevelFromActivity(activity) : null;
              const locationLabel = locations.find((item) => item.id === editorBlock.location_id)?.name || null;
              const blockSolfegeRule = blockSolfegeLevel
                ? solfegeRules.find((rule) => String(rule.level_code) === String(blockSolfegeLevel)) || null
                : null;
              const pendingSlotOptions =
                selectionPending && blockSolfegeLevel ? slotOptionsFromRule(blockSolfegeRule, locationLabel, language) : [];
              const liveOptions = matchingLiveSeriesOptions(editorBlock);
              const selectedLiveOptionKey =
                liveOptions.find((option) => option.series_key === editorBlock.series_key)?.key
                ?? liveOptions.find((option) => option.start_time === editorBlock.start_time && option.end_time === editorBlock.end_time)?.key
                ?? "";
              return (
                <article className="quote-line-card quote-line-card-modal">
                  <div className="row spread wrap gap-sm">
                    <strong>{t("admin.quote_planning.kind_planning")}</strong>
                    {editorState?.originalUid ? (
                      <button
                        type="button"
                        className="ghost small-btn"
                        onClick={() => {
                          removeBlock(editorState.originalUid as string);
                          closeEditor();
                        }}
                        disabled={!editable}
                      >
                        {t("common.delete")}
                      </button>
                    ) : null}
                  </div>
                  <div className="grid cols-2 quote-planning-draft-grid top-gap-sm">
                    <label>
                      {t("admin.quote_lines.kind_activity")}
                      <select
                        value={editorBlock.activity_id}
                        onChange={(event) => syncEndTimeWithActivity(event.target.value)}
                        disabled={!editable}
                      >
                        <option value="">{t("common.select")}</option>
                        {activities.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name} ({row.duration_minutes} min)
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("common.location")}
                      <select
                        value={editorBlock.location_id}
                        onChange={(event) => updateEditor({ location_id: event.target.value }, { autoApplyLiveSeries: true })}
                        disabled={!editable}
                      >
                        <option value="">{t("admin.quote_detail.none")}</option>
                        {locations.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.quote_planning.day")}
                      <select
                        value={String(editorBlock.weekday)}
                        onChange={(event) => {
                          const parsed = Number.parseInt(event.target.value, 10);
                          if (!Number.isFinite(parsed)) {
                            return;
                          }
                          if (parsed === WEEKDAY_UNSET) {
                            updateEditor({
                              weekday: WEEKDAY_UNSET,
                              start_date: "",
                              end_date: "",
                              start_time: "",
                              end_time: "",
                            });
                            return;
                          }
                          const duration = planningDurationMinutes(activity);
                          const nextStart = editorBlock.start_time || "17:00";
                          updateEditor({
                            weekday: parsed,
                            start_time: nextStart,
                            end_time: addMinutesToTime(nextStart, duration),
                          }, { autoApplyLiveSeries: true });
                        }}
                        disabled={!editable}
                      >
                        {WEEKDAY_OPTIONS.map((row) => (
                          <option key={row.value} value={row.value}>
                            {t(row.key)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.quote_planning.modality")}
                      <select
                        value={resolvePlanningModality(activity, editorBlock.modality)}
                        onChange={(event) => updateEditor({ modality: resolvePlanningModality(activity, event.target.value) })}
                        disabled={!editable || Boolean(lockedModality)}
                      >
                        <option value="">{t("admin.quote_planning.modality_auto")}</option>
                        <option value="ONLINE">{t("admin.quote_planning.modality_online")}</option>
                        <option value="ONSITE">{t("admin.quote_planning.modality_onsite")}</option>
                      </select>
                    </label>
                    {liveOptions.length > 0 ? (
                      <label className="span-2">
                        {t("admin.quote_planning.live_slot")}
                        <select
                          value={selectedLiveOptionKey}
                          onChange={(event) => {
                            const selected = liveOptions.find((option) => option.key === event.target.value);
                            if (!selected) {
                              return;
                            }
                            updateEditor(applyLiveSeriesToBlock(editorBlock, selected), { preserveLiveIdentity: true });
                          }}
                          disabled={!editable || selectionPending}
                        >
                          {liveOptions.map((option) => (
                            <option key={option.key} value={option.key}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <label>
                      {t("admin.quote_planning.frequency")}
                      <select
                        value={editorBlock.recurrence_frequency}
                        onChange={(event) => {
                          const next = event.target.value === "biweekly" || event.target.value === "monthly"
                            ? event.target.value
                            : "weekly";
                          updateEditor({ recurrence_frequency: next });
                        }}
                        disabled={!editable}
                      >
                        {RECURRENCE_OPTIONS.map((entry) => (
                          <option key={`${editorBlock.uid}-freq-${entry.value}`} value={entry.value}>
                            {t(entry.key)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      {t("admin.quote_planning.start_date")}
                      <input
                        type="date"
                        value={editorBlock.start_date}
                        onChange={(event) => updateEditor({ start_date: event.target.value })}
                        disabled={!editable || selectionPending}
                      />
                    </label>
                    <label>
                      {t("admin.quote_planning.end_date")}
                      <input
                        type="date"
                        value={editorBlock.end_date}
                        onChange={(event) => updateEditor({ end_date: event.target.value })}
                        disabled={!editable || selectionPending}
                      />
                    </label>
                    <label>
                      {t("admin.quote_planning.start_time")}
                      <input
                        type="time"
                        value={editorBlock.start_time}
                        onChange={(event) => {
                          const nextStart = event.target.value;
                          const currentActivity = activities.find((item) => item.id === editorBlock.activity_id);
                          const duration = planningDurationMinutes(currentActivity);
                          updateEditor({
                            start_time: nextStart,
                            end_time: addMinutesToTime(nextStart, duration),
                          });
                        }}
                        disabled={!editable || selectionPending}
                      />
                    </label>
                    <label>
                      {t("admin.quote_planning.end_time_auto")}
                      <input type="time" value={editorBlock.end_time} readOnly />
                    </label>

                    <p className="muted span-2">
                      {t("admin.quote_planning.distinct_activities_hint")}
                    </p>
                    {selectionPending && blockSolfegeLevel ? (
                      <div className="span-2">
                        <p className="muted">{t("admin.quote_planning.solfege_level_pending", { level: blockSolfegeLevel })}</p>
                        {pendingSlotOptions.length > 0 ? (
                          <ul className="muted top-gap-sm">
                            {pendingSlotOptions.map((slot) => (
                              <li key={`${editorBlock.uid}-${slot.key}`}>{slot.label}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="muted top-gap-sm">{t("admin.quote_planning.no_slot_for_level")}</p>
                        )}
                      </div>
                    ) : null}
                  </div>
                  <div className="row end gap-sm top-gap-sm">
                    <button type="button" className="ghost" onClick={closeEditor}>
                      {t("common.cancel")}
                    </button>
                    <button type="button" onClick={commitEditor} disabled={!editable}>
                      {t("admin.quote_lines.apply_draft")}
                    </button>
                  </div>
                </article>
              );
            })()}
          </article>
        </section>
      ) : null}

      <div className="row end top-gap-sm">
        <button type="submit" disabled={!editable}>{t("admin.quote_planning.save_planning")}</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">{t("admin.quote_lines.immutable_after_send")}</p> : null}
    </form>
  );
}
