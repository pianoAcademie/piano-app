import Link from "next/link";

import { startFormulaPurchaseLinkAction } from "../../../../lib/actions";
import { backendRequest } from "../../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../../../lib/ui-i18n";
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

function formatMoney(amountRaw: string | null, currency: string, language: UiLanguage): string {
  if (!amountRaw) {
    return uiText(language, "public_formula_checkout.price_on_request");
  }
  const amount = Number(amountRaw);
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(localeForUiLanguage(language), {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function formulaTypeLabel(value: PublicFormulaPurchaseSummaryOut["formula_type"], language: UiLanguage): string {
  if (value === "PACK") {
    return uiText(language, "public_formula_checkout.type_pack");
  }
  if (value === "FORFAIT") {
    return uiText(language, "public_formula_checkout.type_forfait");
  }
  return uiText(language, "public_formula_checkout.type_subscription");
}

export default async function FormulaPurchaseLandingPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams?: SearchParams;
}): Promise<JSX.Element> {
  const query = searchParams ?? {};
  const language = normalizeUiLanguage(readParam(query, "lang"));
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const okMessage = resolveAuthOkMessage(readParam(query, "ok"), readParam(query, "ok_code"), language);
  const errorMessage = readParam(query, "error");
  const emailHint = readParam(query, "email");
  const landingHref = `/buy/formula/${params.formulaId}${language === "en" ? "?lang=en" : ""}`;

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
                <h1>{t("public_formula_checkout.landing_title")}</h1>
                <p className="muted">{t("public_formula_checkout.landing_subtitle")}</p>
              </header>

              {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
              {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

              <section className="public-buy-summary">
                <h2>{summaryResult.data.name}</h2>
                <div className="row public-buy-badges">
                  <span className="status-pill status-info">{formulaTypeLabel(summaryResult.data.formula_type, language)}</span>
                  {summaryResult.data.frequency_label ? <span className="status-pill status-ok">{summaryResult.data.frequency_label}</span> : null}
                </div>
                <p className="public-buy-price">{formatMoney(summaryResult.data.price_ttc, summaryResult.data.currency, language)}</p>
                {summaryResult.data.description ? <p className="muted">{summaryResult.data.description}</p> : null}
                {summaryResult.data.includes.length > 0 ? (
                  <section>
                    <h3>{t("public_formula_checkout.includes_title")}</h3>
                    <ul className="public-buy-list">
                      {summaryResult.data.includes.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {summaryResult.data.restriction_labels.length > 0 ? (
                  <section>
                    <h3>{t("public_formula_checkout.restrictions_title")}</h3>
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
                <input type="hidden" name="return_to" value={landingHref} />
                <label>
                  {t("common.email")}
                  <input type="email" name="email" required autoComplete="email" defaultValue={emailHint} placeholder="prenom.nom@email.com" />
                </label>
                <button type="submit">{t("common.continue")}</button>
              </form>

              <p className="muted">{t("public_formula_checkout.account_flow_help")}</p>
            </>
          ) : (
            <>
              <header className="public-buy-header">
                <h1>{t("public_formula_checkout.unavailable_title")}</h1>
              </header>
              <section className="flash-err">{summaryResult.message}</section>
              <div className="row">
                <Link href={`/login?mode=login${language === "en" ? "&lang=en" : ""}`} className="mode-link">
                  {t("auth.back_to_login")}
                </Link>
              </div>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
