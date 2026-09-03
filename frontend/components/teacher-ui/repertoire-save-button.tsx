"use client";

import { useFormStatus } from "react-dom";

type Props = {
  saved?: boolean;
};

export default function RepertoireSaveButton({ saved = false }: Props) {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      className={`ghost teacher-repertoire-save-button${saved ? " is-saved" : ""}`}
      disabled={pending}
      aria-disabled={pending}
    >
      {pending ? <span className="teacher-save-spinner" aria-hidden /> : null}
      {pending ? "Enregistrement…" : saved ? "✓ Progression enregistrée" : "Enregistrer la progression"}
    </button>
  );
}
