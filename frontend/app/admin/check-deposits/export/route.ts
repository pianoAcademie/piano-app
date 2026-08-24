import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../lib/backend";
import type { AdminCheckDepositPaymentOut } from "../../../../lib/types";

function exportLanguage(request: NextRequest): "fr" | "en" {
  return request.nextUrl.searchParams.get("lang") === "en" ? "en" : "fr";
}

function csvCell(value: string | number | null | undefined): string {
  const text = String(value ?? "");
  if (/[;\n\r"]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function rowsToCsv(rows: AdminCheckDepositPaymentOut[]): string {
  const headers = [
    "transaction_id",
    "client_id",
    "client_name",
    "date",
    "reference",
    "invoice_number",
    "amount",
    "currency",
    "status",
    "lieu_reception",
    "situation_physique",
    "suivi",
    "nom_sur_cheque",
  ];
  const lines = rows.map((row) => [
    row.transaction_id,
    row.client_id,
    row.client_name,
    row.occurred_at.slice(0, 10),
    row.reference ?? "",
    row.invoice_number ?? "",
    row.amount_incl_vat,
    row.currency,
    row.status,
    row.receipt_location_name ?? row.receipt_location_code ?? "",
    row.custody_status ?? "",
    row.tracking_note ?? "",
    "",
  ]);
  return `${headers.join(";")}\n${lines.map((line) => line.map(csvCell).join(";")).join("\n")}\n`;
}

export async function GET(request: NextRequest): Promise<Response> {
  const language = exportLanguage(request);
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const response = await fetch(
    `${backendUrl()}/api/v1/admin/clients/check-deposits/pending?statuses=CHECK_RECEIVED,CHECK_DEPOSITED,CHECK_REFUSED`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const fallback = new URL(
      `/admin/check-deposits?error=${encodeURIComponent(language === "en" ? `Export unavailable (${response.status})` : `Export impossible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const rows = (await response.json()) as AdminCheckDepositPaymentOut[];
  const csv = `\uFEFF${rowsToCsv(rows)}`;

  return new Response(csv, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="${language === "en" ? "checks_to_deposit.csv" : "cheques_a_deposer.csv"}"`,
      "cache-control": "no-store",
    },
  });
}
