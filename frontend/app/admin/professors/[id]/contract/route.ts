import { NextRequest, NextResponse } from "next/server";

import { getAdminToken } from "../../../../../lib/auth-cookies";
import { backendUrl } from "../../../../../lib/backend";
import { buildPublicUrl } from "../../../../../lib/request-url";

type Params = {
  params: {
    id: string;
  };
};

export async function GET(request: NextRequest, { params }: Params): Promise<Response> {
  const token = getAdminToken();
  if (!token) {
    const loginUrl = buildPublicUrl(request, "/login?error=Session%20expiree");
    return NextResponse.redirect(loginUrl, 302);
  }

  const professorId = params.id;
  const response = await fetch(`${backendUrl()}/api/v1/admin/collaborators/${professorId}/contract`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = buildPublicUrl(
      request,
      `/admin/professors/${professorId}?tab=profil&error=${encodeURIComponent(`Contrat indisponible (${response.status})`)}`,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const contentDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="contrat_collaborateur.pdf"';
  const contentType = response.headers.get("content-type") ?? "application/pdf";

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
