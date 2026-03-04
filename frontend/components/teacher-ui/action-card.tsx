import type { ReactNode } from "react";

type ActionCardProps = {
  title: string;
  subtitle?: string;
  chips?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
};

export default function ActionCard({ title, subtitle, chips, action, children }: ActionCardProps): JSX.Element {
  return (
    <article className="teacher-action-card card">
      <div className="teacher-action-card-head">
        <h2>{title}</h2>
        {chips ? <div className="teacher-action-card-chips">{chips}</div> : null}
      </div>
      {subtitle ? <p className="muted">{subtitle}</p> : null}
      {children}
      {action ? <div className="teacher-action-card-footer">{action}</div> : null}
    </article>
  );
}
