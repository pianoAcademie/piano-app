import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../lib/backend";

export async function GET(request: NextRequest): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login?error_code=session_expired", request.url), 302);
  }
  const query = request.nextUrl.searchParams.toString();
  const upstream = await fetch(
    `${backendUrl()}/api/v1/admin/reports/trial-courses/export.xlsx${query ? `?${query}` : ""}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );
  if (!upstream.ok) {
    return NextResponse.redirect(
      new URL(`/admin/reporting/trial-courses?error=${encodeURIComponent(`Export impossible (${upstream.status})`)}`, request.url),
      302,
    );
  }
  return new Response(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": upstream.headers.get("content-disposition") ?? 'attachment; filename="cours-essai.xlsx"',
      "cache-control": "no-store",
    },
  });
}
