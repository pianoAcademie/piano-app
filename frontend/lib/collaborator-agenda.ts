// The collaborator calendar uses the school's local time, never the server TZ.
export const COLLABORATOR_AGENDA_TIMEZONE = "Europe/Paris";
export type AgendaView = "month" | "week" | "day";
export type AgendaRange = { from: Date; to: Date; dayKeys: string[]; title: string };

const localDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: COLLABORATOR_AGENDA_TIMEZONE,
  year: "numeric", month: "2-digit", day: "2-digit",
});
const localClockFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: COLLABORATOR_AGENDA_TIMEZONE,
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});

export function isAgendaDateKey(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function parisDateKey(value: string | Date): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = Object.fromEntries(localDateFormatter.formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

// UTC here is only a representation of calendar dates for day arithmetic and
// labels. These values are converted to real Paris midnights for API queries.
function calendarDate(key: string): Date {
  if (!isAgendaDateKey(key)) throw new RangeError(`Invalid agenda date: ${key}`);
  return new Date(`${key}T00:00:00.000Z`);
}

function addCalendarDays(date: Date, count: number): Date {
  const result = new Date(date);
  result.setUTCDate(result.getUTCDate() + count);
  return result;
}

function parisMidnight(key: string): Date {
  const target = calendarDate(key).getTime();
  let instant = target;
  // Resolve the offset at the boundary itself, including DST transitions.
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const parts = Object.fromEntries(localClockFormatter.formatToParts(new Date(instant)).map((part) => [part.type, part.value]));
    const wallTime = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second));
    const delta = target - wallTime;
    if (delta === 0) return new Date(instant);
    instant += delta;
  }
  throw new RangeError(`Cannot resolve Paris midnight: ${key}`);
}

export function buildAgendaRange(view: AgendaView, focusDayKey: string, locale: string): AgendaRange {
  const focus = calendarDate(focusDayKey);
  let first = focus;
  let next = addCalendarDays(focus, 1);
  if (view === "week") {
    first = addCalendarDays(focus, -((focus.getUTCDay() + 6) % 7));
    next = addCalendarDays(first, 7);
  } else if (view === "month") {
    first = new Date(focus);
    first.setUTCDate(1);
    next = new Date(first);
    next.setUTCMonth(next.getUTCMonth() + 1);
  }
  const dayKeys: string[] = [];
  for (let day = first; day < next; day = addCalendarDays(day, 1)) {
    dayKeys.push(day.toISOString().slice(0, 10));
  }
  let title: string;
  if (view === "day") {
    title = formatAgendaDayLabel(focusDayKey, view, locale);
  } else if (view === "month") {
    title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(first);
  } else {
    const format = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
    title = `${format.format(first)} - ${format.format(addCalendarDays(next, -1))}`;
  }
  return {
    from: parisMidnight(dayKeys[0]),
    // The sessions API's `to` bound is inclusive.
    to: new Date(parisMidnight(next.toISOString().slice(0, 10)).getTime() - 1),
    dayKeys,
    title,
  };
}

export function formatAgendaTime(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: COLLABORATOR_AGENDA_TIMEZONE,
  }).format(date);
}

export function formatAgendaDayLabel(key: string, view: AgendaView, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: view === "day" ? "long" : "short",
    day: "2-digit",
    month: view === "day" ? "long" : "short",
    ...(view === "day" ? { year: "numeric" as const } : {}),
    timeZone: "UTC",
  }).format(calendarDate(key));
}
