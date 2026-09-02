import type { AdminClientBookingOut } from "./types";

export type RegularScheduleSummary = {
  key: string;
  courseTypeName: string;
  locationName: string;
  professorName: string | null;
  startAt: string;
  endAt: string;
  firstDate: string;
  lastDate: string;
  occurrenceCount: number;
  waitlisted: boolean;
  isRecurring: boolean;
};

function parisScheduleKey(start: Date, end: Date): string {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  return `${formatter.format(start)}|${formatter.format(end)}`;
}

export function regularScheduleSummaries(
  bookings: AdminClientBookingOut[],
  nowMs = Date.now(),
): RegularScheduleSummary[] {
  const groups = new Map<string, RegularScheduleSummary>();
  for (const row of bookings) {
    const bookingStatus = (row.status || "").toUpperCase();
    if (!["BOOKED", "WAITLISTED"].includes(bookingStatus)) continue;
    if ((row.session_status || "").toUpperCase() === "CANCELLED") continue;

    const start = new Date(row.session_start_at_utc);
    const end = new Date(row.session_end_at_utc);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end.getTime() < nowMs) continue;

    const scheduleKey = parisScheduleKey(start, end);
    const courseIdentity = `${row.course_type_name}|${row.location_name}|${row.professor_name || ""}`;
    const key = row.recurrence_group_id
      ? `${row.recurrence_group_id}|${courseIdentity}|${scheduleKey}`
      : `${courseIdentity}|${scheduleKey}`;
    const existing = groups.get(key);
    if (existing) {
      existing.firstDate = existing.firstDate < row.session_start_at_utc ? existing.firstDate : row.session_start_at_utc;
      existing.lastDate = existing.lastDate > row.session_start_at_utc ? existing.lastDate : row.session_start_at_utc;
      existing.occurrenceCount += 1;
      existing.waitlisted = existing.waitlisted || bookingStatus === "WAITLISTED";
      if (row.session_start_at_utc < existing.startAt) {
        existing.startAt = row.session_start_at_utc;
        existing.endAt = row.session_end_at_utc;
      }
      continue;
    }
    groups.set(key, {
      key,
      courseTypeName: row.course_type_name,
      locationName: row.location_name,
      professorName: row.professor_name,
      startAt: row.session_start_at_utc,
      endAt: row.session_end_at_utc,
      firstDate: row.session_start_at_utc,
      lastDate: row.session_start_at_utc,
      occurrenceCount: 1,
      waitlisted: bookingStatus === "WAITLISTED",
      isRecurring: Boolean(row.recurrence_group_id),
    });
  }
  return [...groups.values()]
    .filter((item) => item.isRecurring || item.occurrenceCount > 1)
    .sort((a, b) => a.startAt.localeCompare(b.startAt));
}
