import React from "react";

export type QuoteIntegrationUiState =
  | "non_concerne"
  | "en_attente_validation_client"
  | "a_preparer"
  | "a_verifier"
  | "pret_a_integrer"
  | "integre"
  | "erreur_integration";

const LABELS: Record<QuoteIntegrationUiState, string> = {
  non_concerne: "Non concerne",
  en_attente_validation_client: "En attente validation",
  a_preparer: "A preparer",
  a_verifier: "A verifier",
  pret_a_integrer: "Pret a integrer",
  integre: "Integre",
  erreur_integration: "Erreur integration",
};

const CLASSES: Record<QuoteIntegrationUiState, string> = {
  non_concerne: "status-off",
  en_attente_validation_client: "status-off",
  a_preparer: "status-warn",
  a_verifier: "status-warn",
  pret_a_integrer: "status-warn",
  integre: "status-ok",
  erreur_integration: "status-cancelled",
};

export default function QuoteRowIntegrationState({ state }: { state: QuoteIntegrationUiState }): JSX.Element {
  return <span className={`status-pill ${CLASSES[state]}`}>{LABELS[state]}</span>;
}
