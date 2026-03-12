import React from "react";

export default function QuoteClientMatchCard({
  status,
  detail,
}: {
  status: "aucun" | "probable" | "multiple" | "deja_lie";
  detail: string;
}): JSX.Element {
  const label =
    status === "aucun"
      ? "Aucun client trouve"
      : status === "probable"
      ? "Correspondance probable"
      : status === "multiple"
      ? "Plusieurs correspondances"
      : "Client deja lie";
  return (
    <article className="item quote-integration-card">
      <h4>Correspondance client</h4>
      <p className="top-gap-sm">
        <strong>{label}</strong>
      </p>
      <p className="muted">{detail}</p>
    </article>
  );
}
