import { NextRequest, NextResponse } from "next/server";

import { getAdminToken } from "../../../../../lib/auth-cookies";
import { backendRequest } from "../../../../../lib/backend";
import type { AdminAdultCandidateOut, AdminClientOut } from "../../../../../lib/types";

function displayName(client: AdminClientOut): string {
  return [client.first_name, client.last_name].filter(Boolean).join(" ").trim() || client.email;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Session expirée" }, { status: 401 });
  }

  const query = (request.nextUrl.searchParams.get("q") ?? "").trim();
  if (!query) {
    return NextResponse.json([] satisfies AdminAdultCandidateOut[]);
  }
  if (query.length > 255) {
    return NextResponse.json({ detail: "Recherche trop longue" }, { status: 422 });
  }

  const params = new URLSearchParams({
    search: query,
    client_kind: "ADULT",
    include_archived: "false",
    sort_by: "last_name",
    sort_dir: "asc",
    limit: "100",
  });
  const result = await backendRequest<AdminClientOut[]>(`/api/v1/admin/clients?${params.toString()}`, {}, token);
  if (!result.ok) {
    return NextResponse.json({ detail: result.message }, { status: result.status });
  }

  const candidates: AdminAdultCandidateOut[] = result.data.map((adult) => ({
    id: adult.id,
    display_name: displayName(adult),
    email: adult.email,
    mobile_phone_1: adult.mobile_phone_1,
    mobile_phone_2: adult.mobile_phone_2,
    home_phone: adult.home_phone,
    address_line: adult.address_line,
    postal_code: adult.postal_code,
    city: adult.city,
    address_country: adult.address_country,
    residence_country: adult.residence_country,
  }));

  return NextResponse.json(candidates, { headers: { "Cache-Control": "no-store" } });
}
