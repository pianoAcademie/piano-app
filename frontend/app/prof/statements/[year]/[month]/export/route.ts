import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../../lib/backend";
import { buildPublicUrl } from "../../../../../../lib/request-url";

type RouteParams = {
  params: {
    year: string;
    month: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getPortalToken();
  if (!token) {
    const loginUrl = buildPublicUrl(request, "/login?error=Session%20expiree");
    return NextResponse.redirect(loginUrl, 302);
  }

  const year = String(params.year || "").trim();
  const month = String(params.month || "").trim();
  if (!year || !month) {
    const fallback = buildPublicUrl(request, "/prof/statements?error=Periode%20invalide");
    return NextResponse.redirect(fallback, 302);
  }

  const upstream = await fetch(`${backendUrl()}/api/v1/teacher/statements/${year}/${month}/export.csv`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!upstream.ok) {
    const fallback = buildPublicUrl(
      request,
      `/prof/statements/${year}/${month}?error=${encodeURIComponent(`Export impossible (${upstream.status})`)}`,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const body = await upstream.arrayBuffer();
  const contentType = upstream.headers.get("content-type") ?? "text/csv; charset=utf-8";
  const disposition = upstream.headers.get("content-disposition") ?? `attachment; filename="releve_prestations_${year}_${month}.csv"`;

  return new Response(body, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": disposition,
      "cache-control": "no-store",
    },
  });
}
