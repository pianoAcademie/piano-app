import React from "react";

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

const LABELS: Record<QuoteValidationUiState, string> = {
  brouillon: "Brouillon",
  incomplet: "Incomplet",
  pret_a_envoyer: "Pret a envoyer",
  envoye: "Envoye",
  consulte: "Consulte",
  modification_demandee: "Modification demandee",
  valide: "Valide",
  refuse: "Refuse",
  expire: "Expire",
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

export default function QuoteRowValidationState({ state }: { state: QuoteValidationUiState }): JSX.Element {
  return <span className={`status-pill ${CLASSES[state]}`}>{LABELS[state]}</span>;
}
