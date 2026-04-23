"use client";

import { useEffect, useMemo, useState } from "react";
import ConfirmSubmitButton from "./confirm-submit-button";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

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
  language?: UiLanguage | string;
  submitAction: (formData: FormData) => Promise<void>;
};

function weekdayLabel(weekday: number, language: UiLanguage): string {
  if (weekday === 0) return uiText(language, "common.weekday_monday");
  if (weekday === 1) return uiText(language, "common.weekday_tuesday");
  if (weekday === 2) return uiText(language, "common.weekday_wednesday");
  if (weekday === 3) return uiText(language, "common.weekday_thursday");
  if (weekday === 4) return uiText(language, "common.weekday_friday");
  if (weekday === 5) return uiText(language, "common.weekday_saturday");
  if (weekday === 6) return uiText(language, "common.weekday_sunday");
  return uiText(language, "admin.quote_planning.day");
}

function modalityLabel(value: string | null, language: UiLanguage): string {
  const normalized = String(value || "").trim().toUpperCase();
  if (!normalized || normalized === "AUTO") {
    return "";
  }
  if (normalized === "ONLINE") {
    return uiText(language, "admin.quote_planning.modality_online");
  }
  if (normalized === "ONSITE") {
    return uiText(language, "admin.quote_planning.modality_onsite");
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

function slotOptionsFromRule(rule: SolfegeLevelRule | null, language: UiLanguage): SlotOption[] {
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
      const mode = modalityLabel(rule.modality, language);
      const label = `${weekdayLabel(weekday, language)} ${parts.start}-${parts.end}${mode ? ` · ${mode}` : ""}`;
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        label,
        payload: {
          level_code: rule.level_code,
          weekday,
          weekday_label: weekdayLabel(weekday, language),
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
      const mode = modalityLabel(rule.modality, language);
      const label = `${weekdayLabel(weekday, language)} ${parts.start}-${parts.end}${mode ? ` · ${mode}` : ""}`;
      options.push({
        key: `${weekday}|${parts.start}|${parts.end}`,
        label,
        payload: {
          level_code: rule.level_code,
          weekday,
          weekday_label: weekdayLabel(weekday, language),
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
  language: languageProp = "fr",
  submitAction,
}: QuoteFollowupSlotFormProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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

  const slotOptions = useMemo(() => slotOptionsFromRule(selectedRule, language), [selectedRule, language]);

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
      <h4>{t("admin.quote_followup_slot.title")}</h4>
      <input type="hidden" name="followup_id" value={followupId} />
      <input type="hidden" name="return_to" value={returnTo} />
      <input type="hidden" name="solfege_level_code" value={selectedLevel} />
      <input type="hidden" name="slot_json" value={selectedSlot ? JSON.stringify(selectedSlot.payload) : ""} />

      <label>
        {t("admin.quote_followup_slot.level")}
        <select
          name="solfege_level_choice"
          value={selectedLevel}
          onChange={(event) => setSelectedLevel(event.target.value)}
          required
        >
          <option value="">{t("common.select")}</option>
          {availableLevels.map((levelCode) => (
            <option key={levelCode} value={levelCode}>
              {t("admin.quote_followup_slot.level_value", { level: levelCode })}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("admin.quote_followup_slot.slot_reference")}
        <select
          name="solfege_slot_choice"
          value={selectedSlotKey}
          onChange={(event) => setSelectedSlotKey(event.target.value)}
          required
          disabled={!selectedLevel || slotOptions.length === 0}
        >
          <option value="">{t("common.select")}</option>
          {slotOptions.map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </select>
      </label>

      {!selectedLevel ? <p className="muted">{t("admin.quote_followup_slot.select_level_first")}</p> : null}
      {selectedLevel && slotOptions.length === 0 ? (
        <p className="muted">{t("admin.quote_followup_slot.no_slot_for_level")}</p>
      ) : null}

      <ConfirmSubmitButton
        formId={formId}
        label={t("admin.quote_followup_slot.save_slot")}
        title={t("admin.quote_followup_slot.confirm_title")}
        description={t("admin.quote_followup_slot.confirm_description")}
        confirmLabel={t("common.save")}
        language={language}
        disabled={!canSubmit}
      />
    </form>
  );
}
