"use client";

import { useState } from "react";

type ConfirmSubmitButtonProps = {
  formId: string;
  label: string;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  className?: string;
  disabled?: boolean;
};

export default function ConfirmSubmitButton({
  formId,
  label,
  title,
  description = "",
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  className,
  disabled = false,
}: ConfirmSubmitButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const close = (): void => {
    setOpen(false);
    setErrorMessage("");
  };

  const confirm = (): void => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage("Formulaire introuvable.");
      return;
    }
    close();
    form.requestSubmit();
  };

  return (
    <>
      <button
        type="button"
        className={className}
        disabled={disabled}
        onClick={() => {
          if (disabled) {
            return;
          }
          setOpen(true);
          setErrorMessage("");
        }}
      >
        {label}
      </button>

      {open ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <button className="modal-close-x" type="button" onClick={close} aria-label="Fermer">
              ×
            </button>
            <h3 className="modal-title">{title}</h3>
            {description ? (
              <p className="muted" style={{ whiteSpace: "pre-line" }}>
                {description}
              </p>
            ) : null}
            {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={close}>
                {cancelLabel}
              </button>
              <button type="button" onClick={confirm}>
                {confirmLabel}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
