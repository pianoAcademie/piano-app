import { NextResponse } from "next/server";

import { getAdminToken } from "../../../../lib/auth-cookies";
import { backendRequest } from "../../../../lib/backend";
import type { AdminOnlinePresenceOut } from "../../../../lib/types";


export async function GET(): Promise<NextResponse> {
  const token = getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const result = await backendRequest<AdminOnlinePresenceOut>("/api/v1/admin/presence", {}, token);
  if (!result.ok) {
    return NextResponse.json({ detail: result.message }, { status: result.status });
  }
  return NextResponse.json(result.data);
}
