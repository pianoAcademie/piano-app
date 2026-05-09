function csvCell(value: string | number | null | undefined): string {
  const text = String(value ?? "");
  if (/[;\n\r"]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function rowsToCsv(): string {
  const headers = [
    "transaction_id",
    "reference",
    "amount",
    "payer_name",
    "client_name",
    "commentaire",
  ];
  const examples = [
    ["", "1234567", "450.00", "DUPONT MARIE", "", "Rapprochement possible par numero + montant"],
    ["", "", "320.00", "MARTIN", "", "payer_name peut aussi venir d'une colonne emetteur/tireur/titulaire"],
    ["coller-ici-un-transaction-id-exporte", "", "", "", "", "Rapprochement le plus fiable"],
  ];
  return `${headers.join(";")}\n${examples.map((line) => line.map(csvCell).join(";")).join("\n")}\n`;
}

export function GET(): Response {
  const csv = `\uFEFF${rowsToCsv()}`;
  return new Response(csv, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="modele_import_cheques.csv"',
      "cache-control": "no-store",
    },
  });
}
