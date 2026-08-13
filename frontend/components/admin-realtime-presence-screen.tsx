"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { AdminDailyPresenceUserOut, AdminOnlinePresenceOut, AdminOnlinePresenceUserOut } from "../lib/types";

type Props = {
  language: "fr" | "en";
};

type RoleFilter = "ALL" | "client" | "prof" | "admin";
type PresenceChannel = AdminOnlinePresenceUserOut["channel"];
type ChannelFilter = "ALL" | PresenceChannel;

function channelLabel(channel: PresenceChannel, english: boolean): string {
  if (channel === "NATIVE_APP") return english ? "Native iOS app" : "App iOS native";
  if (channel === "INSTALLED_WEB") return english ? "Installed website" : "Site installé";
  if (channel === "WEB_MOBILE") return english ? "Mobile website" : "Site web mobile";
  if (channel === "WEB_DESKTOP") return english ? "Desktop website" : "Site web ordinateur";
  if (channel === "MOBILE_APP") return english ? "Legacy app/PWA" : "Ancien classement app/site installé";
  return english ? "Legacy website" : "Ancien classement site web";
}

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
  if (origin === "NATIVE_APP") return english ? "Native application" : "Application native";
  if (origin === "INSTALLED_WEB") return english ? "Installed website" : "Site installé";
  if (origin === "APP") return english ? "Legacy app/PWA" : "Ancien classement app/site installé";
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

function deviceLabel(device: string | null, channel: PresenceChannel, english: boolean): string {
  if (device === "APP" && channel === "MOBILE_APP") {
    return english ? "Legacy device (undetermined)" : "Ancien appareil (indéterminé)";
  }
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

function searchableDailyVisitor(visitor: AdminDailyPresenceUserOut): string {
  return [visitor.display_name, visitor.role, ...visitor.channels, ...visitor.active_hour_labels]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
}

export default function AdminRealtimePresenceScreen({ language }: Props): JSX.Element {
  const english = language === "en";
  const [summary, setSummary] = useState<AdminOnlinePresenceOut | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<RoleFilter>("ALL");
  const [channel, setChannel] = useState<ChannelFilter>("ALL");
  const [dailySearch, setDailySearch] = useState("");
  const [dailyRole, setDailyRole] = useState<RoleFilter>("ALL");
  const [dailyChannel, setDailyChannel] = useState<ChannelFilter>("ALL");

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

  const filteredDailyVisitors = useMemo(() => {
    const query = dailySearch.trim().toLocaleLowerCase();
    return (summary?.daily_visitors ?? []).filter((visitor) => (
      (dailyRole === "ALL" || visitor.role === dailyRole)
      && (dailyChannel === "ALL" || visitor.channels.includes(dailyChannel))
      && (!query || searchableDailyVisitor(visitor).includes(query))
    ));
  }, [dailyChannel, dailyRole, dailySearch, summary]);

  const metrics = [
    { label: english ? "Online now" : "En ligne maintenant", value: summary?.total ?? "–", primary: true },
    { label: english ? "Desktop website" : "Web ordinateur", value: summary?.web_desktop ?? "–" },
    { label: english ? "Mobile website" : "Web mobile", value: summary?.web_mobile ?? "–" },
    { label: english ? "Installed website" : "Site installé", value: summary?.installed_web ?? "–" },
    { label: english ? "Native iOS app" : "App iOS native", value: summary?.native_app ?? "–" },
    { label: english ? "Legacy unclassified" : "Historique indéterminé", value: summary?.legacy_unclassified ?? "–" },
    { label: english ? "Clients" : "Clients", value: summary?.clients ?? "–" },
    { label: english ? "Teachers" : "Professeurs", value: summary?.professors ?? "–" },
    { label: english ? "Admins" : "Administrateurs", value: summary?.admins ?? "–" },
  ];
  const hourlyHistory = summary?.hourly_history ?? [];
  const historyMaximum = Math.max(1, ...hourlyHistory.map((bucket) => bucket.total));
  const historyPeak = Math.max(0, ...hourlyHistory.map((bucket) => bucket.total));
  const nowTimestamp = summary ? new Date(summary.generated_at).getTime() : Date.now();

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

      <article className="card realtime-presence-history-card">
        <div className="row spread realtime-presence-history-heading">
          <div>
            <h2>{english ? "Today’s connection history" : "Historique des connexions aujourd’hui"}</h2>
            <p className="muted">
              {english
              ? "Unique active users per hour. Hover or focus a bar for the detailed access channel."
              : "Utilisateurs uniques actifs par heure. Survolez une barre pour le détail du canal d’accès."}
            </p>
          </div>
          <div className="realtime-presence-history-peak">
            <span>{english ? "Daily peak" : "Pic de la journée"}</span>
            <strong>{historyPeak}</strong>
          </div>
        </div>

        {hourlyHistory.length ? (
          <div className="realtime-presence-histogram-scroll">
            <div
              className="realtime-presence-histogram"
              role="group"
              aria-label={english ? "Hourly histogram of unique active users today" : "Histogramme horaire des utilisateurs uniques actifs aujourd’hui"}
            >
              {hourlyHistory.map((bucket, index) => {
                const bucketStart = new Date(bucket.hour_started_at).getTime();
                const isCurrentHour = nowTimestamp >= bucketStart && nowTimestamp < bucketStart + 3_600_000;
                const details = english
                  ? `${bucket.hour_label}: ${bucket.total} unique user(s), ${bucket.web_desktop} desktop web, ${bucket.web_mobile} mobile web, ${bucket.installed_web} installed web, ${bucket.native_app} native app, ${bucket.legacy_unclassified} legacy unclassified`
                  : `${bucket.hour_label} : ${bucket.total} utilisateur(s) unique(s), ${bucket.web_desktop} web ordinateur, ${bucket.web_mobile} web mobile, ${bucket.installed_web} site installé, ${bucket.native_app} app native, ${bucket.legacy_unclassified} historique indéterminé`;
                const showLabel = index % 2 === 0 || index === hourlyHistory.length - 1;
                return (
                  <div key={bucket.hour_started_at} className={`realtime-presence-hour ${isCurrentHour ? "is-current" : ""}`}>
                    <span className="realtime-presence-hour-value" aria-hidden="true">{bucket.total || ""}</span>
                    <span className="realtime-presence-hour-track" title={details} tabIndex={0} aria-label={details}>
                      <span
                        className={`realtime-presence-hour-bar ${bucket.total ? "has-value" : ""}`}
                        style={{ height: bucket.total ? `${Math.max(8, (bucket.total / historyMaximum) * 100)}%` : "2px" }}
                      />
                    </span>
                    <span className="realtime-presence-hour-label" aria-hidden="true">{showLabel ? bucket.hour_label.slice(0, 2) : ""}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="muted realtime-presence-empty">{english ? "Connection history is loading…" : "Chargement de l’historique des connexions…"}</p>
        )}
        <div className="realtime-presence-history-footer">
          <span><i aria-hidden="true" />{english ? "Unique active users" : "Utilisateurs uniques actifs"}</span>
          <small className="muted">
            {english
              ? `Time zone: ${summary?.history_timezone ?? "Europe/Paris"}. History is collected from feature activation.`
              : `Fuseau : ${summary?.history_timezone ?? "Europe/Paris"}. L’historique est collecté depuis l’activation de cette fonctionnalité.`}
          </small>
        </div>
      </article>

      <article className="card realtime-presence-list-card realtime-presence-daily-card">
        <div className="row spread realtime-presence-toolbar-heading">
          <div>
            <h2>{english ? "Today’s visitors" : "Visiteurs aujourd’hui"}</h2>
            <p className="muted">
              {english
                ? "People who used a browser, an installed website, or the native app since midnight. Your own admin session is excluded."
                : "Personnes ayant utilisé le site web, le site installé ou l’app native depuis minuit. Votre propre session admin est exclue."}
            </p>
          </div>
          <span className="realtime-presence-visitor-count">
            <strong>{summary ? (summary.daily_visitors ?? []).length : "–"}</strong>
            {english ? " unique visitor(s)" : " visiteur(s) unique(s)"}
          </span>
        </div>

        <div className="realtime-presence-filters">
          <label>
            <span>{english ? "Search" : "Recherche"}</span>
            <input value={dailySearch} onChange={(event) => setDailySearch(event.target.value)} placeholder={english ? "Name or active hour…" : "Nom ou heure d’activité…"} />
          </label>
          <label>
            <span>{english ? "Profile" : "Profil"}</span>
            <select value={dailyRole} onChange={(event) => setDailyRole(event.target.value as RoleFilter)}>
              <option value="ALL">{english ? "All profiles" : "Tous les profils"}</option>
              <option value="client">{english ? "Clients" : "Clients"}</option>
              <option value="prof">{english ? "Teachers" : "Professeurs"}</option>
              <option value="admin">{english ? "Admins" : "Administrateurs"}</option>
            </select>
          </label>
          <label>
            <span>{english ? "Channel" : "Canal"}</span>
            <select value={dailyChannel} onChange={(event) => setDailyChannel(event.target.value as ChannelFilter)}>
              <option value="ALL">{english ? "All channels" : "Tous les canaux"}</option>
              <option value="WEB_DESKTOP">{channelLabel("WEB_DESKTOP", english)}</option>
              <option value="WEB_MOBILE">{channelLabel("WEB_MOBILE", english)}</option>
              <option value="INSTALLED_WEB">{channelLabel("INSTALLED_WEB", english)}</option>
              <option value="NATIVE_APP">{channelLabel("NATIVE_APP", english)}</option>
              <option value="WEB">{channelLabel("WEB", english)}</option>
              <option value="MOBILE_APP">{channelLabel("MOBILE_APP", english)}</option>
            </select>
          </label>
        </div>

        {filteredDailyVisitors.length ? (
          <div className="realtime-presence-table-wrap">
            <table className="realtime-presence-table realtime-presence-daily-table">
              <thead>
                <tr>
                  <th>{english ? "Person" : "Personne"}</th>
                  <th>{english ? "Profile" : "Profil"}</th>
                  <th>{english ? "Channel" : "Canal"}</th>
                  <th>{english ? "First activity" : "Première activité"}</th>
                  <th>{english ? "Latest activity" : "Dernière activité"}</th>
                  <th>{english ? "Active hours" : "Heures actives"}</th>
                </tr>
              </thead>
              <tbody>
                {filteredDailyVisitors.map((visitor) => {
                  const profile = visitor.role === "client" ? (english ? `/admin/clients/${visitor.user_id}?lang=en` : `/admin/clients/${visitor.user_id}`) : null;
                  return (
                    <tr key={visitor.user_id}>
                      <td>{profile ? <Link href={profile}><strong>{visitor.display_name}</strong></Link> : <strong>{visitor.display_name}</strong>}</td>
                      <td>{roleLabel(visitor.role, english)}</td>
                      <td>
                        <span className="realtime-presence-channel-list">
                          {visitor.channels.map((visitorChannel) => (
                            <span key={visitorChannel} className="online-presence-channel">
                              {channelLabel(visitorChannel, english)}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td><time dateTime={visitor.first_seen_at}>{new Date(visitor.first_seen_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit" })}</time></td>
                      <td><time dateTime={visitor.last_seen_at}>{new Date(visitor.last_seen_at).toLocaleTimeString(english ? "en-GB" : "fr-FR", { hour: "2-digit", minute: "2-digit" })}</time></td>
                      <td><span className="realtime-presence-active-hours">{visitor.active_hour_labels.join(" · ")}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : summary ? (
          <p className="muted realtime-presence-empty">
            {dailySearch || dailyRole !== "ALL" || dailyChannel !== "ALL"
              ? (english ? "No visitor matches these filters." : "Aucun visiteur ne correspond à ces filtres.")
              : (english ? "No other visitor has used the app today." : "Aucun autre visiteur n’a utilisé l’application aujourd’hui.")}
          </p>
        ) : (
          <p className="muted realtime-presence-empty">{english ? "Loading today’s visitors…" : "Chargement des visiteurs du jour…"}</p>
        )}
      </article>

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
              <option value="WEB_DESKTOP">{channelLabel("WEB_DESKTOP", english)}</option>
              <option value="WEB_MOBILE">{channelLabel("WEB_MOBILE", english)}</option>
              <option value="INSTALLED_WEB">{channelLabel("INSTALLED_WEB", english)}</option>
              <option value="NATIVE_APP">{channelLabel("NATIVE_APP", english)}</option>
              <option value="WEB">{channelLabel("WEB", english)}</option>
              <option value="MOBILE_APP">{channelLabel("MOBILE_APP", english)}</option>
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
                          {channelLabel(user.channel, english)}
                        </span>
                        <span>{deviceLabel(user.device_type, user.channel, english)}</span>
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
