"use client";

import { useEffect } from "react";

type ClientKindCreateSyncProps = {
  formId: string;
};

const COMMUNICATION_FIELD_NAMES = [
  "portal_contact_visible",
  "email_opt_in",
  "sms_opt_in",
  "lesson_reminder_email_opt_in",
  "lesson_reminder_sms_opt_in",
] as const;

export default function ClientKindCreateSync({ formId }: ClientKindCreateSyncProps): JSX.Element | null {
  useEffect(() => {
    const form = document.getElementById(formId);
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    const kindSelect = form.querySelector('select[name="client_kind"]');
    if (!(kindSelect instanceof HTMLSelectElement)) {
      return;
    }
    const statusSelect = form.querySelector('select[name="client_status"]');

    const checkboxes = COMMUNICATION_FIELD_NAMES.map((fieldName) =>
      form.querySelector(`input[name="${fieldName}"]`),
    ).filter((element): element is HTMLInputElement => element instanceof HTMLInputElement);

    const applyRules = (): void => {
      const isChild = kindSelect.value.trim().toUpperCase() === "CHILD";
      if (statusSelect instanceof HTMLSelectElement) {
        for (const option of Array.from(statusSelect.options)) {
          if (option.value.trim().toUpperCase() === "RESPONSABLE") {
            option.disabled = isChild;
            if (isChild && statusSelect.value.trim().toUpperCase() === "RESPONSABLE") {
              statusSelect.value = "ACTIVE";
            }
          }
        }
      }
      for (const checkbox of checkboxes) {
        checkbox.disabled = isChild;
        if (isChild) {
          checkbox.checked = false;
        }
      }
    };

    applyRules();
    kindSelect.addEventListener("change", applyRules);
    return () => {
      kindSelect.removeEventListener("change", applyRules);
    };
  }, [formId]);

  return null;
}
