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

type CalendarDayGroup = {
  weekday: number;
  weekdayLabel: string;
  slots: AdminPlanningSimulationSlotOut[];
};

const VACATION_COURSE_TYPE_CODE = "VACATION_DAY";

type SlotPeopleSection = {
  label: string;
  people: string[];
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

function parseTimeToMinutes(value: string): number | null {
  const [hoursRaw, minutesRaw = "0"] = value.split(":");
  const hours = Number(hoursRaw);
  const minutes = Number(minutesRaw);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  return hours * 60 + minutes;
}

function formatMinutes(value: number): string {
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function calendarBounds(slots: AdminPlanningSimulationSlotOut[]): { start: number; end: number; height: number } {
  const starts = slots
    .map((slot) => parseTimeToMinutes(slot.start_time))
    .filter((value): value is number => value !== null);
  const ends = slots
    .map((slot) => parseTimeToMinutes(slot.end_time))
    .filter((value): value is number => value !== null);
  const first = starts.length ? Math.min(...starts) : 8 * 60;
  const last = ends.length ? Math.max(...ends) : 20 * 60;
  const start = Math.max(7 * 60, Math.floor(first / 60) * 60);
  const end = Math.min(23 * 60, Math.ceil(last / 60) * 60);
  const duration = Math.max(60, end - start);
  return { start, end, height: Math.max(360, Math.round(duration * 0.9)) };
}

function calendarHourTicks(bounds: { start: number; end: number }): number[] {
  const ticks: number[] = [];
  for (let cursor = bounds.start; cursor <= bounds.end; cursor += 60) {
    ticks.push(cursor);
  }
  return ticks;
}

function groupByWeekday(slots: AdminPlanningSimulationSlotOut[]): CalendarDayGroup[] {
  const grouped = new Map<number, CalendarDayGroup>();
  for (const slot of slots) {
    const current = grouped.get(slot.weekday);
    if (current) {
      current.slots.push(slot);
      continue;
    }
    grouped.set(slot.weekday, {
      weekday: slot.weekday,
      weekdayLabel: slot.weekday_label,
      slots: [slot],
    });
  }
  return Array.from(grouped.values())
    .sort((a, b) => a.weekday - b.weekday)
    .map((dayGroup) => ({
      ...dayGroup,
      slots: dayGroup.slots
        .slice()
        .sort(
          (a, b) =>
            (parseTimeToMinutes(a.start_time) ?? 0) - (parseTimeToMinutes(b.start_time) ?? 0) ||
            a.course_type_name.localeCompare(b.course_type_name, "fr"),
        ),
    }));
}

function calendarSlotStyle(
  slot: AdminPlanningSimulationSlotOut,
  bounds: { start: number; end: number; height: number },
): { top: string; height: string } {
  const start = parseTimeToMinutes(slot.start_time) ?? bounds.start;
  const end = parseTimeToMinutes(slot.end_time) ?? start + 60;
  const total = Math.max(60, bounds.end - bounds.start);
  const top = ((Math.max(bounds.start, start) - bounds.start) / total) * 100;
  const height = (Math.max(30, end - start) / total) * 100;
  return {
    top: `${Math.max(0, Math.min(100, top))}%`,
    height: `${Math.max(8, height)}%`,
  };
}

function projectedSlotLabel(slot: AdminPlanningSimulationSlotOut): string {
  return slot.capacity !== null ? `${slot.projected_count}/${slot.capacity}` : String(slot.projected_count);
}

function slotPeopleSections(slot: AdminPlanningSimulationSlotOut, language: UiLanguage): SlotPeopleSection[] {
  return [
    { label: text(language, "Inscrits", "Enrolled"), people: slot.booked_students },
    { label: text(language, "Devis valides", "Approved quotes"), people: slot.approved_quote_students },
    { label: text(language, "En attente", "Pending"), people: slot.pending_quote_students },
    { label: text(language, "Brouillons", "Drafts"), people: slot.draft_quote_students },
  ].filter((section) => section.people.length > 0);
}

function slotHoverTitle(slot: AdminPlanningSimulationSlotOut, language: UiLanguage): string {
  const sections = slotPeopleSections(slot, language);
  if (sections.length === 0) {
    return text(language, "Aucun eleve inscrit ou devis en attente sur ce creneau.", "No enrolled student or pending quote on this slot.");
  }
  return sections.map((section) => `${section.label}: ${section.people.join(", ")}`).join("\n");
}

function slotStatusBreakdown(slot: AdminPlanningSimulationSlotOut, language: UiLanguage): Array<{ label: string; count: number; className: string }> {
  return [
    { label: text(language, "Reel", "Live"), count: slot.booked_count, className: "simulation-slot-meta-live" },
    { label: text(language, "Valide", "Approved"), count: slot.approved_quotes_count, className: "simulation-slot-meta-approved" },
    { label: text(language, "Attente", "Pending"), count: slot.pending_quotes_count, className: "simulation-slot-meta-pending" },
    { label: text(language, "Brouillon", "Draft"), count: slot.draft_quotes_count, className: "simulation-slot-meta-draft" },
  ];
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
  const courseTypes = courseTypesResult.ok
    ? courseTypesResult.data.filter((courseType) => courseType.code.toUpperCase() !== VACATION_COURSE_TYPE_CODE)
    : [];
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
          <section className="card simulation-planning-overview">
            <div className="simulation-overview-metrics" aria-label={text(language, "Synthese simulation", "Simulation summary")}>
              <div>
                <span>{text(language, "Creneaux", "Slots")}</span>
                <strong>{simulation.summary.slot_count}</strong>
              </div>
              <div>
                <span>{text(language, "Locaux", "Locations")}</span>
                <strong>{simulation.summary.location_count}</strong>
              </div>
              <div>
                <span>{text(language, "Inscrits", "Enrolled")}</span>
                <strong>{simulation.summary.booked_count}</strong>
              </div>
              <div>
                <span>{text(language, "Valides", "Approved")}</span>
                <strong>{simulation.summary.approved_quotes_count}</strong>
              </div>
              <div>
                <span>{text(language, "En attente", "Pending")}</span>
                <strong>{simulation.summary.pending_quotes_count}</strong>
              </div>
              <div>
                <span>{text(language, "Brouillons", "Drafts")}</span>
                <strong>{simulation.summary.draft_quotes_count}</strong>
              </div>
              <div>
                <span>{text(language, "Sans live", "Without live")}</span>
                <strong>{simulation.summary.quote_only_slot_count}</strong>
              </div>
            </div>
            <div className="simulation-overview-side">
              <div className="simulation-planning-legend-chips">
                <span className="simulation-chip simulation-chip-live">{text(language, "Reel", "Live")}</span>
                <span className="simulation-chip simulation-chip-approved">{text(language, "Valide", "Approved")}</span>
                <span className="simulation-chip simulation-chip-pending">{text(language, "En attente", "Pending")}</span>
                <span className="simulation-chip simulation-chip-draft">{text(language, "En cours", "In progress")}</span>
              </div>
              <p className="muted">
                {text(language, "Mise a jour :", "Updated:")} {formatDateTime(simulation.generated_at, language)}
              </p>
            </div>
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

                <section className="simulation-calendar-view">
                  <div className="simulation-calendar-heading">
                    <div>
                      <h4>{text(language, "Vue calendrier - semaine type", "Calendar view - typical week")}</h4>
                      <p className="muted">
                        {text(
                          language,
                          "Chaque bloc represente un creneau. La couleur indique l'etat de remplissage projete.",
                          "Each block represents a slot. The color shows the projected occupancy status.",
                        )}
                      </p>
                    </div>
                    <div className="simulation-calendar-scale" aria-label={text(language, "Legende calendrier", "Calendar legend")}>
                      <span>
                        <i className="simulation-calendar-dot simulation-calendar-dot-ok" />{" "}
                        {text(language, "Disponible", "Available")}
                      </span>
                      <span>
                        <i className="simulation-calendar-dot simulation-calendar-dot-warning" />{" "}
                        {text(language, "Presque plein", "Nearly full")}
                      </span>
                      <span>
                        <i className="simulation-calendar-dot simulation-calendar-dot-critical" />{" "}
                        {text(language, "Surcharge", "Over capacity")}
                      </span>
                    </div>
                  </div>

                  {(() => {
                    const bounds = calendarBounds(locationGroup.slots);
                    const ticks = calendarHourTicks(bounds);
                    const dayGroups = groupByWeekday(locationGroup.slots);
                    return (
                      <div className="simulation-calendar-scroll">
                        <div
                          className="simulation-calendar-grid"
                          style={{
                            gridTemplateColumns: `72px repeat(${Math.max(1, dayGroups.length)}, minmax(190px, 1fr))`,
                          }}
                        >
                          <div className="simulation-calendar-corner" />
                          {dayGroups.map((dayGroup) => (
                            <div className="simulation-calendar-day-head" key={dayGroup.weekday}>
                              <strong>{dayGroup.weekdayLabel}</strong>
                              <span>
                                {dayGroup.slots.length} {text(language, "creneau(x)", "slot(s)")}
                              </span>
                            </div>
                          ))}

                          <div className="simulation-calendar-hours" style={{ height: `${bounds.height}px` }}>
                            {ticks.map((tick) => (
                              <span
                                key={tick}
                                style={{
                                  top: `${((tick - bounds.start) / Math.max(60, bounds.end - bounds.start)) * 100}%`,
                                }}
                              >
                                {formatMinutes(tick)}
                              </span>
                            ))}
                          </div>

                          {dayGroups.map((dayGroup) => (
                            <div
                              className="simulation-calendar-day"
                              key={dayGroup.weekday}
                              style={{ height: `${bounds.height}px` }}
                            >
                              {ticks.map((tick) => (
                                <span
                                  className="simulation-calendar-rule"
                                  key={tick}
                                  style={{
                                    top: `${((tick - bounds.start) / Math.max(60, bounds.end - bounds.start)) * 100}%`,
                                  }}
                                />
                              ))}
                              {dayGroup.slots.map((slot) => {
                                const tone = projectionTone(slot);
                                const percent = fillPercent(slot.projected_fill_rate);
                                const peopleSections = slotPeopleSections(slot, language);
                                return (
                                  <article
                                    className={`simulation-calendar-slot simulation-calendar-slot-${tone}`}
                                    key={slot.slot_key}
                                    style={calendarSlotStyle(slot, bounds)}
                                    tabIndex={0}
                                    title={slotHoverTitle(slot, language)}
                                  >
                                    <div className="simulation-calendar-slot-top">
                                      <strong>
                                        {slot.start_time}-{slot.end_time}
                                      </strong>
                                      <span>{projectedSlotLabel(slot)}</span>
                                    </div>
                                    <p>{slot.course_type_name}</p>
                                    <div className="simulation-calendar-slot-fill" aria-hidden="true">
                                      <span style={{ width: `${percent}%` }} />
                                    </div>
                                    <div className="simulation-calendar-slot-meta">
                                      {slotStatusBreakdown(slot, language).map((item) => (
                                        <span className={item.className} key={`${slot.slot_key}-${item.className}`}>
                                          {item.label} {item.count}
                                        </span>
                                      ))}
                                    </div>
                                    <div className="simulation-calendar-slot-detail" role="tooltip">
                                      {peopleSections.length === 0 ? (
                                        <p>
                                          {text(
                                            language,
                                            "Aucun eleve inscrit ou devis en attente.",
                                            "No enrolled student or pending quote.",
                                          )}
                                        </p>
                                      ) : (
                                        peopleSections.map((section) => (
                                          <div className="simulation-calendar-people-section" key={section.label}>
                                            <strong>{section.label}</strong>
                                            <ul>
                                              {section.people.slice(0, 8).map((person) => (
                                                <li key={person}>{person}</li>
                                              ))}
                                              {section.people.length > 8 ? <li>+{section.people.length - 8}</li> : null}
                                            </ul>
                                          </div>
                                        ))
                                      )}
                                    </div>
                                  </article>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                </section>

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
                              const projectedLabel = projectedSlotLabel(slot);
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
