"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

type UiLanguage = "fr" | "en";

type Props = {
  computedPrice: string | null;
  effectivePrice: string | null;
  currency: string;
  initialPriceMode: string;
  initialForcedPrice: string | null;
  language?: UiLanguage;
};

function formatMoney(amountRaw: string | null, currency: string, language: UiLanguage): string {
  if (!amountRaw) {
    return "-";
  }
  const amount = Number(amountRaw);
  if (!Number.isFinite(amount)) {
    return `${amountRaw} ${currency}`;
  }
  try {
    return new Intl.NumberFormat(language === "en" ? "en-GB" : "fr-FR", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

export default function CatalogKitPriceFields({
  computedPrice,
  effectivePrice,
  currency,
  initialPriceMode,
  initialForcedPrice,
  language,
}: Props): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage = language ?? (searchParams?.get("lang") === "en" ? "en" : "fr");
  const initialMode = initialPriceMode.trim().toLowerCase() === "forced" ? "forced" : "calculated";
  const [priceMode, setPriceMode] = useState<"calculated" | "forced">(initialMode);
  const normalizedCurrency = useMemo(() => {
    const value = currency.trim().toUpperCase();
    return /^[A-Z]{3}$/.test(value) ? value : "EUR";
  }, [currency]);
  const text = resolvedLanguage === "en"
    ? {
        title: "Price",
        automaticPrice: "Calculated price (automatic)",
        priceMode: "Price mode",
        useCalculatedPrice: "Use the calculated price",
        forcePrice: "Set a manual price",
        invoicePrice: "Invoice price incl. tax",
        currency: "Currency",
        currentInvoicePrice: "Current invoice price",
        mode: "Mode",
        forced: "Manual",
        automatic: "Automatic",
      }
    : {
        title: "Prix",
        automaticPrice: "Prix calcule (automatique)",
        priceMode: "Mode de prix",
        useCalculatedPrice: "Utiliser le prix calcule",
        forcePrice: "Forcer un prix",
        invoicePrice: "Prix TTC facture",
        currency: "Devise",
        currentInvoicePrice: "Prix facture actuel",
        mode: "Mode",
        forced: "Force",
        automatic: "Automatique",
      };

  return (
    <article className="card">
      <h4>{text.title}</h4>
      <div className="grid cols-2 config-form-grid">
        <article className="span-2 catalog-kit-price-readonly">
          <span className="muted">{text.automaticPrice}</span>
          <strong>{formatMoney(computedPrice, normalizedCurrency, resolvedLanguage)}</strong>
        </article>

        <fieldset className="span-2 catalog-kit-price-mode-group">
          <legend>{text.priceMode}</legend>
          <label className="checkline">
            <input
              type="radio"
              name="price_mode"
              value="calculated"
              checked={priceMode === "calculated"}
              onChange={() => setPriceMode("calculated")}
            />
            {text.useCalculatedPrice}
          </label>
          <label className="checkline">
            <input
              type="radio"
              name="price_mode"
              value="forced"
              checked={priceMode === "forced"}
              onChange={() => setPriceMode("forced")}
            />
            {text.forcePrice}
          </label>
        </fieldset>

        <label>
          {text.invoicePrice}
          <input
            type="number"
            name="forced_price"
            min={0}
            step="0.01"
            defaultValue={initialForcedPrice ?? ""}
            disabled={priceMode !== "forced"}
            required={priceMode === "forced"}
          />
        </label>
        <label>
          {text.currency}
          <select name="currency" defaultValue={normalizedCurrency}>
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
          </select>
        </label>

        <p className="span-2 muted">
          {text.currentInvoicePrice}: {formatMoney(effectivePrice, normalizedCurrency, resolvedLanguage)} | {text.mode}:{" "}
          {priceMode === "forced" ? text.forced : text.automatic}
        </p>
      </div>
    </article>
  );
}
