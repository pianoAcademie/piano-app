import React from "react";

export default function QuoteIntegrationResultCard({
  rows,
}: {
  rows: Array<{ label: string; value: string }>;
}): JSX.Element {
  return (
    <article className="item quote-integration-card">
      <h4>Resultat d'integration</h4>
      <div className="grid cols-2 top-gap-sm">
        {rows.map((row) => (
          <p key={row.label}>
            <strong>{row.label}:</strong> {row.value}
          </p>
        ))}
      </div>
    </article>
  );
}
