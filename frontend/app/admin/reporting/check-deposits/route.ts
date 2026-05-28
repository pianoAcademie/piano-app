import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../lib/backend";

export async function GET(request: NextRequest): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/reports/check-deposits-due`);
  for (const [key, value] of request.nextUrl.searchParams.entries()) {
    upstreamUrl.searchParams.set(key, value);
  }

  const response = await fetch(upstreamUrl, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(`/admin/reporting?create=1&type=check-deposits&error=${encodeURIComponent(`Export impossible (${response.status})`)}`, request.url);
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": response.headers.get("content-type") || "application/octet-stream",
      "content-disposition": response.headers.get("content-disposition") || 'attachment; filename="cheques-a-deposer.pdf"',
      "cache-control": "no-store",
    },
  });
}
