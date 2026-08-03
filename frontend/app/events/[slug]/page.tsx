import Link from "next/link";
import { randomUUID } from "crypto";
import { headers } from "next/headers";
import { notFound } from "next/navigation";

import {
  registerSchoolEventAction,
  registerPublicSchoolEventAction,
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
  const familyMembers = family
    ? [
        family.me,
        ...family.links_as_adult.map((link) => link.child),
      ].filter((member, index, rows) => rows.findIndex((candidate) => candidate.id === member.id) === index && member.is_active)
    : [];
  const participants = event.collect_performer_booking
    ? familyMembers.filter((member) => member.client_kind === "CHILD")
    : familyMembers;
  const previousBookingSlotIds = new Set(
    registrations
      .filter((registration) =>
        registration.event_id === event.id
        && ["CONFIRMED", "WAITLISTED"].includes(registration.status)
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
            {event.price_tiers.length ? (
              <div>
                <strong>{text("Tarifs proposés", "Available prices")}</strong>
                <ul>
                  {event.price_tiers.map((tier) => (
                    <li key={tier.id}>{language === "en" && tier.label_en ? tier.label_en : tier.label_fr} : {Number(tier.price_ttc).toFixed(2)} €</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p><strong>{Number(event.price_ttc) > 0
                ? `${Number(event.price_ttc).toFixed(2)} € ${text("par personne", "per person")}`
                : text("Événement gratuit", "Free event")}</strong></p>
            )}
          </div>
          {event.image_url ? (
            <img className={styles.detailImage} src={event.image_url} alt="" />
          ) : (
            <div className={`${styles.detailImage} ${styles.cardImageFallback}`} aria-hidden="true">♪</div>
          )}
        </section>

        {ok ? <p className="notice success">{ok}</p> : null}
        {error ? <p className="notice error">{error}</p> : null}

        {!token ? (
          <section className={styles.accountPrompt}>
            <div>
              <span className={styles.eyebrow}>{text("Déjà client de l’école ?", "Already a school client?")}</span>
              <h2>{text("Connectez-vous avant de réserver", "Sign in before booking")}</h2>
              <p>{text(
                "Vous pourrez sélectionner un ou plusieurs de vos enfants depuis votre dossier famille, puis ajouter les accompagnants éventuels.",
                "You can select one or more children from your family account, then add any accompanying guests.",
              )}</p>
            </div>
            <Link
              className={styles.loginCta}
              href={withLanguage(`/login?mode=login&return_to=${encodeURIComponent(withLanguage(`/events/${event.slug}`))}`)}
            >
              {text("Se connecter et choisir mes enfants", "Sign in and choose my children")}
            </Link>
            <small>{text(
              "Vous n’avez pas de compte client ? La réservation sans compte reste disponible ci-dessous.",
              "No client account? Guest booking remains available below.",
            )}</small>
          </section>
        ) : null}

        <section className={styles.panel}>
          <h2>{text("Choisir un créneau", "Choose a time")}</h2>
          <p className="muted">{text(
            event.show_remaining_seats
              ? "Les places restantes sont mises à jour lors de chaque inscription."
              : "La disponibilité est mise à jour lors de chaque inscription.",
            event.show_remaining_seats
              ? "Remaining places are updated after every registration."
              : "Availability is updated after every registration.",
          )}</p>
          <div className={styles.slots}>
            {slots.map((slot) => {
              const isFull = slot.seats_remaining <= 0;
              const publicPaidOnline = event.payment_mode === "ONLINE"
                && (event.price_tiers.some((tier) => Number(tier.price_ttc) > 0) || Number(event.price_ttc) > 0);
              const hasPendingPayment = pendingBySlot.has(slot.id);
              const hasPreviousBooking = previousBookingSlotIds.has(slot.id);
              const alreadyRegistered = hasPendingPayment;
              return (
                <article className={styles.slot} key={slot.id}>
                  <div className={styles.slotHeader}>
                    <div>
                      <h3>{slot.label || formatDate(slot.start_at_utc, slot.timezone, language)}</h3>
                      {slot.label ? <p>{formatDate(slot.start_at_utc, slot.timezone, language)}</p> : null}
                      <p className="muted">
                        {slot.location?.name ?? event.location?.name ?? text("Lieu communiqué prochainement", "Location to be confirmed")}
                        {(slot.location ?? event.location)?.address_line ? ` · ${(slot.location ?? event.location)?.address_line}` : ""}
                        {(slot.location ?? event.location)?.city ? `, ${(slot.location ?? event.location)?.postal_code ?? ""} ${(slot.location ?? event.location)?.city}` : ""}
                      </p>
                    </div>
                    <span className={`${styles.badge} ${isFull && !hasPendingPayment ? styles.waitlist : ""}`}>
                      {hasPendingPayment
                        ? text("Place réservée", "Place reserved")
                        : isFull
                        ? event.waitlist_enabled ? text("Liste d’attente ouverte", "Waiting list open") : text("Complet", "Full")
                        : event.show_remaining_seats
                          ? `${slot.seats_remaining} ${text("place(s) restante(s)", "place(s) remaining")}`
                          : text("Places disponibles", "Places available")}
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
                      {hasPreviousBooking ? (
                        <p className="notice success">{text(
                          "Une réservation existe déjà. Pour acheter des places supplémentaires, ne resélectionnez pas l’enfant et renseignez seulement les nouveaux accompagnants.",
                          "A booking already exists. To buy additional tickets, leave the child unchecked and enter only the new guests.",
                        )}</p>
                      ) : null}
                      <div className={styles.connectedBookingIntro}>
                        <strong>{text("Réservation depuis votre compte famille", "Booking from your family account")}</strong>
                        <span>{text(
                          event.collect_performer_booking
                            ? "Sélectionnez le ou les enfants qui participent au concert, puis ajoutez les accompagnants."
                            : "Sélectionnez les membres de votre famille présents, puis ajoutez éventuellement d’autres accompagnants.",
                          event.collect_performer_booking
                            ? "Select the child or children performing in the concert, then add accompanying guests."
                            : "Select the family members attending, then add any other guests.",
                        )}</span>
                      </div>
                      <fieldset>
                        <legend><strong>{text(
                          event.collect_performer_booking ? "Enfant(s) participant(s)" : "Membres de la famille présents",
                          event.collect_performer_booking ? "Participating child(ren)" : "Family members attending",
                        )}</strong></legend>
                        <div className={styles.participants}>
                          {participants.map((participant) => (
                            <div className={styles.participant} key={participant.id}>
                              <input
                                id={`participant_${participant.id}`}
                                type="checkbox"
                                name="participant_user_ids"
                                value={participant.id}
                                defaultChecked={!hasPreviousBooking && participants.length === 1}
                              />
                              <label htmlFor={`participant_${participant.id}`}>{memberName(participant)}</label>
                              {event.price_tiers.length ? (
                                <select name={`price_tier_id_${participant.id}`} defaultValue="" aria-label={text("Tarif du participant", "Participant price")}>
                                  <option value="" disabled>{text("Choisir son tarif", "Choose their price")}</option>
                                  {event.price_tiers.map((tier) => (
                                    <option value={tier.id} key={tier.id}>
                                      {language === "en" && tier.label_en ? tier.label_en : tier.label_fr} — {Number(tier.price_ttc).toFixed(2)} €
                                    </option>
                                  ))}
                                </select>
                              ) : null}
                            </div>
                          ))}
                          {!participants.length ? (
                            <p className="muted">{text(
                              event.collect_performer_booking
                                ? "Aucun enfant actif n’est rattaché à ce compte. Vous pouvez poursuivre avec les accompagnants ou demander la mise à jour de votre dossier famille."
                                : "Aucun membre actif n’est disponible dans ce dossier famille.",
                              event.collect_performer_booking
                                ? "No active child is linked to this account. You can continue with guests or ask us to update your family account."
                                : "No active member is available in this family account.",
                            )}</p>
                          ) : null}
                        </div>
                      </fieldset>
                      {event.registration_mode === "GROUP_SESSION" ? (
                        <fieldset>
                          <legend><strong>{text("Accompagnants", "Accompanying guests")}</strong></legend>
                          <p className="muted">{text(
                            "Ajoutez uniquement les places supplémentaires nécessaires. Chaque accompagnant peut avoir son propre tarif.",
                            "Add only the extra tickets you need. Each guest may have a different price.",
                          )}</p>
                          <div className={styles.publicTickets}>
                            {Array.from({ length: Math.min(event.max_per_family, 10) }, (_, index) => (
                              <div className={styles.publicTicket} key={index}>
                                <label className={styles.field}>
                                  <span>{text(`Accompagnant ${index + 1}`, `Guest ${index + 1}`)}</span>
                                  <input name={`guest_name_${index}`} placeholder={text("Prénom Nom", "First name Last name")} />
                                </label>
                                {event.price_tiers.length ? (
                                  <label className={styles.field}>
                                    <span>{text("Tarif", "Price")}</span>
                                    <select name={`guest_price_tier_id_${index}`} defaultValue="">
                                      <option value="" disabled>{text("Choisir", "Choose")}</option>
                                      {event.price_tiers.map((tier) => (
                                        <option value={tier.id} key={tier.id}>
                                          {language === "en" && tier.label_en ? tier.label_en : tier.label_fr} — {Number(tier.price_ttc).toFixed(2)} €
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </fieldset>
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
                          : event.payment_mode === "ON_SITE" && (event.price_tiers.some((tier) => Number(tier.price_ttc) > 0) || Number(event.price_ttc) > 0)
                            ? text("Réserver — paiement sur place", "Book — pay on site")
                            : event.payment_mode === "ONLINE" && (event.price_tiers.some((tier) => Number(tier.price_ttc) > 0) || Number(event.price_ttc) > 0)
                              ? text("Réserver et payer en ligne", "Book and pay online")
                            : text("Confirmer l’inscription", "Confirm registration")}
                      </button>
                    </form>
                  ) : (
                    <form action={registerPublicSchoolEventAction} className={styles.registerForm}>
                      <input type="hidden" name="request_id" value={randomUUID()} />
                      <input type="hidden" name="event_slug" value={event.slug} />
                      <input type="hidden" name="slot_id" value={slot.id} />
                      <input type="hidden" name="return_to" value={withLanguage(`/events/${event.slug}`)} />
                      <input type="hidden" name="ui_language" value={language} />
                      <h3>{text("Réserver sans compte", "Book without an account")}</h3>
                      <div className={styles.publicContactGrid}>
                        <label className={styles.field}>
                          <span>{text("Votre prénom *", "Your first name *")}</span>
                          <input name="first_name" required autoComplete="given-name" />
                        </label>
                        <label className={styles.field}>
                          <span>{text("Votre nom *", "Your last name *")}</span>
                          <input name="last_name" required autoComplete="family-name" />
                        </label>
                        <label className={styles.field}>
                          <span>{text("Email de confirmation *", "Confirmation email *")}</span>
                          <input name="email" type="email" required autoComplete="email" />
                        </label>
                        <label className={styles.field}>
                          <span>{text("Téléphone", "Phone")}</span>
                          <input name="phone" type="tel" autoComplete="tel" />
                        </label>
                      </div>
                      <fieldset>
                        <legend><strong>{text("Billets", "Tickets")}</strong></legend>
                        <p className="muted">{text(
                          event.collect_performer_booking
                            ? "Première ligne : enfant qui joue. Ajoutez ensuite chaque accompagnant."
                            : "Ajoutez une ligne nominative pour chaque spectateur.",
                          event.collect_performer_booking
                            ? "First row: performing child. Then add each accompanying guest."
                            : "Add one named line for each audience member.",
                        )}</p>
                        <div className={styles.publicTickets}>
                          {Array.from({ length: Math.min(event.max_per_family, 10) }, (_, index) => (
                            <div className={styles.publicTicket} key={index}>
                              <label className={styles.field}>
                                <span>{event.collect_performer_booking
                                  ? index === 0
                                    ? text("Enfant qui joue *", "Performing child *")
                                    : text(`Accompagnant ${index}`, `Guest ${index}`)
                                  : text(`Spectateur ${index + 1}${index === 0 ? " *" : ""}`, `Audience member ${index + 1}${index === 0 ? " *" : ""}`)}</span>
                                <input name={`ticket_name_${index}`} required={index === 0} placeholder={text("Prénom Nom", "First name Last name")} />
                              </label>
                              {event.price_tiers.length ? (
                                <label className={styles.field}>
                                  <span>{text("Tarif", "Price")}{index === 0 ? " *" : ""}</span>
                                  <select name={`ticket_price_tier_id_${index}`} required={index === 0} defaultValue="">
                                    <option value="" disabled>{text("Choisir", "Choose")}</option>
                                    {event.price_tiers.map((tier) => (
                                      <option value={tier.id} key={tier.id}>
                                        {language === "en" && tier.label_en ? tier.label_en : tier.label_fr} — {Number(tier.price_ttc).toFixed(2)} €
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </fieldset>
                      <label className={styles.participant}>
                        <input type="checkbox" name="terms_accepted" required />
                        <span>{text(
                          "J’accepte que mes informations soient utilisées pour gérer cette réservation.",
                          "I agree that my information may be used to manage this booking.",
                        )}</span>
                      </label>
                      <label className={styles.honeypot} aria-hidden="true">
                        Website<input name="website" tabIndex={-1} autoComplete="off" />
                      </label>
                      <div className={styles.publicBookingActions}>
                        <button
                          className="primary"
                          type="submit"
                          disabled={isFull && (!event.waitlist_enabled || publicPaidOnline)}
                        >
                          {isFull
                            ? publicPaidOnline
                              ? text("Complet", "Sold out")
                              : text("Rejoindre la liste d’attente", "Join the waiting list")
                            : publicPaidOnline
                              ? text("Réserver et payer", "Book and pay")
                              : text("Confirmer la réservation", "Confirm booking")}
                        </button>
                        <Link href={withLanguage(`/login?return_to=${encodeURIComponent(withLanguage(`/events/${event.slug}`))}`)}>
                          {text("Déjà client ? Se connecter", "Already a client? Sign in")}
                        </Link>
                      </div>
                    </form>
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
