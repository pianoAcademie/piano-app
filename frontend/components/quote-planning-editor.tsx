"use client";

import { useMemo, useState } from "react";

type ActivityOption = {
  id: string;
  name: string;
  duration_minutes: number;
};

type LocationOption = {
  id: string;
  name: string;
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
  start_time: string;
  end_time: string;
  duration_minutes: number;
  location_id: string | null;
  modality: string | null;
  label: string;
};

type PlanningBlock = {
  uid: string;
  activity_id: string;
  location_id: string;
  weekday: number;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality: string;
  solfege_enabled: boolean;
  solfege_level: string;
  solfege_start_date: string;
  solfege_slot_key: string;
  solfege_slot_raw: Record<string, unknown> | null;
  masterclass_enabled: boolean;
  masterclass_session: string;
  masterclass_location_id: string;
};

type QuotePlanningEditorProps = {
  quoteId: string;
  returnTo: string;
  editable: boolean;
  schoolYearLabel?: string | null;
  activities: ActivityOption[];
  locations: LocationOption[];
  solfegeRules: SolfegeRule[];
  initialSnapshot: Record<string, unknown>;
  initialMeta: Record<string, unknown>;
  saveAction: (formData: FormData) => Promise<void>;
};

const WEEKDAY_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: "Lundi" },
  { value: 1, label: "Mardi" },
  { value: 2, label: "Mercredi" },
  { value: 3, label: "Jeudi" },
  { value: 4, label: "Vendredi" },
  { value: 5, label: "Samedi" },
  { value: 6, label: "Dimanche" },
];

const MONTH_LABELS = [
  "Janvier",
  "Fevrier",
  "Mars",
  "Avril",
  "Mai",
  "Juin",
  "Juillet",
  "Aout",
  "Septembre",
  "Octobre",
  "Novembre",
  "Decembre",
];

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

function parseDateOnly(value: string): Date | null {
  const trimmed = value.trim();
  if (!trimmed || !/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }
  const parsed = new Date(`${trimmed}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function estimateSessionDates(block: PlanningBlock): string[] {
  const start = parseDateOnly(block.start_date);
  const end = parseDateOnly(block.end_date);
  if (!start || !end || end < start) {
    return [];
  }
  const out: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    const normalizedWeekday = (cursor.getUTCDay() + 6) % 7;
    if (normalizedWeekday === block.weekday) {
      out.push(cursor.toISOString().slice(0, 10));
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

function summarizeBySemester(dates: string[], semester: 1 | 2): Array<{ monthLabel: string; days: string }> {
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
  return Array.from(grouped.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([month, days]) => ({
      monthLabel: MONTH_LABELS[month - 1] || String(month),
      days: Array.from(new Set(days)).sort((a, b) => a - b).join(", "),
    }));
}

function weekdayLabel(weekday: number): string {
  return WEEKDAY_OPTIONS.find((entry) => entry.value === weekday)?.label ?? String(weekday);
}

function timeSlotParts(slot: Record<string, unknown>): { start: string; end: string } | null {
  const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
  const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
  if (!start || !end) {
    return null;
  }
  return { start, end };
}

function slotKey(weekday: number, start: string, end: string): string {
  return `${weekday}|${start}|${end}`;
}

function slotOptionsFromRule(rule: SolfegeRule | null | undefined): SolfegeSlotOption[] {
  if (!rule) {
    return [];
  }
  const options: SolfegeSlotOption[] = [];
  const hasStructuredWeekdays = rule.allowed_time_slots.some((slot) => {
    const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
    return Number.isFinite(weekday) && weekday >= 0 && weekday <= 6;
  });

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
      options.push({
        key: slotKey(weekday, parts.start, parts.end),
        weekday,
        start_time: parts.start,
        end_time: parts.end,
        duration_minutes: rule.duration_minutes,
        location_id: rule.location_id,
        modality: rule.modality,
        label: `${weekdayLabel(weekday)} ${parts.start}-${parts.end}`,
      });
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
      options.push({
        key: slotKey(weekday, parts.start, parts.end),
        weekday,
        start_time: parts.start,
        end_time: parts.end,
        duration_minutes: rule.duration_minutes,
        location_id: rule.location_id,
        modality: rule.modality,
        label: `${weekdayLabel(weekday)} ${parts.start}-${parts.end}`,
      });
    }
  }

  return options;
}

function slotOptionFromRaw(raw: Record<string, unknown> | null): SolfegeSlotOption | null {
  if (!raw) {
    return null;
  }
  const weekday = Number.parseInt(String(raw.weekday ?? ""), 10);
  const startTime = String(raw.start_time ?? "").trim();
  const endTime = String(raw.end_time ?? "").trim();
  const duration = Number.parseInt(String(raw.duration_minutes ?? ""), 10);
  if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6 || !startTime || !endTime) {
    return null;
  }
  return {
    key: slotKey(weekday, startTime, endTime),
    weekday,
    start_time: startTime,
    end_time: endTime,
    duration_minutes: Number.isFinite(duration) && duration > 0 ? duration : 30,
    location_id: typeof raw.location_id === "string" ? raw.location_id : null,
    modality: typeof raw.modality === "string" ? raw.modality : null,
    label: `${weekdayLabel(weekday)} ${startTime}-${endTime}`,
  };
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
        const activityId = typeof row.activity_id === "string" ? row.activity_id : "";
        const startDate = typeof row.start_date === "string" ? row.start_date : "";
        const endDate = typeof row.end_date === "string" ? row.end_date : "";
        const startTime = typeof row.start_time === "string" ? row.start_time : "17:00";
        const endTime = typeof row.end_time === "string" ? row.end_time : "18:00";
        const locationId = typeof row.location_id === "string" ? row.location_id : "";
        const modality = typeof row.modality === "string" ? row.modality : "";

        const solfegeLevel = String(row.solfege_level ?? "").trim();
        const solfegeStartDate = String(row.solfege_start_date ?? "").trim();
        const rawSlot = row.solfege_slot && typeof row.solfege_slot === "object" && !Array.isArray(row.solfege_slot)
          ? (row.solfege_slot as Record<string, unknown>)
          : null;
        const rawSlotOption = slotOptionFromRaw(rawSlot);
        const solfegeEnabled = Boolean(row.solfege_enabled) || !!solfegeLevel || !!solfegeStartDate || !!rawSlotOption;

        const masterclassSession = String(row.masterclass_session ?? "").trim();
        const masterclassLocationId = typeof row.masterclass_location_id === "string" ? row.masterclass_location_id : "";
        const masterclassEnabled = Boolean(row.masterclass_enabled) || !!masterclassSession || !!masterclassLocationId;

        return {
          uid: `block-${index + 1}`,
          activity_id: activityId,
          location_id: locationId,
          weekday: Number.isFinite(weekday) && weekday >= 0 && weekday <= 6 ? weekday : 0,
          start_date: startDate,
          end_date: endDate,
          start_time: startTime,
          end_time: endTime,
          modality,
          solfege_enabled: solfegeEnabled,
          solfege_level: solfegeLevel,
          solfege_start_date: solfegeStartDate,
          solfege_slot_key: rawSlotOption?.key || "",
          solfege_slot_raw: rawSlot,
          masterclass_enabled: masterclassEnabled,
          masterclass_session: masterclassSession,
          masterclass_location_id: masterclassLocationId,
        };
      })
      .filter((item): item is PlanningBlock => item !== null);
    if (parsed.length > 0) {
      return parsed;
    }
  }

  const startDate = typeof snapshot.start_date === "string" ? snapshot.start_date : "";
  const endDate = typeof snapshot.end_date === "string" ? snapshot.end_date : "";
  const startTime = typeof snapshot.start_time === "string" ? snapshot.start_time : "17:00";
  const endTime = typeof snapshot.end_time === "string" ? snapshot.end_time : "18:00";
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
        weekday: weekday >= 0 && weekday <= 6 ? weekday : 0,
        start_date: startDate,
        end_date: endDate,
        start_time: startTime,
        end_time: endTime,
        modality,
        solfege_enabled: false,
        solfege_level: "",
        solfege_start_date: "",
        solfege_slot_key: "",
        solfege_slot_raw: null,
        masterclass_enabled: false,
        masterclass_session: "",
        masterclass_location_id: "",
      },
    ];
  }
  return [];
}

export default function QuotePlanningEditor({
  quoteId,
  returnTo,
  editable,
  schoolYearLabel,
  activities,
  locations,
  solfegeRules,
  initialSnapshot,
  initialMeta,
  saveAction,
}: QuotePlanningEditorProps): JSX.Element {
  const [blocks, setBlocks] = useState<PlanningBlock[]>(parseInitialBlocks(initialSnapshot));

  const levelOptions = useMemo(() => {
    const levels = new Set<string>(["1", "2", "3", "4", "5"]);
    for (const row of solfegeRules) {
      const level = String(row.level_code ?? "").trim();
      if (level) {
        levels.add(level);
      }
    }
    return Array.from(levels).sort((a, b) => {
      const ai = Number.parseInt(a, 10);
      const bi = Number.parseInt(b, 10);
      if (Number.isFinite(ai) && Number.isFinite(bi)) {
        return ai - bi;
      }
      return a.localeCompare(b);
    });
  }, [solfegeRules]);

  function slotOptionsForBlock(block: PlanningBlock): SolfegeSlotOption[] {
    const byLevel = slotOptionsFromRule(solfegeRules.find((rule) => String(rule.level_code) === String(block.solfege_level)));
    const fallback = slotOptionFromRaw(block.solfege_slot_raw);
    if (fallback && !byLevel.some((entry) => entry.key === fallback.key)) {
      return [...byLevel, { ...fallback, label: `${fallback.label} (actuel)` }];
    }
    return byLevel;
  }

  const blocksJson = useMemo(
    () =>
      JSON.stringify(
        blocks.map((row) => {
          const slotOptions = slotOptionsForBlock(row);
          const selectedSlot = row.solfege_enabled
            ? (slotOptions.find((slot) => slot.key === row.solfege_slot_key) ?? slotOptionFromRaw(row.solfege_slot_raw))
            : null;
          return {
            activity_id: row.activity_id || null,
            activity_label: activities.find((item) => item.id === row.activity_id)?.name || null,
            location_id: row.location_id || null,
            location_label: locations.find((item) => item.id === row.location_id)?.name || null,
            weekday: row.weekday,
            weekday_label: WEEKDAY_OPTIONS.find((item) => item.value === row.weekday)?.label || null,
            start_date: row.start_date,
            end_date: row.end_date,
            start_time: row.start_time,
            end_time: row.end_time,
            modality: row.modality || null,
            solfege_enabled: row.solfege_enabled,
            solfege_level: row.solfege_enabled ? (row.solfege_level || null) : null,
            solfege_start_date: row.solfege_enabled ? (row.solfege_start_date || null) : null,
            solfege_slot: selectedSlot
              ? {
                weekday: selectedSlot.weekday,
                weekday_label: weekdayLabel(selectedSlot.weekday),
                start_time: selectedSlot.start_time,
                end_time: selectedSlot.end_time,
                label: selectedSlot.label,
                duration_minutes: selectedSlot.duration_minutes,
                location_id: selectedSlot.location_id,
                location_label: selectedSlot.location_id ? (locations.find((item) => item.id === selectedSlot.location_id)?.name || null) : null,
                modality: selectedSlot.modality || null,
              }
              : null,
            masterclass_enabled: row.masterclass_enabled,
            masterclass_session: row.masterclass_enabled ? (row.masterclass_session || null) : null,
            masterclass_location_id: row.masterclass_enabled ? (row.masterclass_location_id || null) : null,
            masterclass_location_label: row.masterclass_enabled
              ? (locations.find((item) => item.id === row.masterclass_location_id)?.name || null)
              : null,
          };
        }),
      ),
    [blocks, activities, locations, solfegeRules],
  );

  function addBlock(): void {
    const defaultActivityId = activities[0]?.id ?? "";
    const defaultDuration = activities[0]?.duration_minutes ?? 60;
    const startTime = "17:00";
    const endTime = addMinutesToTime(startTime, defaultDuration);
    setBlocks((prev) => [
      ...prev,
      {
        uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        activity_id: defaultActivityId,
        location_id: locations[0]?.id ?? "",
        weekday: 0,
        start_date: "",
        end_date: "",
        start_time: startTime,
        end_time: endTime,
        modality: "",
        solfege_enabled: false,
        solfege_level: "",
        solfege_start_date: "",
        solfege_slot_key: "",
        solfege_slot_raw: null,
        masterclass_enabled: false,
        masterclass_session: "",
        masterclass_location_id: "",
      },
    ]);
  }

  function removeBlock(uid: string): void {
    setBlocks((prev) => prev.filter((row) => row.uid !== uid));
  }

  function updateBlock(uid: string, patch: Partial<PlanningBlock>): void {
    setBlocks((prev) => prev.map((row) => (row.uid === uid ? { ...row, ...patch } : row)));
  }

  function syncEndTimeWithActivity(uid: string, activityId: string, startTime: string): void {
    const activity = activities.find((item) => item.id === activityId);
    const duration = activity?.duration_minutes ?? 60;
    const endTime = addMinutesToTime(startTime, duration);
    updateBlock(uid, {
      activity_id: activityId,
      end_time: endTime,
    });
  }

  return (
    <form action={saveAction}>
      <input type="hidden" name="quote_id" value={quoteId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="school_year_label" value={schoolYearLabel || ""} />
      <input type="hidden" name="planning_blocks_json" value={blocksJson} />
      <input type="hidden" name="current_meta_json" value={JSON.stringify(initialMeta || {})} />

      <div className="row wrap gap-sm">
        <button type="button" className="ghost" onClick={addBlock} disabled={!editable}>
          + Ajouter une activite planning
        </button>
      </div>

      {blocks.length === 0 ? <p className="muted top-gap-sm">Aucun bloc planning configure.</p> : null}
      <div className="list top-gap-sm">
        {blocks.map((block, index) => {
          const activity = activities.find((item) => item.id === block.activity_id);
          const estimatedDates = estimateSessionDates(block);
          const semester1 = summarizeBySemester(estimatedDates, 1);
          const semester2 = summarizeBySemester(estimatedDates, 2);
          const blockSlotOptions = slotOptionsForBlock(block);
          return (
            <article key={block.uid} className="item">
              <div className="row spread wrap gap-sm">
                <strong>{activity?.name || `Activite #${index + 1}`}</strong>
                <span className="badge">{estimatedDates.length} cours</span>
              </div>
              {estimatedDates.length > 0 ? (
                <div className="grid cols-2 top-gap-sm">
                  <div>
                    <p><strong>1er semestre</strong></p>
                    {semester1.length === 0 ? <p className="muted">Aucune seance</p> : null}
                    {semester1.map((item) => (
                      <p key={`${block.uid}-s1-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                    ))}
                  </div>
                  <div>
                    <p><strong>2e semestre</strong></p>
                    {semester2.length === 0 ? <p className="muted">Aucune seance</p> : null}
                    {semester2.map((item) => (
                      <p key={`${block.uid}-s2-${item.monthLabel}`} className="muted">{item.monthLabel}: {item.days}</p>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="muted top-gap-sm">Dates manquantes pour calculer la synthese.</p>
              )}

              <div className="row spread wrap gap-sm">
                <button type="button" className="ghost small-btn" onClick={() => removeBlock(block.uid)} disabled={!editable}>
                  Supprimer
                </button>
              </div>

              <div className="grid cols-4 top-gap-sm">
                <label>
                  Activite
                  <select
                    value={block.activity_id}
                    onChange={(event) => syncEndTimeWithActivity(block.uid, event.target.value, block.start_time)}
                    disabled={!editable}
                  >
                    <option value="">Selectionner</option>
                    {activities.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.name} ({row.duration_minutes} min)
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lieu
                  <select
                    value={block.location_id}
                    onChange={(event) => updateBlock(block.uid, { location_id: event.target.value })}
                    disabled={!editable}
                  >
                    <option value="">Aucun</option>
                    {locations.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Jour
                  <select
                    value={String(block.weekday)}
                    onChange={(event) => updateBlock(block.uid, { weekday: Number.parseInt(event.target.value, 10) || 0 })}
                    disabled={!editable}
                  >
                    {WEEKDAY_OPTIONS.map((row) => (
                      <option key={row.value} value={row.value}>
                        {row.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Modalite
                  <select
                    value={block.modality}
                    onChange={(event) => updateBlock(block.uid, { modality: event.target.value })}
                    disabled={!editable}
                  >
                    <option value="">Auto</option>
                    <option value="ONLINE">En ligne</option>
                    <option value="ONSITE">Presentiel</option>
                  </select>
                </label>
                <label>
                  Date debut
                  <input type="date" value={block.start_date} onChange={(event) => updateBlock(block.uid, { start_date: event.target.value })} disabled={!editable} />
                </label>
                <label>
                  Date fin
                  <input type="date" value={block.end_date} onChange={(event) => updateBlock(block.uid, { end_date: event.target.value })} disabled={!editable} />
                </label>
                <label>
                  Heure debut
                  <input
                    type="time"
                    value={block.start_time}
                    onChange={(event) => {
                      const nextStart = event.target.value;
                      const currentActivity = activities.find((item) => item.id === block.activity_id);
                      const duration = currentActivity?.duration_minutes ?? 60;
                      updateBlock(block.uid, {
                        start_time: nextStart,
                        end_time: addMinutesToTime(nextStart, duration),
                      });
                    }}
                    disabled={!editable}
                  />
                </label>
                <label>
                  Heure fin (auto)
                  <input type="time" value={block.end_time} readOnly />
                </label>

                <label className="checkline span-2">
                  <input
                    type="checkbox"
                    checked={block.solfege_enabled}
                    onChange={(event) => updateBlock(block.uid, {
                      solfege_enabled: event.target.checked,
                      solfege_level: event.target.checked ? block.solfege_level : "",
                      solfege_start_date: event.target.checked ? block.solfege_start_date : "",
                      solfege_slot_key: event.target.checked ? block.solfege_slot_key : "",
                      solfege_slot_raw: event.target.checked ? block.solfege_slot_raw : null,
                    })}
                    disabled={!editable}
                  />
                  Cette activite inclut le solfege
                </label>

                {block.solfege_enabled ? (
                  <>
                    <label>
                      Niveau solfege
                      <select
                        value={block.solfege_level}
                        onChange={(event) => updateBlock(block.uid, {
                          solfege_level: event.target.value,
                          solfege_slot_key: "",
                          solfege_slot_raw: null,
                        })}
                        disabled={!editable}
                      >
                        <option value="">Selectionner</option>
                        {levelOptions.map((level) => (
                          <option key={`${block.uid}-solfege-level-${level}`} value={level}>Niveau {level}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Date demarrage solfege
                      <input
                        type="date"
                        value={block.solfege_start_date}
                        onChange={(event) => updateBlock(block.uid, { solfege_start_date: event.target.value })}
                        disabled={!editable}
                      />
                    </label>
                    <label className="span-2">
                      Creneau solfege
                      <select
                        value={block.solfege_slot_key}
                        onChange={(event) => {
                          const nextKey = event.target.value;
                          const nextRaw = blockSlotOptions.find((slot) => slot.key === nextKey);
                          updateBlock(block.uid, {
                            solfege_slot_key: nextKey,
                            solfege_slot_raw: nextRaw
                              ? {
                                weekday: nextRaw.weekday,
                                weekday_label: weekdayLabel(nextRaw.weekday),
                                start_time: nextRaw.start_time,
                                end_time: nextRaw.end_time,
                                label: nextRaw.label,
                                duration_minutes: nextRaw.duration_minutes,
                                location_id: nextRaw.location_id,
                                modality: nextRaw.modality,
                              }
                              : null,
                          });
                        }}
                        disabled={!editable}
                      >
                        <option value="">Selectionner</option>
                        {blockSlotOptions.map((slot) => (
                          <option key={`${block.uid}-solfege-slot-${slot.key}`} value={slot.key}>{slot.label}</option>
                        ))}
                      </select>
                    </label>
                  </>
                ) : (
                  <p className="muted span-2">Sans solfege pour cette activite.</p>
                )}

                <label className="checkline span-2">
                  <input
                    type="checkbox"
                    checked={block.masterclass_enabled}
                    onChange={(event) => updateBlock(block.uid, {
                      masterclass_enabled: event.target.checked,
                      masterclass_session: event.target.checked ? block.masterclass_session : "",
                      masterclass_location_id: event.target.checked ? block.masterclass_location_id : "",
                    })}
                    disabled={!editable}
                  />
                  Participation Masterclass du samedi
                </label>

                {block.masterclass_enabled ? (
                  <>
                    <label>
                      Session masterclass
                      <select
                        value={block.masterclass_session}
                        onChange={(event) => updateBlock(block.uid, { masterclass_session: event.target.value })}
                        disabled={!editable}
                      >
                        <option value="">Selectionner</option>
                        <option value="morning">Matin 09:00-12:00</option>
                        <option value="afternoon_1330">Apres-midi 13:30-16:30</option>
                        <option value="afternoon_1400">Apres-midi 14:00-17:00</option>
                      </select>
                    </label>
                    <label>
                      Local masterclass
                      <select
                        value={block.masterclass_location_id}
                        onChange={(event) => updateBlock(block.uid, { masterclass_location_id: event.target.value })}
                        disabled={!editable}
                      >
                        <option value="">Selectionner</option>
                        {locations.map((item) => (
                          <option key={`${block.uid}-masterclass-location-${item.id}`} value={item.id}>{item.name}</option>
                        ))}
                      </select>
                    </label>
                  </>
                ) : (
                  <p className="muted span-2">Sans masterclass pour cette activite.</p>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <div className="row top-gap-sm">
        <button type="submit" disabled={!editable}>Enregistrer le planning</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">Le devis est immuable apres envoi.</p> : null}
    </form>
  );
}
