import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../lib/backend";

type RouteParams = {
  params: {
    quoteId: string;
  };
};

function requestOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const host = (forwardedHost || request.headers.get("host") || request.nextUrl.host || "localhost:3000")
    .split(",")[0]
    .trim();
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const nextProtocol = request.nextUrl.protocol.replace(/:$/, "");
  const proto = (forwardedProto || nextProtocol || (host.includes("localhost") ? "http" : "https"))
    .split(",")[0]
    .trim();
  return `${proto}://${host}`;
}

function buildRedirectUrl(request: NextRequest, path: string): URL {
  return new URL(path, requestOrigin(request));
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const quoteId = String(params.quoteId || "").trim();
  const token = request.nextUrl.searchParams.get("t")?.trim() ?? "";
  const version = request.nextUrl.searchParams.get("v")?.trim() ?? "";
  const language = request.nextUrl.searchParams.get("lang")?.trim().toLowerCase() === "en" ? "en" : "";
  const langSuffix = language ? `&lang=${encodeURIComponent(language)}` : "";
  const versionSuffix = version ? `&v=${encodeURIComponent(version)}` : "";

  if (!quoteId || !token) {
    const fallback = buildRedirectUrl(
      request,
      `/q/${encodeURIComponent(quoteId)}?error_code=quote_pdf_token_invalid${langSuffix}${versionSuffix}`,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const upstream = await fetch(
    `${backendUrl()}/api/v1/public/quotes/${encodeURIComponent(quoteId)}/pdf?t=${encodeURIComponent(token)}`,
    {
      method: "GET",
      cache: "no-store",
    },
  );

  if (!upstream.ok) {
    const fallback = buildRedirectUrl(
      request,
      `/q/${encodeURIComponent(quoteId)}?t=${encodeURIComponent(token)}&error_code=quote_pdf_unavailable&error_status=${encodeURIComponent(
        String(upstream.status),
      )}${langSuffix}${versionSuffix}`,
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
