"use client";

import { useEffect, useState } from "react";
import { useFormStatus } from "react-dom";

import type { UiLanguage } from "../../lib/ui-i18n";

type AttendanceSubmitButtonProps = {
  formId: string;
  language: UiLanguage;
  idleLabel: string;
  targetHref?: string | null;
  className?: string;
  showReadyIcon?: boolean;
};

export function AttendanceSubmitButton({
  formId,
  language,
  idleLabel,
  targetHref,
  className,
  showReadyIcon = true,
}: AttendanceSubmitButtonProps): JSX.Element {
  const [pending, setPending] = useState(false);
  const isEnglish = language === "en";

  useEffect(() => {
    const form = document.getElementById(formId) as HTMLFormElement | null;
    if (!form) {
      return;
    }
    const handleSubmit = (): void => setPending(true);
    form.addEventListener("submit", handleSubmit);
    return () => form.removeEventListener("submit", handleSubmit);
  }, [formId]);

  const submitToTarget = (): void => {
    const form = document.getElementById(formId) as HTMLFormElement | null;
    if (!form || pending) {
      return;
    }
    if (targetHref) {
      const returnTo = form.elements.namedItem("return_to") as HTMLInputElement | null;
      if (returnTo) {
        returnTo.value = targetHref;
      }
    }
    form.requestSubmit();
  };

  return (
    <button
      type="button"
      className={`${className ?? ""} ${pending ? "is-pending" : ""}`.trim()}
      disabled={pending}
      aria-busy={pending}
      onClick={submitToTarget}
    >
      {pending || showReadyIcon ? <span aria-hidden="true">{pending ? "◌" : "✓"}</span> : null}
      {pending ? (isEnglish ? "Saving…" : "Enregistrement…") : idleLabel}
    </button>
  );
}

type PendingFormButtonProps = {
  language: UiLanguage;
  idleLabel: string;
  className?: string;
};

export function PendingFormButton({ language, idleLabel, className }: PendingFormButtonProps): JSX.Element {
  const { pending } = useFormStatus();
  const isEnglish = language === "en";

  return (
    <button type="submit" className={`${className ?? ""} ${pending ? "is-pending" : ""}`.trim()} disabled={pending} aria-busy={pending}>
      <span aria-hidden="true">{pending ? "◌" : "✓"}</span>
      {pending ? (isEnglish ? "Saving…" : "Enregistrement…") : idleLabel}
    </button>
  );
}
