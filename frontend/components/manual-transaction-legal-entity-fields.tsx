"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

type LegalEntityOption = {
  id: string;
  name: string;
};

type PaymentMethodOption = {
  code: string;
  label: string;
  defaultLegalEntityId: string | null;
  defaultLegalEntityName: string | null;
};

type ReconcilableInvoiceOption = {
  noteId: string;
  occurredAtLabel: string;
  totalLabel: string;
  invoiceNumber: string;
  sellerLegalEntityId: string | null;
  sellerLegalEntityName: string | null;
};

type ManualTransactionLegalEntityFieldsProps = {
  legalEntities: LegalEntityOption[];
  paymentMethods?: PaymentMethodOption[];
  paymentMethodRequired?: boolean;
  initialPaymentMethodCode?: string;
  initialLegalEntityId?: string | null;
  reconcilableInvoices?: ReconcilableInvoiceOption[];
  showReconciliation?: boolean;
  language?: "fr" | "en";
};

export default function ManualTransactionLegalEntityFields({
  legalEntities,
  paymentMethods = [],
  paymentMethodRequired = false,
  initialPaymentMethodCode = "",
  initialLegalEntityId = null,
  reconcilableInvoices = [],
  showReconciliation = false,
  language,
}: ManualTransactionLegalEntityFieldsProps): JSX.Element {
  const searchParams = useSearchParams();
  const resolvedLanguage = language ?? (searchParams?.get("lang") === "en" ? "en" : "fr");
  const isEnglish = resolvedLanguage === "en";
  const text = isEnglish
    ? {
        paymentMethodRequired: "Payment method *",
        paymentMethodOptional: "Payment method (optional)",
        select: "Choose...",
        unspecified: "(Not specified)",
        reconciliation: "Invoice reconciliation (optional)",
        selection: "Pick",
        invoiceDate: "Invoice date",
        amount: "Amount",
        invoiceNumber: "Invoice number",
        legalEntity: "Legal entity",
        noInvoice: "No issued invoice waiting for payment matching.",
        markPaid: "Manually mark selected invoices as paid (if the payment amount is sufficient)",
        checkHint: "Checks are tracked as received first. Mark them as cashed from the payment list after bank deposit.",
        reconciliationHint:
          "If payment amount < invoice total(s), they remain unpaid. If payment amount >= invoice total(s), you can validate them as paid.",
        legalEntityRequired: "Legal entity *",
        separatePaymentPerEntity: "Create one payment per legal entity",
        selectedInvoiceEntityUndetermined: "Cannot determine the legal entity for a selected invoice",
      }
    : {
        paymentMethodRequired: "Mode de paiement *",
        paymentMethodOptional: "Mode de paiement (optionnel)",
        select: "Selectionner...",
        unspecified: "(Non precise)",
        reconciliation: "Rapprochement facture (optionnel)",
        selection: "Choix",
        invoiceDate: "Date de facture",
        amount: "Montant",
        invoiceNumber: "Numero de facture",
        legalEntity: "Entite legale",
        noInvoice: "Aucune facture emise en attente de paiement a rapprocher.",
        markPaid: "Marquer manuellement les factures selectionnees comme payees (si montant regle suffisant)",
        checkHint: "Les cheques sont d'abord enregistres comme recus. Passez-les en encaisses depuis la liste des paiements apres depot en banque.",
        reconciliationHint:
          "Si le montant du paiement est inferieur au total des factures, elles restent a payer. S il couvre le total, vous pouvez les valider comme payees.",
        legalEntityRequired: "Entite legale *",
        separatePaymentPerEntity: "Creer un paiement par entite legale",
        selectedInvoiceEntityUndetermined: "Impossible de determiner l'entite juridique d'une facture selectionnee",
      };
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [paymentMethodCode, setPaymentMethodCode] = useState<string>(initialPaymentMethodCode);
  const [manualLegalEntityId, setManualLegalEntityId] = useState<string>(initialLegalEntityId ?? "");
  const [selectedNoteIds, setSelectedNoteIds] = useState<Set<string>>(new Set<string>());

  const paymentDefaultByMethod = useMemo(() => {
    const out = new Map<string, string>();
    for (const method of paymentMethods) {
      const code = String(method.code || "").trim().toUpperCase();
      const entityId = String(method.defaultLegalEntityId || "").trim();
      if (!code || !entityId) {
        continue;
      }
      out.set(code, entityId);
    }
    return out;
  }, [paymentMethods]);

  const invoiceByNoteId = useMemo(() => {
    const out = new Map<string, ReconcilableInvoiceOption>();
    for (const invoice of reconcilableInvoices) {
      out.set(invoice.noteId, invoice);
    }
    return out;
  }, [reconcilableInvoices]);

  const selectedInvoices = useMemo(
    () => Array.from(selectedNoteIds).map((noteId) => invoiceByNoteId.get(noteId)).filter((row): row is ReconcilableInvoiceOption => Boolean(row)),
    [invoiceByNoteId, selectedNoteIds],
  );

  const selectedInvoiceEntityIds = useMemo(() => {
    const out = new Set<string>();
    for (const row of selectedInvoices) {
      if (row.sellerLegalEntityId) {
        out.add(row.sellerLegalEntityId);
      }
    }
    return out;
  }, [selectedInvoices]);

  const hasSelectedInvoiceWithoutEntity = selectedInvoices.some((row) => !row.sellerLegalEntityId);
  const hasMixedSelectedInvoiceEntities = selectedInvoiceEntityIds.size > 1;
  const invoiceDerivedLegalEntityId =
    selectedInvoices.length > 0 && !hasSelectedInvoiceWithoutEntity && selectedInvoiceEntityIds.size === 1
      ? Array.from(selectedInvoiceEntityIds)[0] ?? null
      : null;

  const paymentMethodDerivedLegalEntityId =
    selectedInvoices.length === 0 && paymentMethodCode
      ? (paymentDefaultByMethod.get(paymentMethodCode.trim().toUpperCase()) ?? null)
      : null;

  const derivedLegalEntityId = invoiceDerivedLegalEntityId ?? paymentMethodDerivedLegalEntityId;
  const derivedLegalEntityName = derivedLegalEntityId
    ? (legalEntities.find((entity) => entity.id === derivedLegalEntityId)?.name ?? null)
    : null;

  const blockingError = hasMixedSelectedInvoiceEntities
    ? text.separatePaymentPerEntity
    : hasSelectedInvoiceWithoutEntity
      ? text.selectedInvoiceEntityUndetermined
      : null;

  useEffect(() => {
    const form = rootRef.current?.closest("form");
    if (!form) {
      return undefined;
    }
    const submitButtons = Array.from(form.querySelectorAll("button[type='submit']")) as HTMLButtonElement[];
    const originalStates = submitButtons.map((button) => ({ button, disabled: button.disabled }));
    for (const button of submitButtons) {
      button.disabled = Boolean(blockingError);
    }
    return () => {
      for (const { button, disabled } of originalStates) {
        button.disabled = disabled;
      }
    };
  }, [blockingError]);

  const resolvedLegalEntityId = derivedLegalEntityId ?? manualLegalEntityId;
  const showManualSelector = derivedLegalEntityId === null;
  const isCheckPayment = paymentMethodCode.trim().toUpperCase() === "CHECK";

  return (
    <div ref={rootRef} className="span-2 grid">
      {paymentMethods.length > 0 ? (
        <label>
          {paymentMethodRequired ? text.paymentMethodRequired : text.paymentMethodOptional}
          <select
            name="payment_method_code"
            defaultValue={initialPaymentMethodCode}
            required={paymentMethodRequired}
            onChange={(event) => setPaymentMethodCode(event.currentTarget.value)}
          >
            {paymentMethodRequired ? <option value="" disabled>{text.select}</option> : <option value="">{text.unspecified}</option>}
            {paymentMethods.map((method) => (
              <option key={method.code} value={method.code}>
                {method.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {showReconciliation ? (
        <fieldset className="config-payment-fieldset span-2">
          <legend>{text.reconciliation}</legend>
          {reconcilableInvoices.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th aria-label={text.selection}>{text.selection}</th>
                    <th>{text.invoiceDate}</th>
                    <th>{text.amount}</th>
                    <th>{text.invoiceNumber}</th>
                    <th>{text.legalEntity}</th>
                  </tr>
                </thead>
                <tbody>
                  {reconcilableInvoices.map((row) => (
                    <tr key={`manual-reconcile-${row.noteId}`}>
                      <td>
                        <input
                          type="checkbox"
                          name="reconciled_invoice_note_ids"
                          value={row.noteId}
                          onChange={(event) => {
                            const noteId = row.noteId;
                            const checked = event.currentTarget.checked;
                            setSelectedNoteIds((previous) => {
                              const next = new Set(previous);
                              if (checked) {
                                next.add(noteId);
                              } else {
                                next.delete(noteId);
                              }
                              return next;
                            });
                          }}
                        />
                      </td>
                      <td>{row.occurredAtLabel}</td>
                      <td>{row.totalLabel}</td>
                      <td>{row.invoiceNumber}</td>
                      <td>{row.sellerLegalEntityName || row.sellerLegalEntityId || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">{text.noInvoice}</p>
          )}
          <input type="hidden" name="mark_reconciled_invoices_paid" value="off" />
          <label className="checkline">
            <input type="checkbox" name="mark_reconciled_invoices_paid" value="on" disabled={isCheckPayment} />
            {text.markPaid}
          </label>
          {isCheckPayment ? <p className="muted">{text.checkHint}</p> : null}
          <p className="muted">{text.reconciliationHint}</p>
        </fieldset>
      ) : null}

      <label>
        {text.legalEntityRequired}
        {showManualSelector ? (
          <select
            name="legal_entity_id"
            required
            value={manualLegalEntityId}
            onChange={(event) => setManualLegalEntityId(event.currentTarget.value)}
          >
            <option value="" disabled>{text.select}</option>
            {legalEntities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
        ) : (
          <>
            <input type="text" value={derivedLegalEntityName ?? derivedLegalEntityId ?? ""} readOnly />
            <input type="hidden" name="legal_entity_id" value={resolvedLegalEntityId} />
          </>
        )}
      </label>
      {blockingError ? (
        <p className="muted">{blockingError}</p>
      ) : null}
    </div>
  );
}
