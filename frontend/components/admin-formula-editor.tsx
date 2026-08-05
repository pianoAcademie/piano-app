/* eslint-disable react/no-array-index-key */
"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { createAdminFormulaAction, disableAdminFormulaAction, duplicateAdminFormulaAction, updateAdminFormulaAction } from "../lib/actions";
import type {
  AdminCreditTypeOut,
  AdminFormulaCreditGrantsRelation,
  AdminFormulaOut,
  AdminFormulaPriceTaxMode,
  AdminFormulaRestrictionPeriod,
  AdminPaymentMethodOptionOut,
  CourseTypeOut,
} from "../lib/types";
import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type FormulaEditorMode = "create" | "edit";

type AdminFormulaEditorProps = {
  mode: FormulaEditorMode;
  formula: AdminFormulaOut | null;
  courseTypes: CourseTypeOut[];
  creditTypes: AdminCreditTypeOut[];
  paymentMethods: AdminPaymentMethodOptionOut[];
  currencyOptions: string[];
  returnTo: string;
  backHref: string;
  okMessage?: string;
  errorMessage?: string;
  language?: UiLanguage | string;
};

type CreditGrantRow = {
  key: string;
  creditTypeId: string;
  creditsCount: string;
};

type RestrictionRow = {
  key: string;
  period: AdminFormulaRestrictionPeriod | "";
  maxBookings: string;
  courseTypeIds: string[];
};

const RESTRICTION_PERIOD_OPTIONS: Array<{ value: AdminFormulaRestrictionPeriod; labelKey: string }> = [
  { value: "ACTIVE_BOOKINGS", labelKey: "admin.formulas.restriction_active_bookings" },
  { value: "DAY", labelKey: "admin.formulas.restriction_day" },
  { value: "WEEK", labelKey: "admin.formulas.restriction_week" },
  { value: "MONTH", labelKey: "admin.formulas.restriction_month" },
  { value: "ROLLING_MONTH", labelKey: "admin.formulas.restriction_rolling_month" },
  { value: "SEMESTER", labelKey: "admin.formulas.restriction_semester" },
];

function newRowKey(prefix: string, index: number): string {
  return `${prefix}-${index}`;
}

function paymentMethodLabel(method: AdminPaymentMethodOptionOut, language: UiLanguage): string {
  const normalized = method.code.trim().toUpperCase();
  if (normalized === "CARD_ONLINE") return uiText(language, "admin.client_detail.billing.card_online");
  if (normalized === "SEPA_DEBIT") return uiText(language, "admin.client_detail.billing.sepa_debit");
  if (normalized === "CARD_TERMINAL") return uiText(language, "admin.client_detail.billing.card_terminal");
  if (normalized === "BANK_TRANSFER") return uiText(language, "admin.client_detail.billing.bank_transfer");
  if (normalized === "CASH") return uiText(language, "admin.client_detail.billing.cash");
  if (normalized === "CHECK") return uiText(language, "admin.client_detail.billing.check");
  if (normalized === "PAYPAL") return "PayPal";
  if (normalized === "FACTURATION_AUTO") return uiText(language, "admin.client_detail.billing.invoice");
  return method.label;
}

export default function AdminFormulaEditor({
  mode,
  formula,
  courseTypes,
  creditTypes,
  paymentMethods,
  currencyOptions,
  returnTo,
  backHref,
  okMessage,
  errorMessage,
  language: languageProp = "fr",
}: AdminFormulaEditorProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
  const action = mode === "create" ? createAdminFormulaAction : updateAdminFormulaAction;
  const title = mode === "create" ? t("admin.formulas.editor_new_title") : formula?.name || t("admin.formulas.editor_edit_title");

  const activeCreditTypes = useMemo(() => creditTypes.filter((creditType) => creditType.active), [creditTypes]);
  const availableCurrencies = useMemo(() => {
    const normalized = Array.from(
      new Set(
        currencyOptions
          .map((code) => code.trim().toUpperCase())
          .filter((code) => code.length === 3),
      ),
    );
    return normalized.length > 0 ? normalized : ["EUR", "USD"];
  }, [currencyOptions]);
  const selectedPaymentCodes = formula
    ? formula.payment_methods
    : paymentMethods.filter((method) => method.enabled).map((method) => method.code);
  const selectedEntitlementIds = formula?.entitlement_course_type_ids ?? [];
  const defaultKind = formula?.kind ?? "PACK";
  const defaultPriceTaxMode: AdminFormulaPriceTaxMode = formula?.price_tax_mode ?? "HT";
  const defaultCreditGrantsRelation: AdminFormulaCreditGrantsRelation = formula?.credit_grants_relation ?? "OR";
  const [kind, setKind] = useState<"PACK" | "SUBSCRIPTION" | "FORFAIT">(defaultKind);
  const [priceTaxMode, setPriceTaxMode] = useState<AdminFormulaPriceTaxMode>(defaultPriceTaxMode);
  const [creditGrantsRelation, setCreditGrantsRelation] = useState<AdminFormulaCreditGrantsRelation>(defaultCreditGrantsRelation);

  const [creditRows, setCreditRows] = useState<CreditGrantRow[]>(() => {
    if (formula?.credit_grants?.length) {
      return formula.credit_grants.map((grant, index) => ({
        key: newRowKey("cg", index),
        creditTypeId: grant.credit_type_id,
        creditsCount: String(grant.credits_count),
      }));
    }

    const defaultCreditTypeId = activeCreditTypes[0]?.id ?? "";
    if (formula?.kind === "PACK") {
      return [
        {
          key: newRowKey("cg", 0),
          creditTypeId: defaultCreditTypeId,
          creditsCount: String(formula.credits_count ?? 1),
        },
      ];
    }

    return [
      {
        key: newRowKey("cg", 0),
        creditTypeId: defaultCreditTypeId,
        creditsCount: "1",
      },
    ];
  });
  const [creditRowIndex, setCreditRowIndex] = useState<number>(Math.max(creditRows.length, 1));

  const [restrictionRows, setRestrictionRows] = useState<RestrictionRow[]>(() => {
    if (formula?.restrictions?.length) {
      return formula.restrictions.map((restriction, index) => ({
        key: newRowKey("r", index),
        period: restriction.period,
        maxBookings: String(restriction.max_bookings),
        courseTypeIds: restriction.course_type_ids,
      }));
    }
    return [
      {
        key: newRowKey("r", 0),
        period: "",
        maxBookings: "",
        courseTypeIds: [],
      },
    ];
  });
  const [restrictionRowIndex, setRestrictionRowIndex] = useState<number>(Math.max(restrictionRows.length, 1));

  const totalCredits = creditRows.reduce((sum, row) => {
    const parsed = Number.parseInt(row.creditsCount, 10);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return sum;
    }
    return sum + parsed;
  }, 0);

  const isForfait = kind === "FORFAIT";
  const priceLabel = priceTaxMode === "TTC" ? t("admin.formulas.editor_price_ttc") : t("admin.formulas.editor_price_ht");
  const signupLabel = priceTaxMode === "TTC" ? t("admin.formulas.editor_signup_ttc") : t("admin.formulas.editor_signup_ht");
  const priceLabelWithOptional = isForfait ? t("admin.formulas.editor_optional_parenthetical", { label: priceLabel }) : priceLabel;
  const defaultPriceValue = formula?.monthly_price_value ?? formula?.monthly_price_excl_vat ?? "";
  const defaultSignupValue = formula?.signup_fee_value ?? formula?.signup_fee_excl_vat ?? "0";
  const defaultForfaitStartDate = formula?.forfait_start_date ?? "";
  const defaultForfaitEndDate = formula?.forfait_end_date ?? "";

  return (
    <section className="admin-page-grid">
      <section className="card formula-editor-header">
        <div className="row spread">
          <div>
            <h2>{title}</h2>
          </div>

          <div className="row">
            <Link className="reset-link" href={backHref}>
              {t("admin.formulas.editor_back")}
            </Link>
          </div>
        </div>
      </section>

      {okMessage ? <section className="flash-ok">{okMessage}</section> : null}
      {errorMessage ? <section className="flash-err">{errorMessage}</section> : null}

      <form action={action} className="admin-page-grid">
        <input type="hidden" name="return_to" value={returnTo} />
        {mode === "edit" && formula ? <input type="hidden" name="formula_id" value={formula.id} /> : null}

        <section className="formula-editor-grid">
          <article className="card formula-editor-main">
            <h3>{t("admin.formulas.editor_settings_title")}</h3>
            <div className="grid cols-2 config-form-grid">
              <label className="checkline">
                <input type="checkbox" name="active" defaultChecked={formula ? formula.active : true} />
                {t("common.active")}
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_private" defaultChecked={formula ? formula.is_private : false} />
                {t("common.private")}
              </label>

              <label>
                {t("common.type")}
                <select name="kind" value={kind} onChange={(event) => setKind(event.currentTarget.value as "PACK" | "SUBSCRIPTION" | "FORFAIT")}>
                  <option value="PACK">{t("admin.formulas.editor_kind_pack")}</option>
                  <option value="SUBSCRIPTION">{t("admin.formulas.kind_subscription")}</option>
                  <option value="FORFAIT">{t("admin.formulas.editor_kind_forfait")}</option>
                </select>
              </label>

              <label>
                {t("common.name")}
                <input type="text" name="name" defaultValue={formula?.name ?? ""} required maxLength={255} />
              </label>

              <label className="span-2">
                {t("common.description")}
                <textarea name="description" defaultValue={formula?.description ?? ""} rows={3} />
              </label>

              <label>
                {t("admin.formulas.editor_price_tax_mode")}
                <select
                  name="price_tax_mode"
                  value={priceTaxMode}
                  onChange={(event) => setPriceTaxMode(event.currentTarget.value as AdminFormulaPriceTaxMode)}
                >
                  <option value="HT">{t("admin.formulas.editor_tax_ht")}</option>
                  <option value="TTC">{t("admin.formulas.editor_tax_ttc")}</option>
                </select>
              </label>

              <label>
                {priceLabelWithOptional}
                <input
                  type="number"
                  name="monthly_price_value"
                  min={0}
                  step="0.01"
                  defaultValue={defaultPriceValue}
                  required={!isForfait}
                />
              </label>

              <label>
                {t("admin.formulas.editor_currency")}
                <select name="currency_code" defaultValue={formula?.currency_code ?? availableCurrencies[0]} required>
                  {availableCurrencies.map((currencyCode) => (
                    <option key={`formula-currency-${currencyCode}`} value={currencyCode}>
                      {currencyCode}
                    </option>
                  ))}
                </select>
              </label>

              <section className="span-2 config-dynamic-section">
                <h4>{t("admin.formulas.editor_first_purchase_title")}</h4>
                <p className="muted">{t("admin.formulas.editor_first_purchase_help")}</p>
                <div className="grid cols-2 config-form-grid">
                  <label>
                    <span className="checkline">
                      <input
                        type="checkbox"
                        name="first_purchase_signup_fee_enabled"
                        defaultChecked={formula?.first_purchase_signup_fee_enabled ?? false}
                      />
                      {t("admin.formulas.editor_first_purchase_signup_fee_enabled")}
                    </span>
                    <input
                      type="number"
                      name="signup_fee_value"
                      min={0}
                      step="0.01"
                      defaultValue={defaultSignupValue}
                      placeholder={signupLabel}
                    />
                    <small className="muted">{t("admin.formulas.editor_first_purchase_signup_fee_amount_help")}</small>
                  </label>
                  <label>
                    <span className="checkline">
                      <input
                        type="checkbox"
                        name="first_purchase_partitions_enabled"
                        defaultChecked={formula?.first_purchase_partitions_enabled ?? false}
                      />
                      {t("admin.formulas.editor_first_purchase_partitions_enabled")}
                    </span>
                    <input
                      type="number"
                      name="first_purchase_partitions_price_value"
                      min={0}
                      step="0.01"
                      defaultValue={formula?.first_purchase_partitions_price_value ?? ""}
                      placeholder={t("admin.formulas.editor_first_purchase_partitions_price")}
                    />
                  </label>
                </div>
              </section>

              <label className="span-2">
                {t("admin.formulas.editor_options_csv")}
                <input
                  type="text"
                  name="options_csv"
                  defaultValue={formula?.options.join(", ") ?? ""}
                  placeholder={t("admin.formulas.editor_options_placeholder")}
                />
              </label>

              <label className="span-2">
                {t("admin.formulas.editor_entitlements")}
                <select
                  name="entitlement_course_type_ids"
                  multiple
                  size={Math.max(4, Math.min(8, courseTypes.length || 4))}
                  defaultValue={selectedEntitlementIds}
                >
                  {courseTypes.map((courseType) => (
                    <option key={courseType.id} value={courseType.id}>
                      {courseType.name}
                    </option>
                  ))}
                </select>
                <small className="muted">{t("admin.formulas.editor_multi_select_help")}</small>
              </label>

              {kind === "PACK" ? (
                <section className="span-2 config-dynamic-section">
                  <div className="row spread">
                    <h4>{t("admin.formulas.editor_credit_section")}</h4>
                    <button
                      type="button"
                      className="ghost small-btn"
                      onClick={() => {
                        setCreditRows((prev) => [
                          ...prev,
                          {
                            key: newRowKey("cg", creditRowIndex),
                            creditTypeId: activeCreditTypes[0]?.id ?? "",
                            creditsCount: "1",
                          },
                        ]);
                        setCreditRowIndex((value) => value + 1);
                      }}
                      disabled={activeCreditTypes.length === 0}
                    >
                      <span aria-hidden="true">＋</span> {t("admin.formulas.editor_add")}
                    </button>
                  </div>

                  <label>
                    {t("admin.formulas.editor_pack_validity_months")}
                    <input
                      type="number"
                      name="pack_validity_months"
                      min={1}
                      max={12}
                      step={1}
                      defaultValue={formula?.pack_validity_months ?? 12}
                      required
                    />
                  </label>

                  <p className="muted">{t("admin.formulas.editor_credit_help")}</p>
                  <p className="muted">
                    {t("admin.formulas.editor_total_credits")} <strong>{totalCredits}</strong>
                  </p>
                  {creditRows.length > 1 ? (
                    <>
                      <label>
                        {t("admin.formulas.editor_credit_relation")}
                        <select
                          name="credit_grants_relation"
                          value={creditGrantsRelation}
                          onChange={(event) => setCreditGrantsRelation(event.currentTarget.value as AdminFormulaCreditGrantsRelation)}
                        >
                          <option value="OR">{t("admin.formulas.editor_credit_relation_or")}</option>
                          <option value="AND">{t("admin.formulas.editor_credit_relation_and")}</option>
                        </select>
                      </label>
                      <small className="muted">{t("admin.formulas.editor_credit_relation_help")}</small>
                    </>
                  ) : (
                    <input type="hidden" name="credit_grants_relation" value={creditGrantsRelation} />
                  )}

                  <div className="formula-dynamic-list">
                    {creditRows.map((row, index) => (
                      <div key={row.key} className="formula-dynamic-row">
                        <input type="hidden" name="credit_grant_row_key" value={row.key} />

                        <label>
                          {t("admin.formulas.editor_credit_type")}
                          <select
                            name={`credit_grant_credit_type_id_${row.key}`}
                            value={row.creditTypeId}
                            onChange={(event) => {
                              const nextValue = event.currentTarget.value;
                              setCreditRows((prev) =>
                                prev.map((item) => (item.key === row.key ? { ...item, creditTypeId: nextValue } : item)),
                              );
                            }}
                          >
                            <option value="">{t("common.select")}</option>
                            {activeCreditTypes.map((creditType) => (
                              <option key={`grant-credit-type-${creditType.id}`} value={creditType.id}>
                                {creditType.name}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label>
                          {t("admin.formulas.editor_credit_count")}
                          <input
                            type="number"
                            name={`credit_grant_credits_count_${row.key}`}
                            min={1}
                            step={1}
                            value={row.creditsCount}
                            onChange={(event) => {
                              const nextValue = event.currentTarget.value;
                              setCreditRows((prev) =>
                                prev.map((item) => (item.key === row.key ? { ...item, creditsCount: nextValue } : item)),
                              );
                            }}
                          />
                        </label>

                        <div className="formula-dynamic-row-actions">
                          <button
                            type="button"
                            className="danger small-btn formula-row-delete-btn"
                            onClick={() => setCreditRows((prev) => prev.filter((item) => item.key !== row.key))}
                            disabled={creditRows.length === 1}
                            title={t("admin.formulas.editor_delete_credit_line")}
                          >
                            <span className="formula-row-delete-icon" aria-hidden="true">
                              🗑
                            </span>
                            <span>{t("common.delete")}</span>
                          </button>
                          <small className="muted">{t("admin.formulas.editor_line", { index: index + 1 })}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ) : kind === "FORFAIT" ? (
                <section className="span-2 config-dynamic-section">
                  <div className="grid cols-2 config-form-grid">
                    <label>
                      {t("admin.formulas.editor_forfait_start")}
                      <input type="date" name="forfait_start_date" defaultValue={defaultForfaitStartDate} required />
                    </label>
                    <label>
                      {t("admin.formulas.editor_forfait_end")}
                      <input type="date" name="forfait_end_date" defaultValue={defaultForfaitEndDate} required />
                    </label>
                  </div>
                  <p className="muted">{t("admin.formulas.editor_forfait_help")}</p>
                </section>
              ) : null}
            </div>
          </article>

          <article className="card formula-editor-side">
            <h3>{t("admin.formulas.editor_payment_title")}</h3>
            <p className="muted">{t("admin.formulas.editor_payment_help")}</p>
            <div className="config-payment-grid">
              {paymentMethods.map((method) => (
                <label key={method.code} className="checkline config-payment-line">
                  <input
                    type="checkbox"
                    name="payment_methods"
                    value={method.code}
                    defaultChecked={selectedPaymentCodes.includes(method.code)}
                  />
                  <span>{paymentMethodLabel(method, language)}</span>
                </label>
              ))}
            </div>
          </article>
        </section>

        <section className="card">
          <h3>{t("admin.formulas.editor_restriction_title")}</h3>
          <div className="row spread">
            <p className="muted">{t("admin.formulas.editor_restriction_help")}</p>
            <button
              type="button"
              className="ghost small-btn"
              onClick={() => {
                setRestrictionRows((prev) => [
                  ...prev,
                  {
                    key: newRowKey("r", restrictionRowIndex),
                    period: "",
                    maxBookings: "",
                    courseTypeIds: [],
                  },
                ]);
                setRestrictionRowIndex((value) => value + 1);
              }}
            >
              <span aria-hidden="true">＋</span> {t("admin.formulas.editor_add")}
            </button>
          </div>

          <div className="formula-dynamic-list">
            {restrictionRows.map((row, index) => (
              <article key={row.key} className="config-restriction-row">
                <input type="hidden" name="restriction_row_key" value={row.key} />
                <div className="row spread">
                  <h4>
                    <span aria-hidden="true">✎</span> {t("admin.formulas.editor_restriction_item", { index: index + 1 })}
                  </h4>
                  <button
                    type="button"
                    className="danger small-btn formula-row-delete-btn"
                    onClick={() => setRestrictionRows((prev) => prev.filter((item) => item.key !== row.key))}
                    disabled={restrictionRows.length === 1}
                    title={t("admin.formulas.editor_delete_restriction")}
                  >
                    <span className="formula-row-delete-icon" aria-hidden="true">
                      🗑
                    </span>
                    <span>{t("common.delete")}</span>
                  </button>
                </div>

                <div className="config-restriction-form-grid">
                  <label>
                    {t("common.type")}
                    <select
                      name={`restriction_period_${row.key}`}
                      value={row.period}
                      onChange={(event) => {
                        const nextValue = event.currentTarget.value as AdminFormulaRestrictionPeriod | "";
                        setRestrictionRows((prev) =>
                          prev.map((item) => (item.key === row.key ? { ...item, period: nextValue } : item)),
                        );
                      }}
                    >
                      <option value="">{t("admin.formulas.no_activity")}</option>
                      {RESTRICTION_PERIOD_OPTIONS.map((option) => (
                        <option key={`restriction-period-option-${option.value}`} value={option.value}>
                          {t(option.labelKey)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    {t("admin.formulas.editor_max_courses")}
                    <input
                      type="number"
                      name={`restriction_max_${row.key}`}
                      min={1}
                      max={200}
                      value={row.maxBookings}
                      onChange={(event) => {
                        const nextValue = event.currentTarget.value;
                        setRestrictionRows((prev) =>
                          prev.map((item) => (item.key === row.key ? { ...item, maxBookings: nextValue } : item)),
                        );
                      }}
                    />
                  </label>

                  <label className="span-2">
                    {t("admin.formulas.activities_label")}
                    <select
                      name={`restriction_course_type_ids_${row.key}`}
                      multiple
                      size={Math.max(3, Math.min(8, courseTypes.length || 3))}
                      value={row.courseTypeIds}
                      onChange={(event) => {
                        const selectedIds = Array.from(event.currentTarget.selectedOptions).map((option) => option.value);
                        setRestrictionRows((prev) =>
                          prev.map((item) => (item.key === row.key ? { ...item, courseTypeIds: selectedIds } : item)),
                        );
                      }}
                    >
                      {courseTypes.map((courseType) => (
                        <option key={`r-${row.key}-${courseType.id}`} value={courseType.id}>
                          {courseType.name}
                        </option>
                      ))}
                    </select>
                    <small className="muted">{t("admin.formulas.editor_restriction_empty_help")}</small>
                  </label>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="card formula-editor-footer">
          <div className="row">
            <button type="submit">{mode === "create" ? t("common.create") : t("common.save")}</button>
            <Link className="reset-link" href={backHref}>
              {t("common.cancel")}
            </Link>
          </div>
        </section>
      </form>

      {mode === "edit" && formula ? (
        <section className="card formula-editor-footer">
          <div className="row quick-actions-row">
            <form action={duplicateAdminFormulaAction}>
              <input type="hidden" name="formula_id" value={formula.id} />
              <input type="hidden" name="return_to" value={returnTo} />
              <button className="ghost" type="submit">
                {t("common.duplicate")}
              </button>
            </form>

            <form action={disableAdminFormulaAction}>
              <input type="hidden" name="formula_id" value={formula.id} />
              <input type="hidden" name="return_to" value={returnTo} />
              <button className="danger" type="submit" disabled={!formula.active}>
                {t("admin.formulas.disable")}
              </button>
            </form>
          </div>
        </section>
      ) : null}
    </section>
  );
}
