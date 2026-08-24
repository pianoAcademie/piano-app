"use client";

import { useEffect, useRef, useState } from "react";

import { localeForUiLanguage, type UiLanguage, uiText } from "../lib/ui-i18n";

type InvoiceFrequency = "MONTHLY" | "BIMONTHLY" | "QUARTERLY" | "YEARLY";
type BillingTiming = "UPCOMING_LESSONS" | "PREVIOUS_LESSONS";
type DueDateRule = "SAME_DAY_ISSUE" | "X_DAYS_AFTER_ISSUE";

type PreviewValues = {
  nextRun: string;
  startDate: string;
  endDate: string;
  dueDate: string;
  billingTiming: BillingTiming;
};

type AutomaticInvoicePreviewProps = {
  language: UiLanguage;
  today: string;
  initialCycleStart: string;
  initialFrequency: InvoiceFrequency;
  initialBillingTiming: BillingTiming;
  initialDueDateRule: DueDateRule;
  initialDueDateDaysOffset: number;
};

function isDateInput(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function parseDateInput(value: string): Date | null {
  if (!isDateInput(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDateInput(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function addMonths(value: Date, months: number): Date {
  const next = new Date(value.getTime());
  const sourceDay = next.getUTCDate();
  next.setUTCDate(1);
  next.setUTCMonth(next.getUTCMonth() + months);
  const daysInMonth = new Date(Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 0)).getUTCDate();
  next.setUTCDate(Math.min(sourceDay, daysInMonth));
  return next;
}

function frequencyMonths(frequency: InvoiceFrequency): number {
  if (frequency === "BIMONTHLY") {
    return 2;
  }
  if (frequency === "QUARTERLY") {
    return 3;
  }
  if (frequency === "YEARLY") {
    return 12;
  }
  return 1;
}

function normalizeFrequency(value: FormDataEntryValue | null, fallback: InvoiceFrequency): InvoiceFrequency {
  return value === "MONTHLY" || value === "BIMONTHLY" || value === "QUARTERLY" || value === "YEARLY"
    ? value
    : fallback;
}

function normalizeBillingTiming(value: FormDataEntryValue | null, fallback: BillingTiming): BillingTiming {
  return value === "UPCOMING_LESSONS" || value === "PREVIOUS_LESSONS" ? value : fallback;
}

function normalizeDueDateRule(value: FormDataEntryValue | null, fallback: DueDateRule): DueDateRule {
  return value === "SAME_DAY_ISSUE" || value === "X_DAYS_AFTER_ISSUE" ? value : fallback;
}

function normalizeDueDateDaysOffset(value: FormDataEntryValue | null, fallback: number): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(365, Math.max(0, parsed));
}

function calculatePreview({
  today,
  cycleStart,
  frequency,
  billingTiming,
  dueDateRule,
  dueDateDaysOffset,
}: {
  today: string;
  cycleStart: string;
  frequency: InvoiceFrequency;
  billingTiming: BillingTiming;
  dueDateRule: DueDateRule;
  dueDateDaysOffset: number;
}): PreviewValues {
  const cycleStartDate = parseDateInput(cycleStart);
  const todayDate = parseDateInput(today);
  if (!cycleStartDate || !todayDate) {
    return {
      nextRun: cycleStart,
      startDate: cycleStart,
      endDate: cycleStart,
      dueDate: cycleStart,
      billingTiming,
    };
  }

  const months = frequencyMonths(frequency);
  let nextRunDate = cycleStartDate;
  let guard = 0;
  while (nextRunDate.getTime() < todayDate.getTime() && guard < 240) {
    nextRunDate = addMonths(nextRunDate, months);
    guard += 1;
  }

  const periodStart = billingTiming === "PREVIOUS_LESSONS" ? addMonths(nextRunDate, -months) : nextRunDate;
  const periodEnd = billingTiming === "PREVIOUS_LESSONS" ? nextRunDate : addMonths(nextRunDate, months);
  const dueDate = dueDateRule === "X_DAYS_AFTER_ISSUE" ? addDays(nextRunDate, dueDateDaysOffset) : nextRunDate;

  return {
    nextRun: formatDateInput(nextRunDate),
    startDate: formatDateInput(periodStart),
    endDate: formatDateInput(periodEnd),
    dueDate: formatDateInput(dueDate),
    billingTiming,
  };
}

function formatDateLabel(value: string, language: UiLanguage): string {
  const parsed = parseDateInput(value);
  if (!parsed) {
    return value;
  }
  return parsed.toLocaleDateString(localeForUiLanguage(language), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
}

export default function AutomaticInvoicePreview({
  language,
  today,
  initialCycleStart,
  initialFrequency,
  initialBillingTiming,
  initialDueDateRule,
  initialDueDateDaysOffset,
}: AutomaticInvoicePreviewProps): JSX.Element {
  const previewRef = useRef<HTMLElement>(null);
  const issuedDateRef = useRef<HTMLInputElement>(null);
  const startDateRef = useRef<HTMLInputElement>(null);
  const endDateRef = useRef<HTMLInputElement>(null);
  const dueDateRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<PreviewValues>(() =>
    calculatePreview({
      today,
      cycleStart: initialCycleStart,
      frequency: initialFrequency,
      billingTiming: initialBillingTiming,
      dueDateRule: initialDueDateRule,
      dueDateDaysOffset: initialDueDateDaysOffset,
    }),
  );

  useEffect(() => {
    const form = previewRef.current?.closest("form");
    if (!form) {
      return;
    }

    const refreshPreview = () => {
      const data = new FormData(form);
      const cycleStartValue = String(data.get("auto_cycle_start_date") ?? initialCycleStart);
      const nextPreview = calculatePreview({
        today,
        cycleStart: isDateInput(cycleStartValue) ? cycleStartValue : initialCycleStart,
        frequency: normalizeFrequency(data.get("auto_frequency"), initialFrequency),
        billingTiming: normalizeBillingTiming(data.get("auto_billing_timing"), initialBillingTiming),
        dueDateRule: normalizeDueDateRule(data.get("auto_due_date_rule_type"), initialDueDateRule),
        dueDateDaysOffset: normalizeDueDateDaysOffset(
          data.get("auto_due_date_days_offset"),
          initialDueDateDaysOffset,
        ),
      });

      // Synchronize the submitted values immediately too, including when the
      // administrator changes a field and validates the form straight away.
      if (issuedDateRef.current) issuedDateRef.current.value = nextPreview.nextRun;
      if (startDateRef.current) startDateRef.current.value = nextPreview.startDate;
      if (endDateRef.current) endDateRef.current.value = nextPreview.endDate;
      if (dueDateRef.current) dueDateRef.current.value = nextPreview.dueDate;
      setPreview(nextPreview);
    };

    refreshPreview();
    form.addEventListener("input", refreshPreview);
    form.addEventListener("change", refreshPreview);
    form.addEventListener("submit", refreshPreview);
    return () => {
      form.removeEventListener("input", refreshPreview);
      form.removeEventListener("change", refreshPreview);
      form.removeEventListener("submit", refreshPreview);
    };
  }, [
    initialBillingTiming,
    initialCycleStart,
    initialDueDateDaysOffset,
    initialDueDateRule,
    initialFrequency,
    today,
  ]);

  return (
    <>
      <input ref={issuedDateRef} type="hidden" name="issued_date" value={preview.nextRun} />
      <input ref={startDateRef} type="hidden" name="start_date" value={preview.startDate} />
      <input ref={endDateRef} type="hidden" name="end_date" value={preview.endDate} />
      <input ref={dueDateRef} type="hidden" name="due_date" value={preview.dueDate} />
      <input type="hidden" name="no_due_date" value="false" />

      <article
        ref={previewRef}
        className="card modal-card invoice-wizard-card span-2"
        aria-live="polite"
        aria-atomic="true"
      >
        <h4>{uiText(language, "admin.client_detail.invoice_preview_section")}</h4>
        <div className="grid cols-2">
          <p>
            {uiText(language, "admin.client_detail.invoice_preview_next_run", {
              date: formatDateLabel(preview.nextRun, language),
            })}
          </p>
          <p>
            {uiText(language, "admin.client_detail.invoice_preview_period", {
              start: formatDateLabel(preview.startDate, language),
              end: formatDateLabel(preview.endDate, language),
            })}
          </p>
          <p>
            {uiText(language, "admin.client_detail.invoice_preview_due", {
              date: formatDateLabel(preview.dueDate, language),
            })}
          </p>
          <p>
            {uiText(language, "admin.client_detail.invoice_preview_mode", {
              mode:
                preview.billingTiming === "PREVIOUS_LESSONS"
                  ? uiText(language, "admin.client_detail.invoice_billing_previous")
                  : uiText(language, "admin.client_detail.invoice_billing_upcoming"),
            })}
          </p>
        </div>
      </article>
    </>
  );
}
