import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../lib/backend";
import { buildPublicUrl } from "../../../../lib/request-url";

type RouteParams = {
  params: {
    quoteId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const quoteId = String(params.quoteId || "").trim();
  const token = request.nextUrl.searchParams.get("t")?.trim() ?? "";
  if (!quoteId || !token) {
    const fallback = buildPublicUrl(request, `/q/${encodeURIComponent(quoteId)}?error=Token%20PDF%20invalide`);
    return NextResponse.redirect(fallback, 302);
  }

  const upstream = await fetch(`${backendUrl()}/api/v1/public/quotes/${encodeURIComponent(quoteId)}/pdf?t=${encodeURIComponent(token)}`, {
    method: "GET",
    cache: "no-store",
  });

  if (!upstream.ok) {
    const fallback = buildPublicUrl(
      request,
      `/q/${encodeURIComponent(quoteId)}?t=${encodeURIComponent(token)}&error=${encodeURIComponent(`PDF indisponible (${upstream.status})`)}`,
    );
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
