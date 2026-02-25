"use client";

import { useState } from "react";

type EffectiveDateSubmitButtonProps = {
  formId: string;
  defaultDate: string;
  label?: string;
  title?: string;
};

export default function EffectiveDateSubmitButton({
  formId,
  defaultDate,
  label = "Enregistrer les taux",
  title = "Date d'effet des nouveaux taux",
}: EffectiveDateSubmitButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [effectiveDate, setEffectiveDate] = useState(defaultDate);
  const [errorMessage, setErrorMessage] = useState("");

  const close = (): void => {
    setOpen(false);
    setErrorMessage("");
  };

  const confirm = (): void => {
    if (!effectiveDate) {
      setErrorMessage("Selectionnez une date d'effet.");
      return;
    }

    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage("Formulaire introuvable.");
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
        {label}
      </button>

      {open ? (
        <section className="modal-overlay">
          <article className="modal-panel modal-compact">
            <button className="modal-close-x" type="button" onClick={close} aria-label="Fermer">
              ×
            </button>
            <h3 className="modal-title">{title}</h3>
            <p className="muted">La mise a jour remplacera les taux collaborateur a partir de cette date.</p>

            {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

            <label>
              Date d effet
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
                Annuler
              </button>
              <button type="button" onClick={confirm}>
                Valider
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
