import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../lib/backend";

const ACCESS_TOKEN_COOKIE = "access_token";

export async function POST(request: Request, context: { params: { productId: string } }): Promise<Response> {
  const token = cookies().get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Session expiree" }, { status: 401 });
  }

  const productId = context.params.productId?.trim();
  if (!productId) {
    return NextResponse.json({ detail: "Produit invalide" }, { status: 400 });
  }

  const incomingFormData = await request.formData();
  const file = incomingFormData.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ detail: "Fichier image requis" }, { status: 400 });
  }

  const forwarded = new FormData();
  forwarded.append("file", file, file.name || "image");

  const response = await fetch(`${backendUrl()}/api/v1/admin/config/catalog/products/${productId}/image`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: forwarded,
    cache: "no-store",
  });

  const text = await response.text();
  const payload = text ? safeJsonParse(text) : {};
  if (!response.ok) {
    return NextResponse.json(payload || { detail: `Backend error ${response.status}` }, { status: response.status });
  }
  return NextResponse.json(payload, { status: 200 });
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw || "Invalid backend payload" };
  }
}

