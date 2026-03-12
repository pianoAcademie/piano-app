import React from "react";

export default function QuoteWorkspaceHeader({
  title,
  subtitle,
  backLink,
  statuses,
}: {
  title: string;
  subtitle: string;
  backLink: React.ReactNode;
  statuses: Array<{ label: string; value: string; className?: string }>;
}): JSX.Element {
  return (
    <section className="card quote-workspace-header-card">
      <div className="row spread wrap gap-sm">
        <div>
          <h2>{title}</h2>
          <p className="muted">{subtitle}</p>
        </div>
        <div className="row wrap gap-sm">{backLink}</div>
      </div>
      <div className="row wrap gap-sm top-gap-sm">
        {statuses.map((item) => (
          <span key={item.label} className={`badge quote-header-status ${item.className || ""}`.trim()}>
            {item.label}: <strong>{item.value}</strong>
          </span>
        ))}
      </div>
    </section>
  );
}
