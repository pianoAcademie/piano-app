import { NextRequest } from "next/server";

import { backendUrl } from "../../../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    noteId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const { clientId, noteId } = params;
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/public-pdf`);

  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });

  const response = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: {
      "user-agent": request.headers.get("user-agent") ?? "piano-academie-frontend",
    },
    cache: "no-store",
    redirect: "manual",
  });

  if (!response.ok) {
    const payload = await response.text();
    return new Response(payload || "Facture introuvable", {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "text/plain; charset=utf-8",
        "cache-control": "no-store",
      },
    });
  }

  const buffer = await response.arrayBuffer();
  return new Response(buffer, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/pdf",
      "content-disposition": response.headers.get("content-disposition") ?? 'attachment; filename="facture.pdf"',
      "cache-control": "no-store",
    },
  });
}
