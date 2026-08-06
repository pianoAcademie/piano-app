"use client";

type ClientSupportButtonProps = {
  label: string;
  className?: string;
  compact?: boolean;
};

export default function ClientSupportButton({ label, className = "", compact = false }: ClientSupportButtonProps): JSX.Element {
  const openSupport = (): void => {
    if (!window.zE) {
      window.location.href = "tel:+33186476088";
      return;
    }
    window.zE("messenger", "show");
    window.zE("messenger", "open");
  };

  return (
    <button type="button" className={className} onClick={openSupport} aria-label={label}>
      {compact ? "💬" : `💬 ${label}`}
    </button>
  );
}
