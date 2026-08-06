import { NextRequest, NextResponse } from "next/server";

import { getPortalToken } from "../../../../../lib/auth-cookies";
import { backendRequest } from "../../../../../lib/backend";


export async function GET(): Promise<NextResponse> {
  const token = getPortalToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const result = await backendRequest<unknown[]>("/api/v1/clients/me/push-devices", {}, token);
  if (!result.ok) return NextResponse.json({ detail: result.message }, { status: result.status });
  return NextResponse.json(result.data);
}


export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = getPortalToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const body = await request.text();
  const result = await backendRequest<unknown>(
    "/api/v1/clients/me/push-devices",
    { method: "POST", body },
    token,
  );
  if (!result.ok) return NextResponse.json({ detail: result.message }, { status: result.status });
  return NextResponse.json(result.data);
}


export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const token = getPortalToken();
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const body = await request.text();
  const result = await backendRequest<unknown>(
    "/api/v1/clients/me/push-devices",
    { method: "DELETE", body },
    token,
  );
  if (!result.ok) return NextResponse.json({ detail: result.message }, { status: result.status });
  return new NextResponse(null, { status: 204 });
}
