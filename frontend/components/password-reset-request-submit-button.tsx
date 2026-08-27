"use client";

import { useEffect, useState } from "react";
import { useFormStatus } from "react-dom";

type PasswordResetRequestSubmitButtonProps = {
  label: string;
  pendingLabel: string;
  cooldownTemplate: string;
  initialCooldownSeconds?: number;
};

export default function PasswordResetRequestSubmitButton({
  label,
  pendingLabel,
  cooldownTemplate,
  initialCooldownSeconds = 0,
}: PasswordResetRequestSubmitButtonProps): JSX.Element {
  const { pending } = useFormStatus();
  const [remainingSeconds, setRemainingSeconds] = useState(Math.max(0, initialCooldownSeconds));

  useEffect(() => {
    if (remainingSeconds <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setRemainingSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [remainingSeconds]);

  const coolingDown = remainingSeconds > 0;
  const buttonLabel = pending
    ? pendingLabel
    : coolingDown
      ? cooldownTemplate.replace("{seconds}", String(remainingSeconds))
      : label;

  return (
    <button type="submit" disabled={pending || coolingDown} aria-disabled={pending || coolingDown}>
      {buttonLabel}
    </button>
  );
}
