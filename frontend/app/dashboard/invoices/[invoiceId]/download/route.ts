import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";

type RouteParams = {
  params: {
    invoiceId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const invoiceId = params.invoiceId.trim();
  if (!invoiceId) {
    return NextResponse.redirect("/client?tab=finance&error=Facture%20indisponible", 302);
  }

  if (invoiceId.startsWith("plan:")) {
    const subscriptionId = invoiceId.slice("plan:".length).trim();
    if (!subscriptionId) {
      return NextResponse.redirect("/client?tab=finance&error=Facture%20indisponible", 302);
    }
    return NextResponse.redirect(`/api/v1/public/invoices/plans/${encodeURIComponent(subscriptionId)}/download`, 302);
  }

  const token = getPortalToken();
  if (!token) {
    return NextResponse.redirect("/login?error=Session%20expiree", 302);
  }

  const url = `${backendUrl()}/api/v1/clients/me/invoices/${invoiceId}/download`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    return NextResponse.redirect(
      `/client?tab=finance&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      302,
    );
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
