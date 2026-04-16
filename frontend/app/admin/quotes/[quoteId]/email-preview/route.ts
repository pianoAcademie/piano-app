import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ADMIN_ACCESS_TOKEN_COOKIE, LEGACY_ACCESS_TOKEN_COOKIE } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";

type PreviewPayload = {
  recipient_email?: string | null;
  template_ref?: string | null;
};

export async function POST(request: Request, context: { params: { quoteId: string } }): Promise<Response> {
  const token = cookies().get(ADMIN_ACCESS_TOKEN_COOKIE)?.value ?? cookies().get(LEGACY_ACCESS_TOKEN_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Session expiree" }, { status: 401 });
  }

  const quoteId = context.params.quoteId?.trim();
  if (!quoteId) {
    return NextResponse.json({ detail: "Devis invalide" }, { status: 400 });
  }

  const incoming = await request.json().catch(() => null);
  if (!incoming || typeof incoming !== "object") {
    return NextResponse.json({ detail: "Payload invalide" }, { status: 400 });
  }

  const payload = incoming as PreviewPayload;
  const response = await fetch(`${backendUrl()}/api/v1/quotes/${quoteId}/email/preview`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      recipient_email: typeof payload.recipient_email === "string" ? payload.recipient_email : null,
      template_ref: typeof payload.template_ref === "string" ? payload.template_ref : null,
    }),
    cache: "no-store",
  });

  const text = await response.text();
  const parsed = text ? safeJsonParse(text) : {};
  if (!response.ok) {
    return NextResponse.json(parsed || { detail: `Backend error ${response.status}` }, { status: response.status });
  }
  return NextResponse.json(parsed, { status: 200 });
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw || "Invalid backend payload" };
  }
}
