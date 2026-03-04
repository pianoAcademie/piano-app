import type { ReactNode } from "react";

type StatCardProps = {
  title: string;
  value: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
};

export default function StatCard({ title, value, subtitle, action }: StatCardProps): JSX.Element {
  return (
    <article className="client-stat-card">
      <small>{title}</small>
      <strong>{value}</strong>
      {subtitle ? <p className="muted">{subtitle}</p> : null}
      {action ? <div className="client-stat-card-action">{action}</div> : null}
    </article>
  );
}
