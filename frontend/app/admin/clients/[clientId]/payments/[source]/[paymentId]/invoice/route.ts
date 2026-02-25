import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    source: string;
    paymentId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const { clientId, source, paymentId } = params;
  const url = `${backendUrl()}/api/v1/admin/clients/${clientId}/payments/${source}/${paymentId}/invoice`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/admin/clients/${clientId}?tab=paiements&error=${encodeURIComponent(`Facture indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="facture.txt"';
  const contentType = response.headers.get("content-type") ?? "text/plain; charset=utf-8";

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
