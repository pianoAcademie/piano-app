import React from "react";

export type QuoteNextAction =
  | "completer_le_devis"
  | "envoyer"
  | "relancer"
  | "regenerer"
  | "preparer_integration"
  | "verifier_correspondance_client"
  | "integrer_dans_centrale"
  | "aucune_action";

const LABELS: Record<QuoteNextAction, string> = {
  completer_le_devis: "Completer le devis",
  envoyer: "Envoyer",
  relancer: "Relancer",
  regenerer: "Regenerer",
  preparer_integration: "Preparer integration",
  verifier_correspondance_client: "Verifier correspondance client",
  integrer_dans_centrale: "Integrer dans application centrale",
  aucune_action: "Aucune action",
};

export default function QuoteRowNextAction({ action }: { action: QuoteNextAction }): JSX.Element {
  return <span className="badge quote-next-action-badge">{LABELS[action]}</span>;
}
