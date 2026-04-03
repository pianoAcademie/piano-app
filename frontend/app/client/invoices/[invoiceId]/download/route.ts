import { NextRequest } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";

type RouteParams = {
  params: {
    invoiceId: string;
  };
};

function redirectTo(path: string): Response {
  return new Response(null, {
    status: 302,
    headers: {
      location: path,
      "cache-control": "no-store",
    },
  });
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const invoiceId = params.invoiceId.trim();
  if (!invoiceId) {
    return redirectTo("/client?tab=finance&error=Facture%20indisponible");
  }

  if (invoiceId.startsWith("plan:")) {
    const subscriptionId = invoiceId.slice("plan:".length).trim();
    if (!subscriptionId) {
      return redirectTo("/client?tab=finance&error=Facture%20indisponible");
    }
    return redirectTo(`/api/v1/public/invoices/plans/${encodeURIComponent(subscriptionId)}/download`);
  }

  const token = getPortalToken();
  if (!token) {
    return redirectTo("/login?error=Session%20expiree");
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
    return redirectTo(`/client?tab=finance&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`);
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
