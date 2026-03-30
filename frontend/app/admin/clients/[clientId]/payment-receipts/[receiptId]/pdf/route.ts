import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../lib/backend";

type RouteParams = {
  params: {
    clientId: string;
    receiptId: string;
  };
};

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error=Session%20expiree", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const { clientId, receiptId } = params;
  const inline = request.nextUrl.searchParams.get("inline") === "true";
  const upstreamUrl = new URL(`${backendUrl()}/api/v1/admin/clients/${clientId}/payment-receipts/${receiptId}/download`);

  const response = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/admin/clients/${clientId}?tab=reservations&error=${encodeURIComponent(`Justificatif indisponible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const buffer = await response.arrayBuffer();
  const upstreamDisposition = response.headers.get("content-disposition") ?? 'attachment; filename="justificatif-paiement.pdf"';
  const fileNameMatch = upstreamDisposition.match(/filename="?([^"]+)"?/i);
  const fileName = fileNameMatch?.[1] ?? "justificatif-paiement.pdf";
  const contentType = response.headers.get("content-type") ?? "application/pdf";
  const contentDisposition = `${inline ? "inline" : "attachment"}; filename="${fileName.replace(/"/g, "")}"`;

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type": contentType,
      "content-disposition": contentDisposition,
      "cache-control": "no-store",
    },
  });
}
