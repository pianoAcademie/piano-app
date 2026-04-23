"use client";

import { useEffect, useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type Props = {
  formId: string;
  selectAllLabel?: string;
  summaryLabel?: string;
  language?: UiLanguage | string;
};

function getForm(formId: string): HTMLFormElement | null {
  const form = document.getElementById(formId);
  if (form instanceof HTMLFormElement) {
    return form;
  }
  return null;
}

function allCollaboratorCheckboxes(form: HTMLFormElement): HTMLInputElement[] {
  return Array.from(form.querySelectorAll<HTMLInputElement>('input[name="collaborator_ids"]'));
}

function formatSummary(template: string, selectedCount: number, totalCount: number): string {
  return template.replace("{selected}", String(selectedCount)).replace("{total}", String(totalCount));
}

export default function CollaboratorSelectionControls({
  formId,
  selectAllLabel,
  summaryLabel,
  language: languageProp = "fr",
}: Props): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const localizedSelectAllLabel = selectAllLabel ?? uiText(language, "collaborator_selection.select_all");
  const localizedSummaryLabel = summaryLabel ?? uiText(language, "collaborator_selection.summary");
  const [selectedCount, setSelectedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    const form = getForm(formId);
    if (!form) {
      return;
    }

    const toggle = form.querySelector<HTMLInputElement>('input[data-role="select-all-collaborators"]');
    const sync = (): void => {
      const boxes = allCollaboratorCheckboxes(form);
      const selected = boxes.filter((box) => box.checked).length;
      setSelectedCount(selected);
      setTotalCount(boxes.length);
      if (toggle) {
        toggle.checked = boxes.length > 0 && selected === boxes.length;
        toggle.indeterminate = selected > 0 && selected < boxes.length;
      }
    };

    const onChange = (): void => {
      sync();
    };

    const onToggle = (): void => {
      if (!toggle) {
        return;
      }
      for (const box of allCollaboratorCheckboxes(form)) {
        box.checked = toggle.checked;
      }
      sync();
    };

    form.addEventListener("change", onChange);
    if (toggle) {
      toggle.addEventListener("change", onToggle);
    }
    sync();

    return () => {
      form.removeEventListener("change", onChange);
      if (toggle) {
        toggle.removeEventListener("change", onToggle);
      }
    };
  }, [formId]);

  return (
    <div className="row spread">
      <label className="checkline">
        <input type="checkbox" data-role="select-all-collaborators" />
        {localizedSelectAllLabel}
      </label>
      <small className="muted">
        {formatSummary(localizedSummaryLabel, selectedCount, totalCount)}
      </small>
    </div>
  );
}
