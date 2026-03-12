import React from "react";

export default function QuoteValidationIntegrationSection({
  validationRows,
  projectionCard,
  clientMatchCard,
  integrationResultCard,
  note,
}: {
  validationRows: Array<{ label: string; value: string }>;
  projectionCard: React.ReactNode;
  clientMatchCard: React.ReactNode;
  integrationResultCard: React.ReactNode;
  note?: string;
}): JSX.Element {
  return (
    <section className="card quote-validation-integration-section">
      <h3>Validation et integration</h3>
      <p className="muted">
        Section preparee pour la future connexion a l'application centrale. Lecture seule pour le moment.
      </p>
      <article className="item top-gap-sm">
        <h4>Validation client</h4>
        <div className="grid cols-2 top-gap-sm">
          {validationRows.map((row) => (
            <p key={row.label}>
              <strong>{row.label}:</strong> {row.value}
            </p>
          ))}
        </div>
      </article>
      <div className="grid cols-1 top-gap-sm quote-integration-stack">
        {projectionCard}
        {clientMatchCard}
        {integrationResultCard}
      </div>
      {note ? <p className="flash-warn top-gap-sm">{note}</p> : null}
    </section>
  );
}
