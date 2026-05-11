"use server";

import { backendRequest } from "./backend";
import type { AdminSessionOut } from "./types";

export type LivePlanningBlockInput = {
  activity_id: string | null;
  activity_label?: string | null;
  location_id: string | null;
  location_label?: string | null;
  weekday: number;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  modality?: string | null;
  selection_pending?: boolean;
  series_key?: string | null;
  [key: string]: unknown;
};

export type LivePlanningMatch = {
  block: LivePlanningBlockInput;
  sessions: Array<Record<string, unknown>>;
};

type LocalSessionParts = {
  date: string;
  start_time: string;
  end_time: string;
  weekday: number;
};

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function localParts(iso: string, timezone: string): { date: string; time: string; weekday: number } | null {
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) {
    return null;
  }
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone || "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const pick = (type: Intl.DateTimeFormatPartTypes): number => {
    const value = parts.find((part) => part.type === type)?.value ?? "0";
    return Number.parseInt(value, 10);
  };
  const year = pick("year");
  const month = pick("month");
  const day = pick("day");
  const hour = pick("hour");
  const minute = pick("minute");
  if (![year, month, day, hour, minute].every(Number.isFinite)) {
    return null;
  }
  const date = `${year}-${pad2(month)}-${pad2(day)}`;
  const time = `${pad2(hour)}:${pad2(minute)}`;
  const utcDay = new Date(`${date}T00:00:00Z`).getUTCDay();
  return {
    date,
    time,
    weekday: utcDay === 0 ? 6 : utcDay - 1,
  };
}

function sessionLocalParts(session: AdminSessionOut): LocalSessionParts | null {
  const start = localParts(session.start_at_utc, session.timezone);
  const end = localParts(session.end_at_utc, session.timezone);
  if (!start || !end) {
    return null;
  }
  return {
    date: start.date,
    start_time: start.time,
    end_time: end.time,
    weekday: start.weekday,
  };
}

function validBlock(block: LivePlanningBlockInput): boolean {
  return !block.selection_pending
    && Boolean(block.activity_id)
    && /^\d{4}-\d{2}-\d{2}$/.test(String(block.start_date || ""))
    && /^\d{4}-\d{2}-\d{2}$/.test(String(block.end_date || ""))
    && /^\d{2}:\d{2}$/.test(String(block.start_time || ""))
    && /^\d{2}:\d{2}$/.test(String(block.end_time || ""))
    && Number.isFinite(block.weekday)
    && block.weekday >= 0
    && block.weekday <= 6;
}

function blockIsOnline(block: LivePlanningBlockInput): boolean {
  const haystack = [
    block.modality,
    block.location_label,
    block.activity_label,
  ]
    .filter((item) => item !== null && item !== undefined)
    .map((item) => String(item))
    .join(" ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  return haystack.includes("online") || haystack.includes("ligne");
}

export async function loadLivePlanningMatchForBlock({
  block,
  token,
}: {
  block: LivePlanningBlockInput;
  token: string;
}): Promise<LivePlanningMatch | null> {
  if (!validBlock(block) || !block.activity_id) {
    return null;
  }

  const query = new URLSearchParams();
  query.set("course_type_id", block.activity_id);
  const isOnlineBlock = blockIsOnline(block);
  if (block.location_id && !isOnlineBlock) {
    query.set("location_id", block.location_id);
  }
  query.set("status", "SCHEDULED");
  const result = await backendRequest<AdminSessionOut[]>(`/api/v1/admin/sessions?${query.toString()}`, {}, token);
  if (!result.ok) {
    return null;
  }

  const matched = result.data
    .map((session) => ({ session, local: sessionLocalParts(session) }))
    .filter((item): item is { session: AdminSessionOut; local: LocalSessionParts } => item.local !== null)
    .filter(({ session, local }) => {
      if (session.course_type_id !== block.activity_id) {
        return false;
      }
      if (block.location_id && !isOnlineBlock && session.location_id !== block.location_id) {
        return false;
      }
      if (local.date < block.start_date || local.date > block.end_date) {
        return false;
      }
      return (
        local.weekday === block.weekday
        && local.start_time === block.start_time
        && local.end_time === block.end_time
      );
    })
    .sort((left, right) => {
      const byDate = left.local.date.localeCompare(right.local.date);
      if (byDate !== 0) {
        return byDate;
      }
      return left.local.start_time.localeCompare(right.local.start_time);
    });

  if (matched.length === 0) {
    return null;
  }

  const first = matched[0];
  const last = matched[matched.length - 1];
  const recurrenceGroups = Array.from(
    new Set(matched.map(({ session }) => String(session.recurrence_group_id || "")).filter(Boolean)),
  );
  const seriesKey = recurrenceGroups.length === 1 ? recurrenceGroups[0] : String(block.series_key || "");
  const locationId = String(block.location_id || first.session.location_id || "");
  const locationLabel = String(block.location_label || first.session.location_label || "").trim() || null;

  const nextBlock: LivePlanningBlockInput = {
    ...block,
    location_id: locationId || null,
    location_label: locationLabel,
    series_key: seriesKey || null,
    start_date: first.local.date,
    end_date: last.local.date,
    source: "live_planning",
  };

  return {
    block: nextBlock,
    sessions: matched.map(({ session, local }) => ({
      session_id: session.id,
      date: local.date,
      start_time: local.start_time,
      end_time: local.end_time,
      duration_minutes: Math.max(
        0,
        Math.round((new Date(session.end_at_utc).getTime() - new Date(session.start_at_utc).getTime()) / 60000),
      ),
      activity_id: session.course_type_id,
      activity_label: block.activity_label || session.type_label,
      location_id: session.location_id,
      location_label: session.location_label,
      modality: block.modality || null,
      weekday: local.weekday,
      weekday_label: block.weekday_label || null,
      series_key: seriesKey || null,
    })),
  };
}
