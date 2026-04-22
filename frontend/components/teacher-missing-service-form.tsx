"use client";

import { useMemo, useState } from "react";
import { useFormStatus } from "react-dom";

import type { UiLanguage } from "../lib/ui-i18n";
import { uiText } from "../lib/ui-i18n";

type MissingServiceRule = {
  min_students: number;
  max_students: number | null;
  hourly_rate: string;
};

export type MissingServiceActivityOption = {
  id: string;
  label: string;
  duration_minutes: number;
  mode_label: string;
  default_hourly_rate: string | null;
  rules: MissingServiceRule[];
};

export type MissingServiceLocationOption = {
  id: string;
  label: string;
};

type TeacherMissingServiceFormProps = {
  action: (formData: FormData) => Promise<void>;
  year: number;
  month: number;
  returnTo: string;
  defaultDate: string;
  currency: string;
  language: UiLanguage;
  activities: MissingServiceActivityOption[];
  locations: MissingServiceLocationOption[];
};

function parseDecimal(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number.parseFloat(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value: number | null, currency: string): string {
  if (value === null) {
    return "-";
  }
  return `${value.toFixed(2).replace(".", ",")} ${currency}`;
}

function resolveHourlyRate(activity: MissingServiceActivityOption | null, attendeeCount: number): number | null {
  if (!activity) {
    return null;
  }
  const safeCount = Number.isFinite(attendeeCount) && attendeeCount >= 0 ? attendeeCount : 0;
  for (const rule of activity.rules) {
    if (safeCount < rule.min_students) {
      continue;
    }
    if (rule.max_students !== null && safeCount > rule.max_students) {
      continue;
    }
    return parseDecimal(rule.hourly_rate);
  }
  return parseDecimal(activity.default_hourly_rate);
}

function SubmitButton({ disabled, language }: { disabled: boolean; language: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="ghost" disabled={disabled || pending}>
      {pending ? uiText(language, "teacher.sending") : uiText(language, "teacher.send_to_admin")}
    </button>
  );
}

export default function TeacherMissingServiceForm({
  action,
  year,
  month,
  returnTo,
  defaultDate,
  currency,
  language,
  activities,
  locations,
}: TeacherMissingServiceFormProps): JSX.Element {
  const [courseTypeId, setCourseTypeId] = useState<string>(activities[0]?.id ?? "");
  const [attendeeCount, setAttendeeCount] = useState<number>(1);

  const selectedActivity = useMemo(
    () => activities.find((item) => item.id === courseTypeId) ?? null,
    [activities, courseTypeId],
  );
  const estimatedRate = useMemo(
    () => resolveHourlyRate(selectedActivity, attendeeCount),
    [selectedActivity, attendeeCount],
  );
  const hasSelectableData = activities.length > 0 && locations.length > 0;

  return (
    <form action={action} className="grid top-gap-sm teacher-form-stack">
      <input type="hidden" name="year" value={year} />
      <input type="hidden" name="month" value={month} />
      <input type="hidden" name="return_to" value={returnTo} />

      <label>
        {uiText(language, "teacher.service_date")}
        <input type="date" name="service_date" required defaultValue={defaultDate} />
      </label>

      <label>
        {uiText(language, "teacher.service_type")}
        <select
          name="course_type_id"
          required
          value={courseTypeId}
          onChange={(event) => setCourseTypeId(event.target.value)}
          disabled={!hasSelectableData}
        >
          {activities.length === 0 ? <option value="">{uiText(language, "teacher.no_service_available")}</option> : null}
          {activities.map((activity) => (
            <option key={activity.id} value={activity.id}>
              {activity.label} • {activity.mode_label}
            </option>
          ))}
        </select>
      </label>

      <label>
        {uiText(language, "teacher.location_required")}
        <select name="location_id" required disabled={!hasSelectableData}>
          {locations.length === 0 ? <option value="">{uiText(language, "teacher.no_location_available")}</option> : null}
          {locations.map((location) => (
            <option key={location.id} value={location.id}>
              {location.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        {uiText(language, "teacher.student_or_group")}
        <input type="text" name="student_or_group" maxLength={200} placeholder={uiText(language, "teacher.student_or_group_placeholder")} />
      </label>

      <label>
        {uiText(language, "teacher.attendee_count")}
        <input
          type="number"
          name="attendee_count"
          min={0}
          max={300}
          value={attendeeCount}
          onChange={(event) => {
            const parsed = Number.parseInt(event.target.value, 10);
            setAttendeeCount(Number.isFinite(parsed) && parsed >= 0 ? parsed : 0);
          }}
        />
      </label>

      <label>
        {uiText(language, "teacher.duration_auto")}
        <input
          type="text"
          value={selectedActivity ? `${selectedActivity.duration_minutes} min` : "-"}
          readOnly
          disabled
        />
      </label>

      <label>
        {uiText(language, "teacher.estimated_hourly_rate_excl_tax")}
        <input type="text" value={formatMoney(estimatedRate, currency)} readOnly disabled />
      </label>

      {!hasSelectableData ? (
        <p className="muted">{uiText(language, "teacher.cannot_send_missing_service")}</p>
      ) : (
        <p className="muted">{uiText(language, "teacher.rate_auto_help")}</p>
      )}

      <label>
        {uiText(language, "teacher.required_comment")}
        <textarea
          name="comment"
          required
          minLength={5}
          maxLength={4000}
          rows={5}
          placeholder={uiText(language, "teacher.missing_service_placeholder")}
        />
      </label>
      <SubmitButton disabled={!hasSelectableData} language={language} />
    </form>
  );
}
