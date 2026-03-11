"use client";

import { useEffect, useMemo, useState } from "react";
import ConfirmSubmitButton from "./confirm-submit-button";

type SolfegeLevelRule = {
  id: string;
  level_code: string;
  duration_minutes: number;
  allowed_weekdays: number[];
  allowed_time_slots: Array<Record<string, unknown>>;
  location_id: string | null;
  modality: string | null;
};

type SlotOption = {
  key: string;
  label: string;
  payload: Record<string, unknown>;
};

type QuoteFollowupSlotFormProps = {
  followupId: string;
  returnTo: string;
  solfegeRules: SolfegeLevelRule[];
  initialLevelCode: string;
  initialSelectedSlot: Record<string, unknown> | null;
  submitAction: (formData: FormData) => Promise<void>;
};

function weekdayLabel(weekday: number): string {
  if (weekday === 0) return "Lundi";
  if (weekday === 1) return "Mardi";
  if (weekday === 2) return "Mercredi";
  if (weekday === 3) return "Jeudi";
  if (weekday === 4) return "Vendredi";
  if (weekday === 5) return "Samedi";
  if (weekday === 6) return "Dimanche";
  return "Jour";
}

function modalityLabel(value: string | null): string {
  const normalized = String(value || "").trim().toUpperCase();
  if (!normalized || normalized === "AUTO") {
    return "";
  }
  if (normalized === "ONLINE") {
    return "En ligne";
  }
  if (normalized === "ONSITE") {
    return "Presentiel";
  }
  return normalized;
}

function slotParts(slot: Record<string, unknown>): { start: string; end: string } | null {
  const start = typeof slot.start_time === "string" ? slot.start_time : typeof slot.start === "string" ? slot.start : "";
  const end = typeof slot.end_time === "string" ? slot.end_time : typeof slot.end === "string" ? slot.end : "";
  if (!start || !end) {
    return null;
  }
  return { start, end };
}

function slotOptionsFromRule(rule: SolfegeLevelRule | null): SlotOption[] {
  if (!rule) {
    return [];
  }

  const options: SlotOption[] = [];
  const hasStructuredWeekdays = rule.allowed_time_slots.some((slot) => {
    const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
    return Number.isFinite(weekday) && weekday >= 0 && weekday <= 6;
  });

  if (hasStructuredWeekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = slotParts(slot);
      if (!parts) {
        continue;
      }
      const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
      if (!Number.isFinite(weekday) || weekday < 0 || weekday > 6) {
        continue;
      }
      const mode = modalityLabel(rule.modality);
      const label = `${weekdayLabel(weekday)} ${parts.start}-${parts.end}${mode ? ` · ${mode}` : ""}`;
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        label,
        payload: {
          level_code: rule.level_code,
          weekday,
          weekday_label: weekdayLabel(weekday),
          start_time: parts.start,
          end_time: parts.end,
          duration_minutes: rule.duration_minutes,
          location_id: rule.location_id,
          modality: rule.modality,
          label,
        },
      });
    }
    return options;
  }

  const weekdays = rule.allowed_weekdays.length > 0
    ? rule.allowed_weekdays.filter((day) => Number.isFinite(day) && day >= 0 && day <= 6)
    : [0, 1, 2, 3, 4, 5, 6];

  for (const weekday of weekdays) {
    for (const slot of rule.allowed_time_slots) {
      const parts = slotParts(slot);
      if (!parts) {
        continue;
      }
      const mode = modalityLabel(rule.modality);
      const label = `${weekdayLabel(weekday)} ${parts.start}-${parts.end}${mode ? ` · ${mode}` : ""}`;
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        label,
        payload: {
          level_code: rule.level_code,
          weekday,
          weekday_label: weekdayLabel(weekday),
          start_time: parts.start,
          end_time: parts.end,
          duration_minutes: rule.duration_minutes,
          location_id: rule.location_id,
          modality: rule.modality,
          label,
        },
      });
    }
  }
  return options;
}

function keyFromSlot(slot: Record<string, unknown> | null): string {
  if (!slot) {
    return "";
  }
  const weekday = Number.parseInt(String(slot.weekday ?? ""), 10);
  const start = String(slot.start_time ?? "").trim();
  const end = String(slot.end_time ?? "").trim();
  if (!Number.isFinite(weekday) || !start || !end) {
    return "";
  }
  return `${weekday}|${start}|${end}`;
}

export default function QuoteFollowupSlotForm({
  followupId,
  returnTo,
  solfegeRules,
  initialLevelCode,
  initialSelectedSlot,
  submitAction,
}: QuoteFollowupSlotFormProps): JSX.Element {
  const formId = `quote-followup-slot-form-${followupId}`;
  const availableLevels = useMemo(
    () => Array.from(new Set(solfegeRules.map((row) => String(row.level_code || "").trim()).filter(Boolean))),
    [solfegeRules],
  );

  const [selectedLevel, setSelectedLevel] = useState<string>(() => {
    const initial = String(initialLevelCode || "").trim();
    if (initial && availableLevels.includes(initial)) {
      return initial;
    }
    return availableLevels[0] || "";
  });

  const selectedRule = useMemo(
    () => solfegeRules.find((row) => String(row.level_code || "").trim() === selectedLevel) ?? null,
    [solfegeRules, selectedLevel],
  );

  const slotOptions = useMemo(() => slotOptionsFromRule(selectedRule), [selectedRule]);

  const [selectedSlotKey, setSelectedSlotKey] = useState<string>(() => keyFromSlot(initialSelectedSlot));

  useEffect(() => {
    if (slotOptions.some((row) => row.key === selectedSlotKey)) {
      return;
    }
    const initialKey = keyFromSlot(initialSelectedSlot);
    if (initialKey && slotOptions.some((row) => row.key === initialKey)) {
      setSelectedSlotKey(initialKey);
      return;
    }
    setSelectedSlotKey("");
  }, [slotOptions, selectedSlotKey, initialSelectedSlot]);

  const selectedSlot = useMemo(
    () => slotOptions.find((row) => row.key === selectedSlotKey) ?? null,
    [slotOptions, selectedSlotKey],
  );

  const canSubmit = Boolean(selectedLevel) && Boolean(selectedSlot);

  return (
    <form id={formId} action={submitAction} className="card quote-followup-form">
      <h4>Selectionner / modifier le creneau solfege</h4>
      <input type="hidden" name="followup_id" value={followupId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="solfege_level_code" value={selectedLevel} />
      <input type="hidden" name="slot_json" value={selectedSlot ? JSON.stringify(selectedSlot.payload) : ""} />

      <label>
        Niveau
        <select
          name="solfege_level_choice"
          value={selectedLevel}
          onChange={(event) => setSelectedLevel(event.target.value)}
          required
        >
          <option value="">Selectionner</option>
          {availableLevels.map((levelCode) => (
            <option key={levelCode} value={levelCode}>
              Niveau {levelCode}
            </option>
          ))}
        </select>
      </label>

      <label>
        Creneau (referentiel)
        <select
          name="solfege_slot_choice"
          value={selectedSlotKey}
          onChange={(event) => setSelectedSlotKey(event.target.value)}
          required
          disabled={!selectedLevel || slotOptions.length === 0}
        >
          <option value="">Selectionner</option>
          {slotOptions.map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </select>
      </label>

      {!selectedLevel ? <p className="muted">Selectionnez d'abord un niveau.</p> : null}
      {selectedLevel && slotOptions.length === 0 ? (
        <p className="muted">Aucun creneau disponible pour ce niveau dans le referentiel.</p>
      ) : null}

      <ConfirmSubmitButton
        formId={formId}
        label="Enregistrer creneau"
        title="Confirmer la mise a jour du creneau de solfege ?"
        description="Le creneau selectionne sera applique au parcours post-approbation."
        confirmLabel="Enregistrer"
        disabled={!canSubmit}
      />
    </form>
  );
}
