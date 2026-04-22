import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export type QuoteNextAction =
  | "completer_le_devis"
  | "envoyer"
  | "relancer"
  | "traiter_demande_client"
  | "regenerer"
  | "preparer_integration"
  | "verifier_correspondance_client"
  | "integrer_dans_centrale"
  | "aucune_action";

const LABEL_KEYS: Record<QuoteNextAction, string> = {
  completer_le_devis: "admin.quotes.next.completer_le_devis",
  envoyer: "admin.quotes.next.envoyer",
  relancer: "admin.quotes.next.relancer",
  traiter_demande_client: "admin.quotes.next.traiter_demande_client",
  regenerer: "admin.quotes.next.regenerer",
  preparer_integration: "admin.quotes.next.preparer_integration",
  verifier_correspondance_client: "admin.quotes.next.verifier_correspondance_client",
  integrer_dans_centrale: "admin.quotes.next.integrer_dans_centrale",
  aucune_action: "admin.quotes.next.aucune_action",
};

export default function QuoteRowNextAction({
  action,
  language = "fr",
}: {
  action: QuoteNextAction;
  language?: UiLanguage;
}): JSX.Element {
  return <span className="badge quote-next-action-badge">{uiText(language, LABEL_KEYS[action])}</span>;
}
