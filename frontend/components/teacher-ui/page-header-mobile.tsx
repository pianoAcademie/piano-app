import type { ReactNode } from "react";

type PageHeaderMobileProps = {
  title: string;
  subtitle?: string;
  statusLabel?: string;
  trailing?: ReactNode;
  menu?: ReactNode;
  menuLabel?: string;
};

export default function PageHeaderMobile({
  title,
  subtitle,
  statusLabel,
  trailing,
  menu,
  menuLabel = "Menu",
}: PageHeaderMobileProps): JSX.Element {
  return (
    <header className="teacher-page-header card">
      <div className="teacher-page-header-main">
        <h1>{title}</h1>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      <div className="teacher-page-header-actions">
        {statusLabel ? <span className="teacher-status-pill">{statusLabel}</span> : null}
        {trailing}
        {menu ? (
          <details className="teacher-header-menu">
            <summary aria-label={menuLabel}>⋯</summary>
            <div className="teacher-header-menu-panel">{menu}</div>
          </details>
        ) : null}
      </div>
    </header>
  );
}
