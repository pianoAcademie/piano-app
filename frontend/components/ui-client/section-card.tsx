import type { ReactNode } from "react";

type SectionCardProps = {
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
};

export default function SectionCard({ title, action, className = "", children }: SectionCardProps): JSX.Element {
  return (
    <section className={`client-section-card ${className}`.trim()}>
      <header className="client-section-card-header">
        <h2>{title}</h2>
        {action ? <div className="client-section-card-action">{action}</div> : null}
      </header>
      <div className="client-section-card-body">{children}</div>
    </section>
  );
}
