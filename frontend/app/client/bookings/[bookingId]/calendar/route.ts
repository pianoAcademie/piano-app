import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";

type RouteParams = {
  params: {
    bookingId: string;
  };
};

function planningErrorRedirect(status?: number): URLSearchParams {
  const params = new URLSearchParams({ tab: "planning", error_code: "calendar_unavailable" });
  if (typeof status === "number" && Number.isFinite(status) && status > 0) {
    params.set("error_status", String(status));
  }
  return params;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getPortalToken();
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
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
    const fallback = new URL(`/client?${planningErrorRedirect(response.status).toString()}`, request.url);
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
