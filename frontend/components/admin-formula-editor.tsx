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

const RESTRICTION_PERIOD_OPTIONS: Array<{ value: AdminFormulaRestrictionPeriod; label: string }> = [
  { value: "DAY", label: "par jour" },
  { value: "WEEK", label: "par semaine" },
  { value: "MONTH", label: "par mois" },
  { value: "ROLLING_MONTH", label: "par mois glissant" },
  { value: "SEMESTER", label: "par semestre" },
];

function newRowKey(prefix: string, index: number): string {
  return `${prefix}-${index}`;
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
}: AdminFormulaEditorProps): JSX.Element {
  const action = mode === "create" ? createAdminFormulaAction : updateAdminFormulaAction;
  const title = mode === "create" ? "Nouvelle formule" : formula?.name || "Edition formule";

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

  const priceLabel = priceTaxMode === "TTC" ? "Tarif TTC" : "Tarif HT";
  const signupLabel = priceTaxMode === "TTC" ? "Frais d'inscription TTC" : "Frais d'inscription HT";
  const defaultPriceValue = formula?.monthly_price_value ?? formula?.monthly_price_excl_vat ?? "";
  const defaultSignupValue = formula?.signup_fee_value ?? formula?.signup_fee_excl_vat ?? "0";

  return (
    <section className="admin-page-grid">
      <section className="card formula-editor-header">
        <div className="row spread">
          <div>
            <h2>{title}</h2>
          </div>

          <div className="row">
            <Link className="reset-link" href={backHref}>
              Retour aux formules
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
            <h3>Parametres de la formule</h3>
            <div className="grid cols-2 config-form-grid">
              <label className="checkline">
                <input type="checkbox" name="active" defaultChecked={formula ? formula.active : true} />
                Active
              </label>

              <label className="checkline">
                <input type="checkbox" name="is_private" defaultChecked={formula ? formula.is_private : false} />
                Privee
              </label>

              <label>
                Type
                <select name="kind" value={kind} onChange={(event) => setKind(event.currentTarget.value as "PACK" | "SUBSCRIPTION" | "FORFAIT")}>
                  <option value="PACK">Carnet (credits)</option>
                  <option value="SUBSCRIPTION">Abonnement</option>
                  <option value="FORFAIT">Forfait (facturation au reel)</option>
                </select>
              </label>

              <label>
                Nom
                <input type="text" name="name" defaultValue={formula?.name ?? ""} required maxLength={255} />
              </label>

              <label className="span-2">
                Description
                <textarea name="description" defaultValue={formula?.description ?? ""} rows={3} />
              </label>

              <label>
                Mode tarifaire
                <select
                  name="price_tax_mode"
                  value={priceTaxMode}
                  onChange={(event) => setPriceTaxMode(event.currentTarget.value as AdminFormulaPriceTaxMode)}
                >
                  <option value="HT">Saisie en HT</option>
                  <option value="TTC">Saisie en TTC</option>
                </select>
              </label>

              <label>
                {priceLabel}
                <input
                  type="number"
                  name="monthly_price_value"
                  min={0}
                  step="0.01"
                  defaultValue={defaultPriceValue}
                  required
                />
              </label>

              <label>
                Devise
                <select name="currency_code" defaultValue={formula?.currency_code ?? availableCurrencies[0]} required>
                  {availableCurrencies.map((currencyCode) => (
                    <option key={`formula-currency-${currencyCode}`} value={currencyCode}>
                      {currencyCode}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {signupLabel}
                <input
                  type="number"
                  name="signup_fee_value"
                  min={0}
                  step="0.01"
                  defaultValue={defaultSignupValue}
                />
              </label>

              <label className="span-2">
                Option(s) (csv)
                <input
                  type="text"
                  name="options_csv"
                  defaultValue={formula?.options.join(", ") ?? ""}
                  placeholder="ex: engagement 1 mois, acces studio"
                />
              </label>

              <label className="span-2">
                Activites accessibles
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
                <small className="muted">Maintenez Ctrl/Cmd pour selectionner plusieurs activites.</small>
              </label>

              {kind === "PACK" ? (
                <section className="span-2 config-dynamic-section">
                  <div className="row spread">
                    <h4>Credits associes</h4>
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
                      <span aria-hidden="true">＋</span> Ajouter
                    </button>
                  </div>

                  <label>
                    Duree de validite (mois)
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

                  <p className="muted">Associez un type de credit et un nombre de credits pour ce carnet.</p>
                  <p className="muted">
                    Total credits: <strong>{totalCredits}</strong>
                  </p>
                  {creditRows.length > 1 ? (
                    <>
                      <label>
                        Relation entre les lignes de credit
                        <select
                          name="credit_grants_relation"
                          value={creditGrantsRelation}
                          onChange={(event) => setCreditGrantsRelation(event.currentTarget.value as AdminFormulaCreditGrantsRelation)}
                        >
                          <option value="OR">OU (un type de credit suffit)</option>
                          <option value="AND">ET (tous les types de credit sont requis)</option>
                        </select>
                      </label>
                      <small className="muted">
                        Exemple: Presentiel ET En ligne oblige les deux credits. Presentiel OU En ligne accepte l’un des deux.
                      </small>
                    </>
                  ) : (
                    <input type="hidden" name="credit_grants_relation" value={creditGrantsRelation} />
                  )}

                  <div className="formula-dynamic-list">
                    {creditRows.map((row, index) => (
                      <div key={row.key} className="formula-dynamic-row">
                        <input type="hidden" name="credit_grant_row_key" value={row.key} />

                        <label>
                          Type de credit
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
                            <option value="">Selectionner</option>
                            {activeCreditTypes.map((creditType) => (
                              <option key={`grant-credit-type-${creditType.id}`} value={creditType.id}>
                                {creditType.name}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label>
                          Nombre de credits
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
                            title="Supprimer cette ligne de credit"
                          >
                            <span className="formula-row-delete-icon" aria-hidden="true">
                              🗑
                            </span>
                            <span>Supprimer</span>
                          </button>
                          <small className="muted">Ligne {index + 1}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ) : kind === "FORFAIT" ? (
                <section className="span-2 config-dynamic-section">
                  <p className="muted">
                    Le forfait n&apos;a pas de credits. Les transactions seront calculees depuis les cours reserves.
                  </p>
                </section>
              ) : null}
            </div>
          </article>

          <article className="card formula-editor-side">
            <h3>Paiement(s)</h3>
            <p className="muted">Selectionnez un ou plusieurs moyens de paiement autorises pour cette formule.</p>
            <div className="config-payment-grid">
              {paymentMethods.map((method) => (
                <label key={method.code} className="checkline config-payment-line">
                  <input
                    type="checkbox"
                    name="payment_methods"
                    value={method.code}
                    defaultChecked={selectedPaymentCodes.includes(method.code)}
                  />
                  <span>{method.label}</span>
                </label>
              ))}
            </div>
          </article>
        </section>

        <section className="card">
          <h3>Restriction d'acces</h3>
          <div className="row spread">
            <p className="muted">Ajoutez autant de restrictions que necessaire puis configurez periode + activites.</p>
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
              <span aria-hidden="true">＋</span> Ajouter
            </button>
          </div>

          <div className="formula-dynamic-list">
            {restrictionRows.map((row, index) => (
              <article key={row.key} className="config-restriction-row">
                <input type="hidden" name="restriction_row_key" value={row.key} />
                <div className="row spread">
                  <h4>
                    <span aria-hidden="true">✎</span> Restriction {index + 1}
                  </h4>
                  <button
                    type="button"
                    className="danger small-btn formula-row-delete-btn"
                    onClick={() => setRestrictionRows((prev) => prev.filter((item) => item.key !== row.key))}
                    disabled={restrictionRows.length === 1}
                    title="Supprimer cette restriction"
                  >
                    <span className="formula-row-delete-icon" aria-hidden="true">
                      🗑
                    </span>
                    <span>Supprimer</span>
                  </button>
                </div>

                <div className="config-restriction-form-grid">
                  <label>
                    Type
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
                      <option value="">Aucune</option>
                      {RESTRICTION_PERIOD_OPTIONS.map((option) => (
                        <option key={`restriction-period-option-${option.value}`} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    NB cours max
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
                    Activites
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
                    <small className="muted">Laissez vide pour appliquer la restriction a toutes les activites.</small>
                  </label>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="card formula-editor-footer">
          <div className="row">
            <button type="submit">{mode === "create" ? "Creer" : "Enregistrer"}</button>
            <Link className="reset-link" href={backHref}>
              Annuler
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
                Dupliquer
              </button>
            </form>

            <form action={disableAdminFormulaAction}>
              <input type="hidden" name="formula_id" value={formula.id} />
              <input type="hidden" name="return_to" value={returnTo} />
              <button className="danger" type="submit" disabled={!formula.active}>
                Desactiver
              </button>
            </form>
          </div>
        </section>
      ) : null}
    </section>
  );
}
