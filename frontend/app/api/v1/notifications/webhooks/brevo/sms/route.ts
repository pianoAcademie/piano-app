import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../lib/backend";

function passthroughHeaders(request: Request): HeadersInit {
  const headers: Record<string, string> = {
    "content-type": request.headers.get("content-type") || "application/json",
  };
  const userAgent = request.headers.get("user-agent");
  if (userAgent) {
    headers["user-agent"] = userAgent;
  }
  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.authorization = authorization;
  }
  return headers;
}

export async function POST(request: Request): Promise<Response> {
  const rawBody = await request.text();

  const upstream = await fetch(`${backendUrl()}/api/v1/notifications/webhooks/brevo/sms`, {
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
