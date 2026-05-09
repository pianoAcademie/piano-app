import { NextRequest } from "next/server";

function csvCell(value: string | number | null | undefined): string {
  const text = String(value ?? "");
  if (/[;\n\r"]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function rowsToCsv(language: "fr" | "en"): string {
  const headers = [
    "transaction_id",
    "reference",
    "amount",
    "payer_name",
    "client_name",
    "commentaire",
  ];
  const examples = language === "en"
    ? [
        ["", "1234567", "450.00", "SMITH MARIE", "", "Possible match by number + amount"],
        ["", "", "320.00", "MARTIN", "", "payer_name can also come from an issuer/drawer/account holder column"],
        ["paste-an-exported-transaction-id-here", "", "", "", "", "Most reliable match"],
      ]
    : [
        ["", "1234567", "450.00", "DUPONT MARIE", "", "Rapprochement possible par numero + montant"],
        ["", "", "320.00", "MARTIN", "", "payer_name peut aussi venir d'une colonne emetteur/tireur/titulaire"],
        ["coller-ici-un-transaction-id-exporte", "", "", "", "", "Rapprochement le plus fiable"],
      ];
  return `${headers.join(";")}\n${examples.map((line) => line.map(csvCell).join(";")).join("\n")}\n`;
}

export function GET(request: NextRequest): Response {
  const language = request.nextUrl.searchParams.get("lang") === "en" ? "en" : "fr";
  const csv = `\uFEFF${rowsToCsv(language)}`;
  return new Response(csv, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="${language === "en" ? "check_import_template.csv" : "modele_import_cheques.csv"}"`,
      "cache-control": "no-store",
    },
  });
}
