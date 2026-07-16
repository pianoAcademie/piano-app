import Link from "next/link";
import { redirect } from "next/navigation";

import PortalBrandLockup from "../../../components/portal-brand-lockup";
import { submitFormulaCheckoutAction } from "../../../lib/actions";
import { getPortalToken } from "../../../lib/auth-cookies";
import { backendRequest } from "../../../lib/backend";
import { localeForUiLanguage, normalizeUiLanguage, resolveAuthOkMessage, type UiLanguage, uiText } from "../../../lib/ui-i18n";
import type { PublicFormulaPurchaseContextOut, UserOut } from "../../../lib/types";

type SearchParams = Record<string, string | string[] | undefined>;

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

function buildSessionCheckoutHref(sessionId: string, planningReturnTo: string, bookingUserId: string, language: UiLanguage): string {
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  if (planningReturnTo) {
    params.set("planning_return_to", planningReturnTo);
  }
  if (bookingUserId) {
    params.set("booking_user_id", bookingUserId);
  }
  if (language === "en") {
    params.set("lang", "en");
  }
  return `/buy/session/checkout?${params.toString()}`;
}

export default async function BuyCheckoutPage({ searchParams }: { searchParams?: SearchParams }): Promise<JSX.Element> {
  const params = searchParams ?? {};
  const queryLanguage = normalizeUiLanguage(readParam(params, "lang"));
  const purchaseContext = readParam(params, "purchase_context").trim();
  const okMessage = resolveAuthOkMessage(readParam(params, "ok"), readParam(params, "ok_code"), queryLanguage);
  const errorMessage = readParam(params, "error");
  const warningMessage = readParam(params, "warning");
  const confirmExistingPackPurchase = readParam(params, "confirm_existing_pack_purchase") === "1";

  if (!purchaseContext) {
    return (
      <main className="page public-buy-page">
        <section className="public-buy-shell">
          <article className="card public-buy-card">
            <h1>{uiText(queryLanguage, "public_formula_checkout.missing_context_title")}</h1>
            <p className="flash-err">{uiText(queryLanguage, "public_formula_checkout.missing_context_body")}</p>
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
            <h1>{uiText(queryLanguage, "public_formula_checkout.invalid_context_title")}</h1>
            <p className="flash-err">{contextResult.message}</p>
          </article>
        </section>
      </main>
    );
  }

  const portalToken = getPortalToken();
  if (!portalToken) {
    redirect(
      `/login?mode=login&email=${encodeURIComponent(contextResult.data.email)}&purchase_context=${encodeURIComponent(purchaseContext)}${queryLanguage === "en" ? "&lang=en" : ""}`,
    );
  }
  const authResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, portalToken);
  if (!authResult.ok) {
    redirect(
      `/login?mode=login&email=${encodeURIComponent(contextResult.data.email)}&purchase_context=${encodeURIComponent(
        purchaseContext,
      )}&error=${encodeURIComponent(uiText(queryLanguage, "public_formula_checkout.session_expired"))}${queryLanguage === "en" ? "&lang=en" : ""}`,
    );
  }

  const language = normalizeUiLanguage(readParam(params, "lang") || authResult.data.preferred_language);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const summary = contextResult.data.summary;
  const returnTo = `/buy/checkout?purchase_context=${encodeURIComponent(purchaseContext)}${language === "en" ? "&lang=en" : ""}`;
  const isSessionReservationFlow = Boolean(contextResult.data.session_id);
  const subscriptionPaymentMethods = summary.formula_type === "SUBSCRIPTION"
    ? summary.payment_methods.filter((method) => method === "CARD_ONLINE" || method === "SEPA_DEBIT")
    : [];
  const backHref =
    contextResult.data.session_id != null
      ? buildSessionCheckoutHref(
          String(contextResult.data.session_id),
          contextResult.data.planning_return_to || "",
          contextResult.data.booking_user_id ? String(contextResult.data.booking_user_id) : "",
          language,
        )
      : `/buy/formula/${summary.formula_id}${language === "en" ? "?lang=en" : ""}`;
  const backLabel = isSessionReservationFlow ? t("public_formula_checkout.back_to_booking_options") : t("public_formula_checkout.back_to_formula");
  return (
    <main className="page public-buy-page">
      <section className="public-buy-shell">
        <article className="card public-buy-card">
          <header className="public-buy-header">
            <PortalBrandLockup
              title={t("common.app_name")}
              subtitle={t("public_formula_checkout.brand_subtitle")}
              eyebrow="Mi-Young Lee"
              className="public-buy-brand-lockup"
            />
            <h1>{t("public_formula_checkout.checkout_title")}</h1>
            <p className="muted">{t("public_formula_checkout.checkout_subtitle")}</p>
          </header>

          {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
          {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}
          {warningMessage ? <section className="flash-warn">{warningMessage}</section> : null}

          <section className="public-buy-summary">
            <article className="public-buy-line">
              <span>{t("public_formula_checkout.formula_label")}</span>
              <strong>{summary.name}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("public_formula_checkout.amount_incl_tax")}</span>
              <strong>{formatMoney(summary.price_ttc, summary.currency, language)}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("public_formula_checkout.frequency_label")}</span>
              <strong>{summary.frequency_label ?? t("public_formula_checkout.one_time_payment")}</strong>
            </article>
            <article className="public-buy-line">
              <span>{t("common.email")}</span>
              <strong>{contextResult.data.email}</strong>
            </article>
            {!isSessionReservationFlow ? (
              <article className="public-buy-line">
                <span>{t("public_formula_checkout.payment_methods")}</span>
                <strong>
                  {summary.payment_methods.length > 0
                    ? t("public_formula_checkout.payment_methods_formula_config")
                    : t("public_formula_checkout.payment_methods_default_config")}
                </strong>
              </article>
            ) : null}
          </section>

          {isSessionReservationFlow ? <p className="muted">{t("public_formula_checkout.session_flow_online_only")}</p> : null}

          <form action={submitFormulaCheckoutAction} className="grid public-buy-form">
            <input type="hidden" name="purchase_context" value={purchaseContext} />
            <input type="hidden" name="return_to" value={returnTo} />
            {confirmExistingPackPurchase ? <input type="hidden" name="confirm_existing_pack_purchase" value="1" /> : null}
            {subscriptionPaymentMethods.length > 1 ? (
              <fieldset>
                <legend>{t("public_formula_checkout.choose_payment_method")}</legend>
                {subscriptionPaymentMethods.map((method) => (
                  <label key={method} className="row">
                    <input type="radio" name="billing_method_code" value={method} defaultChecked={method === "CARD_ONLINE"} />
                    <span>
                      <strong>{method === "SEPA_DEBIT" ? t("public_formula_checkout.sepa_debit") : t("public_formula_checkout.card")}</strong>
                      {method === "SEPA_DEBIT" ? <small className="muted">{t("public_formula_checkout.sepa_first_card_notice")}</small> : null}
                    </span>
                  </label>
                ))}
              </fieldset>
            ) : subscriptionPaymentMethods.length === 1 ? (
              <input type="hidden" name="billing_method_code" value={subscriptionPaymentMethods[0]} />
            ) : null}
            <button type="submit">{t("public_formula_checkout.pay_formula")}</button>
          </form>

          <div className="row">
            <Link className="ghost small-btn" href={backHref}>
              {backLabel}
            </Link>
          </div>
        </article>
      </section>
    </main>
  );
}
