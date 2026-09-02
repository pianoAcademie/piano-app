import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../../lib/backend";

export async function GET(request: NextRequest): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login?error_code=session_expired", request.url), 302);
  }

  const professorId = request.nextUrl.searchParams.get("professor_id")?.trim() ?? "";
  const year = request.nextUrl.searchParams.get("year")?.trim() ?? "";
  const month = request.nextUrl.searchParams.get("month")?.trim() ?? "";
  if (!professorId || !/^20\d{2}$/.test(year) || !/^(?:[1-9]|1[0-2])$/.test(month)) {
    return NextResponse.redirect(
      new URL("/admin/teacher-invoicing/statements?error_code=statement_period_invalid", request.url),
      302,
    );
  }

  const upstreamPath = professorId === "all"
    ? `/api/v1/teacher/admin/statements-summary/${year}/${month}/export.pdf`
    : `/api/v1/teacher/admin/statements/${encodeURIComponent(professorId)}/${year}/${month}/export.pdf`;
  const upstream = await fetch(
    `${backendUrl()}${upstreamPath}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );

  if (!upstream.ok) {
    const fallback = new URL("/admin/teacher-invoicing/statements", request.url);
    fallback.searchParams.set("professor_id", professorId);
    fallback.searchParams.set("period", `${year}-${month.padStart(2, "0")}`);
    fallback.searchParams.set("error_code", "statement_pdf_export_failed");
    fallback.searchParams.set("error_status", String(upstream.status));
    return NextResponse.redirect(fallback, 302);
  }

  return new Response(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/pdf",
      "content-disposition": upstream.headers.get("content-disposition") ?? (
        professorId === "all"
          ? `attachment; filename="releves_professeurs_${year}-${month.padStart(2, "0")}.pdf"`
          : `attachment; filename="releve_heures_${year}_${month}.pdf"`
      ),
      "cache-control": "no-store",
    },
  });
}
