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
  const isLongCodeValue = (label: string, value: string): boolean => (
    label.toLowerCase().includes("hash")
    || /^[a-f0-9]{32,}$/i.test(value.replace(/\s+/g, ""))
  );

  return (
    <section className="card quote-validation-integration-section">
      <h3>Validation et integration</h3>
      <p className="muted">
        Section preparee pour la future connexion a l'application centrale. Lecture seule pour le moment.
      </p>
      <article className="item top-gap-sm">
        <h4>Validation client</h4>
        <div className="grid cols-2 top-gap-sm quote-validation-grid">
          {validationRows.map((row) => (
            <div key={row.label} className="quote-validation-row">
              <strong className="quote-validation-row-label">{row.label}:</strong>
              <span
                className={`quote-validation-row-value${isLongCodeValue(row.label, row.value) ? " is-code" : ""}`}
              >
                {row.value}
              </span>
            </div>
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
