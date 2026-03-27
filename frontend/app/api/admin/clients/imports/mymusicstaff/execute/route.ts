import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl } from "../../../../../../../lib/backend";

export async function POST(request: Request): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Session expiree" }, { status: 401 });
  }

  const incoming = await request.formData();
  const csvFile = incoming.get("csv_file");
  if (!(csvFile instanceof File)) {
    return NextResponse.json({ detail: "Choisissez un fichier CSV MyMusicStaff." }, { status: 400 });
  }

  const formData = new FormData();
  formData.append("csv_file", csvFile, csvFile.name);

  const response = await fetch(`${backendUrl()}/api/v1/admin/clients/imports/mymusicstaff/execute`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
    cache: "no-store",
  });

  const payload = await response.text();
  return new Response(payload, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
