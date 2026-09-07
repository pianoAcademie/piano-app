"use client";

import type { ReactNode } from "react";

export function TeacherSyncConfirmForm({
  action,
  children,
  message,
  className,
  selectionInputName,
  emptySelectionMessage,
}: {
  action: (formData: FormData) => void | Promise<void>;
  children: ReactNode;
  message: string;
  className?: string;
  selectionInputName?: string;
  emptySelectionMessage?: string;
}): JSX.Element {
  return (
    <form
      action={action}
      className={className}
      onSubmit={(event) => {
        const selected = selectionInputName
          ? Array.from(event.currentTarget.elements).filter(
              (element): element is HTMLInputElement =>
                element instanceof HTMLInputElement &&
                element.name === selectionInputName &&
                element.checked,
            )
          : [];
        if (selectionInputName && selected.length === 0) {
          event.preventDefault();
          window.alert(emptySelectionMessage || "Select at least one change.");
          return;
        }
        const confirmationMessage = message.replace("{count}", String(selected.length));
        if (!window.confirm(confirmationMessage)) event.preventDefault();
      }}
    >
      {children}
    </form>
  );
}

export function TeacherSyncSelectionButtons({
  inputName,
  selectAllLabel,
  clearAllLabel,
}: {
  inputName: string;
  selectAllLabel: string;
  clearAllLabel: string;
}): JSX.Element {
  const setChecked = (button: HTMLButtonElement, checked: boolean): void => {
    const form = button.closest("form");
    if (!form) return;
    form.querySelectorAll<HTMLInputElement>(`input[name="${inputName}"]`).forEach((input) => {
      if (input.disabled) return;
      input.checked = checked;
    });
  };

  return (
    <div className="row">
      <button type="button" className="ghost" onClick={(event) => setChecked(event.currentTarget, true)}>
        {selectAllLabel}
      </button>
      <button type="button" className="ghost" onClick={(event) => setChecked(event.currentTarget, false)}>
        {clearAllLabel}
      </button>
    </div>
  );
}
