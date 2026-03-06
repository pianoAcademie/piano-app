"use client";

import { useState } from "react";

type CopyLinkButtonProps = {
  value: string;
  label?: string;
  className?: string;
};

export default function CopyLinkButton({ value, label = "Copier le lien", className = "ghost small-btn" }: CopyLinkButtonProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button type="button" className={className} onClick={handleCopy}>
      {copied ? "Lien copie" : label}
    </button>
  );
}
