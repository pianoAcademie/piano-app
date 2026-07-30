import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  createSchoolEventSlotAction,
  deleteSchoolEventSlotAction,
  updateSchoolEventAction,
  updateSchoolEventRegistrationStatusAction,
} from "../../../../lib/actions";
import { hasAdminPermission } from "../../../../lib/admin-access";
import { getAdminToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type {
  LocationOut,
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
  const [meResult, eventResult, registrationResult, locationsResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<SchoolEventOut>(`/api/v1/admin/events/${encodeURIComponent(params.eventId)}`, {}, token),
    backendRequest<SchoolEventRegistrationOut[]>(
      `/api/v1/admin/events/${encodeURIComponent(params.eventId)}/registrations`,
      {},
      token,
    ),
    backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token),
  ]);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_events")) {
    redirect("/admin?error=Accès%20non%20autorisé");
  }
  if (!eventResult.ok) {
    if (eventResult.status === 404) notFound();
    redirect(`/admin/events?error=${encodeURIComponent(eventResult.message)}`);
  }
  const event = eventResult.data;
  const registrations = registrationResult.ok ? registrationResult.data : [];
  const locations = locationsResult.ok ? locationsResult.data : [];
  const ok = param(searchParams, "ok");
  const error = param(searchParams, "error") || (!registrationResult.ok ? registrationResult.message : "");
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
          </div>
        </div>
        {event.status === "PUBLISHED" ? (
          <Link className="ghost" href={`/events/${event.slug}`} target="_blank">Voir côté client</Link>
        ) : null}
      </section>

      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

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
            <select name="location_id" defaultValue={event.location?.id ?? ""}>
              <option value="">À définir par créneau</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
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
            <select name="payment_mode" defaultValue={event.payment_mode === "ONLINE" ? "ON_SITE" : event.payment_mode}>
              <option value="FREE">Gratuit</option>
              <option value="ON_SITE">Paiement sur place</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Prix par personne</span>
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
        <h2>Créneaux proposés</h2>
        <p className="muted">Chaque créneau gère sa capacité et sa liste d’attente.</p>
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
            <span>Capacité *</span>
            <input name="capacity_max" type="number" min="1" required defaultValue="10" />
          </label>
          <label className={styles.field}>
            <span>Lieu</span>
            <select name="location_id" defaultValue={event.location?.id ?? ""}>
              <option value="">Lieu par défaut</option>
              {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
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
                  <span className={styles.badge}>{slot.booked_count}/{slot.capacity_max}</span>
                  {slot.waitlist_count ? <span className={styles.badge}>{slot.waitlist_count} en attente</span> : null}
                </div>
              </div>
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
        <h2>Inscriptions</h2>
        <p className="muted">{registrations.length} ligne(s), participants et invités compris.</p>
        <div className={styles.registrationList}>
          {registrations.map((registration) => (
            <article className={styles.registration} key={registration.id}>
              <div className={styles.registrationGrid}>
                <div>
                  <strong>{registration.participant_display_name}</strong>
                  <p className="muted">{formatDate(registration.start_at_utc, registration.timezone)} · {registration.location_name ?? "Lieu à préciser"}</p>
                </div>
                <span className={styles.badge}>{registrationLabel(registration.status)}</span>
                <span>{registration.party_size} place(s)</span>
                <form action={updateSchoolEventRegistrationStatusAction} className={styles.actions}>
                  <input type="hidden" name="event_id" value={event.id} />
                  <input type="hidden" name="registration_id" value={registration.id} />
                  <input type="hidden" name="return_to" value={returnTo} />
                  <select name="status" defaultValue={registration.status}>
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
          ))}
          {registrations.length === 0 ? <div className={styles.empty}>Aucune inscription pour le moment.</div> : null}
        </div>
      </section>
    </main>
  );
}
