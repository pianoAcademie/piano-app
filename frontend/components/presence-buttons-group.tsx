"use client";

import { useEffect, useMemo, useState } from "react";

type PresenceValue = "BOOKED" | "ATTENDED" | "EXCUSED_ABSENCE" | "NO_SHOW";

type PresenceButtonsGroupProps = {
  formId: string;
  name?: string;
  initialValue: PresenceValue;
  previousHref?: string | null;
  nextHref?: string | null;
};

const OPTIONS: Array<{ value: PresenceValue; label: string; hotkey: string; tone: string }> = [
  { value: "BOOKED", label: "A saisir", hotkey: "1", tone: "warn" },
  { value: "ATTENDED", label: "Present", hotkey: "2", tone: "ok" },
  { value: "EXCUSED_ABSENCE", label: "Abs. excuse", hotkey: "3", tone: "neutral" },
  { value: "NO_SHOW", label: "Abs. non excuse", hotkey: "4", tone: "danger" },
];

export default function PresenceButtonsGroup({
  formId,
  name = "attendance_status",
  initialValue,
  previousHref,
  nextHref,
}: PresenceButtonsGroupProps): JSX.Element {
  const [selected, setSelected] = useState<PresenceValue>(initialValue);
  const isDirty = selected !== initialValue;

  useEffect(() => {
    setSelected(initialValue);
  }, [initialValue]);

  const shortcutsHint = useMemo(() => "1-4: statut · Enter: enregistrer · ↑/↓: eleve", []);

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
      <div className="presence-buttons-grid" role="radiogroup" aria-label="Statut de presence">
        {OPTIONS.map((option) => {
          const active = option.value === selected;
          return (
            <button
              key={option.value}
              type="button"
              className={`presence-button tone-${option.tone} ${active ? "active" : ""}`}
              onClick={() => setSelected(option.value)}
              role="radio"
              aria-checked={active}
              aria-label={`${option.label} (raccourci ${option.hotkey})`}
            >
              <span>{option.label}</span>
              <small>{option.hotkey}</small>
            </button>
          );
        })}
      </div>
      <div className="presence-group-meta">
        <small className="muted">{shortcutsHint}</small>
        {isDirty ? <small className="presence-dirty-flag">Modifications non enregistrees</small> : null}
      </div>
    </div>
  );
}
