import React from "react";

export default function QuoteOverviewSection({
  cards,
  alerts,
  quickActions,
}: {
  cards: Array<{ label: string; value: string }>;
  alerts: Array<{ level: "ok" | "warn" | "error"; message: string }>;
  quickActions?: React.ReactNode;
}): JSX.Element {
  return (
    <section className="card quote-overview-section">
      <h3>Vue d'ensemble</h3>
      <div className="grid cols-3 top-gap-sm quote-overview-kpis">
        {cards.map((card) => (
          <article key={card.label} className="item quote-overview-kpi">
            <small className="muted">{card.label}</small>
            <strong>{card.value}</strong>
          </article>
        ))}
      </div>
      {alerts.length > 0 ? (
        <div className="top-gap-sm quote-overview-alerts">
          {alerts.map((alert, index) => (
            <p key={`${alert.level}-${index}`} className={`flash-${alert.level === "error" ? "err" : alert.level}`}>
              {alert.message}
            </p>
          ))}
        </div>
      ) : null}
      {quickActions ? <div className="row wrap gap-sm top-gap-sm">{quickActions}</div> : null}
    </section>
  );
}
