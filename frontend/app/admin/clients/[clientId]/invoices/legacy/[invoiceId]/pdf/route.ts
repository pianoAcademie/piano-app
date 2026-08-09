import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    invoiceId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login?error_code=session_expired", request.url), 302);
  }

  const inline = request.nextUrl.searchParams.get("inline") === "true";
  const upstreamUrl = new URL(
    `${backendUrl()}/api/v1/admin/clients/${params.clientId}/invoices/legacy/${params.invoiceId}/download`,
  );
  upstreamUrl.searchParams.set("inline", inline ? "true" : "false");
  const response = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/admin/clients/${params.clientId}?tab=factures&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  return new Response(await response.arrayBuffer(), {
    status: 200,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/pdf",
      "content-disposition":
        response.headers.get("content-disposition") ??
        `${inline ? "inline" : "attachment"}; filename="facture-sportigo.pdf"`,
      "cache-control": "no-store",
    },
  });
}
