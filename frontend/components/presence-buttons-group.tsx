"use client";

import { useEffect, useMemo, useState } from "react";

import { type UiLanguage, uiText } from "../lib/ui-i18n";

type PresenceValue = "BOOKED" | "ATTENDED" | "EXCUSED_ABSENCE" | "NO_SHOW";

type PresenceButtonsGroupProps = {
  formId: string;
  name?: string;
  initialValue: PresenceValue;
  language?: UiLanguage;
  previousHref?: string | null;
  nextHref?: string | null;
};

export default function PresenceButtonsGroup({
  formId,
  name = "attendance_status",
  initialValue,
  language = "fr",
  previousHref,
  nextHref,
}: PresenceButtonsGroupProps): JSX.Element {
  const [selected, setSelected] = useState<PresenceValue>(initialValue);
  const isDirty = selected !== initialValue;
  const options = useMemo(
    () => [
      { value: "BOOKED" as const, label: uiText(language, "admin.planning.attendance.to_fill"), hotkey: "1", tone: "warn" },
      { value: "ATTENDED" as const, label: uiText(language, "admin.planning.attendance.attended"), hotkey: "2", tone: "ok" },
      { value: "EXCUSED_ABSENCE" as const, label: uiText(language, "admin.planning.attendance.excused"), hotkey: "3", tone: "neutral" },
      { value: "NO_SHOW" as const, label: uiText(language, "admin.planning.attendance.no_show"), hotkey: "4", tone: "danger" },
    ],
    [language],
  );

  useEffect(() => {
    setSelected(initialValue);
  }, [initialValue]);

  const shortcutsHint = useMemo(() => uiText(language, "admin.planning.shortcuts_hint"), [language]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const active = document.activeElement as HTMLElement | null;
      if (!active?.closest(".session-attendance-modal-v2")) {
        return;
      }

      const tag = active.tagName.toLowerCase();
      const inTextField = tag === "textarea" || (tag === "input" && (active as HTMLInputElement).type === "text");

      if (!inTextField) {
        if (event.key === "1") {
          event.preventDefault();
          setSelected("BOOKED");
          return;
        }
        if (event.key === "2") {
          event.preventDefault();
          setSelected("ATTENDED");
          return;
        }
        if (event.key === "3") {
          event.preventDefault();
          setSelected("EXCUSED_ABSENCE");
          return;
        }
        if (event.key === "4") {
          event.preventDefault();
          setSelected("NO_SHOW");
          return;
        }
        if (event.key === "ArrowUp" && previousHref) {
          event.preventDefault();
          window.location.assign(previousHref);
          return;
        }
        if (event.key === "ArrowDown" && nextHref) {
          event.preventDefault();
          window.location.assign(nextHref);
          return;
        }
      }

      if (event.key === "Enter" && tag !== "textarea") {
        const form = document.getElementById(formId) as HTMLFormElement | null;
        if (form) {
          event.preventDefault();
          form.requestSubmit();
        }
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [formId, nextHref, previousHref]);

  return (
    <div className="presence-buttons-group">
      <input type="hidden" name={name} value={selected} />
      <div className="presence-buttons-grid" role="radiogroup" aria-label={uiText(language, "admin.planning.presence_radio_label")}>
        {options.map((option) => {
          const active = option.value === selected;
          return (
            <button
              key={option.value}
              type="button"
              className={`presence-button tone-${option.tone} ${active ? "active" : ""}`}
              onClick={() => setSelected(option.value)}
              role="radio"
              aria-checked={active}
              aria-label={uiText(language, "admin.planning.presence_shortcut_label", { label: option.label, hotkey: option.hotkey })}
            >
              <span>{option.label}</span>
              <small>{option.hotkey}</small>
            </button>
          );
        })}
      </div>
      <div className="presence-group-meta">
        <small className="muted">{shortcutsHint}</small>
        {isDirty ? <small className="presence-dirty-flag">{uiText(language, "admin.planning.unsaved_changes")}</small> : null}
      </div>
    </div>
  );
}
