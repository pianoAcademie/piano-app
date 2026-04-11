"use client";

import { useFormStatus } from "react-dom";

export default function SessionCreateSubmitButton(): JSX.Element {
  const { pending } = useFormStatus();

  return (
    <button type="submit" disabled={pending}>
      {pending ? "Creation en cours..." : "Creer le creneau"}
    </button>
  );
}
