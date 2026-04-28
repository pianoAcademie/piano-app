"use client";

import { useFormStatus } from "react-dom";

type UiLanguage = "fr" | "en";

export default function SessionCreateSubmitButton({ language = "fr" }: { language?: UiLanguage }): JSX.Element {
  const { pending } = useFormStatus();

  return (
    <button type="submit" disabled={pending}>
      {pending
        ? (language === "en" ? "Creating..." : "Creation en cours...")
        : (language === "en" ? "Create slot" : "Creer le creneau")}
    </button>
  );
}
