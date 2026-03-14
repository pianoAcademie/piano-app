import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import ConditionalConfirmSubmitButton from "../../../../components/conditional-confirm-submit-button";
import ConfirmSubmitButton from "../../../../components/confirm-submit-button";

import {
  bulkAdminQuoteSchoolCalendarsAction,
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
  updateAdminQuoteSchoolCalendarGroupAction,
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

type CalendarGroupSummary = {
  key: string;
  name: string;
  school_year_label: string;
  items: QuoteSchoolCalendarOut[];
  representative: QuoteSchoolCalendarOut;
  location_names: string[];
  active_slots: number;
  badge_class: string;
  badge_label: string;
  is_fully_removed: boolean;
};

type GeneratedGroupSlotRow = QuoteSchoolCalendarGeneratedSlotOut & {
  location_name: string;
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

function deploymentStatusClass(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "deployed") {
    return "status-ok";
  }
  if (normalized === "stale") {
    return "status-warn";
  }
  return "status-off";
}

function buildCalendarsPath(params: {
  locationFilter?: string;
  deploymentFilter?: string;
  statusFilter?: string;
  generatedFor?: string;
  previewGroup?: string;
  editGroup?: string;
  generatedGroup?: string;
  createModal?: string;
}): string {
  const search = new URLSearchParams();
  if (params.locationFilter) {
    search.set("location_filter", params.locationFilter);
  }
  if (params.deploymentFilter) {
    search.set("deployment_filter", params.deploymentFilter);
  }
  if (params.statusFilter) {
    search.set("status_filter", params.statusFilter);
  }
  if (params.generatedFor) {
    search.set("generated_for", params.generatedFor);
  }
  if (params.previewGroup) {
    search.set("preview_group", params.previewGroup);
  }
  if (params.editGroup) {
    search.set("edit_group", params.editGroup);
  }
  if (params.generatedGroup) {
    search.set("generated_group", params.generatedGroup);
  }
  if (params.createModal === "1") {
    search.set("create_modal", "1");
  }
  const query = search.toString();
  return query ? `/admin/config/calendars?${query}` : "/admin/config/calendars";
}

function calendarLocationSummary(names: string[]): string {
  if (names.length <= 4) {
    return names.join(", ");
  }
  const preview = names.slice(0, 4).join(", ");
  return `${preview} +${names.length - 4}`;
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
  const editGroupKey = readParam(params, "edit_group");
  const generatedGroupKey = readParam(params, "generated_group");
  const createModalOpen = readParam(params, "create_modal") === "1";
  const locationFilter = readParam(params, "location_filter");
  const deploymentFilter = readParam(params, "deployment_filter");
  const statusFilter = readParam(params, "status_filter");

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
  const filteredCalendars = quoteSchoolCalendars.filter((row) => {
    if (locationFilter && row.location_id !== locationFilter) {
      return false;
    }
    if (deploymentFilter && row.deployment_status !== deploymentFilter) {
      return false;
    }
    if (statusFilter === "active" && !row.is_active) {
      return false;
    }
    if (statusFilter === "inactive" && row.is_active) {
      return false;
    }
    return true;
  });
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
  const groupSummaries: CalendarGroupSummary[] = groupedCalendars.map((group) => {
    const representative = [...group.items].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0] ?? group.items[0];
    const locationNames = Array.from(new Set(group.items.map((item) => locationById.get(item.location_id) || item.location_id))).sort((a, b) =>
      a.localeCompare(b, "fr")
    );
    const activeSlots = group.items.reduce((sum, item) => sum + Number(item.deployment_generated_active_count || 0), 0);
    const hasStale = group.items.some((item) => item.deployment_status === "stale");
    const allDeployed = group.items.every((item) => item.deployment_status === "deployed");
    const allRemoved = group.items.every((item) => item.deployment_status === "removed");
    return {
      ...group,
      representative,
      location_names: locationNames,
      active_slots: activeSlots,
      badge_class: hasStale ? "status-warn" : allDeployed ? "status-ok" : allRemoved ? "status-off" : "status-warn",
      badge_label: hasStale ? "A resynchroniser" : allDeployed ? "Deploye" : allRemoved ? "Retire" : "Partiel",
      is_fully_removed: allRemoved,
    };
  });
  const returnPath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    editGroup: editGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: createModalOpen ? "1" : "",
  });
  const basePath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    generatedGroup: generatedGroupKey,
  });
  const createModalPath = buildCalendarsPath({
    locationFilter,
    deploymentFilter,
    statusFilter,
    generatedFor,
    previewGroup: previewGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: "1",
  });
  const resetFiltersPath = buildCalendarsPath({
    generatedFor,
    previewGroup: previewGroupKey,
    editGroup: editGroupKey,
    generatedGroup: generatedGroupKey,
    createModal: createModalOpen ? "1" : "",
  });

  const previewGroup = groupSummaries.find((group) => group.key === previewGroupKey) ?? null;
  const editGroup = groupSummaries.find((group) => group.key === editGroupKey) ?? null;
  const generatedGroup = groupSummaries.find((group) => group.key === generatedGroupKey) ?? null;
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
  const generatedGroupSlots = generatedGroup
    ? (
        await Promise.all(
          generatedGroup.items.map(async (item) => {
            const result = await backendRequest<QuoteSchoolCalendarGeneratedSlotOut[]>(
              `/api/v1/quote-school-calendars/${encodeURIComponent(item.id)}/generated-blocking-slots`,
              {},
              token,
            );
            if (!result.ok) {
              loadErrors.push(`Creneaux du bloc ${generatedGroup.name} (${locationById.get(item.location_id) || item.location_id}): ${result.message}`);
              return [] as GeneratedGroupSlotRow[];
            }
            const locationName = locationById.get(item.location_id) || item.location_id;
            return result.data.map((slot) => ({ ...slot, location_name: locationName }));
          }),
        )
      )
        .flat()
        .sort((a, b) => `${a.date}-${a.location_name}-${a.title}`.localeCompare(`${b.date}-${b.location_name}-${b.title}`, "fr"))
    : [];
  const modalErrorMessage = errorMessage || "";

  const renderCalendarBlockForm = (params: {
    action: (formData: FormData) => Promise<void>;
    returnTo: string;
    successReturnTo: string;
    submitLabel: string;
    cancelHref: string;
    defaults: {
      name: string;
      schoolYearLabel: string;
      selectedLocationIds: string[];
      vacationPeriodsText: string;
      holidayDatesText: string;
      closureDatesText: string;
      isActive: boolean;
    };
    applyPlanningLabel: string;
    existingEntries?: Array<{ calendarId: string; locationId: string }>;
    errorText?: string;
    footerNote?: string;
    extraActions?: JSX.Element | null;
  }): JSX.Element => (
    <form action={params.action} className="calendar-editor-form">
      <input type="hidden" name="return_to" value={params.returnTo} />
      <input type="hidden" name="success_return_to" value={params.successReturnTo} />
      {(params.existingEntries || []).map((entry) => (
        <input
          key={`calendar-editor-existing-${entry.calendarId}-${entry.locationId}`}
          type="hidden"
          name="existing_calendar_entries"
          value={`${entry.calendarId}:${entry.locationId}`}
        />
      ))}
      {params.errorText ? (
        <section className="flash-err modal-flash" role="alert">
          {params.errorText}
        </section>
      ) : null}
      <div className="grid cols-2 config-form-grid">
        <label>
          Nom du bloc
          <input type="text" name="name" defaultValue={params.defaults.name} required maxLength={180} placeholder="Calendrier Paris 2026-2027" />
        </label>
        <label>
          Annee scolaire
          <input type="text" name="school_year_label" defaultValue={params.defaults.schoolYearLabel} required maxLength={40} placeholder="2026-2027" />
        </label>
      </div>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>Locaux cibles</h4>
          <p className="muted">Le meme bloc sera applique sur tous les locaux coches.</p>
        </header>
        <fieldset className="calendar-locations-fieldset">
          <div className="calendar-location-grid">
            {locations.map((location) => (
              <label key={`calendar-modal-location-${location.id}`} className="checkline">
                <input
                  type="checkbox"
                  name="location_ids"
                  value={location.id}
                  defaultChecked={params.defaults.selectedLocationIds.includes(location.id)}
                />
                {location.name}
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>Saisie des dates</h4>
          <p className="muted">Ajoutez ou corrigez directement une date oubliee, puis enregistrez le bloc.</p>
        </header>
        <div className="calendar-inline-help">
          <strong>Saisie rapide</strong>
          <p className="muted">
            Vacances: une ligne = <code>YYYY-MM-DD | YYYY-MM-DD | Libelle</code>. Jours feries et fermetures: une date par ligne.
          </p>
        </div>
        <div className="grid cols-3 config-form-grid calendar-editor-text-grid">
          <label className="calendar-textarea-field">
            Vacances scolaires (periodes)
            <textarea
              name="vacation_periods_text"
              rows={8}
              defaultValue={params.defaults.vacationPeriodsText}
              placeholder={"2026-10-17 | 2026-11-01 | Vacances Toussaint\n2026-12-19 | 2027-01-03 | Vacances Noel"}
            />
          </label>
          <label className="calendar-textarea-field">
            Jours feries (une date par ligne)
            <textarea
              name="holiday_dates_text"
              rows={8}
              defaultValue={params.defaults.holidayDatesText}
              placeholder={"2026-11-11\n2026-12-25\n2027-01-01"}
            />
          </label>
          <label className="calendar-textarea-field">
            Fermetures exceptionnelles (une date par ligne)
            <textarea
              name="closure_dates_text"
              rows={8}
              defaultValue={params.defaults.closureDatesText}
              placeholder={"2026-09-02\n2027-05-19"}
            />
          </label>
        </div>
      </section>

      <section className="calendar-editor-section">
        <header className="calendar-editor-section-header">
          <h4>Options</h4>
          <p className="muted">Choisissez si le bloc reste actif et s il doit etre redeploye tout de suite.</p>
        </header>
        <div className="calendar-editor-toggle-grid">
          <label className="checkline">
            <input type="checkbox" name="is_active" defaultChecked={params.defaults.isActive} />
            Actif
          </label>
          <label className="checkline">
            <input type="checkbox" name="apply_to_management_planning" />
            {params.applyPlanningLabel}
          </label>
        </div>
      </section>

      <footer className="calendar-editor-footer">
        <div className="calendar-editor-footer-copy">
          <p className="muted">{params.footerNote || "Les changements sont appliques a tout le bloc, local par local."}</p>
          {params.extraActions}
        </div>
        <div className="row wrap gap-sm">
          <Link className="ghost" href={params.cancelHref}>
            Annuler
          </Link>
          <button type="submit">{params.submitLabel}</button>
        </div>
      </footer>
    </form>
  );

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

      {okMessage ? (
        <section className="card calendar-feedback-banner calendar-feedback-banner-ok" role="status">
          <strong>Action enregistree</strong>
          <p>{okMessage}</p>
        </section>
      ) : null}
      {errorMessage ? (
        <section className="card calendar-feedback-banner calendar-feedback-banner-error" role="alert">
          <strong>Action non terminee</strong>
          <p>{errorMessage}</p>
        </section>
      ) : null}
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
        <div className="row spread wrap gap-sm">
          <div>
            <h3>Calendriers scolaires par local</h3>
            <p className="muted">Travaillez par blocs calendaires, puis ouvrez le detail par local uniquement quand c est necessaire.</p>
          </div>
          <Link className="ghost" href={createModalPath}>
            Ajouter un calendrier
          </Link>
        </div>

        <section className="top-gap-sm">
          <div className="row spread wrap gap-sm">
            <div>
              <h4>Blocs calendaires</h4>
              <p className="muted">Travaillez d abord au niveau du bloc: un libelle, une annee, des dates communes et une liste de locaux.</p>
            </div>
            <span className="status-pill status-info">{groupSummaries.length} bloc(s)</span>
          </div>
          {groupSummaries.length === 0 ? (
            <p className="muted">Aucun bloc de calendrier pour les filtres en cours.</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Bloc</th>
                    <th>Annee</th>
                    <th>Locaux</th>
                    <th>Deploiement</th>
                    <th>Creneaux actifs</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {groupSummaries.map((group) => (
                    <tr key={group.key}>
                      <td><strong>{group.name}</strong></td>
                      <td>{group.school_year_label}</td>
                      <td title={group.location_names.join(", ")}>{calendarLocationSummary(group.location_names)}</td>
                      <td><span className={`status-pill ${group.badge_class}`}>{group.badge_label}</span></td>
                      <td>{group.active_slots}</td>
                      <td>
                        <div className="row wrap gap-sm">
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor,
                              previewGroup: previewGroupKey,
                              editGroup: group.key,
                              generatedGroup: generatedGroupKey,
                            })}
                          >
                            Modifier le bloc
                          </Link>
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor,
                              previewGroup: previewGroupKey,
                              editGroup: editGroupKey,
                              generatedGroup: group.key,
                            })}
                          >
                            Voir tous les creneaux
                          </Link>
                          <form action={previewAdminQuoteSchoolCalendarGroupDeploymentAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-preview-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">Previsualiser</button>
                          </form>
                          <form action={deployAdminQuoteSchoolCalendarGroupAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-deploy-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit">Deployer</button>
                          </form>
                          <form action={syncAdminQuoteSchoolCalendarGroupAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-sync-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="ghost">Resynchroniser</button>
                          </form>
                          <form action={removeAdminQuoteSchoolCalendarGroupDeploymentAction}>
                            {group.items.map((item) => (
                              <input key={`${group.key}-remove-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                            ))}
                            <input type="hidden" name="return_to" value={returnPath} />
                            <button type="submit" className="danger">Retirer</button>
                          </form>
                          {group.is_fully_removed ? (
                            <>
                              <form id={`calendar-group-delete-${group.key}`} action={bulkAdminQuoteSchoolCalendarsAction}>
                                {group.items.map((item) => (
                                  <input key={`${group.key}-delete-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                                ))}
                                <input type="hidden" name="bulk_action" value="DELETE" />
                                <input type="hidden" name="return_to" value={returnPath} />
                                <input type="hidden" name="success_return_to" value={basePath} />
                              </form>
                              <ConfirmSubmitButton
                                formId={`calendar-group-delete-${group.key}`}
                                label="Supprimer"
                                title="Supprimer ce bloc retire ?"
                                description={`Le bloc ${group.name} sera supprime pour ${group.items.length} local(aux). Cette action est irreversible.`}
                                confirmLabel="Supprimer le bloc"
                                className="danger"
                              />
                            </>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>

      <section className="card top-gap-sm">
        <div className="row spread wrap gap-sm">
          <div>
            <h4>Administration fine par local</h4>
            <p className="muted">
              Filtrez puis traitez plusieurs lignes locales a la fois. Retire signifie que les creneaux bloquants generes ont ete supprimes du planning, pas que le calendrier a disparu.
            </p>
          </div>
          <span className="status-pill status-info">{filteredCalendars.length} calendrier(s) visible(s)</span>
        </div>
        <form method="GET" className="grid cols-4 config-form-grid top-gap-sm">
          {generatedFor ? <input type="hidden" name="generated_for" value={generatedFor} /> : null}
          {previewGroupKey ? <input type="hidden" name="preview_group" value={previewGroupKey} /> : null}
          <label>
            Local
            <select name="location_filter" defaultValue={locationFilter || ""}>
              <option value="">Tous</option>
              {locations.map((row) => (
                <option key={`calendar-filter-location-${row.id}`} value={row.id}>{row.name}</option>
              ))}
            </select>
          </label>
          <label>
            Deploiement
            <select name="deployment_filter" defaultValue={deploymentFilter || ""}>
              <option value="">Tous</option>
              <option value="not_deployed">Non deploye</option>
              <option value="deployed">Deploye</option>
              <option value="stale">A resynchroniser</option>
              <option value="removed">Retire</option>
            </select>
          </label>
          <label>
            Statut
            <select name="status_filter" defaultValue={statusFilter || ""}>
              <option value="">Tous</option>
              <option value="active">Actif</option>
              <option value="inactive">Inactif</option>
            </select>
          </label>
          <div className="row wrap gap-sm" style={{ alignItems: "end" }}>
            <button type="submit" className="ghost">Filtrer</button>
            <Link className="ghost" href={resetFiltersPath}>Reinitialiser</Link>
          </div>
        </form>
        <form id="calendar-bulk-form" action={bulkAdminQuoteSchoolCalendarsAction} className="grid cols-4 config-form-grid top-gap-sm">
          <input type="hidden" name="return_to" value={returnPath} />
          <input type="hidden" name="success_return_to" value={basePath} />
          <label className="span-2">
            Action de masse
            <select name="bulk_action" defaultValue="SYNC">
              <option value="DEPLOY">Deployer les selections</option>
              <option value="SYNC">Resynchroniser les selections</option>
              <option value="REMOVE">Retirer les creneaux generes</option>
              <option value="DELETE">Supprimer les calendriers selectionnes</option>
            </select>
          </label>
          <div className="span-2 row wrap gap-sm" style={{ alignItems: "end" }}>
            <ConditionalConfirmSubmitButton
              formId="calendar-bulk-form"
              label="Appliquer"
              confirmFieldName="bulk_action"
              confirmFieldValue="DELETE"
              title="Supprimer les calendriers selectionnes ?"
              description="Les calendriers coches seront supprimes definitivement. Si certains ont encore des creneaux generes, ils seront retires du planning avant suppression."
              confirmLabel="Supprimer la selection"
            />
            <span className="muted">Cochez les lignes a traiter dans le tableau ci-dessous. Les suppressions demandent une confirmation.</span>
          </div>
        </form>

        <div className="table-wrap top-gap-sm">
          <table className="data-table">
            <thead>
              <tr>
                <th>Selection</th>
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
              {filteredCalendars.length === 0 ? (
                <tr><td colSpan={11}><p className="muted">Aucun calendrier ne correspond aux filtres.</p></td></tr>
              ) : (
                filteredCalendars.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <input
                        type="checkbox"
                        name="calendar_ids"
                        value={row.id}
                        form="calendar-bulk-form"
                        aria-label={`Selectionner ${row.name} ${locationById.get(row.location_id) || row.location_id}`}
                      />
                    </td>
                    <td><strong>{row.name}</strong></td>
                    <td>{row.school_year_label}</td>
                    <td>{locationById.get(row.location_id) || row.location_id}</td>
                    <td>{row.vacation_periods.length}</td>
                    <td>{row.holiday_dates.length}</td>
                    <td>{row.closure_dates.length}</td>
                    <td>
                      <span className={`status-pill ${deploymentStatusClass(row.deployment_status)}`}>
                        {deploymentStatusLabel(row.deployment_status)}
                      </span>
                    </td>
                    <td>{row.deployment_generated_active_count || 0}</td>
                    <td><span className={`status-pill ${row.is_active ? "status-ok" : "status-off"}`}>{row.is_active ? "Actif" : "Inactif"}</span></td>
                    <td>
                      <details>
                        <summary className="mode-link">Actions locales</summary>
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
                          <Link
                            className="ghost"
                            href={buildCalendarsPath({
                              locationFilter,
                              deploymentFilter,
                              statusFilter,
                              generatedFor: row.id,
                              previewGroup: previewGroupKey,
                            })}
                          >
                            Voir creneaux generes
                          </Link>
                        </div>
                        <form id={`calendar-delete-${row.id}`} action={deleteAdminQuoteSchoolCalendarConfigAction} className="row top-gap-sm">
                          <input type="hidden" name="calendar_id" value={row.id} />
                          <input type="hidden" name="return_to" value={returnPath} />
                          <ConfirmSubmitButton
                            formId={`calendar-delete-${row.id}`}
                            label="Supprimer"
                            title="Supprimer ce calendrier local ?"
                            description={`Le calendrier ${row.name} pour ${locationById.get(row.location_id) || row.location_id} sera supprime.`}
                            confirmLabel="Supprimer"
                            className="danger"
                          />
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

      {createModalOpen ? (
        <section className="modal-overlay">
          <article className="modal-panel client-create-modal calendar-editor-modal">
            <Link className="modal-close-x" href={basePath} aria-label="Fermer">
              ×
            </Link>
            <header className="calendar-editor-header">
              <div>
                <h3 className="modal-title">Ajouter un calendrier</h3>
                <p className="muted">
                  Creez un bloc calendrier commun, puis appliquez-le sur un ou plusieurs locaux.
                </p>
              </div>
            </header>
            {renderCalendarBlockForm({
              action: createAdminQuoteSchoolCalendarConfigAction,
              returnTo: createModalPath,
              successReturnTo: basePath,
              submitLabel: "Ajouter le calendrier",
              cancelHref: basePath,
              defaults: {
                name: "",
                schoolYearLabel: "",
                selectedLocationIds: [],
                vacationPeriodsText: "",
                holidayDatesText: "",
                closureDatesText: "",
                isActive: true,
              },
              applyPlanningLabel: "Deployer immediatement en creneaux bloquants (journee entiere)",
              errorText: modalErrorMessage,
              footerNote: "Apres validation, le bloc sera cree pour chaque local coche et vous reverrez une confirmation claire sur la page.",
            })}
          </article>
        </section>
      ) : null}

      {editGroup ? (
        <section className="modal-overlay">
          <article className="modal-panel client-create-modal calendar-editor-modal">
            <Link className="modal-close-x" href={basePath} aria-label="Fermer">
              ×
            </Link>
            <header className="calendar-editor-header">
              <div>
                <h3 className="modal-title">Modifier le bloc</h3>
                <p className="muted">
                  {editGroup.name} · {editGroup.school_year_label} · {editGroup.location_names.join(", ")}
                </p>
              </div>
              <span className={`status-pill ${editGroup.badge_class}`}>{editGroup.badge_label}</span>
            </header>
            {renderCalendarBlockForm({
              action: updateAdminQuoteSchoolCalendarGroupAction,
              returnTo: buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                previewGroup: previewGroupKey,
                editGroup: editGroup.key,
                generatedGroup: generatedGroupKey,
              }),
              successReturnTo: basePath,
              submitLabel: "Enregistrer le bloc",
              cancelHref: basePath,
              defaults: {
                name: editGroup.representative.name,
                schoolYearLabel: editGroup.representative.school_year_label,
                selectedLocationIds: editGroup.items.map((item) => item.location_id),
                vacationPeriodsText: calendarVacationPeriodsText(editGroup.representative.vacation_periods),
                holidayDatesText: calendarDatesText(editGroup.representative.holiday_dates),
                closureDatesText: calendarDatesText(editGroup.representative.closure_dates),
                isActive: editGroup.representative.is_active,
              },
              applyPlanningLabel: "Redeployer immediatement les creneaux bloquants apres mise a jour",
              existingEntries: editGroup.items.map((item) => ({ calendarId: item.id, locationId: item.location_id })),
              errorText: modalErrorMessage,
              footerNote: editGroup.is_fully_removed
                ? "Ce bloc est retire du planning. Vous pouvez maintenant le supprimer definitivement si vous n en avez plus besoin."
                : "Pour ajouter un creneau oublie, ajoutez simplement une ligne puis enregistrez le bloc.",
              extraActions: editGroup.is_fully_removed ? (
                <>
                  <form id={`calendar-group-delete-modal-${editGroup.key}`} action={bulkAdminQuoteSchoolCalendarsAction}>
                    {editGroup.items.map((item) => (
                      <input key={`calendar-group-delete-modal-${item.id}`} type="hidden" name="calendar_ids" value={item.id} />
                    ))}
                    <input type="hidden" name="bulk_action" value="DELETE" />
                    <input type="hidden" name="return_to" value={buildCalendarsPath({
                      locationFilter,
                      deploymentFilter,
                      statusFilter,
                      generatedFor,
                      previewGroup: previewGroupKey,
                      editGroup: editGroup.key,
                      generatedGroup: generatedGroupKey,
                    })} />
                    <input type="hidden" name="success_return_to" value={basePath} />
                  </form>
                  <ConfirmSubmitButton
                    formId={`calendar-group-delete-modal-${editGroup.key}`}
                    label="Supprimer ce bloc"
                    title="Supprimer ce bloc retire ?"
                    description={`Le bloc ${editGroup.name} sera supprime pour ${editGroup.items.length} local(aux). Cette action est irreversible.`}
                    confirmLabel="Supprimer le bloc"
                    className="danger"
                  />
                </>
              ) : null,
            })}
          </article>
        </section>
      ) : null}

      {previewGroup ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>Previsualisation detaillee du deploiement</h3>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                editGroup: editGroupKey,
                generatedGroup: generatedGroupKey,
              })}
            >
              Fermer
            </Link>
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

      {generatedGroup ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <div>
              <h3>Tous les creneaux du bloc</h3>
              <p className="muted">
                {generatedGroup.name} · {generatedGroup.school_year_label} · {generatedGroup.location_names.join(", ")}
              </p>
            </div>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                generatedFor,
                previewGroup: previewGroupKey,
                editGroup: editGroupKey,
              })}
            >
              Fermer
            </Link>
          </div>
          {generatedGroupSlots.length === 0 ? (
            <p className="muted">Aucun creneau genere pour ce bloc.</p>
          ) : (
            <div className="table-wrap top-gap-sm">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Local</th>
                    <th>Date</th>
                    <th>Raisons</th>
                    <th>Statut</th>
                    <th>Session</th>
                  </tr>
                </thead>
                <tbody>
                  {generatedGroupSlots.map((slot) => (
                    <tr key={`${slot.session_id}-${slot.location_name}`}>
                      <td>{slot.location_name}</td>
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

      {selectedCalendar ? (
        <section className="card">
          <div className="row spread wrap gap-sm">
            <h3>Creneaux bloquants generes</h3>
            <Link
              className="ghost"
              href={buildCalendarsPath({
                locationFilter,
                deploymentFilter,
                statusFilter,
                previewGroup: previewGroupKey,
                editGroup: editGroupKey,
                generatedGroup: generatedGroupKey,
              })}
            >
              Fermer
            </Link>
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
