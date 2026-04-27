import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../lib/backend";

export async function GET(request: NextRequest): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const query = request.nextUrl.searchParams.toString();
  const url = `${backendUrl()}/api/v1/admin/clients/export${query ? `?${query}` : ""}`;
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(`/admin/clients?error=${encodeURIComponent(`Export impossible (${response.status})`)}`, request.url);
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="clients_export.csv"';

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
