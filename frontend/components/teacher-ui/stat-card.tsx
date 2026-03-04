import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: ReactNode;
  hint?: string;
};

export default function StatCard({ label, value, hint }: StatCardProps): JSX.Element {
  return (
    <article className="teacher-stat-card card">
      <p className="teacher-stat-card-label">{label}</p>
      <strong className="teacher-stat-card-value">{value}</strong>
      {hint ? <small className="muted">{hint}</small> : null}
    </article>
  );
}
