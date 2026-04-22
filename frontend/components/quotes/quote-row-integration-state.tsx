import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export type QuoteIntegrationUiState =
  | "non_concerne"
  | "en_attente_validation_client"
  | "a_preparer"
  | "a_verifier"
  | "pret_a_integrer"
  | "integre"
  | "erreur_integration";

const LABEL_KEYS: Record<QuoteIntegrationUiState, string> = {
  non_concerne: "admin.quotes.integration.non_concerne",
  en_attente_validation_client: "admin.quotes.integration.en_attente_validation_client",
  a_preparer: "admin.quotes.integration.a_preparer",
  a_verifier: "admin.quotes.integration.a_verifier",
  pret_a_integrer: "admin.quotes.integration.pret_a_integrer",
  integre: "admin.quotes.integration.integre",
  erreur_integration: "admin.quotes.integration.erreur_integration",
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

export default function QuoteRowIntegrationState({
  state,
  language = "fr",
}: {
  state: QuoteIntegrationUiState;
  language?: UiLanguage;
}): JSX.Element {
  return <span className={`status-pill ${CLASSES[state]}`}>{uiText(language, LABEL_KEYS[state])}</span>;
}
