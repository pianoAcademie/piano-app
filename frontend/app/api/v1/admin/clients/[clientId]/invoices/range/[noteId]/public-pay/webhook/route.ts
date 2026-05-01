import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    noteId: string;
  };
};

function upstreamWebhookUrl(request: Request, clientId: string, noteId: string): URL {
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/public-pay/webhook`);
  incomingUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });
  return upstreamUrl;
}

function passthroughHeaders(request: Request): HeadersInit {
  const headers: Record<string, string> = {
    "content-type": request.headers.get("content-type") || "application/json",
  };
  const userAgent = request.headers.get("user-agent");
  if (userAgent) {
    headers["user-agent"] = userAgent;
  }
  return headers;
}

export async function POST(request: Request, { params }: RouteParams): Promise<Response> {
  const rawBody = await request.text();
  const upstream = await fetch(upstreamWebhookUrl(request, params.clientId, params.noteId).toString(), {
    method: "POST",
    headers: passthroughHeaders(request),
    body: rawBody,
    cache: "no-store",
  });

  const responseText = await upstream.text();
  const contentType = upstream.headers.get("content-type") || "application/json; charset=utf-8";

  return new Response(responseText, {
    status: upstream.status,
    headers: {
      "content-type": contentType,
      "cache-control": "no-store",
    },
  });
}

export async function GET(): Promise<Response> {
  return NextResponse.json({ detail: "Method not allowed" }, { status: 405 });
}
