import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../lib/backend";

type RouteParams = {
  params: {
    reportId: string;
  };
};

export async function GET(request: Request, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Session expiree" }, { status: 401 });
  }
  const requestUrl = new URL(request.url);
  const inline = requestUrl.searchParams.get("inline") === "1";
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/reports/generated/${encodeURIComponent(params.reportId)}/pdf`);
  if (inline) {
    upstreamUrl.searchParams.set("inline", "1");
  }
  const response = await fetch(upstreamUrl, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });
  const content = await response.arrayBuffer();
  return new Response(content, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/pdf",
      "Content-Disposition": inline ? 'inline; filename="rapport.pdf"' : response.headers.get("content-disposition") || 'attachment; filename="rapport.pdf"',
    },
  });
}
