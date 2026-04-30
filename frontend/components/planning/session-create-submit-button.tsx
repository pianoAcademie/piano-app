"use client";

import { useFormStatus } from "react-dom";

type UiLanguage = "fr" | "en";

export default function SessionCreateSubmitButton({ language = "fr" }: { language?: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();
  const text = language === "en"
    ? { pending: "Creating...", idle: "Create slot" }
    : { pending: "Creation en cours...", idle: "Creer le creneau" };

  return (
    <button type="submit" disabled={pending}>
      {pending ? text.pending : text.idle}
    </button>
  );
}
