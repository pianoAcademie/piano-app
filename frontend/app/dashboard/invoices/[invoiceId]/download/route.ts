import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";

type RouteParams = {
  params: {
    invoiceId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = getPortalToken();
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const invoiceId = params.invoiceId;
  const url = `${backendUrl()}/api/v1/clients/me/invoices/${invoiceId}/download`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/client?tab=finance&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="facture.pdf"';
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
