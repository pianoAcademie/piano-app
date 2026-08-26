import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const header = [
    "code",
    "order_id",
    "line_id",
    "status",
    "paid_at",
    "product_name",
    "face_value_ttc",
    "purchase_price_ttc",
  ].join(";");
  const example = [
    "XXXX-XXXX-XXXX-XXXX",
    "000000",
    "1",
    "completed",
    "2026-08-26 15:30",
    "Carte cadeau - offre à associer",
    "150.00",
    "150.00",
  ].join(";");
  return new NextResponse(`\uFEFF${header}\n${example}\n`, {
    headers: {
      "Content-Disposition": 'attachment; filename="modele-import-cartes-cadeaux.csv"',
      "Content-Type": "text/csv; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
