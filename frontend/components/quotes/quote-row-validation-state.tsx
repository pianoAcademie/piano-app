import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export type QuoteValidationUiState =
  | "brouillon"
  | "incomplet"
  | "pret_a_envoyer"
  | "envoye"
  | "consulte"
  | "modification_demandee"
  | "valide"
  | "refuse"
  | "expire";

const LABEL_KEYS: Record<QuoteValidationUiState, string> = {
  brouillon: "admin.quotes.validation.brouillon",
  incomplet: "admin.quotes.validation.incomplet",
  pret_a_envoyer: "admin.quotes.validation.pret_a_envoyer",
  envoye: "admin.quotes.validation.envoye",
  consulte: "admin.quotes.validation.consulte",
  modification_demandee: "admin.quotes.validation.modification_demandee",
  valide: "admin.quotes.validation.valide",
  refuse: "admin.quotes.validation.refuse",
  expire: "admin.quotes.validation.expire",
};

const CLASSES: Record<QuoteValidationUiState, string> = {
  brouillon: "status-off",
  incomplet: "status-warn",
  pret_a_envoyer: "status-warn",
  envoye: "status-warn",
  consulte: "status-warn",
  modification_demandee: "status-info",
  valide: "status-ok",
  refuse: "status-cancelled",
  expire: "status-cancelled",
};

export default function QuoteRowValidationState({
  state,
  language = "fr",
}: {
  state: QuoteValidationUiState;
  language?: UiLanguage;
}): JSX.Element {
  return <span className={`status-pill ${CLASSES[state]}`}>{uiText(language, LABEL_KEYS[state])}</span>;
}
