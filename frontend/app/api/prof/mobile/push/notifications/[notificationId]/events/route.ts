import { NextRequest, NextResponse } from "next/server";

import { getProfessorPortalToken } from "../../../../../../../../lib/auth-cookies";
import { backendRequest } from "../../../../../../../../lib/backend";

export async function POST(request: NextRequest, { params }: { params: { notificationId: string } }): Promise<NextResponse> {
  const token = getProfessorPortalToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const notificationId = encodeURIComponent(params.notificationId);
  const result = await backendRequest<unknown>(
    `/api/v1/professors/me/push-notifications/${notificationId}/events`,
    { method: "POST", body: await request.text() },
    token,
  );
  if (!result.ok) return NextResponse.json({ detail: result.message }, { status: result.status });
  return new NextResponse(null, { status: 204 });
}
