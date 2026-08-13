"use client";

import Link from "next/link";
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

function channelLabel(channel: AdminOnlinePresenceOut["online_users"][number]["channel"], english: boolean): string {
  if (channel === "NATIVE_APP") return english ? "Native iOS app" : "App iOS native";
  if (channel === "INSTALLED_WEB") return english ? "Installed website" : "Site installé";
  if (channel === "WEB_MOBILE") return english ? "Mobile website" : "Site web mobile";
  if (channel === "WEB_DESKTOP") return english ? "Desktop website" : "Site web ordinateur";
  if (channel === "MOBILE_APP") return english ? "Legacy app/PWA" : "Ancien classement app/site installé";
  return english ? "Legacy website" : "Ancien classement site web";
}

function pageLabel(path: string | null, english: boolean): string {
  if (!path) return english ? "Page not reported" : "Page non remontée";
  const pathname = path.split("?")[0];
  const parameters = new URLSearchParams(path.includes("?") ? path.split("?")[1] : "");
  if (pathname === "/admin") return english ? "Admin planning" : "Planning admin";
  if (pathname.startsWith("/admin/clients")) return english ? "Clients" : "Clients";
  if (pathname.startsWith("/admin/config/formulas")) return english ? "Formulas" : "Formules";
  if (pathname.startsWith("/admin/config")) return english ? "Configuration" : "Configuration";
  if (pathname === "/dashboard" || pathname === "/client") {
    const tab = parameters.get("tab");
    if (tab === "planning") return english ? "Client planning" : "Planning client";
    if (tab === "bookings") return english ? "Client bookings" : "Réservations client";
    if (tab === "offers") return english ? "Offers" : "Offres";
    if (tab === "news") return english ? "News" : "Actualités";
    return english ? "Client portal" : "Espace client";
  }
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
    { label: english ? "Desktop website" : "Web ordinateur", value: summary?.web_desktop ?? "–" },
    { label: english ? "Mobile website" : "Web mobile", value: summary?.web_mobile ?? "–" },
    { label: english ? "Installed website" : "Site installé", value: summary?.installed_web ?? "–" },
    { label: english ? "Native iOS app" : "App iOS native", value: summary?.native_app ?? "–" },
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
                  {channelLabel(user.channel, english)}
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
        <div className="row spread top-gap-sm">
          <small className="muted">
            {english ? "Updated" : "Mis à jour"} {new Date(summary.generated_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </small>
          <Link className="ghost" href={english ? "/admin/realtime?lang=en" : "/admin/realtime"}>
            {english ? "Open detailed view" : "Ouvrir la vue détaillée"}
          </Link>
        </div>
      ) : null}
    </section>
  );
}
