"use client";

import { useState } from "react";

type CopyLinkButtonProps = {
  value: string;
  label?: string;
  copiedLabel?: string;
  className?: string;
};

export default function CopyLinkButton({
  value,
  label = "Copier le lien",
  copiedLabel = "Lien copie",
  className = "ghost small-btn",
}: CopyLinkButtonProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (): Promise<void> => {
    try {
      const resolvedValue = value.startsWith("/") ? `${window.location.origin}${value}` : value;
      await navigator.clipboard.writeText(resolvedValue);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button type="button" className={className} onClick={handleCopy}>
      {copied ? copiedLabel : label}
    </button>
  );
}
