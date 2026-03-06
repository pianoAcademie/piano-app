import Link from "next/link";

import { startFormulaPurchaseLinkAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import type { PublicFormulaPurchaseSummaryOut } from "../../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;
type Params = { formulaId: string };

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

function formulaTypeLabel(value: PublicFormulaPurchaseSummaryOut["formula_type"]): string {
  if (value === "PACK") {
    return "Carnet";
  }
  if (value === "FORFAIT") {
    return "Forfait";
  }
  return "Abonnement";
}

export default async function FormulaPurchaseLandingPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const query = searchParams ?? {};
  const okMessage = readParam(query, "ok");
  const errorMessage = readParam(query, "error");
  const emailHint = readParam(query, "email");

  const summaryResult = await backendRequest<PublicFormulaPurchaseSummaryOut>(
    `/api/v1/public/formulas/${params.formulaId}/purchase-summary`,
  );

  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          {summaryResult.ok ? (
            <>
              <header className="public-buy-header">
                <h1>Confirmation de commande</h1>
                <p className="muted">Confirme ton email pour poursuivre l achat de la formule choisie.</p>
              </header>

              {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
              {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

              <section className="public-buy-summary">
                <h2>{summaryResult.data.name}</h2>
                <div className="row public-buy-badges">
                  <span className="status-pill status-info">{formulaTypeLabel(summaryResult.data.formula_type)}</span>
                  {summaryResult.data.frequency_label ? <span className="status-pill status-ok">{summaryResult.data.frequency_label}</span> : null}
                </div>
                <p className="public-buy-price">{formatMoney(summaryResult.data.price_ttc, summaryResult.data.currency)}</p>
                {summaryResult.data.description ? <p className="muted">{summaryResult.data.description}</p> : null}
                {summaryResult.data.includes.length > 0 ? (
                  <section>
                    <h3>Ce qui est inclus</h3>
                    <ul className="public-buy-list">
                      {summaryResult.data.includes.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {summaryResult.data.restriction_labels.length > 0 ? (
                  <section>
                    <h3>Restrictions principales</h3>
                    <ul className="public-buy-list">
                      {summaryResult.data.restriction_labels.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </section>

              <form action={startFormulaPurchaseLinkAction} className="grid public-buy-form">
                <input type="hidden" name="formula_id" value={summaryResult.data.formula_id} />
                <input type="hidden" name="return_to" value={`/buy/formula/${params.formulaId}`} />
                <label>
                  Email
                  <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} placeholder="prenom.nom@email.com" />
                </label>
                <button type="submit">Continuer</button>
              </form>

              <p className="muted">
                Si ton email existe deja, tu seras redirige vers la connexion. Sinon, tu passeras par la creation de compte avant le paiement.
              </p>
            </>
          ) : (
            <>
              <header className="public-buy-header">
                <h1>Formule indisponible</h1>
              </header>
              <section className="flash-err">{summaryResult.message}</section>
              <div className="row">
                <Link href="/login?mode=login" className="mode-link">
                  Retour a la connexion
                </Link>
              </div>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
