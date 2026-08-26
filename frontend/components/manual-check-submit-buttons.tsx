"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";

type ManualCheckSubmitButtonsProps = {
  repeatLabel: string;
  finishLabel: string;
  pendingLabel: string;
};

export default function ManualCheckSubmitButtons({
  repeatLabel,
  finishLabel,
  pendingLabel,
}: ManualCheckSubmitButtonsProps): JSX.Element {
  const { pending } = useFormStatus();
  const [submitIntent, setSubmitIntent] = useState<"repeat" | "finish" | null>(null);

  return (
    <>
      {pending ? (
        <span className="manual-check-submit-status" role="status" aria-live="polite">
          {pendingLabel}
        </span>
      ) : null}
      <button
        type="submit"
        name="submit_intent"
        value="save_and_add_check"
        data-check-repeat-submit
        hidden
        className="secondary"
        disabled={pending}
        aria-disabled={pending}
        onClick={() => setSubmitIntent("repeat")}
      >
        {pending && submitIntent === "repeat" ? pendingLabel : repeatLabel}
      </button>
      <button
        type="submit"
        name="submit_intent"
        value="save"
        disabled={pending}
        aria-disabled={pending}
        onClick={() => setSubmitIntent("finish")}
      >
        {pending && submitIntent === "finish" ? pendingLabel : finishLabel}
      </button>
    </>
  );
}
