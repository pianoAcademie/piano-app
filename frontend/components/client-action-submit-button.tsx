"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

type ClientActionSubmitButtonProps = {
  children: ReactNode;
  className?: string;
  pendingLabel?: ReactNode;
  title?: string;
};

export default function ClientActionSubmitButton({
  children,
  className,
  pendingLabel,
  title,
}: ClientActionSubmitButtonProps): JSX.Element {
  const { pending } = useFormStatus();

  return (
    <button type="submit" className={className} title={title} disabled={pending} aria-disabled={pending}>
      {pending ? pendingLabel ?? children : children}
    </button>
  );
}
