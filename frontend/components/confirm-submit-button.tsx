"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type ConfirmSubmitButtonProps = {
  formId: string;
  label: string;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  closeAriaLabel?: string;
  missingFormError?: string;
  language?: UiLanguage | string;
  className?: string;
  disabled?: boolean;
  disabledReason?: string;
  pendingLabel?: string;
};

export default function ConfirmSubmitButton({
  formId,
  label,
  title,
  description = "",
  confirmLabel,
  cancelLabel,
  closeAriaLabel,
  missingFormError,
  language: languageProp = "fr",
  className,
  disabled = false,
  disabledReason = "",
  pendingLabel,
}: ConfirmSubmitButtonProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const resolvedConfirmLabel = confirmLabel ?? uiText(language, "common.confirm");
  const resolvedCancelLabel = cancelLabel ?? uiText(language, "common.cancel");
  const resolvedCloseAriaLabel = closeAriaLabel ?? uiText(language, "common.close");
  const resolvedMissingFormError = missingFormError ?? uiText(language, "common.form_not_found");
  const { pending } = useFormStatus();
  const [open, setOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const close = (): void => {
    setOpen(false);
    setErrorMessage("");
  };

  const confirm = (): void => {
    if (disabled) {
      setErrorMessage(disabledReason || resolvedMissingFormError);
      return;
    }
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage(resolvedMissingFormError);
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
        disabled={pending || (disabled && !disabledReason)}
        aria-disabled={pending || disabled || undefined}
        onClick={() => {
          if (pending) {
            return;
          }
          if (disabled) {
            if (disabledReason) {
              setOpen(true);
              setErrorMessage(disabledReason);
            }
            return;
          }
          setOpen(true);
          setErrorMessage("");
        }}
      >
        {pending ? pendingLabel ?? label : label}
      </button>

      {open ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact" role="dialog" aria-modal="true" aria-label={title}>
            <button className="modal-close-x" type="button" onClick={close} aria-label={resolvedCloseAriaLabel}>
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
                {resolvedCancelLabel}
              </button>
              {disabled ? null : (
                <button type="button" onClick={confirm}>
                  {resolvedConfirmLabel}
                </button>
              )}
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
