import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { CSSProperties } from "react";

import { backendRequest } from "../../../lib/backend";
import { adminUpdatePlanningSimulationTeacherAssignmentAction } from "../../../lib/actions";
import { hasAdminPermission } from "../../../lib/admin-access";
import type {
  AdminProfessorOut,
  AdminPlanningSimulationOut,
  AdminPlanningSimulationSlotOut,
  AdminPlanningSimulationTeacherNeedsOut,
  CourseTypeOut,
  LocationOut,
  UserOut,
} from "../../../lib/types";
import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage } from "../../../lib/ui-i18n";
import { SimulationPlanningFilterForm } from "./filter-form";
import { TeacherAssignmentGridCell } from "./assignment-grid-cell";

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

type PositionedCalendarSlot = {
  slot: AdminPlanningSimulationSlotOut;
  column: number;
  columns: number;
};

type SimulationView = "capacity" | "teacher_needs";

const VACATION_COURSE_TYPE_CODE = "VACATION_DAY";
const DEFAULT_SIMULATION_SCHOOL_YEAR = "2026-2027";
const DEFAULT_SIMULATION_ACTIVITY_FILTER = "__collective_piano__";
const ALL_SIMULATION_ACTIVITY_FILTER = "__all__";
const ACTIVITY_FILTER_PREFIX = "activity:";
const TEACHER_NEEDS_EXCLUDED_LOCATION_NAME = "Bar-le-Duc";

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

function simulationViewFromParams(params: SearchParams): SimulationView {
  return readParam(params, "view").trim() === "teacher_needs" ? "teacher_needs" : "capacity";
}

function activityFilterFromParams(params: SearchParams, view: SimulationView): string {
  const requestedFilter = readParam(params, "activity_filter").trim();
  if (requestedFilter) {
    return requestedFilter;
  }
  const legacyActivityId = readParam(params, "activity_id").trim();
  if (legacyActivityId) {
    return `${ACTIVITY_FILTER_PREFIX}${legacyActivityId}`;
  }
  return view === "teacher_needs" ? ALL_SIMULATION_ACTIVITY_FILTER : DEFAULT_SIMULATION_ACTIVITY_FILTER;
}

function isOnlineSolfegeCourseType(courseType: CourseTypeOut): boolean {
  const searchable = `${courseType.code} ${courseType.name}`
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr");
  return courseType.mode.toUpperCase() === "ONLINE" && searchable.includes("solfege");
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

function formatTeachingMinutes(minutes: number, language: UiLanguage): string {
  const safeMinutes = Math.max(0, Math.floor(minutes));
  const hours = Math.floor(safeMinutes / 60);
  const remainingMinutes = safeMinutes % 60;
  if (hours === 0) {
    return `${remainingMinutes} min`;
  }
  if (remainingMinutes === 0) {
    return `${hours} h`;
  }
  return `${hours} h ${String(remainingMinutes).padStart(2, "0")}`;
}

function planningDimensionMatches(
  slotId: string | null,
  slotName: string,
  rowId: string | null,
  rowName: string,
): boolean {
  if (slotId && rowId) {
    return slotId === rowId;
  }
  return slotName.trim().toLocaleLowerCase("fr") === rowName.trim().toLocaleLowerCase("fr");
}

function teacherSlotsForTimelineCell(
  slots: AdminPlanningSimulationSlotOut[],
  weekday: number,
  locationId: string | null,
  locationName: string,
  courseTypeId: string | null,
  courseTypeName: string,
  bucketStart: string,
  bucketEnd: string,
): AdminPlanningSimulationSlotOut[] {
  const bucketStartMinutes = parseTimeToMinutes(bucketStart);
  const bucketEndMinutes = parseTimeToMinutes(bucketEnd);
  if (bucketStartMinutes === null || bucketEndMinutes === null) {
    return [];
  }
  return slots.filter((slot) => {
    const slotStart = parseTimeToMinutes(slot.start_time);
    const slotEnd = parseTimeToMinutes(slot.end_time);
    return slot.weekday === weekday
      && planningDimensionMatches(slot.location_id, slot.location_name, locationId, locationName)
      && planningDimensionMatches(slot.course_type_id, slot.course_type_name, courseTypeId, courseTypeName)
      && slotStart !== null
      && slotEnd !== null
      && slotStart < bucketEndMinutes
      && slotEnd > bucketStartMinutes;
  });
}

function TeacherNeedsDashboard({
  needs,
  slots,
  professors,
  schoolYearLabel,
  returnTo,
  canEdit,
  language,
}: {
  needs: AdminPlanningSimulationTeacherNeedsOut;
  slots: AdminPlanningSimulationSlotOut[];
  professors: AdminProfessorOut[];
  schoolYearLabel: string;
  returnTo: string;
  canEdit: boolean;
  language: UiLanguage;
}): JSX.Element {
  const activeProfessors = professors.filter((professor) => professor.active);
  return (
    <div className="simulation-teacher-needs-shell">
      <section className="card simulation-teacher-needs-hero">
        <div>
          <span className="simulation-teacher-needs-eyebrow">
            {text(language, "Besoin prudent maximal", "Maximum conservative requirement")}
          </span>
          <strong>{needs.summary.mobilized_teachers}</strong>
          <p>
            {text(
              language,
              "professeur(s) a mobiliser sur la journee la plus chargee",
              "teacher(s) to mobilize on the busiest day",
            )}
          </p>
        </div>
        <dl className="simulation-teacher-needs-metrics">
          <div>
            <dt>{text(language, "Cours / semaine", "Courses / week")}</dt>
            <dd>{needs.summary.slot_count}</dd>
          </div>
          <div>
            <dt>{text(language, "Pic simultane", "Concurrent peak")}</dt>
            <dd>{needs.summary.peak_concurrent_teachers}</dd>
          </div>
          <div>
            <dt>{text(language, "Heures prof / semaine", "Teacher hours / week")}</dt>
            <dd>{formatTeachingMinutes(needs.summary.teaching_minutes, language)}</dd>
          </div>
          <div>
            <dt>{text(language, "Jours actifs", "Active days")}</dt>
            <dd>{needs.summary.active_day_count}</dd>
          </div>
        </dl>
      </section>

      <section className="simulation-teacher-rule-note" aria-label={text(language, "Regle de calcul", "Calculation rule")}>
        <strong>{text(language, "Calcul prudent", "Conservative calculation")}</strong>
        <span>
          {text(
            language,
            "Chaque type de cours est traite comme une competence distincte, un professeur reste sur le meme site pendant une demi-journee, Bar-le-Duc et le solfege en ligne sont exclus.",
            "Each course type is treated as a separate skill, a teacher remains at the same location for a half-day, and Bar-le-Duc and online music theory are excluded.",
          )}
        </span>
      </section>

      <section className="card simulation-teacher-needs-weekly">
        <div className="simulation-teacher-needs-section-head">
          <div>
            <h3>{text(language, "Besoin global par type de cours", "Overall requirement by course type")}</h3>
            <p className="muted">
              {text(
                language,
                "Le besoin a mobiliser tient compte des sites et separe chaque type de cours.",
                "The mobilization requirement accounts for locations and separates each course type.",
              )}
            </p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="simulation-teacher-needs-table">
            <thead>
              <tr>
                <th>{text(language, "Type de cours", "Course type")}</th>
                <th>{text(language, "Cours / semaine", "Courses / week")}</th>
                <th>{text(language, "Heures prof", "Teacher hours")}</th>
                <th>{text(language, "A mobiliser", "To mobilize")}</th>
                <th>{text(language, "Pic simultane", "Concurrent peak")}</th>
              </tr>
            </thead>
            <tbody>
              {needs.activities.map((activity) => (
                <tr key={activity.course_type_id || activity.course_type_name}>
                  <td>
                    <span className="simulation-teacher-activity-name">
                      <i style={{ backgroundColor: activity.course_type_color_hex || "#94C973" }} />
                      {activity.course_type_name}
                    </span>
                  </td>
                  <td>{activity.slot_count}</td>
                  <td>{formatTeachingMinutes(activity.teaching_minutes, language)}</td>
                  <td>
                    <strong>{activity.mobilized_teachers}</strong>
                  </td>
                  <td>
                    <strong>{activity.peak_concurrent_teachers}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="simulation-teacher-weekly-mobile">
          {needs.activities.map((activity) => (
            <article key={activity.course_type_id || activity.course_type_name}>
              <span className="simulation-teacher-activity-name">
                <i style={{ backgroundColor: activity.course_type_color_hex || "#94C973" }} />
                {activity.course_type_name}
              </span>
              <strong>{activity.mobilized_teachers} {text(language, "a mobiliser", "to mobilize")}</strong>
              <small>
                {activity.slot_count} {text(language, "cours", "courses")} · {formatTeachingMinutes(activity.teaching_minutes, language)} · {text(language, "pic", "peak")} {activity.peak_concurrent_teachers}
              </small>
            </article>
          ))}
        </div>
      </section>

      <nav className="simulation-teacher-day-nav" aria-label={text(language, "Acces rapide par jour", "Quick access by day")}>
        {needs.days.map((day) => (
          <a href={`#teacher-day-${day.weekday}`} key={day.weekday}>
            <span>{day.weekday_label}</span>
            <strong>{day.mobilized_teachers}</strong>
          </a>
        ))}
      </nav>

      <section className="simulation-teacher-day-list">
        {needs.days.map((day) => (
          <article className="card simulation-teacher-day-detail" id={`teacher-day-${day.weekday}`} key={day.weekday}>
            <header className="simulation-teacher-day-detail-head">
              <div>
                <span className="simulation-teacher-day-title">{day.weekday_label}</span>
                <small>
                  {day.first_start_time && day.last_end_time ? `${day.first_start_time} - ${day.last_end_time}` : "-"}
                </small>
              </div>
              <div className="simulation-teacher-day-kpis">
                <div className="primary">
                  <strong>{day.mobilized_teachers}</strong>
                  <span>{text(language, "a mobiliser", "to mobilize")}</span>
                </div>
                <div>
                  <strong>{day.peak_concurrent_teachers}</strong>
                  <span>{text(language, "au pic", "at peak")}</span>
                </div>
              </div>
            </header>
            <div className="simulation-teacher-day-summary">
              <span>
                <strong>{day.slot_count}</strong> {text(language, "cours", "courses")}
              </span>
              <span>
                <strong>{formatTeachingMinutes(day.teaching_minutes, language)}</strong> {text(language, "d enseignement", "of teaching")}
              </span>
            </div>

            <div className="simulation-teacher-timeline-desktop">
              <div className="simulation-teacher-timeline-scroll">
                <table style={{ minWidth: `${340 + day.time_buckets.length * 58}px` }}>
                  <thead>
                    <tr>
                      <th>{text(language, "Site et type de cours", "Location and course type")}</th>
                      {day.time_buckets.map((bucket) => (
                        <th key={bucket.start_time}>{bucket.start_time}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {day.timeline_rows.map((row) => (
                      <tr key={`${row.location_id || row.location_name}:${row.course_type_id || row.course_type_name}`}>
                        <th>
                          <small>{row.location_name}</small>
                          <span className="simulation-teacher-activity-name">
                            <i style={{ backgroundColor: row.course_type_color_hex || "#94C973" }} />
                            {row.course_type_name}
                          </span>
                        </th>
                        {row.bucket_teachers.map((teacherCount, index) => {
                          const bucket = day.time_buckets[index];
                          const cellSlots = bucket
                            ? teacherSlotsForTimelineCell(
                                slots,
                                day.weekday,
                                row.location_id,
                                row.location_name,
                                row.course_type_id,
                                row.course_type_name,
                                bucket.start_time,
                                bucket.end_time,
                              )
                            : [];
                          return (
                            <td
                              className={teacherCount > 0 ? `need need-${Math.min(teacherCount, 4)} interactive` : ""}
                              key={`${bucket?.start_time || index}`}
                            >
                              {teacherCount > 0 ? (
                                <TeacherAssignmentGridCell
                                  count={teacherCount}
                                  slots={cellSlots}
                                  professors={activeProfessors}
                                  schoolYearLabel={schoolYearLabel}
                                  returnTo={returnTo}
                                  canEdit={canEdit}
                                  language={language}
                                />
                              ) : ""}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th>{text(language, "Total simultane", "Concurrent total")}</th>
                      {day.time_buckets.map((bucket) => (
                        <td className={bucket.total_teachers > 0 ? "need total" : ""} key={bucket.start_time}>
                          {bucket.total_teachers || ""}
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>

            <div className="simulation-teacher-timeline-mobile">
              {day.time_buckets.map((bucket, bucketIndex) => {
                const activeRows = day.timeline_rows.filter((row) => (row.bucket_teachers[bucketIndex] || 0) > 0);
                if (activeRows.length === 0) {
                  return null;
                }
                return (
                  <section className="simulation-teacher-mobile-hour" key={bucket.start_time}>
                    <header>
                      <time>{bucket.start_time}–{bucket.end_time}</time>
                      <strong>{bucket.total_teachers} {text(language, "prof.", "teachers")}</strong>
                    </header>
                    <div>
                      {activeRows.map((row) => {
                        const teacherCount = row.bucket_teachers[bucketIndex] || 0;
                        const cellSlots = teacherSlotsForTimelineCell(
                          slots,
                          day.weekday,
                          row.location_id,
                          row.location_name,
                          row.course_type_id,
                          row.course_type_name,
                          bucket.start_time,
                          bucket.end_time,
                        );
                        return (
                          <article key={`${row.location_id || row.location_name}:${row.course_type_id || row.course_type_name}`}>
                            <span>{row.location_name}</span>
                            <span className="simulation-teacher-activity-name">
                              <i style={{ backgroundColor: row.course_type_color_hex || "#94C973" }} />
                              {row.course_type_name}
                            </span>
                            <TeacherAssignmentGridCell
                              count={teacherCount}
                              slots={cellSlots}
                              professors={activeProfessors}
                              schoolYearLabel={schoolYearLabel}
                              returnTo={returnTo}
                              canEdit={canEdit}
                              language={language}
                              mobile
                            />
                          </article>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function teacherAssignmentWarningLabel(code: string, language: UiLanguage): string {
  if (code === "TIME_OVERLAP") {
    return text(language, "Chevauchement horaire", "Schedule overlap");
  }
  if (code === "MULTI_SITE_HALF_DAY") {
    return text(language, "Plusieurs sites sur la même demi-journée", "Multiple locations in the same half-day");
  }
  return code;
}

function slotTeachingMinutes(slot: AdminPlanningSimulationSlotOut): number {
  const start = parseTimeToMinutes(slot.start_time);
  const end = parseTimeToMinutes(slot.end_time);
  return start === null || end === null || end <= start ? 0 : end - start;
}

function teacherAssignmentBulkGroups(
  slots: AdminPlanningSimulationSlotOut[],
  language: UiLanguage,
): Array<{ key: string; label: string; slots: AdminPlanningSimulationSlotOut[] }> {
  const groups = new Map<string, { key: string; label: string; slots: AdminPlanningSimulationSlotOut[] }>();
  for (const slot of slots) {
    const start = parseTimeToMinutes(slot.start_time) ?? 0;
    const halfDay = start < 13 * 60 ? "morning" : "afternoon";
    const key = `${slot.location_id || slot.location_name}:${halfDay}`;
    const label = `${slot.location_name} · ${halfDay === "morning" ? text(language, "matin", "morning") : text(language, "après-midi", "afternoon")}`;
    const existing = groups.get(key);
    if (existing) {
      existing.slots.push(slot);
    } else {
      groups.set(key, { key, label, slots: [slot] });
    }
  }
  return Array.from(groups.values()).sort((first, second) => first.label.localeCompare(second.label, "fr"));
}

function TeacherAssignmentBoard({
  slots,
  professors,
  schoolYearLabel,
  returnTo,
  canEdit,
  language,
}: {
  slots: AdminPlanningSimulationSlotOut[];
  professors: AdminProfessorOut[];
  schoolYearLabel: string;
  returnTo: string;
  canEdit: boolean;
  language: UiLanguage;
}): JSX.Element {
  const activeProfessors = professors.filter((professor) => professor.active);
  const assignedSlots = slots.filter((slot) => Boolean(slot.teacher_assignment_label));
  const confirmedSlots = assignedSlots.filter((slot) => slot.teacher_assignment_status === "CONFIRMED");
  const warningSlots = assignedSlots.filter((slot) => slot.teacher_assignment_warnings.length > 0);
  const dayGroups = groupByWeekday(slots);
  const teacherSummary = new Map<string, {
    slotCount: number;
    minutes: number;
    confirmed: number;
    warnings: number;
    professorId: string | null;
    slotKeys: string[];
  }>();

  for (const slot of assignedSlots) {
    const label = slot.teacher_assignment_label || "-";
    const current = teacherSummary.get(label) || {
      slotCount: 0,
      minutes: 0,
      confirmed: 0,
      warnings: 0,
      professorId: slot.teacher_assignment_professor_id,
      slotKeys: [],
    };
    current.slotCount += 1;
    current.minutes += slotTeachingMinutes(slot);
    current.confirmed += slot.teacher_assignment_status === "CONFIRMED" ? 1 : 0;
    current.warnings += slot.teacher_assignment_warnings.length > 0 ? 1 : 0;
    current.slotKeys.push(slot.slot_key);
    teacherSummary.set(label, current);
  }

  return (
    <section className="simulation-assignment-board">
      <datalist id="simulation-placeholder-teachers">
        <option value="Prof à confirmer 1" />
        <option value="Prof à confirmer 2" />
        <option value="Prof à confirmer 3" />
        <option value="Poste à recruter 1" />
        <option value="Renfort à prévoir" />
      </datalist>

      <section className="card simulation-assignment-overview">
        <div>
          <span className="simulation-teacher-needs-eyebrow">
            {text(language, "Organisation prévisionnelle", "Provisional organization")}
          </span>
          <h3>{text(language, "Prépositionnement des professeurs", "Provisional teacher assignments")}</h3>
          <p className="muted">
            {text(
              language,
              "Ces choix restent dans la simulation et ne modifient jamais le planning réel.",
              "These choices stay in the simulation and never modify the live schedule.",
            )}
          </p>
        </div>
        <dl>
          <div><dt>{text(language, "Affectés", "Assigned")}</dt><dd>{assignedSlots.length}/{slots.length}</dd></div>
          <div><dt>{text(language, "Confirmés", "Confirmed")}</dt><dd>{confirmedSlots.length}</dd></div>
          <div><dt>{text(language, "À pourvoir", "Unfilled")}</dt><dd>{Math.max(0, slots.length - assignedSlots.length)}</dd></div>
          <div className={warningSlots.length > 0 ? "warning" : ""}><dt>{text(language, "Alertes", "Warnings")}</dt><dd>{warningSlots.length}</dd></div>
        </dl>
      </section>

      {teacherSummary.size > 0 ? (
        <section className="card simulation-assignment-summary">
          <h3>{text(language, "Charge prévisionnelle par professeur", "Provisional workload by teacher")}</h3>
          <div>
            {Array.from(teacherSummary.entries())
              .sort(([first], [second]) => first.localeCompare(second, "fr"))
              .map(([label, summary]) => (
                <article className={summary.warnings > 0 ? "has-warning" : ""} key={label}>
                  <strong>{label}</strong>
                  <span>{summary.slotCount} {text(language, "cours", "courses")} · {formatTeachingMinutes(summary.minutes, language)}</span>
                  <small>{summary.confirmed} {text(language, "confirmé(s)", "confirmed")} {summary.warnings > 0 ? `· ${summary.warnings} ${text(language, "alerte(s)", "warning(s)")}` : ""}</small>
                  {canEdit && !summary.professorId ? (
                    <form action={adminUpdatePlanningSimulationTeacherAssignmentAction} className="simulation-assignment-replace-form">
                      <input type="hidden" name="school_year_label" value={schoolYearLabel} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      {summary.slotKeys.map((slotKey) => <input type="hidden" name="slot_key" value={slotKey} key={slotKey} />)}
                      <select name="professor_id" defaultValue="" required aria-label={text(language, "Professeur définitif", "Final teacher")}>
                        <option value="" disabled>{text(language, "Remplacer par…", "Replace with…")}</option>
                        {activeProfessors.map((professor) => (
                          <option value={professor.id} key={professor.id}>{professor.first_name} {professor.last_name}</option>
                        ))}
                      </select>
                      <select name="assignment_status" defaultValue="PREVISIONAL" aria-label={text(language, "Statut", "Status")}>
                        <option value="PREVISIONAL">{text(language, "Prévisionnel", "Provisional")}</option>
                        <option value="CONFIRMED">{text(language, "Confirmé", "Confirmed")}</option>
                      </select>
                      <button type="submit" name="operation" value="save">{text(language, "Remplacer partout", "Replace everywhere")}</button>
                    </form>
                  ) : null}
                </article>
              ))}
          </div>
        </section>
      ) : null}

      <section className="simulation-assignment-days">
        {dayGroups.map((day) => (
          <article className="card simulation-assignment-day" key={day.weekday}>
            <header>
              <h3>{day.weekdayLabel}</h3>
              <span>{day.slots.filter((slot) => slot.teacher_assignment_label).length}/{day.slots.length} {text(language, "affectés", "assigned")}</span>
            </header>
            {canEdit ? (
              <details className="simulation-assignment-bulk">
                <summary>{text(language, "Affecter une demi-journée en une fois", "Assign a half-day at once")}</summary>
                <div>
                  {teacherAssignmentBulkGroups(day.slots, language).map((group) => (
                    <form action={adminUpdatePlanningSimulationTeacherAssignmentAction} key={group.key}>
                      <input type="hidden" name="school_year_label" value={schoolYearLabel} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      {group.slots.map((slot) => <input type="hidden" name="slot_key" value={slot.slot_key} key={slot.slot_key} />)}
                      <strong>{group.label}</strong>
                      <small>{group.slots.length} {text(language, "créneau(x)", "slot(s)")}</small>
                      <select name="professor_id" defaultValue="" aria-label={text(language, "Professeur", "Teacher")}>
                        <option value="">{text(language, "— Professeur provisoire —", "— Placeholder teacher —")}</option>
                        {activeProfessors.map((professor) => (
                          <option value={professor.id} key={professor.id}>{professor.first_name} {professor.last_name}</option>
                        ))}
                      </select>
                      <input
                        name="teacher_label"
                        list="simulation-placeholder-teachers"
                        placeholder={text(language, "Ou libellé provisoire", "Or placeholder label")}
                        aria-label={text(language, "Libellé provisoire", "Placeholder label")}
                      />
                      <select name="assignment_status" defaultValue="PREVISIONAL" aria-label={text(language, "Statut", "Status")}>
                        <option value="PREVISIONAL">{text(language, "Prévisionnel", "Provisional")}</option>
                        <option value="CONFIRMED">{text(language, "Confirmé", "Confirmed")}</option>
                      </select>
                      <button type="submit" name="operation" value="save">{text(language, "Affecter le groupe", "Assign group")}</button>
                    </form>
                  ))}
                </div>
              </details>
            ) : null}
            <div className="simulation-assignment-slot-list">
              {day.slots
                .slice()
                .sort((first, second) => first.start_time.localeCompare(second.start_time) || first.location_name.localeCompare(second.location_name, "fr"))
                .map((slot) => (
                  <section className={`simulation-assignment-slot ${slot.teacher_assignment_label ? "assigned" : "unfilled"}`} key={slot.slot_key}>
                    <div className="simulation-assignment-slot-heading">
                      <div>
                        <time>{slot.start_time}–{slot.end_time}</time>
                        <strong>{slot.course_type_name}</strong>
                        <span>{slot.location_name}</span>
                      </div>
                      <div className="simulation-assignment-current">
                        <span className={`simulation-assignment-status ${slot.teacher_assignment_status?.toLowerCase() || "unfilled"}`}>
                          {slot.teacher_assignment_status === "CONFIRMED"
                            ? text(language, "Confirmé", "Confirmed")
                            : slot.teacher_assignment_label
                              ? text(language, "Prévisionnel", "Provisional")
                              : text(language, "À pourvoir", "Unfilled")}
                        </span>
                        <strong>
                          {(slot.teacher_assignment_labels?.length
                            ? slot.teacher_assignment_labels.join(" · ")
                            : slot.teacher_assignment_label) || text(language, "Aucun professeur", "No teacher")}
                        </strong>
                      </div>
                    </div>

                    {slot.teacher_assignment_warnings.length > 0 ? (
                      <div className="simulation-assignment-warnings">
                        {slot.teacher_assignment_warnings.map((warning) => (
                          <span key={warning}>{teacherAssignmentWarningLabel(warning, language)}</span>
                        ))}
                      </div>
                    ) : null}

                    {canEdit ? (
                      <form action={adminUpdatePlanningSimulationTeacherAssignmentAction} className="simulation-assignment-form">
                        <input type="hidden" name="school_year_label" value={schoolYearLabel} />
                        <input type="hidden" name="slot_key" value={slot.slot_key} />
                        <input type="hidden" name="position" value="1" />
                        <input type="hidden" name="return_to" value={returnTo} />
                        <label>
                          <span>{text(language, "Professeur connu", "Known teacher")}</span>
                          <select name="professor_id" defaultValue={slot.teacher_assignment_professor_id || ""}>
                            <option value="">{text(language, "— Aucun / provisoire —", "— None / placeholder —")}</option>
                            {activeProfessors.map((professor) => (
                              <option value={professor.id} key={professor.id}>{professor.first_name} {professor.last_name}</option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>{text(language, "Ou libellé provisoire", "Or placeholder label")}</span>
                          <input
                            name="teacher_label"
                            list="simulation-placeholder-teachers"
                            defaultValue={slot.teacher_assignment_professor_id ? "" : slot.teacher_assignment_label || ""}
                            placeholder={text(language, "Ex. Prof à confirmer 1", "E.g. Teacher to confirm 1")}
                          />
                        </label>
                        <label>
                          <span>{text(language, "Statut", "Status")}</span>
                          <select name="assignment_status" defaultValue={slot.teacher_assignment_status || "PREVISIONAL"}>
                            <option value="PREVISIONAL">{text(language, "Prévisionnel", "Provisional")}</option>
                            <option value="CONFIRMED">{text(language, "Confirmé", "Confirmed")}</option>
                          </select>
                        </label>
                        <div className="simulation-assignment-actions">
                          <button type="submit" name="operation" value="save">{text(language, "Enregistrer", "Save")}</button>
                          {slot.teacher_assignment_label ? (
                            <button className="ghost" type="submit" name="operation" value="clear">{text(language, "Retirer", "Clear")}</button>
                          ) : null}
                        </div>
                      </form>
                    ) : null}
                    {canEdit && /master\s*class/i.test(slot.course_type_name) ? ([2, 3, 4] as const).map((position) => {
                      const assignmentIndex = position - 1;
                      const assignedProfessorId = slot.teacher_assignment_professor_ids?.[assignmentIndex] || "";
                      const assignedLabel = slot.teacher_assignment_labels?.[assignmentIndex] || "";
                      const assignedStatus = slot.teacher_assignment_statuses?.[assignmentIndex] || "PREVISIONAL";
                      return (
                        <form action={adminUpdatePlanningSimulationTeacherAssignmentAction} className="simulation-assignment-form" key={`${slot.slot_key}-${position}`}>
                          <input type="hidden" name="school_year_label" value={schoolYearLabel} />
                          <input type="hidden" name="slot_key" value={slot.slot_key} />
                          <input type="hidden" name="position" value={position} />
                          <input type="hidden" name="return_to" value={returnTo} />
                          <label>
                            <span>{text(language, `Professeur ${position}`, `Teacher ${position}`)}</span>
                            <select name="professor_id" defaultValue={assignedProfessorId}>
                              <option value="">{text(language, "— Aucun / provisoire —", "— None / placeholder —")}</option>
                              {activeProfessors.map((professor) => (
                                <option value={professor.id} key={professor.id}>{professor.first_name} {professor.last_name}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            <span>{text(language, "Ou libellé provisoire", "Or placeholder label")}</span>
                            <input
                              name="teacher_label"
                              list="simulation-placeholder-teachers"
                              defaultValue={assignedProfessorId ? "" : assignedLabel}
                            />
                          </label>
                          <label>
                            <span>{text(language, "Statut", "Status")}</span>
                            <select name="assignment_status" defaultValue={assignedStatus}>
                              <option value="PREVISIONAL">{text(language, "Prévisionnel", "Provisional")}</option>
                              <option value="CONFIRMED">{text(language, "Confirmé", "Confirmed")}</option>
                            </select>
                          </label>
                          <div className="simulation-assignment-actions">
                            <button type="submit" name="operation" value="save">{text(language, "Enregistrer", "Save")}</button>
                            {assignedLabel ? (
                              <button className="ghost" type="submit" name="operation" value="clear">{text(language, "Retirer", "Clear")}</button>
                            ) : null}
                          </div>
                        </form>
                      );
                    }) : null}
                  </section>
                ))}
            </div>
          </article>
        ))}
      </section>
    </section>
  );
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
            (parseTimeToMinutes(a.end_time) ?? 0) - (parseTimeToMinutes(b.end_time) ?? 0) ||
            a.course_type_name.localeCompare(b.course_type_name, "fr"),
        ),
    }));
}

function positionedCalendarSlots(slots: AdminPlanningSimulationSlotOut[]): PositionedCalendarSlot[] {
  const sorted = slots
    .slice()
    .sort(
      (a, b) =>
        (parseTimeToMinutes(a.start_time) ?? 0) - (parseTimeToMinutes(b.start_time) ?? 0) ||
        (parseTimeToMinutes(a.end_time) ?? 0) - (parseTimeToMinutes(b.end_time) ?? 0) ||
        a.course_type_name.localeCompare(b.course_type_name, "fr") ||
        a.slot_key.localeCompare(b.slot_key, "fr"),
    );
  const positioned: PositionedCalendarSlot[] = [];
  let cluster: AdminPlanningSimulationSlotOut[] = [];
  let clusterEnd = -1;

  function flushCluster(): void {
    if (cluster.length === 0) {
      return;
    }
    const columnEnds: number[] = [];
    const clusterPositions: PositionedCalendarSlot[] = [];
    for (const slot of cluster) {
      const start = parseTimeToMinutes(slot.start_time) ?? 0;
      const end = parseTimeToMinutes(slot.end_time) ?? start + 60;
      let column = columnEnds.findIndex((value) => value <= start);
      if (column < 0) {
        column = columnEnds.length;
        columnEnds.push(end);
      } else {
        columnEnds[column] = end;
      }
      clusterPositions.push({ slot, column, columns: 1 });
    }
    const columns = Math.max(1, columnEnds.length);
    for (const item of clusterPositions) {
      positioned.push({ ...item, columns });
    }
    cluster = [];
    clusterEnd = -1;
  }

  for (const slot of sorted) {
    const start = parseTimeToMinutes(slot.start_time) ?? 0;
    const end = parseTimeToMinutes(slot.end_time) ?? start + 60;
    if (cluster.length > 0 && start >= clusterEnd) {
      flushCluster();
    }
    cluster.push(slot);
    clusterEnd = Math.max(clusterEnd, end);
  }
  flushCluster();
  return positioned;
}

function calendarSlotStyle(
  item: PositionedCalendarSlot,
  bounds: { start: number; end: number; height: number },
): CSSProperties {
  const slot = item.slot;
  const start = parseTimeToMinutes(slot.start_time) ?? bounds.start;
  const end = parseTimeToMinutes(slot.end_time) ?? start + 60;
  const total = Math.max(60, bounds.end - bounds.start);
  const top = ((Math.max(bounds.start, start) - bounds.start) / total) * 100;
  const height = (Math.max(30, end - start) / total) * 100;
  const columnGap = 6;
  const sideInset = 8;
  const width = `calc((100% - ${sideInset * 2}px - ${(item.columns - 1) * columnGap}px) / ${item.columns})`;
  return {
    top: `${Math.max(0, Math.min(100, top))}%`,
    height: `${Math.max(8, height)}%`,
    left: `calc(${sideInset}px + ${item.column} * (${width} + ${columnGap}px))`,
    right: "auto",
    width,
  };
}

function calendarSlotDetailPlacement(
  slot: AdminPlanningSimulationSlotOut,
  bounds: { start: number; end: number; height: number },
): "above" | "below" {
  const start = parseTimeToMinutes(slot.start_time) ?? bounds.start;
  const total = Math.max(60, bounds.end - bounds.start);
  const topRatio = (Math.max(bounds.start, start) - bounds.start) / total;
  const remainingMinutes = bounds.end - start;
  return remainingMinutes <= 180 || topRatio >= 0.62 ? "above" : "below";
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
  if (!meResult.ok || !hasAdminPermission(meResult.data, "can_view_planning_simulation")) {
    redirect("/login?error_code=admin_access_required");
  }

  const language = normalizeUiLanguage(meResult.data.preferred_language);
  const canEditSimulation = hasAdminPermission(meResult.data, "can_edit_planning");
  const requestedView = simulationViewFromParams(searchParams ?? {});
  const requestedSchoolYear = readParam(searchParams ?? {}, "school_year").trim() || DEFAULT_SIMULATION_SCHOOL_YEAR;
  const scopedLocationId = String(meResult.data.admin_permissions?.planning_simulation_location_id ?? "").trim();
  const rawRequestedLocationId = readParam(searchParams ?? {}, "location_id").trim();
  const requestedLocationId = scopedLocationId || rawRequestedLocationId;
  const requestedActivityFilter = activityFilterFromParams(searchParams ?? {}, requestedView);
  const requestedActivityId = requestedActivityFilter.startsWith(ACTIVITY_FILTER_PREFIX)
    ? requestedActivityFilter.slice(ACTIVITY_FILTER_PREFIX.length)
    : "";
  const requestedActivityGroup =
    requestedActivityFilter === DEFAULT_SIMULATION_ACTIVITY_FILTER ? "collective_piano" : "";

  const simulationQuery = new URLSearchParams();
  if (requestedSchoolYear) simulationQuery.set("school_year_label", requestedSchoolYear);
  if (requestedLocationId) simulationQuery.set("location_id", requestedLocationId);
  if (requestedActivityId) simulationQuery.set("activity_id", requestedActivityId);
  if (requestedActivityGroup) simulationQuery.set("activity_group", requestedActivityGroup);
  if (requestedView === "teacher_needs") {
    simulationQuery.append("exclude_location_name", TEACHER_NEEDS_EXCLUDED_LOCATION_NAME);
    simulationQuery.set("exclude_online_solfege", "true");
  }
  const simulationPath = simulationQuery.size
    ? `/api/v1/admin/plannings/simulation?${simulationQuery.toString()}`
    : "/api/v1/admin/plannings/simulation";

  const [locationsResult, courseTypesResult, simulationResult, professorsResult] = await Promise.all([
    loadPlanningSimulationLocations(token),
    backendRequest<CourseTypeOut[]>("/api/v1/course-types?active=true", {}, token),
    backendRequest<AdminPlanningSimulationOut>(simulationPath, {}, token),
    requestedView === "teacher_needs" && canEditSimulation
      ? backendRequest<AdminProfessorOut[]>("/api/v1/admin/professors?active=true", {}, token)
      : Promise.resolve({ ok: true as const, data: [] as AdminProfessorOut[] }),
  ]);

  const permittedLocations = locationsResult.ok
    ? scopedLocationId
      ? locationsResult.data.filter((location) => location.id === scopedLocationId)
      : locationsResult.data
    : [];
  const locations =
    requestedView === "teacher_needs"
      ? permittedLocations.filter(
          (location) => location.name.trim().toLocaleLowerCase("fr") !== TEACHER_NEEDS_EXCLUDED_LOCATION_NAME.toLocaleLowerCase("fr"),
        )
      : permittedLocations;
  const courseTypes = courseTypesResult.ok
    ? courseTypesResult.data.filter(
        (courseType) =>
          courseType.code.toUpperCase() !== VACATION_COURSE_TYPE_CODE &&
          (requestedView !== "teacher_needs" || !isOnlineSolfegeCourseType(courseType)),
      )
    : [];
  const simulation = simulationResult.ok ? simulationResult.data : null;
  const locationsError = locationsResult.ok ? null : locationsResult.message;
  const courseTypesError = courseTypesResult.ok ? null : courseTypesResult.message;
  const simulationError = simulationResult.ok ? null : simulationResult.message;
  const professors = professorsResult.ok ? professorsResult.data : [];
  const professorsError = professorsResult.ok ? null : professorsResult.message;
  const okMessage = readParam(searchParams ?? {}, "ok").trim();
  const actionError = readParam(searchParams ?? {}, "error").trim();

  const effectiveSchoolYear = simulation?.school_year_label || requestedSchoolYear || "";
  const availableSchoolYears = Array.from(
    new Set([effectiveSchoolYear, ...(simulation?.available_school_years ?? [])].filter(Boolean)),
  );
  const groupedLocations = simulation ? groupByLocation(simulation.slots) : [];
  const assignmentReturnParams = new URLSearchParams();
  assignmentReturnParams.set("view", "teacher_needs");
  assignmentReturnParams.set("school_year", effectiveSchoolYear);
  if (requestedLocationId) assignmentReturnParams.set("location_id", requestedLocationId);
  assignmentReturnParams.set("activity_filter", requestedActivityFilter);
  const assignmentReturnTo = `/admin/simulation-planning?${assignmentReturnParams.toString()}`;

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

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {actionError ? <section className="flash-err">{actionError}</section> : null}

      <nav className="simulation-planning-tabs" aria-label={text(language, "Vues de simulation", "Simulation views")}>
        <Link
          className={`simulation-planning-tab ${requestedView === "capacity" ? "active" : ""}`}
          href={`/admin/simulation-planning?view=capacity&school_year=${encodeURIComponent(requestedSchoolYear)}${requestedLocationId ? `&location_id=${encodeURIComponent(requestedLocationId)}` : ""}&activity_filter=${encodeURIComponent(requestedActivityFilter)}`}
        >
          <strong>{text(language, "Capacite des cours", "Course capacity")}</strong>
          <span>{text(language, "Remplissage et pression devis", "Occupancy and quote pressure")}</span>
        </Link>
        <Link
          className={`simulation-planning-tab ${requestedView === "teacher_needs" ? "active" : ""}`}
          href={`/admin/simulation-planning?view=teacher_needs&school_year=${encodeURIComponent(requestedSchoolYear)}${requestedLocationId ? `&location_id=${encodeURIComponent(requestedLocationId)}` : ""}&activity_filter=${encodeURIComponent(requestedView === "capacity" && requestedActivityFilter === DEFAULT_SIMULATION_ACTIVITY_FILTER ? ALL_SIMULATION_ACTIVITY_FILTER : requestedActivityFilter)}`}
        >
          <strong>{text(language, "Besoin professeurs", "Teacher requirements")}</strong>
          <span>{text(language, "Par jour et type de cours", "By day and course type")}</span>
        </Link>
      </nav>

      <section className="card">
        <SimulationPlanningFilterForm className="simulation-planning-toolbar">
          <input type="hidden" name="view" value={requestedView} />
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
              {scopedLocationId ? null : <option value="">{text(language, "Tous les locaux", "All locations")}</option>}
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
            <select name="activity_filter" defaultValue={requestedActivityFilter}>
              <option value={DEFAULT_SIMULATION_ACTIVITY_FILTER}>
                {text(language, "Collectifs piano (defaut)", "Piano groups (default)")}
              </option>
              <option value={ALL_SIMULATION_ACTIVITY_FILTER}>{text(language, "Tous les types", "All course types")}</option>
              {courseTypes
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name, "fr"))
                .map((courseType) => (
                  <option key={courseType.id} value={`${ACTIVITY_FILTER_PREFIX}${courseType.id}`}>
                    {courseType.name}
                  </option>
                ))}
            </select>
          </label>

          <div className="simulation-planning-toolbar-actions">
            <button type="submit" className="simulation-planning-submit">
              {text(language, "Mettre a jour", "Refresh")}
            </button>
            <Link className="ghost" href={`/admin/simulation-planning?view=${requestedView}`}>
              {text(language, "Reinitialiser", "Reset")}
            </Link>
          </div>
        </SimulationPlanningFilterForm>
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

      {professorsError ? (
        <section className="flash-err">
          {text(language, "Impossible de charger les professeurs : ", "Unable to load teachers: ")}
          {professorsError}
        </section>
      ) : null}

      {!simulation ? (
        <section className="flash-err">
          {text(language, "Impossible de charger la simulation : ", "Unable to load the simulation: ")}
          {simulationError}
        </section>
      ) : requestedView === "teacher_needs" ? (
        simulation.teacher_needs.days.length === 0 ? (
          <section className="card">
            <h3>{text(language, "Aucun besoin professeur visible", "No visible teacher requirement")}</h3>
            <p className="muted">
              {text(
                language,
                "Aucun cours n entre dans les filtres de cette saison. Elargissez le filtre lieu ou type de cours.",
                "No course matches the current filters for this season. Broaden the location or course type filter.",
              )}
            </p>
          </section>
        ) : (
          <>
            <TeacherNeedsDashboard
              needs={simulation.teacher_needs}
              slots={simulation.slots}
              professors={professors}
              schoolYearLabel={effectiveSchoolYear}
              returnTo={assignmentReturnTo}
              canEdit={canEditSimulation && !professorsError}
              language={language}
            />
            <TeacherAssignmentBoard
              slots={simulation.slots}
              professors={professors}
              schoolYearLabel={effectiveSchoolYear}
              returnTo={assignmentReturnTo}
              canEdit={canEditSimulation && !professorsError}
              language={language}
            />
          </>
        )
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
                    const calendarMinWidth = 72 + dayGroups.length * 190;
                    return (
                      <>
                        <div className="simulation-calendar-scroll">
                          <div
                            className="simulation-calendar-grid"
                            style={{
                              gridTemplateColumns: `72px repeat(${Math.max(1, dayGroups.length)}, minmax(190px, 1fr))`,
                              minWidth: `max(920px, ${calendarMinWidth}px)`,
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
                                {positionedCalendarSlots(dayGroup.slots).map((positionedSlot) => {
                                  const slot = positionedSlot.slot;
                                  const tone = projectionTone(slot);
                                  const percent = fillPercent(slot.projected_fill_rate);
                                  const peopleSections = slotPeopleSections(slot, language);
                                  const detailPlacement = calendarSlotDetailPlacement(slot, bounds);
                                  return (
                                    <article
                                      className={`simulation-calendar-slot simulation-calendar-slot-${tone}`}
                                      key={slot.slot_key}
                                      style={calendarSlotStyle(positionedSlot, bounds)}
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
                                      <div
                                        className={`simulation-calendar-slot-detail simulation-calendar-slot-detail-${detailPlacement}`}
                                        role="tooltip"
                                      >
                                        <div className="simulation-calendar-slot-meta simulation-calendar-slot-detail-counts">
                                          {slotStatusBreakdown(slot, language).map((item) => (
                                            <span className={item.className} key={`${slot.slot_key}-${item.className}`}>
                                              {item.label} {item.count}
                                            </span>
                                          ))}
                                        </div>
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
                                                {section.people.map((person) => (
                                                  <li key={person}>{person}</li>
                                                ))}
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
                        <div className="simulation-mobile-slot-list">
                          {dayGroups.map((dayGroup) => (
                            <section className="simulation-mobile-day" key={`mobile-${dayGroup.weekday}`}>
                              <div className="simulation-mobile-day-head">
                                <strong>{dayGroup.weekdayLabel}</strong>
                                <span>
                                  {dayGroup.slots.length} {text(language, "creneau(x)", "slot(s)")}
                                </span>
                              </div>
                              <div className="simulation-mobile-day-slots">
                                {dayGroup.slots.map((slot) => {
                                  const tone = projectionTone(slot);
                                  const percent = fillPercent(slot.projected_fill_rate);
                                  const peopleSections = slotPeopleSections(slot, language);
                                  const notes = noteList(slot, language);
                                  return (
                                    <details
                                      className={`simulation-mobile-slot simulation-mobile-slot-${tone}`}
                                      key={`mobile-${slot.slot_key}`}
                                    >
                                      <summary>
                                        <span>
                                          <strong>
                                            {slot.start_time}-{slot.end_time}
                                          </strong>
                                          <small>{slot.course_type_name}</small>
                                        </span>
                                        <b>{projectedSlotLabel(slot)}</b>
                                      </summary>
                                      <div className="simulation-mobile-slot-body">
                                        <div className="simulation-calendar-slot-meta simulation-calendar-slot-detail-counts">
                                          {slotStatusBreakdown(slot, language).map((item) => (
                                            <span className={item.className} key={`mobile-${slot.slot_key}-${item.className}`}>
                                              {item.label} {item.count}
                                            </span>
                                          ))}
                                        </div>
                                        <div className="simulation-calendar-slot-fill" aria-hidden="true">
                                          <span style={{ width: `${percent}%` }} />
                                        </div>
                                        <p>
                                          <strong>{text(language, "Serie active :", "Live series:")}</strong>{" "}
                                          {formatSeasonWindow(slot, language)}
                                        </p>
                                        {peopleSections.length === 0 ? (
                                          <p className="muted">
                                            {text(
                                              language,
                                              "Aucun eleve inscrit ou devis en attente.",
                                              "No enrolled student or pending quote.",
                                            )}
                                          </p>
                                        ) : (
                                          peopleSections.map((section) => (
                                            <div className="simulation-calendar-people-section" key={`mobile-${slot.slot_key}-${section.label}`}>
                                              <strong>{section.label}</strong>
                                              <ul>
                                                {section.people.map((person) => (
                                                  <li key={person}>{person}</li>
                                                ))}
                                              </ul>
                                            </div>
                                          ))
                                        )}
                                        {notes.map((note) => (
                                          <p className={`simulation-inline-note simulation-tone-${tone}`} key={`mobile-${slot.slot_key}-${note}`}>
                                            {note}
                                          </p>
                                        ))}
                                      </div>
                                    </details>
                                  );
                                })}
                              </div>
                            </section>
                          ))}
                        </div>
                      </>
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
