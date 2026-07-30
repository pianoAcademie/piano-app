import { NextRequest, NextResponse } from "next/server";

import { getAdminToken } from "../../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../../lib/backend";

type RouteParams = {
  params: {
    eventId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getAdminToken();
  if (!token) {
    return NextResponse.redirect(new URL("/login?error_code=session_expired", request.url), 302);
  }
  const response = await fetch(
    `${backendUrl()}/api/v1/admin/events/${encodeURIComponent(params.eventId)}/registrations/export`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );
  if (!response.ok) {
    const fallback = new URL(
      `/admin/events/${encodeURIComponent(params.eventId)}?error=${encodeURIComponent(`Export impossible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }
  const body = await response.arrayBuffer();
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": response.headers.get("content-type") ?? "text/csv; charset=utf-8",
      "content-disposition":
        response.headers.get("content-disposition") ?? 'attachment; filename="inscriptions_evenement.csv"',
      "cache-control": "no-store",
    },
  });
}
