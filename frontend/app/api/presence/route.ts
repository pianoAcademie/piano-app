import { NextRequest, NextResponse } from "next/server";

import { getAnyToken, getTokenForPathname } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";


export async function POST(request: NextRequest): Promise<NextResponse> {
  let token: string | null = null;
  const referer = request.headers.get("referer");
  if (referer) {
    try {
      token = getTokenForPathname(new URL(referer).pathname);
    } catch {
      token = null;
    }
  }
  token ??= getAnyToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const result = await backendRequest<unknown>(
    "/api/v1/auth/presence",
    { method: "POST", body: await request.text() },
    token,
  );
  if (!result.ok) {
    return NextResponse.json({ detail: result.message }, { status: result.status });
  }
  return NextResponse.json(result.data);
}
