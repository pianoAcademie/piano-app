import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    noteId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const { clientId, noteId } = params;
  const inline = request.nextUrl.searchParams.get("inline") === "true";
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/pdf`);
  upstreamUrl.searchParams.set("inline", inline ? "true" : "false");

  const response = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const returnTab = request.nextUrl.searchParams.get("payment_return_tab") === "paiements" ? "paiements" : "factures";
    const fallback = new URL(
      `/admin/clients/${clientId}?tab=${returnTab}&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="facture-periode.pdf"';
  const contentType = response.headers.get("content-type") ?? "application/pdf";

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
