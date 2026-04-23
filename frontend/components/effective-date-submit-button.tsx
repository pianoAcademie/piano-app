"use client";

import { useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type EffectiveDateSubmitButtonProps = {
  formId: string;
  defaultDate: string;
  label?: string;
  title?: string;
  language?: UiLanguage | string;
};

export default function EffectiveDateSubmitButton({
  formId,
  defaultDate,
  label,
  title,
  language: languageProp = "fr",
}: EffectiveDateSubmitButtonProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const localizedLabel = label ?? uiText(language, "effective_date_submit.save_rates");
  const localizedTitle = title ?? uiText(language, "effective_date_submit.title");
  const [open, setOpen] = useState(false);
  const [effectiveDate, setEffectiveDate] = useState(defaultDate);
  const [errorMessage, setErrorMessage] = useState("");

  const close = (): void => {
    setOpen(false);
    setErrorMessage("");
  };

  const confirm = (): void => {
    if (!effectiveDate) {
      setErrorMessage(uiText(language, "effective_date_submit.date_required"));
      return;
    }

    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage(uiText(language, "common.form_not_found"));
      return;
    }

    const hidden =
      form.querySelector<HTMLInputElement>('input[name="effective_from"]') ??
      (() => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "effective_from";
        form.appendChild(input);
        return input;
      })();

    hidden.value = effectiveDate;
    close();
    form.requestSubmit();
  };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        {localizedLabel}
      </button>

      {open ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <button className="modal-close-x" type="button" onClick={close} aria-label={uiText(language, "common.close")}>
              ×
            </button>
            <h3 className="modal-title">{localizedTitle}</h3>
            <p className="muted">{uiText(language, "effective_date_submit.help")}</p>

            {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

            <label>
              {uiText(language, "effective_date_submit.effective_date")}
              <input
                type="date"
                value={effectiveDate}
                onChange={(event) => {
                  setEffectiveDate(event.target.value);
                  setErrorMessage("");
                }}
              />
            </label>

            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={close}>
                {uiText(language, "common.cancel")}
              </button>
              <button type="button" onClick={confirm}>
                {uiText(language, "common.validate")}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
