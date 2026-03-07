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
};

type QuotePlanningEditorProps = {
  quoteId: string;
  returnTo: string;
  editable: boolean;
  activities: ActivityOption[];
  locations: LocationOption[];
  initialSnapshot: Record<string, unknown>;
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
      },
    ];
  }
  return [];
}

export default function QuotePlanningEditor({
  quoteId,
  returnTo,
  editable,
  activities,
  locations,
  initialSnapshot,
  saveAction,
}: QuotePlanningEditorProps): JSX.Element {
  const [blocks, setBlocks] = useState<PlanningBlock[]>(parseInitialBlocks(initialSnapshot));

  const blocksJson = useMemo(
    () =>
      JSON.stringify(
        blocks.map((row) => ({
          activity_id: row.activity_id || null,
          location_id: row.location_id || null,
          weekday: row.weekday,
          start_date: row.start_date,
          end_date: row.end_date,
          start_time: row.start_time,
          end_time: row.end_time,
          modality: row.modality || null,
        })),
      ),
    [blocks],
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
      <input type="hidden" name="planning_blocks_json" value={blocksJson} />

      <div className="row wrap gap-sm">
        <button type="button" className="ghost" onClick={addBlock} disabled={!editable}>
          + Ajouter une activite planning
        </button>
      </div>

      {blocks.length === 0 ? <p className="muted top-gap-sm">Aucun bloc planning configure.</p> : null}
      <div className="list top-gap-sm">
        {blocks.map((block, index) => (
          <article key={block.uid} className="item">
            <div className="row spread wrap gap-sm">
              <strong>Activite #{index + 1}</strong>
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
                    const activity = activities.find((item) => item.id === block.activity_id);
                    const duration = activity?.duration_minutes ?? 60;
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
            </div>
          </article>
        ))}
      </div>

      <div className="row top-gap-sm">
        <button type="submit" disabled={!editable}>Enregistrer le planning</button>
      </div>
      {!editable ? <p className="muted top-gap-sm">Le devis est immuable apres envoi.</p> : null}
    </form>
  );
}
