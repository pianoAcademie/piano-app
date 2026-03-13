"use client";

import { useMemo, useRef, useState } from "react";

type SessionTimeFieldsProps = {
  startName?: string;
  endName?: string;
  durationName?: string;
  startLabel?: string;
  endLabel?: string;
  durationLabel?: string;
  defaultStartTime?: string;
  defaultEndTime?: string;
  defaultDurationMinutes?: number | null;
  requiredStart?: boolean;
  labelClassName?: string;
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
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function durationFromTimes(start: string, end: string): number | null {
  const startMinutes = parseTimeToMinutes(start);
  const endMinutes = parseTimeToMinutes(end);
  if (startMinutes === null || endMinutes === null || endMinutes < startMinutes) {
    return null;
  }
  return endMinutes - startMinutes;
}

function endFromDuration(start: string, durationMinutes: number): string | null {
  const startMinutes = parseTimeToMinutes(start);
  if (startMinutes === null || durationMinutes <= 0) {
    return null;
  }
  const endMinutes = startMinutes + durationMinutes;
  if (endMinutes > (24 * 60) - 1) {
    return null;
  }
  return toTimeValue(endMinutes);
}

export default function SessionTimeFields({
  startName = "start_time",
  endName = "end_time",
  durationName = "duration_minutes",
  startLabel = "Heure debut",
  endLabel = "Heure fin",
  durationLabel = "Duree (minutes)",
  defaultStartTime = "12:00",
  defaultEndTime = "13:00",
  defaultDurationMinutes = null,
  requiredStart = true,
  labelClassName = "session-time-field",
}: SessionTimeFieldsProps) {
  const normalizedDuration = useMemo(() => {
    if (typeof defaultDurationMinutes === "number" && Number.isFinite(defaultDurationMinutes) && defaultDurationMinutes > 0) {
      return String(Math.floor(defaultDurationMinutes));
    }
    const computed = durationFromTimes(defaultStartTime, defaultEndTime);
    return computed && computed > 0 ? String(computed) : "";
  }, [defaultDurationMinutes, defaultEndTime, defaultStartTime]);

  const [startTime, setStartTime] = useState(defaultStartTime);
  const [endTime, setEndTime] = useState(defaultEndTime);
  const [durationValue, setDurationValue] = useState(normalizedDuration);
  const lastEdited = useRef<"start" | "end" | "duration">(normalizedDuration ? "duration" : "end");

  const handleStartTimeChange = (value: string) => {
    lastEdited.current = "start";
    setStartTime(value);
    const parsedDuration = Number.parseInt(durationValue, 10);
    if (Number.isFinite(parsedDuration) && parsedDuration > 0) {
      const computedEnd = endFromDuration(value, parsedDuration);
      if (computedEnd) {
        setEndTime(computedEnd);
        return;
      }
    }

    const computedDuration = durationFromTimes(value, endTime);
    setDurationValue(computedDuration && computedDuration > 0 ? String(computedDuration) : "");
  };

  const handleEndTimeChange = (value: string) => {
    lastEdited.current = "end";
    setEndTime(value);
    const computedDuration = durationFromTimes(startTime, value);
    setDurationValue(computedDuration && computedDuration > 0 ? String(computedDuration) : "");
  };

  const handleDurationChange = (value: string) => {
    lastEdited.current = "duration";
    const sanitized = value.replace(/[^\d]/g, "");
    setDurationValue(sanitized);

    const parsedDuration = Number.parseInt(sanitized, 10);
    if (!Number.isFinite(parsedDuration) || parsedDuration <= 0) {
      return;
    }

    const computedEnd = endFromDuration(startTime, parsedDuration);
    if (computedEnd) {
      setEndTime(computedEnd);
    }
  };

  return (
    <>
      <label className={labelClassName}>
        {startLabel}
        <input type="time" name={startName} value={startTime} required={requiredStart} onChange={(event) => handleStartTimeChange(event.target.value)} />
      </label>

      <label className={labelClassName}>
        {endLabel}
        <input type="time" name={endName} value={endTime} onChange={(event) => handleEndTimeChange(event.target.value)} />
      </label>

      <label className={labelClassName}>
        {durationLabel}
        <input
          type="number"
          min={1}
          step={1}
          name={durationName}
          value={durationValue}
          placeholder="60"
          onChange={(event) => handleDurationChange(event.target.value)}
        />
      </label>
    </>
  );
}
