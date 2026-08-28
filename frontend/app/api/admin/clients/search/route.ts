import { NextRequest, NextResponse } from "next/server";

import { getAdminToken } from "../../../../../lib/auth-cookies";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminClientOut } from "../../../../../lib/types";

export type AdminClientSearchCandidate = {
  id: string;
  label: string;
  email: string;
  client_kind: "ADULT" | "CHILD";
};

function displayName(client: AdminClientOut): string {
  return [client.first_name, client.last_name].filter(Boolean).join(" ").trim() || client.email || client.id;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Session expirée" }, { status: 401 });
  }

  const query = (request.nextUrl.searchParams.get("q") ?? "").trim();
  const kind = (request.nextUrl.searchParams.get("kind") ?? "").trim().toUpperCase();
  if (query.length < 2) {
    return NextResponse.json([] satisfies AdminClientSearchCandidate[]);
  }
  if (query.length > 255 || (kind !== "ADULT" && kind !== "CHILD")) {
    return NextResponse.json({ detail: "Recherche invalide" }, { status: 422 });
  }

  const params = new URLSearchParams({
    search: query,
    client_kind: kind,
    include_archived: "false",
    sort_by: "last_name",
    sort_dir: "asc",
    limit: "25",
  });
  const result = await backendRequest<AdminClientOut[]>(`/api/v1/admin/clients?${params.toString()}`, {}, token);
  if (!result.ok) {
    return NextResponse.json({ detail: result.message }, { status: result.status });
  }

  const candidates: AdminClientSearchCandidate[] = result.data.map((client) => ({
    id: client.id,
    label: displayName(client),
    email: client.email || "",
    client_kind: client.client_kind === "CHILD" ? "CHILD" : "ADULT",
  }));
  return NextResponse.json(candidates, { headers: { "Cache-Control": "private, no-store" } });
}
