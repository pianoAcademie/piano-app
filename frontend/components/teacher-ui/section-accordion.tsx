import type { ReactNode } from "react";

type SectionAccordionProps = {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  badge?: ReactNode;
  children: ReactNode;
};

export default function SectionAccordion({
  title,
  subtitle,
  defaultOpen = false,
  badge,
  children,
}: SectionAccordionProps): JSX.Element {
  return (
    <details className="teacher-accordion card" open={defaultOpen}>
      <summary>
        <div className="teacher-accordion-title">
          <strong>{title}</strong>
          {subtitle ? <small className="muted">{subtitle}</small> : null}
        </div>
        {badge ? <span>{badge}</span> : null}
      </summary>
      <div className="teacher-accordion-content">{children}</div>
    </details>
  );
}
