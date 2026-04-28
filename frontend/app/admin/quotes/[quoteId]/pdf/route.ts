import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../lib/backend";
import { withUiLanguage, withUiMessageCode } from "../../../../../lib/ui-messages";

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
  const language = request.nextUrl.searchParams.get("lang")?.trim().toLowerCase() === "en" ? "en" : "fr";
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = buildRedirectUrl(request, withUiLanguage("/login?error_code=session_expired", language));
    return NextResponse.redirect(loginUrl, 302);
  }

  const quoteId = String(params.quoteId || "").trim();
  if (!quoteId) {
    const fallback = buildRedirectUrl(request, withUiMessageCode("/admin/quotes", "error", "invalid_quote", { lang: language }));
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
    const quotePath = withUiLanguage(`/admin/quotes/${encodeURIComponent(quoteId)}?section=document`, language);
    const fallback = buildRedirectUrl(
      request,
      withUiMessageCode(quotePath, "error", "quote_pdf_unavailable", {
        lang: language,
        statusCode: String(upstream.status),
      }),
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
