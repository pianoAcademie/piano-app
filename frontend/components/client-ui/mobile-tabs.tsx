import type { ReactNode } from "react";

type MobileTabItem = {
  id: string;
  label: string;
  href: string;
  icon?: ReactNode;
};

type MobileTabsProps = {
  items: MobileTabItem[];
  activeId: string;
};

export default function MobileTabs({ items, activeId }: MobileTabsProps): JSX.Element {
  return (
    <nav className="client-mobile-tabs" aria-label="Navigation client mobile">
      {items.map((item) => (
        <a key={item.id} className={`client-mobile-tab ${activeId === item.id ? "active" : ""}`} href={item.href}>
          <span className="client-mobile-tab-icon" aria-hidden="true">
            {item.icon ?? "•"}
          </span>
          <span className="client-mobile-tab-label">{item.label}</span>
        </a>
      ))}
    </nav>
  );
}
