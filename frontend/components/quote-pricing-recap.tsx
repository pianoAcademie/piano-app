export type PricingLine = { id: string; title: string; quantity: string; unit: string; total: string; kind: string; origin: string };
export function pricingMoney(value: string | number, currency = "EUR"): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency }).format(Number(value));
}
export function PricingLinesTable({ lines, currency = "EUR" }: { lines: PricingLine[]; currency?: string }): JSX.Element {
  return <div className="table-wrap"><table className="data-table pricing-recap-table">
    <thead><tr><th>Prestation / remise / supplément</th><th>Origine</th><th>Quantité</th><th>Prix unitaire TTC</th><th>Total TTC</th></tr></thead>
    <tbody>{lines.map(l => <tr key={l.id} className={l.kind === "discount" ? "pricing-discount-row" : undefined}>
      <td>{l.title}</td><td>{l.origin}</td><td>{Number(l.quantity).toLocaleString("fr-FR")}</td>
      <td>{pricingMoney(l.unit, currency)}</td><td><strong>{pricingMoney(l.total, currency)}</strong></td>
    </tr>)}</tbody>
  </table></div>;
}
export default function QuotePricingRecap({ lines, total, currency, adjustment }: {
  lines: PricingLine[]; total: string; currency: string; adjustment: { amount: number; label: string };
}): JSX.Element {
  const sum = lines.reduce((s, l) => s + Math.round(Number(l.total) * 100), 0);
  const adjusted = Math.max(0, sum + Math.round(adjustment.amount * 100));
  const matches = adjusted === Math.round(Number(total) * 100);
  return <section className="card pricing-recap" aria-label="Récapitulatif des lignes enregistrées">
    <h3>Montants enregistrés — base du prochain envoi</h3>
    <p>Les aperçus non confirmés ne modifient pas ce récapitulatif. Chaque remise et supplément est détaillé ci-dessous.</p>
    <PricingLinesTable lines={lines} currency={currency} />
    {adjustment.amount !== 0 ? <p>Ajustement hors lignes : {adjustment.label || "Ajustement financier"} · {pricingMoney(adjustment.amount, currency)}</p> : null}
    <p><strong>Total du devis enregistré : {pricingMoney(total, currency)}</strong></p>
    {!matches ? <p role="alert" className="form-feedback error">Le total ne correspond pas aux lignes et ajustements enregistrés. Faites corriger cet écart avant envoi.</p> :
      <p className="muted">Total cohérent avec les lignes et ajustements enregistrés. Le document est régénéré à l’envoi à partir de ces données.</p>}
  </section>;
}
