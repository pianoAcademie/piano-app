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

function rewriteContentDisposition(disposition: string, inline: boolean): string {
  if (!inline) {
    return disposition;
  }
  if (/^attachment/i.test(disposition)) {
    return disposition.replace(/^attachment/i, "inline");
  }
  if (/^inline/i.test(disposition)) {
    return disposition;
  }
  return `inline; ${disposition}`;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const { clientId, source, paymentId } = params;
  const inline = request.nextUrl.searchParams.get("inline") === "true";
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
  const contentDisposition = rewriteContentDisposition(
    response.headers.get("content-disposition") ?? 'attachment; filename="facture.pdf"',
    inline,
  );
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
