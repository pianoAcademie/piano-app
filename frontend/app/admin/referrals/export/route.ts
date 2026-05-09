import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { backendUrl } from "../../../../lib/backend";
import type { AdminReferralRewardOut } from "../../../../lib/types";

function csvCell(value: string | number | null | undefined): string {
  const text = String(value ?? "");
  if (/[;\n\r"]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function candidateLabel(candidate: Record<string, unknown>): string {
  const name = String(candidate.display_name ?? "").trim();
  const email = String(candidate.email ?? "").trim();
  const confidence = Number(candidate.confidence ?? 0);
  const suffix = Number.isFinite(confidence) && confidence > 0 ? ` (${confidence}%)` : "";
  return `${name || email || "Candidat"}${suffix}`;
}

function rowMatchesQuery(row: AdminReferralRewardOut, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystack = normalizeSearch([
    row.declared_referrer_text,
    row.referrer_name ?? "",
    row.referrer_email ?? "",
    row.referred_client_name ?? "",
    row.referred_student_name ?? "",
    row.category ?? "",
    row.status,
    row.match_status,
    row.reward_amount,
    row.invoice_total ?? "",
    row.paid_total ?? "",
    row.threshold_amount ?? "",
    row.match_candidates.map(candidateLabel).join(" "),
  ].join(" "));
  return haystack.includes(query);
}

function rowsToCsv(rows: AdminReferralRewardOut[]): string {
  const headers = [
    "id",
    "status",
    "match_status",
    "match_confidence",
    "parrain_declare",
    "parrain",
    "parrain_email",
    "filleul",
    "eleve",
    "categorie",
    "facture_total",
    "encaisse_total",
    "seuil_avoir",
    "progression_encaissement",
    "montant_avoir",
    "devise",
    "email_annonce",
    "email_avoir",
    "intake_id",
    "quote_id",
    "credit_transaction_id",
    "candidats",
  ];
  const lines = rows.map((row) => [
    row.id,
    row.status,
    row.match_status,
    row.match_confidence,
    row.declared_referrer_text,
    row.referrer_name ?? "",
    row.referrer_email ?? "",
    row.referred_client_name ?? "",
    row.referred_student_name ?? "",
    row.category ?? "",
    row.invoice_total ?? "",
    row.paid_total ?? "",
    row.threshold_amount ?? "",
    row.payment_progress_ratio ?? "",
    row.reward_amount,
    row.currency,
    row.announcement_email_sent_at ?? "",
    row.credit_email_sent_at ?? "",
    row.typeform_intake_id ?? "",
    row.quote_id ?? "",
    row.credit_transaction_id ?? "",
    row.match_candidates.map(candidateLabel).join(" | "),
  ]);
  return `${headers.join(";")}\n${lines.map((line) => line.map(csvCell).join(";")).join("\n")}\n`;
}

export async function GET(request: NextRequest): Promise<Response> {
  const token = cookies().get("admin_access_token")?.value ?? cookies().get("access_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login?error_code=session_expired", request.url);
    return NextResponse.redirect(loginUrl, 302);
  }

  const response = await fetch(`${backendUrl()}/api/v1/admin/clients/referrals/rewards`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const fallback = new URL(
      `/admin/referrals?error=${encodeURIComponent(`Export impossible (${response.status})`)}`,
      request.url,
    );
    return NextResponse.redirect(fallback, 302);
  }

  const status = request.nextUrl.searchParams.get("status")?.trim().toUpperCase() ?? "";
  const searchQuery = normalizeSearch(request.nextUrl.searchParams.get("q")?.trim() ?? "");
  const rows = ((await response.json()) as AdminReferralRewardOut[])
    .filter((row) => (!status || row.status === status) && rowMatchesQuery(row, searchQuery));
  const csv = `\uFEFF${rowsToCsv(rows)}`;

  return new Response(csv, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="parrainages.csv"',
      "cache-control": "no-store",
    },
  });
}
