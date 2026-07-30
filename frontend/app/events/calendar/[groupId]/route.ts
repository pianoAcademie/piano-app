import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../lib/auth-cookies";
import { backendUrl } from "../../../../lib/backend";
import type { SchoolEventRegistrationOut } from "../../../../lib/types";

type RouteParams = {
  params: {
    groupId: string;
  };
};

function icsEscape(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("\n", "\\n").replaceAll(",", "\\,").replaceAll(";", "\\;");
}

function icsDate(value: string): string {
  return new Date(value).toISOString().replaceAll("-", "").replaceAll(":", "").replace(".000", "");
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getPortalToken();
  if (!token) {
    return NextResponse.redirect(new URL("/login?error_code=session_expired", request.url), 302);
  }
  const response = await fetch(`${backendUrl()}/api/v1/clients/me/event-registrations`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    return NextResponse.redirect(new URL("/events?error_code=calendar_unavailable", request.url), 302);
  }
  const registrations = (await response.json()) as SchoolEventRegistrationOut[];
  const group = registrations.filter((registration) => registration.group_id === params.groupId);
  if (!group.length || group.every((registration) => registration.status === "CANCELLED")) {
    return NextResponse.redirect(new URL("/events?error_code=calendar_unavailable", request.url), 302);
  }
  const first = group[0];
  const participants = group.map((registration) => registration.participant_display_name).join(", ");
  const calendar = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Piano Academie//School Events//FR",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:school-event-${params.groupId}@piano-academie.com`,
    `DTSTAMP:${icsDate(new Date().toISOString())}`,
    `DTSTART:${icsDate(first.start_at_utc)}`,
    `DTEND:${icsDate(first.end_at_utc)}`,
    `SUMMARY:${icsEscape(first.event_title_fr)}`,
    `LOCATION:${icsEscape(first.location_name ?? "")}`,
    `DESCRIPTION:${icsEscape(`Participants : ${participants}`)}`,
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");
  return new Response(calendar, {
    status: 200,
    headers: {
      "content-type": "text/calendar; charset=utf-8",
      "content-disposition": `attachment; filename="evenement-${first.event_slug}.ics"`,
      "cache-control": "no-store",
    },
  });
}
