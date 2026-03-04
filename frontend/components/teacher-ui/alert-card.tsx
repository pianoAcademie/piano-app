import type { ReactNode } from "react";

type AlertCardProps = {
  tone?: "error" | "ok" | "warn";
  title?: string;
  children: ReactNode;
};

export default function AlertCard({ tone = "warn", title, children }: AlertCardProps): JSX.Element {
  return (
    <article className={`teacher-alert-card ${tone}`}>
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </article>
  );
}
