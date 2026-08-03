import Link from "next/link";
import { redirect } from "next/navigation";

import { createSchoolEventAction, createSchoolEventVenueAction } from "../../../lib/actions";
import { hasAdminPermission } from "../../../lib/admin-access";
import { getAdminToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { SchoolEventOut, SchoolEventVenueOut, UserOut } from "../../../lib/types";
import styles from "./events.module.css";

type SearchParams = Record<string, string | string[] | undefined>;

function param(params: SearchParams, key: string): string {
  const value = params[key];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function statusLabel(value: string): string {
  return {
    DRAFT: "Brouillon",
    PUBLISHED: "Publié",
    CLOSED: "Inscriptions closes",
    CANCELLED: "Annulé",
    COMPLETED: "Terminé",
  }[value] ?? value;
}

function nextSlot(event: SchoolEventOut): string {
  const next = event.slots.find((slot) => slot.status === "SCHEDULED" && new Date(slot.start_at_utc).getTime() > Date.now());
  if (!next) return "Aucun créneau à venir";
  return new Date(next.start_at_utc).toLocaleString("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: next.timezone,
  });
}

export default async function AdminEventsPage({ searchParams = {} }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = getAdminToken();
  if (!token) redirect("/login?error_code=session_expired");
  const [meResult, eventsResult, venuesResult] = await Promise.all([
    backendRequest<UserOut>("/api/v1/auth/me", {}, token),
    backendRequest<SchoolEventOut[]>("/api/v1/admin/events", {}, token),
    backendRequest<SchoolEventVenueOut[]>("/api/v1/admin/event-venues", {}, token),
  ]);
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_manage_events")) {
    redirect("/admin?error=Accès%20non%20autorisé");
  }
  const events = eventsResult.ok ? eventsResult.data : [];
  const venues = venuesResult.ok ? venuesResult.data : [];
  const query = param(searchParams, "q").trim().toLowerCase();
  const status = param(searchParams, "status").trim().toUpperCase();
  const visibleEvents = events.filter((event) => {
    const matchesQuery = !query || `${event.title_fr} ${event.title_en ?? ""} ${event.category}`.toLowerCase().includes(query);
    const matchesStatus = !status || event.status === status;
    return matchesQuery && matchesStatus;
  });
  const published = events.filter((event) => event.status === "PUBLISHED").length;
  const futureSlots = events.flatMap((event) => event.slots).filter((slot) => new Date(slot.start_at_utc).getTime() > Date.now()).length;
  const registrations = events.reduce((sum, event) => sum + event.registration_count, 0);
  const ok = param(searchParams, "ok");
  const error = param(searchParams, "error") || (!eventsResult.ok ? eventsResult.message : "");

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <h1>Événements</h1>
          <p className="muted">Concerts, cours de contrôle, masterclasses et rendez-vous ponctuels.</p>
        </div>
        <a className="primary" href="#new-event">Créer un événement</a>
      </section>

      {ok ? <p className="notice success">{ok}</p> : null}
      {error ? <p className="notice error">{error}</p> : null}

      <section className={styles.panel}>
        <strong>Visibilité côté client</strong>
        <p className="muted">
          Dès qu’il est publié, « Comptes clients » l’affiche dans l’onglet Événements après connexion ;
          « Public » l’affiche aussi sur la page publique et autorise la réservation sans compte. Ajoutez au moins un créneau pour permettre les inscriptions.
        </p>
      </section>

      <section className={styles.metrics}>
        <div className={styles.metric}><span>Total</span><strong>{events.length}</strong></div>
        <div className={styles.metric}><span>Publiés</span><strong>{published}</strong></div>
        <div className={styles.metric}><span>Créneaux à venir</span><strong>{futureSlots}</strong></div>
        <div className={styles.metric}><span>Inscrits confirmés</span><strong>{registrations}</strong></div>
      </section>

      <section className={styles.panel}>
        <form className={styles.filters}>
          <label className={styles.field}>
            <span>Recherche</span>
            <input name="q" defaultValue={param(searchParams, "q")} placeholder="Titre ou catégorie" />
          </label>
          <label className={styles.field}>
            <span>Statut</span>
            <select name="status" defaultValue={status}>
              <option value="">Tous</option>
              <option value="DRAFT">Brouillons</option>
              <option value="PUBLISHED">Publiés</option>
              <option value="CLOSED">Clos</option>
              <option value="COMPLETED">Terminés</option>
              <option value="CANCELLED">Annulés</option>
            </select>
          </label>
          <button type="submit">Filtrer</button>
        </form>
      </section>

      <section className={styles.cards} aria-label="Liste des événements">
        {visibleEvents.map((event) => (
          <Link className={styles.card} href={`/admin/events/${event.id}`} key={event.id}>
            <div className={styles.cardTop}>
              <div>
                <small>{event.category}</small>
                <h2>{event.title_fr}</h2>
              </div>
              <span className={`${styles.badge} ${event.status === "PUBLISHED" ? styles.badgePublished : styles.badgeClosed}`}>
                {statusLabel(event.status)}
              </span>
            </div>
            <div className={styles.badges}>
              <span className={styles.badge}>{event.slots.length} créneau(x)</span>
              <span className={styles.badge}>{event.registration_count} inscrit(s)</span>
              {event.waitlist_count ? <span className={styles.badge}>{event.waitlist_count} en attente</span> : null}
              {event.reminder_sent_count ? (
                <span className={styles.badge}>{event.reminder_sent_count} rappel(s) envoyé(s)</span>
              ) : null}
            </div>
            <p><strong>Prochain :</strong> {nextSlot(event)}</p>
          </Link>
        ))}
        {visibleEvents.length === 0 ? <div className={styles.empty}>Aucun événement ne correspond aux filtres.</div> : null}
      </section>

      <details className={styles.panel} id="event-venues">
        <summary><strong>Lieux événementiels ({venues.length})</strong></summary>
        <p className="muted">Ce répertoire est indépendant des lieux utilisés pour les cours.</p>
        {venues.length ? (
          <p>{venues.map((venue) => `${venue.name}${venue.city ? ` — ${venue.city}` : ""}`).join(" · ")}</p>
        ) : null}
        <form action={createSchoolEventVenueAction} className={styles.formGrid}>
          <input type="hidden" name="return_to" value="/admin/events" />
          <label className={styles.field}><span>Nom du lieu *</span><input name="name" required placeholder="Théâtre le Ranelagh" /></label>
          <label className={styles.field}><span>Adresse</span><input name="address_line" placeholder="5 rue des Vignes" /></label>
          <label className={styles.field}><span>Code postal</span><input name="postal_code" placeholder="75016" /></label>
          <label className={styles.field}><span>Ville</span><input name="city" placeholder="Paris" /></label>
          <div className={styles.actions}><button type="submit">Ajouter ce lieu</button></div>
        </form>
      </details>

      <details className={styles.panel} id="new-event" open={events.length === 0}>
        <summary><strong>Créer un événement</strong></summary>
        <form action={createSchoolEventAction} className={styles.formGrid}>
          <input type="hidden" name="return_to" value="/admin/events" />
          <label className={styles.field}>
            <span>Titre français *</span>
            <input name="title_fr" required minLength={2} />
          </label>
          <label className={styles.field}>
            <span>Titre anglais</span>
            <input name="title_en" />
          </label>
          <label className={styles.field}>
            <span>Adresse web *</span>
            <input name="slug" required placeholder="concert-fin-annee-2027" />
          </label>
          <label className={styles.field}>
            <span>Catégorie</span>
            <select name="category" defaultValue="CONCERT">
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
            <textarea name="description_fr" rows={4} />
          </label>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Description anglaise</span>
            <textarea name="description_en" rows={3} />
          </label>
          <label className={`${styles.field} ${styles.full}`}>
            <span>Visuel du concert (JPG, PNG ou WebP — 8 Mo maximum)</span>
            <input name="image_file" type="file" accept="image/jpeg,image/png,image/webp" />
          </label>
          <label className={styles.field}>
            <span>Lieu par défaut</span>
            <select name="event_venue_id" defaultValue="">
              <option value="">À définir par créneau</option>
              {venues.map((venue) => <option value={venue.id} key={venue.id}>{venue.name}</option>)}
            </select>
          </label>
          <label className={styles.field}>
            <span>Visibilité</span>
            <select name="audience" defaultValue="CLIENTS">
              <option value="CLIENTS">Comptes clients</option>
              <option value="PUBLIC">Public</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Type d’inscription</span>
            <select name="registration_mode" defaultValue="GROUP_SESSION">
              <option value="GROUP_SESSION">Plusieurs personnes / famille</option>
              <option value="INDIVIDUAL_SLOT">Une personne par créneau</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Paiement</span>
            <select name="payment_mode" defaultValue="FREE">
              <option value="FREE">Gratuit</option>
              <option value="ON_SITE">Paiement sur place</option>
              <option value="ONLINE">Paiement en ligne</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Prix unique initial</span>
            <input name="price_ttc" type="number" min="0" step="0.01" defaultValue="0" />
          </label>
          <label className={styles.field}>
            <span>Maximum par famille</span>
            <input name="max_per_family" type="number" min="1" defaultValue="6" />
          </label>
          <input type="hidden" name="status" value="DRAFT" />
          <input type="hidden" name="cancellation_deadline_hours" value="24" />
          <div className={`${styles.checkRow} ${styles.full}`}>
            <label className={styles.checkLabel}><input type="checkbox" name="waitlist_enabled" defaultChecked /> Liste d’attente</label>
            <label className={styles.checkLabel}>
              <input type="checkbox" name="show_remaining_seats" defaultChecked /> Afficher les places restantes
            </label>
            <label className={styles.checkLabel}><input type="checkbox" name="collect_piece_info" /> Pièce interprétée</label>
            <label className={styles.checkLabel}><input type="checkbox" name="collect_photo_consent" /> Consentement photo</label>
            <label className={styles.checkLabel}>
              <input type="checkbox" name="collect_performer_booking" /> L’enfant réservé est interprète
            </label>
          </div>
          <div className={`${styles.actions} ${styles.full}`}>
            <button className="primary" type="submit">Créer puis ajouter les créneaux</button>
          </div>
          <p className={`${styles.full} muted`}>Après création, vous pourrez ajouter plusieurs tarifs et définir la jauge maximale de chaque créneau.</p>
        </form>
      </details>
    </main>
  );
}
