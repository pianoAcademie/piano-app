import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export default function QuoteValidationIntegrationSection({
  validationRows,
  projectionCard,
  clientMatchCard,
  integrationResultCard,
  note,
  language = "fr",
}: {
  validationRows: Array<{ label: string; value: string }>;
  projectionCard: React.ReactNode;
  clientMatchCard: React.ReactNode;
  integrationResultCard: React.ReactNode;
  note?: string;
  language?: UiLanguage;
}): JSX.Element {
  return (
    <section className="card quote-validation-integration-section">
      <h3>{uiText(language, "admin.quote_detail.validation_integration_title")}</h3>
      <p className="muted">
        {uiText(language, "admin.quote_detail.validation_integration_subtitle")}
      </p>
      <article className="item top-gap-sm">
        <h4>{uiText(language, "admin.quote_detail.client_validation_title")}</h4>
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
