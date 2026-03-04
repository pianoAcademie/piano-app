import type { ReactNode } from "react";

type DrawerFiltersProps = {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
};

export default function DrawerFilters({ title, children, defaultOpen = false, className = "" }: DrawerFiltersProps): JSX.Element {
  return (
    <details className={`client-drawer-filters ${className}`.trim()} open={defaultOpen}>
      <summary>{title}</summary>
      <div className="client-drawer-filters-content">{children}</div>
    </details>
  );
}
