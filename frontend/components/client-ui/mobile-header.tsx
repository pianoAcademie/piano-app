import type { ReactNode } from "react";

type MobileHeaderProps = {
  title: string;
  subtitle?: string;
  menu?: ReactNode;
};

export default function MobileHeader({ title, subtitle, menu }: MobileHeaderProps): JSX.Element {
  return (
    <header className="client-mobile-header card">
      <div className="client-mobile-header-main">
        <h1>{title}</h1>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      <div className="client-mobile-header-actions">
        <details className="client-mobile-menu">
          <summary aria-label="Menu client">⋯</summary>
          <div className="client-mobile-menu-panel">{menu}</div>
        </details>
      </div>
    </header>
  );
}
