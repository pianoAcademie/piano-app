import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export default function QuoteClientMatchCard({
  status,
  detail,
  language = "fr",
}: {
  status: "aucun" | "probable" | "multiple" | "deja_lie";
  detail: string;
  language?: UiLanguage;
}): JSX.Element {
  const label =
    status === "aucun"
      ? uiText(language, "admin.quote_detail.client_match_none")
      : status === "probable"
      ? uiText(language, "admin.quote_detail.client_match_probable")
      : status === "multiple"
      ? uiText(language, "admin.quote_detail.client_match_multiple")
      : uiText(language, "admin.quote_detail.client_match_linked");
  return (
    <article className="item quote-integration-card">
      <h4>{uiText(language, "admin.quote_detail.client_match_title")}</h4>
      <p className="top-gap-sm">
        <strong>{label}</strong>
      </p>
      <p className="muted">{detail}</p>
    </article>
  );
}
