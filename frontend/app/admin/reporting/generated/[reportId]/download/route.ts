import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../lib/backend";

type RouteParams = {
  params: {
    reportId: string;
  };
};

export async function GET(_request: Request, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Session expiree" }, { status: 401 });
  }
  const response = await fetch(`${backendUrl()}/api/v1/admin/reports/generated/${encodeURIComponent(params.reportId)}/download`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });
  const content = await response.arrayBuffer();
  return new Response(content, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") || 'attachment; filename="rapport"',
    },
  });
}
