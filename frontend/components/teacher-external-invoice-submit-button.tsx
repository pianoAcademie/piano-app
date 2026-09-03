"use client";

import { useFormStatus } from "react-dom";

import type { UiLanguage } from "../lib/ui-i18n";
import { uiText } from "../lib/ui-i18n";

export default function TeacherExternalInvoiceSubmitButton({ language }: { language: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();

  return (
    <div>
      <button type="submit" disabled={pending} aria-disabled={pending}>
        {pending ? uiText(language, "teacher.sending") : uiText(language, "teacher.send_external_invoice")}
      </button>
      {pending ? (
        <p className="muted" role="status" aria-live="polite">
          {uiText(language, "teacher.external_invoice_sending_help")}
        </p>
      ) : null}
    </div>
  );
}
