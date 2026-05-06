import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../../../lib/backend";
import type {
  AdminPlanningSimulationOut,
  AdminPlanningSimulationSlotOut,
  CourseTypeOut,
  LocationOut,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";

type SearchParams = Record<string, string | string[] | undefined>;

type LocationGroup = {
  locationId: string;
  locationName: string;
  timezone: string | null;
  slots: AdminPlanningSimulationSlotOut[];
};

type ActivityGroup = {
  courseTypeId: string;
  courseTypeName: string;
  colorHex: string | null;
  slots: AdminPlanningSimulationSlotOut[];
};

function readParam(params: SearchParams, key: string): string {
  const raw = params[key];
  if (Array.isArray(raw)) {
    return raw[0] ?? "";
  }
  return raw ?? "";
}

async function loadPlanningSimulationLocations(
  token: string,
): Promise<{ ok: true; data: LocationOut[] } | { ok: false; message: string }> {
  const directResult = await backendRequest<LocationOut[]>("/api/v1/locations?active=true", {}, token);
  if (directResult.ok) {
    return directResult;
  }
  const legacyResult = await backendRequest<LocationOut[]>("/api/v1/catalogue/locations?active=true", {}, token);
  if (legacyResult.ok) {
    return legacyResult;
  }
  return { ok: false, message: `${directResult.message} | ${legacyResult.message}` };
}

function text(language: UiLanguage, fr: string, en: string): string {
  return language === "en" ? en : fr;
}

function formatDateOnly(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), { dateStyle: "medium" });
}

function formatDateTime(value: string | null, language: UiLanguage): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(localeForUiLanguage(language), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatSeasonWindow(slot: AdminPlanningSimulationSlotOut, language: UiLanguage): string {
  const datesCount = slot.occurrence_count;
  const seasonSpan =
    slot.first_date && slot.last_date
      ? `${text(language, "du", "from")} ${formatDateOnly(slot.first_date, language)} ${text(language, "au", "to")} ${formatDateOnly(slot.last_date, language)}`
      : text(language, "Periode non renseignee", "Missing season range");
  return `${datesCount} ${text(language, "date(s)", "occurrence(s)")} · ${seasonSpan}`;
}

function formatCapacity(slot: AdminPlanningSimulationSlotOut): string {
  if (slot.capacity_min === null && slot.capacity_max === null) {
    return "-";
  }
  if (slot.capacity_min !== null && slot.capacity_max !== null && slot.capacity_min !== slot.capacity_max) {
    return `${slot.capacity_min}-${slot.capacity_max}`;
  }
  return String(slot.capacity ?? slot.capacity_max ?? slot.capacity_min ?? "-");
}

function fillPercent(value: number | null): number {
  if (value === null || !Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

function projectionTone(slot: AdminPlanningSimulationSlotOut): "critical" | "warning" | "ok" {
  if (slot.remaining_capacity !== null && slot.remaining_capacity < 0) {
    return "critical";
  }
  if (slot.projected_fill_rate !== null && slot.projected_fill_rate >= 0.9) {
    return "warning";
  }
  return "ok";
}

function noteList(slot: AdminPlanningSimulationSlotOut, language: UiLanguage): string[] {
  const notes = [...slot.notes];
  if (slot.quote_only) {
    notes.unshift(text(language, "Pas de serie live raccordee a ce creneau devis.", "No live series is linked to this quote slot."));
  }
  if (slot.remaining_capacity !== null && slot.remaining_capacity < 0) {
    notes.unshift(
      text(
        language,
        "Projection au-dessus de la capacite. Arbitrage ou ouverture de place a prevoir.",
        "Projected occupancy exceeds capacity. Arbitration or additional seats are required.",
      ),
    );
  }
  return notes;
}

function groupByLocation(slots: AdminPlanningSimulationSlotOut[]): LocationGroup[] {
  const grouped = new Map<string, LocationGroup>();
  for (const slot of slots) {
    const locationId = slot.location_id || "__unknown__";
    const current = grouped.get(locationId);
    if (current) {
      current.slots.push(slot);
      continue;
    }
    grouped.set(locationId, {
      locationId,
      locationName: slot.location_name,
      timezone: slot.location_timezone,
      slots: [slot],
    });
  }
  return Array.from(grouped.values()).sort((a, b) => a.locationName.localeCompare(b.locationName, "fr"));
}

function groupByActivity(slots: AdminPlanningSimulationSlotOut[]): ActivityGroup[] {
  const grouped = new Map<string, ActivityGroup>();
  for (const slot of slots) {
    const activityId = slot.course_type_id || `__${slot.course_type_name}`;
    const current = grouped.get(activityId);
    if (current) {
      current.slots.push(slot);
      continue;
    }
    grouped.set(activityId, {
      courseTypeId: activityId,
      courseTypeName: slot.course_type_name,
      colorHex: slot.course_type_color_hex,
      slots: [slot],
    });
  }
  return Array.from(grouped.values()).sort((a, b) => a.courseTypeName.localeCompare(b.courseTypeName, "fr"));
}

function sumPipeline(summary: AdminPlanningSimulationOut["summary"]): number {
  return summary.approved_quotes_count + summary.pending_quotes_count + summary.draft_quotes_count;
}

export default async function AdminSimulationPlanningPage({
  searchParams,
}: {
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login?error_code=session_expired");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok || meResult.data.role !== "admin") {
    redirect("/login?error_code=admin_access_required");
  }

  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const requestedSchoolYear = readParam(searchParams ?? {}, "school_year").trim();
  const requestedLocationId = readParam(searchParams ?? {}, "location_id").trim();
  const requestedActivityId = readParam(searchParams ?? {}, "activity_id").trim();

  const simulationQuery = new URLSearchParams();
  if (requestedSchoolYear) simulationQuery.set("school_year_label", requestedSchoolYear);
  if (requestedLocationId) simulationQuery.set("location_id", requestedLocationId);
  if (requestedActivityId) simulationQuery.set("activity_id", requestedActivityId);
  const simulationPath = simulationQuery.size
    ? `/api/v1/admin/plannings/simulation?${simulationQuery.toString()}`
    : "/api/v1/admin/plannings/simulation";

  const [locationsResult, courseTypesResult, simulationResult] = await Promise.all([
    loadPlanningSimulationLocations(token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types?active=true", {}, token),
    backendRequest<AdminPlanningSimulationOut>(simulationPath, {}, token),
  ]);

  const locations = locationsResult.ok ? locationsResult.data : [];
  const courseTypes = courseTypesResult.ok ? courseTypesResult.data : [];
  const simulation = simulationResult.ok ? simulationResult.data : null;
  const locationsError = locationsResult.ok ? null : locationsResult.message;
  const courseTypesError = courseTypesResult.ok ? null : courseTypesResult.message;
  const simulationError = simulationResult.ok ? null : simulationResult.message;

  const effectiveSchoolYear = simulation?.school_year_label || requestedSchoolYear || "";
  const availableSchoolYears = simulation?.available_school_years ?? [effectiveSchoolYear].filter(Boolean);
  const groupedLocations = simulation ? groupByLocation(simulation.slots) : [];

  return (
    <section className="admin-page-grid">
      <section className="card">
        <div className="row spread">
          <div>
            <h2>{text(language, "Simulation planning", "Planning simulation")}</h2>
            <p className="muted">
              {text(
                language,
                "Lecture de charge par saison : capacite live, inscriptions reelles et pression devis sur chaque creneau d'une semaine type.",
                "Season-based capacity view: live capacity, real enrollments, and quote pressure on each slot of a typical week.",
              )}
            </p>
          </div>
          <div className="row">
            <Link className="ghost" href="/admin">
              {text(language, "Retour au planning", "Back to planning")}
            </Link>
            <Link className="ghost" href="/admin/config?section=activities">
              {text(language, "Catalogue des activites", "Activities catalog")}
            </Link>
          </div>
        </div>
      </section>

      <section className="card">
        <form className="simulation-planning-toolbar" method="get">
          <label>
            <span>{text(language, "Saison", "Season")}</span>
            <select name="school_year" defaultValue={effectiveSchoolYear}>
              {availableSchoolYears.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>{text(language, "Local", "Location")}</span>
            <select name="location_id" defaultValue={requestedLocationId}>
              <option value="">{text(language, "Tous les locaux", "All locations")}</option>
              {locations
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name, "fr"))
                .map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
            </select>
          </label>

          <label>
            <span>{text(language, "Type de cours", "Course type")}</span>
            <select name="activity_id" defaultValue={requestedActivityId}>
              <option value="">{text(language, "Tous les types", "All course types")}</option>
              {courseTypes
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name, "fr"))
                .map((courseType) => (
                  <option key={courseType.id} value={courseType.id}>
                    {courseType.name}
                  </option>
                ))}
            </select>
          </label>

          <div className="simulation-planning-toolbar-actions">
            <button type="submit" className="simulation-planning-submit">
              {text(language, "Mettre a jour", "Refresh")}
            </button>
            <Link className="ghost" href="/admin/simulation-planning">
              {text(language, "Reinitialiser", "Reset")}
            </Link>
          </div>
        </form>
      </section>

      {locationsError ? (
        <section className="flash-err">
          {text(language, "Impossible de charger les lieux : ", "Unable to load locations: ")}
          {locationsError}
        </section>
      ) : null}

      {courseTypesError ? (
        <section className="flash-err">
          {text(language, "Impossible de charger les activites : ", "Unable to load activities: ")}
          {courseTypesError}
        </section>
      ) : null}

      {!simulation ? (
        <section className="flash-err">
          {text(language, "Impossible de charger la simulation : ", "Unable to load the simulation: ")}
          {simulationError}
        </section>
      ) : (
        <>
          <section className="grid cols-5 simulation-planning-summary-grid">
            <article className="card">
              <h3>{text(language, "Creneaux suivis", "Tracked slots")}</h3>
              <p className="muted">
                {text(language, "Semaine type consolidee sur la saison.", "Typical week consolidated over the season.")}
              </p>
              <strong>{simulation.summary.slot_count}</strong>
            </article>

            <article className="card">
              <h3>{text(language, "Locaux visibles", "Visible locations")}</h3>
              <p className="muted">
                {text(language, "Locaux avec un creneau ou une pression devis.", "Locations with slots or quote pressure.")}
              </p>
              <strong>{simulation.summary.location_count}</strong>
            </article>

            <article className="card">
              <h3>{text(language, "Inscriptions reelles", "Live enrollments")}</h3>
              <p className="muted">
                {text(language, "Eleves deja presents sur les series live.", "Students already present on live series.")}
              </p>
              <strong>{simulation.summary.booked_count}</strong>
            </article>

            <article className="card">
              <h3>{text(language, "Pipeline devis", "Quote pipeline")}</h3>
              <p className="muted">
                {text(language, "Valides, en attente de validation et en cours.", "Approved, pending validation, and in progress.")}
              </p>
              <strong>{sumPipeline(simulation.summary)}</strong>
            </article>

            <article className="card">
              <h3>{text(language, "Sans serie live", "Without live series")}</h3>
              <p className="muted">
                {text(language, "Creneaux devis non relies a une serie existante.", "Quote slots not linked to an existing live series.")}
              </p>
              <strong>{simulation.summary.quote_only_slot_count}</strong>
            </article>
          </section>

          <section className="card simulation-planning-legend">
            <div>
              <h3>{text(language, "Lecture de la charge", "How to read the load")}</h3>
              <p className="muted">
                {text(
                  language,
                  "Reel = eleves deja inscrits. Valides = devis approuves non integres. En attente = devis envoyes. En cours = brouillons admin.",
                  "Live = already enrolled students. Approved = approved quotes not integrated yet. Pending = sent quotes. In progress = admin drafts.",
                )}
              </p>
            </div>
            <div className="simulation-planning-legend-chips">
              <span className="simulation-chip simulation-chip-live">{text(language, "Reel", "Live")}</span>
              <span className="simulation-chip simulation-chip-approved">{text(language, "Valide", "Approved")}</span>
              <span className="simulation-chip simulation-chip-pending">{text(language, "En attente", "Pending")}</span>
              <span className="simulation-chip simulation-chip-draft">{text(language, "En cours", "In progress")}</span>
            </div>
            <p className="muted">
              {text(language, "Mise a jour :", "Updated:")} {formatDateTime(simulation.generated_at, language)}
            </p>
          </section>

          {groupedLocations.length === 0 ? (
            <section className="card">
              <h3>{text(language, "Aucun creneau visible", "No visible slot")}</h3>
              <p className="muted">
                {text(
                  language,
                  "Aucun creneau n'entre dans les filtres de cette saison. Elargissez le filtre lieu ou type de cours.",
                  "No slot matches the current filters for this season. Broaden the location or course type filter.",
                )}
              </p>
            </section>
          ) : (
            groupedLocations.map((locationGroup) => (
              <section className="card simulation-location-card" key={locationGroup.locationId}>
                <div className="simulation-location-header">
                  <div>
                    <h3>{locationGroup.locationName}</h3>
                    <p className="muted">
                      {locationGroup.slots.length} {text(language, "creneau(x) suivi(s)", "tracked slot(s)")}
                      {locationGroup.timezone ? ` · ${locationGroup.timezone}` : ""}
                    </p>
                  </div>
                </div>

                <div className="simulation-activity-stack">
                  {groupByActivity(locationGroup.slots).map((activityGroup) => (
                    <section className="simulation-activity-block" key={activityGroup.courseTypeId}>
                      <div className="simulation-activity-heading">
                        <div className="simulation-activity-label">
                          <span
                            className="simulation-activity-swatch"
                            style={{ backgroundColor: activityGroup.colorHex || "#D6A34A" }}
                          />
                          <strong>{activityGroup.courseTypeName}</strong>
                        </div>
                        <span className="muted">
                          {activityGroup.slots.length} {text(language, "creneau(x)", "slot(s)")}
                        </span>
                      </div>

                      <div className="table-wrap">
                        <table className="simulation-planning-table">
                          <thead>
                            <tr>
                              <th>{text(language, "Creneau", "Slot")}</th>
                              <th>{text(language, "Serie active", "Live series")}</th>
                              <th>{text(language, "Capacite", "Capacity")}</th>
                              <th>{text(language, "Reel", "Live")}</th>
                              <th>{text(language, "Valides", "Approved")}</th>
                              <th>{text(language, "Attente", "Pending")}</th>
                              <th>{text(language, "En cours", "In progress")}</th>
                              <th>{text(language, "Projection", "Projection")}</th>
                              <th>{text(language, "Lecture", "Readout")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activityGroup.slots.map((slot) => {
                              const notes = noteList(slot, language);
                              const tone = projectionTone(slot);
                              const projectedPercent = fillPercent(slot.projected_fill_rate);
                              const livePercent = fillPercent(slot.fill_rate);
                              const capacity = formatCapacity(slot);
                              const projectedLabel =
                                slot.capacity !== null
                                  ? `${slot.projected_count}/${slot.capacity}`
                                  : String(slot.projected_count);
                              return (
                                <tr key={slot.slot_key}>
                                  <td>
                                    <strong>
                                      {slot.weekday_label} · {slot.start_time}-{slot.end_time}
                                    </strong>
                                  </td>
                                  <td>
                                    <div>{formatSeasonWindow(slot, language)}</div>
                                    {slot.quote_only ? (
                                      <div className="simulation-inline-note">
                                        {text(language, "Devis sans serie live", "Quote without live series")}
                                      </div>
                                    ) : null}
                                  </td>
                                  <td>{capacity}</td>
                                  <td>{slot.booked_count}</td>
                                  <td>{slot.approved_quotes_count}</td>
                                  <td>{slot.pending_quotes_count}</td>
                                  <td>{slot.draft_quotes_count}</td>
                                  <td>
                                    <strong>{projectedLabel}</strong>
                                    {slot.remaining_capacity !== null ? (
                                      <div className={`simulation-inline-note simulation-tone-${tone}`}>
                                        {slot.remaining_capacity >= 0
                                          ? text(language, `{count} place(s) restante(s)`, `{count} seat(s) left`).replace(
                                              "{count}",
                                              String(slot.remaining_capacity),
                                            )
                                          : text(language, `{count} place(s) en surcharge`, `{count} seat(s) over`).replace(
                                              "{count}",
                                              String(Math.abs(slot.remaining_capacity)),
                                            )}
                                      </div>
                                    ) : null}
                                  </td>
                                  <td>
                                    <div className="simulation-fill">
                                      <div className="simulation-fill-track">
                                        <span
                                          className="simulation-fill-live"
                                          style={{ width: `${livePercent}%` }}
                                        />
                                        <span
                                          className={`simulation-fill-projected simulation-fill-projected-${tone}`}
                                          style={{ width: `${projectedPercent}%` }}
                                        />
                                      </div>
                                      <div className="simulation-inline-note">
                                        {text(language, "Reel", "Live")} {livePercent}% · {text(language, "Projete", "Projected")}{" "}
                                        {projectedPercent}%
                                      </div>
                                      {notes.map((note) => (
                                        <div className="simulation-inline-note" key={note}>
                                          {note}
                                        </div>
                                      ))}
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  ))}
                </div>
              </section>
            ))
          )}
        </>
      )}
    </section>
  );
}
