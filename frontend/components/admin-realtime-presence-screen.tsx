"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { AdminOnlinePresenceOut, AdminOnlinePresenceUserOut } from "../lib/types";

type Props = {
  language: "fr" | "en";
};

type RoleFilter = "ALL" | "client" | "prof" | "admin";
type ChannelFilter = "ALL" | "WEB" | "MOBILE_APP";

function roleLabel(role: string, english: boolean): string {
  if (role === "client") return english ? "Client" : "Client";
  if (role === "prof") return english ? "Teacher" : "Professeur";
  if (role === "admin") return english ? "Admin" : "Administrateur";
  return role;
}

function pageLabel(path: string | null, english: boolean): string {
  if (!path) return english ? "Page not reported" : "Page non remontée";
  const pathname = path.split("?")[0];
  const parameters = new URLSearchParams(path.includes("?") ? path.split("?")[1] : "");
  if (pathname === "/admin") return english ? "Admin planning" : "Planning admin";
  if (pathname.startsWith("/admin/realtime")) return english ? "Real-time statistics" : "Statistiques temps réel";
  if (pathname.startsWith("/admin/clients")) return english ? "Client management" : "Gestion des clients";
  if (pathname.startsWith("/admin/config")) return english ? "Configuration" : "Configuration";
  if (pathname === "/client" || pathname === "/dashboard") {
    const tab = parameters.get("tab");
    if (tab === "planning") return english ? "Client planning" : "Planning client";
    if (tab === "bookings") return english ? "Client bookings" : "Réservations client";
    if (tab === "offers") return english ? "Offers" : "Offres";
    if (tab === "news") return english ? "News" : "Actualités";
    if (tab === "messages") return english ? "Messages" : "Messages";
    return english ? "Client home" : "Accueil client";
  }
  if (pathname.startsWith("/client/bookings")) return english ? "Client bookings" : "Réservations client";
  if (pathname.startsWith("/client")) return english ? "Client portal" : "Espace client";
  if (pathname.startsWith("/prof")) return english ? "Teacher portal" : "Espace professeur";
  if (pathname.startsWith("/embed/planning")) return english ? "Public planning" : "Planning public";
  return pathname;
}

function originLabel(origin: string | null, english: boolean): string {
  if (!origin || origin === "DIRECT") return english ? "Direct access" : "Accès direct";
  if (origin === "APP") return english ? "Mobile application" : "Application mobile";
  if (origin.startsWith("CAMPAIGN:")) return `${english ? "Campaign" : "Campagne"} · ${origin.slice(9)}`;
  if (origin.startsWith("EXTERNAL:")) return `${english ? "External" : "Externe"} · ${origin.slice(9)}`;
  if (origin.startsWith("INTERNAL:")) return `${english ? "Internal navigation" : "Navigation interne"} · ${origin.slice(9)}`;
  return origin;
}

function actionLabel(action: string | null, english: boolean): string {
  if (!action || action === "PAGE_VIEW") return english ? "Page opened" : "Page ouverte";
  if (action.startsWith("NAVIGATION:")) return `${english ? "Navigation" : "Navigation"} · ${action.slice(11)}`;
  if (action.startsWith("ACTION:")) return `${english ? "Action" : "Action"} · ${action.slice(7)}`;
  return action;
}

function deviceLabel(device: string | null, english: boolean): string {
  if (device === "APP") return english ? "Native app" : "App native";
  if (device === "MOBILE") return english ? "Mobile browser" : "Navigateur mobile";
  if (device === "TABLET") return english ? "Tablet" : "Tablette";
  if (device === "DESKTOP") return english ? "Computer" : "Ordinateur";
  return english ? "Unknown device" : "Appareil inconnu";
}

function siteLabel(site: string | null, english: boolean): string | null {
  if (site === "PARIS") return "Paris";
  if (site === "BAR_LE_DUC") return "Bar-le-Duc";
  if (site === "ONLINE") return english ? "Online" : "En ligne";
  return site;
}

function searchableText(user: AdminOnlinePresenceUserOut): string {
  return [
    user.display_name,
    user.role,
    user.channel,
    user.current_path,
    user.origin,
    user.last_action,
    user.device_type,
    user.residence_country,
    user.student_site,
  ].filter(Boolean).join(" ").toLocaleLowerCase();
}

export default function AdminRealtimePresenceScreen({ language }: Props): JSX.Element {
  const english = language === "en";
  const [summary, setSummary] = useState<AdminOnlinePresenceOut | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<RoleFilter>("ALL");
  const [channel, setChannel] = useState<ChannelFilter>("ALL");

  useEffect(() => {
    let stopped = false;
    const refresh = async (): Promise<void> => {
      try {
        const response = await fetch("/api/admin/presence", { cache: "no-store" });
        if (!response.ok) throw new Error(`Presence ${response.status}`);
        const payload = (await response.json()) as AdminOnlinePresenceOut;
        if (!stopped) {
          setSummary(payload);
          setError("");
        }
      } catch {
        if (!stopped) setError(english ? "Live data is temporarily unavailable." : "Les données en direct sont temporairement indisponibles.");
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 5_000);
    return () => {
      stopped = true;
      window.clearInterval(interval);
    };
  }, [english]);

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (summary?.online_users ?? []).filter((user) => (
      (role === "ALL" || user.role === role)
      && (channel === "ALL" || user.channel === channel)
      && (!query || searchableText(user).includes(query))
    ));
  }, [channel, role, search, summary]);

  const metrics = [
    { label: english ? "Online now" : "En ligne maintenant", value: summary?.total ?? "–", primary: true },
    { label: english ? "Website" : "Site internet", value: summary?.web ?? "–" },
    { label: english ? "Mobile app" : "Application mobile", value: summary?.mobile_app ?? "–" },
    { label: english ? "Clients" : "Clients", value: summary?.clients ?? "–" },
    { label: english ? "Teachers" : "Professeurs", value: summary?.professors ?? "–" },
    { label: english ? "Admins" : "Administrateurs", value: summary?.admins ?? "–" },
  ];

  return (
    <section className="admin-page-grid realtime-presence-page" aria-live="polite">
      <article className="card realtime-presence-hero">
        <div>
          <p className="eyebrow">{english ? "LIVE ACTIVITY" : "ACTIVITÉ EN DIRECT"}</p>
          <h1>{english ? "Real-time users" : "Utilisateurs en temps réel"}</h1>
          <p className="muted">
            {english
              ? "See who is online, their current page, latest action and visit origin. Your own admin session is excluded."
              : "Visualisez qui est en ligne, la page consultée, la dernière action et l’origine de la visite. Votre propre session admin est exclue."}
          </p>
        </div>
        <span className={`online-presence-status ${error ? "is-unavailable" : ""}`}>
          <span aria-hidden="true" />
          {error ? (english ? "Unavailable" : "Indisponible") : (english ? "Live" : "En direct")}
        </span>
      </article>

      {error ? <section className="flash-err">{error}</section> : null}

      <div className="online-presence-metrics realtime-presence-metrics">
        {metrics.map((metric) => (
          <article key={metric.label} className={metric.primary ? "is-primary" : ""}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </div>

      <article className="card realtime-presence-list-card">
        <div className="row spread realtime-presence-toolbar-heading">
          <div>
            <h2>{english ? "People online" : "Personnes en ligne"}</h2>
            <p className="muted">
              {english ? "A person is online after activity within the last 90 seconds." : "Une personne est en ligne après une activité au cours des 90 dernières secondes."}
            </p>
          </div>
          {summary ? (
            <small className="muted">
              {english ? "Updated" : "Mis à jour"} {new Date(summary.generated_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </small>
          ) : null}
        </div>

        <div className="realtime-presence-filters">
          <label>
            <span>{english ? "Search" : "Recherche"}</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={english ? "Name, page, origin…" : "Nom, page, origine…"} />
          </label>
          <label>
            <span>{english ? "Profile" : "Profil"}</span>
            <select value={role} onChange={(event) => setRole(event.target.value as RoleFilter)}>
              <option value="ALL">{english ? "All profiles" : "Tous les profils"}</option>
              <option value="client">{english ? "Clients" : "Clients"}</option>
              <option value="prof">{english ? "Teachers" : "Professeurs"}</option>
              <option value="admin">{english ? "Admins" : "Administrateurs"}</option>
            </select>
          </label>
          <label>
            <span>{english ? "Channel" : "Canal"}</span>
            <select value={channel} onChange={(event) => setChannel(event.target.value as ChannelFilter)}>
              <option value="ALL">{english ? "All channels" : "Tous les canaux"}</option>
              <option value="WEB">{english ? "Website" : "Site internet"}</option>
              <option value="MOBILE_APP">{english ? "Mobile app" : "Application mobile"}</option>
            </select>
          </label>
        </div>

        {filteredUsers.length ? (
          <div className="realtime-presence-table-wrap">
            <table className="realtime-presence-table">
              <thead>
                <tr>
                  <th>{english ? "Person" : "Personne"}</th>
                  <th>{english ? "Channel / device" : "Canal / appareil"}</th>
                  <th>{english ? "Current page" : "Page actuelle"}</th>
                  <th>{english ? "Latest action" : "Dernière action"}</th>
                  <th>{english ? "Origin" : "Origine"}</th>
                  <th>{english ? "Location" : "Localisation"}</th>
                  <th>{english ? "Last activity" : "Dernière activité"}</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => {
                  const site = siteLabel(user.student_site, english);
                  const profile = user.role === "client" ? (english ? `/admin/clients/${user.user_id}?lang=en` : `/admin/clients/${user.user_id}`) : null;
                  return (
                    <tr key={user.user_id}>
                      <td>
                        {profile ? <Link href={profile}><strong>{user.display_name}</strong></Link> : <strong>{user.display_name}</strong>}
                        <span>{roleLabel(user.role, english)}</span>
                      </td>
                      <td>
                        <span className="online-presence-channel">
                          {user.channel === "MOBILE_APP" ? (english ? "App" : "Application") : (english ? "Website" : "Site")}
                        </span>
                        <span>{deviceLabel(user.device_type, english)}</span>
                      </td>
                      <td>
                        <strong>{pageLabel(user.current_path, english)}</strong>
                        {user.current_path ? <code>{user.current_path}</code> : null}
                      </td>
                      <td>{actionLabel(user.last_action, english)}</td>
                      <td>{originLabel(user.origin, english)}</td>
                      <td>
                        <span>{site ?? (english ? "Not provided" : "Non renseignée")}</span>
                        {user.residence_country ? <span>{user.residence_country}</span> : null}
                      </td>
                      <td>
                        <time dateTime={user.last_seen_at}>
                          {new Date(user.last_seen_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : summary ? (
          <p className="muted realtime-presence-empty">
            {search || role !== "ALL" || channel !== "ALL"
              ? (english ? "No online user matches these filters." : "Aucun utilisateur en ligne ne correspond à ces filtres.")
              : (english ? "No other user is online right now." : "Aucun autre utilisateur n’est en ligne actuellement.")}
          </p>
        ) : (
          <p className="muted realtime-presence-empty">{english ? "Loading live activity…" : "Chargement de l’activité en direct…"}</p>
        )}
      </article>
    </section>
  );
}
