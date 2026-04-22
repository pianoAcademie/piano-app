import Link from "next/link";

type BottomTabItem = {
  id: string;
  label: string;
  href: string;
  icon?: string;
};

type BottomTabsProps = {
  items: BottomTabItem[];
  activeId: string;
  ariaLabel?: string;
};

export default function BottomTabs({ items, activeId, ariaLabel = "Navigation" }: BottomTabsProps): JSX.Element {
  return (
    <nav className="teacher-bottom-tabs" aria-label={ariaLabel}>
      {items.map((item) => (
        <Link key={item.id} href={item.href} className={`teacher-bottom-tab ${activeId === item.id ? "active" : ""}`}>
          <span className="teacher-bottom-tab-icon" aria-hidden="true">
            {item.icon ?? "•"}
          </span>
          <span className="teacher-bottom-tab-label">{item.label}</span>
        </Link>
      ))}
    </nav>
  );
}
