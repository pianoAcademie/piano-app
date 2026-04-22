"use client";

import { useMemo, useState } from "react";

type KitProductOption = {
  id: string;
  title: string;
  priceInclVat: string;
};

type KitItemSeed = {
  productId: string;
  quantity: number;
  displayOrder: number;
};

type RowState = {
  key: string;
  productId: string;
  quantity: number;
  displayOrder: number;
};

type Props = {
  products: KitProductOption[];
  initialItems: KitItemSeed[];
  initialPriceMode: string;
  initialForcedPrice: string | null;
  initialCurrency: string;
  locale?: string;
  labels: {
    compositionTitle: string;
    compositionSubtitle: string;
    addLine: string;
    emptyLine: string;
    product: string;
    selectProduct: string;
    quantity: string;
    order: string;
    unitPrice: string;
    subtotal: string;
    action: string;
    delete: string;
    priceTitle: string;
    computedPriceAutomatic: string;
    priceMode: string;
    useCalculatedPrice: string;
    forcePrice: string;
    billedPriceTtc: string;
    currency: string;
    computedPrice: string;
    billedPrice: string;
    gap: string;
  };
  maxLines?: number;
};

const CURRENCIES = ["EUR", "USD", "GBP", "CHF"];

function formatMoney(amount: number, currency: string, locale: string): string {
  if (!Number.isFinite(amount)) {
    return "-";
  }
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function parseNonNegativeNumber(raw: string): number | null {
  const value = raw.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function normalizedCurrency(raw: string): string {
  const value = raw.trim().toUpperCase();
  if (!value || !/^[A-Z]{3}$/.test(value)) {
    return "EUR";
  }
  return value;
}

function nextRowKey(seed: number): string {
  return `kit-row-${seed}`;
}

export default function CatalogKitCompositionPricing({
  products,
  initialItems,
  initialPriceMode,
  initialForcedPrice,
  initialCurrency,
  locale = "fr-FR",
  labels,
  maxLines = 20,
}: Props): JSX.Element {
  const startingRows: RowState[] = initialItems.map((item, index) => ({
    key: nextRowKey(index),
    productId: item.productId,
    quantity: Math.max(1, Number(item.quantity) || 1),
    displayOrder: Math.max(0, Number(item.displayOrder) || index),
  }));

  const [rows, setRows] = useState<RowState[]>(startingRows);
  const [nextSeed, setNextSeed] = useState(startingRows.length);
  const [priceMode, setPriceMode] = useState<"calculated" | "forced">(
    initialPriceMode.trim().toLowerCase() === "forced" ? "forced" : "calculated",
  );
  const [forcedPrice, setForcedPrice] = useState(initialForcedPrice ?? "");
  const [currency, setCurrency] = useState(normalizedCurrency(initialCurrency));

  const productPriceById = useMemo(() => {
    const out = new Map<string, number>();
    for (const product of products) {
      const parsed = Number(product.priceInclVat);
      out.set(product.id, Number.isFinite(parsed) ? parsed : 0);
    }
    return out;
  }, [products]);

  const computedPrice = useMemo(() => {
    return rows.reduce((sum, row) => {
      const unitPrice = productPriceById.get(row.productId) ?? 0;
      return sum + unitPrice * row.quantity;
    }, 0);
  }, [rows, productPriceById]);

  const forcedParsed = parseNonNegativeNumber(forcedPrice);
  const effectivePrice = priceMode === "forced" && forcedParsed !== null ? forcedParsed : computedPrice;
  const priceDelta = effectivePrice - computedPrice;

  const updateRow = (index: number, patch: Partial<RowState>): void => {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  };

  const removeRow = (index: number): void => {
    setRows((current) => current.filter((_, rowIndex) => rowIndex !== index));
  };

  const addRow = (): void => {
    setRows((current) => {
      if (current.length >= maxLines) {
        return current;
      }
      return [
        ...current,
        {
          key: nextRowKey(nextSeed),
          productId: "",
          quantity: 1,
          displayOrder: current.length,
        },
      ];
    });
    setNextSeed((value) => value + 1);
  };

  const canAddRow = rows.length < maxLines;

  return (
    <>
      <article className="card">
        <div className="row spread">
          <div>
            <h4>{labels.compositionTitle}</h4>
            <p className="muted">{labels.compositionSubtitle}</p>
          </div>
          <button type="button" className="ghost" onClick={addRow} disabled={!canAddRow}>
            {labels.addLine}
          </button>
        </div>

        {rows.length === 0 ? (
          <div className="catalog-kit-empty-state">
            <p>{labels.emptyLine}</p>
            <button type="button" className="mode-link" onClick={addRow} disabled={!canAddRow}>
              {labels.addLine}
            </button>
          </div>
        ) : (
          <div className="table-wrap catalog-kit-composition-wrap">
            <table className="data-table catalog-kit-composition-table">
              <thead>
                <tr>
                  <th>{labels.product}</th>
                  <th>{labels.quantity}</th>
                  <th>{labels.order}</th>
                  <th>{labels.unitPrice}</th>
                  <th>{labels.subtotal}</th>
                  <th>{labels.action}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const unitPrice = productPriceById.get(row.productId) ?? 0;
                  const lineTotal = unitPrice * row.quantity;
                  return (
                    <tr key={row.key}>
                      <td>
                        <select
                          name={`item_product_id_${index}`}
                          value={row.productId}
                          onChange={(event) => updateRow(index, { productId: event.target.value })}
                        >
                          <option value="">{labels.selectProduct}</option>
                          {products.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.title}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          name={`item_quantity_${index}`}
                          min={1}
                          step={1}
                          value={row.quantity}
                          onChange={(event) => {
                            const parsed = Number.parseInt(event.target.value, 10);
                            updateRow(index, { quantity: Number.isFinite(parsed) && parsed > 0 ? parsed : 1 });
                          }}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          name={`item_order_${index}`}
                          min={0}
                          step={1}
                          value={row.displayOrder}
                          onChange={(event) => {
                            const parsed = Number.parseInt(event.target.value, 10);
                            updateRow(index, { displayOrder: Number.isFinite(parsed) && parsed >= 0 ? parsed : index });
                          }}
                        />
                      </td>
                      <td>{formatMoney(unitPrice, currency, locale)}</td>
                      <td>{formatMoney(lineTotal, currency, locale)}</td>
                      <td>
                        <button type="button" className="ghost" onClick={() => removeRow(index)}>
                          {labels.delete}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <input type="hidden" name="item_count" value={rows.length} />
      </article>

      <article className="card">
        <h4>{labels.priceTitle}</h4>
        <div className="grid cols-2 config-form-grid">
          <article className="span-2 catalog-kit-price-readonly">
            <span className="muted">{labels.computedPriceAutomatic}</span>
            <strong>{formatMoney(computedPrice, currency, locale)}</strong>
          </article>

          <fieldset className="span-2 catalog-kit-price-mode-group">
            <legend>{labels.priceMode}</legend>
            <label className="checkline">
              <input
                type="radio"
                name="price_mode"
                value="calculated"
                checked={priceMode === "calculated"}
                onChange={() => setPriceMode("calculated")}
              />
              {labels.useCalculatedPrice}
            </label>
            <label className="checkline">
              <input
                type="radio"
                name="price_mode"
                value="forced"
                checked={priceMode === "forced"}
                onChange={() => setPriceMode("forced")}
              />
              {labels.forcePrice}
            </label>
          </fieldset>

          <label>
            {labels.billedPriceTtc}
            <input
              type="number"
              name="forced_price"
              min={0}
              step="0.01"
              value={forcedPrice}
              onChange={(event) => setForcedPrice(event.target.value)}
              disabled={priceMode !== "forced"}
              required={priceMode === "forced"}
            />
          </label>

          <label>
            {labels.currency}
            <select
              name="currency"
              value={currency}
              onChange={(event) => setCurrency(normalizedCurrency(event.target.value))}
            >
              {CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>

          <article className="span-2 catalog-kit-price-summary">
            <div className="row spread">
              <span>{labels.computedPrice}</span>
              <strong>{formatMoney(computedPrice, currency, locale)}</strong>
            </div>
            <div className="row spread">
              <span>{labels.billedPrice}</span>
              <strong>{formatMoney(effectivePrice, currency, locale)}</strong>
            </div>
            <div className="row spread">
              <span>{labels.gap}</span>
              <strong>{formatMoney(priceDelta, currency, locale)}</strong>
            </div>
          </article>

          <input type="hidden" name="price_incl_vat" value={effectivePrice.toFixed(2)} />
        </div>
      </article>
    </>
  );
}
