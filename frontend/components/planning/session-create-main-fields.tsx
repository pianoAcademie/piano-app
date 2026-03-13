"use client";

import { useMemo, useState } from "react";

import SessionTimeFields from "../session-time-fields";

type CourseTypeOption = {
  id: string;
  name: string;
  durationMinutes: number;
  defaultCapacity: number;
  requiresProfessor: boolean;
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
}: SessionCreateMainFieldsProps): JSX.Element {
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
    : 1;
  const draftedCapacity = typeof draft?.capacityMax === "number" && Number.isFinite(draft.capacityMax) && draft.capacityMax > 0
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

  return (
    <div className="grid cols-4 create-session-grid">
      <label className="span-2">
        Titre
        <input type="text" name="title" defaultValue={titleDefaultValue} required maxLength={255} autoFocus />
      </label>

      <label>
        Type de cours
        <select
          name="course_type_id"
          value={selectedCourseTypeId}
          required
          onChange={(event) => setSelectedCourseTypeId(event.target.value)}
        >
          <option value="">Selectionner</option>
          {courseTypes.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
        {selectedCourseType ? (
          <small className="muted">
            Duree type: {selectedCourseType.durationMinutes} min · Capacite type: {selectedCourseType.defaultCapacity}
          </small>
        ) : null}
      </label>

      <label>
        Coach
        <select name="professor_id" defaultValue={professorDefaultValue} required={Boolean(selectedCourseType?.requiresProfessor)}>
          <option value="">{selectedCourseType?.requiresProfessor ? "Selectionner un professeur" : "Sans professeur"}</option>
          {professors.map((row) => (
            <option key={row.id} value={row.id}>
              {row.firstName} {row.lastName}
            </option>
          ))}
        </select>
      </label>

      <label>
        Lieu
        <select name="location_id" defaultValue={locationDefaultValue} required>
          {locations.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Fuseau horaire du creneau
        <select name="session_timezone" defaultValue={timezoneDefaultValue} required>
          {sessionTimezoneOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        Jour debut
        <input type="date" name="start_date" defaultValue={startDateDefaultValue} required />
      </label>

      <label className="checkline create-session-toggle">
        <input type="checkbox" name="is_all_day" defaultChecked={isAllDayDefaultValue} />
        Creneau sur toute la journee
      </label>

      <SessionTimeFields
        key={`create-time-${selectedCourseTypeId || "default"}-${defaultDuration}`}
        labelClassName="create-time-field session-time-field"
        defaultStartTime={startTimeDefault}
        defaultEndTime={endTimeDefault}
        defaultDurationMinutes={defaultDuration}
        requiredStart
      />

      <label key={`create-capacity-${selectedCourseTypeId || "default"}-${draftedCapacity ?? capacityDefault}`}>
        Capacite max
        <input type="number" name="capacity_max" min={0} defaultValue={draftedCapacity ?? capacityDefault} required />
      </label>

      <label className="span-2">
        Lien Zoom (optionnel)
        <input type="url" name="zoom_link" defaultValue={zoomLinkDefaultValue} placeholder="https://..." />
      </label>
    </div>
  );
}
