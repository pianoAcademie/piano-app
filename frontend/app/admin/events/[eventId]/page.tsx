import Link from "next/link";
import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import {
  createAdminSchoolEventRegistrationAction,
  createSchoolEventPriceTierAction,
  createSchoolEventSlotAction,
  deleteSchoolEventSlotAction,
  deleteSchoolEventPriceTierAction,
  duplicateSchoolEventAction,
  updateSchoolEventAction,
  uploadSchoolEventImageAction,
  updateSchoolEventRegistrationGroupStatusAction,
  updateSchoolEventSlotCapacitiesAction,
} from "../../../../lib/actions";
import { hasAdminPermission } from "../../../../lib/admin-access";
import { getAdminToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type {
  SchoolEventVenueOut,
  SchoolEventAdminParticipantOptionOut,
  SchoolEventOut,
  SchoolEventRegistrationOut,
  UserOut,
} from "../../../../lib/types";
import styles from "../events.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function dateTimeLocal(value: string | null, timezoneName = "Europe/Paris"): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: timezoneName,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function formatDate(value: string, timezoneName: string): string {
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: timezoneName,
  });
}

function registrationLabel(status: string): string {
  return {
    CONFIRMED: "Confirmée",
    WAITLISTED: "Liste d’attente",
    CANCELLED: "Annulée",
    ATTENDED: "Présent",
    NO_SHOW: "Absent",
    PENDING_PAYMENT: "Paiement en attente",
  }[status] ?? status;
}

export default async function AdminEventDetailPage({
  params,
  searchParams = {},
}: {
  params: { eventId: string };
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const [meResult, eventResult, registrationResult, venuesResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<SchoolEventOut>(`/api/v1/admin/events/${encodeURIComponent(params.eventId)}`, {}, token),
    backendRequest<SchoolEventRegistrationOut[]>(
      `/api/v1/admin/events/${encodeURIComponent(params.eventId)}/registrations`,
      {},
      token,
    ),
    backendRequest<SchoolEventVenueOut[]>("/api/v1/admin/event-venues", {}, token),
  ]);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_events")) {
    redirect("/admin?error=Accès%20non%20autorisé");
  }
  if (!eventResult.ok) {
    if (eventResult.status === 404) notFound();
    redirect(`/admin/events?error=${encodeURIComponent(eventResult.message)}`);
  }
  const event = eventResult.data;
  const requestHeaders = headers();
  const forwardedHost = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "";
  const forwardedProtocol = requestHeaders.get("x-forwarded-proto") ?? (forwardedHost.includes("localhost") ? "http" : "https");
  const directBookingUrl = forwardedHost ? `${forwardedProtocol}://${forwardedHost}/events/${event.slug}` : `/events/${event.slug}`;
  const registrations = registrationResult.ok ? registrationResult.data : [];
  const clientSearch = param(searchParams, "client_search").trim();
  const participantOptionsResult = clientSearch.length >= 2
    ? await backendRequest<SchoolEventAdminParticipantOptionOut[]>(
      `/api/v1/admin/events/participant-options?search=${encodeURIComponent(clientSearch)}&limit=30`,
      {},
      token,
    )
    : null;
  const participantOptions = participantOptionsResult?.ok ? participantOptionsResult.data : [];
  const registrationGroups = Array.from(
    registrations.reduce((groups, registration) => {
      const group = groups.get(registration.group_id) ?? [];
      group.push(registration);
      groups.set(registration.group_id, group);
      return groups;
    }, new Map<string, SchoolEventRegistrationOut[]>()),
  );
  const venues = venuesResult.ok ? venuesResult.data : [];
  const ok = param(searchParams, "ok");
  const error = param(searchParams, "error")
    || (!registrationResult.ok ? registrationResult.message : "")
    || (participantOptionsResult && !participantOptionsResult.ok ? participantOptionsResult.message : "");
  const returnTo = `/admin/events/${event.id}`;
  const nextStart = new Date(Date.now() + 24 * 60 * 60 * 1000);
  nextStart.setMinutes(0, 0, 0);
  const nextEnd = new Date(nextStart.getTime() + 60 * 60 * 1000);

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <Link href="/admin/events">← Tous les événements</Link>
          <h1>{event.title_fr}</h1>
          <div className={styles.badges}>
            <span className={styles.badge}>{event.category}</span>
            <span className={`${styles.badge} ${event.status === "PUBLISHED" ? styles.badgePublished : styles.badgeClosed}`}>
              {event.status}
            </span>
            <span className={styles.badge}>{event.registration_count} inscrit(s)</span>
            <span className={styles.badge}>
              Rappel automatique {event.reminder_hours_before_start} h avant
            </span>
            {event.reminder_sent_count ? (
              <span className={styles.badge}>{event.reminder_sent_count} envoyé(s)</span>
            ) : null}
          </div>
        </div>
        <div className={styles.heroActions}>
          <form action={duplicateSchoolEventAction}>
            <input type="hidden" name="event_id" value={event.id} />
            <input type="hidden" name="return_to" value="/admin/events" />
            <button className="ghost" type="submit">Dupliquer</button>
          </form>
          {event.status === "PUBLISHED" ? (
            <Link className="ghost" href={`/events/${event.slug}`} target="_blank">Voir côté client</Link>
          ) : null}
        </div>
      </section>

      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      {event.status === "PUBLISHED" && event.audience === "PUBLIC" ? (
        <section className={styles.panel}>
          <h2>Lien direct de réservation</h2>
          <p className="muted">Envoyez ce lien aux familles et aux accompagnants. Aucun compte n’est nécessaire.</p>
          <div className={styles.slotForm}>
            <input readOnly value={directBookingUrl} aria-label="Lien direct de réservation" />
            <a className="ghost" href={directBookingUrl} target="_blank" rel="noreferrer">Ouvrir le formulaire</a>
          </div>
        </section>
      ) : null}

      <section className={styles.panel}>
        <h2>Visuel du concert</h2>
        <div className={styles.slotForm}>
          {event.image_url ? (
            <img src={event.image_url} alt={`Visuel de ${event.title_fr}`} style={{ maxWidth: "260px", maxHeight: "180px", objectFit: "cover", borderRadius: "12px" }} />
          ) : <p className="muted">Aucun visuel importé.</p>}
          <form action={uploadSchoolEventImageAction} className={styles.field}>
            <input type="hidden" name="event_id" value={event.id} />
            <input type="hidden" name="return_to" value={returnTo} />
            <span>Importer ou remplacer le visuel</span>
            <input name="image_file" type="file" accept="image/jpeg,image/png,image/webp" required />
            <button type="submit">Importer</button>
            <small className="muted">JPG, PNG ou WebP — 8 Mo maximum.</small>
          </form>
        </div>
      </section>

      <details className={styles.panel}>
        <summary><strong>Paramètres et publication</strong></summary>
        <form action={updateSchoolEventAction} className={styles.formGrid}>
          <input type="hidden" name="event_id" value={event.id} />
          <input type="hidden" name="return_to" value={returnTo} />
          <label className={styles.field}>
            <span>Titre français *</span>
            <input name="title_fr" required defaultValue={event.title_fr} />
          </label>
          <label className={styles.field}>
            <span>Titre anglais</span>
            <input name="title_en" defaultValue={event.title_en ?? ""} />
          </label>
          <label className={styles.field}>
            <span>Adresse web *</span>
            <input name="slug" required defaultValue={event.slug} />
          </label>
          <label className={styles.field}>
            <span>Catégorie</span>
            <select name="category" defaultValue={event.category}>
              {!["CONCERT", "COURS_CONTROLE", "MASTERCLASS", "ATELIER", "STAGE", "AUTRE"].includes(event.category) ? (
                <option value={event.category}>{event.category}</option>
              ) : null}
              <option value="CONCERT">Concert</option>
              <option value="COURS_CONTROLE">Cours de contrôle</option>
              <option value="MASTERCLASS">Masterclass</option>
              <option value="ATELIER">Atelier</option>
              <option value="STAGE">Stage</option>
              <option value="AUTRE">Autre</option>
            </select>
          </label>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Description française</span>
            <textarea name="description_fr" rows={5} defaultValue={event.description_fr ?? ""} />
          </label>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Description anglaise</span>
            <textarea name="description_en" rows={4} defaultValue={event.description_en ?? ""} />
          </label>
          <label className={styles.field}>
            <span>Image (URL)</span>
            <input name="image_url" type="url" defaultValue={event.image_url ?? ""} />
          </label>
          <label className={styles.field}>
            <span>Lieu par défaut</span>
            <select name="event_venue_id" defaultValue={event.location?.id ?? ""}>
              <option value="">À définir par créneau</option>
              {venues.map((venue) => <option value={venue.id} key={venue.id}>{venue.name}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Statut</span>
            <select name="status" defaultValue={event.status}>
              <option value="DRAFT">Brouillon</option>
              <option value="PUBLISHED">Publié</option>
              <option value="CLOSED">Inscriptions closes</option>
              <option value="COMPLETED">Terminé</option>
              <option value="CANCELLED">Annulé</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Visibilité</span>
            <select name="audience" defaultValue={event.audience}>
              <option value="CLIENTS">Comptes clients</option>
              <option value="PUBLIC">Public</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Ouverture des inscriptions</span>
            <input name="booking_opens_at" type="datetime-local" defaultValue={dateTimeLocal(event.booking_opens_at)} />
          </label>
          <label className={styles.field}>
            <span>Clôture des inscriptions</span>
            <input name="booking_closes_at" type="datetime-local" defaultValue={dateTimeLocal(event.booking_closes_at)} />
          </label>
          <label className={styles.field}>
            <span>Type d’inscription</span>
            <select name="registration_mode" defaultValue={event.registration_mode}>
              <option value="GROUP_SESSION">Plusieurs personnes / famille</option>
              <option value="INDIVIDUAL_SLOT">Une personne par créneau</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Paiement</span>
            <select name="payment_mode" defaultValue={event.payment_mode}>
              <option value="FREE">Gratuit</option>
              <option value="ON_SITE">Paiement sur place</option>
              <option value="ONLINE">Paiement en ligne</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Prix unique (utilisé sans grille tarifaire)</span>
            <input name="price_ttc" type="number" min="0" step="0.01" defaultValue={event.price_ttc} />
          </label>
          <label className={styles.field}>
            <span>Maximum par famille</span>
            <input name="max_per_family" type="number" min="1" defaultValue={event.max_per_family} />
          </label>
          <label className={styles.field}>
            <span>Annulation jusqu’à (heures avant)</span>
            <input name="cancellation_deadline_hours" type="number" min="0" defaultValue={event.cancellation_deadline_hours} />
          </label>
          <div className={`${styles.checkRow} ${styles.full}`}>
            <label className={styles.checkLabel}><input type="checkbox" name="waitlist_enabled" defaultChecked={event.waitlist_enabled} /> Liste d’attente</label>
            <label className={styles.checkLabel}><input type="checkbox" name="collect_piece_info" defaultChecked={event.collect_piece_info} /> Pièce interprétée</label>
            <label className={styles.checkLabel}><input type="checkbox" name="collect_photo_consent" defaultChecked={event.collect_photo_consent} /> Consentement photo</label>
            <label className={styles.checkLabel}>
              <input type="checkbox" name="collect_performer_booking" defaultChecked={event.collect_performer_booking} />
              L’enfant réservé est interprète
            </label>
          </div>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Message de confirmation français</span>
            <textarea name="confirmation_message_fr" rows={3} defaultValue={event.confirmation_message_fr ?? ""} />
          </label>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Message de confirmation anglais</span>
            <textarea name="confirmation_message_en" rows={3} defaultValue={event.confirmation_message_en ?? ""} />
          </label>
          <div className={`${styles.actions} ${styles.full}`}>
            <button className="primary" type="submit">Enregistrer</button>
          </div>
        </form>
      </details>

      <section className={styles.panel}>
        <h2>Tarifs proposés</h2>
        <p className="muted">
          Ajoutez autant de catégories que nécessaire (enfant, adulte, élève, parent d’élève, invité…).
          Le client choisira son tarif lors de l’inscription.
        </p>
        <div className={styles.slotList}>
          {event.price_tiers.map((tier) => (
            <div className={styles.slot} key={tier.id}>
              <strong>{tier.label_fr}</strong> — {Number(tier.price_ttc).toFixed(2)} {event.currency}
              <form action={deleteSchoolEventPriceTierAction}>
                <input type="hidden" name="event_id" value={event.id} />
                <input type="hidden" name="tier_id" value={tier.id} />
                <input type="hidden" name="return_to" value={returnTo} />
                <button type="submit" className="ghost">Retirer</button>
              </form>
            </div>
          ))}
        </div>
        <form action={createSchoolEventPriceTierAction} className={styles.slotForm}>
          <input type="hidden" name="event_id" value={event.id} />
          <input type="hidden" name="return_to" value={returnTo} />
          <label className={styles.field}><span>Libellé *</span><input name="label_fr" required placeholder="Tarif enfant" /></label>
          <label className={styles.field}><span>Libellé anglais</span><input name="label_en" placeholder="Child" /></label>
          <label className={styles.field}><span>Prix TTC *</span><input name="price_ttc" type="number" min="0" step="0.01" required /></label>
          <input type="hidden" name="sort_order" value={event.price_tiers.length} />
          <div className={styles.actions}><button type="submit">Ajouter le tarif</button></div>
        </form>
        {!event.price_tiers.length ? <p className="muted">Le prix unique ci-dessus reste utilisé tant qu’aucun tarif n’est ajouté.</p> : null}
      </section>

      <section className={styles.panel}>
        <h2>Créneaux proposés</h2>
        <p className="muted">
          Le nombre maximum d’inscrits est géré ici, pour chaque créneau. La jauge client bloque les inscriptions publiques ;
          la jauge administrative autorise les ajouts manuels au-delà de ce seuil.
        </p>
        <form action={createSchoolEventSlotAction} className={styles.slotForm}>
          <input type="hidden" name="event_id" value={event.id} />
          <input type="hidden" name="return_to" value={returnTo} />
          <input type="hidden" name="timezone" value="Europe/Paris" />
          <label className={styles.field}>
            <span>Début *</span>
            <input name="start_at" type="datetime-local" required defaultValue={dateTimeLocal(nextStart.toISOString())} />
          </label>
          <label className={styles.field}>
            <span>Fin *</span>
            <input name="end_at" type="datetime-local" required defaultValue={dateTimeLocal(nextEnd.toISOString())} />
          </label>
          <label className={styles.field}>
            <span>Libellé facultatif</span>
            <input name="label" placeholder="Passage 1, répétition..." />
          </label>
          <label className={styles.field}>
            <span>Jauge client (maximum d’inscrits) *</span>
            <input name="capacity_max" type="number" min="1" required defaultValue="10" />
          </label>
          <label className={styles.field}>
            <span>Jauge administrative *</span>
            <input name="admin_capacity_max" type="number" min="1" required defaultValue="12" />
          </label>
          <label className={styles.field}>
            <span>Lieu</span>
            <select name="event_venue_id" defaultValue={event.location?.id ?? ""}>
              <option value="">Lieu par défaut</option>
              {venues.map((venue) => <option value={venue.id} key={venue.id}>{venue.name}</option>)}
            </select>
          </label>
          <div className={styles.actions}><button type="submit">Ajouter le créneau</button></div>
        </form>
        <div className={styles.slotList}>
          {event.slots.map((slot) => (
            <article className={styles.slot} key={slot.id}>
              <div className={styles.slotTop}>
                <div>
                  <strong>{slot.label || formatDate(slot.start_at_utc, slot.timezone)}</strong>
                  {slot.label ? <p>{formatDate(slot.start_at_utc, slot.timezone)}</p> : null}
                  <p className="muted">{slot.location?.name ?? event.location?.name ?? "Lieu à préciser"}</p>
                </div>
                <div className={styles.badges}>
                  <span className={styles.badge}>Public {slot.booked_count}/{slot.capacity_max}</span>
                  <span className={styles.badge}>
                    Admin {slot.booked_count}/{slot.admin_capacity_max}
                  </span>
                  {slot.waitlist_count ? <span className={styles.badge}>{slot.waitlist_count} en attente</span> : null}
                </div>
              </div>
              <form action={updateSchoolEventSlotCapacitiesAction} className={styles.capacityForm}>
                <input type="hidden" name="event_id" value={event.id} />
                <input type="hidden" name="slot_id" value={slot.id} />
                <input type="hidden" name="return_to" value={returnTo} />
                <label className={styles.field}>
                  <span>Jauge client</span>
                  <input name="capacity_max" type="number" min="1" required defaultValue={slot.capacity_max} />
                </label>
                <label className={styles.field}>
                  <span>Jauge administrative</span>
                  <input
                    name="admin_capacity_max"
                    type="number"
                    min="1"
                    required
                    defaultValue={slot.admin_capacity_max}
                  />
                </label>
                <div className={styles.actions}>
                  <button type="submit">Mettre à jour</button>
                </div>
              </form>
              <form action={deleteSchoolEventSlotAction}>
                <input type="hidden" name="event_id" value={event.id} />
                <input type="hidden" name="slot_id" value={slot.id} />
                <input type="hidden" name="return_to" value={returnTo} />
                <button type="submit" className="ghost" disabled={slot.booked_count + slot.waitlist_count > 0}>Supprimer</button>
              </form>
            </article>
          ))}
          {event.slots.length === 0 ? <div className={styles.empty}>Ajoutez au moins un créneau avant de publier.</div> : null}
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHeading}>
          <div>
            <h2>Inscriptions</h2>
            <p className="muted">
              {registrationGroups.length} réservation(s) · {registrations.length} participant(s), invités compris.
            </p>
          </div>
          <Link className="ghost" href={`/admin/events/${event.id}/registrations/export`}>
            Exporter en CSV
          </Link>
        </div>
        <details className={styles.manualRegistration} open={Boolean(clientSearch)}>
          <summary><strong>Ajouter une personne manuellement</strong></summary>
          <p className="muted">
            Cet ajout utilise la limite administrative du créneau et confirme immédiatement l’inscription.
          </p>
          <form method="get" className={styles.clientSearchForm}>
            <label className={styles.field}>
              <span>Rechercher un client</span>
              <input
                name="client_search"
                type="search"
                minLength={2}
                required
                defaultValue={clientSearch}
                placeholder="Nom, prénom ou email"
              />
            </label>
            <div className={styles.actions}>
              <button type="submit">Rechercher</button>
              {clientSearch ? <Link className="ghost" href={returnTo}>Effacer</Link> : null}
            </div>
          </form>
          {clientSearch.length >= 2 ? (
            <div className={styles.participantOptions}>
              {participantOptions.map((participant) => (
                <form
                  action={createAdminSchoolEventRegistrationAction}
                  className={styles.participantOption}
                  key={participant.id}
                >
                  <input type="hidden" name="event_id" value={event.id} />
                  <input type="hidden" name="participant_user_id" value={participant.id} />
                  <input type="hidden" name="return_to" value={returnTo} />
                  <div>
                    <strong>{participant.display_name}</strong>
                    <p className="muted">
                      {participant.client_kind === "CHILD" ? "Enfant" : "Adulte"}
                      {participant.email ? ` · ${participant.email}` : ""}
                    </p>
                  </div>
                  <label className={styles.field}>
                    <span>Créneau</span>
                    <select name="slot_id" required>
                      {event.slots
                        .filter((slot) => slot.status === "SCHEDULED")
                        .map((slot) => (
                          <option value={slot.id} key={slot.id}>
                            {slot.label || formatDate(slot.start_at_utc, slot.timezone)}
                            {` · ${slot.booked_count}/${slot.admin_capacity_max} admin`}
                          </option>
                        ))}
                    </select>
                  </label>
                  {event.price_tiers.length ? (
                    <label className={styles.field}>
                      <span>Tarif</span>
                      <select name="price_tier_id" required defaultValue="">
                        <option value="" disabled>Choisir</option>
                        {event.price_tiers.map((tier) => (
                          <option value={tier.id} key={tier.id}>{tier.label_fr} — {Number(tier.price_ttc).toFixed(2)} €</option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <label className={styles.checkLabel}>
                    <input type="checkbox" name="send_confirmation" defaultChecked />
                    Envoyer la confirmation
                  </label>
                  <button type="submit" disabled={!event.slots.some((slot) => slot.status === "SCHEDULED")}>
                    Ajouter et confirmer
                  </button>
                </form>
              ))}
              {participantOptions.length === 0 ? (
                <div className={styles.empty}>Aucun client trouvé pour « {clientSearch} ».</div>
              ) : null}
            </div>
          ) : null}
        </details>
        <div className={styles.registrationList}>
          {registrationGroups.map(([groupId, group]) => {
            const registration = group[0];
            const participantNames = group.map((item) => item.participant_display_name);
            const totalPlaces = group.reduce((sum, item) => sum + item.party_size, 0);
            const totalAmount = group.reduce((sum, item) => sum + Number(item.total_ttc_snapshot), 0);
            return (
              <article className={styles.registration} key={groupId}>
                <div className={styles.registrationGrid}>
                  <div>
                    <strong>{participantNames.join(", ")}</strong>
                    <p className="muted">{formatDate(registration.start_at_utc, registration.timezone)} · {registration.location_name ?? "Lieu à préciser"}</p>
                    {registration.public_booker_email ? (
                      <small className="muted">
                        Réservation publique par {[registration.public_booker_first_name, registration.public_booker_last_name].filter(Boolean).join(" ")}
                        {` · ${registration.public_booker_email}`}
                        {registration.public_booker_phone ? ` · ${registration.public_booker_phone}` : ""}
                      </small>
                    ) : null}
                    {registration.price_tier_label_snapshot ? (
                      <small className="muted">Tarif : {registration.price_tier_label_snapshot} · {totalAmount.toFixed(2)} €</small>
                    ) : null}
                    {registration.payment_reference ? (
                      <small className="muted">
                        Paiement {registration.payment_provider ?? "PSP"} · {registration.payment_reference} · {totalAmount.toFixed(2)} €
                      </small>
                    ) : null}
                  </div>
                  <span className={styles.badge}>{registrationLabel(registration.status)}</span>
                  <span>{totalPlaces} place(s)</span>
                  <form action={updateSchoolEventRegistrationGroupStatusAction} className={styles.actions}>
                    <input type="hidden" name="event_id" value={event.id} />
                    <input type="hidden" name="group_id" value={groupId} />
                    <input type="hidden" name="return_to" value={returnTo} />
                    <select name="status" defaultValue={registration.status}>
                      <option value="PENDING_PAYMENT">Paiement requis</option>
                      <option value="CONFIRMED">Confirmée</option>
                      <option value="WAITLISTED">Liste d’attente</option>
                      <option value="ATTENDED">Présent</option>
                      <option value="NO_SHOW">Absent</option>
                      <option value="CANCELLED">Annulée</option>
                    </select>
                    <button type="submit">Appliquer</button>
                  </form>
                </div>
              </article>
            );
          })}
          {registrationGroups.length === 0 ? <div className={styles.empty}>Aucune inscription pour le moment.</div> : null}
        </div>
      </section>
    </main>
  );
}
