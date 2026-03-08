"use client";

import { useMemo, useState } from "react";

type ActivityOption = {
  id: string;
  name: string;
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
  weekday: number;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality: string;
  calendar_name: string;
  holiday_dates: string[];
  closure_dates: string[];
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

function uniqueSortedDateList(values: string[]): string[] {
  return Array.from(new Set(values.filter((item) => /^\d{4}-\d{2}-\d{2}$/.test(item)))).sort((a, b) =>
    a.localeCompare(b),
  );
}

function estimateSessionDates(block: PlanningBlock): string[] {
  const start = parseDateOnly(block.start_date);
  const end = parseDateOnly(block.end_date);
  if (!start || !end || end < start) {
    return [];
  }
  const excluded = new Set(uniqueSortedDateList([...block.holiday_dates, ...block.closure_dates]));
  const out: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    const normalizedWeekday = (cursor.getUTCDay() + 6) % 7;
    const dayIso = cursor.toISOString().slice(0, 10);
    if (normalizedWeekday === block.weekday && !excluded.has(dayIso)) {
      out.push(dayIso);
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

type SnapshotSession = {
  date: string;
  activity_id: string;
  location_id: string;
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
        start_time: startTime,
        end_time: endTime,
        weekday: Number.isFinite(weekdayRaw) && weekdayRaw >= 0 && weekdayRaw <= 6 ? weekdayRaw : null,
      };
    })
    .filter((item): item is SnapshotSession => item !== null);
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
  const matched = sessions
    .filter((row) => {
      if (row.activity_id !== block.activity_id) {
        return false;
      }
      if ((row.location_id || "") !== (block.location_id || "")) {
        return false;
      }
      if (row.start_time !== block.start_time || row.end_time !== block.end_time) {
        return false;
      }
      if (row.date < startIso || row.date > endIso) {
        return false;
      }
      if (row.weekday !== null && row.weekday !== block.weekday) {
        return false;
      }
      return true;
    })
    .map((row) => row.date);
  return uniqueSortedDateList(matched);
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
          weekday: Number.isFinite(weekday) && weekday >= 0 && weekday <= 6 ? weekday : 0,
          start_date: startDate,
          end_date: endDate,
          start_time: startTime,
          end_time: endTime,
          modality,
          calendar_name: calendarName,
          holiday_dates: holidayDates,
          closure_dates: closureDates,
          solfege_enabled: false,
          solfege_level: "",
          solfege_start_date: "",
          solfege_slot_key: "",
          solfege_slot_raw: null,
          masterclass_enabled: false,
          masterclass_session: "",
          masterclass_location_id: "",
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
        calendar_name: "",
        holiday_dates: [],
        closure_dates: [],
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
  initialSnapshot,
  initialMeta,
  saveAction,
}: QuotePlanningEditorProps): JSX.Element {
  const [blocks, setBlocks] = useState<PlanningBlock[]>(parseInitialBlocks(initialSnapshot));
  const snapshotSessions = useMemo(() => parseSnapshotSessions(initialSnapshot), [initialSnapshot]);

  const blocksJson = useMemo(
    () =>
      JSON.stringify(
        blocks.map((row) => {
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
            exclude_holidays_in_recurrence:
              activities.find((item) => item.id === row.activity_id)?.exclude_holidays_in_recurrence !== false,
            exclude_school_vacations_in_recurrence:
              activities.find((item) => item.id === row.activity_id)?.exclude_school_vacations_in_recurrence !== false,
          };
        }),
      ),
    [blocks, activities, locations],
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
        calendar_name: "",
        holiday_dates: [],
        closure_dates: [],
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
          const calculatedDates = datesFromSnapshotSessions(block, snapshotSessions);
          const estimatedDates = calculatedDates.length > 0 ? calculatedDates : estimateSessionDates(block);
          const semester1 = summarizeBySemester(estimatedDates, 1);
          const semester2 = summarizeBySemester(estimatedDates, 2);
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
              <p className="muted top-gap-sm">
                Calendrier: {block.calendar_name || "Par defaut"}.
              </p>

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

                <p className="muted span-4">
                  Solfege et Masterclass sont des activites distinctes: ajoutez-les comme blocs planning separes.
                </p>
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
