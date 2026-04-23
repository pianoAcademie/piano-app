"use client";

import { useMemo, useState } from "react";

import { type UiLanguage, uiText } from "../../lib/ui-i18n";
import SessionTimeFields from "../session-time-fields";

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
  language: UiLanguage;
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
  language,
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
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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

  return (
    <div className="grid cols-4 create-session-grid">
      <label className="span-2">
        {t("admin.planning.title_label")}
        <input type="text" name="title" defaultValue={titleDefaultValue} required maxLength={255} autoFocus />
      </label>

      <label>
        {t("admin.planning.course_type")}
        <select
          name="course_type_id"
          value={selectedCourseTypeId}
          required
          onChange={(event) => setSelectedCourseTypeId(event.target.value)}
        >
          <option value="">{t("admin.planning.selection")}</option>
          {courseTypes.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
        {selectedCourseType ? (
          <small className="muted">
            {t("admin.planning.default_duration", { count: selectedCourseType.durationMinutes })} · {t("admin.planning.default_capacity", { count: selectedCourseType.defaultCapacity })} ·{" "}
            {selectedCourseType.allowsStudentBookings ? t("admin.planning.with_students") : t("admin.planning.without_students")}
          </small>
        ) : null}
      </label>

      <label>
        {t("admin.planning.coach")}
        <select name="professor_id" defaultValue={professorDefaultValue} required={Boolean(selectedCourseType?.requiresProfessor)}>
          <option value="">{selectedCourseType?.requiresProfessor ? t("admin.planning.select_teacher") : t("admin.planning.no_teacher")}</option>
          {professors.map((row) => (
            <option key={row.id} value={row.id}>
              {row.firstName} {row.lastName}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("common.location")}
        <select name="location_id" defaultValue={locationDefaultValue} required>
          {locations.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("admin.planning.filter.session_timezone")}
        <select name="session_timezone" defaultValue={timezoneDefaultValue} required>
          {sessionTimezoneOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("admin.planning.start_day")}
        <input type="date" name="start_date" defaultValue={startDateDefaultValue} required />
      </label>

      <label className="checkline create-session-toggle">
        <input type="checkbox" name="is_all_day" defaultChecked={isAllDayDefaultValue} />
        {t("admin.planning.all_day_slot")}
      </label>

      <SessionTimeFields
        key={`create-time-${selectedCourseTypeId || "default"}-${defaultDuration}`}
        startLabel={t("admin.planning.start_time")}
        endLabel={t("admin.planning.end_time")}
        durationLabel={t("admin.planning.duration_minutes")}
        labelClassName="create-time-field session-time-field"
        defaultStartTime={startTimeDefault}
        defaultEndTime={endTimeDefault}
        defaultDurationMinutes={defaultDuration}
        requiredStart
      />

      {selectedCourseType?.allowsStudentBookings === false ? (
        <label key={`create-capacity-${selectedCourseTypeId || "default"}-${draftedCapacity ?? capacityDefault}`}>
          {t("admin.planning.capacity_max")}
          <input type="hidden" name="capacity_max" value="0" />
          <input type="number" value={0} min={0} readOnly disabled />
          <small className="muted">{t("admin.planning.forced_zero_capacity")}</small>
        </label>
      ) : (
        <label key={`create-capacity-${selectedCourseTypeId || "default"}-${draftedCapacity ?? capacityDefault}`}>
          {t("admin.planning.capacity_max")}
          <input type="number" name="capacity_max" min={0} defaultValue={draftedCapacity ?? capacityDefault} required />
        </label>
      )}

      <label className="span-2">
        {t("admin.planning.zoom_link_optional")}
        <input type="url" name="zoom_link" defaultValue={zoomLinkDefaultValue} placeholder="https://..." />
      </label>
    </div>
  );
}
