import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../lib/backend";

type Params = {
  params: {
    professorId: string;
  };
};

export async function GET(request: NextRequest, { params }: Params): Promise<Response> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const professorId = params.professorId;
  const response = await fetch(`${backendUrl()}/api/v1/admin/collaborators/${professorId}/contract`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/admin/professors/${professorId}?tab=profil&error=${encodeURIComponent(`Contrat indisponible (${response.status})`)}`,
      request.url,
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
