import { NextRequest, NextResponse } from "next/server";

import { getProfessorPortalToken } from "../../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../../lib/backend";

type RouteParams = {
  params: {
    year: string;
    month: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getProfessorPortalToken();
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const year = String(params.year || "").trim();
  const month = String(params.month || "").trim();
  if (!year || !month) {
    const fallback = new URL("/prof/statements?error_code=prof_statement_period_invalid", request.url);
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
    const fallback = new URL(`/prof/statements/${year}/${month}?error_code=prof_statement_export_failed&error_status=${encodeURIComponent(String(upstream.status))}`, request.url);
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
