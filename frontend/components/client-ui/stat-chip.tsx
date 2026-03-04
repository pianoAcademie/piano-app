import type { ReactNode } from "react";

type StatChipProps = {
  label: string;
  value: ReactNode;
  tone?: "default" | "ok" | "warn";
};

export default function StatChip({ label, value, tone = "default" }: StatChipProps): JSX.Element {
  return (
    <span className={`client-stat-chip ${tone}`}>
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}
