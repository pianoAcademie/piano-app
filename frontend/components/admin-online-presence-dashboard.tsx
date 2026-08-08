"use client";

import { useEffect, useState } from "react";

import type { AdminOnlinePresenceOut } from "../lib/types";

type Props = {
  language: "fr" | "en";
};

function roleLabel(role: string, english: boolean): string {
  if (role === "client") return english ? "Client" : "Client";
  if (role === "prof") return english ? "Teacher" : "Professeur";
  if (role === "admin") return english ? "Admin" : "Administrateur";
  return role;
}

function pageLabel(path: string | null, english: boolean): string {
  if (!path) return english ? "Page not reported" : "Page non remontée";
  const pathname = path.split("?")[0];
  if (pathname === "/admin") return english ? "Admin planning" : "Planning admin";
  if (pathname.startsWith("/admin/clients")) return english ? "Clients" : "Clients";
  if (pathname.startsWith("/admin/config/formulas")) return english ? "Formulas" : "Formules";
  if (pathname.startsWith("/admin/config")) return english ? "Configuration" : "Configuration";
  if (pathname === "/dashboard" || pathname === "/client") return english ? "Client portal" : "Espace client";
  if (pathname.startsWith("/prof")) return english ? "Teacher portal" : "Espace professeur";
  if (pathname.startsWith("/embed/planning")) return english ? "Public planning" : "Planning public";
  return path;
}

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
      {summary?.online_users.length ? (
        <div className="online-presence-users">
          <h4>{english ? "People online" : "Personnes en ligne"}</h4>
          <div className="online-presence-users-table" role="table">
            {summary.online_users.map((user) => (
              <article key={user.user_id} className="online-presence-user" role="row">
                <div>
                  <strong>{user.display_name}</strong>
                  <span>{roleLabel(user.role, english)}</span>
                </div>
                <span className="online-presence-channel">
                  {user.channel === "MOBILE_APP" ? (english ? "Mobile app" : "Application") : (english ? "Website" : "Site internet")}
                </span>
                <div className="online-presence-page">
                  <strong>{pageLabel(user.current_path, english)}</strong>
                  {user.current_path ? <code>{user.current_path}</code> : null}
                </div>
                <time dateTime={user.last_seen_at}>
                  {new Date(user.last_seen_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </time>
              </article>
            ))}
          </div>
        </div>
      ) : summary ? (
        <p className="muted online-presence-empty">
          {english ? "No other user is online right now." : "Aucun autre utilisateur n’est en ligne actuellement."}
        </p>
      ) : null}
      {summary ? (
        <small className="muted">
          {english ? "Updated" : "Mis à jour"} {new Date(summary.generated_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </small>
      ) : null}
    </section>
  );
}
