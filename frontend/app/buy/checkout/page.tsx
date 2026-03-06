import Link from "next/link";
import { redirect } from "next/navigation";

import { submitFormulaCheckoutAction } from "../../../lib/actions";
import { getPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import type { PublicFormulaPurchaseContextOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

function readParam(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function formatMoney(amountRaw: string | null, currency: string): string {
  if (!amountRaw) {
    return "Prix sur devis";
  }
  const amount = Number(amountRaw);
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function paymentMethodLabel(code: string): string {
  const normalized = code.trim().toUpperCase();
  if (normalized === "CARD_ONLINE") {
    return "Carte en ligne";
  }
  if (normalized === "SEPA_DEBIT") {
    return "Prelevement SEPA";
  }
  if (normalized === "BANK_TRANSFER") {
    return "Virement";
  }
  if (normalized === "CHECK") {
    return "Cheque";
  }
  if (normalized === "CASH") {
    return "Especes";
  }
  if (normalized === "PAYPAL") {
    return "PayPal";
  }
  if (normalized === "CARD_TERMINAL") {
    return "CB sur place";
  }
  return normalized || "-";
}

export default async function BuyCheckoutPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const purchaseContext = readParam(params, "purchase_context").trim();
  const okMessage = readParam(params, "ok");
  const errorMessage = readParam(params, "error");

  if (!purchaseContext) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>Contexte d achat manquant</h1>
            <p className="flash-err">Le lien de paiement est invalide. Reprends le lien de formule depuis le debut.</p>
          </article>
        </section>
      </main>
    );
  }

  const contextResult = await backendRequest<PublicFormulaPurchaseContextOut>(
    `/api/v1/public/formulas/purchase-context/${encodeURIComponent(purchaseContext)}`,
  );
  if (!contextResult.ok) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>Contexte d achat invalide</h1>
            <p className="flash-err">{contextResult.message}</p>
          </article>
        </section>
      </main>
    );
  }

  const portalToken = getPortalToken();
  if (!portalToken) {
    redirect(
      `/login?mode=login&email=${encodeURIComponent(contextResult.data.email)}&purchase_context=${encodeURIComponent(purchaseContext)}`,
    );
  }

  const summary = contextResult.data.summary;
  const returnTo = `/buy/checkout?purchase_context=${encodeURIComponent(purchaseContext)}`;
  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <header className="public-buy-header">
            <h1>Paiement de la formule</h1>
            <p className="muted">Verifier le recapitulatif, puis continuer vers le paiement securise.</p>
          </header>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

          <section className="public-buy-summary">
            <article className="public-buy-line">
              <span>Formule</span>
              <strong>{summary.name}</strong>
            </article>
            <article className="public-buy-line">
              <span>Montant TTC</span>
              <strong>{formatMoney(summary.price_ttc, summary.currency)}</strong>
            </article>
            <article className="public-buy-line">
              <span>Frequence</span>
              <strong>{summary.frequency_label ?? "Paiement unique"}</strong>
            </article>
            <article className="public-buy-line">
              <span>Email</span>
              <strong>{contextResult.data.email}</strong>
            </article>
            <article className="public-buy-line">
              <span>Moyens de paiement</span>
              <strong>{summary.payment_methods.length > 0 ? summary.payment_methods.map(paymentMethodLabel).join(", ") : "Selon configuration"}</strong>
            </article>
          </section>

          <form action={submitFormulaCheckoutAction} className="grid public-buy-form">
            <input type="hidden" name="purchase_context" value={purchaseContext} />
            <input type="hidden" name="return_to" value={returnTo} />
            <button type="submit">Payer cette formule</button>
          </form>

          <div className="row">
            <Link className="ghost small-btn" href={`/buy/formula/${summary.formula_id}`}>
              Revenir a la formule
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
