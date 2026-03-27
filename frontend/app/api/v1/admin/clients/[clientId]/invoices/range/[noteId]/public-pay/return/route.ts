import { NextRequest } from "next/server";

import { backendUrl } from "../../../../../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    noteId: string;
  };
};

function upstreamReturnUrl(request: NextRequest, clientId: string, noteId: string): URL {
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/invoices/range/${noteId}/public-pay/return`);
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });
  return upstreamUrl;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const upstream = await fetch(upstreamReturnUrl(request, params.clientId, params.noteId).toString(), {
    method: "GET",
    cache: "no-store",
  });

  const body = await upstream.text();
  const contentType = upstream.headers.get("content-type") ?? "text/html; charset=utf-8";

  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": contentType,
      "cache-control": "no-store",
    },
  });
}
