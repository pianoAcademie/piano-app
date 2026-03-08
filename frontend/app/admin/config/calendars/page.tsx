import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminQuoteSchoolCalendarConfigAction,
  deleteAdminQuoteSchoolCalendarConfigAction,
  updateAdminQuoteSchoolCalendarConfigAction,
} from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { LocationOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

type QuoteSchoolCalendarPeriodOut = {
  start_date: string;
  end_date: string;
  label: string | null;
};

type QuoteSchoolCalendarOut = {
  id: string;
  name: string;
  school_year_label: string;
  location_id: string;
  vacation_periods: QuoteSchoolCalendarPeriodOut[];
  holiday_dates: string[];
  closure_dates: string[];
  is_active: boolean;
  updated_at: string;
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

function calendarVacationPeriodsText(periods: QuoteSchoolCalendarPeriodOut[]): string {
  if (!periods.length) {
    return "";
  }
  return periods
    .map((period) => {
      const label = (period.label || "").trim();
      return label
        ? `${period.start_date} | ${period.end_date} | ${label}`
        : `${period.start_date} | ${period.end_date}`;
    })
    .join("\n");
}

function calendarDatesText(dates: string[]): string {
  if (!dates.length) {
    return "";
  }
  return dates.join("\n");
}

export default async function AdminSchoolCalendarsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  const [quoteSchoolCalendarsResult, locationsResult] = await Promise.all([
    backendRequest<QuoteSchoolCalendarOut[]>("/api/v1/quote-school-calendars", {}, token),
    backendRequest<LocationOut[]>("/api/v1/locations?active=false", {}, token),
  ]);

  const loadErrors: string[] = [];
  const quoteSchoolCalendars = quoteSchoolCalendarsResult.ok
    ? quoteSchoolCalendarsResult.data
    : (() => {
        loadErrors.push(`Calendriers scolaires: ${quoteSchoolCalendarsResult.message}`);
        return [] as QuoteSchoolCalendarOut[];
      })();
  const locations = locationsResult.ok
    ? locationsResult.data
    : (() => {
        loadErrors.push(`Lieux: ${locationsResult.message}`);
        return [] as LocationOut[];
      })();

  const locationById = new Map(locations.map((row) => [row.id, row.name]));
  const returnPath = "/admin/config/calendars";

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread wrap gap-sm">
          <div>
            <h2>Calendriers scolaires</h2>
            <p className="muted">
              Referentiel global des vacances, jours feries et fermetures, reutilise dans les devis et la gestion des plannings.
            </p>
          </div>
          <div className="row wrap gap-sm">
            <Link className="ghost" href="/admin/config">Retour Configuration</Link>
            <Link className="ghost" href="/admin/config/quotes">Configuration Devis</Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
      {loadErrors.length > 0 ? (
        <section className="card">
          <h3>Erreurs de chargement</h3>
          <ul className="config-error-list">
            {loadErrors.map((message) => (
              <li key={message} className="flash-err">{message}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="card">
        <h3>Calendriers scolaires par local</h3>
        <p className="muted">Definissez les vacances, jours feries et fermetures exceptionnelles par annee scolaire et par local.</p>
        <form action={createAdminQuoteSchoolCalendarConfigAction} className="grid cols-4 config-form-grid top-gap-sm">
          <input type="hidden" name="return_to" value={returnPath} />
          <label className="span-2">
            Nom du calendrier
            <input type="text" name="name" required maxLength={180} placeholder="Calendrier Paris 2026-2027" />
          </label>
          <label>
            Annee scolaire
            <input type="text" name="school_year_label" required maxLength={40} placeholder="2026-2027" />
          </label>
          <fieldset className="span-4 calendar-locations-fieldset">
            <legend>Locaux cibles</legend>
            <p className="muted">Selection multiple possible: le meme calendrier sera deploie sur tous les locaux coches.</p>
            <div className="calendar-location-grid">
              {locations.map((row) => (
                <label key={`calendar-create-location-${row.id}`} className="checkline">
                  <input type="checkbox" name="location_ids" value={row.id} />
                  {row.name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="span-4 calendar-inline-help">
            <strong>Saisie rapide</strong>
            <p className="muted">Vacances: une ligne = <code>YYYY-MM-DD | YYYY-MM-DD | Libelle</code> (libelle optionnel). Jours feries et fermetures: une date par ligne.</p>
          </div>
          <label className="span-2 calendar-textarea-field">
            Vacances scolaires (periodes)
            <textarea
              name="vacation_periods_text"
              rows={8}
              placeholder={"2026-10-17 | 2026-11-01 | Vacances Toussaint\n2026-12-19 | 2027-01-03 | Vacances Noel"}
            />
          </label>
          <label className="calendar-textarea-field">
            Jours feries (une date par ligne)
            <textarea
              name="holiday_dates_text"
              rows={8}
              placeholder={"2026-11-11\n2026-12-25\n2027-01-01"}
            />
          </label>
          <label className="calendar-textarea-field">
            Fermetures exceptionnelles (une date par ligne)
            <textarea
              name="closure_dates_text"
              rows={8}
              placeholder={"2026-09-02\n2027-05-19"}
            />
          </label>
          <div className="span-4 calendar-inline-help compact">
            <p className="muted">Astuce: copiez/collez une liste de dates depuis Excel/Sheets, une ligne par date.</p>
          </div>
          <label className="checkline">
            <input type="checkbox" name="is_active" defaultChecked />
            Actif
          </label>
          <label className="checkline span-3">
            <input type="checkbox" name="apply_to_management_planning" />
            Appliquer au planning de gestion actuel (creation de creneaux bloquants journee entiere)
          </label>
          <div className="row span-4">
            <button type="submit">Ajouter le calendrier</button>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Annee</th>
                <th>Local</th>
                <th>Vacances</th>
                <th>Feries</th>
                <th>Fermetures</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {quoteSchoolCalendars.length === 0 ? (
                <tr><td colSpan={8}><p className="muted">Aucun calendrier configure.</p></td></tr>
              ) : (
                quoteSchoolCalendars.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.school_year_label}</td>
                    <td>{locationById.get(row.location_id) || row.location_id}</td>
                    <td>{row.vacation_periods.length}</td>
                    <td>{row.holiday_dates.length}</td>
                    <td>{row.closure_dates.length}</td>
                    <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span></td>
                    <td>
                      <details>
                        <summary className="mode-link">Modifier</summary>
                        <form action={updateAdminQuoteSchoolCalendarConfigAction} className="grid config-form-grid top-gap-sm">
                          <input type="hidden" name="calendar_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnPath} />
                          <label className="span-2">
                            Nom
                            <input type="text" name="name" defaultValue={row.name} required maxLength={180} />
                          </label>
                          <label>
                            Annee scolaire
                            <input type="text" name="school_year_label" defaultValue={row.school_year_label} required maxLength={40} />
                          </label>
                          <fieldset className="span-4 calendar-locations-fieldset">
                            <legend>Locaux cibles</legend>
                            <p className="muted">Selection multiple possible: le calendrier mis a jour sera duplique vers les locaux coches.</p>
                            <div className="calendar-location-grid">
                              {locations.map((location) => (
                                <label key={`${row.id}-location-${location.id}`} className="checkline">
                                  <input
                                    type="checkbox"
                                    name="location_ids"
                                    value={location.id}
                                    defaultChecked={location.id === row.location_id}
                                  />
                                  {location.name}
                                </label>
                              ))}
                            </div>
                          </fieldset>
                          <div className="span-4 calendar-inline-help">
                            <strong>Saisie rapide</strong>
                            <p className="muted">Vacances: une ligne = <code>YYYY-MM-DD | YYYY-MM-DD | Libelle</code>. Jours feries et fermetures: une date par ligne.</p>
                          </div>
                          <label className="span-2 calendar-textarea-field">
                            Vacances scolaires (periodes)
                            <textarea
                              name="vacation_periods_text"
                              rows={8}
                              defaultValue={calendarVacationPeriodsText(row.vacation_periods)}
                            />
                          </label>
                          <label className="calendar-textarea-field">
                            Jours feries (une date par ligne)
                            <textarea
                              name="holiday_dates_text"
                              rows={8}
                              defaultValue={calendarDatesText(row.holiday_dates)}
                            />
                          </label>
                          <label className="calendar-textarea-field">
                            Fermetures exceptionnelles (une date par ligne)
                            <textarea
                              name="closure_dates_text"
                              rows={8}
                              defaultValue={calendarDatesText(row.closure_dates)}
                            />
                          </label>
                          <label className="checkline">
                            <input type="checkbox" name="is_active" defaultChecked={row.is_active} />
                            Actif
                          </label>
                          <label className="checkline span-3">
                            <input type="checkbox" name="apply_to_management_planning" />
                            Appliquer au planning de gestion actuel (creation de creneaux bloquants journee entiere)
                          </label>
                          <div className="row">
                            <button type="submit">Enregistrer</button>
                          </div>
                        </form>
                        <form action={deleteAdminQuoteSchoolCalendarConfigAction} className="row top-gap-sm">
                          <input type="hidden" name="calendar_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnPath} />
                          <button type="submit" className="danger">Supprimer</button>
                        </form>
                      </details>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
