import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export default function QuoteIntegrationProjectionCard({
  rows,
  language = "fr",
}: {
  rows: Array<{ label: string; value: string }>;
  language?: UiLanguage;
}): JSX.Element {
  return (
    <article className="item quote-integration-card">
      <h4>{uiText(language, "admin.quote_detail.integration_projection_title")}</h4>
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
