"use client";

import { useEffect, useState } from "react";

import type { AdminOnlinePresenceOut } from "../lib/types";

type Props = {
  language: "fr" | "en";
};

export default function AdminOnlinePresenceDashboard({ language }: Props): JSX.Element {
  const [summary, setSummary] = useState<AdminOnlinePresenceOut | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const english = language === "en";

  useEffect(() => {
    let stopped = false;
    const refresh = async (): Promise<void> => {
      try {
        const response = await fetch("/api/admin/presence", { cache: "no-store" });
        if (!response.ok) throw new Error(`Presence ${response.status}`);
        const payload = (await response.json()) as AdminOnlinePresenceOut;
        if (!stopped) {
          setSummary(payload);
          setUnavailable(false);
        }
      } catch {
        if (!stopped) setUnavailable(true);
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 10_000);
    return () => {
      stopped = true;
      window.clearInterval(interval);
    };
  }, []);

  const metrics = [
    { label: english ? "Online now" : "En ligne maintenant", value: summary?.total ?? "–", primary: true },
    { label: english ? "Website" : "Site internet", value: summary?.web ?? "–" },
    { label: english ? "Mobile app" : "Application mobile", value: summary?.mobile_app ?? "–" },
    { label: english ? "Clients" : "Clients", value: summary?.clients ?? "–" },
    { label: english ? "Teachers" : "Professeurs", value: summary?.professors ?? "–" },
    { label: english ? "Admins" : "Administrateurs", value: summary?.admins ?? "–" },
  ];

  return (
    <section className="card online-presence-card" aria-live="polite">
      <div className="row spread online-presence-heading">
        <div>
          <h3>{english ? "Live connections" : "Connexions en temps réel"}</h3>
          <p className="muted">
            {english ? "Active during the last 90 seconds." : "Personnes actives au cours des 90 dernières secondes."}
          </p>
        </div>
        <span className={`online-presence-status ${unavailable ? "is-unavailable" : ""}`}>
          <span aria-hidden="true" />
          {unavailable ? (english ? "Unavailable" : "Indisponible") : (english ? "Live" : "En direct")}
        </span>
      </div>
      <div className="online-presence-metrics">
        {metrics.map((metric) => (
          <article key={metric.label} className={metric.primary ? "is-primary" : ""}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </div>
      {summary ? (
        <small className="muted">
          {english ? "Updated" : "Mis à jour"} {new Date(summary.generated_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </small>
      ) : null}
    </section>
  );
}
