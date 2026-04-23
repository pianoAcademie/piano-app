"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { normalizeUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

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
  language?: UiLanguage | string;
};

export default function ManualTransactionLegalEntityFields({
  legalEntities,
  paymentMethods = [],
  paymentMethodRequired = false,
  initialPaymentMethodCode = "",
  initialLegalEntityId = null,
  reconcilableInvoices = [],
  showReconciliation = false,
  language: languageProp = "fr",
}: ManualTransactionLegalEntityFieldsProps): JSX.Element {
  const language = normalizeUiLanguage(languageProp);
  const t = (key: string, values?: Record<string, string | number>) => uiText(language, key, values);
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
    ? t("admin.client_detail.manual_reconcile_block_mixed_entities")
    : hasSelectedInvoiceWithoutEntity
      ? t("admin.client_detail.manual_reconcile_block_missing_entity")
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

  return (
    <div ref={rootRef} className="span-2 grid">
      {paymentMethods.length > 0 ? (
        <label>
          {paymentMethodRequired ? t("admin.client_detail.manual_payment_method_required") : t("admin.client_detail.manual_payment_method_optional")}
          <select
            name="payment_method_code"
            defaultValue={initialPaymentMethodCode}
            required={paymentMethodRequired}
            onChange={(event) => setPaymentMethodCode(event.currentTarget.value)}
          >
            {paymentMethodRequired ? <option value="" disabled>{t("admin.client_detail.select_placeholder")}</option> : <option value="">{t("admin.client_detail.not_specified")}</option>}
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
          <legend>{t("admin.client_detail.manual_reconcile_title")}</legend>
          {reconcilableInvoices.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th aria-label={t("admin.client_detail.manual_reconcile_selection_aria")}>{t("admin.client_detail.manual_reconcile_selection_short")}</th>
                    <th>{t("admin.client_detail.manual_reconcile_invoice_date")}</th>
                    <th>{t("common.amount")}</th>
                    <th>{t("admin.client_detail.manual_reconcile_invoice_number")}</th>
                    <th>{t("admin.client_detail.manual_reconcile_entity")}</th>
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
                            setSelectedNoteIds((previous) => {
                              const next = new Set(previous);
                              if (event.currentTarget.checked) {
                                next.add(row.noteId);
                              } else {
                                next.delete(row.noteId);
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
            <p className="muted">{t("admin.client_detail.manual_reconcile_empty")}</p>
          )}
          <input type="hidden" name="mark_reconciled_invoices_paid" value="off" />
          <label className="checkline">
            <input type="checkbox" name="mark_reconciled_invoices_paid" value="on" />
            {t("admin.client_detail.manual_reconcile_mark_paid")}
          </label>
          <p className="muted">
            {t("admin.client_detail.manual_reconcile_help")}
          </p>
        </fieldset>
      ) : null}

      <label>
        {t("admin.client_detail.manual_legal_entity_required")}
        {showManualSelector ? (
          <select
            name="legal_entity_id"
            required
            value={manualLegalEntityId}
            onChange={(event) => setManualLegalEntityId(event.currentTarget.value)}
          >
            <option value="" disabled>{t("admin.client_detail.select_placeholder")}</option>
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
