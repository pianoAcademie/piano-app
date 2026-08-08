import { NextResponse } from "next/server";

import { getAdminToken } from "../../../../../../lib/auth-cookies";
import { backendRequest } from "../../../../../../lib/backend";

type AccessLinkResult = {
  client_id: string;
  email: string;
  message_id: string;
  sent_at: string;
};

export async function POST(_request: Request, context: { params: { clientId: string } }): Promise<NextResponse> {
  const token = getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Session expirée" }, { status: 401 });
  }
  const clientId = context.params.clientId?.trim();
  if (!clientId) {
    return NextResponse.json({ detail: "Client invalide" }, { status: 400 });
  }
  const result = await backendRequest<AccessLinkResult>(
    `/api/v1/admin/clients/${clientId}/send-password-email`,
    { method: "POST" },
    token,
    120_000,
  );
  if (!result.ok) {
    return NextResponse.json({ detail: result.message }, { status: result.status });
  }
  return NextResponse.json(result.data);
}
