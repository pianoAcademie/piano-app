import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  createAdminQuoteSchoolCalendarConfigAction,
  deployAdminQuoteSchoolCalendarAction,
  deployAdminQuoteSchoolCalendarGroupAction,
  deleteAdminQuoteSchoolCalendarConfigAction,
  previewAdminQuoteSchoolCalendarDeploymentAction,
  previewAdminQuoteSchoolCalendarGroupDeploymentAction,
  removeAdminQuoteSchoolCalendarDeploymentAction,
  removeAdminQuoteSchoolCalendarGroupDeploymentAction,
  syncAdminQuoteSchoolCalendarDeploymentAction,
  syncAdminQuoteSchoolCalendarGroupAction,
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
  deployment_status: string;
  deployment_last_at: string | null;
  deployment_last_sync_at: string | null;
  deployment_source_hash: string | null;
  deployment_generated_count: number;
  deployment_generated_active_count: number;
  updated_at: string;
};

type QuoteSchoolCalendarGeneratedSlotOut = {
  session_id: string;
  location_id: string;
  date: string;
  reason_types: string[];
  status: string;
  title: string;
  start_at: string;
  end_at: string;
};

type QuoteSchoolCalendarDeploymentPreviewOut = {
  calendar_id: string;
  location_id: string;
  deployment_status: string;
  source_hash: string;
  existing_generated_active_count: number;
  summary: {
    total_target_days: number;
    vacation_days: number;
    holiday_days: number;
    closure_days: number;
  };
  would_create: number;
  would_keep: number;
  would_reactivate: number;
  would_cancel: number;
  sample_dates: string[];
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

function deploymentStatusLabel(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "deployed") {
    return "Deploye";
  }
  if (normalized === "stale") {
    return "A resynchroniser";
  }
  if (normalized === "removed") {
    return "Retire";
  }
  return "Non deploye";
}

export default async function AdminSchoolCalendarsPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error=Session%20expiree");
  }

  const params = searchParams ?? {};
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");
  const generatedFor = readParam(params, "generated_for");
  const previewGroupKey = readParam(params, "preview_group");

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
  const groupedCalendars = Array.from(
    quoteSchoolCalendars.reduce<Map<string, { key: string; name: string; school_year_label: string; items: QuoteSchoolCalendarOut[] }>>(
      (acc, row) => {
        const key = `${row.name.trim().toLowerCase()}::${row.school_year_label.trim().toLowerCase()}`;
        const existing = acc.get(key);
        if (existing) {
          existing.items.push(row);
        } else {
          acc.set(key, {
            key,
            name: row.name,
            school_year_label: row.school_year_label,
            items: [row],
          });
        }
        return acc;
      },
      new Map(),
    ).values(),
  ).sort((a, b) => a.name.localeCompare(b.name, "fr"));

  const previewGroup = groupedCalendars.find((group) => group.key === previewGroupKey) ?? null;
  const groupPreviewRows = previewGroup
    ? (
        await Promise.all(
          previewGroup.items.map(async (item) => {
            const result = await backendRequest<QuoteSchoolCalendarDeploymentPreviewOut>(
              `/api/v1/quote-school-calendars/${encodeURIComponent(item.id)}/deployment/preview`,
              {},
              token,
            );
            if (!result.ok) {
              loadErrors.push(`Preview deploiement ${item.name} (${locationById.get(item.location_id) || item.location_id}): ${result.message}`);
              return null;
            }
            return { calendar: item, preview: result.data };
          }),
        )
      ).filter((entry): entry is { calendar: QuoteSchoolCalendarOut; preview: QuoteSchoolCalendarDeploymentPreviewOut } => entry !== null)
    : [];

  const groupPreviewTotals = groupPreviewRows.reduce(
    (acc, row) => {
      acc.totalTargetDays += Number(row.preview.summary?.total_target_days ?? 0);
      acc.vacationDays += Number(row.preview.summary?.vacation_days ?? 0);
      acc.holidayDays += Number(row.preview.summary?.holiday_days ?? 0);
      acc.closureDays += Number(row.preview.summary?.closure_days ?? 0);
      acc.wouldCreate += Number(row.preview.would_create ?? 0);
      acc.wouldKeep += Number(row.preview.would_keep ?? 0);
      acc.wouldReactivate += Number(row.preview.would_reactivate ?? 0);
      acc.wouldCancel += Number(row.preview.would_cancel ?? 0);
      acc.existingGenerated += Number(row.preview.existing_generated_active_count ?? 0);
      return acc;
    },
    {
      totalTargetDays: 0,
      vacationDays: 0,
      holidayDays: 0,
      closureDays: 0,
      wouldCreate: 0,
      wouldKeep: 0,
      wouldReactivate: 0,
      wouldCancel: 0,
      existingGenerated: 0,
    },
  );
  const selectedCalendar = quoteSchoolCalendars.find((row) => row.id === generatedFor) ?? null;
  const generatedSlotsResult = selectedCalendar
    ? await backendRequest<QuoteSchoolCalendarGeneratedSlotOut[]>(
        `/api/v1/quote-school-calendars/${encodeURIComponent(selectedCalendar.id)}/generated-blocking-slots`,
        {},
        token,
      )
    : null;
  const generatedSlots = generatedSlotsResult?.ok ? generatedSlotsResult.data : [];
  if (generatedSlotsResult && !generatedSlotsResult.ok) {
    loadErrors.push(`Creneaux generes: ${generatedSlotsResult.message}`);
  }
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
            Deployer immediatement en creneaux bloquants (journee entiere)
          </label>
          <div className="row span-4">
            <button type="submit">Ajouter le calendrier</button>
          </div>
        </form>

        <section className="top-gap-sm">
          <h4>Vue groupee multi-locaux</h4>
          {groupedCalendars.length === 0 ? (
            <p className="muted">Aucun groupe de calendrier.</p>
          ) : (
            <div className="grid cols-2 top-gap-sm">
              {groupedCalendars.map((group) => {
                const activeSlots = group.items.reduce((sum, item) => sum + Number(item.deployment_generated_active_count || 0), 0);
                const hasStale = group.items.some((item) => item.deployment_status === "stale");
                const allDeployed = group.items.every((item) => item.deployment_status === "deployed");
                const allRemoved = group.items.every((item) => item.deployment_status === "removed");
                const badgeClass = hasStale
                  ? "status-warn"
                  : allDeployed
                    ? "status-ok"
                    : allRemoved
                      ? "status-off"
                      : "status-warn";
                const badgeLabel = hasStale
                  ? "A resynchroniser"
                  : allDeployed
                    ? "Deploye"
                    : allRemoved
                      ? "Retire"
                      : "Partiel";
                return (
                  <article key={group.key} className="card">
                    <div className="row spread wrap gap-sm">
                      <div>
                        <strong>{group.name}</strong>
                        <p className="muted">{group.school_year_label} · {group.items.length} locaux</p>
                      </div>
                      <span className={`status-pill ${badgeClass}`}>{badgeLabel}</span>
                    </div>
                    <p className="muted">Creneaux actifs generes: {activeSlots}</p>
                    <p className="muted">
                      {group.items.map((item) => locationById.get(item.location_id) || item.location_id).join(", ")}
                    </p>
                    <div className="row wrap gap-sm top-gap-sm">
                      <form action={previewAdminQuoteSchoolCalendarGroupDeploymentAction}>
                        {group.items.map((item) => (
                          <input key={`${group.key}-preview-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                        ))}
                        <input type="hidden" name="return_to" value={returnPath} />
                        <button type="submit" className="ghost">Previsualiser</button>
                      </form>
                      <Link className="ghost" href={`/admin/config/calendars?preview_group=${encodeURIComponent(group.key)}`}>
                        Ouvrir preview detaillee
                      </Link>
                      <form action={deployAdminQuoteSchoolCalendarGroupAction}>
                        {group.items.map((item) => (
                          <input key={`${group.key}-deploy-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                        ))}
                        <input type="hidden" name="return_to" value={returnPath} />
                        <button type="submit">Deployer groupe</button>
                      </form>
                      <form action={syncAdminQuoteSchoolCalendarGroupAction}>
                        {group.items.map((item) => (
                          <input key={`${group.key}-sync-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                        ))}
                        <input type="hidden" name="return_to" value={returnPath} />
                        <button type="submit" className="ghost">Resynchroniser groupe</button>
                      </form>
                      <form action={removeAdminQuoteSchoolCalendarGroupDeploymentAction}>
                        {group.items.map((item) => (
                          <input key={`${group.key}-remove-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                        ))}
                        <input type="hidden" name="return_to" value={returnPath} />
                        <button type="submit" className="danger">Retirer groupe</button>
                      </form>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

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
                <th>Deploiement</th>
                <th>Creneaux actifs</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {quoteSchoolCalendars.length === 0 ? (
                <tr><td colSpan={10}><p className="muted">Aucun calendrier configure.</p></td></tr>
              ) : (
                quoteSchoolCalendars.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.school_year_label}</td>
                    <td>{locationById.get(row.location_id) || row.location_id}</td>
                    <td>{row.vacation_periods.length}</td>
                    <td>{row.holiday_dates.length}</td>
                    <td>{row.closure_dates.length}</td>
                    <td>
                      <span className={`status-pill ${
                        row.deployment_status === "deployed"
                          ? "status-ok"
                          : row.deployment_status === "stale"
                            ? "status-warn"
                            : row.deployment_status === "removed"
                              ? "status-off"
                              : "status-off"
                      }`}
                      >
                        {deploymentStatusLabel(row.deployment_status)}
                      </span>
                    </td>
                    <td>{row.deployment_generated_active_count || 0}</td>
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
                            Deployer immediatement en creneaux bloquants (journee entiere)
                          </label>
                          <div className="row">
                            <button type="submit">Enregistrer</button>
                          </div>
                        </form>
                        <div className="row wrap top-gap-sm gap-sm">
                          <form action={previewAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">Previsualiser le deploiement</button>
                          </form>
                          <form action={deployAdminQuoteSchoolCalendarAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit">Deployer</button>
                          </form>
                          <form action={syncAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">Mettre a jour le deploiement</button>
                          </form>
                          <form action={removeAdminQuoteSchoolCalendarDeploymentAction}>
                            <input type="hidden" name="calendar_id" value={row.id} />
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="danger">Retirer les creneaux generes</button>
                          </form>
                          <Link className="ghost" href={`/admin/config/calendars?generated_for=${encodeURIComponent(row.id)}`}>
                            Voir creneaux generes
                          </Link>
                        </div>
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

      {previewGroup ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>Previsualisation detaillee du deploiement</h3>
            <Link className="ghost" href="/admin/config/calendars">Fermer</Link>
          </div>
          <p className="muted">
            {previewGroup.name} · {previewGroup.school_year_label} · {previewGroup.items.length} locaux
          </p>
          <div className="row wrap gap-sm top-gap-sm">
            <span className="status-pill status-info">Dates cibles: {groupPreviewTotals.totalTargetDays}</span>
            <span className="status-pill status-info">Vacances: {groupPreviewTotals.vacationDays}</span>
            <span className="status-pill status-info">Feries: {groupPreviewTotals.holidayDays}</span>
            <span className="status-pill status-info">Fermetures: {groupPreviewTotals.closureDays}</span>
            <span className="status-pill status-ok">A creer: {groupPreviewTotals.wouldCreate}</span>
            <span className="status-pill status-ok">A reactiver: {groupPreviewTotals.wouldReactivate}</span>
            <span className="status-pill status-warn">A retirer: {groupPreviewTotals.wouldCancel}</span>
            <span className="status-pill status-info">Actifs existants: {groupPreviewTotals.existingGenerated}</span>
          </div>

          <div className="table-wrap top-gap-sm">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Local</th>
                  <th>Dates cibles</th>
                  <th>Vacances</th>
                  <th>Feries</th>
                  <th>Fermetures</th>
                  <th>A creer</th>
                  <th>A reactiver</th>
                  <th>A retirer</th>
                  <th>Actifs existants</th>
                </tr>
              </thead>
              <tbody>
                {groupPreviewRows.length === 0 ? (
                  <tr><td colSpan={9}><p className="muted">Aucune donnee de preview disponible.</p></td></tr>
                ) : (
                  groupPreviewRows.map(({ calendar, preview }) => (
                    <tr key={`preview-${calendar.id}`}>
                      <td>{locationById.get(calendar.location_id) || calendar.location_id}</td>
                      <td>{Number(preview.summary?.total_target_days ?? 0)}</td>
                      <td>{Number(preview.summary?.vacation_days ?? 0)}</td>
                      <td>{Number(preview.summary?.holiday_days ?? 0)}</td>
                      <td>{Number(preview.summary?.closure_days ?? 0)}</td>
                      <td>{Number(preview.would_create ?? 0)}</td>
                      <td>{Number(preview.would_reactivate ?? 0)}</td>
                      <td>{Number(preview.would_cancel ?? 0)}</td>
                      <td>{Number(preview.existing_generated_active_count ?? 0)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="row wrap gap-sm top-gap-sm">
            <form action={deployAdminQuoteSchoolCalendarGroupAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-deploy-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit">Confirmer et deployer</button>
            </form>
            <form action={syncAdminQuoteSchoolCalendarGroupAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-sync-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit" className="ghost">Resynchroniser ce groupe</button>
            </form>
            <form action={removeAdminQuoteSchoolCalendarGroupDeploymentAction}>
              {previewGroup.items.map((item) => (
                <input key={`preview-remove-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
              ))}
              <input type="hidden" name="return_to" value={returnPath} />
              <button type="submit" className="danger">Retirer les creneaux de ce groupe</button>
            </form>
          </div>
        </section>
      ) : null}

      {selectedCalendar ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>Creneaux bloquants generes</h3>
            <Link className="ghost" href="/admin/config/calendars">Fermer</Link>
          </div>
          <p className="muted">
            {selectedCalendar.name} · {locationById.get(selectedCalendar.location_id) || selectedCalendar.location_id}
          </p>
          {generatedSlots.length === 0 ? (
            <p className="muted">Aucun creneau genere pour ce calendrier.</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Raisons</th>
                    <th>Statut</th>
                    <th>Session</th>
                  </tr>
                </thead>
                <tbody>
                  {generatedSlots.map((slot) => (
                    <tr key={slot.session_id}>
                      <td>{slot.date}</td>
                      <td>{slot.reason_types.join(", ") || "-"}</td>
                      <td>{slot.status}</td>
                      <td>{slot.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}
