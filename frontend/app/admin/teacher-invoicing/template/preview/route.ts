import { cookies } from "next/headers";

import { backendUrl } from "../../../../../lib/backend";

export async function GET(): Promise<Response> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    return new Response("Session expiree", { status: 401 });
  }

  const response = await fetch(`${backendUrl()}/api/v1/admin/teacher-invoice-template/preview`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    return new Response(text || "Erreur preview", { status: response.status });
  }
  const bytes = await response.arrayBuffer();
  return new Response(bytes, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": 'attachment; filename="teacher-invoice-preview.pdf"',
      "Cache-Control": "no-store",
    },
  });
}
