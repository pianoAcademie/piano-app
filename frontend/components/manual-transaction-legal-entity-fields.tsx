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

type EmailPreview = {
  subject: string;
  body: string;
};

type ManualTransactionLegalEntityFieldsProps = {
  legalEntities: LegalEntityOption[];
  paymentMethods?: PaymentMethodOption[];
  paymentMethodRequired?: boolean;
  initialPaymentMethodCode?: string;
  initialLegalEntityId?: string | null;
  reconcilableInvoices?: ReconcilableInvoiceOption[];
  showReconciliation?: boolean;
  showReceiptEmailOption?: boolean;
  clientDisplayName?: string;
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
  showReceiptEmailOption = false,
  clientDisplayName,
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
        checkDepositMonth: "Expected deposit month (optional)",
        checkDepositMonthPlaceholder: "Month",
        checkDepositYearPlaceholder: "Year",
        checkDepositHelp: "When filled, the payment label and comment are prepared automatically.",
        receiptEmailGeneric: "Send a receipt email to the client",
        receiptEmailCheck: "Notify the client that the check has been received",
        emailPreviewTitle: "Email preview",
        emailPreviewSubject: "Subject",
        emailPreviewBody: "Message",
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
        checkDepositMonth: "Mois de depot prevu (optionnel)",
        checkDepositMonthPlaceholder: "Mois",
        checkDepositYearPlaceholder: "Annee",
        checkDepositHelp: "Si renseigne, le libelle et le commentaire du paiement sont prepares automatiquement.",
        receiptEmailGeneric: "Envoyer un recu par courriel au client",
        receiptEmailCheck: "Notifier le client que le cheque a bien ete recu",
        emailPreviewTitle: "Apercu du mail",
        emailPreviewSubject: "Objet",
        emailPreviewBody: "Message",
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
  const [checkDepositMonth, setCheckDepositMonth] = useState<string>("");
  const [checkDepositYear, setCheckDepositYear] = useState<string>(String(new Date().getFullYear()));
  const [receiptEmailChecked, setReceiptEmailChecked] = useState<boolean>(false);
  const [checkEmailPreview, setCheckEmailPreview] = useState<EmailPreview | null>(null);
  const receiptEmailTouchedRef = useRef<boolean>(false);
  const lastAutoCheckDescriptionRef = useRef<string>("");
  const lastAutoCheckLabelRef = useRef<string>("");

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

  const singleLegalEntity = legalEntities.length === 1 ? legalEntities[0] : null;
  const defaultLegalEntity =
    legalEntities.find((entity) => normalizeLegalEntityName(entity.name) === "pianoacademie") ?? null;
  const fallbackLegalEntity =
    derivedLegalEntityId === null && !manualLegalEntityId ? singleLegalEntity ?? defaultLegalEntity : null;
  const fallbackLegalEntityId = fallbackLegalEntity?.id ?? null;
  const fallbackLegalEntityName = fallbackLegalEntity?.name ?? null;
  const finalLegalEntityId = derivedLegalEntityId ?? fallbackLegalEntityId ?? manualLegalEntityId;
  const finalLegalEntityName = derivedLegalEntityName ?? fallbackLegalEntityName;
  const showManualSelector = derivedLegalEntityId === null && fallbackLegalEntityId === null;
  const isCheckPayment = paymentMethodCode.trim().toUpperCase() === "CHECK";
  const checkDepositLabel =
    checkDepositMonth && checkDepositYear
      ? formatMonthYearLabel(checkDepositMonth, checkDepositYear, resolvedLanguage)
      : "";
  const previewClientName = (clientDisplayName || "").trim() || "client";
  const checkDepositYearOptions = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, index) => String(currentYear + index));
  }, []);

  useEffect(() => {
    const form = rootRef.current?.closest("form");
    if (!form || !isCheckPayment || !checkDepositLabel) {
      return;
    }
    const descriptionField = form.querySelector<HTMLTextAreaElement>("textarea[name='description']");
    const labelField = form.querySelector<HTMLInputElement>("input[name='label']");
    const occurredAtField = form.querySelector<HTMLInputElement>("input[name='occurred_at']");
    const receivedLabel = formatInputDateLabel(occurredAtField?.value || "", resolvedLanguage);
    const autoText = isEnglish
      ? `Check received on ${receivedLabel} - to deposit in ${checkDepositLabel}`
      : `Cheque recu le ${receivedLabel} - a deposer en ${checkDepositLabel}`;

    if (
      descriptionField &&
      (!descriptionField.value.trim() || descriptionField.value === lastAutoCheckDescriptionRef.current)
    ) {
      descriptionField.value = autoText;
      lastAutoCheckDescriptionRef.current = autoText;
    }
    if (labelField && (!labelField.value.trim() || labelField.value === lastAutoCheckLabelRef.current)) {
      labelField.value = autoText;
      lastAutoCheckLabelRef.current = autoText;
    }
  }, [checkDepositLabel, isCheckPayment, resolvedLanguage, isEnglish]);

  useEffect(() => {
    if (!showReceiptEmailOption || receiptEmailTouchedRef.current) {
      return;
    }
    setReceiptEmailChecked(isCheckPayment);
  }, [isCheckPayment, showReceiptEmailOption]);

  useEffect(() => {
    if (!isCheckPayment || !receiptEmailChecked) {
      setCheckEmailPreview(null);
      return undefined;
    }
    const form = rootRef.current?.closest("form");
    if (!form) {
      setCheckEmailPreview(null);
      return undefined;
    }

    const updatePreview = () => {
      const amount = form.querySelector<HTMLInputElement>("input[name='amount_incl_vat']")?.value || "";
      const currency = form.querySelector<HTMLInputElement>("input[name='currency']")?.value || "EUR";
      const occurredAt = form.querySelector<HTMLInputElement>("input[name='occurred_at']")?.value || "";
      const description = form.querySelector<HTMLTextAreaElement>("textarea[name='description']")?.value.trim() || "";
      const depositLabel = form.querySelector<HTMLInputElement>("input[name='check_deposit_label']")?.value.trim() || "";
      const amountLabel = formatAmountLabel(amount, currency, resolvedLanguage);
      const receivedLabel = formatInputDateLabel(occurredAt, resolvedLanguage);
      const subject = isEnglish ? `Check received - ${previewClientName}` : `Reception de votre cheque - ${previewClientName}`;
      const bodyLines = isEnglish
        ? [
            `Hello ${previewClientName},`,
            "",
            `We confirm that we have received your check for ${amountLabel}.`,
            `Date received: ${receivedLabel}.`,
            "",
            depositLabel
              ? `This message only confirms receipt of the check. It will be cashed when deposited at the bank as planned during ${depositLabel}.`
              : "This message only confirms receipt of the check. It will be cashed when it is deposited at the bank.",
          ]
        : [
            `Bonjour ${previewClientName},`,
            "",
            `Nous confirmons la bonne reception de votre cheque de ${amountLabel}.`,
            `Date de reception: ${receivedLabel}.`,
            "",
            depositLabel
              ? `Ce message confirme uniquement la reception du cheque. L'encaissement interviendra lors du depot en banque prevu durant ${depositLabel}.`
              : "Ce message confirme uniquement la reception du cheque. L'encaissement interviendra lors du depot en banque.",
          ];
      if (description) {
        bodyLines.push("", isEnglish ? `Tracking note: ${description}` : `Information de suivi: ${description}`);
      }
      bodyLines.push("", isEnglish ? "Best regards," : "Cordialement,");
      setCheckEmailPreview({ subject, body: bodyLines.join("\n") });
    };

    updatePreview();
    form.addEventListener("input", updatePreview);
    form.addEventListener("change", updatePreview);
    return () => {
      form.removeEventListener("input", updatePreview);
      form.removeEventListener("change", updatePreview);
    };
  }, [isCheckPayment, receiptEmailChecked, resolvedLanguage, isEnglish, previewClientName, checkDepositLabel]);

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

      {isCheckPayment ? (
        <>
          <div className="span-2 grid">
            <input type="hidden" name="check_deposit_label" value={checkDepositLabel} />
            <label>
              {text.checkDepositMonth}
              <select name="check_deposit_month" value={checkDepositMonth} onChange={(event) => setCheckDepositMonth(event.currentTarget.value)}>
                <option value="">{text.checkDepositMonthPlaceholder}</option>
                {monthOptions(resolvedLanguage).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {text.checkDepositYearPlaceholder}
              <select name="check_deposit_year" value={checkDepositYear} onChange={(event) => setCheckDepositYear(event.currentTarget.value)}>
                {checkDepositYearOptions.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted span-2">{text.checkDepositHelp}</p>
        </>
      ) : null}

      {showReceiptEmailOption ? (
        <>
          <input type="hidden" name="send_receipt_email" value="off" />
          <label className="checkline span-2">
            <input
              type="checkbox"
              name="send_receipt_email"
              value="on"
              checked={receiptEmailChecked}
              onChange={(event) => {
                receiptEmailTouchedRef.current = true;
                setReceiptEmailChecked(event.currentTarget.checked);
              }}
            />
            {isCheckPayment ? text.receiptEmailCheck : text.receiptEmailGeneric}
          </label>
          {isCheckPayment && receiptEmailChecked && checkEmailPreview ? (
            <div className="span-2 flash-info">
              <strong>{text.emailPreviewTitle}</strong>
              <p>
                <strong>{text.emailPreviewSubject}:</strong> {checkEmailPreview.subject}
              </p>
              <p>
                <strong>{text.emailPreviewBody}:</strong>
              </p>
              <pre className="quote-email-preview-body quote-email-preview-text">{checkEmailPreview.body}</pre>
            </div>
          ) : null}
        </>
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
            <input type="text" value={finalLegalEntityName ?? finalLegalEntityId ?? ""} readOnly />
            <input type="hidden" name="legal_entity_id" value={finalLegalEntityId} />
          </>
        )}
      </label>
      {blockingError ? (
        <p className="muted">{blockingError}</p>
      ) : null}
    </div>
  );
}

function formatInputDateLabel(value: string, language: "fr" | "en"): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) {
    return new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR").format(new Date());
  }
  const [, year, month, day] = match;
  return language === "en" ? `${day}/${month}/${year}` : `${day}/${month}/${year}`;
}

function monthOptions(language: "fr" | "en"): Array<{ value: string; label: string }> {
  return Array.from({ length: 12 }, (_, index) => {
    const month = String(index + 1).padStart(2, "0");
    return {
      value: month,
      label: new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", { month: "long" }).format(
        new Date(2026, index, 1),
      ),
    };
  });
}

function formatMonthYearLabel(month: string, year: string, language: "fr" | "en"): string {
  const date = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat(language === "en" ? "en-GB" : "fr-FR", {
    month: "long",
    year: "numeric",
  }).format(date);
}

function formatAmountLabel(value: string, currency: string, language: "fr" | "en"): string {
  const amount = Number(value.trim().replace(",", "."));
  if (!Number.isFinite(amount)) {
    return `0.00 ${currency || "EUR"}`;
  }
  return new Intl.NumberFormat(language === "en" ? "en-GB" : "fr-FR", {
    style: "currency",
    currency: currency || "EUR",
  }).format(amount);
}

function normalizeLegalEntityName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/gi, "")
    .toLowerCase();
}
