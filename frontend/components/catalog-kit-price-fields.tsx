"use client";

import { useMemo, useState } from "react";

type Props = {
  computedPrice: string | null;
  effectivePrice: string | null;
  currency: string;
  initialPriceMode: string;
  initialForcedPrice: string | null;
};

function formatMoney(amountRaw: string | null, currency: string): string {
  if (!amountRaw) {
    return "-";
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

export default function CatalogKitPriceFields({
  computedPrice,
  effectivePrice,
  currency,
  initialPriceMode,
  initialForcedPrice,
}: Props): JSX.Element {
  const initialMode = initialPriceMode.trim().toLowerCase() === "forced" ? "forced" : "calculated";
  const [priceMode, setPriceMode] = useState<"calculated" | "forced">(initialMode);
  const normalizedCurrency = useMemo(() => {
    const value = currency.trim().toUpperCase();
    return /^[A-Z]{3}$/.test(value) ? value : "EUR";
  }, [currency]);

  return (
    <article className="card">
      <h4>Prix</h4>
      <div className="grid cols-2 config-form-grid">
        <article className="span-2 catalog-kit-price-readonly">
          <span className="muted">Prix calcule (automatique)</span>
          <strong>{formatMoney(computedPrice, normalizedCurrency)}</strong>
        </article>

        <fieldset className="span-2 catalog-kit-price-mode-group">
          <legend>Mode de prix</legend>
          <label className="checkline">
            <input
              type="radio"
              name="price_mode"
              value="calculated"
              checked={priceMode === "calculated"}
              onChange={() => setPriceMode("calculated")}
            />
            Utiliser le prix calcule
          </label>
          <label className="checkline">
            <input
              type="radio"
              name="price_mode"
              value="forced"
              checked={priceMode === "forced"}
              onChange={() => setPriceMode("forced")}
            />
            Forcer un prix
          </label>
        </fieldset>

        <label>
          Prix TTC facture
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
          Devise
          <select name="currency" defaultValue={normalizedCurrency}>
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
          </select>
        </label>

        <p className="span-2 muted">
          Prix facture actuel: {formatMoney(effectivePrice, normalizedCurrency)} | Mode:{" "}
          {priceMode === "forced" ? "Force" : "Automatique"}
        </p>
      </div>
    </article>
  );
}
