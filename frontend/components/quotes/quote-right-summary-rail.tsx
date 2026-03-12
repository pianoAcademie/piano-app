import React from "react";

export default function QuoteRightSummaryRail({
  top,
  statuses,
  alerts,
}: {
  top: Array<{ label: string; value: string }>;
  statuses: Array<{ label: string; value: string }>;
  alerts: string[];
}): JSX.Element {
  return (
    <section className="quote-right-summary-rail">
      <article className="card quote-right-summary-card">
        <h3>Suite operationnelle</h3>
        <div className="top-gap-sm">
          {top.map((row) => (
            <p key={row.label}>
              <strong>{row.label}:</strong> {row.value}
            </p>
          ))}
        </div>
        <div className="top-gap-sm quote-right-summary-statuses">
          {statuses.map((row) => (
            <p key={row.label} className="muted">
              {row.label}: <strong>{row.value}</strong>
            </p>
          ))}
        </div>
        {alerts.length > 0 ? (
          <ul className="top-gap-sm quote-right-summary-alerts">
            {alerts.map((alert) => (
              <li key={alert}>{alert}</li>
            ))}
          </ul>
        ) : null}
      </article>
    </section>
  );
}
