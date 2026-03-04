"use client";

import { useState } from "react";

type CopyIdButtonProps = {
  value: string;
  label?: string;
};

export default function CopyIdButton({ value, label = "Copier" }: CopyIdButtonProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button className="ghost" type="button" onClick={handleCopy}>
      {copied ? "Copie" : label}
    </button>
  );
}
