import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../lib/backend";

type RouteParams = {
  params: {
    quoteId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    const fallback = new URL("/admin/quotes?error=Devis%20invalide", request.url);
    return NextResponse.redirect(fallback, 302);
  }

  const upstream = await fetch(`${backendUrl()}/api/v1/quotes/${encodeURIComponent(quoteId)}/pdf`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!upstream.ok) {
    const fallback = new URL(`/admin/quotes?quote_id=${encodeURIComponent(quoteId)}&error=${encodeURIComponent(`PDF indisponible (${upstream.status})`)}`, request.url);
    return NextResponse.redirect(fallback, 302);
  }

  const body = await upstream.arrayBuffer();
  const contentType = upstream.headers.get("content-type") ?? "application/pdf";
  const disposition = upstream.headers.get("content-disposition") ?? 'inline; filename="devis.pdf"';

  return new Response(body, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": disposition,
      "cache-control": "no-store",
    },
  });
}
