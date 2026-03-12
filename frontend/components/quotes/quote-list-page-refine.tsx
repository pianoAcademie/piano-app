import React from "react";

export default function QuoteListPageRefine({
  actions,
  children,
}: {
  actions?: React.ReactNode;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section className="card quote-list-refine-card">
      <div className="row spread wrap gap-sm">
        <div>
          <h3>Pilotage des devis</h3>
          <p className="muted">Filtres rapides et filtres avances pour traiter un grand volume.</p>
        </div>
        {actions ? <div className="row wrap gap-sm">{actions}</div> : null}
      </div>
      <div className="top-gap-sm">{children}</div>
    </section>
  );
}
