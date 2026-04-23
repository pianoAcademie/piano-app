"use client";

import { useMemo, useState } from "react";

import { localeForUiLanguage, normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type ManualNonCashFlowProductOption = {
  id: string;
  title: string;
  categoryName: string | null;
  priceInclVat: string;
  vatRate: string;
};

type ManualTransactionNonCashFlowFieldsProps = {
  transactionType: "CHARGE" | "DISCOUNT";
  amountLabel: string;
  defaultVatRate: string;
  categories: string[];
  products: ManualNonCashFlowProductOption[];
  initialAmountInclVat?: string;
  initialVatRate?: string;
  currencyCode?: string;
  language?: UiLanguage | string;
};

function normalizeCategory(value: string, locale: string): string {
  return value.trim().toLocaleLowerCase(locale);
}

function formatAmountLabel(value: string, locale: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return value;
  }
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function ManualTransactionNonCashFlowFields({
  transactionType,
  amountLabel,
  defaultVatRate,
  categories,
  products,
  initialAmountInclVat = "",
  initialVatRate = "",
  currencyCode = "EUR",
  language: languageProp = "fr",
}: ManualTransactionNonCashFlowFieldsProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const locale = localeForUiLanguage(language);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [amountInclVat, setAmountInclVat] = useState<string>(initialAmountInclVat);
  const [vatRate, setVatRate] = useState<string>(initialVatRate || defaultVatRate);

  const availableProducts = useMemo(() => {
    if (transactionType !== "CHARGE" || !selectedCategory) {
      return [] as ManualNonCashFlowProductOption[];
    }
    const selectedCategoryKey = normalizeCategory(selectedCategory, locale);
    return products
      .filter((product) => normalizeCategory(product.categoryName || "", locale) === selectedCategoryKey)
      .sort((a, b) => a.title.localeCompare(b.title, locale));
  }, [locale, products, selectedCategory, transactionType]);

  return (
    <>
      <label>
        {amountLabel}
        <input
          type="number"
          name="amount_incl_vat"
          step="0.01"
          min="0.01"
          placeholder="0.00"
          value={amountInclVat}
          onChange={(event) => setAmountInclVat(event.currentTarget.value)}
          required
        />
      </label>
      <label>
        {t("common.vat")} (%)
        <input
          type="number"
          name="vat_rate"
          step="0.001"
          min="0"
          max="100"
          value={vatRate}
          onChange={(event) => setVatRate(event.currentTarget.value)}
          readOnly={transactionType === "CHARGE" && selectedProductId.length > 0}
          required
        />
      </label>
      <label>
        {t("admin.client_detail.manual_category_optional")}
        <select
          name="category"
          value={selectedCategory}
          onChange={(event) => {
            const nextCategory = event.currentTarget.value;
            setSelectedCategory(nextCategory);
            if (transactionType === "CHARGE") {
              setSelectedProductId("");
              setAmountInclVat("");
              setVatRate(defaultVatRate);
            }
          }}
        >
          <option value="">{t("admin.client_detail.manual_select_placeholder")}</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>
      {transactionType === "CHARGE" ? (
        <>
          <label>
            {t("admin.client_detail.manual_catalog_product_optional")}
            <select
              name="catalog_product_id"
              value={selectedProductId}
              onChange={(event) => {
                const nextProductId = event.currentTarget.value;
                setSelectedProductId(nextProductId);
                const selectedProduct = availableProducts.find((product) => product.id === nextProductId);
                if (!selectedProduct) {
                  setAmountInclVat("");
                  setVatRate(defaultVatRate);
                  return;
                }
                setAmountInclVat(selectedProduct.priceInclVat);
                setVatRate(selectedProduct.vatRate);
              }}
              disabled={!selectedCategory || availableProducts.length === 0}
            >
              <option value="">{t("admin.client_detail.manual_select_placeholder")}</option>
              {availableProducts.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.title} ({formatAmountLabel(product.priceInclVat, locale)} {currencyCode} {t("common.ttc")})
                </option>
              ))}
            </select>
          </label>
          <p className="muted span-2">
            {t("admin.client_detail.manual_catalog_autofill_help")}
          </p>
          {selectedCategory && availableProducts.length === 0 ? (
            <p className="muted span-2">{t("admin.client_detail.manual_no_catalog_product")}</p>
          ) : null}
        </>
      ) : null}
    </>
  );
}
