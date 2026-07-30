import Link from "next/link";
import { headers } from "next/headers";

import { cancelSchoolEventRegistrationAction } from "../../lib/actions";
import { getPortalToken } from "../../lib/auth-cookies";
import { backendRequest } from "../../lib/backend";
import type {
  SchoolEventOut,
  SchoolEventRegistrationOut,
} from "../../lib/types";
import styles from "./events.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

type Language = "fr" | "en";

function eventDate(event: SchoolEventOut, language: Language): string {
  const slot = event.slots.find((item) => item.status === "SCHEDULED" && new Date(item.start_at_utc).getTime() > Date.now());
  if (!slot) return language === "en" ? "Dates coming soon" : "Dates à venir";
  return new Date(slot.start_at_utc).toLocaleDateString(language === "en" ? "en-GB" : "fr-FR", {
    dateStyle: "medium",
    timeZone: slot.timezone,
  });
}

function registrationStatus(value: string, language: Language): string {
  if (value === "WAITLISTED") return language === "en" ? "Waiting list" : "Liste d’attente";
  if (value === "CONFIRMED") return language === "en" ? "Confirmed" : "Confirmée";
  if (value === "ATTENDED") return language === "en" ? "Attendance recorded" : "Participation enregistrée";
  if (value === "NO_SHOW") return language === "en" ? "Absence recorded" : "Absence enregistrée";
  return value;
}

function formatRegistrationDate(registration: SchoolEventRegistrationOut, language: Language): string {
  return new Date(registration.start_at_utc).toLocaleString(language === "en" ? "en-GB" : "fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: registration.timezone,
  });
}

export default async function EventsPage({ searchParams = {} }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const requestedLanguage = param(searchParams, "lang").trim().toLowerCase();
  const language: Language =
    requestedLanguage === "en"
    || (!requestedLanguage && (headers().get("accept-language") ?? "").toLowerCase().startsWith("en"))
      ? "en"
      : "fr";
  const text = (fr: string, en: string): string => language === "en" ? en : fr;
  const withLanguage = (href: string): string => {
    if (language !== "en") return href;
    return `${href}${href.includes("?") ? "&" : "?"}lang=en`;
  };
  const token = getPortalToken();
  const eventsResult = token
    ? await backendRequest<SchoolEventOut[]>("/api/v1/clients/me/events", {}, token)
    : await backendRequest<SchoolEventOut[]>("/api/v1/events");
  const registrationsResult = token
    ? await backendRequest<SchoolEventRegistrationOut[]>("/api/v1/clients/me/event-registrations", {}, token)
    : null;
  const events = eventsResult.ok ? eventsResult.data : [];
  const registrations = registrationsResult?.ok ? registrationsResult.data : [];
  const category = param(searchParams, "category").trim().toUpperCase();
  const categories = Array.from(new Set(events.map((event) => event.category))).sort();
  const visibleEvents = category ? events.filter((event) => event.category === category) : events;
  const activeRegistrations = registrations.filter((registration) =>
    ["CONFIRMED", "WAITLISTED", "ATTENDED", "NO_SHOW"].includes(registration.status),
  );
  const groupedRegistrations = Array.from(
    activeRegistrations.reduce((groups, registration) => {
      const current = groups.get(registration.group_id) ?? [];
      current.push(registration);
      groups.set(registration.group_id, current);
      return groups;
    }, new Map<string, SchoolEventRegistrationOut[]>()),
  );
  const ok = param(searchParams, "ok");
  const error = param(searchParams, "error") || (!eventsResult.ok ? eventsResult.message : "");

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href={withLanguage("/events")}>Piano Académie · {text("Événements", "Events")}</Link>
        <div className={styles.headerActions}>
          {token
            ? <Link href="/dashboard">{text("Mon compte", "My account")}</Link>
            : <Link href={withLanguage("/login?return_to=%2Fevents")}>{text("Se connecter", "Sign in")}</Link>}
        </div>
      </header>
      <div className={styles.shell}>
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <small>{text("Agenda de l’école", "School events")}</small>
            <h1>{text("Réservez votre place", "Book your place")}</h1>
            <p>{text(
              "Concerts, cours de contrôle, masterclasses, ateliers et rendez-vous proposés par Piano Académie.",
              "Concerts, assessment classes, masterclasses, workshops and special events by Piano Académie.",
            )}</p>
          </div>
          <div className={styles.myBookings}>
            <span>{token ? text("Mes inscriptions", "My registrations") : text("Réservation simple", "Easy booking")}</span>
            <strong>{token ? groupedRegistrations.length : text("En quelques clics", "In a few clicks")}</strong>
            <p className="muted">{token
              ? text("Retrouvez ici les inscriptions de toute votre famille.", "Find all your family registrations here.")
              : text("Connectez-vous pour choisir les participants de votre famille.", "Sign in to choose participants from your family.")}</p>
          </div>
        </section>

        {ok ? <p className="notice success">{ok}</p> : null}
        {error ? <p className="notice error">{error}</p> : null}

        {groupedRegistrations.length ? (
          <section className={styles.panel}>
            <h2>{text("Mes inscriptions", "My registrations")}</h2>
            <div className={styles.bookings}>
              {groupedRegistrations.map(([groupId, rows]) => {
                const first = rows[0];
                const participantNames = rows.map((row) => row.participant_display_name).join(", ");
                return (
                  <article className={styles.booking} key={groupId}>
                    <div>
                      <strong>{language === "en" && first.event_title_en ? first.event_title_en : first.event_title_fr}</strong>
                      <p>{formatRegistrationDate(first, language)} · {first.location_name ?? text("Lieu à préciser", "Location to be confirmed")}</p>
                      <small className="muted">{participantNames}</small>
                    </div>
                    <span className={`${styles.badge} ${first.status === "WAITLISTED" ? styles.waitlist : ""}`}>
                      {registrationStatus(first.status, language)}
                    </span>
                    {["CONFIRMED", "WAITLISTED"].includes(first.status) ? (
                      <form action={cancelSchoolEventRegistrationAction}>
                        <input type="hidden" name="group_id" value={groupId} />
                        <input type="hidden" name="return_to" value={withLanguage("/events")} />
                        <input type="hidden" name="ui_language" value={language} />
                        <button className="ghost" type="submit">{text("Annuler", "Cancel")}</button>
                      </form>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}

        <nav className={styles.filters} aria-label="Catégories">
          <Link className={`${styles.filter} ${!category ? styles.filterActive : ""}`} href={withLanguage("/events")}>{text("Tout", "All")}</Link>
          {categories.map((item) => (
            <Link
              className={`${styles.filter} ${category === item ? styles.filterActive : ""}`}
              href={withLanguage(`/events?category=${encodeURIComponent(item)}`)}
              key={item}
            >
              {item.replaceAll("_", " ")}
            </Link>
          ))}
        </nav>

        <section className={styles.grid} aria-label="Événements disponibles">
          {visibleEvents.map((event) => (
            <Link className={styles.card} href={withLanguage(`/events/${event.slug}`)} key={event.id}>
              {event.image_url ? (
                <img className={styles.cardImage} src={event.image_url} alt="" />
              ) : (
                <div className={styles.cardImageFallback} aria-hidden="true">♪</div>
              )}
              <div className={styles.cardBody}>
                <span className={styles.eyebrow}>{event.category.replaceAll("_", " ")}</span>
                <h2>{language === "en" && event.title_en ? event.title_en : event.title_fr}</h2>
                <p>{(language === "en" ? event.description_en : event.description_fr) || text(
                  "Découvrez les créneaux proposés et réservez votre place.",
                  "View the available times and book your place.",
                )}</p>
              </div>
              <div className={styles.cardFooter}>
                <span>{eventDate(event, language)}</span>
                <span>{Number(event.price_ttc) > 0 ? `${Number(event.price_ttc).toFixed(2)} €` : text("Gratuit", "Free")}</span>
              </div>
            </Link>
          ))}
          {!visibleEvents.length ? <div className={styles.empty}>{text("Aucun événement ouvert pour le moment.", "No events are currently open.")}</div> : null}
        </section>
      </div>
    </main>
  );
}
