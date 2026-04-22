"use client";

import { useState } from "react";

type ConditionalConfirmSubmitButtonProps = {
  formId: string;
  label: string;
  confirmFieldName: string;
  confirmFieldValue: string;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  closeAriaLabel?: string;
  missingFormError?: string;
  className?: string;
  disabled?: boolean;
};

function readFieldValue(form: HTMLFormElement, fieldName: string): string {
  const field = form.elements.namedItem(fieldName);
  if (field instanceof RadioNodeList) {
    return String(field.value ?? "");
  }
  if (
    field instanceof HTMLInputElement ||
    field instanceof HTMLSelectElement ||
    field instanceof HTMLTextAreaElement
  ) {
    return String(field.value ?? "");
  }
  return "";
}

export default function ConditionalConfirmSubmitButton({
  formId,
  label,
  confirmFieldName,
  confirmFieldValue,
  title,
  description = "",
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  closeAriaLabel = "Fermer",
  missingFormError = "Formulaire introuvable.",
  className,
  disabled = false,
}: ConditionalConfirmSubmitButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const close = (): void => {
    setOpen(false);
    setErrorMessage("");
  };

  const getForm = (): HTMLFormElement | null => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage(missingFormError);
      setOpen(true);
      return null;
    }
    return form;
  };

  const submitNow = (): void => {
    const form = getForm();
    if (!form) {
      return;
    }
    form.requestSubmit();
  };

  const handleClick = (): void => {
    if (disabled) {
      return;
    }
    const form = getForm();
    if (!form) {
      return;
    }
    const currentValue = readFieldValue(form, confirmFieldName).trim().toUpperCase();
    if (currentValue === confirmFieldValue.trim().toUpperCase()) {
      setErrorMessage("");
      setOpen(true);
      return;
    }
    form.requestSubmit();
  };

  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={handleClick}>
        {label}
      </button>

      {open ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <button className="modal-close-x" type="button" onClick={close} aria-label={closeAriaLabel}>
              ×
            </button>
            <h3 className="modal-title">{title}</h3>
            {description ? <p className="muted">{description}</p> : null}
            {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={close}>
                {cancelLabel}
              </button>
              <button
                type="button"
                onClick={() => {
                  close();
                  submitNow();
                }}
              >
                {confirmLabel}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
