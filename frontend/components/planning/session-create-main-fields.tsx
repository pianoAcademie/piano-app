"use client";

import { useMemo, useState } from "react";

import SessionTimeFields from "../session-time-fields";

type UiLanguage = "fr" | "en";

type CourseTypeOption = {
  id: string;
  name: string;
  durationMinutes: number;
  defaultCapacity: number;
  requiresProfessor: boolean;
  allowsStudentBookings: boolean;
};

type ProfessorOption = {
  id: string;
  firstName: string;
  lastName: string;
};

type LocationOption = {
  id: string;
  name: string;
};

type TimezoneOption = {
  value: string;
  label: string;
};

type SessionCreateMainFieldsProps = {
  courseTypes: CourseTypeOption[];
  professors: ProfessorOption[];
  locations: LocationOption[];
  sessionTimezoneOptions: TimezoneOption[];
  defaultCourseTypeId: string;
  defaultLocationId: string;
  defaultSessionTimezone: string;
  defaultStartDate: string;
  draft?: {
    title?: string;
    courseTypeId?: string;
    professorId?: string;
    locationId?: string;
    sessionTimezone?: string;
    startDate?: string;
    isAllDay?: boolean;
    startTime?: string;
    endTime?: string;
    durationMinutes?: number | null;
    capacityMax?: number | null;
    zoomLink?: string;
  };
  recurrenceDefaults: {
    mode: "NONE" | "RECURRING";
    frequency: "DAILY" | "WEEKLY" | "MONTHLY";
    interval: number;
    untilDate?: string;
    keepLocalTime: boolean;
  };
  language?: UiLanguage;
};

function parseTimeToMinutes(value: string): number | null {
  const match = value.trim().match(/^([01]\d|2[0-3]):([0-5]\d)$/);
  if (!match) {
    return null;
  }
  const hours = Number.parseInt(match[1], 10);
  const minutes = Number.parseInt(match[2], 10);
  return (hours * 60) + minutes;
}

function toTimeValue(totalMinutes: number): string {
  const clamped = Math.max(0, Math.min(totalMinutes, (24 * 60) - 1));
  const hours = Math.floor(clamped / 60);
  const minutes = clamped % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function endTimeFromStartAndDuration(startTime: string, durationMinutes: number): string {
  const startMinutes = parseTimeToMinutes(startTime);
  if (startMinutes === null || durationMinutes <= 0) {
    return "13:00";
  }
  return toTimeValue(startMinutes + durationMinutes);
}

export default function SessionCreateMainFields({
  courseTypes,
  professors,
  locations,
  sessionTimezoneOptions,
  defaultCourseTypeId,
  defaultLocationId,
  defaultSessionTimezone,
  defaultStartDate,
  draft,
  recurrenceDefaults,
  language = "fr",
}: SessionCreateMainFieldsProps): JSX.Element {
  const text = language === "en"
    ? {
        title: "Title",
        courseType: "Course type",
        select: "Select",
        defaultDuration: "Default duration",
        defaultCapacity: "Default capacity",
        withStudents: "with students",
        withoutStudent: "without student",
        teacher: "Teacher",
        selectTeacher: "Select a teacher",
        noTeacher: "No teacher",
        location: "Location",
        timezone: "Session timezone",
        startDate: "Start date",
        allDay: "All-day slot",
        startTime: "Start time",
        endTime: "End time",
        duration: "Duration (minutes)",
        maxCapacity: "Max capacity",
        capacityForced: "Capacity is forced to 0 for slots without students.",
        zoomLink: "Zoom link (optional)",
        recurrence: "Recurrence",
        oneTimeEvent: "One-time event",
        recurringEvent: "Recurring event",
        frequency: "Frequency",
        daily: "Daily",
        weekly: "Weekly",
        monthly: "Monthly",
        repeatsEvery: "Repeats every",
        repeatsEveryHint: "Example: 2 for every 2 weeks.",
        repeatUntil: "Repeat until",
        keepLocalTime: "Keep local time",
        keepLocalTimeHint: "Recommended for France: a slot created at 6 PM stays at 6 PM after summer/winter time changes.",
        recurrenceUntilHint: "Recurrence is created up to and including the end date.",
      }
    : {
        title: "Titre",
        courseType: "Type de cours",
        select: "Selectionner",
        defaultDuration: "Duree type",
        defaultCapacity: "Capacite type",
        withStudents: "avec eleves",
        withoutStudent: "sans eleve",
        teacher: "Professeur",
        selectTeacher: "Selectionner un professeur",
        noTeacher: "Sans professeur",
        location: "Lieu",
        timezone: "Fuseau horaire du creneau",
        startDate: "Date de debut",
        allDay: "Creneau sur toute la journee",
        startTime: "Heure debut",
        endTime: "Heure fin",
        duration: "Duree (minutes)",
        maxCapacity: "Capacite max",
        capacityForced: "Capacite forcee a 0 pour les creneaux sans eleve.",
        zoomLink: "Lien Zoom (optionnel)",
        recurrence: "Recurrence",
        oneTimeEvent: "Evenement unique",
        recurringEvent: "Evenement recurrent",
        frequency: "Frequence",
        daily: "Journaliere",
        weekly: "Hebdomadaire",
        monthly: "Mensuelle",
        repeatsEvery: "Se repete chaque",
        repeatsEveryHint: "Ex: 2 pour toutes les 2 semaines.",
        repeatUntil: "Repeter jusqu au",
        keepLocalTime: "Heure locale fixe",
        keepLocalTimeHint: "Recommande pour la France : un creneau cree a 18h reste a 18h apres le changement d'heure ete/hiver.",
        recurrenceUntilHint: "La recurrence est creee jusqu a la date de fin incluse.",
      };

  const normalizedDefaultCourseTypeId = useMemo(() => {
    const fromDraft = String(draft?.courseTypeId || "").trim();
    if (fromDraft && courseTypes.some((row) => row.id === fromDraft)) {
      return fromDraft;
    }
    if (courseTypes.some((row) => row.id === defaultCourseTypeId)) {
      return defaultCourseTypeId;
    }
    return courseTypes[0]?.id || "";
  }, [courseTypes, defaultCourseTypeId, draft?.courseTypeId]);

  const [selectedCourseTypeId, setSelectedCourseTypeId] = useState(normalizedDefaultCourseTypeId);
  const selectedCourseType = useMemo(
    () => courseTypes.find((row) => row.id === selectedCourseTypeId) || null,
    [courseTypes, selectedCourseTypeId],
  );

  const durationMinutes = selectedCourseType?.durationMinutes && selectedCourseType.durationMinutes > 0
    ? selectedCourseType.durationMinutes
    : 60;
  const draftedDuration = typeof draft?.durationMinutes === "number" && Number.isFinite(draft.durationMinutes) && draft.durationMinutes > 0
    ? Math.floor(draft.durationMinutes)
    : null;
  const defaultDuration = draftedDuration ?? durationMinutes;
  const capacityDefault = selectedCourseType?.defaultCapacity && selectedCourseType.defaultCapacity > 0
    ? selectedCourseType.defaultCapacity
    : (selectedCourseType?.allowsStudentBookings === false ? 0 : 1);
  const draftedCapacity = typeof draft?.capacityMax === "number" && Number.isFinite(draft.capacityMax) && draft.capacityMax >= 0
    ? Math.floor(draft.capacityMax)
    : null;
  const startTimeDefault = String(draft?.startTime || "").trim() || "12:00";
  const endTimeDefault = String(draft?.endTime || "").trim() || endTimeFromStartAndDuration(startTimeDefault, defaultDuration);
  const locationDefaultValue = String(draft?.locationId || "").trim() || defaultLocationId;
  const timezoneDefaultValue = String(draft?.sessionTimezone || "").trim() || defaultSessionTimezone;
  const startDateDefaultValue = String(draft?.startDate || "").trim() || defaultStartDate;
  const professorDefaultValue = String(draft?.professorId || "").trim();
  const titleDefaultValue = String(draft?.title || "");
  const zoomLinkDefaultValue = String(draft?.zoomLink || "");
  const isAllDayDefaultValue = Boolean(draft?.isAllDay);
  const draftStartDateValue = String(draft?.startDate || "").trim();
  const draftedRecurrenceUntilDate = String(recurrenceDefaults.untilDate || "").trim();
  const recurrenceUntilDefaultValue = draftedRecurrenceUntilDate || startDateDefaultValue;
  const recurrenceUntilWasCustomized = draftedRecurrenceUntilDate.length > 0 && draftedRecurrenceUntilDate !== draftStartDateValue;

  const [startDate, setStartDate] = useState(startDateDefaultValue);
  const [recurrenceUntilDate, setRecurrenceUntilDate] = useState(recurrenceUntilDefaultValue);
  const [recurrenceUntilCustomized, setRecurrenceUntilCustomized] = useState(recurrenceUntilWasCustomized);

  const handleStartDateChange = (value: string) => {
    setStartDate(value);
    if (!recurrenceUntilCustomized) {
      setRecurrenceUntilDate(value);
    }
  };

  const handleRecurrenceUntilDateChange = (value: string) => {
    setRecurrenceUntilDate(value);
    setRecurrenceUntilCustomized(value.trim().length > 0 && value !== startDate);
  };

  return (
    <>
      <div className="grid cols-4 create-session-grid">
        <label className="span-2">
          {text.title}
          <input type="text" name="title" defaultValue={titleDefaultValue} required maxLength={255} autoFocus />
        </label>

        <label>
          {text.courseType}
          <select
            name="course_type_id"
            value={selectedCourseTypeId}
            required
            onChange={(event) => setSelectedCourseTypeId(event.target.value)}
          >
            <option value="">{text.select}</option>
            {courseTypes.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
          {selectedCourseType ? (
            <small className="muted">
              {text.defaultDuration}: {selectedCourseType.durationMinutes} min · {text.defaultCapacity}: {selectedCourseType.defaultCapacity} ·{" "}
              {selectedCourseType.allowsStudentBookings ? text.withStudents : text.withoutStudent}
            </small>
          ) : null}
        </label>

        <label>
          {text.teacher}
          <select name="professor_id" defaultValue={professorDefaultValue} required={Boolean(selectedCourseType?.requiresProfessor)}>
            <option value="">{selectedCourseType?.requiresProfessor ? text.selectTeacher : text.noTeacher}</option>
            {professors.map((row) => (
              <option key={row.id} value={row.id}>
                {row.firstName} {row.lastName}
              </option>
            ))}
          </select>
        </label>

        <label>
          {text.location}
          <select name="location_id" defaultValue={locationDefaultValue} required>
            {locations.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {text.timezone}
          <select name="session_timezone" defaultValue={timezoneDefaultValue} required>
            {sessionTimezoneOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          {text.startDate}
          <input type="date" name="start_date" value={startDate} required onChange={(event) => handleStartDateChange(event.target.value)} />
        </label>

        <label className="checkline create-session-toggle">
          <input type="checkbox" name="is_all_day" defaultChecked={isAllDayDefaultValue} />
          {text.allDay}
        </label>

        <SessionTimeFields
          key={`create-time-${selectedCourseTypeId || "default"}-${defaultDuration}`}
          labelClassName="create-time-field session-time-field"
          language={language}
          startLabel={text.startTime}
          endLabel={text.endTime}
          durationLabel={text.duration}
          defaultStartTime={startTimeDefault}
          defaultEndTime={endTimeDefault}
          defaultDurationMinutes={defaultDuration}
          requiredStart
        />

        {selectedCourseType?.allowsStudentBookings === false ? (
          <label key={`create-capacity-${selectedCourseTypeId || "default"}-${draftedCapacity ?? capacityDefault}`}>
            {text.maxCapacity}
            <input type="hidden" name="capacity_max" value="0" />
            <input type="number" value={0} min={0} readOnly disabled />
            <small className="muted">{text.capacityForced}</small>
          </label>
        ) : (
          <label key={`create-capacity-${selectedCourseTypeId || "default"}-${draftedCapacity ?? capacityDefault}`}>
            {text.maxCapacity}
            <input type="number" name="capacity_max" min={0} defaultValue={draftedCapacity ?? capacityDefault} required />
          </label>
        )}

        <label className="span-2">
          {text.zoomLink}
          <input type="url" name="zoom_link" defaultValue={zoomLinkDefaultValue} placeholder="https://..." />
        </label>
      </div>

      <fieldset className="create-session-section recurrence-panel">
        <legend>{text.recurrence}</legend>
        <div className="recurrence-mode-row">
          <label className="checkline">
            <input type="radio" name="recurrence_mode" value="NONE" defaultChecked={recurrenceDefaults.mode === "NONE"} />
            {text.oneTimeEvent}
          </label>
          <label className="checkline">
            <input type="radio" name="recurrence_mode" value="RECURRING" defaultChecked={recurrenceDefaults.mode === "RECURRING"} />
            {text.recurringEvent}
          </label>
        </div>

        <div className="recurrence-settings">
          <div className="grid cols-3 recurrence-grid">
            <label>
              {text.frequency}
              <select name="recurrence_frequency" defaultValue={recurrenceDefaults.frequency}>
                <option value="DAILY">{text.daily}</option>
                <option value="WEEKLY">{text.weekly}</option>
                <option value="MONTHLY">{text.monthly}</option>
              </select>
            </label>

            <label>
              {text.repeatsEvery}
              <input type="number" name="recurrence_interval" min={1} defaultValue={recurrenceDefaults.interval} />
              <small className="muted">{text.repeatsEveryHint}</small>
            </label>

            <label>
              {text.repeatUntil}
              <input
                type="date"
                name="recurrence_until_date"
                value={recurrenceUntilDate}
                onChange={(event) => handleRecurrenceUntilDateChange(event.target.value)}
              />
            </label>
          </div>
          <label className="checkline">
              <input
                type="checkbox"
                name="recurrence_keep_local_time"
                value="1"
                defaultChecked={recurrenceDefaults.keepLocalTime}
              />
            {text.keepLocalTime}
          </label>
          <p className="muted">{text.keepLocalTimeHint}</p>
          <p className="muted">{text.recurrenceUntilHint}</p>
        </div>
      </fieldset>
    </>
  );
}
