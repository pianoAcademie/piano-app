"use client";

import { useState } from "react";

type SeriesCancellationSubmitButtonProps = {
  formId: string;
  language?: string;
};

function isSeriesScope(value: string): boolean {
  return value === "SERIES_FUTURE" || value === "SERIES_ALL";
}

export default function SeriesCancellationSubmitButton({
  formId,
  language = "fr",
}: SeriesCancellationSubmitButtonProps): JSX.Element {
  const isEnglish = language === "en";
  const [open, setOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const getForm = (): HTMLFormElement | null => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      setErrorMessage(isEnglish ? "Cancellation form not found." : "Formulaire d'annulation introuvable.");
      setOpen(true);
      return null;
    }
    return form;
  };

  const submit = (seriesConfirmed: boolean): void => {
    const form = getForm();
    if (!form) {
      return;
    }
    const existingConfirmationField = form.elements.namedItem("series_cancellation_confirmed");
    let confirmationField: HTMLInputElement;
    if (existingConfirmationField instanceof HTMLInputElement) {
      confirmationField = existingConfirmationField;
    } else {
      confirmationField = document.createElement("input");
      confirmationField.type = "hidden";
      confirmationField.name = "series_cancellation_confirmed";
      form.appendChild(confirmationField);
    }
    confirmationField.value = seriesConfirmed ? "1" : "0";
    form.requestSubmit();
  };

  const handleInitialConfirmation = (): void => {
    const form = getForm();
    if (!form) {
      return;
    }
    const scopeField = form.elements.namedItem("apply_scope");
    const scope = scopeField instanceof HTMLSelectElement ? scopeField.value : "ONE";
    if (isSeriesScope(scope)) {
      setErrorMessage("");
      setOpen(true);
      return;
    }
    submit(false);
  };

  return (
    <>
      <button className="danger" type="button" onClick={handleInitialConfirmation}>
        {isEnglish ? "Confirm cancellation" : "Confirmer l'annulation"}
      </button>

      {open ? (
        <section className="modal-overlay modal-overlay-front">
          <article className="modal-panel modal-compact" role="dialog" aria-modal="true">
            <button
              className="modal-close-x"
              type="button"
              onClick={() => setOpen(false)}
              aria-label={isEnglish ? "Close" : "Fermer"}
            >
              ×
            </button>
            <h3 className="modal-title">
              {isEnglish ? "Cancel the recurring series?" : "Annuler la série récurrente ?"}
            </h3>
            <p className="muted">
              {isEnglish
                ? "You selected a series scope. Several lessons will be cancelled. This second confirmation is required to continue."
                : "Vous avez sélectionné une portée de série. Plusieurs cours seront annulés. Cette seconde confirmation est obligatoire pour continuer."}
            </p>
            {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
            <div className="row modal-actions-end">
              <button type="button" className="ghost" onClick={() => setOpen(false)}>
                {isEnglish ? "Back" : "Retour"}
              </button>
              <button
                type="button"
                className="danger"
                onClick={() => {
                  setOpen(false);
                  submit(true);
                }}
              >
                {isEnglish ? "Yes, cancel the series" : "Oui, annuler la série"}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}
