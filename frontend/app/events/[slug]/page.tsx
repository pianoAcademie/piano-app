import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";

import {
  registerSchoolEventAction,
  startSchoolEventPaymentAction,
} from "../../../lib/actions";
import { getPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type {
  ClientFamilyOverviewOut,
  FamilyMemberOut,
  SchoolEventOut,
  SchoolEventRegistrationOut,
} from "../../../lib/types";
import styles from "../events.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function memberName(member: FamilyMemberOut): string {
  return [member.first_name, member.last_name].filter(Boolean).join(" ") || member.email || "Membre de la famille";
}

type Language = "fr" | "en";

function formatDate(value: string, timezoneName: string, language: Language): string {
  return new Date(value).toLocaleString(language === "en" ? "en-GB" : "fr-FR", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: timezoneName,
  });
}

export default async function EventDetailPage({
  params,
  searchParams = {},
}: {
  params: { slug: string };
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
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
  let event: SchoolEventOut | null = null;
  if (token) {
    const eventsResult = await backendRequest<SchoolEventOut[]>("/api/v1/clients/me/events", {}, token);
    event = eventsResult.ok ? eventsResult.data.find((item) => item.slug === params.slug) ?? null : null;
  } else {
    const eventResult = await backendRequest<SchoolEventOut>(`/api/v1/events/${encodeURIComponent(params.slug)}`);
    event = eventResult.ok ? eventResult.data : null;
  }
  if (!event) notFound();

  const [familyResult, registrationsResult] = token
    ? await Promise.all([
        backendRequest<ClientFamilyOverviewOut>("/api/v1/clients/me/family", {}, token),
        backendRequest<SchoolEventRegistrationOut[]>("/api/v1/clients/me/event-registrations", {}, token),
      ])
    : [null, null];
  const family = familyResult?.ok ? familyResult.data : null;
  const registrations = registrationsResult?.ok ? registrationsResult.data : [];
  const participants = family
    ? [
        family.me,
        ...family.links_as_adult.map((link) => link.child),
      ].filter((member, index, rows) => rows.findIndex((candidate) => candidate.id === member.id) === index && member.is_active)
    : [];
  const existingSlotIds = new Set(
    registrations
      .filter((registration) =>
        registration.event_id === event.id
        && (
          ["CONFIRMED", "WAITLISTED"].includes(registration.status)
          || (
            registration.status === "PENDING_PAYMENT"
            && (
              !registration.payment_hold_expires_at
              || new Date(registration.payment_hold_expires_at).getTime() > Date.now()
            )
          )
        )
      )
      .map((registration) => registration.slot_id),
  );
  const pendingBySlot = new Map(
    registrations
      .filter((registration) =>
        registration.event_id === event.id
        && registration.status === "PENDING_PAYMENT"
        && (
          !registration.payment_hold_expires_at
          || new Date(registration.payment_hold_expires_at).getTime() > Date.now()
        )
      )
      .map((registration) => [registration.slot_id, registration]),
  );
  const slots = event.slots.filter((slot) => slot.status === "SCHEDULED" && new Date(slot.start_at_utc).getTime() > Date.now());
  const paymentReturn = param(searchParams, "payment_return");
  const ok = param(searchParams, "ok") || (
    paymentReturn === "success"
      ? text(
          "Paiement reçu. Votre confirmation apparaîtra dès sa validation.",
          "Payment received. Your confirmation will appear as soon as it is validated.",
        )
      : ""
  );
  const error = param(searchParams, "error") || (
    paymentReturn === "cancel"
      ? text(
          "Paiement interrompu. Votre place reste réservée temporairement et vous pouvez réessayer.",
          "Payment interrupted. Your place remains temporarily reserved and you can try again.",
        )
      : ""
  );

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href={withLanguage("/events")}>Piano Académie · {text("Événements", "Events")}</Link>
        <div className={styles.headerActions}>
          <Link href={withLanguage("/events")}>{text("Tous les événements", "All events")}</Link>
          {token ? <Link href="/dashboard">{text("Mon compte", "My account")}</Link> : null}
        </div>
      </header>
      <div className={styles.shell}>
        <section className={styles.detailHero}>
          <div className={styles.detailTitle}>
            <span className={styles.eyebrow}>{event.category.replaceAll("_", " ")}</span>
            <h1>{language === "en" && event.title_en ? event.title_en : event.title_fr}</h1>
            <p>{(language === "en" ? event.description_en : event.description_fr) || text(
              "Choisissez le créneau qui vous convient et réservez votre place.",
              "Choose the time that suits you and book your place.",
            )}</p>
            <p><strong>{Number(event.price_ttc) > 0
              ? `${Number(event.price_ttc).toFixed(2)} € ${text("par personne", "per person")}`
              : text("Événement gratuit", "Free event")}</strong></p>
          </div>
          {event.image_url ? (
            <img className={styles.detailImage} src={event.image_url} alt="" />
          ) : (
            <div className={`${styles.detailImage} ${styles.cardImageFallback}`} aria-hidden="true">♪</div>
          )}
        </section>

        {ok ? <p className="notice success">{ok}</p> : null}
        {error ? <p className="notice error">{error}</p> : null}

        <section className={styles.panel}>
          <h2>{text("Choisir un créneau", "Choose a time")}</h2>
          <p className="muted">{text(
            "Les places affichées sont mises à jour lors de chaque inscription.",
            "Availability is updated after every registration.",
          )}</p>
          <div className={styles.slots}>
            {slots.map((slot) => {
              const isFull = slot.seats_remaining <= 0;
              const alreadyRegistered = existingSlotIds.has(slot.id);
              const hasPendingPayment = pendingBySlot.has(slot.id);
              return (
                <article className={styles.slot} key={slot.id}>
                  <div className={styles.slotHeader}>
                    <div>
                      <h3>{slot.label || formatDate(slot.start_at_utc, slot.timezone, language)}</h3>
                      {slot.label ? <p>{formatDate(slot.start_at_utc, slot.timezone, language)}</p> : null}
                      <p className="muted">{slot.location?.name ?? event.location?.name ?? text("Lieu communiqué prochainement", "Location to be confirmed")}</p>
                      <p className="muted">
                        {text("Capacité officielle", "Official capacity")} : {slot.capacity_max} {text("personne(s)", "people")}
                      </p>
                    </div>
                    <span className={`${styles.badge} ${isFull && !hasPendingPayment ? styles.waitlist : ""}`}>
                      {hasPendingPayment
                        ? text("Place réservée", "Place reserved")
                        : isFull
                        ? event.waitlist_enabled ? text("Liste d’attente ouverte", "Waiting list open") : text("Complet", "Full")
                        : `${slot.seats_remaining} ${text("place(s)", "place(s)")}`}
                    </span>
                  </div>

                  {alreadyRegistered ? (
                    hasPendingPayment ? (
                      <div className={styles.pendingPayment}>
                        <p className="notice">{text(
                          "Votre place est réservée temporairement. Finalisez le paiement pour confirmer l’inscription.",
                          "Your place is temporarily reserved. Complete payment to confirm the registration.",
                        )}</p>
                        <form action={startSchoolEventPaymentAction}>
                          <input type="hidden" name="group_id" value={pendingBySlot.get(slot.id)?.group_id} />
                          <input type="hidden" name="event_slug" value={event.slug} />
                          <input type="hidden" name="return_to" value={withLanguage(`/events/${event.slug}`)} />
                          <button className="primary" type="submit">{text("Finaliser le paiement", "Complete payment")}</button>
                        </form>
                      </div>
                    ) : (
                      <p className="notice success">{text(
                        "Votre famille possède déjà une inscription sur ce créneau.",
                        "Your family already has a registration for this time.",
                      )}</p>
                    )
                  ) : token && family ? (
                    <form action={registerSchoolEventAction} className={styles.registerForm}>
                      <input type="hidden" name="event_slug" value={event.slug} />
                      <input type="hidden" name="slot_id" value={slot.id} />
                      <input type="hidden" name="return_to" value={withLanguage(`/events/${event.slug}`)} />
                      <input type="hidden" name="ui_language" value={language} />
                      <fieldset>
                        <legend><strong>{text("Qui participe ?", "Who is attending?")}</strong></legend>
                        <div className={styles.participants}>
                          {participants.map((participant, index) => (
                            <label className={styles.participant} key={participant.id}>
                              <input
                                type="checkbox"
                                name="participant_user_ids"
                                value={participant.id}
                                defaultChecked={participants.length === 1 || index === 0}
                              />
                              <span>{memberName(participant)}</span>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                      {event.registration_mode === "GROUP_SESSION" ? (
                        <label className={styles.field}>
                          <span>{text("Invités supplémentaires (un nom par ligne)", "Additional guests (one name per line)")}</span>
                          <textarea name="guest_names" rows={2} placeholder={text("Prénom Nom", "First name Last name")} />
                        </label>
                      ) : null}
                      {event.collect_piece_info ? (
                        <label className={styles.field}>
                          <span>{text("Pièce interprétée", "Piece performed")}</span>
                          <input name="piece_info" placeholder={text("Compositeur et titre", "Composer and title")} />
                        </label>
                      ) : null}
                      {event.collect_photo_consent ? (
                        <label className={styles.participant}>
                          <input type="checkbox" name="photo_consent" />
                          <span>{text(
                            "J’autorise l’utilisation des photos prises pendant cet événement.",
                            "I authorise the use of photographs taken during this event.",
                          )}</span>
                        </label>
                      ) : null}
                      <button className="primary" type="submit" disabled={isFull && !event.waitlist_enabled}>
                        {isFull
                          ? text("Rejoindre la liste d’attente", "Join the waiting list")
                          : event.payment_mode === "ON_SITE" && Number(event.price_ttc) > 0
                            ? text("Réserver — paiement sur place", "Book — pay on site")
                            : event.payment_mode === "ONLINE" && Number(event.price_ttc) > 0
                              ? text("Réserver et payer en ligne", "Book and pay online")
                            : text("Confirmer l’inscription", "Confirm registration")}
                      </button>
                    </form>
                  ) : (
                    <Link className={styles.loginCta} href={withLanguage(`/login?return_to=${encodeURIComponent(withLanguage(`/events/${event.slug}`))}`)}>
                      {text("Se connecter pour réserver", "Sign in to book")}
                    </Link>
                  )}
                </article>
              );
            })}
            {!slots.length ? <div className={styles.empty}>{text("Aucun créneau ouvert actuellement.", "No times are currently open.")}</div> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
