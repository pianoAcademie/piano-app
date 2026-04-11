import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";
import { buildPublicUrl } from "../../../../../lib/request-url";

type RouteParams = {
  params: {
    bookingId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getPortalToken();
  if (!token) {
    const loginUrl = buildPublicUrl(request, "/login?error=Session%20expiree");
    return NextResponse.redirect(loginUrl, 302);
  }

  const bookingId = params.bookingId;
  const url = `${backendUrl()}/api/v1/clients/me/bookings/${bookingId}/calendar.ics`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = buildPublicUrl(
      request,
      `/client?tab=planning&error=${encodeURIComponent(`Agenda indisponible (${response.status})`)}`,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="reservation.ics"';
  const contentType = response.headers.get("content-type") ?? "text/calendar; charset=utf-8";

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
