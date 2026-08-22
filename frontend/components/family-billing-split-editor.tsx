"use client";

import { useMemo, useState } from "react";

import { updateFamilyBillingAllocationsAction } from "../lib/actions";
import type { FamilyBillingChildOut } from "../lib/types";


type AllocationType = "PERCENT" | "FIXED" | "REMAINDER";

type RowState = {
  enabled: boolean;
  allocationType: AllocationType;
  value: string;
};

type Props = {
  billingChild: FamilyBillingChildOut;
  returnClientId: string;
  eligibleSiblings: Array<{ id: string; label: string }>;
};

function displayName(person: FamilyBillingChildOut["child"]): string {
  return [person.first_name, person.last_name].filter(Boolean).join(" ") || person.email || "Compte sans nom";
}

function normalizedNumber(value: string): number {
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function FamilyBillingSplitEditor({ billingChild, returnClientId, eligibleSiblings }: Props) {
  const hasSavedSplit = billingChild.payers.filter((payer) => payer.allocation).length >= 2;
  const [rows, setRows] = useState<Record<string, RowState>>(() =>
    Object.fromEntries(
      billingChild.payers.map((payer) => [
        payer.adult.id,
        {
          enabled: Boolean(payer.allocation),
          allocationType: payer.allocation?.allocation_type ?? "PERCENT",
          value:
            payer.allocation?.allocation_value ??
            (payer.is_primary_billing_recipient && !hasSavedSplit ? "100" : ""),
        },
      ]),
    ),
  );

  const summary = useMemo(() => {
    const enabledRows = billingChild.payers
      .map((payer) => ({ payer, state: rows[payer.adult.id] }))
      .filter((row) => row.state?.enabled);
    const percentTotal = enabledRows
      .filter((row) => row.state.allocationType === "PERCENT")
      .reduce((sum, row) => sum + normalizedNumber(row.state.value), 0);
    const fixedTotal = enabledRows
      .filter((row) => row.state.allocationType === "FIXED")
      .reduce((sum, row) => sum + normalizedNumber(row.state.value), 0);
    const remainderCount = enabledRows.filter((row) => row.state.allocationType === "REMAINDER").length;
    let error = "";
    if (enabledRows.length < 2) {
      error = "Sélectionnez au moins deux payeurs.";
    } else if (remainderCount > 1) {
      error = "Un seul payeur peut recevoir le solde.";
    } else if (enabledRows.some((row) => row.state.allocationType !== "REMAINDER" && normalizedNumber(row.state.value) <= 0)) {
      error = "Renseignez une valeur supérieure à zéro pour chaque payeur sélectionné.";
    } else if (percentTotal > 100) {
      error = "Les pourcentages dépassent 100 %.";
    } else if (fixedTotal > 0 && remainderCount !== 1) {
      error = "Avec un montant fixe, choisissez un payeur pour le solde restant.";
    } else if (remainderCount === 0 && (fixedTotal > 0 || Math.abs(percentTotal - 100) > 0.001)) {
      error = "Sans payeur du solde, les pourcentages doivent totaliser 100 %.";
    }
    return { enabledRows, percentTotal, fixedTotal, remainderCount, error };
  }, [billingChild.payers, rows]);

  const setRow = (payerId: string, patch: Partial<RowState>) => {
    setRows((current) => ({ ...current, [payerId]: { ...current[payerId], ...patch } }));
  };

  const applyEqualSplit = () => {
    const payerCount = billingChild.payers.length;
    if (payerCount < 2) return;
    const baseShare = Math.floor((10000 / payerCount)) / 100;
    setRows(
      Object.fromEntries(
        billingChild.payers.map((payer, index) => [
          payer.adult.id,
          {
            enabled: true,
            allocationType: "PERCENT" as const,
            value: (index === payerCount - 1 ? 100 - baseShare * (payerCount - 1) : baseShare).toFixed(2),
          },
        ]),
      ),
    );
  };

  return (
    <article className="billing-split-editor">
      <div className="row spread billing-split-editor-heading">
        <div>
          <strong>{displayName(billingChild.child)}</strong>
          <p className="muted">Une facture distincte sera générée pour chaque payeur sélectionné.</p>
        </div>
        <span className={`status-pill ${hasSavedSplit ? "status-ok" : "status-off"}`}>
          {hasSavedSplit ? "Répartition active" : "Facturation à un seul payeur"}
        </span>
      </div>

      <form action={updateFamilyBillingAllocationsAction} className="billing-split-form">
        <input type="hidden" name="child_id" value={billingChild.child.id} />
        <input type="hidden" name="return_client_id" value={returnClientId} />
        {billingChild.payers.length >= 2 ? (
          <div className="row billing-split-shortcuts">
            <span className="muted">Répartition rapide :</span>
            <button type="button" className="ghost" onClick={applyEqualSplit}>
              Partage égal {billingChild.payers.length === 2 ? "50 / 50" : `entre ${billingChild.payers.length} payeurs`}
            </button>
          </div>
        ) : null}
        <div className="billing-split-table" role="table" aria-label={`Répartition de ${displayName(billingChild.child)}`}>
          <div className="billing-split-row billing-split-header" role="row">
            <span>Payeur</span>
            <span>Type</span>
            <span>Valeur</span>
          </div>
          {billingChild.payers.map((payer) => {
            const state = rows[payer.adult.id];
            return (
              <div className={`billing-split-row ${state.enabled ? "is-enabled" : ""}`} role="row" key={payer.adult.id}>
                <label className="billing-split-payer">
                  <input
                    type="checkbox"
                    name="payer_id"
                    value={payer.adult.id}
                    checked={state.enabled}
                    onChange={(event) => setRow(payer.adult.id, { enabled: event.target.checked })}
                  />
                  <span>
                    <strong>{displayName(payer.adult)}</strong>
                    <small>{payer.is_primary_billing_recipient ? "Payeur principal actuel" : "Coparent"}</small>
                  </span>
                </label>
                <select
                  name={`allocation_type:${payer.adult.id}`}
                  value={state.allocationType}
                  disabled={!state.enabled}
                  onChange={(event) => setRow(payer.adult.id, { allocationType: event.target.value as AllocationType })}
                >
                  <option value="PERCENT">Pourcentage</option>
                  <option value="FIXED">Montant fixe</option>
                  <option value="REMAINDER">Solde restant</option>
                </select>
                <div className="billing-split-value">
                  {state.allocationType === "REMAINDER" ? (
                    <span className="muted">Calculé automatiquement</span>
                  ) : (
                    <>
                      <input
                        name={`allocation_value:${payer.adult.id}`}
                        type="number"
                        min="0.01"
                        max={state.allocationType === "PERCENT" ? "100" : undefined}
                        step="0.01"
                        inputMode="decimal"
                        value={state.value}
                        disabled={!state.enabled}
                        onChange={(event) => setRow(payer.adult.id, { value: event.target.value })}
                      />
                      <span>{state.allocationType === "PERCENT" ? "%" : "€"}</span>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className={`billing-split-summary ${summary.error ? "has-error" : ""}`} aria-live="polite">
          <span>Pourcentages : <strong>{summary.percentTotal.toFixed(2)} %</strong></span>
          {summary.fixedTotal > 0 ? <span>Montants fixes : <strong>{summary.fixedTotal.toFixed(2)} €</strong></span> : null}
          {summary.remainderCount === 1 ? <span>Le solde sera calculé automatiquement.</span> : null}
          {summary.error ? <span className="billing-split-error">{summary.error}</span> : null}
        </div>

        {eligibleSiblings.length > 0 ? (
          <fieldset className="billing-split-siblings">
            <legend>Appliquer aussi à la fratrie</legend>
            {eligibleSiblings.map((sibling) => (
              <label className="checkline" key={sibling.id}>
                <input type="checkbox" name="apply_to_sibling_id" value={sibling.id} />
                {sibling.label}
              </label>
            ))}
          </fieldset>
        ) : null}

        <div className="row spread">
          {hasSavedSplit ? (
            <button type="submit" className="ghost" name="disable_split" value="1" formNoValidate>
              Revenir à un seul payeur
            </button>
          ) : <span />}
          <button type="submit" disabled={Boolean(summary.error)}>
            Enregistrer la répartition
          </button>
        </div>
      </form>
    </article>
  );
}
