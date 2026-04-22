import React from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";

export default function QuoteListPageRefine({
  actions,
  children,
  language = "fr",
}: {
  actions?: React.ReactNode;
  children: React.ReactNode;
  language?: UiLanguage;
}): JSX.Element {
  return (
    <section className="card quote-list-refine-card">
      <div className="row spread wrap gap-sm">
        <div>
          <h3>{uiText(language, "admin.quotes.refine_title")}</h3>
          <p className="muted">{uiText(language, "admin.quotes.refine_subtitle")}</p>
        </div>
        {actions ? <div className="row wrap gap-sm">{actions}</div> : null}
      </div>
      <div className="top-gap-sm">{children}</div>
    </section>
  );
}
